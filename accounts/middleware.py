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
                    logout(request)
                    messages.error(request, status_msg)
                    return redirect('login')

        response = self.get_response(request)
        
        # Add strict cache control headers for ALL responses to prevent back-button data exposure
        # and to ensure status checks are always performed against the server.
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "Sat, 01 Jan 2000 00:00:00 GMT"
        
        return response
