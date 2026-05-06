from PIL import Image
import io
import os
from django.core.files.base import ContentFile

def convert_image_to_pdf(image_file):
    """
    Hardened conversion of uploaded images to PDF.
    Supports resizing for mobile optimization and strict RGB conversion.
    """
    try:
        # 1. Load image and basic logging
        img = Image.open(image_file)
        print(f"📸 Image Conversion: {image_file.name} | Mode: {img.mode} | Size: {img.size}")
        
        # 2. Resizing for Mobile Optimization (Max 1600px width/height)
        max_size = 1600
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            print(f"📏 Resized to: {img.size}")

        # 3. Mode Normalization (Strict RGB for PDF)
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
            
        # 4. Conversion to PDF with Compression
        pdf_io = io.BytesIO()
        img.save(pdf_io, format='PDF', quality=85, optimize=True)
        pdf_io.seek(0)
        
        # 5. Generate Safe Filename
        name_without_ext = os.path.splitext(os.path.basename(image_file.name))[0]
        pdf_filename = f"{name_without_ext}.pdf"
        
        return ContentFile(pdf_io.read(), name=pdf_filename)
    except Exception as e:
        import traceback
        print(f"❌ CRITICAL IMAGE CONVERSION FAILURE: {str(e)}")
        print(traceback.format_exc())
        return None
