import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

load_dotenv()

def list_folders():
    if not os.path.exists('token.json'):
        print("token.json not found. Run auto_backup.py first.")
        return

    creds = Credentials.from_authorized_user_file('token.json')
    service = build('drive', 'v3', credentials=creds)

    print("--- GOOGLE DRIVE FOLDERS ---")
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces='drive',
        fields='files(id, name)',
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    items = results.get('files', [])
    if not items:
        print("No folders found.")
    else:
        for item in items:
            print(f"Name: {item['name']} | ID: {item['id']}")

if __name__ == "__main__":
    list_folders()
