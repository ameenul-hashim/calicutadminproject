import os

head = """import os
import re
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q, Count
from django.db.models.functions import ExtractMonth
from accounts.models import CustomUser, Enrollment, Course, Lesson, ApprovalLog, DeletionRequest, PDFAccessLog
from accounts.utils.cloudinary_helpers import update_image
from accounts.utils.notification_helper import get_notifications, get_unread_count, mark_all_read
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.cache import cache_control
from accounts.utils.supabase_storage import upload_pdf, get_signed_url as get_pdf_url

logger = logging.getLogger(__name__)

def log_admin_activity(request, action, target_user=None, details=""):
    \"\"\"Enterprise helper to track all administrative actions.\"\"\"
    try:
        from accounts.models import AdminActivityLog
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        
        AdminActivityLog.objects.create(
            admin=request.user,
            action=action,
            target_user=target_user,
            details=details,
            ip_address=ip
        )
    except Exception:
        pass

def create_notification(user, message):
    from accounts.models import Notification
    if user.user_type == 'STUDENT':
        return
    Notification.objects.create(user=user, message=message)

@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='admin_login')
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def admin_student_view_auth(request):
    # Direct access as requested - no password required for admin switching
    request.session['student_view_unlocked'] = True
    request.session.set_expiry(0)  # Re-enforce instant expiry
    request.session.modified = True
    messages.success(request, "Switched to Student View. You are now previewing the platform as a student.")
    return redirect('dashboard')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
"""

target_file = 'custom_admin/views.py'
with open(target_file, 'r', encoding='utf-8') as f:
    content = f.read()

if 'def admin_login_view(request):' in content:
    rest = content.split('def admin_login_view(request):')[1]
    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(head + "def admin_login_view(request):" + rest)
    print("Fixed custom_admin/views.py")
else:
    print("Could not find anchor in custom_admin/views.py")
