import os
import subprocess
import datetime
import requests
import cloudinary
from cloudinary.api import resources

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Cloudinary config loading
from dotenv import load_dotenv
load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

SCOPES = ['https://www.googleapis.com/auth/drive.file']

DATABASE_FOLDER_ID = os.getenv("DRIVE_DATABASE_FOLDER_ID", "YOUR_DB_FOLDER_ID")
PDF_FOLDER_ID = os.getenv("DRIVE_PDF_FOLDER_ID", "YOUR_PDF_FOLDER_ID")

# ----------------------------
# AUTHENTICATE GOOGLE DRIVE
# ----------------------------
def authenticate_drive():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

# ----------------------------
# DATABASE BACKUP
# ----------------------------
def backup_database():
    filename = f"db_backup_{datetime.date.today()}.sql"
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL is not set.")
    subprocess.run(f"pg_dump {db_url} > {filename}", shell=True)
    return filename

# ----------------------------
# CLOUDINARY PDF BACKUP
# ----------------------------
def backup_cloudinary():
    os.makedirs("pdf_backup", exist_ok=True)

    res = resources(
        type="upload",
        resource_type="raw",
        prefix="edustream/pdfs",
        max_results=100
    )

    files = []
    for f in res.get("resources", []):
        url = f["secure_url"]
        name = f["public_id"].split("/")[-1] + ".pdf"
        path = f"pdf_backup/{name}"

        r = requests.get(url)
        with open(path, "wb") as file:
            file.write(r.content)

        files.append(path)

    return files

# ----------------------------
# UPLOAD FILE TO DRIVE
# ----------------------------
def upload_to_drive(service, file_path, folder_id):
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    service.files().create(body=file_metadata, media_body=media).execute()
    print(f"Uploaded {file_path} to Google Drive (Folder: {folder_id}).")

# ----------------------------
# MAIN BACKUP EXECUTION
# ----------------------------
def run_backup():
    print("Starting automated backup...")
    try:
        service = authenticate_drive()
    except Exception as e:
        print(f"Error authenticating with Google Drive: {e}")
        print("Please ensure credentials.json is present and valid.")
        return

    # Backup DB
    try:
        print("Backing up PostgreSQL database...")
        db_file = backup_database()
        upload_to_drive(service, db_file, DATABASE_FOLDER_ID)
        # Clean up local db backup
        if os.path.exists(db_file):
            os.remove(db_file)
    except Exception as e:
        print(f"Error backing up database: {e}")

    # Backup PDFs
    try:
        print("Backing up Cloudinary PDFs...")
        pdf_files = backup_cloudinary()
        for f in pdf_files:
            upload_to_drive(service, f, PDF_FOLDER_ID)
            # Clean up local pdf
            if os.path.exists(f):
                os.remove(f)
    except Exception as e:
        print(f"Error backing up Cloudinary PDFs: {e}")

    print("Backup completed successfully")

if __name__ == "__main__":
    run_backup()
