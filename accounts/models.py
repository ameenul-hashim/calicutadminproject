from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    STATUS_CHOICES = (
        ('PENDING', 'Pending Approval'),
        ('ACTIVE', 'Active'),
        ('BLOCKED', 'Blocked'),
    )
    USER_TYPE_CHOICES = (
        ('STUDENT', 'Student'),
        ('TEACHER', 'Teacher'),
    )
    full_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='STUDENT')
    proof_file = models.FileField(upload_to='proofs/', null=True, blank=True)

    def __str__(self):
        return f"{self.username} ({self.user_type})"

class Subject(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Video(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='videos')
    title = models.CharField(max_length=255)
    video_file = models.FileField(upload_to='videos/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Note(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='notes')
    title = models.CharField(max_length=255)
    note_file = models.FileField(upload_to='notes/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
