import cloudinary
import cloudinary.api
import os
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def list_others():
    try:
        for folder in ["samples", "media"]:
            print(f"\nListing folder: {folder}")
            resources = cloudinary.api.resources(type="upload", prefix=folder, max_results=500)
            print(f"Total found: {len(resources.get('resources', []))}")
            for res in resources.get('resources', []):
                print(f"- {res['public_id']} ({res['bytes']} bytes)")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    list_others()
