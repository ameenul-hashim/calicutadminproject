from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import CustomUser, Course, Lesson, Enrollment, EmailOTP, DeletionRequest, PasswordResetOTP, ChatMessage
import uuid
from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.cache import cache_control, never_cache
import re
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
from accounts.utils.notification_helper import get_notifications, get_unread_count, mark_read, mark_all_read
import random
from django.db.models import F
from django.conf import settings
import cloudinary

# Explicitly configure cloudinary for use in helper functions
if hasattr(settings, 'CLOUDINARY_STORAGE'):
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_STORAGE.get('CLOUD_NAME'),
        api_key=settings.CLOUDINARY_STORAGE.get('API_KEY'),
        api_secret=settings.CLOUDINARY_STORAGE.get('API_SECRET'),
        secure=settings.CLOUDINARY_STORAGE.get('SECURE', True)
    )
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
                except Exception:
                    pass
            threading.Thread(target=_async_firebase_log, daemon=True).start()
        else:
            def _async_analytics():
                try:
                    from .utils.firebase_analytics import log_visit
                    log_visit(user)
                except Exception:
                    pass
            threading.Thread(target=_async_analytics, daemon=True).start()
    except Exception:
        pass

def create_notification(user, message):
    from .utils.firebase_db import notif_create
    notif_create(str(user.uid), message)

