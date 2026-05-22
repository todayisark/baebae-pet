from __future__ import annotations

import sys
import threading
import time
from collections import deque


def _is_accessibility_trusted() -> bool:
    """Return True if this process has macOS Accessibility permission."""
    if sys.platform != "darwin":
        return True
    try:
        from HIServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return True  # Can't determine; assume OK


def _show_accessibility_guide() -> None:
    """Show a one-time dialog guiding the user to grant Accessibility permission."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        # Only show if a QApplication exists
        if QApplication.instance() is None:
            return
        msg = QMessageBox()
        msg.setWindowTitle("需要辅助功能权限")
        msg.setText(
            "baebae 需要辅助功能权限才能检测键盘 / 鼠标活动。\n\n"
            "请前往：\n"
            "系统设置 → 隐私与安全性 → 辅助功能\n"
            "将「终端」（或你使用的终端 App）添加进去，\n"
            "然后重新启动 baebae。"
        )
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.exec()
    except Exception:
        pass



class ActivityMonitor:
    """
    Monitors keyboard and mouse activity via pynput.

    Thread-safe.  Call update() once per second from the main thread (via
    QTimer) to refresh the public properties before reading them.

    Public properties (safe to read after update()):
        idle_seconds      – seconds since last keyboard/mouse event
        typing_idle_seconds
                          – seconds since last keyboard event
        is_active         – True if there was keyboard/mouse activity in the last 2 s
        is_typing         – True if there was keyboard activity in the last 2 s
        is_typing_flow    – True if keyboard activity spans typing_flow_seconds
                            with no gap longer than typing_flow_gap_seconds
        work_seconds      – continuous active time (resets after 5 min idle)
    """

    _TYPING_IDLE_THRESHOLD = 2.0  # seconds → still "typing"

    def __init__(self, settings: dict) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._last_activity = time.monotonic()
        self._last_key_activity: float | None = None
        self._typing_burst_start: float | None = None
        self._key_times: deque[float] = deque()
        self._work_start = time.monotonic()

        self._kb_listener = None
        self._ms_listener = None

        # Public state (updated by update())
        self.idle_seconds: float = 0.0
        self.typing_idle_seconds: float = float("inf")
        self.is_active: bool = False
        self.is_typing: bool = False
        self.is_typing_flow: bool = False
        self.work_seconds: float = 0.0

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        try:
            from pynput import keyboard, mouse
        except ImportError:
            return  # degrade gracefully; all properties stay at defaults

        if not _is_accessibility_trusted():
            _show_accessibility_guide()
            # Still start listeners — they will silently no-op until permission is granted.

        self._kb_listener = keyboard.Listener(on_press=self._on_key)
        self._ms_listener = mouse.Listener(on_click=self._on_mouse_click)
        self._kb_listener.start()
        self._ms_listener.start()

    def stop(self) -> None:
        if self._kb_listener:
            self._kb_listener.stop()
        if self._ms_listener:
            self._ms_listener.stop()

    # -------------------------------------------------------------------------
    # pynput callbacks (background threads)
    # -------------------------------------------------------------------------

    def _on_key(self, key) -> None:
        now = time.monotonic()
        gap_seconds = self._settings.get("typing_flow_gap_seconds", 5)
        with self._lock:
            if (
                self._last_key_activity is None
                or now - self._last_key_activity > gap_seconds
            ):
                self._typing_burst_start = now
                self._key_times.clear()
            self._last_activity = now
            self._last_key_activity = now
            self._key_times.append(now)

    def _on_mouse_click(self, x, y, button, pressed) -> None:
        if pressed:
            with self._lock:
                self._last_activity = time.monotonic()

    # -------------------------------------------------------------------------
    # Update (call from main thread / QTimer)
    # -------------------------------------------------------------------------

    def update(self) -> None:
        now = time.monotonic()
        settings = self._settings
        flow_seconds = settings.get("typing_flow_seconds", 20)
        gap_seconds = settings.get("typing_flow_gap_seconds", 5)

        with self._lock:
            idle = now - self._last_activity
            typing_idle = (
                float("inf")
                if self._last_key_activity is None
                else now - self._last_key_activity
            )
            typing_burst_start = self._typing_burst_start

            # Keep recent keys for future diagnostics without dropping the
            # beginning of the active burst before flow can be detected.
            cutoff = now - (flow_seconds + gap_seconds)
            while self._key_times and self._key_times[0] < cutoff:
                self._key_times.popleft()

        # --- idle_seconds ---
        self.idle_seconds = idle
        self.typing_idle_seconds = typing_idle

        # --- is_active ---
        self.is_active = idle < self._TYPING_IDLE_THRESHOLD

        # --- is_typing ---
        self.is_typing = typing_idle < self._TYPING_IDLE_THRESHOLD

        # --- is_typing_flow ---
        # Requires an uninterrupted keyboard burst for flow_seconds, with no
        # gap longer than gap_seconds.
        self.is_typing_flow = (
            typing_burst_start is not None
            and typing_idle <= gap_seconds
            and now - typing_burst_start >= flow_seconds
        )

        # --- work_seconds ---
        # Reset work timer if idle for more than 5 minutes
        if idle > 5 * 60:
            self._work_start = now
        self.work_seconds = now - self._work_start
