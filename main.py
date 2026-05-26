from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import config.settings as cfg
from engine.activity_monitor import ActivityMonitor
from engine.animator import Animator
from engine.state_machine import State, StateMachine
from engine.window import PetWindow

TYPING_IDLE_TIMEOUT_S = 10  # no keyboard input -> idle
SLEEP_TIMEOUT_S = 15 * 60   # no input -> sleep


def normalize_meal_reminder_times(value: object) -> list[str]:
    """Return valid HH:MM meal reminder times, capped to three entries."""
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    for item in value:
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
        if len(normalized) == 3:
            break
    return normalized


class PetController:
    """
    Central coordinator: ties ActivityMonitor → StateMachine → PetWindow.
    Polls every second via QTimer.
    """

    def __init__(self, settings: dict, pet_dir: Path) -> None:
        self.settings = settings
        self.state_machine = StateMachine()
        self.animator = Animator(pet_dir, settings.get("scale", 0.85))
        self.window = PetWindow(self.animator, self.state_machine, settings)
        self.monitor = ActivityMonitor(settings)

        self._remind_shown = False
        self._active_reminder_state: State | None = None
        self._meal_reminders_shown: set[str] = set()

        # Wire up reminder-dismissed callback
        self.window.on_remind_dismissed = self._on_remind_dismissed

        # Start polling
        self._tick_timer = QTimer()
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)

        # Start input listener
        self.monitor.start()

        self.window.show()

    # -------------------------------------------------------------------------
    # Main tick (every 1 s)
    # -------------------------------------------------------------------------

    def _tick(self) -> None:
        self.monitor.update()
        state = self.state_machine.state

        # Never interrupt temporary states (jump / poke / drag / preview)
        if self.state_machine.is_temporary:
            return

        idle = self.monitor.idle_seconds
        typing_idle = self.monitor.typing_idle_seconds
        remind_s = self.settings.get("remind_interval_minutes", 60) * 60
        now = self._now()

        # ── 1. Return to idle after keyboard stops ───────────────────────────
        if (
            typing_idle >= TYPING_IDLE_TIMEOUT_S
            and state in (State.TYPING, State.TYPING_FLOW)
        ):
            self._go(State.IDLE)
            return

        # ── 2. Meal reminder (wall-clock based, once per configured time/day) ─
        meal_time = self._due_meal_reminder(now)
        if meal_time and state not in (State.MEAL, State.REMIND):
            self._meal_reminders_shown.add(self._meal_reminder_key(now, meal_time))
            self._active_reminder_state = State.MEAL
            self._go(State.MEAL)
            self.window.show_reminder(
                self.settings.get("meal_reminder_message", "该吃饭啦！")
            )
            return

        # ── 3. Sleep ──────────────────────────────────────────────────────────
        if idle >= SLEEP_TIMEOUT_S and state != State.SLEEP:
            self._go(State.SLEEP)
            return

        # ── 4. Wake from sleep on any activity ───────────────────────────────
        if state == State.SLEEP and self.monitor.is_active:
            self._go(State.IDLE)
            return

        # ── 5. Remind (skip if already shown this session) ───────────────────
        if (
            self.monitor.work_seconds >= remind_s
            and not self._remind_shown
            and state != State.REMIND
            and state != State.MEAL
            and state != State.SLEEP
        ):
            self._remind_shown = True
            self._active_reminder_state = State.REMIND
            self._go(State.REMIND)
            self.window.show_reminder(
                self.settings.get("remind_message", "该休息了！")
            )
            return

        # ── 6. Typing-flow ────────────────────────────────────────────────────
        if self.monitor.is_typing_flow and state != State.TYPING_FLOW:
            if state not in (State.REMIND, State.MEAL, State.SLEEP):
                self._go(State.TYPING_FLOW)
                return

        # ── 7. Typing ─────────────────────────────────────────────────────────
        if (
            self.monitor.is_typing
            and not self.monitor.is_typing_flow
            and state
            not in (
                State.TYPING,
                State.TYPING_FLOW,
                State.SLEEP,
                State.REMIND,
                State.MEAL,
            )
        ):
            self._go(State.TYPING)
            return

    def _now(self) -> datetime:
        return datetime.now()

    def _due_meal_reminder(self, now: datetime) -> str | None:
        if not self.settings.get("meal_reminder_enabled", True):
            return None

        today = now.date().isoformat()
        self._meal_reminders_shown = {
            key for key in self._meal_reminders_shown if key.startswith(today)
        }

        current_time = now.strftime("%H:%M")
        for meal_time in normalize_meal_reminder_times(
            self.settings.get("meal_reminder_times", [])
        ):
            key = self._meal_reminder_key(now, meal_time)
            if current_time == meal_time and key not in self._meal_reminders_shown:
                return meal_time
        return None

    def _meal_reminder_key(self, now: datetime, meal_time: str) -> str:
        return f"{now.date().isoformat()} {meal_time}"

    def _go(self, state: State) -> None:
        if self.state_machine.transition_to(state):
            self.window.on_state_changed()

    def _on_remind_dismissed(self) -> None:
        """Handle dismissal for both rest and meal reminder bubbles."""
        if self._active_reminder_state == State.REMIND:
            self._remind_shown = False
            # Force work_seconds to reset by resetting _work_start
            self.monitor._work_start = time.monotonic()
        self._active_reminder_state = None

    def stop(self) -> None:
        self.monitor.stop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    app = QApplication(sys.argv)
    # Don't quit when the last visible widget closes (reminder bubble etc.)
    app.setQuitOnLastWindowClosed(False)

    cfg.initialize()
    settings = cfg.load()

    pet_dir = cfg.get_active_pet_dir(settings)

    if pet_dir is None:
        from ui.onboarding import OnboardingWindow
        onboarding = OnboardingWindow(settings)
        onboarding.show()
    else:
        _controller = PetController(settings, pet_dir)  # noqa: F841 (kept alive)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
