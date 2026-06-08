import os
import json
import threading
import logging
from datetime import datetime, timedelta, timezone

import firebase_admin
from firebase_admin import credentials, db

logger = logging.getLogger(__name__)

_firebase_app = None
_lock = threading.Lock()


def _get_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    with _lock:
        if _firebase_app is not None:
            return _firebase_app
        db_url = os.getenv('FIREBASE_RTDB_URL')
        if not db_url:
            logger.warning('Firebase Analytics: FIREBASE_RTDB_URL not set')
            return None
        json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        cred_source = None
        if json_str:
            try:
                cred = credentials.Certificate(json.loads(json_str))
                cred_source = 'FIREBASE_SERVICE_ACCOUNT_JSON (env var)'
            except Exception as e:
                logger.error(f'Firebase Analytics credential parse failed: {e}')
                return None
        elif json_path:
            try:
                cred = credentials.Certificate(json_path)
                cred_source = f'FIREBASE_SERVICE_ACCOUNT_PATH ({json_path})'
            except Exception as e:
                logger.error(f'Firebase Analytics credential load failed from {json_path}: {e}')
                return None
        else:
            logger.warning('Firebase Analytics: no credentials set')
            return None
        try:
            _firebase_app = firebase_admin.initialize_app(
                cred, {'databaseURL': db_url}, name='analytics'
            )
            logger.info(f'Firebase Analytics initialized | source={cred_source} | db_url={db_url}')
        except Exception as e:
            logger.error(f'Firebase Analytics initialize_app failed: {e}')
            return None
    return _firebase_app


def log_visit(user):
    app = _get_app()
    if app is None:
        return
    ref = db.reference('/analytics', app=app)
    now = datetime.now(timezone.utc)
    date_key = now.strftime('%Y-%m-%d')
    hour_key = str(now.hour)

    daily_ref = ref.child(f'daily_counts/{date_key}')
    try:
        daily_ref.transaction(lambda current: (current or 0) + 1)
    except Exception:
        pass

    hourly_ref = ref.child(f'hourly_counts/{date_key}/{hour_key}')
    try:
        hourly_ref.transaction(lambda current: (current or 0) + 1)
    except Exception:
        pass


def log_visit_async(user):
    threading.Thread(target=log_visit, args=(user,), daemon=True).start()


def log_active_user(user):
    app = _get_app()
    if app is None:
        return
    uid = str(user.uid)
    date_key = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    ref = db.reference(f'/analytics/active_users/{date_key}/{uid}', app=app)
    try:
        ref.set(True)
    except Exception:
        pass


def log_active_user_async(user):
    threading.Thread(target=log_active_user, args=(user,), daemon=True).start()


def get_daily_active_user_counts(days=30):
    app = _get_app()
    if app is None:
        return {}
    today = datetime.now(timezone.utc).date()
    result = {}
    for i in range(days):
        d = today - timedelta(days=i)
        key = d.strftime('%Y-%m-%d')
        ref = db.reference(f'/analytics/active_users/{key}', app=app)
        try:
            data = ref.get() or {}
            count = len(data) if isinstance(data, dict) else 0
            result[key] = count
        except Exception:
            result[key] = 0
    return result


def get_daily_visits(days=30):
    app = _get_app()
    if app is None:
        return []
    ref = db.reference('/analytics/daily_counts', app=app)
    try:
        data = ref.get() or {}
    except Exception:
        return []
    today = datetime.now(timezone.utc).date()
    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        key = d.strftime('%Y-%m-%d')
        result.append({
            'date': d.strftime('%d %b'),
            'count': data.get(key, 0),
        })
    return result


def get_hourly_peaks(days=30):
    app = _get_app()
    if app is None:
        return [0] * 24
    ref = db.reference('/analytics/hourly_counts', app=app)
    try:
        data = ref.get() or {}
    except Exception:
        return [0] * 24
    today = datetime.now(timezone.utc).date()
    hourly = [0] * 24
    for i in range(days):
        d = today - timedelta(days=i)
        key = d.strftime('%Y-%m-%d')
        day_data = data.get(key) or {}
        for h in range(24):
            hourly[h] += day_data.get(str(h), 0)
    return hourly


def analytics_cleanup(days=30):
    app = _get_app()
    if app is None:
        return 0
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    total = 0
    paths = ['daily_counts', 'hourly_counts', 'active_users']
    for subpath in paths:
        ref = db.reference(f'/analytics/{subpath}', app=app)
        try:
            data = ref.get() or {}
            for key in list(data.keys()):
                try:
                    d = datetime.strptime(key, '%Y-%m-%d').date()
                    if d < cutoff:
                        ref.child(key).delete()
                        total += 1
                except ValueError:
                    pass
        except Exception:
            pass
    return total
