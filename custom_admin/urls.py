from django.urls import path
from . import views
from django.shortcuts import redirect

urlpatterns = [
    path('portal-secure-access/', views.admin_login_view, name='admin_login'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('students/', views.manage_students, name='manage_students'),
    path('teachers/', views.manage_teachers, name='manage_teachers'),
    path('pending/', views.pending_users_view, name='pending_users'),
    path('pending/teachers/', views.pending_teachers_view, name='pending_teachers'),
    path('pending/resources/', views.pending_resources, name='pending_resources'),
    path('pending/courses/', views.pending_courses_view, name='pending_courses'),
    path('course/approve/<uuid:course_uid>/', views.approve_course, name='approve_course'),
    path('course/reject/<uuid:course_uid>/', views.reject_course, name='reject_course'),
    
    # Lesson actions
    path('lesson/approve/<uuid:lesson_uid>/', views.approve_lesson, name='approve_lesson'),
    path('lesson/reject/<uuid:lesson_uid>/', views.reject_lesson, name='reject_lesson'),
    
    # Resource actions
    path('resource/approve/<uuid:resource_uid>/', views.approve_resource, name='approve_resource'),
    path('resource/reject/<uuid:resource_uid>/', views.reject_resource, name='reject_resource'),
    
    path('storage-dashboard/', views.storage_dashboard, name='storage_dashboard'),
    

    path('user/accept/<uuid:user_uid>/', views.accept_user, name='accept_user'),
    path('user/decline/<uuid:user_uid>/', views.decline_user, name='decline_user'),
    path('user/toggle/<uuid:user_uid>/', views.toggle_user_status, name='toggle_user_status'),
    path('student/create/', views.create_student_admin, name='create_student_admin'),
    path('student/<uuid:user_uid>/profile/', views.admin_student_profile, name='admin_student_profile'),
    path('student-view/auth/', views.admin_student_view_auth, name='admin_student_view_auth'),


    path('teacher/create/', views.create_teacher_admin, name='create_teacher_admin'),
    path('teacher/<uuid:user_uid>/profile/', views.admin_teacher_profile, name='admin_teacher_profile'),
    path('user/edit/<uuid:user_uid>/', views.edit_user_admin, name='edit_user_admin'),
    path('user/delete/<uuid:user_uid>/', views.delete_user_admin, name='delete_user_admin'),
    path('analytics/', views.analytics_view, name='admin_analytics'),
    path('content/', views.content_management_view, name='admin_content'),
    path('course/delete/secure/<uuid:course_uid>/', views.admin_delete_course_secure, name='admin_delete_course_secure'),
    path('lesson/delete/secure/<uuid:lesson_uid>/', views.admin_delete_lesson_secure, name='admin_delete_lesson_secure'),
    path('course/<uuid:course_uid>/verify/', views.admin_view_course_content, name='admin_view_course_content'),
    path('deletion-requests/', views.manage_deletion_requests, name='manage_deletion_requests'),
    path('deletion-requests/<uuid:request_uid>/verify/', views.verify_deletion_request, name='verify_deletion_request'),
    path('deletion-requests/<uuid:request_uid>/approve/', views.approve_deletion_request, name='approve_deletion_request'),
    path('deletion-requests/<uuid:request_uid>/reject/', views.reject_deletion_request, name='reject_deletion_request'),
    path('notifications/', views.admin_all_notifications, name='admin_all_notifications'),
    path('enterprise-monitor/', views.enterprise_monitor, name='enterprise_monitor'),
    path('system-audit/', views.system_audit_view, name='system_audit'),
    path('master-audit-summary/', views.master_audit_summary_view, name='master_audit_summary'),
    path('secure-pdf-access/<uuid:user_uid>/', views.proxy_pdf_access, name='proxy_pdf_access'),
    path('deleted-courses/', views.deleted_courses_view, name='deleted_courses'),
    path('course/restore/<uuid:course_uid>/', views.admin_restore_course, name='admin_restore_course'),
    path('course/permanent-delete/secure/<uuid:course_uid>/', views.admin_permanent_delete_course_secure, name='admin_permanent_delete_course_secure'),
]
