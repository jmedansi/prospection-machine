# -*- coding: utf-8 -*-
from PIL import Image
import os

def main():
    icon_192_path = 'dashboard/static/icon-192.png'
    icon_512_path = 'dashboard/static/icon-512.png'
    
    if not os.path.exists(icon_192_path):
        print(f"Error: Base icon {icon_192_path} not found.")
        return
        
    try:
        with Image.open(icon_192_path) as img:
            # Resize icon to 512x512 using Lanczos resampling for high quality
            img_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
            img_512.save(icon_512_path, 'PNG')
            print(f"[SUCCESS] Created PWA high-res icon: {icon_512_path} (512x512)")
    except Exception as e:
        print(f"Error resizing image: {e}")

if __name__ == '__main__':
    main()
