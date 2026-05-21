from __future__ import annotations

from enum import Enum
from typing import Optional


class State(str, Enum):
    IDLE = "idle"
    TYPING = "typing"
    TYPING_FLOW = "typing_flow"
    SLEEP = "sleep"
    JUMP = "jump"
    REMIND = "remind"
    POKE = "poke"
    DRAG = "drag"


# States that play once and automatically restore to the previous state
ONE_SHOT_STATES = {State.JUMP, State.POKE}


class StateMachine:
    def __init__(self) -> None:
        # App starts with jump animation, then auto-returns to idle
        self._state = State.JUMP
        self._return_state = State.IDLE
        self._is_temporary = True  # JUMP is one-shot

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_temporary(self) -> bool:
        return self._is_temporary

    @property
    def return_state(self) -> State:
        return self._return_state

    # -------------------------------------------------------------------------
    # Transitions
    # -------------------------------------------------------------------------

    def transition_to(
        self,
        new_state: State,
        *,
        temporary: bool = False,
        return_to: Optional[State] = None,
    ) -> bool:
        """
        Transition to new_state.  Returns True if the state actually changed.

        temporary=True  → state will be restored via restore() once the
                          animation completes one full loop (for one-shot states)
                          or when explicitly called.
        return_to       → override the state to restore to (default: current state).
        """
        if new_state == self._state:
            return False

        if temporary:
            self._return_state = return_to if return_to is not None else self._state
            self._is_temporary = True
        else:
            self._is_temporary = False

        self._state = new_state
        return True

    def restore(self) -> bool:
        """Restore from a temporary state.  Returns True if state changed."""
        if self._is_temporary:
            self._state = self._return_state
            self._is_temporary = False
            return True
        return False
