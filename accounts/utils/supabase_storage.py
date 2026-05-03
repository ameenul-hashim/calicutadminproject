import requests
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BUCKET = "calicutadminpanelpdf"

def upload_pdf(file):
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials not found in .env")
        return None

    try:
        # Generate a unique name
        file_extension = file.name.split('.')[-1]
        unique_name = f"{uuid.uuid4()}.{file_extension}"
        
        # Determine folder based on file type or just root
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{unique_name}"

        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/pdf"
        }

        # Read file content
        file_content = file.read()
        
        response = requests.put(url, headers=headers, data=file_content)

        if response.status_code in [200, 201]:
            # Construct public URL
            return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{unique_name}"
        else:
            print(f"Supabase Upload Error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception during Supabase upload: {e}")
        return None
