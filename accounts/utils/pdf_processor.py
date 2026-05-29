import os
import io
import mimetypes
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# To prevent hard crash if PyMuPDF not installed during testing
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF not installed, PDF processing will be skipped")

MAX_COMPRESSED_SIZE_MB = 10
MAX_COMPRESSED_SIZE_BYTES = MAX_COMPRESSED_SIZE_MB * 1024 * 1024

def validate_file(file_obj, filename, expected_type):
    """
    Validates MIME type, extension against expected CourseResource types.
    expected_type in ['PDF', 'DOCX', 'PPTX', 'XLSX', 'TXT']
    """
    mime_type, _ = mimetypes.guess_type(filename)
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    ALLOWED_MIMES = {
        'PDF': [('application/pdf', 'pdf')],
        'DOCX': [('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'docx'), ('application/msword', 'doc')],
        'PPTX': [('application/vnd.openxmlformats-officedocument.presentationml.presentation', 'pptx'), ('application/vnd.ms-powerpoint', 'ppt')],
        'XLSX': [('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'), ('application/vnd.ms-excel', 'xls')],
        'TXT': [('text/plain', 'txt')]
    }
    
    if expected_type not in ALLOWED_MIMES:
        raise ValueError("Unsupported resource type.")
        
    valid_configs = ALLOWED_MIMES[expected_type]
    
    is_valid = False
    for valid_mime, valid_ext in valid_configs:
        if mime_type == valid_mime and ext == valid_ext:
            is_valid = True
            break
            
    if not is_valid:
        raise ValueError(f"Invalid file format for selected category {expected_type}")
        
    return mime_type, ext

def process_pdf(file_bytes):
    """
    Compresses PDF and generates a thumbnail WebP.
    Returns: (compressed_bytes, webp_thumbnail_bytes)
    """
    if not PYMUPDF_AVAILABLE:
        # Fallback if no local C lib
        return file_bytes, None
        
    try:
        # Load PDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        
        # 1. Generate Thumbnail from first page
        thumbnail_bytes = None
        if len(doc) > 0:
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5)) # low res for thumb
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            thumb_io = io.BytesIO()
            # Compress WebP between 50-150KB generally via Quality 60
            img.save(thumb_io, format="WEBP", quality=60)
            thumbnail_bytes = thumb_io.getvalue()
            
        # 2. Compress PDF
        compressed_io = io.BytesIO()
        doc.save(compressed_io, garbage=4, deflate=True, clean=True)
        compressed_bytes = compressed_io.getvalue()
        
        doc.close()
        
        if len(compressed_bytes) > MAX_COMPRESSED_SIZE_BYTES:
            raise ValueError(f"Compressed PDF exceeds absolute {MAX_COMPRESSED_SIZE_MB}MB safety limit.")
            
        return compressed_bytes, thumbnail_bytes
        
    except Exception as e:
        logger.error(f"PDF Processing Error: {e}")
        raise ValueError(f"Failed to process PDF document: {str(e)}")

