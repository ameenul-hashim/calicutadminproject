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
            messages.error(request, "All fields are required.")
            return render(request, 'accounts/signup.html')

        # 2. Email format validation
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            messages.error(request, "Invalid email format.")
            return render(request, 'accounts/signup.html')

        # 3. Username and Email uniqueness
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, 'accounts/signup.html')
        
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return render(request, 'accounts/signup.html')

        # 4. Password match
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/signup.html')

        # 5. Password strength
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, 'accounts/signup.html')
        
        if not any(char.isupper() for char in password):
            messages.error(request, "Password must contain at least one uppercase letter.")
            return render(request, 'accounts/signup.html')
        
        if not any(char.islower() for char in password):
            messages.error(request, "Password must contain at least one lowercase letter.")
            return render(request, 'accounts/signup.html')
        
        special_chars = r'[!@#$%^&*(),.?":{}|<>]'
        if not re.search(special_chars, password):
            messages.error(request, "Password must contain at least one special character.")
            return render(request, 'accounts/signup.html')

        # Create user
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            full_name=fullname,
            is_active=False # Admin approval needed
        )
        messages.success(request, "Account created successfully! Please wait for admin approval.")
        return redirect('login')

    return render(request, 'accounts/signup.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, "Please enter both username and password.")
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, "Your account is pending approval or has been blocked.")
        else:
            messages.error(request, "Invalid username or password.")
            
    return render(request, 'accounts/login.html')

def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'accounts/dashboard.html')

def logout_view(request):
    logout(request)
    return redirect('login')
