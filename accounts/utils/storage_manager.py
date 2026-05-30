import os
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Initialize Secondary Supabase for Resources
RESOURCE_SUPABASE_URL = os.getenv("RESOURCE_SUPABASE_URL")
RESOURCE_SUPABASE_KEY = os.getenv("RESOURCE_SUPABASE_SERVICE_ROLE_KEY")

supabase = None
if RESOURCE_SUPABASE_URL and RESOURCE_SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(RESOURCE_SUPABASE_URL, RESOURCE_SUPABASE_KEY)
    except ImportError:
        logger.warning("supabase package not installed. Secondary storage disabled.")
    except Exception as e:
        logger.error(f"Failed to init Secondary Supabase: {e}")

class StorageManager:
    @staticmethod
    def upload_to_supabase_storage(file_bytes, destination_path, content_type):
        """Uploads a file to the dedicated Supabase Storage project"""
        if not supabase:
            logger.warning("Resource Supabase not configured. Bypassing upload.")
            return destination_path
            
        try:
            # Determine bucket from the start of the path (e.g. 'resources/...' -> bucket 'resources')
            parts = destination_path.split('/', 1)
            bucket_name = parts[0]
            file_path = parts[1] if len(parts) > 1 else destination_path
            
            res = supabase.storage.from_(bucket_name).upload(
                path=file_path,
                file=file_bytes,
                file_options={"content-type": content_type}
            )
            return destination_path
        except Exception as e:
            logger.error(f"Supabase Upload Error: {e}")
            raise ValueError("Cloud storage primary upload failed.")

    @staticmethod
    def backup_to_google_drive(resource_id):
        """Asynchronously backs up the approved resource to Google Drive"""
        from accounts.models import CourseResource
        import traceback
        import os
        import io
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload

        try:
            resource = CourseResource.objects.get(id=resource_id)
            if not supabase:
                raise ValueError("Supabase disabled.")
                
            # 1. Download file bytes from Supabase
            parts = resource.firebase_file_path.split('/', 1)
            bucket_name = parts[0]
            path_in_bucket = parts[1] if len(parts) > 1 else resource.firebase_file_path
            
            download_res = supabase.storage.from_(bucket_name).download(path_in_bucket)
            if not download_res:
                raise ValueError("Failed to download resource from Supabase")
                
            # 2. Authenticate to Google Drive
            # Use the local directory where storage_manager.py resides
            UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
            token_file = os.path.join(UTILS_DIR, "token.json")
            creds_file = os.path.join(UTILS_DIR, "credentials.json")
            
            SCOPES = ['https://www.googleapis.com/auth/drive']
            creds = None
            if os.path.exists(token_file):
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
                except:
                    creds = None
            if not creds or not creds.valid:
                if not os.path.exists(creds_file):
                    raise FileNotFoundError(f"Missing {creds_file} for Drive Auth")
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                creds = flow.run_local_server(port=0)
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
                    
            service = build('drive', 'v3', credentials=creds)
            
            # Helper: get or create folder
            def get_or_create_folder(folder_name, parent_id=None):
                query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                if parent_id: query += f" and '{parent_id}' in parents"
                results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
                items = results.get('files', [])
                if items: return items[0]['id']
                file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
                if parent_id: file_metadata['parents'] = [parent_id]
                return service.files().create(body=file_metadata, fields='id').execute().get('id')
                
            root_id = get_or_create_folder("Neo Learner_Backups")
            res_id = get_or_create_folder("Resources_Backup", parent_id=root_id)
            
            # 3. Upload to Google Drive directly from memory
            file_bytes = download_res
            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=resource.mime_type, resumable=True)
            original_filename = f"{resource.uid}_{resource.title}.{resource.file_extension}"
            file_drive = service.files().create(
                body={'name': original_filename, 'parents': [res_id]},
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file_drive.get('id')
            if not file_id:
                raise ValueError("Drive API returned empty file_id")
                
            # 4. Save to DB
            resource.backup_file_path = file_id
            resource.backup_status = 'SUCCESS'
            resource.save(update_fields=['backup_file_path', 'backup_status'])
            logger.info(f"Successfully backed up {resource.title} to Google Drive: {file_id}")
            
        except Exception as e:
            logger.error(f"Google Drive Backup Failed for resource {resource_id}: {e}")
            logger.error(traceback.format_exc())
            try:
                resource = CourseResource.objects.get(id=resource_id)
                resource.backup_status = 'FAILED'
                resource.save(update_fields=['backup_status'])
            except:
                pass

    @staticmethod
    def delete_from_supabase_storage(file_path):
        """Permanently delete file from Supabase Storage"""
        if not supabase or not file_path:
            return
            
        try:
            parts = file_path.split('/', 1)
            bucket_name = parts[0]
            path_in_bucket = parts[1] if len(parts) > 1 else file_path
            
            supabase.storage.from_(bucket_name).remove([path_in_bucket])
        except Exception as e:
            logger.error(f"Supabase Delete Error for {file_path}: {e}")

    @staticmethod
    def generate_supabase_signed_url(file_path, expiration=None):
        """Generates a short-lived temporary streaming URL."""
        if not supabase or not file_path:
            return None
            
        try:
            parts = file_path.split('/', 1)
            bucket_name = parts[0]
            path_in_bucket = parts[1] if len(parts) > 1 else file_path
            
            if expiration is None:
                expires_in = 7 * 24 * 60 * 60 # 1 week
            elif isinstance(expiration, timedelta):
                expires_in = int(expiration.total_seconds())
            else:
                expires_in = int(expiration) * 60
                
            res = supabase.storage.from_(bucket_name).create_signed_url(path_in_bucket, expires_in)
            
            # The python SDK returns the URL directly in some versions, or a dict in others
            if isinstance(res, dict) and 'signedURL' in res:
                return res['signedURL']
            elif isinstance(res, str):
                return res
                
            return None
        except Exception as e:
            logger.error(f"Supabase Signed URL generation failed for {file_path}: {e}")
            return None


