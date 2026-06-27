"""Shared geometry primitives for gesture recognition (CP-2).

Implements TRD §4.3 (Scale-Invariant Recognition — Reference Implementation)
and TRD §5.3 (Rotation-Tolerant Angle Method). These primitives are the
foundation that every static and dynamic gesture rule in Checkpoint 3
consumes.

The functions in this module are pure-Python, allocation-light, and free
of any camera / MediaPipe / OS-automation dependencies (RULES §4.1,
`gestures/` Forbidden Responsibilities).

RULES §5.7: every helper that produces a numeric measurement is
scale-invariant by construction (ratio of vectors, not absolute pixels).
"""

from __future__ import annotations

import math
from typing import Iterable


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §4.3 / §5.3)
# ---------------------------------------------------------------------------

# Default PIP-joint angle (degrees) above which a finger is considered
# EXTENDED. ~180 deg = perfectly straight; lower = more bent. The 160 deg
# threshold is the TRD §4.3 reference implementation default and matches
# the canonical gesture-recognition literature.
FINGER_EXTENSION_ANGLE_DEG: float = 160.0

# Indices into MediaPipe's 21-landmark hand array, grouped by finger.
# Each tuple is (MCP, PIP, TIP) — exactly the three joints needed to
# measure the PIP angle for extension classification (TRD §4.3).
FINGER_JOINTS: dict[str, tuple[int, int, int]] = {
    'index':  (5, 6, 8),
    'middle': (9, 10, 12),
    'ring':   (13, 14, 16),
    'pinky':  (17, 18, 20),
}

# Landmark indices used elsewhere in the recognition engine.
WRIST: int = 0
THUMB_CMC: int = 1
THUMB_MCP: int = 2
THUMB_IP: int = 3
THUMB_TIP: int = 4
INDEX_MCP: int = 5
INDEX_PIP: int = 6
INDEX_DIP: int = 7
INDEX_TIP: int = 8
MIDDLE_MCP: int = 9
MIDDLE_TIP: int = 12
RING_TIP: int = 16
PINKY_MCP: int = 17
PINKY_TIP: int = 20

# Thumb has different joint geometry than the other four fingers
# (TRD §4.3 `is_thumb_extended` note), so the chirality-aware
# dual-axis (horizontal-and-vertical) test is provided separately.
# The horizontal threshold is normalized to wrist-relative units
# (0..1 in frame space); the vertical threshold is in the same units
# and matches the typical "thumb tip is at least 5% of frame height
# above the thumb MCP" geometry of a Thumbs-Up pose.
THUMB_EXTENSION_HORIZONTAL_DELTA: float = 0.04
THUMB_EXTENSION_VERTICAL_DELTA: float = 0.05


# ---------------------------------------------------------------------------
# Distance / angle primitives
# ---------------------------------------------------------------------------

def euclidean_distance(
    a: tuple[float, float, float] | tuple[float, float],
    b: tuple[float, float, float] | tuple[float, float],
) -> float:
    """Euclidean distance between two 2D or 3D points.

    Scale-invariant in itself; combined with `HandData.scale` it produces
    ratios that survive changes in user-to-camera distance (PRD §5,
    TRD §4.2).
    """
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    if len(a) >= 3 and len(b) >= 3:
        dz = a[2] - b[2]
        return math.hypot(dx, dy, dz)
    return math.hypot(dx, dy)


def finger_angle(
    mcp: tuple[float, float, float] | tuple[float, float],
    pip: tuple[float, float, float] | tuple[float, float],
    tip: tuple[float, float, float] | tuple[float, float],
) -> float:
    """Angle at the PIP joint, in degrees, in the 2D image plane.

    ~180 deg = straight (extended), small angles = sharply bent (curled).
    Scale-invariant by construction since it is a ratio of vectors, not
    an absolute distance. Implementation matches TRD §4.3's reference
    `finger_angle()` exactly.
    """
    v1x = mcp[0] - pip[0]
    v1y = mcp[1] - pip[1]
    v2x = tip[0] - pip[0]
    v2y = tip[1] - pip[1]

    mag1 = math.hypot(v1x, v1y)
    mag2 = math.hypot(v2x, v2y)
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0

    dot = v1x * v2x + v1y * v2y
    cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def is_finger_extended(
    landmarks: list[tuple[float, float, float]],
    mcp_id: int,
    pip_id: int,
    tip_id: int,
    angle_threshold: float = FINGER_EXTENSION_ANGLE_DEG,
) -> bool:
    """Return True if the (MCP, PIP, TIP) joint chain is at least `angle_threshold`
    degrees — i.e., the finger is straight enough to count as EXTENDED.
    """
    return finger_angle(landmarks[mcp_id], landmarks[pip_id], landmarks[tip_id]) >= angle_threshold


