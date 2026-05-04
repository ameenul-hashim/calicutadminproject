from django.core.management.base import BaseCommand
from accounts.models import ChatMessage, Notification
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Optimizes database performance by cleaning up old data'

    def handle(self, *args, **options):
        self.stdout.write('Starting database cleanup...')

        # 1. Clean up old Chat Messages
        # Keep only last 30 days of chat messages OR limit per room (complex without room ID)
        # We will keep last 60 days to be safe.
        cleanup_date = timezone.now() - timedelta(days=60)
        old_messages = ChatMessage.objects.filter(timestamp__lt=cleanup_date)
        msg_count = old_messages.count()
        old_messages.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {msg_count} old chat messages.'))

        # 2. Clean up old Notifications (redundant as we have limit_notifications, but good for safety)
        old_notifs = Notification.objects.filter(created_at__lt=cleanup_date)
        notif_count = old_notifs.count()
        old_notifs.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {notif_count} old notifications.'))

        self.stdout.write(self.style.SUCCESS('Database optimization cleanup complete!'))
