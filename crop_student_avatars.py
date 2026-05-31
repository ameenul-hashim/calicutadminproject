from PIL import Image
import os

def crop_avatars(input_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    img = Image.open(input_path)
    width, height = img.size
    
    # Grid: 2 rows, 5 columns
    rows = 2
    cols = 5
    
    cell_width = width // cols
    cell_height = height // rows
    
    # Process females (top row)
    for c in range(cols):
        left = c * cell_width
        top = 0
        right = (c + 1) * cell_width
        bottom = cell_height
        
        avatar = img.crop((left, top, right, bottom))
        # Smarter crop: Square from the top/center to ensure hair is visible
        w, h = avatar.size
        size = min(w, h)
        left_p = (w - size) // 2
        # Use a small top offset (e.g. 10%) instead of centering vertically to keep hair
        top_p = int(h * 0.05) 
        if top_p + size > h:
            top_p = h - size
            
        avatar = avatar.crop((left_p, top_p, left_p + size, top_p + size))
        
        avatar.save(os.path.join(output_dir, f'student_f_{c}.png'))
        print(f"Saved female avatar {c}")

    # Process males (bottom row)
    for c in range(cols):
        left = c * cell_width
        top = cell_height
        right = (c + 1) * cell_width
        bottom = 2 * cell_height
        
        avatar = img.crop((left, top, right, bottom))
        # Smarter crop
        w, h = avatar.size
        size = min(w, h)
        left_p = (w - size) // 2
        top_p = int(h * 0.05)
        if top_p + size > h:
            top_p = h - size
            
        avatar = avatar.crop((left_p, top_p, left_p + size, top_p + size))
        
        avatar.save(os.path.join(output_dir, f'student_m_{c}.png'))
        print(f"Saved male avatar {c}")

if __name__ == "__main__":
    input_img = r"C:\Users\lenov\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42\media__1778955726048.jpg"
    output_folder = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminproject\static\avatars"
    crop_avatars(input_img, output_folder)
