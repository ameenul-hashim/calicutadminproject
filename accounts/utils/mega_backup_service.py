import os
import io
import asyncio
import tempfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Python 3.11+ removed asyncio.coroutine; mega.py (v1.0.8) still uses it
if not hasattr(asyncio, 'coroutine'):
    asyncio.coroutine = lambda f: f


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
            existing_id = mega.find_path_descriptor(test_path)
            if existing_id is None:
                parent_id = mega.find_path_descriptor(current) if current else None
                created = mega.create_folder(part, parent_id)
                if not created or part not in created:
                    raise ValueError(f'Failed to create folder: {part}')
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
        if not folder_path:
            return None, 'MEGA folder path is empty'
        fd, temp_path = tempfile.mkstemp(suffix=f'_{filename}')
        with os.fdopen(fd, 'wb') as f:
            f.write(file_bytes)
        node_id = mega.find_path_descriptor(folder_path)
        if node_id is None:
            return None, f'MEGA folder not found: {folder_path}'
        mega.upload(temp_path, dest=node_id)
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


def delete_file(mega, mega_path):
    """Delete a file from MEGA by mega:// path.
    Returns True on success, False on failure."""
    path = mega_path
    if path.startswith('mega://'):
        path = path[7:]
    try:
        node = mega.find(path)
        if node is None:
            logger.warning(f'MEGA file not found for deletion: {path}')
            return False
        mega.delete(node[0])
        logger.info(f'Deleted from MEGA: {path}')
        return True
    except Exception as e:
        logger.error(f'MEGA delete failed for {path}: {e}')
        return False


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
