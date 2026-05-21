from __future__ import annotations

import unittest

from engine.state_machine import State, StateMachine
from main import PetController, TYPING_IDLE_TIMEOUT_S


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


class FakeWindow:
    def __init__(self) -> None:
        self.changed_count = 0

    def on_state_changed(self) -> None:
        self.changed_count += 1

    def show_reminder(self, message: str) -> None:
        pass


def make_controller() -> tuple[PetController, FakeMonitor, FakeWindow]:
    controller = object.__new__(PetController)
    controller.settings = {"remind_interval_minutes": 60}
    controller.state_machine = StateMachine()
    controller.state_machine.transition_to(State.IDLE)
    controller.monitor = FakeMonitor()
    controller.window = FakeWindow()
    controller._remind_shown = False
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


if __name__ == "__main__":
    unittest.main()
