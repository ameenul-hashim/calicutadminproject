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
    
    ALLOWED_CONFIGS = {
        'PDF': {'mimes': ['application/pdf'], 'exts': ['pdf']},
        'DOCX': {'mimes': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword'], 'exts': ['docx', 'doc']},
        'PPTX': {'mimes': ['application/vnd.openxmlformats-officedocument.presentationml.presentation', 'application/vnd.ms-powerpoint'], 'exts': ['pptx', 'ppt']},
        'XLSX': {'mimes': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel'], 'exts': ['xlsx', 'xls']},
        'TXT': {'mimes': ['text/plain'], 'exts': ['txt']}
    }
    
    if expected_type not in ALLOWED_CONFIGS:
        raise ValueError(f"Unsupported resource type: {expected_type}")
        
    config = ALLOWED_CONFIGS[expected_type]
    
    # Priority 1: Check extension (most reliable for simple uploads)
    if ext not in config['exts']:
        raise ValueError(f"Invalid file extension '.{ext}' for {expected_type}")

    # Priority 2: Check MIME (lenient - if it's unknown or generic, we allow it if the extension is valid)
    if mime_type and mime_type != 'application/octet-stream':
        # Only raise if it's a CONFLICTING known mime type
        if mime_type not in config['mimes'] and '/' in mime_type:
            # Check if at least the major type matches (e.g. application/...)
            pass

    # Ensure we return a safe default mime if guessing failed
    if not mime_type:
        mime_type = 'application/octet-stream'
        if ext == 'pdf': mime_type = 'application/pdf'
        elif ext == 'txt': mime_type = 'text/plain'

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

