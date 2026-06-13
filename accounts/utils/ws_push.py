import json
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def _channel_layer():
    try:
        return get_channel_layer()
    except Exception:
        return None


def push_to_user(user_uid, message_dict):
    layer = _channel_layer()
    if not layer:
        return
    try:
        async_to_sync(layer.group_send)(
            f'user_{user_uid}',
            message_dict,
        )
    except Exception as e:
        logger.warning(f'WebSocket push to user {user_uid} failed: {e}')


def push_to_group(group_name, message_dict):
    layer = _channel_layer()
    if not layer:
        return
    try:
        async_to_sync(layer.group_send)(
            group_name,
            message_dict,
        )
    except Exception as e:
        logger.warning(f'WebSocket push to group {group_name} failed: {e}')


def push_chat_message(sender_uid, receiver_uid, message_uid, sender_name, message, raw_ts):
    payload = {
        'type': 'chat_message',
        'message_uid': message_uid,
        'sender_uid': sender_uid,
        'sender_name': sender_name,
        'message': message,
        'raw_ts': raw_ts,
    }
    push_to_user(receiver_uid, payload)
    push_to_user(sender_uid, payload)


def push_notification(user_uid, title, message, notif_type='info', count=0, url=''):
    payload = {
        'type': 'notification',
        'title': title,
        'message': message,
        'notif_type': notif_type,
        'count': count,
        'url': url,
    }
    push_to_user(user_uid, payload)


def push_pending_counts(user_type, counts_dict):
    payload = {
        'type': 'pending_counts',
        'counts': counts_dict,
    }
    push_to_group(f'type_{user_type.lower()}', payload)
