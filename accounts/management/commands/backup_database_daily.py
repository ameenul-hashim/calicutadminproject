import os
import logging
import time
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import BackupLog
from accounts.utils.drive_backup_service import (
    _get_drive_service, ensure_folder_path, upload_file,
    compute_sha256, verify_file_integrity, run_pg_dump, run_pg_dump_fallback
)

logger = logging.getLogger(__name__)

FOLDER_PATH = ['NeoLearn_Backups', 'Database']


class Command(BaseCommand):
    help = 'Daily database backup to Google Drive with SHA256 verification'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force backup even if already ran today')

    def handle(self, *args, **options):
        force = options.get('force', False)

        if not force:
            today = timezone.now().date()
            existing = BackupLog.objects.filter(
                backup_type='DATABASE',
                status='SUCCESS',
                created_at__date=today
            ).first()
            if existing:
                self.stdout.write(self.style.WARNING(f'Backup already ran today: {existing.filename}'))
                return

        # Create backup log entry
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        filename = f'{timestamp}.sql'
        log = BackupLog.objects.create(
            backup_type='DATABASE',
            filename=filename,
            status='RUNNING',
        )

        try:
            # Get Drive service
            service = _get_drive_service()
            if not service:
                log.status = 'FAILED'
                log.error_message = 'Google Drive not configured (GOOGLE_DRIVE_CREDENTIALS missing)'
                log.save(update_fields=['status', 'error_message', 'completed_at'])
                self.stdout.write(self.style.ERROR(log.error_message))
                return

            log.status = 'RUNNING'

            # Run pg_dump
            self.stdout.write('Running pg_dump...')
            start_time = time.time()
            sql_bytes, error, file_size = run_pg_dump()
            if error:
                self.stdout.write(f'pg_dump failed, trying fallback: {error}')
                sql_bytes, error, file_size = run_pg_dump_fallback()
                if error:
                    raise ValueError(f'Backup failed: {error}')
                filename = f'{timestamp}.json'
                log.filename = filename

            log.file_size = file_size
            log.status = 'UPLOADING'
            log.save(update_fields=['status', 'file_size', 'filename'])

            # Upload to Drive
            folder_id = ensure_folder_path(service, FOLDER_PATH)
            drive_id, upload_error = upload_file(service, sql_bytes, filename, 'application/octet-stream', folder_id)
            if upload_error:
                raise ValueError(f'Upload failed: {upload_error}')

            log.drive_file_id = drive_id
            log.drive_folder_path = '/'.join(FOLDER_PATH)

            # Verify SHA256
            log.status = 'VERIFYING'
            log.save(update_fields=['status', 'drive_file_id', 'drive_folder_path'])

            is_valid, actual_sha256, verify_error = verify_file_integrity(sql_bytes)
            if not is_valid:
                log.verify_status = 'MISMATCH'
                log.status = 'FAILED'
                log.error_message = verify_error or 'SHA256 verification failed'
                log.completed_at = timezone.now()
                log.duration_seconds = time.time() - start_time
                log.save(update_fields=['verify_status', 'status', 'error_message', 'completed_at', 'duration_seconds'])
                self.stdout.write(self.style.ERROR(log.error_message))
                return

            log.sha256 = actual_sha256
            log.verify_status = 'VERIFIED'
            log.status = 'SUCCESS'
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.save(update_fields=['sha256', 'verify_status', 'status', 'completed_at', 'duration_seconds'])

            self.stdout.write(self.style.SUCCESS(
                f'Database backup complete: {filename} ({file_size} bytes, SHA256: {actual_sha256[:16]}...)'
            ))

        except ValueError as e:
            log.status = 'FAILED'
            log.error_message = str(e)
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - (log.duration_seconds or 0)
            if hasattr(log, 'duration_seconds') and log.duration_seconds == 0:
                log.duration_seconds = time.time()
            log.save(update_fields=['status', 'error_message', 'completed_at', 'duration_seconds'])
            self.stdout.write(self.style.ERROR(str(e)))
        except Exception as e:
            log.status = 'FAILED'
            log.error_message = str(e)[:500]
            log.completed_at = timezone.now()
            log.duration_seconds = time.time()
            log.save(update_fields=['status', 'error_message', 'completed_at', 'duration_seconds'])
            self.stdout.write(self.style.ERROR(f'Unexpected error: {e}'))
