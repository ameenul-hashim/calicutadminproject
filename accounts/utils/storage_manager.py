import os
import logging
import io
import traceback
from datetime import timedelta

logger = logging.getLogger(__name__)

from accounts.utils.supabase_storage import supabase, get_client, _do_upload

def _get_resource_bucket():
    return os.getenv("RESOURCE_SUPABASE_BUCKET", "resources")

class StorageManager:
    @staticmethod
    def upload_to_supabase_storage(file_bytes, destination_path, content_type):
        client = get_client(use_resource_project=True)
        if not client:
            logger.warning("Resource Supabase not configured. Bypassing upload.")
            return destination_path
        try:
            bucket_name = _get_resource_bucket()
            _do_upload(client, bucket_name, destination_path, file_bytes, content_type=content_type)
            return destination_path
        except Exception as e:
            logger.error(f"Supabase Upload Error: {e}")
            raise ValueError("Cloud storage primary upload failed.")

    @staticmethod
    def backup_resource(resource_id, original_supabase_path):
        """
        Backup a teacher resource to Google Drive.
        1. Download original from Supabase
        2. Backup to Google Drive via backup_trigger (with retry + SHA256 verify)
        3. Does NOT delete the original from Supabase (backup = copy, not move)
        """
        from accounts.models import CourseResource
        try:
            resource = CourseResource.objects.get(id=resource_id)
            client = get_client(use_resource_project=True)
            if not client:
                logger.warning("Resource Supabase not configured. Cannot backup.")
                return

            bucket_name = _get_resource_bucket()
            file_bytes = client.storage.from_(bucket_name).download(original_supabase_path)
            if not file_bytes:
                raise ValueError(f"Could not download original file from Supabase: {original_supabase_path}")

            course_title = resource.course.title if resource.course else ''
            chapter = resource.chapter or ''
            category = resource.category or ''

            from accounts.utils.backup_trigger import backup_teacher_resource
            backup_teacher_resource(
                resource_id, original_supabase_path, file_bytes,
                course_title, chapter, category
            )
        except Exception as e:
            logger.error(f"backup_resource failed for resource {resource_id}: {e}")
            try:
                resource = CourseResource.objects.get(id=resource_id)
                resource.backup_status = 'FAILED'
                resource.save(update_fields=['backup_status'])
            except Exception:
                logger.exception("Failed to update resource backup status")

    @staticmethod
    def backup_and_cleanup(resource_id, original_supabase_path):
        """Legacy wrapper — delegates to backup_resource (Google Drive, not MEGA)."""
        StorageManager.backup_resource(resource_id, original_supabase_path)

    @staticmethod
    def backup_to_google_drive(resource_id):
        """Backup resource to Google Drive. Prevents Supabase deletion."""
        from accounts.models import CourseResource
        try:
            resource = CourseResource.objects.get(id=resource_id)
            StorageManager.backup_resource(resource_id, resource.firebase_file_path)
        except Exception as e:
            logger.error(f"backup_to_google_drive failed for {resource_id}: {e}")

    @staticmethod
    def delete_from_supabase_storage(file_path):
        client = get_client(use_resource_project=True)
        if not client or not file_path:
            return
        try:
            bucket_name = _get_resource_bucket()
            client.storage.from_(bucket_name).remove([file_path])
        except Exception as e:
            logger.error(f"Supabase Delete Error for {file_path}: {e}")

    @staticmethod
    def generate_supabase_signed_url(file_path, expiration=None):
        client = get_client(use_resource_project=True)
        if not client or not file_path: return None
        try:
            bucket_name = _get_resource_bucket()
            if expiration is None: expires_in = 7 * 24 * 60 * 60
            elif isinstance(expiration, timedelta): expires_in = int(expiration.total_seconds())
            else: expires_in = int(expiration) * 60
            res = client.storage.from_(bucket_name).create_signed_url(file_path, expires_in)
            if isinstance(res, dict) and 'signedURL' in res: return res['signedURL']
            elif isinstance(res, str): return res
            return None
        except Exception as e:
            logger.error(f"Supabase Signed URL generation failed for {file_path}: {e}")
            return None
