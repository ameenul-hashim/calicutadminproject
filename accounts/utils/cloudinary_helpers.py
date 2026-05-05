import cloudinary.uploader
import logging
from django.db import transaction
from .supabase_storage import (
    upload_pdf as supabase_upload, 
    delete_pdf as supabase_delete,
    validate_pdf as supabase_validate
)

logger = logging.getLogger(__name__)

def validate_pdf(file):
    """
    Validates that a file is actually a PDF using the centralized validator.
    """
    try:
        content = file.read()
        file.seek(0)
        supabase_validate(content, getattr(file, 'name', None))
    except Exception as e:
        raise ValueError(str(e))

def update_image(instance, new_image_file, folder="edustream/profiles"):
    """
    Safely updates an image in Cloudinary and the database model.
    Ensures old images are deleted to save space.
    """
    try:
        # STEP 1: Delete old image if it exists to ensure clean replacement
        old_public_id = getattr(instance, 'image_public_id', None)
        if old_public_id:
            try:
                cloudinary.uploader.destroy(old_public_id)
                logger.info(f"Deleted old image: {old_public_id}")
            except Exception as e:
                logger.warning(f"Failed to delete old Cloudinary image {old_public_id}: {e}")

        # STEP 2: Upload new image
        upload_result = cloudinary.uploader.upload(
            new_image_file,
            folder=folder,
            resource_type="image"
        )

        new_url = upload_result.get("secure_url")
        new_public_id = upload_result.get("public_id")

        if not new_url or not new_public_id:
            logger.error("Cloudinary upload failed: Missing URL or public_id")
            return False

        # STEP 3: Update model fields
        instance.image = new_url
        instance.image_public_id = new_public_id
        
        # Clear legacy local fields to prevent confusion/local storage usage
        if hasattr(instance, 'profile_photo'):
            instance.profile_photo = None
        if hasattr(instance, 'thumbnail'):
            instance.thumbnail = None
            
        instance.save()
        logger.info(f"Successfully updated image for {instance} to {new_url}")
        return True

    except Exception as e:
        logger.error(f"Error in update_image: {e}")
        return False

    except Exception as e:
        logger.error(f"Error in update_image: {e}")
        return False

def delete_image(instance):
    """
    CLEANUP DISABLED: Images are preserved permanently even if model is deleted.
    """
    logger.info(f"PERMANENT DATA POLICY: Preserving image {getattr(instance, 'image_public_id', 'unknown')}")
    pass

def approve_user(instance, admin_user):
    """
    Approves a user account and keeps their PDF.
    """
    instance.status = "ACTIVE" # Application uses ACTIVE for approved users
    instance.save()
    logger.info(f"ADMIN {admin_user.username} APPROVED USER {instance.id}")

def reject_user(instance, admin_user):
    """
    Rejects a user account.
    NO-DELETE POLICY: PDF is preserved in Supabase even if user is rejected.
    """
    # if instance.pdf_path:
    #     supabase_delete(instance.pdf_path)

    # Note: We keep pdf_path to ensure the file remains linked for admin review later
    instance.status = "REJECTED" 
    instance.save()
    logger.warning(f"ADMIN {admin_user.username} REJECTED USER {instance.id} (Data Preserved)")
