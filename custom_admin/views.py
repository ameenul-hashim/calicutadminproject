from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from accounts.models import CustomUser
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.cache import cache_control
from django.db.models import Q, Count
import re
from accounts.models import Notification, Enrollment
from accounts.utils.supabase_storage import upload_pdf

def create_notification(user, message):
    Notification.objects.create(user=user, message=message)

@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='admin_login')
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_student_view_auth(request):
    if request.method == 'POST':
        password = request.POST.get('password')
        # Check if password is correct for current admin user
        user = authenticate(username=request.user.username, password=password)
        if user is not None:
            request.session['student_view_unlocked'] = True
            request.session.modified = True
            return redirect('admin_student_view')
        else:
            messages.error(request, "Invalid admin password. Access denied.")
    return render(request, 'custom_admin/admin_student_view_auth.html')

@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='admin_login')
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_student_view(request):
    if not request.session.get('student_view_unlocked'):
        return redirect('admin_student_view_auth')
    
    from accounts.models import Course, Enrollment, Notification
    from django.db.models import Count, Sum
    
    # Adapt dashboard logic for admin preview
    courses = Course.objects.all().annotate(lesson_count=Count('lessons')).only('id', 'title', 'thumbnail', 'category', 'teacher').select_related('teacher')[:12]
    explore_courses = Course.objects.filter(status='PUBLISHED', is_approved=True).only('id', 'title', 'thumbnail', 'category', 'teacher').select_related('teacher')[:10]
    
    notifications = Notification.objects.filter(user=request.user, is_read=False)[:5]
    unread_notifications_count = Notification.objects.filter(user=request.user, is_read=False).count()

    context = {
        'courses': courses,
        'explore_courses': explore_courses,
        'total_lessons': courses.aggregate(total=Sum('lesson_count'))['total'] or 0,
        'notifications': notifications,
        'unread_student_notifs': unread_notifications_count,
        'is_admin_preview': True,
        'user': request.user # Ensure correct user is passed
    }
    return render(request, 'accounts/dashboard.html', context)

@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='admin_login')
def admin_student_logout(request):
    if 'student_view_unlocked' in request.session:
        del request.session['student_view_unlocked']
    return redirect('admin_dashboard')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff:
                login(request, user)
                messages.success(request, "Admin logged in successfully!")
                return redirect('admin_dashboard')
            else:
                messages.error(request, "Access denied. Admin credentials required.")
        else:
            messages.error(request, "Invalid admin credentials.")
            
    return render(request, 'custom_admin/login.html')

def is_admin(user):
    return user.is_authenticated and user.is_staff

@user_passes_test(is_admin, login_url='admin_login')
def admin_dashboard(request):
    # Redirect to students list by default or provide overview
    return redirect('manage_students')

@user_passes_test(is_admin, login_url='admin_login')
def manage_students(request):
    search_query = request.GET.get('search', '')
    users = CustomUser.objects.filter(user_type='STUDENT').exclude(is_superuser=True).only('id', 'username', 'email', 'full_name', 'profile_photo', 'status', 'date_joined')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(full_name__icontains=search_query)
        )
    
    # Fast notification fetch
    notifications = Notification.objects.filter(user=request.user, is_read=False).only('id', 'message', 'created_at')[:10]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'custom_admin/manage_students.html', {
        'users': page_obj, 
        'search_query': search_query,
        'notifications': notifications,
        'unread_notifications_count': unread_count,
        'page_obj': page_obj
    })

@user_passes_test(is_admin, login_url='admin_login')
def admin_student_profile(request, user_id):
    student = get_object_or_404(CustomUser, id=user_id, user_type='STUDENT')
    enrollments = Enrollment.objects.filter(user=student).select_related('course')
    
    # Calculate balance (Total course prices)
    current_balance = sum(e.course.price for e in enrollments)
    
    # Calculate Yesterday Balance (Enrollments from yesterday)
    from django.utils import timezone
    from datetime import timedelta
    yesterday = timezone.now().date() - timedelta(days=1)
    yesterday_enrollments = enrollments.filter(enrolled_at__date=yesterday)
    yesterday_balance = sum(e.course.price for e in yesterday_enrollments)
    
    return render(request, 'custom_admin/student_profile_invoice.html', {
        'student': student,
        'enrollments': enrollments,
        'current_balance': current_balance,
        'yesterday_balance': yesterday_balance,
        'invoice_date': timezone.now().date(),
        'invoice_number': f"INV-STU-{student.id:05d}"
    })

