from __future__ import annotations

import sys
import threading
import time
from collections import deque

# ---------------------------------------------------------------------------
# macOS: sleep/wake observer via NSWorkspace
# ---------------------------------------------------------------------------

_sleep_wake_observer_class = None

if sys.platform == "darwin":
    try:
        import objc
        from AppKit import NSWorkspace
        from Foundation import NSObject

        class _SleepWakeObserver(NSObject):
            def initWithCallback_(self, callback):
                self = objc.super(_SleepWakeObserver, self).init()
                if self is None:
                    return None
                self._callback = callback
                return self

            def didWake_(self, notification):
                self._callback()

        _sleep_wake_observer_class = _SleepWakeObserver
    except Exception:
        pass

# ---------------------------------------------------------------------------
# macOS: poll HID idle time via CoreGraphics (no threads, no TSM calls)
# ---------------------------------------------------------------------------

_CG = None

if sys.platform == "darwin":
    try:
        import ctypes
        import ctypes.util

        _lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        _lib.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
        _lib.CGEventSourceSecondsSinceLastEventType.argtypes = [
            ctypes.c_int,
            ctypes.c_uint32,
        ]
        _CG = _lib
    except Exception:
        pass

_kCGEventSourceStateHIDSystemState = 1
_kCGAnyInputEventType = 0xFFFFFFFF
_kCGEventKeyDown = 10


def _hid_idle(event_type: int) -> float:
    if _CG is None:
        return 0.0
    return float(
        _CG.CGEventSourceSecondsSinceLastEventType(
            _kCGEventSourceStateHIDSystemState, event_type
        )
    )


# ---------------------------------------------------------------------------
# ActivityMonitor
# ---------------------------------------------------------------------------


class ActivityMonitor:
    """
    Monitors keyboard and mouse activity.

    On macOS: polls CoreGraphics HID state from the main thread — no background
    threads, no TSM calls, no accessibility permission required.

    On other platforms: falls back to pynput listeners in background threads.

    Call update() once per second from a QTimer to refresh public properties.
    """

    _TYPING_IDLE_THRESHOLD = 2.0

    def __init__(self, settings: dict) -> None:
        self._settings = settings
        self._typing_burst_start: float | None = None
        self._work_start = time.monotonic()

        # macOS sleep/wake observer
        self._sleep_wake_observer = None

        # pynput state (non-macOS fallback only)
        self._kb_listener = None
        self._ms_listener = None
        self._lock = threading.Lock()
        self._last_activity = time.monotonic()
        self._last_key_activity: float | None = None
        self._key_times: deque[float] = deque()

        # Public state (refreshed by update())
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
        self._register_sleep_wake_observer()

        if _CG is not None:
            return  # macOS: polling only, no threads needed

        # Non-macOS fallback: pynput listeners
        try:
            from pynput import keyboard, mouse
        except ImportError:
            return

        self._kb_listener = keyboard.Listener(on_press=self._on_key)
        self._ms_listener = mouse.Listener(on_click=self._on_mouse_click)
        self._kb_listener.start()
        self._ms_listener.start()

    def stop(self) -> None:
        if self._sleep_wake_observer is not None:
            try:
                NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(
                    self._sleep_wake_observer
                )
            except Exception:
                pass
            self._sleep_wake_observer = None
        if self._kb_listener:
            self._kb_listener.stop()
        if self._ms_listener:
            self._ms_listener.stop()

    def _register_sleep_wake_observer(self) -> None:
        if _sleep_wake_observer_class is None:
            return
        try:
            observer = _sleep_wake_observer_class.alloc().initWithCallback_(
                self.reset_work_timer
            )
            NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
                observer,
                "didWake:",
                "NSWorkspaceDidWakeNotification",
                None,
            )
            self._sleep_wake_observer = observer
        except Exception:
            pass

    def reset_work_timer(self, offset_seconds: float = 0.0) -> None:
        self._work_start = time.monotonic() - offset_seconds

    # -------------------------------------------------------------------------
    # pynput callbacks (non-macOS background threads)
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
        flow_seconds = self._settings.get("typing_flow_seconds", 20)
        gap_seconds = self._settings.get("typing_flow_gap_seconds", 5)

        if _CG is not None:
            self._update_cg(now, flow_seconds, gap_seconds)
        else:
            self._update_pynput(now, flow_seconds, gap_seconds)

    def _update_cg(
        self, now: float, flow_seconds: float, gap_seconds: float
    ) -> None:
        idle = _hid_idle(_kCGAnyInputEventType)
        key_idle = _hid_idle(_kCGEventKeyDown)

        was_typing = self.is_typing
        is_typing_now = key_idle < self._TYPING_IDLE_THRESHOLD

        if is_typing_now and not was_typing:
            # New typing burst started; back-calculate start from current idle
            self._typing_burst_start = now - key_idle
        elif not is_typing_now and key_idle > gap_seconds:
            self._typing_burst_start = None

        self.idle_seconds = idle
        self.typing_idle_seconds = key_idle
        self.is_active = idle < self._TYPING_IDLE_THRESHOLD
        self.is_typing = is_typing_now
        self.is_typing_flow = (
            self._typing_burst_start is not None
            and is_typing_now
            and now - self._typing_burst_start >= flow_seconds
        )
        if idle > 5 * 60:
            self._work_start = now
        self.work_seconds = now - self._work_start

    def _update_pynput(
        self, now: float, flow_seconds: float, gap_seconds: float
    ) -> None:
        with self._lock:
            idle = now - self._last_activity
            typing_idle = (
                float("inf")
                if self._last_key_activity is None
                else now - self._last_key_activity
            )
            typing_burst_start = self._typing_burst_start
            cutoff = now - (flow_seconds + gap_seconds)
            while self._key_times and self._key_times[0] < cutoff:
                self._key_times.popleft()

        self.idle_seconds = idle
        self.typing_idle_seconds = typing_idle
        self.is_active = idle < self._TYPING_IDLE_THRESHOLD
        self.is_typing = typing_idle < self._TYPING_IDLE_THRESHOLD
        self.is_typing_flow = (
            typing_burst_start is not None
            and typing_idle <= gap_seconds
            and now - typing_burst_start >= flow_seconds
        )
        if idle > 5 * 60:
            self._work_start = now
        self.work_seconds = now - self._work_start
