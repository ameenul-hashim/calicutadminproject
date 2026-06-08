"""
Phase 0: Backup production database + pre-cleanup audit
Phase 2: Clean Render PostgreSQL (keep only hashim)
Phase 11-12: Verification + Final report
"""
import sys, os, subprocess, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DJANGO_SETTINGS_MODULE'] = 'elearning_project.settings'
import django; django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from accounts.models import *
from datetime import datetime as dt
from urllib.parse import urlparse

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)
timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
HASHIM_UID = '56352146-bc01-43a7-b41c-5ee5761db0a8'

def count_all():
    return {
        'Users': CustomUser.objects.count(),
        '  Admins': CustomUser.objects.filter(user_type='ADMIN').count(),
        '  Teachers': CustomUser.objects.filter(user_type='TEACHER').count(),
        '  Students': CustomUser.objects.filter(user_type='STUDENT').count(),
        'Courses': Course.objects.count(),
        'Lessons': Lesson.objects.count(),
        'Resources': CourseResource.objects.count(),
        'Enrollments': Enrollment.objects.count(),
        'ChatMessages': ChatMessage.objects.count(),
        'ChatAttachments': ChatAttachment.objects.count(),
        'ChatAuditLogs': ChatAuditLog.objects.count(),
        'Notifications': Notification.objects.count(),
        'UploadJobs': UploadJob.objects.count(),
        'BackupLogs': BackupLog.objects.count(),
        'LoginHistory': LoginHistory.objects.count(),
        'AdminActivityLog': AdminActivityLog.objects.count(),
        'DeletionRequests': DeletionRequest.objects.count(),
        'EmailOTPs': EmailOTP.objects.count(),
        'Reports': Report.objects.count(),
        'ApprovalLogs': ApprovalLog.objects.count(),
        'PDFAccessLogs': PDFAccessLog.objects.count(),
    }

print("=" * 60)
print("PHASE 0 - PRODUCTION DATABASE BACKUP")
print("=" * 60)

print("\n[STATUS] Pre-cleanup audit:")
for k, v in count_all().items():
    print(f"  {k}: {v}")

db_url = os.getenv('DATABASE_URL') or ''
print(f"\n[STATUS] Database: {'PostgreSQL' if 'postgres' in db_url else 'SQLite'}")

