"""
window.py — 宠物窗口（渲染 + Qt 事件接收）

职责：
  - 透明无边框置顶窗口的创建与配置
  - 逐帧渲染动画（_tick 驱动）
  - 将原始鼠标事件转发给 InteractionHandler
  - 气泡（提醒 / 更新通知）的显示与生命周期管理
  - 设置对话框、右键菜单、素材导入导出

不负责：
  - 具体的交互判断（poke 区域、双击、拖拽速度等）→ interaction.py
  - 宏观状态切换（sleep / typing / meal 等）→ main.py / PetController
  - 动画资源加载 → animator.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
import webbrowser
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, Qt, QTime, QTimer, QUrl
from PySide6.QtGui import QBitmap, QDesktopServices, QPainter, QPixmap
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
from engine.interaction import InteractionHandler
from engine.macos_window import apply_macos_always_on_top
from engine.pet_template import TEMPLATE_ARCHIVE_NAME, export_pet_template
from engine.reminder import ReminderBubble, UpdateBubble
from engine.state_machine import State, StateMachine


SIZE_PRESETS: list[tuple[str, tuple[int, int]]] = [
    ("size.small", (200, 200)),
    ("size.medium", (240, 240)),
    ("size.large", (300, 300)),
]


class PetWindow(QWidget):
    """
    透明、无边框、始终置顶的宠物窗口。

    外部调用方在任何状态切换后都应调用 on_state_changed()，使动画立即刷新。

    on_remind_dismissed: 提醒气泡关闭后触发的可选回调（用户点击或自动超时均触发）。
    """

    # 手动预览状态后自动恢复的等待时间（毫秒）
    MANUAL_PREVIEW_RETURN_MS = 3000

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

        # 气泡关闭后通知 PetController 重置工作计时
        self.on_remind_dismissed: Callable[[], None] | None = None

        # ── 渲染状态 ──────────────────────────────────────────────────────────
        self._frame_index = 0  # 当前播放到第几帧

        # ── 原始拖拽追踪（仅用于窗口位移，不含交互逻辑） ──────────────────────
        self._drag_start_global: QPoint | None = None  # 按下时的全局坐标
        self._drag_window_start: QPoint | None = None  # 按下时的窗口坐标
        self._press_local_y: int = 0                   # 按下时的本地纵坐标（用于区域判断）
        self._dragging = False                          # 是否已进入拖拽手势

        # ── 气泡引用 ──────────────────────────────────────────────────────────
        self._reminder_bubble: ReminderBubble | None = None
        self._update_bubble: UpdateBubble | None = None

        # ── 更新检查器 ────────────────────────────────────────────────────────
        self._update_checker = update_checker
        self._manual_check_pending = False

        # ── 预览恢复计时器（右键菜单手动预览用） ─────────────────────────────
        self._preview_restore_timer = QTimer(self)
        self._preview_restore_timer.setSingleShot(True)
        self._preview_restore_timer.timeout.connect(self._on_preview_restore)

        # ── 交互处理器 ────────────────────────────────────────────────────────
        # 所有"输入 → 状态机"的有状态逻辑都在这里，窗口只负责转发事件。
        self._interaction = InteractionHandler(
            animator, state_machine, self.on_state_changed
        )

        if update_checker is not None:
            update_checker.update_available.connect(self._on_update_available)
            update_checker.up_to_date.connect(self._on_up_to_date)
            update_checker.check_failed.connect(self._on_check_failed)

        self._setup_window()

        # 动画帧定时器，由 _reschedule() 按当前动画的 fps 动态调整间隔
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._reschedule()

    # =========================================================================
    # 窗口初始化
    # =========================================================================

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self._normalized_opacity())

        # 用第 0 帧尺寸初始化窗口大小
        anim = self.animator.get_animation(self.state_machine.state)
        frame = anim.get_frame(0)
        self.resize(frame.size())

        # 默认落在屏幕右下角
        screen = QApplication.primaryScreen().geometry()
        self.move(
            screen.width() - self.width() - 40,
            screen.height() - self.height() - 80,
        )

    def _normalized_size_setting(self) -> tuple[int, int]:
        size = self.settings.get("scale", self.settings.get("size", (240, 240)))
        if isinstance(size, (list, tuple)) and len(size) == 2:
            return (max(1, int(size[0])), max(1, int(size[1])))

        legacy_scale = float(size)
        if legacy_scale <= 0.675:
            return (200, 200)
        if legacy_scale <= 1.025:
            return (240, 240)
        return (300, 300)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_native_level_with_retries()

    def _apply_native_level_with_retries(self, attempts: int = 5) -> None:
        """macOS 原生置顶有时在窗口首次显示时失效，最多重试 5 次。"""
        if apply_macos_always_on_top(self):
            return
        if attempts > 1:
            QTimer.singleShot(
                100,
                lambda: self._apply_native_level_with_retries(attempts - 1),
            )

    # =========================================================================
    # 动画循环
    # =========================================================================

    def _reschedule(self) -> None:
        """根据当前动画的 fps 重设帧定时器间隔。"""
        anim = self.animator.get_animation(self.state_machine.state)
        self._anim_timer.start(anim.frame_interval_ms)

    def _tick(self) -> None:
        """每帧调用一次：推进帧索引，处理 one-shot 恢复，刷新显示。"""
        anim = self.animator.get_animation(self.state_machine.state)

        # 推进到下一帧，到末尾则归零（完成一轮）
        self._frame_index = (self._frame_index + 1) % anim.frame_count

        # 一轮播完时通知交互层（处理最低播放计数和 one-shot restore）
        if self._frame_index == 0:
            restored = self._interaction.on_loop_completed()
            if restored:
                # 状态已 restore，帧索引重置到新状态的起点
                self._frame_index = 0

        self._sync_window_size()
        self._update_window_mask()
        self.update()
        self._reschedule()

    def _sync_window_size(self) -> None:
        """若当前帧尺寸发生变化，以底部中心为锚点调整窗口大小和位置。"""
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

    def _current_frame(self) -> QPixmap:
        """返回当前帧，若启用水平翻转则镜像处理。"""
        anim = self.animator.get_animation(self.state_machine.state)
        frame = anim.get_frame(self._frame_index)
        if self.settings.get("flip_horizontal", False):
            frame = QPixmap.fromImage(frame.toImage().mirrored(True, False))
        return frame

    def _update_window_mask(self) -> None:
        """
        根据当前帧的 alpha 通道更新窗口点击区域遮罩。

        透明像素（alpha ≈ 0）对应 bit=0，点击穿透到下层窗口；
        不透明像素对应 bit=1，正常接收鼠标事件。
        此方法在 OS 层生效，不依赖 Qt 事件传递。
        """
        self.setMask(QBitmap.fromImage(self._current_frame().toImage().createAlphaMask()))

    # =========================================================================
    # 渲染
    # =========================================================================

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._current_frame())

    # =========================================================================
    # 外部调用：状态已在外部切换，通知窗口刷新
    # =========================================================================

    def on_state_changed(self) -> None:
        """
        状态机状态切换后调用此方法（无论是外部触发还是交互层触发）。
        重置帧索引、重算最低播放轮数、刷新显示。
        """
        self._frame_index = 0
        # 通知交互层重新计算当前状态的最低播放轮数
        self._interaction.recompute_min_loops()
        self._sync_window_size()
        self._update_window_mask()
        self.update()
        self._reschedule()

    def is_in_minimum_play_period(self) -> bool:
        """
        当前状态是否仍在最低播放期内。
        PetController._tick() 调用此方法决定是否暂缓宏观状态切换。
        """
        return self._interaction.is_in_minimum_play_period()

    # =========================================================================
    # 鼠标事件（只处理原始几何，交互逻辑转发给 InteractionHandler）
    # =========================================================================

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录按下位置，用于判断是否进入拖拽以及单击的区域
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
        # 超过 3px 死区才正式进入拖拽
        if not self._dragging and (abs(delta.x()) > 3 or abs(delta.y()) > 3):
            self._dragging = True
            self._interaction.on_drag_start()
        if self._dragging:
            self.move(self._drag_window_start + delta)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_dragging = self._dragging
        self._drag_start_global = None
        self._dragging = False
        if was_dragging:
            self._interaction.on_drag_end()
        else:
            # 未发生拖拽，视为点击
            self._interaction.on_click(self._press_local_y, self.height())

    # =========================================================================
    # 提醒气泡
    # =========================================================================

    def show_reminder(self, message: str) -> None:
        """在宠物上方显示提醒气泡。若气泡已存在则忽略。"""
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
        """气泡关闭（用户点击或 15 秒自动超时），恢复 idle 并通知外部重置计时。"""
        self._reminder_bubble = None
        self.state_machine.transition_to(State.IDLE)
        self.on_state_changed()
        if self.on_remind_dismissed:
            self.on_remind_dismissed()

    # =========================================================================
    # 右键菜单
    # =========================================================================

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)

        # 动画预览子菜单
        preview_menu = menu.addMenu(self._text("menu.state_preview"))
        for state in State:
            # 内部自动触发的状态，不暴露给用户手动预览
            if state in (State.IDLE_RANDOM, State.DRAG_3S, State.DRAG_5S):
                continue

            if state == State.IDLE and self.animator.idle_variants:
                # idle 有子动作，展开子菜单
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
                # poke 有区域变体，展开子菜单
                sub = preview_menu.addMenu(self._state_label(state))
                if self.animator.has_animation("poke"):
                    a = sub.addAction(self._text("menu.preview_default"))
                    a.triggered.connect(lambda _checked: self._preview_poke_zone(None))
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
        # 切换宠物子菜单
        switch_menu = menu.addMenu(self._text("menu.switch_pet"))
        current_pet = self.settings.get("pet", "default_pet")
        for pet_name, pet_dir, display_name in self._list_available_pets():
            action = switch_menu.addAction(display_name)
            action.setCheckable(True)
            action.setChecked(pet_name == current_pet)
            action.triggered.connect(
                lambda _checked, n=pet_name, d=pet_dir: self._switch_to_pet(n, d)
            )

        flip_action = menu.addAction(self._text("menu.flip_horizontal"))
        flip_action.setCheckable(True)
        flip_action.setChecked(self.settings.get("flip_horizontal", False))
        flip_action.triggered.connect(self._toggle_flip)

        menu.addAction(self._text("menu.import_pet")).triggered.connect(self._import_pet)
        menu.addAction(self._text("menu.open_pet_folder")).triggered.connect(self._open_pet_folder)
        menu.addAction(self._text("menu.export_template")).triggered.connect(self._export_pet_template)
        menu.addAction(self._text("menu.manual")).triggered.connect(self._open_manual)
        menu.addAction(self._text("menu.settings")).triggered.connect(self._open_settings)
        menu.addAction(self._text("menu.check_update")).triggered.connect(self._check_update)
        menu.addSeparator()
        menu.addAction(self._text("menu.clear_data")).triggered.connect(self._clear_data)
        menu.addAction(self._text("menu.quit")).triggered.connect(QApplication.quit)

        menu.exec(pos)

    # =========================================================================
    # 预览动作（右键菜单触发）
    # =========================================================================

    def _preview_state(self, state: State) -> None:
        """手动预览某个状态，MANUAL_PREVIEW_RETURN_MS 后自动恢复。"""
        self._preview_restore_timer.stop()
        self.state_machine.transition_to(state, temporary=True, return_to=State.IDLE)
        self.on_state_changed()
        self._preview_restore_timer.start(self.MANUAL_PREVIEW_RETURN_MS)

    def _preview_idle_variant(self, variant_key: str) -> None:
        """预览指定的 idle 子动作。"""
        self._preview_restore_timer.stop()
        self.animator.set_idle_variant(variant_key)
        self.state_machine.transition_to(
            State.IDLE_RANDOM, temporary=True, return_to=State.IDLE
        )
        self.on_state_changed()
        self._preview_restore_timer.start(self.MANUAL_PREVIEW_RETURN_MS)

    def _preview_poke_zone(self, zone: str | None) -> None:
        """预览指定区域的 poke 动画（zone=None 使用默认 poke）。"""
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

    def _toggle_flip(self) -> None:
        from config import settings as cfg
        self.settings["flip_horizontal"] = not self.settings.get("flip_horizontal", False)
        cfg.save(self.settings)
        self._update_window_mask()
        self.update()

    # =========================================================================
    # 切换宠物
    # =========================================================================

    def _list_available_pets(self) -> list[tuple[str, Path, str]]:
        """返回本地目录中所有可用宠物的 (folder_name, path, display_name) 列表。"""
        from config import settings as cfg

        pets: list[tuple[str, Path, str]] = []
        base_dir = cfg.pets_dir()
        if not base_dir.exists():
            return pets
        for d in sorted(base_dir.iterdir()):
            if not d.is_dir() or not (d / "manifest.json").exists():
                continue
            try:
                manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
                display = manifest.get("name") or d.name
            except Exception:
                display = d.name
            pets.append((d.name, d, display))
        return pets

    def _switch_to_pet(self, pet_name: str, pet_dir: Path) -> None:
        """切换到指定宠物，替换 Animator 并触发 hello 动画。"""
        if pet_name == self.settings.get("pet"):
            return
        from config import settings as cfg
        self.settings["pet"] = pet_name
        cfg.save(self.settings)
        self.animator = Animator(pet_dir, self.settings.get("scale", (240, 240)))
        self._interaction.set_animator(self.animator)
        self.state_machine.transition_to(State.HELLO, temporary=True, return_to=State.IDLE)
        self.on_state_changed()

    # =========================================================================
    # 素材导入 / 导出
    # =========================================================================

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
                # 替换 Animator 实例，同步通知交互层
                self.animator = Animator(new_dir, self.settings.get("scale", 0.85))
                self._interaction.set_animator(self.animator)
                self.state_machine.transition_to(State.HELLO, temporary=True, return_to=State.IDLE)
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

    # =========================================================================
    # 设置对话框
    # =========================================================================

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
        for label_key, value in SIZE_PRESETS:
            scale.addItem(self._text(label_key), value)
        current_size = self._normalized_size_setting()
        scale_values = [tuple(scale.itemData(i)) for i in range(scale.count())]
        current_index = scale_values.index(current_size)
        scale.setCurrentIndex(current_index)
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
        selected_size = tuple(scale.currentData())
        self.settings["scale"] = list(selected_size)
        self.settings["opacity"] = opacity.value() / 100
        self.settings["remind_interval_minutes"] = rest_interval.value()
        self.settings["remind_message"] = rest_message.text()
        self.settings["meal_reminder_enabled"] = enabled.isChecked()
        self.settings["meal_reminder_times"] = [
            edit.time().toString("HH:mm") for edit in time_edits
        ]
        self.settings["meal_reminder_message"] = meal_message.text()

        self.animator.set_scale(selected_size)
        self.setWindowOpacity(self._normalized_opacity())
        self.on_state_changed()

        from config import settings as cfg
        cfg.save(self.settings)

    # =========================================================================
    # 更新检查
    # =========================================================================

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

    # =========================================================================
    # 数据清除
    # =========================================================================

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

    # =========================================================================
    # 工具方法
    # =========================================================================

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

    def _text(self, key: str, **kwargs: object) -> str:
        return t(key, self.settings.get("language"), **kwargs)

    def _state_label(self, state: State) -> str:
        return self._text(f"state.{state.value}")
