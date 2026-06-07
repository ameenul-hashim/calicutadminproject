import os
import json
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import credentials, db

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
            return None
        json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        if json_str:
            cred = credentials.Certificate(json.loads(json_str))
        elif json_path:
            try:
                with open(json_path) as f:
                    cred = credentials.Certificate(json.load(f))
            except Exception:
                return None
        else:
            return None
        _firebase_app = firebase_admin.initialize_app(
            cred, {'databaseURL': db_url}
        )
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


# ============================================================
# EMAIL OTP (10-minute TTL)
# ============================================================

def otp_create(user_uid, purpose, otp_hash, ip_address='', user_agent=''):
    app = _get_app()
    if app is None:
        return None
    now_ms = int(time.time() * 1000)
    expires_ms = now_ms + (10 * 60 * 1000)  # 10 minutes
    ref = db.reference(f'/otp/{user_uid}/{purpose}', app=app)
    entry = {
        'otp_hash': otp_hash,
        'expires_at': expires_ms,
        'attempt_count': 0,
        'ip_address': ip_address,
        'user_agent': user_agent,
        'created_at': now_ms,
        'is_used': False,
    }
    ref.set(entry)
    return entry


def otp_get_active(user_uid, purpose):
    app = _get_app()
    if app is None:
        return None
    ref = db.reference(f'/otp/{user_uid}/{purpose}', app=app)
    data = ref.get()
    if not data:
        return None
    if data.get('is_used', False):
        return None
    if time.time() * 1000 > data.get('expires_at', 0):
        return None
    return data


def otp_mark_used(user_uid, purpose):
    app = _get_app()
    if app is None:
        return
    db.reference(f'/otp/{user_uid}/{purpose}/is_used', app=app).set(True)


def otp_increment_attempt(user_uid, purpose):
    app = _get_app()
    if app is None:
        return
    ref = db.reference(f'/otp/{user_uid}/{purpose}/attempt_count', app=app)
    try:
        ref.transaction(lambda current: (current or 0) + 1)
    except Exception:
        pass


def otp_invalidate_all(user_uid, purpose):
    app = _get_app()
    if app is None:
        return
    db.reference(f'/otp/{user_uid}/{purpose}/is_used', app=app).set(True)


def otp_get_user_daily_count(user_uid):
    app = _get_app()
    if app is None:
        return 0
    ref = db.reference(f'/otp/{user_uid}', app=app)
    data = ref.get()
    if not data:
        return 0
    cutoff = int(time.time() * 1000) - (24 * 60 * 60 * 1000)
    count = 0
    for purpose, entry in data.items():
        if entry.get('created_at', 0) >= cutoff:
            count += 1
    return count


def otp_get_ip_hourly_count(ip_address):
    app = _get_app()
    if app is None:
        return 0
    ref = db.reference('/otp', app=app)
    all_data = ref.get()
    if not all_data:
        return 0
    cutoff = int(time.time() * 1000) - (60 * 60 * 1000)
    count = 0
    for user_uid, purposes in all_data.items():
        for purpose, entry in purposes.items():
            if entry.get('ip_address') == ip_address and entry.get('created_at', 0) >= cutoff:
                count += 1
    return count


def otp_cleanup(minutes=10):
    app = _get_app()
    if app is None:
        return 0
    cutoff = int(time.time() * 1000) - (minutes * 60 * 1000)
    ref = db.reference('/otp', app=app)
    all_data = ref.get()
    if not all_data:
        return 0
    deleted = 0
    for user_uid, purposes in all_data.items():
        for purpose, entry in purposes.items():
            if entry.get('created_at', 0) < cutoff:
                db.reference(f'/otp/{user_uid}/{purpose}', app=app).delete()
                deleted += 1
    return deleted


# ============================================================
# GLOBAL CLEANUP (call periodically)
# ============================================================

def run_all_cleanup():
    return {
        'notifications': notif_cleanup(),
        'chat': chat_cleanup(),
        'login_history': login_history_cleanup(),
        'admin_log': admin_log_cleanup(),
        'otp': otp_cleanup(),
    }
