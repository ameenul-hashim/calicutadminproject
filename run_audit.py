import os, sys, django, io
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
sys.path.insert(0, r'c:\Users\lenov\OneDrive\Desktop\all degree projects\e-learning application')
django.setup()

buf = io.StringIO()
import logging
logging.disable(logging.CRITICAL)

from accounts.models import (
    CustomUser, Course, Lesson, CourseResource, LiveClass,
    Enrollment, ApprovalLog, Report, Notification, ChatMessage,
    EmailOTP, DeletionRequest, PDFAccessLog, LoginHistory, AdminActivityLog
)
from django.db import connection
from django.contrib.sessions.models import Session
from django.utils import timezone

lines = []

lines.append('=== ROW COUNTS ===')
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
        lines.append(f'  {name}: {count} rows')
    except Exception as e:
        lines.append(f'  {name}: ERROR - {e}')

lines.append('')
lines.append('=== SQLITE TABLE SIZES ===')
with connection.cursor() as cursor:
    try:
        cursor.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY SUM(pgsize) DESC")
        rows = cursor.fetchall()
        total = 0
        for row in rows:
            kb = row[1]/1024
            total += row[1]
            lines.append(f'  {row[0]}: {kb:.1f} KB')
        lines.append(f'  ---')
        lines.append(f'  TOTAL: {total/1024:.1f} KB ({total/1024/1024:.3f} MB)')
    except Exception as e:
        lines.append(f'  dbstat not available: {e}')
        db_path = r'c:\Users\lenov\OneDrive\Desktop\all degree projects\e-learning application\db.sqlite3'
        size = os.path.getsize(db_path)
        lines.append(f'  db.sqlite3 file size: {size/1024:.1f} KB')

lines.append('')
lines.append('=== NOTIFICATION DETAILS ===')
total_notif = Notification.objects.count()
unread = Notification.objects.filter(is_read=False).count()
read = Notification.objects.filter(is_read=True).count()
lines.append(f'  Total: {total_notif}  |  Unread: {unread}  |  Read: {read}')

lines.append('')
lines.append('=== USER BREAKDOWN ===')
for utype in ['ADMIN','TEACHER','STUDENT']:
    count = CustomUser.objects.filter(user_type=utype).count()
    lines.append(f'  {utype}: {count}')
for status in ['ACTIVE','PENDING','BLOCKED','REJECTED']:
    count = CustomUser.objects.filter(status=status).count()
    lines.append(f'  Status.{status}: {count}')

lines.append('')
lines.append('=== COURSE STATUS ===')
for s in ['DRAFT','PENDING','PUBLISHED','REJECTED','DELETED']:
    count = Course.objects.filter(status=s).count()
    lines.append(f'  {s}: {count}')

lines.append('')
lines.append('=== RESOURCE STATUS ===')
for s in ['PENDING','APPROVED','REJECTED','DELETION_PENDING']:
    count = CourseResource.objects.filter(status=s).count()
    lines.append(f'  {s}: {count}')
is_deleted_count = CourseResource.objects.filter(is_deleted=True).count()
total_res = CourseResource.objects.count()
lines.append(f'  is_deleted=True (soft-deleted): {is_deleted_count}')
lines.append(f'  Total CourseResource rows: {total_res}')
try:
    all_res = CourseResource.objects.all()
    total_orig = sum(r.original_size or 0 for r in all_res)
    total_comp = sum(r.compressed_size or 0 for r in all_res)
    total_views = sum(r.view_count or 0 for r in all_res)
    total_downloads = sum(r.download_count or 0 for r in all_res)
    lines.append(f'  Total original_size tracked in DB: {total_orig/1024:.1f} KB')
    lines.append(f'  Total compressed_size tracked in DB: {total_comp/1024:.1f} KB')
    lines.append(f'  Total view_count: {total_views}')
    lines.append(f'  Total download_count: {total_downloads}')
except Exception as e:
    lines.append(f'  Resource size calc error: {e}')

lines.append('')
lines.append('=== EMAIL OTP STATUS ===')
total_otp = EmailOTP.objects.count()
used = EmailOTP.objects.filter(is_used=True).count()
unused = EmailOTP.objects.filter(is_used=False).count()
expired = EmailOTP.objects.filter(expires_at__lt=timezone.now()).count()
lines.append(f'  Total: {total_otp}  |  Used: {used}  |  Unused: {unused}  |  Expired: {expired}')

lines.append('')
lines.append('=== DELETION REQUESTS ===')
for s in ['PENDING','APPROVED','REJECTED']:
    count = DeletionRequest.objects.filter(status=s).count()
    lines.append(f'  {s}: {count}')

lines.append('')
lines.append('=== CHAT MESSAGES ===')
total_chat = ChatMessage.objects.count()
soft_deleted_chat = ChatMessage.objects.filter(is_deleted=True).count()
unread_chat = ChatMessage.objects.filter(is_read=False).count()
lines.append(f'  Total: {total_chat}  |  Soft-deleted: {soft_deleted_chat}  |  Unread: {unread_chat}')

lines.append('')
lines.append('=== LOGIN HISTORY ===')
lines.append(f'  Total rows: {LoginHistory.objects.count()}')

lines.append('')
lines.append('=== PDF ACCESS LOG ===')
lines.append(f'  Total rows: {PDFAccessLog.objects.count()}')

lines.append('')
lines.append('=== APPROVAL LOG ===')
lines.append(f'  Total rows: {ApprovalLog.objects.count()}')

lines.append('')
lines.append('=== ADMIN ACTIVITY LOG ===')
lines.append(f'  Total rows: {AdminActivityLog.objects.count()}')

lines.append('')
lines.append('=== DJANGO SESSIONS ===')
lines.append(f'  Total sessions: {Session.objects.count()}')
try:
    expired_sessions = Session.objects.filter(expire_date__lt=timezone.now()).count()
    lines.append(f'  Expired sessions: {expired_sessions}')
except Exception as e:
    lines.append(f'  Error: {e}')

output_path = r'c:\Users\lenov\OneDrive\Desktop\all degree projects\e-learning application\audit_result.log'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('DONE - written to audit_result.log')
