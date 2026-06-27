"""Motion History Buffer (Checkpoint 2 deliverable).

Implements TRD §3.9 / §4.5 (MotionHistoryBuffer). Stores the previous
N frames of wrist position per hand role, where N is configurable via
`Settings.motion_history_frames` (10..40 per the TRD §7.2 settings
schema; PRD FR-MH-01..04 mandate 15..30 frames).

Critical design property (PRD FR-MH-03, TRD §4.5):
    The buffer stores RAW (unnormalized) position + timestamp.
    Normalization by hand-scale happens at evaluation time, not at
    storage time. This matters because hand-scale is itself a per-frame
    smoothed value (TRD §3.7); pre-normalizing at write-time would
    "bake in" whatever scale was current at storage time and corrupt
    comparisons if scale drifts mid-buffer.

RULES §4.1, `gestures/` Allowed: this module is a pure data buffer with
no camera / OS-automation / PyQt6 dependencies.

RULES §6.1: pure-Python `collections.deque` with `maxlen`, so memory
usage is bounded and oldest entries are evicted automatically as new
ones arrive (PRD FR-MH-02).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Iterable


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.9 / PRD FR-MH-01..04)
# ---------------------------------------------------------------------------

# Default buffer size if the caller does not pass an explicit value.
# Matches PRD FR-MH-01's recommended range lower bound (15 frames).
DEFAULT_MAX_FRAMES: int = 20

# Roles that the buffer always allocates storage for. Anything else
# passed to `update()` is also accepted (the buffer auto-creates a
# per-role deque), but pre-allocation avoids the first-frame dict
# allocation on the typical 2-hand setup.
DEFAULT_ROLES: tuple[str, ...] = ('HAND_A', 'HAND_B')


class MotionHistoryBuffer:
    """Per-hand-role rolling buffer of (x, y, timestamp_ms) wrist samples.

    Each `update()` appends one sample. The buffer auto-evicts the
    oldest entry once it reaches `max_frames` (PRD FR-MH-02). Storage
    is keyed by hand role (`'HAND_A'` / `'HAND_B'`), giving each role
    its own independent trajectory history (PRD FR-MH-04).

    Public methods:
        update(role, wrist_pos, now) -> None
        get(role) -> list[tuple[float, float, float]]
        clear(role) -> None
        snapshot() -> dict[str, list[tuple[float, float, float]]]

    `now` is the current timestamp in seconds (e.g. `time.monotonic()`)
    and is multiplied by 1000 internally to produce millisecond
    timestamps that match the gesture-rule reference implementations
    in TRD §4.4.
    """

    def __init__(
        self,
        max_frames: int = DEFAULT_MAX_FRAMES,
        roles: Iterable[str] = DEFAULT_ROLES,
    ) -> None:
        if max_frames <= 0:
            raise ValueError(
                f'max_frames must be > 0; got {max_frames}'
            )
        self.max_frames = int(max_frames)
        self._buffers: dict[str, deque] = {
            role: deque(maxlen=self.max_frames) for role in roles
        }

    # -- Recording -----------------------------------------------------------

    def update(
        self,
        role: str,
        wrist_pos: tuple[float, float, float] | tuple[float, float],
        now: float,
    ) -> None:
        """Append a wrist sample for `role` at timestamp `now` (seconds).

        Storage is RAW (unnormalized). Do not divide by hand_scale here —
        see module docstring for the rationale (PRD FR-MH-03).
        """
        buf = self._buffers.get(role)
        if buf is None:
            # First time we've seen this role — auto-create its deque.
            buf = deque(maxlen=self.max_frames)
            self._buffers[role] = buf
        # Store the first two components (x, y) plus timestamp in ms.
        # The z component is intentionally dropped: all dynamic-gesture
        # rules in TRD §4.4 normalize displacement in the (x, y) plane.
        buf.append((float(wrist_pos[0]), float(wrist_pos[1]), float(now) * 1000.0))

    def clear(self, role: str) -> None:
        """Empty the buffer for a single role."""
        buf = self._buffers.get(role)
        if buf is not None:
            buf.clear()

    def reset(self) -> None:
        """Empty every role's buffer. Used on camera reconnect / pipeline restart."""
        for buf in self._buffers.values():
            buf.clear()

    # -- Read ----------------------------------------------------------------

    def get(self, role: str) -> list[tuple[float, float, float]]:
        """Return the current sample list for `role` (oldest first).

        Returns an empty list if the role has never been seen. The
        returned list is a fresh copy — the underlying deque continues
        to be mutated by future `update()` calls. Callers therefore
        cannot accidentally mutate the buffer by holding a reference.
        """
        buf = self._buffers.get(role)
        if buf is None:
            return []
        return list(buf)

    def snapshot(self) -> dict[str, list[tuple[float, float, float]]]:
        """Read-only copy of every role's buffer.

        Used by DiagnosticsManager's debug-overlay panel (PRD §12.3
        implicit) and by tests that want to assert multi-role behavior.
        """
        return {role: list(buf) for role, buf in self._buffers.items()}

    # -- Inspection ----------------------------------------------------------

    def __len__(self) -> int:
        """Total number of samples across all roles (for tests)."""
        return sum(len(buf) for buf in self._buffers.values())

    def roles(self) -> list[str]:
        """Roles for which a buffer has been created."""
        return list(self._buffers.keys())