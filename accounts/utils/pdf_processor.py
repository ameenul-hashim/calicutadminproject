import os
import io
import tempfile
import logging

logger = logging.getLogger(__name__)

def validate_file(file_obj, filename, expected_type='PDF'):
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    if ext != 'pdf':
        raise ValueError(f"Invalid file extension '.{ext}'. Only PDF files are supported.")
    mime_type = 'application/pdf'
    return mime_type, ext

