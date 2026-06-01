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
            'home',
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
            'health_check',
            'status_page',
            'trigger_backup',
            'dismiss_updates',
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
                # 🛡️ HARDENING: Route to correct login page based on requested path
                if path.startswith('/customadmin/') or path.startswith('/admin/'):
                    return redirect(f"{reverse('admin_login')}?next={path}")
                elif path.startswith('/teacher/'):
                    return redirect(f"{reverse('teacher_login')}?next={path}")
                else:
                    return redirect(f"{reverse('login')}?next={path}")
            
            # --- IDLE TIMEOUT ENFORCEMENT (15 MINUTES) ---
            # Defeats Chrome's "Continue where you left off" session resurrection
            if getattr(request.user, 'is_staff', False) or getattr(request.user, 'user_type', '') == 'TEACHER':
                import time
                last_activity = request.session.get('last_activity', 0)
                
                # If idle for more than 15 minutes (900 seconds), force logout
                if last_activity and (time.time() - last_activity > 900):
                    # Capture role before logout wipes the user object
                    is_admin_path = getattr(request.user, 'is_staff', False) or path.startswith('/customadmin/')
                    timeout_user = request.user
                    
                    request.session.flush()
                    logout(request)
                    try:
                        from .utils.firebase_audit import log_security_event
                        log_security_event('SESSION_TIMEOUT', 'Inactivity > 15min', username=timeout_user.username)
                    except Exception:
                        pass
                    messages.error(request, "Your session has expired due to inactivity. Please log in again.")
                    return redirect('admin_login' if is_admin_path else 'teacher_login')
                
                # Update last activity timestamp
                request.session['last_activity'] = time.time()
            
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
                if not has_photo and url_name not in ['edit_profile', 'logout', 'student_view_auth', 'teacher_view_auth']:
                    return redirect('edit_profile')

            # --- Admin Isolation Hardening ---
            # Prevent non-staff users from accessing ANY admin URL paths
            admin_paths = ['/customadmin/', '/admin/']
            if any(path.startswith(admin_path) for admin_path in admin_paths):
                
                # 1. Device-level security: Freeze admin access on non-laptop/desktop devices
                user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
                is_mobile = any(keyword in user_agent for keyword in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'windows phone'])
                if is_mobile:
                    if request.user.is_authenticated:
                        logout(request)
                    messages.error(request, "Admin panel is strictly restricted to desktop/laptop devices for security.")
                    return redirect('login')

                # 2. Role-level security: Prevent students and teachers from accessing admin routes
                if request.user.is_authenticated and not request.user.is_staff:
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
            
            # Apply step-up authentication check for non-student users accessing student areas
            if url_name in student_url_names and (request.user.user_type in ['ADMIN', 'TEACHER'] or request.user.is_superuser):
                # Hardening: Ensure session doesn't expire accidentally for admins in student view
                if request.user.user_type == 'ADMIN' or request.user.is_superuser:
                    request.session.modified = True
                
                if not request.session.get('student_view_unlocked'):
                    if url_name != 'student_view_auth':
                        request.session['next_student_url'] = path
                        return redirect('student_view_auth')
                        
            # --- View Persistence Wiping ---
            # If Admin returns to admin panel, wipe the student view flag so they don't get trapped
            if path.startswith('/customadmin/') and request.session.get('student_view_unlocked'):
                del request.session['student_view_unlocked']
                request.session.modified = True
                    
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

        # --- Firebase Analytics: log authenticated page views ---
        if request.user.is_authenticated and request.method == 'GET' and not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                from .utils.firebase_analytics import log_visit_async
                log_visit_async(request.user)
            except Exception:
                pass

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
        except Exception as e:
            # If an error occurs in the view, let Django's handler catch it
            # instead of risking a secondary middleware loop
            raise e
from .utils.malware_scanner import scanner

class EnterpriseHardeningMiddleware:
    """Enterprise-grade security header injection and threat mitigation."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. PRE-PROCESS: Advanced Malware Scanning
        if request.method == 'POST' and request.FILES:
            for file_key in request.FILES:
                uploaded_file = request.FILES[file_key]
                is_infected, reason = scanner.scan_file(uploaded_file)
                
                if is_infected:
                    from django.http import HttpResponseForbidden
                    try:
                        from accounts.models import AdminActivityLog
                        from accounts.models import CustomUser
                        admin_user = CustomUser.objects.filter(user_type='ADMIN', is_active=True).first()
                        if admin_user:
                            AdminActivityLog.objects.create(
                                admin=admin_user,
                                action="MALWARE_BLOCK",
                                details=f"Infected payload blocked: {uploaded_file.name} | Reason: {reason} | IP: {request.META.get('REMOTE_ADDR')}"
                            )
                    except Exception:
                        pass
                    try:
                        from .utils.firebase_audit import log_security_event
                        log_security_event('MALWARE_BLOCK', f"Blocked: {uploaded_file.name} ({reason})", ip=request.META.get('REMOTE_ADDR'))
                    except Exception:
                        pass
                    return HttpResponseForbidden(f"Security Alert: {reason}. Upload blocked by Enterprise SOC.")

        # 2. PRE-PROCESS: Impossible Travel Detection (Simulated)
        if request.user.is_authenticated:
            self.detect_impossible_travel(request)

        response = self.get_response(request)

        # 3. POST-PROCESS: Security Headers (Existing logic)
        csp_rules = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://kit.fontawesome.com https://cdn.plot.ly https://cdn.plyr.io https://cdn.tailwindcss.com https://www.youtube.com https://s.ytimg.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com https://ka-f.fontawesome.com https://cdn.plyr.io",
            "img-src 'self' data: https: http: *.cloudinary.com *.supabase.co ui-avatars.com",
            "font-src 'self' https://fonts.gstatic.com https://ka-f.fontawesome.com",
            "connect-src 'self' https: http: *.supabase.co *.cloudinary.com https://cdn.plyr.io",
            "frame-src 'self' https://*.youtube.com https://www.youtube.com https://youtube.com https: *.cloudinary.com https://*.supabase.co",
            "media-src * data: blob:",
            "frame-ancestors 'self'",
            "object-src 'none'",
            "base-uri 'self'",
        ]
        response["Content-Security-Policy"] = "; ".join(csp_rules)
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "SAMEORIGIN"
        response["X-XSS-Protection"] = "1; mode=block"
        
        return response

    def detect_impossible_travel(self, request):
        """Detects if a user logs in from two geographically distant IPs too quickly."""
        from accounts.models import LoginHistory
        from django.utils import timezone
        from datetime import timedelta
        
        current_ip = request.META.get('REMOTE_ADDR')
        last_login = LoginHistory.objects.filter(user=request.user, status='SUCCESS').order_by('-timestamp').first()
        
        if last_login and last_login.ip_address != current_ip:
            # If last login was within 1 hour and IP changed significantly (mocked check)
            if timezone.now() - last_login.timestamp < timedelta(hours=1):
                from accounts.models import AdminActivityLog
                AdminActivityLog.objects.create(
                    admin=None,
                    target_user=request.user,
                    action="SUSPICIOUS_TRAVEL",
                    details=f"Login from {current_ip} detected 1h after {last_login.ip_address}."
                )
                try:
                    from .utils.firebase_audit import log_security_event
                    log_security_event('SUSPICIOUS_TRAVEL', f"IP change: {last_login.ip_address} -> {current_ip}", username=request.user.username, ip=current_ip)
                except Exception:
                    pass



