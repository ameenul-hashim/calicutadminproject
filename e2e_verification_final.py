import os
import django
import time
import sys
import io

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
django.setup()

from accounts.models import CourseResource, Course, CustomUser
from accounts.utils.storage_manager import StorageManager
from accounts.utils.pdf_processor import validate_file, process_pdf
from django.utils import timezone
import threading

def run_e2e_proof():
    print("--- STARTING REAL-WORLD E2E VERIFICATION ---")
    
    try:
        # 1. Get Test Data
        course = Course.objects.filter(title='Test Course').first()
        admin = CustomUser.objects.filter(username='admin').first()
        if not course or not admin:
            print("Setup missing. Course or Admin not found.")
            return

        print(f"[OK] Found Test Course: {course.title}")
        
        # 2. Simulate Teacher Upload
        print("\nStep 1: Simulating Teacher Upload (PDF)...")
        with open('test_resource.pdf', 'rb') as f:
            file_bytes = f.read()
        
        # Process PDF
        mime_type, ext = validate_file(io.BytesIO(file_bytes), 'test_resource.pdf', 'PDF')
        compressed_bytes, thumbnail_bytes = process_pdf(file_bytes)
        
        # Upload to Supabase
        dest_path = f"resources/{course.uid}/e2e_test_{int(time.time())}.pdf"
        fb_path = StorageManager.upload_to_supabase_storage(compressed_bytes, dest_path, mime_type)
        print(f"[OK] Physically uploaded to Supabase: {fb_path}")

        # Upload Thumbnail to Cloudinary
        thumb_path = None
        thumb_pid = None
        if thumbnail_bytes:
            from accounts.utils.cloudinary_helpers import upload_image_only
            thumb_path, thumb_pid = upload_image_only(thumbnail_bytes, folder="Neo Learner/e2e_tests")
            print(f"[OK] Physically uploaded Thumbnail to Cloudinary: {thumb_path}")

        # create Record
        resource = CourseResource.objects.create(
            course=course,
            title='E2E Verification Resource',
            category='ENGLISH',
            resource_type='PDF',
            firebase_file_path=fb_path,
            thumbnail_path=thumb_path,
            thumbnail_public_id=thumb_pid,
            mime_type=mime_type,
            file_extension=ext,
            original_size=len(file_bytes),
            compressed_size=len(compressed_bytes),
            status='PENDING'
        )
        print(f"[OK] Database record created: ID {resource.id}, Status {resource.status}")

        # 3. Simulate Admin Approval & Backup
        print("\nStep 2: Simulating Admin Approval & Backup...")
        resource.status = 'APPROVED'
        resource.is_approved = True
        resource.approved_by = admin
        resource.approved_at = timezone.now()
        resource.save()
        print(f"[OK] Resource set to APPROVED by {admin.username}")

        # Trigger Backup Logic (Synthetically for verification)
        print("Launching Background Backup Logic...")
        StorageManager.backup_to_google_drive(resource.id)
        
        # Reload resource
        resource.refresh_from_db()
        print(f"BACKUP RESULT:")
        print(f"   Status: {resource.backup_status}")
        print(f"   Drive File ID: {resource.backup_file_path}")

        if resource.backup_status == 'SUCCESS' and resource.backup_file_path:
            print("SUCCESS: GOOGLE DRIVE VERIFICATION SUCCESS!")
        else:
            print("FAILURE: GOOGLE DRIVE BACKUP FAILED.")

        # 4. Access Verification
        print("\nStep 3: Verifying Student Access...")
        signed_url = resource.get_signed_url()
        if signed_url and 'token=' in signed_url:
            print(f"[OK] Signed URL Generated (Expires in 2h): {signed_url[:100]}...")
        else:
            print("Signed URL Generation Failed.")

        # 5. Cleanup Verification
        print("\nStep 4: Simulating Resource Deletion...")
        r_id = resource.id
        fb_p = resource.firebase_file_path
        t_pid = resource.thumbnail_public_id
        
        # Soft delete simulation matches delete_resource view logic
        resource.is_deleted = True
        resource.deleted_at = timezone.now()
        resource.save()
        
        StorageManager.delete_from_supabase_storage(fb_p)
        print(f"[OK] Physically deleted from Supabase: {fb_p}")
        
        if t_pid:
            import cloudinary.uploader
            cloudinary.uploader.destroy(t_pid)
            print(f"[OK] Physically deleted Thumbnail from Cloudinary: {t_pid}")
            
        print("\n--- E2E VERIFICATION COMPLETED ---")
        
    except Exception as e:
        print(f"CRITICAL ERROR DURING VERIFICATION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_e2e_proof()



