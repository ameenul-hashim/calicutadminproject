from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from accounts.models import CustomUser
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
import re

def admin_login_view(request):
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
    users = CustomUser.objects.filter(user_type='STUDENT').exclude(is_superuser=True)
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(full_name__icontains=search_query)
        )
    return render(request, 'custom_admin/manage_students.html', {'users': users, 'search_query': search_query})

@user_passes_test(is_admin, login_url='admin_login')
def manage_teachers(request):
    search_query = request.GET.get('search', '')
    users = CustomUser.objects.filter(user_type='TEACHER').exclude(is_superuser=True)
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(full_name__icontains=search_query)
        )
    return render(request, 'custom_admin/manage_teachers.html', {'users': users, 'search_query': search_query})

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
            CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=fullname,
                is_active=True,
                status='ACTIVE',
                user_type='STUDENT',
                proof_file=proof_file
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
            CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=fullname,
                is_active=True,
                is_staff=True,
                status='ACTIVE',
                user_type='TEACHER',
                proof_file=proof_file
            )
            messages.success(request, f"Teacher {username} created successfully!")
            return redirect('manage_teachers')
            
    return render(request, 'custom_admin/create_teacher.html')

from django.db.models.functions import ExtractMonth
from accounts.models import Course, Lesson

@user_passes_test(is_admin, login_url='admin_login')
def analytics_view(request):
    # Stats Cards
    total_students = CustomUser.objects.filter(user_type='STUDENT').count()
    total_teachers = CustomUser.objects.filter(user_type='TEACHER').count()
    total_courses = Course.objects.count()
    total_lessons = Lesson.objects.count()

    # Month-wise Data (Simple aggregation for Chart.js)
    def get_monthly_data(queryset):
        data = [0] * 12
        counts = queryset.annotate(month=ExtractMonth('created_at')).values('month').annotate(count=models.Count('id'))
        for entry in counts:
            if entry['month']:
                data[entry['month']-1] = entry['count']
        return data

    student_data = get_monthly_data(CustomUser.objects.filter(user_type='STUDENT'))
    teacher_data = get_monthly_data(CustomUser.objects.filter(user_type='TEACHER'))
    course_data = get_monthly_data(Course.objects.all())

    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_courses': total_courses,
        'total_lessons': total_lessons,
        'student_data': student_data,
        'teacher_data': teacher_data,
        'course_data': course_data,
        'months': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    }
    return render(request, 'custom_admin/analytics.html', context)

@user_passes_test(is_admin, login_url='admin_login')
def content_management_view(request):
    courses = Course.objects.all().prefetch_related('lessons')
    return render(request, 'custom_admin/content_management.html', {'courses': courses})

@user_passes_test(is_admin, login_url='admin_login')
def pending_courses_view(request):
    courses = Course.objects.filter(status='PENDING')
    return render(request, 'custom_admin/pending_courses.html', {'courses': courses})

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

def admin_logout(request):
    logout(request)
    messages.success(request, "Admin logged out successfully!")
    return redirect('admin_login')
