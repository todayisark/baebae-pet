from __future__ import annotations

import math
import unittest
from unittest.mock import patch

from engine.activity_monitor import ActivityMonitor


class ActivityMonitorTest(unittest.TestCase):
    def test_typing_uses_keyboard_activity_only(self) -> None:
        with patch("engine.activity_monitor.time.monotonic", return_value=1000.0):
            monitor = ActivityMonitor({})

        with patch("engine.activity_monitor.time.monotonic", return_value=1000.0):
            monitor.update()
        self.assertFalse(monitor.is_typing)
        self.assertTrue(math.isinf(monitor.typing_idle_seconds))

        with patch("engine.activity_monitor.time.monotonic", return_value=1001.0):
            monitor._on_key("a")

        with patch("engine.activity_monitor.time.monotonic", return_value=1002.0):
            monitor.update()
        self.assertTrue(monitor.is_typing)
        self.assertEqual(monitor.typing_idle_seconds, 1.0)

        with patch("engine.activity_monitor.time.monotonic", return_value=1008.0):
            monitor._on_mouse_click(0, 0, None, True)

        with patch("engine.activity_monitor.time.monotonic", return_value=1012.0):
            monitor.update()
        self.assertFalse(monitor.is_typing)
        self.assertEqual(monitor.typing_idle_seconds, 11.0)
        self.assertEqual(monitor.idle_seconds, 4.0)


if __name__ == "__main__":
    unittest.main()
