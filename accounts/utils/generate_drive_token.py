"""
Run this script ONCE locally to get your Google Drive OAuth refresh token.
1. Set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET in .env
2. Run: python -m accounts.utils.generate_drive_token
3. Authorize via browser when it opens
4. Copy the refresh token and set as GOOGLE_DRIVE_REFRESH_TOKEN in .env and on Render
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/drive.file']

client_id = os.getenv('GOOGLE_DRIVE_CLIENT_ID')
client_secret = os.getenv('GOOGLE_DRIVE_CLIENT_SECRET')

if not client_id or not client_secret:
    print('ERROR: Set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET in .env first')
    exit(1)

from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    {
        'installed': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
    },
    SCOPES,
    redirect_uri='http://localhost'
)

creds = flow.run_local_server(port=0, open_browser=True)

print('\n' + '=' * 60)
print('SUCCESS! Add this to your .env and Render:')
print('=' * 60)
print(f'GOOGLE_DRIVE_REFRESH_TOKEN="{creds.refresh_token}"')
print('=' * 60)
