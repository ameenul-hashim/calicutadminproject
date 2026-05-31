from PIL import Image, ImageFilter
import os

def crop_high_quality(input_path, output_dir, prefix_m, prefix_f, top_row_y, bottom_row_y, row_h, col_w_ratio):
    print(f"Processing {input_path}...")
    img = Image.open(input_path).convert('RGB')
    width, height = img.size
    
    cols = 5
    cell_w = width // cols
    exact_w = int(cell_w * col_w_ratio)
    h_offset = (cell_w - exact_w) // 2
    h_px = int(height * row_h)
    
    target_h = 400
    target_w = int(target_h * (exact_w / h_px))

    def process_and_save(left, top, right, bottom, filename):
        avatar = img.crop((left, top, right, bottom))
        avatar = avatar.resize((target_w, target_h), Image.Resampling.LANCZOS)
        avatar = avatar.filter(ImageFilter.SHARPEN)
        avatar.save(os.path.join(output_dir, filename), 'PNG', optimize=True)
        print(f"  Saved {filename}")

    # Top Row (Males)
    for i in range(5):
        left = i * cell_w + h_offset
        top = int(height * top_row_y)
        right = left + exact_w
        bottom = top + h_px
        process_and_save(left, top, right, bottom, f'{prefix_m}_{i}.png')

    # Bottom Row (Females)
    for i in range(5):
        left = i * cell_w + h_offset
        top = int(height * bottom_row_y)
        right = left + exact_w
        bottom = top + h_px
        process_and_save(left, top, right, bottom, f'{prefix_f}_{i}.png')

def main():
    brain_dir = r"C:\Users\lenov\.\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42"
    output_dir = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminproject\static\avatars"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Admin Sheet
    crop_high_quality(os.path.join(brain_dir, "media__1778956880547.jpg"), output_dir, "admin_m", "admin_f", 0.14, 0.52, 0.34, 0.86)
    
    # Teacher Sheet (Keeping the unique professional educators)
    crop_high_quality(os.path.join(brain_dir, "teacher_avatars_new_sheet_1778961232982.png"), output_dir, "teacher_m", "teacher_f", 0.02, 0.52, 0.45, 0.90)
    
    # Student Sheet (REVERTING TO THE ORIGINAL PROFESSIONAL STUDENT SHEET)
    # File: media__1778957043907.jpg
    crop_high_quality(os.path.join(brain_dir, "media__1778957043907.jpg"), output_dir, "student_m", "student_f", 0.14, 0.52, 0.34, 0.86)

if __name__ == "__main__":
    main()
