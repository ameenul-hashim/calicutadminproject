import os
from PIL import Image
import glob

os.makedirs('static/avatars', exist_ok=True)
imgs = glob.glob(r'C:\Users\lenov\.gemini\antigravity\brain\394f4604-ecbd-42cf-9d05-de5e07439c42\*.png')

for f in imgs:
    img = Image.open(f)
    base_name = os.path.basename(f).replace('.png', '')
    # remove timestamp
    base_name = '_'.join(base_name.split('_')[:-1])
    boxes = [
        (0, 0, 512, 512),
        (512, 0, 1024, 512),
        (0, 512, 512, 1024),
        (512, 512, 1024, 1024)
    ]
    for i, box in enumerate(boxes):
        cropped = img.crop(box)
        cropped.save(f'static/avatars/{base_name}_{i}.png')
print("Successfully generated avatars!")
