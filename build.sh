#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Ensure all admin users have superuser+staff permissions
python -c "
import django; import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
django.setup()
from accounts.models import CustomUser
updated = CustomUser.objects.filter(user_type='ADMIN').exclude(is_superuser=True).update(is_superuser=True, is_staff=True)
if updated:
    print(f'Fixed {updated} admin user(s) — set is_superuser=True, is_staff=True')
else:
    print('All admin users already have correct permissions.')
"
