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

def update_image(instance, new_image_file, folder="edustream/uploads"):
    """
    Safely updates an image in Cloudinary and the database model.
    NO-DELETE POLICY: Old images are kept in Cloudinary for archival purposes.
    """
    try:
        # STEP 1: Upload new image
        upload_result = cloudinary.uploader.upload(
            new_image_file,
            folder=folder
        )

        new_url = upload_result.get("secure_url")
        new_public_id = upload_result.get("public_id")

        if not new_url or not new_public_id:
            logger.error("Cloudinary upload failed: Missing URL or public_id")
            return False

        # STEP 2: NO-DELETE: Old image is NOT destroyed.
        # if getattr(instance, 'image_public_id', None):
        #     try:
        #         cloudinary.uploader.destroy(instance.image_public_id)
        #     except Exception as e:
        #         logger.error(f"Failed to delete old Cloudinary image {instance.image_public_id}: {e}")

        # STEP 3: Save new values
        instance.image = new_url
        instance.image_public_id = new_public_id
        instance.save()
        return True

    except Exception as e:
        logger.error(f"Error in update_image: {e}")
        return False

def delete_image(instance):
    """
    CLEANUP DISABLED: Images are preserved permanently even if model is deleted.
    """
    logger.info(f"PERMANENT DATA POLICY: Preserving image {getattr(instance, 'image_public_id', 'unknown')}")
    pass


def upload_pdf(instance, pdf_file):
    """
    Uploads a PDF to Supabase Storage securely.
    Sets status to PENDING.
    """
    try:
        # Validate PDF content
        content = pdf_file.read()
        pdf_file.seek(0)
        validate_pdf(pdf_file)
        
        # Define destination path in Supabase (Aligned with documents/ folder)
        destination_path = f"documents/user_{instance.id}_{instance.uid}.pdf"
        
        with transaction.atomic():
            path = supabase_upload(destination_path, content, destination_path)
            if not path:
                raise Exception("Supabase upload failed")
            
            instance.pdf_path = path
            instance.status = "PENDING"
            instance.save()
            return True
    except ValueError as e:
        logger.error(f"Validation Error: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to upload PDF to Supabase: {e}")
        return False

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
