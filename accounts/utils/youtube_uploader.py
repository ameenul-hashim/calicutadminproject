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
                'embeddable': True,
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
                'status': {
                    'privacyStatus': privacy_status,
                    'embeddable': True,
                }
            }
        ).execute()
        logger.info(f"YouTube video {video_id} visibility changed to {privacy_status} (embeddable: True)")
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
    Returns {'upload_url': ..., 'access_token': ...} on success,
    or {'error': '...'} on failure with a specific message.
    """
    from google.auth.transport.requests import Request as GoogleRequest
    client_id = os.getenv('YOUTUBE_CLIENT_ID')
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
    refresh_token = os.getenv('YOUTUBE_REFRESH_TOKEN')

    if not all([client_id, client_secret, refresh_token]):
        logger.warning("YouTube credentials not configured")
        return {'error': 'YouTube API credentials not configured. Contact admin to set up YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN.'}

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=None
        )

        try:
            creds.refresh(GoogleRequest())
        except Exception as auth_err:
            logger.error(f"YouTube auth refresh failed: {auth_err}")
            return {'error': 'YouTube API credentials expired or invalid. Contact admin to re-authenticate with Google.'}

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
                'embeddable': True,
                'selfDeclaredMadeForKids': False,
            }
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=30)
        except requests.exceptions.ConnectionError:
            logger.error("YouTube API connection failed")
            return {'error': 'Cannot connect to YouTube API. Check your internet connection and try again.'}
        except requests.exceptions.Timeout:
            logger.error("YouTube API request timed out")
            return {'error': 'YouTube API request timed out. Please try again.'}

        if resp.status_code in (200, 201):
            upload_url = resp.headers.get('Location')
            if not upload_url:
                return {'error': 'YouTube did not return an upload URL. Please try again.'}
            return {'upload_url': upload_url, 'access_token': creds.token}

        error_msg = f"YouTube API error (HTTP {resp.status_code})"
        try:
            error_body = resp.json()
            api_errors = error_body.get('error', {}).get('errors', [])
            if api_errors:
                reason = api_errors[0].get('reason', '')
                message = api_errors[0].get('message', '')
                if 'quota' in reason.lower() or 'quota' in message.lower():
                    error_msg = 'YouTube API quota exhausted. The daily upload limit has been reached. Please try again tomorrow or contact admin to increase quota.'
                elif 'auth' in reason.lower() or 'expired' in reason.lower() or 'invalid' in reason.lower():
                    error_msg = 'YouTube API credentials are invalid or expired. Contact admin to re-authenticate.'
                else:
                    error_msg = f"YouTube API rejected the request: {message} (Reason: {reason})"
        except Exception:
            error_msg = f"YouTube API error (HTTP {resp.status_code}). Please try again."

        logger.error(f"YouTube resumable session error: {resp.status_code} {resp.text}")
        return {'error': error_msg}
    except Exception as e:
        logger.error(f"YouTube resumable session creation failed: {e}")
        return {'error': f'YouTube upload initialization failed unexpectedly: {str(e)}'}
