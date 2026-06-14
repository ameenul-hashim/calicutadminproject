import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.user_group = f'user_{self.user.uid}'
        self.type_group = f'type_{self.user.user_type.lower()}'

        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.channel_layer.group_add(self.type_group, self.channel_name)

        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'uid': str(self.user.uid),
            'user_type': self.user.user_type,
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, 'type_group'):
            await self.channel_layer.group_discard(self.type_group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            msg_type = data.get('type', '')

            if msg_type == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
            elif msg_type == 'mark_read':
                await self._handle_mark_read(data)
        except json.JSONDecodeError:
            pass

    async def _handle_mark_read(self, data):
        chat_partner_uid = data.get('partner_uid')
        if chat_partner_uid:
            from accounts.utils.firebase_chat import mark_read as fb_mark_read
            try:
                fb_mark_read(str(self.user.uid), chat_partner_uid)
            except Exception:
                pass

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_uid': event.get('message_uid'),
            'sender_uid': event.get('sender_uid'),
            'sender_name': event.get('sender_name'),
            'message': event.get('message'),
            'raw_ts': event.get('raw_ts'),
            'is_me': str(self.user.uid) == event.get('sender_uid'),
        }))

    async def notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'title': event.get('title', ''),
            'message': event.get('message', ''),
            'notif_type': event.get('notif_type', 'info'),
            'count': event.get('count', 0),
            'url': event.get('url', ''),
        }))

    async def pending_counts(self, event):
        await self.send(text_data=json.dumps({
            'type': 'pending_counts',
            'counts': event.get('counts', {}),
        }))

    async def chat_read_receipt(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_read_receipt',
            'reader_uid': event.get('reader_uid'),
            'message_uid': event.get('message_uid'),
        }))
