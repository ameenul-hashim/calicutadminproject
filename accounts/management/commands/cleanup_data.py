from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.utils.notification_helper import cleanup_old_notifications as cleanup_notifs
from accounts.utils.firebase_db import run_all_cleanup, login_history_cleanup, admin_log_cleanup
from accounts.utils.firebase_analytics import analytics_cleanup
from accounts.utils.firebase_chat import cleanup_old_messages as support_chat_cleanup
from accounts.models import EmailOTP, PasswordResetOTP


class Command(BaseCommand):
    help = 'Cleans up old data in Firebase RTDB and PostgreSQL'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup...')

        # --- Firebase RTDB cleanups (7/30 days) ---

        try:
            cleanup_notifs()
            self.stdout.write(self.style.SUCCESS('Cleaned up notifications older than 30 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Notification cleanup error: {e}'))

        try:
            deleted = run_all_cleanup()
            for k, v in deleted.items():
                self.stdout.write(self.style.SUCCESS(f'  {k}: {v} cleaned'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'run_all_cleanup error: {e}'))

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

        try:
            deleted = support_chat_cleanup(days=30)
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted} support chat messages older than 30 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Support chat cleanup error: {e}'))

        try:
            deleted = analytics_cleanup(days=30)
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted} analytics entries older than 30 days.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Analytics cleanup error: {e}'))

        # --- PostgreSQL cleanup ---

        now = timezone.now()

        # EmailOTP cleanup — delete all OTPs older than 10 minutes
        old_otps = EmailOTP.objects.filter(created_at__lt=now - timedelta(minutes=10)).delete()
        if old_otps[0]:
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {old_otps[0]} old EmailOTPs (>= 10 minutes old).'))

        # PasswordResetOTP cleanup (from forgot-password flow — 5 min expiry)
        expired_reset = PasswordResetOTP.objects.filter(expires_at__lt=now).delete()
        self.stdout.write(self.style.SUCCESS(f'Cleaned up {expired_reset[0]} expired PasswordResetOTPs.'))

        old_reset = PasswordResetOTP.objects.filter(created_at__lt=now - timedelta(hours=1)).delete()
        if old_reset[0]:
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {old_reset[0]} old PasswordResetOTPs.'))

        self.stdout.write(self.style.SUCCESS('Cleanup complete.'))
