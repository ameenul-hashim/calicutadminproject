import os
import logging
import tempfile
from django.core.management.base import BaseCommand
from accounts.models import BackupLog
from accounts.utils.drive_backup_service import (
    _get_drive_service, download_file, verify_file_integrity
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Restore a backup from Google Drive by BackupLog UID'

    def add_arguments(self, parser):
        parser.add_argument('backup_uid', type=str, help='UID of the BackupLog entry to restore')
        parser.add_argument('--output-dir', type=str, help='Directory to save restored file (default: temp)')
        parser.add_argument('--dry-run', action='store_true', help='Verify without restoring')

    def handle(self, *args, **options):
        backup_uid = options.get('backup_uid')
        output_dir = options.get('output_dir')
        dry_run = options.get('dry_run', False)

        try:
            log = BackupLog.objects.get(uid=backup_uid)
        except BackupLog.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'BackupLog not found: {backup_uid}'))
            return

        self.stdout.write(f'Backup: [{log.backup_type}] {log.filename}')
        self.stdout.write(f'Status: {log.status}')
        self.stdout.write(f'Verify Status: {log.verify_status}')
        self.stdout.write(f'SHA256: {log.sha256}')
        self.stdout.write(f'Drive File ID: {log.drive_file_id}')

        if not log.drive_file_id:
            self.stdout.write(self.style.ERROR('No Drive file ID — nothing to restore'))
            return

        service = _get_drive_service()
        if not service:
            self.stdout.write(self.style.ERROR('Google Drive not configured'))
            return

        # Download from Drive
        self.stdout.write('Downloading from Google Drive...')
        file_bytes, error = download_file(service, log.drive_file_id)
        if error:
            self.stdout.write(self.style.ERROR(f'Download failed: {error}'))
            return

        # Verify integrity
        is_valid, actual_sha256, verify_error = verify_file_integrity(file_bytes, log.sha256)
        if not is_valid:
            self.stdout.write(self.style.ERROR(f'Integrity check failed: {verify_error}'))
            self.stdout.write(self.style.ERROR(f'Expected SHA256: {log.sha256}'))
            self.stdout.write(self.style.ERROR(f'Actual SHA256:   {actual_sha256}'))
            return

        self.stdout.write(self.style.SUCCESS(f'RESTORE VERIFIED ({len(file_bytes)} bytes, SHA256 match)'))

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run — no files written'))
            return

        # Save to output directory
        if not output_dir:
            output_dir = tempfile.mkdtemp(prefix='neolearner_restore_')

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, log.filename)

        with open(output_path, 'wb') as f:
            f.write(file_bytes)

        self.stdout.write(self.style.SUCCESS(f'Restored to: {output_path}'))

        # For database backups, provide restore instructions
        if log.backup_type == 'DATABASE':
            self.stdout.write('')
            self.stdout.write('To restore database:')
            if log.filename.endswith('.json'):
                self.stdout.write(f'  python manage.py loaddata {output_path}')
            else:
                db_url = os.getenv('DATABASE_URL', 'postgresql://...')
                self.stdout.write(f'  psql "{db_url}" < {output_path}')
