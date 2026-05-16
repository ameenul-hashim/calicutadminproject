from PIL import Image
import os

def crop_full_view(input_path, output_dir, prefix_m, prefix_f):
    img = Image.open(input_path)
    width, height = img.size
    
    cols = 5
    rows = 2
    cell_w = width // cols
    cell_h = height // rows
    
    # Process males (top row)
    for i in range(5):
        # Crop the full cell to ensure no hair/shoulder is lost
        left = i * cell_w
        top = 0
        right = (i + 1) * cell_w
        bottom = cell_h
        
        avatar = img.crop((left, top, right, bottom))
        
        # Now tight crop but keep vertical space
        aw, ah = avatar.size
        # Remove only the most extreme white space
        tight_avatar = avatar.crop((int(aw*0.05), int(ah*0.05), int(aw*0.95), int(ah*0.95)))
        
        tight_avatar.save(os.path.join(output_dir, f'{prefix_m}_{i}.png'))
        print(f"Saved full-view {prefix_m}_{i}.png")

    # Process females (bottom row)
    for i in range(5):
        left = i * cell_w
        top = cell_h
        right = (i + 1) * cell_w
        bottom = 2 * cell_h
        
        avatar = img.crop((left, top, right, bottom))
        aw, ah = avatar.size
        tight_avatar = avatar.crop((int(aw*0.05), int(ah*0.05), int(aw*0.95), int(ah*0.95)))
        
        tight_avatar.save(os.path.join(output_dir, f'{prefix_f}_{i}.png'))
        print(f"Saved full-view {prefix_f}_{i}.png")

def main():
    brain_dir = r"C:\Users\lenov\.\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42"
    output_dir = r"c:\Users\lenov\OneDrive\Desktop\all degree projects\calicutadminproject\static\avatars"
    
    # Process all 3 sets with the "Full View" logic
    crop_full_view(os.path.join(brain_dir, "media__1778956880547.jpg"), output_dir, "admin_m", "admin_f")
    crop_full_view(os.path.join(brain_dir, "media__1778957043907.jpg"), output_dir, "student_m", "student_f")
    crop_full_view(os.path.join(brain_dir, "media__1778957107973.jpg"), output_dir, "teacher_m", "teacher_f")

if __name__ == "__main__":
    main()
