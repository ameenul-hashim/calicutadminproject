from django.core.cache import cache
from accounts.models import CustomUser, Course, DeletionRequest
from accounts.utils.firebase_notifications import get_notifications_firebase, get_unread_count_firebase
from datetime import datetime

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
        
        notifs = get_notifications_firebase(str(request.user.uid))[:10]
        for n in notifs:
            ts = n.get('created_at', 0)
            n['created_at'] = datetime.fromtimestamp(ts / 1000) if ts else None
        context['notifications'] = notifs
        context['unread_notifications_count'] = get_unread_count_firebase(str(request.user.uid))

        if request.user.user_type == 'ADMIN':
            context['pending_students_count'] = CustomUser.objects.filter(user_type='STUDENT', status='PENDING').count()
            context['pending_teachers_count'] = CustomUser.objects.filter(user_type='TEACHER', status='PENDING').count()
            
            pending_courses = Course.objects.filter(status='PENDING').count()
            courses_with_updates = Course.objects.filter(status='PUBLISHED').filter(lessons__is_approved=False).distinct().count()
            
            context['pending_courses_total'] = pending_courses + courses_with_updates
            context['pending_deletions_count'] = DeletionRequest.objects.filter(status='PENDING').count()
            context['unread_admin_notifs'] = context['unread_notifications_count']

        elif request.user.user_type == 'TEACHER':
            context['teacher_pending_approvals'] = Course.objects.filter(teacher=request.user, status='PENDING').count()
            context['teacher_rejected_courses'] = Course.objects.filter(teacher=request.user, status='REJECTED').count()
            context['unread_teacher_notifs'] = context['unread_notifications_count']

        elif request.user.user_type == 'STUDENT':
            context['unread_student_notifs'] = context['unread_notifications_count']

        # Cache for 60 seconds
        try:
            cache.set(cache_key, context, 60)
        except Exception:
            pass
            
        return context
    except Exception:
        # Absolute fallback to prevent 500 error on every page
        return {}


