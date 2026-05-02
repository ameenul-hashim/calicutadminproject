from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import CustomUser, Course, Lesson, Enrollment, Quiz, Question, QuizAttempt, Assignment, Submission
from django.contrib.auth.decorators import user_passes_test, login_required
import re

def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        proof_file = request.FILES.get('proof_file')

        if not all([username, email, fullname, password, confirm_password, proof_file]):
            messages.error(request, "All fields including student proof (PDF) are required.")
            return render(request, 'accounts/signup.html')

        if not proof_file.name.endswith('.pdf'):
            messages.error(request, "Only PDF files are accepted for student proof.")
            return render(request, 'accounts/signup.html')

        # ... (Existing validations)
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            messages.error(request, "The email address you entered is not in a valid format.")
            return render(request, 'accounts/signup.html')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken. Please choose another one.")
            return render(request, 'accounts/signup.html')
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered. Please login or use a different email.")
            return render(request, 'accounts/signup.html')

        if password != confirm_password:
            messages.error(request, "The passwords you entered do not match.")
            return render(request, 'accounts/signup.html')

        if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            messages.error(request, "Your password must be at least 8 characters long and contain uppercase, lowercase, and a special character.")
            return render(request, 'accounts/signup.html')

        # Create student
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            full_name=fullname,
            is_active=False,
            status='PENDING',
            user_type='STUDENT',
            proof_file=proof_file
        )
        messages.success(request, "Student registration successful! Your proof is pending admin approval.")
        return redirect('login')

    return render(request, 'accounts/signup.html')

def teacher_signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        proof_file = request.FILES.get('proof_file')

        if not all([username, email, fullname, password, confirm_password, proof_file]):
            messages.error(request, "All fields including teacher proof (PDF) are required.")
            return render(request, 'accounts/teacher_signup.html')

        if not proof_file.name.endswith('.pdf'):
            messages.error(request, "Only PDF files are accepted for teacher proof.")
            return render(request, 'accounts/teacher_signup.html')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken.")
            return render(request, 'accounts/teacher_signup.html')
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return render(request, 'accounts/teacher_signup.html')

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/teacher_signup.html')

        if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            messages.error(request, "Password strength requirements not met.")
            return render(request, 'accounts/teacher_signup.html')

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
            proof_file=proof_file
        )
        messages.success(request, "Teacher registration successful! Please wait for admin approval.")
        return redirect('teacher_login')

    return render(request, 'accounts/teacher_signup.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, "Please enter your username and password.")
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.user_type != 'STUDENT':
                messages.error(request, "This login is for students only. Teachers please use the Teacher Login page.")
            elif user.status == 'ACTIVE':
                login(request, user)
                messages.success(request, f"Welcome back, {user.full_name}! Student dashboard loaded.")
                return redirect('dashboard')
            elif user.status == 'PENDING':
                messages.error(request, "Your student account is pending approval.")
            elif user.status == 'BLOCKED':
                messages.error(request, "Your account has been blocked.")
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'accounts/login.html')

def teacher_login_view(request):
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
            else:
                messages.error(request, "Your teacher account is pending approval or blocked.")
        else:
            messages.error(request, "Invalid teacher credentials.")
            
    return render(request, 'accounts/teacher_login.html')

from accounts.models import Course, Lesson, Enrollment

