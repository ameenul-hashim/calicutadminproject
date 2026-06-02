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
        raise ValueError(
            "BACKUP_ENCRYPTION_KEY environment variable is required. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _fmt(bytes_val):
    for unit in ['B', 'KB', 'MB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f}GB"


class Command(BaseCommand):
    help = 'Full encrypted backup: DB + Supabase files + Cloudinary images + Firebase RTDB'

    def add_arguments(self, parser):
        parser.add_argument('--retention', action='store_true',
                            help='Apply retention policy (delete old backups)')
        parser.add_argument('--cron', action='store_true',
                            help='Cron mode: skip local file downloads (DB dump + Firebase + cloud upload only)')

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

        cron_mode = options.get('cron', False)

        if cron_mode:
            # Cron mode: only backup critical data (fast)
            self.stdout.write("  Cron mode: skipping local file downloads")
        else:
            # Full mode: download all files locally
            self._backup_storage_manifest(run_dir)
            self._backup_proof_pdfs(run_dir)
            self._backup_course_resources(run_dir)
            self._backup_cloudinary_images(run_dir)

        self._backup_firebase_rtdb(run_dir)

        # Create integrity checksum
        self._write_checksum(run_dir)

        # Encrypt all files
        self._encrypt_backup(run_dir)

        # Upload critical files to Supabase (survives Render deletion)
        self._upload_to_supabase(run_dir)

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
            'firebase_rtdb': {},
            'generated_at': datetime.datetime.utcnow().isoformat(),
        }

        from accounts.utils.supabase_storage import supabase as client1
        bucket = os.getenv('SUPABASE_BUCKET', 'calicutadminpanelpdf')
        if client1:
            try:
                files = self._supabase_list_all_files(client1, bucket)
                for f in files:
                    manifest['proof_pdfs'].append({
                        'name': f['name'], 'id': f['meta'].get('id'),
                        'updated_at': f['meta'].get('updated_at'),
                    })
                self.stdout.write(f"  Proof PDFs: {len(files)} files")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Could not list proof PDFs: {e}"))

        from accounts.utils.storage_manager import supabase as client2
        if client2:
            try:
                files = self._supabase_list_all_files(client2, 'resources')
                for f in files:
                    manifest['resources'].append({
                        'name': f['name'], 'id': f['meta'].get('id'),
                        'updated_at': f['meta'].get('updated_at'),
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

    def _supabase_list_all_files(self, client, bucket, path=''):
        """Recursively list all files in a Supabase bucket folder."""
        all_files = []
        try:
            entries = client.storage.from_(bucket).list(path)
            for entry in entries:
                name = entry.get('name', '')
                if not name:
                    continue
                full_path = f"{path}/{name}" if path else name
                # If id is None, it's a folder — recurse
                if entry.get('id') is None:
                    sub_files = self._supabase_list_all_files(client, bucket, full_path)
                    all_files.extend(sub_files)
                else:
                    all_files.append({'name': full_path, 'meta': entry})
        except Exception:
            pass
        return all_files

    def _backup_proof_pdfs(self, run_dir):
        from accounts.utils.supabase_storage import supabase as client1
        bucket = os.getenv('SUPABASE_BUCKET', 'calicutadminpanelpdf')
        if not client1:
            return
        pdf_dir = os.path.join(run_dir, 'proof_pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        count = 0
        try:
            files = self._supabase_list_all_files(client1, bucket)
            for f in files:
                name = f['name']
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
            files = self._supabase_list_all_files(client2, 'resources')
            for f in files:
                name = f['name']
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

    def _backup_firebase_rtdb(self, run_dir):
        """Export Firebase RTDB: /audit (security events) and /analytics (visit counts)."""
        db_url = os.getenv('FIREBASE_RTDB_URL')
        if not db_url:
            self.stdout.write("  Firebase RTDB: skipped (FIREBASE_RTDB_URL not set)")
            return

        try:
            import firebase_admin
            from firebase_admin import credentials, db as rtdb
        except ImportError:
            self.stdout.write(self.style.WARNING("  Firebase RTDB: skipped (firebase-admin not installed)"))
            return

        # Initialize Firebase app (reuse existing if available)
        app = None
        try:
            json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
            json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            cred = None
            if json_str:
                cred = credentials.Certificate(json.loads(json_str))
            elif json_path and os.path.exists(json_path):
                cred = credentials.Certificate(json_path)

            if cred:
                # Try to get existing app, or initialize new one
                try:
                    app = firebase_admin.get_app('backup')
                except ValueError:
                    app = firebase_admin.initialize_app(
                        cred, {'databaseURL': db_url}, name='backup'
                    )
            else:
                self.stdout.write(self.style.WARNING("  Firebase RTDB: skipped (no credentials)"))
                return
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Firebase RTDB init failed: {e}"))
            return

        firebase_dir = os.path.join(run_dir, 'firebase_rtdb')
        os.makedirs(firebase_dir, exist_ok=True)

        # Export /audit (security events + counters + infra status)
        audit_exported = False
        try:
            ref = rtdb.reference('/audit', app=app)
            audit_data = ref.get()
            if audit_data:
                audit_path = os.path.join(firebase_dir, 'audit_events.json')
                with open(audit_path, 'w') as f:
                    json.dump(audit_data, f, indent=2, default=str)
                size = os.path.getsize(audit_path)
                self._check_limit(size)
                self.stdout.write(f"  Firebase /audit: exported ({_fmt(size)})")
                audit_exported = True
            else:
                self.stdout.write("  Firebase /audit: empty")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Firebase /audit backup failed: {e}"))

        # Export /analytics (visit counts)
        analytics_exported = False
        try:
            ref = rtdb.reference('/analytics', app=app)
            analytics_data = ref.get()
            if analytics_data:
                analytics_path = os.path.join(firebase_dir, 'analytics.json')
                with open(analytics_path, 'w') as f:
                    json.dump(analytics_data, f, indent=2, default=str)
                size = os.path.getsize(analytics_path)
                self._check_limit(size)
                self.stdout.write(f"  Firebase /analytics: exported ({_fmt(size)})")
                analytics_exported = True
            else:
                self.stdout.write("  Firebase /analytics: empty")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  Firebase /analytics backup failed: {e}"))

        if not audit_exported and not analytics_exported:
            self.stdout.write(self.style.WARNING("  Firebase RTDB: no data exported"))

    def _upload_to_supabase(self, run_dir):
        """Upload critical backup files to Supabase Storage (survives Render deletion)."""
        from accounts.utils.supabase_storage import supabase
        if not supabase:
            self.stdout.write(self.style.WARNING("  Supabase upload: skipped (not configured)"))
            return

        bucket = 'backups'
        timestamp = os.path.basename(run_dir)  # backup_YYYYMMDD_HHMMSS
        uploaded = 0

        # Ensure bucket exists
        try:
            supabase.storage.get_bucket(bucket)
        except Exception:
            try:
                supabase.storage.create_bucket(bucket, options={"public": False})
                self.stdout.write(f"  Created Supabase bucket: {bucket}")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Could not create bucket '{bucket}': {e}"))
                return

        # Files to upload (find .encrypted versions first, fall back to originals)
        files_to_upload = []
        for pattern in ['database.sql.encrypted', 'database.sql',
                        'database_dumpdata.json.encrypted', 'database_dumpdata.json']:
            path = os.path.join(run_dir, pattern)
            if os.path.exists(path):
                files_to_upload.append(('database.sql', path))
                break

        for pattern in ['checksums.json.encrypted', 'checksums.json']:
            path = os.path.join(run_dir, pattern)
            if os.path.exists(path):
                files_to_upload.append(('checksums.json', path))
                break

        for pattern in ['storage_manifest.json.encrypted', 'storage_manifest.json']:
            path = os.path.join(run_dir, pattern)
            if os.path.exists(path):
                files_to_upload.append(('storage_manifest.json', path))
                break

        # Firebase files
        firebase_dir = os.path.join(run_dir, 'firebase_rtdb')
        if os.path.isdir(firebase_dir):
            for fname in os.listdir(firebase_dir):
                fpath = os.path.join(firebase_dir, fname)
                if os.path.isfile(fpath):
                    upload_name = fname.replace('.encrypted', '') if fname.endswith('.encrypted') else fname
                    files_to_upload.append((f'firebase_rtdb/{upload_name}', fpath))

        # Upload each file
        for remote_name, local_path in files_to_upload:
            remote_path = f'{timestamp}/{remote_name}'
            try:
                with open(local_path, 'rb') as f:
                    file_data = f.read()
                supabase.storage.from_(bucket).upload(
                    path=remote_path,
                    file=file_data,
                    file_options={"content-type": "application/octet-stream", "upsert": "true"}
                )
                size = len(file_data)
                self.stdout.write(f"  Supabase upload: {remote_name} ({_fmt(size)})")
                uploaded += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  Supabase upload failed for {remote_name}: {e}"))

        # Cleanup: keep only last 7 backups in Supabase
        try:
            existing = supabase.storage.from_(bucket).list()
            backup_folders = sorted(
                [e['name'] for e in existing if e.get('id') is None],
                reverse=True
            )
            for old_folder in backup_folders[7:]:
                try:
                    old_files = supabase.storage.from_(bucket).list(old_folder)
                    for of in old_files:
                        if of.get('name'):
                            supabase.storage.from_(bucket).remove([f"{old_folder}/{of['name']}"])
                    self.stdout.write(f"  Supabase cleanup: removed {old_folder}")
                except Exception:
                    pass
        except Exception:
            pass

        if uploaded:
            self.stdout.write(f"  Supabase cloud backup: {uploaded} files uploaded")
        else:
            self.stdout.write(self.style.WARNING("  Supabase cloud backup: no files uploaded"))
