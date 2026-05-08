"""
Backup Pipeline Diagnostic Script
Tests each component independently and reports status.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import os
import sys
from dotenv import load_dotenv
load_dotenv()

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️ WARN"

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# =========================================================
# TEST 1: Environment Variables
# =========================================================
separator("TEST 1: Environment Variables")

env_checks = {
    "DATABASE_URL": os.getenv("DATABASE_URL"),
    "CLOUDINARY_CLOUD_NAME": os.getenv("CLOUDINARY_CLOUD_NAME"),
    "CLOUDINARY_API_KEY": os.getenv("CLOUDINARY_API_KEY"),
    "CLOUDINARY_API_SECRET": os.getenv("CLOUDINARY_API_SECRET"),
    "DRIVE_DATABASE_FOLDER_ID": os.getenv("DRIVE_DATABASE_FOLDER_ID"),
    "DRIVE_PDF_FOLDER_ID": os.getenv("DRIVE_PDF_FOLDER_ID"),
    "SUPABASE_URL": os.getenv("SUPABASE_URL"),
    "SUPABASE_KEY": os.getenv("SUPABASE_KEY"),
}

for key, val in env_checks.items():
    if val and val not in ("YOUR_DB_FOLDER_ID", "YOUR_PDF_FOLDER_ID"):
        # Mask sensitive values
        masked = val[:8] + "..." if len(val) > 12 else val
        print(f"  {PASS} {key} = {masked}")
    else:
        print(f"  {FAIL} {key} is NOT SET or has placeholder value")

# =========================================================
# TEST 2: Google Drive Auth Files
# =========================================================
separator("TEST 2: Google Drive Auth Files")

if os.path.exists("credentials.json"):
    print(f"  {PASS} credentials.json found")
else:
    print(f"  {FAIL} credentials.json NOT found (needed for OAuth flow)")

if os.path.exists("token.json"):
    print(f"  {PASS} token.json found (already authenticated)")
else:
    print(f"  {WARN} token.json NOT found (will be created on first auth)")

# =========================================================
# TEST 3: Cloudinary Connection & PDF Listing
# =========================================================
separator("TEST 3: Cloudinary Connection & PDF Listing")

try:
    import cloudinary
    from cloudinary.api import resources

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )

    # Try fetching resources with the configured prefix
    res = resources(
        type="upload",
        resource_type="raw",
        prefix="eduelevate/pdfs",
        max_results=10
    )

    pdf_list = res.get("resources", [])
    print(f"  {PASS} Cloudinary connected successfully!")
    print(f"  Found {len(pdf_list)} PDFs under 'eduelevate/pdfs' prefix")

    if pdf_list:
        for f in pdf_list[:5]:
            print(f"    📄 {f['public_id']}")
        if len(pdf_list) > 5:
            print(f"    ... and {len(pdf_list) - 5} more")
    else:
        # Try listing ALL raw resources to find the actual prefix
        print(f"\n  {WARN} No PDFs found with prefix 'eduelevate/pdfs'. Searching all raw uploads...")
        res_all = resources(
            type="upload",
            resource_type="raw",
            max_results=20
        )
        all_raw = res_all.get("resources", [])
        if all_raw:
            print(f"  Found {len(all_raw)} raw resources total:")
            prefixes = set()
            for f in all_raw:
                pid = f['public_id']
                prefix = "/".join(pid.split("/")[:-1]) if "/" in pid else "(root)"
                prefixes.add(prefix)
                print(f"    📄 {pid}")
            print(f"\n  Detected prefixes: {', '.join(prefixes)}")
            print(f"  → Update auto_backup.py prefix to match one of these!")
        else:
            print(f"  No raw resources found at all in Cloudinary.")
            
        # Also check image resources (profile photos are images, not raw)
        print(f"\n  Checking image uploads too...")
        res_img = resources(
            type="upload",
            resource_type="image",
            max_results=10
        )
        img_list = res_img.get("resources", [])
        if img_list:
            print(f"  Found {len(img_list)} image resources:")
            for f in img_list[:5]:
                print(f"    🖼️  {f['public_id']}")

except ImportError:
    print(f"  {FAIL} 'cloudinary' package not installed. Run: pip install cloudinary")
except Exception as e:
    print(f"  {FAIL} Cloudinary error: {e}")

# =========================================================
# TEST 4: Database Connection (pg_dump availability)
# =========================================================
separator("TEST 4: Database Tools")

import subprocess
try:
    result = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"  {PASS} pg_dump available: {result.stdout.strip()}")
    else:
        print(f"  {FAIL} pg_dump returned error: {result.stderr.strip()}")
except FileNotFoundError:
    print(f"  {WARN} pg_dump NOT found on PATH (needed for database backup)")
    print(f"  Install PostgreSQL client tools or add them to PATH")
except Exception as e:
    print(f"  {FAIL} Error checking pg_dump: {e}")

# =========================================================
# TEST 5: Supabase Connection (for backup_pdfs.py)
# =========================================================
separator("TEST 5: Supabase Connection (backup_pdfs.py path)")

try:
    from supabase import create_client
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if supabase_url and supabase_key:
        client = create_client(supabase_url, supabase_key)
        files = client.storage.from_("calicutadminpanelpdf").list("")
        real_files = [f for f in files if f['name'] != '.emptyFolderPlaceholder']
        print(f"  {PASS} Supabase connected! Found {len(real_files)} PDFs in bucket")
        for f in real_files[:5]:
            print(f"    📄 {f['name']} ({f.get('metadata', {}).get('size', '?')} bytes)")
        if len(real_files) > 5:
            print(f"    ... and {len(real_files) - 5} more")
    else:
        print(f"  {FAIL} SUPABASE_URL or SUPABASE_KEY not set")
except ImportError:
    print(f"  {WARN} 'supabase' package not installed. Run: pip install supabase")
except Exception as e:
    print(f"  {FAIL} Supabase error: {e}")

# =========================================================
# SUMMARY
# =========================================================
separator("PIPELINE SUMMARY")

has_gdrive = os.path.exists("credentials.json")
has_cloudinary = all([os.getenv("CLOUDINARY_CLOUD_NAME"), os.getenv("CLOUDINARY_API_KEY"), os.getenv("CLOUDINARY_API_SECRET")])
has_db_url = bool(os.getenv("DATABASE_URL"))
has_drive_folders = os.getenv("DRIVE_DATABASE_FOLDER_ID") not in (None, "YOUR_DB_FOLDER_ID")

print(f"""
  Database URL:        {'✅' if has_db_url else '❌'} {'Set' if has_db_url else 'Missing'}
  Cloudinary Creds:    {'✅' if has_cloudinary else '❌'} {'Set' if has_cloudinary else 'Missing'}
  Google Drive Auth:   {'✅' if has_gdrive else '❌'} {'credentials.json ' + ('found' if has_gdrive else 'MISSING')}
  Drive Folder IDs:    {'✅' if has_drive_folders else '❌'} {'Set' if has_drive_folders else 'Missing/Placeholder'}

  OVERALL STATUS:      {'🟢 READY' if all([has_gdrive, has_cloudinary, has_db_url, has_drive_folders]) else '🔴 NOT READY — see failures above'}
""")

if not has_gdrive:
    print("""  📋 NEXT STEPS TO COMPLETE SETUP:
  1. Go to https://console.cloud.google.com/apis/credentials
  2. Create OAuth 2.0 Client ID (Desktop app)
  3. Download → save as 'credentials.json' in project root
  4. Create Google Drive folders & set IDs in .env:
     DRIVE_DATABASE_FOLDER_ID=<id>
     DRIVE_PDF_FOLDER_ID=<id>
  5. Run: python auto_backup.py (will open browser for OAuth)
""")
