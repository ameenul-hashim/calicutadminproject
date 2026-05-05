import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")

print(f"URL: {url}")
print(f"Key: {key[:10]}...")
print(f"Bucket: {bucket}")

if not url or not key:
    print("Missing credentials")
    exit(1)

try:
    supabase = create_client(url, key)
    buckets = supabase.storage.list_buckets()
    print("Connection successful. Buckets:")
    for b in buckets:
        print(f"- {b.name}")
    
    # Try to list files in the bucket
    files = supabase.storage.from_(bucket).list()
    print(f"Files in {bucket}: {len(files)} files found.")

    # Try a test upload
    print("Attempting test upload...")
    test_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    test_path = "test_connection.pdf"
    try:
        res = supabase.storage.from_(bucket).upload(
            path=test_path,
            file=test_content,
            file_options={"content-type": "application/pdf", "upsert": "true"}
        )
        print(f"Upload successful: {res}")
        # Clean up
        supabase.storage.from_(bucket).remove([test_path])
        print("Cleanup successful.")
    except Exception as upload_error:
        print(f"Upload FAILED: {upload_error}")

except Exception as e:
    print(f"Error: {e}")
