import uuid
import re
import time
import logging
from firebase_admin import db

from .firebase_db import _get_app as _get_firebase_app

logger = logging.getLogger(__name__)

EDIT_WINDOW_SECONDS = 3600
DELETE_WINDOW_SECONDS = 3600
RETENTION_DAYS = 30
PAGE_SIZE = 25
MAX_MESSAGE_LENGTH = 2000


def _get_app():
    return _get_firebase_app()


def _now_ms():
    return int(time.time() * 1000)


def _sanitize_text(text):
    text = re.sub(r'<[^>]*>', '', text)
    return text[:MAX_MESSAGE_LENGTH]


def _resolve_admin_teacher(uid1, uid2):
    from accounts.models import CustomUser
    u1 = CustomUser.objects.filter(uid=uid1).only('user_type').first()
    u2 = CustomUser.objects.filter(uid=uid2).only('user_type').first()
    admin = str(uid1) if (u1 and u1.user_type == 'ADMIN') else str(uid2)
    teacher = str(uid2) if admin == str(uid1) else str(uid1)
    return admin, teacher


def _conversation_path(admin_uid, teacher_uid):
    return f'/support_chat/{admin_uid}/{teacher_uid}'


def get_admin_uid_by_name(display_name):
    from accounts.models import CustomUser
    admin = CustomUser.objects.filter(
        user_type='ADMIN', status='ACTIVE', full_name=display_name
    ).only('uid').first()
    if admin:
        return str(admin.uid)
    admin = CustomUser.objects.filter(
        user_type='ADMIN', status='ACTIVE', chat_display=display_name
    ).only('uid').first()
    if admin:
        return str(admin.uid)
    return None


def _resolve_sender_name(sender_uid):
    from accounts.models import CustomUser
    u = CustomUser.objects.filter(uid=sender_uid).only('user_type', 'full_name', 'username', 'chat_display_name').first()
    return u.chat_display if u else 'Unknown'


def send_message(sender_uid, receiver_uid, message_text):
    app = _get_app()
    if app is None:
        return None, 0
    msg_uid = str(uuid.uuid4())
    now_ms = _now_ms()
    sanitized = _sanitize_text(message_text)
    if not sanitized:
        return None, 0
    admin_uid, teacher_uid = _resolve_admin_teacher(sender_uid, receiver_uid)
    sender_name = _resolve_sender_name(sender_uid)
    path = _conversation_path(admin_uid, teacher_uid)
    msg_ref = db.reference(f'{path}/messages/{msg_uid}', app=app)
    msg_ref.set({
        'sender_uid': str(sender_uid),
        'receiver_uid': str(receiver_uid),
        'sender_name': sender_name,
        'message': sanitized,
        'created_at': now_ms,
        'is_read': False,
        'deleted': False,
        'edited_at': None,
    })
    return msg_uid, now_ms


def get_messages(user_uid, other_uid, limit=PAGE_SIZE, offset=0, search=None):
    app = _get_app()
    if app is None:
        return [], False
    admin_uid, teacher_uid = _resolve_admin_teacher(user_uid, other_uid)
    path = _conversation_path(admin_uid, teacher_uid)
    data = db.reference(f'{path}/messages', app=app).get()
    if not data:
        return [], False
    msgs = []
    current_uid = str(user_uid)
    for mid, mdata in data.items():
        sender_uid = mdata.get('sender_uid')
        # Skip globally deleted messages (hidden from both parties)
        if mdata.get('deleted', False):
            continue
        # Skip per-user soft-deleted (legacy cleanup)
        if mdata.get('deleted_by_sender', False) or mdata.get('deleted_by_receiver', False):
            continue
        msg_text = mdata.get('message', '')
        if search and search.lower() not in msg_text.lower():
            continue
        msgs.append({
            'uid': mid,
            'sender_uid': sender_uid,
            'message': msg_text,
            'created_at': mdata.get('created_at', 0),
            'is_read': mdata.get('is_read', False),
            'deleted': False,
            'edited_at': mdata.get('edited_at'),
        })
    msgs.sort(key=lambda x: x['created_at'])
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


