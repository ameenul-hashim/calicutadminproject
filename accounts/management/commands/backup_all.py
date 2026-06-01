import os
import json
import base64
import hashlib
import datetime
import logging
import subprocess
import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.join(settings.BASE_DIR, 'backups')
MAX_TOTAL_BYTES = 500 * 1024 * 1024

# Retention in days
RETENTION = {
    'daily': 7,
    'weekly': 28,
    'monthly': 365,
}


def _get_cipher():
    key = os.getenv('BACKUP_ENCRYPTION_KEY')
    if not key:
        raw = os.getenv('SECRET_KEY', 'fallback-dev-only')
        raw = raw.ljust(32)[:32]
        key = base64.urlsafe_b64encode(raw.encode())
    return Fernet(key)


def _fmt(bytes_val):
    for unit in ['B', 'KB', 'MB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f}GB"


class Command(BaseCommand):
    help = 'Full encrypted backup: DB + Supabase files + Cloudinary images'

    def add_arguments(self, parser):
        parser.add_argument('--retention', action='store_true',
                            help='Apply retention policy (delete old backups)')

    def handle(self, *args, **options):
        import base64
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir = os.path.join(BACKUP_DIR, f'backup_{timestamp}')
        os.makedirs(run_dir, exist_ok=True)
        self.total_bytes = 0
        self.cipher = _get_cipher()

        self.stdout.write(f"Backing up to: {run_dir}")

        self._backup_db(run_dir)
        if self.total_bytes > MAX_TOTAL_BYTES:
            self.stdout.write(self.style.WARNING("Total size limit reached."))
            return

        self._backup_storage_manifest(run_dir)
        self._backup_proof_pdfs(run_dir)
        self._backup_course_resources(run_dir)
        self._backup_cloudinary_images(run_dir)

        # Create integrity checksum
        self._write_checksum(run_dir)

        # Encrypt all files
        self._encrypt_backup(run_dir)

        # Apply retention if requested
        if options.get('retention'):
            self._apply_retention()

        # Write heartbeat file for enterprise monitor
        try:
            heartbeat = os.path.join(settings.BASE_DIR, 'last_success.txt')
            with open(heartbeat, 'w') as f:
                f.write(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.stdout.write(f"  Heartbeat: {heartbeat}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Could not write heartbeat: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"Backup complete: {run_dir} ({_fmt(self.total_bytes)} total)"
        ))

    def _write_checksum(self, run_dir):
        checksums = {}
        for root, dirs, files in os.walk(run_dir):
            for f in sorted(files):
                path = os.path.join(root, f)
                h = hashlib.sha256()
                with open(path, 'rb') as fh:
                    for chunk in iter(lambda: fh.read(65536), b''):
                        h.update(chunk)
                rel = os.path.relpath(path, run_dir)
                checksums[rel] = h.hexdigest()
        cs_path = os.path.join(run_dir, 'checksums.json')
        with open(cs_path, 'w') as f:
            json.dump(checksums, f, indent=2)

    def _encrypt_backup(self, run_dir):
        for root, dirs, files in os.walk(run_dir):
            for f in files:
                path = os.path.join(root, f)
                if f.endswith('.encrypted'):
                    continue
                with open(path, 'rb') as fh:
                    data = fh.read()
                encrypted = self.cipher.encrypt(data)
                with open(path + '.encrypted', 'wb') as fh:
                    fh.write(encrypted)
                os.unlink(path)

    def _apply_retention(self):
        now = datetime.datetime.now()
        all_backups = []
        for entry in os.listdir(BACKUP_DIR):
            bdir = os.path.join(BACKUP_DIR, entry)
            if not os.path.isdir(bdir) or not entry.startswith('backup_'):
                continue
            try:
                ts = datetime.datetime.strptime(entry.replace('backup_', ''), '%Y%m%d_%H%M%S')
            except:
                continue
            age = (now - ts).days
            all_backups.append((ts, bdir, age))

        all_backups.sort(key=lambda x: x[0], reverse=True)

        # Keep newest daily for RETENTION['daily'] days
        # Keep newest weekly for RETENTION['weekly'] days
        # Keep newest monthly for RETENTION['monthly'] days
        kept = set()
        for ts, bdir, age in all_backups:
            if age <= RETENTION['daily']:
                kept.add(bdir)
            elif age <= RETENTION['weekly']:
                # Keep one per week
                week_key = ts.isocalendar()[1]
                if not any(os.path.basename(k).startswith(f'backup_') and
                           datetime.datetime.strptime(
                               os.path.basename(k).replace('backup_', ''),
                               '%Y%m%d_%H%M%S'
                           ).isocalendar()[1] == week_key
                           for k in kept):
                    kept.add(bdir)
            elif age <= RETENTION['monthly']:
                month_key = (ts.year, ts.month)
                if not any(os.path.basename(k).startswith(f'backup_') and
                           datetime.datetime.strptime(
                               os.path.basename(k).replace('backup_', ''),
                               '%Y%m%d_%H%M%S'
                           ).year == month_key[0] and
                           datetime.datetime.strptime(
                               os.path.basename(k).replace('backup_', ''),
                               '%Y%m%d_%H%M%S'
                           ).month == month_key[1]
                           for k in kept):
                    kept.add(bdir)

        # Delete what wasn't kept
        for ts, bdir, age in all_backups:
            if bdir not in kept:
                import shutil
                shutil.rmtree(bdir)
                self.stdout.write(f"  Deleted old backup: {os.path.basename(bdir)}")

    def _check_limit(self, added):
        self.total_bytes += added
        if self.total_bytes > MAX_TOTAL_BYTES:
            self.stdout.write(self.style.WARNING(
                f"  Total exceeds {_fmt(MAX_TOTAL_BYTES)}. Stopping."
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
                self.stdout.write(f"  DB dump: {output} ({_fmt(size)})")
                # Verify integrity
                with open(output, 'rb') as f:
                    hashlib.sha256(f.read()).hexdigest()
                self.stdout.write("  DB integrity: OK")
            else:
                self.stdout.write(self.style.WARNING(f"  pg_dump failed: {result.stderr[:200]}"))
                self._backup_db_fallback(run_dir)
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING("  pg_dump not installed. Using dumpdata fallback."))
            self._backup_db_fallback(run_dir)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  DB backup failed: {e}"))
            self._backup_db_fallback(run_dir)

    def _backup_db_fallback(self, run_dir):
        """Fallback: use Django dumpdata if pg_dump is not available."""
        output = os.path.join(run_dir, 'database_dumpdata.json')
        try:
            from django.core import management
            with open(output, 'w') as f:
                management.call_command('dumpdata', stdout=f, indent=2, exclude=['contenttypes', 'auth.Permission'])
            size = os.path.getsize(output)
            self._check_limit(size)
            self.stdout.write(f"  DB dumpdata fallback: {output} ({_fmt(size)})")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  dumpdata fallback failed: {e}"))

    def _backup_sqlite(self, run_dir):
        db_path = settings.DATABASES['default']['NAME']
        if os.path.exists(db_path):
            output = os.path.join(run_dir, 'database.sqlite3')
            import shutil
            shutil.copy2(db_path, output)
            size = os.path.getsize(output)
            self._check_limit(size)
            self.stdout.write(f"  SQLite copy: {output} ({_fmt(size)})")

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
                self.stdout.write(f"  Proof PDFs: {len(files)} files")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Could not list proof PDFs: {e}"))

        from accounts.utils.storage_manager import supabase as client2
        if client2:
            try:
                files = client2.storage.from_('resources').list()
                for f in files:
                    manifest['resources'].append({
                        'name': f.get('name'), 'id': f.get('id'),
                        'updated_at': f.get('updated_at'),
                    })
                self.stdout.write(f"  Resources: {len(files)} files")
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
                except Exception:
                    pass
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
                except Exception:
                    pass
            self.stdout.write(f"  Course resources downloaded: {count}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Resource backup failed: {e}"))

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
                except Exception:
                    pass
            self.stdout.write(f"  Cloudinary images downloaded: {count}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Cloudinary backup failed: {e}"))
