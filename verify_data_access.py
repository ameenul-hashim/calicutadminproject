import os
import subprocess
import datetime
import requests
import cloudinary
from cloudinary.api import resources
from dotenv import load_dotenv

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Load environment variables
load_dotenv()

def separator(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

def verify_db():
    separator("VERIFYING DATABASE DUMP")
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL missing from .env")
        return False
    
    filename = "test_dump.sql"
    print(f"Running pg_dump for: {db_url[:20]}...")
    
    try:
        # Use shell=True for Windows and handle quotes
        result = subprocess.run(
            f'pg_dump "{db_url}" > {filename}',
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and os.path.exists(filename) and os.path.getsize(filename) > 0:
            size = os.path.getsize(filename) / 1024
            print(f"✅ Database dump successful! Created {filename} ({size:.2f} KB)")
            os.remove(filename) # Cleanup
            return True
        else:
            print(f"❌ Database dump failed.")
            print(f"Error: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ Error during pg_dump: {e}")
        return False

def verify_cloudinary():
    separator("VERIFYING CLOUDINARY ACCESS")
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )
    
    try:
        # List raw resources
        res = resources(
            type="upload",
            resource_type="raw",
            prefix="eduaimsthinker/pdfs",
            max_results=5
        )
        files = res.get("resources", [])
        if files:
            print(f"✅ Cloudinary connected! Found {len(files)} PDFs (showing first 5):")
            for f in files:
                print(f"   - {f['public_id']}")
            return True
        else:
            print("⚠️ Cloudinary connected, but no PDFs found with prefix 'eduaimsthinker/pdfs'")
            # Check all raw to be sure
            res_all = resources(type="upload", resource_type="raw", max_results=5)
            all_files = res_all.get("resources", [])
            if all_files:
                print(f"Found {len(all_files)} other raw files. Check your prefix in auto_backup.py.")
            return True
    except Exception as e:
        print(f"❌ Cloudinary connection failed: {e}")
        return False

if __name__ == "__main__":
    db_ok = verify_db()
    cl_ok = verify_cloudinary()
    
    separator("FINAL STATUS")
    print(f"DATABASE:   {'✅ READY' if db_ok else '❌ FAILED'}")
    print(f"CLOUDINARY: {'✅ READY' if cl_ok else '❌ FAILED'}")
    print(f"GDRIVE:     ⌛ AWAITING credentials.json")
    
    if db_ok and cl_ok:
        print("\n🚀 Both data sources are ready. As soon as you add 'credentials.json',")
        print("   the full 'python auto_backup.py' command will work end-to-end.")
