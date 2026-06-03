import os
import json
import datetime
import logging
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from io import StringIO

logger = logging.getLogger(__name__)

BACKUP_DIR = os.path.join(settings.BASE_DIR, 'local_backups')


class Command(BaseCommand):
    help = 'Pull all data from Neon DB and save as local JSON backup'

    def handle(self, *args, **options):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'neon_backup_{timestamp}.json'
        filepath = os.path.join(BACKUP_DIR, filename)

        self.stdout.write(f"Pulling data from Neon to: {filepath}")

        buf = StringIO()
        call_command('dumpdata', stdout=buf, indent=2,
                     exclude=['contenttypes', 'auth.Permission'],
                     natural_foreign=True)
        data = buf.getvalue()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data)

        size = len(data.encode('utf-8'))
        self.stdout.write(self.style.SUCCESS(
            f"Backup saved: {filename} ({size / 1024:.1f} KB)"
        ))

        latest = os.path.join(BACKUP_DIR, 'neon_latest.json')
        with open(latest, 'w', encoding='utf-8') as f:
            f.write(data)

        self.stdout.write(self.style.SUCCESS(
            f"Also saved as: local_backups/neon_latest.json (overwrite)"
        ))
