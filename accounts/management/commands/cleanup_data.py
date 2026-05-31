from django.core.management.base import BaseCommand
from accounts.utils.firebase_notifications import cleanup_old_notifications
from accounts.utils.firebase_chat import cleanup_old_messages


class Command(BaseCommand):
    help = 'Cleans up old data from Firebase: notifications (7 days), chat messages (30 days)'

    def handle(self, *args, **options):
        self.stdout.write('Starting Firebase cleanup...')

        notif_count = cleanup_old_notifications(days=7)
        self.stdout.write(self.style.SUCCESS(f'Cleaned up notifications older than 7 days.'))

        chat_count = cleanup_old_messages(days=30)
        self.stdout.write(self.style.SUCCESS(f'Cleaned up chat messages older than 30 days.'))

        self.stdout.write(self.style.SUCCESS('Firebase cleanup complete.'))