def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Check for student access
    if request.user.user_type != 'STUDENT':
        messages.error(request, "Please use the appropriate portal.")
        return redirect('admin_dashboard') if request.user.is_superuser else redirect('teacher_login')

    # Get enrolled courses
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
    courses = [e.course for e in enrollments]
    
    # Explore courses (all approved and published)
    explore_courses = Course.objects.filter(status='PUBLISHED', is_approved=True).exclude(id__in=[c.id for c in courses])
    
    search_query = request.GET.get('search', '')
    if search_query:
        explore_courses = explore_courses.filter(title__icontains=search_query)

    context = {
        'courses': courses,
        'explore_courses': explore_courses,
        'search_query': search_query,
        'total_lessons': sum(c.lessons.count() for c in courses),
    }
    return render(request, 'accounts/dashboard.html', context)

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def teacher_dashboard(request):
    courses = Course.objects.filter(teacher=request.user)
    total_students = Enrollment.objects.filter(course__teacher=request.user).count()
    
    context = {
        'total_courses': courses.count(),
        'published_courses': courses.filter(status='PUBLISHED').count(),
        'pending_courses': courses.filter(status='PENDING').count(),
        'total_students': total_students,
        'recent_courses': courses.order_by('-created_at')[:5],
    }
    return render(request, 'teacher_portal/dashboard.html', context)

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def explore_courses(request):
    # Other teachers' courses for viewing
    other_courses = Course.objects.exclude(teacher=request.user).filter(is_approved=True).select_related('teacher').prefetch_related('lessons')
    return render(request, 'teacher_portal/explore_courses.html', {'other_courses': other_courses})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def view_other_course(request, course_id):
    # This is for viewing OTHER teachers' courses
    course = get_object_or_404(Course, id=course_id, is_approved=True)
    lessons = course.lessons.all().order_by('order')
    return render(request, 'teacher_portal/view_other_course.html', {
        'course': course,
        'lessons': lessons
    })

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def my_courses(request):
    courses = Course.objects.filter(teacher=request.user)
    return render(request, 'teacher_portal/my_courses.html', {'courses': courses})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def create_course(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        level = request.POST.get('level')
        thumbnail = request.FILES.get('thumbnail')
        
        course = Course.objects.create(
            teacher=request.user,
            title=title,
            description=description,
            category=category,
            level=level,
            thumbnail=thumbnail,
            status='DRAFT'
        )
        messages.success(request, f"Course '{title}' created as draft. You can now add lessons.")
        return redirect('course_lessons', course_id=course.id)
    
    return render(request, 'teacher_portal/create_course.html')

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def course_lessons(request, course_id):
    course = get_object_or_404(Course, id=course_id, teacher=request.user)
    lessons = course.lessons.all()
    return render(request, 'teacher_portal/course_lessons.html', {'course': course, 'lessons': lessons})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def add_lesson(request, course_id):
    course = get_object_or_404(Course, id=course_id, teacher=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        video_url = request.POST.get('video_url')
        video_file = request.FILES.get('video_file')
        notes = request.FILES.get('notes')
        order = request.POST.get('order', 1)
        
        Lesson.objects.create(
            course=course,
            title=title,
            video_url=video_url,
            video_file=video_file,
            notes=notes,
            order=order
        )
        messages.success(request, "Lesson added successfully!")
        return redirect('course_lessons', course_id=course.id)
    
    return render(request, 'teacher_portal/add_lesson.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def submit_course_approval(request, course_id):
    course = get_object_or_404(Course, id=course_id, teacher=request.user)
    if course.lessons.exists():
        course.status = 'PENDING'
        course.save()
        messages.success(request, "Course submitted for admin approval.")
    else:
        messages.error(request, "Please add at least one lesson before submitting for approval.")
    return redirect('my_courses')

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully. Have a great day!")
    return redirect('login')

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'STUDENT', login_url='login')
def enroll_course(request, course_id):
    course = get_object_or_404(Course, id=course_id, status='PUBLISHED', is_approved=True)
    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.info(request, f"You are already enrolled in {course.title}.")
    else:
        Enrollment.objects.create(user=request.user, course=course)
        messages.success(request, f"Successfully enrolled in {course.title}!")
    return redirect('dashboard')

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def create_quiz(request, course_id):
    course = get_object_or_404(Course, id=course_id, teacher=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        timer_minutes = request.POST.get('timer_minutes', 0)
        quiz = Quiz.objects.create(course=course, title=title, timer_minutes=timer_minutes)
        messages.success(request, "Quiz created successfully! Now add some questions.")
        return redirect('add_questions', quiz_id=quiz.id)
    return render(request, 'teacher_portal/create_quiz.html', {'course': course})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def add_questions(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, course__teacher=request.user)
    if request.method == 'POST':
        text = request.POST.get('text')
        option1 = request.POST.get('option1')
        option2 = request.POST.get('option2')
        option3 = request.POST.get('option3')
        option4 = request.POST.get('option4')
        correct_answer = request.POST.get('correct_answer')
        
        Question.objects.create(
            quiz=quiz, text=text, option1=option1, option2=option2, option3=option3, option4=option4, correct_answer=correct_answer
        )
        messages.success(request, "Question added!")
        return redirect('add_questions', quiz_id=quiz.id)
    return render(request, 'teacher_portal/add_questions.html', {'quiz': quiz})

@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def create_assignment(request, course_id):
    course = get_object_or_404(Course, id=course_id, teacher=request.user)
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        deadline = request.POST.get('deadline')
        file = request.FILES.get('file')
        
        Assignment.objects.create(
            course=course, title=title, description=description, deadline=deadline, file=file
        )
        messages.success(request, "Assignment created successfully!")
        return redirect('course_lessons', course_id=course.id) # Or a dedicated assignments page
    return render(request, 'teacher_portal/create_assignment.html', {'course': course})

# ====== STUDENT: Take Quiz ======
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'STUDENT', login_url='login')
def take_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, is_approved=True)
    # Check if already attempted
    if QuizAttempt.objects.filter(quiz=quiz, student=request.user).exists():
        attempt = QuizAttempt.objects.get(quiz=quiz, student=request.user)
        messages.info(request, f"You have already taken this quiz. Score: {attempt.score}/{attempt.total_questions}")
        return render(request, 'accounts/quiz_result.html', {'attempt': attempt, 'quiz': quiz})
    
    if request.method == 'POST':
        questions = quiz.questions.all()
        score = 0
        total = questions.count()
        for q in questions:
            answer = request.POST.get(f'question_{q.id}')
            if answer and answer.strip() == q.correct_answer.strip():
                score += 1
        QuizAttempt.objects.create(quiz=quiz, student=request.user, score=score, total_questions=total)
        messages.success(request, f"Quiz submitted! You scored {score}/{total}.")
        attempt = QuizAttempt.objects.get(quiz=quiz, student=request.user)
        return render(request, 'accounts/quiz_result.html', {'attempt': attempt, 'quiz': quiz})
    
    return render(request, 'accounts/take_quiz.html', {'quiz': quiz})

# ====== STUDENT: Submit Assignment ======
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'STUDENT', login_url='login')
def submit_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, is_approved=True)
    existing = Submission.objects.filter(assignment=assignment, student=request.user).first()
    
    if request.method == 'POST' and not existing:
        file = request.FILES.get('file')
        if file:
            Submission.objects.create(assignment=assignment, student=request.user, file=file)
            messages.success(request, "Assignment submitted successfully!")
        else:
            messages.error(request, "Please attach a file to submit.")
        return redirect('submit_assignment', assignment_id=assignment.id)
    
    return render(request, 'accounts/submit_assignment.html', {
        'assignment': assignment,
        'existing': existing,
    })

