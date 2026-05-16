from PIL import Image
import os

def crop_exact(input_path, output_dir, prefix_m, prefix_f, top_row_y, bottom_row_y, row_h, col_w_ratio):
    img = Image.open(input_path)
    width, height = img.size
    
    # We want 5 columns
    cols = 5
    cell_w = width // cols
    
    # Exact width of the colored box (approx 90% of cell)
    exact_w = int(cell_w * col_w_ratio)
    h_offset = (cell_w - exact_w) // 2
    
    # Row height in pixels
    h_px = int(height * row_h)
    
    # Top Row
    for i in range(5):
        left = i * cell_w + h_offset
        top = int(height * top_row_y)
        right = left + exact_w
        bottom = top + h_px
        
        avatar = img.crop((left, top, right, bottom))
        avatar.save(os.path.join(output_dir, f'{prefix_m}_{i}.png'))
        print(f"Saved exact {prefix_m}_{i}.png")

    # Bottom Row
    for i in range(5):
        left = i * cell_w + h_offset
        top = int(height * bottom_row_y)
        right = left + exact_w
        bottom = top + h_px
        
        avatar = img.crop((left, top, right, bottom))
        avatar.save(os.path.join(output_dir, f'{prefix_f}_{i}.png'))
        print(f"Saved exact {prefix_f}_{i}.png")

def main():
    brain_dir = r"C:\Users\lenov\.\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42"
    output_dir = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminproject\static\avatars"
    
    # Admin Sheet
    # Photos are between y=140 and y=460 (top row) and y=520 and y=840 (bottom row) in a 1024 height image
    # Let's use more precise ratios based on visual check
    crop_exact(os.path.join(brain_dir, "media__1778956880547.jpg"), output_dir, "admin_m", "admin_f", 0.14, 0.52, 0.34, 0.86)
    
    # Student Sheet
    crop_exact(os.path.join(brain_dir, "media__1778957043907.jpg"), output_dir, "student_m", "student_f", 0.14, 0.52, 0.34, 0.86)
    
    # Teacher Sheet
    crop_exact(os.path.join(brain_dir, "media__1778957107973.jpg"), output_dir, "teacher_m", "teacher_f", 0.14, 0.52, 0.34, 0.86)

if __name__ == "__main__":
    main()
