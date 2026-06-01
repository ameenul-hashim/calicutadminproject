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
    """Real-time stats for signup proof PDFs stored via supabase_storage.py"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")

    client = _init_supabase(url, key)
    if not client:
        return {
            'label': 'Signup Proof PDFs',
            'status': 'disconnected',
            'total_files': 0,
            'usage_mb': 0,
            'limit_mb': SUPABASE_LIMIT_MB,
            'percent': 0,
            'remaining_mb': SUPABASE_LIMIT_MB,
            'files': [],
        }

    files = _list_all_files(client, bucket)
    total_files = len(files)
    total_size = sum(
        int(f.get('metadata', {}).get('size', 0))
        for f in files if f.get('metadata')
    )
    usage_mb = total_size / (1024 * 1024)
    percent = min((usage_mb / SUPABASE_LIMIT_MB) * 100, 100) if SUPABASE_LIMIT_MB else 0

    return {
        'label': 'Signup Proof PDFs',
        'status': 'connected',
        'total_files': total_files,
        'usage_mb': round(usage_mb, 2),
        'limit_mb': SUPABASE_LIMIT_MB,
        'percent': round(percent, 1),
        'remaining_mb': round(max(SUPABASE_LIMIT_MB - usage_mb, 0), 2),
        'files': sorted(files, key=lambda f: f.get('created_at', ''), reverse=True)[:20],
        'emoji': '📄',
        'color': '#6366f1',
        'description': 'Teacher verification PDFs uploaded during signup',
    }


def get_supabase_resource_stats():
    """Real-time stats for course resource files stored via storage_manager.py"""
    url = os.getenv("RESOURCE_SUPABASE_URL")
    key = os.getenv("RESOURCE_SUPABASE_SERVICE_ROLE_KEY")

    client = _init_supabase(url, key)
    if not client:
        return {
            'label': 'Course Resources',
            'status': 'disconnected',
            'total_files': 0,
            'usage_mb': 0,
            'limit_mb': SUPABASE_LIMIT_MB,
            'percent': 0,
            'remaining_mb': SUPABASE_LIMIT_MB,
            'files': [],
        }

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
    """Real-time PostgreSQL database size"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database())")
            db_size_bytes = cursor.fetchone()[0]
        usage_mb = db_size_bytes / (1024 * 1024)
        percent = min((usage_mb / DB_LIMIT_MB) * 100, 100) if DB_LIMIT_MB else 0
        return {
            'label': 'PostgreSQL Database',
            'status': 'connected',
            'usage_mb': round(usage_mb, 2),
            'limit_mb': DB_LIMIT_MB,
            'percent': round(percent, 1),
            'remaining_mb': round(max(DB_LIMIT_MB - usage_mb, 0), 2),
            'emoji': '🗄️',
            'color': '#3b82f6',
            'description': 'All platform data: users, courses, lessons, enrollments',
        }
    except Exception as e:
        logger.error(f"Database stats error: {e}")
        return {
            'label': 'PostgreSQL Database',
            'status': 'disconnected',
            'usage_mb': 0,
            'limit_mb': DB_LIMIT_MB,
            'percent': 0,
            'remaining_mb': DB_LIMIT_MB,
            'emoji': '🗄️',
            'color': '#3b82f6',
            'description': 'All platform data: users, courses, lessons, enrollments',
        }


def get_all_storage_stats():
    return {
        'supabase_signup': get_supabase_signup_stats(),
        'supabase_resources': get_supabase_resource_stats(),
        'cloudinary': get_cloudinary_stats(),
        'database': get_database_stats(),
    }
