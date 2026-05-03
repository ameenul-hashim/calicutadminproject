from supabase import create_client
import os
import uuid
import logging

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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
        bucket_name = "calicutadminpanelpdf"
        try:
            res = supabase.storage.from_(bucket_name).upload(
                path=file_path,
                file=file_content,
                file_options={"content-type": "application/pdf"}
            )
            
            # Get public URL
            public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
            return public_url
        except Exception as upload_err:
            logger.error(f"❌ Supabase Upload Error: {upload_err}")
            return None

    except Exception as e:
        logger.error(f"💥 General Upload Error in upload_pdf: {e}")
        return None
