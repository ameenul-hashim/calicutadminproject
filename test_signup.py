import sys, os, django
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
django.setup()

# Test 1: Can we import signup dependencies?
from accounts.utils.supabase_storage import upload_user_proof, supabase
print('Test 1 - Supabase initialized:', supabase is not None)

from accounts.utils.pdf_helpers import convert_image_to_pdf
print('Test 2 - pdf_helpers import OK')

# Test 3: Convert a small test image to PDF
from PIL import Image
import io
img = Image.new('RGB', (100, 100), color='red')
buf = io.BytesIO()
img.save(buf, 'JPEG')
buf.seek(0)

from django.core.files.base import ContentFile
test_file = ContentFile(buf.read(), name='test.jpg')

result = convert_image_to_pdf(test_file)
if result:
    content = result.read()
    print('Test 3 - Image to PDF: OK, size=%d bytes, pdf_header=%s' % (len(content), content[:5] == b'%PDF-'))
else:
    print('Test 3 - Image to PDF: FAILED')

# Test 4: Test upload_user_proof with a mock user
from accounts.models import CustomUser
user = CustomUser.objects.create_user(
    username='test_signup_123',
    email='test_signup_123@test.com',
    password='Test@1234',
    full_name='Test User',
    phone_number='9999999999',
    is_active=False,
    status='PENDING',
    user_type='STUDENT',
)
print('Test 4 - User created: id=%d, uid=%s' % (user.id, user.uid))

# Try uploading
if result:
    result.seek(0)
    success = upload_user_proof(user, result)
    print('Test 5 - Supabase upload:', success)
    if success:
        print('  pdf_path:', user.pdf_path)
        print('  status:', user.status)

# Cleanup
if 'user' in dir():
    user.delete()
# Also delete the login history entries if any
from accounts.models import LoginHistory
LoginHistory.objects.filter(user=user).delete()
print('Test 6 - cleanup OK')
