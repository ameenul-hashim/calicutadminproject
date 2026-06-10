import os
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from accounts.models import BackupLog

logger = logging.getLogger(__name__)


def _get_config(key, default=None):
    try:
        from django.conf import settings as s
        return getattr(s, key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


class Command(BaseCommand):
    help = 'Send daily backup status email report to configured recipients'

    def handle(self, *args, **options):
        to_email = _get_config('BACKUP_REPORT_EMAIL', '')
        if not to_email:
            self.stdout.write(self.style.WARNING('BACKUP_REPORT_EMAIL not set — skipping email report'))
            return

        now = timezone.now()
        yesterday = now - timedelta(hours=24)

        total_all = BackupLog.objects.count()
        success_all = BackupLog.objects.filter(status='SUCCESS').count()
        failed_all = BackupLog.objects.filter(status='FAILED').count()
        pending_all = BackupLog.objects.filter(status__in=['PENDING', 'RUNNING', 'UPLOADING', 'VERIFYING']).count()

        last_24h = BackupLog.objects.filter(created_at__gte=yesterday)
        last_24h_total = last_24h.count()
        last_24h_success = last_24h.filter(status='SUCCESS').count()
        last_24h_failed = last_24h.filter(status='FAILED').count()

        db_last = BackupLog.objects.filter(backup_type='DATABASE', status='SUCCESS').order_by('-created_at').first()
        signup_total = BackupLog.objects.filter(backup_type='SIGNUP_PDF').count()
        resource_total = BackupLog.objects.filter(backup_type='TEACHER_RESOURCE').count()

        from accounts.utils.drive_backup_service import _mega_configured
        drive_ok = _mega_configured()

        overall_rate = (success_all / (total_all or 1)) * 100

        subject = f'[Neo Learner] Daily Backup Report — {now.strftime("%Y-%m-%d")}'

        html = f'''
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; padding: 24px; }}
.container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
h1 {{ font-size: 1.25rem; color: #0f172a; margin-top: 0; }}
.summary {{ background: #f1f5f9; border-radius: 8px; padding: 16px; margin: 16px 0; }}
.row {{ display: flex; justify-content: space-between; padding: 4px 0; }}
.label {{ color: #64748b; }}
.value {{ font-weight: 700; color: #0f172a; }}
.good {{ color: #10b981; }}
.warn {{ color: #f59e0b; }}
.bad {{ color: #ef4444; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }}
th {{ font-size: 0.75rem; text-transform: uppercase; color: #64748b; font-weight: 600; }}
</style></head>
<body>
<div class="container">
<h1>📊 Daily Backup Report</h1>
<p style="color: #64748b;">{now.strftime("%A, %B %d, %Y at %H:%M")}</p>
<div class="summary">
<div class="row"><span class="label">Overall Health</span><span class="value {'good' if overall_rate >= 90 else 'warn' if overall_rate >= 50 else 'bad'}">{overall_rate:.0f}%</span></div>
<div class="row"><span class="label">Total Backups</span><span class="value">{total_all}</span></div>
<div class="row"><span class="label">Successful</span><span class="value good">{success_all}</span></div>
<div class="row"><span class="label">Failed</span><span class="value {'bad' if failed_all > 0 else 'good'}">{failed_all}</span></div>
<div class="row"><span class="label">Pending / Running</span><span class="value">{pending_all}</span></div>
</div>
<h2 style="font-size: 1rem;">Last 24 Hours</h2>
<div class="summary">
<div class="row"><span class="label">Total</span><span class="value">{last_24h_total}</span></div>
<div class="row"><span class="label">Successful</span><span class="value good">{last_24h_success}</span></div>
<div class="row"><span class="label">Failed</span><span class="value {'bad' if last_24h_failed > 0 else 'good'}">{last_24h_failed}</span></div>
</div>
<h2 style="font-size: 1rem;">Storage Summary</h2>
<div class="summary">
<div class="row"><span class="label">Database Backups</span><span class="value">{BackupLog.objects.filter(backup_type='DATABASE').count()}</span></div>
<div class="row"><span class="label">Last Database Backup</span><span class="value">{db_last.created_at.strftime("%Y-%m-%d %H:%M") if db_last else 'Never'}</span></div>
<div class="row"><span class="label">Signup PDF Backups</span><span class="value">{signup_total}</span></div>
<div class="row"><span class="label">Teacher Resource Backups</span><span class="value">{resource_total}</span></div>
<div class="row"><span class="label">MEGA Backup</span><span class="value {'good' if drive_ok else 'bad'}">{'✅ Connected' if drive_ok else '❌ Not configured'}</span></div>
</div>
<p style="color: #94a3b8; font-size: 0.8rem; margin-top: 24px;">
    Generated by Neo Learner Backup System — <a href="https://calicutadmin.onrender.com/customadmin/backup-center/" style="color: #6366f1;">Backup Center</a>
</p>
</div>
</body>
</html>'''

        try:
            from_email = _get_config('DEFAULT_FROM_EMAIL', 'noreply@neolearner.com')
            send_mail(
                subject=subject,
                message='',
                html_message=html,
                from_email=from_email,
                recipient_list=[to_email],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f'Backup report sent to {to_email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to send email: {e}'))
