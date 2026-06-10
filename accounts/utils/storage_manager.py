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
    def _get_mega():
        from accounts.utils.mega_backup_service import _login
        return _login()

    @staticmethod
    def backup_and_cleanup(resource_id, original_supabase_path):
        """
        1. Download original from Supabase
        2. Backup to MEGA
        3. If successful, delete original from Supabase
        """
        from accounts.models import CourseResource
        from accounts.utils.mega_backup_service import _ensure_path, upload_bytes
        try:
            resource = CourseResource.objects.get(id=resource_id)
            client = get_client(use_resource_project=True)
            if not client: return

            bucket_name = _get_resource_bucket()
            file_bytes = client.storage.from_(bucket_name).download(original_supabase_path)
            if not file_bytes:
                raise ValueError(f"Could not download original file from Supabase: {original_supabase_path}")

            mega = StorageManager._get_mega()
            if not mega:
                raise ValueError("Could not login to MEGA")

            folder_path = _ensure_path(mega, ['NeoLearner_Backups', 'Resources_Backup'])
            if not folder_path:
                raise ValueError("Could not create MEGA folder path")

            safe_title = ''.join(c if c.isalnum() or c in ' _-.' else '_' for c in (resource.title or 'Untitled'))[:80]
            ext = resource.file_extension or 'pdf'
            filename = f"ORIGINAL_{resource.uid}_{safe_title}.{ext}"
            dest, error = upload_bytes(mega, file_bytes, filename, folder_path)
            if error:
                raise ValueError(f"MEGA upload failed: {error}")

            resource.backup_file_path = dest
            resource.backup_status = 'SUCCESS'
            resource.save(update_fields=['backup_file_path', 'backup_status'])

            try:
                if resource.firebase_file_path != original_supabase_path:
                    client.storage.from_(bucket_name).remove([original_supabase_path])
                    logger.info(f"Purged original file from Supabase after MEGA backup: {original_supabase_path}")
            except Exception as e:
                logger.error(f"Cleanup of original Supabase file failed for {resource.id}: {e}")

        except Exception as e:
            logger.error(f"backup_and_cleanup failed for resource {resource_id}: {e}")
            try:
                resource = CourseResource.objects.get(id=resource_id)
                resource.backup_status = 'FAILED'
                resource.save(update_fields=['backup_status'])
            except:
                pass

    @staticmethod
    def backup_to_google_drive(resource_id):
        """Legacy wrapper — delegates to backup_and_cleanup."""
        from accounts.models import CourseResource
        try:
            resource = CourseResource.objects.get(id=resource_id)
            StorageManager.backup_and_cleanup(resource_id, resource.firebase_file_path)
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
