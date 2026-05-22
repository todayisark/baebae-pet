from __future__ import annotations

import unittest

from engine.i18n import normalize_language, next_language, t


class I18nTest(unittest.TestCase):
    def test_normalizes_unknown_language_to_chinese(self) -> None:
        self.assertEqual(normalize_language(None), "zh")
        self.assertEqual(normalize_language("fr"), "zh")

    def test_switches_between_chinese_and_english(self) -> None:
        self.assertEqual(next_language("zh"), "en")
        self.assertEqual(next_language("en"), "zh")

    def test_translates_menu_labels(self) -> None:
        self.assertEqual(t("menu.import_pet", "zh"), "导入素材包")
        self.assertEqual(t("menu.import_pet", "en"), "Import Pet Pack")
        self.assertEqual(t("menu.open_pet_folder", "zh"), "打开素材目录")
        self.assertEqual(t("menu.open_pet_folder", "en"), "Open Pet Folder")

    def test_formats_dialog_text(self) -> None:
        self.assertEqual(
            t("dialog.import_success_message", "en", name="demo"),
            "Switched to demo",
        )


if __name__ == "__main__":
    unittest.main()
