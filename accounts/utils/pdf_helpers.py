from PIL import Image
import io
import os
from django.core.files.base import ContentFile

def convert_image_to_pdf(image_file):
    """
    Converts an uploaded image (InMemoryUploadedFile) to a PDF ContentFile.
    Returns the ContentFile if successful, or None if failed.
    """
    try:
        # Load image
        img = Image.open(image_file)
        
        # Convert to RGB (required for PDF saving)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
            
        pdf_io = io.BytesIO()
        img.save(pdf_io, format='PDF', resolution=100.0)
        pdf_io.seek(0)
        
        # Generate safe PDF filename
        original_name = os.path.basename(image_file.name)
        name_without_ext = os.path.splitext(original_name)[0]
        pdf_filename = f"{name_without_ext}.pdf"
        
        return ContentFile(pdf_io.read(), name=pdf_filename)
    except Exception as e:
        print(f"❌ Image to PDF Conversion Error: {str(e)}")
        return None
