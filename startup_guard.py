import os
import datetime
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Path hardening
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def get_path(filename):
    return os.path.join(BASE_DIR, filename)

# Load config
load_dotenv(get_path(".env"))

def send_alert(subject, body):
    """Send redundant alerts via Email and Webhook."""
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
            server = smtplib.SMTP(email_host, email_port)
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
            server.quit()
        except: pass

    webhook_url = os.getenv('ALERT_WEBHOOK_URL')
    if webhook_url:
        try:
            payload = {"text": f"*{subject}*\n{body}"}
            requests.post(webhook_url, json=payload, timeout=10)
        except: pass

def validate_config():
    """Deep validation of required environment variables and cloud keys."""
    required_vars = [
        "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_BUCKET",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_S3_BUCKET"
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        send_alert("🚨 CRITICAL: Missing Environment Variables", f"The following required keys are missing: {', '.join(missing)}")
        return False

    # 2. Supabase Connectivity Check
    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        create_client(url, key).storage.list_buckets()
    except Exception as e:
        send_alert("🚨 CRITICAL: Supabase Connection Failed", f"Startup check failed to connect to Supabase: {e}")
        return False

    return True

def startup_check():
    print("🚀 EduElevate Startup Guard: Initializing...")
    
    # 1. Config Validation
    if not validate_config():
        print("❌ CONFIG VALIDATION FAILED. Alerts sent.")
    else:
        print("✅ Config Validation Passed.")

    # 2. Backup Freshness Check
    heartbeat_file = get_path("last_success.txt")
    if os.path.exists(heartbeat_file):
        with open(heartbeat_file, 'r') as f:
            try:
                last_ts = f.read().strip()
                last_dt = datetime.datetime.fromisoformat(last_ts)
                hours_since = (datetime.datetime.now() - last_dt).total_seconds() / 3600
                
                if hours_since > 25:
                    send_alert(
                        "🚩 EduElevate Startup Guard: BACKUP IS STALE",
                        f"The system just started up, but the last successful backup was {hours_since:.1f} hours ago ({last_dt})."
                    )
            except: pass
    else:
        send_alert("🚩 EduElevate Startup Guard: BACKUP NEVER SUCCEEDED", "No successful backup record found.")

    print("🎯 Startup Guard Complete.")

if __name__ == "__main__":
    startup_check()
