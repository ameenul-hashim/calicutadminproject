import cloudinary.uploader
import logging
from django.db import transaction
import magic

logger = logging.getLogger(__name__)

def validate_pdf(file):
    """
    Validates that a file is actually a PDF using magic numbers.
    """
    mime = magic.from_buffer(file.read(1024), mime=True)
    file.seek(0)

    if mime != "application/pdf":
        raise ValueError("Only valid PDF files are allowed")

def update_image(instance, new_image_file, folder="edustream/uploads"):
    """
    Safely updates an image in Cloudinary and the database model.
    """
    try:
        # STEP 1: Upload new image FIRST (fail-safe)
        upload_result = cloudinary.uploader.upload(
            new_image_file,
            folder=folder
        )

        new_url = upload_result.get("secure_url")
        new_public_id = upload_result.get("public_id")

        if not new_url or not new_public_id:
            logger.error("Cloudinary upload failed: Missing URL or public_id")
            return False

        # STEP 2: Delete old image ONLY after successful upload
        if getattr(instance, 'image_public_id', None):
            try:
                cloudinary.uploader.destroy(instance.image_public_id)
            except Exception as e:
                logger.error(f"Failed to delete old Cloudinary image {instance.image_public_id}: {e}")
                pass  # prevent crash if deletion fails

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
    Cleans up Cloudinary image when a model is deleted.
    """
    if getattr(instance, 'image_public_id', None):
        try:
            cloudinary.uploader.destroy(instance.image_public_id)
        except Exception as e:
            logger.error(f"Failed to delete Cloudinary image {instance.image_public_id}: {e}")
            pass


def upload_pdf(instance, pdf_file):
    """
    Uploads a PDF to Cloudinary securely using transaction logic.
    Sets status to PENDING.
    """
    try:
        validate_pdf(pdf_file)
        
        with transaction.atomic():
            result = cloudinary.uploader.upload(
                pdf_file,
                resource_type="raw",
                folder="edustream/pdfs"
            )
            
            instance.pdf_url = result.get("secure_url")
            instance.pdf_public_id = result.get("public_id")
            instance.status = "PENDING"
            instance.save()
            return True
    except ValueError as e:
        logger.error(f"Validation Error: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to upload PDF to Cloudinary: {e}")
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
    Rejects a user account and deletes their PDF from Cloudinary immediately.
    """
    if getattr(instance, 'pdf_public_id', None):
        try:
            cloudinary.uploader.destroy(
                instance.pdf_public_id,
                resource_type="raw"
            )
        except Exception as e:
            logger.error(f"Failed to delete Cloudinary PDF {instance.pdf_public_id}: {e}")
            pass

    instance.pdf_url = None
    instance.pdf_public_id = None
    instance.status = "REJECTED" 
    instance.save()
    logger.warning(f"ADMIN {admin_user.username} REJECTED USER {instance.id}")
