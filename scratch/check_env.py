# -*- coding: utf-8 -*-
import os

def main():
    print("=== CHECKING .ENV FOR RESEND KEYS ===")
    
    env_paths = ['.env', '../.env']
    found_any = False
    for path in env_paths:
        if os.path.exists(path):
            print(f"\nFound .env at {path}:")
            found_any = True
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line_strip = line.strip()
                    if not line_strip or line_strip.startswith('#'):
                        continue
                    if 'resend' in line_strip.lower() or 'api_key' in line_strip.lower():
                        parts = line_strip.split('=', 1)
                        key = parts[0].strip()
                        val = parts[1].strip() if len(parts) > 1 else 'None'
                        # Mask value for display
                        val_preview = val[:10] + "..." if len(val) > 10 else val
                        print(f"  {key} = {val_preview}")
                        
    if not found_any:
        print("No .env file found in root or parent directories.")

if __name__ == '__main__':
    main()
