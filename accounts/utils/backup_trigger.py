import os
import io
import time
import hashlib
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_config(key, default=None):
    try:
        from django.conf import settings as s
        return getattr(s, key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def backup_signup_pdf(user_id, pdf_path, pdf_bytes):
    """Backup a signup proof PDF to Google Drive in a background thread.
    Never blocks the signup flow — always returns immediately."""
    threading.Thread(
        target=_do_backup_signup_pdf,
        args=(user_id, pdf_path, pdf_bytes),
        daemon=True
    ).start()


def backup_teacher_resource(resource_id, supabase_path, file_bytes, course_title, chapter, category):
    """Backup a teacher resource PDF to Google Drive in a background thread.
    Never blocks the upload flow — always returns immediately."""
    threading.Thread(
        target=_do_backup_teacher_resource,
        args=(resource_id, supabase_path, file_bytes, course_title, chapter, category),
        daemon=True
    ).start()


def _compute_sha256(file_bytes):
    return hashlib.sha256(file_bytes).hexdigest()


def _upload_with_retry(service, file_bytes, filename, mime_type, parent_id, max_retries=None):
    """Upload to Drive with retry logic and exponential backoff."""
    from accounts.utils.drive_backup_service import upload_file
    if max_retries is None:
        max_retries = int(_get_config('BACKUP_MAX_RETRIES', 3))
    for attempt in range(max_retries):
        drive_id, error = upload_file(service, file_bytes, filename, mime_type, parent_id)
        if drive_id:
            return drive_id, None
        logger.warning(f'Upload attempt {attempt+1}/{max_retries} failed: {error}')
        time.sleep(2 ** attempt)
    return None, error


def _verify_and_log(backup_log_id, file_bytes, expected_sha256=None):
    """Verify file integrity and update backup log."""
    from accounts.models import BackupLog
    from accounts.utils.drive_backup_service import verify_file_integrity
    try:
        log = BackupLog.objects.get(id=backup_log_id)
        is_valid, actual_sha256, error = verify_file_integrity(file_bytes, expected_sha256)
        if is_valid:
            log.sha256 = actual_sha256
            log.verify_status = 'VERIFIED'
            log.status = 'SUCCESS'
            log.completed_at = datetime.now()
            log.save(update_fields=['sha256', 'verify_status', 'status', 'completed_at'])
            return True
        else:
            log.verify_status = 'MISMATCH'
            log.status = 'FAILED'
            log.error_message = error or 'SHA256 mismatch'
            log.completed_at = datetime.now()
            log.save(update_fields=['verify_status', 'status', 'error_message', 'completed_at'])
            return False
    except Exception as e:
        logger.error(f'Backup log update failed for {backup_log_id}: {e}')
        return False


def _do_backup_signup_pdf(user_id, pdf_path, pdf_bytes):
    """Background task: backup signup PDF to Google Drive."""
    from accounts.models import BackupLog
    from accounts.utils.drive_backup_service import (
        _get_drive_service, ensure_folder_path
    )
    if _get_config('BACKUP_ENABLED', 'True') != 'True':
        logger.info('Backup disabled by BACKUP_ENABLED=False')
        return
    now = datetime.now()
    year_month = now.strftime('%Y/%m')
    signup_folder = _get_config('BACKUP_SIGNUP_FOLDER', 'Signup_Proofs')
    filename = f'signup_{user_id}_{now.strftime("%Y%m%d_%H%M%S")}.pdf'
    log = BackupLog.objects.create(
        backup_type='SIGNUP_PDF',
        filename=filename,
        file_size=len(pdf_bytes),
        status='RUNNING',
        metadata={'user_id': str(user_id), 'pdf_path': pdf_path},
    )
    try:
        service = _get_drive_service()
        if not service:
            log.status = 'FAILED'
            log.error_message = 'Google Drive not configured'
            log.save(update_fields=['status', 'error_message', 'completed_at'])
            return
        folder_parts = ['NeoLearn_Backups', signup_folder] + year_month.split('/')
        folder_id = ensure_folder_path(service, folder_parts)
        log.drive_folder_path = '/'.join(folder_parts)
        log.status = 'UPLOADING'
        log.save(update_fields=['status', 'drive_folder_path'])
        drive_id, error = _upload_with_retry(service, pdf_bytes, filename, 'application/pdf', folder_id)
        if error:
            raise ValueError(f'Upload failed after retries: {error}')
        log.drive_file_id = drive_id
        log.save(update_fields=['drive_file_id'])
        _verify_and_log(log.id, pdf_bytes)
    except Exception as e:
        log.status = 'FAILED'
        log.error_message = str(e)[:500]
        log.completed_at = datetime.now()
        log.save(update_fields=['status', 'error_message', 'completed_at'])


def _do_backup_teacher_resource(resource_id, supabase_path, file_bytes, course_title, chapter, category):
    """Background task: backup teacher resource PDF to Google Drive."""
    from accounts.models import BackupLog
    from accounts.utils.drive_backup_service import (
        _get_drive_service, ensure_folder_path
    )
    if _get_config('BACKUP_ENABLED', 'True') != 'True':
        logger.info('Backup disabled by BACKUP_ENABLED=False')
        return
    safe_course = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in (course_title or 'Unknown'))[:50]
    safe_chapter = ''.join(c if c.isalnum() or c in ' _-' else '_' for c in (chapter or 'General'))[:50]
    safe_category = (category or 'General').replace('/', '_')
    ext = supabase_path.split('.')[-1] if '.' in supabase_path else 'pdf'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    resource_folder = _get_config('BACKUP_RESOURCE_FOLDER', 'Teacher_Resources')
    filename = f'resource_{resource_id}_{timestamp}.{ext}'
    log = BackupLog.objects.create(
        backup_type='TEACHER_RESOURCE',
        filename=filename,
        file_size=len(file_bytes),
        status='RUNNING',
        metadata={
            'resource_id': str(resource_id),
            'supabase_path': supabase_path,
            'course': safe_course,
            'chapter': safe_chapter,
            'category': safe_category,
        },
    )
    try:
        service = _get_drive_service()
        if not service:
            log.status = 'FAILED'
            log.error_message = 'Google Drive not configured'
            log.save(update_fields=['status', 'error_message', 'completed_at'])
            return
        folder_parts = ['NeoLearn_Backups', resource_folder, safe_course, safe_chapter, safe_category]
        folder_id = ensure_folder_path(service, folder_parts)
        log.drive_folder_path = '/'.join(folder_parts)
        log.status = 'UPLOADING'
        log.save(update_fields=['status', 'drive_folder_path'])
        mime_map = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'txt': 'text/plain',
        }
        mime_type = mime_map.get(ext.lower(), 'application/octet-stream')
        drive_id, error = _upload_with_retry(service, file_bytes, filename, mime_type, folder_id)
        if error:
            raise ValueError(f'Upload failed after retries: {error}')
        log.drive_file_id = drive_id
        log.save(update_fields=['drive_file_id'])
        _verify_and_log(log.id, file_bytes)
    except Exception as e:
        log.status = 'FAILED'
        log.error_message = str(e)[:500]
        log.completed_at = datetime.now()
        log.save(update_fields=['status', 'error_message', 'completed_at'])
