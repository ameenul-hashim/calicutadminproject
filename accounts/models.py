from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid
from django.utils import timezone

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('TEACHER', 'Teacher'),
        ('STUDENT', 'Student'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending Approval'),
        ('ACTIVE', 'Active'),
        ('BLOCKED', 'Blocked'),
        ('REJECTED', 'Rejected'),
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='STUDENT', db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE', db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True) # Legacy
    image = models.URLField(max_length=1000, blank=True, null=True)
    image_public_id = models.CharField(max_length=255, blank=True, null=True)
    proof_pdf = models.CharField(max_length=1000, blank=True, null=True) # Legacy Supabase path
    pdf_path = models.CharField(max_length=1000, blank=True, null=True) # New Supabase storage path
    pdf_url = models.URLField(max_length=1000, blank=True, null=True) # Legacy Cloudinary URL
    pdf_public_id = models.CharField(max_length=255, blank=True, null=True) # Legacy Cloudinary ID
    phone_number = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    rejection_reason = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_users')
    approved_at = models.DateTimeField(null=True, blank=True)
    current_session_key = models.CharField(max_length=40, null=True, blank=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    totp_secret = models.CharField(max_length=32, null=True, blank=True)

    @property
    def avatar_url(self):
        """Returns the raw Cloudinary image URL or a fallback default."""
        if self.image:
            return self.image.strip()
        
        if self.profile_photo:
            try:
                return self.profile_photo.url
            except ValueError:
                pass
        
        return f"https://ui-avatars.com/api/?name={self.username}&background=random&color=fff&size=256"

    @property
    def proof_pdf_url(self):
        """Generates a secure signed URL for the user's proof PDF from Supabase."""
        if not self.pdf_path:
            return self.pdf_url # Fallback to legacy Cloudinary URL if path missing
        from .utils.supabase_storage import get_signed_url
        return get_signed_url(self.pdf_path)

    def __str__(self):
        return f"{self.username} ({self.user_type})"

    class Meta:
        indexes = [
            models.Index(fields=['user_type', 'status']),
            models.Index(fields=['phone_number', 'user_type']),
        ]

class Course(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('PUBLISHED', 'Published'),
        ('REJECTED', 'Rejected'),
        ('DELETED', 'Deleted'),
    )
    LEVEL_CHOICES = (
        ('BEGINNER', 'Beginner'),
        ('INTERMEDIATE', 'Intermediate'),
        ('ADVANCED', 'Advanced'),
    )
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='courses')
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=100, db_index=True)
    thumbnail = models.ImageField(upload_to='course_thumbnails/', null=True, blank=True) # Legacy
    image = models.URLField(max_length=1000, blank=True, null=True)
    image_public_id = models.CharField(max_length=255, blank=True, null=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='BEGINNER', db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    intro_video = models.FileField(upload_to='course_intro/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    is_approved = models.BooleanField(default=False, db_index=True)
    rejection_reason = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_courses')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    pending_title = models.CharField(max_length=255, blank=True, null=True)
    pending_description = models.TextField(blank=True, null=True)
    pending_category = models.CharField(max_length=100, blank=True, null=True)
    pending_level = models.CharField(max_length=20, blank=True, null=True)
    pending_image = models.URLField(max_length=1000, blank=True, null=True)
    pending_image_public_id = models.CharField(max_length=255, blank=True, null=True)
    has_pending_edits = models.BooleanField(default=False, db_index=True)

    @property
    def thumbnail_url(self):
        """Returns the raw course thumbnail URL."""
        if self.image:
            return self.image.strip()
            
        if self.thumbnail:
            try:
                return self.thumbnail.url
            except ValueError:
                pass
        return None

    def __str__(self):
        return self.title

class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    video_url = models.URLField(max_length=500, null=True, blank=True, help_text="YouTube or other video link")
    video_file = models.FileField(upload_to='lessons/videos/', null=True, blank=True)
    order = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='PENDING')
    is_approved = models.BooleanField(default=False, db_index=True) # Keep for backward compatibility/quick checks
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    pending_title = models.CharField(max_length=255, blank=True, null=True)
    pending_video_url = models.URLField(max_length=500, blank=True, null=True)
    pending_video_file = models.FileField(upload_to='lessons/videos/', null=True, blank=True)
    pending_order = models.PositiveIntegerField(null=True, blank=True)
    has_pending_edits = models.BooleanField(default=False, db_index=True)

    youtube_video_id = models.CharField(max_length=100, null=True, blank=True, help_text="YouTube video ID from upload")
    youtube_upload_status = models.CharField(max_length=20, choices=[('NOT_UPLOADED', 'Not Uploaded'), ('UPLOADING', 'Uploading'), ('UPLOADED', 'Uploaded'), ('FAILED', 'Failed')], default='NOT_UPLOADED', db_index=True)
    youtube_uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['course', 'status']),
        ]

