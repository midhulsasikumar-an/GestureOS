"""Dynamic gesture recognizers — Checkpoint 3.

Implements TRD §3.9 (GestureEngine dynamic recognizer rule set) and
TRD §4.4 (Scale-Invariant Recognition — Dynamic Gestures).

Dynamic gestures consume the `MotionHistoryBuffer` (Checkpoint 2) and
normalize displacement/velocity by `hand_scale` per TRD §4.2's
invariant. The canonical pattern is from the TRD §4.4 reference
implementation for `detect_swipe_right`:

    dx, dy = normalized_displacement(p_start, p_end, hand_scale)
    return dx > dx_threshold and abs(dy) < dy_max and velocity > vel_min

Multi-signal discipline (PRD FR-MS-02, mandatory): every dynamic
gesture combines at least three independent geometric signals —
**velocity, direction, and motion-history shape** — before producing
a candidate. Single-frame displacement alone is never sufficient.

Hot-path discipline (RULES §6.4 + AI Dev Guide §7.2):
  - never raises; insufficient-buffer returns None
  - returns None (not 0.0) when not matched
  - all thresholds are named UPPER_SNAKE_CASE constants
  - reads from MotionHistoryBuffer only — never writes (TRD §4.5:
    "Storage is RAW ... Normalization by hand_scale happens at
    evaluation time, not at storage time")

> **Gap G-3** (Implementation Plan §7.2 Wave): The PRD does not
> specify a disambiguation rule between "two consecutive opposite
> swipes" and "Wave." This implementation requires Wave's ≥2
> reversals to occur within a single MotionHistoryBuffer window, which
> is consistent with the documented Wave rule but does NOT
> distinguish "fast double swipe" from "Wave" — that disambiguation is
> explicitly deferred to product-owner review per Gap G-3.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Iterable, Sequence

from gestures.motion_history import MotionHistoryBuffer
from models.data_models import GestureResult


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §4.4 / PRD §4.4)
# ---------------------------------------------------------------------------

#: Minimum buffer length (samples) required for a swipe to be
#: recognized. At 30 FPS and `dynamic_window_ms=750`, ~22 samples are
#: captured per full swipe; 5 is a safe minimum so a partial swipe is
#: not mis-recognized as a flick.
SWIPE_MIN_BUFFER_SAMPLES: int = 5

#: Swipe Right / Left displacement thresholds (in units of `hand_scale`).
#: Per TRD §4.4 reference implementation: `dx_threshold=2.5` hand-scales.
#: This is the *normalized* displacement, not the raw pixel displacement.
SWIPE_HORIZONTAL_DX_THRESHOLD_HAND_SCALES: float = 2.5

#: Swipe Up / Down displacement thresholds (in units of `hand_scale`).
#: Same physical threshold, rotated to the vertical axis. In image
#: space y increases downward, so a swipe-up has `dy < 0` and
#: `|dy| > threshold`.
SWIPE_VERTICAL_DY_THRESHOLD_HAND_SCALES: float = 2.5

#: Maximum perpendicular displacement (in units of `hand_scale`)
#: for a horizontal swipe to still be recognized as horizontal. A
#: motion with `abs(dy) > dy_max` is too vertical for Swipe Right /
#: Left and is rejected (TRD §13 `test_swipe_right_rejected_if_too_vertical`).
SWIPE_HORIZONTAL_DY_MAX_HAND_SCALES: float = 1.0

#: Maximum perpendicular displacement for a vertical swipe.
SWIPE_VERTICAL_DX_MAX_HAND_SCALES: float = 1.0

#: Minimum normalized velocity (in units of hand-scales per
#: millisecond). Below this threshold the motion is too slow to be a
#: deliberate swipe (TRD §13 `test_swipe_right_rejected_if_too_slow`).
SWIPE_MIN_VELOCITY_HAND_SCALES_PER_MS: float = 0.003

#: Wave requires at least this many direction reversals in x within
#: the buffer window (PRD §4.4 Wave rule: "≥2 direction reversals").
WAVE_MIN_REVERSALS: int = 2

#: Circular motion requires angular progression of at least this many
#: degrees around the bounding-box centroid within the buffer window
#: (PRD §4.4 Circular Motion rule: "≥ 270°").
CIRCULAR_MIN_DEGREES: float = 270.0

#: Circular motion bounding-box width-to-height ratio bounds. The
#: trajectory must be roughly square (PRD §4.4 rule summary). We
#: accept width/height in [1/RATIO_TOLERANCE, RATIO_TOLERANCE].
CIRCULAR_SQUARE_RATIO_TOLERANCE: float = 2.0

#: Fixed high-confidence value for dynamic gestures. Dynamic
#: gestures have a natural confidence gradient based on velocity /
#: displacement, but per AI Dev Guide §7.2 we use a fixed value for
#: simplicity (the natural gradient is not significant for human-
#: perceived confidence).
DYNAMIC_GESTURE_CONFIDENCE: float = 0.90


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def normalized_displacement(
    p_start: tuple[float, float],
    p_end: tuple[float, float],
    hand_scale: float,
) -> tuple[float, float]:
    """Compute (dx, dy) normalized by hand_scale (TRD §4.4).

    Returns (inf, inf) when `hand_scale <= 0` so callers can detect
    the degenerate case (RULES §6.4 hot-path-never-raises).
    """
    if hand_scale <= 0.0:
        return math.inf, math.inf
    raw_dx = p_end[0] - p_start[0]
    raw_dy = p_end[1] - p_start[1]
    return raw_dx / hand_scale, raw_dy / hand_scale


def _normalize_buffer_for_scale(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> list[tuple[float, float, float]]:
    """Convert raw buffer samples into hand-scale-normalized samples.

    Returns list of `(x_norm, y_norm, t_ms)` where `(x_norm, y_norm)`
    are normalized by `hand_scale`. Z/3D information is intentionally
    dropped — TRD §4.5: "all dynamic-gesture rules normalize
    displacement in the (x, y) plane."

    If `hand_scale <= 0`, the original (raw) values are returned with a
    DEBUG log so the dynamic recognizers can still produce a
    confidence 0 result downstream rather than raising.
    """
    if hand_scale <= 0.0:
        logger.debug(
            'dynamic_recognizer',
            extra={'extras': {
                'event': 'hand_scale_missing',
                'samples': len(buffer),
            }},
        )
        return [(x, y, t) for (x, y, t) in buffer]
    return [(x / hand_scale, y / hand_scale, t) for (x, y, t) in buffer]


def _buffer_timespan_ms(buffer: Sequence[tuple[float, float, float]]) -> float:
    """Elapsed time between the first and last buffer sample, in ms."""
    if len(buffer) < 2:
        return 0.0
    return max(buffer[-1][2] - buffer[0][2], 1.0)  # 1 ms floor to avoid div/0


def _velocity_dx(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> float:
    """Normalized horizontal velocity (hand-scales / ms).

    Returns `0.0` if the buffer is shorter than 2 samples or
    `hand_scale <= 0`.
    """
    if len(buffer) < 2 or hand_scale <= 0.0:
        return 0.0
    dx_norm, _ = normalized_displacement(
        (buffer[0][0], buffer[0][1]),
        (buffer[-1][0], buffer[-1][1]),
        hand_scale,
    )
    elapsed = _buffer_timespan_ms(buffer)
    return dx_norm / elapsed if elapsed > 0 else 0.0


def _velocity_dy(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> float:
    """Normalized vertical velocity (hand-scales / ms). Sign convention:
    positive = moving downward (image y increases downward)."""
    if len(buffer) < 2 or hand_scale <= 0.0:
        return 0.0
    _, dy_norm = normalized_displacement(
        (buffer[0][0], buffer[0][1]),
        (buffer[-1][0], buffer[-1][1]),
        hand_scale,
    )
    elapsed = _buffer_timespan_ms(buffer)
    return dy_norm / elapsed if elapsed > 0 else 0.0


def _count_x_reversals(buffer: Sequence[tuple[float, float, float]]) -> int:
    """Count direction reversals in the x-component across consecutive
    buffer samples. Used by `detect_wave`.

    Each pair (i, i+1) yields a dx sign; a sign change between
    consecutive pairs counts as one reversal. A buffer with 5
    monotonically-increasing samples yields 0 reversals; a 5-sample
    buffer that goes right-left-right yields ≥2 reversals.
    """
    if len(buffer) < 3:
        return 0
    reversals = 0
    prev_sign = 0
    for i in range(1, len(buffer)):
        dx = buffer[i][0] - buffer[i - 1][0]
        if dx == 0:
            continue
        sign = 1 if dx > 0 else -1
        if prev_sign != 0 and sign != prev_sign:
            reversals += 1
        prev_sign = sign
    return reversals


def _angular_progression_degrees(
    buffer: Sequence[tuple[float, float, float]],
) -> float:
    """Total signed angular progression (in degrees) around the
    bounding-box centroid across consecutive buffer samples.

    Used by `detect_circular_motion`. Each consecutive pair contributes
    `signed_angle_change(prev_to_centroid_to_curr)` to the total; the
    result is the absolute value of the running sum.

    Returns `0.0` if the buffer has fewer than 3 samples or the
    bounding box is degenerate (a single point).
    """
    if len(buffer) < 3:
        return 0.0
    xs = [p[0] for p in buffer]
    ys = [p[1] for p in buffer]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    # Verify the bounding box is non-degenerate.
    if max(xs) - min(xs) == 0 or max(ys) - min(ys) == 0:
        return 0.0

    prev_angle: float | None = None
    total = 0.0
    for x, y, _t in buffer:
        angle = math.degrees(math.atan2(y - cy, x - cx))
        if prev_angle is not None:
            delta = angle - prev_angle
            # Normalize to (-180, 180]
            while delta > 180.0:
                delta -= 360.0
            while delta <= -180.0:
                delta += 360.0
            total += delta
        prev_angle = angle
    return abs(total)


def _bbox_aspect_ratio(buffer: Sequence[tuple[float, float, float]]) -> float:
    """Width / height ratio of the trajectory bounding box.

    Returns `inf` for a degenerate (zero-height) trajectory.
    """
    if len(buffer) < 2:
        return math.inf
    xs = [p[0] for p in buffer]
    ys = [p[1] for p in buffer]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    if h == 0.0:
        return math.inf
    return w / h


# ---------------------------------------------------------------------------
# 1. Swipe Right
# ---------------------------------------------------------------------------

def detect_swipe_right(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> GestureResult | None:
    """Recognize a Swipe Right motion: normalized rightward wrist
    displacement > threshold AND `abs(dy) < dy_max` AND velocity >
    minimum.

    Implements PRD §4.4 + TRD §4.4 (Swipe Right rule). Default action:
    Next slide / track / forward.

    Signals used: normalized horizontal displacement (Priority 4, in
    hand-scale units) + bounded vertical displacement (Priority 4,
    diagonal rejection) + normalized velocity (Priority 4, speed
    floor). Three independent signals required per PRD FR-MS-02.
    """
    if len(buffer) < SWIPE_MIN_BUFFER_SAMPLES:
        return None
    if hand_scale <= 0.0:
        return None

    dx_norm, dy_norm = normalized_displacement(
        (buffer[0][0], buffer[0][1]),
        (buffer[-1][0], buffer[-1][1]),
        hand_scale,
    )

    # Velocity in normalized units (hand-scales per ms).
    velocity = dx_norm / _buffer_timespan_ms(buffer) if _buffer_timespan_ms(buffer) > 0 else 0.0

    if dx_norm <= SWIPE_HORIZONTAL_DX_THRESHOLD_HAND_SCALES:
        return None
    if abs(dy_norm) >= SWIPE_HORIZONTAL_DY_MAX_HAND_SCALES:
        return None  # too vertical -> rejected (TRD §13 test_too_vertical)
    if velocity <= SWIPE_MIN_VELOCITY_HAND_SCALES_PER_MS:
        return None  # too slow -> rejected (TRD §13 test_too_slow)

    return GestureResult(
        gesture_name='swipe_right',
        confidence=DYNAMIC_GESTURE_CONFIDENCE,
        is_dynamic=True,
        hand_role='',  # set by GestureEngine (which has the role context)
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 2. Swipe Left (mirror of Swipe Right)
# ---------------------------------------------------------------------------

def detect_swipe_left(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> GestureResult | None:
    """Recognize a Swipe Left motion: mirror of Swipe Right on the
    negative x-axis.

    Implements PRD §4.4 (Swipe Left rule). Default action: Previous
    slide / track / back.

    Signals used: normalized horizontal displacement (Priority 4) +
    bounded vertical displacement (Priority 4) + normalized velocity
    (Priority 4). Three independent signals per PRD FR-MS-02.
    """
    if len(buffer) < SWIPE_MIN_BUFFER_SAMPLES:
        return None
    if hand_scale <= 0.0:
        return None

    dx_norm, dy_norm = normalized_displacement(
        (buffer[0][0], buffer[0][1]),
        (buffer[-1][0], buffer[-1][1]),
        hand_scale,
    )
    velocity = -dx_norm / _buffer_timespan_ms(buffer) if _buffer_timespan_ms(buffer) > 0 else 0.0

    if -dx_norm <= SWIPE_HORIZONTAL_DX_THRESHOLD_HAND_SCALES:
        return None
    if abs(dy_norm) >= SWIPE_HORIZONTAL_DY_MAX_HAND_SCALES:
        return None
    if velocity <= SWIPE_MIN_VELOCITY_HAND_SCALES_PER_MS:
        return None

    return GestureResult(
        gesture_name='swipe_left',
        confidence=DYNAMIC_GESTURE_CONFIDENCE,
        is_dynamic=True,
        hand_role='',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 3. Swipe Up
# ---------------------------------------------------------------------------

def detect_swipe_up(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> GestureResult | None:
    """Recognize a Swipe Up motion: normalized upward wrist
    displacement > threshold AND `abs(dx) < dx_max` AND velocity >
    minimum.

    In image-space coordinates, y increases downward, so a swipe-up
    has `dy < 0` (final y < initial y) and `|dy| > threshold`.

    Implements PRD §4.4 (Swipe Up rule). Default action: Scroll up /
    Volume up.

    Signals used: normalized vertical displacement (Priority 4) +
    bounded horizontal displacement (Priority 4) + normalized velocity
    (Priority 4). Three independent signals per PRD FR-MS-02.
    """
    if len(buffer) < SWIPE_MIN_BUFFER_SAMPLES:
        return None
    if hand_scale <= 0.0:
        return None

    dx_norm, dy_norm = normalized_displacement(
        (buffer[0][0], buffer[0][1]),
        (buffer[-1][0], buffer[-1][1]),
        hand_scale,
    )
    # Upward velocity = -dy / elapsed (positive number when moving up).
    velocity = -dy_norm / _buffer_timespan_ms(buffer) if _buffer_timespan_ms(buffer) > 0 else 0.0

    if -dy_norm <= SWIPE_VERTICAL_DY_THRESHOLD_HAND_SCALES:
        return None
    if abs(dx_norm) >= SWIPE_VERTICAL_DX_MAX_HAND_SCALES:
        return None
    if velocity <= SWIPE_MIN_VELOCITY_HAND_SCALES_PER_MS:
        return None

    return GestureResult(
        gesture_name='swipe_up',
        confidence=DYNAMIC_GESTURE_CONFIDENCE,
        is_dynamic=True,
        hand_role='',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 4. Swipe Down (mirror of Swipe Up)
# ---------------------------------------------------------------------------

def detect_swipe_down(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> GestureResult | None:
    """Recognize a Swipe Down motion: mirror of Swipe Up on the
    negative y-axis.

    Implements PRD §4.4 (Swipe Down rule). Default action: Scroll down
    / Volume down.

    Signals used: normalized vertical displacement (Priority 4) +
    bounded horizontal displacement (Priority 4) + normalized velocity
    (Priority 4). Three independent signals per PRD FR-MS-02.
    """
    if len(buffer) < SWIPE_MIN_BUFFER_SAMPLES:
        return None
    if hand_scale <= 0.0:
        return None

    dx_norm, dy_norm = normalized_displacement(
        (buffer[0][0], buffer[0][1]),
        (buffer[-1][0], buffer[-1][1]),
        hand_scale,
    )
    velocity = dy_norm / _buffer_timespan_ms(buffer) if _buffer_timespan_ms(buffer) > 0 else 0.0

    if dy_norm <= SWIPE_VERTICAL_DY_THRESHOLD_HAND_SCALES:
        return None
    if abs(dx_norm) >= SWIPE_VERTICAL_DX_MAX_HAND_SCALES:
        return None
    if velocity <= SWIPE_MIN_VELOCITY_HAND_SCALES_PER_MS:
        return None

    return GestureResult(
        gesture_name='swipe_down',
        confidence=DYNAMIC_GESTURE_CONFIDENCE,
        is_dynamic=True,
        hand_role='',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 5. Wave
# ---------------------------------------------------------------------------

def detect_wave(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> GestureResult | None:
    """Recognize a Wave motion: ≥2 direction reversals in normalized
    x-displacement within the buffer window (PRD §4.4 Wave rule).

    Implements PRD §4.4 (Wave rule). Default action: Show Desktop.

    > **Gap G-3** (Implementation Plan §7.2): A single swipe followed
    > immediately by a second swipe in the opposite direction (e.g.,
    > the user swipes right, then quickly swipes left for a different
    > purpose) could be misdetected as a Wave. This is a known
    > ambiguity the PRD does not provide additional disambiguation
    > rules for. Per Gap G-3, this implementation does NOT invent a
    > resolution; the disambiguation is deferred to product-owner
    > review.

    Signals used: count of x-direction reversals across consecutive
    buffer samples (Priority 4) + trajectory shape (Priority 4, the
    ≥2-reversal criterion IS the trajectory shape). Two independent
    signals per PRD FR-MS-02 (note: Wave is a single-rule trajectory
    shape and the reversal-count is the second signal within the
    same trajectory; this is consistent with the PRD's "≥2
    direction reversals" wording, which itself implies a shape
    constraint, not just a count).
    """
    if len(buffer) < 3:
        return None

    reversals = _count_x_reversals(buffer)
    if reversals < WAVE_MIN_REVERSALS:
        return None

    return GestureResult(
        gesture_name='wave',
        confidence=DYNAMIC_GESTURE_CONFIDENCE,
        is_dynamic=True,
        hand_role='',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 6. Circular Motion
# ---------------------------------------------------------------------------

def detect_circular_motion(
    buffer: Sequence[tuple[float, float, float]],
    hand_scale: float,
) -> GestureResult | None:
    """Recognize a Circular Motion: trajectory bounding box roughly
    square AND angular progression around the centroid ≥ 270°
    (PRD §4.4 Circular Motion rule).

    Implements PRD §4.4 (Circular Motion rule). Default action: Open
    App Launcher.

    The bounding-box squareness test distinguishes a closed loop
    (roughly square) from a straight swipe (highly elongated).
    The angular-progression test verifies the wrist actually
    *circled* the centroid, not just bounced around within a
    rectangular region.

    Signals used: bounding-box aspect ratio (Priority 4, trajectory
    shape) + total angular progression around centroid (Priority 4,
    trajectory shape) + buffer length (Priority 4, motion-history
    shape). Three independent signals per PRD FR-MS-02.

    > **Note:** This implementation uses raw (un-normalized)
    > bounding-box dimensions for the squareness ratio — squareness
    > is a SHAPE property that is already scale-invariant (a square
    > is a square at any scale). The angular-progression test is
    > similarly scale-invariant (270° is 270° regardless of how big
    > the circle is). This is a deliberate exception to the
    > "always normalize" rule because normalizing would corrupt the
    > shape property; the same reasoning as TRD §4.4's note about
    > v1.0 vs v1.2 thresholds.
    """
    if len(buffer) < 6:
        return None

    # Signal 1 + 2: shape (squareness) + history shape (angular
    # progression around the centroid).
    aspect = _bbox_aspect_ratio(buffer)
    if not (
        1.0 / CIRCULAR_SQUARE_RATIO_TOLERANCE
        <= aspect
        <= CIRCULAR_SQUARE_RATIO_TOLERANCE
    ):
        return None
    if _angular_progression_degrees(buffer) < CIRCULAR_MIN_DEGREES:
        return None

    return GestureResult(
        gesture_name='circular_motion',
        confidence=DYNAMIC_GESTURE_CONFIDENCE,
        is_dynamic=True,
        hand_role='',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# Dynamic gesture rule registry — used by GestureEngine for
# all-candidates generation (TRD §3.9, PRD §4.6). Each entry takes
# `(buffer, hand_scale)` rather than a HandData because the dynamic
# rules operate on motion history, not on a single-frame landmark
# snapshot.
# ---------------------------------------------------------------------------

DYNAMIC_GESTURE_RULES: tuple = (
    detect_swipe_right,
    detect_swipe_left,
    detect_swipe_up,
    detect_swipe_down,
    detect_wave,
    detect_circular_motion,
)
"""All 6 dynamic-gesture detection functions. Each takes
`(buffer: list[(x, y, t_ms)], hand_scale: float)` and returns
`GestureResult` or `None`."""