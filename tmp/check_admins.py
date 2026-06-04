from accounts.models import CustomUser
print(f"Total Users: {CustomUser.objects.count()}")
print(f"Admins: {CustomUser.objects.filter(user_type='ADMIN').count()}")
for admin in CustomUser.objects.filter(user_type='ADMIN'):
    print(f"Admin: {admin.username}, Status: {admin.status}")
