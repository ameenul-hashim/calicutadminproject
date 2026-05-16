from PIL import Image
import os

def crop_set(input_path, output_dir, prefix_m, prefix_f):
    img = Image.open(input_path)
    width, height = img.size
    
    # All these sheets are 2 rows, 5 columns
    cols = 5
    rows = 2
    
    cell_w = width // cols
    cell_h = height // rows
    
    # Process males (top row)
    for i in range(5):
        avatar = img.crop((i * cell_w, 0, (i + 1) * cell_w, cell_h))
        aw, ah = avatar.size
        # Make it a square crop favoring the top (passport style)
        size = min(aw, ah)
        left = (aw - size) // 2
        # Start from top with a tiny offset to ensure hair
        top = int(ah * 0.02)
        if top + size > ah:
            top = ah - size
        avatar = avatar.crop((left, top, left + size, top + size))
        avatar.save(os.path.join(output_dir, f'{prefix_m}_{i}.png'))
        print(f"Saved {prefix_m}_{i}.png")

    # Process females (bottom row)
    for i in range(5):
        avatar = img.crop((i * cell_w, cell_h, (i + 1) * cell_w, 2 * cell_h))
        aw, ah = avatar.size
        size = min(aw, ah)
        left = (aw - size) // 2
        top = int(ah * 0.02)
        if top + size > ah:
            top = ah - size
        avatar = avatar.crop((left, top, left + size, top + size))
        avatar.save(os.path.join(output_dir, f'{prefix_f}_{i}.png'))
        print(f"Saved {prefix_f}_{i}.png")

def main():
    brain_dir = r"C:\Users\lenov\.\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42"
    output_dir = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminproject\static\avatars"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Admin Set (media__1778956880547.jpg)
    crop_set(os.path.join(brain_dir, "media__1778956880547.jpg"), output_dir, "admin_m", "admin_f")
    
    # Student Set (media__1778957043907.jpg)
    crop_set(os.path.join(brain_dir, "media__1778957043907.jpg"), output_dir, "student_m", "student_f")
    
    # Teacher Set (media__1778957107973.jpg)
    crop_set(os.path.join(brain_dir, "media__1778957107973.jpg"), output_dir, "teacher_m", "teacher_f")

if __name__ == "__main__":
    main()
