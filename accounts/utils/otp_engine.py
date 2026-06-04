import random
import hashlib
from django.utils import timezone
from datetime import timedelta
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class OTPEngine:
    """
    OTP engine using Firebase RTDB for storage. 10-minute TTL auto-cleanup.
    """

    @staticmethod
    def generate_otp():
        return str(random.randint(100000, 999999))

    @staticmethod
    def hash_otp(otp):
        return hashlib.sha256(otp.encode()).hexdigest()

    @classmethod
    def check_rate_limit(cls, user, ip=None):
        now = timezone.now()
        day_ago = now - timedelta(days=1)
        hour_ago = now - timedelta(hours=1)

        from .firebase_db import otp_get_user_daily_count, otp_get_ip_hourly_count

        user_daily_count = otp_get_user_daily_count(str(user.uid))
        if user_daily_count >= 5:
            logger.warning(f"[SECURITY/QUOTA] User {user.email} exceeded daily OTP quota ({user_daily_count} requests).")
            return False, "You have exceeded the maximum number of verification requests for today. Please try again tomorrow."

        if ip:
            ip_hourly_count = otp_get_ip_hourly_count(ip)
            if ip_hourly_count >= 10:
                logger.critical(f"[SECURITY/ABUSE] IP {ip} triggered rate limiting ({ip_hourly_count} requests in 1hr).")
                return False, "Too many requests from your network. Please wait an hour before trying again."

        return True, ""

    @classmethod
    def create_otp(cls, user, purpose, request=None):
        cls.cleanup_old_otps()

        ip = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

        allowed, msg = cls.check_rate_limit(user, ip)
        if not allowed:
            return None, msg

        from .firebase_db import otp_invalidate_all

        otp_invalidate_all(str(user.uid), purpose)

        raw_otp = cls.generate_otp()
        hashed_otp = cls.hash_otp(raw_otp)
        ua = request.META.get('HTTP_USER_AGENT', '') if request else None

        from .firebase_db import otp_create
        otp_create(str(user.uid), purpose, hashed_otp, ip or '', ua or '')

        return raw_otp, None

    @classmethod
    def send_otp_email(cls, user, raw_otp, purpose):
        subject_map = {
            'PASSWORD_RESET': 'Neo Learner: Reset Your Password',
            'EMAIL_VERIFICATION': 'Neo Learner: Verify Your Email',
            'USERNAME_RECOVERY': 'Neo Learner: Recover Your Username',
            'USERNAME_UPDATE': 'Neo Learner: Verify Username Update',
        }

        subject = subject_map.get(purpose, 'Neo Learner Verification Code')
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        context = {
            'user': user,
            'otp': raw_otp,
            'purpose': purpose.replace('_', ' ').title(),
            'expiry': '2 minutes',
            'year': timezone.now().year
        }

        html_content = render_to_string('emails/otp_email.html', context)
        text_content = f"Your Neo Learner verification code is: {raw_otp}. Valid for 2 minutes."

        msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
        msg.attach_alternative(html_content, "text/html")

        try:
            msg.send()
            logger.info(f"OTP email sent to {to_email} for purpose: {purpose}")
            return True
        except Exception as e:
            logger.error(f"Failed to send OTP email: {str(e)}")
            return str(e)

    @classmethod
    def verify_otp(cls, user, raw_otp, purpose):
        if not raw_otp:
            return False, "Please enter a valid verification code."

        hashed_input = cls.hash_otp(raw_otp)

        from .firebase_db import otp_get_active, otp_mark_used, otp_increment_attempt

        otp_data = otp_get_active(str(user.uid), purpose)

        if not otp_data:
            return False, "No active verification code found. Please request a new one."

        expires_at = otp_data.get('expires_at', 0)
        if timezone.now().timestamp() * 1000 > expires_at:
            otp_mark_used(str(user.uid), purpose)
            return False, "This code has expired. Please request a new one."

        attempt_count = otp_data.get('attempt_count', 0)
        if attempt_count >= 5:
            otp_mark_used(str(user.uid), purpose)
            return False, "Too many failed attempts. Please request a new code."

        if otp_data.get('otp_hash') == hashed_input:
            otp_mark_used(str(user.uid), purpose)
            return True, "Verification successful."
        else:
            otp_increment_attempt(str(user.uid), purpose)
            remaining = 5 - (attempt_count + 1)
            return False, f"Invalid code. {remaining} attempts remaining."

    @staticmethod
    def cleanup_old_otps():
        from .firebase_db import otp_cleanup
        otp_cleanup(10)
