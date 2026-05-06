import cloudinary.uploader
import cloudinary.api
from django.conf import settings

def upload_temp_image(image_file):
    """
    Uploads an image to Cloudinary temporarily.
    Returns the secure URL and public_id if successful, or (None, None) if failed.
    """
    try:
        # Use a temporary folder in Cloudinary
        result = cloudinary.uploader.upload(
            image_file,
            folder="temp_verifications/",
            resource_type="image"
        )
        return result.get('secure_url'), result.get('public_id')
    except Exception as e:
        print(f"❌ Cloudinary Temp Upload Error: {str(e)}")
        return None, None

def delete_temp_image(public_id):
    """
    Deletes an image from Cloudinary by its public_id.
    """
    try:
        if public_id:
            cloudinary.uploader.destroy(public_id)
            print(f"🗑️ Deleted temp image: {public_id}")
            return True
    except Exception as e:
        print(f"❌ Cloudinary Delete Error: {str(e)}")
    return False