def _find_conversation_path_by_msg(user_uid, msg_uid):
    app = _get_app()
    if app is None:
        return None
    from accounts.models import CustomUser
    user_str = str(user_uid)
    user = CustomUser.objects.filter(uid=user_uid).only('user_type').first()
    if not user:
        return None
    if user.user_type == 'ADMIN':
        teachers = db.reference(f'/support_chat/{user_str}', app=app).get(shallow=True)
        if teachers:
            for teacher_uid in teachers:
                if db.reference(
                    f'/support_chat/{user_str}/{teacher_uid}/messages/{msg_uid}', app=app
                ).get():
                    return f'/support_chat/{user_str}/{teacher_uid}'
    else:
        admins = CustomUser.objects.filter(user_type='ADMIN', status='ACTIVE').only('uid')
        for admin in admins:
            if db.reference(
                f'/support_chat/{admin.uid}/{user_str}/messages/{msg_uid}', app=app
            ).get():
                return f'/support_chat/{admin.uid}/{user_str}'
    return None


def edit_message(user_uid, msg_uid, new_message):
    app = _get_app()
    if app is None:
        return False, 'Firebase unavailable'
    now_ms = _now_ms()
    path = _find_conversation_path_by_msg(user_uid, msg_uid)
    if not path:
        return False, 'Message not found'
    mref = db.reference(f'{path}/messages/{msg_uid}', app=app)
    mdata = mref.get()
    if not mdata:
        return False, 'Message not found'
    if mdata.get('sender_uid') != str(user_uid):
        return False, 'Cannot edit another user message'
    if mdata.get('deleted', False):
        return False, 'Message already deleted'
    msg_time = mdata.get('created_at', 0)
    if now_ms - msg_time > EDIT_WINDOW_SECONDS * 1000:
        return False, 'Edit window expired (1 hour)'
    sanitized = _sanitize_text(new_message)
    mref.update({'message': sanitized, 'edited_at': now_ms})
    return True, None


def delete_message(user_uid, msg_uid):
    app = _get_app()
    if app is None:
        return False, 'Firebase unavailable'
    now_ms = _now_ms()
    path = _find_conversation_path_by_msg(user_uid, msg_uid)
    if not path:
        return False, 'Message not found'
    mref = db.reference(f'{path}/messages/{msg_uid}', app=app)
    mdata = mref.get()
    if not mdata:
        return False, 'Message not found'
    if mdata.get('sender_uid') != str(user_uid):
        return False, 'Cannot delete another user message'
    if mdata.get('deleted', False):
        return False, 'Message already deleted'
    msg_time = mdata.get('created_at', 0)
    if now_ms - msg_time > DELETE_WINDOW_SECONDS * 1000:
        return False, 'Delete window expired (1 hour)'
    # Hard delete: remove from both sender and receiver view
    mref.update({'deleted': True, 'deleted_at': now_ms})
    return True, None


def mark_read(user_uid, other_uid):
    app = _get_app()
    if app is None:
        return
    now_ms = _now_ms()
    admin_uid, teacher_uid = _resolve_admin_teacher(user_uid, other_uid)
    path = _conversation_path(admin_uid, teacher_uid)
    ref = db.reference(f'{path}/messages', app=app)
    data = ref.get()
    if not data:
        return
    updates = {}
    for mid, mdata in data.items():
        if mdata.get('sender_uid') == str(other_uid) and not mdata.get('is_read', False):
            updates[f'{mid}/is_read'] = True
    if updates:
        ref.update(updates)


