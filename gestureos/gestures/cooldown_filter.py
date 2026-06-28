"""CooldownFilter — per-(hand_role, gesture_name) cooldown timer.

Implements TRD §3.11 and PRD §8.3 (FR-CD-01..03, Cooldown System).

Responsibilities (TRD §3.11):
  - Track last-trigger timestamp per (role, gesture_name) pair
  - On each stability-passed candidate, check elapsed time against
    the gesture-type-appropriate cooldown:
      - `gesture_cooldown_static_ms` for static gestures (default 500 ms)
      - `gesture_cooldown_dynamic_ms` for dynamic gestures (default 1000 ms)
  - Suppress the candidate if still within the cooldown window

PRD rationale (FR-CD-01): dynamic gestures span a longer physical
motion than static gestures, so they need a longer cooldown to
prevent the same action from firing twice.

Independence (FR-CD-02): a cooldown on (HAND_A, swipe_right) does NOT
suppress:
  - a different gesture on HAND_A (e.g., swipe_left)
  - the same gesture on HAND_B (HAND_B can still trigger swipe_right)
  - any other (role, gesture_name) pair

Debug-overlay accessor (FR-CD-03): `remaining_ms()` returns how many
milliseconds remain on the active cooldown for a given (role,
gesture_name) pair. Used by CP-8's Developer Mode overlay.

State held in explicit per-instance dicts (RULES §6.1): no globals.
"""

from __future__ import annotations

import logging
from typing import Iterable

from models.data_models import GestureResult
from settings.settings_manager import Settings


logger = logging.getLogger('gestureos')


class CooldownFilter:
    """Per-(role, gesture_name) cooldown timer.

    Stateful — one instance per pipeline. State lives in a single
    instance attribute:
      - `_last_trigger[(role, gesture_name)]`: timestamp in seconds

    Hot-path (called per role, per stability-passed candidate). All
    operations are O(1).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # (role, gesture_name) -> last-trigger timestamp (seconds).
        self._last_trigger: dict[tuple[str, str], float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        result: GestureResult,
        now: float,
    ) -> GestureResult | None:
        """Apply the cooldown gate to a stability-passed gesture result.

        Args:
            result: stability-passed `GestureResult` from
                `StabilityFilter.check()`
            now: current timestamp in seconds

        Returns:
            The same `result` if the cooldown has elapsed, OR
            `None` if the cooldown is still active (the result is
            suppressed).

        On a successful pass-through, the (role, gesture_name) last-
        trigger timestamp is updated so the next call within the
        cooldown window will be suppressed.
        """
        key = (result.hand_role, result.gesture_name)
        cooldown_ms = (
            self.settings.gesture_cooldown_dynamic_ms
            if result.is_dynamic
            else self.settings.gesture_cooldown_static_ms
        )
        cooldown_s = cooldown_ms / 1000.0

        # If this (role, gesture_name) has never been triggered, emit
        # unconditionally. `dict.get(key, 0.0)` would incorrectly make
        # `elapsed_s == 0.0 < cooldown_s` always True on the very
        # first trigger; instead, use a sentinel (`None`) for "never
        # seen" and short-circuit.
        last = self._last_trigger.get(key)
        if last is not None:
            elapsed_s = now - last
            if elapsed_s < cooldown_s:
                logger.debug(
                    'cooldown',
                    extra={'extras': {
                        'event': 'suppressed',
                        'role': result.hand_role,
                        'gesture': result.gesture_name,
                        'remaining_ms': int((cooldown_s - elapsed_s) * 1000),
                    }},
                )
                return None

        # Cooldown elapsed (or never triggered) -> emit and stamp the
        # new last-trigger timestamp.
        self._last_trigger[key] = now
        logger.debug(
            'cooldown',
            extra={'extras': {
                'event': 'passed',
                'role': result.hand_role,
                'gesture': result.gesture_name,
                'cooldown_ms': cooldown_ms,
            }},
        )
        return result

    # ------------------------------------------------------------------
    # FR-CD-03: debug-overlay accessor
    # ------------------------------------------------------------------

    def remaining_ms(
        self,
        role: str,
        gesture_name: str,
        now: float,
    ) -> int:
        """Return the milliseconds remaining on the cooldown for
        (role, gesture_name), or 0 if no cooldown is active.

        Used by the Developer Mode debug overlay (CP-8) to show
        `Cooldown: Xms remaining` (PRD §12.2 / TRD §9.3 example
        log line / debug overlay).

        Note: the debug overlay uses the STATIC cooldown duration as
        the upper bound for display purposes (matching the TRD §3.11
        reference implementation's `remaining_ms()` behavior). This
        is a display approximation only — the actual cooldown check
        in `check()` uses the gesture-type-appropriate duration
        (static or dynamic). For a debug-overlay readout that
        distinguishes the two, the caller can inspect the settings
        directly.
        """
        key = (role, gesture_name)
        last = self._last_trigger.get(key)
        if last is None:
            return 0
        # Use static cooldown as the display approximation per TRD §3.11
        cooldown_ms = self.settings.gesture_cooldown_static_ms
        elapsed_ms = (now - last) * 1000.0
        return max(0, int(cooldown_ms - elapsed_ms))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all cooldown state. Used on camera reconnect / pipeline restart."""
        self._last_trigger.clear()

    # ------------------------------------------------------------------
    # Read-only introspection
    # ------------------------------------------------------------------

    @property
    def last_trigger_snapshot(self) -> dict[tuple[str, str], float]:
        """Read-only snapshot of the cooldown state, used by tests."""
        return dict(self._last_trigger)