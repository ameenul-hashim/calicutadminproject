import os
import logging
from django.core.management.base import BaseCommand
from accounts.utils.drive_backup_service import _drive_configured

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Diagnose backup drive configuration and test connectivity'

    def handle(self, *args, **options):
        self.stdout.write('\n=== Backup Drive Diagnostics ===\n')

        # 1. Check BACKUP_ENABLED
        from accounts.utils.drive_backup_service import _get_config
        enabled = _get_config('BACKUP_ENABLED', 'True')
        self.stdout.write(f'1. BACKUP_ENABLED: {enabled}')

        if str(enabled) != 'True':
            self.stdout.write(self.style.WARNING('   ⚠  Backups are DISABLED'))
            self.stdout.write(self.style.WARNING('   Set BACKUP_ENABLED=True in env/settings'))

        # 2. Check credentials
        self.stdout.write('\n2. Credentials Check:')
        from accounts.utils.drive_backup_service import _use_google_drive
        gd = _use_google_drive()
        mega_email = os.getenv('MEGA_EMAIL')
        mega_pass = os.getenv('MEGA_PASSWORD')
        mega = bool(mega_email and mega_pass)
        if gd:
            self.stdout.write(self.style.SUCCESS('   ✅ Google Drive credentials set'))
        else:
            self.stdout.write(self.style.WARNING('   ℹ️  GOOGLE_DRIVE_CREDENTIALS not set'))
        if mega:
            self.stdout.write(self.style.SUCCESS(f'   ✅ MEGA_EMAIL set ({mega_email[:4]}...)'))
            self.stdout.write(self.style.SUCCESS('   ✅ MEGA_PASSWORD set'))
        else:
            self.stdout.write(self.style.WARNING('   ℹ️  MEGA_EMAIL / MEGA_PASSWORD not set (fallback)'))

        # 3. Drive Login Test
        self.stdout.write('\n3. Drive Connection Test:')
        if _drive_configured():
            self.stdout.write(self.style.SUCCESS('   ✅ Drive credentials configured'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ No drive backend configured'))
            self.stdout.write(self.style.WARNING('   Set GOOGLE_DRIVE_CREDENTIALS or MEGA_EMAIL/PASSWORD'))

        if _use_google_drive():
            self.stdout.write('\n   Google Drive test:')
            try:
                from accounts.utils.google_drive_service import build_drive_service
                gd_service = build_drive_service()
                about = gd_service.about().get(fields='user').execute()
                user = about.get('user', {})
                self.stdout.write(self.style.SUCCESS(f'   ✅ Google Drive connected as {user.get("displayName", "service account")}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ❌ Google Drive connection failed: {e}'))

        if mega:
            self.stdout.write('\n   MEGA test:')
            from accounts.utils.mega_backup_service import _login
            try:
                mega_instance = _login()
                if mega_instance:
                    self.stdout.write(self.style.SUCCESS('   ✅ MEGA login successful'))
                    folder = mega_instance.find('NeoLearner_Backups')
                    if folder:
                        self.stdout.write(self.style.SUCCESS('   ✅ Root folder "NeoLearner_Backups" exists'))
                    else:
                        self.stdout.write('   ℹ️  Root folder "NeoLearner_Backups" will be created on first backup')
                else:
                    self.stdout.write(self.style.ERROR('   ❌ MEGA login failed — check credentials'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ❌ MEGA test failed: {e}'))

        # 4. Check BackupLog stats
        self.stdout.write('\n4. Backup History (from database):')
        try:
            from accounts.models import BackupLog
            total = BackupLog.objects.count()
            success = BackupLog.objects.filter(status='SUCCESS').count()
            failed_b = BackupLog.objects.filter(status='FAILED').count()
            pending = BackupLog.objects.filter(status__in=['PENDING', 'RUNNING', 'UPLOADING', 'VERIFYING', 'RETRYING']).count()
            db_backups = BackupLog.objects.filter(backup_type='DATABASE').count()
            signup_backups = BackupLog.objects.filter(backup_type='SIGNUP_PDF').count()
            resource_backups = BackupLog.objects.filter(backup_type='TEACHER_RESOURCE').count()

            self.stdout.write(f'   Total: {total} | ✅ {success} | ❌ {failed_b} | ⏳ {pending}')
            self.stdout.write(f'   Database: {db_backups} | Signup PDFs: {signup_backups} | Resources: {resource_backups}')

            if failed_b > 0:
                self.stdout.write('\n   Recent failures:')
                for fb in BackupLog.objects.filter(status='FAILED').order_by('-created_at')[:5]:
                    self.stdout.write(self.style.ERROR(f'   ❌ [{fb.created_at.strftime("%Y-%m-%d %H:%M")}] {fb.filename} — {fb.error_message or "No details"}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   Error reading BackupLog: {e}'))

        # 5. Check CourseResource backup status
        self.stdout.write('\n5. Resource Backup Status:')
        try:
            from accounts.models import CourseResource
            total_res = CourseResource.objects.count()
            backed_up = CourseResource.objects.filter(backup_status='SUCCESS').count()
            failed_res = CourseResource.objects.filter(backup_status='FAILED').count()
            pending_res = total_res - backed_up - failed_res
            self.stdout.write(f'   Total: {total_res} | ✅ {backed_up} | ❌ {failed_res} | ⏳ {pending_res}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   Error reading CourseResource: {e}'))

        self.stdout.write('\n' + '=' * 40)
        if _drive_configured() and total > 0:
            self.stdout.write(self.style.SUCCESS('Drive backup is operational'))
        else:
            self.stdout.write(self.style.WARNING('Set GOOGLE_DRIVE_CREDENTIALS or MEGA_EMAIL/PASSWORD to enable backups'))
        self.stdout.write('=' * 40 + '\n')
