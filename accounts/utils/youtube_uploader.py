import os
import logging
import tempfile
import time
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/youtube']

YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'


def get_authenticated_service():
    client_id = os.getenv('YOUTUBE_CLIENT_ID')
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
    refresh_token = os.getenv('YOUTUBE_REFRESH_TOKEN')

    if not all([client_id, client_secret, refresh_token]):
        logger.warning("YouTube credentials not configured (YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN)")
        return None

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=None
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=creds)
    except Exception as e:
        logger.error(f"YouTube auth error: {e}")
        return None


def upload_video(video_file, title, description, privacy_status='private'):
    youtube = get_authenticated_service()
    if not youtube:
        raise ValueError("YouTube service not available. Check YOUTUBE_* env vars.")

    import uuid
    tmp_path = None
    try:
        if isinstance(video_file, str):
            tmp_path = video_file
        else:
            suffix = '.mp4'
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            for chunk in video_file.chunks():
                tmp.write(chunk)
            tmp.close()
            tmp_path = tmp.name

        body = {
            'snippet': {
                'title': title[:100],
                'description': (description or '')[ :5000],
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False,
            }
        }

        media = MediaFileUpload(tmp_path, chunksize=4*1024*1024, resumable=True)
        request = youtube.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"YouTube upload progress: {progress}%")

        video_id = response.get('id')
        logger.info(f"YouTube upload complete: {video_id}")
        return video_id

    except Exception as e:
        logger.error(f"YouTube upload error: {e}")
        raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def change_video_visibility(video_id, privacy_status):
    youtube = get_authenticated_service()
    if not youtube:
        raise ValueError("YouTube service not available")
    try:
        youtube.videos().update(
            part='status',
            body={
                'id': video_id,
                'status': {'privacyStatus': privacy_status}
            }
        ).execute()
        logger.info(f"YouTube video {video_id} visibility changed to {privacy_status}")
    except Exception as e:
        logger.error(f"YouTube visibility change error: {e}")
        raise


def delete_youtube_video(video_id):
    youtube = get_authenticated_service()
    if not youtube:
        raise ValueError("YouTube service not available")
    try:
        youtube.videos().delete(id=video_id).execute()
        logger.info(f"YouTube video {video_id} deleted")
    except Exception as e:
        logger.error(f"YouTube video delete error: {e}")
        raise


def create_resumable_upload_url(title, description, file_size=None):
    """
    Creates a YouTube resumable upload session and returns the upload URL.
    The browser uploads the file directly to this URL — no server RAM used.
    """
    from google.auth.transport.requests import Request as GoogleRequest
    client_id = os.getenv('YOUTUBE_CLIENT_ID')
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
    refresh_token = os.getenv('YOUTUBE_REFRESH_TOKEN')

    if not all([client_id, client_secret, refresh_token]):
        logger.warning("YouTube credentials not configured")
        return None

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=None
        )
        creds.refresh(GoogleRequest())

        url = 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status'
        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-Type': 'application/json',
            'X-Upload-Content-Type': 'video/*',
        }
        if file_size:
            headers['X-Upload-Content-Length'] = str(file_size)

        body = {
            'snippet': {
                'title': title[:100],
                'description': (description or '')[:5000],
            },
            'status': {
                'privacyStatus': 'unlisted',
                'selfDeclaredMadeForKids': False,
            }
        }

        resp = requests.post(url, headers=headers, json=body)
        if resp.status_code in (200, 201):
            upload_url = resp.headers.get('Location')
            return upload_url

        logger.error(f"YouTube resumable session error: {resp.status_code} {resp.text}")
        return None
    except Exception as e:
        logger.error(f"YouTube resumable session creation failed: {e}")
        return None
