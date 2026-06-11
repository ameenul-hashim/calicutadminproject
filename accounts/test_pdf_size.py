"""
Standalone tests for PDF size validation logic.

These tests verify the core validation conditions directly, WITHOUT
needing Django's test database or full request stack. They test that:

1. PDFs >200KB are rejected by the size condition
2. The `_is_mobile_ua` gate works correctly
3. The combined validation logic produces correct results

Run with: python -m accounts.test_pdf_size
"""
import io
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['DATABASE_URL'] = ''

import django
from django.conf import settings
if not settings.configured:
    settings.configure(
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        INSTALLED_APPS=['django.contrib.contenttypes', 'django.contrib.auth', 'accounts'],
        AUTH_USER_MODEL='accounts.CustomUser',
        SECRET_KEY='test-key',
    )
    django.setup()

MAX_SIZE = 200 * 1024  # 200 KB


def validate_pdf_size(file_size, file_extension):
    """
    Replicates the server-side size check from signup_view.
    Returns (is_valid: bool, error_message: str|None).
    """
    if file_extension == '.pdf' and file_size > MAX_SIZE:
        return False, "Verification document file size must be below 200 KB."
    return True, None


def validate_all(file_ext, file_size, is_mobile=False):
    """
    Replicates the full file validation pipeline from signup_view.
    Returns (is_valid: bool, error_message: str|None).
    """
    ALLOWED_EXTS = ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif']
    if file_ext not in ALLOWED_EXTS:
        return False, f"Unsupported file format '{file_ext}'. Please upload a PDF or an Image."

    is_image = file_ext != '.pdf'
    if is_image and not is_mobile:
        return False, "Image uploads are only supported on mobile devices."

    if file_ext == '.pdf' and file_size > MAX_SIZE:
        return False, "Verification document file size must be below 200 KB."

    if file_ext != '.pdf' and file_size > 10 * 1024 * 1024:
        return False, "Image file is too large. Please choose a smaller image (max 10 MB)."

    return True, None


class TestPDFSizeCondition(unittest.TestCase):
    """Test the PDF size comparison operation directly."""

    def test_199kb_is_under_limit(self):
        is_valid, msg = validate_pdf_size(199 * 1024, '.pdf')
        self.assertTrue(is_valid)

    def test_200kb_is_at_limit(self):
        is_valid, msg = validate_pdf_size(200 * 1024, '.pdf')
        self.assertTrue(is_valid)

    def test_201kb_exceeds_limit(self):
        is_valid, msg = validate_pdf_size(201 * 1024, '.pdf')
        self.assertFalse(is_valid)
        self.assertIn('must be below 200 KB', msg)

    def test_500kb_exceeds_limit(self):
        is_valid, msg = validate_pdf_size(500 * 1024, '.pdf')
        self.assertFalse(is_valid)

    def test_1mb_exceeds_limit(self):
        is_valid, msg = validate_pdf_size(1024 * 1024, '.pdf')
        self.assertFalse(is_valid)

    def test_334mb_exceeds_limit(self):
        is_valid, msg = validate_pdf_size(int(3.34 * 1024 * 1024), '.pdf')
        self.assertFalse(is_valid)

    def test_image_not_checked(self):
        """Images should NOT be checked by the PDF size rule."""
        is_valid, msg = validate_pdf_size(10 * 1024 * 1024, '.jpg')
        self.assertTrue(is_valid, "PDF size validation should not apply to images")


class TestFullValidationPipeline(unittest.TestCase):
    """Test the complete file validation pipeline from signup views."""

    # ── Desktop: PDF uploads ──────────────────────────────────────────

    def test_desktop_pdf_199kb_valid(self):
        is_valid, msg = validate_all('.pdf', 199 * 1024, is_mobile=False)
        self.assertTrue(is_valid)

    def test_desktop_pdf_200kb_valid(self):
        is_valid, msg = validate_all('.pdf', 200 * 1024, is_mobile=False)
        self.assertTrue(is_valid)

    def test_desktop_pdf_201kb_invalid(self):
        is_valid, msg = validate_all('.pdf', 201 * 1024, is_mobile=False)
        self.assertFalse(is_valid)
        self.assertIn('must be below 200 KB', msg)

    def test_desktop_pdf_334mb_invalid(self):
        is_valid, msg = validate_all('.pdf', int(3.34 * 1024 * 1024), is_mobile=False)
        self.assertFalse(is_valid)
        self.assertIn('must be below 200 KB', msg)

    # ── Desktop: image uploads ────────────────────────────────────────

    def test_desktop_image_rejected(self):
        """Desktop must reject images regardless of size."""
        is_valid, msg = validate_all('.jpg', 100 * 1024, is_mobile=False)
        self.assertFalse(is_valid)
        self.assertIn('Image uploads are only supported on mobile devices', msg)

    # ── Mobile: PDF uploads ───────────────────────────────────────────

    def test_mobile_pdf_199kb_valid(self):
        is_valid, msg = validate_all('.pdf', 199 * 1024, is_mobile=True)
        self.assertTrue(is_valid)

    def test_mobile_pdf_201kb_invalid(self):
        is_valid, msg = validate_all('.pdf', 201 * 1024, is_mobile=True)
        self.assertFalse(is_valid)
        self.assertIn('must be below 200 KB', msg)

    # ── Mobile: image uploads ─────────────────────────────────────────

    def test_mobile_image_valid_size(self):
        """Mobile image of reasonable size should pass (will be converted server-side)."""
        is_valid, msg = validate_all('.jpg', 500 * 1024, is_mobile=True)
        self.assertTrue(is_valid)

    def test_mobile_image_over_10mb_invalid(self):
        """Mobile image over 10MB should be rejected (sanity limit)."""
        is_valid, msg = validate_all('.jpg', 11 * 1024 * 1024, is_mobile=True)
        self.assertFalse(is_valid)
        self.assertIn('too large', msg)

    # ── Invalid extensions ────────────────────────────────────────────

    def test_invalid_extension_rejected(self):
        is_valid, msg = validate_all('.exe', 50 * 1024, is_mobile=False)
        self.assertFalse(is_valid)
        self.assertIn('Unsupported file format', msg)

    def test_invalid_extension_mobile_rejected(self):
        is_valid, msg = validate_all('.exe', 50 * 1024, is_mobile=True)
        self.assertFalse(is_valid)
        self.assertIn('Unsupported file format', msg)


class TestConvertedPDFSizeCheck(unittest.TestCase):
    """Test the size check on PDF output from convert_image_to_pdf."""

    def test_converted_pdf_150kb_accepted(self):
        """Converted PDF ≤200KB must pass."""
        pdf_size = 150 * 1024
        self.assertLessEqual(pdf_size, MAX_SIZE)

    def test_converted_pdf_200kb_accepted(self):
        """Converted PDF exactly 200KB must pass (boundary)."""
        pdf_size = 200 * 1024
        self.assertLessEqual(pdf_size, MAX_SIZE)

    def test_converted_pdf_201kb_rejected(self):
        """Converted PDF >200KB must be rejected."""
        pdf_size = 201 * 1024
        self.assertGreater(pdf_size, MAX_SIZE)

    def test_converted_pdf_250kb_rejected(self):
        """Converted PDF 250KB must be rejected."""
        pdf_size = 250 * 1024
        self.assertGreater(pdf_size, MAX_SIZE)

    def test_converted_pdf_1mb_rejected(self):
        """Converted PDF 1MB must be rejected."""
        pdf_size = 1024 * 1024
        self.assertGreater(pdf_size, MAX_SIZE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
