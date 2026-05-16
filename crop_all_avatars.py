from PIL import Image
import os

def crop_set_v2(input_path, output_dir, prefix_m, prefix_f, top_y_start, row_height):
    img = Image.open(input_path)
    width, height = img.size
    
    cols = 5
    cell_w = width // cols
    
    # Process males (top row)
    for i in range(5):
        left = i * cell_w
        top = int(height * top_y_start)
        right = (i + 1) * cell_w
        bottom = top + int(height * row_height)
        
        avatar = img.crop((left, top, right, bottom))
        # Center crop to square
        aw, ah = avatar.size
        size = min(aw, ah)
        # Center horizontally, but favor top for hair
        cx = (aw - size) // 2
        cy = 0 # Already starting from a good 'top'
        
        avatar = avatar.crop((cx, cy, cx + size, cy + size))
        avatar.save(os.path.join(output_dir, f'{prefix_m}_{i}.png'))
        print(f"Saved {prefix_m}_{i}.png")

    # Process females (bottom row)
    for i in range(5):
        left = i * cell_w
        # Bottom row usually starts after the top row
        top = int(height * (top_y_start + row_height + 0.05)) 
        right = (i + 1) * cell_w
        bottom = top + int(height * row_height)
        
        avatar = img.crop((left, top, right, bottom))
        aw, ah = avatar.size
        size = min(aw, ah)
        cx = (aw - size) // 2
        cy = 0
        
        avatar = avatar.crop((cx, cy, cx + size, cy + size))
        avatar.save(os.path.join(output_dir, f'{prefix_f}_{i}.png'))
        print(f"Saved {prefix_f}_{i}.png")

def main():
    brain_dir = r"C:\Users\lenov\.\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42"
    output_dir = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminproject\static\avatars"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Admin Set (media__1778956880547.jpg)
    # This one has a header. Photos start around 15% and each row is ~35%
    crop_set_v2(os.path.join(brain_dir, "media__1778956880547.jpg"), output_dir, "admin_m", "admin_f", 0.15, 0.35)
    
    # Student Set (media__1778957043907.jpg)
    # Similar structure
    crop_set_v2(os.path.join(brain_dir, "media__1778957043907.jpg"), output_dir, "student_m", "student_f", 0.15, 0.35)
    
    # Teacher Set (media__1778957107973.jpg)
    crop_set_v2(os.path.join(brain_dir, "media__1778957107973.jpg"), output_dir, "teacher_m", "teacher_f", 0.15, 0.35)

if __name__ == "__main__":
    main()
