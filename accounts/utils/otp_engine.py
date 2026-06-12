import random
import hashlib
from django.utils import timezone
from datetime import timedelta
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from accounts.models import EmailOTP
import logging

logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 5

class OTPEngine:
    """
    OTP engine using PostgreSQL (EmailOTP model) with 5-minute TTL and auto-cleanup.
    """

    @staticmethod
    def generate_otp():
        return str(random.randint(100000, 999999))

    @staticmethod
    def hash_otp(otp):
        salt = settings.SECRET_KEY[:16]
        return hashlib.sha256((salt + otp).encode()).hexdigest()

    @staticmethod
    def hash_otp_legacy(otp):
        return hashlib.sha256(otp.encode()).hexdigest()

    @classmethod
    def check_rate_limit(cls, user, ip=None):
        now = timezone.now()
        day_ago = now - timedelta(days=1)
        hour_ago = now - timedelta(hours=1)

        user_daily_count = EmailOTP.objects.filter(user=user, created_at__gte=day_ago).count()
        if user_daily_count >= 5:
            logger.warning(f"[SECURITY/QUOTA] User {user.email} exceeded daily OTP quota ({user_daily_count} requests).")
            return False, "You have exceeded the maximum number of verification requests for today. Please try again tomorrow."

        if ip:
            ip_hourly_count = EmailOTP.objects.filter(ip_address=ip, created_at__gte=hour_ago).count()
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

        EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)

        raw_otp = cls.generate_otp()
        hashed_otp = cls.hash_otp(raw_otp)
        ua = request.META.get('HTTP_USER_AGENT', '') if request else None

        otp_obj = EmailOTP.objects.create(
            user=user,
            user_type=user.user_type,
            purpose=purpose,
            otp_hash=hashed_otp,
            expires_at=timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
            ip_address=ip,
            user_agent=ua
        )

        return raw_otp, otp_obj

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
            'expiry': f'{OTP_EXPIRY_MINUTES} minutes',
            'year': timezone.now().year
        }

        html_content = render_to_string('emails/otp_email.html', context)
        text_content = f"Your Neo Learner verification code is: {raw_otp}. Valid for {OTP_EXPIRY_MINUTES} minutes."

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
        from django.db import transaction

        if not raw_otp:
            return False, "Please enter a valid verification code."

        hashed_input = cls.hash_otp(raw_otp)
        legacy_hashed = cls.hash_otp_legacy(raw_otp)

        with transaction.atomic():
            otp_obj = EmailOTP.objects.select_for_update().filter(
                user=user, purpose=purpose, is_used=False
            ).first()

            if not otp_obj:
                return False, "No active verification code found. Please request a new one."

            if otp_obj.is_expired():
                otp_obj.is_used = True
                otp_obj.save()
                return False, "This code has expired. Please request a new one."

            if otp_obj.attempt_count >= 5:
                otp_obj.is_used = True
                otp_obj.save()
                return False, "Too many failed attempts. Please request a new code."

            if otp_obj.otp_hash == hashed_input or otp_obj.otp_hash == legacy_hashed:
                otp_obj.is_used = True
                otp_obj.save()
                return True, "Verification successful."
            else:
                otp_obj.attempt_count += 1
                otp_obj.save()
                remaining = 5 - otp_obj.attempt_count
                return False, f"Invalid code. {remaining} attempts remaining."

    @staticmethod
    def cleanup_old_otps():
        now = timezone.now()
        EmailOTP.objects.filter(created_at__lt=now - timedelta(minutes=10)).delete()
