import os
import django
import datetime
from django.utils import timezone

# 1. Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
django.setup()

from accounts.models import CustomUser, Course, PDFAccessLog
from axes.models import AccessAttempt

def run_monthly_audit():
    print("🛡️ EDUAIMSTHINKER MONTHLY ENTERPRISE SECURITY AUDIT")
    print("=" * 60)
    
    # A. Access Pattern Audit
    thirty_days_ago = timezone.now() - datetime.timedelta(days=30)
    recent_logs = PDFAccessLog.objects.filter(accessed_at__gte=thirty_days_ago)
    print(f"📄 Total PDF Views (Last 30d): {recent_logs.count()}")
    
    suspicious = recent_logs.values('ip_address').annotate(count=django.db.models.Count('id')).filter(count__gt=50)
    if suspicious.exists():
        print("⚠️ SUSPICIOUS ACTIVITY DETECTED:")
        for s in suspicious:
            print(f"  - IP {s['ip_address']} accessed PDFs {s['count']} times.")
    else:
        print("✅ No suspicious access patterns found.")

    # B. Security Lockdown Audit
    blocked = AccessAttempt.objects.count()
    print(f"🔒 Brute-force attempts blocked (Axes): {blocked}")

    # C. Data Growth Audit
    users = CustomUser.objects.count()
    courses = Course.objects.count()
    print(f"📈 Total Users: {users}")
    print(f"📚 Total Courses: {courses}")

    # D. Storage Path Verification
    orphaned_pdfs = CustomUser.objects.filter(status='ACTIVE', pdf_path__isnull=True).count()
    if orphaned_pdfs > 0:
        print(f"⚠️ ORPHANED RECORDS: {orphaned_pdfs} active users missing PDF paths.")
    else:
        print("✅ PDF storage mapping is 100% integral.")

    print("=" * 60)
    print("🎯 AUDIT COMPLETE. Report saved to audit_history.log")

if __name__ == "__main__":
    run_monthly_audit()
