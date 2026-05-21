from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


class Animation:
    """A single named animation: a list of QPixmap frames + playback fps."""

    def __init__(self, frames: list[QPixmap], fps: int) -> None:
        self.frames = frames
        self.fps = max(1, fps)

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def frame_interval_ms(self) -> int:
        return max(40, 1000 // self.fps)

    def get_frame(self, index: int) -> QPixmap:
        return self.frames[index % len(self.frames)]


class Animator:
    """
    Loads and caches all animations for a pet.

    Pet directory layout:
        <pet>/
            manifest.json
            idle/
                0.png  1.png  ...
            typing/
                0.png  ...
            ...
    """

    def __init__(self, pet_dir: Path, scale: float = 1.0) -> None:
        self.pet_dir = pet_dir
        self.scale = scale
        self._manifest: dict = {}
        self._animations: dict[str, Animation] = {}
        self._load_manifest()
        self._preload_animations()

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _load_manifest(self) -> None:
        manifest_path = self.pet_dir / "manifest.json"
        with open(manifest_path, encoding="utf-8") as fh:
            self._manifest = json.load(fh)

    def _build_animation(self, state: str) -> Animation:
        anim_dir = self.pet_dir / state
        anim_cfg = self._manifest.get("animations", {}).get(state, {})
        fps = anim_cfg.get("fps", 10)
        frame_size = self._manifest.get("frameSize", [200, 200])

        frames: list[QPixmap] = []
        if anim_dir.exists():
            png_files = sorted(
                anim_dir.glob("*.png"),
                key=lambda p: int(p.stem) if p.stem.isdigit() else 0,
            )
            for png_path in png_files:
                px = QPixmap(str(png_path))
                if px.isNull():
                    continue
                if self.scale != 1.0:
                    w = max(1, round(px.width() * self.scale))
                    h = max(1, round(px.height() * self.scale))
                    px = px.scaled(
                        w,
                        h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                frames.append(px)

        if not frames:
            # Transparent placeholder
            w = max(1, round(frame_size[0] * self.scale))
            h = max(1, round(frame_size[1] * self.scale))
            px = QPixmap(w, h)
            px.fill(Qt.GlobalColor.transparent)
            frames = [px]

        return Animation(frames, fps)

    def _preload_animations(self) -> None:
        for state in self._manifest.get("animations", {}):
            self._animations[state] = self._build_animation(state)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_animation(self, state: str) -> Animation:
        if state not in self._animations:
            # Attempt lazy load (e.g. a state added by a richer manifest)
            anim_dir = self.pet_dir / state
            if anim_dir.exists():
                self._animations[state] = self._build_animation(state)
            else:
                # Fallback: idle → first available
                return (
                    self._animations.get("idle")
                    or next(iter(self._animations.values()))
                )
        return self._animations[state]

    def set_scale(self, scale: float) -> None:
        self.scale = scale
        self._animations.clear()
        self._preload_animations()

    @property
    def manifest(self) -> dict:
        return self._manifest

    @property
    def frame_size(self) -> tuple[int, int]:
        fw, fh = self._manifest.get("frameSize", [200, 200])
        return (max(1, round(fw * self.scale)), max(1, round(fh * self.scale)))
