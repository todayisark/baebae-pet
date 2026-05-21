from __future__ import annotations

import json
import shutil
import tempfile
import webbrowser
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    QWidget,
)

from engine.animator import Animator
from engine.macos_window import apply_macos_always_on_top
from engine.reminder import ReminderBubble
from engine.state_machine import ONE_SHOT_STATES, State, StateMachine


class PetWindow(QWidget):
    """
    The transparent, frameless, always-on-top pet window.

    External callers should use on_state_changed() after any state transition
    to refresh the animation immediately.

    on_remind_dismissed: optional callback fired when the reminder bubble is
    closed (either by user or auto-timer).  Use it to reset work timers.
    """

    MANUAL_PREVIEW_RETURN_MS = 3000  # ms before preview snaps back

    def __init__(
        self,
        animator: Animator,
        state_machine: StateMachine,
        settings: dict,
    ) -> None:
        super().__init__()
        self.animator = animator
        self.state_machine = state_machine
        self.settings = settings

        self.on_remind_dismissed: Callable[[], None] | None = None

        self._frame_index = 0
        self._drag_start_global: QPoint | None = None
        self._drag_window_start: QPoint | None = None
        self._dragging = False
        self._reminder_bubble: ReminderBubble | None = None
        self._preview_restore_timer = QTimer(self)
        self._preview_restore_timer.setSingleShot(True)
        self._preview_restore_timer.timeout.connect(self._on_preview_restore)

        self._setup_window()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._reschedule()

    # -------------------------------------------------------------------------
    # Setup
    # -------------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Initial size from first frame
        anim = self.animator.get_animation(self.state_machine.state)
        frame = anim.get_frame(0)
        self.resize(frame.size())

        # Position: bottom-right of primary screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.width() - self.width() - 40,
            screen.height() - self.height() - 80,
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_native_level_with_retries()

    def _apply_native_level_with_retries(self, attempts: int = 5) -> None:
        if apply_macos_always_on_top(self):
            return
        if attempts > 1:
            QTimer.singleShot(
                100,
                lambda: self._apply_native_level_with_retries(attempts - 1),
            )

    # -------------------------------------------------------------------------
    # Animation loop
    # -------------------------------------------------------------------------

    def _reschedule(self) -> None:
        anim = self.animator.get_animation(self.state_machine.state)
        self._anim_timer.start(anim.frame_interval_ms)

    def _tick(self) -> None:
        anim = self.animator.get_animation(self.state_machine.state)

        # Advance frame
        self._frame_index = (self._frame_index + 1) % anim.frame_count

        # One-shot states restore after one full loop
        if self._frame_index == 0 and self.state_machine.is_temporary:
            if self.state_machine.state in ONE_SHOT_STATES:
                self.state_machine.restore()
                self._frame_index = 0

        self._sync_window_size()
        self.update()
        self._reschedule()

    def _sync_window_size(self) -> None:
        """Resize window keeping bottom-center anchor fixed."""
        anim = self.animator.get_animation(self.state_machine.state)
        frame = anim.get_frame(self._frame_index)
        new_size = frame.size()
        if new_size == self.size():
            return
        old = self.geometry()
        cx = old.x() + old.width() // 2
        bottom = old.y() + old.height()
        self.resize(new_size)
        self.move(cx - new_size.width() // 2, bottom - new_size.height())
        self._apply_native_level_with_retries()

    # -------------------------------------------------------------------------
    # Paint
    # -------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        anim = self.animator.get_animation(self.state_machine.state)
        frame = anim.get_frame(self._frame_index)
        painter = QPainter(self)
        painter.drawPixmap(0, 0, frame)

    # -------------------------------------------------------------------------
    # Public: notify window that state changed externally
    # -------------------------------------------------------------------------

    def on_state_changed(self) -> None:
        self._frame_index = 0
        self._sync_window_size()
        self.update()
        self._reschedule()

    # -------------------------------------------------------------------------
    # Mouse events
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_window_start = self.pos()
            self._dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_global is None:
            return
        delta = event.globalPosition().toPoint() - self._drag_start_global
        if not self._dragging and (abs(delta.x()) > 3 or abs(delta.y()) > 3):
            self._dragging = True
            self._on_drag_start()
        if self._dragging:
            self.move(self._drag_window_start + delta)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_dragging = self._dragging
        self._drag_start_global = None
        self._dragging = False
        if was_dragging:
            self._on_drag_end()
        else:
            self._on_click()

    # -------------------------------------------------------------------------
    # Interaction handlers
    # -------------------------------------------------------------------------

    def _on_click(self) -> None:
        if self.state_machine.state == State.SLEEP:
            self.state_machine.transition_to(State.IDLE)
        elif not self.state_machine.is_temporary:
            self.state_machine.transition_to(
                State.POKE, temporary=True, return_to=self.state_machine.state
            )
        self.on_state_changed()

    def _on_drag_start(self) -> None:
        if not self.state_machine.is_temporary:
            self.state_machine.transition_to(
                State.DRAG, temporary=True, return_to=self.state_machine.state
            )
            self.on_state_changed()

    def _on_drag_end(self) -> None:
        if self.state_machine.state == State.DRAG:
            self.state_machine.restore()
            self.on_state_changed()

    # -------------------------------------------------------------------------
    # Reminder bubble
    # -------------------------------------------------------------------------

    def show_reminder(self, message: str) -> None:
        if self._reminder_bubble is not None:
            return
        bubble = ReminderBubble(message)
        bubble.dismissed.connect(self._on_reminder_dismissed)
        bubble.adjustSize()
        pos = self.pos()
        bx = max(0, pos.x() + self.width() // 2 - bubble.width() // 2)
        by = max(0, pos.y() - bubble.height() - 8)
        bubble.move(bx, by)
        bubble.show()
        self._reminder_bubble = bubble

    def _on_reminder_dismissed(self) -> None:
        self._reminder_bubble = None
        self.state_machine.transition_to(State.IDLE)
        self.on_state_changed()
        if self.on_remind_dismissed:
            self.on_remind_dismissed()

    # -------------------------------------------------------------------------
    # Context menu
    # -------------------------------------------------------------------------

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)

        preview_menu = menu.addMenu("状态预览")
        for state in State:
            action = preview_menu.addAction(state.value)
            action.triggered.connect(
                lambda _checked, s=state: self._preview_state(s)
            )

        size_menu = menu.addMenu("切换大小")
        for label, scale in [("小", 0.5), ("中", 0.85), ("大", 1.2)]:
            action = size_menu.addAction(label)
            action.triggered.connect(
                lambda _checked, s=scale: self._set_scale(s)
            )

        menu.addSeparator()
        menu.addAction("导入素材包").triggered.connect(self._import_pet)
        menu.addAction("使用手册").triggered.connect(self._open_manual)
        menu.addSeparator()
        menu.addAction("清除所有数据").triggered.connect(self._clear_data)
        menu.addAction("退出").triggered.connect(QApplication.quit)

        menu.exec(pos)

    # -------------------------------------------------------------------------
    # Menu actions
    # -------------------------------------------------------------------------

    def _preview_state(self, state: State) -> None:
        """Play state animation once, then return after MANUAL_PREVIEW_RETURN_MS."""
        self._preview_restore_timer.stop()
        self.state_machine.transition_to(
            state, temporary=True, return_to=State.IDLE
        )
        self.on_state_changed()
        self._preview_restore_timer.start(self.MANUAL_PREVIEW_RETURN_MS)

    def _on_preview_restore(self) -> None:
        if self.state_machine.is_temporary:
            self.state_machine.restore()
            self.on_state_changed()

    def _set_scale(self, scale: float) -> None:
        self.settings["scale"] = scale
        self.animator.set_scale(scale)
        self.on_state_changed()
        from config import settings as cfg
        cfg.save(self.settings)

    def _import_pet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入素材包", "", "素材包 (*.zip)"
        )
        if path:
            self._do_import_pet(path)

    def _do_import_pet(self, zip_path: str) -> None:
        from config import settings as cfg

        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                manifest_files = [n for n in names if n.endswith("manifest.json")]
                if not manifest_files:
                    QMessageBox.warning(self, "导入失败", "素材包中没有 manifest.json")
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

            new_dir = cfg.get_active_pet_dir(self.settings)
            if new_dir:
                self.animator = Animator(new_dir, self.settings.get("scale", 0.85))
                self.state_machine.transition_to(State.JUMP)
                self.on_state_changed()
            QMessageBox.information(
                self, "导入成功", f"已切换到 {manifest.get('name', pet_name)}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))

    def _open_manual(self) -> None:
        webbrowser.open("https://github.com/todayisark/baebae-framework#readme")

    def _clear_data(self) -> None:
        reply = QMessageBox.question(
            self,
            "清除所有数据",
            "这将删除所有素材包和设置，确认吗？\n（程序将退出）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from config import settings as cfg
            cfg.clear_all_data()
            QApplication.quit()
