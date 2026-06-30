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

# ---------------------------------------------------------------------------
# Configuration for thumb-extension recognition (multi-feature, scale-invariant)
# ---------------------------------------------------------------------------

# Minimum multi-feature score required for the thumb to be considered
# EXTENDED.  0.55 gives a safety margin above fist/curled (≈0.20–0.35)
# while keeping genuine Thumbs-Up / Open-Palm thumbs well above it
# (≈0.85–1.00).
THUMB_EXTENSION_THRESHOLD: float = 0.55

# Thumb-extension feature normalisation constants.
# Reach ratio:  tip_reach / mcp_reach  (1.0 = curled, 2.0 = straight out)
_THUMB_REACH_MIN: float = 1.0
_THUMB_REACH_MAX: float = 2.0
# Length ratio:  mcp_tip / cmc_mcp     (0.25 = tucked, 1.5 = extended)
_THUMB_LENGTH_MIN: float = 0.25
_THUMB_LENGTH_MAX: float = 1.50
# Separation ratio:  tip_idx_mcp / wrist_mcp  (0.5 = near palm, 2.5 = away)
_THUMB_SEPARATION_MIN: float = 0.5
_THUMB_SEPARATION_MAX: float = 2.5


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

    Defensive: returns all-`False` for any malformed input (empty list,
    short list that cannot index landmark IDs 5..20). Per RULES §6.4
    hot-path-never-raises.
    """
    out: dict[str, bool] = {}
    for name, (mcp_id, pip_id, tip_id) in FINGER_JOINTS.items():
        if len(landmarks) <= max(mcp_id, pip_id, tip_id):
            out[name] = False
            continue
        out[name] = is_finger_extended(
            landmarks, mcp_id, pip_id, tip_id,
            angle_threshold=angle_threshold,
        )
    return out


def thumb_extension_score(
    landmarks: list[tuple[float, float, float]],
    chirality: str = '',
) -> float:
    """Scale-invariant multi-feature thumb-extension score.

    Returns a float in ``[0.0, 1.0]``:
      ``0.0``  → thumb is tightly curled / folded across the palm,
      ``1.0``  → thumb is fully extended away from the palm.

    The score combines three independent, scale-invariant features:

    1. **Reach ratio**   (50 %)
       ``dist(wrist, thumb_tip) / dist(wrist, thumb_mcp)``
       Curled thumbs sit close to the palm, producing a ratio ≈ 1.0;
       extended thumbs reach out, producing a ratio ≈ 2.0 or more.

    2. **Length ratio**  (30 %)
       ``dist(mcp, tip) / dist(cmc, mcp)``
       Even if the reach ratio is modest, an extended thumb has a
       much larger *relative* length than a tucked thumb.

    3. **Separation ratio**  (20 %)
       ``dist(tip, index_mcp) / dist(wrist, mcp)``
       In a curled fist the thumb tip stays near the palmar index
       MCP; in a genuine thumbs-up / open-palm it is far away.

    All three features are pure ratios of distances, so the score
    is naturally scale-invariant and survives changes in camera
    distance (RULES §5.7).

    To prevent a single noisy feature from creating a false
    positive, the score is penalised if fewer than two of the
    three features are strongly active.
    """
    if len(landmarks) < max(INDEX_MCP, THUMB_TIP) + 1:
        return 0.0

    wrist = landmarks[WRIST]
    thumb_cmc = landmarks[THUMB_CMC]
    thumb_mcp = landmarks[THUMB_MCP]
    thumb_tip = landmarks[THUMB_TIP]
    index_mcp = landmarks[INDEX_MCP]

    # --- Feature 1: Reach ratio -------------------------------------------
    wrist_to_mcp = euclidean_distance(wrist, thumb_mcp)
    wrist_to_tip = euclidean_distance(wrist, thumb_tip)
    if wrist_to_mcp > 0.0:
        reach_ratio = wrist_to_tip / wrist_to_mcp
        score_reach = (reach_ratio - _THUMB_REACH_MIN) / (_THUMB_REACH_MAX - _THUMB_REACH_MIN)
        score_reach = max(0.0, min(1.0, score_reach))
    else:
        score_reach = 0.0

    # --- Feature 2: Length ratio ------------------------------------------
    cmc_to_mcp = euclidean_distance(thumb_cmc, thumb_mcp)
    mcp_to_tip = euclidean_distance(thumb_mcp, thumb_tip)
    if cmc_to_mcp > 0.0:
        length_ratio = mcp_to_tip / cmc_to_mcp
        score_length = (length_ratio - _THUMB_LENGTH_MIN) / (_THUMB_LENGTH_MAX - _THUMB_LENGTH_MIN)
        score_length = max(0.0, min(1.0, score_length))
    else:
        score_length = 0.0

    # --- Feature 3: Separation from palm centre ---------------------------
    tip_to_index = euclidean_distance(thumb_tip, index_mcp)
    if wrist_to_mcp > 0.0:
        separation_ratio = tip_to_index / wrist_to_mcp
        score_separation = (separation_ratio - _THUMB_SEPARATION_MIN) / (_THUMB_SEPARATION_MAX - _THUMB_SEPARATION_MIN)
        score_separation = max(0.0, min(1.0, score_separation))
    else:
        score_separation = 0.0

    # --- Combine -----------------------------------------------------------
    overall_score = (0.5 * score_reach
                    + 0.3 * score_length
                    + 0.2 * score_separation)

    # Penalise when only one feature is strongly active (multi-feature
    # guard against transitional false positives).
    active_features = sum([
        score_reach > 0.2,
        score_length > 0.2,
        score_separation > 0.2,
    ])
    if active_features < 2:
        overall_score *= 0.5

    return float(max(0.0, min(1.0, overall_score)))


def is_thumb_extended(
    landmarks: list[tuple[float, float, float]],
    chirality: str,
    horizontal_delta: float = 0.04,   # kept for backward API compatibility
    vertical_delta: float = 0.05,    # kept for backward API compatibility
) -> bool:
    """Chirality-aware thumb-extension test.

    Replaces the old displacement-only logic with a
    scale-invariant multi-feature score (see
    :func:`thumb_extension_score`). A score above
    :data:`THUMB_EXTENSION_THRESHOLD` is required for the thumb
    to be considered EXTENDED.

    The ``horizontal_delta`` and ``vertical_delta`` parameters
    are retained for API compatibility but no longer take effect.
    """
    score = thumb_extension_score(landmarks, chirality)
    return score >= THUMB_EXTENSION_THRESHOLD


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


def fist_compactness_ratio(
    landmarks: list[tuple[float, float, float]],
    palm_width: float,
) -> float:
    """Average normalized wrist-to-fingertip distance for the four
    non-thumb fingers.

    Used by :func:`gestures.static_recognizer.detect_fist` as the
    second independent geometric signal: a real Closed Fist has
    fingertips pulled in close to the wrist, while a hand with
    loosely-curled but extended fingers (or a transitional pose)
    will show a larger ratio.

    Args:
        landmarks: 21-element MediaPipe landmark list.
        palm_width: hand scale reference (typically
            ``HandData.scale.palm_width``). Used as the normalization
            denominator so the ratio is scale-invariant (RULES §5.7).

    Returns:
        Average ``dist(wrist, fingertip) / palm_width`` across the
        four non-thumb fingertips. Returns ``math.inf`` if
        ``palm_width <= 0.0`` so the caller can detect the
        degenerate case explicitly (RULES §6.4
        hot-path-never-raises).
    """
    if palm_width <= 0.0:
        return math.inf
    if len(landmarks) <= max(WRIST, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP):
        return math.inf
    wrist = landmarks[WRIST]
    tips = (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
    avg = sum(euclidean_distance(wrist, landmarks[t]) for t in tips) / len(tips)
    return avg / palm_width


def thumb_index_alignment_ratio(
    landmarks: list[tuple[float, float, float]],
) -> float:
    """Cosine similarity between the wrist→thumb-tip and
    wrist→index-tip direction vectors.

    Used by :func:`gestures.static_recognizer.detect_pinch` as the
    second independent geometric signal: a deliberate Pinch has
    the thumb tip and index tip meeting at a single point, so
    the two wrist→tip vectors point in nearly the same direction
    (cosine similarity ≈ 1.0). A coincidental close-proximity
    (e.g., user points with index and the curled thumb happens
    to be near the index) yields a low cosine similarity.

    Args:
        landmarks: 21-element MediaPipe landmark list.

    Returns:
        Float in ``[0.0, 1.0]`` (cosine similarity clamped to the
        non-negative range — opposite-direction vectors score 0.0,
        which is the right answer for "not aligned" rather than
        -1.0). Returns 0.0 if the input is malformed or one of
        the vectors has zero length.
    """
    if len(landmarks) <= max(WRIST, THUMB_TIP, INDEX_TIP):
        return 0.0
    wx, wy, _ = landmarks[WRIST]
    tx, ty, _ = landmarks[THUMB_TIP]
    ix, iy, _ = landmarks[INDEX_TIP]
    v1x, v1y = tx - wx, ty - wy
    v2x, v2y = ix - wx, iy - wy
    m1 = math.hypot(v1x, v1y)
    m2 = math.hypot(v2x, v2y)
    if m1 == 0.0 or m2 == 0.0:
        return 0.0
    cos = (v1x * v2x + v1y * v2y) / (m1 * m2)
    return float(max(0.0, min(1.0, cos)))


def remaining_fingers_curled_score(
    landmarks: list[tuple[float, float, float]],
    palm_width: float,
) -> float:
    """Average normalized wrist-to-fingertip distance for the
    three remaining non-thumb, non-index fingers (middle, ring,
    pinky).

    Used by :func:`gestures.static_recognizer.detect_pinch` as the
    third independent geometric signal: a Pinch has these three
    fingertips pulled in close to the palm (low score), while a
    pose where middle/ring/pinky are extended (e.g., Open Palm or
    Three Fingers) yields a high score and is rejected.

    Args:
        landmarks: 21-element MediaPipe landmark list.
        palm_width: hand scale reference (typically
            ``HandData.scale.palm_width``).

    Returns:
        Average ``dist(wrist, fingertip) / palm_width`` across
        middle / ring / pinky. Returns ``math.inf`` if
        ``palm_width <= 0.0`` (RULES §6.4).
    """
    if palm_width <= 0.0:
        return math.inf
    if len(landmarks) <= max(WRIST, MIDDLE_TIP, RING_TIP, PINKY_TIP):
        return math.inf
    wrist = landmarks[WRIST]
    tips = (MIDDLE_TIP, RING_TIP, PINKY_TIP)
    avg = sum(euclidean_distance(wrist, landmarks[t]) for t in tips) / len(tips)
    return avg / palm_width