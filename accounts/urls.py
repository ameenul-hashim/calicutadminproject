from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('student-view/auth/', views.student_view_auth, name='student_view_auth'),


    path('teacher/signup/', views.teacher_signup_view, name='teacher_signup'),
    path('teacher/login/', views.teacher_login_view, name='teacher_login'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/courses/', views.my_courses, name='my_courses'),
    path('teacher/analytics/', views.teacher_analytics_view, name='teacher_analytics'),
    path('teacher/courses/create/', views.create_course, name='create_course'),
    path('teacher/courses/<uuid:course_uid>/edit/', views.edit_course, name='edit_course'),
    path('teacher/courses/<uuid:course_uid>/delete/', views.delete_course, name='delete_course'),
    path('teacher/courses/<uuid:course_uid>/lessons/', views.course_lessons, name='course_lessons'),
    path('teacher/courses/<uuid:course_uid>/lessons/add/', views.add_lesson, name='add_lesson'),
    path('teacher/lessons/<uuid:lesson_uid>/edit/', views.edit_lesson, name='edit_lesson'),
    path('teacher/lessons/<uuid:lesson_uid>/delete/', views.delete_lesson, name='delete_lesson'),
    path('teacher/courses/<uuid:course_uid>/submit/', views.submit_course_approval, name='submit_course_approval'),
    path('student/enroll/<uuid:course_uid>/', views.enroll_course, name='enroll_course'),
    path('logout/', views.logout_view, name='logout'),
    path('teacher/courses/view/<uuid:course_uid>/', views.view_other_course, name='view_other_course'),
    path('teacher/explore/', views.explore_courses, name='teacher_explore'),
    path('course/<uuid:course_uid>/play/', views.course_player, name='course_player'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('student/explore/', views.student_explore, name='student_explore'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('chat/send/', views.send_chat_message, name='send_chat_message'),
    path('chat/messages/<uuid:other_user_uid>/', views.get_chat_messages, name='get_chat_messages'),
    path('chat/list/', views.get_chat_list, name='get_chat_list'),
    path('notification/<uuid:notif_uid>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/read-all/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/', views.all_notifications, name='all_notifications'),
    path('unread-counts/', views.get_unread_counts, name='get_unread_counts'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('reset-password/', views.reset_password, name='reset_password'),
]

