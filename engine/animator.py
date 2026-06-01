from __future__ import annotations

import json
import random
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap

from engine.state_machine import State


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
                0.png  1.png  ...   ← default idle frames
                stretch/            ← random idle sub-action
                    0.png  ...
                yawn/
                    0.png  ...
            typing/
                0.png  ...
            poke/
                0.png  ...          ← default poke (any zone)
                up/                 ← poke top-third of window
                    0.png  ...
                mid/
                    0.png  ...
                down/
                    0.png  ...
            ...

    States are auto-enabled/disabled based on whether the folder exists and
    contains PNG frames — no manual configuration needed.

    Idle sub-actions are played once every 3 minutes (managed by PetController).
    Poke zones are selected by click position (managed by PetWindow).
    """

    def __init__(self, pet_dir: Path, scale: float | tuple[int, int] = 1.0) -> None:
        self.pet_dir = pet_dir
        self.scale = scale
        self._manifest: dict = {}
        self._animations: dict[str, Animation] = {}
        self._idle_variants: list[str] = []          # keys like "idle/stretch"
        self._poke_zones: dict[str, str] = {}        # zone → key, e.g. "up" → "poke/up"
        self._current_idle_variant: str | None = None
        self._current_poke_zone: str | None = None   # key like "poke/up" or None
        self._load_manifest()
        self._preload_animations()

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _load_manifest(self) -> None:
        manifest_path = self.pet_dir / "manifest.json"
        with open(manifest_path, encoding="utf-8") as fh:
            self._manifest = json.load(fh)

    def _target_frame_size(self, source_size: tuple[int, int] | None = None) -> tuple[int, int]:
        if isinstance(self.scale, (tuple, list)) and len(self.scale) == 2:
            return (max(1, int(self.scale[0])), max(1, int(self.scale[1])))

        # Backward compatibility for previously persisted numeric scale values.
        if source_size is not None:
            width, height = source_size
        else:
            width, height = self._manifest.get("frameSize", [200, 200])
        return (
            max(1, round(width * float(self.scale))),
            max(1, round(height * float(self.scale))),
        )

    def _fit_frame(self, px: QPixmap, target_size: tuple[int, int]) -> QPixmap:
        target_w, target_h = target_size
        scaled = px.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() == target_w and scaled.height() == target_h:
            return scaled

        canvas = QPixmap(target_w, target_h)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        offset_x = (target_w - scaled.width()) // 2
        offset_y = target_h - scaled.height()
        painter.drawPixmap(offset_x, offset_y, scaled)
        painter.end()
        return canvas

    def _build_animation(self, key: str) -> Animation:
        """Build an Animation from pet_dir/<key>/ folder.

        key may contain slashes, e.g. "idle/stretch" or "poke/up".
        fps is looked up from manifest["animations"][key]; defaults to 10.
        """
        anim_dir = self.pet_dir / key
        anim_cfg = self._manifest.get("animations", {}).get(key, {})
        fps = anim_cfg.get("fps", 10)
        frame_size = self._manifest.get("frameSize", [200, 200])
        target_size = self._target_frame_size((frame_size[0], frame_size[1]))

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
                frames.append(self._fit_frame(px, target_size))

        if not frames:
            w, h = target_size
            px = QPixmap(w, h)
            px.fill(Qt.GlobalColor.transparent)
            frames = [px]

        return Animation(frames, fps)

    def _preload_animations(self) -> None:
        # Manifest-declared states (idle, typing, poke, drag, ...)
        for state in self._manifest.get("animations", {}):
            self._animations[state] = self._build_animation(state)

        # Auto-discover idle sub-actions: idle/*/
        idle_dir = self.pet_dir / "idle"
        if idle_dir.exists():
            for sub in sorted(idle_dir.iterdir()):
                if sub.is_dir() and not sub.name.startswith(".") and any(sub.glob("*.png")):
                    key = f"idle/{sub.name}"
                    self._animations[key] = self._build_animation(key)
                    self._idle_variants.append(key)

        # Auto-discover poke zones: poke/up, poke/mid, poke/down, poke/up_double
        for zone in ("up", "mid", "down", "up_double"):
            key = f"poke/{zone}"
            zone_dir = self.pet_dir / key
            if zone_dir.exists() and any(zone_dir.glob("*.png")):
                self._animations[key] = self._build_animation(key)
                self._poke_zones[zone] = key

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def has_animation(self, state: str) -> bool:
        """Return True if the animation for *state* exists with at least one PNG frame.

        For IDLE_RANDOM, returns True when idle sub-action folders are available.
        """
        if state == State.IDLE_RANDOM:
            return bool(self._idle_variants)
        anim_dir = self.pet_dir / state
        return anim_dir.is_dir() and any(anim_dir.glob("*.png"))

    @property
    def idle_variants(self) -> list[str]:
        """Keys like 'idle/stretch', 'idle/yawn', ..."""
        return list(self._idle_variants)

    @property
    def poke_zones(self) -> list[str]:
        """Available zone names: subset of ['up', 'mid', 'down']."""
        return list(self._poke_zones.keys())

    def has_idle_variants(self) -> bool:
        return bool(self._idle_variants)

    def has_poke_animation(self) -> bool:
        """True if any poke animation (default or zone-specific) is available."""
        return self.has_animation("poke") or bool(self._poke_zones)

    def random_idle_variant(self) -> str | None:
        if not self._idle_variants:
            return None
        return random.choice(self._idle_variants)

    def set_idle_variant(self, key: str) -> None:
        self._current_idle_variant = key

    def set_poke_zone(self, zone: str | None) -> None:
        """Set the active poke zone ("up", "mid", or "down"), or None for default.

        If no zone-specific animation exists, falls back to default poke.
        """
        self._current_poke_zone = self._poke_zones.get(zone) if zone is not None else None

    def get_animation(self, state: str) -> Animation:
        # Idle random sub-action: return the currently selected variant
        if state == State.IDLE_RANDOM:
            key = self._current_idle_variant
            if key and key in self._animations:
                return self._animations[key]
            return self._animations.get("idle") or next(iter(self._animations.values()))

        # Poke with zone routing
        if state == State.POKE and self._current_poke_zone:
            key = self._current_poke_zone
            if key in self._animations:
                return self._animations[key]
            # Fall through to default poke below

        if state not in self._animations:
            # Attempt lazy load (e.g. a state added by a richer manifest)
            anim_dir = self.pet_dir / state
            if anim_dir.exists():
                self._animations[state] = self._build_animation(state)
            else:
                return (
                    self._animations.get("idle")
                    or next(iter(self._animations.values()))
                )
        return self._animations[state]

    def set_scale(self, scale: float | tuple[int, int]) -> None:
        self.scale = scale
        self._animations.clear()
        self._idle_variants.clear()
        self._poke_zones.clear()
        self._current_idle_variant = None
        self._current_poke_zone = None
        self._preload_animations()

    @property
    def manifest(self) -> dict:
        return self._manifest

    @property
    def frame_size(self) -> tuple[int, int]:
        fw, fh = self._manifest.get("frameSize", [200, 200])
        return self._target_frame_size((fw, fh))
