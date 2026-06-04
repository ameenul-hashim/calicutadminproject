import os
import re
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
import uuid
import mimetypes

load_dotenv()

logger = logging.getLogger(__name__)

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
bucket_name: str = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")
video_bucket: str = os.getenv("SUPABASE_VIDEO_BUCKET", bucket_name)

# Initialize client
supabase: Client = None
if url and key:
    try:
        supabase = create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase Client Init Error: {e}")

def validate_pdf(file_content, filename=None):
    """
    Validates that the content is a PDF.
    Uses mimetypes for stability on Windows systems without libmagic.
    """
    if filename:
        mime, _ = mimetypes.guess_type(filename)
        if mime == "application/pdf":
            return True
            
    # Fallback: check PDF magic number %PDF- (0x25 0x50 0x44 0x46 0x2d)
    if file_content.startswith(b'%PDF-'):
        return True
        
    raise ValueError("Invalid file type. Only PDFs are allowed.")

def upload_pdf(destination_path_or_file, file_content=None, filename=None):
    """
    Uploads a PDF to Supabase Storage.
    Supports two signatures:
    1. upload_pdf(file_obj) -> For legacy compatibility
    2. upload_pdf(path, content, filename) -> For explicit control
    """
    if not supabase:
        logger.error("Supabase client not initialized")
        return None

    try:
        # Signature 1: Legacy (file object only)
        if file_content is None:
            file_obj = destination_path_or_file
            file_obj.seek(0)
            file_content = file_obj.read()
            file_obj.seek(0)
            
            # Generate a unique path in the 'documents' folder
            file_ext = file_obj.name.split('.')[-1] if hasattr(file_obj, 'name') else 'pdf'
            destination_path = f"documents/{uuid.uuid4()}.{file_ext}"
            filename = getattr(file_obj, 'name', None)
        else:
            # Signature 2: Explicit path and content
            destination_path = destination_path_or_file

        validate_pdf(file_content, filename)
        
        # Ensure path starts with documents/ if it doesn't have a folder
        if "/" not in destination_path:
            destination_path = f"documents/{destination_path}"
        
        # Remove leading slash
        if destination_path.startswith("/"):
            destination_path = destination_path[1:]

        # Upload attempt
        supabase.storage.from_(bucket_name).upload(
            path=destination_path,
            file=file_content,
            file_options={
                "content-type": "application/pdf",
                "upsert": "true"
            }
        )
        return destination_path
    except Exception as e:
        logger.error(f"Supabase Upload Error: {e}")
        return None

def get_signed_url(file_path: str, expires_in: int = 3600):
    """
    Generates a signed URL for a private file.
    Default expiry is 1 hour.
    """
    if not supabase or not file_path:
        return file_path # Return as is if it's a legacy URL

    # If it's already a full URL (legacy), return it
    if str(file_path).startswith('http'):
        return file_path

    try:
        if file_path.startswith("/"):
            file_path = file_path[1:]

        res = supabase.storage.from_(bucket_name).create_signed_url(file_path, expires_in)
        # Handle different response formats from supabase-py
        if isinstance(res, dict) and "signedURL" in res:
            return res["signedURL"]
        return res
    except Exception as e:
        logger.error(f"Supabase Signed URL Error: {e}")
        return None

def delete_pdf(file_path: str):
    """Deletes a file from Supabase Storage."""
    if not supabase or not file_path:
        return False

    try:
        if file_path.startswith("/"):
            file_path = file_path[1:]
            
        supabase.storage.from_(bucket_name).remove([file_path])
        return True
    except Exception as e:
        logger.error(f"Supabase Deletion Error: {e}")
        return False

def create_signed_upload_url(file_path: str, expires_in: int = 3600):
    """
    Creates a signed upload URL for browser-direct upload to Supabase.
    The browser can PUT files directly to this URL without going through Django.
    Returns dict with 'signed_url' and 'token', or None on error.
    """
    if not supabase or not file_path:
        return None
    try:
        if file_path.startswith("/"):
            file_path = file_path[1:]
        res = supabase.storage.from_(video_bucket).create_signed_upload_url(file_path)
        if isinstance(res, dict) and 'signed_url' in res:
            return res
        return res
    except Exception as e:
        logger.error(f"Supabase Signed Upload URL Error: {e}")
        return None

def stream_video_upload(video_file, lesson_uid):
    """
    Uploads an MP4 video to Supabase. Memory-optimized for Render 512MB.
    Writes to temp file first, then reads back and uploads.
    Note: Supabase SDK requires full file in memory for upload — this is unavoidable.
    """
    if not supabase:
        logger.error("Supabase client not initialized")
        return None
    import tempfile, os, gc
    destination_path = f"videos/lesson_{lesson_uid}.mp4"
    if destination_path.startswith("/"):
        destination_path = destination_path[1:]

    tmp_path = None
    try:
        # Step 1: Stream incoming file to temp on disk (keeps Django memory low)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        tmp_path = tmp.name
        total_written = 0
        for chunk in video_file.chunks(chunk_size=1024 * 1024):
            tmp.write(chunk)
            total_written += len(chunk)
        tmp.close()
        logger.info(f"Video temp file ready: {tmp_path} ({total_written} bytes)")

        # Step 2: Read from disk and upload to Supabase
        with open(tmp_path, 'rb') as f:
            content = f.read()
        gc.collect()  # Hint Python to free other objects before large allocation
        supabase.storage.from_(video_bucket).upload(
            path=destination_path,
            file=content,
            file_options={"content-type": "video/mp4", "upsert": "true"}
        )
        del content
        gc.collect()
        logger.info(f"Video uploaded to Supabase ({video_bucket}): {destination_path}")
        return f"{video_bucket}/{destination_path}"
    except Exception as e:
        logger.error(f"Supabase Video Upload Error: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

def upload_video_to_supabase(video_file, lesson_uid):
    """
    Uploads an MP4 video to Supabase. Memory-optimized for Render 512MB.
    Writes to temp file first, then streams to Supabase.
    """
    return stream_video_upload(video_file, lesson_uid)

def upload_user_proof(instance, pdf_file):
    """
    High-level helper to upload a user's verification PDF to Supabase.
    Updates the model instance with the path and sets status to PENDING.
    Organises into students/ or teachers/ subfolder based on user type.
    """
    try:
        content = pdf_file.read()
        pdf_file.seek(0)

        user_type = instance.user_type.lower()
        folder = "students" if user_type == "student" else "teachers"
        safe_username = re.sub(r'[^a-zA-Z0-9._-]', '_', instance.username)
        role_tag = "student" if user_type == "student" else "teacher"
        destination_path = f"documents/{folder}/{safe_username}-{role_tag}-signup.pdf"

        path = upload_pdf(destination_path, content, destination_path)
        if not path:
            logger.error(f"Supabase Upload Failed for user {instance.username}. Path returned None.")
            return False

        from django.db import transaction
        with transaction.atomic():
            instance.pdf_path = path
            instance.status = "PENDING"
            instance.save()

        return True
    except Exception as e:
        logger.error(f"Error in upload_user_proof for user {instance.username}: {str(e)}")
        return False


