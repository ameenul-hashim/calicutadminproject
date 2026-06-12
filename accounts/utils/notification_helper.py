RETENTION_DAYS = 7


def _uid(val):
    if val is None:
        return None
    return str(val)


def get_notifications(user_uid=None, limit=25, offset=0, user_obj=None):
    uid = _uid(user_uid or (user_obj.uid if user_obj else None))
    if not uid:
        return [], 0
    from .firebase_db import notif_get_all
    return notif_get_all(uid, limit, offset)


def get_unread_count(user_uid=None, user_obj=None):
    uid = _uid(user_uid or (user_obj.uid if user_obj else None))
    if not uid:
        return 0
    from .firebase_db import notif_get_unread_count
    return notif_get_unread_count(uid)


def mark_read(user_uid, notif_uid):
    uid = _uid(user_uid)
    if not uid:
        return
    from .firebase_db import notif_mark_read
    notif_mark_read(uid, notif_uid)


def mark_all_read(user_uid):
    uid = _uid(user_uid)
    if not uid:
        return
    from .firebase_db import notif_mark_all_read
    notif_mark_all_read(uid)


def delete_notification(user_uid, notif_uid):
    uid = _uid(user_uid)
    if not uid:
        return
    from .firebase_db import notif_delete
    notif_delete(uid, notif_uid)


def cleanup_old_notifications():
    from .firebase_db import notif_cleanup
    notif_cleanup(RETENTION_DAYS)
