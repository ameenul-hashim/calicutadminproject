from django.core.management.base import BaseCommand
from django.db.models import Q
from accounts.models import CourseResource
from accounts.utils.storage_manager import StorageManager


class Command(BaseCommand):
    help = 'Retries failed Google Drive backups for approved resources'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be retried without actually executing',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        failed = CourseResource.objects.filter(
            Q(backup_status='FAILED') | Q(backup_status='PENDING'),
            status='APPROVED',
            is_deleted=False,
        )
        self.stdout.write(f'Found {failed.count()} resources needing backup retry')
        for r in failed:
            self.stdout.write(f'  [{r.uid}] {r.title} ({r.course.title}) — backup_status={r.backup_status}')
            if not dry_run:
                try:
                    StorageManager.backup_and_cleanup(r.id, r.firebase_file_path)
                    self.stdout.write(self.style.SUCCESS(f'    Retry initiated for {r.title}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'    Retry failed: {e}'))
        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run — no changes made'))
