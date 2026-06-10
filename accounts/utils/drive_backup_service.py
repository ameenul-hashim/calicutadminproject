import os
import io
import hashlib
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_config(key, default=None):
    try:
        from django.conf import settings as s
        return getattr(s, key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def _mega_configured():
    """Quick check if MEGA credentials are set (no network call)."""
    return bool(os.getenv('MEGA_EMAIL') and os.getenv('MEGA_PASSWORD'))


def _get_drive_service():
    """Login to MEGA. Returns mega instance or None."""
    from accounts.utils.mega_backup_service import _login
    return _login()


def ensure_folder_path(service, path_parts):
    """Ensure a nested folder path exists in MEGA, creating as needed.
    Returns the path string on success, None on failure."""
    from accounts.utils.mega_backup_service import _ensure_path
    return _ensure_path(service, path_parts)


def upload_file(service, file_bytes, filename, mime_type, parent_id):
    """Upload a file to MEGA. mime_type is ignored (MEGA handles it).
    parent_id is the folder path string returned by ensure_folder_path.
    Returns ('mega://<path>', None) on success, (None, error) on failure."""
    from accounts.utils.mega_backup_service import upload_bytes
    return upload_bytes(service, file_bytes, filename, parent_id)


def download_file(service, file_id):
    """Download a file from MEGA by mega:// path.
    Returns (bytes, error_message)."""
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
            ['pg_dump', '--no-owner', '--no-acl', database_url, '-f', '-'],
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


def delete_old_backups(service, folder_path, keep_count=30):
    """Delete old MEGA backups beyond keep_count using BackupLog.
    Returns number of backups cleaned up."""
    from accounts.models import BackupLog
    from . import mega_backup_service
    deleted = 0
    try:
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
