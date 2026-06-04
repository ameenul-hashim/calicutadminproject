import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def test_main():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")
    print(f"--- Main Supabase ({url}) ---")
    if not url or not key:
        print("MISSING CONFIG")
        return
    try:
        client = create_client(url, key)
        buckets = client.storage.list_buckets()
        print(f"Connection OK. Buckets: {[b.name for b in buckets]}")
        if bucket in [b.name for b in buckets]:
            print(f"Bucket '{bucket}' EXISTS.")
        else:
            print(f"Bucket '{bucket}' NOT FOUND.")
    except Exception as e:
        print(f"ERROR: {e}")

def test_resource():
    url = os.getenv("RESOURCE_SUPABASE_URL")
    key = os.getenv("RESOURCE_SUPABASE_SERVICE_ROLE_KEY")
    print(f"\n--- Resource Supabase ({url}) ---")
    if not url or not key:
        print("MISSING CONFIG")
        return
    try:
        client = create_client(url, key)
        buckets = client.storage.list_buckets()
        print(f"Connection OK. Buckets: {[b.name for b in buckets]}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_main()
    test_resource()
