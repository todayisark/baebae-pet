from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

APP_SUPPORT = Path.home() / "Library" / "Application Support" / "baebae"

DEFAULT_SETTINGS: dict = {
    "pet": "default_pet",
    "language": "en",
    "scale": 0.85,
    "remind_interval_minutes": 60,
    "remind_message": "工作一小时了，起来动一动吧！",
    "typing_flow_seconds": 20,
    "typing_flow_gap_seconds": 5,
}


def bundled_pets_dir() -> Path:
    bundle_root_value = getattr(sys, "_MEIPASS", None)
    if bundle_root_value:
        bundle_root = Path(bundle_root_value)
        bundled = bundle_root / "pets"
        if bundled.exists():
            return bundled
    return Path(__file__).resolve().parent.parent / "pets"


def bundled_pet_dir(name: str = "default_pet") -> Path:
    return bundled_pets_dir() / name


def initialize() -> None:
    """Create app support directory and seed defaults on first run."""
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    pets_dir = APP_SUPPORT / "pets"
    pets_dir.mkdir(exist_ok=True)

    settings_path = APP_SUPPORT / "settings.json"
    if not settings_path.exists():
        settings_path.write_text(
            json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Copy bundled default_pet if not already present
    bundled = bundled_pet_dir("default_pet")
    target = pets_dir / "default_pet"
    if bundled.exists() and not target.exists():
        shutil.copytree(bundled, target)


def load() -> dict:
    initialize()
    settings_path = APP_SUPPORT / "settings.json"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return {**DEFAULT_SETTINGS, **data}


def save(settings: dict) -> None:
    initialize()
    (APP_SUPPORT / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def pets_dir() -> Path:
    return APP_SUPPORT / "pets"


def get_active_pet_dir(settings: dict) -> Path | None:
    for name in (settings.get("pet", "default_pet"), "default_pet"):
        d = pets_dir() / name
        if d.exists():
            return d
    return None


def clear_all_data() -> None:
    """Remove the entire app support directory."""
    if APP_SUPPORT.exists():
        shutil.rmtree(APP_SUPPORT)
