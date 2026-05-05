import os
import json
import logging
import datetime
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def backup_pdfs():
    try:
        # 1. Configuration & Env Variables
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        gdrive_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON")
        gdrive_folder_id = os.getenv("GDRIVE_FOLDER_ID")
        bucket_name = "calicutadminpanelpdf"

        if not all([supabase_url, supabase_key, gdrive_json, gdrive_folder_id]):
            logger.error("❌ Missing required environment variables.")
            return

        # 2. Initialize Clients
        supabase = create_client(supabase_url, supabase_key)
        
        gdrive_info = json.loads(gdrive_json)
        creds = service_account.Credentials.from_service_account_info(
            gdrive_info, 
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        drive_service = build('drive', 'v3', credentials=creds)

        # 3. List Files in Supabase (Listing from bucket root)
        logger.info(f"🔍 Listing files in Supabase bucket: {bucket_name}...")
        
        # We list the root folder to capture all files
        files = supabase.storage.from_(bucket_name).list("")
        
        if not files:
            logger.info("ℹ️ No files found in the bucket root.")
            return

        date_prefix = datetime.date.today().strftime("%Y-%m-%d")
        
        for file_info in files:
            file_name = file_info['name']
            if file_name == ".emptyFolderPlaceholder":
                continue

            # Since we list root, supabase_path is just the file_name
            supabase_path = file_name
            local_filename = f"temp_{file_name}"
            gdrive_filename = f"backup_{date_prefix}_{file_name}"

            try:
                logger.info(f"📥 Downloading: {file_name}")
                
                # 4. Download from Supabase
                with open(local_filename, "wb+") as f:
                    data = supabase.storage.from_(bucket_name).download(supabase_path)
                    f.write(data)

                # 5. Upload to Google Drive
                logger.info(f"📤 Uploading to Google Drive as: {gdrive_filename}")
                file_metadata = {
                    'name': gdrive_filename,
                    'parents': [gdrive_folder_id]
                }
                media = MediaFileUpload(local_filename, mimetype='application/pdf', resumable=True)
                
                uploaded_file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                
                logger.info(f"✅ Success! File ID: {uploaded_file.get('id')}")

            except Exception as e:
                logger.error(f"⚠️ Failed to process {file_name}: {str(e)}")
            
            finally:
                # 6. Cleanup Temporary Local File
                if os.path.exists(local_filename):
                    os.remove(local_filename)

        logger.info("🎯 PDF Backup Process Completed.")

    except Exception as e:
        logger.error(f"💥 Critical Failure: {str(e)}")

if __name__ == "__main__":
    backup_pdfs()