@user_passes_test(is_admin, login_url='admin_login')
def manage_teachers(request):
    search_query = request.GET.get('search', '')
    users = CustomUser.objects.filter(user_type='TEACHER').exclude(is_superuser=True).prefetch_related('courses').only('id', 'username', 'email', 'full_name', 'profile_photo', 'status')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(full_name__icontains=search_query)
        )
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'custom_admin/manage_teachers.html', {
        'users': page_obj, 
        'search_query': search_query,
        'page_obj': page_obj
    })

@user_passes_test(is_admin, login_url='admin_login')
def admin_teacher_profile(request, user_id):
    from accounts.models import Course, Enrollment
    teacher = get_object_or_404(CustomUser, id=user_id, user_type='TEACHER')
    courses = Course.objects.filter(teacher=teacher)
    
    # Calculate Total Revenue (Enrollments for all teacher's courses)
    all_enrollments = Enrollment.objects.filter(course__in=courses)
    current_balance = sum(e.course.price for e in all_enrollments)
    
    # Calculate Yesterday Revenue
    from django.utils import timezone
    from datetime import timedelta
    yesterday = timezone.now().date() - timedelta(days=1)
    yesterday_enrollments = all_enrollments.filter(enrolled_at__date=yesterday)
    yesterday_balance = sum(e.course.price for e in yesterday_enrollments)
    
    return render(request, 'custom_admin/teacher_profile_invoice.html', {
        'teacher': teacher,
        'courses': courses,
        'current_balance': current_balance,
        'yesterday_balance': yesterday_balance,
        'invoice_date': timezone.now().date(),
        'invoice_number': f"INV-TEA-{teacher.id:05d}"
    })

@user_passes_test(is_admin, login_url='admin_login')
def pending_users_view(request):
    pending_students = CustomUser.objects.filter(status='PENDING', user_type='STUDENT').exclude(is_superuser=True)
    return render(request, 'custom_admin/pending_students.html', {'users': pending_students})

@user_passes_test(is_admin, login_url='admin_login')
def pending_teachers_view(request):
    pending_teachers = CustomUser.objects.filter(status='PENDING', user_type='TEACHER').exclude(is_superuser=True)
    return render(request, 'custom_admin/pending_teachers.html', {'users': pending_teachers})

from django.utils import timezone
from accounts.models import ApprovalLog

@user_passes_test(is_admin, login_url='admin_login')
def accept_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    user.status = 'ACTIVE'
    user.is_active = True
    user.approved_by = request.user
    user.approved_at = timezone.now()
    user.rejection_reason = ""
    user.save()
    
    create_notification(user, f"Your account has been approved by admin. You can now login.")
    
    ApprovalLog.objects.create(
        content_type=user.user_type,
        object_id=user.id,
        status='APPROVED',
        reviewed_by=request.user,
        comments="Approved by admin."
    )
    
    messages.success(request, f"{user.user_type.title()} {user.username} has been approved.")
    if user.user_type == 'TEACHER':
        return redirect('pending_teachers')
    return redirect('pending_users')

@user_passes_test(is_admin, login_url='admin_login')
def decline_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        user.status = 'BLOCKED'
        user.is_active = False
        user.rejection_reason = reason
        user.save()
        
        create_notification(user, f"Your account registration was declined. Reason: {reason}")
        
        ApprovalLog.objects.create(
            content_type=user.user_type,
            object_id=user.id,
            status='REJECTED',
            reviewed_by=request.user,
            comments=reason
        )
        
        messages.warning(request, f"{user.user_type.title()} {user.username} has been declined.")
        if user.user_type == 'TEACHER':
            return redirect('pending_teachers')
        return redirect('pending_users')
        
    return render(request, 'custom_admin/decline_reason.html', {'target_user': user})

