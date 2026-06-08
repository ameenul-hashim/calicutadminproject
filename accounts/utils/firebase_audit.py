import os
import json
import threading
import logging
import time as time_module
from datetime import datetime, timedelta, timezone

import firebase_admin
from firebase_admin import credentials, db

logger = logging.getLogger(__name__)

_firebase_app = None
_lock = threading.Lock()
_last_cleanup = 0


def _get_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    with _lock:
        if _firebase_app is not None:
            return _firebase_app
        db_url = os.getenv('FIREBASE_RTDB_URL')
        if not db_url:
            logger.warning('Firebase Audit: FIREBASE_RTDB_URL not set')
            return None
        json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        cred_source = None
        if json_str:
            try:
                cred = credentials.Certificate(json.loads(json_str))
                cred_source = 'FIREBASE_SERVICE_ACCOUNT_JSON (env var)'
            except Exception as e:
                logger.error(f'Firebase Audit credential parse failed: {e}')
                return None
        elif json_path:
            try:
                cred = credentials.Certificate(json_path)
                cred_source = f'FIREBASE_SERVICE_ACCOUNT_PATH ({json_path})'
            except Exception as e:
                logger.error(f'Firebase Audit credential load failed from {json_path}: {e}')
                return None
        else:
            logger.warning('Firebase Audit: no credentials set')
            return None
        try:
            _firebase_app = firebase_admin.initialize_app(
                cred, {'databaseURL': db_url}, name='audit'
            )
            logger.info(f'Firebase Audit initialized | source={cred_source} | db_url={db_url}')
        except Exception as e:
            logger.error(f'Firebase Audit initialize_app failed: {e}')
            return None
    return _firebase_app


def _cleanup_old_events(days=14):
    global _last_cleanup
    now = time_module.time()
    if now - _last_cleanup < 3600:
        return
    _last_cleanup = now
    app = _get_app()
    if app is None:
        return
    ref = db.reference('/audit/events', app=app)
    try:
        data = ref.get() or {}
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
        for date_key in list(data.keys()):
            try:
                d = datetime.strptime(date_key, '%Y-%m-%d').date()
                if d < cutoff:
                    ref.child(date_key).delete()
            except ValueError:
                pass
    except Exception:
        pass


def log_security_event(event_type, detail, username=None, ip=None):
    app = _get_app()
    if app is None:
        return
    ref = db.reference('/audit', app=app)
    now = datetime.now(timezone.utc)
    date_key = now.strftime('%Y-%m-%d')
    hour_key = str(now.hour)

    entry = {
        'type': event_type,
        'detail': detail,
        'timestamp': now.isoformat(),
    }
    if username:
        entry['username'] = username
    if ip:
        entry['ip'] = ip

    try:
        events_ref = ref.child(f'events/{date_key}/{hour_key}')
        events_ref.push(entry)

        counter_ref = ref.child(f'counters/{event_type.lower()}')
        counter_ref.transaction(lambda current: (current or 0) + 1)
    except Exception:
        pass

    threading.Thread(target=_cleanup_old_events, daemon=True).start()


def get_recent_events(hours=24):
    app = _get_app()
    if app is None:
        return []
    ref = db.reference('/audit/events', app=app)
    try:
        data = ref.get() or {}
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    results = []
    for date_key, day_data in data.items():
        try:
            d = datetime.strptime(date_key, '%Y-%m-%d').date()
        except ValueError:
            continue
        if isinstance(day_data, dict):
            for hour_key, hour_events in day_data.items():
                if isinstance(hour_events, dict):
                    for eid, entry in hour_events.items():
                        if isinstance(entry, dict):
                            ts_str = entry.get('timestamp', '')
                            try:
                                ts = datetime.fromisoformat(ts_str)
                            except Exception:
                                continue
                            if ts >= cutoff:
                                entry['id'] = eid
                                entry['_date'] = date_key
                                entry['_hour'] = hour_key
                                results.append(entry)
    results.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return results[:50]


def get_security_counters():
    app = _get_app()
    if app is None:
        return {}
    ref = db.reference('/audit/counters', app=app)
    try:
        data = ref.get() or {}
    except Exception:
        return {}
    return {
        'malware_blocked': data.get('malware_block', 0),
        'travel_anomalies': data.get('suspicious_travel', 0),
        'failed_login': data.get('failed_login', 0),
        'admin_action': data.get('admin_action', 0),
        'session_timeout': data.get('session_timeout', 0),
    }


