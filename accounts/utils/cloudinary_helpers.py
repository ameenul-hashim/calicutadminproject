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

def update_image(instance, image_file, folder="edustream/uploads"):
    """
    Uploads a new image and updates the model instance.
    Deletes the old image from Cloudinary if it exists.
    """
    try:
        # 1. Cleanup Old Image first
        if hasattr(instance, 'image_public_id') and instance.image_public_id:
            cloudinary.uploader.destroy(instance.image_public_id)
            print(f"🗑️ Cleaned up old image: {instance.image_public_id}")

        # 2. Upload New Image
        import uuid
        unique_id = f"img_{uuid.uuid4()}"
        
        result = cloudinary.uploader.upload(
            image_file,
            public_id=unique_id,
            folder=folder,
            resource_type="image"
        )
        
        # 3. Update Instance
        instance.image = result.get('secure_url')
        instance.image_public_id = result.get('public_id')
        instance.save()
        
        print(f"✅ Updated Image for {instance}: {instance.image}")
        return True
    except Exception as e:
        print(f"❌ Cloudinary Update Error: {str(e)}")
        return False

def approve_user(user, approved_by=None):
    """
    Sets user status to ACTIVE and activates them.
    Called by the admin accept_user view.
    """
    try:
        user.status = 'ACTIVE'
        user.is_active = True
        if approved_by:
            user.approved_by = approved_by
        from django.utils import timezone
        user.approved_at = timezone.now()
        user.save()
        print(f"✅ User {user.username} approved.")
        return True
    except Exception as e:
        print(f"❌ approve_user Error: {str(e)}")
        return False

def reject_user_and_clean(user, rejected_by=None):
    """
    Permanently deletes a rejected user and cleans up their Cloudinary/Supabase files.
    Called by the admin decline_user view.
    """
    try:
        # 1. Delete Cloudinary images (profile photo + proof image)
        if hasattr(user, 'image_public_id') and user.image_public_id:
            try:
                cloudinary.uploader.destroy(user.image_public_id)
                print(f"🗑️ Deleted Cloudinary image: {user.image_public_id}")
            except Exception as e:
                print(f"⚠️ Could not delete Cloudinary image: {e}")

        if hasattr(user, 'pdf_public_id') and user.pdf_public_id:
            try:
                cloudinary.uploader.destroy(user.pdf_public_id, resource_type="image")
                print(f"🗑️ Deleted Cloudinary proof: {user.pdf_public_id}")
            except Exception as e:
                print(f"⚠️ Could not delete Cloudinary proof image: {e}")

        # 2. Delete Supabase PDF if exists
        if hasattr(user, 'pdf_path') and user.pdf_path:
            try:
                from accounts.utils.supabase_storage import delete_pdf
                delete_pdf(user.pdf_path)
                print(f"🗑️ Deleted Supabase PDF: {user.pdf_path}")
            except Exception as e:
                print(f"⚠️ Could not delete Supabase PDF: {e}")

        # 3. Permanently delete user record
        username = user.username
        user.delete()
        print(f"✅ User {username} permanently deleted.")
        return True
    except Exception as e:
        print(f"❌ reject_user_and_clean Error: {str(e)}")
        return False