def finger_states(
    landmarks: list[tuple[float, float, float]],
    angle_threshold: float = FINGER_EXTENSION_ANGLE_DEG,
) -> dict[str, bool]:
    """EXTENDED / CURLED classification for the four non-thumb fingers.

    Returns a dict keyed by finger name (`'index'`, `'middle'`, `'ring'`,
    `'pinky'`) → bool (True == EXTENDED). The thumb is *not* classified
    here because its joint geometry differs; use `is_thumb_extended()`
    for that.
    """
    return {
        name: is_finger_extended(landmarks, *joints, angle_threshold=angle_threshold)
        for name, joints in FINGER_JOINTS.items()
    }


def is_thumb_extended(
    landmarks: list[tuple[float, float, float]],
    chirality: str,
    horizontal_delta: float = THUMB_EXTENSION_HORIZONTAL_DELTA,
    vertical_delta: float = THUMB_EXTENSION_VERTICAL_DELTA,
) -> bool:
    """Chirality-aware thumb-extension test.

    The thumb's joint geometry differs from the other four fingers:
    `finger_angle()` on the thumb's MCP/PIP/TIP triplet is unreliable
    because the thumb folds sideways rather than curling through the
    same plane as the other fingers (TRD §4.3 `is_thumb_extended` note).

    A thumb is considered EXTENDED if EITHER:
      (a) it is laterally extended — the thumb tip is horizontally
          past the thumb MCP by at least `horizontal_delta` (mirrored
          for chirality so a right-hand thumb extends LEFT, a left-
          hand thumb extends RIGHT), OR
      (b) it is vertically extended — the thumb tip is at least
          `vertical_delta` above the thumb MCP (i.e., pointing up).
          The vertical check is chirality-agnostic and supports
          Thumbs-Up gestures where the thumb does NOT fan sideways.

    This dual-axis check covers both Lateral (Open Palm, OK Sign)
    and Vertical (Thumbs Up) thumb poses without conflating them with
    a curled thumb (which lies close to the index MCP and is neither
    laterally nor vertically displaced).
    """
    thumb_tip = landmarks[THUMB_TIP]
    thumb_mcp = landmarks[THUMB_MCP]
    dx = thumb_tip[0] - thumb_mcp[0]
    dy = thumb_mcp[1] - thumb_tip[1]  # positive when tip is above MCP
    # Vertically extended: tip above MCP by vertical_delta.
    if dy >= vertical_delta:
        return True
    # Laterally extended: tip past MCP by horizontal_delta.
    if chirality == 'Right':
        return dx <= -horizontal_delta
    return dx >= horizontal_delta


def extended_finger_count(
    landmarks: list[tuple[float, float, float]],
    chirality: str,
    angle_threshold: float = FINGER_EXTENSION_ANGLE_DEG,
) -> int:
    """Count of extended fingers (thumb + 4). Range 0..5.

    Used by ConflictResolver's tie-break priority table (TRD §3.9.2):
    gestures with fewer extended fingers are more geometrically specific
    and preferred over more general poses. A single integer count is
    easier to compare than a four-element boolean dict.
    """
    count = sum(1 for v in finger_states(landmarks, angle_threshold).values() if v)
    if is_thumb_extended(landmarks, chirality):
        count += 1
    return count


def normalized_distance(
    a: tuple[float, float, float] | tuple[float, float],
    b: tuple[float, float, float] | tuple[float, float],
    scale: float,
) -> float:
    """Euclidean distance divided by a per-hand scale reference.

    This is the canonical scale-invariant normalization primitive (PRD §5,
    TRD §4.2). Returns `inf` if `scale <= 0` so callers can detect the
    degenerate case explicitly rather than receiving a silent `ZeroDivisionError`
    (RULES §6.4 hot-path-never-raises).
    """
    if scale <= 0.0:
        return math.inf
    return euclidean_distance(a, b) / scale


def pinch_distance_ratio(
    landmarks: list[tuple[float, float, float]],
    scale: float,
) -> float:
    """Normalized thumb-tip / index-tip distance — the canonical Pinch
    and OK-Sign normalization primitive (TRD §4.3, PRD §5.2 worked example).
    """
    return normalized_distance(landmarks[THUMB_TIP], landmarks[INDEX_TIP], scale)


def all_fingers_curled(landmarks: list[tuple[float, float, float]]) -> bool:
    """Convenience predicate: all four non-thumb fingers curled."""
    states = finger_states(landmarks)
    return not any(states.values())


def all_fingers_extended(
    landmarks: list[tuple[float, float, float]],
    chirality: str,
) -> bool:
    """Convenience predicate: all five fingers extended (Open Palm)."""
    states = finger_states(landmarks)
    return all(states.values()) and is_thumb_extended(landmarks, chirality)