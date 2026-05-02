from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from accounts.models import CustomUser
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q

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
    search_query = request.GET.get('search', '')
    if search_query:
        users = CustomUser.objects.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(full_name__icontains=search_query)
        ).exclude(is_superuser=True)
    else:
        users = CustomUser.objects.all().exclude(is_superuser=True)
    
    return render(request, 'custom_admin/dashboard.html', {'users': users, 'search_query': search_query})

@user_passes_test(is_admin, login_url='admin_login')
def pending_users_view(request):
    pending_users = CustomUser.objects.filter(status='PENDING').exclude(is_superuser=True)
    return render(request, 'custom_admin/pending_users.html', {'users': pending_users})

@user_passes_test(is_admin, login_url='admin_login')
def accept_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    user.status = 'ACTIVE'
    user.is_active = True
    user.save()
    messages.success(request, f"User {user.username} has been approved.")
    return redirect('pending_users')

@user_passes_test(is_admin, login_url='admin_login')
def decline_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    user.status = 'BLOCKED'
    user.is_active = False
    user.save()
    messages.success(request, f"User {user.username} has been declined/blocked.")
    return redirect('pending_users')

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
    return redirect('admin_dashboard')

@user_passes_test(is_admin, login_url='admin_login')
def delete_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    username = user.username
    user.delete()
    messages.success(request, f"User {username} deleted successfully.")
    return redirect('admin_dashboard')

@user_passes_test(is_admin, login_url='admin_login')
def create_user_admin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        password = request.POST.get('password')
        
        if not all([username, email, fullname, password]):
            messages.error(request, "All fields are required.")
        elif CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
        elif CustomUser.objects.filter(email=email).exists():
            messages.error(request, "The email is already exist in the database. The email is already taken, please use another one.")
        else:
            CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=fullname,
                is_active=True,
                status='ACTIVE'
            )
            messages.success(request, "User created successfully!")
            return redirect('admin_dashboard')
            
    return render(request, 'custom_admin/create_user.html')

@user_passes_test(is_admin, login_url='admin_login')
def edit_user_admin(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        fullname = request.POST.get('fullname')
        
        # Check if email/username already taken by ANOTHER user
        if CustomUser.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, "Username already taken.")
        elif CustomUser.objects.filter(email=email).exclude(id=user_id).exists():
            messages.error(request, "The email is already exist in the database. The email is already taken, please use another one.")
        else:
            user.username = username
            user.email = email
            user.full_name = fullname
            user.save()
            messages.success(request, "User updated successfully!")
            return redirect('admin_dashboard')
            
    return render(request, 'custom_admin/edit_user.html', {'edit_user': user})

def admin_logout(request):
    logout(request)
    messages.success(request, "Admin logged out successfully!")
    return redirect('admin_login')
