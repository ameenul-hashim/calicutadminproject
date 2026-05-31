import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .utils.firebase_chat import (
    send_message as fb_send,
    edit_message as fb_edit,
    delete_message as fb_delete,
)


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
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
            sender_name = 'Administrator' if getattr(sender, 'is_staff', False) else sender.username

            msg_uid, now_ms = await self.save_message(sender, receiver_uid, message, sender_name)

            from datetime import datetime
            ts_str = datetime.fromtimestamp(now_ms / 1000).strftime('%I:%M %p') if now_ms else ''

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'action': 'send',
                    'message_uid': str(msg_uid) if msg_uid else '',
                    'message': message,
                    'sender_uid': str(sender.uid),
                    'sender_name': sender_name,
                    'timestamp': ts_str,
                }
            )
        elif action == 'edit':
            message_uid = data['message_uid']
            new_message = data['message']
            success = await self.edit_message_async(sender, message_uid, new_message)
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
            success = await self.delete_message_async(sender, message_uid)
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
                'timestamp': event['timestamp']
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

    async def save_message(self, sender, receiver_uid, message_text, sender_name):
        return fb_send(sender, receiver_uid, message_text, sender_name) or (None, 0)

    async def edit_message_async(self, sender, message_uid, new_message):
        return fb_edit(str(sender.uid), message_uid, new_message)

    async def delete_message_async(self, sender, message_uid):
        return fb_delete(str(sender.uid), message_uid)
