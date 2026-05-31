import os
import re

def remove_placeholders(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Regex to find placeholder="..." and remove it
                # We also handle single quotes and extra spaces
                new_content = re.sub(r'\s*placeholder=["\'][^"\']*["\']', '', content)
                
                if content != new_content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Processed {path}")

if __name__ == "__main__":
    base_dir = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminapplication"
    remove_placeholders(os.path.join(base_dir, "accounts", "templates"))
    remove_placeholders(os.path.join(base_dir, "custom_admin", "templates"))
