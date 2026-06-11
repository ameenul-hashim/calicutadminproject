"""
Tests for PDF size validation during signup.

Run with:
    set DATABASE_URL= && python manage.py test accounts.tests --keepdb --verbosity 2
    (DATABASE_URL must be cleared to force SQLite test database)
"""
import os
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from unittest.mock import patch


def make_pdf(size_bytes, name='test.pdf'):
    content = b'%PDF-1.4\n' + b'x' * max(0, size_bytes - 9) + b'\n%%EOF'
    return SimpleUploadedFile(name, content, content_type='application/pdf')


class SignupPDFSizeValidationTests(TestCase):
    """Verify that PDFs larger than 200KB are rejected during signup."""

    def setUp(self):
        self.client = Client()
        self.signup_url = reverse('signup')
        self.teacher_signup_url = reverse('teacher_signup')
        self.valid_data = {
            'username': 'teststudent',
            'email': 'test@example.com',
            'fullname': 'Test Student',
            'password': 'StrongPass1!',
            'confirm_password': 'StrongPass1!',
            'phone_number': '9876543210',
        }

    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_199kb_pdf_accepted(self, mock_notify, mock_upload):
        """199 KB PDF must pass validation."""
        mock_upload.return_value = True
        response = self.client.post(self.signup_url, {
            **self.valid_data,
            'proof_file': make_pdf(199 * 1024),
        })
        content = response.content.decode()
        self.assertNotIn('must be below 200 KB', content)
        self.assertNotIn('exceeds the maximum limit', content)
        self.assertIn(response.status_code, [200, 302])

    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_200kb_pdf_accepted_boundary(self, mock_notify, mock_upload):
        """Exactly 200 KB PDF must pass validation (boundary)."""
        mock_upload.return_value = True
        response = self.client.post(self.signup_url, {
            **self.valid_data,
            'proof_file': make_pdf(200 * 1024),
        })
        content = response.content.decode()
        self.assertNotIn('must be below 200 KB', content)
        self.assertIn(response.status_code, [200, 302])

    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_201kb_pdf_rejected(self, mock_notify, mock_upload):
        """201 KB PDF must be rejected BEFORE user creation and upload."""
        response = self.client.post(self.signup_url, {
            **self.valid_data,
            'proof_file': make_pdf(201 * 1024),
        })
        self.assertContains(response, 'must be below 200 KB')
        mock_upload.assert_not_called()

    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_334mb_pdf_rejected(self, mock_notify, mock_upload):
        """3.34 MB PDF must be rejected BEFORE user creation and upload."""
        size = int(3.34 * 1024 * 1024)
        response = self.client.post(self.signup_url, {
            **self.valid_data,
            'proof_file': make_pdf(size),
        })
        self.assertContains(response, 'must be below 200 KB')
        mock_upload.assert_not_called()

    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_teacher_201kb_pdf_rejected(self, mock_notify, mock_upload):
        """Teacher signup: 201 KB PDF must be rejected BEFORE upload."""
        data = {**self.valid_data, 'username': 'testteacher'}
        response = self.client.post(self.teacher_signup_url, {
            **data,
            'proof_file': make_pdf(201 * 1024),
        })
        self.assertContains(response, 'must be below 200 KB')
        mock_upload.assert_not_called()

    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_teacher_334mb_pdf_rejected(self, mock_notify, mock_upload):
        """Teacher signup: 3.34 MB PDF must be rejected BEFORE upload."""
        size = int(3.34 * 1024 * 1024)
        data = {**self.valid_data, 'username': 'testteacher'}
        response = self.client.post(self.teacher_signup_url, {
            **data,
            'proof_file': make_pdf(size),
        })
        self.assertContains(response, 'must be below 200 KB')
        mock_upload.assert_not_called()

    @patch('accounts.utils.pdf_helpers.convert_image_to_pdf')
    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_mobile_image_large_converted_pdf_rejected(self, mock_notify, mock_upload, mock_convert):
        """Mobile image → converted PDF >200KB → must NOT reach upload_user_proof."""
        large_pdf = make_pdf(250 * 1024, 'converted.pdf')
        large_pdf.size = 250 * 1024
        mock_convert.return_value = large_pdf
        mock_upload.return_value = True

        image = SimpleUploadedFile('photo.jpg', b'\xff\xd8\xff\xe0' + b'x' * 100, content_type='image/jpeg')
        image.size = 500 * 1024

        response = self.client.post(
            self.signup_url,
            {**self.valid_data, 'proof_file': image},
            HTTP_USER_AGENT='Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36'
        )
        self.assertContains(response, 'Unable to convert the image into a PDF')
        mock_upload.assert_not_called()

    @patch('accounts.utils.pdf_helpers.convert_image_to_pdf')
    @patch('accounts.utils.supabase_storage.upload_user_proof')
    @patch('accounts.views.notify_admins')
    def test_mobile_image_small_converted_pdf_accepted(self, mock_notify, mock_upload, mock_convert):
        """Mobile image → converted PDF ≤200KB → must reach upload_user_proof."""
        small_pdf = make_pdf(150 * 1024, 'converted.pdf')
        small_pdf.size = 150 * 1024
        mock_convert.return_value = small_pdf
        mock_upload.return_value = True

        image = SimpleUploadedFile('photo.jpg', b'\xff\xd8\xff\xe0' + b'x' * 100, content_type='image/jpeg')
        image.size = 100 * 1024

        response = self.client.post(
            self.signup_url,
            {**self.valid_data, 'proof_file': image},
            HTTP_USER_AGENT='Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36'
        )

        self.assertIn(response.status_code, [200, 302])
        mock_upload.assert_called_once()
