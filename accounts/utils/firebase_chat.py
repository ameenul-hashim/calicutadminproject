import os, json, time, uuid, logging
from datetime import datetime, timezone
from firebase_admin import db

from .firebase_db import _get_app as _get_firebase_app

logger = logging.getLogger(__name__)

EDIT_WINDOW_SECONDS = 3600  # 1 hour
DELETE_WINDOW_SECONDS = 3600
RETENTION_DAYS = 7
PAGE_SIZE = 25


def _get_app():
    return _get_firebase_app()


def _now_ms():
    return int(time.time() * 1000)


def get_room_name(uid1, uid2):
    parts = sorted([str(uid1), str(uid2)])
    return f"{parts[0]}_{parts[1]}"


def send_message(sender, receiver_uid, message_text, sender_name):
    app = _get_app()
    if app is None:
        return None
    msg_uid = str(uuid.uuid4())
    now_ms = _now_ms()
    room = get_room_name(sender.uid, receiver_uid)

    msg_ref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}')
    msg_ref.set({
        'sender_uid': str(sender.uid),
        'receiver_uid': str(receiver_uid),
        'sender_name': sender_name,
        'message': message_text,
        'timestamp': now_ms,
        'is_edited': False,
        'is_deleted': False,
        'is_read': False,
        'read_at': None,
        'edited_at': None,
    })

    meta_ref = db.reference(f'/chat_rooms/{room}/metadata')
    meta_ref.update({
        'participants': {str(sender.uid): True, str(receiver_uid): True},
        'last_message': message_text,
        'last_timestamp': now_ms,
        'last_sender_uid': str(sender.uid),
    })

    # Index for O(1) edit/delete lookup
    db.reference(f'/msg_index/{msg_uid}').set({'room': room})

    return msg_uid, now_ms


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
    """Get messages with pagination and optional search."""
    app = _get_app()
    if app is None:
        return [], False
    room = get_room_name(user_uid, other_user_uid)
    data = db.reference(f'/chat_rooms/{room}/messages', app=app).get()
    if not data:
        return [], False

    msgs = []
    for mid, mdata in data.items():
        if mdata.get('is_deleted', False):
            msgs.append({
                'uid': mid,
                'sender_uid': mdata.get('sender_uid'),
                'sender_name': mdata.get('sender_name', ''),
                'message': 'This message was deleted.',
                'timestamp': mdata.get('timestamp', 0),
                'is_edited': mdata.get('is_edited', False),
                'is_deleted': True,
                'read_at': mdata.get('read_at'),
                'edited_at': mdata.get('edited_at'),
            })
        else:
            msg_text = mdata.get('message', '')
            if search and search.lower() not in msg_text.lower():
                continue
            msgs.append({
                'uid': mid,
                'sender_uid': mdata.get('sender_uid'),
                'sender_name': mdata.get('sender_name', ''),
                'message': msg_text,
                'timestamp': mdata.get('timestamp', 0),
                'is_edited': mdata.get('is_edited', False),
                'is_deleted': False,
                'read_at': mdata.get('read_at'),
                'edited_at': mdata.get('edited_at'),
            })

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
    """Edit message within 1-hour window."""
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

    mref.update({'message': new_message, 'is_edited': True, 'edited_at': now_ms})
    return True, None


def delete_message(sender_uid, msg_uid):
    """Soft-delete message within 1-hour window. Content replaced with placeholder."""
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
    return True, None


def mark_read(user_uid, other_user_uid):
    """Mark all unread messages from other_user as read, storing read_at."""
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
    """Get chat list for a user with unread counts and optional search."""
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

        rooms.append({
            'other_uid': other_uid,
            'last_message': last_msg,
            'last_timestamp': meta.get('last_timestamp', 0),
            'last_sender_uid': meta.get('last_sender_uid', ''),
            'unread_count': unread,
        })
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
    """Get unread count for a specific conversation pair."""
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
    """Get all admin users with AVAILABLE or BUSY status for teacher chat list."""
    try:
        from accounts.models import CustomUser
    except Exception:
        return []
    admins = CustomUser.objects.filter(
        user_type='ADMIN', status='ACTIVE'
    ).only('uid', 'chat_display_name', 'chat_status', 'image', 'chat_display')
    result = []
    for a in admins:
        is_online = a.chat_status == 'AVAILABLE' or a.chat_status == 'BUSY'
        result.append({
            'uid': str(a.uid),
            'display_name': a.chat_display,
            'status': a.chat_status,
            'avatar': a.avatar_url,
            'is_online': is_online,
        })
    return result


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
