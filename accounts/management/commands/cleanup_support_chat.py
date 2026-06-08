import logging
from django.core.management.base import BaseCommand
from accounts.utils.firebase_chat import cleanup_old_messages

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete chat messages older than 7 days (Firebase RTDB retention)'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Retention period in days')

    def handle(self, *args, **options):
        days = options['days']
        self.stdout.write(f'Cleaning up messages older than {days} days...')
        deleted = cleanup_old_messages(days=days)
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} old message(s)'))
