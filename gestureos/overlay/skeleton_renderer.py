"""Hand skeleton rendering on the webcam preview frame.

Implements a minimal version of TRD §3.15 (OverlayEngine).  At Checkpoint
1 the renderer draws the MediaPipe hand-landmark skeleton: 21 landmark
points connected by the standard MediaPipe HAND_CONNECTIONS lines.

The renderer is a pure function of (frame, hands) → frame.  No Qt or
threading dependencies, so it can be unit-tested without a display.

Coordinate convention:
  - Input `landmarks` are normalized (0..1) frame coordinates
  - Output frame is in BGR pixel space (the same as `camera.read_frame()`)
  - Drawing respects the frame's pixel dimensions (not the normalized space)
"""

from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from models.data_models import HandData


# MediaPipe's standard hand-skeleton connections (pairs of landmark IDs).
# Each pair represents a "bone" between two adjacent landmarks.
_HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    # Thumb
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Index
    (0, 5), (5, 6), (6, 7), (7, 8),
    # Middle
    (0, 9), (9, 10), (10, 11), (11, 12),
    # Ring
    (0, 13), (13, 14), (14, 15), (15, 16),
    # Pinky
    (0, 17), (17, 18), (18, 19), (19, 20),
    # Palm
    (5, 9), (9, 13), (13, 17),
)

_POINT_COLOR = (0, 255, 0)       # BGR — green
_POINT_RADIUS = 4
_LINE_COLOR = (255, 255, 255)    # BGR — white
_LINE_THICKNESS = 2


def _denormalize(
    landmarks: Iterable[tuple[float, float, float]],
    width: int,
    height: int,
) -> list[tuple[int, int]]:
    """Convert normalized (x, y, z) into pixel-space (x, y) coordinates."""
    out: list[tuple[int, int]] = []
    for x, y, _z in landmarks:
        px = int(round(x * width))
        py = int(round(y * height))
        out.append((px, py))
    return out


def render_skeleton(
    frame: np.ndarray,
    hands: Iterable[HandData],
    point_color: tuple[int, int, int] = _POINT_COLOR,
    line_color: tuple[int, int, int] = _LINE_COLOR,
) -> np.ndarray:
    """Draw hand skeletons on the frame. Returns the modified frame.

    Args:
        frame: BGR frame (H, W, 3) uint8 — mutated in place AND returned
        hands: 0–2 HandData objects with `landmarks` populated

    Returns the same frame object for call-site convenience.
    """
    h, w = frame.shape[:2]
    for hand in hands:
        if len(hand.landmarks) != 21:
            continue  # malformed — skip
        points = _denormalize(hand.landmarks, w, h)
        # Draw connections first so points overlay on top
        for a, b in _HAND_CONNECTIONS:
            cv2.line(frame, points[a], points[b], line_color, _LINE_THICKNESS, cv2.LINE_AA)
        for p in points:
            cv2.circle(frame, p, _POINT_RADIUS, point_color, -1, cv2.LINE_AA)
    return frame