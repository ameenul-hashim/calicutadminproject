from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.utils.notification_helper import cleanup_old_notifications as cleanup_notifs
from accounts.utils.firebase_db import chat_cleanup, login_history_cleanup, admin_log_cleanup
from accounts.models import EmailOTP


class Command(BaseCommand):
    help = 'Cleans up old data in Firebase RTDB and PostgreSQL'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup...')

        # --- Firebase RTDB cleanups (7 days) ---

        try:
            cleanup_notifs()
            self.stdout.write(self.style.SUCCESS('Cleaned up notifications older than 7 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Notification cleanup error: {e}'))

        try:
            deleted = chat_cleanup(7)
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted} chat messages older than 7 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Chat cleanup error: {e}'))

        try:
            deleted = login_history_cleanup(7)
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted} login history entries older than 7 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Login history cleanup error: {e}'))

        try:
            deleted = admin_log_cleanup(7)
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted} admin activity log entries older than 7 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Admin log cleanup error: {e}'))

        # --- PostgreSQL cleanup (5 min expiry for OTPs) ---

        now = timezone.now()
        cutoff = now - timedelta(minutes=5)
        expired_otp = EmailOTP.objects.filter(expires_at__lt=now).delete()
        self.stdout.write(self.style.SUCCESS(f'Cleaned up {expired_otp[0]} expired OTPs.'))

        old_used = EmailOTP.objects.filter(is_used=True, created_at__lt=now - timedelta(hours=24)).delete()
        if old_used[0]:
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {old_used[0]} old used OTPs.'))

        self.stdout.write(self.style.SUCCESS('Cleanup complete.'))
