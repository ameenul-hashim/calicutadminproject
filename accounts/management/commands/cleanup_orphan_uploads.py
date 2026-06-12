from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import UploadJob, Lesson, UploadAuditEvent
from accounts.utils.youtube_uploader import delete_youtube_video
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Enterprise cleanup: orphaned/failed/abandoned upload jobs and audit events'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print what would be deleted without actually deleting')
        parser.add_argument('--hours', type=int, default=24, help='Age threshold in hours (default: 24)')
        parser.add_argument('--cleanup-audit', action='store_true', help='Also cleanup old audit events (>7 days)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        hours = options['hours']
        cutoff = timezone.now() - timedelta(hours=hours)

        self.stdout.write(f"Enterprise cleanup: orphan uploads older than {hours}h (cutoff: {cutoff})")

        # Phase 1: Clean up failed/cancelled/abandoned uploads
        orphan_jobs = UploadJob.objects.filter(
            status__in=['PENDING', 'UPLOADING', 'FAILED', 'CANCELLED', 'YOUTUBE_PROCESSING'],
            created_at__lt=cutoff,
        )

        self.stdout.write(f"Phase 1: Found {orphan_jobs.count()} orphaned upload job(s)")

        stats = {'lessons': 0, 'jobs': 0, 'youtube': 0}

        for job in orphan_jobs:
            job_info = f"UploadJob {job.uid} ('{job.title}', status={job.status})"
            self.stdout.write(f"  {job_info}")

            lesson = job.lesson
            if lesson:
                if lesson.youtube_video_id:
                    if dry_run:
                        self.stdout.write(f"    WOULD delete YouTube video {lesson.youtube_video_id}")
                    else:
                        try:
                            delete_youtube_video(lesson.youtube_video_id)
                            stats['youtube'] += 1
                        except Exception as e:
                            logger.warning(f"cleanup: Could not delete YouTube video {lesson.youtube_video_id}: {e}")

                if dry_run:
                    self.stdout.write(f"    WOULD delete lesson {lesson.uid}")
                else:
                    try:
                        lesson_uid = lesson.uid
                        lesson.delete()
                        stats['lessons'] += 1
                    except Exception as e:
                        logger.warning(f"cleanup: Could not delete lesson: {e}")

            if not dry_run:
                from django.db import connection
                try:
                    UploadAuditEvent.objects.filter(upload_job=job).delete()
                    job.delete()
                    stats['jobs'] += 1
                except Exception as e:
                    logger.warning(f"cleanup: Could not delete UploadJob: {e}")

        self.stdout.write(f"  Phase 1 result: {stats['lessons']} lessons, {stats['youtube']} YouTube videos, {stats['jobs']} upload jobs")

        # Phase 2: Clean up abandoned PROCESSING/COMPLETED jobs with no lesson reference
        abandoned = UploadJob.objects.filter(
            lesson__isnull=True,
            created_at__lt=cutoff,
        ).exclude(status__in=['READY', 'PUBLISHED'])

        self.stdout.write(f"Phase 2: Found {abandoned.count()} abandoned upload job(s) (no lesson reference)")
        abandoned_count = 0
        for job in abandoned:
            if dry_run:
                self.stdout.write(f"  WOULD delete abandoned UploadJob {job.uid}")
            else:
                try:
                    UploadAuditEvent.objects.filter(upload_job=job).delete()
                    job.delete()
                    abandoned_count += 1
                except Exception as e:
                    logger.warning(f"cleanup: Could not delete abandoned UploadJob: {e}")
        self.stdout.write(f"  Phase 2 result: {abandoned_count} abandoned jobs cleaned")

        # Phase 3: Optional audit event cleanup (>7 days)
        if options.get('cleanup_audit'):
            audit_cutoff = timezone.now() - timedelta(days=7)
            old_events = UploadAuditEvent.objects.filter(timestamp__lt=audit_cutoff)
            event_count = old_events.count()
            self.stdout.write(f"Phase 3: Found {event_count} audit event(s) older than 7 days")
            if not dry_run:
                old_events.delete()
                self.stdout.write(f"  Phase 3 result: {event_count} audit events cleaned")

        self.stdout.write(self.style.SUCCESS("Enterprise cleanup completed"))
