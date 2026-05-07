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
    Enterprise-grade centralized OTP engine for EduStream.
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
    def create_otp(cls, user, purpose, request=None):
        """
        Creates and saves a new hashed OTP for a user.
        Invalidates any previous active OTPs for the same purpose.
        """
        # 1. Invalidate existing active OTPs for this purpose
        EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)

        # 2. Generate new OTP
        raw_otp = cls.generate_otp()
        hashed_otp = cls.hash_otp(raw_otp)
        
        # 3. Meta data
        ip = None
        ua = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
            ua = request.META.get('HTTP_USER_AGENT', '')

        # 4. Save
        otp_obj = EmailOTP.objects.create(
            user=user,
            user_type=user.user_type,
            purpose=purpose,
            otp_hash=hashed_otp,
            expires_at=timezone.now() + timedelta(minutes=5),
            ip_address=ip,
            user_agent=ua
        )

        return raw_otp, otp_obj

    @classmethod
    def send_otp_email(cls, user, raw_otp, purpose):
        """Sends a branded HTML email with the OTP."""
        subject_map = {
            'PASSWORD_RESET': 'EduStream: Reset Your Password',
            'EMAIL_VERIFICATION': 'EduStream: Verify Your Email',
            'USERNAME_RECOVERY': 'EduStream: Recover Your Username',
            'USERNAME_UPDATE': 'EduStream: Verify Username Update',
        }
        
        subject = subject_map.get(purpose, 'EduStream Verification Code')
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = user.email

        # Render templates
        context = {
            'user': user,
            'otp': raw_otp,
            'purpose': purpose.replace('_', ' ').title(),
            'expiry': '5 minutes',
            'year': timezone.now().year
        }
        
        html_content = render_to_string('emails/otp_email.html', context)
        text_content = f"Your EduStream verification code is: {raw_otp}. Valid for 5 minutes."

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
