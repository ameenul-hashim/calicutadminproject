from supabase import create_client
import os
import uuid

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_pdf(file):
    try:
        print("📁 FILE RECEIVED IN UPLOAD FUNCTION:", file)

        if not file:
            print("❌ No file received")
            return None

        file_ext = file.name.split('.')[-1]
        file_path = f"documents/{uuid.uuid4()}.{file_ext}"

        print("📂 FILE PATH:", file_path)

        # IMPORTANT
        file.seek(0)

        file_content = file.read()

        print("📦 FILE SIZE:", len(file_content))

        response = supabase.storage.from_("calicutadminpanelpdf").upload(
            file_path,
            file_content,
            {"content-type": "application/pdf"}
        )

        print("✅ UPLOAD RESPONSE:", response)

        public_url = supabase.storage.from_("calicutadminpanelpdf").get_public_url(file_path)

        print("🌐 PUBLIC URL:", public_url)

        return public_url

    except Exception as e:
        print("💥 UPLOAD ERROR:", str(e))
        return None
