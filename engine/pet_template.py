from __future__ import annotations

import json
import zipfile
from pathlib import Path

TEMPLATE_ARCHIVE_NAME = "pet-template.zip"
TEMPLATE_DIR_NAME = "pet_template"
TEMPLATE_README = """# Baebae Pet Template

1. Replace the PNG frames in each state folder.
2. Update `manifest.json`, especially `name`, `author`, and `version`.
3. Keep transparent PNG files named `0.png`, `1.png`, `2.png`, ...
4. Zip this folder and import it from baebae.
"""


def export_pet_template(source_pet_dir: Path, destination_zip: Path) -> Path:
    """
    Export the bundled default pet as an editable template zip.

    The zip keeps the source animation frames, but rewrites the package root
    and manifest name so importing the template will not overwrite default_pet.
    """
    source_pet_dir = source_pet_dir.resolve()
    destination_zip = _with_zip_suffix(destination_zip)

    manifest_path = source_pet_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing template manifest: {manifest_path}")

    destination_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{TEMPLATE_DIR_NAME}/README.md", TEMPLATE_README)

        for path in sorted(source_pet_dir.rglob("*")):
            if not path.is_file() or _should_skip(path):
                continue

            relative_path = path.relative_to(source_pet_dir)
            archive_path = Path(TEMPLATE_DIR_NAME) / relative_path

            if relative_path == Path("manifest.json"):
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifest["name"] = TEMPLATE_DIR_NAME
                zf.writestr(
                    archive_path.as_posix(),
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
            else:
                zf.write(path, archive_path.as_posix())

    return destination_zip


def _with_zip_suffix(path: Path) -> Path:
    if path.suffix.lower() == ".zip":
        return path
    if path.suffix:
        return path.with_suffix(path.suffix + ".zip")
    return path.with_suffix(".zip")


def _should_skip(path: Path) -> bool:
    return (
        path.name == ".DS_Store"
        or path.name.startswith("._")
        or "__pycache__" in path.parts
    )
