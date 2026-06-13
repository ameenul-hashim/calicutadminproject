import os
import io
import json
import time
import zipfile
import hashlib
import logging
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import BackupLog, CourseResource, CustomUser
from accounts.utils.drive_backup_service import (
    _get_drive_service, ensure_folder_path, upload_file,
    compute_sha256, delete_old_backups, _get_config
)
from accounts.utils.supabase_storage import backup_supabase, backup_bucket

logger = logging.getLogger(__name__)


def _list_supabase_files(client, bucket, prefix=''):
    """Recursively list all files in a Supabase bucket path."""
    files = []
    try:
        entries = client.storage.from_(bucket).list(prefix)
        for entry in entries:
            name = entry.get('name', '')
            if entry.get('id') is None:
                sub_files = _list_supabase_files(client, bucket, f"{prefix}/{name}" if prefix else name)
                files.extend(sub_files)
            else:
                full_path = f"{prefix}/{name}" if prefix else name
                files.append({
                    'path': full_path,
                    'name': name,
                    'updated_at': entry.get('updated_at', ''),
                    'metadata': entry.get('metadata', {}),
                })
    except Exception as e:
        logger.warning(f"Failed to list Supabase bucket '{bucket}' prefix '{prefix}': {e}")
    return files


class Command(BaseCommand):
    help = 'Daily full backup - database + Supabase files to ZIP archive + cloud drive + backup Supabase'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force backup even if already ran today')
        parser.add_argument('--skip-retention', action='store_true', help='Skip old backup cleanup')

    def handle(self, *args, **options):
        force = options.get('force', False)
        skip_retention = options.get('skip_retention', False)

        if str(_get_config('BACKUP_ENABLED', 'True')) != 'True':
            self.stdout.write(self.style.WARNING('Backup disabled by BACKUP_ENABLED=False'))
            return

        if not force:
            today = timezone.now().date()
            existing = BackupLog.objects.filter(
                backup_type='DAILY_FULL',
                status='SUCCESS',
                created_at__date=today
            ).first()
            if existing:
                self.stdout.write(self.style.WARNING(f'Daily backup already completed today: {existing.filename}'))
                return

        start_time = time.time()
        archive_name = f'backup_{datetime.now().strftime("%Y_%m_%d")}.zip'
        backup_folder = 'Daily_Backups'
        temp_dir = tempfile.mkdtemp(prefix='daily_backup_')
        archive_path = os.path.join(temp_dir, archive_name)
        db_dir = os.path.join(temp_dir, 'database')
        signup_dir = os.path.join(temp_dir, 'signup_pdfs')
        resources_dir = os.path.join(temp_dir, 'resources')
        os.makedirs(db_dir, exist_ok=True)
        os.makedirs(signup_dir, exist_ok=True)
        os.makedirs(resources_dir, exist_ok=True)

        log = BackupLog.objects.create(
            backup_type='DAILY_FULL',
            filename=archive_name,
            status='RUNNING',
            metadata={
                'started_at': datetime.now().isoformat(),
                'files_included': 0,
                'files_skipped_duplicate': 0,
                'database_size': 0,
                'signup_pdf_count': 0,
                'resource_count': 0,
            },
        )

        dedup_hashes = set()

        try:
            self.stdout.write('Step 1/6: Dumping database...')
            self._dump_database(db_dir, log)
            db_files = list(Path(db_dir).iterdir())
            db_size = sum(f.stat().st_size for f in db_files if f.is_file())
            log.metadata['database_size'] = db_size

            self.stdout.write('Step 2/6: Collecting Supabase signup PDFs...')
            signup_count = self._collect_signup_pdfs(signup_dir, dedup_hashes, log)
            log.metadata['signup_pdf_count'] = signup_count

            self.stdout.write('Step 3/6: Collecting Supabase resource files...')
            resource_count = self._collect_resource_files(resources_dir, dedup_hashes, log)
            log.metadata['resource_count'] = resource_count

            log.metadata['files_included'] = signup_count + resource_count + len(db_files)
            log.metadata['dedup_hashes_count'] = len(dedup_hashes)
            log.save(update_fields=['metadata'])

            self.stdout.write(f'Step 4/6: Creating archive ({archive_name})...')
            self._create_zip_archive(archive_path, temp_dir, log)

            file_size = os.path.getsize(archive_path)
            log.file_size = file_size
            log.status = 'UPLOADING'
            log.save(update_fields=['file_size', 'status'])

            self.stdout.write(f'Step 5/6: Uploading to cloud drive ({file_size} bytes)...')
            with open(archive_path, 'rb') as f:
                archive_bytes = f.read()
            sha256_hash = compute_sha256(archive_bytes)
            log.sha256 = sha256_hash
            log.save(update_fields=['sha256'])

            service = _get_drive_service()
            if not service:
                raise ValueError('No drive configured (set GOOGLE_DRIVE_CREDENTIALS or MEGA_EMAIL/PASSWORD)')

            folder_id = ensure_folder_path(service, ['NeoLearner_Backups', backup_folder])
            if not folder_id:
                raise ValueError('Failed to create drive folder path')

            drive_id, upload_error = upload_file(service, archive_bytes, archive_name, 'application/zip', folder_id)
            if upload_error:
                raise ValueError(f'Upload failed: {upload_error}')

            log.drive_file_id = drive_id
            log.drive_folder_path = f'NeoLearner_Backups/{backup_folder}'
            log.status = 'VERIFYING'
            log.save(update_fields=['drive_file_id', 'drive_folder_path', 'status'])

            raw_verify = _get_config('BACKUP_VERIFY_SHA256', 'True')
            verify_sha = str(raw_verify).lower() == 'true'
            if verify_sha:
                actual_sha = compute_sha256(archive_bytes)
                if actual_sha != sha256_hash:
                    raise ValueError('SHA256 mismatch after upload')
                log.verify_status = 'VERIFIED'
            else:
                log.verify_status = 'PENDING'

            # Upload DB dump to 3rd Supabase bucket
            db_uploaded = self._upload_db_to_backup_supabase(db_dir)

            log.status = 'SUCCESS'
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.metadata['backup_supabase_uploaded'] = db_uploaded
            log.save(update_fields=['verify_status', 'status', 'completed_at', 'duration_seconds', 'metadata'])

            total_files = log.metadata['files_included']
            skipped = log.metadata.get('files_skipped_duplicate', 0)
            self.stdout.write(self.style.SUCCESS(
                f'Daily backup complete: {archive_name} ({file_size} bytes) — '
                f'{total_files} files included, {skipped} duplicates skipped'
            ))

            if not skip_retention:
                self.stdout.write('Step 6/6: Enforcing 30-day retention...')
                retention = int(_get_config('BACKUP_RETENTION_DAYS', 30))
                deleted = delete_old_backups(service, folder_id, keep_count=retention)
                if deleted:
                    self.stdout.write(f'Retention: deleted {deleted} old backup(s), keeping last {retention}')

        except Exception as e:
            log.status = 'FAILED'
            log.error_message = str(e)[:500]
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.save(update_fields=['status', 'error_message', 'completed_at', 'duration_seconds'])
            self.stdout.write(self.style.ERROR(f'Daily backup failed: {e}'))
            self.stdout.write(self.style.WARNING(f'Archive retained at: {archive_path}'))
        finally:
            if log.status == 'SUCCESS' and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            elif log.status != 'SUCCESS':
                retry_dir = os.path.join(tempfile.gettempdir(), 'daily_backup_retry')
                if os.path.exists(retry_dir):
                    shutil.rmtree(retry_dir, ignore_errors=True)
                if os.path.exists(archive_path):
                    os.makedirs(retry_dir, exist_ok=True)
                    shutil.copy2(archive_path, os.path.join(retry_dir, archive_name))

    def _dump_database(self, db_dir, log):
        """Dump database to SQL file in db_dir."""
        from accounts.utils.drive_backup_service import run_pg_dump, run_pg_dump_fallback
        sql_bytes, error, file_size = run_pg_dump()
        if error:
            self.stdout.write(f'  pg_dump failed, trying dumpdata fallback: {error}')
            sql_bytes, error, file_size = run_pg_dump_fallback()
            if error:
                raise ValueError(f'Database dump failed: {error}')
            filename = f'{datetime.now().strftime("%Y-%m-%d_%H%M%S")}.json'
        else:
            filename = f'{datetime.now().strftime("%Y-%m-%d_%H%M%S")}.sql'
        filepath = os.path.join(db_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(sql_bytes)
        self.stdout.write(f'  Database dump: {filename} ({file_size} bytes)')

    def _collect_signup_pdfs(self, signup_dir, dedup_hashes, log):
        """Download signup PDFs from Supabase main bucket."""
        count = 0
        skipped = 0
        try:
            from accounts.utils.supabase_storage import get_signed_url
            users = CustomUser.objects.exclude(pdf_path__isnull=True).exclude(pdf_path='')
            for user in users:
                try:
                    signed_url = get_signed_url(user.pdf_path)
                    if not signed_url:
                        continue
                    import requests
                    resp = requests.get(signed_url, timeout=30)
                    if resp.status_code != 200:
                        continue
                    file_bytes = resp.content
                    fhash = hashlib.sha256(file_bytes).hexdigest()
                    if fhash in dedup_hashes:
                        skipped += 1
                        continue
                    dedup_hashes.add(fhash)
                    safe_name = f'user_{user.id}_{user.uid}.pdf'
                    filepath = os.path.join(signup_dir, safe_name)
                    with open(filepath, 'wb') as f:
                        f.write(file_bytes)
                    count += 1
                except Exception as e:
                    logger.warning(f'  Failed to download signup PDF for user {user.id}: {e}')
        except Exception as e:
            logger.warning(f'  Error collecting signup PDFs: {e}')
        log.metadata['files_skipped_duplicate'] = log.metadata.get('files_skipped_duplicate', 0) + skipped
        self.stdout.write(f'  Signup PDFs: {count} collected, {skipped} duplicates skipped')
        return count

    def _collect_resource_files(self, resources_dir, dedup_hashes, log):
        """Download resource files from Supabase resource bucket."""
        count = 0
        skipped = 0
        try:
            from accounts.utils.storage_manager import StorageManager
            resources = CourseResource.objects.filter(
                is_deleted=False
            ).exclude(firebase_file_path__isnull=True).exclude(firebase_file_path='').select_related('course')
            for res in resources:
                try:
                    signed_url = StorageManager.generate_supabase_signed_url(res.firebase_file_path, 60)
                    if not signed_url:
                        continue
                    import requests
                    resp = requests.get(signed_url, timeout=30)
                    if resp.status_code != 200:
                        continue
                    file_bytes = resp.content
                    fhash = hashlib.sha256(file_bytes).hexdigest()
                    if fhash in dedup_hashes:
                        skipped += 1
                        continue
                    dedup_hashes.add(fhash)
                    course_slug = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in (res.course.title if res.course else 'Unknown'))[:50]
                    chapter_slug = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in (res.chapter or 'General'))[:50]
                    cat_dir = os.path.join(resources_dir, course_slug, chapter_slug)
                    os.makedirs(cat_dir, exist_ok=True)
                    ext = res.firebase_file_path.split('.')[-1] if '.' in res.firebase_file_path else 'bin'
                    safe_name = f'resource_{res.id}_{res.uid}.{ext}'
                    filepath = os.path.join(cat_dir, safe_name)
                    with open(filepath, 'wb') as f:
                        f.write(file_bytes)
                    count += 1
                except Exception as e:
                    logger.warning(f'  Failed to download resource {res.id}: {e}')
        except Exception as e:
            logger.warning(f'  Error collecting resource files: {e}')
        log.metadata['files_skipped_duplicate'] = log.metadata.get('files_skipped_duplicate', 0) + skipped
        self.stdout.write(f'  Resource files: {count} collected, {skipped} duplicates skipped')
        return count

    def _upload_db_to_backup_supabase(self, db_dir):
        """Upload database dump file to 3rd Supabase storage bucket.
        Returns True if uploaded, False if skipped or failed."""
        if not backup_supabase:
            self.stdout.write('  Backup Supabase (3rd): skipped (BACKUP_SUPABASE_URL/KEY not set)')
            return False

        db_files = list(Path(db_dir).iterdir())
        if not db_files:
            self.stdout.write('  Backup Supabase (3rd): no database dump file found')
            return False

        db_file = db_files[0]
        file_name = db_file.name
        remote_path = f'daily_backups/{datetime.now().strftime("%Y/%m/%d")}/{file_name}'

        try:
            backup_supabase.storage.get_bucket(backup_bucket)
        except Exception:
            try:
                backup_supabase.storage.create_bucket(backup_bucket, options={"public": False})
                self.stdout.write(f'  Created bucket "{backup_bucket}" on 3rd Supabase')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Could not create bucket: {e}'))
                return False

        try:
            with open(db_file, 'rb') as f:
                file_bytes = f.read()
            backup_supabase.storage.from_(backup_bucket).upload(
                path=remote_path,
                file=file_bytes,
                file_options={"content-type": "application/octet-stream", "upsert": "true"}
            )
            self.stdout.write(f'  DB dump uploaded to 3rd Supabase: {backup_bucket}/{remote_path} ({len(file_bytes)} bytes)')

            # Retention: keep only last 15 DB dumps in this bucket
            try:
                existing = backup_supabase.storage.from_(backup_bucket).list('daily_backups')
                folders = sorted(
                    [e['name'] for e in existing if e.get('id') is None],
                    reverse=True
                )
                for old_folder in folders[15:]:
                    old_files = backup_supabase.storage.from_(backup_bucket).list(f'daily_backups/{old_folder}')
                    for of in old_files:
                        if of.get('name'):
                            backup_supabase.storage.from_(backup_bucket).remove(
                                [f'daily_backups/{old_folder}/{of["name"]}']
                            )
                    self.stdout.write(f'  Retention: removed old backup {old_folder} from 3rd Supabase')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Retention cleanup on 3rd Supabase failed: {e}'))

            return True
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Upload to 3rd Supabase failed: {e}'))
            return False

    def _create_zip_archive(self, archive_path, source_dir, log):
        """Create ZIP archive from the collected files."""
        manifest = {
            'backup_date': datetime.now().isoformat(),
            'database': {},
            'signup_pdfs': {'count': log.metadata.get('signup_pdf_count', 0)},
            'resources': {'count': log.metadata.get('resource_count', 0)},
            'dedup_skipped': log.metadata.get('files_skipped_duplicate', 0),
            'total_files_included': log.metadata.get('files_included', 0),
        }
        source_path = Path(source_dir)
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_path.rglob('*'):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(source_path))
                    zf.write(file_path, arcname)
                    if arcname.startswith('database/') and 'sql' in arcname:
                        manifest['database']['filename'] = file_path.name
                        manifest['database']['size'] = file_path.stat().st_size
            zf.writestr('manifest.json', json.dumps(manifest, indent=2))
        self.stdout.write(f'  Archive created: {archive_path}')
