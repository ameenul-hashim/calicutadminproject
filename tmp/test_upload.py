import os
from supabase import create_client
from dotenv import load_dotenv
import uuid

load_dotenv()

def test_upload():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")
    
    if not url or not key:
        print("MISSING CONFIG")
        return
        
    try:
        client = create_client(url, key)
        content = b"%PDF-1.4 test content"
        path = f"test_{uuid.uuid4()}.pdf"
        
        print(f"Attempting upload to {bucket}/{path}...")
        res = client.storage.from_(bucket).upload(
            path=path,
            file=content,
            file_options={
                "content-type": "application/pdf",
                "upsert": "true"
            }
        )
        print(f"Upload result: {res}")
        
    except Exception as e:
        print(f"UPLOAD ERROR: {e}")

if __name__ == "__main__":
    test_upload()
