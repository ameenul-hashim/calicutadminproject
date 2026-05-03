import uuid
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)
else:
    supabase = None

def upload_pdf(file):
    """
    Uploads a PDF to Supabase Storage and returns the public URL.
    """
    if not supabase:
        print("Supabase client not initialized. Check your .env file.")
        return None

    try:
        # Generate a unique name
        file_extension = file.name.split('.')[-1]
        unique_name = f"{uuid.uuid4()}.{file_extension}"
        file_path = f"lessons/{unique_name}"

        # Upload to bucket 'calicutadminpanelpdf'
        # Ensure you create this bucket in Supabase dashboard first!
        response = supabase.storage.from_("calicutadminpanelpdf").upload(
            path=file_path,
            file=file.read(),
            file_options={"content-type": "application/pdf"}
        )

        # Get public URL
        url_data = supabase.storage.from_("calicutadminpanelpdf").get_public_url(file_path)
        return url_data
        
    except Exception as e:
        print(f"Error uploading to Supabase: {e}")
        return None
