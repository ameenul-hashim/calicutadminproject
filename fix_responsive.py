import os
import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    responsive_css = """
    <style>
        /* RESPONSIVE INJECTIONS */
        @media (max-width: 1024px) {
            .sidebar, aside { display: none !important; }
            .main-content, main { margin-left: 0 !important; padding: 1rem !important; width: 100% !important; max-width: 100vw !important; }
            .search-bar, .form-container, .card, .edit-card, .login-card, .glass-card { width: 100% !important; max-width: 100% !important; padding: 1rem !important; }
            .stats-grid, .subject-grid, .card-grid, .grid, [style*="grid-template-columns"] { grid-template-columns: 1fr !important; }
            [style*="display: flex"] { flex-direction: column !important; }
            header[style*="display: flex"] { flex-direction: column !important; align-items: flex-start !important; gap: 1rem !important; }
            .btn { width: 100% !important; margin-bottom: 0.5rem !important; }
            
            /* Forms */
            .input-group input, .input-group select, .input-group textarea, input[type="text"], input[type="email"], input[type="password"] { width: 100% !important; max-width: 100% !important; }
        }
        @media (min-width: 768px) and (max-width: 1024px) {
            .stats-grid, .subject-grid, .card-grid, .grid { grid-template-columns: repeat(2, 1fr) !important; }
            [style*="display: flex"] { flex-direction: row !important; flex-wrap: wrap !important; }
            .btn { width: auto !important; }
        }
        .table-responsive, .table-container { overflow-x: auto; width: 100%; }
        table { min-width: 62.5rem; /* 1000px */ }
        
        /* Video Player Responsive */
        .video-container { aspect-ratio: 16 / 9; width: 100%; max-width: 100%; }
        video { width: 100%; height: 100%; }
        
        /* Django Messages Toast */
        .messages, .alert { max-width: 24rem; word-wrap: break-word; }
        @media (max-width: 640px) {
            .messages, .alert { max-width: 90vw; }
        }
    </style>
"""

    if '</head>' in content and 'cdn.tailwindcss.com' not in content:
        tailwind_injection = """
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        corePlugins: { preflight: false }
      }
    </script>
""" + responsive_css + "</head>"
        content = content.replace('</head>', tailwind_injection)
    elif '</head>' in content and '/* RESPONSIVE INJECTIONS */' not in content:
        # Tailwind is there but not our CSS block
        content = content.replace('</head>', responsive_css + "</head>")

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

import glob
changed = 0
for root, dirs, files in os.walk('.'):
    if 'venv' in root or '.git' in root: continue
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            if process_file(filepath):
                changed += 1

print(f"Updated {changed} files.")


