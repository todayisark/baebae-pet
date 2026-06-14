from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import config.settings as cfg
from engine.activity_monitor import ActivityMonitor
from engine.animator import Animator
from engine.state_machine import State, StateMachine
from engine.update_checker import UpdateChecker
from engine.window import PetWindow

TYPING_IDLE_TIMEOUT_S = 3       # no keyboard input -> idle
SLEEP_TIMEOUT_S = 15 * 60       # no input -> sleep
IDLE_RANDOM_INTERVAL_MS = 3 * 60 * 1000  # idle sub-action every 3 minutes


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

    def __init__(
        self,
        settings: dict,
        pet_dir: Path,
        *,
        on_reset: Callable[[], None] | None = None,
        update_checker: UpdateChecker | None = None,
    ) -> None:
        self.settings = settings
        self.state_machine = StateMachine()
        self.animator = Animator(pet_dir, settings.get("scale", [240, 240]))
        self.window = PetWindow(
            self.animator,
            self.state_machine,
            settings,
            on_reset=on_reset,
            update_checker=update_checker,
        )
        self.monitor = ActivityMonitor(settings)

        self._remind_shown = False
        self._active_reminder_state: State | None = None
        self._meal_reminders_shown: set[str] = set()

        # Wire up reminder-dismissed callback
        self.window.on_remind_dismissed = self._on_remind_dismissed

        # If hello animation is missing, skip straight to idle
        if not self.animator.has_animation(State.HELLO):
            self.state_machine.transition_to(State.IDLE)
            self.window.on_state_changed()

        # Start polling
        self._tick_timer = QTimer()
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)

        # Idle sub-action timer (only when variants exist)
        self._idle_random_timer = QTimer()
        self._idle_random_timer.timeout.connect(self._on_idle_random_tick)
        if self.animator.has_idle_variants():
            self._idle_random_timer.start(IDLE_RANDOM_INTERVAL_MS)

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

        # Never interrupt states that haven't completed their minimum play time
        if self.window.is_in_minimum_play_period():
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
            if self.animator.has_animation(State.MEAL):
                self._active_reminder_state = State.MEAL
                self._go(State.MEAL)
                meal_times = normalize_meal_reminder_times(
                    self.settings.get("meal_reminder_times", [])
                )
                meal_idx = meal_times.index(meal_time) if meal_time in meal_times else -1
                meal_msg_keys = [
                    "meal_reminder_message_breakfast",
                    "meal_reminder_message_lunch",
                    "meal_reminder_message_dinner",
                ]
                msg_key = meal_msg_keys[meal_idx] if 0 <= meal_idx < 3 else None
                message = (
                    self.settings.get(msg_key, "") if msg_key else ""
                ) or "该吃饭啦！"
                self.window.show_reminder(message)
            return

        # ── 3. Sleep ──────────────────────────────────────────────────────────
        if idle >= SLEEP_TIMEOUT_S and state != State.SLEEP:
            if self.animator.has_animation(State.SLEEP):
                self.monitor.reset_work_timer()
                self._go(State.SLEEP)
            return

        # ── 4. Wake from sleep on any activity ───────────────────────────────
        if state == State.SLEEP and self.monitor.is_active:
            self.monitor.reset_work_timer()
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
            if self.animator.has_animation(State.REMIND):
                self._active_reminder_state = State.REMIND
                self._go(State.REMIND)
                self.window.show_reminder(
                    self.settings.get("remind_message", "该休息了！")
                )
            return

        # ── 6. Typing-flow ────────────────────────────────────────────────────
        if self.monitor.is_typing_flow and state != State.TYPING_FLOW:
            if state not in (State.REMIND, State.MEAL, State.SLEEP):
                if self.animator.has_animation(State.TYPING_FLOW):
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
            if self.animator.has_animation(State.TYPING):
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

    def _on_idle_random_tick(self) -> None:
        if self.state_machine.state != State.IDLE or self.state_machine.is_temporary:
            return
        variant = self.animator.random_idle_variant()
        if variant is None:
            return
        self.animator.set_idle_variant(variant)
        if self.state_machine.transition_to(
            State.IDLE_RANDOM, temporary=True, return_to=State.IDLE
        ):
            self.window.on_state_changed()

    def _go(self, state: State) -> None:
        if self.state_machine.transition_to(state):
            self.window.on_state_changed()

    def _on_remind_dismissed(self) -> None:
        """Handle dismissal for both rest and meal reminder bubbles."""
        if self._active_reminder_state == State.REMIND:
            self._remind_shown = False
            self.monitor.reset_work_timer()
        self._active_reminder_state = None

    def stop(self) -> None:
        self._tick_timer.stop()
        self._idle_random_timer.stop()
        self.monitor.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_dock_icon(pet_dir: Path | None) -> None:
    from engine.macos_window import set_dock_icon
    candidates = []
    if pet_dir:
        candidates.append(pet_dir / "idle" / "0.png")
    candidates.append(cfg.bundled_pet_dir("default_pet") / "idle" / "0.png")
    for path in candidates:
        if path.exists():
            set_dock_icon(path)
            return


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    app = QApplication(sys.argv)
    # Don't quit when the last visible widget closes (reminder bubble etc.)
    app.setQuitOnLastWindowClosed(False)

    cfg.initialize()

    _checker = UpdateChecker()
    _checker.start_scheduled()

    # These refs live in main()'s frame for the duration of app.exec().
    _controller: PetController | None = None
    _onboarding = None

    def _on_pet_ready(ready_settings: dict, ready_pet_dir: Path) -> None:
        nonlocal _controller, _onboarding
        _apply_dock_icon(ready_pet_dir)
        _controller = PetController(
            ready_settings, ready_pet_dir, on_reset=_on_reset, update_checker=_checker
        )
        _onboarding = None

    def _on_reset() -> None:
        nonlocal _controller, _onboarding
        if _controller is not None:
            _controller.stop()
            _controller.window.hide()
        _controller = None
        cfg.initialize()
        fresh_settings = cfg.load()
        _onboarding = _show_onboarding(fresh_settings)

    def _show_onboarding(settings: dict):
        from ui.onboarding import OnboardingWindow
        w = OnboardingWindow(settings, on_pet_ready=_on_pet_ready)
        w.show()
        return w

    settings = cfg.load()
    pet_dir = cfg.get_active_pet_dir(settings)

    _apply_dock_icon(pet_dir)

    if pet_dir is None:
        _onboarding = _show_onboarding(settings)
    else:
        _controller = PetController(settings, pet_dir, on_reset=_on_reset, update_checker=_checker)

    return app.exec()


if __name__ == "__main__":
    import logging
    import traceback

    log_path = Path.home() / "Library" / "Logs" / "baebae.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    def _excepthook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.critical("Unhandled exception:\n%s", msg)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook
    logging.info("baebae starting")

    try:
        sys.exit(main())
    except Exception:
        logging.critical("main() raised:\n%s", traceback.format_exc())
        raise
