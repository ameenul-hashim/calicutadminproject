import logging
import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import BackupLog
from accounts.utils.drive_backup_service import (
    _get_drive_service, download_file, compute_sha256
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Weekly restore test — verifies that backed-up files can be downloaded and match SHA256'

    def add_arguments(self, parser):
        parser.add_argument('--backup-type', type=str, choices=['DATABASE', 'SIGNUP_PDF', 'TEACHER_RESOURCE', 'ALL'],
                            default='ALL', help='Which backup types to test')
        parser.add_argument('--days', type=int, default=7, help='How far back to look for backups to test')

    def handle(self, *args, **options):
        backup_type = options.get('backup_type', 'ALL')
        days = options.get('days', 7)

        q = {'status': 'SUCCESS', 'verify_status': 'VERIFIED', 'drive_file_id__isnull': False}
        if backup_type != 'ALL':
            q['backup_type'] = backup_type

        since = timezone.now() - timedelta(days=days)
        backups = BackupLog.objects.filter(**q, created_at__gte=since).order_by('-created_at')[:10]

        self.stdout.write(f'Found {backups.count()} backups to test restore')

        if not backups.exists():
            self.stdout.write(self.style.WARNING('No backups found to test'))
            return

        service = _get_drive_service()
        if not service:
            self.stdout.write(self.style.ERROR('Google Drive not configured'))
            return

        passed = 0
        failed = 0

        for log in backups:
            self.stdout.write(f'Testing: [{log.backup_type}] {log.filename}...', ending=' ')
            try:
                start = time.time()
                file_bytes, error = download_file(service, log.drive_file_id)
                if error:
                    self.stdout.write(self.style.ERROR(f'DOWNLOAD FAILED: {error}'))
                    failed += 1
                    continue

                is_valid = True
                if log.sha256:
                    actual = compute_sha256(file_bytes)
                    if actual != log.sha256:
                        self.stdout.write(self.style.ERROR(f'SHA256 MISMATCH'))
                        failed += 1
                        continue

                duration = time.time() - start
                self.stdout.write(self.style.SUCCESS(
                    f'RESTORE VERIFIED ({len(file_bytes)} bytes in {duration:.1f}s)'
                ))
                passed += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'ERROR: {e}'))
                failed += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Restore test complete: {passed} passed, {failed} failed'))
