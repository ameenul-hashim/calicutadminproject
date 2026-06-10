import os
import logging
from django.core.management.base import BaseCommand
from accounts.utils.drive_backup_service import _mega_configured

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Diagnose MEGA backup configuration and test connectivity'

    def handle(self, *args, **options):
        self.stdout.write('\n=== MEGA Backup Diagnostics ===\n')

        # 1. Check BACKUP_ENABLED
        from accounts.utils.drive_backup_service import _get_config
        enabled = _get_config('BACKUP_ENABLED', 'True')
        self.stdout.write(f'1. BACKUP_ENABLED: {enabled}')

        if str(enabled) != 'True':
            self.stdout.write(self.style.WARNING('   ⚠  Backups are DISABLED'))
            self.stdout.write(self.style.WARNING('   Set BACKUP_ENABLED=True in env/settings'))

        # 2. Check MEGA credentials
        self.stdout.write('\n2. MEGA Credentials Check:')
        mega_email = os.getenv('MEGA_EMAIL')
        mega_pass = os.getenv('MEGA_PASSWORD')
        if mega_email and mega_pass:
            self.stdout.write(self.style.SUCCESS(f'   ✅ MEGA_EMAIL set ({mega_email[:4]}...)'))
        else:
            self.stdout.write(self.style.ERROR('   ❌ MEGA_EMAIL / MEGA_PASSWORD not set'))
            self.stdout.write(self.style.WARNING('   Set MEGA_EMAIL and MEGA_PASSWORD env vars'))

        # 3. MEGA Login Test
        self.stdout.write('\n3. MEGA Connection Test:')
        if not _mega_configured():
            self.stdout.write(self.style.ERROR('   ❌ MEGA not configured — skipping login test'))
            self.stdout.write(self.style.WARNING('   Set MEGA_EMAIL and MEGA_PASSWORD'))
        else:
            from accounts.utils.mega_backup_service import _login
            try:
                mega = _login()
                if mega:
                    self.stdout.write(self.style.SUCCESS('   ✅ MEGA login successful'))
                    folder = mega.find('NeoLearner_Backups')
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
        if _mega_configured() and total > 0:
            self.stdout.write(self.style.SUCCESS('MEGA backup should work'))
        else:
            self.stdout.write(self.style.WARNING('Set MEGA_EMAIL and MEGA_PASSWORD in env to enable backups'))
        self.stdout.write('=' * 40 + '\n')
