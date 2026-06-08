import os
import sys
import json
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Diagnose Google Drive backup configuration and connectivity'

    def handle(self, *args, **options):
        results = []
        passed = 0
        failed = 0

        def check(name, ok, detail=''):
            nonlocal passed, failed
            if ok:
                passed += 1
                self.stdout.write(self.style.SUCCESS(f'  [PASS] {name}'))
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(f'  [FAIL] {name}'))
            if detail:
                self.stdout.write(f'         {detail}')

        self.stdout.write(self.style.MIGRATE_HEADING('=== Google Drive Backup Diagnostics ===\n'))

        # 1. Check BACKUP_ENABLED
        self.stdout.write('1. BACKUP_ENABLED setting:')
        be = getattr(settings, 'BACKUP_ENABLED', None)
        env_be = os.getenv('BACKUP_ENABLED')
        check('settings.BACKUP_ENABLED', be is not None, f'Value: {be}')
        check('Env var BACKUP_ENABLED', True, f'Value: {env_be}')
        effective = str(be) if be is not None else str(env_be or 'True')
        check('Backups are ENABLED', effective == 'True')

        # 2. Check GOOGLE_DRIVE_CREDENTIALS
        self.stdout.write('\n2. GOOGLE_DRIVE_CREDENTIALS:')
        creds = os.getenv('GOOGLE_DRIVE_CREDENTIALS')
        if not creds:
            check('Env var exists', False, 'GOOGLE_DRIVE_CREDENTIALS is NOT set in environment')
            self.stdout.write(self.style.WARNING('\n   Set it on Render: Dashboard -> Environment -> Add GOOGLE_DRIVE_CREDENTIALS'))
            self.stdout.write(self.style.WARNING('   Value must be a single-line JSON service account key'))
            self.stdout.write('   Example format (all on one line with \\n for newlines):')
            self.stdout.write('   {"type":"service_account","project_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n","client_email":"...","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token",...}')
        else:
            check('Env var exists', True, f'Length: {len(creds)} chars')
            try:
                parsed = json.loads(creds)
                check('Valid JSON', True)
                check('Is service_account', parsed.get('type') == 'service_account', f'type={parsed.get("type")}')
                check('Has private_key', bool(parsed.get('private_key')), 'Key present')
                check('Has client_email', bool(parsed.get('client_email')), f'Email: {parsed.get("client_email")}')
                check('Has project_id', bool(parsed.get('project_id')), f'Project: {parsed.get("project_id")}')
            except json.JSONDecodeError as e:
                check('Valid JSON', False, f'Parse error: {e}')
                self.stdout.write(self.style.WARNING('   Make sure your env var is valid JSON on a single line'))

        # 3. Try connecting to Drive
        self.stdout.write('\n3. Google Drive Connection Test:')
        if creds:
            try:
                from google.oauth2 import service_account
                from googleapiclient.discovery import build
                parsed = json.loads(creds)
                if parsed.get('type') == 'service_account':
                    scopes = ['https://www.googleapis.com/auth/drive']
                    sa_creds = service_account.Credentials.from_service_account_info(parsed, scopes=scopes)
                    service = build('drive', 'v3', credentials=sa_creds)
                    about = service.about().get(fields='user,storageQuota').execute()
                    user_info = about.get('user', {})
                    check('Drive API connected', True, f'Authenticated as: {user_info.get("displayName", user_info.get("emailAddress", "unknown"))}')
                    quota = about.get('storageQuota', {})
                    limit = int(quota.get('limit', 0))
                    usage = int(quota.get('usage', 0))
                    if limit:
                        pct = usage / limit * 100
                        check('Storage quota', True, f'{pct:.1f}% used ({usage//1048576}MB / {limit//1048576}MB)')
                    # Check if root folder exists
                    q = "name='NeoLearner_Backups' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                    root = service.files().list(q=q, spaces='drive', fields='files(id, name, parents)').execute()
                    items = root.get('files', [])
                    if items:
                        check('Root folder "NeoLearner_Backups"', True, f'ID: {items[0]["id"]}')
                    else:
                        check('Root folder "NeoLearner_Backups"', False, 'Folder does not exist or service account has no access')
                        self.stdout.write(self.style.WARNING('   Create the folder in Google Drive and share it with:'))
                        self.stdout.write(self.style.WARNING(f'   {parsed.get("client_email")} (set as Editor)'))
                else:
                    check('Drive API connected', False, 'Credentials type is not service_account')
            except ImportError as e:
                check('Drive API connected', False, f'Missing package: {e}')
            except Exception as e:
                check('Drive API connected', False, f'Error: {e}')

        # 4. Check BackupLog stats
        self.stdout.write('\n4. Backup History (from database):')
        try:
            from accounts.models import BackupLog
            total = BackupLog.objects.count()
            success = BackupLog.objects.filter(status='SUCCESS').count()
            failed_b = BackupLog.objects.filter(status='FAILED').count()
            pending = BackupLog.objects.filter(status__in=['PENDING', 'RUNNING', 'UPLOADING', 'VERIFYING', 'RETRYING']).count()
            check('BackupLog entries', True, f'Total: {total}, Success: {success}, Failed: {failed_b}, Pending/Running: {pending}')
            if failed_b > 0:
                self.stdout.write('\n   Recent failures:')
                for log in BackupLog.objects.filter(status='FAILED').order_by('-created_at')[:5]:
                    self.stdout.write(f'   - [{log.backup_type}] {log.filename}: {log.error_message or "No error message"}')
                    self.stdout.write(f'     Created: {log.created_at}')
        except Exception as e:
            check('BackupLog entries', False, f'Error: {e}')

        # 5. Check CourseResource backup_status
        self.stdout.write('\n5. Resource Backup Status:')
        try:
            from accounts.models import CourseResource
            total_r = CourseResource.objects.count()
            success_r = CourseResource.objects.filter(backup_status='SUCCESS').count()
            failed_r = CourseResource.objects.filter(backup_status='FAILED').count()
            pending_r = CourseResource.objects.filter(backup_status='PENDING').count()
            check('Resource backup status', True, f'Total: {total_r}, SUCCESS: {success_r}, FAILED: {failed_r}, PENDING: {pending_r}')
        except Exception as e:
            check('Resource backup status', False, f'Error: {e}')

        # Summary
        self.stdout.write('\n' + '=' * 50)
        total_checks = passed + failed
        if failed == 0:
            self.stdout.write(self.style.SUCCESS(f'RESULT: {passed}/{total_checks} passed — Drive backup should work'))
        else:
            self.stdout.write(self.style.WARNING(f'RESULT: {passed}/{total_checks} passed — {failed} issue(s) need fixing'))
            if not creds:
                self.stdout.write(self.style.ERROR('  FIX: Set GOOGLE_DRIVE_CREDENTIALS env var on Render'))
            else:
                self.stdout.write(self.style.WARNING('  FIX: Check the FAIL items above'))

