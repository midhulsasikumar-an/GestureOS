"""MotionHistoryService — Checkpoint 2 deliverable / V2.0 rename.

Implements TRD §3.7 (MotionHistoryService). V2.0 rename of
`motion_history.py` with class renamed to `MotionHistoryService`.

Stores the previous N frames of wrist position per hand role, where
N is configurable via `Settings.motion_history_frames`.

Critical design property (PRD FR-MH-03, TRD §4.5):
    The buffer stores RAW (unnormalized) position + timestamp.
    Normalization by hand-scale happens at evaluation time.

CP-2 (Tracking Stabilization) extensions (TRD §3.7 API):
    - `get_window(role, duration_ms)` — time-windowed query. Returns
      every sample in the per-role buffer whose timestamp is within
      `duration_ms` of the most-recent sample. Used by
      StabilityGate (CP-3) to confirm a gesture was held continuously
      for the configured stability window.
    - `get_hold_duration(role)` — returns the duration (seconds) for
      which `role` has been continuously observed (time-since-first
      sample-in-window). Used by the StabilityGate hold-timer.

RULES §6.3: this service is the sole store of per-hand temporal
landmark history. Static and Dynamic engines (when present) read from
it; no component maintains its own private temporal cache.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Iterable


logger = logging.getLogger('gestureos')


DEFAULT_MAX_FRAMES: int = 20
DEFAULT_ROLES: tuple[str, ...] = ('HAND_A', 'HAND_B')


class MotionHistoryService:
    """Per-hand-role rolling buffer of (x, y, timestamp_ms) wrist samples.

    V2.0 rename of MotionHistoryBuffer. CP-2 (Tracking Stabilization)
    adds the time-windowed read API (TRD §3.7): `get_window(role,
    duration_ms)` and `get_hold_duration(role)`.
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

    def update(
        self,
        role: str,
        wrist_pos: tuple[float, float, float] | tuple[float, float],
        now: float,
    ) -> None:
        buf = self._buffers.get(role)
        if buf is None:
            buf = deque(maxlen=self.max_frames)
            self._buffers[role] = buf
        buf.append((float(wrist_pos[0]), float(wrist_pos[1]), float(now) * 1000.0))

    def clear(self, role: str) -> None:
        buf = self._buffers.get(role)
        if buf is not None:
            buf.clear()

    def reset(self) -> None:
        for buf in self._buffers.values():
            buf.clear()

    def get(self, role: str) -> list[tuple[float, float, float]]:
        buf = self._buffers.get(role)
        if buf is None:
            return []
        return list(buf)

    def get_window(
        self,
        role: str,
        duration_ms: int,
    ) -> list[tuple[float, float, float]]:
        """Return the time-windowed subset of `role`'s recent samples.

        Implements TRD §3.7 (MotionHistoryService.get_window). Returns
        every `(x, y, timestamp_ms)` sample whose timestamp is within
        `duration_ms` milliseconds of the MOST RECENT sample for
        `role`. The window is measured against the most-recent
        sample (not against `time.time()`), so the result is
        deterministic regardless of when the caller invokes the
        method.

        Used by the Static Gesture Engine's stability check (CP-3):
        the gate confirms the candidate gesture was held continuously
        for `gesture_stability_window_ms` by querying
        `get_window(role, gesture_stability_window_ms)` and verifying
        that every returned sample carries the same gesture name.

        Args:
            role: hand role key (e.g. `'HAND_A'`).
            duration_ms: window size in milliseconds. Must be `>= 0`.
                A value of `0` returns only the most-recent sample.
                A negative value returns an empty list (defensive;
                never raises on the hot path per RULES §6.4).

        Returns:
            A new list of `(x, y, timestamp_ms)` tuples, ordered
            oldest-first. Returns `[]` for unknown roles or empty
            buffers.
        """
        try:
            if duration_ms < 0:
                return []
            buf = self._buffers.get(role)
            if buf is None or not buf:
                return []
            # The most recent sample's timestamp is the right edge of
            # the window. We measure against the latest sample, not
            # `time.time()`, so the result is deterministic and
            # frame-coherent.
            latest_ts_ms = buf[-1][2]
            cutoff_ms = latest_ts_ms - float(duration_ms)
            return [
                (x, y, t_ms)
                for (x, y, t_ms) in buf
                if t_ms >= cutoff_ms
            ]
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'motion_history',
                extra={'extras': {
                    'event': 'get_window_failed',
                    'role': role,
                    'duration_ms': duration_ms,
                    'error': str(exc),
                }},
            )
            return []

    def get_hold_duration(self, role: str) -> float:
        """Return how long `role` has been continuously observed, in seconds.

        Implements TRD §3.7 (MotionHistoryService.get_hold_duration).
        Returns `now - first_sample_timestamp` (seconds), where
        `now` is the timestamp of the most recent sample in the
        buffer. If the role has not been seen or the buffer is
        empty, returns `0.0`.

        Used by the Static Gesture Engine's stability check (CP-3):
        the gate compares `get_hold_duration(role)` against
        `gesture_stability_window_ms` to confirm a gesture has
        been held for the required window.

        Args:
            role: hand role key (e.g. `'HAND_A'`).

        Returns:
            Duration in seconds as a float. Always `>= 0.0`. Returns
            `0.0` for unknown roles or empty buffers.
        """
        try:
            buf = self._buffers.get(role)
            if buf is None or not buf:
                return 0.0
            first_ts_ms = buf[0][2]
            latest_ts_ms = buf[-1][2]
            duration_ms = latest_ts_ms - first_ts_ms
            if duration_ms < 0.0:
                return 0.0
            return duration_ms / 1000.0
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'motion_history',
                extra={'extras': {
                    'event': 'get_hold_duration_failed',
                    'role': role,
                    'error': str(exc),
                }},
            )
            return 0.0

    def snapshot(self) -> dict[str, list[tuple[float, float, float]]]:
        return {role: list(buf) for role, buf in self._buffers.items()}

    def __len__(self) -> int:
        return sum(len(buf) for buf in self._buffers.values())

    def roles(self) -> list[str]:
        return list(self._buffers.keys())
