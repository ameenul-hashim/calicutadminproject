import os
import json
import time
import uuid
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Tests Firebase RTDB connectivity by writing, reading, and deleting a test record'

    def add_arguments(self, parser):
        parser.add_argument('--verbose', action='store_true', help='Detailed output')

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)
        self.stdout.write('=== Firebase RTDB Health Check ===')
        self.stdout.write('')

        # Step 0: Check env vars
        db_url = os.getenv('FIREBASE_RTDB_URL')
        json_str = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        json_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')

        self.stdout.write(f'  FIREBASE_RTDB_URL:         {"SET" if db_url else "MISSING!"}')
        self.stdout.write(f'  FIREBASE_SERVICE_ACCOUNT_JSON: {"SET" if json_str else "not set"}')
        self.stdout.write(f'  FIREBASE_SERVICE_ACCOUNT_PATH: {"SET" if json_path else "not set"}')
        if json_path:
            self.stdout.write(f'    path: {json_path}')
            self.stdout.write(f'    exists on disk: {"YES" if os.path.exists(json_path) else "NO"}')
        self.stdout.write('')

        if not db_url:
            self.stdout.write(self.style.ERROR('FAIL: FIREBASE_RTDB_URL is required'))
            return

        if not json_str and not json_path:
            self.stdout.write(self.style.ERROR('FAIL: No Firebase credentials found'))
            return

        if json_path and not os.path.exists(json_path):
            self.stdout.write(self.style.WARNING(f'WARN: FIREBASE_SERVICE_ACCOUNT_PATH file not found at: {json_path}'))
            self.stdout.write('  (Will try FIREBASE_SERVICE_ACCOUNT_JSON next if available)')

        # Step 1: Initialize
        self.stdout.write('  Initializing Firebase...')
        try:
            import firebase_admin
            from firebase_admin import credentials, db as rtdb

            app_name = 'health_check'
            cred = None
            cred_source = None
            try:
                app = firebase_admin.get_app(app_name)
            except ValueError:
                app = None

            if app is None:
                if json_str:
                    cred = credentials.Certificate(json.loads(json_str))
                    cred_source = 'FIREBASE_SERVICE_ACCOUNT_JSON'
                elif json_path and os.path.exists(json_path):
                    cred = credentials.Certificate(json_path)
                    cred_source = f'FIREBASE_SERVICE_ACCOUNT_PATH ({json_path})'
                elif json_path:
                    self.stdout.write(self.style.ERROR('FAIL: FIREBASE_SERVICE_ACCOUNT_PATH file does not exist'))
                    return
                else:
                    self.stdout.write(self.style.ERROR('FAIL: No usable credentials'))
                    return

                app = firebase_admin.initialize_app(cred, {'databaseURL': db_url}, name=app_name)

            self.stdout.write(self.style.SUCCESS(f'  Firebase initialized | source={cred_source} | db_url={db_url}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Firebase init FAILED: {e}'))
            return

        # Step 2: Write test record
        test_uid = f'health_check_{uuid.uuid4().hex[:8]}'
        test_path = f'/health_checks/{test_uid}'
        test_data = {
            'test': True,
            'timestamp': int(time.time() * 1000),
            'message': 'Firebase health check write test',
        }
        self.stdout.write(f'  Writing test record to {test_path}...')
        try:
            ref = rtdb.reference(test_path, app=app)
            ref.set(test_data)
            self.stdout.write(self.style.SUCCESS('  WRITE: PASS'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  WRITE: FAIL — {e}'))
            return

        # Step 3: Read test record
        self.stdout.write('  Reading test record back...')
        try:
            read_data = ref.get()
            if read_data and read_data.get('test') is True:
                self.stdout.write(self.style.SUCCESS(f'  READ: PASS — data={json.dumps(read_data, indent=2)}' if verbose else '  READ: PASS'))
            else:
                self.stdout.write(self.style.ERROR(f'  READ: FAIL — unexpected data: {read_data}'))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  READ: FAIL — {e}'))
            return

        # Step 4: Delete test record
        self.stdout.write('  Deleting test record...')
        try:
            ref.delete()
            # Verify deletion
            verify = rtdb.reference(test_path, app=app).get()
            if verify is None:
                self.stdout.write(self.style.SUCCESS('  DELETE: PASS'))
            else:
                self.stdout.write(self.style.WARNING(f'  DELETE: PARTIAL — record still exists: {verify}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  DELETE: FAIL — {e}'))
            return

        # Step 5: Full result
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== FIREBASE HEALTH: PASS ==='))
        self.stdout.write(self.style.SUCCESS(f'  Credential source: {cred_source}'))
        self.stdout.write(self.style.SUCCESS(f'  RTDB URL: {db_url}'))
        self.stdout.write(self.style.SUCCESS(f'  Operations: WRITE -> READ -> DELETE - all successful'))
