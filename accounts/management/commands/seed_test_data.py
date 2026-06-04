from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from accounts.models import CustomUser
import uuid


class Command(BaseCommand):
    help = 'Seed dummy students and teachers for pagination testing'

    def handle(self, *args, **options):
        created = 0

        for i in range(1, 15):
            username = f'teststudent{i}'
            if CustomUser.objects.filter(username=username).exists():
                continue
            CustomUser.objects.create(
                username=username,
                email=f'teststudent{i}@example.com',
                password=make_password('test123'),
                user_type='STUDENT',
                status='ACTIVE',
                full_name=f'Test Student {i}',
                phone_number=f'+91123456{i:04d}',
            )
            created += 1
            self.stdout.write(f'  Created student: {username}')

        for i in range(1, 5):
            username = f'testteacher{i}'
            if CustomUser.objects.filter(username=username).exists():
                continue
            CustomUser.objects.create(
                username=username,
                email=f'testteacher{i}@example.com',
                password=make_password('test123'),
                user_type='TEACHER',
                status='ACTIVE',
                full_name=f'Test Teacher {i}',
                phone_number=f'+91987654{i:04d}',
            )
            created += 1
            self.stdout.write(f'  Created teacher: {username}')

        if created == 0:
            self.stdout.write(self.style.WARNING('No new users created — they already exist.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Created {created} test user(s). Page 2 should now show for students (14 total, 10 per page).'))
