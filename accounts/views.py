from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import CustomUser
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
                return redirect('dashboard') # Using same dashboard for now or separate one later
            else:
                messages.error(request, "Your teacher account is pending approval or blocked.")
        else:
            messages.error(request, "Invalid teacher credentials.")
            
    return render(request, 'accounts/teacher_login.html')

def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'accounts/dashboard.html')

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully. Have a great day!")
    return redirect('login')
