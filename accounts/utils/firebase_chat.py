import os
import json
import time
import uuid
import threading
from datetime import datetime, timezone
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
                cred = credentials.Certificate(json_path)
            except Exception:
                return None
        else:
            return None
        _firebase_app = firebase_admin.initialize_app(
            cred, {'databaseURL': db_url}, name='chat'
        )
    return _firebase_app


def get_room_name(uid1, uid2):
    parts = sorted([str(uid1), str(uid2)])
    return f"{parts[0]}_{parts[1]}"


def send_message(sender, receiver_uid, message_text, sender_name):
    app = _get_app()
    if app is None:
        return None
    msg_uid = str(uuid.uuid4())
    now_ms = int(time.time() * 1000)
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
    })

    meta_ref = db.reference(f'/chat_rooms/{room}/metadata')
    meta_ref.update({
        'participants': {str(sender.uid): True, str(receiver_uid): True},
        'last_message': message_text,
        'last_timestamp': now_ms,
        'last_sender_uid': str(sender.uid),
    })

    return msg_uid, now_ms


def get_messages(user_uid, other_user_uid, limit=500):
    app = _get_app()
    if app is None:
        return []
    room = get_room_name(user_uid, other_user_uid)
    ref = db.reference(f'/chat_rooms/{room}/messages')
    data = ref.get()
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
            'is_deleted': False,
        })
    msgs.sort(key=lambda x: x['timestamp'])
    return msgs[-limit:]


def edit_message(sender_uid, msg_uid, new_message):
    app = _get_app()
    if app is None:
        return False
    rooms_ref = db.reference('/chat_rooms')
    data = rooms_ref.get(shallow=True)
    if not data:
        return False
    for room in data:
        msg_ref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}')
        mdata = msg_ref.get()
        if mdata and mdata.get('sender_uid') == str(sender_uid):
            msg_ref.update({'message': new_message, 'is_edited': True})
            return True
    return False


def delete_message(sender_uid, msg_uid):
    app = _get_app()
    if app is None:
        return False
    rooms_ref = db.reference('/chat_rooms')
    data = rooms_ref.get(shallow=True)
    if not data:
        return False
    for room in data:
        msg_ref = db.reference(f'/chat_rooms/{room}/messages/{msg_uid}')
        mdata = msg_ref.get()
        if mdata and mdata.get('sender_uid') == str(sender_uid):
            msg_ref.update({'is_deleted': True})
            return True
    return False


def get_chat_list(user_uid):
    app = _get_app()
    if app is None:
        return []
    ref = db.reference('/chat_rooms')
    data = ref.get()
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
        other_uid = others[0]
        msgs = room_data.get('messages', {})
        unread = 0
        for m in msgs.values():
            if (m.get('sender_uid') == other_uid
                    and not m.get('is_read', False)
                    and not m.get('is_deleted', False)):
                unread += 1
        rooms.append({
            'other_uid': other_uid,
            'last_message': meta.get('last_message', ''),
            'last_timestamp': meta.get('last_timestamp', 0),
            'last_sender_uid': meta.get('last_sender_uid', ''),
            'unread_count': unread,
        })
    rooms.sort(key=lambda x: x.get('last_timestamp', 0), reverse=True)
    return rooms


def mark_read(user_uid, other_user_uid):
    app = _get_app()
    if app is None:
        return
    room = get_room_name(user_uid, other_user_uid)
    ref = db.reference(f'/chat_rooms/{room}/messages')
    data = ref.get()
    if not data:
        return
    updates = {}
    for mid, mdata in data.items():
        if (mdata.get('sender_uid') == str(other_user_uid)
                and not mdata.get('is_read', False)):
            updates[f'{mid}/is_read'] = True
    if updates:
        ref.update(updates)


def get_unread_count(user_uid):
    app = _get_app()
    if app is None:
        return 0
    ref = db.reference('/chat_rooms')
    data = ref.get()
    if not data:
        return 0
    user_str = str(user_uid)
    total = 0
    for room_data in data.values():
        meta = room_data.get('metadata', {})
        participants = meta.get('participants', {})
        if user_str not in participants:
            continue
        msgs = room_data.get('messages', {})
        for m in msgs.values():
            if (m.get('sender_uid') != user_str
                    and not m.get('is_read', False)
                    and not m.get('is_deleted', False)):
                total += 1
    return total


def cleanup_old_messages(days=7):
    app = _get_app()
    if app is None:
        return 0
    cutoff = int(time.time() * 1000) - (days * 24 * 60 * 60 * 1000)
    ref = db.reference('/chat_rooms')
    data = ref.get()
    if not data:
        return 0
    deleted = 0
    for room, room_data in data.items():
        msgs = room_data.get('messages', {})
        for mid, mdata in msgs.items():
            if mdata.get('timestamp', 0) < cutoff:
                db.reference(f'/chat_rooms/{room}/messages/{mid}').delete()
                deleted += 1
    return deleted
