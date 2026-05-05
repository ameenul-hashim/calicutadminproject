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

def check_heartbeat():
    heartbeat_file = get_path("last_success.txt")
    max_hours = 25  
    
    if not os.path.exists(heartbeat_file):
        send_alert(
            "⚠️ EduStream Backup Watchdog: MISSING HEARTBEAT (UTC)",
            "The file 'last_success.txt' was not found."
        )
        return

    # Check content which is now UTC string
    try:
        with open(heartbeat_file, "r") as f:
            content = f.read().strip()
            last_success = datetime.datetime.strptime(content, '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    except:
        # Fallback to mtime if file content is invalid
        mtime = os.path.getmtime(heartbeat_file)
        last_success = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    hours_since = (now_utc - last_success).total_seconds() / 3600

    if hours_since > max_hours:
        send_alert(
            "🚨 EduStream Backup Watchdog: STALE BACKUP (UTC)",
            f"The last successful backup was at {last_success} ({hours_since:.1f} hours ago UTC).\n\nThis exceeds the threshold. Please check the server."
        )
    else:
        print(f"Backup is healthy. Last success (UTC): {last_success} ({hours_since:.1f} hours ago)")

if __name__ == "__main__":
    check_heartbeat()