# ====== TEACHER: View Quiz Results ======
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def view_quiz_results(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, course__teacher=request.user)
    attempts = quiz.attempts.all().select_related('student')
    return render(request, 'teacher_portal/quiz_results.html', {'quiz': quiz, 'attempts': attempts})

# ====== TEACHER: View Assignment Submissions ======
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def view_submissions(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, course__teacher=request.user)
    submissions = assignment.submissions.all().select_related('student')
    return render(request, 'teacher_portal/view_submissions.html', {'assignment': assignment, 'submissions': submissions})

# ====== TEACHER: Grade a Submission ======
@user_passes_test(lambda u: u.is_authenticated and u.user_type == 'TEACHER', login_url='teacher_login')
def grade_submission(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, assignment__course__teacher=request.user)
    if request.method == 'POST':
        grade = request.POST.get('grade')
        submission.grade = grade
        submission.save()
        messages.success(request, f"Graded {submission.student.username}'s submission: {grade}")
    return redirect('view_submissions', assignment_id=submission.assignment.id)

@login_required
def course_player(request, course_id):
    # Ensure student is enrolled
    enrollment = get_object_or_404(Enrollment, user=request.user, course_id=course_id)
    course = enrollment.course
    lessons = course.lessons.filter(is_approved=True).order_by('order')
    
    context = {
        'course': course,
        'lessons': lessons,
        'first_lesson': lessons.first() if lessons.exists() else None,
    }
    return render(request, 'accounts/course_player.html', context)


