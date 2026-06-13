import os
import json
import io
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def _get_credentials():
    """Get Google Drive credentials.
    Priority:
    1. OAuth refresh token (GOOGLE_DRIVE_REFRESH_TOKEN + CLIENT_ID/SECRET)
    2. Service account JSON (GOOGLE_DRIVE_CREDENTIALS or _PATH)"""
    client_id = os.getenv('GOOGLE_DRIVE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_DRIVE_CLIENT_SECRET')
    refresh_token = os.getenv('GOOGLE_DRIVE_REFRESH_TOKEN')

    if client_id and client_secret and refresh_token:
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials(
                None,
                refresh_token=refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES
            )
            logger.info('Google Drive OAuth credentials initialized')
            return creds
        except Exception as e:
            logger.error(f'Google Drive OAuth init failed: {e}')
            return None

    creds_val = os.getenv('GOOGLE_DRIVE_CREDENTIALS')
    creds_path = os.getenv('GOOGLE_DRIVE_CREDENTIALS_PATH')

    if creds_val:
        try:
            info = json.loads(creds_val)
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        except (json.JSONDecodeError, ValueError):
            pass
        if os.path.isfile(creds_val):
            try:
                from google.oauth2 import service_account
                return service_account.Credentials.from_service_account_file(creds_val, scopes=SCOPES)
            except Exception as e:
                logger.error(f'Failed to load GOOGLE_DRIVE_CREDENTIALS file: {e}')
                return None
        logger.error(f'GOOGLE_DRIVE_CREDENTIALS is neither valid JSON nor a file path')
        return None

    if creds_path and os.path.isfile(creds_path):
        try:
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        except Exception as e:
            logger.error(f'Failed to load GOOGLE_DRIVE_CREDENTIALS_PATH: {e}')
            return None

    logger.warning('Google Drive not configured')
    return None


def _login():
    """Build Google Drive service. Returns service or None."""
    creds = _get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
        service = build('drive', 'v3', credentials=creds)
        logger.info('Google Drive service initialized')
        return service
    except Exception as e:
        logger.error(f'Google Drive init failed: {e}')
        return None


def _resolve_parent_id(service, parent_id):
    """If parent_id is a path string like 'NeoLearner_Backups/Signup_Proofs',
    resolve it to a folder ID using ensure_folder_path."""
    if parent_id and '/' in parent_id and not parent_id.startswith('http'):
        parts = parent_id.split('/')
        return ensure_folder_path(service, parts)
    return parent_id


def ensure_folder_path(service, path_parts):
    """Ensure a nested folder path exists in Google Drive, creating as needed.
    If GOOGLE_DRIVE_ROOT_FOLDER_ID is set, uses it as the root parent
    (storage counts against that folder owner's quota).
    Returns the folder ID of the deepest folder, or None on failure."""
    try:
        parent_id = os.getenv('GOOGLE_DRIVE_ROOT_FOLDER_ID') or None
        current_path = ''
        for part in path_parts:
            current_path = f'{current_path}/{part}' if current_path else part
            folder_id = _find_folder(service, part, parent_id)
            if folder_id:
                parent_id = folder_id
            else:
                mime = 'application/vnd.google-apps.folder'
                file_meta = {
                    'name': part,
                    'mimeType': mime,
                }
                if parent_id:
                    file_meta['parents'] = [parent_id]
                folder = service.files().create(body=file_meta, fields='id').execute()
                parent_id = folder.get('id')
                logger.info(f'Created Drive folder: {current_path} ({parent_id})')
        return parent_id
    except Exception as e:
        logger.error(f'Google Drive ensure path failed: {e}')
        return None


def _find_folder(service, name, parent_id=None):
    """Find a folder by name, optionally under a parent folder.
    Returns folder ID or None."""
    try:
        query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        results = service.files().list(q=query, spaces='drive', fields='files(id,name)', pageSize=10).execute()
        items = results.get('files', [])
        return items[0]['id'] if items else None
    except Exception as e:
        logger.error(f'Google Drive find folder failed: {e}')
        return None


def upload_file(service, file_bytes, filename, mime_type, parent_id):
    """Upload bytes to Google Drive.
    parent_id can be a folder ID or a path string (e.g. 'Folder/Subfolder').
    Returns (drive_file_id, None) on success, (None, error) on failure."""
    try:
        parent_id = _resolve_parent_id(service, parent_id)

        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
        file_meta = {'name': filename}
        if parent_id:
            file_meta['parents'] = [parent_id]

        file = service.files().create(body=file_meta, media_body=media, fields='id').execute()
        file_id = file.get('id')
        logger.info(f'Uploaded {filename} to Google Drive (ID: {file_id})')
        return file_id, None
    except Exception as e:
        return None, f'Google Drive upload failed: {e}'


def download_file(service, file_id):
    """Download a file from Google Drive by file ID.
    Returns (bytes, None) on success, (None, error) on failure."""
    try:
        request = service.files().get_media(fileId=file_id)
        from googleapiclient.http import MediaIoBaseDownload
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue(), None
    except Exception as e:
        return None, f'Google Drive download failed: {e}'


def delete_file(service, file_id):
    """Delete a file from Google Drive by file ID.
    Returns True on success, False on failure."""
    try:
        service.files().delete(fileId=file_id).execute()
        logger.info(f'Deleted from Google Drive: {file_id}')
        return True
    except Exception as e:
        logger.error(f'Google Drive delete failed for {file_id}: {e}')
        return False


def delete_old_backups(service, folder_id, keep_count=30):
    """Delete old backup files in a folder, keeping only the latest keep_count.
    Returns number of files deleted."""
    deleted = 0
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, spaces='drive',
            fields='files(id, name, createdTime)',
            orderBy='createdTime desc'
        ).execute()
        items = results.get('files', [])
        if len(items) <= keep_count:
            return 0
        for old in items[keep_count:]:
            try:
                service.files().delete(fileId=old['id']).execute()
                deleted += 1
            except Exception as e:
                logger.warning(f'Retention delete failed for {old["name"]}: {e}')
    except Exception as e:
        logger.error(f'Retention cleanup error: {e}')
    return deleted
