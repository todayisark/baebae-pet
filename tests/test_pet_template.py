from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from engine.pet_template import TEMPLATE_DIR_NAME, export_pet_template


class PetTemplateTest(unittest.TestCase):
    def test_exports_default_pet_as_template_zip(self) -> None:
        source_pet_dir = Path("pets/default_pet")

        with tempfile.TemporaryDirectory() as tmp:
            output_path = export_pet_template(
                source_pet_dir,
                Path(tmp) / "pet-template.zip",
            )

            with zipfile.ZipFile(output_path) as zf:
                names = set(zf.namelist())
                manifest = json.loads(
                    zf.read(f"{TEMPLATE_DIR_NAME}/manifest.json").decode("utf-8")
                )
                template_readme = zf.read(f"{TEMPLATE_DIR_NAME}/README.md").decode(
                    "utf-8"
                )

        self.assertIn(f"{TEMPLATE_DIR_NAME}/README.md", names)
        self.assertIn(f"{TEMPLATE_DIR_NAME}/manifest.json", names)
        self.assertIn(f"{TEMPLATE_DIR_NAME}/idle/0.png", names)
        self.assertIn(f"{TEMPLATE_DIR_NAME}/typing/0.png", names)
        self.assertEqual(manifest["name"], TEMPLATE_DIR_NAME)
        self.assertIn("Replace the PNG frames", template_readme)

    def test_adds_zip_suffix_when_missing(self) -> None:
        source_pet_dir = Path("pets/default_pet")

        with tempfile.TemporaryDirectory() as tmp:
            output_path = export_pet_template(source_pet_dir, Path(tmp) / "pet-template")

        self.assertEqual(output_path.name, "pet-template.zip")


if __name__ == "__main__":
    unittest.main()
