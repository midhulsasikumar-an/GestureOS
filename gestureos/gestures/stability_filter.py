"""StabilityFilter — gesture hold-timer for static gestures.

Implements TRD §3.10 and PRD §8.2 (FR-GS-01..04, Gesture Stability
Requirement).

Responsibilities (TRD §3.10):
  - Track, per hand role, the gesture name first seen and the
    timestamp it started
  - On each frame, if the same gesture is still the candidate,
    check elapsed time against `gesture_stability_window_ms`
  - Once satisfied, emit the gesture exactly once (not every frame
    thereafter — see Cooldown interaction below)
  - If the candidate changes before the window elapses, reset the
    hold timer with NO partial credit (FR-GS-02)
  - Dynamic gestures bypass this filter entirely (FR-GS-04 — they're
    already multi-frame by construction)

State held in explicit per-instance dicts (RULES §6.1): no globals.

RULES §6.4: hot-path — never raises. The `held_since` comparison
uses `>=` (not `>`) per TRD §3.10's reference implementation: a
gesture held for exactly the boundary duration triggers.
"""

from __future__ import annotations

import logging
from typing import Iterable

from models.data_models import GestureResult


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.10, PRD FR-GS-01)
# ---------------------------------------------------------------------------

DEFAULT_HOLD_WINDOW_MS: int = 200
"""Default per-gesture hold window. Per PRD §8.2: 200 ms default,
100-500 ms configurable range."""


class StabilityFilter:
    """Per-hand-role gesture hold-timer.

    Stateful — one instance per pipeline. State lives in two
    instance attributes:
      - `_hold_start[role]`: tuple(gesture_name, start_time_seconds)
        OR absent if no gesture is currently being held
      - `_already_emitted[role]`: the last-emitted gesture name (used
        to ensure we emit each gesture exactly once per hold cycle)

    The filter is hot-path (called every frame, per hand role, per
    gesture). All operations are O(1).
    """

    def __init__(self, window_ms: int = DEFAULT_HOLD_WINDOW_MS) -> None:
        if window_ms <= 0:
            raise ValueError(f'window_ms must be > 0; got {window_ms}')
        self.window_ms = int(window_ms)
        self.window_s = self.window_ms / 1000.0

        # role -> (gesture_name, hold_start_seconds). Absent means no
        # active hold.
        self._hold_start: dict[str, tuple[str, float]] = {}
        # role -> last-emitted gesture_name (to enforce "emit once per
        # hold cycle"). Absent means no emission yet for this role.
        self._already_emitted: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        role: str,
        candidate: GestureResult | None,
        now: float,
    ) -> GestureResult | None:
        """Apply the stability window to a single per-role candidate.

        Args:
            role: hand role (`'HAND_A'` or `'HAND_B'`)
            candidate: per-frame candidate from ConflictResolver
                (may be None for "no gesture this frame")
            now: current timestamp in seconds

        Returns:
            The candidate once it has been held continuously for
            `window_ms` (returns it ONCE per hold cycle), or `None`
            if the candidate has not yet been held long enough, has
            disappeared, or has changed identity mid-hold.

        Dynamic candidates pass through unchanged on the FIRST frame
        they appear and are also "emitted once" thereafter (until the
        candidate changes), per FR-GS-04. Dynamic gestures are
        inherently multi-frame so the stability window doesn't apply.
        """
        # Dynamic gestures exempt per FR-GS-04
        if candidate is not None and candidate.is_dynamic:
            return candidate

        # No candidate -> reset state for this role.
        if candidate is None:
            self._hold_start.pop(role, None)
            self._already_emitted.pop(role, None)
            return None

        # Static candidate: check whether it's a continuation of the
        # current hold or a fresh start.
        held_name, held_since = self._hold_start.get(role, (None, now))

        if candidate.gesture_name != held_name:
            # FR-GS-02: candidate changed -> restart hold with NO
            # partial credit. The previously-held gesture's hold
            # timer is discarded; the new candidate's hold starts now.
            self._hold_start[role] = (candidate.gesture_name, now)
            self._already_emitted.pop(role, None)
            return None

        # Same candidate continues the hold. Check elapsed time.
        elapsed = now - held_since
        if elapsed >= self.window_s:
            # Hold window satisfied. Emit ONCE per hold cycle.
            if self._already_emitted.get(role) != candidate.gesture_name:
                self._already_emitted[role] = candidate.gesture_name
                return candidate
            # Already emitted this hold cycle — don't emit again until
            # the candidate changes (and re-triggers the hold cycle).
            return None

        # Still within the hold window — partial hold, no emit yet.
        return None

    # ------------------------------------------------------------------
    # Read-only introspection
    # ------------------------------------------------------------------

    @property
    def holds_in_progress(self) -> dict[str, tuple[str, float]]:
        """Read-only snapshot of currently-tracked holds.

        Used by tests and (in CP-8) by the debug overlay to display
        "Stability: held Xms" feedback for the operator.
        """
        return dict(self._hold_start)

    def reset(self) -> None:
        """Clear all per-role hold state. Used on camera reconnect /
        pipeline restart."""
        self._hold_start.clear()
        self._already_emitted.clear()