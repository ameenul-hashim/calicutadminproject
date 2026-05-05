from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import CustomUser, Course, Lesson, Enrollment, Notification, ChatMessage, PasswordResetOTP
from django.contrib.auth.decorators import user_passes_test, login_required
from django.views.decorators.cache import cache_control
import re
from accounts.utils.supabase_storage import upload_pdf
import random
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q

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

        print("🧾 REQUEST FILES:", request.FILES)
        print("📄 PROOF FILE:", proof_file)

        if not all([username, email, fullname, password, confirm_password, proof_file]):
            messages.error(request, "All fields including verification document (PDF) are required.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if proof_file.size > 200 * 1024:
            messages.error(request, "Verification document file size must be below 200 KB.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Upload verification document
        # Note: We create the user first in memory, or upload first and assign later.
        # Since upload_pdf expects an instance, we will delay upload until user is created,
        # or we rewrite upload_pdf to return url/public_id. 
        # The user's helper expects an instance: upload_pdf(instance, pdf_file)
        # So we will handle this after user creation below.


        # ... (Existing validations)
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            messages.error(request, "The email address you entered is not in a valid format.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken. Please choose another one.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered. Please login or use a different email.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if password != confirm_password:
            messages.error(request, "The passwords you entered do not match.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            messages.error(request, "Your password must be at least 8 characters long and contain uppercase, lowercase, and a special character.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Create student
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            full_name=fullname,
            is_active=False,
            status='PENDING',
            user_type='STUDENT',
        )

        # Upload verification document
        from accounts.utils.supabase_storage import upload_user_proof
        if not upload_user_proof(user, proof_file):
            user.delete() # Rollback user creation
            messages.error(request, "Failed to upload your document. Please check your connection.")
            return render(request, 'accounts/signup.html', {'username': username, 'email': email, 'fullname': fullname})

        messages.success(request, "✅ Registration successful! admin approval needed to login please wait for a while or contact admin for login")
        notify_admins(f"New student registration: {username}. Approval needed.")
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

        if not all([username, email, fullname, password, confirm_password, proof_file]):
            messages.error(request, "All fields including verification document (PDF) are required.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if proof_file.size > 200 * 1024:
            messages.error(request, "Verification document file size must be below 200 KB.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Email format validation
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            messages.error(request, "The email address you entered is not in a valid format.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken. Please choose another one.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered. Please login or use a different email.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            messages.error(request, "Your password must be at least 8 characters long and contain uppercase, lowercase, and a special character.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        # Create teacher (staff but inactive until approved)
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            full_name=fullname,
            is_active=False,
            is_staff=True,
            status='PENDING',
            user_type='TEACHER',
        )

        # Upload verification document
        from accounts.utils.supabase_storage import upload_user_proof
        if not upload_user_proof(user, proof_file):
            user.delete()
            messages.error(request, "Failed to upload your document. Please check your connection.")
            return render(request, 'accounts/teacher_signup.html', {'username': username, 'email': email, 'fullname': fullname})

        messages.success(request, "✅ Registration successful! admin approval needed to login please wait for a while or contact admin for login")
        notify_admins(f"New teacher registration: {username}. Approval needed.")
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
def login_view(request):
    if request.user.is_authenticated:
        if request.user.user_type == 'STUDENT':
            return redirect('dashboard')
        elif request.user.user_type == 'TEACHER':
            return redirect('teacher_login')
        elif request.user.user_type == 'ADMIN':
            return redirect('admin_login')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, "Please enter your username and password.")
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.user_type != 'STUDENT':
                messages.error(request, "This login is for students only. Teachers and Admins please use their respective login pages.")
                return render(request, 'accounts/login.html')

            if user.status == 'ACTIVE':
                # Concurrent login restriction for students
                # Efficiently handle concurrent login restriction
                from django.contrib.sessions.models import Session
                if user.current_session_key:
                    Session.objects.filter(session_key=user.current_session_key).delete()
                
                login(request, user)
                
                # Save the new session key
                if not request.session.session_key:
                    request.session.save()
                user.current_session_key = request.session.session_key
                user.save(update_fields=['current_session_key'])
                
                messages.success(request, f"Welcome back, {user.full_name}! Student dashboard loaded.")
                return redirect('dashboard')
            elif user.status == 'PENDING':
                messages.info(request, "admin approval needed to login please wait for a while or contact admin for login")
            elif user.status == 'BLOCKED':
                messages.error(request, "Your account has been blocked.")
        else:
            messages.error(request, "Invalid username or password.")
            
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
        next_url = request.session.pop('next_student_url', 'dashboard')
        return redirect(next_url)

    if request.session.get('student_view_unlocked'):
        next_url = request.session.get('next_student_url', 'dashboard')
        return redirect(next_url)

    if request.method == 'POST':
        password = request.POST.get('password')
        if request.user.check_password(password):
            request.session['student_view_unlocked'] = True
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
            next_url = request.session.pop('next_teacher_url', 'teacher_dashboard')
            messages.success(request, "Teacher View access granted.")
            return redirect(next_url)
        else:
            messages.error(request, "Incorrect password. Please try again.")

    return render(request, 'accounts/teacher_view_auth.html')


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def teacher_login_view(request):
    if request.user.is_authenticated:
        if request.user.user_type == 'TEACHER':
            return redirect('teacher_dashboard')
        elif request.user.user_type == 'STUDENT':
            return redirect('login')
        elif request.user.user_type == 'ADMIN':
            return redirect('admin_login')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.user_type != 'TEACHER':
                messages.error(request, "This login is for teachers only.")
            elif user.status == 'ACTIVE':
                login(request, user)
                messages.success(request, "Teacher dashboard logged in successfully!")
                return redirect('teacher_dashboard')
            elif user.status == 'PENDING':
                messages.info(request, "admin approval needed to login please wait for a while or contact admin for login")
            elif user.status == 'BLOCKED':
                messages.error(request, "Your account has been blocked.")
        else:
            messages.error(request, "Invalid teacher credentials.")
            
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

    if request.user.user_type == 'TEACHER' and not is_admin:
        # Teacher viewing their own courses in student layout
        courses = Course.objects.filter(teacher=request.user).exclude(status='REJECTED').annotate(lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))).only('id', 'title', 'thumbnail', 'status', 'category', 'teacher').select_related('teacher')
    elif is_admin and is_unlocked:
        # Admin in Student View - show all approved courses as if enrolled for testing
        courses = Course.objects.filter(is_approved=True, status='PUBLISHED').annotate(lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))).only('id', 'title', 'thumbnail', 'category', 'teacher').select_related('teacher')
    else:
        # Real Student - show only their enrolled courses
        courses = Course.objects.filter(enrollments__user=request.user, is_approved=True, status='PUBLISHED').annotate(lesson_count=Count('lessons', filter=Q(lessons__status='APPROVED'))).only('id', 'title', 'thumbnail', 'category', 'teacher').select_related('teacher')
    
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

    # Add platform updates to Django messages so they appear in the dashboard message card
    for update in platform_updates:
        messages.info(request, update)

    # Build initial context
    context = {
        'courses': courses,
        'search_query': search_query,
        'total_lessons': sum(c.lesson_count for c in courses),
        'is_admin_preview': is_unlocked,
    }
    return render(request, 'accounts/dashboard.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_dashboard(request):
    courses = Course.objects.filter(teacher=request.user).annotate(lesson_count=Count('lessons')).only('id', 'title', 'status', 'created_at', 'thumbnail')
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
        'pending_courses': courses.filter(status='PENDING').count(),
        'total_students': total_students,
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
        .only('id', 'title', 'thumbnail', 'category', 'teacher__username', 'teacher__full_name')\
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
        .only('id', 'title', 'status', 'created_at', 'thumbnail', 'teacher__username', 'teacher__full_name')\
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
        rejected_lessons_count=Count('lessons', filter=Q(lessons__status='REJECTED'))
    ).only('id', 'title', 'status', 'created_at', 'thumbnail').order_by('-created_at')
    
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

