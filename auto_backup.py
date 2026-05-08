import os
import subprocess
import datetime
import requests
import time
import logging
from logging.handlers import RotatingFileHandler
import traceback
import smtplib
import shutil
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from supabase import create_client, Client
import boto3
from botocore.exceptions import NoCredentialsError

import sys
import io

VERSION = "3.0.0-Enterprise"

# Force UTF-8 for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Config loading
from dotenv import load_dotenv
load_dotenv()

# Supabase Config
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase_bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")
supabase: Client = None
if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)

# AWS S3 Config (Secondary Backup)
s3_client = None
if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1")
    )
s3_bucket = os.getenv("AWS_S3_BUCKET")

SCOPES = ['https://www.googleapis.com/auth/drive']
RETENTION_DAYS = 30  

# ----------------------------
# PATH RESOLUTION
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def get_path(filename):
    return os.path.join(BASE_DIR, filename)

log_file = get_path("backup.log")
token_file = get_path("token.json")
creds_file = get_path("credentials.json")
success_file = get_path("last_success.txt")
lock_file = get_path("backup.lock")

# ----------------------------
# LOGGING SETUP
# ----------------------------
log_formatter = logging.Formatter('[%(asctime)s UTC] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler = RotatingFileHandler(log_file, mode='a', maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

app_log = logging.getLogger('backup_logger')
app_log.setLevel(logging.INFO)
app_log.addHandler(file_handler)
app_log.addHandler(console_handler)

def log(msg, level="info"):
    if level == "error": app_log.error(msg)
    elif level == "warning": app_log.warning(msg)
    elif level == "critical": app_log.critical(f"*** CRITICAL FAILURE *** {msg}")
    else: app_log.info(msg)

# ----------------------------
# INTEGRITY & UTILS
# ----------------------------
def get_file_hash(filepath):
    """Generate MD5 hash."""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def send_alert(subject, body, include_logs=True):
    # 1. Email Alert
    email_host = os.getenv('EMAIL_HOST')
    email_port = int(os.getenv('EMAIL_PORT', 587))
    email_user = os.getenv('EMAIL_HOST_USER')
    email_pass = os.getenv('EMAIL_HOST_PASSWORD')
    target_email = os.getenv('ADMIN_EMAIL', email_user)

    if all([email_host, email_user, email_pass]):
        try:
            msg = MIMEMultipart()
            msg['From'] = email_user
            msg['To'] = target_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            if include_logs:
                try:
                    with open(log_file, "r") as f:
                        logs = f.readlines()[-30:]
                        msg.attach(MIMEText("\n\n--- AUDIT LOG SNIPPET ---\n" + "".join(logs), 'plain'))
                except: pass
            server = smtplib.SMTP(email_host, email_port)
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
            server.quit()
        except Exception as e: log(f"Email failed: {e}", level="error")
    
    # 2. Webhook Alert
    webhook_url = os.getenv('ALERT_WEBHOOK_URL')
    if webhook_url:
        try:
            requests.post(webhook_url, json={"text": f"*{subject}*\n{body}"}, timeout=5)
        except: pass

    # 3. Telegram Alert (Escalation)
    tg_token = os.getenv('TELEGRAM_BOT_TOKEN')
    tg_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if tg_token and tg_chat_id:
        try:
            tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            requests.post(tg_url, json={"chat_id": tg_chat_id, "text": f"🚨 *{subject}*\n{body}", "parse_mode": "Markdown"}, timeout=5)
        except: pass

# ----------------------------
# HEALTH CHECKS
# ----------------------------
def api_health_check(service):
    log("Running Enterprise API Health Checks...")
    checks = {
        "Google Drive": False,
        "Supabase Storage": False,
        "AWS S3": "N/A"
    }
    
    # 1. Google Drive Check
    try:
        service.about().get(fields='user').execute()
        checks["Google Drive"] = True
    except Exception as e:
        log(f"Google Drive API: FAILED ({e})", level="error")
        
    # 2. Supabase Check
    if supabase:
        try:
            supabase.storage.list_buckets()
            checks["Supabase Storage"] = True
        except Exception as e:
            log(f"Supabase Storage: FAILED ({e})", level="error")
            
    # 3. AWS S3 Check
    if s3_client and s3_bucket:
        try:
            s3_client.head_bucket(Bucket=s3_bucket)
            checks["AWS S3"] = True
        except Exception as e:
            log(f"AWS S3: FAILED ({e})", level="warning")
            checks["AWS S3"] = False

    return checks

# ----------------------------
# MULTI-CLOUD UPLOAD
# ----------------------------
def multi_cloud_upload(filepath, gdrive_folder_id, s3_prefix):
    name = os.path.basename(filepath)
    local_hash = get_file_hash(filepath)
    success = {"gdrive": False, "s3": "N/A"}

    # 1. Google Drive
    try:
        from googleapiclient.http import MediaFileUpload
        service = authenticate_drive()
        media = MediaFileUpload(filepath, resumable=True)
        file_drive = service.files().create(
            body={'name': name, 'parents': [gdrive_folder_id]}, 
            media_body=media,
            fields='id, md5Checksum'
        ).execute()
        
        drive_hash = file_drive.get('md5Checksum')
        if drive_hash and drive_hash.lower() == local_hash.lower():
            log(f"GDRIVE VERIFIED: {name}")
            success["gdrive"] = True
    except Exception as e:
        log(f"GDRIVE UPLOAD FAILED: {name} ({e})", level="error")

    # 2. AWS S3 (Optional Redundancy)
    if s3_client and s3_bucket:
        try:
            s3_path = f"{s3_prefix}/{name}"
            s3_client.upload_file(filepath, s3_bucket, s3_path)
            log(f"S3 VERIFIED: {name}")
            success["s3"] = True
        except Exception as e:
            log(f"S3 UPLOAD FAILED: {name} ({e})", level="warning")
            success["s3"] = False

    return success

# ----------------------------
# CORE LOGIC
# ----------------------------
def authenticate_drive():
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(token_file, 'w') as token: token.write(creds.to_json())
        except: creds = None
    if not creds or not creds.valid:
        if not os.path.exists(creds_file): raise FileNotFoundError(f"Missing {creds_file}")
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token: token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id: query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    if items: return items[0]['id']
    file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id: file_metadata['parents'] = [parent_id]
    return service.files().create(body=file_metadata, fields='id').execute().get('id')

# ----------------------------
# MAIN EXECUTION
# ----------------------------
def run_backup():
    if os.path.exists(lock_file):
        age = (time.time() - os.path.getmtime(lock_file)) / 3600
        if age > 2: os.remove(lock_file)
        else: return

    start_time = time.time()
    db_success = False
    pdf_success = False
    stats = {"pdfs_found": 0, "pdfs_saved": 0, "pdfs_failed": 0}

    try:
        with open(lock_file, "w") as f: f.write(str(os.getpid()))
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        date_str = now_utc.strftime('%Y-%m-%d')
        
        log("=" * 60)
        log(f"EDUAIMSTHINKER ENTERPRISE BACKUP {VERSION}")
        log("=" * 60)

        service = authenticate_drive()
        health = api_health_check(service)
        if not health["Google Drive"] or not health["Supabase Storage"]:
            raise RuntimeError(f"Critical API health check failed: {health}")

        root_id = get_or_create_folder(service, "EduAimsThinker_Backups")
        db_folder_id = get_or_create_folder(service, "database", parent_id=root_id)
        pdf_root_id = get_or_create_folder(service, "pdfs", parent_id=root_id)

        # 1. Database
        try:
            db_url = os.getenv('DATABASE_URL')
            db_file = f"db_backup_{date_str}.sql"
            log("Dumping Database...")
            subprocess.run(f'pg_dump "{db_url}" > "{db_file}"', shell=True, check=True, capture_output=True)
            
            res = multi_cloud_upload(db_file, db_folder_id, "database")
            if res["gdrive"]:
                db_success = True
                log("DB_BACKUP_SUCCESS")
            os.remove(db_file)
        except Exception as e:
            log(f"Database backup failed: {e}", level="error")

        # 2. PDFs from Supabase
        try:
            os.makedirs("pdf_temp", exist_ok=True)
            log("Fetching PDF list from Supabase Storage...")
            
            res = supabase.storage.from_(supabase_bucket).list('documents')
            items = [f for f in res if f['name'].lower().endswith('.pdf')]
            stats["pdfs_found"] = len(items)
            
            # COST GUARDRAIL: Check total estimated size
            total_size = sum(f.get('metadata', {}).get('size', 0) for f in res)
            if total_size > 500 * 1024 * 1024: # 500MB Threshold
                log(f"COST ALERT: Archival payload ({total_size/1024/1024:.1f}MB) exceeds safety threshold!", level="warning")
                send_alert("⚠️ EduAimsThinker Cost Guardrail Breach", f"Total PDF storage size ({total_size/1024/1024:.1f}MB) is approaching free tier limits.")

            if items:
                daily_folder = get_or_create_folder(service, date_str, parent_id=pdf_root_id)
                for item in items:
                    name = item['name']
                    path = os.path.join("pdf_temp", name)
                    
                    with open(path, "wb") as f:
                        f.write(supabase.storage.from_(supabase_bucket).download(f"documents/{name}"))
                    
                    res = multi_cloud_upload(path, daily_folder, f"pdfs/{date_str}")
                    if res["gdrive"]:
                        stats["pdfs_saved"] += 1
                    else: stats["pdfs_failed"] += 1
                    os.remove(path)
                
                if stats["pdfs_saved"] == stats["pdfs_found"] and stats["pdfs_found"] > 0:
                    pdf_success = True
                    log("PDF_BACKUP_SUCCESS")
            else:
                pdf_success = True 
                log("PDF_BACKUP_SUCCESS (Empty)")
            
            shutil.rmtree("pdf_temp", ignore_errors=True)
        except Exception as e:
            log(f"Supabase PDF backup failed: {e}", level="error")

        # Final Summary
        duration = time.time() - start_time
        log("-" * 60)
        log("BACKUP SUMMARY REPORT")
        log(f"Duration: {duration:.1f}s")
        log(f"Database: {'SUCCESS' if db_success else 'FAILED'}")
        log(f"PDFs: {stats['pdfs_saved']}/{stats['pdfs_found']} saved")
        log("-" * 60)

        if db_success and pdf_success:
            with open(success_file, "w") as f: f.write(now_utc.strftime('%Y-%m-%d %H:%M:%S'))
            log("FULL_PIPELINE_SUCCESS")
        else:
            log("PARTIAL_PIPELINE_FAILURE", level="warning")
            send_alert("⚠️ EduAimsThinker Backup: PARTIAL FAILURE", 
                      f"Database: {'OK' if db_success else 'FAIL'}\nPDFs: {stats['pdfs_saved']}/{stats['pdfs_found']}")

    except Exception as e:
        log(f"CRITICAL SYSTEM ERROR: {e}", level="critical")
        send_alert("🚨 EduAimsThinker Backup: CRITICAL SYSTEM ERROR", f"Error: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(lock_file): os.remove(lock_file)
        log("=" * 60)

if __name__ == "__main__":
    run_backup()
