from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import CustomUser, Course, Lesson, Enrollment, Notification, ChatMessage, EmailOTP, DeletionRequest
from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.cache import cache_control
import re
import logging
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.clickjacking import xframe_options_exempt

logger = logging.getLogger(__name__)
import os
from accounts.utils.supabase_storage import upload_pdf
import random
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

def log_login_attempt(request, user, status='SUCCESS'):
    """Audit helper for enterprise login tracking."""
    try:
        from .models import LoginHistory
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        # Basic device detection
        device = "Desktop"
        if "Mobile" in user_agent: device = "Mobile"
        elif "Tablet" in user_agent: device = "Tablet"
        
        LoginHistory.objects.create(
            user=user,
            ip_address=ip,
            user_agent=user_agent,
            device_type=device,
            status=status
        )

        if status == 'FAILED':
            from .utils.firebase_audit import log_security_event
            log_security_event('FAILED_LOGIN', f'Failed login for {user.username}', username=user.username, ip=ip)
    except Exception:
        pass # Never block login due to logging failure

def limit_notifications(user):
    """Limit notifications: 10 for Teachers, 50 for Admins."""
    from .models import Notification
    limit = 10 if user.user_type == 'TEACHER' else 50
    qs = Notification.objects.filter(user=user).order_by('-created_at')
    if qs.count() > limit:
        ids_to_keep = qs.values_list('id', flat=True)[:limit]
        Notification.objects.filter(user=user).exclude(id__in=ids_to_keep).delete()

def create_notification(user, message):
    from .models import Notification
    # Objective 1: No DB storage for Students
    if user.user_type == 'STUDENT':
        return # Skip DB creation for students
        
    # Objective 3: Keep notifications only for important Admin/Teacher events
    important_keywords = ['approved', 'rejected', 'request', 'resubmit', 'deletion', 'submitted']
    is_important = any(word in message.lower() for word in important_keywords)
    
    if is_important:
        Notification.objects.create(user=user, message=message)
        limit_notifications(user) # Objective 5: Limit DB size

