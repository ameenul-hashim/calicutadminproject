import os
import logging
from django.conf import settings
from django.db import connection, models
from supabase import create_client
import cloudinary.api
import cloudinary

logger = logging.getLogger(__name__)

SUPABASE_LIMIT_MB = 1024
CLOUDINARY_LIMIT_MB = 25600
DB_LIMIT_MB = 1024


def _init_supabase(url, key):
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase init error: {e}")
        return None


def _list_all_files(client, bucket, prefix=""):
    try:
        if prefix:
            files = client.storage.from_(bucket).list(prefix)
        else:
            files = client.storage.from_(bucket).list()
        return files or []
    except Exception as e:
        logger.error(f"Supabase list error (bucket={bucket}, prefix={prefix}): {e}")
        return []


def get_supabase_signup_stats():
    """Stats for signup proof PDFs - uses DB count as primary, Supabase list as enrichment"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")

    from accounts.models import CustomUser
    total_users_with_pdf = CustomUser.objects.filter(
        pdf_path__isnull=False
    ).exclude(pdf_path='').count()

    client = _init_supabase(url, key)
    total_files = total_users_with_pdf
    usage_mb = 0
    remaining_mb = SUPABASE_LIMIT_MB
    percent = 0
    status = 'connected'

    if client:
        try:
            files = _list_all_files(client, bucket)
            total_size = sum(
                int(f.get('metadata', {}).get('size', 0))
                for f in files if f.get('metadata')
            )
            usage_mb = total_size / (1024 * 1024)
            total_files = max(len(files), total_users_with_pdf)
        except Exception as e:
            logger.error(f"Supabase signup list error: {e}")

    percent = min((usage_mb / SUPABASE_LIMIT_MB) * 100, 100) if SUPABASE_LIMIT_MB else 0
    remaining_mb = round(max(SUPABASE_LIMIT_MB - usage_mb, 0), 2)

    return {
        'label': 'Signup Proof PDFs',
        'status': status,
        'total_files': total_files,
        'usage_mb': round(usage_mb, 2),
        'limit_mb': SUPABASE_LIMIT_MB,
        'percent': round(percent, 1),
        'remaining_mb': remaining_mb,
        'files': [],
        'emoji': '📄',
        'color': '#6366f1',
        'description': 'Teacher verification PDFs uploaded during signup',
    }


def get_supabase_resource_stats():
    """Stats for course resources - uses DB compressed_size, enriched with Supabase if available"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    from accounts.models import CourseResource
    resources = CourseResource.objects.filter(is_deleted=False)
    total_files = resources.count()

    total_compressed = resources.aggregate(total_size=models.Sum('compressed_size'))['total_size'] or 0
    usage_mb = total_compressed / (1024 * 1024)
    percent = min((usage_mb / SUPABASE_LIMIT_MB) * 100, 100) if SUPABASE_LIMIT_MB else 0

    recent = resources.select_related('course').order_by('-created_at')[:20]

    return {
        'label': 'Course Resources',
        'status': 'connected',
        'total_files': total_files,
        'usage_mb': round(usage_mb, 2),
        'limit_mb': SUPABASE_LIMIT_MB,
        'percent': round(percent, 1),
        'remaining_mb': round(max(SUPABASE_LIMIT_MB - usage_mb, 0), 2),
        'files': recent,
        'emoji': '📚',
        'color': '#10b981',
        'description': 'Study materials (PDFs, DOCX, PPTX) uploaded by teachers',
    }


