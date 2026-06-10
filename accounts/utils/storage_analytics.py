import os
import json
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
RENDER_RAM_LIMIT_MB = 512
FB_LIMIT_MB = 1024


def _kb(mb):
    return round(mb * 1024, 1)


def _enrich_kb(d):
    d['usage_kb'] = _kb(d.get('usage_mb', 0))
    d['remaining_kb'] = _kb(d.get('remaining_mb', 0))
    d['limit_kb'] = _kb(d.get('limit_mb', 0))
    d['balance_kb'] = d['remaining_kb']
    return d


def _init_supabase(url, key):
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase init error: {e}")
        return None


def _list_files_in_dir(client, bucket, prefix):
    """List files (not subdirectories) in a given prefix path."""
    try:
        return client.storage.from_(bucket).list(prefix) or []
    except Exception as e:
        logger.error(f"Supabase list error (bucket={bucket}, prefix={prefix}): {e}")
        return []


def get_supabase_signup_stats():
    """Stats for signup proof PDFs — matches DB records to Supabase files by directory"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")

    from accounts.models import CustomUser

    active_users = CustomUser.objects.filter(
        pdf_path__isnull=False
    ).exclude(pdf_path='').values('id', 'full_name', 'username', 'user_type', 'pdf_path')

    from collections import defaultdict
    dirs = defaultdict(set)
    path_to_user = {}
    for u in active_users:
        fp = u['pdf_path']
        parts = fp.rsplit('/', 1)
        if len(parts) == 2:
            dirs[parts[0]].add(parts[1])
            path_to_user[parts[1]] = u

    total_files = len(active_users)
    client = _init_supabase(url, key)
    usage_mb = 0
    status = 'connected'
    file_details = []

    if client and dirs:
        try:
            total_size = 0
            for dirname, basenames in dirs.items():
                items = _list_files_in_dir(client, bucket, dirname)
                for item in items or []:
                    nm = item.get('name')
                    if item.get('metadata') and nm in basenames:
                        sz = int(item['metadata'].get('size', 0))
                        total_size += sz
                        user = path_to_user.get(nm, {})
                        file_details.append({
                            'name': nm,
                            'path': f"{dirname}/{nm}",
                            'size_bytes': sz,
                            'size_mb': round(sz / (1024 * 1024), 3),
                            'teacher': user.get('full_name') or user.get('username', '?'),
                            'user_type': user.get('user_type', '?'),
                            'user_id': user.get('id'),
                        })
            usage_mb = total_size / (1024 * 1024)
        except Exception as e:
            logger.error(f"Supabase signup list error: {e}")

    percent = min((usage_mb / SUPABASE_LIMIT_MB) * 100, 100) if SUPABASE_LIMIT_MB else 0
    remaining_mb = round(max(SUPABASE_LIMIT_MB - usage_mb, 0), 2)

    result = {
        'label': 'Signup Proof PDFs',
        'status': status,
        'total_files': total_files,
        'usage_mb': round(usage_mb, 2),
        'limit_mb': SUPABASE_LIMIT_MB,
        'percent': round(percent, 1),
        'remaining_mb': remaining_mb,
        'files': file_details,
        'emoji': '\U0001f4c4',
        'color': '#6366f1',
        'description': 'Teacher verification PDFs uploaded during signup',
    }
    return _enrich_kb(result)


def get_supabase_resource_stats():
    """Stats for course resources - real-time from active DB records only"""
    from accounts.models import CourseResource
    resources = CourseResource.objects.filter(is_deleted=False)
    total_files = resources.count()
    status = 'connected'

    total_bytes = resources.aggregate(total_size=models.Sum('compressed_size'))['total_size'] or 0
    usage_mb = total_bytes / (1024 * 1024)

    percent = min((usage_mb / SUPABASE_LIMIT_MB) * 100, 100) if SUPABASE_LIMIT_MB else 0
    remaining_mb = round(max(SUPABASE_LIMIT_MB - usage_mb, 0), 2)

    recent = resources.select_related('course').order_by('-created_at')[:20]

    result = {
        'label': 'Course Resources',
        'status': status,
        'total_files': total_files,
        'usage_mb': round(usage_mb, 2),
        'limit_mb': SUPABASE_LIMIT_MB,
        'percent': round(percent, 1),
        'remaining_mb': remaining_mb,
        'files': recent,
        'emoji': '\U0001f4da',
        'color': '#10b981',
        'description': 'Study materials (PDFs, DOCX, PPTX) uploaded by teachers',
    }
    return _enrich_kb(result)


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

        result = {
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
            'usage_mb': round(storage_used_mb, 2),
            'limit_mb': round(storage_limit_mb, 2),
            'percent': round(storage_percent, 1),
            'remaining_mb': round(max(storage_limit_mb - storage_used_mb, 0), 2),
            'emoji': '\U0001f5bc\ufe0f',
            'color': '#f59e0b',
            'description': 'Profile photos, course thumbnails, and resource thumbnails',
        }
        return _enrich_kb(result)
    except Exception as e:
        logger.error(f"Cloudinary stats error: {e}")
        result = {
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
            'usage_mb': 0,
            'limit_mb': CLOUDINARY_LIMIT_MB,
            'percent': 0,
            'remaining_mb': CLOUDINARY_LIMIT_MB,
            'emoji': '\U0001f5bc\ufe0f',
            'color': '#f59e0b',
            'description': 'Profile photos, course thumbnails, and resource thumbnails',
        }
        return _enrich_kb(result)


def get_database_stats():
    """PostgreSQL database size — Render PostgreSQL (free tier: 1GB)"""
    RENDER_LIMIT_MB = 1024
    try:
        from accounts.models import CustomUser, Course, Lesson, CourseResource, Enrollment, Notification, ChatMessage
        total_rows = (
            CustomUser.objects.count() +
            Course.objects.count() +
            Lesson.objects.count() +
            CourseResource.objects.count() +
            Enrollment.objects.count() +
            Notification.objects.count() +
            ChatMessage.objects.count()
        )
        usage_mb = total_rows * 0.002
    except Exception:
        usage_mb = 0
    percent = min((usage_mb / RENDER_LIMIT_MB) * 100, 100) if RENDER_LIMIT_MB else 0
    result = {
        'label': 'Render PostgreSQL',
        'status': 'connected',
        'usage_mb': round(usage_mb, 2),
        'limit_mb': RENDER_LIMIT_MB,
        'percent': round(percent, 1),
        'remaining_mb': round(max(RENDER_LIMIT_MB - usage_mb, 0), 2),
        'emoji': '\U0001f418',
        'color': '#3b82f6',
        'description': 'PostgreSQL on Render — users, courses, lessons, enrollments',
    }
    return _enrich_kb(result)


def get_render_memory_stats():
    """Render RAM usage — reads /proc/meminfo on Linux (Render) for real-time data."""
    limit_mb = RENDER_RAM_LIMIT_MB
    usage_mb = 0
    try:
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo') as f:
                data = f.read()
            total_kb = 0
            avail_kb = 0
            for line in data.splitlines():
                if line.startswith('MemTotal:'):
                    total_kb = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    avail_kb = int(line.split()[1])
            if total_kb > 0:
                usage_mb = (total_kb - avail_kb) / 1024
                limit_mb = total_kb / 1024
    except Exception:
        pass

    usage_mb = max(usage_mb, 0)
    percent = min((usage_mb / limit_mb) * 100, 100) if limit_mb else 0

    result = {
        'label': 'Render RAM',
        'status': 'connected',
        'usage_mb': round(usage_mb, 1),
        'limit_mb': round(limit_mb, 1),
        'percent': round(percent, 1),
        'remaining_mb': round(max(limit_mb - usage_mb, 0), 1),
        'emoji': '\U0001f9f1',
        'color': '#8b5cf6',
        'description': 'Render RAM — 512 MB free tier, real-time from /proc/meminfo',
    }
    return result


def get_firebase_rtdb_stats():
    """Firebase Realtime Database stats — audit events, analytics, notifications, with KB"""
    FB_LIMIT_MB = 1024
    db_url = os.getenv('FIREBASE_RTDB_URL')
    if not db_url:
        result = {
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
            'emoji': '\U0001f525',
            'color': '#ef4444',
            'description': 'Real-time audit events, analytics, and security counters',
        }
        return _enrich_kb(result)

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
            result = {
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
                'emoji': '\U0001f525',
                'color': '#ef4444',
                'description': 'Real-time audit events, analytics, and security counters',
            }
            return _enrich_kb(result)

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

        analytics_days = 0
        try:
            analytics_ref = rtdb.reference('/analytics/daily_counts', app=app)
            analytics_data = analytics_ref.get() or {}
            analytics_days = len(analytics_data)
        except Exception:
            pass

        estimated_bytes = (audit_count * 200) + (analytics_days * 500)
        usage_mb = estimated_bytes / (1024 * 1024)
        percent = min((usage_mb / FB_LIMIT_MB) * 100, 100) if FB_LIMIT_MB else 0

        result = {
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
            'emoji': '\U0001f525',
            'color': '#ef4444',
            'description': 'Real-time audit events, analytics, and security counters',
        }
        return _enrich_kb(result)
    except Exception as e:
        logger.error(f"Firebase RTDB stats error: {e}")
        result = {
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
            'emoji': '\U0001f525',
            'color': '#ef4444',
            'description': 'Real-time audit events, analytics, and security counters',
        }
        return _enrich_kb(result)


def get_all_storage_stats():
    return {
        'supabase_signup': get_supabase_signup_stats(),
        'supabase_resources': get_supabase_resource_stats(),
        'cloudinary': get_cloudinary_stats(),
        'database': get_database_stats(),
        'firebase_rtdb': get_firebase_rtdb_stats(),
    }
