"""
Secure Resource Token Engine
============================
Generates and verifies short-lived HMAC tokens for resource access.
The signing key rotates weekly automatically, so any captured URL
becomes invalid the following Monday — no manual rotation needed.

Token format: <uid>.<timestamp_epoch>.<hmac_hex>
"""
import hmac
import hashlib
import time
from django.conf import settings


def _get_weekly_key():
    """
    Derives a signing key that changes every Monday at midnight UTC.
    Combines SECRET_KEY + ISO week number so it auto-rotates weekly.
    No cron jobs or manual steps needed.
    """
    import datetime
    today = datetime.date.today()
    iso_week = today.isocalendar()[1]   # 1–53
    iso_year = today.isocalendar()[0]
    weekly_salt = f"neolearner-resource-week-{iso_year}-{iso_week}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        weekly_salt.encode(),
        hashlib.sha256
    ).hexdigest()


def generate_resource_token(resource_uid: str, user_id: int, ttl_seconds: int = 3600) -> str:
    """
    Creates a signed token valid for `ttl_seconds` (default 1 hour).
    Token embeds uid + user_id so it cannot be used by another user.
    """
    key = _get_weekly_key()
    expires = int(time.time()) + ttl_seconds
    payload = f"{resource_uid}:{user_id}:{expires}"
    sig = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def verify_resource_token(resource_uid: str, user_id: int, token: str) -> bool:
    """
    Returns True only if:
      1. HMAC signature matches (correct key, correct uid, correct user)
      2. Token has not expired
      3. Weekly key is still valid (key auto-rotated = token invalid)
    """
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        expires_str, sig = parts
        expires = int(expires_str)
        if time.time() > expires:
            return False  # Expired
        key = _get_weekly_key()
        payload = f"{resource_uid}:{user_id}:{expires}"
        expected_sig = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, sig)
    except Exception:
        return False