def get_cloudinary_stats():
    """Real-time Cloudinary account usage via Admin API"""
    try:
        usage = cloudinary.api.usage()
        storage = usage.get('storage', {})
        credits = usage.get('credits', {})
        transformations = usage.get('transformations', {})
        resources_usage = usage.get('resources', {})
        images_data = resources_usage.get('image', {}) if resources_usage else {}

        storage_used_mb = storage.get('used', 0) / (1024 * 1024) if storage.get('used') else 0
        storage_limit_mb = storage.get('limit', CLOUDINARY_LIMIT_MB) / (1024 * 1024) if storage.get('limit') else CLOUDINARY_LIMIT_MB
        storage_percent = min((storage_used_mb / storage_limit_mb) * 100, 100) if storage_limit_mb else 0

        return {
            'label': 'Cloudinary Images',
            'status': 'connected',
            'storage_used_mb': round(storage_used_mb, 2),
            'storage_limit_mb': round(storage_limit_mb, 2),
            'storage_percent': round(storage_percent, 1),
            'storage_remaining_mb': round(max(storage_limit_mb - storage_used_mb, 0), 2),
            'credits_used': credits.get('used', 0),
            'credits_limit': credits.get('limit', 0),
            'credits_percent': round(min((credits.get('used', 0) / max(credits.get('limit', 1), 1)) * 100, 100), 1),
            'transformations_used': transformations.get('used', 0),
            'transformations_limit': transformations.get('limit', 0),
            'transformations_percent': round(min((transformations.get('used', 0) / max(transformations.get('limit', 1), 1)) * 100, 100), 1),
            'total_files': usage.get('objects', {}).get('used', 0),
            'images_count': images_data.get('used', 0),
            'emoji': '🖼️',
            'color': '#f59e0b',
            'description': 'Profile photos, course thumbnails, and resource thumbnails',
        }
    except Exception as e:
        logger.error(f"Cloudinary stats error: {e}")
        return {
            'label': 'Cloudinary Images',
            'status': 'disconnected',
            'storage_used_mb': 0,
            'storage_limit_mb': CLOUDINARY_LIMIT_MB,
            'storage_percent': 0,
            'storage_remaining_mb': CLOUDINARY_LIMIT_MB,
            'credits_used': 0,
            'credits_limit': 0,
            'credits_percent': 0,
            'transformations_used': 0,
            'transformations_limit': 0,
            'transformations_percent': 0,
            'total_files': 0,
            'images_count': 0,
            'emoji': '🖼️',
            'color': '#f59e0b',
            'description': 'Profile photos, course thumbnails, and resource thumbnails',
        }


def get_database_stats():
    """PostgreSQL database size — now Neon (free tier: 500MB)"""
    NEON_LIMIT_MB = 500
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database())")
            db_size_bytes = cursor.fetchone()[0]
        usage_mb = db_size_bytes / (1024 * 1024)
    except Exception:
        try:
            from accounts.models import CustomUser, Course, Lesson, CourseResource, ChatMessage
            total_rows = (
                CustomUser.objects.count() +
                Course.objects.count() +
                Lesson.objects.count() +
                CourseResource.objects.count() +
                ChatMessage.objects.count()
            )
            usage_mb = total_rows * 0.5
        except Exception:
            usage_mb = 0
    percent = min((usage_mb / NEON_LIMIT_MB) * 100, 100) if NEON_LIMIT_MB else 0
    return {
        'label': 'Neon Database',
        'status': 'connected',
        'usage_mb': round(usage_mb, 2),
        'limit_mb': NEON_LIMIT_MB,
        'percent': round(percent, 1),
        'remaining_mb': round(max(NEON_LIMIT_MB - usage_mb, 0), 2),
        'emoji': '🐘',
        'color': '#3b82f6',
        'description': 'PostgreSQL on Neon — users, courses, lessons, enrollments',
    }


