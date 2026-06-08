import sys
path = r'accounts/views.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    '    mark_read(str(request.user.uid), notif_uid)\n    if request.headers.get',
    '    mark_read(str(request.user.uid), notif_uid)\n    from django.core.cache import cache\n    cache.delete(f"pending_counts_{request.user.id}_{request.user.user_type}")\n    if request.headers.get'
)
text = text.replace(
    '    db_del(str(request.user.uid), notif_uid)\n    if request.headers.get',
    '    db_del(str(request.user.uid), notif_uid)\n    from django.core.cache import cache\n    cache.delete(f"pending_counts_{request.user.id}_{request.user.user_type}")\n    if request.headers.get'
)
text = text.replace(
    '    mark_all_read(str(request.user.uid))\n    return redirect',
    '    mark_all_read(str(request.user.uid))\n    from django.core.cache import cache\n    cache.delete(f"pending_counts_{request.user.id}_{request.user.user_type}")\n    return redirect'
)

with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(text)
