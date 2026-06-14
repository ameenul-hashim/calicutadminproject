from PIL import Image
import io
import os
import gc
import logging
from django.core.files.base import ContentFile
from pillow_heif import register_heif_opener
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)

register_heif_opener()

def optimize_image_internally(img, max_width=1200, quality=80):
    if img.width > max_width:
        ratio = max_width / float(img.width)
        new_height = int(float(img.height) * float(ratio))
        img = img.resize((max_width, new_height), Image.LANCZOS)
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    output_io = io.BytesIO()
    img.save(output_io, format='JPEG', quality=quality, optimize=True)
    output_io.seek(0)
    return output_io

def convert_image_to_pdf(image_source):
    """Convert an uploaded image file to a PDF. Only accepts file objects — never URLs."""
    try:
        img = Image.open(image_source)
        filename = getattr(image_source, 'name', 'verification_upload.jpg')

        logger.info(f"PDF Pipeline: Processing {filename} ({img.width}x{img.height})")

        MAX_SIZE_BYTES = 200 * 1024
        current_quality = 85
        current_max_width = 1200
        final_pdf_buffer = None
        pdf_buffer = None
        optimized_jpg_io = None

        for attempt in range(3):
            if optimized_jpg_io:
                try:
                    optimized_jpg_io.close()
                except Exception:
                    pass
            optimized_jpg_io = optimize_image_internally(img, max_width=current_max_width, quality=current_quality)

            if pdf_buffer:
                try:
                    pdf_buffer.close()
                except Exception:
                    pass
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            width, height = A4
            img_reader = ImageReader(optimized_jpg_io)
            img_w, img_h = img_reader.getSize()
            aspect = img_h / float(img_w)
            display_w = width - 40
            display_h = display_w * aspect
            if display_h > (height - 40):
                display_h = height - 40
                display_w = display_h / aspect
            x_centered = (width - display_w) / 2
            y_centered = (height - display_h) / 2
            c.drawImage(img_reader, x_centered, y_centered, width=display_w, height=display_h)
            c.showPage()
            c.save()
            pdf_size = pdf_buffer.tell()
            logger.debug(f"PDF Stats Attempt {attempt+1}: Quality={current_quality}, Width={current_max_width}, Size={pdf_size/1024:.2f}KB")
            if pdf_size <= MAX_SIZE_BYTES:
                final_pdf_buffer = pdf_buffer
                pdf_buffer = None
                break
            current_quality -= 20
            current_max_width = int(current_max_width * 0.75)

        if not final_pdf_buffer:
            final_pdf_buffer = pdf_buffer
            pdf_buffer = None

        final_pdf_buffer.seek(0)
        base_name = os.path.splitext(os.path.basename(filename))[0]
        result = ContentFile(final_pdf_buffer.read(), name=f"{base_name}_verified.pdf")

        img.close()
        if optimized_jpg_io:
            try:
                optimized_jpg_io.close()
            except Exception:
                pass
        final_pdf_buffer.close()
        gc.collect()
        return result

    except Exception as e:
        import traceback
        logger.error(f"PDF PIPELINE ERROR: {str(e)}")
        logger.error(traceback.format_exc())
        return None
