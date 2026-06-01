import os
import json
import datetime
import logging
import subprocess
import requests
from dotenv import load_dotenv
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)
load_dotenv()

BACKUP_DIR = os.path.join(settings.BASE_DIR, 'backups')
MAX_TOTAL_BYTES = 500 * 1024 * 1024  # stop if total exceeds 500MB


class Command(BaseCommand):
    help = 'Full backup: DB + Supabase storage files + Cloudinary images'

    def handle(self, *args, **options):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir = os.path.join(BACKUP_DIR, f'backup_{timestamp}')
        os.makedirs(run_dir, exist_ok=True)
        self.total_bytes = 0

        self.stdout.write(f"Backing up to: {run_dir}")

        self._backup_db(run_dir)
        if self.total_bytes > MAX_TOTAL_BYTES:
            self.stdout.write(self.style.WARNING("  Total size limit reached. Skipping remaining backups."))
            return

        self._backup_storage_manifest(run_dir)
        self._backup_proof_pdfs(run_dir)
        self._backup_course_resources(run_dir)
        self._backup_cloudinary_images(run_dir)

        self.stdout.write(self.style.SUCCESS(
            f"Backup complete: {run_dir} ({self._fmt(self.total_bytes)} total)"
        ))

    def _check_limit(self, added):
        self.total_bytes += added
        if self.total_bytes > MAX_TOTAL_BYTES:
            self.stdout.write(self.style.WARNING(
                f"  Total backup size ({self._fmt(self.total_bytes)}) exceeds {self._fmt(MAX_TOTAL_BYTES)}. Stopping."
            ))

    def _backup_db(self, run_dir):
        db_url = os.getenv('DATABASE_URL')
        if db_url and db_url.startswith('postgres'):
            self._backup_postgres(db_url, run_dir)
        else:
            self._backup_sqlite(run_dir)

    def _backup_postgres(self, db_url, run_dir):
        output = os.path.join(run_dir, 'database.sql')
        try:
            result = subprocess.run(
                ['pg_dump', '--no-owner', '--no-acl', db_url, '-f', output],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                size = os.path.getsize(output)
                self._check_limit(size)
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
            self._check_limit(size)
            self.stdout.write(f"  SQLite copy: {output} ({self._fmt(size)})")

    def _backup_storage_manifest(self, run_dir):
        import cloudinary
        cloudinary.config(
            cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
            api_key=os.getenv('CLOUDINARY_API_KEY'),
            api_secret=os.getenv('CLOUDINARY_API_SECRET'),
        )
        manifest = {
            'proof_pdfs': [], 'resources': [], 'cloudinary_images': [],
            'generated_at': datetime.datetime.utcnow().isoformat(),
        }

        from accounts.utils.supabase_storage import supabase as client1
        bucket = os.getenv('SUPABASE_BUCKET', 'calicutadminpanelpdf')
        if client1:
            try:
                files = client1.storage.from_(bucket).list()
                for f in files:
                    manifest['proof_pdfs'].append({
                        'name': f.get('name'), 'id': f.get('id'),
                        'updated_at': f.get('updated_at'),
                    })
                self.stdout.write(f"  Proof PDFs in bucket '{bucket}': {len(files)} files")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Could not list proof PDFs: {e}"))

        from accounts.utils.storage_manager import supabase as client2
        if client2:
            try:
                for b in ['resources']:
                    files = client2.storage.from_(b).list()
                    for f in files:
                        manifest['resources'].append({
                            'bucket': b, 'name': f.get('name'),
                            'id': f.get('id'), 'updated_at': f.get('updated_at'),
                        })
                    self.stdout.write(f"  Resources in bucket '{b}': {len(files)} files")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Could not list resources: {e}"))

        try:
            import cloudinary.api
            result = cloudinary.api.resources(type='upload', max_results=500)
            for r in result.get('resources', []):
                manifest['cloudinary_images'].append({
                    'public_id': r.get('public_id'),
                    'format': r.get('format'),
                    'bytes': r.get('bytes'),
                    'url': r.get('secure_url'),
                    'created_at': r.get('created_at'),
                })
            total = len(result.get('resources', []))
            self.stdout.write(f"  Cloudinary images: {total}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Could not list Cloudinary images: {e}"))

        manifest_path = os.path.join(run_dir, 'storage_manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2, default=str)
        size = os.path.getsize(manifest_path)
        self._check_limit(size)
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
                        self._check_limit(len(data))
                        count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    Skipped {name}: {e}"))
            self.stdout.write(f"  Proof PDFs downloaded: {count}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Proof PDF backup failed: {e}"))

    def _backup_course_resources(self, run_dir):
        from accounts.utils.storage_manager import supabase as client2
        if not client2:
            return
        res_dir = os.path.join(run_dir, 'course_resources')
        os.makedirs(res_dir, exist_ok=True)
        count = 0
        try:
            files = client2.storage.from_('resources').list()
            for f in files:
                name = f.get('name', '')
                if not name:
                    continue
                try:
                    data = client2.storage.from_('resources').download(name)
                    if data:
                        safe_name = name.replace('/', '_').replace('\\', '_')
                        out_path = os.path.join(res_dir, safe_name)
                        with open(out_path, 'wb') as out:
                            out.write(data)
                        self._check_limit(len(data))
                        count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    Skipped {name}: {e}"))
            self.stdout.write(f"  Course resources downloaded: {count}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Course resource backup failed: {e}"))

    def _backup_cloudinary_images(self, run_dir):
        import cloudinary
        cloudinary.config(
            cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
            api_key=os.getenv('CLOUDINARY_API_KEY'),
            api_secret=os.getenv('CLOUDINARY_API_SECRET'),
        )
        img_dir = os.path.join(run_dir, 'cloudinary_images')
        os.makedirs(img_dir, exist_ok=True)
        count = 0
        try:
            import cloudinary.api
            result = cloudinary.api.resources(type='upload', max_results=500)
            for r in result.get('resources', []):
                url = r.get('secure_url')
                public_id = r.get('public_id', 'unknown')
                if not url:
                    continue
                try:
                    resp = requests.get(url, timeout=30)
                    if resp.status_code == 200:
                        safe_name = public_id.replace('/', '_') + '.' + (r.get('format') or 'jpg')
                        out_path = os.path.join(img_dir, safe_name)
                        with open(out_path, 'wb') as out:
                            out.write(resp.content)
                        self._check_limit(len(resp.content))
                        count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    Skipped {public_id}: {e}"))
            self.stdout.write(f"  Cloudinary images downloaded: {count}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Cloudinary backup failed: {e}"))

    def _fmt(self, bytes_val):
        for unit in ['B', 'KB', 'MB']:
            if bytes_val < 1024:
                return f"{bytes_val:.1f}{unit}"
            bytes_val /= 1024
        return f"{bytes_val:.1f}GB"
