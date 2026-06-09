import os
import json
import time
import uuid
import threading
import logging
from datetime import datetime, timezone, timedelta
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
            logger.warning('Firebase RTDB URL not set (FIREBASE_RTDB_URL missing). Firebase disabled.')
            return None
        json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        cred_source = None
        if json_str:
            try:
                cred = credentials.Certificate(json.loads(json_str))
                cred_source = 'FIREBASE_SERVICE_ACCOUNT_JSON (env var)'
            except Exception as e:
                logger.error(f'Firebase credential parse failed from FIREBASE_SERVICE_ACCOUNT_JSON: {e}')
                return None
        elif json_path:
            try:
                with open(json_path) as f:
                    cred = credentials.Certificate(json.load(f))
                cred_source = f'FIREBASE_SERVICE_ACCOUNT_PATH ({json_path})'
            except Exception as e:
                logger.error(f'Firebase credential load failed from {json_path}: {e}')
                return None
        else:
            logger.warning('No Firebase credentials found (neither FIREBASE_SERVICE_ACCOUNT_JSON nor FIREBASE_SERVICE_ACCOUNT_PATH set).')
            return None
        try:
            _firebase_app = firebase_admin.initialize_app(
                cred, {'databaseURL': db_url}
            )
            logger.info(f'Firebase initialized successfully | source={cred_source} | db_url={db_url} | app=default')
        except Exception as e:
            logger.error(f'Firebase initialize_app failed: {e}')
            return None
    return _firebase_app


# ============================================================
# NOTIFICATIONS (30-day retention, structured)
# Structure per node:
#   title: str
#   message: str
#   type: str (e.g. 'course_approved', 'new_course', etc.)
#   action_url: str
#   is_read: bool
#   created_at: int (ms)
#   read_at: int (ms) or null
#   expires_at: int (ms) or null
# ============================================================

NOTIF_RETENTION_DAYS = 30

def _notif_now_ms():
    return int(time.time() * 1000)


def _notif_expires_at():
    return _notif_now_ms() + (NOTIF_RETENTION_DAYS * 24 * 60 * 60 * 1000)


def notif_create(user_uid, title, message, notif_type='general', action_url=''):
    app = _get_app()
    if app is None:
        return None
    notif_uid = str(uuid.uuid4())
    now_ms = _notif_now_ms()
    ref = db.reference(f'/notifications/{user_uid}/{notif_uid}', app=app)
    ref.set({
        'title': title,
        'message': message,
        'type': notif_type,
        'action_url': action_url,
        'is_read': False,
        'created_at': now_ms,
        'read_at': None,
        'expires_at': _notif_expires_at(),
    })
    return notif_uid


def notif_create_batch(user_uids, title, message, notif_type='general', action_url=''):
    app = _get_app()
    if app is None or not user_uids:
        return []
    now_ms = _notif_now_ms()
    updates = {}
    notif_uids = []
    for user_uid in user_uids:
        notif_uid = str(uuid.uuid4())
        updates[f'/notifications/{user_uid}/{notif_uid}'] = {
            'title': title,
            'message': message,
            'type': notif_type,
            'action_url': action_url,
            'is_read': False,
            'created_at': now_ms,
            'read_at': None,
            'expires_at': _notif_expires_at(),
        }
        notif_uids.append(notif_uid)
    if updates:
        db.reference('/', app=app).update(updates)
    return notif_uids


def notif_get_all(user_uid, limit=25, offset=0):
    app = _get_app()
    if app is None:
        return [], 0
    ref = db.reference(f'/notifications/{user_uid}', app=app)
    data = ref.get()
    if not data:
        return [], 0
    notifs = []
    for nid, ndata in data.items():
        notifs.append({
            'uid': nid,
            'title': ndata.get('title', ''),
            'message': ndata.get('message', ''),
            'type': ndata.get('type', 'general'),
            'action_url': ndata.get('action_url', ''),
            'is_read': ndata.get('is_read', False),
            'created_at': ndata.get('created_at', 0),
            'read_at': ndata.get('read_at'),
            'expires_at': ndata.get('expires_at'),
        })
    notifs.sort(key=lambda x: x['created_at'], reverse=True)
    total = len(notifs)
    page = notifs[offset:offset + limit]
    return page, total