def get_chat_list(user_uid, user_type):
    app = _get_app()
    if app is None:
        return []
    user_str = str(user_uid)
    result = []
    if user_type == 'TEACHER':
        from accounts.models import CustomUser
        admins = CustomUser.objects.filter(user_type='ADMIN', status='ACTIVE').only('uid', 'full_name', 'chat_display_name')
        for admin in admins:
            admin_str = str(admin.uid)
            path = _conversation_path(admin_str, user_str)
            msgs_data = db.reference(f'{path}/messages', app=app).get()
            if not msgs_data:
                continue
            msgs = []
            unread = 0
            for mid, mdata in msgs_data.items():
                sender_uid = mdata.get('sender_uid')
                # Skip globally/per-user deleted messages
                if mdata.get('deleted', False) or mdata.get('deleted_by_sender', False) or mdata.get('deleted_by_receiver', False):
                    continue
                created_at = mdata.get('created_at', 0)
                msg_text = mdata.get('message', '')
                msgs.append({
                    'uid': mid,
                    'created_at': created_at,
                    'sender_uid': sender_uid,
                    'message': msg_text,
                })
                if sender_uid == admin_str and not mdata.get('is_read', False):
                    unread += 1
            msgs.sort(key=lambda x: x['created_at'], reverse=True)
            last_msg = msgs[0] if msgs else None
            result.append({
                'other_uid': admin_str,
                'other_name': admin.chat_display,
                'last_message': last_msg['message'] if last_msg else '',
                'last_timestamp': last_msg['created_at'] if last_msg else 0,
                'last_sender_uid': last_msg['sender_uid'] if last_msg else '',
                'unread_count': unread,
            })
    else:
        teachers = db.reference(f'/support_chat/{user_str}', app=app).get(shallow=True)
        if not teachers:
            return []
        from accounts.models import CustomUser
        for teacher_uid in teachers:
            path = _conversation_path(user_str, teacher_uid)
            msgs_data = db.reference(f'{path}/messages', app=app).get()
            if not msgs_data:
                continue
            msgs = []
            unread = 0
            for mid, mdata in msgs_data.items():
                sender_uid = mdata.get('sender_uid')
                # Skip globally/per-user deleted messages
                if mdata.get('deleted', False) or mdata.get('deleted_by_sender', False) or mdata.get('deleted_by_receiver', False):
                    continue
                created_at = mdata.get('created_at', 0)
                msg_text = mdata.get('message', '')
                msgs.append({
                    'uid': mid,
                    'created_at': created_at,
                    'sender_uid': sender_uid,
                    'message': msg_text,
                })
                if sender_uid == teacher_uid and not mdata.get('is_read', False):
                    unread += 1
            msgs.sort(key=lambda x: x['created_at'], reverse=True)
            last_msg = msgs[0] if msgs else None
            teacher_user = CustomUser.objects.filter(uid=teacher_uid).only('full_name').first()
            result.append({
                'other_uid': teacher_uid,
                'other_name': teacher_user.full_name if teacher_user else 'Unknown',
                'last_message': last_msg['message'] if last_msg else '',
                'last_timestamp': last_msg['created_at'] if last_msg else 0,
                'last_sender_uid': last_msg['sender_uid'] if last_msg else '',
                'unread_count': unread,
            })
    result.sort(key=lambda x: x.get('last_timestamp', 0), reverse=True)
    return result


def get_unread_count(user_uid, user_type):
    app = _get_app()
    if app is None:
        return 0
    user_str = str(user_uid)
    total = 0
    if user_type == 'TEACHER':
        from accounts.models import CustomUser
        admins = CustomUser.objects.filter(user_type='ADMIN', status='ACTIVE').only('uid')
        for admin in admins:
            path = _conversation_path(str(admin.uid), user_str)
            msgs_data = db.reference(f'{path}/messages', app=app).get()
            if not msgs_data:
                continue
            for mdata in msgs_data.values():
                sender_uid = mdata.get('sender_uid')
                if mdata.get('deleted', False) or mdata.get('deleted_by_sender', False) or mdata.get('deleted_by_receiver', False):
                    continue
                if sender_uid == str(admin.uid) and not mdata.get('is_read', False):
                    total += 1
    else:
        teachers = db.reference(f'/support_chat/{user_str}', app=app).get(shallow=True)
        if not teachers:
            return 0
        for teacher_uid in teachers:
            path = _conversation_path(user_str, teacher_uid)
            msgs_data = db.reference(f'{path}/messages', app=app).get()
            if not msgs_data:
                continue
            for mdata in msgs_data.values():
                sender_uid = mdata.get('sender_uid')
                if mdata.get('deleted', False) or mdata.get('deleted_by_sender', False) or mdata.get('deleted_by_receiver', False):
                    continue
                if sender_uid == teacher_uid and not mdata.get('is_read', False):
                    total += 1
    return total


def cleanup_old_messages(days=RETENTION_DAYS):
    app = _get_app()
    if app is None:
        return 0
    cutoff = _now_ms() - (days * 24 * 60 * 60 * 1000)
    data = db.reference('/support_chat', app=app).get()
    if not data:
        return 0
    deleted = 0
    for admin_uid, teachers in data.items():
        for teacher_uid, conv in teachers.items():
            msgs = conv.get('messages', {})
            if not msgs:
                continue
            to_delete = []
            for msg_uid, mdata in msgs.items():
                if mdata.get('created_at', 0) < cutoff:
                    to_delete.append(msg_uid)
            for msg_uid in to_delete:
                db.reference(f'/support_chat/{admin_uid}/{teacher_uid}/messages/{msg_uid}', app=app).delete()
                deleted += 1
    return deleted
