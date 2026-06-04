from django.core.management.base import BaseCommand
from accounts.utils.notification_helper import cleanup_old_notifications as cleanup_notifs
from accounts.utils.firebase_db import chat_cleanup, login_history_cleanup, admin_log_cleanup, otp_cleanup


class Command(BaseCommand):
    help = 'Cleans up old data in Firebase RTDB: notifications, chat, login history, admin activity (7 days), OTPs (10 min)'

    def handle(self, *args, **options):
        self.stdout.write('Starting Firebase cleanup...')

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

        try:
            deleted = otp_cleanup(10)
            self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted} expired OTPs.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'OTP cleanup error: {e}'))

        self.stdout.write(self.style.SUCCESS('Cleanup complete.'))
