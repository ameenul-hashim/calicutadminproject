import os, json, time, uuid, logging
from datetime import datetime, timezone
from firebase_admin import db

from .firebase_db import _get_app as _get_firebase_app

logger = logging.getLogger(__name__)

EDIT_WINDOW_SECONDS = 3600
DELETE_WINDOW_SECONDS = 3600
RETENTION_DAYS = 7
PAGE_SIZE = 25
MAX_MESSAGE_LENGTH = 2000
RATE_LIMIT_MESSAGES = 20
RATE_LIMIT_WINDOW = 60


def _get_app():
    return _get_firebase_app()


def _now_ms():
    return int(time.time() * 1000)


def get_room_name(uid1, uid2):
    parts = sorted([str(uid1), str(uid2)])
    return f"{parts[0]}_{parts[1]}"


def _check_rate_limit(sender_uid):
    """Enforce rate limit: max RATE_LIMIT_MESSAGES per RATE_LIMIT_WINDOW seconds per user."""
    app = _get_app()
    if app is None:
        return True
    now = _now_ms()
    window_start = now - RATE_LIMIT_WINDOW * 1000
    rl_ref = db.reference(f'/rate_limits/{sender_uid}', app=app)
    timestamps = rl_ref.get() or []
    timestamps = [t for t in timestamps if t > window_start]
    if len(timestamps) >= RATE_LIMIT_MESSAGES:
        return False
    timestamps.append(now)
    rl_ref.set(timestamps[-RATE_LIMIT_MESSAGES * 2:])
    return True


def _sanitize_text(text):
    """Strip HTML tags but allow emoji and safe Unicode."""
    import re
    text = re.sub(r'<[^>]*>', '', text)
    return text[:MAX_MESSAGE_LENGTH]


def send_message(sender, receiver_uid, message_text, sender_name, attachment=None):
    app = _get_app()
    if app is None:
        return None
    if not _check_rate_limit(str(sender.uid)):
        return None, 'RATE_LIMITED'
    msg_uid = str(uuid.uuid4())
    now_ms = _now_ms()
    room = get_room_name(sender.uid, receiver_uid)

    sanitized = _sanitize_text(message_text)
    if not sanitized and not attachment:
        return None, 'EMPTY'

    msg_ref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}')
    msg_data = {
        'sender_uid': str(sender.uid),
        'receiver_uid': str(receiver_uid),
        'sender_name': sender_name,
        'message': sanitized,
        'timestamp': now_ms,
        'is_edited': False,
        'is_deleted': False,
        'is_read': False,
        'read_at': None,
        'edited_at': None,
    }
    if attachment:
        msg_data['attachment'] = attachment
    msg_ref.set(msg_data)

    meta_ref = db.reference(f'/chat_rooms/{room}/metadata')
    # Initialize metadata with conversation status if new
    meta_ref.update({
        'participants': {str(sender.uid): True, str(receiver_uid): True},
        'last_message': sanitized or '[Attachment]',
        'last_timestamp': now_ms,
        'last_sender_uid': str(sender.uid),
    })
    # Ensure default status
    meta = meta_ref.get()
    if meta and 'status' not in meta:
        meta_ref.update({'status': 'OPEN'})
    if meta and 'assigned_admin' not in meta:
        # Auto-assign to the first admin who participates
        if sender.user_type == 'TEACHER':
            from accounts.models import CustomUser
            first_admin = CustomUser.objects.filter(user_type='ADMIN', status='ACTIVE').order_by('id').first()
            if first_admin:
                meta_ref.update({'assigned_admin': str(first_admin.uid), 'assigned_admin_name': first_admin.chat_display})

    db.reference(f'/msg_index/{msg_uid}').set({'room': room})

    # Log audit
    _log_audit(sender, 'MESSAGE_SENT', {'message_uid': msg_uid, 'room': room, 'has_attachment': bool(attachment)})

    return msg_uid, now_ms