def get_firebase_rtdb_stats():
    """Firebase Realtime Database stats — audit events, analytics, notifications."""
    FB_LIMIT_MB = 1024  # Firebase free tier: 1GB
    db_url = os.getenv('FIREBASE_RTDB_URL')
    if not db_url:
        return {
            'label': 'Firebase RTDB',
            'status': 'disconnected',
            'usage_mb': 0,
            'limit_mb': FB_LIMIT_MB,
            'percent': 0,
            'remaining_mb': FB_LIMIT_MB,
            'audit_events_24h': 0,
            'audit_count': 0,
            'analytics_days': 0,
            'security_counters': {},
            'emoji': '🔥',
            'color': '#ef4444',
            'description': 'Real-time audit events, analytics, and security counters',
        }

    try:
        import firebase_admin
        from firebase_admin import credentials, db as rtdb

        json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        cred = None
        if json_str:
            cred = credentials.Certificate(json.loads(json_str))
        elif json_path and os.path.exists(json_path):
            cred = credentials.Certificate(json_path)

        app = None
        if cred:
            try:
                app = firebase_admin.get_app('analytics_stats')
            except ValueError:
                app = firebase_admin.initialize_app(
                    cred, {'databaseURL': db_url}, name='analytics_stats'
                )

        if not app:
            return {
                'label': 'Firebase RTDB',
                'status': 'disconnected',
                'usage_mb': 0,
                'limit_mb': FB_LIMIT_MB,
                'percent': 0,
                'remaining_mb': FB_LIMIT_MB,
                'audit_events_24h': 0,
                'audit_count': 0,
                'analytics_days': 0,
                'security_counters': {},
                'emoji': '🔥',
                'color': '#ef4444',
                'description': 'Real-time audit events, analytics, and security counters',
            }

        # Audit events count
        audit_count = 0
        audit_events_24h = 0
        try:
            from datetime import datetime, timedelta, timezone
            audit_ref = rtdb.reference('/audit/events', app=app)
            audit_data = audit_ref.get() or {}
            cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
            for date_key, day_data in audit_data.items():
                if isinstance(day_data, dict):
                    for hour_key, hour_events in day_data.items():
                        if isinstance(hour_events, dict):
                            for eid, entry in hour_events.items():
                                if isinstance(entry, dict):
                                    audit_count += 1
                                    try:
                                        ts = datetime.fromisoformat(entry.get('timestamp', ''))
                                        if ts >= cutoff_24h:
                                            audit_events_24h += 1
                                    except Exception:
                                        pass
        except Exception:
            pass

        # Security counters
        security_counters = {}
        try:
            counter_ref = rtdb.reference('/audit/counters', app=app)
            counter_data = counter_ref.get() or {}
            security_counters = {
                'malware_blocked': counter_data.get('malware_block', 0),
                'failed_login': counter_data.get('failed_login', 0),
                'admin_action': counter_data.get('admin_action', 0),
                'suspicious_travel': counter_data.get('suspicious_travel', 0),
            }
        except Exception:
            pass

        # Analytics days with data
        analytics_days = 0
        try:
            analytics_ref = rtdb.reference('/analytics/daily_counts', app=app)
            analytics_data = analytics_ref.get() or {}
            analytics_days = len(analytics_data)
        except Exception:
            pass

        # Estimate storage (rough: each event ~200 bytes)
        estimated_bytes = (audit_count * 200) + (analytics_days * 500)
        usage_mb = estimated_bytes / (1024 * 1024)
        percent = min((usage_mb / FB_LIMIT_MB) * 100, 100) if FB_LIMIT_MB else 0

        return {
            'label': 'Firebase RTDB',
            'status': 'connected',
            'usage_mb': round(usage_mb, 4),
            'limit_mb': FB_LIMIT_MB,
            'percent': round(percent, 2),
            'remaining_mb': round(max(FB_LIMIT_MB - usage_mb, 0), 2),
            'audit_events_24h': audit_events_24h,
            'audit_count': audit_count,
            'analytics_days': analytics_days,
            'security_counters': security_counters,
            'emoji': '🔥',
            'color': '#ef4444',
            'description': 'Real-time audit events, analytics, and security counters',
        }
    except Exception as e:
        logger.error(f"Firebase RTDB stats error: {e}")
        return {
            'label': 'Firebase RTDB',
            'status': 'error',
            'usage_mb': 0,
            'limit_mb': FB_LIMIT_MB,
            'percent': 0,
            'remaining_mb': FB_LIMIT_MB,
            'audit_events_24h': 0,
            'audit_count': 0,
            'analytics_days': 0,
            'security_counters': {},
            'emoji': '🔥',
            'color': '#ef4444',
            'description': 'Real-time audit events, analytics, and security counters',
        }


def get_all_storage_stats():
    return {
        'supabase_signup': get_supabase_signup_stats(),
        'supabase_resources': get_supabase_resource_stats(),
        'cloudinary': get_cloudinary_stats(),
        'database': get_database_stats(),
        'firebase_rtdb': get_firebase_rtdb_stats(),
    }
