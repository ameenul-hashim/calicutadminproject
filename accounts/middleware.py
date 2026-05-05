from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.urls import reverse, resolve
from django.utils.cache import add_never_cache_headers

class PortalSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        
        # Public URL names that don't require authentication
        public_url_names = [
            'login',
            'signup',
            'teacher_login',
            'teacher_signup',
            'admin_login',
            'forgot_password',
            'verify_otp',
            'reset_password',
            'logout',
            'admin_logout',
            'student_view_auth',
            'teacher_view_auth',
        ]
        
        # Check if the current URL is in public_url_names
        try:
            url_name = resolve(path).url_name
        except:
            url_name = None

        # Determine if the request is for a public path
        is_public = (
            url_name in public_url_names or 
            path.startswith('/admin/') or 
            path.startswith('/static/') or 
            path.startswith('/media/') or
            path == reverse('home') # home redirects to login anyway
        )
        
        if not is_public:
            if not request.user.is_authenticated:
                # Store the attempted URL to redirect back after login
                return redirect(f"{reverse('login')}?next={path}")
            
            # Check for active status (Admin Approval)
            # Superusers are exempt from this check to prevent lockout
            if not request.user.is_superuser:
                if hasattr(request.user, 'status') and request.user.status != 'ACTIVE':
                    status_msg = "Your account is pending admin approval." if request.user.status == 'PENDING' else "Your account has been blocked."
                    request.session.flush()
                    logout(request)
                    messages.error(request, status_msg)
                    if url_name != 'login':
                        return redirect('login')
            
            # --- Mandatory Profile Photo Constraint ---
            if not request.user.is_superuser and request.user.user_type in ['STUDENT', 'TEACHER']:
                has_photo = bool(request.user.image) or bool(request.user.profile_photo)
                if not has_photo and url_name != 'edit_profile' and url_name != 'logout':
                    return redirect('edit_profile')

            # --- Admin Isolation Hardening ---
            # Prevent non-staff users from accessing ANY admin URL paths
            admin_paths = ['/customadmin/', '/admin/']
            if any(path.startswith(admin_path) for admin_path in admin_paths):
                if not request.user.is_staff:
                    if request.user.user_type == 'TEACHER':
                        return redirect('teacher_dashboard')
                    else:
                        return redirect('dashboard')
                    
            # --- Student View Step-Up Authentication for Admin/Teachers ---
            student_url_names = [
                'dashboard', 'student_explore', 'course_player', 'profile', 
                'edit_profile', 'all_notifications', 'enroll_course', 
                'take_quiz', 'submit_assignment'
            ]
            
            if url_name in student_url_names and (request.user.user_type in ['ADMIN', 'TEACHER'] or request.user.is_superuser):
                if not request.session.get('student_view_unlocked'):
                    if url_name != 'student_view_auth':
                        request.session['next_student_url'] = path
                        return redirect('student_view_auth')
                    
            # --- Teacher View Step-Up Authentication for Admins ---
            teacher_url_names = [
                'teacher_dashboard', 'my_courses', 'create_course', 'edit_course', 'delete_course',
                'course_lessons', 'add_lesson', 'edit_lesson', 'delete_lesson', 'submit_course_approval',
                'create_quiz', 'add_questions', 'create_assignment', 'view_quiz_results', 'view_submissions',
                'grade_submission', 'view_other_course', 'teacher_explore', 'teacher_analytics'
            ]
            
            if url_name in teacher_url_names and (request.user.user_type == 'ADMIN' or request.user.is_superuser):
                if not request.session.get('teacher_view_unlocked'):
                    if url_name != 'teacher_view_auth':
                        request.session['next_teacher_url'] = path
                        return redirect('teacher_view_auth')

        try:
            response = self.get_response(request)
            
            # 🛡️ HARDENING: Remove technical exposure
            response["Server"] = "Webserver"
            response["X-Powered-By"] = "Secure Portal"
            
            # Add strict cache control headers
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "Sat, 01 Jan 2000 00:00:00 GMT"
            
            # Referrer Policy for security
            response["Referrer-Policy"] = "same-origin"
            
            return response
        except Exception:
            return self.get_response(request)
