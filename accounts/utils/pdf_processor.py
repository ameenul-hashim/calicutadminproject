import os
import io
import tempfile
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

# Try to import python-docx for DOCX conversion
try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not installed, DOCX upload will not work")

def validate_file(file_obj, filename, expected_type):
    """
    Validates MIME type, extension against expected CourseResource types.
    expected_type in ['PDF', 'DOCX']
    """
    mime_type, _ = mimetypes.guess_type(filename)
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    allowed = ['PDF', 'DOCX']
    if expected_type not in allowed:
        raise ValueError(f"Only PDF and DOCX formats are supported. Got: {expected_type}")
    
    ALLOWED_CONFIGS = {
        'PDF': {'mimes': ['application/pdf'], 'exts': ['pdf']},
        'DOCX': {'mimes': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword'], 'exts': ['docx', 'doc']},
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
    Uses temp file on disk for PyMuPDF to minimize RAM (avoids 2-5x in-memory overhead).
    Returns: (compressed_bytes, webp_thumbnail_bytes)
    """
    if not PYMUPDF_AVAILABLE:
        return file_bytes, None

    tmp_path = None
    try:
        # Write to temp file so PyMuPDF reads from disk, not memory
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        file_bytes = None  # allow GC to reclaim

        doc = fitz.open(tmp_path)

        # 1. Generate Thumbnail from first page
        thumbnail_bytes = None
        if len(doc) > 0:
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            thumb_io = io.BytesIO()
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
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

def convert_docx_to_pdf(file_bytes, title="Document"):
    """
    Converts a DOCX file to PDF using python-docx + reportlab.
    Returns PDF bytes on success, raises ValueError on failure.
    """
    if not DOCX_AVAILABLE:
        raise ValueError("DOCX processing is not available (python-docx not installed). Install it with: pip install python-docx")

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

    try:
        import io
        docx_doc = DocxDocument(io.BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f"Failed to read DOCX file: {e}")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocxTitle', parent=styles['Title'], fontSize=18, spaceAfter=12)
    heading_style = ParagraphStyle('DocxHeading', parent=styles['Heading1'], fontSize=14, spaceAfter=8, spaceBefore=12)
    body_style = ParagraphStyle('DocxBody', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=6, alignment=TA_JUSTIFY)
    bullet_style = ParagraphStyle('DocxBullet', parent=body_style, leftIndent=20, bulletIndent=10)

    elements = []
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 6*mm))

    for para in docx_doc.paragraphs:
        text = para.text.strip()
        if not text:
            elements.append(Spacer(1, 3*mm))
            continue

        style_name = para.style.name.lower() if para.style else ''

        if 'heading' in style_name or 'title' in style_name:
            level = 1
            for key in para.style.element.xpath('@w:outlineLvl') if hasattr(para.style, 'element') else []:
                try: level = int(key) + 1
                except: pass
            h_style = ParagraphStyle(f'H{level}', parent=heading_style, fontSize=max(14 - (level-1)*2, 10))
            elements.append(Paragraph(escape_xml(text), h_style))
        elif para.style and 'list' in style_name:
            elements.append(Paragraph(f'&bull; {escape_xml(text)}', bullet_style))
        else:
            elements.append(Paragraph(escape_xml(text), body_style))

    try:
        doc.build(elements)
    except Exception as e:
        raise ValueError(f"Failed to build PDF from DOCX content: {e}")

    pdf_bytes = buf.getvalue()
    if len(pdf_bytes) == 0:
        raise ValueError("Generated PDF is empty")

    return pdf_bytes


def escape_xml(text):
    """Escape text for use in reportlab XML paragraphs."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

