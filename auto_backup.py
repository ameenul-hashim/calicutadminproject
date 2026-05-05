import os
import subprocess
import datetime
import requests
import cloudinary
from cloudinary.api import resources

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Config loading
from dotenv import load_dotenv
load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

SCOPES = ['https://www.googleapis.com/auth/drive.file']

DATABASE_FOLDER_ID = os.getenv("DRIVE_DATABASE_FOLDER_ID")
PDF_FOLDER_ID = os.getenv("DRIVE_PDF_FOLDER_ID")

# ----------------------------
# AUTHENTICATE GOOGLE DRIVE
# ----------------------------
def authenticate_drive():
    """Authenticate with Google Drive, handling token refresh automatically."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # If token is expired or invalid, refresh or re-auth
    if creds and creds.expired and creds.refresh_token:
        print("Refreshing expired Google Drive token...")
        creds.refresh(Request())
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    elif not creds or not creds.valid:
        if not os.path.exists('credentials.json'):
            raise FileNotFoundError(
                "credentials.json not found!\n"
                "Download it from Google Cloud Console > Credentials > OAuth 2.0 Client ID.\n"
                "See the setup guide for details."
            )
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

# ----------------------------
# DATABASE BACKUP
# ----------------------------
def backup_database():
    """Dump PostgreSQL database to a local .sql file."""
    filename = f"db_backup_{datetime.date.today()}.sql"
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL is not set in .env")
    
    result = subprocess.run(
        f'pg_dump "{db_url}" > {filename}',
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"  pg_dump stderr: {result.stderr.strip()}")
    
    # Verify file was created and has content
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        raise RuntimeError(f"Database dump failed - {filename} is empty or missing")
    
    size_kb = os.path.getsize(filename) / 1024
    print(f"  Database dumped: {filename} ({size_kb:.1f} KB)")
    return filename

# ----------------------------
# CLOUDINARY PDF BACKUP
# (with pagination for >100 files)
# ----------------------------
def backup_cloudinary():
    """Download all PDFs from Cloudinary with pagination support."""
    os.makedirs("pdf_backup", exist_ok=True)

    all_resources = []
    next_cursor = None

    # Paginate through all Cloudinary raw uploads
    while True:
        params = {
            "type": "upload",
            "resource_type": "raw",
            "prefix": "edustream/pdfs",
            "max_results": 100,
        }
        if next_cursor:
            params["next_cursor"] = next_cursor

        res = resources(**params)
        batch = res.get("resources", [])
        all_resources.extend(batch)

        next_cursor = res.get("next_cursor")
        if not next_cursor or not batch:
            break

    print(f"  Found {len(all_resources)} PDFs in Cloudinary")

    files = []
    for f in all_resources:
        url = f["secure_url"]
        public_id = f["public_id"]
        name = public_id.split("/")[-1] + ".pdf"
        path = f"pdf_backup/{name}"

        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            with open(path, "wb") as file:
                file.write(r.content)
            size_kb = len(r.content) / 1024
            print(f"    Downloaded: {name} ({size_kb:.1f} KB)")
            files.append(path)
        except Exception as e:
            print(f"    Failed to download {name}: {e}")

    return files

# ----------------------------
# UPLOAD FILE TO DRIVE
# ----------------------------
def upload_to_drive(service, file_path, folder_id):
    """Upload a local file to a specific Google Drive folder."""
    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,name'
    ).execute()
    print(f"    Uploaded to Drive: {uploaded.get('name')} (ID: {uploaded.get('id')})")

# ----------------------------
# MAIN BACKUP EXECUTION
# ----------------------------
def run_backup():
    print("=" * 50)
    print("  EduStream Automated Backup")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Validate folder IDs
    if not DATABASE_FOLDER_ID or not PDF_FOLDER_ID:
        print("ERROR: DRIVE_DATABASE_FOLDER_ID and DRIVE_PDF_FOLDER_ID must be set in .env")
        return

    # Authenticate
    try:
        print("\n[1/3] Authenticating with Google Drive...")
        service = authenticate_drive()
        print("  Authentication successful!")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    # Backup Database
    try:
        print("\n[2/3] Backing up PostgreSQL database...")
        db_file = backup_database()
        upload_to_drive(service, db_file, DATABASE_FOLDER_ID)
        if os.path.exists(db_file):
            os.remove(db_file)
        print("  Database backup complete!")
    except Exception as e:
        print(f"  ERROR backing up database: {e}")

    # Backup Cloudinary PDFs
    try:
        print("\n[3/3] Backing up Cloudinary PDFs...")
        pdf_files = backup_cloudinary()
        if pdf_files:
            for f in pdf_files:
                upload_to_drive(service, f, PDF_FOLDER_ID)
                if os.path.exists(f):
                    os.remove(f)
            print(f"  PDF backup complete! ({len(pdf_files)} files)")
        else:
            print("  No PDFs found to backup.")
    except Exception as e:
        print(f"  ERROR backing up PDFs: {e}")

    # Cleanup pdf_backup directory
    if os.path.exists("pdf_backup"):
        try:
            os.rmdir("pdf_backup")
        except OSError:
            pass

    print("\n" + "=" * 50)
    print("  Backup completed successfully!")
    print("=" * 50)

if __name__ == "__main__":
    run_backup()