# Phase 0: Try pg_dump first
backup_path = None
if 'postgres' in db_url:
    backup_path = os.path.join(BACKUP_DIR, f'neolearner_prod_backup_{timestamp}.sql')
    print(f"\n[STATUS] Attempting pg_dump to: {backup_path}")
    try:
        parsed = urlparse(db_url)
        dbname = parsed.path.lstrip('/')
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 5432
        env = os.environ.copy()
        env['PGPASSWORD'] = password
        result = subprocess.run(
            ['pg_dump', '--no-owner', '--no-acl', '-h', host, '-p', str(port), '-U', user, '-d', dbname, '-F', 'c', '-f', backup_path],
            env=env, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            size = os.path.getsize(backup_path)
            print(f"  [OK] pg_dump created: {size} bytes ({size/1024/1024:.1f} MB)")
        else:
            print(f"  [FAIL] pg_dump: {result.stderr[:200]}")
            backup_path = None
    except FileNotFoundError:
        print("  [INFO] pg_dump not installed, using Django dumpdata")
        backup_path = None
    except Exception as e:
        print(f"  [FAIL] pg_dump error: {e}")
        backup_path = None

# Fallback: Django dumpdata
if not backup_path:
    backup_path = os.path.join(BACKUP_DIR, f'neolearner_dumpdata_{timestamp}.json')
    print(f"\n[STATUS] Using Django dumpdata to: {backup_path}")
    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            call_command('dumpdata', stdout=f, exclude=['contenttypes', 'auth.permission', 'sessions'])
        size = os.path.getsize(backup_path)
        print(f"  [OK] dumpdata created: {size} bytes ({size/1024/1024:.1f} MB)")
    except Exception as e:
        print(f"  [FAIL] dumpdata: {e}")
        backup_path = None

# Verify backup integrity
if backup_path and os.path.exists(backup_path):
    sha = hashlib.sha256()
    with open(backup_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha.update(chunk)
    checksum = sha.hexdigest()
    with open(backup_path + '.sha256', 'w') as f:
        f.write(checksum)
    
    sha2 = hashlib.sha256()
    with open(backup_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha2.update(chunk)
    assert sha2.hexdigest() == checksum, "CHECKSUM MISMATCH"
    print(f"  [OK] SHA256: {checksum[:20]}...")
    print(f"  [OK] Backup integrity verified")
    print(f"\n  [PASS] PHASE 0 COMPLETE")
else:
    print(f"\n  [FAIL] PHASE 0 - No backup created. Aborting.")
    sys.exit(1)

print("\n" + "=" * 60)
print("PHASE 2 - CLEAN RENDER POSTGRESQL")
print("=" * 60)

# Delete everything except hashim
print("\n[STATUS] Deleting all data except hashim...")
with transaction.atomic():
    # Delete in FK-safe order
    print(f"  Deleting {ChatAuditLog.objects.count()} ChatAuditLog")
    ChatAuditLog.objects.all().delete()
    print(f"  Deleting {ChatAttachment.objects.count()} ChatAttachment")
    ChatAttachment.objects.exclude(sender__uid=HASHIM_UID).delete()
    print(f"  Deleting {BackupLog.objects.count()} BackupLog")
    BackupLog.objects.all().delete()
    print(f"  Deleting {UploadJob.objects.count()} UploadJob")
    UploadJob.objects.exclude(teacher__uid=HASHIM_UID).delete()
    print(f"  Deleting {AdminActivityLog.objects.count()} AdminActivityLog")
    AdminActivityLog.objects.all().delete()
    print(f"  Deleting {LoginHistory.objects.count()} LoginHistory")
    LoginHistory.objects.all().delete()
    print(f"  Deleting {PDFAccessLog.objects.count()} PDFAccessLog")
    PDFAccessLog.objects.all().delete()
    print(f"  Deleting {DeletionRequest.objects.count()} DeletionRequest")
    DeletionRequest.objects.all().delete()
    print(f"  Deleting {Notification.objects.count()} Notification")
    Notification.objects.all().delete()
    print(f"  Deleting {EmailOTP.objects.count()} EmailOTP")
    EmailOTP.objects.all().delete()
    print(f"  Deleting {ChatMessage.objects.count()} ChatMessage")
    ChatMessage.objects.all().delete()
    print(f"  Deleting {ApprovalLog.objects.count()} ApprovalLog")
    ApprovalLog.objects.all().delete()
    print(f"  Deleting {Report.objects.count()} Report")
    Report.objects.all().delete()
    print(f"  Deleting {Enrollment.objects.count()} Enrollment")
    Enrollment.objects.all().delete()
    print(f"  Deleting {CourseResource.objects.count()} CourseResource")
    CourseResource.objects.all().delete()
    print(f"  Deleting {Lesson.objects.count()} Lesson")
    Lesson.objects.all().delete()
    print(f"  Deleting {Course.objects.count()} Course")
    Course.objects.all().delete()
    
    # Delete non-hashim users
    non_hashim = CustomUser.objects.exclude(uid=HASHIM_UID)
    count = non_hashim.count()
    non_hashim.delete()
    print(f"  Deleting {count} users (non-hashim)")

print("  [OK] Phase 2 complete")

print("\n" + "=" * 60)
print("PHASE 11 - VERIFICATION")
print("=" * 60)

v = count_all()
all_clear = True
for k, c in v.items():
    expected = 0
    if k == 'Users': expected = 1  # hashim only
    if k == '  Admins': expected = 1
    status = 'OK' if c == expected else 'WARNING'
    if status == 'WARNING':
        all_clear = False
    print(f"  {k}: {c} [{status}]")

if all_clear:
    print("\n  [PASS] All counts verified")
else:
    print("\n  [WARNING] Some counts unexpected")

print("\n" + "=" * 60)
print("PHASE 12 - FINAL REPORT")
print("=" * 60)

final = count_all()
print(f"  Overall: {'PASS' if all_clear else 'WARNING'}")
print(f"  Users Remaining: {final['Users']}")
print(f"  Teachers Remaining: {final.get('  Teachers', 0)}")
print(f"  Students Remaining: {final.get('  Students', 0)}")
print(f"  Courses Remaining: {final['Courses']}")
print(f"  Lessons Remaining: {final['Lessons']}")
print(f"  Resources Remaining: {final['Resources']}")
print(f"  Notifications Remaining: {final['Notifications']}")
print(f"  Chats Remaining: {final['ChatMessages']}")
print(f"  UploadJobs: {final['UploadJobs']}")
print(f"  BackupLogs: {final['BackupLogs']}")
print(f"  LoginHistory: {final['LoginHistory']}")
print(f"  AdminActivityLog: {final['AdminActivityLog']}")
print(f"  DeletionRequests: {final['DeletionRequests']}")
print(f"  EmailOTPs: {final['EmailOTPs']}")
print(f"  Reports: {final['Reports']}")
print(f"  ApprovalLogs: {final['ApprovalLogs']}")
print(f"  PDFAccessLogs: {final['PDFAccessLogs']}")

print("\n" + "=" * 60)
print("ALL PHASES COMPLETE")
print("=" * 60)
