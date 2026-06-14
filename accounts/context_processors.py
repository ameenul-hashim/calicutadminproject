import logging
from django.core.cache import cache
from time import time as _time

logger = logging.getLogger(__name__)


def pending_counts(request):
    try:
        if not request.user.is_authenticated:
            return {}

        user = request.user
        is_admin = user.user_type == 'ADMIN'

        # All users get cached counts (30s for admin, 300s for others)
        cache_key = f"pending_counts_{user.id}_{user.user_type}"
        try:
            cached_context = cache.get(cache_key)
            if cached_context:
                return cached_context
        except Exception:
            pass

        context = {
            'is_admin_preview': request.session.get('student_view_unlocked', False)
        }

        from accounts.utils.notification_helper import get_notifications, get_unread_count
        notifs, _ = get_notifications(user_obj=user)
        context['notifications'] = notifs[:10]
        context['unread_notifications_count'] = get_unread_count(user_obj=user)

        if is_admin:
            from accounts.models import CustomUser, Course, DeletionRequest, BackupLog, CourseDeletionRequest
            from django.db.models import Count, Q
            counts = CustomUser.objects.filter(
                Q(user_type='STUDENT', status='PENDING') |
                Q(user_type='TEACHER', status='PENDING')
            ).aggregate(
                pending_students=Count('id', filter=Q(user_type='STUDENT', status='PENDING')),
                pending_teachers=Count('id', filter=Q(user_type='TEACHER', status='PENDING')),
            )
            context['pending_students_count'] = counts['pending_students']
            context['pending_teachers_count'] = counts['pending_teachers']

            pending_courses = Course.objects.filter(status='PENDING').count()
            courses_with_updates = Course.objects.filter(
                status='PUBLISHED', lessons__is_approved=False
            ).values_list('id', flat=True).distinct().count()

            context['pending_courses_total'] = pending_courses + courses_with_updates
            context['pending_deletions_count'] = DeletionRequest.objects.filter(status='PENDING').count()
            context['pending_course_deletion_count'] = CourseDeletionRequest.objects.filter(status='PENDING').count()
            context['unread_admin_notifs'] = context['unread_notifications_count']
            context['backup_failed_count'] = BackupLog.objects.filter(status='FAILED').count()
            context['backup_pending_count'] = BackupLog.objects.filter(status__in=['PENDING', 'RUNNING', 'UPLOADING', 'VERIFYING']).count()
            try:
                from accounts.utils.firebase_chat import get_unread_count as chat_unread
                context['support_chat_unread'] = chat_unread(str(user.uid), user.user_type)
            except Exception:
                context['support_chat_unread'] = 0

        elif user.user_type == 'TEACHER':
            from accounts.models import Course
            from django.db.models import Count, Q
            teacher_counts = Course.objects.filter(teacher=request.user).aggregate(
                pending=Count('id', filter=Q(status='PENDING')),
                rejected=Count('id', filter=Q(status='REJECTED')),
            )
            context['teacher_pending_approvals'] = teacher_counts['pending']
            context['teacher_rejected_courses'] = teacher_counts['rejected']
            context['unread_teacher_notifs'] = context['unread_notifications_count']
            try:
                from accounts.utils.firebase_chat import get_unread_count as chat_unread
                context['support_chat_unread'] = chat_unread(str(user.uid), user.user_type)
            except Exception:
                context['support_chat_unread'] = 0

        elif user.user_type == 'STUDENT':
            context['unread_student_notifs'] = context['unread_notifications_count']

        # Hourly cleanup of old data (notifications, analytics)
        cleanup_cache_key = "cleanup_last_run"
        last_cleanup = cache.get(cleanup_cache_key, 0)
        if _time() - last_cleanup > 3600:
            try:
                from accounts.utils.notification_helper import cleanup_old_notifications
                cleanup_old_notifications()
            except Exception:
                pass
            try:
                from accounts.utils.firebase_db import run_all_cleanup
                run_all_cleanup()
            except Exception:
                pass
            try:
                from accounts.utils.firebase_analytics import analytics_cleanup
                analytics_cleanup(days=30)
            except Exception:
                pass
            cache.set(cleanup_cache_key, _time(), 7200)

        # Cache counts (30s admin, 300s others)
        try:
            cache.set(cache_key, context, 30 if is_admin else 300)
        except Exception:
            pass

        return context
    except Exception as e:
        logger.critical(f"pending_counts CRASH: {e}", exc_info=True)
        return {}
