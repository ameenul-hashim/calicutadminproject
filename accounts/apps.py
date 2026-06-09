from django.apps import AppConfig
import sys

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # Only run startup tasks if running the actual server, not during migrations/management commands
        is_server = any(cmd in arg for arg in sys.argv for cmd in ['runserver', 'daphne', 'gunicorn'])
        if is_server:
            try:
                from .utils.keep_alive import start_keep_alive
                start_keep_alive()
            except ImportError:
                pass

            # Startup log: Google Drive credential status
            try:
                from .utils.drive_backup_service import _load_credentials_json, _get_drive_service
                parsed, source = _load_credentials_json()
                if parsed:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f'Google Drive credentials loaded: PASS (source: {source})')
                    service = _get_drive_service()
                    if service:
                        logger.info('Google Drive client initialized: PASS')
                        try:
                            from .utils.drive_backup_service import ensure_folder_path
                            folder_id = ensure_folder_path(service, ['NeoLearner_Backups', 'StartupCheck'])
                            if folder_id:
                                logger.info('Google Drive backup folder verified: PASS')
                        except Exception as e:
                            logger.warning(f'Google Drive backup folder check: FAIL ({e})')
                    else:
                        logger.warning('Google Drive client initialized: FAIL')
                else:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f'Google Drive credentials loaded: FAIL ({source})')
            except Exception:
                pass
