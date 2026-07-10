"""GestureGate — merged StabilityFilter + CooldownFilter facade.

Implements TRD §3.10 (StabilityFilter) and TRD §3.11 (CooldownFilter)
as a single facade with independently testable internal classes.

The facade applies both filters in sequence per role:
  1. StabilityFilter (hold-timer for static gestures)
  2. CooldownFilter (per-role, per-gesture cooldown)

RULES §2.5: GestureGate is framework-agnostic (no Qt dependency).
RULES §6.4: hot-path — never raises.
"""

from __future__ import annotations

import logging
from typing import Iterable

from models.data_models import GestureResult
from settings.settings_manager import Settings


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants
# ---------------------------------------------------------------------------

DEFAULT_HOLD_WINDOW_MS: int = 200


class StabilityFilter:
    """Per-hand-role gesture hold-timer (internal class).

    Implements TRD §3.10 / PRD §8.2 (FR-GS-01..04). Tracking
    state is held in instance dicts. Dynamic gestures bypass
    the stability window (FR-GS-04).

    Identical contract to the V1.x StabilityFilter — refactored
    into gesture_gate.py as an internal class for encapsulation.
    """

    def __init__(self, window_ms: int = DEFAULT_HOLD_WINDOW_MS) -> None:
        if window_ms <= 0:
            raise ValueError(f'window_ms must be > 0; got {window_ms}')
        self.window_ms = int(window_ms)
        self.window_s = self.window_ms / 1000.0
        self._hold_start: dict[str, tuple[str, float]] = {}
        self._already_emitted: dict[str, str] = {}

    def check(
        self,
        role: str,
        candidate: GestureResult | None,
        now: float,
    ) -> GestureResult | None:
        if candidate is not None and candidate.is_dynamic:
            return candidate
        if candidate is None:
            self._hold_start.pop(role, None)
            self._already_emitted.pop(role, None)
            return None
        held_name, held_since = self._hold_start.get(role, (None, now))
        if candidate.gesture_name != held_name:
            self._hold_start[role] = (candidate.gesture_name, now)
            self._already_emitted.pop(role, None)
            return None
        elapsed = now - held_since
        if elapsed >= self.window_s:
            if self._already_emitted.get(role) != candidate.gesture_name:
                self._already_emitted[role] = candidate.gesture_name
                return candidate
            return None
        return None

    @property
    def holds_in_progress(self) -> dict[str, tuple[str, float]]:
        return dict(self._hold_start)

    def reset(self) -> None:
        self._hold_start.clear()
        self._already_emitted.clear()


class CooldownFilter:
    """Per-(role, gesture_name) cooldown timer (internal class).

    Implements TRD §3.11 / PRD §8.3 (FR-CD-01..03). Uses
    separate durations for static and dynamic gestures.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._last_trigger: dict[tuple[str, str], float] = {}

    def check(
        self,
        result: GestureResult,
        now: float,
    ) -> GestureResult | None:
        key = (result.hand_role, result.gesture_name)
        cooldown_ms = (
            self.settings.gesture_cooldown_dynamic_ms
            if result.is_dynamic
            else self.settings.gesture_cooldown_static_ms
        )
        cooldown_s = cooldown_ms / 1000.0
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
        self._last_trigger[key] = now
        return result

    def remaining_ms(
        self,
        role: str,
        gesture_name: str,
        now: float,
    ) -> int:
        key = (role, gesture_name)
        last = self._last_trigger.get(key)
        if last is None:
            return 0
        cooldown_ms = self.settings.gesture_cooldown_static_ms
        elapsed_ms = (now - last) * 1000.0
        return max(0, int(cooldown_ms - elapsed_ms))

    def reset(self) -> None:
        self._last_trigger.clear()

    @property
    def last_trigger_snapshot(self) -> dict[tuple[str, str], float]:
        return dict(self._last_trigger)


class GestureGate:
    """Facade that applies StabilityFilter then CooldownFilter.

    Accepts conflict-resolved winners per frame and returns the
    list of cooldown-cleared GestureResult objects.

    Usage:
        gate = GestureGate(settings)
        cleared = gate.process(winners, now)
    """

    def __init__(
        self,
        settings: Settings,
        stability_window_ms: int = DEFAULT_HOLD_WINDOW_MS,
    ) -> None:
        self.settings = settings
        self.stability = StabilityFilter(window_ms=stability_window_ms)
        self.cooldown = CooldownFilter(settings=settings)

    def process(
        self,
        winners: Iterable[GestureResult],
        now: float,
    ) -> list[GestureResult]:
        """Apply stability + cooldown filtering to resolved winners.

        Args:
            winners: conflict-resolved winners (one per role).
            now: current timestamp in seconds.

        Returns:
            List of cooldown-cleared GestureResult objects.
        """
        cleared: list[GestureResult] = []
        for winner in winners:
            stable = self.stability.check(winner.hand_role, winner, now)
            if stable is None:
                continue
            cleared_cooldown = self.cooldown.check(stable, now)
            if cleared_cooldown is None:
                continue
            cleared.append(cleared_cooldown)
        return cleared

    def reset(self) -> None:
        self.stability.reset()
        self.cooldown.reset()
