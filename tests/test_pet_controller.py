from __future__ import annotations

import unittest
from datetime import datetime

from engine.state_machine import State, StateMachine
from main import PetController, TYPING_IDLE_TIMEOUT_S, normalize_meal_reminder_times


class FakeMonitor:
    def __init__(self) -> None:
        self.idle_seconds = 0.0
        self.typing_idle_seconds = float("inf")
        self.is_active = False
        self.is_typing = False
        self.is_typing_flow = False
        self.work_seconds = 0.0

    def update(self) -> None:
        pass


class FakeAnimator:
    def has_animation(self, state: str) -> bool:
        return True

    def has_idle_variants(self) -> bool:
        return False

    def has_poke_animation(self) -> bool:
        return True


class FakeWindow:
    def __init__(self) -> None:
        self.changed_count = 0
        self.reminders: list[str] = []

    def on_state_changed(self) -> None:
        self.changed_count += 1

    def show_reminder(self, message: str) -> None:
        self.reminders.append(message)


def make_controller() -> tuple[PetController, FakeMonitor, FakeWindow]:
    controller = object.__new__(PetController)
    controller.settings = {
        "remind_interval_minutes": 60,
        "meal_reminder_enabled": True,
        "meal_reminder_times": ["08:00", "12:00", "18:00"],
        "meal_reminder_message": "该吃饭啦！",
    }
    controller.state_machine = StateMachine()
    controller.state_machine.transition_to(State.IDLE)
    controller.animator = FakeAnimator()
    controller.monitor = FakeMonitor()
    controller.window = FakeWindow()
    controller._remind_shown = False
    controller._active_reminder_state = None
    controller._meal_reminders_shown = set()
    controller._now = lambda: datetime(2026, 5, 26, 9, 0)
    return controller, controller.monitor, controller.window


class PetControllerTest(unittest.TestCase):
    def test_mouse_activity_does_not_enter_typing(self) -> None:
        controller, monitor, window = make_controller()
        monitor.is_active = True
        monitor.idle_seconds = 0.1
        monitor.typing_idle_seconds = float("inf")

        controller._tick()

        self.assertEqual(controller.state_machine.state, State.IDLE)
        self.assertEqual(window.changed_count, 0)

    def test_mouse_activity_does_not_keep_typing_alive(self) -> None:
        controller, monitor, _window = make_controller()
        controller.state_machine.transition_to(State.TYPING)
        monitor.is_active = True
        monitor.idle_seconds = 0.1
        monitor.typing_idle_seconds = TYPING_IDLE_TIMEOUT_S

        controller._tick()

        self.assertEqual(controller.state_machine.state, State.IDLE)

    def test_meal_reminder_triggers_once_for_configured_wall_clock_time(self) -> None:
        controller, _monitor, window = make_controller()
        controller._now = lambda: datetime(2026, 5, 26, 12, 0, 5)

        controller._tick()
        controller.state_machine.transition_to(State.IDLE)
        controller._tick()

        self.assertEqual(controller.state_machine.state, State.IDLE)
        self.assertEqual(window.reminders, ["该吃饭啦！"])

    def test_meal_reminder_can_be_disabled(self) -> None:
        controller, _monitor, window = make_controller()
        controller.settings["meal_reminder_enabled"] = False
        controller._now = lambda: datetime(2026, 5, 26, 12, 0)

        controller._tick()

        self.assertEqual(controller.state_machine.state, State.IDLE)
        self.assertEqual(window.reminders, [])

    def test_normalize_meal_reminder_times(self) -> None:
        self.assertEqual(
            normalize_meal_reminder_times(["8:0", "12:30", "25:00", "18:05"]),
            ["08:00", "12:30", "18:05"],
        )


if __name__ == "__main__":
    unittest.main()