@user_passes_test(is_admin, login_url='admin_login')
def toggle_user_status(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if user.status == 'ACTIVE':
        user.status = 'BLOCKED'
        user.is_active = False
        msg = "blocked"
    else:
        user.status = 'ACTIVE'
        user.is_active = True
        msg = "activated"
    user.save()
    messages.success(request, f"User {user.username} has been {msg}.")
    if user.user_type == 'TEACHER':
        return redirect('manage_teachers')
    return redirect('manage_students')


@user_passes_test(is_admin, login_url='admin_login')
def create_student_admin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        proof_file = request.FILES.get('proof_file')
        
        if not all([username, email, fullname, password, confirm_password, proof_file]):
            messages.error(request, "All fields including Student Proof (PDF) are required.")
        elif password != confirm_password:
            messages.error(request, "Passwords do not match.")
        elif len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            messages.error(request, "Password length 8 needed and one uppercase lowercase and a special character needed.")
        elif CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
        elif CustomUser.objects.filter(email=email).exists():
            messages.error(request, "The email is already exist in the database.")
        else:
            # Upload PDF to Supabase
            pdf_url = upload_pdf(proof_file)
            if not pdf_url:
                messages.error(request, "Failed to upload student proof to Supabase.")
                return render(request, 'custom_admin/create_student.html')

            CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=fullname,
                is_active=True,
                status='ACTIVE',
                user_type='STUDENT',
                proof_pdf=pdf_url
            )
            messages.success(request, f"Student {username} created successfully!")
            return redirect('manage_students')
            
    return render(request, 'custom_admin/create_student.html')

@user_passes_test(is_admin, login_url='admin_login')
def create_teacher_admin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        proof_file = request.FILES.get('proof_file')
        
        if not all([username, email, fullname, password, confirm_password, proof_file]):
            messages.error(request, "All fields including Teacher Proof (PDF) are required.")
        elif password != confirm_password:
            messages.error(request, "Passwords do not match.")
        elif len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            messages.error(request, "Password length 8 needed and one uppercase lowercase and a special character needed.")
        elif CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
        elif CustomUser.objects.filter(email=email).exists():
            messages.error(request, "The email is already exist in the database.")
        else:
            # Upload PDF to Supabase
            pdf_url = upload_pdf(proof_file)
            if not pdf_url:
                messages.error(request, "Failed to upload teacher proof to Supabase.")
                return render(request, 'custom_admin/create_teacher.html')

            CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=fullname,
                is_active=True,
                is_staff=True,
                status='ACTIVE',
                user_type='TEACHER',
                proof_pdf=pdf_url
            )
            messages.success(request, f"Teacher {username} created successfully!")
            return redirect('manage_teachers')
            
    return render(request, 'custom_admin/create_teacher.html')

from django.db.models.functions import ExtractMonth
from django.db import models
from accounts.models import Course, Lesson

@user_passes_test(is_admin, login_url='admin_login')
def analytics_view(request):
    from django.core.cache import cache
    
    # Try to get cached stats
    cache_key = 'admin_analytics_stats'
    context = cache.get(cache_key)
    
    if not context:
        # Stats Cards
        total_students = CustomUser.objects.filter(user_type='STUDENT').count()
        total_teachers = CustomUser.objects.filter(user_type='TEACHER').count()
        total_courses = Course.objects.count()
        total_lessons = Lesson.objects.count()

        # Month-wise Data
        def get_monthly_data(queryset, date_field='created_at'):
            data = [0] * 12
            counts = queryset.annotate(month=ExtractMonth(date_field)).values('month').annotate(count=models.Count('id'))
            for entry in counts:
                if entry['month']:
                    data[entry['month']-1] = entry['count']
            return data

        student_data = get_monthly_data(CustomUser.objects.filter(user_type='STUDENT'), 'date_joined')
        teacher_data = get_monthly_data(CustomUser.objects.filter(user_type='TEACHER'), 'date_joined')
        course_data = get_monthly_data(Course.objects.all())

        # Approval Stats
        approval_stats = {
            'approved': Course.objects.filter(status='PUBLISHED').count(),
            'rejected': Course.objects.filter(status='REJECTED').count(),
            'pending': Course.objects.filter(status='PENDING').count(),
        }
        
        # Teacher Performance
        top_teachers = CustomUser.objects.filter(user_type='TEACHER').annotate(num_courses=Count('courses')).order_by('-num_courses')[:5]
        teacher_performance_labels = [t.username for t in top_teachers]
        teacher_performance_data = [t.num_courses for t in top_teachers]
        
        # Course Enrollments
        top_courses = Course.objects.annotate(enrollment_count=Count('enrollments')).select_related('teacher').order_by('-enrollment_count')[:5]

        pending_students_count = CustomUser.objects.filter(user_type='STUDENT', status='PENDING').count()
        pending_teachers_count = CustomUser.objects.filter(user_type='TEACHER', status='PENDING').count()

        context = {
            'total_students': total_students,
            'total_teachers': total_teachers,
            'total_courses': total_courses,
            'total_lessons': total_lessons,
            'student_data': student_data,
            'teacher_data': teacher_data,
            'course_data': course_data,
            'approval_stats': approval_stats,
            'teacher_perf_labels': teacher_performance_labels,
            'teacher_perf_data': teacher_performance_data,
            'top_courses': top_courses,
            'months': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            'pending_students_count': pending_students_count,
            'pending_teachers_count': pending_teachers_count,
        }
        # Cache for 5 minutes
        cache.set(cache_key, context, 300)

    # These shouldn't be cached as they are user-specific/time-sensitive
    context['notifications'] = Notification.objects.filter(user=request.user, is_read=False).only('id', 'message', 'created_at')[:10]
    context['unread_notifications_count'] = Notification.objects.filter(user=request.user, is_read=False).count()
    
    return render(request, 'custom_admin/analytics.html', context)

