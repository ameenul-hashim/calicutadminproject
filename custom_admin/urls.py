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
    path('pending/courses/', views.pending_courses_view, name='pending_courses'),
    path('course/approve/<int:course_id>/', views.approve_course, name='approve_course'),
    path('course/reject/<int:course_id>/', views.reject_course, name='reject_course'),
    
    # Lesson actions
    path('lesson/approve/<int:lesson_id>/', views.approve_lesson, name='approve_lesson'),
    path('lesson/reject/<int:lesson_id>/', views.reject_lesson, name='reject_lesson'),
    
    # Quiz actions
    path('quiz/approve/<int:quiz_id>/', views.approve_quiz, name='approve_quiz'),
    path('quiz/reject/<int:quiz_id>/', views.reject_quiz, name='reject_quiz'),
    
    # Assignment actions
    path('assignment/approve/<int:assignment_id>/', views.approve_assignment, name='approve_assignment'),
    path('assignment/reject/<int:assignment_id>/', views.reject_assignment, name='reject_assignment'),

    path('user/accept/<int:user_id>/', views.accept_user, name='accept_user'),
    path('user/decline/<int:user_id>/', views.decline_user, name='decline_user'),
    path('user/toggle/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('student/create/', views.create_student_admin, name='create_student_admin'),
    path('student/<int:user_id>/profile/', views.admin_student_profile, name='admin_student_profile'),
    path('student-view/auth/', views.admin_student_view_auth, name='admin_student_view_auth'),
    path('student-view/', views.admin_student_view, name='admin_student_view'),
    path('student-view/logout/', views.admin_student_logout, name='admin_student_logout'),
    path('teacher/create/', views.create_teacher_admin, name='create_teacher_admin'),
    path('teacher/<int:user_id>/profile/', views.admin_teacher_profile, name='admin_teacher_profile'),
    path('user/edit/<int:user_id>/', views.edit_user_admin, name='edit_user_admin'),
    path('user/delete/<int:user_id>/', views.delete_user_admin, name='delete_user_admin'),
    path('analytics/', views.analytics_view, name='admin_analytics'),
    path('content/', views.content_management_view, name='admin_content'),
    path('course/delete/secure/<int:course_id>/', views.admin_delete_course_secure, name='admin_delete_course_secure'),
    path('assignment/<int:assignment_id>/submissions/', views.admin_view_submissions, name='admin_view_submissions'),
    path('quiz/<int:quiz_id>/attempts/', views.admin_view_quiz_attempts, name='admin_view_quiz_attempts'),
    path('course/<int:course_id>/verify/', views.admin_view_course_content, name='admin_view_course_content'),
    path('deletion-requests/', views.manage_deletion_requests, name='manage_deletion_requests'),
    path('deletion-requests/<int:request_id>/verify/', views.verify_deletion_request, name='verify_deletion_request'),
    path('deletion-requests/<int:request_id>/approve/', views.approve_deletion_request, name='approve_deletion_request'),
    path('deletion-requests/<int:request_id>/reject/', views.reject_deletion_request, name='reject_deletion_request'),
    path('quizzes/<int:quiz_id>/delete/', views.delete_quiz, name='delete_quiz'),
    path('assignments/<int:assignment_id>/delete/', views.delete_assignment, name='delete_assignment'),
]
