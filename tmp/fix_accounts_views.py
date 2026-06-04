import os

target_file = 'accounts/views.py'
with open(target_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # Improve student signup error handling
    if "if 'user' in locals() and user: user.delete()" in line:
        indent = line.split("if")[0]
        new_lines.append(f"{indent}# Safe deletion logic\n")
        new_lines.append(f"{indent}if 'user' in locals() and user and user.id:\n")
        new_lines.append(f"{indent}    try: user.delete()\n")
        new_lines.append(f"{indent}    except Exception as del_err: print(f'[ERROR] Could not delete: {{del_err}}')\n")
    else:
        new_lines.append(line)

with open(target_file, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Updated accounts/views.py")
