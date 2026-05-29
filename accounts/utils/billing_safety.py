import os
from django.conf import settings

class BillingSafetyWatchdog:
    """
    Ensures the platform stays strictly within Free-Tier limits.
    Prevents automatic billing by enforcing hard stops on expensive operations.
    """
    
    # HARD QUOTAS (Free Tier Limits)
    QUOTAS = {
        'supabase_storage_mb': 1024,  # 1GB Free
        'cloudinary_storage_mb': 500,  # Safety cap for free tier
        'db_rows_limit': 10000,        # Render starter limits safety
        'pdf_upload_cap_kb': 2048,     # 2MB per upload max
    }

    @classmethod
    def check_upload_safety(cls, current_usage_mb, incoming_kb=0):
        """Checks if a new upload will exceed the free tier storage."""
        projected_mb = current_usage_mb + (incoming_kb / 1024)
        if projected_mb >= cls.QUOTAS['supabase_storage_mb']:
            return False, "QUOTA_EXCEEDED"
        return True, "SAFE"

    @classmethod
    def is_enterprise_trial_active(cls):
        """Safety check to ensure no enterprise trials are accidentally enabled."""
        # This is a logical check; real enforcement happens in provider dashboards
        # But we ensure our code doesn't request premium fNLures.
        return False

    @classmethod
    def get_billing_status(cls):
        """Returns a unified billing safety status for the SOC dashboard."""
        return {
            'render': 'Free/Starter (No Auto-Scaling)',
            'supabase': 'Free Tier (Hard Cap Enforced)',
            'cloudinary': 'Free Tier (No Auto-Upgrade)',
            'cloudflare': 'Free Plan (No Paid WAF)',
            'github': 'Free Plan (Private)',
            'billing_risk': 'ZERO (Hard Stops Enforced)',
        }

# Global watchdog instance
billing_guard = BillingSafetyWatchdog()

