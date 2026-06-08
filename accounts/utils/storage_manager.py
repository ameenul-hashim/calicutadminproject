import os
import logging
import io
import traceback
from datetime import timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

# Use the shared Supabase clients and helpers from supabase_storage (single source of truth)
from accounts.utils.supabase_storage import supabase, get_client, _do_upload

def _get_resource_bucket():
    """Returns the Supabase bucket name for resource storage (second Supabase project)."""
    return os.getenv("RESOURCE_SUPABASE_BUCKET", "resources")

class StorageManager:
    @staticmethod
    def upload_to_supabase_storage(file_bytes, destination_path, content_type):
        """Uploads a file to the dedicated Supabase Storage project"""
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
    def _get_drive_service():
        """Build Drive service: env var > local OAuth token > credentials file"""
        try:
            SCOPES = ['https://www.googleapis.com/auth/drive']
            UTILS_DIR = os.path.dirname(os.path.abspath(__file__))

            # 1) Try GOOGLE_DRIVE_CREDENTIALS env var (service account JSON)
            env_creds = os.getenv('GOOGLE_DRIVE_CREDENTIALS')
            if env_creds:
                import json
                try:
                    creds_dict = json.loads(env_creds)
                    if creds_dict.get('type') == 'service_account':
                        from google.oauth2 import service_account
                        creds = service_account.Credentials.from_service_account_info(
                            creds_dict, scopes=SCOPES
                        )
                        return build('drive', 'v3', credentials=creds)
                except Exception as e:
                    logger.warning(f"GOOGLE_DRIVE_CREDENTIALS parse failed: {e}")

            # 2) Fall back to local OAuth token.json / credentials.json (dev only)
            token_file = os.path.join(UTILS_DIR, "token.json")
            creds_file = os.path.join(UTILS_DIR, "credentials.json")
            creds = None
            if os.path.exists(token_file):
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
                else:
                    if not os.path.exists(creds_file):
                        return None
                    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Drive Service Init Failed: {e}")
            return None

    @staticmethod
    def backup_and_cleanup(resource_id, original_supabase_path):
        """
        1. Download original from Supabase
        2. Backup to Google Drive
        3. If successful, delete original from Supabase
        """
        from accounts.models import CourseResource
        try:
            resource = CourseResource.objects.get(id=resource_id)
            client = get_client(use_resource_project=True)
            if not client: return
            
            # 1. Download original
            bucket_name = _get_resource_bucket()
            
            file_bytes = client.storage.from_(bucket_name).download(original_supabase_path)
            if not file_bytes:
                raise ValueError(f"Could not download original file from Supabase: {original_supabase_path}")

            # 2. Upload to Drive
            service = StorageManager._get_drive_service()
            if not service:
                raise ValueError("Could not initialize Google Drive service")

            def get_or_create_folder(f_name, p_id=None):
                query = f"name='{f_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                if p_id: query += f" and '{p_id}' in parents"
                results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
                items = results.get('files', [])
                if items: return items[0]['id']
                file_metadata = {'name': f_name, 'mimeType': 'application/vnd.google-apps.folder'}
                if p_id: file_metadata['parents'] = [p_id]
                return service.files().create(body=file_metadata, fields='id').execute().get('id')
            
            root_id = get_or_create_folder("NeoLearner_Backups")
            res_id = get_or_create_folder("Resources_Backup", p_id=root_id)
            
            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=resource.mime_type, resumable=True)
            original_filename = f"ORIGINAL_{resource.uid}_{resource.title}.{resource.file_extension or 'pdf'}"
            file_drive = service.files().create(
                body={'name': original_filename, 'parents': [res_id]},
                media_body=media,
                fields='id'
            ).execute()
            
            drive_id = file_drive.get('id')
            if drive_id:
                resource.backup_file_path = drive_id
                resource.backup_status = 'SUCCESS'
                resource.save(update_fields=['backup_file_path', 'backup_status'])
                
                # 3. CLEANUP SUPABASE (Delete original)
                try:
                    if resource.firebase_file_path != original_supabase_path:
                        client.storage.from_(bucket_name).remove([original_supabase_path])
                        logger.info(f"Purged original file from Supabase after Drive backup: {original_supabase_path}")
                except Exception as e:
                    logger.error(f"Cleanup of original Supabase file failed for {resource.id}: {e}")
            
        except Exception as e:
            logger.error(f"backup_and_cleanup failed for resource {resource_id}: {e}")
            try:
                resource = CourseResource.objects.get(id=resource_id)
                resource.backup_status = 'FAILED'
                resource.save(update_fields=['backup_status'])
            except: pass

    @staticmethod
    def backup_to_google_drive(resource_id):
        """Asynchronously backs up the current resource to Google Drive"""
        from accounts.models import CourseResource
        try:
            resource = CourseResource.objects.get(id=resource_id)
            StorageManager.backup_and_cleanup(resource_id, resource.firebase_file_path)
        except Exception as e:
            logger.error(f"backup_to_google_drive failed for {resource_id}: {e}")

    @staticmethod
    def delete_from_supabase_storage(file_path):
        """Permanently delete file from Supabase Storage"""
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
        """Generates a short-lived temporary streaming URL."""
        client = get_client(use_resource_project=True)
        if not client or not file_path: return None
        try:
            bucket_name = _get_resource_bucket()
            
            if expiration is None: expires_in = 7 * 24 * 60 * 60 # 1 week
            elif isinstance(expiration, timedelta): expires_in = int(expiration.total_seconds())
            else: expires_in = int(expiration) * 60
                
            res = client.storage.from_(bucket_name).create_signed_url(file_path, expires_in)
            if isinstance(res, dict) and 'signedURL' in res: return res['signedURL']
            elif isinstance(res, str): return res
            return None
        except Exception as e:
            logger.error(f"Supabase Signed URL generation failed for {file_path}: {e}")
            return None
