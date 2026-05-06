import cloudinary.uploader
import cloudinary.api
from django.conf import settings

def upload_temp_image(image_file):
    """
    Uploads an image to Cloudinary temporarily.
    Returns the secure URL and public_id if successful, or (None, None) if failed.
    """
    try:
        import uuid
        unique_id = f"temp_{uuid.uuid4()}"
        
        # Use a temporary folder in Cloudinary
        result = cloudinary.uploader.upload(
            image_file,
            public_id=unique_id,
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

def delete_image(instance):
    """
    General cleanup function for models using Cloudinary (CustomUser, Course, etc.).
    Checks for image_public_id and pdf_public_id and deletes them.
    """
    try:
        # 1. Clean Main Image (User Profile or Course Thumbnail)
        if hasattr(instance, 'image_public_id') and instance.image_public_id:
            cloudinary.uploader.destroy(instance.image_public_id)
            print(f"🗑️ Deleted Cloudinary Image: {instance.image_public_id}")

        # 2. Clean Legacy PDF Proof from Cloudinary if exists
        if hasattr(instance, 'pdf_public_id') and instance.pdf_public_id:
            cloudinary.uploader.destroy(instance.pdf_public_id, resource_type="raw")
            print(f"🗑️ Deleted Legacy Cloudinary PDF: {instance.pdf_public_id}")
            
        return True
    except Exception as e:
        print(f"❌ Cloudinary Cleanup Error: {str(e)}")
        return False