def _log_audit(actor, action, details=None):
    """Internal audit logger. Creates ChatAuditLog entry."""
    try:
        from accounts.models import ChatAuditLog
        actor_obj = actor if (actor and getattr(actor, 'pk', None)) else None
        ChatAuditLog.objects.create(
            actor=actor_obj,
            action=action,
            details=details or {},
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")


def _find_room_by_msgid(app, sender_uid, msg_uid):
    idx_ref = db.reference(f'/msg_index/{msg_uid}/room', app=app)
    room = idx_ref.get()
    if room:
        return room
    rooms = db.reference('/chat_rooms', app=app).get(shallow=True)
    if not rooms:
        return None
    for room_name in rooms:
        mref = db.reference(f'/chat_rooms/{room_name}/messages/{msg_uid}', app=app)
        mdata = mref.get()
        if mdata and mdata.get('sender_uid') == str(sender_uid):
            db.reference(f'/msg_index/{msg_uid}', app=app).set({'room': room_name})
            return room_name
    return None


def get_messages(user_uid, other_user_uid, limit=PAGE_SIZE, offset=0, search=None):
    app = _get_app()
    if app is None:
        return [], False
    room = get_room_name(user_uid, other_user_uid)
    data = db.reference(f'/chat_rooms/{room}/messages', app=app).get()
    if not data:
        return [], False

    msgs = []
    for mid, mdata in data.items():
        entry = {
            'uid': mid,
            'sender_uid': mdata.get('sender_uid'),
            'sender_name': mdata.get('sender_name', ''),
            'timestamp': mdata.get('timestamp', 0),
            'is_edited': mdata.get('is_edited', False),
            'is_deleted': mdata.get('is_deleted', False),
            'read_at': mdata.get('read_at'),
            'edited_at': mdata.get('edited_at'),
        }
        if mdata.get('is_deleted', False):
            entry['message'] = 'This message was deleted.'
        else:
            msg_text = mdata.get('message', '')
            if search and search.lower() not in msg_text.lower():
                continue
            entry['message'] = msg_text
        if mdata.get('attachment'):
            entry['attachment'] = mdata['attachment']
        msgs.append(entry)

    msgs.sort(key=lambda x: x['timestamp'])

    total = len(msgs)
    start = total - offset - limit
    if start < 0:
        start = 0
    end = total - offset
    if end > total:
        end = total
    page = msgs[start:end]
    has_more = start > 0

    return page, has_more


def edit_message(sender_uid, msg_uid, new_message):
    app = _get_app()
    if app is None:
        return False, 'Firebase unavailable'
    now_ms = _now_ms()
    room = _find_room_by_msgid(app, sender_uid, msg_uid)
    if not room:
        return False, 'Message not found'
    mref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}', app=app)
    mdata = mref.get()
    if not mdata:
        return False, 'Message not found'
    if mdata.get('sender_uid') != str(sender_uid):
        return False, 'Cannot edit another user message'
    if mdata.get('is_deleted', False):
        return False, 'Message already deleted'

    msg_time = mdata.get('timestamp', 0)
    if now_ms - msg_time > EDIT_WINDOW_SECONDS * 1000:
        return False, 'Edit window expired (1 hour)'

    sanitized = _sanitize_text(new_message)
    mref.update({'message': sanitized, 'is_edited': True, 'edited_at': now_ms})
    _log_audit(None, 'MESSAGE_EDITED', {'message_uid': msg_uid, 'room': room, 'actor_uid': sender_uid})
    return True, None


def delete_message(sender_uid, msg_uid):
    app = _get_app()
    if app is None:
        return False, 'Firebase unavailable'
    now_ms = _now_ms()
    room = _find_room_by_msgid(app, sender_uid, msg_uid)
    if not room:
        return False, 'Message not found'
    mref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}', app=app)
    mdata = mref.get()
    if not mdata:
        return False, 'Message not found'
    if mdata.get('sender_uid') != str(sender_uid):
        return False, 'Cannot delete another user message'
    if mdata.get('is_deleted', False):
        return False, 'Message already deleted'

    msg_time = mdata.get('timestamp', 0)
    if now_ms - msg_time > DELETE_WINDOW_SECONDS * 1000:
        return False, 'Delete window expired (1 hour)'

    mref.update({
        'is_deleted': True,
        'message': 'This message was deleted.',
        'edited_at': now_ms,
    })
    _log_audit(None, 'MESSAGE_DELETED', {'message_uid': msg_uid, 'room': room, 'actor_uid': sender_uid})
    return True, None


def mark_read(user_uid, other_user_uid):
    app = _get_app()
    if app is None:
        return
    now_ms = _now_ms()
    room = get_room_name(user_uid, other_user_uid)
    ref = db.reference(f'/chat_rooms/{room}/messages', app=app)
    data = ref.get()
    if not data:
        return
    updates = {}
    for mid, mdata in data.items():
        if (mdata.get('sender_uid') == str(other_user_uid)
                and not mdata.get('is_read', False)):
            updates[f'{mid}/is_read'] = True
            updates[f'{mid}/read_at'] = now_ms
    if updates:
        ref.update(updates)


