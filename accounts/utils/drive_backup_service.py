import os
import io
import json
import hashlib
import logging
import subprocess
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']


def _get_config(key, default=None):
    try:
        from django.conf import settings as s
        return getattr(s, key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def _load_credentials_json():
    """Load Google Drive service account JSON from all possible sources.
    
    Priority:
    1. GOOGLE_DRIVE_CREDENTIALS environment variable
    2. /etc/secrets/GOOGLE_DRIVE_CREDENTIALS (Render Secret File)
    3. credentials.json in this utils directory
    
    Returns (parsed_dict, source_name) or (None, error_message).
    Never exposes secret values in logs — only PASS/FAIL and source name.
    """
    source = None
    raw = None

    # 1) Environment variable
    raw = os.getenv('GOOGLE_DRIVE_CREDENTIALS')
    if raw:
        source = 'env var'
        logger.info("GOOGLE_DRIVE_CREDENTIALS loaded from environment variable")

    # 2) Render Secret File
    if not raw:
        secret_path = '/etc/secrets/GOOGLE_DRIVE_CREDENTIALS'
        try:
            if os.path.isfile(secret_path):
                with open(secret_path, 'r') as f:
                    raw = f.read()
                if raw:
                    source = 'secret file'
                    logger.info("GOOGLE_DRIVE_CREDENTIALS loaded from Render Secret File")
        except Exception as e:
            logger.warning(f"Failed to read Render Secret File: {e}")

    # 3) Local credentials.json (dev only)
    if not raw:
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')
        try:
            if os.path.isfile(local_path):
                with open(local_path, 'r') as f:
                    raw = f.read()
                if raw:
                    source = 'credentials.json'
                    logger.info("GOOGLE_DRIVE_CREDENTIALS loaded from credentials.json")
        except Exception as e:
            logger.warning(f"Failed to read credentials.json: {e}")

    if not raw:
        return None, 'no credential source found (checked env var, /etc/secrets/, credentials.json)'

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None, 'credential JSON is not a dict'
        return parsed, source
    except json.JSONDecodeError as e:
        return None, f'credential JSON parse failed: {e}'


def _get_drive_service():
    """Build Drive service from best available credential source.
    Returns service object or None."""
    try:
        parsed, source = _load_credentials_json()
        if not parsed:
            logger.warning(f"Google Drive credentials not available: {source}")
            return None
        if parsed.get('type') != 'service_account':
            logger.warning(f"Credential type is '{parsed.get('type')}', expected 'service_account'")
            return None
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_info(
            parsed, scopes=SCOPES
        )
        logger.info(f"Google Drive service initialized from {source}")
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Drive service init failed: {e}")
        return None


def get_or_create_folder(service, folder_name, parent_id=None):
    """Find or create a Google Drive folder."""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        file_metadata['parents'] = [parent_id]
    return service.files().create(body=file_metadata, fields='id').execute().get('id')


def ensure_folder_path(service, path_parts):
    """Ensure a nested folder path exists, creating folders as needed.
    Returns the ID of the last folder in the path."""
    parent_id = None
    for part in path_parts:
        parent_id = get_or_create_folder(service, part, parent_id)
    return parent_id


def upload_file(service, file_bytes, filename, mime_type, parent_id):
    """Upload a file to Google Drive. Returns (drive_file_id, error_message)."""
    from googleapiclient.http import MediaIoBaseUpload
    try:
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file_drive = service.files().create(
            body={'name': filename, 'parents': [parent_id]},
            media_body=media,
            fields='id, name, size'
        ).execute()
        return file_drive.get('id'), None
    except Exception as e:
        return None, str(e)


def download_file(service, file_id):
    """Download a file from Google Drive. Returns (bytes, error_message)."""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        try:
            from googleapiclient.http import MediaIoBaseDownload
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        except ImportError:
            fh.write(request.execute())
        return fh.getvalue(), None
    except Exception as e:
        return None, str(e)


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


def delete_old_backups(service, folder_id, keep_count=None):
    """Delete old backup files in a Drive folder, keeping only the most recent N.
    Returns count of deleted files."""
    if keep_count is None:
        keep_count = _get_config('BACKUP_RETENTION_DAYS', 30)
    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            spaces='drive',
            fields='files(id, name, createdTime)',
            orderBy='createdTime'
        ).execute()
        files = results.get('files', [])
        if len(files) <= keep_count:
            return 0
        to_delete = files[:-keep_count]
        for f in to_delete:
            try:
                service.files().delete(fileId=f['id']).execute()
                logger.info(f"Deleted old backup: {f['name']}")
            except Exception as e:
                logger.error(f"Failed to delete {f['name']}: {e}")
        return len(to_delete)
    except Exception as e:
        logger.error(f"Retention cleanup failed: {e}")
        return 0
