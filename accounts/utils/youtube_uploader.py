import os
import logging
import tempfile
import time
import requests
import hashlib
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/youtube']

YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

SESSION_IDLE_TIMEOUT_MINUTES = 55
SESSION_TOTAL_TIMEOUT_HOURS = 23


def _get_credentials():
    client_id = os.getenv('YOUTUBE_CLIENT_ID')
    client_secret = os.getenv('YOUTUBE_CLIENT_SECRET')
    refresh_token = os.getenv('YOUTUBE_REFRESH_TOKEN')
    if not all([client_id, client_secret, refresh_token]):
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
        creds.refresh(Request())
        return creds
    except Exception as e:
        logger.error(f"YouTube credential refresh error: {e}")
        return None


def get_authenticated_service():
    creds = _get_credentials()
    if not creds:
        return None
    try:
        return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=creds)
    except Exception as e:
        logger.error(f"YouTube build error: {e}")
        return None


def get_fresh_access_token():
    creds = _get_credentials()
    if not creds:
        return None
    return creds.token


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
                'description': (description or '')[:5000],
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
    creds = _get_credentials()
    if not creds:
        return {'error': 'YouTube API credentials not configured or expired. Contact admin.'}

    try:
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


def query_uploaded_bytes(upload_url, access_token, total_bytes):
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Length': '0',
            'Content-Range': f'bytes */{total_bytes}',
        }
        resp = requests.put(upload_url, headers=headers, timeout=30)
        if resp.status_code == 308:
            range_header = resp.headers.get('Range', '')
            if range_header:
                match = __import__('re').match(r'bytes=0-(\d+)', range_header)
                if match:
                    return int(match.group(1)) + 1
            return 0
        elif resp.status_code in (200, 201):
            return -1
        elif resp.status_code == 404 or resp.status_code == 410:
            return -2
        else:
            logger.warning(f"query_uploaded_bytes: unexpected status {resp.status_code}")
            return 0
    except requests.exceptions.Timeout:
        logger.warning("query_uploaded_bytes: timeout")
        return -3
    except Exception as e:
        logger.error(f"query_uploaded_bytes error: {e}")
        return -3


def verify_youtube_video(video_id):
    if not video_id:
        return False
    try:
        youtube = get_authenticated_service()
        if not youtube:
            return False
        request = youtube.videos().list(part='status,processingDetails', id=video_id)
        response = request.execute()
        items = response.get('items', [])
        if not items:
            return False
        item = items[0]
        status = item.get('status', {})
        processing = item.get('processingDetails', {})
        upload_status = status.get('uploadStatus', 'unknown')
        privacy_status = status.get('privacyStatus', 'unknown')
        embeddable = status.get('embeddable', False)
        processing_status = processing.get('processingStatus', 'unknown')
        failure_reason = processing.get('processingFailureReason', '')

        logger.info(
            f"YouTube video {video_id} status: uploadStatus={upload_status}, "
            f"processingStatus={processing_status}, privacyStatus={privacy_status}, "
            f"embeddable={embeddable}"
            f"{', failureReason=' + failure_reason if failure_reason else ''}"
        )

        if upload_status in ('rejected', 'failed'):
            return False
        if processing_status == 'failed':
            return False
        if not embeddable:
            return False
        if upload_status == 'uploaded' and processing_status == 'succeeded':
            return True
        return False
    except Exception as e:
        logger.error(f"YouTube verification error for {video_id}: {e}")
        return False


def get_processing_details(video_id):
    if not video_id:
        return {'error': 'No video_id'}
    try:
        youtube = get_authenticated_service()
        if not youtube:
            return {'error': 'YouTube service unavailable'}
        request = youtube.videos().list(part='status,processingDetails,snippet', id=video_id)
        response = request.execute()
        items = response.get('items', [])
        if not items:
            return {'error': 'Video not found'}
        item = items[0]
        status = item.get('status', {})
        processing = item.get('processingDetails', {})
        snippet = item.get('snippet', {})
        upload_status = status.get('uploadStatus', 'unknown')
        processing_status = processing.get('processingStatus', 'unknown')
        failure_reason = processing.get('processingFailureReason', '')
        embeddable = status.get('embeddable', False)
        privacy_status = status.get('privacyStatus', 'unknown')
        thumbnails = snippet.get('thumbnails', {})
        has_thumbnail = 'default' in thumbnails if thumbnails else False

        result = {
            'video_id': video_id,
            'upload_status': upload_status,
            'processing_status': processing_status,
            'embeddable': embeddable,
            'privacy_status': privacy_status,
            'has_thumbnail': has_thumbnail,
            'failure_reason': failure_reason,
            'title': snippet.get('title', ''),
        }

        if processing_status == 'succeeded' and upload_status == 'uploaded':
            result['ready'] = True
        elif processing_status == 'failed':
            result['ready'] = False
            result['error'] = f'Processing failed: {failure_reason}'
        elif upload_status == 'uploaded':
            result['ready'] = False
            result['error'] = 'still_processing'
        else:
            result['ready'] = False
            result['error'] = f'Upload status: {upload_status}'

        return result
    except Exception as e:
        logger.error(f"get_processing_details error: {e}")
        return {'error': str(e)}


