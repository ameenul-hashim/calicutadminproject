from PIL import Image
import io
import os
from django.core.files.base import ContentFile

import requests

def convert_image_to_pdf(image_source):
    """
    Hardened conversion of uploaded images or Cloudinary URLs to PDF.
    Supports resizing for mobile optimization and strict RGB conversion.
    Targets ~200KB final size.
    """
    try:
        # 1. Load image (handle both file objects and URLs)
        if isinstance(image_source, str) and (image_source.startswith('http://') or image_source.startswith('https://')):
            response = requests.get(image_source, timeout=10)
            img = Image.open(io.BytesIO(response.content))
            filename = os.path.basename(image_source).split('?')[0]
        else:
            img = Image.open(image_source)
            filename = image_source.name

        print(f"📸 Image Conversion Start: {filename} | Mode: {img.mode} | Size: {img.size}")
        
        # 2. Resizing for Mobile Optimization (Targeting small file size)
        # 1280px is plenty for documents and keeps size down
        max_size = 1280
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            print(f"📏 Optimized size to: {img.size}")

        # 3. Mode Normalization (Strict RGB for PDF)
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
            
        # 4. Conversion to PDF with Compression (Targeting ~200KB)
        pdf_io = io.BytesIO()
        # Using a resolution and quality balance to hit the 200KB goal
        img.save(pdf_io, format='PDF', quality=75, optimize=True, resolution=72.0)
        pdf_io.seek(0)
        
        # 5. Generate Safe Filename
        name_without_ext = os.path.splitext(os.path.basename(filename))[0]
        pdf_filename = f"{name_without_ext}.pdf"
        
        return ContentFile(pdf_io.read(), name=pdf_filename)
    except Exception as e:
        import traceback
        print(f"❌ CRITICAL IMAGE CONVERSION FAILURE: {str(e)}")
        print(traceback.format_exc())
        return None
