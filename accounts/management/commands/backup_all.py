import os
import json
import datetime
import logging
import subprocess
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.join(settings.BASE_DIR, 'backups')


class Command(BaseCommand):
    help = 'Backup database + storage metadata to local disk'

    def handle(self, *args, **options):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir = os.path.join(BACKUP_DIR, f'backup_{timestamp}')
        os.makedirs(run_dir, exist_ok=True)

        self.stdout.write(f"Backing up to: {run_dir}")

        # 1. Database dump
        self._backup_db(run_dir)

        # 2. Storage manifest (proof PDFs + course resources)
        self._backup_storage_manifest(run_dir)

        # 3. Download proof PDFs (small files, Client 1)
        self._backup_proof_pdfs(run_dir)

        self.stdout.write(self.style.SUCCESS(f"Backup complete: {run_dir}"))

    def _backup_db(self, run_dir):
        db_url = os.getenv('DATABASE_URL')
        if db_url and db_url.startswith('postgres'):
            self._backup_postgres(db_url, run_dir)
        else:
            self._backup_sqlite(run_dir)

    def _backup_postgres(self, db_url, run_dir):
        output = os.path.join(run_dir, 'database.sql')
        try:
            env = os.environ.copy()
            env['PGPASSWORD'] = ''
            result = subprocess.run(
                ['pg_dump', '--no-owner', '--no-acl', db_url, '-f', output],
                capture_output=True, text=True, timeout=120, env=env
            )
            if result.returncode == 0:
                size = os.path.getsize(output)
                self.stdout.write(f"  DB dump: {output} ({self._fmt(size)})")
            else:
                self.stdout.write(self.style.WARNING(f"  pg_dump failed: {result.stderr[:200]}"))
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING("  pg_dump not installed. Skipping PostgreSQL dump."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  DB backup failed: {e}"))

    def _backup_sqlite(self, run_dir):
        db_path = settings.DATABASES['default']['NAME']
        if os.path.exists(db_path):
            output = os.path.join(run_dir, 'database.sqlite3')
            import shutil
            shutil.copy2(db_path, output)
            size = os.path.getsize(output)
            self.stdout.write(f"  SQLite copy: {output} ({self._fmt(size)})")

    def _backup_storage_manifest(self, run_dir):
        manifest = {
            'proof_pdfs': [],
            'resources': [],
            'generated_at': datetime.datetime.utcnow().isoformat(),
        }

        # Client 1: proof PDFs (supabase_storage)
        from accounts.utils.supabase_storage import supabase as client1
        bucket = os.getenv('SUPABASE_BUCKET', 'calicutadminpanelpdf')
        if client1:
            try:
                files = client1.storage.from_(bucket).list()
                for f in files:
                    manifest['proof_pdfs'].append({
                        'name': f.get('name'),
                        'id': f.get('id'),
                        'updated_at': f.get('updated_at'),
                    })
                self.stdout.write(f"  Proof PDFs in bucket '{bucket}': {len(files)} files")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Could not list proof PDFs: {e}"))

        # Client 2: course resources (storage_manager)
        from accounts.utils.storage_manager import supabase as client2
        if client2:
            try:
                buckets = ['resources']
                for b in buckets:
                    files = client2.storage.from_(b).list()
                    for f in files:
                        manifest['resources'].append({
                            'bucket': b,
                            'name': f.get('name'),
                            'id': f.get('id'),
                            'updated_at': f.get('updated_at'),
                        })
                    self.stdout.write(f"  Resources in bucket '{b}': {len(files)} files")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Could not list resources: {e}"))

        manifest_path = os.path.join(run_dir, 'storage_manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2, default=str)
        self.stdout.write(f"  Manifest: {manifest_path}")

    def _backup_proof_pdfs(self, run_dir):
        from accounts.utils.supabase_storage import supabase as client1
        bucket = os.getenv('SUPABASE_BUCKET', 'calicutadminpanelpdf')
        if not client1:
            return

        pdf_dir = os.path.join(run_dir, 'proof_pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        count = 0

        try:
            files = client1.storage.from_(bucket).list()
            for f in files:
                name = f.get('name', '')
                if not name:
                    continue
                try:
                    data = client1.storage.from_(bucket).download(name)
                    if data:
                        safe_name = name.replace('/', '_').replace('\\', '_')
                        out_path = os.path.join(pdf_dir, safe_name)
                        with open(out_path, 'wb') as out:
                            out.write(data)
                        count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    Skipped {name}: {e}"))
            self.stdout.write(f"  Proof PDFs downloaded: {count}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Proof PDF backup failed: {e}"))

    def _fmt(self, bytes_val):
        for unit in ['B', 'KB', 'MB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f}GB"
