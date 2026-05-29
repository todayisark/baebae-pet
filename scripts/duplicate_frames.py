"""
Copy all PNG frames in an animation folder and append them after the last existing frame.

Example: folder contains 0.png 1.png 2.png  →  adds 3.png 4.png 5.png (copies of 0-2)

Usage:
    .venv/bin/python scripts/duplicate_frames.py <folder>
    .venv/bin/python scripts/duplicate_frames.py <folder> --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def duplicate_frames(folder: Path, *, dry_run: bool = False) -> None:
    frames = sorted(
        folder.glob("*.png"),
        key=lambda p: int(p.stem) if p.stem.isdigit() else -1,
    )
    frames = [f for f in frames if f.stem.isdigit()]

    if not frames:
        print(f"No numbered PNG frames found in {folder}")
        return

    next_index = int(frames[-1].stem) + 1

    print(f"Found {len(frames)} frame(s), appending copies starting at {next_index}.png")
    for i, src in enumerate(frames):
        dest = folder / f"{next_index + i}.png"
        if dry_run:
            print(f"  [dry] {src.name}  →  {dest.name}")
        else:
            shutil.copy2(src, dest)
            print(f"  {src.name}  →  {dest.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("folder", help="Animation folder containing numbered PNG frames")
    parser.add_argument("--dry-run", action="store_true", help="Preview without copying files")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Error: not a directory: {folder}", file=sys.stderr)
        sys.exit(1)

    duplicate_frames(folder, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
