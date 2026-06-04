import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

def test_cloudinary():
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET")
    )
    print(f"--- Cloudinary ({os.getenv('CLOUDINARY_CLOUD_NAME')}) ---")
    try:
        res = cloudinary.api.ping()
        print(f"Connection OK: {res}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_cloudinary()
