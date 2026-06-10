import logging
import time
from django.core.management.base import BaseCommand
from django.db.models import Q
from accounts.models import BackupLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Retry failed backups up to max_retries times'

    def add_arguments(self, parser):
        parser.add_argument('--backup-type', type=str, choices=['DATABASE', 'SIGNUP_PDF', 'TEACHER_RESOURCE', 'DAILY_FULL', 'ALL'],
                            default='ALL', help='Filter by backup type')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be retried')

    def handle(self, *args, **options):
        backup_type = options.get('backup_type', 'ALL')
        dry_run = options.get('dry_run', False)

        q = Q(status='FAILED', retry_count__lt=3)
        if backup_type != 'ALL':
            q &= Q(backup_type=backup_type)

        failed = BackupLog.objects.filter(q).order_by('-created_at')[:50]
        self.stdout.write(f'Found {failed.count()} failed backups needing retry')

        if dry_run:
            for log in failed:
                self.stdout.write(f'  [{log.backup_type}] {log.filename} — retry_count={log.retry_count}')
            return

        service = _get_drive_service()
        if not service:
            self.stdout.write(self.style.ERROR('Google Drive not configured'))
            return

        for log in failed:
            self.stdout.write(f'Retrying: [{log.backup_type}] {log.filename}...')
            log.retry_count += 1
            log.status = 'RETRYING'
            log.save(update_fields=['retry_count', 'status'])

            try:
                if log.backup_type == 'DAILY_FULL':
                    self._retry_daily_full(log)
                elif log.backup_type == 'DATABASE':
                    self._retry_database_backup(log, service)
                elif log.backup_type == 'SIGNUP_PDF':
                    self._retry_signup_pdf_backup(log, service)
                elif log.backup_type == 'TEACHER_RESOURCE':
                    self._retry_resource_backup(log, service)
            except Exception as e:
                log.status = 'FAILED'
                log.error_message = str(e)[:500]
                log.save(update_fields=['status', 'error_message'])
                self.stdout.write(self.style.ERROR(f'  Failed: {e}'))

        self.stdout.write(self.style.SUCCESS('Retry complete'))

    def _retry_daily_full(self, log):
        from django.core.management import call_command
        from io import StringIO
        buf = StringIO()
        try:
            call_command('backup_daily_full', '--force', stdout=buf)
            log.refresh_from_db()
            if log.status == 'FAILED':
                raise ValueError(log.error_message or 'Daily full backup retry failed')
            self.stdout.write(self.style.SUCCESS('  Daily full backup retry SUCCESS'))
        except Exception as e:
            log.refresh_from_db()
            log.status = 'FAILED'
            log.error_message = str(e)[:500]
            log.save(update_fields=['status', 'error_message'])
            self.stdout.write(self.style.ERROR(f'  Daily full retry failed: {e}'))

    def _retry_database_backup(self, log, service):
        from accounts.utils.drive_backup_service import run_pg_dump, run_pg_dump_fallback
        start = time.time()

        sql_bytes, error, file_size = run_pg_dump()
        if error:
            sql_bytes, error, file_size = run_pg_dump_fallback()
            if error:
                raise ValueError(f'pg_dump failed: {error}')

        folder_parts = ['NeoLearner_Backups', 'Database']
        folder_id = ensure_folder_path(service, folder_parts)
        log.drive_folder_path = '/'.join(folder_parts)
        log.file_size = file_size
        log.status = 'UPLOADING'
        log.save(update_fields=['drive_folder_path', 'file_size', 'status'])

        drive_id, upload_error = upload_file(service, sql_bytes, log.filename, 'application/octet-stream', folder_id)
        if upload_error:
            raise ValueError(f'Upload failed: {upload_error}')

        log.drive_file_id = drive_id
        actual_sha256 = compute_sha256(sql_bytes)
        log.sha256 = actual_sha256
        log.verify_status = 'VERIFIED'
        log.status = 'SUCCESS'
        log.duration_seconds = time.time() - start
        log.error_message = None
        log.save(update_fields=['drive_file_id', 'sha256', 'verify_status', 'status', 'duration_seconds', 'error_message'])
        self.stdout.write(self.style.SUCCESS(f'  Database backup retry SUCCESS'))

    def _retry_signup_pdf_backup(self, log, service):
        from accounts.models import CustomUser
        from accounts.utils.supabase_storage import get_signed_url
        import requests

        user_id = log.metadata.get('user_id')
        pdf_path = log.metadata.get('pdf_path')
        if not user_id or not pdf_path:
            raise ValueError('Missing user_id or pdf_path in metadata')

        signed_url = get_signed_url(pdf_path)
        if not signed_url:
            raise ValueError('Could not generate signed URL for PDF')

        resp = requests.get(signed_url, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f'Could not download PDF: HTTP {resp.status_code}')

        file_bytes = resp.content
        year_month = log.created_at.strftime('%Y/%m')
        folder_parts = ['NeoLearner_Backups', 'Signup_Proofs'] + year_month.split('/')
        folder_id = ensure_folder_path(service, folder_parts)
        log.drive_folder_path = '/'.join(folder_parts)
        log.file_size = len(file_bytes)
        log.save(update_fields=['drive_folder_path', 'file_size'])

        drive_id, error = upload_file(service, file_bytes, log.filename, 'application/pdf', folder_id)
        if error:
            raise ValueError(f'Upload failed: {error}')

        log.drive_file_id = drive_id
        actual_sha256 = compute_sha256(file_bytes)
        log.sha256 = actual_sha256
        log.verify_status = 'VERIFIED'
        log.status = 'SUCCESS'
        log.error_message = None
        log.save(update_fields=['drive_file_id', 'sha256', 'verify_status', 'status', 'error_message'])
        self.stdout.write(self.style.SUCCESS(f'  Signup PDF retry SUCCESS'))

    def _retry_resource_backup(self, log, service):
        from accounts.utils.supabase_storage import get_client

        resource_id = log.metadata.get('resource_id')
        supabase_path = log.metadata.get('supabase_path')
        if not supabase_path:
            raise ValueError('Missing supabase_path in metadata')

        client = get_client(use_resource_project=True)
        if not client:
            raise ValueError('Resource Supabase not configured')

        file_bytes = client.storage.from_('resources').download(supabase_path)
        if not file_bytes:
            raise ValueError('Could not download file from Supabase')

        course = log.metadata.get('course', 'Unknown')
        chapter = log.metadata.get('chapter', 'General')
        category = log.metadata.get('category', 'General')
        folder_parts = ['NeoLearner_Backups', 'Teacher_Resources', course, chapter, category]
        folder_id = ensure_folder_path(service, folder_parts)
        log.drive_folder_path = '/'.join(folder_parts)
        log.file_size = len(file_bytes)
        log.save(update_fields=['drive_folder_path', 'file_size'])

        mime_map = {'pdf': 'application/pdf', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'txt': 'text/plain'}
        ext = supabase_path.split('.')[-1] if '.' in supabase_path else 'pdf'
        mime_type = mime_map.get(ext.lower(), 'application/octet-stream')

        drive_id, error = upload_file(service, file_bytes, log.filename, mime_type, folder_id)
        if error:
            raise ValueError(f'Upload failed: {error}')

        log.drive_file_id = drive_id
        actual_sha256 = compute_sha256(file_bytes)
        log.sha256 = actual_sha256
        log.verify_status = 'VERIFIED'
        log.status = 'SUCCESS'
        log.error_message = None
        log.save(update_fields=['drive_file_id', 'sha256', 'verify_status', 'status', 'error_message'])
        self.stdout.write(self.style.SUCCESS(f'  Resource retry SUCCESS'))
