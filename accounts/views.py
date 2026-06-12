from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import CustomUser, Course, Lesson, Enrollment, EmailOTP, DeletionRequest, PasswordResetOTP, ChatMessage, UploadJob, UploadAuditEvent
import uuid
from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.cache import cache_control, never_cache
import re
import hmac
import logging
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST
from django.utils.html import escape
from urllib.parse import urlparse
import socket
from django_ratelimit.decorators import ratelimit

logger = logging.getLogger(__name__)
import os
from accounts.utils.supabase_storage import upload_pdf


def _log_upload_event(upload_job, event_type, details=None, request=None):
    """Enterprise audit logging for upload lifecycle events."""
    try:
        UploadAuditEvent.objects.create(
            upload_job=upload_job,
            event_type=event_type,
            details=details or {},
            ip_address=request.META.get('REMOTE_ADDR') if request else None,
        )
    except Exception as e:
        logger.warning(f"Failed to log upload event {event_type}: {e}")
from accounts.utils.notification_helper import get_notifications, get_unread_count, mark_read, mark_all_read
import random
from django.db.models import F
from django.conf import settings
from django.core.cache import cache
import cloudinary

# Explicitly configure cloudinary for use in helper functions
if hasattr(settings, 'CLOUDINARY_STORAGE'):
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_STORAGE.get('CLOUD_NAME'),
        api_key=settings.CLOUDINARY_STORAGE.get('API_KEY'),
        api_secret=settings.CLOUDINARY_STORAGE.get('API_SECRET'),
        secure=settings.CLOUDINARY_STORAGE.get('SECURE', True)
    )
from django.core.validators import validate_email as django_validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q
from .utils.pdf_helpers import convert_image_to_pdf

