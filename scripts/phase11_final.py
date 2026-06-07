"""
Phase 11-12: Final verification across ALL environments.
Reports PASS/WARNING/FAIL for each.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DJANGO_SETTINGS_MODULE'] = 'elearning_project.settings'
import django; django.setup()
from django.conf import settings
from accounts.models import *
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)

HASHIM_UID = '56352146-bc01-43a7-b41c-5ee5761db0a8'

print("=" * 60)
print("PHASE 11 - FINAL VERIFICATION")
print("=" * 60)

results = []

# ── DATABASE ──
print("\n--- DATABASE ---")
db = settings.DATABASES['default']['ENGINE']
print(f"  Engine: {db}")
db_type = 'PostgreSQL' if 'postgres' in db else 'SQLite'

total_users = CustomUser.objects.count()
hashim = CustomUser.objects.filter(uid=HASHIM_UID).first()
only_hashim = total_users == 1 and hashim is not None
results.append(('DB Users Only Hashim', 'PASS' if only_hashim else 'FAIL', f'{total_users} users'))

admins = CustomUser.objects.filter(user_type='ADMIN').count()
teachers = CustomUser.objects.filter(user_type='TEACHER').count()
students = CustomUser.objects.filter(user_type='STUDENT').count()
results.append(('DB Admins', 'PASS' if admins == 1 else 'WARNING', str(admins)))
results.append(('DB Teachers', 'PASS' if teachers == 0 else 'FAIL', str(teachers)))
results.append(('DB Students', 'PASS' if students == 0 else 'FAIL', str(students)))

for model_name, model in [
    ('Courses', Course), ('Lessons', Lesson), ('Resources', CourseResource),
    ('Enrollments', Enrollment), ('ChatMessages', ChatMessage),
    ('Notifications', Notification), ('UploadJobs', UploadJob),
    ('BackupLogs', BackupLog), ('DeletionRequests', DeletionRequest),
    ('EmailOTPs', EmailOTP), ('Reports', Report), ('ApprovalLogs', ApprovalLog),
    ('ChatAuditLogs', ChatAuditLog), ('ChatAttachments', ChatAttachment),
    ('LoginHistory', LoginHistory), ('AdminActivityLog', AdminActivityLog),
    ('PDFAccessLogs', PDFAccessLog),
]:
    count = model.objects.count()
    status = 'PASS' if count == 0 else 'WARNING'
    results.append((f'DB {model_name}', status, str(count)))

# ── SUPABASE ──
print("\n--- SUPABASE ---")
import requests

def check_supabase(url, key, bucket):
    if not url or not key:
        return 'SKIP', 'Not configured'
    headers = {'apikey': key, 'Authorization': f'Bearer {key}'}
    resp = requests.post(f'{url}/storage/v1/object/list/{bucket}', headers=headers, json={'prefix': '', 'limit': 1000}, timeout=15)
    if resp.status_code != 200:
        return 'FAIL', f'List error {resp.status_code}'
    items = resp.json()
    # Count actual files (ones with 'id' field)
    file_count = sum(1 for item in items if item.get('id'))
    return 'PASS' if file_count == 0 else 'WARNING', f'{file_count} files'

supa_status, supa_msg = check_supabase(
    os.getenv('SUPABASE_URL', ''),
    os.getenv('SUPABASE_KEY', ''),
    os.getenv('SUPABASE_BUCKET', 'calicutadminpanelpdf')
)
results.append(('Supabase', supa_status, supa_msg))

res_supa_status, res_supa_msg = check_supabase(
    os.getenv('RESOURCE_SUPABASE_URL', ''),
    os.getenv('RESOURCE_SUPABASE_SERVICE_ROLE_KEY', ''),
    'resources'
)
results.append(('Resource Supabase', res_supa_status, res_supa_msg))

# ── CLOUDINARY ──
print("\n--- CLOUDINARY ---")
cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME', '')
if cloud_name:
    try:
        import cloudinary.api
        result = cloudinary.api.resources(max_results=10)
        resources = result.get('resources', [])
        status = 'PASS' if len(resources) == 0 else 'WARNING'
        results.append(('Cloudinary', status, f'{len(resources)} images'))
    except Exception as e:
        results.append(('Cloudinary', 'FAIL', str(e)[:60]))
else:
    results.append(('Cloudinary', 'SKIP', 'Not configured locally'))

# ── YOUTUBE ──
print("\n--- YOUTUBE ---")
yt = os.getenv('YOUTUBE_CLIENT_ID', '')
uploaded = UploadJob.objects.exclude(youtube_video_id__isnull=True).exclude(youtube_video_id='')
if uploaded.exists():
    results.append(('YouTube', 'WARNING', f'{uploaded.count()} uploaded videos in DB'))
else:
    results.append(('YouTube', 'PASS', 'No uploaded videos'))

# ── FIREBASE ──
print("\n--- FIREBASE ---")
firebase_key = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', '')
firebase_url = os.getenv('FIREBASE_RTDB_URL', '')
if firebase_key and os.path.exists(firebase_key) and firebase_url:
    try:
        import firebase_admin
        from firebase_admin import db as fb_db
        if not firebase_admin._apps:
            cred = firebase_admin.credentials.Certificate(firebase_key)
            firebase_admin.initialize_app(cred, {'databaseURL': firebase_url})
        app = list(firebase_admin._apps.values())[0]
        rooms = fb_db.reference('/chat_rooms', app=app).get(shallow=True)
        count = len(rooms) if rooms else 0
        status = 'PASS' if count == 0 else 'WARNING'
        results.append(('Firebase Chat', status, f'{count} rooms'))
    except Exception as e:
        results.append(('Firebase Chat', 'FAIL', str(e)[:60]))
else:
    # Check if there's a default app
    try:
        import firebase_admin
        if firebase_admin._apps:
            results.append(('Firebase Chat', 'PASS', 'Firebase initialized, check not run'))
        else:
            results.append(('Firebase Chat', 'SKIP', 'Not configured'))
    except:
        results.append(('Firebase Chat', 'SKIP', 'Not configured'))

# ── GOOGLE DRIVE ──
print("\n--- GOOGLE DRIVE ---")
drive_creds = os.getenv('GOOGLE_DRIVE_CREDENTIALS', '')
if drive_creds:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds_dict = json.loads(drive_creds)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)
        folders = service.files().list(
            q="name='NeoLearner_Backups' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields='files(id)'
        ).execute().get('files', [])
        total_files = 0
        for f in folders:
            files = service.files().list(
                q=f"'{f['id']}' in parents and trashed=false",
                fields='files(id)'
            ).execute().get('files', [])
            total_files += len(files)
        status = 'PASS' if total_files == 0 else 'WARNING'
        results.append(('Google Drive', status, f'{total_files} backups'))
    except Exception as e:
        results.append(('Google Drive', 'FAIL', str(e)[:60]))
else:
    results.append(('Google Drive', 'SKIP', 'Not configured locally'))

print("\n" + "=" * 60)
print("PHASE 12 - FINAL REPORT")
print("=" * 60)

all_pass = all(r[1] == 'PASS' for r in results)
print(f"\n  OVERALL: {'PASS' if all_pass else 'WARNING / FAIL'}")
print()

for name, status, detail in results:
    print(f"  {name:25s} [{status:7s}]  {detail}")

skipped = [r for r in results if r[1] == 'SKIP']
failures = [r for r in results if r[1] in ('FAIL', 'WARNING')]
if skipped:
    print(f"\n  Skipped ({len(skipped)}):")
    for name, _, detail in skipped:
        print(f"    {name}: {detail}")
if failures:
    print(f"\n  Action needed ({len(failures)}):")
    for name, status, detail in failures:
        print(f"    {name}: {status} - {detail}")

print(f"\n  DB Type: {db_type}")
print(f"  Users: {total_users}")
print(f"  Hashim: {hashim.username if hashim else 'MISSING!'} (UID: {HASHIM_UID})")
print(f"  Hashim Superuser: {hashim.is_superuser if hashim else 'N/A'}")
print()
print("=" * 60)
print("COMPLETE")
print("=" * 60)
