import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
sys.path.insert(0, r'c:\Users\lenov\OneDrive\Desktop\all degree projects\e-learning application')
django.setup()

from accounts.models import (
    CustomUser, Course, Lesson, CourseResource, LiveClass,
    Enrollment, ApprovalLog, Report, Notification, ChatMessage,
    EmailOTP, DeletionRequest, PDFAccessLog, LoginHistory, AdminActivityLog
)
from django.db import connection
from django.contrib.sessions.models import Session

print('=== ROW COUNTS ===')
models_list = [
    ('CustomUser', CustomUser),
    ('Course', Course),
    ('Lesson', Lesson),
    ('CourseResource', CourseResource),
    ('LiveClass', LiveClass),
    ('Enrollment', Enrollment),
    ('ApprovalLog', ApprovalLog),
    ('Report', Report),
    ('Notification', Notification),
    ('ChatMessage', ChatMessage),
    ('EmailOTP', EmailOTP),
    ('DeletionRequest', DeletionRequest),
    ('PDFAccessLog', PDFAccessLog),
    ('LoginHistory', LoginHistory),
    ('AdminActivityLog', AdminActivityLog),
    ('Session', Session),
]
for name, model in models_list:
    try:
        count = model.objects.count()
        print(f'{name}: {count}')
    except Exception as e:
        print(f'{name}: ERROR - {e}')

print()
print('=== SQLITE TABLE SIZES ===')
with connection.cursor() as cursor:
    try:
        cursor.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY SUM(pgsize) DESC")
        rows = cursor.fetchall()
        total = 0
        for row in rows:
            kb = row[1]/1024
            total += row[1]
            print(f'{row[0]}: {kb:.1f} KB')
        print(f'TOTAL DB SIZE: {total/1024:.1f} KB ({total/1024/1024:.3f} MB)')
    except Exception as e:
        print(f'dbstat not available: {e}')
        # fallback: get file size
        import os
        db_path = r'c:\Users\lenov\OneDrive\Desktop\all degree projects\e-learning application\db.sqlite3'
        size = os.path.getsize(db_path)
        print(f'db.sqlite3 file size: {size/1024:.1f} KB ({size/1024/1024:.3f} MB)')

print()
print('=== NOTIFICATION DETAILS ===')
total_notif = Notification.objects.count()
unread = Notification.objects.filter(is_read=False).count()
read = Notification.objects.filter(is_read=True).count()
print(f'Total Notifications: {total_notif}  (Unread: {unread}, Read: {read})')

print()
print('=== USER BREAKDOWN ===')
for utype in ['ADMIN','TEACHER','STUDENT']:
    count = CustomUser.objects.filter(user_type=utype).count()
    print(f'  {utype}: {count}')
for status in ['ACTIVE','PENDING','BLOCKED','REJECTED']:
    count = CustomUser.objects.filter(status=status).count()
    print(f'  Status {status}: {count}')

print()
print('=== COURSE STATUS ===')
for s in ['DRAFT','PENDING','PUBLISHED','REJECTED','DELETED']:
    count = Course.objects.filter(status=s).count()
    print(f'  {s}: {count}')

print()
print('=== RESOURCE STATUS ===')
for s in ['PENDING','APPROVED','REJECTED','DELETION_PENDING']:
    count = CourseResource.objects.filter(status=s).count()
    print(f'  {s}: {count}')
deleted = CourseResource.objects.filter(is_deleted=True).count()
total_res = CourseResource.objects.count()
total_size = sum(r.original_size for r in CourseResource.objects.all())
print(f'  is_deleted=True: {deleted}')
print(f'  Total resources: {total_res}')
print(f'  Total original_size stored: {total_size/1024:.1f} KB ({total_size/1024/1024:.3f} MB)')

print()
print('=== EMAIL OTP STATUS ===')
total_otp = EmailOTP.objects.count()
used = EmailOTP.objects.filter(is_used=True).count()
unused = EmailOTP.objects.filter(is_used=False).count()
from django.utils import timezone
expired = EmailOTP.objects.filter(expires_at__lt=timezone.now()).count()
print(f'Total OTPs: {total_otp}  Used: {used}  Unused: {unused}  Expired: {expired}')

print()
print('=== DELETION REQUESTS ===')
for s in ['PENDING','APPROVED','REJECTED']:
    count = DeletionRequest.objects.filter(status=s).count()
    print(f'  {s}: {count}')

print()
print('=== CHAT MESSAGE STATS ===')
total_chat = ChatMessage.objects.count()
soft_deleted = ChatMessage.objects.filter(is_deleted=True).count()
print(f'Total Messages: {total_chat}  Soft-deleted: {soft_deleted}')

print()
print('=== LOGIN HISTORY ===')
print(f'Total login records: {LoginHistory.objects.count()}')

print()
print('=== PDF ACCESS LOG ===')
print(f'Total PDF access log records: {PDFAccessLog.objects.count()}')

print()
print('=== APPROVAL LOG ===')
print(f'Total approval log entries: {ApprovalLog.objects.count()}')

print()
print('=== ADMIN ACTIVITY LOG ===')
print(f'Total admin activity entries: {AdminActivityLog.objects.count()}')
