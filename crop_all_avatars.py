from PIL import Image
import os

def crop_tight(input_path, output_dir, prefix_m, prefix_f, top_y, row_h):
    img = Image.open(input_path)
    width, height = img.size
    
    cols = 5
    cell_w = width // cols
    
    # Tight width (remove side white space)
    tight_w = int(cell_w * 0.88)
    # Horizontal offset to center the tight crop
    h_offset = (cell_w - tight_w) // 2
    
    # Process males (top row)
    for i in range(5):
        left = i * cell_w + h_offset
        top = int(height * top_y)
        right = left + tight_w
        bottom = top + int(height * row_h)
        
        avatar = img.crop((left, top, right, bottom))
        # No square crop here, we want the full professional rectangle
        avatar.save(os.path.join(output_dir, f'{prefix_m}_{i}.png'))
        print(f"Saved tight {prefix_m}_{i}.png")

    # Process females (bottom row)
    for i in range(5):
        left = i * cell_w + h_offset
        # Offset for bottom row
        top = int(height * (top_y + row_h + 0.05))
        right = left + tight_w
        bottom = top + int(height * row_h)
        
        avatar = img.crop((left, top, right, bottom))
        avatar.save(os.path.join(output_dir, f'{prefix_f}_{i}.png'))
        print(f"Saved tight {prefix_f}_{i}.png")

def main():
    brain_dir = r"C:\Users\lenov\.\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42"
    output_dir = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminproject\static\avatars"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # All three sheets follow a similar layout
    # Admin Set
    crop_tight(os.path.join(brain_dir, "media__1778956880547.jpg"), output_dir, "admin_m", "admin_f", 0.12, 0.38)
    
    # Student Set
    crop_tight(os.path.join(brain_dir, "media__1778957043907.jpg"), output_dir, "student_m", "student_f", 0.12, 0.38)
    
    # Teacher Set
    crop_tight(os.path.join(brain_dir, "media__1778957107973.jpg"), output_dir, "teacher_m", "teacher_f", 0.12, 0.38)

if __name__ == "__main__":
    main()
