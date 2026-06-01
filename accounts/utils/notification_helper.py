from django.utils import timezone
from datetime import timedelta

RETENTION_DAYS = 7


def get_notifications(user_uid, limit=50):
    from accounts.models import Notification, CustomUser
    user = CustomUser.objects.filter(uid=user_uid).first()
    if not user:
        return []
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    qs = Notification.objects.filter(user=user, created_at__gte=cutoff).order_by('-created_at')[:limit]
    return [{
        'uid': n.uid,
        'message': n.message,
        'is_read': n.is_read,
        'created_at': n.created_at,
    } for n in qs]


def get_unread_count(user_uid):
    from accounts.models import Notification, CustomUser
    user = CustomUser.objects.filter(uid=user_uid).first()
    if not user:
        return 0
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    return Notification.objects.filter(user=user, is_read=False, created_at__gte=cutoff).count()


def mark_read(user_uid, notif_uid):
    from accounts.models import Notification, CustomUser
    user = CustomUser.objects.filter(uid=user_uid).first()
    if not user:
        return
    Notification.objects.filter(user=user, uid=notif_uid).update(is_read=True)


def mark_all_read(user_uid):
    from accounts.models import Notification, CustomUser
    user = CustomUser.objects.filter(uid=user_uid).first()
    if not user:
        return
    Notification.objects.filter(user=user, is_read=False).update(is_read=True)


def delete_notification(user_uid, notif_uid):
    from accounts.models import Notification, CustomUser
    user = CustomUser.objects.filter(uid=user_uid).first()
    if not user:
        return
    Notification.objects.filter(user=user, uid=notif_uid).delete()


def cleanup_old_notifications():
    from accounts.models import Notification
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    deleted, _ = Notification.objects.filter(created_at__lt=cutoff).delete()
    return deleted
