import os
path = r'accounts/utils/firebase_db.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

func = """
def init_firebase_structure():
    \"\"\"Creates root nodes in RTDB to prevent manual setup.\"\"\"
    app = _get_app()
    if app is None:
        return False
    try:
        ref = db.reference('/', app=app)
        existing = ref.get(shallow=True) or {}
        updates = {}
        for node in ['admin_activity', 'analytics', 'audit', 'login_history', 'notifications', 'support_chat', 'test_write', 'backup']:
            if node not in existing:
                updates[f'/{node}/_init'] = True
        if updates:
            ref.update(updates)
        return True
    except Exception as e:
        logger.error(f"Failed to intialize firebase structure: {e}")
        return False
"""
if "def init_firebase_structure" not in text:
    text += "\n" + func + "\n"
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
print("Updated firebase_db.py")