def get_chat_list(user_uid, search=None):
    app = _get_app()
    if app is None:
        return []
    data = db.reference('/chat_rooms', app=app).get()
    if not data:
        return []
    user_str = str(user_uid)
    rooms = []
    for room_name, room_data in data.items():
        meta = room_data.get('metadata', {})
        participants = meta.get('participants', {})
        if user_str not in participants:
            continue
        others = [p for p in participants if p != user_str]
        if not others:
            continue
        other_uid = others[0]
        msgs = room_data.get('messages', {})
        unread = 0
        for m in msgs.values():
            if (m.get('sender_uid') == other_uid
                    and not m.get('is_read', False)
                    and not m.get('is_deleted', False)):
                unread += 1

        last_msg = meta.get('last_message', '')
        if search:
            if search.lower() not in last_msg.lower():
                continue

        room_entry = {
            'other_uid': other_uid,
            'last_message': last_msg,
            'last_timestamp': meta.get('last_timestamp', 0),
            'last_sender_uid': meta.get('last_sender_uid', ''),
            'unread_count': unread,
            'status': meta.get('status', 'OPEN'),
            'assigned_admin': meta.get('assigned_admin', ''),
            'assigned_admin_name': meta.get('assigned_admin_name', ''),
        }
        rooms.append(room_entry)
    rooms.sort(key=lambda x: x.get('last_timestamp', 0), reverse=True)
    return rooms


def get_unread_count(user_uid):
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
        participants = meta.get('participants', {})
        if user_str not in participants:
            continue
        for m in room_data.get('messages', {}).values():
            if (m.get('sender_uid') != user_str
                    and not m.get('is_read', False)
                    and not m.get('is_deleted', False)):
                total += 1
    return total


def get_room_unread(user_uid, other_user_uid):
    app = _get_app()
    if app is None:
        return 0
    room = get_room_name(user_uid, other_user_uid)
    data = db.reference(f'/chat_rooms/{room}/messages', app=app).get()
    if not data:
        return 0
    count = 0
    for m in data.values():
        if (m.get('sender_uid') == str(other_user_uid)
                and not m.get('is_read', False)
                and not m.get('is_deleted', False)):
            count += 1
    return count


def get_online_admins():
    """Get all admin users with status info. Never exposes internal UIDs to teachers."""
    try:
        from accounts.models import CustomUser
        from django.utils import timezone
    except Exception:
        return []
    admins = CustomUser.objects.filter(
        user_type='ADMIN', status='ACTIVE'
    ).only('uid', 'chat_display_name', 'chat_status', 'image', 'chat_display', 'last_seen')
    now = timezone.now()
    result = []
    for a in admins:
        is_online = a.chat_status in ('AVAILABLE', 'BUSY')
        last_seen_str = None
        if a.last_seen:
            delta = now - a.last_seen
            mins = int(delta.total_seconds() / 60)
            if mins < 1:
                last_seen_str = 'Just now'
            elif mins < 60:
                last_seen_str = f'{mins} minute{"s" if mins != 1 else ""} ago'
            else:
                hours = mins // 60
                last_seen_str = f'{hours} hour{"s" if hours != 1 else ""} ago'
        result.append({
            'display_name': a.chat_display,
            'status': a.chat_status,
            'avatar': a.avatar_url,
            'is_online': is_online,
            'last_seen': last_seen_str,
        })
    return result


def set_conversation_status(sender_uid, other_uid, new_status):
    """Set conversation status. Valid statuses: OPEN, WAITING_ADMIN, WAITING_TEACHER, RESOLVED, CLOSED."""
    valid = ('OPEN', 'WAITING_ADMIN', 'WAITING_TEACHER', 'RESOLVED', 'CLOSED')
    if new_status not in valid:
        return False, 'Invalid status'
    app = _get_app()
    if app is None:
        return False, 'Firebase unavailable'
    room = get_room_name(sender_uid, other_uid)
    meta_ref = db.reference(f'/chat_rooms/{room}/metadata', app=app)
    meta_ref.update({'status': new_status})
    return True, None


def get_conversation_status(sender_uid, other_uid):
    app = _get_app()
    if app is None:
        return 'OPEN'
    room = get_room_name(sender_uid, other_uid)
    meta_ref = db.reference(f'/chat_rooms/{room}/metadata', app=app)
    meta = meta_ref.get()
    if not meta:
        return 'OPEN'
    return meta.get('status', 'OPEN')


def get_all_messages_for_export(user_uid, other_user_uid):
    """Get ALL messages for export (no pagination)."""
    app = _get_app()
    if app is None:
        return []
    room = get_room_name(user_uid, other_user_uid)
    data = db.reference(f'/chat_rooms/{room}/messages', app=app).get()
    if not data:
        return []
    msgs = []
    for mid, mdata in data.items():
        if mdata.get('is_deleted', False):
            continue
        ts = mdata.get('timestamp', 0)
        dt_str = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %I:%M %p') if ts else ''
        msgs.append({
            'uid': mid,
            'sender_name': mdata.get('sender_name', ''),
            'message': mdata.get('message', ''),
            'timestamp': dt_str,
            'raw_ts': ts,
            'is_edited': mdata.get('is_edited', False),
        })
    msgs.sort(key=lambda x: x['raw_ts'])
    return msgs


def cleanup_old_messages(days=RETENTION_DAYS):
    app = _get_app()
    if app is None:
        return 0
    cutoff = _now_ms() - (days * 24 * 60 * 60 * 1000)
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
