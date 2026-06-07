import json
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils.html import escape
from accounts.utils.firebase_chat import send_message, edit_message, delete_message, mark_read
from accounts.utils.firebase_chat import MAX_MESSAGE_LENGTH, RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW


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
            message = data.get('message', '').strip()
            if len(message) > MAX_MESSAGE_LENGTH:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'error': f'Message too long (max {MAX_MESSAGE_LENGTH} characters)',
                }))
                return
            if not message:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'error': 'Message cannot be empty',
                }))
                return

            message = escape(message)
            receiver_uid = data['receiver_uid']
            sender_name = sender.chat_display if is_admin_user else (sender.full_name or sender.username)

            # Check for attachment metadata in send
            attachment = data.get('attachment')

            result = await sync_to_async(send_message)(sender, receiver_uid, message, sender_name, attachment=attachment)
            if result is None:
                return
            if isinstance(result, tuple) and result[1] == 'RATE_LIMITED':
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'error': f'Rate limited — max {RATE_LIMIT_MESSAGES} messages per {RATE_LIMIT_WINDOW}s',
                }))
                return
            msg_uid, now_ms = result
            ts_str = datetime.fromtimestamp(now_ms / 1000).strftime('%I:%M %p')

            event = {
                'type': 'chat_message',
                'action': 'send',
                'message_uid': msg_uid,
                'message': message,
                'sender_uid': str(sender.uid),
                'sender_name': sender_name,
                'timestamp': ts_str,
                'raw_ts': now_ms,
                'sender_status': sender.chat_status if is_admin_user else 'AVAILABLE',
            }
            if attachment:
                event['attachment'] = attachment

            await self.channel_layer.group_send(
                self.room_group_name,
                event
            )

        elif action == 'edit':
            message_uid = data['message_uid']
            new_message = data.get('message', '').strip()
            if len(new_message) > MAX_MESSAGE_LENGTH:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'error': f'Message too long (max {MAX_MESSAGE_LENGTH} characters)',
                }))
                return
            if not new_message:
                return
            new_message = escape(new_message)
            success, error = await sync_to_async(edit_message)(str(sender.uid), message_uid, new_message)
            if success:
                now_ms = int(datetime.now().timestamp() * 1000)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'edit',
                        'message_uid': message_uid,
                        'message': new_message,
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'error': error or 'Edit failed',
                }))

        elif action == 'delete':
            message_uid = data['message_uid']
            success, error = await sync_to_async(delete_message)(str(sender.uid), message_uid)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'delete',
                        'message_uid': message_uid,
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'error': error or 'Delete failed',
                }))

        elif action == 'read':
            other_uid = data.get('other_uid')
            if other_uid:
                await sync_to_async(mark_read)(str(sender.uid), str(other_uid))
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'read',
                        'reader_uid': str(sender.uid),
                    }
                )

        elif action == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'action': 'typing',
                    'sender_uid': str(sender.uid),
                    'is_typing': data.get('is_typing', False),
                }
            )

        elif action == 'status_change':
            """Admin changes conversation status."""
            if not is_admin_user:
                await self.send(text_data=json.dumps({
                    'action': 'error', 'error': 'Access denied',
                }))
                return
            new_status = data.get('status', '')
            other_uid = data.get('other_uid', '')
            from accounts.utils.firebase_chat import set_conversation_status
            success, _ = await sync_to_async(set_conversation_status)(str(sender.uid), other_uid, new_status)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'status_change',
                        'status': new_status,
                        'changed_by': str(sender.uid),
                    }
                )

    async def chat_message(self, event):
        action = event.get('action', 'send')

        if action == 'send':
            msg = {
                'action': 'send',
                'message_uid': event['message_uid'],
                'message': event['message'],
                'sender_uid': event['sender_uid'],
                'sender_name': event['sender_name'],
                'timestamp': event['timestamp'],
                'raw_ts': event.get('raw_ts', 0),
                'sender_status': event.get('sender_status', 'AVAILABLE'),
            }
            if event.get('attachment'):
                msg['attachment'] = event['attachment']
            await self.send(text_data=json.dumps(msg))
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
        elif action == 'read':
            await self.send(text_data=json.dumps({
                'action': 'read',
                'reader_uid': event['reader_uid'],
            }))
        elif action == 'typing':
            await self.send(text_data=json.dumps({
                'action': 'typing',
                'sender_uid': event['sender_uid'],
                'is_typing': event['is_typing'],
            }))
        elif action == 'status_change':
            await self.send(text_data=json.dumps({
                'action': 'status_change',
                'status': event['status'],
                'changed_by': event.get('changed_by', ''),
            }))
