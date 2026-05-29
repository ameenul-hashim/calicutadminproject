import os
import io
import uuid
import logging
from datetime import timedelta
import firebase_admin
from firebase_admin import credentials, storage

logger = logging.getLogger(__name__)

# Initialize Firebase via config
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_JSON")
FIREBASE_BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET")

firebase_app = None
if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            firebase_app = firebase_admin.initialize_app(cred, {
                'storageBucket': FIREBASE_BUCKET_NAME
            })
        else:
            firebase_app = firebase_admin.get_app()
    except Exception as e:
        logger.error(f"Failed to init Firebase Admin: {e}")

class StorageManager:
    @staticmethod
    def upload_to_firebase(file_bytes, destination_path, content_type):
        """Uploads a file to Firebase Storage"""
        if not firebase_app or not FIREBASE_BUCKET_NAME:
            logger.warning("Firebase not configured. Bypassing upload.")
            return destination_path
            
        try:
            bucket = storage.bucket()
            blob = bucket.blob(destination_path)
            blob.upload_from_string(file_bytes, content_type=content_type)
            return destination_path
        except Exception as e:
            logger.error(f"Firebase Upload Error: {e}")
            raise ValueError("Cloud storage primary upload failed.")

    @staticmethod
    def upload_to_drive(file_bytes, filename):
        """Mock/Stub for Google Drive Uploads until Drive creds are wired"""
        # In actual prod, uses google-api-python-client with Service Account
        logger.info(f"Uploading {filename} to Google Drive backup...")
        # Stub returns a dummy ID/path
        return f"gdrive_backup/{filename}"

    @staticmethod
    def delete_from_firebase(file_path):
        """Permanently delete file from Firebase"""
        if not firebase_app or not FIREBASE_BUCKET_NAME or not file_path:
            return
            
        try:
            bucket = storage.bucket()
            blob = bucket.blob(file_path)
            if blob.exists():
                blob.delete()
        except Exception as e:
            logger.error(f"Firebase Delete Error for {file_path}: {e}")

    @staticmethod
    def generate_signed_url(file_path, expiration=None):
        """Generates a short-lived temporary streaming URL. Expiration can be timedelta or int (minutes)."""
        if not firebase_app or not FIREBASE_BUCKET_NAME or not file_path:
            # Security: never expose raw storage paths — return None so caller can show a proper error
            return None
            
        try:
            bucket = storage.bucket()
            blob = bucket.blob(file_path)
            if not blob.exists():
                return None
            
            if expiration is None:
                expiration = timedelta(minutes=30)
            elif isinstance(expiration, int):
                expiration = timedelta(minutes=expiration)
                
            return blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET"
            )
        except Exception as e:
            logger.error(f"Firebase Signed URL generation failed for {file_path}: {e}")
            return None
