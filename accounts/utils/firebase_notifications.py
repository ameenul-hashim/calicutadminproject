import os
import json
import time
import uuid
import threading
import logging
import firebase_admin
from firebase_admin import credentials, db

logger = logging.getLogger(__name__)

_firebase_app = None
_lock = threading.Lock()


def _get_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    with _lock:
        if _firebase_app is not None:
            return _firebase_app
        db_url = os.getenv('FIREBASE_RTDB_URL')
        if not db_url:
            logger.warning('Firebase Notifications: FIREBASE_RTDB_URL not set')
            return None
        json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        cred_source = None
        if json_str:
            try:
                cred = credentials.Certificate(json.loads(json_str))
                cred_source = 'FIREBASE_SERVICE_ACCOUNT_JSON (env var)'
            except Exception as e:
                logger.error(f'Firebase Notifications credential parse failed: {e}')
                return None
        elif json_path:
            try:
                cred = credentials.Certificate(json_path)
                cred_source = f'FIREBASE_SERVICE_ACCOUNT_PATH ({json_path})'
            except Exception as e:
                logger.error(f'Firebase Notifications credential load failed from {json_path}: {e}')
                return None
        else:
            logger.warning('Firebase Notifications: no credentials set')
            return None
        try:
            _firebase_app = firebase_admin.initialize_app(
                cred, {'databaseURL': db_url}, name='notifications'
            )
            logger.info(f'Firebase Notifications initialized | source={cred_source} | db_url={db_url}')
        except Exception as e:
            logger.error(f'Firebase Notifications initialize_app failed: {e}')
            return None
    return _firebase_app


def create_notification_firebase(user_uid, message):
    app = _get_app()
    if app is None:
        return None
    notif_uid = str(uuid.uuid4())
    now_ms = int(time.time() * 1000)
    ref = db.reference(f'/notifications/{user_uid}/{notif_uid}')
    ref.set({
        'message': message,
        'is_read': False,
        'created_at': now_ms
    })
    return notif_uid


def get_notifications_firebase(user_uid, limit=50, filter_keywords=None):
    app = _get_app()
    if app is None:
        return []
    ref = db.reference(f'/notifications/{user_uid}')
    data = ref.get()
    if not data:
        return []
    notifs = []
    for nid, ndata in data.items():
        msg = ndata.get('message', '')
        if filter_keywords:
            if not any(kw.lower() in msg.lower() for kw in filter_keywords):
                continue
        notifs.append({
            'uid': nid,
            'message': msg,
            'is_read': ndata.get('is_read', False),
            'created_at': ndata.get('created_at', 0),
        })
    notifs.sort(key=lambda x: x['created_at'], reverse=True)
    return notifs[:limit]


def mark_read_firebase(user_uid, notif_uid):
    app = _get_app()
    if app is None:
        return
    ref = db.reference(f'/notifications/{user_uid}/{notif_uid}/is_read')
    ref.set(True)


def mark_all_read_firebase(user_uid):
    app = _get_app()
    if app is None:
        return
    ref = db.reference(f'/notifications/{user_uid}')
    data = ref.get()
    if data:
        for nid in data:
            db.reference(f'/notifications/{user_uid}/{nid}/is_read').set(True)


def delete_notification_firebase(user_uid, notif_uid):
    app = _get_app()
    if app is None:
        return
    ref = db.reference(f'/notifications/{user_uid}/{notif_uid}')
    ref.delete()


def get_unread_count_firebase(user_uid, filter_keywords=None):
    app = _get_app()
    if app is None:
        return 0
    ref = db.reference(f'/notifications/{user_uid}')
    data = ref.get()
    if not data:
        return 0
    count = 0
    for ndata in data.values():
        if ndata.get('is_read', False):
            continue
        msg = ndata.get('message', '')
        if filter_keywords:
            if any(kw.lower() in msg.lower() for kw in filter_keywords):
                count += 1
        else:
            count += 1
    return count


def cleanup_old_notifications(days=7):
    app = _get_app()
    if app is None:
        return 0
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    ref = db.reference('/notifications')
    users = ref.get()
    if not users:
        return 0
    deleted = 0
    for user_uid, notifs in users.items():
        for notif_uid, ndata in notifs.items():
            if ndata.get('created_at', 0) < cutoff:
                db.reference(f'/notifications/{user_uid}/{notif_uid}').delete()
                deleted += 1
    return deleted
