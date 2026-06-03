import os
import logging
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.join(settings.BASE_DIR, 'local_backups')


class Command(BaseCommand):
    help = 'Restore local backup to current database (Neon)'

    def add_arguments(self, parser):
        parser.add_argument('backup_file', nargs='?', default=None,
                            help='JSON backup file path (default: local_backups/neon_latest.json)')

    def handle(self, *args, **options):
        backup_file = options['backup_file']
        if not backup_file:
            backup_file = os.path.join(BACKUP_DIR, 'neon_latest.json')

        if not os.path.exists(backup_file):
            self.stdout.write(self.style.ERROR(f"Backup file not found: {backup_file}"))
            self.stdout.write("Run `python manage.py local_backup` first to create a backup.")
            return

        self.stdout.write(f"Restoring from: {backup_file}")
        self.stdout.write(self.style.WARNING(
            "WARNING: This will OVERWRITE all data in your current database!"
        ))
        self.stdout.write("Press Ctrl+C to cancel, or wait 5 seconds to continue...")
        import time
        time.sleep(5)

        call_command('loaddata', backup_file)
        self.stdout.write(self.style.SUCCESS("Restore complete!"))
