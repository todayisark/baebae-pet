from __future__ import annotations

import sys
from typing import Any


def apply_macos_always_on_top(widget: Any) -> bool:
    """
    Apply the native macOS window settings that Qt's WindowStaysOnTopHint does
    not consistently preserve for frameless Tool windows.

    Returns True when the native NSWindow was found and updated.
    """
    if sys.platform != "darwin":
        return True

    try:
        import objc
        from AppKit import (
            NSFloatingWindowLevel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
        )
    except Exception as exc:
        print(f"[macOS window] PyObjC unavailable: {exc}")
        return False

    try:
        ns_object = objc.objc_object(c_void_p=int(widget.winId()))
        ns_window = _coerce_ns_window(ns_object)
        if ns_window is None:
            return False

        ns_window.setLevel_(NSFloatingWindowLevel)
        ns_window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        if hasattr(ns_window, "setCanHide_"):
            ns_window.setCanHide_(False)
        if hasattr(ns_window, "setHidesOnDeactivate_"):
            ns_window.setHidesOnDeactivate_(False)
        ns_window.orderFrontRegardless()
        return True
    except Exception as exc:
        print(f"[macOS window] failed to apply always-on-top: {exc}")
        return False


def _coerce_ns_window(ns_object: Any) -> Any | None:
    """Qt may hand back either a QNSView-like object or the NSWindow itself."""
    if ns_object is None:
        return None

    if hasattr(ns_object, "setLevel_"):
        return ns_object

    if hasattr(ns_object, "window"):
        ns_window = ns_object.window()
        if ns_window is not None and hasattr(ns_window, "setLevel_"):
            return ns_window

    return None