@user_passes_test(is_admin, login_url='admin_login')
def content_management_view(request):
    courses = Course.objects.all().prefetch_related('lessons', 'quizzes', 'assignments').only('id', 'title', 'teacher__username', 'status', 'created_at')
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(courses, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'custom_admin/content_management.html', {
        'courses': page_obj,
        'page_obj': page_obj
    })

@user_passes_test(is_admin, login_url='admin_login')
def pending_courses_view(request):
    # Show courses that are PENDING approval OR courses that are PUBLISHED but have new unapproved content
    courses = Course.objects.filter(
        Q(status='PENDING') | 
        Q(lessons__is_approved=False) |
        Q(quizzes__is_approved=False) |
        Q(assignments__is_approved=False)
    ).prefetch_related('lessons', 'quizzes', 'assignments').distinct().order_by('-created_at')
    notifications = Notification.objects.filter(user=request.user, is_read=False)[:10]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(request, 'custom_admin/pending_courses.html', {
        'courses': courses,
        'notifications': notifications,
        'unread_notifications_count': unread_count,
    })

@user_passes_test(is_admin, login_url='admin_login')
def approve_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    course.status = 'PUBLISHED'
    course.is_approved = True
    course.approved_by = request.user
    course.rejection_reason = ""
    course.save()
    
    # Auto-approve all current lessons in the course
    course.lessons.update(is_approved=True)

    create_notification(course.teacher, f"Your course '{course.title}' has been approved and published!")
    
    # Notify all active students about new course
    students = CustomUser.objects.filter(user_type='STUDENT', status='ACTIVE')
    teacher_name = course.teacher.full_name or course.teacher.username
    for student in students:
        create_notification(student, f"{teacher_name} added course {course.title}")

    
    ApprovalLog.objects.create(
        content_type='COURSE',
        object_id=course.id,
        status='APPROVED',
        reviewed_by=request.user,
        comments="Course published."
    )
    
    messages.success(request, f"Course '{course.title}' has been approved and published!")
    return redirect('pending_courses')

@user_passes_test(is_admin, login_url='admin_login')
def reject_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        course.status = 'REJECTED'
        course.is_approved = False
        course.rejection_reason = reason
        course.save()
        
        create_notification(course.teacher, f"Your course '{course.title}' was rejected. Reason: {reason}")
        
        ApprovalLog.objects.create(
            content_type='COURSE',
            object_id=course.id,
            status='REJECTED',
            reviewed_by=request.user,
            comments=reason
        )
        
        messages.warning(request, f"Course '{course.title}' has been rejected.")
        return redirect('pending_courses')
        
    return render(request, 'custom_admin/decline_reason.html', {'course': course, 'is_course': True})

@user_passes_test(is_admin, login_url='admin_login')
def edit_user_admin(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if not all([username, email, fullname]):
            messages.error(request, "All fields are required for updating.")
        elif password and (password != confirm_password):
            messages.error(request, "Passwords do not match.")
        elif password and (len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password)):
            messages.error(request, "Password length 8 needed and one uppercase lowercase and a special character needed.")
        elif CustomUser.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, "This username is already taken by another user. Please use a unique username.")
        elif CustomUser.objects.filter(email=email).exclude(id=user_id).exists():
            messages.error(request, "The email is already exist in the database. The email is already taken, please use another one.")
        else:
            user.username = username
            user.email = email
            user.full_name = fullname
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, f"User {user.username} data updated successfully!")
            if user.user_type == 'TEACHER':
                return redirect('manage_teachers')
            return redirect('manage_students')
            
    return render(request, 'custom_admin/edit_user.html', {'edit_user': user})

