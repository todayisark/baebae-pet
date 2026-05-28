"""
Split GIF files inside pets/default_pet/ into numbered PNG frames.

Each GIF is extracted into a sibling folder with the same name (no extension).
Existing PNG files in the target folder are overwritten.

Usage:
    .venv/bin/python scripts/split_gif.py [--pet-dir PATH]

Options:
    --pet-dir PATH   Path to the pet directory to scan (default: pets/default_pet)
    --dry-run        Print what would be done without writing files
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


def split_gif(gif_path: Path, out_dir: Path, *, dry_run: bool = False) -> int:
    """Extract frames from *gif_path* into *out_dir* as 0.png, 1.png, ...

    Returns the number of frames written.
    """
    with Image.open(gif_path) as img:
        if not hasattr(img, "n_frames") or img.n_frames < 1:
            print(f"  [skip] {gif_path.name}: no frames found")
            return 0

        n = img.n_frames
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)

        for i in range(n):
            img.seek(i)
            frame = img.convert("RGBA")
            dest = out_dir / f"{i}.png"
            if dry_run:
                print(f"  [dry] would write {dest}")
            else:
                frame.save(dest, "PNG")

        return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--pet-dir",
        default="pets/default_pet",
        help="Pet directory to scan (default: pets/default_pet)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    args = parser.parse_args()

    pet_dir = Path(args.pet_dir)
    if not pet_dir.exists():
        print(f"Error: directory not found: {pet_dir}", file=sys.stderr)
        sys.exit(1)

    gifs = sorted(pet_dir.rglob("*.gif"))
    if not gifs:
        print(f"No GIF files found under {pet_dir}")
        return

    for gif_path in gifs:
        out_dir = gif_path.parent
        print(f"{gif_path.relative_to(pet_dir)}  →  {out_dir.relative_to(pet_dir)}/")
        count = split_gif(gif_path, out_dir, dry_run=args.dry_run)
        if count:
            action = "would write" if args.dry_run else "wrote"
            print(f"  {action} {count} frame(s)")
            if args.dry_run:
                print(f"  [dry] would delete {gif_path.name}")
            else:
                gif_path.unlink()
                print(f"  deleted {gif_path.name}")


if __name__ == "__main__":
    main()
