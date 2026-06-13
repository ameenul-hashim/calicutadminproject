import os
import io
import hashlib
import logging
import subprocess
import socket
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _get_config(key, default=None):
    try:
        from django.conf import settings as s
        return getattr(s, key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def _drive_configured():
    """Check if any drive backend is configured (Google Drive or MEGA)."""
    gd = bool(os.getenv('GOOGLE_DRIVE_CREDENTIALS') or os.getenv('GOOGLE_DRIVE_CREDENTIALS_PATH'))
    oauth = bool(os.getenv('GOOGLE_DRIVE_CLIENT_ID') and os.getenv('GOOGLE_DRIVE_CLIENT_SECRET') and os.getenv('GOOGLE_DRIVE_REFRESH_TOKEN'))
    mega = bool(os.getenv('MEGA_EMAIL') and os.getenv('MEGA_PASSWORD'))
    return gd or oauth or mega


def _use_google_drive():
    """Returns True if Google Drive credentials are available."""
    return bool(os.getenv('GOOGLE_DRIVE_CREDENTIALS') or os.getenv('GOOGLE_DRIVE_CREDENTIALS_PATH') or
                (os.getenv('GOOGLE_DRIVE_CLIENT_ID') and os.getenv('GOOGLE_DRIVE_CLIENT_SECRET') and os.getenv('GOOGLE_DRIVE_REFRESH_TOKEN')))


def _get_drive_service():
    """Login to Google Drive or MEGA (auto-detects based on env vars).
    Returns service instance or None."""
    if _use_google_drive():
        from accounts.utils.google_drive_service import _login
        return _login()
    from accounts.utils.mega_backup_service import _login
    return _login()


def ensure_folder_path(service, path_parts):
    """Ensure a nested folder path exists in Google Drive or MEGA.
    Returns folder ID (Google Drive) or path string (MEGA)."""
    if _use_google_drive():
        from accounts.utils.google_drive_service import ensure_folder_path as gd_ensure
        return gd_ensure(service, path_parts)
    from accounts.utils.mega_backup_service import _ensure_path
    return _ensure_path(service, path_parts)


def upload_file(service, file_bytes, filename, mime_type, parent_id):
    """Upload a file to Google Drive or MEGA (auto-detected).
    Returns (file_identifier, None) on success, (None, error) on failure."""
    if _use_google_drive():
        from accounts.utils.google_drive_service import upload_file as gd_upload
        return gd_upload(service, file_bytes, filename, mime_type, parent_id)
    from accounts.utils.mega_backup_service import upload_bytes
    return upload_bytes(service, file_bytes, filename, parent_id)


def download_file(service, file_id):
    """Download a file from Google Drive or MEGA.
    Returns (bytes, error_message)."""
    if _use_google_drive():
        from accounts.utils.google_drive_service import download_file as gd_download
        return gd_download(service, file_id)
    from accounts.utils.mega_backup_service import download_file as mega_download
    return mega_download(service, file_id)


def compute_sha256(file_bytes):
    """Compute SHA256 hash of file bytes."""
    return hashlib.sha256(file_bytes).hexdigest()


def verify_file_integrity(file_bytes, expected_sha256=None):
    """Verify file integrity. Returns (is_valid, actual_sha256, error_message)."""
    try:
        actual_sha256 = compute_sha256(file_bytes)
        if expected_sha256 and actual_sha256 != expected_sha256:
            return False, actual_sha256, "SHA256 mismatch"
        return True, actual_sha256, None
    except Exception as e:
        return False, None, str(e)


def run_pg_dump(database_url=None):
    """Run pg_dump and return (sql_bytes, error_message, file_size)."""
    if not database_url:
        database_url = os.getenv('DATABASE_URL')
    if not database_url:
        return None, "DATABASE_URL not set", 0
    try:
        result = subprocess.run(
            ['pg_dump', '--no-owner', '--no-acl', '--clean', database_url, '-f', '-'],
            capture_output=True, timeout=120
        )
        if result.returncode != 0:
            return None, f"pg_dump failed: {result.stderr[:500]}", 0
        data = result.stdout
        return data, None, len(data)
    except FileNotFoundError:
        return None, "pg_dump not installed", 0
    except subprocess.TimeoutExpired:
        return None, "pg_dump timed out", 0
    except Exception as e:
        return None, str(e), 0


def run_pg_dump_fallback():
    """Fallback: use Django dumpdata if pg_dump is unavailable."""
    from io import StringIO
    from django.core import management
    try:
        buf = StringIO()
        management.call_command('dumpdata', stdout=buf, indent=2,
                                exclude=['contenttypes', 'auth.Permission'])
        data = buf.getvalue().encode('utf-8')
        return data, None, len(data)
    except Exception as e:
        return None, str(e), 0


def restore_to_backup_db(sql_bytes, backup_db_url=None):
    """Restore a pg_dump SQL dump to the backup Supabase PostgreSQL database.
    
    Uses BACKUP_DATABASE_URL env var if no URL is provided.
    Returns (success: bool, message: str).
    """
    if not backup_db_url:
        backup_db_url = os.getenv('BACKUP_DATABASE_URL')
    if not backup_db_url:
        return False, "BACKUP_DATABASE_URL not set"
    
    try:
        import psycopg2
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(backup_db_url)
        dbname = parsed.path.lstrip('/') or 'postgres'
        user = parsed.username or 'postgres'
        password = parsed.password or ''
        port = parsed.port or 5432
        host = parsed.hostname or 'localhost'
        qs = parse_qs(parsed.query)

        # Resolve hostname to IPv4 to avoid Render IPv6 connectivity issues
        ipv4 = None
        try:
            addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            if addrs:
                ipv4 = addrs[0][4][0]
        except Exception:
            pass

        # Build connection parameters
        conn_params = {
            'dbname': dbname,
            'user': user,
            'password': password,
            'port': port,
            'sslmode': qs.get('sslmode', ['require'])[0],
            'connect_timeout': 10,
        }

        if ipv4:
            conn_params['host'] = ipv4
        else:
            conn_params['host'] = host

        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql_bytes.decode('utf-8'))
        cur.close()
        conn.close()

        logger.info(f"Backup DB restore succeeded: {len(sql_bytes)} bytes restored")
        return True, None

    except psycopg2.OperationalError as e:
        err_str = str(e)
        if 'could not connect' in err_str.lower() or 'network is unreachable' in err_str.lower():
            # Try fallback: swap port (5432 ↔ 6543)
            fallback_port = 5432 if port == 6543 else 6543
            try:
                conn_params['port'] = fallback_port
                conn = psycopg2.connect(**conn_params)
                conn.autocommit = True
                cur = conn.cursor()
                cur.execute(sql_bytes.decode('utf-8'))
                cur.close()
                conn.close()
                logger.info(f"Backup DB restore succeeded via port {fallback_port}: {len(sql_bytes)} bytes restored")
                return True, None
            except Exception as e2:
                return False, f"psycopg2 restore failed: {e2}"
        return False, f"psycopg2 restore failed: {err_str}"
    except Exception as e:
        return False, f"psycopg2 restore failed: {e}"


