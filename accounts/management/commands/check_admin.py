import sys
from django.core.management.base import BaseCommand
from django.contrib.auth import authenticate
from accounts.models import CustomUser

class Command(BaseCommand):
    help = 'Check if an admin user exists with given username and password, or list all admin users.'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Admin username to verify')
        parser.add_argument('--password', type=str, help='Password for the admin user')
        parser.add_argument('--list', action='store_true', help='List all admin usernames')

    def handle(self, *args, **options):
        if options['list']:
            admins = CustomUser.objects.filter(user_type='ADMIN')
            if not admins:
                self.stdout.write(self.style.WARNING('No admin users found.'))
                return
            self.stdout.write(self.style.SUCCESS('Admin users:'))
            for admin in admins:
                self.stdout.write(f"- {admin.username} (status: {admin.status})")
            return

        username = options.get('username')
        password = options.get('password')
        if not username or not password:
            self.stderr.write(self.style.ERROR('Both --username and --password are required unless using --list.'))
            sys.exit(1)

        user = authenticate(username=username, password=password)
        if user is None:
            self.stdout.write(self.style.ERROR('Authentication failed: invalid credentials.'))
        elif user.user_type != 'ADMIN':
            self.stdout.write(self.style.ERROR('User exists but is not an admin.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Admin user "{username}" authenticated successfully.'))
