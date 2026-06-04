from django.utils import timezone
from datetime import timedelta

RETENTION_DAYS = 7


def _uid(val):
    if val is None:
        return None
    return str(val)


def get_notifications(user_uid=None, limit=50, user_obj=None):
    uid = _uid(user_uid or (user_obj.uid if user_obj else None))
    if not uid:
        return []
    from .firebase_notifications import get_notifications_firebase
    fb = get_notifications_firebase(uid, limit)
    if fb:
        return fb
    return _get_db(uid, limit)


def _get_db(user_uid, limit):
    from accounts.models import Notification, CustomUser
    try:
        user = CustomUser.objects.only('id').get(uid=user_uid)
    except CustomUser.DoesNotExist:
        return []
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    qs = Notification.objects.filter(user=user, created_at__gte=cutoff).order_by('-created_at')[:limit]
    return [{
        'uid': n.uid,
        'message': n.message,
        'is_read': n.is_read,
        'created_at': n.created_at,
    } for n in qs]


def get_unread_count(user_uid=None, user_obj=None):
    uid = _uid(user_uid or (user_obj.uid if user_obj else None))
    if not uid:
        return 0
    from .firebase_notifications import get_unread_count_firebase
    fb = get_unread_count_firebase(uid)
    if fb is not None:
        return fb
    return _unread_db(uid)


def _unread_db(user_uid):
    from accounts.models import Notification, CustomUser
    try:
        user = CustomUser.objects.only('id').get(uid=user_uid)
    except CustomUser.DoesNotExist:
        return 0
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    return Notification.objects.filter(user=user, is_read=False, created_at__gte=cutoff).count()


def mark_read(user_uid, notif_uid):
    uid = _uid(user_uid)
    if not uid:
        return
    from .firebase_notifications import mark_read_firebase
    mark_read_firebase(uid, notif_uid)


def mark_all_read(user_uid):
    uid = _uid(user_uid)
    if not uid:
        return
    from .firebase_notifications import mark_all_read_firebase
    mark_all_read_firebase(uid)


def delete_notification(user_uid, notif_uid):
    uid = _uid(user_uid)
    if not uid:
        return
    from .firebase_notifications import delete_notification_firebase
    delete_notification_firebase(uid, notif_uid)


def cleanup_old_notifications():
    from .firebase_notifications import cleanup_old_notifications as fb_cleanup
    fb_cleanup(RETENTION_DAYS)
    from accounts.models import Notification
    cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
    Notification.objects.filter(created_at__lt=cutoff).delete()
