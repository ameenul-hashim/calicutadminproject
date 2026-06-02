from django.core.cache import cache
from accounts.models import CustomUser, Course, DeletionRequest
from accounts.utils.notification_helper import get_notifications, get_unread_count
from time import time

def pending_counts(request):
    try:
        if not request.user.is_authenticated:
            return {}
        
        cache_key = f"pending_counts_{request.user.id}_{request.user.user_type}"
        try:
            cached_context = cache.get(cache_key)
            if cached_context:
                return cached_context
        except Exception:
            pass
        
        context = {
            'is_admin_preview': request.session.get('student_view_unlocked', False)
        }
        
        cleanup_cache_key = "cleanup_notifications_last_run"
        last_cleanup = cache.get(cleanup_cache_key, 0)
        if time() - last_cleanup > 3600:
            from accounts.utils.notification_helper import cleanup_old_notifications
            cleanup_old_notifications()
            try:
                cache.set(cleanup_cache_key, time(), 7200)
            except Exception:
                pass

        context['notifications'] = get_notifications(str(request.user.uid))[:10]
        context['unread_notifications_count'] = get_unread_count(str(request.user.uid))

        if request.user.user_type == 'ADMIN':
            context['pending_students_count'] = CustomUser.objects.filter(user_type='STUDENT', status='PENDING').count()
            context['pending_teachers_count'] = CustomUser.objects.filter(user_type='TEACHER', status='PENDING').count()
            
            pending_courses = Course.objects.filter(status='PENDING').count()
            courses_with_updates = Course.objects.filter(status='PUBLISHED', lessons__is_approved=False).values_list('id', flat=True).distinct().count()
            
            context['pending_courses_total'] = pending_courses + courses_with_updates
            context['pending_deletions_count'] = DeletionRequest.objects.filter(status='PENDING').count()
            context['unread_admin_notifs'] = context['unread_notifications_count']

        elif request.user.user_type == 'TEACHER':
            context['teacher_pending_approvals'] = Course.objects.filter(teacher=request.user, status='PENDING').count()
            context['teacher_rejected_courses'] = Course.objects.filter(teacher=request.user, status='REJECTED').count()
            context['unread_teacher_notifs'] = context['unread_notifications_count']

        elif request.user.user_type == 'STUDENT':
            context['unread_student_notifs'] = context['unread_notifications_count']

        try:
            cache.set(cache_key, context, 120)
        except Exception:
            pass
            
        return context
    except Exception:
        return {}