def is_strong_password(password):
    """Enforces enterprise password policy: 8+ chars, Upper, Lower, Special."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r'[@$!%*?&#]', password):
        return False, "Password must contain at least one special character (@$!%*?&#)."
    return True, ""

def validate_avatar_url(url):
    """SSRF guard: only allow Cloudinary and ui-avatars URLs, block private IPs."""
    if not url:
        return True
    ALLOWED_DOMAINS = (
        'res.cloudinary.com',
        'ui-avatars.com',
    )
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname.lower()
        if hostname not in ALLOWED_DOMAINS:
            logger.warning(f"SSRF blocked: disallowed domain {hostname}")
            return False
        try:
            addr = socket.getaddrinfo(hostname, 80)[0][4][0]
            if addr.startswith(('127.', '10.', '172.16.', '192.168.', '169.254.')) or addr == '::1':
                logger.warning(f"SSRF blocked: private IP {addr} for {hostname}")
                return False
        except Exception:
            pass
        return True
    except Exception:
        return False

def log_login_attempt(request, user, status='SUCCESS'):
    """Audit helper for login tracking. All data → Firebase RTDB only."""
    import threading
    import logging
    _logger = logging.getLogger(__name__)
    try:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        device = "Desktop"
        if "Mobile" in user_agent: device = "Mobile"
        elif "Tablet" in user_agent: device = "Tablet"

        user_uid = str(user.uid)
        from .utils.firebase_db import login_history_create
        login_history_create(user_uid, ip, user_agent, device, status)

        if status == 'FAILED':
            def _async_firebase_log():
                try:
                    from .utils.firebase_audit import log_security_event
                    log_security_event('FAILED_LOGIN', f'Failed login for {user.username}', username=user.username, ip=ip)
                except Exception as e:
                    _logger.error("Firebase audit log error: %s", e)
            threading.Thread(target=_async_firebase_log, daemon=True).start()
        else:
            def _async_analytics():
                try:
                    from .utils.firebase_analytics import log_visit
                    log_visit(user)
                except Exception as e:
                    _logger.error("Firebase analytics log error: %s", e)
            threading.Thread(target=_async_analytics, daemon=True).start()
    except Exception as e:
        _logger.error("Login history Firebase write failed: %s", e)

def create_notification(user, message):
    from .utils.firebase_db import notif_create
    notif_create(str(user.uid), "Notification", message, notif_type='general')

def notify_admins(title, message, notif_type='general', action_url=''):
    from .models import CustomUser
    from .utils.firebase_db import notif_create_batch
    admin_uids = list(CustomUser.objects.filter(user_type='ADMIN').values_list('uid', flat=True))
    if admin_uids:
        notif_create_batch([str(uid) for uid in admin_uids], title, message, notif_type, action_url)

def notify_teacher(teacher_uid, title, message, notif_type='general', action_url=''):
    from .utils.firebase_db import notif_create
    notif_create(str(teacher_uid), title, message, notif_type, action_url)

def _is_mobile_ua(request):
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    return any(k in ua for k in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'windows phone', 'opera mini', 'iemobile'])

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        proof_file = request.FILES.get('proof_file')
        phone_number = request.POST.get('phone_number')
        avatar_url = request.POST.get('avatar_url', '')

        logger.debug("Student signup attempt: %s", username)

        ctx = {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number, 'avatar_url': avatar_url}

        if not all([username, email, fullname, password, confirm_password, phone_number, proof_file]):
            messages.error(request, "All fields are required. Please fill in every field to proceed.")
            return render(request, 'accounts/signup.html', ctx)

        try:
            django_validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return render(request, 'accounts/signup.html', ctx)

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            messages.error(request, "Please enter a valid email address with a proper domain (e.g., name@domain.com).")
            return render(request, 'accounts/signup.html', ctx)

        if CustomUser.objects.filter(username__iexact=username).exclude(status='REJECTED').exists():
            messages.error(request, "This username is already taken. Please try another one.")
            return render(request, 'accounts/signup.html', ctx)

        if CustomUser.objects.filter(email__iexact=email).exclude(status='REJECTED').exists():
            messages.error(request, "This email is already registered. If it's yours, try logging in.")
            return render(request, 'accounts/signup.html', ctx)

        if CustomUser.objects.filter(phone_number=phone_number).exclude(status='REJECTED').exists():
            messages.error(request, "This phone number is already associated with an account.")
            return render(request, 'accounts/signup.html', ctx)

        # Phone digits check
        phone_digits = ''.join(filter(str.isdigit, phone_number))
        if len(phone_digits) != 10:
            messages.error(request, "Contact number must be exactly 10 digits.")
            return render(request, 'accounts/signup.html', ctx)

        # Password match & strength
        if password != confirm_password:
            messages.error(request, "Passwords do not match. Please re-enter them correctly.")
            return render(request, 'accounts/signup.html', ctx)

        is_strong, msg = is_strong_password(password)
        if not is_strong:
            messages.error(request, msg)
            return render(request, 'accounts/signup.html', ctx)

        # File validation
        allowed_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif']
        file_ext = os.path.splitext(proof_file.name.lower())[1]
        if file_ext not in allowed_exts:
            messages.error(request, f"Unsupported file format '{file_ext}'. Please upload a PDF or an Image.")
            return render(request, 'accounts/signup.html', ctx)

        is_image = file_ext != '.pdf'
        if is_image and not _is_mobile_ua(request):
            messages.error(request, "Image uploads are only supported on mobile devices. Please upload a PDF from your computer.")
            return render(request, 'accounts/signup.html', ctx)

        # PDF size check (max 200KB) — for direct PDF uploads
        if file_ext == '.pdf' and proof_file.size > 200 * 1024:
            messages.error(request, "Verification document file size must be below 200 KB.")
            return render(request, 'accounts/signup.html', ctx)

        # Image size check (max 10MB) — images are compressed internally but we still need a sanity limit
        if file_ext != '.pdf' and proof_file.size > 10 * 1024 * 1024:
            messages.error(request, "Image file is too large. Please choose a smaller image (max 10 MB).")
            return render(request, 'accounts/signup.html', ctx)

        # 4. Processing File Uploads
        try:
            from accounts.utils.supabase_storage import upload_user_proof
            
            # create User First
            user = CustomUser.objects.create_user(
                username=username, email=email, password=password,
                full_name=fullname, phone_number=phone_number,
                is_active=False, status='PENDING', user_type='STUDENT',
            )

            from accounts.utils.pdf_helpers import convert_image_to_pdf
            from accounts.utils.supabase_storage import upload_user_proof

            if file_ext == '.pdf':
                logger.debug("Uploading PDF to Supabase for %s", username)
                # Final size guard: catch any file >200KB before upload
                if proof_file.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "PDF size exceeds the maximum limit of 200 KB.")
                    return redirect('login')
                if not upload_user_proof(user, proof_file):
                    user.delete()
                    raise Exception("Supabase storage failure.")
            else:
                logger.debug("Processing image (%s) for %s", file_ext, username)
                optimized_pdf = convert_image_to_pdf(proof_file)
                
                if not optimized_pdf:
                    user.delete()
                    raise Exception("PDF conversion failed. File may be corrupted.")

                # Size check on the converted PDF before upload
                if optimized_pdf.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "Unable to convert the image into a PDF smaller than 200 KB. Please choose a smaller or lower-resolution image.")
                    return redirect('login')

                if not upload_user_proof(user, optimized_pdf):
                    user.delete()
                    raise Exception("Supabase upload failed.")
                
                logger.info("Student registration complete: %s", username)

            messages.success(request, "Registration successful! Admin approval pending.")
            notify_admins("New Student Registration", f"New student: {username}.", 'new_student')
            return redirect('login')

        except Exception as e:
            logger.error("Student signup failed for %s: %s", username, str(e), exc_info=True)
            if 'user' in locals() and user: user.delete()
            messages.error(request, "Registration failed due to a system error. Please try again later.")
            return redirect('login')


    return render(request, 'accounts/signup.html')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def teacher_signup_view(request):
    if request.user.is_authenticated:
        return redirect('teacher_dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        proof_file = request.FILES.get('proof_file')
        phone_number = request.POST.get('phone_number')
        avatar_url = request.POST.get('avatar_url', '')

        ctx = {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number, 'avatar_url': avatar_url}

        # 1. Validation Logic
        if not all([username, email, fullname, password, confirm_password, phone_number, proof_file]):
            messages.error(request, "All fields are required. Please fill in every field to proceed.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        # Email format check
        try:
            django_validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            messages.error(request, "Please enter a valid email address with a proper domain (e.g., name@domain.com).")
            return render(request, 'accounts/teacher_signup.html', ctx)

        # Unique checks — exclude REJECTED so users can reapply
        if CustomUser.objects.filter(username__iexact=username).exclude(status='REJECTED').exists():
            messages.error(request, "This username is already taken. Please try another one.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        if CustomUser.objects.filter(email__iexact=email).exclude(status='REJECTED').exists():
            messages.error(request, "This email is already registered. If it's yours, try logging in.")
            return render(request, 'accounts/teacher_signup.html', ctx)
        
        if CustomUser.objects.filter(phone_number=phone_number).exclude(status='REJECTED').exists():
            messages.error(request, "This phone number is already associated with an account.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        # Phone digits check
        phone_digits = ''.join(filter(str.isdigit, phone_number))
        if len(phone_digits) != 10:
            messages.error(request, "Contact number must be exactly 10 digits.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        # Password match & strength
        if password != confirm_password:
            messages.error(request, "Passwords do not match. Please re-enter them correctly.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        is_strong, msg = is_strong_password(password)
        if not is_strong:
            messages.error(request, msg)
            return render(request, 'accounts/teacher_signup.html', ctx)

        # File validation
        allowed_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif']
        file_ext = os.path.splitext(proof_file.name.lower())[1]
        if file_ext not in allowed_exts:
            messages.error(request, f"Unsupported file format '{file_ext}'. Please upload a PDF or an Image.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        is_image = file_ext != '.pdf'
        if is_image and not _is_mobile_ua(request):
            messages.error(request, "Image uploads are only supported on mobile devices. Please upload a PDF from your computer.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        # PDF size check (max 200KB) — for direct PDF uploads
        if file_ext == '.pdf' and proof_file.size > 200 * 1024:
            messages.error(request, "Verification document file size must be below 200 KB.")
            return render(request, 'accounts/teacher_signup.html', ctx)

        # Image size check (max 10MB) — images are compressed internally but we still need a sanity limit
        if file_ext != '.pdf' and proof_file.size > 10 * 1024 * 1024:
            messages.error(request, "Image file is too large. Please choose a smaller image (max 10 MB).")
            return render(request, 'accounts/teacher_signup.html', ctx)

        # 4. Processing File Uploads
        try:
            from accounts.utils.supabase_storage import upload_user_proof
            
            # create User First
            user = CustomUser.objects.create_user(
                username=username, email=email, password=password,
                full_name=fullname, phone_number=phone_number,
                is_active=False, status='PENDING', user_type='TEACHER',
            )

            from accounts.utils.pdf_helpers import convert_image_to_pdf
            from accounts.utils.supabase_storage import upload_user_proof

            if file_ext == '.pdf':
                logger.debug("Teacher signup: uploading PDF to Supabase for %s", username)
                # Final size guard: catch any file >200KB before upload
                if proof_file.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "PDF size exceeds the maximum limit of 200 KB.")
                    return redirect('teacher_login')
                if not upload_user_proof(user, proof_file):
                    user.delete()
                    raise Exception("Supabase storage failure.")
            else:
                logger.debug("Teacher signup: processing image for %s", username)
                optimized_pdf = convert_image_to_pdf(proof_file)
                
                if not optimized_pdf:
                    user.delete()
                    raise Exception("PDF conversion failed. File may be corrupted.")

                # Size check on the converted PDF before upload
                if optimized_pdf.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "Unable to convert the image into a PDF smaller than 200 KB. Please choose a smaller or lower-resolution image.")
                    return redirect('teacher_login')

                if not upload_user_proof(user, optimized_pdf):
                    user.delete()
                    raise Exception("Supabase upload failed.")
                
                logger.info("Teacher registration complete for %s", username)

            messages.success(request, "Teacher registration successful! Admin review pending.")
            notify_admins("New Teacher Registration", f"New teacher: {username}.", 'new_teacher')
            return redirect('teacher_login')

        except Exception as e:
            logger.error("Teacher signup failed for %s: %s", username, str(e), exc_info=True)
            if 'user' in locals() and user: user.delete()
            messages.error(request, "Registration failed due to a system error. Please try again later.")
            return redirect('teacher_login')

    return render(request, 'accounts/teacher_signup.html')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def health_check(request):
    """Deep health check for production monitoring."""
    import time
    from django.db import connection
    
    health_data = {
        "status": "healthy",
        "timestamp": timezone.now().isoformat(),
        "services": {}
    }
    
    # 1. Database Latency
    try:
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_data["services"]["database"] = {"status": "up", "latency_ms": round((time.time() - start) * 1000, 2)}
    except Exception as e:
        health_data["status"] = "partial_failure"
        health_data["services"]["database"] = {"status": "down", "error": str(e)}

    # 2. Supabase Connectivity (Lightweight check)
    try:
        from accounts.utils.supabase_storage import supabase
        res = supabase.storage.list_buckets()
        health_data["services"]["supabase"] = {"status": "up"}
    except Exception as e:
        health_data["status"] = "partial_failure"
        health_data["services"]["supabase"] = {"status": "down", "error": str(e)}

    return JsonResponse(health_data, status=200 if health_data["status"] == "healthy" else 503)


def firebase_health_check(request):
    """Production-safe Firebase RTDB connectivity test: write → read → delete."""
    import time
    import uuid
    import json
    import os

    result = {
        'status': 'running',
        'credential_source': None,
        'db_url': None,
        'write': None,
        'read': None,
        'delete': None,
        'error': None,
    }

    db_url = os.getenv('FIREBASE_RTDB_URL')
    json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
    json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
    result['db_url'] = db_url

    if not db_url:
        result['status'] = 'FAIL'
        result['error'] = 'FIREBASE_RTDB_URL not set'
        return JsonResponse(result, status=503)

    if not json_str and not json_path:
        result['status'] = 'SKIP'
        result['error'] = 'No Firebase credentials configured'
        return JsonResponse(result, status=200)

    try:
        import firebase_admin
        from firebase_admin import credentials, db as rtdb

        app_name = 'health_check_http'
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            app = None

        if app is None:
            cred = None
            if json_str:
                cred = credentials.Certificate(json.loads(json_str))
                result['credential_source'] = 'FIREBASE_SERVICE_ACCOUNT_JSON'
            elif json_path and os.path.exists(json_path):
                cred = credentials.Certificate(json_path)
                result['credential_source'] = f'FIREBASE_SERVICE_ACCOUNT_PATH ({json_path})'
            elif json_path:
                result['status'] = 'FAIL'
                result['error'] = f'FIREBASE_SERVICE_ACCOUNT_PATH file not found at {json_path}'
                return JsonResponse(result, status=503)
            else:
                result['status'] = 'FAIL'
                result['error'] = 'No usable credentials'
                return JsonResponse(result, status=503)

            app = firebase_admin.initialize_app(cred, {'databaseURL': db_url}, name=app_name)

        # Write test
        test_uid = f'hc_{uuid.uuid4().hex[:8]}'
        test_path = f'/health_checks/{test_uid}'
        ref = rtdb.reference(test_path, app=app)
        ref.set({'test': True, 'timestamp': int(time.time() * 1000)})
        result['write'] = 'PASS'

        # Read test
        read_data = ref.get()
        if read_data and read_data.get('test') is True:
            result['read'] = 'PASS'
        else:
            result['read'] = 'FAIL'
            result['status'] = 'FAIL'
            result['error'] = f'Read returned unexpected data: {read_data}'
            return JsonResponse(result, status=503)

        # Delete test
        ref.delete()
        verify = rtdb.reference(test_path, app=app).get()
        result['delete'] = 'PASS' if verify is None else 'PARTIAL'

        result['status'] = 'PASS'
        return JsonResponse(result, status=200)

    except Exception as e:
        result['status'] = 'FAIL'
        result['error'] = str(e)
        return JsonResponse(result, status=503)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def status_page(request):
    """Public status page for stakeholders."""
    # We use a simplified status for public consumption
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status = "OPERATIONAL"
        color = "success"
    except:
        status = "DEGRADED"
        color = "warning"
        
    return render(request, 'accounts/status_page.html', {
        'status': status,
        'color': color,
        'timestamp': timezone.now()
    })

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@csrf_protect
def login_view(request):
    if request.user.is_authenticated:
        if request.user.user_type == 'STUDENT':
            return redirect('dashboard')
        elif request.user.user_type == 'TEACHER':
            return redirect('teacher_dashboard')
        elif getattr(request.user, 'is_staff', False):
            return redirect('admin_dashboard')
        else:
            # Break redirect loops for corrupted sessions by clearing the cookie
            from django.contrib.auth import logout
            logout(request)
            return redirect('login')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, "Please enter your username and password.")
            return render(request, 'accounts/login.html')

        # 1. Generic check — same message whether user exists or password wrong (anti-enumeration)
        user_candidate = CustomUser.objects.filter(username=username).first()
        if not user_candidate or not user_candidate.check_password(password):
            if user_candidate:
                log_login_attempt(request, user_candidate, status='FAILED')
            messages.error(request, "Invalid username or password. Please try again.")
            return render(request, 'accounts/login.html')

        # 2. Check user_type — generic message to prevent type enumeration
        if user_candidate.user_type != 'STUDENT':
            messages.error(request, "Invalid username or password. Please try again.")
            return render(request, 'accounts/login.html')

        # 3. Check account status — only reveal status if credentials are valid
        if user_candidate.status in ('PENDING', 'REJECTED', 'BLOCKED'):
            status_msgs = {
                'PENDING': 'Your account is PENDING approval. Please wait or contact administration.',
                'REJECTED': 'Your account was REJECTED. Please contact admin for details.',
                'BLOCKED': 'Your account has been BLOCKED. Access is restricted.',
            }
            messages.error(request, status_msgs[user_candidate.status])
            return render(request, 'accounts/login.html')

        # 5. Status is ACTIVE, proceed with authentication
        if user_candidate.status == 'ACTIVE':
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Invalidate any previous session — async to not block login response
                if user.current_session_key:
                    old_key = user.current_session_key
                    import threading
                    threading.Thread(
                        target=lambda: __import__('django.contrib.sessions.models', fromlist=['Session']).Session.objects.filter(session_key=old_key).delete(),
                        daemon=True
                    ).start()
                
                login(request, user)
                request.session.set_expiry(0)

                if not request.session.session_key:
                    request.session.save()
                user.current_session_key = request.session.session_key
                user.save(update_fields=['current_session_key'])
                
                log_login_attempt(request, user, status='SUCCESS')
                messages.success(request, f"Welcome back, {user.full_name}!")
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid username or password. Please try again.")
                return render(request, 'accounts/login.html')
            
    return render(request, 'accounts/login.html')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def student_view_auth(request):
    """
    Step-up authentication for Admins/Teachers accessing the Student View.
    Teachers now get direct, password-free access once logged into their panel.
    """
    if request.user.user_type == 'STUDENT':
        return redirect('dashboard')

    # Direct access for Teachers and Admins as requested
    if request.user.user_type == 'TEACHER' or getattr(request.user, 'is_staff', False):
        request.session['student_view_unlocked'] = True
        request.session.set_expiry(0)  # Re-enforce instant expiry
        next_url = request.session.pop('next_student_url', 'dashboard')
        return redirect(next_url)

    if request.session.get('student_view_unlocked'):
        next_url = request.session.get('next_student_url', 'dashboard')
        return redirect(next_url)

    if request.method == 'POST':
        password = request.POST.get('password')
        if request.user.check_password(password):
            request.session['student_view_unlocked'] = True
            request.session.set_expiry(0)  # Re-enforce instant expiry
            next_url = request.session.pop('next_student_url', 'dashboard')
            messages.success(request, "Student View access granted.")
            return redirect(next_url)
        else:
            messages.error(request, "Incorrect password. Please try again.")

    return render(request, 'accounts/student_view_auth.html')


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def teacher_view_auth(request):
    """
    Step-up authentication for Admins accessing the Teacher View.
    They must re-enter their own password to unlock the teacher view session.
    """
    if request.user.user_type == 'TEACHER':
        return redirect('teacher_dashboard')

    if request.session.get('teacher_view_unlocked'):
        next_url = request.session.get('next_teacher_url', 'teacher_dashboard')
        return redirect(next_url)

    if request.method == 'POST':
        password = request.POST.get('password')
        if request.user.check_password(password):
            request.session['teacher_view_unlocked'] = True
            request.session.set_expiry(0)  # Re-enforce instant expiry
            next_url = request.session.pop('next_teacher_url', 'teacher_dashboard')
            messages.success(request, "Teacher View access granted.")
            return redirect(next_url)
        else:
            messages.error(request, "Incorrect password. Please try again.")

    return render(request, 'accounts/teacher_view_auth.html')


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@csrf_protect
def teacher_login_view(request):
    if request.user.is_authenticated:
        if request.user.user_type == 'TEACHER':
            return redirect('teacher_dashboard')
        elif request.user.user_type == 'STUDENT':
            return redirect('dashboard')
        elif getattr(request.user, 'is_staff', False):
            return redirect('admin_dashboard')
        else:
            # Break redirect loops for corrupted sessions
            from django.contrib.auth import logout
            logout(request)
            return redirect('teacher_login')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user_candidate = CustomUser.objects.filter(username=username).first()
        logger.debug("Teacher login attempt: username=%s, user_candidate=%s, is_active=%s, status=%s",
                     username, user_candidate is not None,
                     user_candidate.is_active if user_candidate else 'N/A',
                     user_candidate.status if user_candidate else 'N/A')
        user = authenticate(request, username=username, password=password)
        logger.debug("Authenticate result: user=%s", user is not None)
        
        if user is not None:
            if user.status == 'PENDING':
                logger.debug("Login blocked: PENDING status for %s", username)
                messages.warning(request, "Your account is PENDING approval. Please wait or contact administration.")
                return render(request, 'accounts/teacher_login.html')
            elif user.status == 'REJECTED':
                logger.debug("Login blocked: REJECTED status for %s", username)
                messages.error(request, "Your account was REJECTED. Please contact admin for details.")
                return render(request, 'accounts/teacher_login.html')
            elif user.status == 'BLOCKED':
                logger.debug("Login allowed for BLOCKED teacher %s (auto-reinstate on edit)", username)
                messages.warning(request, "Your account is currently suspended. Your content is hidden from students. Edit and save any course to automatically reinstate your account.")
            
            if user.user_type != 'TEACHER':
                logger.debug("Login blocked: user_type=%s for %s", user.user_type, username)
                messages.error(request, "Invalid username or password. Please try again.")
                return render(request, 'accounts/teacher_login.html')
                
            if user.status in ('ACTIVE', 'BLOCKED'):
                logger.debug("Login success for %s (status=%s)", username, user.status)
                login(request, user)
                request.session.set_expiry(0)
                if user.status == 'BLOCKED':
                    log_login_attempt(request, user, status='SUCCESS_BLOCKED')
                    messages.warning(request, "Your account is suspended. Your content is hidden from students. Edit any course to auto-reinstate.")
                else:
                    log_login_attempt(request, user, status='SUCCESS')
                    messages.success(request, f"Welcome, {user.full_name}!")
                return redirect('teacher_dashboard')
        else:
            reason = "user not found" if not user_candidate else "password mismatch" if not user_candidate.check_password(password) else "backend rejected"
            logger.debug("Login FAILED for %s: %s", username, reason)
            log_login_attempt(request, user_candidate, status='FAILED')
            if user_candidate and user_candidate.status == 'PENDING':
                messages.warning(request, "Your account is PENDING approval. Please wait or contact administration.")
            elif user_candidate and user_candidate.status == 'REJECTED':
                messages.error(request, "Your account was REJECTED. Please contact admin for details.")
            elif user_candidate and user_candidate.status == 'BLOCKED':
                messages.error(request, "Your account has been BLOCKED. Access is restricted.")
            else:
                messages.error(request, "Invalid username or password. Please try again.")
            
    return render(request, 'accounts/teacher_login.html')

from accounts.models import Course, Lesson, Enrollment
from django.db.models import Count, Q, Sum

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
def dashboard_view(request):
    is_unlocked = request.session.get('student_view_unlocked')
    is_admin = getattr(request.user, 'is_staff', False)
    
    if request.user.user_type not in ['STUDENT', 'TEACHER'] and not is_unlocked:
        messages.error(request, "Please use the appropriate portal.")
        return redirect('login')

    if is_unlocked and (is_admin or request.user.user_type == 'TEACHER'):
        courses = Course.objects.filter(is_approved=True, status='PUBLISHED').annotate(
            lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))
        ).only('id', 'uid', 'title', 'image', 'thumbnail', 'category', 'teacher').select_related('teacher')
    elif request.user.user_type == 'TEACHER' and not is_admin:
        courses = Course.objects.filter(teacher=request.user).annotate(
            lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))
        ).only('id', 'uid', 'title', 'image', 'thumbnail', 'status', 'category', 'teacher').select_related('teacher')
    else:
        courses = Course.objects.filter(
            enrollments__user=request.user, 
            is_approved=True, 
            status='PUBLISHED'
        ).annotate(
            lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))
        ).only('id', 'uid', 'title', 'image', 'thumbnail', 'category', 'teacher').select_related('teacher')
    
    search_query = request.GET.get('search', '')
    if search_query:
        courses = courses.filter(title__icontains=search_query)

    # Platform updates — use DB aggregate for total lessons, not Python sum()
    from django.db.models import Sum as DBSum
    total_lessons = courses.aggregate(total=DBSum('lesson_count'))['total'] or 0

    platform_updates = []
    last_cleared = request.session.get('updates_cleared_at')
    since = last_cleared if last_cleared else (timezone.now() - timedelta(hours=24))

    new_courses = Course.objects.filter(
        is_approved=True, status='PUBLISHED', created_at__gte=since
    ).only('title')
    for c in new_courses:
        platform_updates.append(f"\U0001f680 New Course Added: '{c.title}' is now available in the Explore area!")

    if request.user.is_authenticated and request.user.user_type == 'STUDENT':
        new_lessons = Lesson.objects.filter(
            course__enrollments__user=request.user,
            status='APPROVED',
            created_at__gte=since
        ).select_related('course').only('title', 'course__title')
        for l in new_lessons:
            platform_updates.append(f"\U0001f4d6 Content Released: New lesson '{l.title}' added to your course '{l.course.title}'.")

    context = {
        'courses': courses,
        'search_query': search_query,
        'total_lessons': total_lessons,
        'is_admin_preview': is_unlocked,
        'platform_updates': platform_updates,
    }
    return render(request, 'accounts/dashboard.html', context)


def dismiss_updates(request):
    request.session['updates_cleared_at'] = timezone.now().isoformat()
    return JsonResponse({'ok': True})


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_dashboard(request):
    from django.core.paginator import Paginator

    teacher_courses = Course.objects.filter(teacher=request.user)

    # Single aggregate query for all stats — replaces 5+ separate COUNT queries
    stats = teacher_courses.aggregate(
        total_courses=Count('id'),
        published_courses=Count('id', filter=Q(status='PUBLISHED')),
        pending_courses=Count('id', filter=Q(status='PENDING')),
    )

    total_students = Enrollment.objects.filter(course__teacher=request.user).count()
    pending_deletions = DeletionRequest.objects.filter(teacher=request.user, status='PENDING').count()

    courses = teacher_courses.annotate(
        total_lessons=Count('lessons'),
        approved_lessons=Count('lessons', filter=Q(lessons__status='APPROVED')),
        pending_lessons=Count('lessons', filter=Q(lessons__status='PENDING'))
    ).only('id', 'uid', 'title', 'status', 'created_at', 'image', 'thumbnail')

    recent_courses = courses.order_by('-created_at')[:5]

    paginator = Paginator(courses, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'total_courses': stats['total_courses'],
        'published_courses': stats['published_courses'],
        'pending_courses': stats['pending_courses'],
        'total_students': total_students,
        'pending_deletions': pending_deletions,
        'recent_courses': recent_courses,
        'courses': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'teacher_portal/dashboard.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@user_passes_test(lambda u: u.is_authenticated and (u.user_type in ['STUDENT', 'TEACHER'] or getattr(u, 'is_staff', False)), login_url='login')
def student_explore(request):
    # Enrolled course IDs to exclude
    enrolled_ids = Enrollment.objects.filter(user=request.user).values_list('course_id', flat=True)
    
    # All approved and published courses not yet enrolled (exclude BLOCKED teachers)
    explore_courses = Course.objects.filter(status='PUBLISHED', is_approved=True)\
        .exclude(id__in=enrolled_ids)\
        .exclude(teacher__status='BLOCKED')\
        .select_related('teacher')\
        .annotate(lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED')))\
        .only('id', 'uid', 'title', 'description', 'image', 'thumbnail', 'category', 'teacher__username', 'teacher__full_name', 'teacher__image')\
        .order_by('-created_at')
    
    search_query = request.GET.get('search', '')
    if search_query:
        explore_courses = explore_courses.filter(title__icontains=search_query)
        
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(explore_courses, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'accounts/explore_courses.html', {
        'explore_courses': page_obj,
        'page_obj': page_obj,
        'search_query': search_query
    })

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def explore_courses(request):
    # Other teachers' courses for viewing (exclude BLOCKED teachers)
    other_courses_qs = Course.objects.exclude(teacher=request.user)\
        .filter(is_approved=True, status='PUBLISHED')\
        .exclude(teacher__status='BLOCKED')\
        .select_related('teacher')\
        .only('id', 'uid', 'title', 'category', 'status', 'created_at', 'image', 'thumbnail', 'teacher__username', 'teacher__full_name', 'teacher__image')\
        .order_by('-created_at')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(other_courses_qs, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'teacher_portal/explore_courses.html', {
        'other_courses': page_obj,
        'page_obj': page_obj
    })

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def view_other_course(request, course_uid):
    # This is for viewing OTHER teachers' courses
    course = get_object_or_404(Course.objects.select_related('teacher'), uid=course_uid, is_approved=True)
    lessons = course.lessons.all().order_by('order')
    return render(request, 'teacher_portal/view_other_course.html', {
        'course': course,
        'lessons': lessons
    })

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def my_courses(request):
    from django.db.models import Count, Q, Exists, OuterRef
    from .models import CourseDeletionRequest
    pending_req_sub = CourseDeletionRequest.objects.filter(course=OuterRef('pk'), status='PENDING')
    courses_qs = Course.objects.filter(teacher=request.user).exclude(status='DELETED').annotate(
        total_lessons=Count('lessons'),
        approved_lessons=Count('lessons', filter=Q(lessons__status='APPROVED')),
        pending_lessons=Count('lessons', filter=Q(lessons__status='PENDING')),
        rejected_lessons_count=Count('lessons', filter=Q(lessons__status='REJECTED')),
        has_pending_deletion=Exists(pending_req_sub),
    ).only('id', 'uid', 'title', 'status', 'created_at', 'image', 'thumbnail').order_by('-created_at')
    
# Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(courses_qs, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'teacher_portal/my_courses.html', {
        'courses': page_obj,
        'page_obj': page_obj
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
@require_POST
def delete_course(request, course_uid):
    from .models import Course, CourseDeletionRequest
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)

    existing = CourseDeletionRequest.objects.filter(course=course, status='PENDING').first()
    if existing:
        messages.info(request, "A deletion request for this course is already pending admin approval.")
        return redirect('my_courses')

    reason = request.POST.get('reason', '').strip()
    if len(reason) < 20:
        messages.error(request, "Please provide a reason for deletion (minimum 20 characters).")
        return redirect('my_courses')
    if len(reason) > 1000:
        messages.error(request, "Reason must not exceed 1000 characters.")
        return redirect('my_courses')

    CourseDeletionRequest.objects.create(
        course=course,
        teacher=request.user,
        reason=reason,
        status='PENDING',
    )
    messages.success(request, "Course deletion request submitted successfully. Your request is pending administrator approval.")
    notify_admins("Course Deletion Requested", f"Teacher {request.user.username} requested deletion of course '{course.title}'.", 'deletion_request', '/customadmin/course-deletion-requests/')

    return redirect('my_courses')


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def create_course(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        level = request.POST.get('level')
        # Accept either the compressed version (JS succeeded) or raw version (JS fallback)
        thumbnail = request.FILES.get('thumbnail') or request.FILES.get('thumbnail_compressed')

        if not all([title, description, category, level]):
            messages.error(request, "All required fields (title, description, category, level) must be filled.")
            return render(request, 'teacher_portal/create_course.html')

        from .utils.cloudinary_helpers import update_image
        course = Course.objects.create(
            teacher=request.user,
            title=title,
            description=description,
            category=category,
            level=level,
            status='DRAFT'
        )
        if thumbnail:
            if thumbnail.size > 5 * 1024 * 1024:
                messages.warning(request, "Thumbnail exceeds 5MB limit. Course created without custom thumbnail.")
            else:
                success = update_image(course, thumbnail, folder="Neo Learner/courses")
                if not success:
                    logger.warning("Thumbnail upload failed for course '%s' — saved without thumbnail.", title)
                    messages.warning(request, "Thumbnail could not be saved. Course was created without a custom thumbnail.")
        
        messages.success(request, f"Course '{title}' created as draft. You can now add lessons.")
        return redirect('course_lessons', course_uid=course.uid)
    
    return render(request, 'teacher_portal/create_course.html')

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_course(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if course.status == 'DELETED':
        messages.error(request, "Cannot edit a deleted course. Restore it first.")
        return redirect('my_courses')
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        level = request.POST.get('level')
        
        thumbnail_file = None
        if request.FILES.get('thumbnail') or request.FILES.get('thumbnail_compressed'):
            thumbnail_file = request.FILES.get('thumbnail') or request.FILES.get('thumbnail_compressed')
            
        if course.is_approved:
            course.title = title
            course.description = description
            course.category = category
            course.level = level
            
            if thumbnail_file:
                if thumbnail_file.size > 5 * 1024 * 1024:
                    messages.warning(request, "Thumbnail exceeds 5MB limit. Changes saved without thumbnail update.")
                else:
                    from .utils.cloudinary_helpers import update_image
                    success = update_image(course, thumbnail_file, folder="Neo Learner/courses")
                    if not success:
                        logger.warning("Thumbnail update failed for course '%s'", course.title)
            
            course.has_pending_edits = False
            course.save()
            messages.success(request, f"Course '{course.title}' updated successfully!")
        else:
            # Course is not approved yet (draft or rejected), so overwrite main fields directly
            course.title = title
            course.description = description
            course.category = category
            course.level = level
            
            if thumbnail_file:
                if thumbnail_file.size > 5 * 1024 * 1024:
                    messages.warning(request, "Thumbnail exceeds 5MB limit. Edits saved without thumbnail update.")
                else:
                    from .utils.cloudinary_helpers import update_image
                    success = update_image(course, thumbnail_file, folder="Neo Learner/courses")
                    if not success:
                        logger.warning("Thumbnail update failed for course '%s'", course.title)
            
            if course.status == 'REJECTED':
                course.rejection_reason = ""
                
            course.status = 'PENDING'
            course.is_approved = False
            course.save()
            messages.success(request, f"Course '{course.title}' updated successfully!")

        # Auto-reinstate BLOCKED teacher after successful edit
        if request.user.status == 'BLOCKED':
            request.user.status = 'ACTIVE'
            request.user.is_active = True
            request.user.save(update_fields=['status', 'is_active'])
            cache.delete(f"user_status_{request.user.id}")
            messages.success(request, "Your account has been automatically reinstated. Your content is now visible to students again.")
            
        return redirect('my_courses')
        
    return render(request, 'teacher_portal/edit_course.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def course_lessons(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if course.status == 'DELETED':
        messages.error(request, "Cannot access a deleted course.")
        return redirect('my_courses')
    from .models import CourseResource, DeletionRequest
    from itertools import groupby

    lessons = course.lessons.all().only('id', 'title', 'order', 'status', 'is_approved', 'chapter', 'rejection_reason', 'created_at', 'video_url', 'uid', 'video_file', 'youtube_video_id', 'youtube_upload_status', 'upload_status').order_by('chapter', 'order')
    resources = course.resources.filter(is_deleted=False).only('id', 'title', 'category', 'resource_type', 'status', 'is_approved', 'chapter', 'rejection_reason', 'uid', 'compressed_size', 'thumbnail_path').order_by('chapter', 'created_at')

    has_pending_content = lessons.filter(status='PENDING').exists() or resources.filter(status='PENDING').exists()
    any_lesson_rejected = lessons.filter(status='REJECTED').exists() or resources.filter(status='REJECTED').exists()

    # Build deletion request lookup maps
    lesson_ids = list(lessons.values_list('id', flat=True))
    resource_ids = list(resources.values_list('id', flat=True))
    lesson_del_requests = DeletionRequest.objects.filter(
        teacher=request.user, item_type='Lesson', item_id__in=lesson_ids
    )
    resource_del_requests = DeletionRequest.objects.filter(
        teacher=request.user, item_type='Resource', item_id__in=resource_ids
    )
    lesson_dr_map = {dr.item_id: dr for dr in lesson_del_requests}
    resource_dr_map = {dr.item_id: dr for dr in resource_del_requests}

    # Attach deletion request to each lesson/resource
    for lesson in lessons:
        lesson.deletion_request = lesson_dr_map.get(lesson.id)
    for res in resources:
        res.deletion_request = resource_dr_map.get(res.id)

    # Group by chapter
    lessons_list = list(lessons)
    resources_list = list(resources)

    lesson_by_chapter = {}
    for ch, grp in groupby(lessons_list, key=lambda x: x.chapter or ''):
        lesson_by_chapter[ch] = list(grp)

    res_by_chapter = {}
    for ch, grp in groupby(resources_list, key=lambda x: x.chapter or ''):
        res_by_chapter[ch] = list(grp)

    # Order chapters: course.chapters first (teacher-set order), then remaining by creation date
    course_chapters = list(course.chapters or [])
    derived_chapters = set(list(lesson_by_chapter.keys()) + list(res_by_chapter.keys()))
    all_chapter_names = []
    seen = set()
    from datetime import datetime as dt_module
    def _chapter_first_ts(ch_name):
        ts = []
        for l in lesson_by_chapter.get(ch_name, []):
            if l.created_at:
                ts.append(l.created_at)
        for r in res_by_chapter.get(ch_name, []):
            if r.created_at:
                ts.append(r.created_at)
        return ts[0] if ts else dt_module.min
    for name in course_chapters:
        if name and name not in seen:
            seen.add(name)
            all_chapter_names.append(name)
    for name in sorted((d for d in derived_chapters if d), key=_chapter_first_ts):
        if name not in seen:
            seen.add(name)
            all_chapter_names.append(name)

    chapters_data = []
    for ch_name in all_chapter_names:
        ch_lessons = lesson_by_chapter.get(ch_name, [])
        ch_resources = res_by_chapter.get(ch_name, [])

        cat_counts = {}
        for code in ('ENGLISH', 'MALAYALAM', 'ONLINE'):
            cat_items = [r for r in ch_resources if r.category == code]
            cat_counts[code] = {
                'total': len(cat_items),
                'approved': sum(1 for r in cat_items if r.status == 'APPROVED'),
                'pending': sum(1 for r in cat_items if r.status == 'PENDING'),
                'rejected': sum(1 for r in cat_items if r.status == 'REJECTED'),
            }

        chapters_data.append({
            'name': ch_name,
            'videos': ch_lessons,
            'videos_count': len(ch_lessons),
            'videos_approved': sum(1 for l in ch_lessons if l.status == 'APPROVED'),
            'videos_pending': sum(1 for l in ch_lessons if l.status == 'PENDING'),
            'videos_rejected': sum(1 for l in ch_lessons if l.status == 'REJECTED'),
            'resources': ch_resources,
            'resources_count': len(ch_resources),
            'cat_counts': cat_counts,
        })

    return render(request, 'teacher_portal/course_lessons.html', {
        'course': course,
        'chapters': chapters_data,
        'has_pending_content': has_pending_content,
        'any_lesson_rejected': any_lesson_rejected,
        'total_lessons': len(lessons_list),
        'total_resources': len(resources_list),
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
@require_POST
def create_chapter(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    chapter_name = request.POST.get('chapter_name', '').strip()
    if not chapter_name:
        messages.error(request, "Chapter name is required.")
        return redirect('course_lessons', course_uid=course.uid)
    chapters = list(course.chapters or [])
    if chapter_name not in chapters:
        chapters.append(chapter_name)
        course.chapters = chapters
        course.save(update_fields=['chapters'])
        messages.success(request, f"Chapter '{chapter_name}' created!")
    else:
        messages.warning(request, f"Chapter '{chapter_name}' already exists.")
    return redirect('course_lessons', course_uid=course.uid)


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
@require_POST
def rename_chapter(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    old_name = request.POST.get('old_name', '').strip()
    new_name = request.POST.get('new_name', '').strip()
    if not new_name:
        messages.error(request, "New chapter name is required.")
        return redirect('course_lessons', course_uid=course.uid)
    if old_name == new_name:
        messages.info(request, "No change — names are identical.")
        return redirect('course_lessons', course_uid=course.uid)
    chapters = list(course.chapters or [])
    if old_name not in chapters:
        messages.error(request, f"Chapter '{old_name}' not found.")
        return redirect('course_lessons', course_uid=course.uid)
    if new_name in chapters:
        messages.warning(request, f"Chapter '{new_name}' already exists.")
        return redirect('course_lessons', course_uid=course.uid)
    # Rename in master list
    idx = chapters.index(old_name)
    chapters[idx] = new_name
    course.chapters = chapters
    course.save(update_fields=['chapters'])
    # Rename on all lessons and resources using this chapter
    course.lessons.filter(chapter=old_name).update(chapter=new_name)
    from .models import CourseResource
    CourseResource.objects.filter(course=course, chapter=old_name).update(chapter=new_name)
    messages.success(request, f"Chapter renamed from '{old_name}' to '{new_name}'.")
    return redirect('course_lessons', course_uid=course.uid)


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
@require_POST
def delete_chapter(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    chapter_name = request.POST.get('chapter_name', '').strip()
    if not chapter_name:
        messages.error(request, "Chapter name is required.")
        return redirect('course_lessons', course_uid=course.uid)
    chapters = list(course.chapters or [])
    if chapter_name not in chapters:
        messages.error(request, f"Chapter '{chapter_name}' not found.")
        return redirect('course_lessons', course_uid=course.uid)
    # Check for existing pending deletion request for this chapter
    existing = DeletionRequest.objects.filter(
        teacher=request.user, item_type='Chapter', item_id=course.id,
        item_name=chapter_name, status='PENDING'
    ).first()
    if existing:
        messages.warning(request, f"A deletion request for chapter '{chapter_name}' is already pending.")
        return redirect('course_lessons', course_uid=course.uid)
    # Check if chapter has content
    lesson_count = course.lessons.filter(chapter=chapter_name).count()
    resource_count = course.resources.filter(is_deleted=False, chapter=chapter_name).count()
    # Create deletion request for admin approval
    DeletionRequest.objects.create(
        teacher=request.user,
        item_type='Chapter',
        item_id=course.id,
        item_name=chapter_name,
        reason=request.POST.get('reason', '').strip() or f"Delete entire chapter '{chapter_name}' with {lesson_count} lesson(s) and {resource_count} resource(s)."
    )
    from .models import Notification
    # Notify all admins
    from django.db.models import Q
    from .models import CustomUser
    admins = CustomUser.objects.filter(
        Q(user_type='ADMIN') | Q(is_superuser=True)
    )
    for admin in admins:
        Notification.objects.create(
            user=admin,
            message=f"Teacher {request.user.full_name} requested to delete chapter '{chapter_name}' from course '{course.title}'."
        )
    messages.success(request, f"Deletion request sent for chapter '{chapter_name}'. Waiting for admin approval.")
    return redirect('course_lessons', course_uid=course.uid)


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def manage_chapter_items(request, course_uid, chapter_name, item_type, category=None):
    """Show all items (videos or resources) in a specific chapter for a course."""
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    from .models import CourseResource

    if item_type == 'videos':
        items = course.lessons.filter(chapter=chapter_name).order_by('order')
        template = 'teacher_portal/chapter_videos.html'
        extra_ctx = {}
    elif item_type == 'resources' and category:
        items = course.resources.filter(is_deleted=False, chapter=chapter_name, category=category).order_by('-created_at')
        template = 'teacher_portal/chapter_resources.html'
        extra_ctx = {'category': category, 'category_label': dict(CourseResource.CATEGORY_CHOICES).get(category, category)}
    else:
        messages.error(request, "Invalid request.")
        return redirect('course_lessons', course_uid=course.uid)

    return render(request, template, {
        'course': course,
        'chapter_name': chapter_name,
        'items': items,
        'item_type': item_type,
        **extra_ctx,
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def add_lesson(request, course_uid):
    """
    Handles YouTube URL lesson creation (form POST).
    MP4 file uploads use AJAX via /api/video/init-youtube/ + browser→YouTube PUT.
    """

    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if course.status == 'DELETED':
        messages.error(request, "Cannot add lessons to a deleted course.")
        return redirect('my_courses')
    if request.method == 'POST':
        title = request.POST.get('title')
        video_source = request.POST.get('video_source', 'file')
        video_url = request.POST.get('video_url', '')
        video_file = request.FILES.get('video_file')

        chapter = request.POST.get('chapter', '')

        if video_source == 'file' and video_file:
            messages.error(request, "MP4 uploads must use the upload button. Please try again.")
            return render(request, 'teacher_portal/add_lesson.html', {'course': course, 'chapter': chapter})

        if video_source == 'file' and not video_file:
            messages.error(request, "Please upload a video file or select YouTube URL mode.")
            return render(request, 'teacher_portal/add_lesson.html', {'course': course, 'chapter': chapter})

        if video_source == 'url' and video_url:
            video_url = video_url.strip()
        elif video_source == 'url' and not video_url:
            messages.error(request, "Please provide a YouTube video link.")
            return render(request, 'teacher_portal/add_lesson.html', {'course': course, 'chapter': chapter})
        elif video_source not in ('file', 'url'):
            messages.error(request, "Invalid video source selected.")
            return render(request, 'teacher_portal/add_lesson.html', {'course': course, 'chapter': chapter})

        youtube_match = re.search(r'(?:v=|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})', video_url)
        youtube_video_id = youtube_match.group(1) if youtube_match else None

        course_is_published = course.status == 'PUBLISHED' and course.is_approved

        lesson_status = 'APPROVED' if course_is_published else 'PENDING'
        lesson_approved = True if course_is_published else False

        lesson = Lesson.objects.create(
            course=course,
            title=title,
            chapter=chapter,
            video_url=video_url,
            video_file=None,
            order=max(int(order_raw), 1) if (order_raw := request.POST.get('order')) and order_raw.strip() else (course.lessons.count() + 1),
            status=lesson_status,
            is_approved=lesson_approved,
            youtube_video_id=youtube_video_id,
            youtube_upload_status='UPLOADED' if youtube_video_id else 'NOT_UPLOADED',
            upload_status='READY' if youtube_video_id else 'NOT_UPLOADED',
        )

        if youtube_video_id:
            lesson.youtube_uploaded_at = timezone.now()
            lesson.save(update_fields=['youtube_uploaded_at'])

        if course_is_published:
            messages.success(request, f"Lesson '{title}' added and immediately available to students.")
        else:
            messages.success(request, f"Lesson '{title}' added successfully! Submit for admin approval when ready.")
            notify_admins("New Lesson Added", f"Teacher {request.user.username} added lesson '{title}' to course '{course.title}'.", 'new_lesson', '')

        # Auto-reinstate BLOCKED teacher after successful edit
        if request.user.status == 'BLOCKED':
            request.user.status = 'ACTIVE'
            request.user.is_active = True
            request.user.save(update_fields=['status', 'is_active'])
            cache.delete(f"user_status_{request.user.id}")
            messages.success(request, "Your account has been automatically reinstated. Your content is now visible to students again.")

        return redirect('course_lessons', course_uid=course.uid)
    
    chapter = request.GET.get('chapter', '')
    return render(request, 'teacher_portal/add_lesson.html', {
        'course': course,
        'chapter': chapter,
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_lesson(request, lesson_uid):
    """
    Handles YouTube URL lesson updates (form POST).
    MP4 file uploads use AJAX via /api/video/init-youtube-edit/ + browser→YouTube PUT.
    """
    import traceback
    lesson = get_object_or_404(Lesson, uid=lesson_uid, course__teacher=request.user)
    if request.method == 'POST':
        try:
            # Save suspended state BEFORE auto-unsuspending
            was_suspended = lesson.is_suspended or lesson.status == 'SUSPENDED'
            if lesson.is_suspended:
                lesson.is_suspended = False
                lesson.suspended_at = None
                lesson.suspended_by = None
                lesson.suspension_reason = ''
            title = request.POST.get('title')
            chapter = request.POST.get('chapter', lesson.chapter)
            video_source = request.POST.get('video_source', 'file')
            video_url = request.POST.get('video_url', '')
            video_file = request.FILES.get('video_file')

            if video_source == 'file' and video_file:
                messages.error(request, "MP4 uploads must use the upload button. Please try again.")
                return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course, 'course_chapters': lesson.course.chapters or []})

            if video_source == 'file' and not video_file:
                messages.error(request, "Please upload a video file or select YouTube URL mode.")
                return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course, 'course_chapters': lesson.course.chapters or []})

            if video_source == 'url' and video_url:
                video_url = video_url.strip()
            elif video_source == 'url' and not video_url:
                video_url = lesson.video_url or ''
            elif video_source not in ('file', 'url'):
                messages.error(request, "Invalid video source selected.")
                return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course, 'course_chapters': lesson.course.chapters or []})

            try:
                order_raw = request.POST.get('order')
                order = max(int(order_raw), 1) if order_raw and order_raw.strip() else lesson.order
            except (ValueError, TypeError):
                order = lesson.order

            youtube_match = re.search(r'(?:v=|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})', video_url)
            new_youtube_video_id = youtube_match.group(1) if youtube_match else None

            course_is_published = lesson.course.status == 'PUBLISHED' and lesson.course.is_approved

            lesson.title = title
            lesson.chapter = chapter
            if new_youtube_video_id:
                lesson.youtube_video_id = new_youtube_video_id
                lesson.youtube_upload_status = 'UPLOADED'
                lesson.youtube_uploaded_at = timezone.now()
            lesson.video_url = video_url
            lesson.order = order

            if was_suspended:
                # Suspended content edited → route to PENDING for re-review
                lesson.is_approved = False
                lesson.status = 'PENDING'
                lesson.has_pending_edits = True
                lesson.save()
                messages.success(request, "Your lesson has been updated and submitted for re-review.")
            elif course_is_published:
                lesson.is_approved = True
                lesson.status = 'APPROVED'
                lesson.save()
                messages.success(request, "Lesson updated and immediately visible to students.")
            elif lesson.is_approved:
                lesson.save()
                messages.success(request, "Lesson updated successfully.")
            else:
                lesson.is_approved = False
                lesson.status = 'PENDING'
                lesson.save()
                messages.success(request, "Lesson updated successfully.")

            # Auto-reinstate BLOCKED teacher after successful edit
            if request.user.status == 'BLOCKED':
                request.user.status = 'ACTIVE'
                request.user.is_active = True
                request.user.save(update_fields=['status', 'is_active'])
                cache.delete(f"user_status_{request.user.id}")
                messages.success(request, "Your account has been automatically reinstated. Your content is now visible to students again.")

            return redirect('course_lessons', course_uid=lesson.course.uid)
        except Exception as e:
            logger.error("Lesson edit UNHANDLED ERROR | user=%s lesson=%s\n%s",
                request.user.username, lesson.uid, traceback.format_exc())
            messages.error(request, "An unexpected error occurred. Please try again or contact support.")
            return redirect('course_lessons', course_uid=lesson.course.uid)

    return render(request, 'teacher_portal/edit_lesson.html', {
        'lesson': lesson,
        'course': lesson.course,
        'course_chapters': lesson.course.chapters or [],
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def delete_lesson(request, lesson_uid):
    if request.method != 'POST':
        return redirect('teacher_dashboard')
    lesson = get_object_or_404(Lesson, uid=lesson_uid, course__teacher=request.user)
    course_uid = lesson.course.uid

    # Teacher password confirmation
    teacher = request.user
    t_password = request.POST.get('teacher_password', '')
    if not teacher.check_password(t_password):
        messages.error(request, "Incorrect password. Please enter your account password to confirm deletion.")
        return redirect('course_lessons', course_uid=course_uid)

    from .models import DeletionRequest

    # Always create a deletion request (even for PENDING/REJECTED items)
    existing_request = DeletionRequest.objects.filter(
        teacher=request.user, item_type='Lesson', item_id=lesson.id, status='PENDING'
    ).first()
    
    if existing_request:
        messages.info(request, "A deletion request for this lesson is already pending admin approval.")
    else:
        reason = request.POST.get('reason', '').strip() or 'Teacher requested deletion.'
        DeletionRequest.objects.create(
            teacher=request.user,
            item_type='Lesson',
            item_id=lesson.id,
            item_name=f"{lesson.title} (Course: {lesson.course.title})",
            reason=reason,
            status='PENDING',
        )
        messages.success(request, "Deletion request sent to admin. The lesson will be removed once approved.")
        notify_admins("Deletion Request Submitted", f"Teacher {request.user.username} requested to delete lesson '{lesson.title}'.", 'deletion_request', '')
        
    return redirect('course_lessons', course_uid=course_uid)

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def add_resource(request, course_uid):
    from .utils.pdf_processor import validate_file
    from .utils.storage_manager import StorageManager
    from .models import CourseResource
    import traceback

    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if course.status == 'DELETED':
        messages.error(request, "Cannot add resources to a deleted course.")
        return redirect('my_courses')
    if request.method == 'POST':
        try:
            title = request.POST.get('title', '').strip()
            category = request.POST.get('category', '').strip()
            upload_file = request.FILES.get('upload_file')

            if not title:
                messages.error(request, "Please enter a resource name.")
                return redirect('course_lessons', course_uid=course.uid)

            if not category or category not in ('ENGLISH', 'MALAYALAM', 'ONLINE'):
                messages.error(request, "Please select a category (English, Malayalam, or Online).")
                return redirect('course_lessons', course_uid=course.uid)

            if not upload_file:
                messages.error(request, "Please select a PDF file to upload.")
                return redirect('course_lessons', course_uid=course.uid)

            MAX_UPLOAD_BYTES = 10 * 1024 * 1024
            if upload_file.size > MAX_UPLOAD_BYTES:
                messages.error(request, "File size exceeds the 10MB limit. Please upload a smaller PDF.")
                return redirect('course_lessons', course_uid=course.uid)

            uploaded_fb_path = None
            try:
                from .utils.malware_scanner import scanner
                mime_type, ext = validate_file(upload_file, upload_file.name)
                is_infected, scan_reason = scanner.scan_file(upload_file)
                if is_infected:
                    logger.warning("Security scan blocked | user=%s file=%s reason=%s ip=%s",
                        request.user.username, upload_file.name, scan_reason,
                        request.META.get('REMOTE_ADDR'))
                    messages.error(request, "This file could not be uploaded because it does not meet our security requirements.")
                    return redirect('course_lessons', course_uid=course.uid)
                file_bytes = upload_file.read()
                file_size = len(file_bytes)

                import uuid
                course_slug = re.sub(r'[^a-zA-Z0-9]', '-', course.title).strip('-').lower()
                course_slug = re.sub(r'-+', '-', course_slug)
                safe_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip()
                safe_title = re.sub(r'\s+', '-', safe_title)
                safe_title = re.sub(r'-+', '-', safe_title).lower()
                safe_title = safe_title[:40]
                category_folder = category.lower() if category else 'uncategorised'
                suffix = uuid.uuid4().hex[:4]
                dest_filename = f"{safe_title}-{suffix}.pdf"
                dest_path = f"{course_slug}/{category_folder}/{dest_filename}"
                uploaded_fb_path = StorageManager.upload_to_supabase_storage(file_bytes, dest_path, 'application/pdf')
                del file_bytes

                chapter = request.POST.get('chapter', '')
                course_is_published = course.status == 'PUBLISHED' and course.is_approved
                if course_is_published:
                    resource_status = 'APPROVED'
                    resource_approved = True
                    success_msg = f"Resource '{title}' added and immediately available to students."
                else:
                    resource_status = 'PENDING'
                    resource_approved = False
                    success_msg = f"Resource '{title}' uploaded and pending approval."
                    notify_admins("New Resource Submitted", f"Teacher {request.user.username} uploaded a resource for course '{course.title}'.", 'new_resource', '')

                CourseResource.objects.create(
                    course=course,
                    title=title,
                    chapter=chapter,
                    category=category,
                    resource_type='PDF',
                    firebase_file_path=uploaded_fb_path,
                    backup_file_path=None,
                    mime_type='application/pdf',
                    file_extension='pdf',
                    original_size=file_size,
                    compressed_size=file_size,
                    status=resource_status,
                    is_approved=resource_approved
                )
                messages.success(request, success_msg)
            except Exception as e:
                logger.error("Resource upload error | user=%s course=%s error=%s",
                    request.user.username, course.uid, str(e))
                if uploaded_fb_path:
                    try:
                        StorageManager.delete_from_supabase_storage(uploaded_fb_path)
                    except Exception:
                        pass
                messages.error(request, "An error occurred while uploading the file. Please try again.")

            # Auto-reinstate BLOCKED teacher after successful edit
            if request.user.status == 'BLOCKED':
                request.user.status = 'ACTIVE'
                request.user.is_active = True
                request.user.save(update_fields=['status', 'is_active'])
                cache.delete(f"user_status_{request.user.id}")
                messages.success(request, "Your account has been automatically reinstated. Your content is now visible to students again.")

            return redirect('course_lessons', course_uid=course.uid)
        except Exception as e:
            logger.error("Resource add UNHANDLED ERROR | user=%s course=%s\n%s",
                request.user.username, course.uid, traceback.format_exc())
            messages.error(request, "An unexpected error occurred. Please try again or contact support.")
            return redirect('course_lessons', course_uid=course.uid)

    chapter = request.GET.get('chapter', '')
    return render(request, 'teacher_portal/add_resource.html', {
        'course': course,
        'chapter': chapter,
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_resource(request, resource_uid):
    from .utils.pdf_processor import validate_file
    from .utils.storage_manager import StorageManager
    from .models import CourseResource
    import traceback

    resource = get_object_or_404(CourseResource, uid=resource_uid, course__teacher=request.user)
    course = resource.course

    if request.method == 'POST':
        try:
            # Save suspended state BEFORE auto-unsuspending
            was_suspended = resource.is_suspended or resource.status == 'SUSPENDED'
            if resource.is_suspended:
                resource.is_suspended = False
                resource.suspended_at = None
                resource.suspended_by = None
                resource.suspension_reason = ''
            title = request.POST.get('title', '').strip()
            category = request.POST.get('category', '').strip()
            chapter = request.POST.get('chapter', '').strip() or resource.chapter
            upload_file = request.FILES.get('upload_file')

            if not title:
                messages.error(request, "Please enter a resource name.")
                return redirect('edit_resource', resource_uid=resource.uid)

            if not category or category not in ('ENGLISH', 'MALAYALAM', 'ONLINE'):
                messages.error(request, "Please select a category (English, Malayalam, or Online).")
                return redirect('edit_resource', resource_uid=resource.uid)

            is_approved = resource.status == 'APPROVED'
            new_fb_path = None
            new_file_size = 0
            uploaded_fb_path = None

            if upload_file:
                MAX_UPLOAD_BYTES = 10 * 1024 * 1024
                if upload_file.size > MAX_UPLOAD_BYTES:
                    messages.error(request, "File size exceeds the 10MB limit. Please upload a smaller PDF.")
                    return redirect('edit_resource', resource_uid=resource.uid)

                try:
                    from .utils.malware_scanner import scanner
                    from .utils.pdf_processor import validate_file
                    new_mime, new_ext = validate_file(upload_file, upload_file.name)
                    is_infected, scan_reason = scanner.scan_file(upload_file)
                    if is_infected:
                        logger.warning("Security scan blocked | user=%s file=%s reason=%s ip=%s",
                            request.user.username, upload_file.name, scan_reason,
                            request.META.get('REMOTE_ADDR'))
                        messages.error(request, "This file could not be uploaded because it does not meet our security requirements.")
                        return redirect('edit_resource', resource_uid=resource.uid)
                    file_bytes = upload_file.read()
                    new_file_size = len(file_bytes)

                    import uuid
                    course_slug = re.sub(r'[^a-zA-Z0-9]', '-', course.title).strip('-').lower()
                    course_slug = re.sub(r'-+', '-', course_slug)
                    safe_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip()
                    safe_title = re.sub(r'\s+', '-', safe_title)
                    safe_title = re.sub(r'-+', '-', safe_title).lower()
                    safe_title = safe_title[:40]
                    category_folder = category.lower() if category else 'uncategorised'
                    suffix = uuid.uuid4().hex[:4]
                    dest_filename = f"{safe_title}-{suffix}.pdf"
                    dest_path = f"{course_slug}/{category_folder}/{dest_filename}"
                    uploaded_fb_path = StorageManager.upload_to_supabase_storage(file_bytes, dest_path, 'application/pdf')
                    new_fb_path = uploaded_fb_path
                    del file_bytes
                except Exception as e:
                    logger.error("Resource edit error | user=%s resource=%s error=%s",
                        request.user.username, resource.uid, str(e))
                    if uploaded_fb_path:
                        try:
                            StorageManager.delete_from_supabase_storage(uploaded_fb_path)
                        except Exception:
                            pass
                    messages.error(request, "An error occurred while processing the file. Please try again.")
                    return redirect('edit_resource', resource_uid=resource.uid)

            course_is_published = course.status == 'PUBLISHED' and course.is_approved

            # Set resource metadata fields
            if new_fb_path and resource.firebase_file_path:
                try:
                    StorageManager.delete_from_supabase_storage(resource.firebase_file_path)
                except:
                    pass
            resource.title = title
            resource.category = category
            resource.chapter = chapter
            resource.resource_type = 'PDF'
            if new_fb_path:
                resource.firebase_file_path = new_fb_path
                resource.mime_type = 'application/pdf'
                resource.file_extension = 'pdf'
                resource.original_size = new_file_size
                resource.compressed_size = new_file_size

            if was_suspended:
                resource.status = 'APPROVED'
                resource.is_approved = True
                resource.rejection_reason = None
                resource.has_pending_edits = False
                resource.save()
                messages.success(request, f"Resource '{title}' unsuspended and immediately available to students.")
            elif course_is_published:
                resource.status = 'APPROVED'
                resource.is_approved = True
                resource.rejection_reason = None
                resource.has_pending_edits = False
                resource.save()
                messages.success(request, f"Resource '{title}' updated and immediately available to students.")
            elif is_approved:
                resource.has_pending_edits = False
                resource.save()
                messages.success(request, f"Resource '{title}' updated successfully.")
            else:
                resource.status = 'PENDING'
                resource.is_approved = False
                resource.rejection_reason = None
                resource.save()
                messages.success(request, f"Resource '{title}' updated successfully.")

            # Auto-reinstate BLOCKED teacher after successful edit
            if request.user.status == 'BLOCKED':
                request.user.status = 'ACTIVE'
                request.user.is_active = True
                request.user.save(update_fields=['status', 'is_active'])
                cache.delete(f"user_status_{request.user.id}")
                messages.success(request, "Your account has been automatically reinstated. Your content is now visible to students again.")

            return redirect('course_lessons', course_uid=course.uid)
        except Exception as e:
            logger.error("Resource edit UNHANDLED ERROR | user=%s resource=%s\n%s",
                request.user.username, resource.uid, traceback.format_exc())
            messages.error(request, "An unexpected error occurred. Please try again or contact support.")
            return redirect('edit_resource', resource_uid=resource.uid)

    return render(request, 'teacher_portal/edit_resource.html', {
        'resource': resource,
        'course': course,
        'course_chapters': course.chapters or [],
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def delete_resource(request, resource_uid):
    if request.method != 'POST':
        return redirect('teacher_dashboard')
    from .models import CourseResource, DeletionRequest
    resource = get_object_or_404(CourseResource, uid=resource_uid, course__teacher=request.user)

    # Teacher password confirmation
    teacher = request.user
    t_password = request.POST.get('teacher_password', '')
    if not teacher.check_password(t_password):
        messages.error(request, "Incorrect password. Please enter your account password to confirm deletion.")
        return redirect('course_lessons', course_uid=resource.course.uid)

    # Always create a deletion request for admin approval (even for PENDING/REJECTED items)
    # Prevent duplicate PENDING deletion requests
    existing = DeletionRequest.objects.filter(resource=resource, status='PENDING').exists()
    if existing:
        messages.warning(request, "A deletion request for this resource is already pending admin review.")
        return redirect('course_lessons', course_uid=resource.course.uid)

    reason = request.POST.get('reason', '').strip() or 'Teacher requested deletion.'
    DeletionRequest.objects.create(
        teacher=request.user,
        item_type='Resource',
        item_id=resource.id,
        item_name=resource.title,
        resource=resource,
        reason=reason,
        status='PENDING',
    )
    # Mark the resource as deletion-pending so students can't see it
    resource.status = 'DELETION_PENDING'
    resource.save()

    notify_admins("Deletion Request Submitted", f"Teacher {request.user.username} requested deletion of resource '{resource.title}'.", 'deletion_request', '')
    messages.success(request, f"Deletion request for '{resource.title}' submitted. Awaiting admin approval.")
    return redirect('course_lessons', course_uid=resource.course.uid)

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_deletion_requests(request):
    from .models import DeletionRequest, CourseDeletionRequest
    lesson_res_requests = DeletionRequest.objects.filter(teacher=request.user).order_by('-created_at')
    course_requests = CourseDeletionRequest.objects.filter(teacher=request.user).order_by('-requested_at')
    return render(request, 'teacher_portal/deletion_requests.html', {
        'lesson_res_requests': lesson_res_requests,
        'course_requests': course_requests,
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def submit_course_approval(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if course.status == 'DELETED':
        messages.error(request, "Cannot submit a deleted course for approval.")
        return redirect('my_courses')
    lessons = course.lessons.all()
    
    if lessons.exists():
        # Identify what exactly is being resubmitted
        rejected_lessons = lessons.filter(status='REJECTED')
        pending_lessons = lessons.filter(status='PENDING')
        
        # Reset rejected lessons to pending
        if rejected_lessons.exists():
            rejected_lessons.update(status='PENDING', is_approved=False)
        
        old_status = course.status
        is_course_rejection_fix = (old_status == 'REJECTED')
        
        # Only change course status if it's not already published
        if old_status in ['DRAFT', 'REJECTED']:
            course.status = 'PENDING'
            course.save()
            
        # Messaging and Notifications
        if is_course_rejection_fix:
            messages.success(request, f"Course '{course.title}' has been re-submitted after rejection.")
            notify_admins("Course Resubmitted", f"Teacher {request.user.username} re-submitted course '{course.title}'.", 'course_edit', '')
        elif rejected_lessons.exists():
            messages.success(request, "Rejected lessons have been resubmitted for approval.")
            notify_admins("Lesson Resubmitted", f"Teacher {request.user.username} resubmitted lessons in course '{course.title}'.", 'lesson_edit', '')
        elif pending_lessons.exists():
            messages.success(request, "New content submitted for review.")
            notify_admins("New Content Submitted", f"Teacher {request.user.username} submitted new content for course '{course.title}'.", 'new_lesson', '')
        else:
            messages.info(request, "All content is already under review or approved.")
            
    else:
        messages.error(request, "Please add at least one lesson before submitting for approval.")
        
    return redirect('my_courses')

@login_required
def logout_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    user_type = request.user.user_type
    is_staff = getattr(request.user, 'is_staff', False)
    
    # Perform a complete logout and flush
    request.session.flush()
    logout(request)
    
    # Redirect to the appropriate login page based on user type
    if user_type == 'TEACHER':
        messages.success(request, "Teacher logged out successfully. Sessions cleared.")
        return redirect('teacher_login')
    elif is_staff or user_type == 'ADMIN':
        messages.success(request, "Admin logged out successfully. Sessions cleared.")
        return redirect('admin_login')
    else:
        messages.success(request, "You have been logged out successfully. Sessions cleared.")
        return redirect('login')

@user_passes_test(lambda u: u.is_authenticated and (u.user_type in ['STUDENT', 'TEACHER'] or getattr(u, 'is_staff', False)), login_url='login')
@login_required
def enroll_course(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, status='PUBLISHED', is_approved=True)

    # Block enrollment if teacher is BLOCKED
    if course.teacher.status == 'BLOCKED':
        messages.error(request, "This course is currently unavailable for enrollment.")
        return redirect('student_explore')

    # Constrain: Student must update profile picture to enroll
    if request.user.user_type == 'STUDENT' and not getattr(request.user, 'is_staff', False):
        if not request.user.image and not request.user.profile_photo:
            messages.error(request, "You must update your profile picture before you can enroll in courses.")
            return redirect('edit_profile')
            
    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.info(request, f"You are already enrolled in {course.title}.")
    else:
        Enrollment.objects.create(user=request.user, course=course)
        messages.success(request, f"Successfully enrolled in {course.title}!")
        create_notification(request.user, f"Welcome! You have successfully enrolled in '{course.title}'.")
    return redirect('course_player', course_uid=course.uid)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html', {'user': request.user})

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def check_username(request):
    from django.http import JsonResponse
    username = request.GET.get('username', '').strip()
    if not username or len(username) < 3:
        return JsonResponse({'available': False, 'error': 'Username must be at least 3 characters.'})
    exclude_id = request.user.id if request.user.is_authenticated else None
    exists = CustomUser.objects.filter(username__iexact=username).exclude(id=exclude_id).exists()
    return JsonResponse({'available': not exists})

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def edit_profile(request):
    has_photo = bool(request.user.image) or bool(request.user.profile_photo)
    url_name = request.resolver_match.url_name
    if not has_photo and url_name not in ['edit_profile', 'logout', 'student_view_auth', 'teacher_view_auth']:
        if request.user.user_type in ['STUDENT', 'TEACHER'] and not request.user.is_superuser:
            messages.info(request, "Welcome! Please select an avatar to complete your account setup.")

    if request.method == 'POST':
        try:
            from django.contrib.auth import update_session_auth_hash
            from django.core.cache import cache
            import re

            # Handle Skip — set default avatar and mark photo cache so middleware stops redirecting
            if request.POST.get('skip'):
                if getattr(request.user, 'is_staff', False) or request.user.user_type == 'ADMIN':
                    request.user.image = '/static/avatars/admin_m_0.png'
                elif request.user.user_type == 'TEACHER':
                    request.user.image = '/static/avatars/teacher_m_0.png'
                else:
                    request.user.image = '/static/avatars/student_m_0.png'
                request.user.save(update_fields=['image'])
                cache.delete(f"user_has_photo_{request.user.id}")
                redirect_url = reverse('teacher_dashboard') if request.user.user_type == 'TEACHER' else reverse('dashboard')
                return JsonResponse({'status': 'skip', 'redirect': redirect_url})

            changes_made = False
            password_changed = False
            avatar_changed = False

            new_username = request.POST.get('new_username')
            if new_username:
                new_username = new_username.strip()
                if CustomUser.objects.filter(username=new_username).exclude(id=request.user.id).exists():
                    return JsonResponse({'status': 'error', 'message': 'Username is already taken.'}, status=400)
                if new_username != request.user.username:
                    request.user.username = new_username
                    changes_made = True

            new_password = request.POST.get('new_password')
            if new_password:
                curr_pass = request.POST.get('current_password')
                if not request.user.check_password(curr_pass):
                    return JsonResponse({'status': 'error', 'message': 'Current password is incorrect.'}, status=400)
                
                if len(new_password) < 8 or not any(c.isupper() for c in new_password) or not any(c.islower() for c in new_password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password):
                    return JsonResponse({'status': 'error', 'message': 'Password must be 8+ chars and contain Uppercase, Lowercase, and a Special character.'}, status=400)
                
                if new_password != request.POST.get('confirm_password'):
                    return JsonResponse({'status': 'error', 'message': 'Passwords do not match.'}, status=400)
                    
                request.user.set_password(new_password)
                changes_made = True
                password_changed = True

            avatar_url = request.POST.get('avatar_url')
            if avatar_url:
                request.user.image = avatar_url
                changes_made = True
                avatar_changed = True

            profile_photo = request.FILES.get('profile_photo')
            if profile_photo:
                MAX_SIZE = 5 * 1024 * 1024
                if profile_photo.size > MAX_SIZE:
                    return JsonResponse({'status': 'error', 'message': 'File is too large (Maximum 5MB allowed).'}, status=400)
                
                from .utils.cloudinary_helpers import update_image
                if update_image(request.user, profile_photo, folder="Neo Learner/profiles"):
                    changes_made = True
                    avatar_changed = True
                else:
                    return JsonResponse({'status': 'error', 'message': 'Failed to upload photo. Please try again.'}, status=500)

            if changes_made:
                request.user.save()
                if password_changed:
                    update_session_auth_hash(request, request.user)

                if avatar_changed:
                    request.session.pop('avatar_skipped', None)
                    photo_cache_key = f"user_has_photo_{request.user.id}"
                    cache.delete(photo_cache_key)

                if avatar_changed and not new_username and not new_password:
                    redirect_url = reverse('teacher_dashboard') if request.user.user_type == 'TEACHER' else reverse('dashboard')
                    return JsonResponse({'status': 'success', 'message': 'Avatar updated successfully!', 'redirect': redirect_url})

                return JsonResponse({'status': 'success', 'message': 'Profile updated successfully!'})
            else:
                return JsonResponse({'status': 'error', 'message': 'No changes detected.'}, status=400)
        except Exception as e:
            logger.exception(f'Profile update error: {e}')
            return JsonResponse({'status': 'error', 'message': 'Update failed. Please try again.'}, status=500)
    
    if getattr(request.user, 'is_staff', False) or request.user.user_type == 'ADMIN':
        # 10 Professional Admin Avatars (5 Male, 5 Female)
        avatars = [f"/static/avatars/admin_m_{i}.png" for i in range(5)] + \
                  [f"/static/avatars/admin_f_{i}.png" for i in range(5)]
    elif request.user.user_type == 'TEACHER':
        # 10 Professional Teacher Avatars (5 Male, 5 Female)
        avatars = [f"/static/avatars/teacher_m_{i}.png" for i in range(5)] + \
                  [f"/static/avatars/teacher_f_{i}.png" for i in range(5)]
    else:
        # 10 Professional Student Avatars (5 Male, 5 Female)
        avatars = [f"/static/avatars/student_m_{i}.png" for i in range(5)] + \
                  [f"/static/avatars/student_f_{i}.png" for i in range(5)]

    return render(request, 'accounts/edit_profile.html', {'user': request.user, 'avatars': avatars})

@login_required
def skip_avatar(request):
    request.session['avatar_skipped'] = True
    photo_cache_key = f"user_has_photo_{request.user.id}"
    cache.delete(photo_cache_key)
    if request.user.user_type == 'TEACHER':
        return redirect('teacher_dashboard')
    return redirect('dashboard')


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def teacher_edit_profile(request):
    if request.method == 'POST':
        try:
            from django.contrib.auth import update_session_auth_hash
            import re

            new_username = request.POST.get('new_username', '').strip()
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            current_password = request.POST.get('current_password', '')
            avatar_url = request.POST.get('avatar_url', '')

            changes_made = False
            password_changed = False

            # --- Username Change ---
            if new_username and new_username != request.user.username:
                if CustomUser.objects.filter(username=new_username).exclude(id=request.user.id).exists():
                    return JsonResponse({'status': 'error', 'message': 'Username is already taken.'}, status=400)
                request.user.username = new_username
                changes_made = True

            # --- Password Change ---
            if new_password:
                if not current_password:
                    return JsonResponse({'status': 'error', 'message': 'Current password is required.'}, status=400)
                if not request.user.check_password(current_password):
                    return JsonResponse({'status': 'error', 'message': 'Current password is incorrect.'}, status=400)
                if new_password != confirm_password:
                    return JsonResponse({'status': 'error', 'message': 'Passwords do not match.'}, status=400)
                if len(new_password) < 8:
                    return JsonResponse({'status': 'error', 'message': 'Password must be at least 8 characters.'}, status=400)
                if not re.search(r'[A-Z]', new_password):
                    return JsonResponse({'status': 'error', 'message': 'Password needs an uppercase letter.'}, status=400)
                if not re.search(r'[a-z]', new_password):
                    return JsonResponse({'status': 'error', 'message': 'Password needs a lowercase letter.'}, status=400)
                if not re.search(r'[@$!%*?&#]', new_password):
                    return JsonResponse({'status': 'error', 'message': 'Password needs a special character.'}, status=400)
                request.user.set_password(new_password)
                changes_made = True
                password_changed = True

            # --- Avatar Change (preset) ---
            if avatar_url:
                request.user.image = avatar_url
                request.user.image_public_id = ''
                changes_made = True

            if changes_made:
                request.user.save()
                if password_changed:
                    update_session_auth_hash(request, request.user)
                if avatar_url:
                    request.session.pop('avatar_skipped', None)
                    photo_cache_key = f"user_has_photo_{request.user.id}"
                    cache.delete(photo_cache_key)
                    return JsonResponse({'status': 'success', 'message': 'Profile updated successfully!', 'redirect': reverse('teacher_dashboard')})
                return JsonResponse({'status': 'success', 'message': 'Profile updated successfully!'})
            else:
                return JsonResponse({'status': 'error', 'message': 'No changes detected.'}, status=400)
        except Exception as e:
            logger.exception(f'Teacher profile update error: {e}')
            return JsonResponse({'status': 'error', 'message': 'Update failed. Please try again.'}, status=500)

    avatars = [f"/static/avatars/teacher_m_{i}.png" for i in range(5)] + \
              [f"/static/avatars/teacher_f_{i}.png" for i in range(5)]
    return render(request, 'teacher_portal/edit_profile.html', {'user': request.user, 'avatars': avatars})


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def course_player(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid)

    # Hide content from students if teacher is BLOCKED
    if course.teacher.status == 'BLOCKED' and not request.user.is_staff and request.user.user_type != 'TEACHER':
        messages.error(request, "This course is currently unavailable.")
        return redirect('student_explore')

    is_unlocked = request.session.get('student_view_unlocked')
    is_admin = getattr(request.user, 'is_staff', False)

    # === ACCESS CONTROL ===
    if is_unlocked and (is_admin or request.user.user_type == 'TEACHER'):
        lessons = course.lessons.filter(status='APPROVED', is_suspended=False).only('id', 'title', 'order', 'video_url', 'video_file', 'chapter', 'youtube_video_id').order_by('chapter', 'order')

    elif is_admin:
        lessons = course.lessons.exclude(status='REJECTED').order_by('chapter', 'order')

    elif request.user.user_type == 'TEACHER':
        if course.teacher != request.user and not course.is_approved:
            messages.error(request, "You do not have permission to view this course.")
            return redirect('teacher_dashboard')
        lessons = course.lessons.exclude(status='REJECTED').order_by('chapter', 'order')

    else:
        if not Enrollment.objects.filter(user=request.user, course=course).exists():
            messages.error(request, "You are not enrolled in this course.")
            return redirect('student_explore')
        lessons = course.lessons.filter(status='APPROVED', is_suspended=False).only('id', 'title', 'order', 'video_url', 'video_file', 'chapter', 'youtube_video_id').order_by('chapter', 'order')

    from .models import CourseResource
    approved_resources = CourseResource.objects.filter(
        course=course, status='APPROVED', is_deleted=False, is_suspended=False
    ).order_by('chapter', '-created_at')

    # Category counts for resource chart
    resource_counts = {
        'ENGLISH': approved_resources.filter(category='ENGLISH').count(),
        'MALAYALAM': approved_resources.filter(category='MALAYALAM').count(),
        'ONLINE': approved_resources.filter(category='ONLINE').count(),
    }

    # Resolve Supabase video URLs to signed URLs
    for lesson in lessons:
        if lesson.video_url and lesson.video_url.startswith('supabase://'):
            if lesson.upload_status not in ('READY', 'NOT_UPLOADED'):
                lesson.video_url = ''
                continue
            storage_path = lesson.video_url.replace('supabase://', '', 1)
            try:
                from .utils.supabase_storage import supabase as vid_supabase
                parts = storage_path.split('/', 1)
                if len(parts) == 2 and '-' in parts[0]:
                    v_bucket, v_path = parts[0], parts[1]
                else:
                    from .utils.supabase_storage import video_bucket as v_bucket
                    v_path = storage_path
                res = vid_supabase.storage.from_(v_bucket).create_signed_url(v_path, 86400)
                signed = res.get("signedURL") if isinstance(res, dict) else res
                if signed:
                    lesson.video_url = signed
                else:
                    lesson.video_url = ''
            except Exception:
                lesson.video_url = ''

    # Group by chapter
    from itertools import groupby
    lessons_list = list(lessons)
    resources_list = list(approved_resources)

    lesson_by_chapter = {}
    for ch, grp in groupby(lessons_list, key=lambda x: x.chapter or ''):
        lesson_by_chapter[ch] = list(grp)

    res_by_chapter = {}
    for ch, grp in groupby(resources_list, key=lambda x: x.chapter or ''):
        res_by_chapter[ch] = list(grp)

    # Order chapters: course.chapters first (teacher-set order), then remaining by creation date
    course_chapters = list(course.chapters or [])
    derived_chapters = set(list(lesson_by_chapter.keys()) + list(res_by_chapter.keys()))
    all_chapter_names = []
    seen = set()
    from datetime import datetime as dt_module
    def _chapter_first_ts(ch_name):
        ts = []
        for l in lesson_by_chapter.get(ch_name, []):
            if l.created_at:
                ts.append(l.created_at)
        for r in res_by_chapter.get(ch_name, []):
            if r.created_at:
                ts.append(r.created_at)
        return ts[0] if ts else dt_module.min
    for name in course_chapters:
        if name and name in derived_chapters and name not in seen:
            seen.add(name)
            all_chapter_names.append(name)
    for name in sorted((d for d in derived_chapters if d), key=_chapter_first_ts):
        if name not in seen:
            seen.add(name)
            all_chapter_names.append(name)

    chapters_data = []
    for ch_name in all_chapter_names:
        ch_lessons = lesson_by_chapter.get(ch_name, [])
        ch_resources = res_by_chapter.get(ch_name, [])
        # Per-chapter category counts for resource chart
        cat_counts = {}
        for code in ('ENGLISH', 'MALAYALAM', 'ONLINE'):
            cat_items = [r for r in ch_resources if r.category == code]
            cat_counts[code] = len(cat_items)
        chapters_data.append({
            'name': ch_name,
            'videos': ch_lessons,
            'videos_count': len(ch_lessons),
            'resources': ch_resources,
            'resources_count': len(ch_resources),
            'cat_counts': cat_counts,
        })

    context = {
        'course': course,
        'lessons': lessons,
        'approved_resources': approved_resources,
        'resource_counts': resource_counts,
        'chapters': chapters_data,
        'first_lesson': lessons.first(),
        'is_admin': getattr(request.user, 'is_staff', False),
    }
    return render(request, 'accounts/course_player.html', context)

@login_required
@login_required
@require_POST
def send_chat_message(request):
    sender = request.user
    is_teacher = sender.user_type == 'TEACHER'
    is_admin_user = sender.is_superuser or sender.is_staff or sender.user_type == 'ADMIN'
    if not sender.is_authenticated or not (is_teacher or is_admin_user):
        return JsonResponse({'status': 'error', 'message': 'Access denied'}, status=403)

    receiver_uid = request.POST.get('receiver_uid')
    message_text = request.POST.get('message')

    try:
        receiver = CustomUser.objects.get(uid=receiver_uid)
        receiver_is_valid = (
            (is_teacher and (receiver.is_superuser or receiver.user_type == 'ADMIN' or receiver.is_staff)) or
            (is_admin_user and receiver.user_type == 'TEACHER')
        )
        if not receiver_is_valid:
            return JsonResponse({'status': 'error', 'message': 'Invalid recipient'}, status=403)
    except CustomUser.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)

    sender_name = sender.chat_display if is_admin_user else (sender.full_name or sender.username)

    from accounts.utils.firebase_chat import send_message as fb_send
    result = fb_send(str(sender.uid), receiver_uid, message_text)
    if result is None or result[0] is None:
        return JsonResponse({'status': 'error', 'message': 'Message delivery failed'}, status=500)

    msg_uid, now_ms = result
    from datetime import datetime
    ts_str = datetime.fromtimestamp(now_ms / 1000).strftime('%b %d, %I:%M %p')

    return JsonResponse({
        'status': 'success',
        'message_uid': msg_uid,
        'message': message_text,
        'timestamp': ts_str,
        'sender': sender_name
    })


@login_required
@require_POST
def edit_chat_message(request):
    sender = request.user
    msg_uid = request.POST.get('message_uid')
    new_message = request.POST.get('message')
    if not msg_uid or not new_message:
        return JsonResponse({'status': 'error', 'message': 'Missing fields'}, status=400)
    from accounts.utils.firebase_chat import edit_message as fb_edit
    success, error = fb_edit(str(sender.uid), msg_uid, new_message)
    if not success:
        return JsonResponse({'status': 'error', 'message': error or 'Edit failed'}, status=400)
    return JsonResponse({'status': 'success'})


@login_required
@require_POST
def delete_chat_message(request):
    sender = request.user
    msg_uid = request.POST.get('message_uid')
    if not msg_uid:
        return JsonResponse({'status': 'error', 'message': 'Missing message_uid'}, status=400)
    from accounts.utils.firebase_chat import delete_message as fb_delete
    success, error = fb_delete(str(sender.uid), msg_uid)
    if not success:
        return JsonResponse({'status': 'error', 'message': error or 'Delete failed'}, status=400)
    return JsonResponse({'status': 'success'})

@login_required
@never_cache
def get_chat_messages(request, other_user_uid):
    user = request.user
    is_teacher = user.user_type == 'TEACHER'
    is_admin = user.is_superuser or user.is_staff or user.user_type == 'ADMIN'
    if not (is_teacher or is_admin):
        return JsonResponse({'messages': [], 'has_more': False})

    try:
        other = CustomUser.objects.get(uid=other_user_uid)
    except CustomUser.DoesNotExist:
        return JsonResponse({'messages': [], 'has_more': False})

    if not ((is_teacher and (other.is_superuser or other.user_type == 'ADMIN' or other.is_staff)) or
            (is_admin and other.user_type == 'TEACHER')):
        return JsonResponse({'messages': [], 'has_more': False})

    limit = int(request.GET.get('limit', 25))
    offset = int(request.GET.get('offset', 0))
    search_q = request.GET.get('search', '')

    from accounts.utils.firebase_chat import get_messages, mark_read
    fb_msgs, has_more = get_messages(str(user.uid), str(other_user_uid), limit=limit, offset=offset, search=search_q)

    mark_read(str(user.uid), str(other_user_uid))

    data = []
    from datetime import datetime as dt_mod
    _sender_cache = {}
    def _resolve_name(sender_uid):
        if sender_uid not in _sender_cache:
            u = CustomUser.objects.filter(uid=sender_uid).only('user_type', 'full_name', 'username', 'chat_display_name').first()
            _sender_cache[sender_uid] = u.chat_display if u else ''
        return _sender_cache[sender_uid]
    for m in fb_msgs:
        is_me = str(m['sender_uid']) == str(user.uid)
        raw_ts = m.get('created_at', 0)
        ts_str = dt_mod.fromtimestamp(raw_ts / 1000).strftime('%b %d, %I:%M %p') if raw_ts else ''
        sender_name = _resolve_name(m['sender_uid'])
        data.append({
            'message_uid': m['uid'],
            'sender_uid': m['sender_uid'],
            'sender_name': sender_name,
            'message': m['message'],
            'timestamp': ts_str,
            'raw_ts': raw_ts,
            'is_me': is_me,
            'is_edited': m.get('edited_at') is not None,
            'is_deleted': m.get('deleted', False),
            'read_at': m.get('read_at'),
            'edited_at': m.get('edited_at'),
        })

    return JsonResponse({'messages': data, 'has_more': has_more})

@login_required
def get_chat_list(request):
    from django.db.models import Q

    user = request.user
    is_teacher = user.user_type == 'TEACHER'
    is_admin_user = user.is_superuser or user.is_staff or user.user_type == 'ADMIN'

    if not (is_teacher or is_admin_user):
        return JsonResponse({'users': []})

    if is_teacher:
        chat_partner_filter = Q(user_type='ADMIN') | Q(is_superuser=True)
    else:
        chat_partner_filter = Q(user_type='TEACHER')

    all_partners = CustomUser.objects.filter(
        chat_partner_filter, status='ACTIVE'
    ).exclude(uid=user.uid).only('uid', 'full_name', 'username', 'image', 'user_type', 'chat_display_name')

    partner_map = {str(u.uid): u for u in all_partners}

    from accounts.utils.firebase_chat import get_chat_list as fb_get_chat_list
    fb_rooms = fb_get_chat_list(str(user.uid), user.user_type)

    result = []
    seen = set()

    for room in fb_rooms:
        other_uid = room['other_uid']
        if other_uid not in partner_map:
            continue
        u = partner_map[other_uid]
        name = u.chat_display if u.user_type == 'ADMIN' else (u.full_name or u.username)
        result.append({
            'uid': other_uid,
            'name': name,
            'last_message': room.get('last_message', '') or 'No messages yet',
            'unread_count': room.get('unread_count', 0),
            'profile_photo': u.avatar_url,
        })
        seen.add(other_uid)

    remaining = [u for u in partner_map.values() if str(u.uid) not in seen]
    remaining.sort(key=lambda u: (u.full_name or u.username).lower())
    for u in remaining:
        uid_str = str(u.uid)
        name = u.chat_display if u.user_type == 'ADMIN' else (u.full_name or u.username)
        result.append({
            'uid': uid_str,
            'name': name,
            'last_message': 'No messages yet',
            'unread_count': 0,
            'profile_photo': u.avatar_url,
        })

    return JsonResponse({'users': result})





@login_required
def mark_notification_read(request, notif_uid):
    mark_read(str(request.user.uid), notif_uid)
    from django.core.cache import cache
    cache.delete(f"pending_counts_{request.user.id}_{request.user.user_type}")
    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({"status": "read"})
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def delete_notification(request, notif_uid):
    from .utils.notification_helper import delete_notification as db_del
    db_del(str(request.user.uid), notif_uid)
    from django.core.cache import cache
    cache.delete(f"pending_counts_{request.user.id}_{request.user.user_type}")
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({"status": "deleted"})
    messages.success(request, "Notification deleted.")
    return redirect(request.META.get('HTTP_REFERER', '/'))

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_analytics_view(request):
    from django.db.models import Count
    from datetime import datetime, timedelta
    from django.utils import timezone
    from django.core.cache import cache

    cache_key = f'teacher_analytics_{request.user.uid}'
    cached = cache.get(cache_key)
    if cached:
        cached['notifications'] = (get_notifications(str(request.user.uid))[0])[:10]
        cached['unread_notifications_count'] = get_unread_count(str(request.user.uid))
        return render(request, 'teacher_portal/analytics.html', cached)

    # Get courses provided by this teacher
    courses = Course.objects.filter(teacher=request.user).annotate(enroll_count=Count('enrollments')).only('id', 'title').order_by('-enroll_count')
    
    course_labels = [c.title for c in courses]
    course_data = [c.enroll_count for c in courses]
    
    # Enrollment trend (last 7 days)
    today = timezone.now().date()
    enrollment_trend_labels = []
    enrollment_trend_data = []
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        enrollment_trend_labels.append(day.strftime('%b %d'))
        count = Enrollment.objects.filter(
            course__teacher=request.user,
            enrolled_at__date=day
        ).count()
        enrollment_trend_data.append(count)
    
    total_courses = courses.count()
    total_students = sum(c.enroll_count for c in courses)
    
    context = {
        'total_courses': total_courses,
        'total_students': total_students,
        'course_labels': course_labels,
        'course_data': course_data,
        'trend_labels': enrollment_trend_labels,
        'trend_data': enrollment_trend_data,
    }
    cache.set(cache_key, context, 60)
    context['notifications'] = (get_notifications(str(request.user.uid))[0])[:10]
    context['unread_notifications_count'] = get_unread_count(str(request.user.uid))
    return render(request, 'teacher_portal/analytics.html', context)

@login_required
def mark_all_notifications_read(request):
    mark_all_read(str(request.user.uid))
    from django.core.cache import cache
    cache.delete(f"pending_counts_{request.user.id}_{request.user.user_type}")
    return redirect(request.META.get('HTTP_REFERER', '/'))

@xframe_options_exempt
@login_required(login_url='login')
@ratelimit(key='user', rate='60/m', block=True)
def access_resource(request, resource_uid):
    from accounts.models import CourseResource, Enrollment
    from django.shortcuts import get_object_or_404, redirect
    from django.http import HttpResponseForbidden, Http404
    
    resource = get_object_or_404(CourseResource, uid=resource_uid, is_deleted=False)
    
    is_teacher = (request.user.user_type == 'TEACHER' and resource.course.teacher == request.user)
    is_admin = getattr(request.user, 'is_staff', False) or request.user.user_type == 'ADMIN'
    
    if not (is_teacher or is_admin):
        if resource.status != 'APPROVED':
            raise Http404("Resource not found or not approved.")
        has_enrollment = Enrollment.objects.filter(user=request.user, course=resource.course).exists()
        if not has_enrollment:
            return HttpResponseForbidden("You are not enrolled in this course.")
    
    # Generate a short-lived signed URL — browser loads PDF directly from Supabase CDN
    if resource.firebase_file_path:
        try:
            from accounts.utils.storage_manager import StorageManager
            signed_url = StorageManager.generate_supabase_signed_url(resource.firebase_file_path, 10)
            if signed_url:
                return redirect(signed_url)
        except Exception as e:
            logger.error(f"Signed URL generation failed for {resource_uid}: {e}")
    
    return HttpResponseForbidden("Failed to retrieve resource. Please contact administrator.")


@xframe_options_exempt
@login_required(login_url='login')
def pdf_viewer(request, resource_uid):
    from accounts.models import CourseResource, Enrollment
    from django.shortcuts import get_object_or_404, redirect, render
    from django.http import Http404, HttpResponseForbidden

    resource = get_object_or_404(CourseResource, uid=resource_uid, is_deleted=False)

    is_teacher = (request.user.user_type == 'TEACHER' and resource.course.teacher == request.user)
    is_admin = getattr(request.user, 'is_staff', False) or request.user.user_type == 'ADMIN'

    if not (is_teacher or is_admin):
        if resource.status != 'APPROVED':
            raise Http404("Resource not found or not approved.")
        has_enrollment = Enrollment.objects.filter(user=request.user, course=resource.course).exists()
        if not has_enrollment:
            return HttpResponseForbidden("You are not enrolled in this course.")

    # Generate signed URL — PDF.js renders pages directly from Supabase CDN
    signed_url = None
    if resource.firebase_file_path:
        try:
            from accounts.utils.storage_manager import StorageManager
            signed_url = StorageManager.generate_supabase_signed_url(resource.firebase_file_path, 10)
        except Exception as e:
            logger.error(f"Signed URL failed in pdf_viewer for {resource_uid}: {e}")

    if not signed_url:
        return HttpResponseForbidden("Failed to retrieve resource. Please contact administrator.")

    # Track view on initial page load (not on iframe redirect)
    CourseResource.objects.filter(pk=resource.pk).update(view_count=F('view_count') + 1)

    return render(request, 'accounts/pdf_viewer.html', {
        'proxy_url': signed_url,
        'title': resource.title,
        'uid': resource.uid,
    })


@login_required(login_url='login')
@ratelimit(key='user', rate='20/m', block=True)
def download_resource(request, resource_uid):
    """Downloads a resource file with Content-Disposition: attachment for actual file download."""
    from accounts.models import CourseResource, Enrollment
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponseForbidden, Http404, StreamingHttpResponse
    
    resource = get_object_or_404(CourseResource, uid=resource_uid, is_deleted=False)
    
    is_teacher = (request.user.user_type == 'TEACHER' and resource.course.teacher == request.user)
    is_admin = getattr(request.user, 'is_staff', False) or request.user.user_type == 'ADMIN'
    
    if not (is_teacher or is_admin):
        if resource.status != 'APPROVED':
            raise Http404("Resource not found or not approved.")
        
        has_enrollment = Enrollment.objects.filter(user=request.user, course=resource.course).exists()
        if not has_enrollment:
            return HttpResponseForbidden("You are not enrolled in this course.")
        
        resource.download_count += 1
        resource.save(update_fields=['download_count'])
    
    # Stream file bytes from Supabase in chunks (never expose signed URL directly)
    if resource.firebase_file_path:
        try:
            from accounts.utils.storage_manager import StorageManager
            content_type = resource.mime_type or 'application/octet-stream'
            filename = f"{resource.title}.{resource.file_extension or 'pdf'}"

            signed_url = StorageManager.generate_supabase_signed_url(resource.firebase_file_path, 10)
            if not signed_url:
                raise ValueError("Failed to generate signed URL")

            import urllib.request
            def file_stream():
                with urllib.request.urlopen(signed_url) as upstream:
                    while True:
                        chunk = upstream.read(65536)
                        if not chunk:
                            break
                        yield chunk

            response = StreamingHttpResponse(file_stream(), content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            return response
        except Exception as e:
            logger.error(f"Resource proxy download failed for {resource_uid}: {e}")
    
    return HttpResponseForbidden("Failed to download resource. Please contact administrator.")


@login_required(login_url='login')
def stream_video(request, lesson_uid):
    from accounts.models import Lesson, Enrollment
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponseForbidden, Http404, StreamingHttpResponse
    from django.db.models import Q
    import requests

    lesson = get_object_or_404(Lesson, uid=lesson_uid)
    course = lesson.course
    is_teacher = (request.user.user_type == 'TEACHER' and course.teacher == request.user)
    is_admin = getattr(request.user, 'is_staff', False) or request.user.user_type == 'ADMIN'

    if not (is_teacher or is_admin):
        has_enrollment = Enrollment.objects.filter(user=request.user, course=course).exists()
        if not has_enrollment:
            return HttpResponseForbidden("You are not enrolled in this course.")

    if not lesson.video_file:
        raise Http404("No video file found for this lesson.")

    video_url = lesson.video_file.url
    if not video_url:
        raise Http404("No video file found for this lesson.")

    try:
        req = requests.get(video_url, stream=True)
        response = StreamingHttpResponse(
            req.iter_content(chunk_size=8192),
            content_type=req.headers.get('content-type', 'video/mp4')
        )
        response['Content-Disposition'] = 'inline'
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response['Pragma'] = 'no-cache'
        return response
    except Exception as e:
        logger.error(f"Video stream failed for {lesson_uid}: {e}")
        return HttpResponseForbidden("Failed to stream video.")


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def all_notifications(request):
    from django.shortcuts import render
    from .utils.notification_helper import cleanup_old_notifications
    
    cleanup_old_notifications()
    
    filter_keywords = None
    if request.user.user_type == 'STUDENT' and not getattr(request.user, 'is_staff', False):
        filter_keywords = ['added course', 'new content added to your course']
    
    notifications, _ = get_notifications(str(request.user.uid))
    
    if filter_keywords:
        notifications = [n for n in notifications if any(kw.lower() in n['message'].lower() for kw in filter_keywords)]
    
    from datetime import datetime as dt_mod, timezone as tz_mod
    for n in notifications:
        ts = n.get('created_at')
        if ts:
            n['created_at_display'] = dt_mod.fromtimestamp(ts / 1000, tz=tz_mod.utc).strftime('%b %d, %Y %I:%M %p')
        else:
            n['created_at_display'] = ''
    
    base_template = 'custom_admin/base_admin.html' if (request.user.user_type == 'ADMIN' or request.user.is_superuser) else 'accounts/base.html'
    if request.user.user_type == 'TEACHER' and not request.user.is_superuser:
        base_template = 'teacher_portal/base_teacher.html'
    
    return render(request, 'accounts/all_notifications.html', {
        'notifications': notifications,
        'base_template': base_template
    })
@login_required
def firebase_notification_list(request):
    """REST endpoint: Get paginated Firebase notifications for bell."""
    from django.http import JsonResponse
    from .utils.notification_helper import get_notifications
    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 25))
    offset = (page - 1) * limit
    notifs, total = get_notifications(user_uid=str(request.user.uid), limit=limit, offset=offset)
    return JsonResponse({'notifications': notifs, 'total': total, 'page': page})


@login_required
@require_POST
def firebase_notification_mark_read(request, notif_uid):
    """REST endpoint: Mark one notification as read."""
    from django.http import JsonResponse
    from .utils.notification_helper import mark_read
    mark_read(str(request.user.uid), notif_uid)
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def firebase_notification_mark_all_read(request):
    """REST endpoint: Mark all notifications as read."""
    from django.http import JsonResponse
    from .utils.notification_helper import mark_all_read
    mark_all_read(str(request.user.uid))
    return JsonResponse({'status': 'ok'})


def update_last_seen(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'ok'})
    request.user.last_seen = timezone.now()
    request.user.save(update_fields=['last_seen'])
    return JsonResponse({'status': 'ok'})


def get_unread_counts(request):
    from django.http import JsonResponse
    from .utils.notification_helper import cleanup_old_notifications

    cleanup_old_notifications()

    notif_count = get_unread_count(str(request.user.uid))

    chat_count = 0
    can_chat = request.user.user_type == 'TEACHER' or request.user.is_superuser or request.user.is_staff or request.user.user_type == 'ADMIN'
    if can_chat:
        from accounts.utils.firebase_chat import get_unread_count as fb_get_unread_count
        chat_count = fb_get_unread_count(str(request.user.uid), request.user.user_type)

    return JsonResponse({
        'notifications': notif_count,
        'chat': chat_count
    })

# ====== ENTERPRISE OTP RECOVERY PIPELINE ======
from .utils.otp_engine import OTPEngine
import secrets
from django.contrib.auth.hashers import make_password, check_password


@csrf_protect
def forgot_password(request):
    user_type = request.GET.get('type', 'student').upper()
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        if not username and not email:
            messages.error(request, "Please enter both username and email.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        user_by_username = CustomUser.objects.filter(username=username).first() if username else None
        user_by_email = CustomUser.objects.filter(email=email).first() if email else None
        if not user_by_username and not user_by_email:
            messages.error(request, "Invalid credentials.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        if not user_by_username:
            messages.error(request, "Username is incorrect.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        if not user_by_email:
            messages.error(request, "Email is incorrect.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        if user_by_username != user_by_email:
            messages.error(request, "Invalid credentials.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        user = user_by_username
        if user.is_superuser:
            messages.error(request, "Password reset is not available for this account.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        from django.utils import timezone
        from datetime import timedelta
        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_count = PasswordResetOTP.objects.filter(user=user, created_at__gte=one_hour_ago).count()
        if recent_count >= 5:
            messages.error(request, "Too many reset requests. Please try again later.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        code = f"{secrets.randbelow(1000000):06d}"
        expires_at = timezone.now() + timedelta(minutes=5)
        otp_obj = PasswordResetOTP.objects.create(
            user=user,
            otp_hash=make_password(code),
            expires_at=expires_at,
        )
        PasswordResetOTP.objects.filter(user=user, expires_at__gt=timezone.now()).exclude(id=otp_obj.id).delete()
        request.session['reset_user_uid'] = str(user.uid)
        request.session['reset_otp_id'] = otp_obj.id
        request.session['reset_raw_code'] = code
        return redirect('verify_reset_code')
    return render(request, 'accounts/forgot_password.html', {'user_type': user_type})


@csrf_protect
def verify_reset_code(request):
    user_uid = request.session.get('reset_user_uid')
    otp_id = request.session.get('reset_otp_id')
    raw_code = request.session.pop('reset_raw_code', None)

    # Resend OTP — auto-generate new code, keep user in session
    if request.GET.get('resend') and user_uid:
        try:
            user = CustomUser.objects.get(uid=user_uid)
            old_expires = PasswordResetOTP.objects.filter(user=user).delete()
            code = f"{secrets.randbelow(1000000):06d}"
            from datetime import timedelta
            expires_at = timezone.now() + timedelta(minutes=5)
            otp_obj = PasswordResetOTP.objects.create(
                user=user,
                otp_hash=make_password(code),
                expires_at=expires_at,
            )
            request.session['reset_otp_id'] = otp_obj.id
            request.session['reset_raw_code'] = code
            messages.success(request, "A new verification code has been generated.")
            return redirect('verify_reset_code')
        except Exception:
            request.session.pop('reset_user_uid', None)
            request.session.pop('reset_otp_id', None)
            request.session.pop('reset_raw_code', None)
            messages.error(request, "Could not resend code. Please request again.")
            return redirect('forgot_password')

    if not user_uid or not otp_id:
        messages.error(request, "Session expired. Please restart the password reset process.")
        return redirect('forgot_password')
    try:
        user = CustomUser.objects.get(uid=user_uid)
        otp_obj = PasswordResetOTP.objects.get(id=otp_id, user=user)
    except (CustomUser.DoesNotExist, PasswordResetOTP.DoesNotExist):
        messages.error(request, "Session expired. Please restart the password reset process.")
        return redirect('forgot_password')
    if request.method == 'POST':
        if otp_obj.is_expired():
            otp_obj.delete()
            request.session.pop('reset_otp_id', None)
            messages.error(request, "The code has expired. Please request a new one.")
            return redirect('forgot_password')
        if otp_obj.is_blocked():
            otp_obj.delete()
            request.session.pop('reset_otp_id', None)
            messages.error(request, "Too many failed attempts. Please request a new code.")
            return redirect('forgot_password')
        raw_input = request.POST.get('code', '').strip()
        if not raw_input or not raw_input.isdigit() or len(raw_input) != 6:
            otp_obj.attempts += 1
            otp_obj.save()
            remaining = 5 - otp_obj.attempts
            messages.error(request, f"Invalid code. {remaining} attempt(s) remaining.")
            return render(request, 'accounts/verify_reset_code.html', {'raw_code': raw_code, 'expires_at': otp_obj.expires_at})
        if check_password(raw_input, otp_obj.otp_hash):
            request.session['reset_verified'] = True
            messages.success(request, "Verification successful. Please set a new password.")
            return redirect('set_new_password')
        else:
            otp_obj.attempts += 1
            otp_obj.save()
            remaining = 5 - otp_obj.attempts
            if remaining <= 0:
                otp_obj.delete()
                request.session.pop('reset_otp_id', None)
                messages.error(request, "Too many failed attempts. Please request a new code.")
                return redirect('forgot_password')
            messages.error(request, f"Invalid code. {remaining} attempt(s) remaining.")
            return render(request, 'accounts/verify_reset_code.html', {'raw_code': raw_code, 'expires_at': otp_obj.expires_at})
    return render(request, 'accounts/verify_reset_code.html', {'raw_code': raw_code, 'expires_at': otp_obj.expires_at})


@csrf_protect
def set_new_password(request):
    user_uid = request.session.get('reset_user_uid')
    is_verified = request.session.get('reset_verified')
    if not user_uid or not is_verified:
        messages.error(request, "Security verification required. Please restart the process.")
        return redirect('forgot_password')
    try:
        user = CustomUser.objects.get(uid=user_uid)
    except CustomUser.DoesNotExist:
        messages.error(request, "Security verification required. Please restart the process.")
        return redirect('forgot_password')
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/set_new_password.html')
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
            return render(request, 'accounts/set_new_password.html')
        user.set_password(new_password)
        user.save()
        PasswordResetOTP.objects.filter(user=user).delete()
        request.session.flush()
        messages.success(request, "Password updated successfully.")
        if user.user_type == 'TEACHER':
            return redirect('teacher_login')
        return redirect('login')
    return render(request, 'accounts/set_new_password.html')


def recover_username(request):
    user_type = request.GET.get('type', 'student').upper()
    
    if request.method == 'POST':
        email = request.POST.get('email')
        user = CustomUser.objects.filter(email=email).first()
        
        if user:
            result = OTPEngine.create_otp(user, 'USERNAME_RECOVERY', request)
            if isinstance(result, tuple) and result[0] is not None:
                raw_otp, otp_obj = result
                success = OTPEngine.send_otp_email(user, raw_otp, 'USERNAME_RECOVERY')
                
                if success is not True:
                    messages.warning(request, f"Demo Mode: Email blocked by server. Your recovery code is: {raw_otp}")
                else:
                    messages.success(request, f"✅ Verification code sent to {email}.")
                request.session['recovery_otp_uid'] = str(otp_obj.uid)
                request.session['recovery_user_uid'] = str(user.uid)
                return redirect('verify_otp')
            else:
                msg = result[1] if isinstance(result, tuple) else "Verification system unavailable."
                messages.error(request, f"🛡️ {msg}")
                return redirect('login' if user_type == 'STUDENT' else 'teacher_login')
        else:
            messages.error(request, "No account found with this email.")
            
    return render(request, 'accounts/recover_username.html', {'user_type': user_type})

def verify_otp(request):
    otp_uid = request.session.get('recovery_otp_uid')
    user_uid = request.session.get('recovery_user_uid')
    
    if not otp_uid or not user_uid:
        messages.error(request, "Session expired. Please restart recovery.")
        return redirect('forgot_password')
        
    try:
        otp_obj = get_object_or_404(EmailOTP, uid=otp_uid)
        user = get_object_or_404(CustomUser, uid=user_uid)
        
        if request.method == 'POST':
            raw_otp = request.POST.get('otp')
            success, msg = OTPEngine.verify_otp(user, raw_otp, otp_obj.purpose)
            
            if success:
                messages.success(request, "✅ Verification successful.")
                if otp_obj.purpose == 'PASSWORD_RESET':
                    request.session['otp_verified_for_reset'] = True
                    return redirect('reset_password')
                elif otp_obj.purpose == 'USERNAME_RECOVERY':
                    return render(request, 'accounts/username_revealed.html', {'target_user': user})
            else:
                messages.error(request, f"❌ {msg}")
                
        return render(request, 'accounts/verify_otp.html', {
            'user': user,
            'purpose': otp_obj.get_purpose_display(),
            'expires_at': otp_obj.expires_at
        })
    except Exception as e:
        logger.error(f"OTP Verification Error: {str(e)}")
        messages.error(request, "An unexpected error occurred during verification. Please try again.")
        return redirect('forgot_password')

def reset_password(request):
    user_uid = request.session.get('recovery_user_uid')
    is_verified = request.session.get('otp_verified_for_reset')
    
    if not user_uid or not is_verified:
        messages.error(request, "Security verification required.")
        return redirect('forgot_password')
        
    user = get_object_or_404(CustomUser, uid=user_uid)
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/reset_password.html', {'user': user})
            
        is_strong, strength_msg = is_strong_password(new_password)
        if not is_strong:
            messages.error(request, strength_msg)
            return render(request, 'accounts/reset_password.html', {'user': user})
            
        user.set_password(new_password)
        user.save()
        
        request.session.flush()
        messages.success(request, "✅ Account updated successfully. Please login.")
        return redirect('login' if user.user_type == 'STUDENT' else 'teacher_login')
        
    return render(request, 'accounts/reset_password.html', {'user': user})


@ratelimit(key='user', rate='10/m', method='POST', block=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def init_video_upload(request):
    """
    Phase 1: Create UploadJob + Lesson and YouTube resumable session.
    Browser uploads MP4 directly to YouTube — zero server bytes.
    Idempotent: same idempotency_key returns same UploadJob.
    Stores hash of first 5MB for resume file verification.
    """
    import json
    from django.utils import timezone as tz

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        course_uid = data.get('course_uid')
        title = data.get('title', '').strip()
        order = data.get('order', 1)
        chapter = data.get('chapter', '')
        file_size = data.get('file_size')
        idempotency_key = data.get('idempotency_key', '')
        mime_type = data.get('mime_type', 'video/mp4')
        file_hash = data.get('file_hash_first_5mb', '')

        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)

        course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
        course_is_published = course.status == 'PUBLISHED' and course.is_approved

        now = tz.now()

        if idempotency_key:
            existing_job = UploadJob.objects.filter(
                idempotency_key=idempotency_key,
                teacher=request.user,
            ).first()
            if existing_job:
                if existing_job.status in ('COMPLETED',):
                    return JsonResponse({
                        'lesson_uid': str(existing_job.lesson.uid) if existing_job.lesson else '',
                        'status': 'already_complete',
                        'upload_job_uid': str(existing_job.uid),
                    })
                if existing_job.youtube_upload_url and existing_job.status in ('UPLOADING', 'PENDING'):
                    from .utils.youtube_uploader import query_uploaded_bytes
                    youtube_bytes = query_uploaded_bytes(
                        existing_job.youtube_upload_url,
                        existing_job.access_token,
                        existing_job.file_size or 0,
                    )
                    if youtube_bytes == -2:
                        return JsonResponse({
                            'lesson_uid': str(existing_job.lesson.uid) if existing_job.lesson else '',
                            'status': 'session_expired',
                            'upload_job_uid': str(existing_job.uid),
                            'message': 'Upload session expired. A new session will be created.',
                        })
                    if youtube_bytes == -1:
                        existing_job.uploaded_bytes = existing_job.file_size
                        existing_job.progress_percentage = 100
                        existing_job.save(update_fields=['uploaded_bytes', 'progress_percentage'])
                    elif youtube_bytes > 0:
                        existing_job.uploaded_bytes = youtube_bytes
                        existing_job.progress_percentage = min(int((youtube_bytes / max(existing_job.file_size, 1)) * 100), 99)
                        existing_job.last_activity = now
                        existing_job.save(update_fields=['uploaded_bytes', 'progress_percentage', 'last_activity'])
                    return JsonResponse({
                        'lesson_uid': str(existing_job.lesson.uid) if existing_job.lesson else '',
                        'upload_url': existing_job.youtube_upload_url,
                        'access_token': existing_job.access_token,
                        'upload_job_uid': str(existing_job.uid),
                        'uploaded_bytes': existing_job.uploaded_bytes,
                        'progress_percentage': existing_job.progress_percentage,
                        'resumed': True,
                        'file_hash_first_5mb': existing_job.file_hash_first_5mb,
                    })

        lesson = Lesson.objects.create(
            course=course,
            title=title,
            chapter=chapter,
            order=order,
            status='APPROVED' if course_is_published else 'PENDING',
            is_approved=course_is_published,
            upload_status='PENDING',
            youtube_upload_status='PENDING',
        )

        from .utils.youtube_uploader import create_resumable_upload_url
        result = create_resumable_upload_url(
            title=title,
            description=f'Lesson from course: {course.title}',
            file_size=file_size,
        )

        if not result or result.get('error'):
            error_msg = result.get('error', 'YouTube upload service unavailable.')
            lesson.delete()
            return JsonResponse({'error': error_msg}, status=500)

        upload_url = result['upload_url']
        access_token = result['access_token']
        session_expiry = now + timedelta(hours=23)

        upload_job = UploadJob.objects.create(
            teacher=request.user,
            lesson=lesson,
            title=title,
            file_size=file_size or 0,
            file_name=title,
            mime_type=mime_type,
            file_hash_first_5mb=file_hash,
            status='UPLOADING',
            progress_percentage=0,
            uploaded_bytes=0,
            youtube_upload_url=upload_url,
            access_token=access_token,
            idempotency_key=idempotency_key or None,
            chunk_size=5242880,
            last_activity=now,
            session_created_at=now,
            session_expires_at=session_expiry,
            client_ip=request.META.get('REMOTE_ADDR'),
            source_ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        lesson.upload_status = 'UPLOADING'
        lesson.youtube_upload_status = 'UPLOADING'
        lesson.save(update_fields=['upload_status', 'youtube_upload_status'])

        _log_upload_event(upload_job, 'UPLOAD_STARTED', {
            'file_size': file_size,
            'mime_type': mime_type,
            'file_name': title,
            'lesson_uid': str(lesson.uid),
            'course_uid': str(course_uid),
        }, request)

        return JsonResponse({
            'lesson_uid': str(lesson.uid),
            'upload_url': upload_url,
            'access_token': access_token,
            'upload_job_uid': str(upload_job.uid),
            'total_bytes': file_size or 0,
            'uploaded_bytes': 0,
            'progress_percentage': 0,
            'resumed': False,
            'file_hash_first_5mb': file_hash,
            'mime_type': mime_type,
            'chunk_size': upload_job.chunk_size,
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"init_video_upload error: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)


@ratelimit(key='user', rate='10/m', method='POST', block=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def youtube_upload_complete(request):
    """
    Phase 2: Browser finished uploading MP4 directly to YouTube.
    video_id captured from YouTube's final 200/201 response body by the browser.
    Saves video_id immediately. NEVER uses title-search auto_recover or fallback.
    Transitions UploadJob to YOUTUBE_PROCESSING for processing verification.
    """
    from django.utils import timezone as tz
    import json

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        lesson_uid_str = data.get('lesson_uid')
        video_id = data.get('video_id', '').strip()
        upload_job_uid = data.get('upload_job_uid', '')

        if not lesson_uid_str:
            return JsonResponse({'error': 'lesson_uid required'}, status=400)

        if not video_id:
            return JsonResponse({'error': 'video_id required - browser must capture YouTube response'}, status=400)

        now = tz.now()

        lesson = Lesson.objects.get(uid=lesson_uid_str, course__teacher=request.user)

        if lesson.youtube_video_id == video_id and lesson.upload_status == 'READY':
            if upload_job_uid:
                UploadJob.objects.filter(uid=upload_job_uid, teacher=request.user).update(
                    status='READY',
                    youtube_video_id=video_id,
                    progress_percentage=100,
                    completed_at=now,
                    last_activity=now,
                )
            return JsonResponse({'success': True, 'status': 'already_complete', 'video_id': video_id})

        course = lesson.course
        course_is_published = course.status == 'PUBLISHED' and course.is_approved

        lesson.youtube_video_id = video_id
        lesson.youtube_upload_status = 'UPLOADED'
        lesson.youtube_uploaded_at = now
        lesson.video_url = f'https://www.youtube.com/watch?v={video_id}'
        lesson.upload_status = 'PROCESSING'

        if course_is_published:
            lesson.status = 'APPROVED'
            lesson.is_approved = True

        update_fields = [
            'youtube_video_id', 'youtube_upload_status', 'youtube_uploaded_at',
            'upload_status', 'video_url',
        ]
        if course_is_published:
            update_fields.extend(['status', 'is_approved'])
        lesson.save(update_fields=update_fields)

        if upload_job_uid:
            try:
                job = UploadJob.objects.get(uid=upload_job_uid, teacher=request.user)
                job.status = 'UPLOADED'
                job.youtube_video_id = video_id
                job.youtube_url = lesson.video_url
                job.progress_percentage = 100
                job.processing_status = 'YOUTUBE_PROCESSING'
                job.last_activity = now
                job.save(update_fields=[
                    'status', 'youtube_video_id', 'youtube_url',
                    'progress_percentage', 'processing_status', 'last_activity',
                ])
                _log_upload_event(job, 'UPLOAD_COMPLETED', {
                    'video_id': video_id,
                    'lesson_uid': str(lesson.uid),
                }, request)
            except UploadJob.DoesNotExist:
                pass

        return JsonResponse({
            'success': True,
            'message': 'Video uploaded to YouTube successfully! YouTube is now processing the video.',
            'video_id': video_id,
            'upload_job_uid': upload_job_uid,
            'processing_status': 'YOUTUBE_PROCESSING',
        })
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'Lesson not found'}, status=404)
    except Exception as e:
        logger.error(f"youtube_upload_complete error: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)


@ratelimit(key='user', rate='10/m', method='POST', block=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def init_youtube_edit_upload(request):
    """
    Phase 1 of EDIT flow: create YouTube resumable upload session for existing lesson.
    Browser uploads MP4 directly to YouTube — no bytes pass through Django.
    Idempotent with session expiry detection + auto-renewal.
    """
    import json
    from django.utils import timezone as tz

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        lesson_uid_str = data.get('lesson_uid')
        file_size = data.get('file_size')
        idempotency_key = data.get('idempotency_key', '')
        file_hash = data.get('file_hash_first_5mb', '')
        mime_type = data.get('mime_type', 'video/mp4')

        if not lesson_uid_str:
            return JsonResponse({'error': 'lesson_uid required'}, status=400)

        lesson = get_object_or_404(Lesson, uid=lesson_uid_str, course__teacher=request.user)
        now = tz.now()

        if idempotency_key:
            existing_job = UploadJob.objects.filter(
                idempotency_key=idempotency_key,
                teacher=request.user,
            ).first()
            if existing_job:
                if existing_job.status in ('COMPLETED',):
                    return JsonResponse({
                        'lesson_uid': str(lesson.uid),
                        'status': 'already_complete',
                        'upload_job_uid': str(existing_job.uid),
                    })
                if existing_job.youtube_upload_url and existing_job.status in ('UPLOADING', 'PENDING'):
                    from .utils.youtube_uploader import query_uploaded_bytes
                    youtube_bytes = query_uploaded_bytes(
                        existing_job.youtube_upload_url,
                        existing_job.access_token,
                        existing_job.file_size or 0,
                    )
                    if youtube_bytes == -2:
                        return JsonResponse({
                            'lesson_uid': str(lesson.uid),
                            'status': 'session_expired',
                            'upload_job_uid': str(existing_job.uid),
                            'message': 'Upload session expired. A new session will be created.',
                        })
                    if youtube_bytes == -1:
                        existing_job.uploaded_bytes = existing_job.file_size
                        existing_job.progress_percentage = 100
                        existing_job.save(update_fields=['uploaded_bytes', 'progress_percentage'])
                    elif youtube_bytes > 0:
                        existing_job.uploaded_bytes = youtube_bytes
                        existing_job.progress_percentage = min(int((youtube_bytes / max(existing_job.file_size, 1)) * 100), 99)
                        existing_job.last_activity = now
                        existing_job.save(update_fields=['uploaded_bytes', 'progress_percentage', 'last_activity'])
                    return JsonResponse({
                        'lesson_uid': str(lesson.uid),
                        'upload_url': existing_job.youtube_upload_url,
                        'access_token': existing_job.access_token,
                        'upload_job_uid': str(existing_job.uid),
                        'uploaded_bytes': existing_job.uploaded_bytes,
                        'progress_percentage': existing_job.progress_percentage,
                        'resumed': True,
                        'file_hash_first_5mb': existing_job.file_hash_first_5mb,
                    })

        if lesson.is_approved and lesson.course.status == 'PUBLISHED' and lesson.course.is_approved:
            lesson.has_pending_edits = False
            lesson.pending_video_url = ''
            lesson.save(update_fields=['has_pending_edits', 'pending_video_url'])

        from .utils.youtube_uploader import create_resumable_upload_url
        result = create_resumable_upload_url(
            title=lesson.title,
            description=f'Updated lesson: {lesson.title}',
            file_size=file_size,
        )

        if not result or result.get('error'):
            error_msg = result.get('error', 'YouTube upload service unavailable.')
            return JsonResponse({'error': error_msg}, status=500)

        upload_url = result['upload_url']
        access_token = result['access_token']
        session_expiry = now + timedelta(hours=23)

        upload_job = UploadJob.objects.create(
            teacher=request.user,
            lesson=lesson,
            title=lesson.title,
            file_size=file_size or 0,
            file_name=lesson.title,
            mime_type=mime_type,
            file_hash_first_5mb=file_hash,
            status='UPLOADING',
            progress_percentage=0,
            uploaded_bytes=0,
            youtube_upload_url=upload_url,
            access_token=access_token,
            idempotency_key=idempotency_key or None,
            chunk_size=5242880,
            last_activity=now,
            session_created_at=now,
            session_expires_at=session_expiry,
            client_ip=request.META.get('REMOTE_ADDR'),
            source_ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        lesson.upload_status = 'UPLOADING'
        lesson.youtube_upload_status = 'UPLOADING'
        lesson.save(update_fields=['upload_status', 'youtube_upload_status'])

        return JsonResponse({
            'lesson_uid': str(lesson.uid),
            'upload_url': upload_url,
            'access_token': access_token,
            'upload_job_uid': str(upload_job.uid),
            'uploaded_bytes': 0,
            'progress_percentage': 0,
            'resumed': False,
            'file_hash_first_5mb': file_hash,
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"init_youtube_edit_upload error: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)


@ratelimit(key='user', rate='10/m', method='POST', block=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def youtube_edit_complete(request):
    """
    Phase 2 of EDIT flow: browser finished uploading replacement MP4 to YouTube.
    video_id captured by browser from YouTube's final response.
    Transitions to PROCESSING state — verification happens separately.
    MP4 bytes never touched Django.
    """
    from django.utils import timezone as tz
    import json

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    lesson_uid_str = data.get('lesson_uid')
    video_id = data.get('video_id', '').strip()
    upload_job_uid = data.get('upload_job_uid', '')

    if not lesson_uid_str:
        return JsonResponse({'error': 'lesson_uid required'}, status=400)

    if not video_id:
        return JsonResponse({'error': 'video_id required - browser must capture YouTube response'}, status=400)

    now = tz.now()

    try:
        lesson = Lesson.objects.get(uid=lesson_uid_str, course__teacher=request.user)
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'Lesson not found. The lesson may have been deleted.'}, status=404)

    if lesson.youtube_video_id == video_id and lesson.upload_status == 'READY':
        if upload_job_uid:
            UploadJob.objects.filter(uid=upload_job_uid, teacher=request.user).update(
                status='COMPLETED',
                youtube_video_id=video_id,
                progress_percentage=100,
                completed_at=now,
                last_activity=now,
            )
        return JsonResponse({'success': True, 'status': 'already_complete', 'video_id': video_id})

    new_youtube_url = f'https://www.youtube.com/watch?v={video_id}'
    course_is_published = lesson.course.status == 'PUBLISHED' and lesson.course.is_approved

    if lesson.is_approved and not course_is_published:
        lesson.pending_video_url = new_youtube_url
        lesson.has_pending_edits = True
        lesson.youtube_video_id = video_id
        lesson.youtube_upload_status = 'UPLOADED'
        lesson.youtube_uploaded_at = now
        lesson.upload_status = 'PROCESSING'
        lesson.save(update_fields=[
            'pending_video_url', 'has_pending_edits', 'youtube_video_id',
            'youtube_upload_status', 'youtube_uploaded_at', 'upload_status',
        ])
    elif lesson.is_approved and course_is_published:
        lesson.youtube_video_id = video_id
        lesson.youtube_upload_status = 'UPLOADED'
        lesson.youtube_uploaded_at = now
        lesson.upload_status = 'PROCESSING'
        lesson.video_url = new_youtube_url
        lesson.status = 'APPROVED'
        lesson.is_approved = True
        lesson.save(update_fields=[
            'youtube_video_id', 'youtube_upload_status', 'youtube_uploaded_at',
            'upload_status', 'video_url', 'status', 'is_approved',
        ])
    else:
        lesson.youtube_video_id = video_id
        lesson.youtube_upload_status = 'UPLOADED'
        lesson.youtube_uploaded_at = now
        lesson.upload_status = 'PROCESSING'
        lesson.video_url = new_youtube_url
        lesson.save(update_fields=[
            'youtube_video_id', 'youtube_upload_status', 'youtube_uploaded_at',
            'upload_status', 'video_url',
        ])

    if upload_job_uid:
        UploadJob.objects.filter(uid=upload_job_uid, teacher=request.user).update(
            status='UPLOADED',
            youtube_video_id=video_id,
            youtube_url=new_youtube_url,
            progress_percentage=100,
            uploaded_bytes=0,
            processing_status='PROCESSING',
            last_activity=now,
        )

    if auto_recover:
        logger.info(f"youtube_edit_complete auto_recover: Saved recovered video_id={video_id} to lesson {lesson_uid_str}")

    return JsonResponse({
        'success': True,
        'message': 'Video uploaded to YouTube successfully! YouTube is now processing.',
        'video_id': video_id,
        'processing_status': 'PROCESSING',
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def update_upload_progress(request, job_uid):
    """
    Reports chunk upload progress from browser to server.
    Only updates if new uploaded_bytes exceeds stored value (monotonic).
    Never resets to a lower value (protects against stale client reports).
    Accepts optional speed and eta fields for enhanced tracking.
    """
    import json
    from django.utils import timezone as tz

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uploaded_bytes = int(data.get('uploaded_bytes', 0))
    total_bytes = int(data.get('total_bytes', 0))
    speed = data.get('speed')
    eta = data.get('eta')

    try:
        job = UploadJob.objects.get(uid=job_uid, teacher=request.user)
    except UploadJob.DoesNotExist:
        return JsonResponse({'error': 'Upload job not found'}, status=404)

    if uploaded_bytes < job.uploaded_bytes:
        return JsonResponse({'success': True, 'progress_percentage': job.progress_percentage, 'note': 'stale_report_ignored'})

    progress = int((uploaded_bytes / total_bytes) * 100) if total_bytes > 0 else 0
    job.uploaded_bytes = uploaded_bytes
    job.progress_percentage = min(progress, 99)
    job.file_size = total_bytes
    job.last_activity = tz.now()

    update_fields = ['uploaded_bytes', 'progress_percentage', 'file_size', 'last_activity']
    job.save(update_fields=update_fields)

    return JsonResponse({
        'success': True,
        'progress_percentage': job.progress_percentage,
        'uploaded_bytes': job.uploaded_bytes,
        'total_bytes': job.file_size,
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def get_upload_status(request, job_uid):
    """
    Returns current upload status for resume/recovery.
    Includes ALL fields needed for resume: upload_url, access_token, hash, session expiry.
    Single source of truth for recovery modal.
    """
    try:
        job = UploadJob.objects.get(uid=job_uid, teacher=request.user)
    except UploadJob.DoesNotExist:
        return JsonResponse({'error': 'Upload job not found'}, status=404)

    return JsonResponse({
        'status': job.status,
        'progress_percentage': job.progress_percentage,
        'uploaded_bytes': job.uploaded_bytes,
        'total_bytes': job.file_size,
        'upload_uid': str(job.uid),
        'youtube_upload_url': job.youtube_upload_url or '',
        'access_token': job.access_token,
        'lesson_uid': str(job.lesson.uid) if job.lesson else '',
        'error_message': job.error_message,
        'youtube_video_id': job.youtube_video_id or '',
        'youtube_url': job.youtube_url or '',
        'processing_status': job.processing_status,
        'file_hash_first_5mb': job.file_hash_first_5mb,
        'mime_type': job.mime_type,
        'file_name': job.file_name,
        'chunk_size': job.chunk_size,
        'title': job.title,
        'retry_count': job.retry_count,
        'last_activity': job.last_activity.isoformat() if job.last_activity else '',
        'session_created_at': job.session_created_at.isoformat() if job.session_created_at else '',
        'session_expires_at': job.session_expires_at.isoformat() if job.session_expires_at else '',
        'created_at': job.created_at.isoformat(),
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def cancel_upload(request, job_uid):
    """
    Cancel an in-progress upload.
    Optionally deletes the lesson (keep_lesson=false) or keeps it as draft (keep_lesson=true).
    """
    import json
    from django.utils import timezone as tz

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    keep_lesson = data.get('keep_lesson', False)

    try:
        job = UploadJob.objects.get(uid=job_uid, teacher=request.user)
    except UploadJob.DoesNotExist:
        return JsonResponse({'error': 'Upload job not found'}, status=404)

    job.status = 'CANCELLED'
    job.error_message = 'Cancelled by teacher'
    job.last_activity = tz.now()
    job.save(update_fields=['status', 'error_message', 'last_activity'])

    lesson_deleted = False
    if job.lesson and not keep_lesson:
        lesson = job.lesson
        try:
            lesson.delete()
            job.lesson = None
            job.save(update_fields=['lesson'])
            lesson_deleted = True
        except Exception as e:
            logger.warning(f"cancel_upload: Could not delete lesson: {e}")

    _log_upload_event(job, 'CANCELLED', {
        'keep_lesson': keep_lesson,
        'lesson_deleted': lesson_deleted,
        'uploaded_bytes': job.uploaded_bytes,
    }, request)

    return JsonResponse({
        'success': True,
        'message': 'Upload cancelled.',
        'lesson_deleted': lesson_deleted,
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def pause_upload(request, job_uid):
    """
    Pause an in-progress upload without cancelling it.
    Upload can be resumed later from the same byte position.
    """
    from django.utils import timezone as tz

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        job = UploadJob.objects.get(uid=job_uid, teacher=request.user)
    except UploadJob.DoesNotExist:
        return JsonResponse({'error': 'Upload job not found'}, status=404)

    if job.status not in ('UPLOADING',):
        return JsonResponse({'error': f'Cannot pause job in status {job.status}'}, status=400)

    now = tz.now()
    job.last_activity = now
    job.save(update_fields=['last_activity'])

    _log_upload_event(job, 'PAUSED', {
        'uploaded_bytes': job.uploaded_bytes,
        'progress_percentage': job.progress_percentage,
    }, request)

    return JsonResponse({
        'success': True,
        'message': 'Upload paused. You can resume later.',
        'uploaded_bytes': job.uploaded_bytes,
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def list_active_uploads(request):
    """
    Returns all active uploads for the current teacher.
    Used to detect orphaned/in-progress uploads on page load.
    NOW INCLUDES youtube_upload_url and access_token for full recovery support.
    """
    active_jobs = UploadJob.objects.filter(
        teacher=request.user,
        status__in=['PENDING', 'UPLOADING'],
    ).order_by('-created_at')[:5]

    results = []
    for job in active_jobs:
        results.append({
            'uid': str(job.uid),
            'upload_uid': str(job.uid),
            'upload_job_uid': str(job.uid),
            'title': job.title,
            'total_bytes': job.file_size,
            'file_size': job.file_size,
            'progress_percentage': job.progress_percentage,
            'uploaded_bytes': job.uploaded_bytes,
            'status': job.status,
            'youtube_upload_url': job.youtube_upload_url or '',
            'access_token': job.access_token,
            'file_hash_first_5mb': job.file_hash_first_5mb,
            'mime_type': job.mime_type,
            'chunk_size': job.chunk_size,
            'last_activity': job.last_activity.isoformat() if job.last_activity else '',
            'created_at': job.created_at.isoformat(),
            'lesson_uid': str(job.lesson.uid) if job.lesson else '',
        })

    return JsonResponse({'uploads': results})


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def recover_lesson_view(request, lesson_uid):
    """
    Auto-recover a lesson whose video_id was not saved due to browser
    disconnect, callback failure, or any other upload interruption.
    Teacher opens lesson page → JS detects NULL youtube_video_id
    → calls this endpoint → searches YouTube for matching video → saves if found.
    """
    from django.utils import timezone as tz
    import json

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        lesson = Lesson.objects.get(uid=lesson_uid, course__teacher=request.user)
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'Lesson not found'}, status=404)

    if lesson.upload_status == 'READY' and lesson.youtube_video_id:
        return JsonResponse({'status': 'already_ready', 'youtube_video_id': lesson.youtube_video_id})

    if lesson.video_url and not lesson.youtube_video_id:
        return JsonResponse({'status': 'url_based', 'message': 'Lesson uses a direct URL, not YouTube upload.'})

    from .utils.youtube_uploader import find_latest_youtube_upload
    recovered_id = find_latest_youtube_upload(lesson.title)
    if not recovered_id:
        logger.info(f"recover_lesson_view: No matching video found for lesson {lesson_uid} ('{lesson.title}')")
        return JsonResponse({
            'status': 'not_found',
            'message': 'Could not find a matching video on YouTube. The upload may not have completed.',
        })

    lesson.youtube_video_id = recovered_id
    lesson.youtube_upload_status = 'UPLOADED'
    lesson.youtube_uploaded_at = tz.now()
    lesson.video_url = f'https://www.youtube.com/watch?v={recovered_id}'
    lesson.upload_status = 'READY'

    course = lesson.course
    course_is_published = course.status == 'PUBLISHED' and course.is_approved
    if course_is_published:
        lesson.status = 'APPROVED'
        lesson.is_approved = True

    update_fields = [
        'youtube_video_id', 'youtube_upload_status', 'youtube_uploaded_at',
        'upload_status', 'video_url',
    ]
    if course_is_published:
        update_fields.extend(['status', 'is_approved'])
    lesson.save(update_fields=update_fields)

    logger.info(f"recover_lesson_view: Recovered lesson {lesson_uid} → video_id={recovered_id}")
    return JsonResponse({
        'status': 'recovered',
        'youtube_video_id': recovered_id,
        'watch_url': lesson.video_url,
        'embed_url': f'https://www.youtube.com/embed/{recovered_id}',
        'thumbnail_url': f'https://img.youtube.com/vi/{recovered_id}/0.jpg',
    })


@csrf_exempt
@ratelimit(key='ip', rate='10/hour', method='POST', block=True)
def trigger_backup(request):
    """Triggers encrypted backup. Protected by rate limit + token auth."""
    import json, subprocess, sys, os, threading
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
        token = body.get('token', '')
        expected = os.getenv('BACKUP_TOKEN', '')
        if not expected or not hmac.compare_digest(token, expected):
            logger.warning(f"Unauthorized backup attempt from {request.META.get('REMOTE_ADDR')}")
            return JsonResponse({'error': 'Forbidden'}, status=403)
    except:
        return JsonResponse({'error': 'Bad request'}, status=400)

    def run_backup():
        try:
            manage_py = os.path.join(settings.BASE_DIR, 'manage.py')
            result = subprocess.run(
                [sys.executable, manage_py, 'backup_all', '--retention', '--cron'],
                capture_output=True, text=True, timeout=600
            )
            logger.info(f"Backup {'succeeded' if result.returncode == 0 else 'failed'}")
        except Exception as e:
            logger.error(f"Backup failed: {e}")

    thread = threading.Thread(target=run_backup, daemon=True)
    thread.start()
    return JsonResponse({'success': True, 'message': 'Backup started'})


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def verify_processing_view(request, job_uid):
    """
    Polled by frontend after upload complete.
    Checks YouTube processingDetails via API.
    Enterprise workflow: UPLOADED -> YOUTUBE_PROCESSING -> SUCCEEDED -> READY
    Transitions UploadJob: YOUTUBE_PROCESSING -> SUCCEEDED -> READY / FAILED
    Transitions Lesson: PROCESSING -> READY / FAILED
    """
    from django.utils import timezone as tz
    from .utils.youtube_uploader import verify_youtube_processing_status, get_video_thumbnail_status

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        job = UploadJob.objects.get(uid=job_uid, teacher=request.user)
    except UploadJob.DoesNotExist:
        return JsonResponse({'error': 'Upload job not found'}, status=404)

    if not job.youtube_video_id:
        return JsonResponse({'error': 'No video_id to verify'}, status=400)

    processing_state = verify_youtube_processing_status(job.youtube_video_id)
    now = tz.now()

    if processing_state == 'VERIFIED':
        thumbnail_info = get_video_thumbnail_status(job.youtube_video_id)
        job.processing_status = 'VERIFIED'
        job.processing_verified_at = now
        job.status = 'READY'
        job.completed_at = now
        job.youtube_url = f'https://www.youtube.com/watch?v={job.youtube_video_id}'
        job.save(update_fields=[
            'processing_status', 'processing_verified_at', 'status',
            'completed_at', 'youtube_url', 'last_activity',
        ])

        if job.lesson:
            lesson = job.lesson
            lesson.upload_status = 'READY'
            lesson.processing_verified_at = now
            lesson.save(update_fields=['upload_status', 'processing_verified_at'])

        _log_upload_event(job, 'PROCESSING_VERIFIED', {
            'video_id': job.youtube_video_id,
            'has_thumbnail': thumbnail_info.get('has_thumbnail', False),
        }, request)

        return JsonResponse({
            'status': 'VERIFIED',
            'ready': True,
            'thumbnail_available': thumbnail_info.get('has_thumbnail', False),
            'thumbnail_url': thumbnail_info.get('thumbnail_url', ''),
        })

    elif processing_state == 'FAILED':
        job.processing_status = 'FAILED'
        job.status = 'FAILED'
        job.error_message = 'YouTube processing failed'
        job.save(update_fields=['processing_status', 'status', 'error_message', 'last_activity'])

        if job.lesson:
            lesson = job.lesson
            lesson.upload_status = 'FAILED'
            lesson.save(update_fields=['upload_status'])

        _log_upload_event(job, 'FAILED', {
            'video_id': job.youtube_video_id,
            'reason': 'processing_failed',
        }, request)

        return JsonResponse({'status': 'FAILED', 'ready': False})

    else:
        job.processing_status = 'YOUTUBE_PROCESSING'
        job.processing_retry_count = (job.processing_retry_count or 0) + 1
        job.last_activity = now
        job.save(update_fields=['processing_status', 'processing_retry_count', 'last_activity'])

        return JsonResponse({'status': 'YOUTUBE_PROCESSING', 'ready': False})


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def renew_session_view(request, job_uid):
    """
    Creates a new YouTube resumable upload session when the old one expires.
    Called when browser detects 404/410 from YouTube during resume.
    Preserves all progress: queries YouTube for last received byte.
    """
    import json
    from django.utils import timezone as tz

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        job = UploadJob.objects.get(uid=job_uid, teacher=request.user)
    except UploadJob.DoesNotExist:
        return JsonResponse({'error': 'Upload job not found'}, status=404)

    if job.status not in ('UPLOADING', 'PENDING'):
        return JsonResponse({'error': f'Cannot renew session for job in status {job.status}'}, status=400)

    now = tz.now()

    from .utils.youtube_uploader import renew_upload_session, query_uploaded_bytes

    query_result = query_uploaded_bytes(
        job.youtube_upload_url or '',
        job.access_token,
        job.file_size or 0,
    )

    if query_result not in (-2, -3):
        return JsonResponse({'status': 'session_still_valid', 'uploaded_bytes': query_result})

    result = renew_upload_session(
        title=job.title,
        description=f'Lesson: {job.title}',
        file_size=job.file_size,
    )

    if not result or result.get('error'):
        return JsonResponse({'error': result.get('error', 'Failed to renew upload session')}, status=500)

    session_expiry = now + timedelta(hours=23)
    job.youtube_upload_url = result['upload_url']
    job.access_token = result['access_token']
    job.session_created_at = now
    job.session_expires_at = session_expiry
    job.last_activity = now
    job.save(update_fields=['youtube_upload_url', 'access_token', 'session_created_at', 'session_expires_at', 'last_activity'])

    _log_upload_event(job, 'SESSION_RENEWED', {
        'uploaded_bytes': job.uploaded_bytes,
        'previous_session_created': job.session_created_at.isoformat() if job.session_created_at else '',
        'new_expiry': session_expiry.isoformat(),
    }, request)

    return JsonResponse({
        'status': 'renewed',
        'upload_url': result['upload_url'],
        'access_token': result['access_token'],
        'uploaded_bytes': job.uploaded_bytes,
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type in ('ADMIN', 'TEACHER'), login_url='login')
def upload_audit_log(request, job_uid):
    """
    Returns the full audit trail for a specific UploadJob.
    Admin or the owning teacher can access.
    """
    try:
        if request.user.user_type == 'ADMIN':
            job = UploadJob.objects.get(uid=job_uid)
        else:
            job = UploadJob.objects.get(uid=job_uid, teacher=request.user)
    except UploadJob.DoesNotExist:
        return JsonResponse({'error': 'Upload job not found'}, status=404)

    return JsonResponse({
        'uid': str(job.uid),
        'title': job.title,
        'status': job.status,
        'processing_status': job.processing_status,
        'file_name': job.file_name,
        'file_size': job.file_size,
        'mime_type': job.mime_type,
        'uploaded_bytes': job.uploaded_bytes,
        'progress_percentage': job.progress_percentage,
        'chunk_size': job.chunk_size,
        'youtube_video_id': job.youtube_video_id or '',
        'youtube_url': job.youtube_url or '',
        'error_message': job.error_message,
        'retry_count': job.retry_count,
        'processing_retry_count': job.processing_retry_count,
        'idempotency_key': job.idempotency_key or '',
        'session_created_at': job.session_created_at.isoformat() if job.session_created_at else '',
        'session_expires_at': job.session_expires_at.isoformat() if job.session_expires_at else '',
        'last_activity': job.last_activity.isoformat() if job.last_activity else '',
        'completed_at': job.completed_at.isoformat() if job.completed_at else '',
        'created_at': job.created_at.isoformat(),
        'client_ip': job.client_ip or '',
        'user_agent': job.user_agent,
    })