class CourseResource(models.Model):
    CATEGORY_CHOICES = (
        ('ENGLISH', 'English Notes'),
        ('MALAYALAM', 'Malayalam Notes'),
        ('ONLINE', 'Online Class Notes'),
    )
    RESOURCE_TYPE_CHOICES = (
        ('PDF', 'PDF Document'),
        ('DOCX', 'Word Document'),
        ('PPTX', 'PowerPoint Presentation'),
        ('XLSX', 'Excel Spreadsheet'),
        ('TXT', 'Text File'),
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='resources')
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    resource_type = models.CharField(max_length=10, choices=RESOURCE_TYPE_CHOICES, db_index=True)
    
    # Storage Paths
    firebase_file_path = models.CharField(max_length=1000)
    backup_file_path = models.CharField(max_length=1000, null=True, blank=True)
    backup_status = models.CharField(max_length=10, choices=[('PENDING', 'Pending'), ('SUCCESS', 'Success'), ('FAILED', 'Failed')], default='PENDING', db_index=True)
    thumbnail_path = models.CharField(max_length=1000, null=True, blank=True)
    thumbnail_public_id = models.CharField(max_length=500, null=True, blank=True)
    
    # Validation & Analytics
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    file_extension = models.CharField(max_length=10, blank=True, null=True)
    original_size = models.PositiveIntegerField(default=0, help_text="Size in bytes")
    compressed_size = models.PositiveIntegerField(default=0, help_text="Size in bytes")
    view_count = models.PositiveIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    
    # Approval Workflow
    status = models.CharField(max_length=20, choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('DELETION_PENDING', 'Deletion Pending')], default='PENDING', db_index=True)
    is_approved = models.BooleanField(default=False, db_index=True)
    approved_by = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_resources')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='rejected_resources')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Lifecycle & Soft Deletes
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    # Pending Edits (Teacher resubmission workflow)
    has_pending_edits = models.BooleanField(default=False)
    pending_title = models.CharField(max_length=255, null=True, blank=True)
    pending_category = models.CharField(max_length=20, null=True, blank=True)
    pending_resource_type = models.CharField(max_length=10, null=True, blank=True)
    pending_firebase_file_path = models.CharField(max_length=1000, null=True, blank=True)
    pending_thumbnail_path = models.CharField(max_length=1000, null=True, blank=True)
    pending_thumbnail_public_id = models.CharField(max_length=500, null=True, blank=True)
    pending_mime_type = models.CharField(max_length=100, null=True, blank=True)
    pending_file_extension = models.CharField(max_length=10, null=True, blank=True)
    pending_original_size = models.PositiveIntegerField(default=0)
    pending_compressed_size = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'status', 'is_deleted']),
            models.Index(fields=['status', 'is_deleted']),
            models.Index(fields=['course', '-created_at']),
        ]

class Enrollment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('user', 'course')
        indexes = [
            models.Index(fields=['course', 'user']),
        ]

