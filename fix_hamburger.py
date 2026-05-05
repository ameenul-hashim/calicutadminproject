import os

def inject_hamburger(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'id="mobile-sidebar-toggle"' in content:
        return False
        
    if '</body>' not in content:
        return False

    hamburger_html = """
    <!-- Mobile Hamburger Toggle -->
    <button id="mobile-sidebar-toggle" style="display: none; position: fixed; bottom: 20px; right: 20px; z-index: 1001; background: #0ea5e9; color: white; width: 50px; height: 50px; border-radius: 50%; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.1); cursor: pointer; align-items: center; justify-content: center; font-size: 24px;">
        ☰
    </button>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            var toggleBtn = document.getElementById('mobile-sidebar-toggle');
            var sidebars = document.querySelectorAll('.sidebar, aside');
            
            function checkWidth() {
                if (window.innerWidth <= 1024) {
                    if (sidebars.length > 0) {
                        toggleBtn.style.display = 'flex';
                    }
                } else {
                    toggleBtn.style.display = 'none';
                    sidebars.forEach(function(sb) {
                        sb.style.display = '';
                        sb.classList.remove('mobile-active');
                    });
                }
            }
            
            checkWidth();
            window.addEventListener('resize', checkWidth);
            
            toggleBtn.addEventListener('click', function() {
                sidebars.forEach(function(sb) {
                    if (sb.classList.contains('mobile-active')) {
                        sb.classList.remove('mobile-active');
                        sb.style.display = 'none';
                    } else {
                        sb.classList.add('mobile-active');
                        sb.style.display = 'block';
                        sb.style.position = 'fixed';
                        sb.style.zIndex = '1000';
                        sb.style.height = '100vh';
                        sb.style.left = '0';
                        sb.style.top = '0';
                    }
                });
            });
        });
    </script>
    </body>
"""
    content = content.replace('</body>', hamburger_html)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return True

import glob
changed = 0
for root, dirs, files in os.walk('.'):
    if 'venv' in root or '.git' in root: continue
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            if inject_hamburger(filepath):
                changed += 1

print(f"Injected hamburger into {changed} files.")