def delete_old_backups(service, folder_path, keep_count=30):
    """Delete old backups beyond keep_count using BackupLog.
    Supports both Google Drive and MEGA.
    Returns number of backups cleaned up."""
    from accounts.models import BackupLog
    deleted = 0
    try:
        if _use_google_drive():
            from accounts.utils.google_drive_service import delete_file as gd_delete
            old_logs = BackupLog.objects.filter(
                status='SUCCESS',
                drive_folder_path__isnull=False,
            ).exclude(drive_file_id__startswith='mega://').order_by('-created_at')
            if old_logs.count() <= keep_count:
                return 0
            old_logs = list(old_logs[keep_count:])
            for log in old_logs:
                try:
                    ok = gd_delete(service, log.drive_file_id)
                    if ok:
                        log.status = 'CLEANED'
                        log.save(update_fields=['status'])
                        deleted += 1
                        logger.info(f'Retention: cleaned old backup {log.filename}')
                except Exception as e:
                    logger.warning(f'Retention delete failed for {log.filename}: {e}')
        else:
            from . import mega_backup_service
            old_logs = BackupLog.objects.filter(
                status='SUCCESS',
                drive_file_id__startswith='mega://',
            ).order_by('-created_at')
            if old_logs.count() <= keep_count:
                return 0
            old_logs = list(old_logs[keep_count:])
            for log in old_logs:
                try:
                    ok = mega_backup_service.delete_file(service, log.drive_file_id)
                    if ok:
                        log.status = 'CLEANED'
                        log.save(update_fields=['status'])
                        deleted += 1
                        logger.info(f'Retention: cleaned old backup {log.filename}')
                except Exception as e:
                    logger.warning(f'Retention delete failed for {log.filename}: {e}')
    except Exception as e:
        logger.error(f'Retention cleanup error: {e}')
    return deleted
