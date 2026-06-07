import json
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils.html import escape
from accounts.utils.firebase_chat import send_message, edit_message, delete_message


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
        is_admin_user = sender.is_superuser or sender.is_staff or sender.user_type == 'ADMIN'

        if action == 'send':
            message = escape(data['message'])
            receiver_uid = data['receiver_uid']
            sender_name = 'Support Team' if is_admin_user else (sender.full_name or sender.username)

            result = await sync_to_async(send_message)(sender, receiver_uid, message, sender_name)
            if result is None:
                return
            msg_uid, now_ms = result
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
            new_message = escape(data['message'])
            success = await sync_to_async(edit_message)(str(sender.uid), message_uid, new_message)
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
            success = await sync_to_async(delete_message)(str(sender.uid), message_uid)
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
