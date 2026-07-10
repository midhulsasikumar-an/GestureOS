"""MotionHistoryService — Checkpoint 2 deliverable / V2.0 rename.

Implements TRD §3.9 / §4.5 (MotionHistoryBuffer). V2.0 rename of
`motion_history.py` with class renamed to `MotionHistoryService`.

Stores the previous N frames of wrist position per hand role, where
N is configurable via `Settings.motion_history_frames`.

Critical design property (PRD FR-MH-03, TRD §4.5):
    The buffer stores RAW (unnormalized) position + timestamp.
    Normalization by hand-scale happens at evaluation time.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Iterable


logger = logging.getLogger('gestureos')


DEFAULT_MAX_FRAMES: int = 20
DEFAULT_ROLES: tuple[str, ...] = ('HAND_A', 'HAND_B')


class MotionHistoryService:
    """Per-hand-role rolling buffer of (x, y, timestamp_ms) wrist samples.

    V2.0 rename of MotionHistoryBuffer.
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

    def snapshot(self) -> dict[str, list[tuple[float, float, float]]]:
        return {role: list(buf) for role, buf in self._buffers.items()}

    def __len__(self) -> int:
        return sum(len(buf) for buf in self._buffers.values())

    def roles(self) -> list[str]:
        return list(self._buffers.keys())
