import os
import django
import time

# 1. Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
django.setup()

from accounts.utils.supabase_storage import supabase, generate_signed_url

def run_canary():
    print("🚦 EDUELEVATE WEEKLY CANARY CHECK")
    print("=" * 60)
    
    # A. Supabase Canary (Upload & Signed URL)
    try:
        bucket = os.getenv("SUPABASE_BUCKET", "calicutadminpanelpdf")
        test_file = "canary_test.txt"
        content = f"Canary check at {time.ctime()}".encode()
        
        # 1. Upload
        print("📤 Testing Supabase Upload...")
        res = supabase.storage.from_(bucket).upload(test_file, content, {"upsert": "true"})
        print("✅ Upload Success.")
        
        # 2. Signed URL
        print("🔗 Testing Signed URL Generation...")
        url = generate_signed_url(test_file)
        if url:
            print(f"✅ URL Generated: {url[:50]}...")
        else:
            raise Exception("URL generation returned empty")
            
        # 3. Cleanup
        supabase.storage.from_(bucket).remove([test_file])
        print("🧹 Canary cleanup complete.")
        
    except Exception as e:
        print(f"❌ SUPABASE CANARY FAILURE: {e}")

    # B. DB Query Canary
    try:
        from django.db import connection
        start = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print(f"✅ DB Canary: latency {round((time.time()-start)*1000, 2)}ms")
    except Exception as e:
        print(f"❌ DB CANARY FAILURE: {e}")

    print("=" * 60)
    print("🎯 CANARY FINISHED.")

if __name__ == "__main__":
    run_canary()