def notif_get_unread_count(user_uid):
    app = _get_app()
    if app is None:
        return 0
    ref = db.reference(f'/notifications/{user_uid}', app=app)
    data = ref.get()
    if not data:
        return 0
    count = 0
    for ndata in data.values():
        if not ndata.get('is_read', False):
            count += 1
    return count


def notif_mark_read(user_uid, notif_uid):
    app = _get_app()
    if app is None:
        return
    now_ms = _notif_now_ms()
    db.reference(f'/notifications/{user_uid}/{notif_uid}/is_read', app=app).set(True)
    db.reference(f'/notifications/{user_uid}/{notif_uid}/read_at', app=app).set(now_ms)


def notif_mark_all_read(user_uid):
    app = _get_app()
    if app is None:
        return
    now_ms = _notif_now_ms()
    ref = db.reference(f'/notifications/{user_uid}', app=app)
    data = ref.get()
    if data:
        for nid in data:
            db.reference(f'/notifications/{user_uid}/{nid}/is_read', app=app).set(True)
            db.reference(f'/notifications/{user_uid}/{nid}/read_at', app=app).set(now_ms)


def notif_delete(user_uid, notif_uid):
    app = _get_app()
    if app is None:
        return
    db.reference(f'/notifications/{user_uid}/{notif_uid}', app=app).delete()


def notif_cleanup(days=NOTIF_RETENTION_DAYS):
    app = _get_app()
    if app is None:
        return 0
    cutoff = _notif_now_ms() - (days * 24 * 60 * 60 * 1000)
    ref = db.reference('/notifications', app=app)
    users = ref.get()
    if not users:
        return 0
    deleted = 0
    for user_uid, notifs in users.items():
        to_delete = []
        for notif_uid, ndata in notifs.items():
            if ndata.get('created_at', 0) < cutoff:
                to_delete.append(notif_uid)
        for notif_uid in to_delete:
            db.reference(f'/notifications/{user_uid}/{notif_uid}', app=app).delete()
            deleted += 1
        if to_delete and len(to_delete) == len(notifs):
            db.reference(f'/notifications/{user_uid}', app=app).delete()
    return deleted


# ============================================================
# CHAT MESSAGES (7-day retention)
# ============================================================

def _chat_room_name(uid1, uid2):
    parts = sorted([str(uid1), str(uid2)])
    return f"{parts[0]}_{parts[1]}"


def chat_send(sender_uid, receiver_uid, message_text, sender_name=''):
    app = _get_app()
    if app is None:
        return None, 0
    msg_uid = str(uuid.uuid4())
    now_ms = int(time.time() * 1000)
    room = _chat_room_name(sender_uid, receiver_uid)
    msg_ref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}', app=app)
    msg_ref.set({
        'sender_uid': str(sender_uid),
        'receiver_uid': str(receiver_uid),
        'sender_name': sender_name,
        'message': message_text,
        'timestamp': now_ms,
        'is_edited': False,
        'is_deleted': False,
        'is_read': False,
    })
    meta_ref = db.reference(f'/chat_rooms/{room}/metadata', app=app)
    meta_ref.update({
        'participants': {str(sender_uid): True, str(receiver_uid): True},
        'last_message': message_text,
        'last_timestamp': now_ms,
        'last_sender_uid': str(sender_uid),
    })
    # Index for O(1) edit/delete lookup
    db.reference(f'/msg_index/{msg_uid}', app=app).set({'room': room})
    return msg_uid, now_ms


def _chat_find_room(app, sender_uid, msg_uid):
    """Look up room by msg_index; fallback to scanning all rooms for legacy messages."""
    idx = db.reference(f'/msg_index/{msg_uid}/room', app=app).get()
    if idx:
        return idx
    # Fallback: scan all rooms (legacy messages without index)
    rooms = db.reference('/chat_rooms', app=app).get(shallow=True)
    if not rooms:
        return None
    for room in rooms:
        mref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}', app=app)
        mdata = mref.get()
        if mdata and mdata.get('sender_uid') == str(sender_uid):
            return room
    return None


