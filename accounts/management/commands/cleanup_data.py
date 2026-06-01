from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import ChatMessage
from accounts.utils.notification_helper import cleanup_old_notifications as cleanup_notifs


class Command(BaseCommand):
    help = 'Cleans up old data: notifications (7 days), chat messages (7 days)'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup...')

        # Clean up notifications
        try:
            cleanup_notifs()
            self.stdout.write(self.style.SUCCESS('Cleaned up notifications older than 7 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Notification cleanup error: {e}'))

        # Clean up chat messages older than 7 days (hard delete)
        cutoff = timezone.now() - timedelta(days=7)
        deleted_count, _ = ChatMessage.objects.filter(timestamp__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted_count} chat messages older than 7 days.'))

        self.stdout.write(self.style.SUCCESS('Cleanup complete.'))
