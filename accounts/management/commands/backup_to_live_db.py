import os
import time
import logging
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import BackupLog
from accounts.utils.drive_backup_service import (
    run_pg_dump, run_pg_dump_fallback, restore_to_backup_db,
    compute_sha256, _get_config
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Dump primary DB and restore to backup Supabase PostgreSQL (BACKUP_DATABASE_URL)'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force even if already ran today')

    def handle(self, *args, **options):
        force = options.get('force', False)

        backup_db_url = os.getenv('BACKUP_DATABASE_URL')
        if not backup_db_url:
            self.stdout.write(self.style.ERROR('BACKUP_DATABASE_URL not set — cannot run live DB backup'))
            return

        if str(_get_config('BACKUP_ENABLED', 'True')) != 'True':
            self.stdout.write(self.style.WARNING('Backup disabled by BACKUP_ENABLED=False'))
            return

        if not force:
            today = timezone.now().date()
            existing = BackupLog.objects.filter(
                backup_type='LIVE_DB',
                status='SUCCESS',
                created_at__date=today
            ).first()
            if existing:
                self.stdout.write(self.style.WARNING(f'Live DB backup already ran today: {existing.filename}'))
                return

        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        log = BackupLog.objects.create(
            backup_type='LIVE_DB',
            filename=f'live_restore_{timestamp}.sql',
            status='RUNNING',
            metadata={
                'source': 'primary DATABASE_URL',
                'target': 'BACKUP_DATABASE_URL',
                'started_at': datetime.now().isoformat(),
            },
        )

        start_time = time.time()

        try:
            self.stdout.write('Step 1/2: Dumping primary database...')
            sql_bytes, error, file_size = run_pg_dump()
            if error:
                self.stdout.write(f'  pg_dump failed, trying dumpdata fallback: {error}')
                sql_bytes, error, file_size = run_pg_dump_fallback()
                if error:
                    raise ValueError(f'Primary DB dump failed: {error}')

            log.file_size = file_size
            log.sha256 = compute_sha256(sql_bytes)
            log.metadata['dump_size'] = file_size
            log.save(update_fields=['file_size', 'sha256', 'metadata'])
            self.stdout.write(f'  Primary DB dumped: {file_size} bytes')

            self.stdout.write('Step 2/2: Restoring to backup Supabase database...')
            success, msg = restore_to_backup_db(sql_bytes, backup_db_url)
            if not success:
                raise ValueError(f'Backup DB restore failed: {msg}')

            log.status = 'SUCCESS'
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.drive_folder_path = 'supabase_live_db'
            log.metadata['restore_status'] = 'ok'
            log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'drive_folder_path', 'metadata'])

            self.stdout.write(self.style.SUCCESS(
                f'Live DB backup complete — primary → backup Supabase: {file_size} bytes restored'
            ))

        except ValueError as e:
            log.status = 'FAILED'
            log.error_message = str(e)[:500]
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.save(update_fields=['status', 'error_message', 'completed_at', 'duration_seconds'])
            self.stdout.write(self.style.ERROR(str(e)))
        except Exception as e:
            log.status = 'FAILED'
            log.error_message = str(e)[:500]
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.save(update_fields=['status', 'error_message', 'completed_at', 'duration_seconds'])
            self.stdout.write(self.style.ERROR(f'Unexpected error: {e}'))
