import sys, os
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')

import django
django.setup()

from supabase import create_client

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
print(f"URL: {url}")
print(f"Key set: {bool(key)}")

if url and key:
    client = create_client(url, key)
    buckets = client.storage.list_buckets()
    print("Existing buckets:")
    for b in buckets:
        print(f"  - {b.name} (id: {b.id})")
    print(f"Default bucket env: {os.getenv('SUPABASE_BUCKET', 'calicutadminpanelpdf')}")
