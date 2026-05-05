from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

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

    @property
    def avatar_url(self):
        """Returns Cloudinary image URL, falling back to legacy profile_photo, then a professional default avatar."""
        if self.image:
            return self.image
        if self.profile_photo:
            try:
                return self.profile_photo.url
            except ValueError:
                pass
        # High-quality default avatar
        from django.templatetags.static import static
        return static('images/default_avatar.png')

    @property
    def proof_pdf_url(self):
        """Generates a secure signed URL for the user's proof PDF from Supabase."""
        if not self.pdf_path:
            return self.pdf_url # Fallback to legacy Cloudinary URL if path missing
        from .utils.supabase_storage import get_signed_url
        return get_signed_url(self.pdf_path)

    def __str__(self):
        return f"{self.username} ({self.user_type})"

class Course(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending Approval'),
        ('PUBLISHED', 'Published'),
        ('REJECTED', 'Rejected'),
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

    @property
    def thumbnail_url(self):
        """Returns Cloudinary image URL, falling back to legacy thumbnail."""
        if self.image:
            return self.image
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


    class Meta:
        ordering = ['order']


class LiveClass(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='live_classes')
    title = models.CharField(max_length=255)
    meeting_link = models.URLField()
    date_time = models.DateTimeField()

class Enrollment(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ('user', 'course')

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

class ChatMessage(models.Model):
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        ordering = ['timestamp']

class PasswordResetOTP(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.otp}"

class DeletionRequest(models.Model):
    teacher = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='deletion_requests')
    item_type = models.CharField(max_length=50) # e.g., 'Lesson'
    item_id = models.IntegerField()
    item_name = models.CharField(max_length=255)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='PENDING')
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