def notify_admins(message):
    from .models import CustomUser
    from .utils.firebase_db import notif_create
    admins = CustomUser.objects.filter(user_type='ADMIN')
    for admin in admins:
        notif_create(str(admin.uid), message)

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

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            messages.error(request, "Please enter a valid email address.")
            return render(request, 'accounts/signup.html', ctx)

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            messages.error(request, "Please enter a valid email address with a proper domain (e.g., name@domain.com).")
            return render(request, 'accounts/signup.html', ctx)

        if (CustomUser.objects.filter(username__iexact=username).exclude(status='REJECTED').exists() or
            CustomUser.objects.filter(email__iexact=email).exclude(status='REJECTED').exists() or
            CustomUser.objects.filter(phone_number=phone_number).exclude(status='REJECTED').exists()):
            messages.error(request, "This information conflicts with an existing account. Please check your details or try logging in.")
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
                if proof_file.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "PDF exceeds 200KB limit. Please optimize before uploading.")
                    return redirect('login')

                logger.debug("Uploading PDF to Supabase for %s", username)
                if not upload_user_proof(user, proof_file):
                    user.delete()
                    raise Exception("Supabase storage failure.")
            else:
                logger.debug("Processing image (%s) for %s", file_ext, username)
                optimized_pdf = convert_image_to_pdf(proof_file)
                
                if not optimized_pdf:
                    user.delete()
                    raise Exception("PDF conversion failed. File may be corrupted.")

                if not upload_user_proof(user, optimized_pdf):
                    user.delete()
                    raise Exception("Supabase upload failed.")
                
                logger.info("Student registration complete: %s", username)

            messages.success(request, "Registration successful! Admin approval pending.")
            notify_admins(f"New student: {username}.")
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
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
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
                if proof_file.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "PDF exceeds 200KB limit. Please optimize before uploading.")
                    return redirect('teacher_login')

                logger.debug("Teacher signup: uploading PDF to Supabase for %s", username)
                if not upload_user_proof(user, proof_file):
                    user.delete()
                    raise Exception("Supabase storage failure.")
            else:
                logger.debug("Teacher signup: processing image for %s", username)
                optimized_pdf = convert_image_to_pdf(proof_file)
                
                if not optimized_pdf:
                    user.delete()
                    raise Exception("PDF conversion failed. File may be corrupted.")

                if not upload_user_proof(user, optimized_pdf):
                    user.delete()
                    raise Exception("Supabase upload failed.")
                
                logger.info("Teacher registration complete for %s", username)

            messages.success(request, "Teacher registration successful! Admin review pending.")
            notify_admins(f"New teacher: {username}.")
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
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.status == 'PENDING':
                messages.warning(request, "Your account is PENDING approval. Please wait or contact administration.")
                return render(request, 'accounts/teacher_login.html')
            elif user.status == 'REJECTED':
                messages.error(request, "Your account was REJECTED. Please contact admin for details.")
                return render(request, 'accounts/teacher_login.html')
            elif user.status == 'BLOCKED':
                messages.error(request, "Your account has been BLOCKED. Access is restricted.")
                return render(request, 'accounts/teacher_login.html')
            
            if user.user_type != 'TEACHER':
                messages.error(request, "Invalid username or password. Please try again.")
                return render(request, 'accounts/teacher_login.html')
                
            if user.status == 'ACTIVE':
                login(request, user)
                request.session.set_expiry(0)
                log_login_attempt(request, user, status='SUCCESS')
                messages.success(request, f"Welcome, {user.full_name}!")
                return redirect('teacher_dashboard')
        else:
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
    
    # All approved and published courses not yet enrolled
    explore_courses = Course.objects.filter(status='PUBLISHED', is_approved=True)\
        .exclude(id__in=enrolled_ids)\
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
    # Other teachers' courses for viewing
    other_courses_qs = Course.objects.exclude(teacher=request.user)\
        .filter(is_approved=True)\
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
    from django.db.models import Count, Q
    courses_qs = Course.objects.filter(teacher=request.user).annotate(
        total_lessons=Count('lessons'),
        approved_lessons=Count('lessons', filter=Q(lessons__status='APPROVED')),
        pending_lessons=Count('lessons', filter=Q(lessons__status='PENDING')),
        rejected_lessons_count=Count('lessons', filter=Q(lessons__status='REJECTED'))
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
    from .models import DeletionRequest, Course
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    
    existing_request = DeletionRequest.objects.filter(
        teacher=request.user, item_type='Course', item_id=course.id, status='PENDING'
    ).first()
    
    if existing_request:
        messages.info(request, "A deletion request for this course is already pending admin approval.")
    else:
        DeletionRequest.objects.create(
            teacher=request.user,
            item_type='Course',
            item_id=course.id,
            item_name=course.title
        )
        messages.success(request, "Deletion request for course sent to admin.")
        notify_admins(f"Deletion Request: Teacher {request.user.username} requested to delete course '{course.title}'.")
        
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
        
        messages.success(request, f"Course '{title}' created as draft. You can now add lessons.")
        return redirect('course_lessons', course_uid=course.uid)
    
    return render(request, 'teacher_portal/create_course.html')

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_course(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        level = request.POST.get('level')
        
        thumbnail_file = None
        if request.FILES.get('thumbnail') or request.FILES.get('thumbnail_compressed'):
            thumbnail_file = request.FILES.get('thumbnail') or request.FILES.get('thumbnail_compressed')
            
        if course.is_approved:
            # Course is already approved, so store edits in pending fields to keep old version visible to student
            course.pending_title = title
            course.pending_description = description
            course.pending_category = category
            course.pending_level = level
            course.has_pending_edits = True
            
            if thumbnail_file:
                if thumbnail_file.size > 5 * 1024 * 1024:
                    messages.warning(request, "Thumbnail exceeds 5MB limit. Changes saved without thumbnail update.")
                else:
                    from .utils.cloudinary_helpers import upload_image_only
                    p_url, p_id = upload_image_only(thumbnail_file, folder="Neo Learner/courses")
                    if p_url:
                        if course.pending_image_public_id:
                            try:
                                import cloudinary.uploader
                                cloudinary.uploader.destroy(course.pending_image_public_id)
                            except Exception:
                                pass
                        course.pending_image = p_url
                        course.pending_image_public_id = p_id
            
            course.save()
            notify_admins(f"🔄 PENDING EDITS: Teacher {request.user.username} edited the approved course '{course.title}'. Changes are pending admin approval.")
            messages.success(request, f"Changes to '{course.title}' submitted for admin approval. Students will continue to see the previously approved version until approved.")
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
            notify_admins(f"🔄 COURSE UPDATE: Teacher {request.user.username} updated course '{course.title}'. It is now PENDING re-approval.")
            messages.success(request, f"Course '{course.title}' updated successfully!")
            
        return redirect('my_courses')
        
    return render(request, 'teacher_portal/edit_course.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def course_lessons(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    from .models import CourseResource, DeletionRequest
    from itertools import groupby

    lessons = course.lessons.all().only('id', 'title', 'order', 'status', 'is_approved', 'chapter', 'rejection_reason', 'created_at', 'video_url', 'uid', 'video_file', 'youtube_video_id', 'youtube_upload_status').order_by('chapter', 'order')
    resources = course.resources.filter(is_deleted=False).only('id', 'title', 'category', 'resource_type', 'status', 'is_approved', 'chapter', 'rejection_reason', 'uid', 'compressed_size', 'thumbnail_path').order_by('-created_at')

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

    # Merge Course.chapters list with derived chapter names
    course_chapters = list(course.chapters or [])
    derived_chapters = set(list(lesson_by_chapter.keys()) + list(res_by_chapter.keys()))
    all_chapter_names = []
    seen = set()
    for name in course_chapters + sorted(d for d in derived_chapters if d):
        if name and name not in seen:
            seen.add(name)
            all_chapter_names.append(name)
    # Remove empty chapter if no items
    if '' in all_chapter_names and not lesson_by_chapter.get('') and not res_by_chapter.get(''):
        all_chapter_names.remove('')

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
    if not old_name or not new_name:
        messages.error(request, "Both old and new chapter names are required.")
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
    chapters.remove(chapter_name)
    course.chapters = chapters
    course.save(update_fields=['chapters'])
    # Unlink lessons and resources — move them to uncategorized
    course.lessons.filter(chapter=chapter_name).update(chapter='')
    from .models import CourseResource
    CourseResource.objects.filter(course=course, chapter=chapter_name).update(chapter='')
    messages.success(request, f"Chapter '{chapter_name}' deleted. Content moved to uncategorized.")
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
            notify_admins(f"NEW CONTENT: Teacher {request.user.username} added lesson '{title}' to course '{course.title}'.")

        return redirect('course_lessons', course_uid=course.uid)
    
    chapter = request.GET.get('chapter', '')
    return render(request, 'teacher_portal/add_lesson.html', {'course': course, 'chapter': chapter})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_lesson(request, lesson_uid):
    """
    Handles YouTube URL lesson updates (form POST).
    MP4 file uploads use AJAX via /api/video/init-youtube-edit/ + browser→YouTube PUT.
    """
    lesson = get_object_or_404(Lesson, uid=lesson_uid, course__teacher=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        video_source = request.POST.get('video_source', 'file')
        video_url = request.POST.get('video_url', '')
        video_file = request.FILES.get('video_file')

        if video_source == 'file' and video_file:
            messages.error(request, "MP4 uploads must use the upload button. Please try again.")
            return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course})

        if video_source == 'file' and not video_file:
            messages.error(request, "Please upload a video file or select YouTube URL mode.")
            return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course})

        if video_source == 'url' and video_url:
            video_url = video_url.strip()
        elif video_source == 'url' and not video_url:
            video_url = lesson.video_url or ''
        elif video_source not in ('file', 'url'):
            messages.error(request, "Invalid video source selected.")
            return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course})

        order_raw = request.POST.get('order')
        order = max(int(order_raw), 1) if order_raw and order_raw.strip() else lesson.order

        youtube_match = re.search(r'(?:v=|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})', video_url)
        new_youtube_video_id = youtube_match.group(1) if youtube_match else None

        course_is_published = lesson.course.status == 'PUBLISHED' and lesson.course.is_approved

        if course_is_published:
            lesson.title = title
            if new_youtube_video_id:
                lesson.youtube_video_id = new_youtube_video_id
                lesson.youtube_upload_status = 'UPLOADED'
                lesson.youtube_uploaded_at = timezone.now()
            lesson.video_url = video_url
            lesson.order = order
            lesson.is_approved = True
            lesson.status = 'APPROVED'
            lesson.save()
            messages.success(request, "Lesson updated and immediately visible to students.")
        elif lesson.is_approved:
            lesson.pending_title = title
            lesson.pending_video_url = video_url
            lesson.pending_order = order
            lesson.has_pending_edits = True
            lesson.save()

            notify_admins(f"LESSON EDITS PENDING: Teacher {request.user.username} edited approved lesson '{lesson.title}'. Changes pending admin approval.")
            messages.success(request, "Lesson edits submitted for approval! Students will continue to view the current version until approved.")
        else:
            lesson.title = title
            if new_youtube_video_id:
                lesson.youtube_video_id = new_youtube_video_id
                lesson.youtube_upload_status = 'UPLOADED'
                lesson.youtube_uploaded_at = timezone.now()
            lesson.video_url = video_url
            lesson.order = order
            lesson.is_approved = False
            lesson.status = 'PENDING'
            lesson.save()

            messages.success(request, "Lesson updated successfully! It will be visible to students once re-approved by admin.")
            notify_admins(f"CONTENT UPDATE: Teacher {request.user.username} updated lesson '{lesson.title}'.")

        return redirect('course_lessons', course_uid=lesson.course.uid)

    return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course})

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
    
    # For PENDING/REJECTED lessons (not yet approved), delete immediately
    if lesson.status in ('PENDING', 'REJECTED'):
        from .utils.youtube_uploader import delete_youtube_video
        if lesson.youtube_video_id:
            try:
                delete_youtube_video(lesson.youtube_video_id)
            except Exception:
                pass
        lesson.delete()
        messages.success(request, "Lesson deleted successfully.")
        return redirect('course_lessons', course_uid=course_uid)
    
    # For APPROVED lessons — create a deletion request
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
        notify_admins(f"Deletion Request: Teacher {request.user.username} requested to delete lesson '{lesson.title}'.")
        
    return redirect('course_lessons', course_uid=course_uid)

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def add_resource(request, course_uid):
    from .utils.pdf_processor import validate_file, process_pdf
    from .utils.storage_manager import StorageManager
    from .models import CourseResource

    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if request.method == 'POST':
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

        # Pre-read size gate: 10MB raw upload limit
        MAX_UPLOAD_BYTES = 10 * 1024 * 1024
        if upload_file.size > MAX_UPLOAD_BYTES:
            messages.error(request, "File size exceeds the 10MB limit. Please upload a smaller PDF.")
            return redirect('course_lessons', course_uid=course.uid)
            
        try:
            from .utils.malware_scanner import scanner
            resource_type = 'PDF'
            mime_type, ext = validate_file(upload_file, upload_file.name, resource_type)
            if ext.lower() != 'pdf':
                messages.error(request, "Only PDF files are allowed. Please select a PDF file.")
                return redirect('course_lessons', course_uid=course.uid)
            is_infected, scan_reason = scanner.scan_file(upload_file)
            if is_infected:
                logger.warning("Security scan blocked | user=%s file=%s reason=%s ip=%s",
                    request.user.username, upload_file.name, scan_reason,
                    request.META.get('REMOTE_ADDR'))
                messages.error(request, "This file could not be uploaded because it does not meet our security requirements.")
                return redirect('course_lessons', course_uid=course.uid)
            file_bytes = upload_file.read()
            original_size = len(file_bytes)
            
            compressed_bytes, thumbnail_bytes = process_pdf(file_bytes)
            compressed_size = len(compressed_bytes)
            
            import uuid
            course_slug = re.sub(r'[^a-zA-Z0-9]', '-', course.title).strip('-').lower()
            course_slug = re.sub(r'-+', '-', course_slug)
            safe_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip()
            safe_title = re.sub(r'\s+', '-', safe_title)
            safe_title = re.sub(r'-+', '-', safe_title).lower()
            safe_title = safe_title[:40]
            category_folder = category.lower() if category else 'uncategorised'
            suffix = uuid.uuid4().hex[:4]
            dest_filename = f"{safe_title}-{suffix}.{ext}"
            # compressed_bytes is ALREADY compressed (process_pdf ran above) — only compressed saved
            dest_path = f"{course_slug}/{category_folder}/{dest_filename}"
            fb_path = StorageManager.upload_to_supabase_storage(compressed_bytes, dest_path, mime_type)
            
            thumb_path = None
            thumb_public_id = None
            if thumbnail_bytes:
                from accounts.utils.cloudinary_helpers import upload_image_only
                t_url, t_pid = upload_image_only(thumbnail_bytes, folder="Neo Learner/course_thumbnails")
                if t_url and t_pid:
                    thumb_path = t_url
                    thumb_public_id = t_pid
            
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
                notify_admins(f"🆕 NEW RESOURCE: Teacher {request.user.username} uploaded a PDF for course '{course.title}'.")

            CourseResource.objects.create(
                course=course,
                title=title,
                chapter=chapter,
                category=category,
                resource_type=resource_type,
                firebase_file_path=fb_path,
                backup_file_path=None,
                thumbnail_path=thumb_path,
                thumbnail_public_id=thumb_public_id,
                mime_type=mime_type,
                file_extension=ext,
                original_size=original_size,
                compressed_size=compressed_size,
                status=resource_status,
                is_approved=resource_approved
            )
            messages.success(request, success_msg)
        except Exception as e:
            logger.error("Resource upload error | user=%s course=%s error=%s",
                request.user.username, course.uid, str(e))
            messages.error(request, "An error occurred while uploading the file. Please try again.")
            
        return redirect('course_lessons', course_uid=course.uid)
        
    chapter = request.GET.get('chapter', '')
    return render(request, 'teacher_portal/add_resource.html', {'course': course, 'chapter': chapter})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_resource(request, resource_uid):
    from .utils.pdf_processor import validate_file, process_pdf
    from .utils.storage_manager import StorageManager
    from .models import CourseResource

    resource = get_object_or_404(CourseResource, uid=resource_uid, course__teacher=request.user)
    course = resource.course

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        category = request.POST.get('category', '').strip()
        upload_file = request.FILES.get('upload_file')

        if not title:
            messages.error(request, "Please enter a resource name.")
            return redirect('edit_resource', resource_uid=resource.uid)

        if not category or category not in ('ENGLISH', 'MALAYALAM', 'ONLINE'):
            messages.error(request, "Please select a category (English, Malayalam, or Online).")
            return redirect('edit_resource', resource_uid=resource.uid)

        resource_type = 'PDF'
        is_approved = resource.status == 'APPROVED'

        # If a new file is uploaded
        new_fb_path = None
        new_thumb_path = None
        new_thumb_pid = None
        new_mime = None
        new_ext = None
        new_orig_size = 0
        new_comp_size = 0

        if upload_file:
            # Pre-read size gate: 10MB
            MAX_UPLOAD_BYTES = 10 * 1024 * 1024
            if upload_file.size > MAX_UPLOAD_BYTES:
                messages.error(request, "File size exceeds the 10MB limit. Please upload a smaller PDF.")
                return redirect('edit_resource', resource_uid=resource.uid)
                
            try:
                from .utils.malware_scanner import scanner
                new_mime, new_ext = validate_file(upload_file, upload_file.name, resource_type)
                if new_ext.lower() != 'pdf':
                    messages.error(request, "Only PDF files are allowed. Please select a PDF file.")
                    return redirect('edit_resource', resource_uid=resource.uid)
                is_infected, scan_reason = scanner.scan_file(upload_file)
                if is_infected:
                    logger.warning("Security scan blocked | user=%s file=%s reason=%s ip=%s",
                        request.user.username, upload_file.name, scan_reason,
                        request.META.get('REMOTE_ADDR'))
                    messages.error(request, "This file could not be uploaded because it does not meet our security requirements.")
                    return redirect('edit_resource', resource_uid=resource.uid)
                file_bytes = upload_file.read()
                new_orig_size = len(file_bytes)
                
                compressed_bytes, thumbnail_bytes = process_pdf(file_bytes)
                new_comp_size = len(compressed_bytes)
                
                import uuid
                course_slug = re.sub(r'[^a-zA-Z0-9]', '-', course.title).strip('-').lower()
                course_slug = re.sub(r'-+', '-', course_slug)
                safe_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip()
                safe_title = re.sub(r'\s+', '-', safe_title)
                safe_title = re.sub(r'-+', '-', safe_title).lower()
                safe_title = safe_title[:40]
                category_folder = category.lower() if category else 'uncategorised'
                suffix = uuid.uuid4().hex[:4]
                dest_filename = f"{safe_title}-{suffix}.{new_ext}"
                # compressed_bytes is already compressed — only compressed version saved
                dest_path = f"{course_slug}/{category_folder}/{dest_filename}"
                new_fb_path = StorageManager.upload_to_supabase_storage(compressed_bytes, dest_path, new_mime)
                
                if thumbnail_bytes:
                    from accounts.utils.cloudinary_helpers import upload_image_only
                    t_url, t_pid = upload_image_only(thumbnail_bytes, folder="Neo Learner/course_thumbnails")
                    if t_url and t_pid:
                        new_thumb_path = t_url
                        new_thumb_pid = t_pid
            except Exception as e:
                logger.error("Resource edit error | user=%s resource=%s error=%s",
                    request.user.username, resource.uid, str(e))
                messages.error(request, "An error occurred while processing the file. Please try again.")
                return redirect('edit_resource', resource_uid=resource.uid)

        course_is_published = course.status == 'PUBLISHED' and course.is_approved

        if course_is_published:
            # For approved courses, save directly — no admin approval needed for edits
            if new_fb_path and resource.firebase_file_path:
                try:
                    StorageManager.delete_from_supabase_storage(resource.firebase_file_path)
                    if resource.thumbnail_public_id:
                        from accounts.utils.cloudinary_helpers import delete_temp_image
                        delete_temp_image(resource.thumbnail_public_id)
                except:
                    pass

            resource.title = title
            resource.category = category
            resource.resource_type = resource_type

            if new_fb_path:
                resource.firebase_file_path = new_fb_path
                resource.thumbnail_path = new_thumb_path
                resource.thumbnail_public_id = new_thumb_pid
                resource.mime_type = new_mime
                resource.file_extension = new_ext
                resource.original_size = new_orig_size
                resource.compressed_size = new_comp_size

            resource.status = 'APPROVED'
            resource.is_approved = True
            resource.rejection_reason = None
            resource.has_pending_edits = False
            resource.save()
            messages.success(request, f"Resource '{title}' updated and immediately available to students.")
        elif is_approved:
            # For approved resources in non-published courses, use pending fields
            resource.pending_title = title
            resource.pending_category = category
            resource.pending_resource_type = resource_type
            
            if new_fb_path:
                resource.pending_firebase_file_path = new_fb_path
                resource.pending_thumbnail_path = new_thumb_path
                resource.pending_thumbnail_public_id = new_thumb_pid
                resource.pending_mime_type = new_mime
                resource.pending_file_extension = new_ext
                resource.pending_original_size = new_orig_size
                resource.pending_compressed_size = new_comp_size
                
            resource.has_pending_edits = True
            resource.save()
            messages.success(request, f"Changes to resource '{title}' submitted for admin review.")
            notify_admins(f"🔄 RESOURCE EDIT: Teacher {request.user.username} edited approved resource '{resource.title}'.")
        else:
            # For PENDING or REJECTED resources, overwrite directly and set to PENDING
            # Delete old file if a new one is uploaded
            if new_fb_path and resource.firebase_file_path:
                try:
                    StorageManager.delete_from_supabase_storage(resource.firebase_file_path)
                    if resource.thumbnail_public_id:
                        from accounts.utils.cloudinary_helpers import delete_temp_image
                        delete_temp_image(resource.thumbnail_public_id)
                except:
                    pass
                
            resource.title = title
            resource.category = category
            resource.resource_type = resource_type
            
            if new_fb_path:
                resource.firebase_file_path = new_fb_path
                resource.thumbnail_path = new_thumb_path
                resource.thumbnail_public_id = new_thumb_pid
                resource.mime_type = new_mime
                resource.file_extension = new_ext
                resource.original_size = new_orig_size
                resource.compressed_size = new_comp_size
            
            resource.status = 'PENDING'
            resource.is_approved = False
            resource.rejection_reason = None # Clear reason on resubmission
            resource.save()
            messages.success(request, f"Resource '{title}' updated and resubmitted for approval.")
            notify_admins(f"🆕 RESOURCE RESUBMISSION: Teacher {request.user.username} updated resource '{title}'.")

        return redirect('course_lessons', course_uid=course.uid)

    return render(request, 'teacher_portal/edit_resource.html', {'resource': resource})

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

    # If still PENDING / REJECTED (not yet approved), allow immediate deletion
    if resource.status in ('PENDING', 'REJECTED'):
        from .utils.storage_manager import StorageManager
        from django.utils import timezone
        try:
            StorageManager.delete_from_supabase_storage(resource.firebase_file_path)
            if resource.thumbnail_public_id:
                from accounts.utils.cloudinary_helpers import delete_temp_image
                delete_temp_image(resource.thumbnail_public_id)
        except Exception:
            pass
        resource.is_deleted = True
        resource.deleted_at = timezone.now()
        resource.save()
        messages.success(request, "Resource deleted successfully.")
        return redirect('course_lessons', course_uid=resource.course.uid)

    # For APPROVED resources — create a deletion request and wait for admin approval
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

    notify_admins(f"🗑️ DELETION REQUEST: Teacher {request.user.username} requested deletion of resource '{resource.title}' in course '{resource.course.title}'.")
    messages.success(request, f"Deletion request for '{resource.title}' submitted. Awaiting admin approval.")
    return redirect('course_lessons', course_uid=resource.course.uid)

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_deletion_requests(request):
    from .models import DeletionRequest
    deletion_requests = DeletionRequest.objects.filter(teacher=request.user).order_by('-created_at')
    return render(request, 'teacher_portal/deletion_requests.html', {
        'deletion_requests': deletion_requests,
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def submit_course_approval(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
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
            notify_admins(f"🔁 COURSE RESUBMISSION: Teacher {request.user.username} fixed and re-submitted the entire course '{course.title}'.")
        elif rejected_lessons.exists():
            messages.success(request, "Rejected lessons have been resubmitted for approval.")
            notify_admins(f"🔁 LESSON RESUBMISSION: Teacher {request.user.username} resubmitted rejected lessons in course '{course.title}'.")
        elif pending_lessons.exists():
            messages.success(request, "New content submitted for review.")
            notify_admins(f"🆕 NEW CONTENT: Teacher {request.user.username} submitted new content for course '{course.title}'.")
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
def enroll_course(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, status='PUBLISHED', is_approved=True)
    
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
            messages.info(request, "👋 Welcome! Please select an avatar to complete your account setup.")

    if request.method == 'POST':
        from django.contrib.auth import update_session_auth_hash
        import re

        # Handle Skip — set default avatar and mark photo cache so middleware stops redirecting
        if request.POST.get('skip'):
            from django.core.cache import cache
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

            # Clear middleware photo cache so user isn't redirected back to edit_profile
            from django.core.cache import cache
            cache.delete(f"user_has_photo_{request.user.id}")

            if avatar_changed and not new_username and not new_password:
                return JsonResponse({'status': 'success', 'message': '✅ Avatar updated successfully!'})
            
            return JsonResponse({'status': 'success', 'message': '✅ Profile updated successfully!'})
        else:
            return JsonResponse({'status': 'error', 'message': 'No changes detected.'}, status=400)
    
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

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def teacher_edit_profile(request):
    if request.method == 'POST':
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
            from django.core.cache import cache
            cache.delete(f"user_has_photo_{request.user.id}")
            return JsonResponse({'status': 'success', 'message': '✅ Profile updated successfully!'})
        else:
            return JsonResponse({'status': 'error', 'message': 'No changes detected.'}, status=400)

    avatars = [f"/static/avatars/admin_m_{i}.png" for i in range(5)] + \
              [f"/static/avatars/admin_f_{i}.png" for i in range(5)]
    return render(request, 'teacher_portal/edit_profile.html', {'user': request.user, 'avatars': avatars})


@login_required
def course_player(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid)

    is_unlocked = request.session.get('student_view_unlocked')
    is_admin = getattr(request.user, 'is_staff', False)

    # === ACCESS CONTROL ===
    if is_unlocked and (is_admin or request.user.user_type == 'TEACHER'):
        lessons = course.lessons.filter(status='APPROVED').only('id', 'title', 'order', 'video_url', 'video_file', 'chapter').order_by('chapter', 'order')

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
        lessons = course.lessons.filter(status='APPROVED').only('id', 'title', 'order', 'video_url', 'video_file', 'chapter').order_by('chapter', 'order')

    from .models import CourseResource
    approved_resources = CourseResource.objects.filter(
        course=course, status='APPROVED', is_deleted=False
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

    all_chapter_names = sorted(set(list(lesson_by_chapter.keys()) + list(res_by_chapter.keys())), key=lambda x: (x == ''), reverse=True)
    if '' in all_chapter_names and not lesson_by_chapter.get('') and not res_by_chapter.get(''):
        all_chapter_names.remove('')

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
            'name': ch_name if ch_name else 'Uncategorized',
            'is_uncategorized': ch_name == '',
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
def send_chat_message(request):
    if request.method == 'POST':
        sender = request.user
        is_teacher = sender.user_type == 'TEACHER'
        is_admin = sender.is_superuser or sender.is_staff or sender.user_type == 'ADMIN'
        if not (is_teacher or is_admin):
            return JsonResponse({'status': 'error', 'message': 'Access denied'}, status=403)

        receiver_uid = request.POST.get('receiver_uid')
        message_text = request.POST.get('message')

        try:
            receiver = CustomUser.objects.get(uid=receiver_uid)
            receiver_is_valid = (
                (is_teacher and (receiver.is_superuser or receiver.user_type == 'ADMIN' or receiver.is_staff)) or
                (is_admin and receiver.user_type == 'TEACHER')
            )
            if not receiver_is_valid:
                return JsonResponse({'status': 'error', 'message': 'Invalid recipient'}, status=403)
        except CustomUser.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)

        sender_name = 'Support Team' if is_admin else (sender.full_name or sender.username)

        from accounts.utils.firebase_chat import send_message as fb_send
        result = fb_send(sender, receiver_uid, message_text, sender_name)
        if result is None:
            return JsonResponse({'status': 'error', 'message': 'Message delivery failed'}, status=500)

        msg_uid, now_ms = result
        from datetime import datetime
        ts_str = datetime.fromtimestamp(now_ms / 1000).strftime('%I:%M %p')

        return JsonResponse({
            'status': 'success',
            'message_uid': msg_uid,
            'message': message_text,
            'timestamp': ts_str,
            'sender': sender_name
        })
    return JsonResponse({'status': 'error'}, status=400)

@login_required
@never_cache
def get_chat_messages(request, other_user_uid):
    user = request.user
    is_teacher = user.user_type == 'TEACHER'
    is_admin = user.is_superuser or user.is_staff or user.user_type == 'ADMIN'
    if not (is_teacher or is_admin):
        return JsonResponse({'messages': []})

    try:
        other = CustomUser.objects.get(uid=other_user_uid)
    except CustomUser.DoesNotExist:
        return JsonResponse({'messages': []})

    if not ((is_teacher and (other.is_superuser or other.user_type == 'ADMIN' or other.is_staff)) or
            (is_admin and other.user_type == 'TEACHER')):
        return JsonResponse({'messages': []})

    from accounts.utils.firebase_chat import get_messages, mark_read
    fb_msgs = get_messages(str(user.uid), str(other_user_uid))

    mark_read(str(user.uid), str(other_user_uid))

    data = []
    from datetime import datetime as dt_mod
    for m in fb_msgs:
        is_me = str(m['sender_uid']) == str(user.uid)
        raw_ts = m.get('timestamp', 0)
        ts_str = dt_mod.fromtimestamp(raw_ts / 1000).strftime('%I:%M %p') if raw_ts else ''
        data.append({
            'message_uid': m['uid'],
            'sender_uid': m['sender_uid'],
            'sender_name': m.get('sender_name', ''),
            'message': m['message'],
            'timestamp': ts_str,
            'raw_ts': raw_ts,
            'is_me': is_me,
            'is_edited': m.get('is_edited', False),
        })

    return JsonResponse({'messages': data})

@login_required
def get_chat_list(request):
    from django.db.models import Q

    user = request.user
    is_teacher = user.user_type == 'TEACHER'
    is_admin_user = user.is_superuser or user.is_staff or user.user_type == 'ADMIN'

    if not (is_teacher or is_admin_user):
        return JsonResponse({'users': []})

    if is_teacher:
        chat_partner_filter = Q(is_superuser=True) | Q(user_type='ADMIN') | (Q(is_staff=True) & ~Q(user_type='TEACHER') & ~Q(user_type='STUDENT'))
    else:
        chat_partner_filter = Q(user_type='TEACHER')

    all_partners = CustomUser.objects.filter(
        chat_partner_filter, status='ACTIVE'
    ).exclude(uid=user.uid).only('uid', 'full_name', 'username', 'image', 'user_type')

    partner_map = {str(u.uid): u for u in all_partners}

    from accounts.utils.firebase_chat import get_chat_list as fb_get_chat_list, get_unread_count
    fb_rooms = fb_get_chat_list(str(user.uid))
    fb_data = {r['other_uid']: r for r in fb_rooms}
    fb_unread = get_unread_count(str(user.uid))

    result = []
    seen = set()

    for room in fb_rooms:
        other_uid = room['other_uid']
        if other_uid not in partner_map:
            continue
        u = partner_map[other_uid]
        display_name = 'Support Team' if u.user_type == 'ADMIN' else (u.full_name or u.username)
        result.append({
            'uid': other_uid,
            'name': display_name,
            'last_message': room.get('last_message', '') or 'No messages yet',
            'unread_count': room.get('unread_count', 0),
            'profile_photo': u.avatar_url,
        })
        seen.add(other_uid)

    remaining = [u for u in partner_map.values() if str(u.uid) not in seen]
    remaining.sort(key=lambda u: (u.full_name or u.username).lower())
    for u in remaining:
        uid_str = str(u.uid)
        display_name = 'Support Team' if u.user_type == 'ADMIN' else (u.full_name or u.username)
        result.append({
            'uid': uid_str,
            'name': display_name,
            'last_message': 'No messages yet',
            'unread_count': 0,
            'profile_photo': u.avatar_url,
        })

    return JsonResponse({'users': result})

@login_required
def mark_notification_read(request, notif_uid):
    mark_read(str(request.user.uid), notif_uid)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({"status": "read"})
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def delete_notification(request, notif_uid):
    from .utils.notification_helper import delete_notification as db_del
    db_del(str(request.user.uid), notif_uid)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({"status": "deleted"})
    messages.success(request, "Notification deleted.")
    return redirect(request.META.get('HTTP_REFERER', '/'))

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_analytics_view(request):
    from django.db.models import Count
    from datetime import datetime, timedelta
    from django.utils import timezone
    
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
        'notifications': get_notifications(str(request.user.uid))[:10],
        'unread_notifications_count': get_unread_count(str(request.user.uid)),
    }
    return render(request, 'teacher_portal/analytics.html', context)

@login_required
def mark_all_notifications_read(request):
    mark_all_read(str(request.user.uid))
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
    
    # Generate a short-lived signed URL — browser loads PDF directly from Supabase
    if resource.firebase_file_path:
        try:
            from accounts.utils.storage_manager import supabase as res_supabase, _get_resource_bucket
            if res_supabase is None:
                logger.error(f"Resource Supabase client not initialized for {resource_uid}")
                raise ValueError("Storage service not configured")
            bucket = _get_resource_bucket()

            res = res_supabase.storage.from_(bucket).create_signed_url(resource.firebase_file_path, 600)
            signed_url = res.get("signedURL") if isinstance(res, dict) else res
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

    # Use signed URL instead of direct proxy — browser loads PDF from Supabase directly
    signed_url = None
    if resource.firebase_file_path:
        try:
            from accounts.utils.storage_manager import supabase as res_supabase, _get_resource_bucket
            if res_supabase is None:
                logger.error(f"Resource Supabase client not initialized for pdf_viewer {resource_uid}")
                raise ValueError("Storage service not configured")
            bucket = _get_resource_bucket()
            res = res_supabase.storage.from_(bucket).create_signed_url(resource.firebase_file_path, 600)
            signed_url = res.get("signedURL") if isinstance(res, dict) else res
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
    from accounts.utils.storage_manager import supabase as res_supabase, _get_resource_bucket
    if res_supabase and resource.firebase_file_path:
        try:
            bucket = _get_resource_bucket()
            content_type = resource.mime_type or 'application/octet-stream'
            filename = f"{resource.title}.{resource.file_extension or 'pdf'}"

            # Generate signed URL for streaming (10 min expiry)
            signed_result = res_supabase.storage.from_(bucket).create_signed_url(
                resource.firebase_file_path, 600
            )
            signed_url = signed_result if isinstance(signed_result, str) else signed_result.get('signedURL')
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
    
    notifications = get_notifications(str(request.user.uid))
    
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
def get_unread_counts(request):
    from django.http import JsonResponse
    from .utils.notification_helper import cleanup_old_notifications
    from accounts.utils.firebase_chat import cleanup_old_messages, get_unread_count as fb_get_unread_count

    cleanup_old_notifications()
    cleanup_old_messages(7)

    notif_count = get_unread_count(str(request.user.uid))

    chat_count = 0
    can_chat = request.user.user_type == 'TEACHER' or request.user.is_superuser or request.user.is_staff or request.user.user_type == 'ADMIN'
    if can_chat:
        chat_count = fb_get_unread_count(str(request.user.uid))

    return JsonResponse({
        'notifications': notif_count,
        'chat': chat_count
    })

# ====== ENTERPRISE OTP RECOVERY PIPELINE ======
from .utils.otp_engine import OTPEngine
import secrets
from django.contrib.auth.hashers import make_password, check_password


def send_reset_code_email(user, code):
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils import timezone
    subject = 'NeoLearn Password Reset Verification Code'
    context = {
        'user': user,
        'otp': code,
        'expiry': '10',
    }
    html_content = render_to_string('emails/password_reset_code.html', context)
    text_content = f'Hello {user.full_name or user.username},\n\nYour verification code is: {code}\n\nThis code expires in 10 minutes.\n\nIf you did not request a password reset, ignore this email.\n\nNeoLearn Team'
    msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [user.email])
    msg.attach_alternative(html_content, 'text/html')
    try:
        msg.send()
        return True
    except Exception as e:
        logger.error("Failed to send password reset email: %s", str(e))
        return False


@csrf_protect
def forgot_password(request):
    user_type = request.GET.get('type', 'student').upper()
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        user = None
        if username and email:
            user = CustomUser.objects.filter(username=username, email=email).first()
        if not user:
            messages.error(request, "We could not verify your details. Please try again.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
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
        expires_at = timezone.now() + timedelta(minutes=10)
        otp_obj = PasswordResetOTP.objects.create(
            user=user,
            otp_hash=make_password(code),
            expires_at=expires_at,
        )
        email_sent = send_reset_code_email(user, code)
        if not email_sent:
            otp_obj.delete()
            messages.error(request, "Unable to send verification email. Please try again later.")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        PasswordResetOTP.objects.filter(user=user, expires_at__gt=timezone.now()).exclude(id=otp_obj.id).delete()
        request.session['reset_user_uid'] = str(user.uid)
        request.session['reset_otp_id'] = otp_obj.id
        messages.success(request, "A verification code has been sent to your registered email.")
        return redirect('verify_reset_code')
    return render(request, 'accounts/forgot_password.html', {'user_type': user_type})


@csrf_protect
def verify_reset_code(request):
    user_uid = request.session.get('reset_user_uid')
    otp_id = request.session.get('reset_otp_id')
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
        raw_code = request.POST.get('code', '').strip()
        if not raw_code or not raw_code.isdigit() or len(raw_code) != 6:
            otp_obj.attempts += 1
            otp_obj.save()
            remaining = 5 - otp_obj.attempts
            messages.error(request, f"Invalid code. {remaining} attempt(s) remaining.")
            return render(request, 'accounts/verify_reset_code.html')
        if check_password(raw_code, otp_obj.otp_hash):
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
            return render(request, 'accounts/verify_reset_code.html')
    return render(request, 'accounts/verify_reset_code.html')


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


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def init_video_upload(request):
    """
    Phase 1: Create lesson record and get YouTube resumable upload URL.
    Browser uploads MP4 directly to YouTube — no bytes pass through Django.
    Returns {lesson_uid, upload_url} for browser to PUT file to YouTube.
    """
    import json

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        course_uid = data.get('course_uid')
        title = data.get('title', '').strip()
        order = data.get('order', 1)
        chapter = data.get('chapter', '')
        file_size = data.get('file_size')

        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)

        course = get_object_or_404(Course, uid=course_uid, teacher=request.user)

        course_is_published = course.status == 'PUBLISHED' and course.is_approved

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

        lesson.upload_status = 'UPLOADING'
        lesson.youtube_upload_status = 'UPLOADING'
        lesson.save(update_fields=['upload_status', 'youtube_upload_status'])

        return JsonResponse({
            'lesson_uid': str(lesson.uid),
            'upload_url': upload_url,
            'access_token': access_token,
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"init_video_upload error: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)


@csrf_exempt
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def youtube_upload_complete(request):
    """
    Phase 2: Browser has finished uploading MP4 directly to YouTube.
    Receives video_id from browser, saves to lesson.
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
    auto_recover = data.get('auto_recover', False)

    if not lesson_uid_str:
        return JsonResponse({'error': 'lesson_uid required'}, status=400)

    if not video_id:
        if not auto_recover:
            return JsonResponse({'error': 'video_id required'}, status=400)
        from .utils.youtube_uploader import find_latest_youtube_upload
        try:
            lesson_lookup = Lesson.objects.get(uid=lesson_uid_str, course__teacher=request.user)
            lesson_title = lesson_lookup.title
            recovered_id = find_latest_youtube_upload(lesson_title)
            if not recovered_id:
                return JsonResponse({
                    'error': 'upload_succeeded_but_needs_manual_url',
                    'message': 'Video uploaded to YouTube but the video ID could not be captured automatically. Please edit the lesson to add the YouTube URL manually.',
                }, status=200)
            video_id = recovered_id
        except Lesson.DoesNotExist:
            return JsonResponse({'error': 'auto_recover: Lesson not found'}, status=404)

    try:
        lesson = Lesson.objects.get(uid=lesson_uid_str, course__teacher=request.user)
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'Lesson not found. The lesson may have been deleted.'}, status=404)

    if lesson.youtube_video_id == video_id and lesson.upload_status == 'READY':
        return JsonResponse({'success': True, 'status': 'already_complete', 'video_id': video_id})

    course = lesson.course
    course_is_published = course.status == 'PUBLISHED' and course.is_approved

    lesson.youtube_video_id = video_id
    lesson.youtube_upload_status = 'UPLOADED'
    lesson.youtube_uploaded_at = tz.now()
    lesson.video_url = f'https://www.youtube.com/watch?v={video_id}'
    lesson.upload_status = 'READY'

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

    if auto_recover:
        logger.info(f"auto_recover: Saved recovered video_id={video_id} to lesson {lesson_uid_str}")

    return JsonResponse({
        'success': True,
        'message': 'Video uploaded to YouTube successfully!',
        'video_id': video_id,
    })


@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def init_youtube_edit_upload(request):
    """
    Phase 1 of EDIT flow: create YouTube resumable upload session for existing lesson.
    Browser uploads MP4 directly to YouTube — no bytes pass through Django.
    """
    import json

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    lesson_uid_str = data.get('lesson_uid')
    file_size = data.get('file_size')

    if not lesson_uid_str:
        return JsonResponse({'error': 'lesson_uid required'}, status=400)

    try:
        lesson = Lesson.objects.get(uid=lesson_uid_str, course__teacher=request.user)
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'Lesson not found'}, status=404)

    # If lesson is currently approved but course is published, auto-approve the edit
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

    lesson.upload_status = 'UPLOADING'
    lesson.youtube_upload_status = 'UPLOADING'
    lesson.save(update_fields=['upload_status', 'youtube_upload_status'])

    return JsonResponse({
        'lesson_uid': str(lesson.uid),
        'upload_url': upload_url,
        'access_token': access_token,
    })


@csrf_exempt
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def youtube_edit_complete(request):
    """
    Phase 2 of EDIT flow: browser finished uploading replacement MP4 to YouTube.
    Saves video_id. If lesson is approved, stages as pending edit for admin approval.
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
    auto_recover = data.get('auto_recover', False)

    if not lesson_uid_str:
        return JsonResponse({'error': 'lesson_uid required'}, status=400)

    if not video_id:
        if not auto_recover:
            return JsonResponse({'error': 'video_id required'}, status=400)
        from .utils.youtube_uploader import find_latest_youtube_upload
        try:
            lesson_lookup = Lesson.objects.get(uid=lesson_uid_str, course__teacher=request.user)
            recovered_id = find_latest_youtube_upload(lesson_lookup.title)
            if not recovered_id:
                return JsonResponse({
                    'error': 'upload_succeeded_but_needs_manual_url',
                    'message': 'Video uploaded to YouTube but the video ID could not be captured automatically. Please add the YouTube URL manually.',
                }, status=200)
            video_id = recovered_id
        except Lesson.DoesNotExist:
            return JsonResponse({'error': 'auto_recover: Lesson not found'}, status=404)

    try:
        lesson = Lesson.objects.get(uid=lesson_uid_str, course__teacher=request.user)
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'Lesson not found. The lesson may have been deleted.'}, status=404)

    if lesson.youtube_video_id == video_id and lesson.upload_status == 'READY':
        return JsonResponse({'success': True, 'status': 'already_complete', 'video_id': video_id})

    new_youtube_url = f'https://www.youtube.com/watch?v={video_id}'
    course_is_published = lesson.course.status == 'PUBLISHED' and lesson.course.is_approved

    if lesson.is_approved and not course_is_published:
        lesson.pending_video_url = new_youtube_url
        lesson.has_pending_edits = True
        lesson.youtube_video_id = video_id
        lesson.youtube_upload_status = 'UPLOADED'
        lesson.youtube_uploaded_at = tz.now()
        lesson.upload_status = 'READY'
        lesson.save(update_fields=[
            'pending_video_url', 'has_pending_edits', 'youtube_video_id',
            'youtube_upload_status', 'youtube_uploaded_at', 'upload_status',
        ])
        notify_admins(f"LESSON EDITS PENDING: Teacher {request.user.username} edited approved lesson '{lesson.title}'. Changes pending admin approval.")
    elif lesson.is_approved and course_is_published:
        lesson.youtube_video_id = video_id
        lesson.youtube_upload_status = 'UPLOADED'
        lesson.youtube_uploaded_at = tz.now()
        lesson.upload_status = 'READY'
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
        lesson.youtube_uploaded_at = tz.now()
        lesson.upload_status = 'READY'
        lesson.video_url = new_youtube_url
        lesson.save(update_fields=[
            'youtube_video_id', 'youtube_upload_status', 'youtube_uploaded_at',
            'upload_status', 'video_url',
        ])

    if auto_recover:
        logger.info(f"youtube_edit_complete auto_recover: Saved recovered video_id={video_id} to lesson {lesson_uid_str}")

    return JsonResponse({
        'success': True,
        'message': 'Video uploaded to YouTube successfully!',
        'video_id': video_id,
    })


@csrf_exempt
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
        if not expected or token != expected:
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