class ApprovalLog(models.Model):
    content_type = models.CharField(max_length=50)
    object_id = models.PositiveIntegerField()
    status = models.CharField(max_length=20)
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    comments = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

class Report(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('REVIEWED', 'Reviewed'),
        ('RESOLVED', 'Resolved'),
    )
    reporter = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='filed_reports')
    content_type = models.CharField(max_length=50)
    object_id = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]

class ChatMessage(models.Model):
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['sender', 'receiver', 'timestamp']),
            models.Index(fields=['receiver', 'is_read']),
        ]

class EmailOTP(models.Model):
    PURPOSE_CHOICES = (
        ('PASSWORD_RESET', 'Password Reset'),
        ('EMAIL_VERIFICATION', 'Email Verification'),
        ('USERNAME_RECOVERY', 'Username Recovery'),
        ('EMAIL_UPDATE', 'Email Update'),
        ('USERNAME_UPDATE', 'Username Update'),
    )
    USER_TYPE_CHOICES = (
        ('STUDENT', 'Student'),
        ('TEACHER', 'Teacher'),
        ('ADMIN', 'Admin'),
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='otps')
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='STUDENT')
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='PASSWORD_RESET')
    otp_hash = models.CharField(max_length=255) # Hashed for security
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempt_count = models.IntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Email OTP"
        verbose_name_plural = "Email OTPs"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.username} - {self.purpose} ({self.created_at})"

class DeletionRequest(models.Model):
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='deletion_requests')
    item_type = models.CharField(max_length=50)  # e.g., 'Lesson' or 'Resource'
    item_id = models.IntegerField()
    item_name = models.CharField(max_length=255)
    # Direct FK for Resource deletion requests (nullable for legacy lesson requests)
    resource = models.ForeignKey('CourseResource', on_delete=models.CASCADE, null=True, blank=True, related_name='deletion_requests')
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='PENDING')
    reviewed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_deletion_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.item_type} deletion request by {self.teacher.username}"

class PDFAccessLog(models.Model):
    """Logs every time a user accesses a sensitive PDF."""
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    pdf_path = models.CharField(max_length=1000)
    accessed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-accessed_at']

    def __str__(self):
        return f"{self.user} accessed {self.pdf_path} at {self.accessed_at}"

class LoginHistory(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='login_history')
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_type = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=255, blank=True) # Mocked/GeoIP
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='SUCCESS') # SUCCESS, FAILED, ANOMALY

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = "Login Histories"
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['user', 'status', '-timestamp']),
            models.Index(fields=['ip_address', 'user']),
        ]

class AdminActivityLog(models.Model):
    admin = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='admin_actions')
    action = models.CharField(max_length=255)
    target_user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

# Signals for explicit image cleanup
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .utils.cloudinary_helpers import delete_image

@receiver(pre_delete, sender=CustomUser)
def cleanup_user_files(sender, instance, **kwargs):
    # 1. Clean Cloudinary Image
    delete_image(instance)
    
    # 2. Clean Supabase PDF
    if hasattr(instance, 'pdf_path') and instance.pdf_path:
        try:
            from .utils.supabase_storage import delete_pdf
            delete_pdf(instance.pdf_path)
        except Exception:
            pass

@receiver(pre_delete, sender=Course)
def cleanup_course_image(sender, instance, **kwargs):
    delete_image(instance)
    if hasattr(instance, 'pending_image_public_id') and instance.pending_image_public_id:
        try:
            import cloudinary.uploader
            cloudinary.uploader.destroy(instance.pending_image_public_id)
        except Exception:
            pass

@receiver(pre_delete, sender=Lesson)
def cleanup_lesson_video(sender, instance, **kwargs):
    """Clean up uploaded video file when lesson is deleted."""
    if instance.video_file:
        try:
            instance.video_file.delete(save=False)
        except Exception:
            pass
    if hasattr(instance, 'pending_video_file') and instance.pending_video_file:
        try:
            instance.pending_video_file.delete(save=False)
        except Exception:
            pass


