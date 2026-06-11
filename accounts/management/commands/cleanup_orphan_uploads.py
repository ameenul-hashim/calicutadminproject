from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import UploadJob, Lesson
from accounts.utils.youtube_uploader import delete_youtube_video
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up orphaned upload jobs and lessons older than 24 hours'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print what would be deleted without actually deleting')
        parser.add_argument('--hours', type=int, default=24, help='Age threshold in hours (default: 24)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        hours = options['hours']
        cutoff = timezone.now() - timedelta(hours=hours)

        self.stdout.write(f"Cleaning up orphan uploads older than {hours} hours (cutoff: {cutoff})")

        orphan_jobs = UploadJob.objects.filter(
            status__in=['PENDING', 'UPLOADING', 'FAILED', 'CANCELLED'],
            created_at__lt=cutoff,
        )

        self.stdout.write(f"Found {orphan_jobs.count()} orphaned upload job(s)")

        cleaned_lessons = 0
        cleaned_jobs = 0
        cleaned_youtube = 0

        for job in orphan_jobs:
            job_info = f"UploadJob {job.uid} ('{job.title}', status={job.status})"
            self.stdout.write(f"  Processing {job_info}")

            lesson = job.lesson
            if lesson:
                if lesson.youtube_video_id:
                    if dry_run:
                        self.stdout.write(f"    WOULD delete YouTube video {lesson.youtube_video_id}")
                    else:
                        try:
                            delete_youtube_video(lesson.youtube_video_id)
                            cleaned_youtube += 1
                            self.stdout.write(f"    Deleted YouTube video {lesson.youtube_video_id}")
                        except Exception as e:
                            logger.warning(f"cleanup: Could not delete YouTube video {lesson.youtube_video_id}: {e}")

                if dry_run:
                    self.stdout.write(f"    WOULD delete lesson {lesson.uid} ('{lesson.title}')")
                else:
                    try:
                        lesson_uid = lesson.uid
                        lesson.delete()
                        cleaned_lessons += 1
                        self.stdout.write(f"    Deleted lesson {lesson_uid}")
                    except Exception as e:
                        logger.warning(f"cleanup: Could not delete lesson: {e}")

            if dry_run:
                self.stdout.write(f"    WOULD delete UploadJob {job.uid}")
            else:
                try:
                    job.delete()
                    cleaned_jobs += 1
                    self.stdout.write(f"    Deleted UploadJob {job.uid}")
                except Exception as e:
                    logger.warning(f"cleanup: Could not delete UploadJob: {e}")

        self.stdout.write(f"\nSummary: {cleaned_lessons} lessons, {cleaned_youtube} YouTube videos, {cleaned_jobs} upload jobs cleaned")
