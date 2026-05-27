from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.i18n import normalize_language, t

TEMPLATE_EXPORT_PATH = Path.home() / "Downloads" / "pet_template.zip"


class OnboardingWindow(QWidget):
    """
    Shown on first launch (or when no pet directory is found in Application Support).
    The bundled default_pet is a read-only template; assets must be explicitly imported.
    """

    def __init__(
        self,
        settings: dict,
        on_pet_ready: Callable[[dict, Path], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self._on_pet_ready = on_pet_ready
        self._lang = normalize_language(settings.get("language"))
        self._pet_launched = False
        self.setWindowFlags(Qt.WindowType.Window)
        self.setFixedSize(400, 360)
        self._build_ui()

    # -------------------------------------------------------------------------
    # i18n
    # -------------------------------------------------------------------------

    def _t(self, key: str, **kwargs: object) -> str:
        return t(key, self._lang, **kwargs)

    def _lang_toggle_label(self) -> str:
        return "中文" if self._lang == "en" else "English"

    def _toggle_language(self) -> None:
        self._lang = "en" if self._lang == "zh" else "zh"
        self.settings["language"] = self._lang
        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(self._t("onboarding.window_title"))
        self._title_label.setText(self._t("onboarding.title"))
        self._desc_label.setText(self._t("onboarding.desc"))
        self._btn_export.setText(self._t("onboarding.export_template"))
        self._btn_open_dir.setText(self._t("onboarding.open_template_dir"))
        self._btn_use_default.setText(self._t("onboarding.use_default"))
        self._btn_import.setText(self._t("onboarding.import_pack"))
        self._btn_quit.setText(self._t("onboarding.quit"))
        self._lang_btn.setText(self._lang_toggle_label())

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._pet_launched:
            QApplication.quit()
        event.accept()

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(self._t("onboarding.window_title"))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(28, 20, 28, 24)

        # Header row: title label + language toggle button (top-right)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel(self._t("onboarding.title"))
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self._title_label.setFont(font)
        header.addWidget(self._title_label)
        header.addStretch()

        self._lang_btn = QPushButton(self._lang_toggle_label())
        self._lang_btn.setFixedSize(64, 26)
        self._lang_btn.clicked.connect(self._toggle_language)
        header.addWidget(self._lang_btn, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header)

        # Description
        self._desc_label = QLabel(self._t("onboarding.desc"))
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)

        # Row: export template + open template dir
        row = QHBoxLayout()
        row.setSpacing(8)

        self._btn_export = QPushButton(self._t("onboarding.export_template"))
        self._btn_export.setMinimumHeight(32)
        self._btn_export.clicked.connect(self._export_template)
        row.addWidget(self._btn_export)

        self._btn_open_dir = QPushButton(self._t("onboarding.open_template_dir"))
        self._btn_open_dir.setMinimumHeight(32)
        self._btn_open_dir.clicked.connect(self._open_template_dir)
        row.addWidget(self._btn_open_dir)

        layout.addLayout(row)

        # Use bundled template directly
        self._btn_use_default = QPushButton(self._t("onboarding.use_default"))
        self._btn_use_default.setMinimumHeight(32)
        self._btn_use_default.clicked.connect(self._use_default_template)
        layout.addWidget(self._btn_use_default)

        # Import custom zip
        self._btn_import = QPushButton(self._t("onboarding.import_pack"))
        self._btn_import.setMinimumHeight(32)
        self._btn_import.clicked.connect(self._import_pet)
        layout.addWidget(self._btn_import)

        # Quit
        self._btn_quit = QPushButton(self._t("onboarding.quit"))
        self._btn_quit.setMinimumHeight(32)
        self._btn_quit.clicked.connect(QApplication.quit)
        layout.addWidget(self._btn_quit)

    # -------------------------------------------------------------------------
    # Button handlers
    # -------------------------------------------------------------------------

    def _export_template(self) -> None:
        from config import settings as cfg
        from engine.pet_template import export_pet_template

        try:
            bundled = cfg.bundled_pet_dir("default_pet")
            export_pet_template(bundled, TEMPLATE_EXPORT_PATH)
            QMessageBox.information(
                self,
                self._t("dialog.export_success_title"),
                self._t("onboarding.export_success_msg", path=TEMPLATE_EXPORT_PATH),
            )
        except Exception as exc:
            QMessageBox.critical(self, self._t("dialog.export_failed_title"), str(exc))

    def _open_template_dir(self) -> None:
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(TEMPLATE_EXPORT_PATH.parent))
        )

    def _use_default_template(self) -> None:
        from config import settings as cfg
        from engine.pet_template import export_pet_template

        try:
            bundled = cfg.bundled_pet_dir("default_pet")
            tmp_path = Path(tempfile.mktemp(suffix=".zip"))
            try:
                export_pet_template(bundled, tmp_path)
                self._do_import(str(tmp_path))
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            QMessageBox.critical(self, self._t("onboarding.error_title"), str(exc))

    def _import_pet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("dialog.import_pet_title"),
            "",
            self._t("dialog.pet_package_filter"),
        )
        if path:
            self._do_import(path)

    # -------------------------------------------------------------------------
    # Import logic (shared by all import paths)
    # -------------------------------------------------------------------------

    def _do_import(self, zip_path: str) -> None:
        from config import settings as cfg

        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                manifest_files = [n for n in names if n.endswith("manifest.json")]
                if not manifest_files:
                    QMessageBox.warning(
                        self,
                        self._t("dialog.import_failed_title"),
                        self._t("dialog.missing_manifest"),
                    )
                    return

                with tempfile.TemporaryDirectory() as tmp:
                    zf.extractall(tmp)
                    manifest_path = Path(tmp) / manifest_files[0]
                    with open(manifest_path, encoding="utf-8") as fh:
                        manifest = json.load(fh)

                    pet_name = (
                        manifest.get("name", "imported_pet")
                        .strip()
                        .replace(" ", "_")
                        .lower()
                    )
                    pet_src = manifest_path.parent
                    pet_dst = cfg.pets_dir() / pet_name
                    if pet_dst.exists():
                        shutil.rmtree(pet_dst)
                    shutil.copytree(pet_src, pet_dst)

            self.settings["pet"] = pet_name
            cfg.save(self.settings)
            self._launch_pet()

        except Exception as exc:
            QMessageBox.critical(self, self._t("dialog.import_failed_title"), str(exc))

    def _launch_pet(self) -> None:
        from config import settings as cfg

        pet_dir = cfg.get_active_pet_dir(self.settings)
        if pet_dir is None:
            QMessageBox.critical(
                self,
                self._t("onboarding.error_title"),
                self._t("onboarding.no_pet_dir"),
            )
            return

        self._pet_launched = True
        self._on_pet_ready(self.settings, pet_dir)
        self.close()
