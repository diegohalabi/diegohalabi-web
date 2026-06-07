#!/usr/bin/env python3
import os
from PIL import Image

def compress_image(src_path, dest_path, max_width=None, max_height=None, quality=85):
    print(f"Compressing {src_path} -> {dest_path}...")
    img = Image.open(src_path)
    
    # Handle resizing if max width or height is defined
    if max_width or max_height:
        width, height = img.size
        ratio = width / height
        
        new_width = width
        new_height = height
        
        if max_width and new_width > max_width:
            new_width = max_width
            new_height = int(new_width / ratio)
            
        if max_height and new_height > max_height:
            new_height = max_height
            new_width = int(new_height * ratio)
            
        if (new_width, new_height) != img.size:
            print(f"  Resizing from {img.size} to {(new_width, new_height)}")
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
    # Save image with optimization
    ext = os.path.splitext(dest_path)[1].lower()
    if ext in ['.jpg', '.jpeg']:
        # Convert to RGB if needed (e.g. RGBA source)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(dest_path, 'JPEG', quality=quality, optimize=True)
    elif ext == '.png':
        # PNG optimization
        img.save(dest_path, 'PNG', optimize=True)
    else:
        img.save(dest_path)
        
    print(f"  Saved size: {os.path.getsize(dest_path) / 1024:.1f} KB (Original: {os.path.getsize(src_path) / (1024*1024):.2f} MB)")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    images_dir = os.path.join(base_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 1. Profile image
    myself_src = os.path.join(base_dir, "myself.jpg")
    myself_dest = os.path.join(images_dir, "myself.jpg")
    if os.path.exists(myself_src):
        compress_image(myself_src, myself_dest, max_width=600, max_height=600, quality=85)
        
    # 2. Adipocites image
    adipocites_src = os.path.join(base_dir, "adipocites.png")
    adipocites_dest = os.path.join(images_dir, "adipocites.png")
    if os.path.exists(adipocites_src):
        compress_image(adipocites_src, adipocites_dest, max_width=1000, quality=85)
        
    # 3. RStudio stack image
    rstudio_src = os.path.join(base_dir, "rstudio.png")
    rstudio_dest = os.path.join(images_dir, "rstudio.png")
    if os.path.exists(rstudio_src):
        compress_image(rstudio_src, rstudio_dest, max_width=800, quality=85)

if __name__ == "__main__":
    main()