def chat_edit(sender_uid, msg_uid, new_message):
    app = _get_app()
    if app is None:
        return False
    room = _chat_find_room(app, sender_uid, msg_uid)
    if not room:
        return False
    mref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}', app=app)
    mdata = mref.get()
    if mdata and mdata.get('sender_uid') == str(sender_uid):
        mref.update({'message': new_message, 'is_edited': True})
        if not db.reference(f'/msg_index/{msg_uid}/room', app=app).get():
            db.reference(f'/msg_index/{msg_uid}', app=app).set({'room': room})
        return True
    return False


def chat_delete(sender_uid, msg_uid):
    app = _get_app()
    if app is None:
        return False
    room = _chat_find_room(app, sender_uid, msg_uid)
    if not room:
        return False
    mref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}', app=app)
    mdata = mref.get()
    if mdata and mdata.get('sender_uid') == str(sender_uid):
        mref.update({'is_deleted': True})
        if not db.reference(f'/msg_index/{msg_uid}/room', app=app).get():
            db.reference(f'/msg_index/{msg_uid}', app=app).set({'room': room})
        return True
    return False


def chat_get_messages(user_uid, other_user_uid, limit=500):
    app = _get_app()
    if app is None:
        return []
    room = _chat_room_name(user_uid, other_user_uid)
    data = db.reference(f'/chat_rooms/{room}/messages', app=app).get()
    if not data:
        return []
    msgs = []
    for mid, mdata in data.items():
        if mdata.get('is_deleted', False):
            continue
        msgs.append({
            'uid': mid,
            'sender_uid': mdata.get('sender_uid'),
            'sender_name': mdata.get('sender_name', ''),
            'message': mdata.get('message', ''),
            'timestamp': mdata.get('timestamp', 0),
            'is_edited': mdata.get('is_edited', False),
        })
    msgs.sort(key=lambda x: x['timestamp'])
    return msgs[-limit:]


def chat_mark_read(user_uid, other_user_uid):
    app = _get_app()
    if app is None:
        return
    room = _chat_room_name(user_uid, other_user_uid)
    ref = db.reference(f'/chat_rooms/{room}/messages', app=app)
    data = ref.get()
    if not data:
        return
    updates = {}
    for mid, mdata in data.items():
        if mdata.get('sender_uid') == str(other_user_uid) and not mdata.get('is_read', False):
            updates[f'{mid}/is_read'] = True
    if updates:
        ref.update(updates)


def chat_get_list(user_uid):
    app = _get_app()
    if app is None:
        return []
    data = db.reference('/chat_rooms', app=app).get()
    if not data:
        return []
    user_str = str(user_uid)
    rooms = []
    for room, room_data in data.items():
        meta = room_data.get('metadata', {})
        participants = meta.get('participants', {})
        if user_str not in participants:
            continue
        others = [p for p in participants if p != user_str]
        if not others:
            continue
        msgs = room_data.get('messages', {})
        unread = sum(
            1 for m in msgs.values()
            if m.get('sender_uid') == others[0]
            and not m.get('is_read', False)
            and not m.get('is_deleted', False)
        )
        rooms.append({
            'other_uid': others[0],
            'last_message': meta.get('last_message', ''),
            'last_timestamp': meta.get('last_timestamp', 0),
            'last_sender_uid': meta.get('last_sender_uid', ''),
            'unread_count': unread,
        })
    rooms.sort(key=lambda x: x.get('last_timestamp', 0), reverse=True)
    return rooms


def chat_get_unread_count(user_uid):
    app = _get_app()
    if app is None:
        return 0
    data = db.reference('/chat_rooms', app=app).get()
    if not data:
        return 0
    user_str = str(user_uid)
    total = 0
    for room_data in data.values():
        meta = room_data.get('metadata', {})
        if user_str not in meta.get('participants', {}):
            continue
        for m in room_data.get('messages', {}).values():
            if (m.get('sender_uid') != user_str
                    and not m.get('is_read', False)
                    and not m.get('is_deleted', False)):
                total += 1
    return total


