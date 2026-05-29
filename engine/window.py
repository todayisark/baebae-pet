from __future__ import annotations

import json
import math
import shutil
import time
from collections import deque
import tempfile
import webbrowser
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, Qt, QTime, QTimer, QUrl
from PySide6.QtGui import QBitmap, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from engine.animator import Animator
from engine.i18n import normalize_language, t
from engine.macos_window import apply_macos_always_on_top
from engine.pet_template import TEMPLATE_ARCHIVE_NAME, export_pet_template
from engine.reminder import ReminderBubble, UpdateBubble
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
    DRAG_FAST_THRESHOLD_PX_S = 600   # pixels/second to be considered "fast drag"
    DRAG_VEL_WINDOW_S = 0.15         # velocity averaging window in seconds
    DOUBLE_CLICK_MS = 300            # max interval between clicks to count as double-click

    # Minimum play duration (seconds) per state. Frame count is read at runtime
    # so user-replaced assets with different frame counts are handled correctly.
    _MIN_PLAY_SECONDS: dict = {
        State.MEAL: 10.0,
        State.REMIND: 10.0,
        State.IDLE_RANDOM: 5.0,
    }

    def __init__(
        self,
        animator: Animator,
        state_machine: StateMachine,
        settings: dict,
        *,
        on_reset: Callable[[], None] | None = None,
        update_checker=None,
    ) -> None:
        super().__init__()
        self.animator = animator
        self.state_machine = state_machine
        self.settings = settings
        self.on_reset = on_reset

        self.on_remind_dismissed: Callable[[], None] | None = None

        self._frame_index = 0
        self._min_loops_remaining: int = 0
        self._drag_start_global: QPoint | None = None
        self._drag_window_start: QPoint | None = None
        self._press_local_y: int = 0
        self._dragging = False
        self._drag_is_long: bool = False
        self._drag_is_fast: bool = False
        self._drag_vel_samples: deque = deque()  # (monotonic_time, QPoint)
        self._last_click_time: float = 0.0
        self._last_click_zone: str | None = None
        self._reminder_bubble: ReminderBubble | None = None
        self._update_bubble: UpdateBubble | None = None
        self._update_checker = update_checker
        self._manual_check_pending = False
        self._preview_restore_timer = QTimer(self)
        self._preview_restore_timer.setSingleShot(True)
        self._preview_restore_timer.timeout.connect(self._on_preview_restore)

        self._long_drag_timer = QTimer(self)
        self._long_drag_timer.setSingleShot(True)
        self._long_drag_timer.timeout.connect(self._on_long_drag_timer)

        if update_checker is not None:
            update_checker.update_available.connect(self._on_update_available)
            update_checker.up_to_date.connect(self._on_up_to_date)
            update_checker.check_failed.connect(self._on_check_failed)

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
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self._normalized_opacity())

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

        # On each completed loop, consume one unit of the minimum-play counter
        if self._frame_index == 0 and self._min_loops_remaining > 0:
            self._min_loops_remaining -= 1

        # One-shot states restore only after minimum loops are exhausted
        if self._frame_index == 0 and self.state_machine.is_temporary:
            if self.state_machine.state in ONE_SHOT_STATES:
                if self._min_loops_remaining == 0:
                    self.state_machine.restore()
                    self._frame_index = 0

        self._sync_window_size()
        self._update_window_mask()
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
        self._min_loops_remaining = self._compute_min_loops()
        self._sync_window_size()
        self._update_window_mask()
        self.update()
        self._reschedule()

    def _compute_min_loops(self) -> int:
        """Return the minimum number of full loops required for the current state."""
        state = self.state_machine.state
        min_s = self._MIN_PLAY_SECONDS.get(state, 0.0)
        if min_s <= 0:
            return 0
        anim = self.animator.get_animation(state)
        cycle_s = anim.frame_count / anim.fps
        return math.ceil(min_s / cycle_s)

    def is_in_minimum_play_period(self) -> bool:
        """True while the current state has not yet completed its minimum loops."""
        return self._min_loops_remaining > 0

    # -------------------------------------------------------------------------
    # Mouse events
    # -------------------------------------------------------------------------

    def _update_window_mask(self) -> None:
        anim = self.animator.get_animation(self.state_machine.state)
        frame = anim.get_frame(self._frame_index)
        self.setMask(QBitmap.fromImage(frame.toImage().createAlphaMask()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_window_start = self.pos()
            self._press_local_y = int(event.position().y())
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
            self._update_drag_velocity(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_dragging = self._dragging
        self._drag_start_global = None
        self._dragging = False
        if was_dragging:
            self._on_drag_end()
        else:
            self._on_click(self._press_local_y)

    # -------------------------------------------------------------------------
    # Interaction handlers
    # -------------------------------------------------------------------------

    def _on_click(self, local_y: int = 0) -> None:
        if self.state_machine.state == State.SLEEP:
            self.state_machine.transition_to(State.IDLE)
            self.on_state_changed()
            return

        h = self.height()
        if local_y < h * 44 // 100:    # top 44% → up
            zone = "up"
        elif local_y < h * 74 // 100:  # mid 30% (44%–74%)
            zone = "mid"
        else:
            zone = "down"

        now = time.monotonic()
        is_double = (
            zone == "up"
            and self._last_click_zone == "up"
            and (now - self._last_click_time) * 1000 < self.DOUBLE_CLICK_MS
            and self.animator.has_animation("poke/up_double")
        )
        self._last_click_time = now
        self._last_click_zone = None if is_double else zone  # reset after double so triple doesn't chain

        # Double-click interrupts current poke; single-click only fires when not temporary
        if is_double or not self.state_machine.is_temporary:
            return_to = (
                self.state_machine.return_state
                if self.state_machine.is_temporary
                else self.state_machine.state
            )
            self.animator.set_poke_zone("up_double" if is_double else zone)
            if self.animator.has_poke_animation():
                self.state_machine.transition_to(
                    State.POKE, temporary=True, return_to=return_to
                )
            self.on_state_changed()

    def _on_drag_start(self) -> None:
        if not self.state_machine.is_temporary and self.animator.has_animation(State.DRAG):
            self._drag_is_long = False
            self._drag_is_fast = False
            self._drag_vel_samples.clear()
            self.state_machine.transition_to(
                State.DRAG, temporary=True, return_to=self.state_machine.state
            )
            self.on_state_changed()
            self._long_drag_timer.start(5000)

    def _on_long_drag_timer(self) -> None:
        if not self._dragging:
            return
        self._drag_is_long = True
        self._apply_drag_state()

    def _on_drag_end(self) -> None:
        self._long_drag_timer.stop()
        self._drag_vel_samples.clear()
        _drag_states = (State.DRAG, State.DRAG_FAST, State.DRAG_LONG)
        if self.state_machine.state in _drag_states:
            self.state_machine.restore()
            self.on_state_changed()

    def _update_drag_velocity(self, global_pos: QPoint) -> None:
        now = time.monotonic()
        self._drag_vel_samples.append((now, global_pos))
        cutoff = now - self.DRAG_VEL_WINDOW_S
        while self._drag_vel_samples and self._drag_vel_samples[0][0] < cutoff:
            self._drag_vel_samples.popleft()

        if len(self._drag_vel_samples) >= 2:
            t0, p0 = self._drag_vel_samples[0]
            t1, p1 = self._drag_vel_samples[-1]
            dt = t1 - t0
            if dt > 0:
                dx = p1.x() - p0.x()
                dy = p1.y() - p0.y()
                speed = (dx * dx + dy * dy) ** 0.5 / dt
                new_fast = speed >= self.DRAG_FAST_THRESHOLD_PX_S
                if new_fast != self._drag_is_fast:
                    self._drag_is_fast = new_fast
                    self._apply_drag_state()

    def _drag_target_state(self) -> State:
        """Return the best available drag state for current phase and speed, with fallback."""
        if self._drag_is_long:
            candidates = [State.DRAG_LONG, State.DRAG]
        else:
            candidates = (
                [State.DRAG_FAST, State.DRAG]
                if self._drag_is_fast
                else [State.DRAG]
            )
        for state in candidates:
            if self.animator.has_animation(state):
                return state
        return State.DRAG

    def _apply_drag_state(self) -> None:
        target = self._drag_target_state()
        if self.state_machine.state == target:
            return
        return_to = self.state_machine.return_state
        self.state_machine.transition_to(target, temporary=True, return_to=return_to)
        self.on_state_changed()

    # -------------------------------------------------------------------------
    # Reminder bubble
    # -------------------------------------------------------------------------

    def show_reminder(self, message: str) -> None:
        if self._reminder_bubble is not None:
            return
        bubble = ReminderBubble(
            message,
            dismiss_label=self._text("reminder.dismiss"),
        )
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

        preview_menu = menu.addMenu(self._text("menu.state_preview"))
        for state in State:
            if state in (State.IDLE_RANDOM, State.DRAG_FAST, State.DRAG_LONG):
                continue  # internal states; not user-previewable

            if state == State.IDLE and self.animator.idle_variants:
                sub = preview_menu.addMenu(self._state_label(state))
                a = sub.addAction(self._text("menu.preview_default"))
                a.triggered.connect(lambda _checked: self._preview_state(State.IDLE))
                for variant_key in self.animator.idle_variants:
                    name = variant_key.split("/", 1)[1]
                    a = sub.addAction(name)
                    a.triggered.connect(
                        lambda _checked, k=variant_key: self._preview_idle_variant(k)
                    )
            elif state == State.POKE and self.animator.poke_zones:
                sub = preview_menu.addMenu(self._state_label(state))
                if self.animator.has_animation("poke"):
                    a = sub.addAction(self._text("menu.preview_default"))
                    a.triggered.connect(
                        lambda _checked: self._preview_poke_zone(None)
                    )
                for zone in self.animator.poke_zones:
                    a = sub.addAction(zone)
                    a.triggered.connect(
                        lambda _checked, z=zone: self._preview_poke_zone(z)
                    )
            else:
                action = preview_menu.addAction(self._state_label(state))
                action.triggered.connect(
                    lambda _checked, s=state: self._preview_state(s)
                )

        menu.addSeparator()
        menu.addAction(self._text("menu.import_pet")).triggered.connect(
            self._import_pet
        )
        menu.addAction(self._text("menu.open_pet_folder")).triggered.connect(
            self._open_pet_folder
        )
        menu.addAction(self._text("menu.export_template")).triggered.connect(
            self._export_pet_template
        )
        menu.addAction(self._text("menu.manual")).triggered.connect(self._open_manual)
        menu.addAction(self._text("menu.settings")).triggered.connect(
            self._open_settings
        )
        menu.addAction(self._text("menu.check_update")).triggered.connect(
            self._check_update
        )
        menu.addSeparator()
        menu.addAction(self._text("menu.clear_data")).triggered.connect(
            self._clear_data
        )
        menu.addAction(self._text("menu.quit")).triggered.connect(QApplication.quit)

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

    def _preview_idle_variant(self, variant_key: str) -> None:
        """Preview a specific idle sub-action once, then return to idle."""
        self._preview_restore_timer.stop()
        self.animator.set_idle_variant(variant_key)
        self.state_machine.transition_to(
            State.IDLE_RANDOM, temporary=True, return_to=State.IDLE
        )
        self.on_state_changed()
        self._preview_restore_timer.start(self.MANUAL_PREVIEW_RETURN_MS)

    def _preview_poke_zone(self, zone: str | None) -> None:
        """Preview a poke animation for a specific zone (or default if zone is None)."""
        self._preview_restore_timer.stop()
        self.animator.set_poke_zone(zone)
        self.state_machine.transition_to(
            State.POKE, temporary=True, return_to=State.IDLE
        )
        self.on_state_changed()
        self._preview_restore_timer.start(self.MANUAL_PREVIEW_RETURN_MS)

    def _on_preview_restore(self) -> None:
        if self.state_machine.is_temporary:
            self.state_machine.restore()
            self.on_state_changed()

    def _import_pet(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._text("dialog.import_pet_title"),
            "",
            self._text("dialog.pet_package_filter"),
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
                    QMessageBox.warning(
                        self,
                        self._text("dialog.import_failed_title"),
                        self._text("dialog.missing_manifest"),
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

            new_dir = cfg.get_active_pet_dir(self.settings)
            if new_dir:
                self.animator = Animator(new_dir, self.settings.get("scale", 0.85))
                self.state_machine.transition_to(State.JUMP)
                self.on_state_changed()
            QMessageBox.information(
                self,
                self._text("dialog.import_success_title"),
                self._text(
                    "dialog.import_success_message",
                    name=manifest.get("name", pet_name),
                ),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._text("dialog.import_failed_title"),
                str(exc),
            )

    def _open_pet_folder(self) -> None:
        pet_dir = self.animator.pet_dir
        if pet_dir.exists() and QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(pet_dir))
        ):
            return

        QMessageBox.warning(
            self,
            self._text("dialog.open_folder_failed_title"),
            self._text("dialog.open_folder_failed_message", path=pet_dir),
        )

    def _export_pet_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._text("dialog.export_template_title"),
            TEMPLATE_ARCHIVE_NAME,
            self._text("dialog.pet_package_filter"),
        )
        if not path:
            return

        from config import settings as cfg

        try:
            output_path = export_pet_template(
                cfg.bundled_pet_dir("default_pet"),
                Path(path),
            )
            QMessageBox.information(
                self,
                self._text("dialog.export_success_title"),
                self._text("dialog.export_success_message", path=output_path),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._text("dialog.export_failed_title"),
                self._text("dialog.export_failed_message", error=exc),
            )

    def _open_manual(self) -> None:
        webbrowser.open("https://github.com/todayisark/baebae-pet#readme")

    def _open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._text("dialog.settings_title"))

        layout = QVBoxLayout(dialog)

        general_box = QGroupBox(self._text("dialog.settings_general"))
        general_form = QFormLayout(general_box)

        language = QComboBox()
        language.addItem("中文", "zh")
        language.addItem("English", "en")
        current_language = normalize_language(self.settings.get("language"))
        language.setCurrentIndex(language.findData(current_language))
        general_form.addRow(self._text("dialog.settings_language"), language)

        scale = QComboBox()
        for label_key, value in [
            ("size.small", 0.5),
            ("size.medium", 0.85),
            ("size.large", 1.2),
        ]:
            scale.addItem(self._text(label_key), value)
        current_scale = self.settings.get("scale", 0.85)
        scale_values = [scale.itemData(i) for i in range(scale.count())]
        nearest_scale = min(
            range(len(scale_values)),
            key=lambda i: abs(float(scale_values[i]) - float(current_scale)),
        )
        scale.setCurrentIndex(nearest_scale)
        general_form.addRow(self._text("menu.size"), scale)

        opacity = QSpinBox()
        opacity.setRange(30, 100)
        opacity.setSuffix("%")
        opacity.setValue(round(self._normalized_opacity() * 100))
        general_form.addRow(self._text("dialog.settings_opacity"), opacity)
        self._add_hint(general_form, self._text("dialog.settings_opacity_hint"))
        layout.addWidget(general_box)

        rest_box = QGroupBox(self._text("dialog.settings_rest"))
        rest_form = QFormLayout(rest_box)
        rest_interval = QSpinBox()
        rest_interval.setRange(1, 1440)
        rest_interval.setValue(int(self.settings.get("remind_interval_minutes", 60)))
        rest_form.addRow(self._text("dialog.settings_rest_interval"), rest_interval)
        self._add_hint(rest_form, self._text("dialog.settings_rest_interval_hint"))

        rest_message = QLineEdit(str(self.settings.get("remind_message", "")))
        rest_form.addRow(self._text("dialog.settings_rest_message"), rest_message)
        layout.addWidget(rest_box)

        meal_box = QGroupBox(self._text("dialog.settings_meal"))
        meal_layout = QVBoxLayout(meal_box)
        enabled = QCheckBox(self._text("dialog.meal_enabled"))
        enabled.setChecked(self.settings.get("meal_reminder_enabled", True))
        meal_layout.addWidget(enabled)

        form = QFormLayout()
        time_edits: list[QTimeEdit] = []
        meal_times = self._normalized_meal_times()
        labels = [
            self._text("dialog.meal_breakfast"),
            self._text("dialog.meal_lunch"),
            self._text("dialog.meal_dinner"),
        ]
        for label, meal_time in zip(labels, meal_times):
            edit = QTimeEdit()
            edit.setDisplayFormat("HH:mm")
            edit.setTime(QTime.fromString(meal_time, "HH:mm"))
            form.addRow(label, edit)
            time_edits.append(edit)
        meal_layout.addLayout(form)

        meal_message = QLineEdit(str(self.settings.get("meal_reminder_message", "")))
        form.addRow(self._text("dialog.settings_meal_message"), meal_message)
        layout.addWidget(meal_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.settings["language"] = str(language.currentData())
        self.settings["scale"] = float(scale.currentData())
        self.settings["opacity"] = opacity.value() / 100
        self.settings["remind_interval_minutes"] = rest_interval.value()
        self.settings["remind_message"] = rest_message.text()
        self.settings["meal_reminder_enabled"] = enabled.isChecked()
        self.settings["meal_reminder_times"] = [
            edit.time().toString("HH:mm") for edit in time_edits
        ]
        self.settings["meal_reminder_message"] = meal_message.text()

        self.animator.set_scale(self.settings["scale"])
        self.setWindowOpacity(self._normalized_opacity())
        self.on_state_changed()

        from config import settings as cfg
        cfg.save(self.settings)

    def _normalized_meal_times(self) -> list[str]:
        raw_times = self.settings.get("meal_reminder_times", [])
        if not isinstance(raw_times, list):
            raw_times = []

        normalized: list[str] = []
        for item in raw_times:
            raw = str(item).strip()
            parts = raw.split(":")
            if len(parts) != 2:
                continue
            try:
                hour = int(parts[0])
                minute = int(parts[1])
            except ValueError:
                continue
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                normalized.append(f"{hour:02d}:{minute:02d}")

        defaults = ["08:00", "12:00", "18:00"]
        return (normalized + defaults)[:3]

    def _normalized_opacity(self) -> float:
        try:
            opacity = float(self.settings.get("opacity", 1.0))
        except (TypeError, ValueError):
            opacity = 1.0
        return min(1.0, max(0.3, opacity))

    def _add_hint(self, form: QFormLayout, text: str) -> None:
        hint = QLabel(text)
        hint.setStyleSheet("color: #666666; font-size: 11px;")
        form.addRow("", hint)

    def _check_update(self) -> None:
        if self._update_checker is None:
            return
        self._manual_check_pending = True
        self._update_checker.check()

    def _on_update_available(self, version: str, url: str) -> None:
        if not self.isVisible():
            return
        self._manual_check_pending = False
        if self._update_bubble is not None:
            return
        bubble = UpdateBubble(
            self._text("update.available", version=version),
            url,
            download_label=self._text("update.download"),
            dismiss_label=self._text("update.dismiss"),
        )
        bubble.dismissed.connect(self._on_update_bubble_dismissed)
        bubble.adjustSize()
        pos = self.pos()
        bx = max(0, pos.x() + self.width() // 2 - bubble.width() // 2)
        by = max(0, pos.y() - bubble.height() - 8)
        bubble.move(bx, by)
        bubble.show()
        self._update_bubble = bubble

    def _on_update_bubble_dismissed(self) -> None:
        self._update_bubble = None

    def _on_up_to_date(self) -> None:
        if not self.isVisible() or not self._manual_check_pending:
            return
        self._manual_check_pending = False
        self.show_reminder(self._text("update.up_to_date"))

    def _on_check_failed(self, msg: str) -> None:
        if not self.isVisible() or not self._manual_check_pending:
            return
        self._manual_check_pending = False
        self.show_reminder(self._text("update.failed"))

    def _clear_data(self) -> None:
        reply = QMessageBox.question(
            self,
            self._text("dialog.clear_data_title"),
            self._text("dialog.clear_data_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from config import settings as cfg
            cfg.clear_all_data()
            if self.on_reset:
                QTimer.singleShot(0, self.on_reset)

    def _text(self, key: str, **kwargs: object) -> str:
        return t(key, self.settings.get("language"), **kwargs)

    def _state_label(self, state: State) -> str:
        return self._text(f"state.{state.value}")
