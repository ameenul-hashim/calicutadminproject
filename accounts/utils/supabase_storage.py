from supabase import create_client
import os
import uuid

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Singleton client instance to avoid repeated initialization overhead
_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        if SUPABASE_URL and SUPABASE_KEY:
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

def upload_pdf(file):
    try:
        supabase = get_supabase_client()
        if not supabase:
            print("❌ Supabase client initialization failed.")
            return None

        file_ext = file.name.split('.')[-1]
        file_path = f"documents/{uuid.uuid4()}.{file_ext}"

        file.seek(0)
        file_content = file.read()

        # Direct upload
        supabase.storage.from_("calicutadminpanelpdf").upload(
            file_path,
            file_content,
            {"content-type": "application/pdf"}
        )

        return supabase.storage.from_("calicutadminpanelpdf").get_public_url(file_path)

    except Exception as e:
        print("💥 UPLOAD ERROR:", str(e))
        return None