def run_infrastructure_check():
    app = _get_app()
    if app is None:
        return {}
    result = {}
    from django.db import connection
    import time
    try:
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        lat = round((time.time() - start) * 1000, 2)
        result['postgres'] = {'status': 'ONLINE', 'latency': lat}
    except Exception:
        result['postgres'] = {'status': 'OFFLINE', 'latency': 0}

    try:
        from accounts.utils.supabase_storage import supabase
        supabase.storage.list_buckets()
        result['supabase'] = {'status': 'ONLINE'}
    except Exception:
        result['supabase'] = {'status': 'OFFLINE'}

    success_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "last_success.txt"
    )
    if os.path.exists(success_file):
        with open(success_file, "r") as f:
            result['backup'] = {'status': 'HEALTHY', 'last_sync': f.read().strip()}
    else:
        result['backup'] = {'status': 'STALE', 'last_sync': 'Never'}

    try:
        infra_ref = db.reference('/audit/infra', app=app)
        infra_ref.set({
            'postgres': result['postgres'],
            'supabase': result['supabase'],
            'backup': result['backup'],
            'last_check': datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    return result


def run_infrastructure_check_async():
    threading.Thread(target=run_infrastructure_check, daemon=True).start()


def get_infrastructure_status():
    app = _get_app()
    if app is None:
        return {}
    ref = db.reference('/audit/infra', app=app)
    try:
        data = ref.get() or {}
    except Exception:
        return {}
    return data


def save_audit_results(results, username="system"):
    """Save system audit results to Firebase for historical tracking"""
    app = _get_app()
    if app is None:
        return
    now = datetime.now(timezone.utc)
    date_key = now.strftime('%Y-%m-%d')
    try:
        ref = db.reference(f'/audit/snapshots/{date_key}', app=app)
        snap_id = now.strftime('%H-%M-%S')
        ref.child(snap_id).set({
            'timestamp': now.isoformat(),
            'username': username,
            'results': results,
        })
        # Auto-cleanup old snapshots (keep 30 days)
        _cleanup_old_snapshots(app)
    except Exception as e:
        logger.error(f"Failed to save audit results: {e}")


def _cleanup_old_snapshots(app):
    """Remove audit snapshots older than 30 days"""
    try:
        ref = db.reference('/audit/snapshots', app=app)
        data = ref.get() or {}
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)
        for date_key in list(data.keys()):
            try:
                d = datetime.strptime(date_key, '%Y-%m-%d').date()
                if d < cutoff:
                    ref.child(date_key).delete()
            except ValueError:
                pass
    except Exception:
        pass


def save_backup_info(backup_data):
    """Save backup info to Firebase with dynamic count"""
    app = _get_app()
    if app is None:
        return
    now = datetime.now(timezone.utc)
    date_key = now.strftime('%Y-%m-%d')
    try:
        ref = db.reference(f'/backup/history/{date_key}', app=app)
        ref.push({
            'timestamp': now.isoformat(),
            'data': backup_data,
        })
        # Update aggregated counts
        count_ref = db.reference('/backup/counts', app=app)
        count_ref.transaction(lambda current: {
            'total': (current or {}).get('total', 0) + 1,
            'success': (current or {}).get('success', 0) + (1 if backup_data.get('status') == 'SUCCESS' else 0),
            'failed': (current or {}).get('failed', 0) + (1 if backup_data.get('status') == 'FAILED' else 0),
        })
        _cleanup_old_backups(app)
    except Exception as e:
        logger.error(f"Failed to save backup info: {e}")


def _cleanup_old_backups(app):
    """Remove backup entries older than 30 days"""
    try:
        ref = db.reference('/backup/history', app=app)
        data = ref.get() or {}
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=30)
        for date_key in list(data.keys()):
            try:
                d = datetime.strptime(date_key, '%Y-%m-%d').date()
                if d < cutoff:
                    ref.child(date_key).delete()
            except ValueError:
                pass
    except Exception:
        pass


def get_backup_counts():
    """Get backup counts from Firebase"""
    app = _get_app()
    if app is None:
        return {'total': 0, 'success': 0, 'failed': 0}
    try:
        ref = db.reference('/backup/counts', app=app)
        data = ref.get() or {}
        return data
    except Exception:
        return {'total': 0, 'success': 0, 'failed': 0}
