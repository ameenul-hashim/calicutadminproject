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
        message = data['message']
        sender = self.scope['user']
        receiver_uid = data['receiver_uid']

        # Save message to database
        await self.save_message(sender, receiver_uid, message)

        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender_uid': str(sender.uid),
                'sender_name': sender.username,
                'timestamp': timezone.now().strftime('%H:%M')
            }
        )

    # Receive message from room group
    async def chat_message(self, event):
        message = event['message']
        sender_uid = event['sender_uid']
        sender_name = event['sender_name']
        timestamp = event['timestamp']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'sender_uid': sender_uid,
            'sender_name': sender_name,
            'timestamp': timestamp
        }))

    @database_sync_to_async
    def save_message(self, sender, receiver_uid, message):
        receiver = CustomUser.objects.get(uid=receiver_uid)
        return ChatMessage.objects.create(sender=sender, receiver=receiver, message=message)
