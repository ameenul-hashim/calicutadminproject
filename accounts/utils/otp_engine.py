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

class OTPEngine:
    """
    Enterprise-grade centralized OTP engine for EduAimsThinker.
    Handles generation, hashing, delivery, and verification.
    """

    @staticmethod
    def generate_otp():
        """Generates a secure 6-digit random OTP."""
        return str(random.randint(100000, 999999))

    @staticmethod
    def hash_otp(otp):
        """Hashes the OTP for secure storage."""
        return hashlib.sha256(otp.encode()).hexdigest()

    @classmethod
    def check_rate_limit(cls, user, ip=None):
        """
        Enterprise Abuse Prevention:
        - Max 5 OTP requests per email per day
        - Max 10 OTP requests per IP per hour
        """
        now = timezone.now()
        day_ago = now - timedelta(days=1)
        hour_ago = now - timedelta(hours=1)

        # 1. User/Email Quota (5 per day)
        user_daily_count = EmailOTP.objects.filter(user=user, created_at__gte=day_ago).count()
        if user_daily_count >= 5:
            logger.warning(f"⚠️ [SECURITY/QUOTA] User {user.email} exceeded daily OTP quota ({user_daily_count} requests).")
            return False, "You have exceeded the maximum number of verification requests for today. Please try again tomorrow."

        # 2. IP Quota (10 per hour)
        if ip:
            ip_hourly_count = EmailOTP.objects.filter(ip_address=ip, created_at__gte=hour_ago).count()
            if ip_hourly_count >= 10:
                logger.critical(f"🚨 [SECURITY/ABUSE] IP {ip} triggered rate limiting ({ip_hourly_count} requests in 1hr). Possible brute-force or spam attempt.")
                return False, "Too many requests from your network. Please wait an hour before trying again."

        return True, ""

    @classmethod
    def create_otp(cls, user, purpose, request=None):
        """
        Creates and saves a new hashed OTP for a user.
        Includes abuse detection and rate limiting.
        """
        # Automatically clean up old database records
        cls.cleanup_old_otps()
        
        # 0. Rate Limit Check
        ip = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        
        allowed, msg = cls.check_rate_limit(user, ip)
        if not allowed:
            return None, msg

        # 1. Invalidate existing active OTPs for this purpose
        EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)

        # 2. Generate new OTP
        raw_otp = cls.generate_otp()
        hashed_otp = cls.hash_otp(raw_otp)
        
        # 3. Meta data
        ua = request.META.get('HTTP_USER_AGENT', '') if request else None

        # 4. Save
        otp_obj = EmailOTP.objects.create(
            user=user,
            user_type=user.user_type,
            purpose=purpose,
            otp_hash=hashed_otp,
            expires_at=timezone.now() + timedelta(minutes=2),
            ip_address=ip,
            user_agent=ua
        )

        return raw_otp, otp_obj

    @classmethod
    def send_otp_email(cls, user, raw_otp, purpose):
        """Sends a branded HTML email with the OTP."""
        subject_map = {
            'PASSWORD_RESET': 'EduAimsThinker: Reset Your Password',
            'EMAIL_VERIFICATION': 'EduAimsThinker: Verify Your Email',
            'USERNAME_RECOVERY': 'EduAimsThinker: Recover Your Username',
            'USERNAME_UPDATE': 'EduAimsThinker: Verify Username Update',
        }
        
        subject = subject_map.get(purpose, 'EduAimsThinker Verification Code')
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        # Render templates
        context = {
            'user': user,
            'otp': raw_otp,
            'purpose': purpose.replace('_', ' ').title(),
            'expiry': '2 minutes',
            'year': timezone.now().year
        }
        
        html_content = render_to_string('emails/otp_email.html', context)
        text_content = f"Your EduAimsThinker verification code is: {raw_otp}. Valid for 2 minutes."

        msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
        msg.attach_alternative(html_content, "text/html")
        
        try:
            msg.send()
            logger.info(f"✅ OTP email sent to {to_email} for purpose: {purpose}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send OTP email: {str(e)}")
            return False

    @classmethod
    def verify_otp(cls, user, raw_otp, purpose):
        """
        Verifies a raw OTP against the hashed value in DB.
        Returns (success, message).
        """
        if not raw_otp:
            return False, "Please enter a valid verification code."
            
        hashed_input = cls.hash_otp(raw_otp)
        
        # Find active OTP for this user and purpose
        otp_obj = EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).first()

        if not otp_obj:
            return False, "No active verification code found. Please request a new one."

        # 1. Expiry Check
        if otp_obj.is_expired():
            otp_obj.is_used = True
            otp_obj.save()
            return False, "This code has expired. Please request a new one."

        # 2. Attempt Count Check
        if otp_obj.attempt_count >= 5:
            otp_obj.is_used = True
            otp_obj.save()
            return False, "Too many failed attempts. Please request a new code."

        # 3. Hash Matching
        if otp_obj.otp_hash == hashed_input:
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
        """Purges used and expired OTPs."""
        now = timezone.now()
        # Delete expired
        EmailOTP.objects.filter(expires_at__lt=now).delete()
        # Delete used older than 24h
        EmailOTP.objects.filter(is_used=True, created_at__lt=now - timedelta(hours=24)).delete()
