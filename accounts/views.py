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

        # 1. All fields entered
        if not all([username, email, fullname, password, confirm_password]):
            messages.error(request, "Please fill in all the required fields.")
            return render(request, 'accounts/signup.html')

        # 2. Email format validation
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            messages.error(request, "The email address you entered is not in a valid format.")
            return render(request, 'accounts/signup.html')

        # 3. Username and Email uniqueness
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken. Please choose another one.")
            return render(request, 'accounts/signup.html')
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "This email is already registered. Please login or use a different email.")
            return render(request, 'accounts/signup.html')

        # 4. Password match
        if password != confirm_password:
            messages.error(request, "The passwords you entered do not match.")
            return render(request, 'accounts/signup.html')

        # 5. Password strength
        if len(password) < 8:
            messages.error(request, "Your password must be at least 8 characters long.")
            return render(request, 'accounts/signup.html')
        
        if not any(char.isupper() for char in password):
            messages.error(request, "Your password must contain at least one uppercase letter (A-Z).")
            return render(request, 'accounts/signup.html')
        
        if not any(char.islower() for char in password):
            messages.error(request, "Your password must contain at least one lowercase letter (a-z).")
            return render(request, 'accounts/signup.html')
        
        special_chars = r'[!@#$%^&*(),.?":{}|<>]'
        if not re.search(special_chars, password):
            messages.error(request, "Your password must contain at least one special character (e.g. @, #, $, %).")
            return render(request, 'accounts/signup.html')

        # Create user
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            full_name=fullname,
            is_active=False,
            status='PENDING'
        )
        messages.success(request, "Registration successful! Your account is pending admin approval. Please wait for verification.")
        return redirect('login')

    return render(request, 'accounts/signup.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, "Please enter your username and password.")
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.status == 'ACTIVE':
                login(request, user)
                messages.success(request, f"Welcome back, {user.full_name}! You have logged in successfully.")
                return redirect('dashboard')
            elif user.status == 'PENDING':
                messages.error(request, "Your account is pending approval. Please wait for acceptance or contact the administrator for verification.")
            elif user.status == 'BLOCKED':
                messages.error(request, "Your account has been blocked by admin verification. Please contact support if you believe this is an error.")
            else:
                messages.error(request, "Account status unknown. Please contact admin.")
        else:
            messages.error(request, "Invalid username or password. Please try again.")
            
    return render(request, 'accounts/login.html')
            
    return render(request, 'accounts/login.html')

def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'accounts/dashboard.html')

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully. Have a great day!")
    return redirect('login')
