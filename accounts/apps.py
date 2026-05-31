from django.apps import AppConfig
import sys

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # Only start keep-alive if running the actual server, not during migrations/management commands
        is_server = any(cmd in arg for arg in sys.argv for cmd in ['runserver', 'daphne', 'gunicorn'])
        if is_server:
            try:
                from .utils.keep_alive import start_keep_alive
                start_keep_alive()
            except ImportError:
                pass
