"""
Fix hamburger menus properly in all base templates.
Strategy:
 - Remove the injected duplicate hamburger block (lines with 'mobile-sidebar-toggle')
 - For base_admin and base_teacher: fix existing .mobile-toggle to use correct CSS + JS
 - For standalone student pages: ensure proper sidebar toggle exists
"""
import os
import re

def remove_duplicate_hamburger(content):
    """Remove the duplicate injected hamburger button and its script block."""
    # Remove from <!-- Mobile Hamburger Toggle --> to the </script> after it
    pattern = r'\n\s*<!-- Mobile Hamburger Toggle -->.*?</script>\s*'
    return re.sub(pattern, '\n', content, flags=re.DOTALL)

def fix_base_admin(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Step 1: Remove duplicate injected hamburger
    content = remove_duplicate_hamburger(content)

    # Step 2: Fix the existing mobile-toggle button to use toggleSidebar()
    content = content.replace(
        'onclick="document.querySelector(\'.sidebar\').classList.toggle(\'active\')"',
        'id="hamburger-btn" onclick="toggleSidebar()" aria-label="Toggle navigation"'
    )

    # Step 3: Add sidebar backdrop div before the toggle button
    if 'sidebar-backdrop' not in content:
        content = content.replace(
            '<button class="mobile-toggle"',
            '<div id="sidebar-backdrop" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1050;" onclick="closeSidebar()"></div>\n    <button class="mobile-toggle"'
        )

    # Step 4: Replace the close-sidebar click handler with toggleSidebar functions
    old_close = '''        // Close sidebar when clicking main content on mobile
        document.querySelector('.main-stage').addEventListener('click', () => {
            if (window.innerWidth <= 1024) {
                document.querySelector('.sidebar').classList.remove('active');
            }
        });'''
    new_close = '''        // Sidebar toggle functions
        function toggleSidebar() {
            var sb = document.querySelector('.sidebar');
            var bd = document.getElementById('sidebar-backdrop');
            if (!sb) return;
            if (sb.classList.contains('active')) {
                sb.classList.remove('active');
                if (bd) bd.style.display = 'none';
            } else {
                sb.classList.add('active');
                if (bd) bd.style.display = 'block';
            }
        }
        function closeSidebar() {
            var sb = document.querySelector('.sidebar');
            var bd = document.getElementById('sidebar-backdrop');
            if (sb) sb.classList.remove('active');
            if (bd) bd.style.display = 'none';
        }
        var mainStage = document.querySelector('.main-stage');
        if (mainStage) {
            mainStage.addEventListener('click', function() {
                if (window.innerWidth <= 1024) closeSidebar();
            });
        }'''
    if old_close in content:
        content = content.replace(old_close, new_close)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Fixed: {filepath}")

def fix_base_teacher(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Step 1: Remove duplicate injected hamburger
    content = remove_duplicate_hamburger(content)

    # Step 2: Fix the existing mobile-toggle button
    content = content.replace(
        'onclick="document.querySelector(\'.sidebar\').classList.toggle(\'active\')"',
        'id="hamburger-btn" onclick="toggleSidebar()" aria-label="Toggle navigation"'
    )

    # Step 3: Add sidebar backdrop div before the toggle button (if not there)
    if 'sidebar-backdrop' not in content:
        content = content.replace(
            '<button class="mobile-toggle"',
            '<div id="sidebar-backdrop" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:999;" onclick="closeSidebar()"></div>\n    <button class="mobile-toggle"'
        )

    # Step 4: Replace the close-sidebar click handler with toggleSidebar functions
    old_close = '''        // Close sidebar when clicking main content on mobile
        document.querySelector('.main-content').addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                document.querySelector('.sidebar').classList.remove('active');
            }
        });'''
    new_close = '''        // Sidebar toggle functions
        function toggleSidebar() {
            var sb = document.querySelector('.sidebar');
            var bd = document.getElementById('sidebar-backdrop');
            if (!sb) return;
            if (sb.classList.contains('active')) {
                sb.classList.remove('active');
                if (bd) bd.style.display = 'none';
            } else {
                sb.classList.add('active');
                if (bd) bd.style.display = 'block';
            }
        }
        function closeSidebar() {
            var sb = document.querySelector('.sidebar');
            var bd = document.getElementById('sidebar-backdrop');
            if (sb) sb.classList.remove('active');
            if (bd) bd.style.display = 'none';
        }
        var mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.addEventListener('click', function() {
                if (window.innerWidth <= 1024) closeSidebar();
            });
        }'''
    if old_close in content:
        content = content.replace(old_close, new_close)

    # Step 5: Fix the mobile breakpoint from 768px to 1024px for the teacher sidebar
    content = content.replace(
        '@media (max-width: 768px) {\n            .sidebar { transform: translateX(-100%); }\n            .sidebar.active { transform: translateX(0); }\n            .main-content { margin-left: 0; padding: 1.5rem; }\n            .mobile-toggle { display: flex !important; }\n        }',
        '@media (max-width: 1024px) {\n            .sidebar { transform: translateX(-100%); z-index: 1100; }\n            .sidebar.active { transform: translateX(0); }\n            .main-content { margin-left: 0; padding: 1.5rem; padding-top: 5rem; }\n            .mobile-toggle { display: flex !important; }\n        }'
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Fixed: {filepath}")

def fix_student_dashboard(filepath):
    """Student dashboard doesn't have a sidebar but may have the duplicate hamburger. Remove it."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    content = remove_duplicate_hamburger(content)
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Cleaned: {filepath}")

print("Fixing hamburger menus...")
base_dir = '.'

# Admin base
fix_base_admin(os.path.join(base_dir, 'custom_admin', 'templates', 'custom_admin', 'base_admin.html'))

# Teacher base
fix_base_teacher(os.path.join(base_dir, 'accounts', 'templates', 'teacher_portal', 'base_teacher.html'))

# Remove duplicate hamburger from all other HTML files
print("\nCleaning up duplicate injected hamburger from all templates...")
cleaned = 0
for root, dirs, files in os.walk(base_dir):
    if 'venv' in root or '.git' in root:
        continue
    for file in files:
        if file.endswith('.html') and file not in ('base_admin.html', 'base_teacher.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            new_content = remove_duplicate_hamburger(content)
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                cleaned += 1

print(f"Cleaned duplicate hamburger from {cleaned} files.")
print("Done!")
