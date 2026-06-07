import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import BackupLog
from accounts.utils.drive_backup_service import (
    _get_drive_service, download_file, compute_sha256
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Monthly integrity verification — verifies SHA256 of all recent backups'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='How far back to check')

    def handle(self, *args, **options):
        days = options.get('days', 30)
        since = timezone.now() - timedelta(days=days)

        backups = BackupLog.objects.filter(
            status='SUCCESS', drive_file_id__isnull=False, created_at__gte=since
        ).order_by('-created_at')

        self.stdout.write(f'Verifying {backups.count()} backups from last {days} days...')

        service = _get_drive_service()
        if not service:
            self.stdout.write(self.style.ERROR('Google Drive not configured'))
            return

        verified = 0
        mismatched = 0
        failed = 0

        for log in backups:
            try:
                file_bytes, error = download_file(service, log.drive_file_id)
                if error:
                    self.stdout.write(self.style.WARNING(f'  [{log.backup_type}] {log.filename}: DOWNLOAD ERROR - {error[:100]}'))
                    failed += 1
                    continue

                actual = compute_sha256(file_bytes)
                if log.sha256 and actual != log.sha256:
                    self.stdout.write(self.style.ERROR(
                        f'  [{log.backup_type}] {log.filename}: SHA256 MISMATCH'
                    ))
                    log.verify_status = 'MISMATCH'
                    log.save(update_fields=['verify_status'])
                    mismatched += 1
                else:
                    log.verify_status = 'VERIFIED'
                    log.save(update_fields=['verify_status'])
                    verified += 1

            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  [{log.backup_type}] {log.filename}: ERROR - {e}'))
                failed += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Integrity check complete: {verified} verified, {mismatched} mismatched, {failed} failed'
        ))