def notify_admins(message):
    from .models import CustomUser
    admins = CustomUser.objects.filter(user_type='ADMIN')
    for admin in admins:
        create_notification(admin, message)

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
        is_mobile = request.POST.get('is_mobile') == 'true'

        # 1. Extensive Debug Logging
        print("\n--- 📝 STUDENT SIGNUP (HYBRID FLOW) ---")
        print(f"👤 User: {username} | Mobile Device: {is_mobile}")
        if proof_file:
            print(f"📄 FILE: {proof_file.name} | SIZE: {proof_file.size} bytes | TYPE: {proof_file.content_type}")
        else:
            print("❌ NO FILE")

        # 1. Validation Logic
        if not all([username, email, fullname, password, confirm_password, phone_number, proof_file]):
            messages.error(request, "All fields are required. Please fill in every field to proceed.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        # Email format check
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            messages.error(request, "Please enter a valid email address.")
            return render(request, 'accounts/signup.html', {'username': username, 'fullname': fullname, 'phone_number': phone_number})

        # Unique checks
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken. Please try another one.")
            return render(request, 'accounts/signup.html', {'email': email, 'fullname': fullname, 'phone_number': phone_number})
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered. If it's yours, try logging in.")
            return render(request, 'accounts/signup.html', {'username': username, 'fullname': fullname, 'phone_number': phone_number})
        
        if CustomUser.objects.filter(phone_number=phone_number).exclude(status='REJECTED').exists():
            messages.error(request, "This phone number is already associated with an account.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Phone digits check
        phone_digits = ''.join(filter(str.isdigit, phone_number))
        if len(phone_digits) != 10:
            messages.error(request, "Contact number must be exactly 10 digits.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Password match & strength
        if password != confirm_password:
            messages.error(request, "Passwords do not match. Please re-enter them correctly.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        is_strong, msg = is_strong_password(password)
        if not is_strong:
            messages.error(request, msg)
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        # File validation
        allowed_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif']
        file_ext = os.path.splitext(proof_file.name.lower())[1]
        if file_ext not in allowed_exts:
            messages.error(request, f"Unsupported file format '{file_ext}'. Please upload a PDF or an Image.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        # 4. Processing File Uploads
        try:
            from accounts.utils.supabase_storage import upload_user_proof
            
            # create User First
            user = CustomUser.objects.create_user(
                username=username, email=email, password=password,
                full_name=fullname, phone_number=phone_number,
                is_active=False, status='PENDING', user_type='STUDENT',
            )

            # OPTIMIZED HYBRID FLOW (Direct Memory Processing):
            from accounts.utils.pdf_helpers import convert_image_to_pdf
            from accounts.utils.supabase_storage import upload_user_proof

            if file_ext == '.pdf':
                if proof_file.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "PDF exceeds 200KB limit. Please optimize before uploading.")
                    return redirect('login')

                print("📄 Uploading PDF directly to Supabase...")
                if not upload_user_proof(user, proof_file):
                    user.delete()
                    raise Exception("Supabase storage failure.")
            else:
                print(f"⚡ Processing image ({file_ext}) directly from memory...")
                # convert_image_to_pdf now processes the file object directly in RAM
                optimized_pdf = convert_image_to_pdf(proof_file)
                
                if not optimized_pdf:
                    user.delete()
                    raise Exception("PDF conversion failed. File may be corrupted.")

                if not upload_user_proof(user, optimized_pdf):
                    user.delete()
                    raise Exception("Supabase upload failed.")
                
                print(f"✅ Fast-track registration complete for {username}")

            messages.success(request, "✅ Registration successful! Admin approval pending.")
            notify_admins(f"New student: {username}.")
            return redirect('login')

        except Exception as e:
            import traceback
            print(f"❌ SIGNUP ERROR: {str(e)}")
            print(traceback.format_exc())
            if 'user' in locals() and user: user.delete()
            messages.error(request, f"Registration failed: {str(e)}")
            return redirect('login')


    return render(request, 'accounts/signup.html')

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
        is_mobile = request.POST.get('is_mobile') == 'true'

        # 1. Extensive Debug Logging
        print("\n--- 📝 TEACHER SIGNUP (HYBRID FLOW) ---")
        print(f"👨‍🏫 Teacher: {username} | Mobile: {is_mobile}")
        if proof_file:
            print(f"📄 FILE: {proof_file.name} | SIZE: {proof_file.size} bytes")
        else:
            print("❌ NO FILE")

        # 1. Validation Logic
        if not all([username, email, fullname, password, confirm_password, phone_number, proof_file]):
            messages.error(request, "All fields are required. Please fill in every field to proceed.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        # Email format check
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            messages.error(request, "Please enter a valid email address.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'fullname': fullname, 'phone_number': phone_number})

        # Unique checks
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken. Please try another one.")
            return render(request, 'accounts/teacher_signup.html', {'email': email, 'fullname': fullname, 'phone_number': phone_number})
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered. If it's yours, try logging in.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'fullname': fullname, 'phone_number': phone_number})
        
        if CustomUser.objects.filter(phone_number=phone_number).exclude(status='REJECTED').exists():
            messages.error(request, "This phone number is already associated with an account.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Phone digits check
        phone_digits = ''.join(filter(str.isdigit, phone_number))
        if len(phone_digits) != 10:
            messages.error(request, "Contact number must be exactly 10 digits.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Password match & strength
        if password != confirm_password:
            messages.error(request, "Passwords do not match. Please re-enter them correctly.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        is_strong, msg = is_strong_password(password)
        if not is_strong:
            messages.error(request, msg)
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        # File validation
        allowed_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif']
        file_ext = os.path.splitext(proof_file.name.lower())[1]
        if file_ext not in allowed_exts:
            messages.error(request, f"Unsupported file format '{file_ext}'. Please upload a PDF or an Image.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname, 'phone_number': phone_number})

        # 4. Processing File Uploads
        try:
            from accounts.utils.supabase_storage import upload_user_proof
            
            # create User First
            user = CustomUser.objects.create_user(
                username=username, email=email, password=password,
                full_name=fullname, phone_number=phone_number,
                is_active=False, is_staff=True, status='PENDING', user_type='TEACHER',
            )

            # OPTIMIZED HYBRID FLOW (Direct Memory Processing):
            from accounts.utils.pdf_helpers import convert_image_to_pdf
            from accounts.utils.supabase_storage import upload_user_proof

            if file_ext == '.pdf':
                if proof_file.size > 200 * 1024:
                    user.delete()
                    messages.error(request, "PDF exceeds 200KB limit. Please optimize before uploading.")
                    return redirect('teacher_login')

                print("📄 Uploading PDF directly to Supabase...")
                if not upload_user_proof(user, proof_file):
                    user.delete()
                    raise Exception("Supabase storage failure.")
            else:
                print(f"⚡ Processing teacher image ({file_ext}) directly from memory...")
                # convert_image_to_pdf now processes the file object directly in RAM
                optimized_pdf = convert_image_to_pdf(proof_file)
                
                if not optimized_pdf:
                    user.delete()
                    raise Exception("PDF conversion failed. File may be corrupted.")

                if not upload_user_proof(user, optimized_pdf):
                    user.delete()
                    raise Exception("Supabase upload failed.")
                
                print(f"✅ Fast-track teacher registration complete for {username}")

            messages.success(request, "✅ Teacher registration successful! Admin review pending.")
            notify_admins(f"New teacher: {username}.")
            return redirect('teacher_login')

        except Exception as e:
            import traceback
            print(f"❌ TEACHER SIGNUP ERROR: {str(e)}")
            print(traceback.format_exc())
            if 'user' in locals() and user: user.delete()
            messages.error(request, f"Registration failed: {str(e)}")
            return redirect('teacher_login')

    return render(request, 'accounts/teacher_signup.html')

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

        # 1. Check if user exists
        user_candidate = CustomUser.objects.filter(username=username).first()
        if not user_candidate:
            messages.error(request, "Account not found. Please check your username or sign up.")
            return render(request, 'accounts/login.html')

        # 2. Check if password is correct
        if not user_candidate.check_password(password):
            log_login_attempt(request, user_candidate, status='FAILED')
            messages.error(request, "Incorrect password. Please try again.")
            return render(request, 'accounts/login.html')

        # 3. User exists and password is correct, check user_type
        if user_candidate.user_type != 'STUDENT':
            messages.error(request, "This login area is strictly for Students. Teachers and Admins must use their respective portals.")
            return render(request, 'accounts/login.html')

        # 4. Check account status
        if user_candidate.status == 'PENDING':
            messages.warning(request, "Your account is currently PENDING approval. Admin approval is required to login. Please wait for a while or contact the administration.")
            return render(request, 'accounts/login.html')
        elif user_candidate.status == 'REJECTED':
            messages.error(request, "Your registration was REJECTED. Please contact admin for details.")
            return render(request, 'accounts/login.html')
        elif user_candidate.status == 'BLOCKED':
            messages.error(request, "Your account has been BLOCKED. Access is restricted.")
            return render(request, 'accounts/login.html')

        # 5. Status is ACTIVE, proceed with authentication
        if user_candidate.status == 'ACTIVE':
            user = authenticate(request, username=username, password=password)
            if user is not None:
                # Concurrent login restriction for students
                from django.contrib.sessions.models import Session
                if user.current_session_key:
                    Session.objects.filter(session_key=user.current_session_key).delete()
                
                login(request, user)
                request.session.set_expiry(0)  # Instantly expire session on browser close
                
                if not request.session.session_key:
                    request.session.save()
                user.current_session_key = request.session.session_key
                user.save(update_fields=['current_session_key'])
                
                messages.success(request, f"Welcome back, {user.full_name}! Student dashboard loaded.")
                return redirect('dashboard')
            else:
                messages.error(request, "Authentication failed. Please check your credentials.")
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

        # Check for inactive/pending users FIRST because authenticate() returns None for them
        user_candidate = CustomUser.objects.filter(username=username).first()
        if user_candidate:
            if user_candidate.status == 'PENDING':
                messages.warning(request, "Your teacher account is PENDING approval. Admin approval is needed to login. Please wait for a while or contact the administration.")
                return render(request, 'accounts/teacher_login.html')
            elif user_candidate.status == 'REJECTED':
                messages.error(request, "Your teacher application was REJECTED. Please contact admin for details.")
                return render(request, 'accounts/teacher_login.html')
            elif user_candidate.status == 'BLOCKED':
                messages.error(request, "Your teacher account has been BLOCKED.")
                return render(request, 'accounts/teacher_login.html')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.user_type != 'TEACHER':
                messages.error(request, "This login area is strictly for Teachers. Students and Admins must use their respective portals.")
                return render(request, 'accounts/teacher_login.html')
                
            if user.status == 'ACTIVE':
                login(request, user)
                request.session.set_expiry(0)  # Instantly expire session on browser close
                messages.success(request, f"Welcome, {user.full_name}! Teacher Dashboard active.")
                return redirect('teacher_dashboard')
        else:
            # Check existence vs wrong password
            if user_candidate:
                log_login_attempt(request, user_candidate, status='FAILED')
                messages.error(request, "Incorrect password. Please try again.")
            else:
                messages.error(request, "Teacher account not found. Please check your username or apply.")
            
    return render(request, 'accounts/teacher_login.html')

from accounts.models import Course, Lesson, Enrollment
from django.db.models import Count, Q, Sum

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='login')
def dashboard_view(request):
    # Check for access
    is_unlocked = request.session.get('student_view_unlocked')
    is_admin = getattr(request.user, 'is_staff', False)
    
    if request.user.user_type not in ['STUDENT', 'TEACHER'] and not is_unlocked:
        messages.error(request, "Please use the appropriate portal.")
        return redirect('login')

    if is_unlocked and (is_admin or request.user.user_type == 'TEACHER'):
        # Admin or Teacher in Student View - strictly mimic student by showing only approved courses
        # This prevents "previewing" unapproved/deleted/draft content in the live student environment
        courses = Course.objects.filter(is_approved=True, status='PUBLISHED').annotate(lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))).only('id', 'uid', 'title', 'image', 'thumbnail', 'category', 'teacher').select_related('teacher')
    elif request.user.user_type == 'TEACHER' and not is_admin:
        # Teacher viewing normally - show their own courses (all statuses)
        courses = Course.objects.filter(teacher=request.user).annotate(
            lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))
        ).only('id', 'uid', 'title', 'image', 'thumbnail', 'status', 'category', 'teacher').select_related('teacher')
    else:
        # Real Student - show only their enrolled courses that are PUBLISHED and APPROVED
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

    # Objective 1: Dynamic Messages instead of DB saving for Students
    platform_updates = []
    yesterday = timezone.now() - timedelta(hours=24)
    
    # 1. New Courses added to Explore
    new_courses = Course.objects.filter(is_approved=True, status='PUBLISHED', created_at__gte=yesterday).only('title')
    for c in new_courses:
        platform_updates.append(f"🚀 New Course Added: '{c.title}' is now available in the Explore area!")

    # 2. New Content in Enrolled Courses
    if request.user.is_authenticated and request.user.user_type == 'STUDENT':
        new_lessons = Lesson.objects.filter(
            course__enrollments__user=request.user,
            status='APPROVED',
            created_at__gte=yesterday
        ).select_related('course').only('title', 'course__title')
        for l in new_lessons:
            platform_updates.append(f"📖 Content Released: New lesson '{l.title}' added to your course '{l.course.title}'.")

    # Build initial context
    context = {
        'courses': courses,
        'search_query': search_query,
        'total_lessons': sum(c.lesson_count for c in courses),
        'is_admin_preview': is_unlocked,
        'platform_updates': platform_updates,
    }
    return render(request, 'accounts/dashboard.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_dashboard(request):
    courses = Course.objects.filter(teacher=request.user).annotate(
        total_lessons=Count('lessons'),
        approved_lessons=Count('lessons', filter=Q(lessons__status='APPROVED')),
        pending_lessons=Count('lessons', filter=Q(lessons__status='PENDING'))
    ).only('id', 'uid', 'title', 'status', 'created_at', 'image', 'thumbnail')
    
    total_students = Enrollment.objects.filter(course__teacher=request.user).count()
    
    # Efficient aggregation
    recent_courses = courses.order_by('-created_at')[:5]
    
    # Pagination for courses
    from django.core.paginator import Paginator
    paginator = Paginator(courses, 20)  # 20 courses per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'total_courses': courses.count(),
        'published_courses': courses.filter(status='PUBLISHED').count(),
        'pending_courses': courses.filter(Q(status='PENDING') | Q(pending_lessons__gt=0)).distinct().count(),
        'total_students': total_students,
        'pending_deletions': DeletionRequest.objects.filter(teacher=request.user, status='PENDING').count(),
        'recent_courses': recent_courses,
        'courses': page_obj,
        'page_obj': page_obj,
        'notifications': Notification.objects.filter(user=request.user).order_by('-created_at')[:10],
        'unread_notifications_count': Notification.objects.filter(user=request.user, is_read=False).count(),
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
            success = update_image(course, thumbnail, folder="Neo Learner/courses")
            if not success:
                print(f"⚠️ Thumbnail upload failed for course '{title}' — course saved without thumbnail.")
        
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
                from .utils.cloudinary_helpers import update_image
                success = update_image(course, thumbnail_file, folder="Neo Learner/courses")
                if not success:
                    print(f"⚠️ Thumbnail update failed for course '{course.title}'")
            
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
    lessons = course.lessons.all().only('id', 'title', 'order', 'status', 'is_approved').order_by('order')
    from .models import CourseResource
    resources = course.resources.filter(is_deleted=False).only('id', 'title', 'category', 'resource_type', 'status', 'is_approved').order_by('-created_at')
    
    has_pending_content = lessons.filter(status='PENDING').exists() or resources.filter(status='PENDING').exists()
    any_lesson_rejected = lessons.filter(status='REJECTED').exists() or resources.filter(status='REJECTED').exists()
    
    return render(request, 'teacher_portal/course_lessons.html', {
        'course': course, 
        'lessons': lessons,
        'resources': resources,
        'has_pending_content': has_pending_content,
        'any_lesson_rejected': any_lesson_rejected,
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def add_lesson(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        video_url = request.POST.get('video_url')
        video_file = request.FILES.get('video_file')

        # === APPROVAL ENFORCEMENT ===
        # Always create lesson as PENDING — never bypass admin review
        lesson = Lesson.objects.create(
            course=course,
            title=title,
            video_url=video_url,
            video_file=video_file,
            order=request.POST.get('order', course.lessons.count() + 1),
            status='PENDING',
            is_approved=False,
        )

        # If course was already PUBLISHED, we keep it PUBLISHED.
        # Only the NEW lesson will be PENDING (set above), making it invisible to students.
        if course.status == 'PUBLISHED' or course.is_approved:
            messages.success(request, f"Lesson '{title}' added! It will be visible to students once approved by admin. The rest of your course remains live.")
            notify_admins(f"🆕 NEW LESSON on PUBLISHED COURSE: Teacher {request.user.username} added lesson '{title}' to already-published course '{course.title}'.")
        else:
            messages.success(request, f"Lesson '{title}' added successfully! Submit for admin approval when ready.")
            notify_admins(f"🆕 NEW CONTENT: Teacher {request.user.username} added lesson '{title}' to course '{course.title}'.")

        return redirect('course_lessons', course_uid=course.uid)
    
    return render(request, 'teacher_portal/add_lesson.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_lesson(request, lesson_uid):
    lesson = get_object_or_404(Lesson, uid=lesson_uid, course__teacher=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        video_url = request.POST.get('video_url')
        video_file = request.FILES.get('video_file')
        order = request.POST.get('order', 1)
        
        if lesson.is_approved:
            # Lesson is already approved, so store edits in pending fields
            lesson.pending_title = title
            lesson.pending_video_url = video_url
            if video_file:
                if lesson.pending_video_file:
                    try:
                        lesson.pending_video_file.delete(save=False)
                    except Exception:
                        pass
                lesson.pending_video_file = video_file
            lesson.pending_order = order
            lesson.has_pending_edits = True
            lesson.save()
            
            notify_admins(f"🔁 LESSON EDITS PENDING: Teacher {request.user.username} edited approved lesson '{lesson.title}' in course '{lesson.course.title}'. Changes are pending admin approval.")
            messages.success(request, "Lesson edits submitted for approval! Students will continue to view the current version until approved.")
        else:
            # Lesson is not approved yet, overwrite main fields directly
            lesson.title = title
            lesson.video_url = video_url
            if video_file:
                lesson.video_file = video_file
            lesson.order = order
            lesson.is_approved = False
            lesson.status = 'PENDING'
            lesson.save()
            
            messages.success(request, "Lesson updated successfully! It will be visible to students once re-approved by admin.")
            notify_admins(f"🔁 CONTENT UPDATE: Teacher {request.user.username} updated lesson '{lesson.title}' in course '{lesson.course.title}'.")
            
        return redirect('course_lessons', course_uid=lesson.course.uid)
    
    return render(request, 'teacher_portal/edit_lesson.html', {'lesson': lesson, 'course': lesson.course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def delete_lesson(request, lesson_uid):
    lesson = get_object_or_404(Lesson, uid=lesson_uid, course__teacher=request.user)
    course_uid = lesson.course.uid
    
    from .models import DeletionRequest
    existing_request = DeletionRequest.objects.filter(
        teacher=request.user, item_type='Lesson', item_id=lesson.id, status='PENDING'
    ).first()
    
    if existing_request:
        messages.info(request, "A deletion request for this lesson is already pending admin approval.")
    else:
        DeletionRequest.objects.create(
            teacher=request.user,
            item_type='Lesson',
            item_id=lesson.id,
            item_name=f"{lesson.title} (Course: {lesson.course.title})"
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
        title = request.POST.get('title')
        category = request.POST.get('category')
        resource_type = request.POST.get('resource_type')
        upload_file = request.FILES.get('upload_file')

        if not upload_file:
            messages.error(request, "File upload missing.")
            return redirect('course_lessons', course_uid=course.uid)

        # Pre-read size gate: 50MB raw upload limit to prevent DoS
        MAX_UPLOAD_BYTES = 50 * 1024 * 1024
        if upload_file.size > MAX_UPLOAD_BYTES:
            messages.error(request, "File too large. Maximum upload size is 50MB.")
            return redirect('course_lessons', course_uid=course.uid)
            
        try:
            mime_type, ext = validate_file(upload_file, upload_file.name, resource_type)
            file_bytes = upload_file.read()
            original_size = len(file_bytes)
            
            compressed_bytes = file_bytes
            thumbnail_bytes = None
            if resource_type == 'PDF':
                compressed_bytes, thumbnail_bytes = process_pdf(file_bytes)
            
            compressed_size = len(compressed_bytes)
            
            import uuid
            # Ensure safe alphanumeric strings, replacing spaces with underscores
            safe_course = re.sub(r'[^a-zA-Z0-9]', '_', course.title).strip('_')
            safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title).strip('_')
            # Collapse multiple underscores
            safe_course = re.sub(r'_+', '_', safe_course)
            safe_title = re.sub(r'_+', '_', safe_title)
            
            dest_path = f"resources/{safe_course}/{safe_title}_v{uuid.uuid4().hex[:6]}.{ext}"
            fb_path = StorageManager.upload_to_supabase_storage(compressed_bytes, dest_path, mime_type)
            
            thumb_path = None
            thumb_public_id = None
            if thumbnail_bytes:
                from accounts.utils.cloudinary_helpers import upload_image_only
                t_url, t_pid = upload_image_only(thumbnail_bytes, folder="Neo Learner/course_thumbnails")
                if t_url and t_pid:
                    thumb_path = t_url
                    thumb_public_id = t_pid
            
            CourseResource.objects.create(
                course=course,
                title=title,
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
                status='PENDING',
                is_approved=False
            )
            messages.success(request, f"Resource '{title}' uploaded and pending approval.")
            notify_admins(f"🆕 NEW RESOURCE: Teacher {request.user.username} uploaded a {resource_type} for course '{course.title}'.")
        except Exception as e:
            messages.error(request, f"Upload failed: {str(e)}")
            
        return redirect('course_lessons', course_uid=course.uid)
        
    return render(request, 'teacher_portal/add_resource.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_resource(request, resource_uid):
    from .utils.pdf_processor import validate_file, process_pdf
    from .utils.storage_manager import StorageManager
    from .models import CourseResource

    resource = get_object_or_404(CourseResource, uid=resource_uid, course__teacher=request.user)
    course = resource.course

    if request.method == 'POST':
        title = request.POST.get('title')
        category = request.POST.get('category')
        resource_type = request.POST.get('resource_type')
        upload_file = request.FILES.get('upload_file')

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
            # Pre-read size gate
            MAX_UPLOAD_BYTES = 50 * 1024 * 1024
            if upload_file.size > MAX_UPLOAD_BYTES:
                messages.error(request, "File too large. Maximum upload size is 50MB.")
                return redirect('edit_resource', resource_uid=resource.uid)
                
            try:
                new_mime, new_ext = validate_file(upload_file, upload_file.name, resource_type)
                file_bytes = upload_file.read()
                new_orig_size = len(file_bytes)
                
                compressed_bytes = file_bytes
                thumbnail_bytes = None
                if resource_type == 'PDF':
                    compressed_bytes, thumbnail_bytes = process_pdf(file_bytes)
                
                new_comp_size = len(compressed_bytes)
                
                import uuid
                safe_course = re.sub(r'[^a-zA-Z0-9]', '_', course.title).strip('_')
                safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title).strip('_')
                safe_course = re.sub(r'_+', '_', safe_course)
                safe_title = re.sub(r'_+', '_', safe_title)
                dest_path = f"resources/{safe_course}/{safe_title}_v{uuid.uuid4().hex[:6]}.{new_ext}"
                new_fb_path = StorageManager.upload_to_supabase_storage(compressed_bytes, dest_path, new_mime)
                
                if thumbnail_bytes:
                    from accounts.utils.cloudinary_helpers import upload_image_only
                    t_url, t_pid = upload_image_only(thumbnail_bytes, folder="Neo Learner/course_thumbnails")
                    if t_url and t_pid:
                        new_thumb_path = t_url
                        new_thumb_pid = t_pid
            except Exception as e:
                messages.error(request, f"File processing failed: {str(e)}")
                return redirect('edit_resource', resource_uid=resource.uid)

        if is_approved:
            # For approved resources, use pending fields
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

        new_username = request.POST.get('new_username')
        if new_username:
            new_username = new_username.strip()
            if CustomUser.objects.filter(username=new_username).exclude(id=request.user.id).exists():
                return JsonResponse({'status': 'error', 'message': 'Username is already taken.'}, status=400)
            request.user.username = new_username

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
            
        if new_username or new_password:
            request.user.save()
            if new_password:
                update_session_auth_hash(request, request.user)
            return JsonResponse({'status': 'success', 'message': '✅ Credentials updated successfully!'})

        avatar_url = request.POST.get('avatar_url')
        if avatar_url:
            request.user.image = avatar_url
            request.user.save(update_fields=['image'])
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
                return JsonResponse({'status': 'success', 'message': '✅ Avatar updated successfully!'})
            
            messages.success(request, '✅ Avatar updated successfully!')
            return redirect('profile')

        profile_photo = request.FILES.get('profile_photo')
        if profile_photo:
            # Objective: Accept any size up to 2GB and process
            MAX_SIZE = 2 * 1024 * 1024 * 1024 # 2GB
            if profile_photo.size > MAX_SIZE:
                return JsonResponse({'status': 'error', 'message': 'File is too large (Maximum 2GB allowed).'}, status=400)
            
            from .utils.cloudinary_helpers import update_image
            if update_image(request.user, profile_photo, folder="Neo Learner/profiles"):
                # Support both AJAX and Standard Form Submission
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('ajax') == 'true':
                    return JsonResponse({'status': 'success', 'message': '✅ Profile photo updated successfully!'})
                
                messages.success(request, '✅ Profile photo updated successfully!')
                return redirect('profile')
            else:
                return JsonResponse({'status': 'error', 'message': 'Failed to upload photo. Please try again.'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': 'Please select an avatar or photo.'}, status=400)
    
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

        changes_made = False

        # --- Username Change ---
        if new_username and new_username != request.user.username:
            if CustomUser.objects.filter(username=new_username).exclude(id=request.user.id).exists():
                messages.error(request, "This username is already taken.")
                return redirect('teacher_edit_profile')
            request.user.username = new_username
            changes_made = True

        # --- Password Change ---
        if new_password:
            if not current_password:
                messages.error(request, "Current password is required to set a new password.")
                return redirect('teacher_edit_profile')
            if not request.user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
                return redirect('teacher_edit_profile')
            if new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
                return redirect('teacher_edit_profile')
            if len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return redirect('teacher_edit_profile')
            if not re.search(r'[A-Z]', new_password):
                messages.error(request, "Password must contain at least one uppercase letter.")
                return redirect('teacher_edit_profile')
            if not re.search(r'[a-z]', new_password):
                messages.error(request, "Password must contain at least one lowercase letter.")
                return redirect('teacher_edit_profile')
            if not re.search(r'[@$!%*?&#]', new_password):
                messages.error(request, "Password must contain at least one special character (@$!%*?&#).")
                return redirect('teacher_edit_profile')
            request.user.set_password(new_password)
            changes_made = True

        if changes_made:
            request.user.save()
            if new_password:
                update_session_auth_hash(request, request.user)
            messages.success(request, "✅ Profile credentials updated successfully! You can now login with your new credentials.")
        else:
            messages.info(request, "No changes were made.")

        return redirect('teacher_edit_profile')

    return render(request, 'teacher_portal/edit_profile.html', {'user': request.user})


@login_required
def course_player(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid)

    is_unlocked = request.session.get('student_view_unlocked')
    is_admin = getattr(request.user, 'is_staff', False)

    # === ACCESS CONTROL ===
    if is_unlocked and (is_admin or request.user.user_type == 'TEACHER'):
        # Admin or Teacher in Student View: Strictly mimic student behavior (APPROVED only)
        lessons = course.lessons.filter(status='APPROVED').only('id', 'title', 'order', 'video_url', 'video_file').order_by('order')

    elif is_admin:
        # Normal Admin: Always allowed, sees all non-rejected content
        lessons = course.lessons.exclude(status='REJECTED').order_by('order')

    # Teacher: allowed for own course OR any approved course
    elif request.user.user_type == 'TEACHER':
        if course.teacher != request.user and not course.is_approved:
            messages.error(request, "You do not have permission to view this course.")
            return redirect('teacher_dashboard')
        lessons = course.lessons.exclude(status='REJECTED').order_by('order')

    # Student: must be enrolled, sees approved lessons
    else:
        if not Enrollment.objects.filter(user=request.user, course=course).exists():
            messages.error(request, "You are not enrolled in this course.")
            return redirect('student_explore')
        # Filter: Students see APPROVED content only
        lessons = course.lessons.filter(status='APPROVED').only('id', 'title', 'order', 'video_url', 'video_file').order_by('order')

    from .models import CourseResource
    approved_resources = CourseResource.objects.filter(
        course=course, status='APPROVED', is_deleted=False
    ).order_by('-created_at')

    context = {
        'course': course,
        'lessons': lessons,
        'approved_resources': approved_resources,
        'first_lesson': lessons.first() if lessons.exists() else None,
        'is_admin': getattr(request.user, 'is_staff', False),
    }
    return render(request, 'accounts/course_player.html', context)

@login_required
def send_chat_message(request):
    if request.method == 'POST':
        receiver_uid = request.POST.get('receiver_uid')
        message_text = request.POST.get('message')
        receiver = get_object_or_404(CustomUser, uid=receiver_uid)
        
        msg = ChatMessage.objects.create(sender=request.user, receiver=receiver, message=message_text)
        
        from django.http import JsonResponse
        return JsonResponse({
            'status': 'success',
            'message': msg.message,
            'timestamp': msg.timestamp.strftime('%I:%M %p'),
            'sender': 'Administrator' if getattr(msg.sender, 'is_staff', False) else msg.sender.username
        })
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def get_chat_messages(request, other_user_uid):
    other_user = get_object_or_404(CustomUser, uid=other_user_uid)
    from django.db.models import Q
    messages = ChatMessage.objects.filter(
        (Q(sender=request.user) & Q(receiver=other_user)) |
        (Q(sender=other_user) & Q(receiver=request.user))
    ).select_related('sender').only('uid', 'sender__uid', 'sender__username', 'message', 'timestamp', 'is_edited', 'is_deleted').order_by('timestamp')
    
    # Mark as read
    messages.filter(receiver=request.user, is_read=False).update(is_read=True)
    
    data = []
    for m in messages:
        if m.is_deleted:
            continue # Skip deleted messages or send a placeholder if desired
        data.append({
            'message_uid': str(m.uid),
            'sender_uid': m.sender.uid,
            'sender_name': 'Administrator' if getattr(m.sender, 'is_staff', False) else m.sender.username,
            'message': m.message,
            'timestamp': m.timestamp.strftime('%I:%M %p'),
            'is_me': m.sender == request.user,
            'is_edited': m.is_edited
        })
    
    from django.http import JsonResponse
    return JsonResponse({'messages': data})

@login_required
def get_chat_list(request):
    from django.db.models import Q
    # For Admin: list all teachers with messages
    # For Teacher: list all admins
    if request.user.is_superuser or (request.user.is_staff and request.user.user_type != 'TEACHER'):
        users = CustomUser.objects.filter(user_type='TEACHER').only('uid', 'full_name', 'username', 'image', 'profile_photo')
    else:
        users = CustomUser.objects.filter(
            Q(is_superuser=True) | 
            (Q(is_staff=True) & ~Q(user_type='TEACHER') & ~Q(user_type='STUDENT'))
        ).distinct().only('uid', 'full_name', 'username', 'image', 'profile_photo')
        
    data = []
    for u in users:
        last_msg = ChatMessage.objects.filter(
            (Q(sender=request.user) & Q(receiver=u)) |
            (Q(sender=u) & Q(receiver=request.user))
        ).last()
        
        unread_count = ChatMessage.objects.filter(sender=u, receiver=request.user, is_read=False).count()
        
        data.append({
            'uid': u.uid,
            'name': 'Administrator' if getattr(u, 'is_staff', False) and u.user_type != 'TEACHER' else (u.full_name or u.username),
            'last_message': last_msg.message if last_msg else "No messages yet",
            'unread_count': unread_count,
            'profile_photo': u.avatar_url
        })
    
    from django.http import JsonResponse
    return JsonResponse({'users': data})

@login_required
def mark_notification_read(request, notif_uid):
    from .models import Notification
    notif = get_object_or_404(Notification, uid=notif_uid, user=request.user)
    notif.is_read = True
    notif.save()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({"status": "read"})
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def delete_notification(request, notif_uid):
    from .models import Notification
    notif = get_object_or_404(Notification, uid=notif_uid, user=request.user)
    if not notif.is_read:
        messages.error(request, "Please mark as read before deleting.")
        return redirect(request.META.get('HTTP_REFERER', '/'))
    notif.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.http import JsonResponse
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
        'notifications': Notification.objects.filter(user=request.user, is_read=False)[:10],
        'unread_notifications_count': Notification.objects.filter(user=request.user, is_read=False).count(),
    }
    return render(request, 'teacher_portal/analytics.html', context)

@login_required
def mark_all_notifications_read(request):
    from django.shortcuts import redirect
    from .models import Notification
    from django.utils import timezone
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect(request.META.get('HTTP_REFERER', '/'))

@xframe_options_exempt
@login_required(login_url='login')
def access_resource(request, resource_uid):
    from accounts.models import CourseResource, Enrollment
    from django.shortcuts import get_object_or_404, redirect
    from django.http import HttpResponseForbidden, Http404, HttpResponse
    
    # We query without status='APPROVED' restriction first, then verify access based on user role
    resource = get_object_or_404(CourseResource, uid=resource_uid, is_deleted=False)
    
    # Verify access
    is_teacher = (request.user.user_type == 'TEACHER' and resource.course.teacher == request.user)
    is_admin = getattr(request.user, 'is_staff', False) or request.user.user_type == 'ADMIN'
    
    if not (is_teacher or is_admin):
        # Strict enforcement for students
        if resource.status != 'APPROVED':
            raise Http404("Resource not found or not approved.")
            
        has_enrollment = Enrollment.objects.filter(user=request.user, course=resource.course).exists()
        if not has_enrollment:
            return HttpResponseForbidden("You are not enrolled in this course.")
            
    # Primary: stream file bytes directly from Supabase (Secure Proxy, No Expiry)
    try:
        from accounts.utils.storage_manager import StorageManager, supabase as res_supabase
        if res_supabase and resource.firebase_file_path:
            parts = resource.firebase_file_path.split('/', 1)
            bucket = parts[0]
            path_in_bucket = parts[1] if len(parts) > 1 else resource.firebase_file_path
            
            file_bytes = res_supabase.storage.from_(bucket).download(path_in_bucket)
            if file_bytes:
                content_type = resource.mime_type or 'application/octet-stream'
                response = HttpResponse(file_bytes, content_type=content_type)
                filename = f"{resource.title}.{resource.file_extension or 'pdf'}"
                # For 'access', we use 'inline'
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response
    except Exception as e:
        logger.error(f"Resource proxy stream failed for {resource_uid}: {e}")
        
    # Fallback to signed URL if proxy fails for some reason (rare)
    url = resource.get_signed_url()
    if url:
        return redirect(url)
    
    # Fallback: stream file bytes directly from Supabase
    try:
        from accounts.utils.storage_manager import StorageManager, supabase as res_supabase
        if res_supabase and resource.firebase_file_path:
            parts = resource.firebase_file_path.split('/', 1)
            bucket = parts[0]
            path_in_bucket = parts[1] if len(parts) > 1 else resource.firebase_file_path
            file_bytes = res_supabase.storage.from_(bucket).download(path_in_bucket)
            if file_bytes:
                content_type = resource.mime_type or 'application/octet-stream'
                response = HttpResponse(file_bytes, content_type=content_type)
                filename = f"{resource.title}.{resource.file_extension or 'pdf'}"
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response
    except Exception as e:
        logger.error(f"Resource fallback stream failed for {resource_uid}: {e}")
        
    return HttpResponseForbidden("Failed to retrieve resource. Please contact administrator.")

@login_required(login_url='login')
def download_resource(request, resource_uid):
    """Downloads a resource file with Content-Disposition: attachment for actual file download."""
    from accounts.models import CourseResource, Enrollment
    from django.shortcuts import get_object_or_404, redirect
    from django.http import HttpResponseForbidden, Http404, HttpResponse
    
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
        
    # Primary: stream file bytes directly as attachment (Secure Proxy, No Expiry)
    try:
        from accounts.utils.storage_manager import StorageManager, supabase as res_supabase
        if res_supabase and resource.firebase_file_path:
            parts = resource.firebase_file_path.split('/', 1)
            bucket = parts[0]
            path_in_bucket = parts[1] if len(parts) > 1 else resource.firebase_file_path
            
            file_bytes = res_supabase.storage.from_(bucket).download(path_in_bucket)
            if file_bytes:
                content_type = resource.mime_type or 'application/octet-stream'
                response = HttpResponse(file_bytes, content_type=content_type)
                filename = f"{resource.title}.{resource.file_extension or 'pdf'}"
                # For 'download', we use 'attachment'
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                response['Content-Length'] = len(file_bytes)
                return response
    except Exception as e:
        logger.error(f"Resource proxy download failed for {resource_uid}: {e}")

    # Fallback to signed URL
    url = resource.get_signed_url()
    if url:
        return redirect(url)
    
    return HttpResponseForbidden("Failed to download resource. Please contact administrator.")

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required
def all_notifications(request):
    from django.shortcuts import render
    from django.db.models import Q
    
    notifications_qs = request.user.notifications.all().order_by('-created_at')
    
    # Filter for Students
    if request.user.user_type == 'STUDENT' and not getattr(request.user, 'is_staff', False):
        notifications_qs = notifications_qs.filter(
            Q(message__icontains="added course") | 
            Q(message__icontains="New content added to your course")
        )
    
    notifications = notifications_qs
    
    # Mark as read = Delete permanently (No DB save needed)
    # Only delete for Admin/Teacher to keep their history clean
    if request.user.user_type in ['ADMIN', 'TEACHER'] or request.user.is_superuser:
        notifications_qs.delete()
    else:
        # Students keep history (is_read only)
        notifications_qs.filter(is_read=False).update(is_read=True)
    
    # Determine base template based on user type
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
    from .models import Notification, ChatMessage
    from django.db.models import Q
    
    notif_qs = Notification.objects.filter(user=request.user, is_read=False)
    
    # Filter for Students
    if request.user.user_type == 'STUDENT' and not getattr(request.user, 'is_staff', False):
        notif_qs = notif_qs.filter(
            Q(message__icontains="added course") | 
            Q(message__icontains="New content added to your course")
        )
        
    notif_count = notif_qs.count()
    chat_count = ChatMessage.objects.filter(receiver=request.user, is_read=False).count()
    
    return JsonResponse({
        'notifications': notif_count,
        'chat': chat_count
    })

# ====== ENTERPRISE OTP RECOVERY PIPELINE ======
from .utils.otp_engine import OTPEngine

def forgot_password(request):
    user_type = request.GET.get('type', 'student').upper()
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        
        # Security: Verify both username and email belong to the same user
        user = None
        if username and email:
            user = CustomUser.objects.filter(username=username, email=email).first()
            if user and user.is_superuser:
                messages.error(request, "This is not changeable credentials")
                return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
        
        # Security: Always show success message to prevent email enumeration
        if user:
            result = OTPEngine.create_otp(user, 'PASSWORD_RESET', request)
            if isinstance(result, tuple) and result[0] is not None:
                raw_otp, otp_obj = result
                # Disable email sending as requested by user and display OTP directly
                messages.success(request, f"✅ Verification successful! Your OTP is: {raw_otp}. (It will disappear in 15 seconds)")
                
                request.session['recovery_otp_uid'] = str(otp_obj.uid)
                request.session['recovery_user_uid'] = str(user.uid)
                return redirect('verify_otp')
            else:
                # Rate limited or system error
                msg = result[1] if isinstance(result, tuple) else "Security system triggered. Please try again later."
                messages.error(request, f"🛡️ {msg}")
                return redirect('login' if user_type == 'STUDENT' else 'teacher_login')
        else:
            messages.error(request, "Username and email not correct please enter correctly")
            return render(request, 'accounts/forgot_password.html', {'user_type': user_type})
            
    return render(request, 'accounts/forgot_password.html', {'user_type': user_type})

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