@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='admin_login')
def admin_student_logout(request):
    if 'student_view_unlocked' in request.session:
        del request.session['student_view_unlocked']
    messages.success(request, "Exited student view. Returned to admin dashboard.")
    return redirect('admin_dashboard')

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def create_course(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        level = request.POST.get('level')
        thumbnail = request.FILES.get('thumbnail')
        
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
            update_image(course, thumbnail, folder="edustream/courses")
        
        messages.success(request, f"Course '{title}' created as draft. You can now add lessons.")
        return redirect('course_lessons', course_uid=course.uid)
    
    return render(request, 'teacher_portal/create_course.html')

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_course(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    if request.method == 'POST':
        course.title = request.POST.get('title')
        course.description = request.POST.get('description')
        course.category = request.POST.get('category')
        course.level = request.POST.get('level')
        if request.FILES.get('thumbnail'):
            from .utils.cloudinary_helpers import update_image
            update_image(course, request.FILES.get('thumbnail'), folder="edustream/courses")
        
        # If it was rejected or published, editing it should ideally keep it in draft/pending review
        # For now, let's clear the rejection reason if they edit it
        if course.status == 'REJECTED':
            course.status = 'DRAFT'
            course.rejection_reason = ""
            
        course.save()
        messages.success(request, f"Course '{course.title}' updated successfully!")
        return redirect('my_courses')
    
    return render(request, 'teacher_portal/edit_course.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def course_lessons(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid, teacher=request.user)
    lessons = course.lessons.all().only('id', 'title', 'order', 'status', 'is_approved').order_by('order')
    has_pending_content = lessons.filter(status='PENDING').exists()
    any_lesson_rejected = lessons.filter(status='REJECTED').exists()
    
    return render(request, 'teacher_portal/course_lessons.html', {
        'course': course, 
        'lessons': lessons,
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
        lesson = Lesson.objects.create(
            course=course,
            title=title,
            video_url=video_url,
            video_file=video_file,
            order=request.POST.get('order', course.lessons.count() + 1)
        )
            
        messages.success(request, "Lesson added successfully!")
        notify_admins(f"🆕 NEW CONTENT: Teacher {request.user.username} added a new lesson '{title}' to course '{course.title}'.")
        return redirect('course_lessons', course_uid=course.uid)
    
    return render(request, 'teacher_portal/add_lesson.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def edit_lesson(request, lesson_uid):
    lesson = get_object_or_404(Lesson, uid=lesson_uid, course__teacher=request.user)
    if request.method == 'POST':
        lesson.title = request.POST.get('title')
        lesson.video_url = request.POST.get('video_url')
        if request.FILES.get('video_file'):
            lesson.video_file = request.FILES.get('video_file')
                
        lesson.order = request.POST.get('order', 1)
        
        # Reset approval status on edit
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
    if not has_photo and request.method == 'GET':
        if request.user.user_type in ['STUDENT', 'TEACHER'] and not request.user.is_superuser:
            messages.info(request, "👋 Welcome! Please upload a profile photo to complete your account setup.")

    if request.method == 'POST':
        profile_photo = request.FILES.get('profile_photo')
        if profile_photo:
            if profile_photo.size > 2 * 1024 * 1024:
                messages.error(request, "Profile photo exceeds 2MB limit.")
            else:
                from .utils.cloudinary_helpers import update_image
                if update_image(request.user, profile_photo, folder="edustream/profiles"):
                    messages.success(request, "✅ Profile photo updated successfully!")
                else:
                    messages.error(request, "Failed to upload photo. Please try again.")
            return redirect('profile')
        else:
            messages.error(request, "Please select a photo to upload.")
    
    return render(request, 'accounts/edit_profile.html', {'user': request.user})

@login_required
def course_player(request, course_uid):
    course = get_object_or_404(Course, uid=course_uid)

    # === ACCESS CONTROL ===
    # Admin (is_staff): Always allowed, sees all non-rejected content
    if getattr(request.user, 'is_staff', False):
        lessons = course.lessons.exclude(status='REJECTED').order_by('order')

    # Teacher: allowed for own course OR any approved course
    elif request.user.user_type == 'TEACHER':
        if course.teacher != request.user and not course.is_approved:
            messages.error(request, "You do not have permission to view this course.")
            return redirect('teacher_dashboard')
        lessons = course.lessons.exclude(status='REJECTED').order_by('order')

    # Student: must be enrolled, sees approved lessons (and pending for testing if requested)
    else:
        if not Enrollment.objects.filter(user=request.user, course=course).exists():
            messages.error(request, "You are not enrolled in this course.")
            return redirect('student_explore')
        # Filter: Students see Approved content only in production, but user wants uploaded content visible
        lessons = course.lessons.exclude(status='REJECTED').only('id', 'title', 'order', 'video_url', 'video_file').order_by('order')

    context = {
        'course': course,
        'lessons': lessons,
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
            'timestamp': msg.timestamp.strftime('%H:%M'),
            'sender': msg.sender.username
        })
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def get_chat_messages(request, other_user_uid):
    other_user = get_object_or_404(CustomUser, uid=other_user_uid)
    from django.db.models import Q
    messages = ChatMessage.objects.filter(
        (Q(sender=request.user) & Q(receiver=other_user)) |
        (Q(sender=other_user) & Q(receiver=request.user))
    ).select_related('sender').only('sender__uid', 'sender__username', 'message', 'timestamp').order_by('timestamp')
    
    # Mark as read
    messages.filter(receiver=request.user, is_read=False).update(is_read=True)
    
    data = []
    for m in messages:
        data.append({
            'sender_uid': m.sender.uid,
            'sender_name': m.sender.username,
            'message': m.message,
            'timestamp': m.timestamp.strftime('%H:%M'),
            'is_me': m.sender == request.user
        })
    
    from django.http import JsonResponse
    return JsonResponse({'messages': data})

@login_required
def get_chat_list(request):
    from django.db.models import Q
    # For Admin: list all teachers with messages
    # For Teacher: list all admins
    if request.user.user_type == 'ADMIN' or request.user.is_superuser:
        users = CustomUser.objects.filter(user_type='TEACHER').only('uid', 'full_name', 'username', 'profile_photo')
    else:
        users = CustomUser.objects.filter(is_superuser=True).only('uid', 'full_name', 'username', 'profile_photo')
        
    data = []
    for u in users:
        last_msg = ChatMessage.objects.filter(
            (Q(sender=request.user) & Q(receiver=u)) |
            (Q(sender=u) & Q(receiver=request.user))
        ).last()
        
        unread_count = ChatMessage.objects.filter(sender=u, receiver=request.user, is_read=False).count()
        
        data.append({
            'uid': u.uid,
            'name': u.full_name or u.username,
            'last_message': last_msg.message if last_msg else "No messages yet",
            'unread_count': unread_count,
            'profile_photo': u.avatar_url
        })
    
    from django.http import JsonResponse
    return JsonResponse({'users': data})

@login_required
def mark_notification_read(request, notif_uid):
    from .models import Notification
    # Objective 4: Mark as Read -> DELETE from DB
    notif = get_object_or_404(Notification, uid=notif_uid, user=request.user)
    notif.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({"status": "deleted"})
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
    # Objective 4: Mass cleanup
    Notification.objects.filter(user=request.user).delete()
    return redirect(request.META.get('HTTP_REFERER', '/'))

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
    
    # Mark all as read when viewing this page
    request.user.notifications.filter(is_read=False).update(is_read=True)
    
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

# ====== FORGOT PASSWORD FLOW ======

def forgot_password(request):
    if request.method == 'POST':
        identifier = request.POST.get('identifier') # Can be username or email
        user = CustomUser.objects.filter(Q(email=identifier) | Q(username=identifier)).first()
        
        if user:
            # Generate 6-digit OTP
            otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            PasswordResetOTP.objects.create(user=user, otp=otp)
            
            # Send Email
            subject = 'Password Reset OTP - EduStream'
            message = f'Your OTP for password reset is: {otp}. It is valid for 10 minutes.'
            email_from = settings.DEFAULT_FROM_EMAIL
            recipient_list = [email]
            
            try:
                send_mail(subject, message, email_from, recipient_list)
                messages.success(request, f"OTP has been sent to your registered email: {user.email}")
                request.session['reset_email'] = user.email
                return redirect('verify_otp')
            except Exception as e:
                messages.error(request, "Error sending email. Please try again later.")
        else:
            messages.error(request, "No user found with this email address.")
            
    return render(request, 'accounts/forgot_password.html')

def verify_otp(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('forgot_password')
        
    if request.method == 'POST':
        otp_entered = request.POST.get('otp')
        # Check latest OTP for this user
        otp_record = PasswordResetOTP.objects.filter(
            user__email=email, 
            otp=otp_entered,
            created_at__gte=timezone.now() - timedelta(minutes=10)
        ).last()
        
        if otp_record:
            otp_record.is_verified = True
            otp_record.save()
            messages.success(request, "OTP verified successfully. You can now reset your password.")
            return redirect('reset_password')
        else:
            messages.error(request, "Invalid or expired OTP.")
            
    return render(request, 'accounts/verify_otp.html', {'email': email})

def reset_password(request):
    email = request.session.get('reset_email')
    if not email:
        return redirect('forgot_password')
        
    # Ensure OTP was verified
    otp_record = PasswordResetOTP.objects.filter(user__email=email, is_verified=True).last()
    if not otp_record:
        messages.error(request, "Please verify your OTP first.")
        return redirect('verify_otp')
        
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
        else:
            # Password Validation
            if len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
            elif not re.search(r'[A-Z]', new_password):
                messages.error(request, "Password must contain at least one uppercase letter.")
            elif not re.search(r'[a-z]', new_password):
                messages.error(request, "Password must contain at least one lowercase letter.")
            elif not re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password):
                messages.error(request, "Password must contain at least one special character.")
            else:
                user = otp_record.user
                user.set_password(new_password)
                user.save()
                
                # Cleanup
                PasswordResetOTP.objects.filter(user=user).delete()
                del request.session['reset_email']
                
                messages.success(request, "Password reset successful! Please login with your new password.")
                if user.user_type == 'TEACHER':
                    return redirect('teacher_login')
                return redirect('login')
                
    return render(request, 'accounts/reset_password.html')
