import os
import io
import tempfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _login():
    """Login to MEGA. Returns mega instance or None."""
    email = os.getenv('MEGA_EMAIL')
    password = os.getenv('MEGA_PASSWORD')
    if not email or not password:
        logger.warning('MEGA not configured: set MEGA_EMAIL and MEGA_PASSWORD')
        return None
    try:
        from mega import Mega
        mega = Mega()
        m = mega.login(email, password)
        logger.info('Logged in to MEGA successfully')
        return m
    except ImportError:
        logger.error('mega.py package not installed')
        return None
    except Exception as e:
        logger.error(f'MEGA login failed: {e}')
        return None


def _ensure_path(mega, path_parts):
    """Ensure a nested folder path exists in MEGA, creating folders as needed.
    Returns the full path string on success, None on failure."""
    try:
        current = ''
        for part in path_parts:
            test_path = f"{current}/{part}" if current else part
            try:
                found = mega.find(test_path, exclude_deleted=True)
                if found is None:
                    raise ValueError('Not found')
            except Exception:
                mega.create_folder(part, current if current else None)
            current = test_path
        return current
    except Exception as e:
        logger.error(f'MEGA ensure path failed: {e}')
        return None


def upload_bytes(mega, file_bytes, filename, folder_path):
    """Upload bytes to a MEGA folder path.
    Returns ('mega://<full_path>', None) on success, (None, error) on failure."""
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=f'_{filename}')
        with os.fdopen(fd, 'wb') as f:
            f.write(file_bytes)
        folder = mega.find(folder_path)
        if folder is None:
            return None, f'MEGA folder not found: {folder_path}'
        mega.upload(temp_path, folder)
        dest = f"mega://{folder_path}/{filename}"
        logger.info(f'Uploaded {filename} to MEGA ({dest})')
        return dest, None
    except Exception as e:
        return None, f'MEGA upload failed: {e}'
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def download_file(mega, mega_path):
    """Download a file from MEGA by mega:// path.
    Returns (bytes, None) on success, (None, error) on failure."""
    path = mega_path
    if path.startswith('mega://'):
        path = path[7:]
    temp_path = None
    try:
        node = mega.find(path)
        if node is None:
            return None, f'MEGA file not found: {path}'
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name
        mega.download(node, temp_path)
        with open(temp_path, 'rb') as f:
            data = f.read()
        return data, None
    except Exception as e:
        return None, f'MEGA download failed: {e}'
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
