from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class OnboardingWindow(QWidget):
    """
    Shown on first launch (or when no pet directory is found).
    Lets the user import a .zip pet pack to get started.
    After a successful import the window closes itself and launches the pet.
    """

    def __init__(self, settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("欢迎使用 baebae")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setFixedSize(320, 210)
        self._setup_ui()

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(28, 28, 28, 28)

        title = QLabel("欢迎使用 baebae 🐾")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        desc = QLabel(
            "请导入一个素材包（.zip 格式）来启动你的桌面宠物。\n\n"
            "素材包需包含 manifest.json 以及各状态的 PNG 帧。"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn = QPushButton("选择素材包…")
        btn.setMinimumHeight(32)
        btn.clicked.connect(self._import_pet)
        layout.addWidget(btn)

    # -------------------------------------------------------------------------
    # Import logic
    # -------------------------------------------------------------------------

    def _import_pet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入素材包", "", "素材包 (*.zip)"
        )
        if path:
            self._do_import(path)

    def _do_import(self, zip_path: str) -> None:
        from config import settings as cfg

        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                manifest_files = [n for n in names if n.endswith("manifest.json")]
                if not manifest_files:
                    QMessageBox.warning(self, "导入失败", "素材包中没有找到 manifest.json")
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
            QMessageBox.critical(self, "导入失败", str(exc))

    def _launch_pet(self) -> None:
        from config import settings as cfg
        from engine.animator import Animator
        from engine.state_machine import StateMachine
        from engine.window import PetWindow
        from main import PetController

        pet_dir = cfg.get_active_pet_dir(self.settings)
        if pet_dir is None:
            QMessageBox.critical(self, "错误", "无法找到素材包目录")
            return

        self._controller = PetController(self.settings, pet_dir)
        self.close()
