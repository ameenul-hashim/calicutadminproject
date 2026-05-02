from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.admin_login_view, name='admin_login'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('pending/', views.pending_users_view, name='pending_users'),
    path('pending/teachers/', views.pending_teachers_view, name='pending_teachers'),
    path('user/accept/<int:user_id>/', views.accept_user, name='accept_user'),
    path('user/decline/<int:user_id>/', views.decline_user, name='decline_user'),
    path('user/toggle/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('user/create/', views.create_user_admin, name='create_user_admin'),
    path('user/edit/<int:user_id>/', views.edit_user_admin, name='edit_user_admin'),
]