def chat_cleanup(days=7):
    app = _get_app()
    if app is None:
        return 0
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    data = db.reference('/chat_rooms', app=app).get()
    if not data:
        return 0
    deleted = 0
    for room, room_data in data.items():
        msgs = room_data.get('messages', {})
        for mid, mdata in msgs.items():
            if mdata.get('timestamp', 0) < cutoff:
                db.reference(f'/chat_rooms/{room}/messages/{mid}', app=app).delete()
                db.reference(f'/msg_index/{mid}', app=app).delete()
                deleted += 1
    return deleted


# ============================================================
# LOGIN HISTORY (7-day retention)
# ============================================================

def login_history_create(user_uid, ip_address, user_agent, device_type, status):
    app = _get_app()
    if app is None:
        return None
    entry_uid = str(uuid.uuid4())
    now_ms = int(time.time() * 1000)
    ref = db.reference(f'/login_history/{user_uid}/{entry_uid}', app=app)
    ref.set({
        'ip_address': ip_address,
        'user_agent': user_agent,
        'device_type': device_type,
        'status': status,
        'timestamp': now_ms,
    })
    return entry_uid


def login_history_get_recent(user_uid=None, limit=15):
    app = _get_app()
    if app is None:
        return []
    if user_uid:
        data = db.reference(f'/login_history/{user_uid}', app=app).get()
        if not data:
            return []
        entries = []
        for eid, edata in data.items():
            edata['uid'] = eid
            entries.append({
                'uid': eid,
                'user_uid': user_uid,
                'ip_address': edata.get('ip_address', ''),
                'user_agent': edata.get('user_agent', ''),
                'device_type': edata.get('device_type', ''),
                'status': edata.get('status', ''),
                'timestamp': edata.get('timestamp', 0),
            })
        entries.sort(key=lambda x: x['timestamp'], reverse=True)
        return entries[:limit]
    # All users
    ref = db.reference('/login_history', app=app)
    all_data = ref.get()
    if not all_data:
        return []
    entries = []
    for uid, user_entries in all_data.items():
        for eid, edata in user_entries.items():
            entries.append({
                'uid': eid,
                'user_uid': uid,
                'ip_address': edata.get('ip_address', ''),
                'user_agent': edata.get('user_agent', ''),
                'device_type': edata.get('device_type', ''),
                'status': edata.get('status', ''),
                'timestamp': edata.get('timestamp', 0),
            })
    entries.sort(key=lambda x: x['timestamp'], reverse=True)
    return entries[:limit]


def login_history_get_last(user_uid):
    app = _get_app()
    if app is None:
        return None
    data = db.reference(f'/login_history/{user_uid}', app=app).get()
    if not data:
        return None
    entries = []
    for eid, edata in data.items():
        entries.append(edata | {'uid': eid, 'user_uid': user_uid})
    entries.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return entries[0] if entries else None


def login_history_get_daily_total(days=30, status='SUCCESS'):
    app = _get_app()
    if app is None:
        return {}
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    ref = db.reference('/login_history', app=app)
    all_data = ref.get()
    if not all_data:
        return {}
    daily = {}
    for uid, user_entries in all_data.items():
        for eid, edata in user_entries.items():
            ts = edata.get('timestamp', 0)
            if ts < cutoff:
                continue
            if edata.get('status') != status:
                continue
            date_key = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            daily[date_key] = daily.get(date_key, 0) + 1
    return daily


def login_history_get_daily_unique(days=30, status='SUCCESS'):
    app = _get_app()
    if app is None:
        return {}
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    ref = db.reference('/login_history', app=app)
    all_data = ref.get()
    if not all_data:
        return {}
    daily = {}
    for uid, user_entries in all_data.items():
        for eid, edata in user_entries.items():
            ts = edata.get('timestamp', 0)
            if ts < cutoff:
                continue
            if edata.get('status') != status:
                continue
            date_key = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            daily.setdefault(date_key, set()).add(uid)
    return {k: len(v) for k, v in daily.items()}


def login_history_get_total_count(days=None):
    app = _get_app()
    if app is None:
        return 0
    ref = db.reference('/login_history', app=app)
    all_data = ref.get()
    if not all_data:
        return 0
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000) if days else 0
    count = 0
    for user_entries in all_data.values():
        for edata in user_entries.values():
            if cutoff and edata.get('timestamp', 0) < cutoff:
                continue
            count += 1
    return count


