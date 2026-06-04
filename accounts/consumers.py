import json
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from accounts.models import CustomUser, ChatMessage


@sync_to_async
def get_user_by_uid(uid):
    try:
        return CustomUser.objects.get(uid=uid)
    except CustomUser.DoesNotExist:
        return None


@sync_to_async
def _orm_save_message(sender, receiver_uid, message_text, sender_name):
    try:
        receiver = CustomUser.objects.get(uid=receiver_uid)
        msg = ChatMessage.objects.create(
            sender=sender,
            receiver=receiver,
            message=message_text,
        )
        return str(msg.uid), int(msg.timestamp.timestamp() * 1000)
    except CustomUser.DoesNotExist:
        return None, 0


@sync_to_async
def _orm_edit_message(sender, msg_uid, new_message):
    try:
        msg = ChatMessage.objects.get(uid=msg_uid, sender=sender, is_deleted=False)
        msg.message = new_message
        msg.is_edited = True
        msg.save(update_fields=['message', 'is_edited'])
        return True
    except ChatMessage.DoesNotExist:
        return False


@sync_to_async
def _orm_delete_message(sender, msg_uid):
    try:
        msg = ChatMessage.objects.get(uid=msg_uid, sender=sender, is_deleted=False)
        msg.is_deleted = True
        msg.save(update_fields=['is_deleted'])
        return True
    except ChatMessage.DoesNotExist:
        return False


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close()
            return
        is_teacher = user.user_type == 'TEACHER'
        is_admin = user.is_superuser or user.is_staff or user.user_type == 'ADMIN'
        if not (is_teacher or is_admin):
            await self.close()
            return

        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action', 'send')
        sender = self.scope['user']

        if action == 'send':
            message = data['message']
            receiver_uid = data['receiver_uid']
            sender_name = 'Administrator' if getattr(sender, 'is_staff', False) else (
                sender.full_name or sender.username
            )

            msg_uid, now_ms = await _orm_save_message(
                sender, receiver_uid, message, sender_name
            )
            if msg_uid and now_ms:
                ts_str = datetime.fromtimestamp(now_ms / 1000).strftime('%I:%M %p')

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'send',
                        'message_uid': msg_uid,
                        'message': message,
                        'sender_uid': str(sender.uid),
                        'sender_name': sender_name,
                        'timestamp': ts_str,
                        'raw_ts': now_ms,
                    }
                )
        elif action == 'edit':
            message_uid = data['message_uid']
            new_message = data['message']
            success = await _orm_edit_message(sender, message_uid, new_message)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'edit',
                        'message_uid': message_uid,
                        'message': new_message,
                    }
                )
        elif action == 'delete':
            message_uid = data['message_uid']
            success = await _orm_delete_message(sender, message_uid)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'delete',
                        'message_uid': message_uid,
                    }
                )

    async def chat_message(self, event):
        action = event.get('action', 'send')

        if action == 'send':
            await self.send(text_data=json.dumps({
                'action': 'send',
                'message_uid': event['message_uid'],
                'message': event['message'],
                'sender_uid': event['sender_uid'],
                'sender_name': event['sender_name'],
                'timestamp': event['timestamp'],
                'raw_ts': event.get('raw_ts', 0),
            }))
        elif action == 'edit':
            await self.send(text_data=json.dumps({
                'action': 'edit',
                'message_uid': event['message_uid'],
                'message': event['message'],
            }))
        elif action == 'delete':
            await self.send(text_data=json.dumps({
                'action': 'delete',
                'message_uid': event['message_uid'],
            }))
