#!/usr/bin/env python3
"""Resize and convert site images to WebP.

Usage:
    python scripts/compress_images.py SRC DEST.webp [--max-width N] [--quality Q]

Example:
    python scripts/compress_images.py ~/Desktop/evalumina.png images/evalumina.webp --max-width 1000

Remember to set the new width/height attributes on the <img> in index.html.
"""
import argparse
import os

from PIL import Image


def compress_image(src_path, dest_path, max_width=None, quality=82):
    print(f"Compressing {src_path} -> {dest_path}...")
    img = Image.open(src_path)

    if max_width and img.width > max_width:
        new_size = (max_width, round(img.height * max_width / img.width))
        print(f"  Resizing from {img.size} to {new_size}")
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    ext = os.path.splitext(dest_path)[1].lower()
    if ext == '.webp':
        # WebP keeps transparency, so RGBA sources are saved as-is
        img.save(dest_path, 'WEBP', quality=quality, method=6)
    elif ext in ['.jpg', '.jpeg']:
        img.convert('RGB').save(dest_path, 'JPEG', quality=quality, optimize=True, progressive=True)
    else:
        img.save(dest_path, optimize=True)

    print(f"  {img.width}x{img.height}, {os.path.getsize(dest_path) / 1024:.1f} KB "
          f"(original {os.path.getsize(src_path) / 1024:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src")
    parser.add_argument("dest")
    parser.add_argument("--max-width", type=int)
    parser.add_argument("--quality", type=int, default=82)
    args = parser.parse_args()
    compress_image(args.src, args.dest, args.max_width, args.quality)


if __name__ == "__main__":
    main()
