from supabase import create_client
import os
import uuid
import logging

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")

# Singleton client instance
_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                logger.error(f"❌ Supabase initialization failed: {e}")
        else:
            logger.error("❌ SUPABASE_URL or SUPABASE_KEY not found in environment.")
    return _supabase_client

def upload_pdf(file):
    """Uploads a PDF and returns the STORAGE PATH (not the public URL)."""
    if not file:
        return None
        
    try:
        supabase = get_supabase_client()
        if not supabase:
            logger.error("❌ Supabase client not available.")
            return None

        # Ensure we are at the start of the file
        file.seek(0)
        file_content = file.read()
        
        file_ext = file.name.split('.')[-1] if hasattr(file, 'name') else 'pdf'
        file_path = f"documents/{uuid.uuid4()}.{file_ext}"

        # Upload attempt
        try:
            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=file_path,
                file=file_content,
                file_options={"content-type": "application/pdf"}
            )
            # Return the path so we can generate signed URLs later
            return file_path
        except Exception as upload_err:
            logger.error(f"❌ Supabase Upload Error: {upload_err}")
            return None

    except Exception as e:
        logger.error(f"💥 General Upload Error in upload_pdf: {e}")
        return None

def get_signed_url(file_path, expires_in=900):
    """
    Generates a signed URL for a file path.
    Default expiry is 15 minutes (900 seconds).
    """
    if not file_path:
        return None
    
    # If it's already a full URL (legacy), return it
    if file_path.startswith('http'):
        return file_path
        
    try:
        supabase = get_supabase_client()
        if not supabase:
            return None
            
        res = supabase.storage.from_(SUPABASE_BUCKET).create_signed_url(
            path=file_path,
            expires_in=expires_in
        )
        return res.get('signedURL') or res # Handle different lib versions
    except Exception as e:
        logger.error(f"❌ Error generating signed URL for {file_path}: {e}")
        return None