def login_history_cleanup(days=7):
    app = _get_app()
    if app is None:
        return 0
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    ref = db.reference('/login_history', app=app)
    all_data = ref.get()
    if not all_data:
        return 0
    deleted = 0
    for uid, user_entries in all_data.items():
        for eid, edata in user_entries.items():
            if edata.get('timestamp', 0) < cutoff:
                db.reference(f'/login_history/{uid}/{eid}', app=app).delete()
                deleted += 1
    return deleted


# ============================================================
# ADMIN ACTIVITY LOG (7-day retention)
# ============================================================

def admin_log_create(admin_uid, action, target_user_uid=None, details='', ip_address=''):
    app = _get_app()
    if app is None:
        return None
    entry_uid = str(uuid.uuid4())
    now_ms = int(time.time() * 1000)
    ref = db.reference(f'/admin_activity/{entry_uid}', app=app)
    ref.set({
        'admin_uid': str(admin_uid) if admin_uid else '',
        'action': action,
        'target_user_uid': str(target_user_uid) if target_user_uid else '',
        'details': details,
        'ip_address': ip_address,
        'timestamp': now_ms,
    })
    return entry_uid


def admin_log_get_recent(limit=15):
    app = _get_app()
    if app is None:
        return []
    ref = db.reference('/admin_activity', app=app)
    data = ref.get()
    if not data:
        return []
    entries = []
    for eid, edata in data.items():
        entries.append({
            'uid': eid,
            'admin_uid': edata.get('admin_uid', ''),
            'action': edata.get('action', ''),
            'target_user_uid': edata.get('target_user_uid', ''),
            'details': edata.get('details', ''),
            'ip_address': edata.get('ip_address', ''),
            'timestamp': edata.get('timestamp', 0),
        })
    entries.sort(key=lambda x: x['timestamp'], reverse=True)
    return entries[:limit]


def admin_log_get_total_count(days=None):
    app = _get_app()
    if app is None:
        return 0
    ref = db.reference('/admin_activity', app=app)
    data = ref.get()
    if not data:
        return 0
    if not days:
        return len(data)
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    return sum(1 for edata in data.values() if edata.get('timestamp', 0) >= cutoff)


def admin_log_cleanup(days=7):
    app = _get_app()
    if app is None:
        return 0
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    ref = db.reference('/admin_activity', app=app)
    data = ref.get()
    if not data:
        return 0
    deleted = 0
    for eid, edata in data.items():
        if edata.get('timestamp', 0) < cutoff:
            db.reference(f'/admin_activity/{eid}', app=app).delete()
            deleted += 1
    return deleted


# (Email OTP uses PostgreSQL EmailOTP model — no Firebase path needed)


# ============================================================
# USER DATA CLEANUP (on user deletion)
# ============================================================

