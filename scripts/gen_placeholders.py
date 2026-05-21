"""
Generate placeholder sprite frames for the default_pet.

Run once before first launch:
    python scripts/gen_placeholders.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# State → (fill_color_hex, frame_count)
STATES: dict[str, tuple[str, int]] = {
    "idle":         ("#A8D8EA", 4),
    "typing":       ("#AA96DA", 4),
    "typing_flow":  ("#FCBAD3", 6),
    "sleep":        ("#FFFFD2", 4),
    "jump":         ("#A8E6CF", 6),
    "remind":       ("#FFD3B6", 4),
    "poke":         ("#D3E0EA", 3),
    "drag":         ("#B8D8D8", 3),
}

FRAME_W, FRAME_H = 200, 200
PETS_DIR = Path(__file__).resolve().parent.parent / "pets" / "default_pet"


def hex_to_rgba(hex_color: str, alpha: int = 200) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)


def make_frame(
    state: str,
    frame_idx: int,
    frame_count: int,
    fill: str,
) -> Image.Image:
    img = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 12
    draw.rounded_rectangle(
        [margin, margin, FRAME_W - margin, FRAME_H - margin],
        radius=24,
        fill=hex_to_rgba(fill),
        outline=(80, 80, 80, 80),
        width=2,
    )

    # State label
    draw.text(
        (FRAME_W // 2, FRAME_H // 2 - 16),
        state,
        fill=(60, 60, 60, 220),
        anchor="mm",
    )
    # Frame counter
    draw.text(
        (FRAME_W // 2, FRAME_H // 2 + 12),
        f"{frame_idx + 1} / {frame_count}",
        fill=(100, 100, 100, 180),
        anchor="mm",
    )

    # Small animation dot that shifts per frame
    dot_x = FRAME_W // 2 - (frame_count // 2) * 10 + frame_idx * 10
    draw.ellipse([dot_x - 5, FRAME_H // 2 + 36, dot_x + 5, FRAME_H // 2 + 46],
                 fill=(80, 80, 80, 180))

    return img


def generate() -> None:
    PETS_DIR.mkdir(parents=True, exist_ok=True)
    for state, (color, n_frames) in STATES.items():
        state_dir = PETS_DIR / state
        state_dir.mkdir(exist_ok=True)
        for i in range(n_frames):
            frame = make_frame(state, i, n_frames, color)
            frame.save(state_dir / f"{i}.png")
        print(f"  {state:<14} {n_frames} frames  →  {state_dir}")
    print(f"\nPlaceholders saved to:\n  {PETS_DIR}")


if __name__ == "__main__":
    generate()
