import os
import json
import time
import logging
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import BackupLog
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
    help = 'Daily backup - DB dump to 3rd Supabase bucket only (no file downloads, no ZIP, no Drive)'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force backup even if already ran today')
        parser.add_argument('--skip-retention', action='store_true', help='Skip old backup cleanup')

    def handle(self, *args, **options):
        force = options.get('force', False)
        skip_retention = options.get('skip_retention', False)

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
        temp_dir = tempfile.mkdtemp(prefix='daily_backup_')
        db_dir = os.path.join(temp_dir, 'database')
        os.makedirs(db_dir, exist_ok=True)

        log = BackupLog.objects.create(
            backup_type='DAILY_FULL',
            filename='db_dump',
            status='RUNNING',
            metadata={
                'started_at': datetime.now().isoformat(),
                'database_size': 0,
            },
        )

        try:
            self.stdout.write('Step 1/2: Dumping database...')
            self._dump_database(db_dir, log)
            db_files = list(Path(db_dir).iterdir())
            db_size = sum(f.stat().st_size for f in db_files if f.is_file())
            log.metadata['database_size'] = db_size

            log.status = 'UPLOADING'
            log.file_size = db_size
            log.save(update_fields=['status', 'file_size', 'metadata'])

            self.stdout.write(f'Step 2/2: Uploading DB dump to 3rd Supabase bucket...')
            db_uploaded = self._upload_db_to_backup_supabase(db_dir)

            log.status = 'SUCCESS'
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.metadata['backup_supabase_uploaded'] = db_uploaded
            log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'metadata'])

            self.stdout.write(self.style.SUCCESS(
                f'Daily backup complete: DB dump ({db_size} bytes), upload={db_uploaded}'
            ))

        except Exception as e:
            log.status = 'FAILED'
            log.error_message = str(e)[:500]
            log.completed_at = timezone.now()
            log.duration_seconds = time.time() - start_time
            log.save(update_fields=['status', 'error_message', 'completed_at', 'duration_seconds'])
            self.stdout.write(self.style.ERROR(f'Daily backup failed: {e}'))
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

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
        log.filename = filename
        log.save(update_fields=['filename'])
        self.stdout.write(f'  Database dump: {filename} ({file_size} bytes)')

    def _upload_db_to_backup_supabase(self, db_dir):
        """Upload database dump file to 3rd Supabase storage bucket.
        Uses direct HTTP requests for bucket management (supabase-py v2.x
        storage API has URL construction issues for bucket CRUD).
        Returns True if uploaded, False if skipped or failed."""
        import requests as req

        backup_url = os.getenv('BACKUP_SUPABASE_URL', '').rstrip('/').replace('/rest/v1', '')
        backup_key = os.getenv('BACKUP_SUPABASE_KEY', '')
        if not backup_url or not backup_key:
            self.stdout.write('  Backup Supabase (3rd): skipped (BACKUP_SUPABASE_URL/KEY not set)')
            return False

        db_files = list(Path(db_dir).iterdir())
        if not db_files:
            self.stdout.write('  Backup Supabase (3rd): no database dump file found')
            return False

        db_file = db_files[0]
        file_name = db_file.name
        remote_path = f'daily_backups/{datetime.now().strftime("%Y/%m/%d")}/{file_name}'
        headers = {
            'Authorization': f'Bearer {backup_key}',
            'Content-Type': 'application/json',
        }

        # Check/create bucket via direct HTTP (supabase-py storage API has URL issues)
        try:
            r = req.get(f'{backup_url}/storage/v1/bucket/{backup_bucket}', headers=headers)
            if r.status_code == 404:
                r2 = req.post(f'{backup_url}/storage/v1/bucket', headers=headers, json={'name': backup_bucket, 'public': False})
                if r2.status_code in (200, 201):
                    self.stdout.write(f'  Created bucket "{backup_bucket}" on 3rd Supabase')
                else:
                    self.stdout.write(self.style.WARNING(f'  Could not create bucket: {r2.text}'))
                    return False
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Bucket check/create failed: {e}'))
            return False

        # Upload file — try direct HTTP first, then SDK fallback
        try:
            if not backup_url or not backup_key:
                self.stdout.write('  Backup Supabase (3rd): skipped (BACKUP_SUPABASE_URL/KEY not set)')
                return False
            with open(db_file, 'rb') as f:
                file_bytes = f.read()

            uploaded = False
            upload_url = f'{backup_url}/storage/v1/object/{backup_bucket}/{remote_path}'
            # Try direct HTTP
            upload_headers = {
                'Authorization': f'Bearer {backup_key}',
                'apikey': backup_key,
                'Content-Type': 'application/octet-stream',
            }
            r = req.post(upload_url, headers=upload_headers, data=file_bytes, timeout=30)
            if r.status_code in (200, 201):
                uploaded = True
            else:
                self.stdout.write(f'  Direct HTTP upload failed ({r.status_code}): {r.text[:200]} for URL: {upload_url}')

            # Fallback: try SDK
            if not uploaded and backup_supabase:
                try:
                    backup_supabase.storage.from_(backup_bucket).upload(
                        path=remote_path,
                        file=file_bytes,
                        file_options={"content-type": "application/octet-stream", "upsert": "true"}
                    )
                    uploaded = True
                except Exception:
                    pass

            if not uploaded:
                self.stdout.write(self.style.WARNING(f'  Upload failed: {r.status_code} {r.text}'))
                return False

            self.stdout.write(f'  DB dump uploaded to 3rd Supabase: {backup_bucket}/{remote_path} ({len(file_bytes)} bytes)')

            # Retention: keep only last 15 DB dumps
            try:
                list_headers = {
                    'Authorization': f'Bearer {backup_key}',
                    'apikey': backup_key,
                }
                r_list = req.get(f'{backup_url}/storage/v1/object/list/{backup_bucket}',
                                 headers=list_headers,
                                 params={'prefix': 'daily_backups/'})
                if r_list.status_code == 200:
                    existing = r_list.json()
                    folders = sorted(
                        set(e['name'].split('/')[1] for e in existing if '/' in e.get('name', '')),
                        reverse=True
                    )
                    for old_folder in folders[15:]:
                        r_old = req.get(f'{backup_url}/storage/v1/object/list/{backup_bucket}',
                                        headers=list_headers,
                                        params={'prefix': f'daily_backups/{old_folder}/'})
                        if r_old.status_code == 200:
                            for of in r_old.json():
                                if of.get('name'):
                                    del_path = f'{backup_bucket}/{of["name"]}'
                                    req.delete(f'{backup_url}/storage/v1/object/{del_path}',
                                              headers=list_headers)
                            self.stdout.write(f'  Retention: removed old backup {old_folder} from 3rd Supabase')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Retention cleanup on 3rd Supabase failed: {e}'))

            return True
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Upload to 3rd Supabase failed: {e}'))
            return False