def cleanup_user_firebase_data(user_uid):
    """Delete ALL Firebase data for a deleted user across all RTDB nodes.

    Handles: notifications, chat_rooms, msg_index, support_chat,
    login_history, admin_activity, analytics/daily_counts.
    Returns dict of counts per node cleaned.
    """
    app = _get_app()
    if app is None:
        return {}
    user_str = str(user_uid)
    counts = {}

    # 1. Notifications
    try:
        nref = db.reference(f'/notifications/{user_str}', app=app)
        ndata = nref.get(shallow=True)
        if ndata:
            nref.delete()
            counts['notifications'] = len(ndata)
        else:
            counts['notifications'] = 0
    except Exception as e:
        logger.error(f"Firebase cleanup notifications for {user_str}: {e}")
        counts['notifications'] = -1

    # 2. Chat rooms — find all rooms where user is a participant, delete entire room
    try:
        rooms_deleted = 0
        msgs_cleaned = 0
        all_rooms = db.reference('/chat_rooms', app=app).get()
        if all_rooms:
            for room_name, room_data in all_rooms.items():
                meta = room_data.get('metadata', {})
                participants = meta.get('participants', {})
                if user_str in participants:
                    # Collect msg_index entries for cleanup
                    msgs = room_data.get('messages', {})
                    if msgs:
                        for mid in msgs:
                            db.reference(f'/msg_index/{mid}', app=app).delete()
                            msgs_cleaned += 1
                    db.reference(f'/chat_rooms/{room_name}', app=app).delete()
                    rooms_deleted += 1
        counts['chat_rooms'] = rooms_deleted
        counts['msg_index'] = msgs_cleaned
    except Exception as e:
        logger.error(f"Firebase cleanup chat_rooms for {user_str}: {e}")
        counts['chat_rooms'] = -1
        counts['msg_index'] = -1

    # 3. Support chat — find entries where user is admin or teacher
    try:
        support_deleted = 0
        all_support = db.reference('/support_chat', app=app).get()
        if all_support:
            for admin_uid, teachers in all_support.items():
                if admin_uid == user_str:
                    db.reference(f'/support_chat/{admin_uid}', app=app).delete()
                    support_deleted += 1
                elif teachers:
                    for teacher_uid in teachers:
                        if teacher_uid == user_str:
                            db.reference(f'/support_chat/{admin_uid}/{teacher_uid}', app=app).delete()
                            support_deleted += 1
        counts['support_chat'] = support_deleted
    except Exception as e:
        logger.error(f"Firebase cleanup support_chat for {user_str}: {e}")
        counts['support_chat'] = -1

    # 4. Login history
    try:
        lref = db.reference(f'/login_history/{user_str}', app=app)
        ldata = lref.get(shallow=True)
        if ldata:
            lref.delete()
            counts['login_history'] = len(ldata)
        else:
            counts['login_history'] = 0
    except Exception as e:
        logger.error(f"Firebase cleanup login_history for {user_str}: {e}")
        counts['login_history'] = -1

    # 5. Admin activity — delete entries where admin_uid or target_user_uid matches
    try:
        admin_deleted = 0
        all_admin = db.reference('/admin_activity', app=app).get()
        if all_admin:
            for eid, edata in all_admin.items():
                if edata.get('admin_uid') == user_str or edata.get('target_user_uid') == user_str:
                    db.reference(f'/admin_activity/{eid}', app=app).delete()
                    admin_deleted += 1
        counts['admin_activity'] = admin_deleted
    except Exception as e:
        logger.error(f"Firebase cleanup admin_activity for {user_str}: {e}")
        counts['admin_activity'] = -1

    # 6. Analytics daily counts — scan for user references
    try:
        analytics_cleaned = 0
        all_analytics = db.reference('/analytics/daily_counts', app=app).get()
        if all_analytics:
            for date_key, entries in all_analytics.items():
                if isinstance(entries, dict):
                    to_remove = [k for k, v in entries.items() if isinstance(v, dict) and v.get('user_uid') == user_str]
                    for k in to_remove:
                        db.reference(f'/analytics/daily_counts/{date_key}/{k}', app=app).delete()
                        analytics_cleaned += 1
        counts['analytics'] = analytics_cleaned
    except Exception as e:
        logger.error(f"Firebase cleanup analytics for {user_str}: {e}")
        counts['analytics'] = -1

    logger.info(f"Firebase cleanup complete for user {user_str}: {counts}")
    return counts


# ============================================================
# GLOBAL CLEANUP (call periodically)
# ============================================================

def run_all_cleanup():
    from .firebase_chat import cleanup_old_messages as chat_v2_cleanup
    return {
        'notifications': notif_cleanup(),
        'chat_legacy': chat_cleanup(),
        'chat_v2': chat_v2_cleanup(),
        'login_history': login_history_cleanup(),
        'admin_log': admin_log_cleanup(),
    }


def init_firebase_structure():
    """Creates root nodes in RTDB to prevent manual setup."""
    app = _get_app()
    if app is None:
        return False
    try:
        ref = db.reference('/', app=app)
        existing = ref.get(shallow=True) or {}
        updates = {}
        for node in ['admin_activity', 'analytics', 'audit', 'login_history', 'notifications', 'support_chat', 'test_write', 'backup']:
            if node not in existing:
                updates[f'/{node}/_init'] = True
        if updates:
            ref.update(updates)
        return True
    except Exception as e:
        logger.error(f"Failed to intialize firebase structure: {e}")
        return False

