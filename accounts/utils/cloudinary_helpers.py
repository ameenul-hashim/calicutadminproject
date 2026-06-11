import cloudinary.uploader
import cloudinary.api
import cloudinary
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# Explicitly configure cloudinary for use in helper functions
if hasattr(settings, 'CLOUDINARY_STORAGE'):
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_STORAGE.get('CLOUD_NAME'),
        api_key=settings.CLOUDINARY_STORAGE.get('API_KEY'),
        api_secret=settings.CLOUDINARY_STORAGE.get('API_SECRET'),
        secure=settings.CLOUDINARY_STORAGE.get('SECURE', True)
    )

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
        logger.error(f"Cloudinary Temp Upload Error: {str(e)}")
        return None, None

def delete_temp_image(public_id):
    """
    Deletes an image from Cloudinary by its public_id.
    """
    try:
        if public_id:
            cloudinary.uploader.destroy(public_id)
            logger.info(f"Deleted temp image: {public_id}")
            return True
    except Exception as e:
        logger.error(f"Cloudinary Delete Error: {str(e)}")
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
            logger.info(f"Deleted Cloudinary Image: {instance.image_public_id}")

        # 2. Clean Legacy PDF Proof from Cloudinary if exists
        if hasattr(instance, 'pdf_public_id') and instance.pdf_public_id:
            cloudinary.uploader.destroy(instance.pdf_public_id, resource_type="raw")
            logger.info(f"Deleted Legacy Cloudinary PDF: {instance.pdf_public_id}")
            
        return True
    except Exception as e:
        logger.error(f"Cloudinary Cleanup Error: {str(e)}")
        return False

def upload_image_only(image_file, folder="Neo Learner/uploads"):
    """
    Uploads an image to Cloudinary and returns (secure_url, public_id)
    without updating or saving any model instances directly.
    """
    try:
        if not image_file:
            return None, None
        import uuid
        unique_id = f"img_{uuid.uuid4()}"
        logger.info(f"Uploading image only to Cloudinary (Folder: {folder})...")
        result = cloudinary.uploader.upload(
            image_file,
            public_id=unique_id,
            folder=folder,
            resource_type="image",
            quality="auto",
            fetch_format="auto"
        )
        return result.get('secure_url'), result.get('public_id')
    except Exception as e:
        logger.error(f"Cloudinary Upload Only Error: {str(e)}")
        return None, None

def update_image(instance, image_file, folder="Neo Learner/uploads"):
    """
    Uploads a new image and updates the model instance.
    Deletes the old image from Cloudinary if it exists.
    Robust for mobile uploads (large files, HEIC format).
    """
    try:
        if not image_file:
            logger.warning(f"No image file provided for {instance}")
            return False

        # 0. Handle Lazy Objects (e.g. request.user)
        from django.utils.functional import SimpleLazyObject
        if isinstance(instance, SimpleLazyObject):
            from django.contrib.auth import get_user_model
            instance = get_user_model().objects.get(pk=instance.pk)
            logger.info(f"Resolved LazyObject to real user: {instance.username}")

        # 1. Cleanup Old Image first
        if hasattr(instance, 'image_public_id') and instance.image_public_id:
            try:
                cloudinary.uploader.destroy(instance.image_public_id)
                logger.info(f"Cleaned up old image: {instance.image_public_id}")
            except Exception as cleanup_err:
                logger.warning(f"Non-critical cleanup error: {str(cleanup_err)}")

        # 2. Upload New Image
        import uuid
        unique_id = f"img_{uuid.uuid4()}"
        
        logger.info(f"Uploading image to Cloudinary (Folder: {folder})...")
        result = cloudinary.uploader.upload(
            image_file,
            public_id=unique_id,
            folder=folder,
            resource_type="image",
            quality="auto",
            fetch_format="auto"
        )
        
        # 3. Update Instance
        secure_url = result.get('secure_url')
        public_id = result.get('public_id')

        if secure_url and public_id:
            # Update modern Cloudinary fields
            instance.image = secure_url
            instance.image_public_id = public_id
            
            # IMPORTANT: Clear legacy fields to ensure 'avatar_url' and 'thumbnail_url' 
            # properties ALWAYS prefer the new Cloudinary URL.
            if hasattr(instance, 'profile_photo') and instance.profile_photo:
                instance.profile_photo = None
            if hasattr(instance, 'thumbnail') and instance.thumbnail:
                instance.thumbnail = None
            
            # Save the entire instance to ensure database persistence
            instance.save()

            logger.info(f"Successfully updated Image for {instance}")
            logger.debug(f"Image URL: {instance.image}")
            return True
        else:
            logger.error(f"Cloudinary returned empty result for {instance}")
            return False

    except Exception as e:
        import traceback
        logger.error(f"Cloudinary Update Error: {str(e)}")
        logger.error(traceback.format_exc())
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
        logger.info(f"User {user.username} approved.")
        return True
    except Exception as e:
        logger.error(f"approve_user Error: {str(e)}")
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
                logger.info(f"Deleted Cloudinary image: {user.image_public_id}")
            except Exception as e:
                logger.warning(f"Could not delete Cloudinary image: {e}")

        if hasattr(user, 'pdf_public_id') and user.pdf_public_id:
            try:
                cloudinary.uploader.destroy(user.pdf_public_id, resource_type="image")
                logger.info(f"Deleted Cloudinary proof: {user.pdf_public_id}")
            except Exception as e:
                logger.warning(f"Could not delete Cloudinary proof image: {e}")

        # 2. Delete Supabase PDF if exists
        if hasattr(user, 'pdf_path') and user.pdf_path:
            try:
                from accounts.utils.supabase_storage import delete_pdf
                delete_pdf(user.pdf_path)
                logger.info(f"Deleted Supabase PDF: {user.pdf_path}")
            except Exception as e:
                logger.warning(f"Could not delete Supabase PDF: {e}")

        # 3. Permanently delete user record
        username = user.username
        user.delete()
        logger.info(f"User {username} permanently deleted.")
        return True
    except Exception as e:
        logger.error(f"reject_user_and_clean Error: {str(e)}")
        return False
