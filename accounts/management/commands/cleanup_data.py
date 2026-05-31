from django.core.management.base import BaseCommand
from accounts.models import ChatMessage, Notification
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Validates data integrity (Deletions DISABLED for Zero-Delete Policy)'

    def handle(self, *args, **options):
        self.stdout.write('Starting database integrity scan (Zero-Delete Mode)...')

        # 1. Check old Chat Messages
        cleanup_date = timezone.now() - timedelta(days=60)
        old_messages = ChatMessage.objects.filter(timestamp__lt=cleanup_date)
        msg_count = old_messages.count()
        
        # old_messages.delete() # DISABLED
        self.stdout.write(self.style.WARNING(f'Found {msg_count} old chat messages. PRESERVED per Zero-Delete Policy.'))

        # 2. Check old Notifications
        old_notifs = Notification.objects.filter(created_at__lt=cleanup_date)
        notif_count = old_notifs.count()
        
        # old_notifs.delete() # DISABLED
        self.stdout.write(self.style.WARNING(f'Found {notif_count} old notifications. PRESERVED per Zero-Delete Policy.'))

        self.stdout.write(self.style.SUCCESS('Data integrity scan complete. No data was removed.'))


