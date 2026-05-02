from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.admin_login_view, name='admin_login'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('students/', views.manage_students, name='manage_students'),
    path('teachers/', views.manage_teachers, name='manage_teachers'),
    path('pending/', views.pending_users_view, name='pending_users'),
    path('pending/teachers/', views.pending_teachers_view, name='pending_teachers'),
    path('pending/courses/', views.pending_courses_view, name='pending_courses'),
    path('course/approve/<int:course_id>/', views.approve_course, name='approve_course'),
    path('course/reject/<int:course_id>/', views.reject_course, name='reject_course'),
    path('lesson/toggle/<int:lesson_id>/', views.toggle_lesson_approval, name='toggle_lesson_approval'),
    path('user/accept/<int:user_id>/', views.accept_user, name='accept_user'),
    path('user/decline/<int:user_id>/', views.decline_user, name='decline_user'),
    path('user/toggle/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('student/create/', views.create_student_admin, name='create_student_admin'),
    path('teacher/create/', views.create_teacher_admin, name='create_teacher_admin'),
    path('user/edit/<int:user_id>/', views.edit_user_admin, name='edit_user_admin'),
    path('analytics/', views.analytics_view, name='admin_analytics'),
    path('content/', views.content_management_view, name='admin_content'),
]