def verify_youtube_processing_status(video_id):
    if not video_id:
        return 'FAILED'
    try:
        youtube = get_authenticated_service()
        if not youtube:
            return 'PENDING'
        request = youtube.videos().list(part='status,processingDetails', id=video_id)
        response = request.execute()
        items = response.get('items', [])
        if not items:
            return 'FAILED'
        item = items[0]
        status = item.get('status', {})
        processing = item.get('processingDetails', {})
        upload_status = status.get('uploadStatus', 'unknown')
        processing_status = processing.get('processingStatus', 'unknown')
        failure_reason = processing.get('processingFailureReason', '')
        embeddable = status.get('embeddable', False)

        if upload_status in ('rejected', 'failed') or processing_status == 'failed':
            logger.warning(f"verify_youtube_processing_status: {video_id} failed: {failure_reason}")
            return 'FAILED'
        if processing_status == 'processing' or (upload_status == 'uploaded' and processing_status != 'succeeded'):
            return 'PROCESSING'
        if processing_status == 'succeeded' and upload_status == 'uploaded' and embeddable:
            return 'VERIFIED'
        return 'PROCESSING'
    except Exception as e:
        logger.error(f"verify_youtube_processing_status error: {e}")
        return 'PENDING'


def renew_upload_session(title, description, file_size=None):
    return create_resumable_upload_url(title, description, file_size)


def compute_file_hash_first_5mb(file_obj):
    hasher = hashlib.sha256()
    chunk = file_obj.read(5242880)
    hasher.update(chunk)
    file_obj.seek(0)
    return hasher.hexdigest()


def find_latest_youtube_upload(lesson_title=None, minutes_back=30):
    youtube = get_authenticated_service()
    if not youtube:
        return None

    try:
        search_response = youtube.search().list(
            part='snippet',
            forMine=True,
            order='date',
            maxResults=10,
            type='video',
        ).execute()

        items = search_response.get('items', [])
        if not items:
            return None

        cutoff = datetime.utcnow() - timedelta(minutes=minutes_back)
        best_match = None

        for item in items:
            snippet = item.get('snippet', {})
            video_id = item['id']['videoId']
            published_str = snippet.get('publishedAt', '')

            try:
                published_str = published_str.replace('Z', '+00:00')
                published_dt = datetime.fromisoformat(published_str)
                published_utc = published_dt.replace(tzinfo=None) if published_dt.tzinfo else published_dt
            except Exception:
                published_utc = datetime.utcnow()

            if published_utc < cutoff:
                continue

            item_title = snippet.get('title', '')
            if lesson_title and lesson_title.lower() in item_title.lower():
                logger.info(f"find_latest_youtube_upload: Title match -> {video_id}")
                return video_id

            if best_match is None or published_utc > best_match['published']:
                best_match = {'video_id': video_id, 'published': published_utc, 'title': item_title}

        if best_match:
            logger.info(f"find_latest_youtube_upload: Using most recent -> {best_match['video_id']}")
            return best_match['video_id']

        return None
    except Exception as e:
        logger.error(f"find_latest_youtube_upload error: {e}")
        return None


def get_video_thumbnail_status(video_id):
    """Check if YouTube thumbnail is available for a video."""
    if not video_id:
        return {'has_thumbnail': False, 'thumbnail_url': ''}
    try:
        youtube = get_authenticated_service()
        if not youtube:
            return {'has_thumbnail': False, 'thumbnail_url': ''}
        request = youtube.videos().list(part='snippet', id=video_id)
        response = request.execute()
        items = response.get('items', [])
        if not items:
            return {'has_thumbnail': False, 'thumbnail_url': ''}
        thumbnails = items[0].get('snippet', {}).get('thumbnails', {})
        has_thumb = 'default' in thumbnails
        url = ''
        if has_thumb:
            url = thumbnails.get('high', thumbnails.get('default', {})).get('url', '')
        return {'has_thumbnail': has_thumb, 'thumbnail_url': url}
    except Exception as e:
        logger.error(f"get_video_thumbnail_status error: {e}")
        return {'has_thumbnail': False, 'thumbnail_url': ''}


def check_upload_session_valid(upload_url, access_token):
    """Check if a YouTube resumable upload session is still valid."""
    if not upload_url or not access_token:
        return False
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Length': '0',
            'Content-Range': 'bytes */0',
        }
        resp = requests.put(upload_url, headers=headers, timeout=15)
        if resp.status_code in (200, 201, 308):
            return True
        if resp.status_code in (404, 410):
            return False
        if resp.status_code in (401, 403):
            return False
        return True
    except Exception as e:
        logger.warning(f"check_upload_session_valid error: {e}")
        return False


def get_video_embed_html(video_id, width=560, height=315):
    """Generate embed HTML for a YouTube video that is still processing.
    Shows 'Processing...' overlay instead of broken thumbnail."""
    if not video_id:
        return '<div class="video-processing">No video</div>'
    return (
        f'<div style="position:relative;width:{width}px;height:{height}px;background:#1a1a2e;'
        f'border-radius:8px;display:flex;align-items:center;justify-content:center;overflow:hidden;">'
        f'<iframe src="https://www.youtube.com/embed/{video_id}?autoplay=0" '
        f'width="{width}" height="{height}" frameborder="0" '
        f'allow="accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture" '
        f'allowfullscreen style="opacity:0;position:absolute;top:0;left:0;"></iframe>'
        f'<div style="color:#94a3b8;font-size:1.1rem;font-weight:500;text-align:center;z-index:1;">'
        f'<div style="font-size:2rem;margin-bottom:0.5rem;">⏳</div>'
        f'Processing...<br><span style="font-size:0.85rem;color:#64748b;">Video will appear shortly</span>'
        f'</div></div>'
    )
