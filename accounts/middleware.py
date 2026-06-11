import time as _time
import logging
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.urls import reverse, resolve
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache static CSP header once — no rebuild per request
_CSP_HEADER = None

def _get_csp_header():
    global _CSP_HEADER
    if _CSP_HEADER is None:
        csp_rules = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://kit.fontawesome.com https://cdn.plot.ly https://cdn.plyr.io https://cdn.tailwindcss.com https://www.youtube.com https://s.ytimg.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com https://ka-f.fontawesome.com https://cdn.plyr.io",
            "img-src 'self' data: https: http: *.cloudinary.com *.supabase.co ui-avatars.com",
            "font-src 'self' https://fonts.gstatic.com https://ka-f.fontawesome.com",
            "connect-src 'self' https: http: *.supabase.co *.cloudinary.com https://cdn.plyr.io",
            "frame-src 'self' https://*.youtube.com https://www.youtube.com https://youtube https: *.cloudinary.com https://*.supabase.co",
            "media-src * data: blob:",
            "frame-ancestors 'self'",
            "object-src 'none'",
            "base-uri 'self'",
        ]
        _CSP_HEADER = "; ".join(csp_rules)
    return _CSP_HEADER

# Pre-compute public URL names as a set for O(1) lookup
_PUBLIC_URL_NAMES = frozenset([
    'home', 'login', 'signup', 'teacher_login', 'teacher_signup',
    'admin_login', 'forgot_password', 'verify_reset_code', 'set_new_password',
    'verify_otp', 'reset_password', 'logout', 'admin_logout',
    'student_view_auth', 'teacher_view_auth', 'health_check', 'firebase_health_check', 'status_page',
    'trigger_backup', 'dismiss_updates',
])

# Pre-compute student/teacher URL names as sets
_STUDENT_URL_NAMES = frozenset([
    'dashboard', 'student_explore', 'course_player', 'profile',
    'edit_profile', 'all_notifications', 'enroll_course',
    'take_quiz', 'submit_assignment',
])

_TEACHER_URL_NAMES = frozenset([
    'teacher_dashboard', 'my_courses', 'create_course', 'edit_course', 'delete_course',
    'course_lessons', 'add_lesson', 'edit_lesson', 'delete_lesson', 'submit_course_approval',
    'create_quiz', 'add_questions', 'create_assignment', 'view_quiz_results', 'view_submissions',
    'grade_submission', 'view_other_course', 'teacher_explore', 'teacher_analytics',
])


class PortalSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Cache URL resolution per path — avoid resolve() on repeated requests
        _url_cache_key = f"un:{path}"
        url_name = cache.get(_url_cache_key)
        if url_name is None:
            try:
                url_name = resolve(path).url_name
            except Exception:
                url_name = None
            cache.set(_url_cache_key, url_name, 600)

        is_public = (
            url_name in _PUBLIC_URL_NAMES
            or path.startswith('/admin/')
            or path.startswith('/static/')
            or path.startswith('/media/')
            or path == '/'  # home path — avoid reverse() on every request
        )

        if not is_public:
            if not request.user.is_authenticated:
                if path.startswith('/customadmin/') or path.startswith('/admin/'):
                    return redirect(f"{reverse('admin_login')}?next={path}")
                elif path.startswith('/teacher/'):
                    return redirect(f"{reverse('teacher_login')}?next={path}")
                else:
                    return redirect(f"{reverse('login')}?next={path}")

            # --- IDLE TIMEOUT (15 min) — stored in SESSION (DB-backed, shared across workers) ---
            if request.user.is_superuser or getattr(request.user, 'user_type', '') in ('ADMIN', 'TEACHER'):
                last_activity = request.session.get('last_activity', 0)

                if last_activity and (_time.time() - last_activity > 900):
                    is_admin_path = (request.user.is_superuser or getattr(request.user, 'user_type', '') == 'ADMIN') or path.startswith('/customadmin/')
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

                # Write activity to SESSION (throttled: every 30s to avoid excessive DB writes)
                now = int(_time.time())
                if now - last_activity > 30:
                    request.session['last_activity'] = now
                    # Log active user to Firebase Analytics for DAU tracking
                    try:
                        from .utils.firebase_analytics import log_active_user_async
                        log_active_user_async(request.user)
                    except Exception:
                        pass

            # --- Cached status check (avoids DB hit per request) ---
            # Staff users (admins) and superusers are exempt from status-based session flushing
            # BLOCKED teachers are allowed through so they can edit and auto-reinstate
            if not request.user.is_superuser and not request.user.is_staff and getattr(request.user, 'user_type', '') != 'ADMIN':
                status_cache_key = f"user_status_{request.user.id}"
                cached_status = cache.get(status_cache_key)
                if cached_status is None:
                    cached_status = request.user.status
                    cache.set(status_cache_key, cached_status, 300)
                if cached_status == 'BLOCKED' and request.user.user_type == 'TEACHER':
                    pass
                elif cached_status != 'ACTIVE':
                    status_msg = "Your account is pending admin approval." if cached_status == 'PENDING' else "Your account has been blocked."
                    request.session.flush()
                    logout(request)
                    messages.error(request, status_msg)
                    if url_name != 'login':
                        return redirect('login')

            # --- Cached profile photo constraint ---
            if not request.user.is_superuser and request.user.user_type in ['STUDENT', 'TEACHER'] and request.user.user_type != 'ADMIN':
                if not request.session.get('avatar_skipped'):
                    photo_cache_key = f"user_has_photo_{request.user.id}"
                    has_photo = cache.get(photo_cache_key)
                    if has_photo is None:
                        has_photo = bool(request.user.image) or bool(request.user.profile_photo)
                        cache.set(photo_cache_key, has_photo, 300)
                    if not has_photo and url_name not in ['edit_profile', 'teacher_edit_profile', 'skip_avatar', 'logout', 'student_view_auth', 'teacher_view_auth']:
                        return redirect('teacher_edit_profile' if request.user.user_type == 'TEACHER' else 'edit_profile')

            # --- Admin Isolation ---
            if path.startswith('/customadmin/') or path.startswith('/admin/'):
                user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
                is_mobile = any(kw in user_agent for kw in ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'windows phone'])
                if is_mobile:
                    if request.user.is_authenticated:
                        logout(request)
                    messages.error(request, "Admin panel is strictly restricted to desktop/laptop devices for security.")
                    return redirect('login')

                if request.user.is_authenticated and not (request.user.is_superuser or request.user.user_type == 'ADMIN' or (request.user.is_staff and request.user.user_type != 'TEACHER')):
                    if request.user.user_type == 'TEACHER':
                        return redirect('teacher_dashboard')
                    else:
                        return redirect('dashboard')

            # --- Student View Step-Up ---
            if url_name in _STUDENT_URL_NAMES and (request.user.user_type in ['ADMIN', 'TEACHER'] or request.user.is_superuser):
                if request.user.user_type == 'ADMIN' or request.user.is_superuser:
                    request.session.modified = True
                if not request.session.get('student_view_unlocked'):
                    if url_name != 'student_view_auth':
                        request.session['next_student_url'] = path
                        return redirect('student_view_auth')

            if path.startswith('/customadmin/') and request.session.get('student_view_unlocked'):
                del request.session['student_view_unlocked']
                request.session.modified = True

            # --- Teacher View Step-Up ---
            if url_name in _TEACHER_URL_NAMES and (request.user.user_type == 'ADMIN' or request.user.is_superuser):
                if not request.session.get('teacher_view_unlocked'):
                    if url_name != 'teacher_view_auth':
                        request.session['next_teacher_url'] = path
                        return redirect('teacher_view_auth')

        try:
            response = self.get_response(request)

            response["Server"] = "Webserver"
            response["X-Powered-By"] = "Secure Portal"
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "Sat, 01 Jan 2000 00:00:00 GMT"
            response["Referrer-Policy"] = "same-origin"

            return response
        except Exception as e:
            raise e


class EnterpriseHardeningMiddleware:
    """Enterprise-grade security header injection and threat mitigation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # File upload malware scanning is handled per-view for better UX
        # (professional messages, stay-on-page, AJAX support)

        if request.user.is_authenticated:
            import threading
            threading.Thread(target=self._check_impossible_travel, args=(request,), daemon=True).start()

        response = self.get_response(request)

        # Use pre-computed CSP header
        response["Content-Security-Policy"] = _get_csp_header()
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "SAMEORIGIN"
        response["X-XSS-Protection"] = "1; mode=block"

        return response

    def _check_impossible_travel(self, request):
        from django.utils import timezone
        from datetime import timedelta

        cache_key = f"impossible_travel_{request.user.id}"
        if cache.get(cache_key):
            return

        current_ip = request.META.get('REMOTE_ADDR')

        from .utils.firebase_db import login_history_get_last
        last_login = login_history_get_last(str(request.user.uid))

        if last_login and last_login.get('ip_address') != current_ip:
            last_ts = last_login.get('timestamp', 0)
            if last_ts and (timezone.now().timestamp() * 1000 - last_ts) < 3600000:
                try:
                    from .utils.firebase_db import admin_log_create
                    admin_log_create(None, 'SUSPICIOUS_TRAVEL', target_user_uid=str(request.user.uid),
                                     details=f"Login from {current_ip} detected 1h after {last_login.get('ip_address')}.",
                                     ip_address=current_ip)
                except Exception:
                    pass
                def _async_suspicious():
                    try:
                        from .utils.firebase_audit import log_security_event
                        log_security_event('SUSPICIOUS_TRAVEL', f"IP change: {last_login.get('ip_address')} -> {current_ip}", username=request.user.username, ip=current_ip)
                    except Exception:
                        pass
                import threading
                threading.Thread(target=_async_suspicious, daemon=True).start()

        cache.set(cache_key, True, 3600)


slow_query_logger = logging.getLogger('django.db.backends.schema')


class SlowQueryMonitorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = _time.time()
        response = self.get_response(request)
        duration = _time.time() - start
        if duration > 2.0:
            slow_query_logger.warning(
                "SLOW_REQUEST: %.2fs %s %s | user=%s",
                duration,
                request.method,
                request.path,
                request.user.username if request.user.is_authenticated else 'anonymous',
            )
        return response
