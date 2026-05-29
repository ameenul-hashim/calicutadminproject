from django.contrib import admin
from .models import CustomUser, Course, Lesson, Enrollment, Notification, ChatMessage, DeletionRequest, EmailOTP

@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_type', 'purpose', 'created_at', 'expires_at', 'is_used', 'attempt_count', 'ip_address')
    list_filter = ('user_type', 'purpose', 'is_used', 'created_at')
    search_fields = ('user__username', 'user__email', 'ip_address')
    readonly_fields = ('otp_hash', 'created_at', 'expires_at', 'uid', 'ip_address', 'user_agent')
    
    def has_add_permission(self, request):
        return False # Only system can create OTPs

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'user_type', 'status', 'date_joined')
    list_filter = ('user_type', 'status')
    search_fields = ('username', 'email', 'full_name')

admin.site.register(Course)
admin.site.register(Lesson)
admin.site.register(Enrollment)
admin.site.register(Notification)
admin.site.register(ChatMessage)
admin.site.register(DeletionRequest)



