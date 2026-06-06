from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import Lesson
from accounts.utils.youtube_uploader import find_latest_youtube_upload
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recover lessons where YouTube upload succeeded but video_id was not saved (browser disconnect, callback failure, etc.)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes-back',
            type=int,
            default=5,
            help='Only consider lessons older than this many minutes (default: 5)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be recovered without actually saving',
        )

    def handle(self, *args, **options):
        minutes_back = options['minutes_back']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(minutes=minutes_back)

        lessons = Lesson.objects.filter(
            youtube_video_id__isnull=True,
        ).exclude(
            upload_status='READY',
        ).filter(
            created_at__lt=cutoff,
        )

        self.stdout.write(f"Found {lessons.count()} orphaned lesson(s) older than {minutes_back} minute(s)")

        recovered = 0
        failed = 0
        still_uploading = 0

        for lesson in lessons:
            # Skip if lesson has a direct URL (not YouTube upload)
            if lesson.video_url and not lesson.youtube_video_id:
                self.stdout.write(f"  SKIP  uid={lesson.uid} — uses direct URL, not YouTube upload")
                continue

            # Skip lessons with active upload timestamps (still might be uploading)
            if lesson.upload_status == 'UPLOADING' and lesson.youtube_upload_status == 'UPLOADING':
                still_uploading += 1
                self.stdout.write(f"  SKIP  uid={lesson.uid} — still uploading (status=UPLOADING)")
                continue

            self.stdout.write(f"  TRY   uid={lesson.uid} title='{lesson.title}' upload_status='{lesson.upload_status}' youtube_upload_status='{lesson.youtube_upload_status}'")

            recovered_id = find_latest_youtube_upload(lesson.title)
            if not recovered_id:
                failed += 1
                self.stdout.write(f"  FAIL  uid={lesson.uid} — no matching video found on YouTube")
                logger.warning(f"recover_orphaned_lessons: Could not recover lesson {lesson.uid} ('{lesson.title}')")
                continue

            if dry_run:
                self.stdout.write(f"  WOULD_RECOVER uid={lesson.uid} → video_id={recovered_id}")
                recovered += 1
                continue

            lesson.youtube_video_id = recovered_id
            lesson.youtube_upload_status = 'UPLOADED'
            lesson.youtube_uploaded_at = timezone.now()
            lesson.video_url = f'https://www.youtube.com/watch?v={recovered_id}'
            lesson.upload_status = 'READY'
            lesson.save(update_fields=[
                'youtube_video_id', 'youtube_upload_status', 'youtube_uploaded_at',
                'upload_status', 'video_url',
            ])

            recovered += 1
            self.stdout.write(f"  DONE  uid={lesson.uid} → video_id={recovered_id}")
            logger.info(f"recover_orphaned_lessons: Recovered lesson {lesson.uid} → video_id={recovered_id}")

        self.stdout.write(f"\nSummary: {recovered} recovered, {failed} failed, {still_uploading} still uploading, {lessons.count() - recovered - failed - still_uploading} skipped")
