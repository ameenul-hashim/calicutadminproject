import os, django, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
django.setup()

from custom_admin.views import analytics_view
from django.test import RequestFactory
from accounts.models import CustomUser

req = RequestFactory().get('/admin_login/')
req.user = CustomUser.objects.filter(is_superuser=True).first() or CustomUser.objects.filter(is_staff=True).first()
if not req.user:
    req.user = CustomUser.objects.first()
print('Testing with User:', req.user)

try:
    resp = analytics_view(req)
    print('Status:', resp.status_code)
except Exception as e:
    traceback.print_exc()
