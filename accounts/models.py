from django.contrib.auth.models import AbstractUser
from django.db import models

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
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='STUDENT', db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE', db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    proof_pdf = models.URLField(max_length=1000, blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_users')
    approved_at = models.DateTimeField(null=True, blank=True)
    current_session_key = models.CharField(max_length=40, null=True, blank=True)

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
    category = models.CharField(max_length=100)
    thumbnail = models.ImageField(upload_to='course_thumbnails/', null=True, blank=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='BEGINNER')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    intro_video = models.FileField(upload_to='course_intro/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    is_approved = models.BooleanField(default=False, db_index=True)
    rejection_reason = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_courses')
    created_at = models.DateTimeField(auto_now_add=True)

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
    created_at = models.DateTimeField(auto_now_add=True)

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
    enrolled_at = models.DateTimeField(auto_now_add=True)

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class ChatMessage(models.Model):
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

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

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.item_type} deletion request by {self.teacher.username}"