@user_passes_test(is_admin, login_url='admin_login')
def toggle_lesson_approval(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if lesson.is_approved:
        lesson.is_approved = False
        msg = "rejected"
    else:
        lesson.is_approved = True
        msg = "approved"
    lesson.save()
    
    create_notification(lesson.course.teacher, f"Your lesson '{lesson.title}' in course '{lesson.course.title}' has been {msg}.")
    
    if msg == "approved":
        # Notify enrolled students
        enrollments = Enrollment.objects.filter(course=lesson.course)
        teacher_name = lesson.course.teacher.full_name or lesson.course.teacher.username
        for e in enrollments:
            create_notification(e.user, f"{teacher_name} added content {lesson.title}")
    
    from accounts.models import ApprovalLog
    ApprovalLog.objects.create(
        content_type='LESSON',
        object_id=lesson.id,
        status='APPROVED' if lesson.is_approved else 'REJECTED',
        reviewed_by=request.user,
        comments=f"Lesson {msg} by admin."
    )
    
    messages.success(request, f"Lesson '{lesson.title}' content has been {msg}.")
    return redirect('admin_content')

@user_passes_test(is_admin, login_url='admin_login')
def toggle_quiz_approval(request, quiz_id):
    from accounts.models import Quiz
    quiz = get_object_or_404(Quiz, id=quiz_id)
    quiz.is_approved = not quiz.is_approved
    quiz.save()
    msg = "approved" if quiz.is_approved else "rejected"
    messages.success(request, f"Quiz '{quiz.title}' has been {msg}.")
    return redirect('admin_content')

@user_passes_test(is_admin, login_url='admin_login')
def toggle_assignment_approval(request, assignment_id):
    from accounts.models import Assignment
    assignment = get_object_or_404(Assignment, id=assignment_id)
    assignment.is_approved = not assignment.is_approved
    assignment.save()
    msg = "approved" if assignment.is_approved else "rejected"
    messages.success(request, f"Assignment '{assignment.title}' has been {msg}.")
    return redirect('admin_content')

@user_passes_test(is_admin, login_url='admin_login')
def admin_view_submissions(request, assignment_id):
    from accounts.models import Assignment
    assignment = get_object_or_404(Assignment, id=assignment_id)
    submissions_qs = assignment.submissions.all().select_related('student')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(submissions_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'custom_admin/admin_view_submissions.html', {
        'assignment': assignment, 
        'submissions': page_obj,
        'page_obj': page_obj
    })

@user_passes_test(is_admin, login_url='admin_login')
def admin_view_quiz_attempts(request, quiz_id):
    from accounts.models import Quiz
    quiz = get_object_or_404(Quiz, id=quiz_id)
    attempts = quiz.attempts.all().select_related('student')
    return render(request, 'custom_admin/admin_view_quiz_attempts.html', {'quiz': quiz, 'attempts': attempts})

@user_passes_test(is_admin, login_url='admin_login')
def admin_view_course_content(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    lessons = course.lessons.all().order_by('order')
    quizzes = course.quizzes.all()
    assignments = course.assignments.all()
    
    notifications = Notification.objects.filter(user=request.user, is_read=False)[:10]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    
    return render(request, 'custom_admin/course_content_verify.html', {
        'course': course,
        'lessons': lessons,
        'quizzes': quizzes,
        'assignments': assignments,
        'notifications': notifications,
        'unread_notifications_count': unread_count,
    })



@user_passes_test(is_admin, login_url='admin_login')
def admin_delete_course_secure(request, course_id):
    from accounts.models import Course
    if request.method == 'POST':
        username = request.POST.get('admin_username')
        password = request.POST.get('admin_password')
        
        # Verify credentials
        user = authenticate(request, username=username, password=password)
        if user is not None and user == request.user and user.is_staff:
            course = get_object_or_404(Course, id=course_id)
            course_title = course.title
            course.delete()
            messages.success(request, f"Course '{course_title}' has been successfully deleted.")
            return redirect('admin_content')
        else:
            messages.error(request, "Authentication failed. Incorrect username or password, or you don't have permission.")
            
    return redirect(request.META.get('HTTP_REFERER', 'admin_content'))

@user_passes_test(is_admin, login_url='admin_login')
def delete_user_admin(request, user_id):
    target_user = get_object_or_404(CustomUser, id=user_id)
    
    if request.method == 'POST':
        username = request.POST.get('admin_username')
        password = request.POST.get('admin_password')
        
        # Verify admin credentials
        user = authenticate(request, username=username, password=password)
        if user is not None and user == request.user and user.is_staff:
            user_info = f"{target_user.full_name or target_user.username} ({target_user.user_type})"
            target_user.delete()
            messages.success(request, f"User '{user_info}' has been permanently deleted.")
            
            # Redirect back to appropriate list
            if target_user.user_type == 'TEACHER':
                return redirect('manage_teachers')
            return redirect('manage_students')
        else:
            messages.error(request, "Authentication failed. Incorrect admin credentials.")
            
    return render(request, 'custom_admin/delete_user_confirm.html', {
        'target_user': target_user
    })

def admin_logout(request):
    logout(request)
    messages.success(request, "Admin logged out successfully!")
    return redirect('admin_login')


@user_passes_test(is_admin, login_url='admin_login')
def manage_deletion_requests(request):
    from accounts.models import DeletionRequest
    requests = DeletionRequest.objects.filter(status='PENDING')
    notifications = Notification.objects.filter(user=request.user, is_read=False)[:10]
    unread_notifications_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(request, 'custom_admin/manage_deletion_requests.html', {
        'requests': requests,
        'notifications': notifications,
        'unread_notifications_count': unread_notifications_count
    })

@user_passes_test(is_admin, login_url='admin_login')
def verify_deletion_request(request, request_id):
    from accounts.models import DeletionRequest, Lesson, Course
    del_request = get_object_or_404(DeletionRequest, id=request_id)
    if del_request.item_type == 'Lesson':
        lesson = Lesson.objects.filter(id=del_request.item_id).first()
        if lesson:
            messages.info(request, f"Verifying deletion request for Lesson: {lesson.title}.")
            return redirect('admin_view_course_content', course_id=lesson.course.id)
    elif del_request.item_type == 'Course':
        course = Course.objects.filter(id=del_request.item_id).first()
        if course:
            messages.info(request, f"Verifying deletion request for Course: {course.title}.")
            return redirect('admin_view_course_content', course_id=course.id)
            
    messages.error(request, "The item could not be found or verified.")
    return redirect('manage_deletion_requests')

@user_passes_test(is_admin, login_url='admin_login')
def approve_deletion_request(request, request_id):
    from accounts.models import DeletionRequest, Lesson, Course
    del_request = get_object_or_404(DeletionRequest, id=request_id)
    
    if del_request.status != 'PENDING':
        messages.error(request, "This request has already been processed.")
        return redirect('manage_deletion_requests')

    success_msg = f"{del_request.item_type} '{del_request.item_name}' deleted successfully."
    
    if del_request.item_type == 'Lesson':
        lesson = Lesson.objects.filter(id=del_request.item_id).first()
        if lesson:
            lesson.delete()
        else:
            messages.warning(request, "Item already gone.")
    elif del_request.item_type == 'Course':
        course = Course.objects.filter(id=del_request.item_id).first()
        if course:
            course.delete()
        else:
            messages.warning(request, "Item already gone.")
    
    del_request.status = 'APPROVED'
    del_request.save()
    messages.success(request, success_msg)
    create_notification(del_request.teacher, f"Your request to delete {del_request.item_type} '{del_request.item_name}' has been APPROVED.")
    return redirect('manage_deletion_requests')

@user_passes_test(is_admin, login_url='admin_login')
def reject_deletion_request(request, request_id):
    from accounts.models import DeletionRequest
    del_request = get_object_or_404(DeletionRequest, id=request_id)
    
    del_request.status = 'REJECTED'
    del_request.save()
    messages.success(request, f"Deletion request for '{del_request.item_name}' rejected.")
    create_notification(del_request.teacher, f"Your request to delete '{del_request.item_name}' has been REJECTED by admin.")
    
    return redirect('manage_deletion_requests')

def error_404(request, exception):
    return render(request, '404.html', status=404)

def error_500(request):
    return render(request, '500.html', status=500)
