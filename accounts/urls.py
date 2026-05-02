from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('teacher/signup/', views.teacher_signup_view, name='teacher_signup'),
    path('teacher/login/', views.teacher_login_view, name='teacher_login'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/courses/', views.my_courses, name='my_courses'),
    path('teacher/courses/create/', views.create_course, name='create_course'),
    path('teacher/courses/<int:course_id>/lessons/', views.course_lessons, name='course_lessons'),
    path('teacher/courses/<int:course_id>/lessons/add/', views.add_lesson, name='add_lesson'),
    path('teacher/courses/<int:course_id>/submit/', views.submit_course_approval, name='submit_course_approval'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
]
