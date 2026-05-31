import os
import sys
import django
import uuid

# Add current directory to path so elearning_project can be found
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'elearning_project.settings')
django.setup()

from accounts.models import CustomUser, Course, Lesson

def populate_uuids():
    print("Fixing CustomUser UIDs...")
    for user in CustomUser.objects.all():
        user.uid = uuid.uuid4()
        user.save()
        
    print("Fixing Course UIDs...")
    for course in Course.objects.all():
        course.uid = uuid.uuid4()
        course.save()
        
    print("Fixing Lesson UIDs...")
    for lesson in Lesson.objects.all():
        lesson.uid = uuid.uuid4()
        lesson.save()

    print("Done!")


if __name__ == "__main__":
    populate_uuids()
