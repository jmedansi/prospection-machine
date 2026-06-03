# -*- coding: utf-8 -*-
from PIL import Image
import os

def compress_image(source_path, target_path, size):
    if not os.path.exists(source_path):
        print(f"Source file {source_path} does not exist.")
        return
        
    try:
        orig_size_kb = os.path.getsize(source_path) / 1024.0
        with Image.open(source_path) as img:
            # Convert to RGBA if not already
            img_rgba = img.convert('RGBA')
            
            # Resize
            img_resized = img_rgba.resize((size, size), Image.Resampling.LANCZOS)
            
            # Apply color palette reduction (Quantization) to convert to PNG8 (8-bit color index)
            # This drastically reduces PNG size (often by 70-80%) while maintaining transparency
            # and looking identical on mobile screens!
            img_quantized = img_resized.quantize(colors=256, method=2).convert('RGBA')
            
            # Since quantization returns a paletted image, let's copy the alpha mask back
            alpha = img_resized.split()[3]
            img_quantized.putalpha(alpha)
            
            # Save with maximum PNG compression and optimization enabled
            img_quantized.save(target_path, 'PNG', optimize=True, compress_level=9)
            
        new_size_kb = os.path.getsize(target_path) / 1024.0
        pct_reduced = (1 - (new_size_kb / orig_size_kb)) * 100
        print(f"Compressed {source_path} ({orig_size_kb:.1f} KB) -> {target_path} ({new_size_kb:.1f} KB) | Reduced by {pct_reduced:.1f}%")
    except Exception as e:
        print(f"Error compressing {source_path}: {e}")

def main():
    print("=== HIGH-COMPRESSION PWA ICON OPTIMIZATION ===")
    
    # 1. Compress icon-192.png
    compress_image('dashboard/static/icon-192.png', 'dashboard/static/icon-192.png', 192)
    
    # 2. Compress icon-512.png
    compress_image('dashboard/static/icon-512.png', 'dashboard/static/icon-512.png', 512)

if __name__ == '__main__':
    main()
