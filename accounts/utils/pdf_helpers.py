from PIL import Image
import io
import os
import requests
from django.core.files.base import ContentFile
from pillow_heif import register_heif_opener
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

# Enable HEIC support for Pillow to handle iPhone uploads
register_heif_opener()

def optimize_image_internally(img, max_width=1200, quality=80):
    """
    Intelligently resizes, removes metadata, and compresses an image.
    Returns a BytesIO object containing the optimized JPEG data.
    """
    # 1. Resize intelligently if too large (Banking KYC standard: 1000px-1200px)
    if img.width > max_width:
        ratio = max_width / float(img.width)
        new_height = int(float(img.height) * float(ratio))
        img = img.resize((max_width, new_height), Image.LANCZOS)
    
    # 2. Mode Normalization & Metadata Removal
    # Converting to RGB and saving as JPEG effectively strips EXIF and Alpha channels
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    
    # 3. Save to memory as optimized JPEG
    output_io = io.BytesIO()
    img.save(output_io, format='JPEG', quality=quality, optimize=True)
    output_io.seek(0)
    return output_io

def convert_image_to_pdf(image_source):
    """
    Professional PDF generation pipeline for verification documents.
    - Supports: .jpg, .jpeg, .png, .heic
    - Logic: Adaptive re-compression to hit < 200KB target.
    - Output: Standardized professional PDF for admin review.
    """
    try:
        # 1. Load Image from URL or File
        if isinstance(image_source, str) and (image_source.startswith('http://') or image_source.startswith('https://')):
            response = requests.get(image_source, timeout=15)
            img = Image.open(io.BytesIO(response.content))
            filename = os.path.basename(image_source).split('?')[0]
        else:
            img = Image.open(image_source)
            filename = getattr(image_source, 'name', 'verification_upload.jpg')

        print(f"[PDF] Pipeline: Processing {filename} ({img.width}x{img.height})")

        # 2. Adaptive Optimization Loop
        # Goal: < 200KB (Target 180KB)
        MAX_SIZE_BYTES = 200 * 1024
        
        current_quality = 85
        current_max_width = 1200
        final_pdf_buffer = None
        
        # Max 3 attempts with decreasing quality/resolution
        for attempt in range(3):
            # A. Compress image in-memory
            optimized_jpg_io = optimize_image_internally(img, max_width=current_max_width, quality=current_quality)
            
            # B. Generate Professional PDF using ReportLab
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            width, height = A4
            
            # Draw the image to fit the page while maintaining aspect ratio
            img_reader = ImageReader(optimized_jpg_io)
            img_w, img_h = img_reader.getSize()
            
            aspect = img_h / float(img_w)
            display_w = width - 40  # 20pt margins
            display_h = display_w * aspect
            
            # If image height exceeds page, scale down
            if display_h > (height - 40):
                display_h = height - 40
                display_w = display_h / aspect
                
            # Center on page
            x_centered = (width - display_w) / 2
            y_centered = (height - display_h) / 2
            
            c.drawImage(img_reader, x_centered, y_centered, width=display_w, height=display_h)
            c.showPage()
            c.save()
            
            pdf_size = pdf_buffer.tell()
            print(f"[STATS] Attempt {attempt+1}: Quality={current_quality}, Width={current_max_width}, Size={pdf_size/1024:.2f}KB")
            
            if pdf_size <= MAX_SIZE_BYTES:
                final_pdf_buffer = pdf_buffer
                break
            
            # Adjust parameters for next attempt if too large
            current_quality -= 20
            current_max_width = int(current_max_width * 0.75)

        if not final_pdf_buffer:
            final_pdf_buffer = pdf_buffer # Use the last one anyway

        final_pdf_buffer.seek(0)
        
        # 3. Return as ContentFile for Django
        base_name = os.path.splitext(os.path.basename(filename))[0]
        return ContentFile(final_pdf_buffer.read(), name=f"{base_name}_verified.pdf")

    except Exception as e:
        import traceback
        print(f"[ERROR] PDF PIPELINE ERROR: {str(e)}")
        print(traceback.format_exc())
        return None
