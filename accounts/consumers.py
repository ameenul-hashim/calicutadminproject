import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatMessage, CustomUser
from django.utils import timezone

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action', 'send')
        sender = self.scope['user']

        if action == 'send':
            message = data['message']
            receiver_uid = data['receiver_uid']
            
            # Save message to database
            msg = await self.save_message(sender, receiver_uid, message)

            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'action': 'send',
                    'message_uid': str(msg.uid),
                    'message': message,
                    'sender_uid': str(sender.uid),
                    'sender_name': 'Administrator' if getattr(sender, 'is_staff', False) else sender.username,
                    'timestamp': msg.timestamp.strftime('%I:%M %p')
                }
            )
        elif action == 'edit':
            message_uid = data['message_uid']
            new_message = data['message']
            msg = await self.edit_message(sender, message_uid, new_message)
            if msg:
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
            deleted = await self.delete_message(sender, message_uid)
            if deleted:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'action': 'delete',
                        'message_uid': message_uid,
                    }
                )

    # Receive message from room group
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

    @database_sync_to_async
    def save_message(self, sender, receiver_uid, message):
        receiver = CustomUser.objects.get(uid=receiver_uid)
        return ChatMessage.objects.create(sender=sender, receiver=receiver, message=message)

    @database_sync_to_async
    def edit_message(self, sender, message_uid, new_message):
        try:
            msg = ChatMessage.objects.get(uid=message_uid, sender=sender)
            msg.message = new_message
            msg.is_edited = True
            msg.save()
            return msg
        except ChatMessage.DoesNotExist:
            return None

    @database_sync_to_async
    def delete_message(self, sender, message_uid):
        try:
            msg = ChatMessage.objects.get(uid=message_uid, sender=sender)
            msg.is_deleted = True
            msg.save()
            return True
        except ChatMessage.DoesNotExist:
            return False


