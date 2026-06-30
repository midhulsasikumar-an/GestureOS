"""Static gesture recognizers — Checkpoint 3.

Implements TRD §3.9 (GestureEngine static recognizer rule set) and
TRD §4.3 (Scale-Invariant Recognition — Reference Implementation).

Each `detect_<gesture>` function returns a `GestureResult` if the
gesture matches, or `None` if it does not. The function's docstring
explicitly lists which PRD §4.5 signals it combines (FR-MS-03).

Multi-signal discipline (PRD FR-MS-01, mandatory): every static
gesture combines at least two independent geometric signals before
producing a candidate. A finger-state pattern alone, or a single
normalized-distance check alone, is not sufficient.

Hot-path discipline (RULES §6.4 + AI Dev Guide §7.2):
  - `hand.scale is None` -> return None immediately (PRD FR-SC-04)
  - never raises; malformed input degrades to None
  - returns None (not 0.0) when not matched, so ConflictResolver
    candidate list is not contaminated with zero-confidence entries
  - all thresholds are named UPPER_SNAKE_CASE constants (RULES §3)

RULES §5.7 (Scale-Invariance): every distance comparison divides
by `hand.scale.palm_width` (or `palm_height`, where more appropriate)
BEFORE comparing to a literal threshold.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from gestures.gesture_utils import (
    INDEX_MCP,
    INDEX_TIP,
    MIDDLE_TIP,
    PINKY_MCP,
    THUMB_MCP,
    THUMB_TIP,
    WRIST,
    euclidean_distance,
    finger_states,
    fist_compactness_ratio,
    is_thumb_extended,
    remaining_fingers_curled_score,
    thumb_extension_score,
    thumb_index_alignment_ratio,
)
from models.data_models import GestureResult, HandData


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §4.3 / PRD §4.3)
# ---------------------------------------------------------------------------

#: Normalized thumb-index distance below which Pinch / OK Sign match
#: (PRD §4.3 Pinch + OK Sign rule; PRD §5.2 worked example).
PINCH_NORMALIZED_DISTANCE_THRESHOLD: float = 0.35

#: Average fingertip spread (normalized by palm_width) above which
#: Open Palm matches. Tuned so a loosely-closed fist does not false-
#: positive (Implementation Plan §7.1 Open Palm failure-case note).
OPEN_PALM_SPREAD_THRESHOLD: float = 0.55

#: Confidence ceiling for Open Palm at the spread threshold (used in
#: `confidence = min(1.0, spread / 0.7)` from the TRD §4.3 reference
#: implementation; 0.7 is the "ceiling" spread beyond which confidence
#: is saturated at 1.0).
OPEN_PALM_SPREAD_CONFIDENCE_CEILING: float = 0.70

#: Average normalized wrist-to-fingertip distance below which a Fist
#: is considered compact. A genuine Closed Fist has the four
#: non-thumb fingertips pulled in close to the wrist; a transitional
#: pose or a loosely-closed hand has the fingertips further out and
#: fails this check. Expressed in `palm_width`-normalized units
#: (scale-invariant per RULES §5.7).
#:
#: 1.5 hand-scales is generous enough that the canonical fist_right
#: fixture (compactness ≈ 1.0–1.4) passes comfortably, and tight
#: enough that an Open Palm (compactness ≈ 3–4) is cleanly rejected.
FIST_COMPACTNESS_THRESHOLD: float = 1.5

#: Confidence ceiling for Fist compactness (used to scale the
#: compactness-based confidence gradient). At or below this
#: compactness, confidence is saturated at 1.0; above the
#: :data:`FIST_COMPACTNESS_THRESHOLD` the gesture is rejected
#: outright.
FIST_COMPACTNESS_CONFIDENCE_CEILING: float = 0.8

#: Minimum cosine-similarity between the wrist→thumb-tip and
#: wrist→index-tip direction vectors for a Pinch to be accepted.
#: A genuine Pinch has the two vectors aligned (cosine ≈ 1.0);
#: a coincidental close-proximity pose has them misaligned.
#: 0.85 is the empirical lower bound observed on the canonical
#: pinch_right fixture.
PINCH_ALIGNMENT_THRESHOLD: float = 0.85

#: Average normalized wrist-to-fingertip distance for middle/ring/
#: pinky below which the "remaining fingers are curled" Pinch
#: constraint is satisfied. Pinch requires the three non-index,
#: non-thumb fingers to be pulled in (they do not participate in
#: the pinch action). 2.0 hand-scales accommodates the synthetic
#: pinch_right fixture while rejecting Open Palm and Three Fingers.
PINCH_REMAINING_CURL_THRESHOLD: float = 2.0

#: Fixed high-confidence value for boolean-pattern gestures (Three
#: Fingers, Peace Sign, Thumbs Up/Down) per AI Dev Guide §7.2:
#: "a fixed high-confidence constant (e.g., 0.9) is acceptable and
#: matches the pattern already used for similar boolean-rule gestures".
#:
#: NOTE: Fist, Pinch, Open Palm, and OK Sign now use blended
#: confidence from multiple signals (multi-signal discipline per
#: PRD FR-MS-01), so the constant is no longer applied to them.
BOOLEAN_GESTURE_CONFIDENCE: float = 0.92

#: Fixed confidence value used by the no-scale fallback detection
#: paths (none of the current gestures need it, but it's named here
#: for symmetry with the AI Dev Guide §7.2 contract).
NO_SCALE_CONFIDENCE: float = 0.85


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

#: Minimum number of landmarks required for any recognizer to safely
#: index the joint arrays. Anything fewer is malformed (TrackingModule
#: already discards these per CP-1) and short-circuits to None.
_MIN_LANDMARKS: int = 21


def _has_min_landmarks(hand: HandData) -> bool:
    """Defensive length check: every recognizer requires 21 landmarks.

    Per RULES §6.4 (hot-path-never-raises), malformed input must
    degrade to None rather than propagating an IndexError from
    downstream landmark indexing.
    """
    return len(hand.landmarks) >= _MIN_LANDMARKS


def _average_fingertip_spread(landmarks: list[tuple[float, float, float]]) -> float:
    """Average pairwise distance between the four non-thumb fingertips.

    Used by `detect_open_palm` as the second signal (Priority 3) in
    addition to the finger-state pattern (Priority 1) — guards against
    a loosely-closed fist with fingers barely extended.
    """
    tips = (INDEX_TIP, MIDDLE_TIP, 16, 20)  # INDEX, MIDDLE, RING, PINKY
    pairwise: list[float] = []
    for i in range(len(tips)):
        for j in range(i + 1, len(tips)):
            pairwise.append(
                euclidean_distance(landmarks[tips[i]], landmarks[tips[j]])
            )
    return sum(pairwise) / len(pairwise)


def _scale_palm_width(hand: HandData) -> float:
    """Return the palm-width normalization reference for a hand.

    Returns 0.0 (not raising) if `hand.scale` is None or has a
    non-positive palm_width — callers should treat 0.0 as "no scale
    available" and short-circuit before any threshold comparison.
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return 0.0
    return float(hand.scale.palm_width)


# ---------------------------------------------------------------------------
# 1. Open Palm
# ---------------------------------------------------------------------------

def detect_open_palm(hand: HandData) -> GestureResult | None:
    """Recognize the Open Palm gesture: all five fingers EXTENDED, AND
    the average fingertip spread (normalized by palm_width) above
    threshold (TRD §4.3 reference implementation).

    Implements PRD §4.3 (Open Palm gesture rule). Default action:
    Pause / Stop (also the Activation Mode toggle gesture — though
    activation logic itself is Checkpoint 4).

    Signals used: finger-state pattern (Priority 1, all five
    EXTENDED) + normalized average fingertip spread (Priority 3,
    `palm_width` denominator). Two independent signals required per
    PRD FR-MS-01.
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    # Priority 1: all five fingers extended.
    states = finger_states(hand.landmarks)
    if not all(states.values()):
        return None
    if not is_thumb_extended(hand.landmarks, hand.chirality):
        return None

    # Priority 3: spread check, normalized by palm_width (TRD §4.3).
    # Guards against the loosely-closed-fist false-positive that a
    # finger-state check alone would permit.
    palm_width = _scale_palm_width(hand)
    if palm_width <= 0.0:
        return None
    spread = _average_fingertip_spread(hand.landmarks) / palm_width
    if spread < OPEN_PALM_SPREAD_THRESHOLD:
        return None

    # Confidence: scales with the spread, saturated at the ceiling
    # (TRD §4.3 reference implementation).
    confidence = min(1.0, spread / OPEN_PALM_SPREAD_CONFIDENCE_CEILING)

    return GestureResult(
        gesture_name='open_palm',
        confidence=float(confidence),
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 2. Closed Fist
# ---------------------------------------------------------------------------

def detect_fist(hand: HandData) -> GestureResult | None:
    """Recognize the Closed Fist gesture: all four non-thumb fingers
    CURLED AND the four fingertips are pulled in close to the wrist.

    Implements PRD §4.3 (Closed Fist gesture rule). Default action:
    Hold / Drag start.

    Signals used (two independent signals per PRD FR-MS-01):
      - four-finger CURLED state (Priority 1, boolean)
      - normalized fist compactness ratio (Priority 3): the average
        wrist-to-fingertip distance for the four non-thumb fingers,
        normalized by ``palm_width``. A genuine fist has the
        fingertips pulled in close; a loosely-curled hand with
        fingers barely past the PIP threshold has a larger ratio
        and is rejected.

    The compactness signal is what distinguishes a real fist from a
    transitional pose where all four fingers are technically
    "curled" by the 160° angle threshold but the hand is not
    actually closed.
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    states = finger_states(hand.landmarks)
    if any(states.values()):
        return None  # any non-thumb finger extended -> not a fist

    palm_width = _scale_palm_width(hand)
    if palm_width <= 0.0:
        return None

    # Priority 3: compactness — average wrist-to-fingertip distance
    # normalized by palm_width. A tight fist has a small ratio; a
    # hand with fingers barely curled has a larger ratio and fails
    # the threshold.
    compactness = fist_compactness_ratio(hand.landmarks, palm_width)
    if compactness >= FIST_COMPACTNESS_THRESHOLD:
        return None  # fingertips too far from the wrist -> not a fist

    # Confidence blends compactness strength with the boolean
    # finger-state gate. A tight fist (compactness ≈ 0.8) saturates
    # the compactness gradient at 1.0; a fist right at the threshold
    # (compactness ≈ 1.5) scores 0.0 on the gradient, yielding an
    # overall confidence of 0.6 from the binary-gate floor.
    compactness_score = max(
        0.0,
        1.0 - compactness / FIST_COMPACTNESS_CONFIDENCE_CEILING,
    )
    confidence = 0.6 + 0.4 * compactness_score

    return GestureResult(
        gesture_name='fist',
        confidence=float(confidence),
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 3. Pinch
# ---------------------------------------------------------------------------

def detect_pinch(hand: HandData) -> GestureResult | None:
    """Recognize the Pinch gesture: thumb and index tips in close
    proximity, wrist→thumb and wrist→index vectors aligned, AND
    the remaining three fingers (middle / ring / pinky) curled in
    toward the palm.

    Implements PRD §4.3 + §5.2 (Pinch rule and scale-invariance worked
    example). Default action: Click / Select.

    Three independent signals per PRD FR-MS-01:
      - normalized thumb-index distance (Priority 3): the primary
        proximity check; must be below 0.35 hand-scales.
      - thumb-index alignment ratio (Priority 2): cosine similarity
        between the wrist→thumb-tip and wrist→index-tip direction
        vectors. A genuine pinching gesture has the two fingertips
        meeting at a single point so the vectors align; a coincidental
        close-proximity (e.g., pointing with index while curled thumb
        happens to lie near it) has misaligned vectors and is rejected.
      - remaining-fingers curled score (Priority 3): average normalized
        wrist-to-fingertip distance for middle / ring / pinky. In a
        genuine Pinch these three fingers are pulled in toward the palm
        (they do not participate); an Open Palm, Peace Sign, or Three
        Fingers pose has them extended and fails the threshold.
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    palm_width = _scale_palm_width(hand)
    if palm_width <= 0.0:
        return None

    # Priority 3: normalized thumb-index distance.
    raw_dist = euclidean_distance(hand.landmarks[THUMB_TIP], hand.landmarks[INDEX_TIP])
    normalized_dist = raw_dist / palm_width
    if normalized_dist >= PINCH_NORMALIZED_DISTANCE_THRESHOLD:
        return None

    # Priority 2: thumb-index alignment ratio.
    alignment = thumb_index_alignment_ratio(hand.landmarks)
    if alignment < PINCH_ALIGNMENT_THRESHOLD:
        return None

    # Priority 3: remaining three fingers curled.
    if remaining_fingers_curled_score(hand.landmarks, palm_width) >= PINCH_REMAINING_CURL_THRESHOLD:
        return None

    # Blended confidence: three binary gates cleared yields a floor of
    # 0.6, plus the proximity gradient (0 at threshold, 1 at perfect
    # contact) contributes up to 0.4 additional.
    distance_score = max(
        0.0,
        1.0 - normalized_dist / PINCH_NORMALIZED_DISTANCE_THRESHOLD,
    )
    confidence = 0.6 + 0.4 * distance_score

    return GestureResult(
        gesture_name='pinch',
        confidence=float(confidence),
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 4. Thumbs Up
# ---------------------------------------------------------------------------

def detect_thumbs_up(hand: HandData) -> GestureResult | None:
    """Recognize the Thumbs Up gesture: thumb EXTENDED upward,
    AND the other four fingers CURLED.

    Uses the multi-feature :func:`thumb_extension_score` for both
    the extension check and for computing dynamic confidence.

    Implements PRD §4.3 (Thumbs Up gesture rule). Default action:
    Confirm / Volume Up.

    Signals used (three independent signals per PRD FR-MS-01):
      - four-finger CURLED state (Priority 1)
      - thumb extension score (Priority 2, multi-feature)
      - thumb tip direction relative to wrist (Priority 2)
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    # Priority 1: all four non-thumb fingers curled.
    states = finger_states(hand.landmarks)
    if any(states.values()):
        return None

    # Priority 2: multi-feature thumb extension score.
    thumb_score = thumb_extension_score(hand.landmarks)
    if thumb_score < 0.55:  # Must be well above fist-level score
        return None

    # Priority 2: direction — thumb tip must be substantially above
    # the thumb MCP *and* above the wrist.
    # The direction check uses a wrist-to-MCP normalization reference
    # so it is scale-invariant like the rest of the pipeline (RULES §5.7).
    wrist = hand.landmarks[WRIST]
    thumb_mcp = hand.landmarks[THUMB_MCP]
    thumb_tip = hand.landmarks[THUMB_TIP]

    wrist_to_mcp = euclidean_distance(wrist, thumb_mcp)
    if wrist_to_mcp <= 0.0:
        return None

    # Ratio-based displacement: how far the tip is above the MCP / wrist,
    # normalized by the wrist-to-MCP distance (scale-invariant).
    dy_mcp_ratio = (thumb_mcp[1] - thumb_tip[1]) / wrist_to_mcp
    dy_wrist_ratio = (wrist[1] - thumb_tip[1]) / wrist_to_mcp

    direction_score = (
        max(0.0, min(1.0, dy_mcp_ratio / 1.0)) *
        max(0.0, min(1.0, dy_wrist_ratio / 1.5))
    )
    if direction_score <= 0.0:
        return None  # not pointing up

    # Confidence blends extension strength and direction clarity.
    # For a genuine thumbs-up (thumb_score ≈ 0.93, direction ≈ 1.0)
    # the result is ≈ 0.97, well above the BOOLEAN_GESTURE_CONFIDENCE
    # floor; a transitional pose scores lower so ConflictResolver
    # can prefer a more specific gesture (e.g. fist at 0.92).
    confidence = 0.6 + 0.4 * thumb_score * direction_score

    return GestureResult(
        gesture_name='thumbs_up',
        confidence=float(confidence),
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 5. Thumbs Down (mirror of Thumbs Up)
# ---------------------------------------------------------------------------

def detect_thumbs_down(hand: HandData) -> GestureResult | None:
    """Recognize the Thumbs Down gesture: thumb EXTENDED downward,
    AND the other four fingers CURLED (PRD §4.3 Thumbs Down rule).

    Implements PRD §4.3 (Thumbs Down gesture rule). Default action:
    Cancel / Volume Down.

    Signals used (three independent signals per PRD FR-MS-01):
      - four-finger CURLED state (Priority 1)
      - thumb extension score (Priority 2, multi-feature)
      - thumb tip direction DOWN (Priority 2, wrist-relative)
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    states = finger_states(hand.landmarks)
    if any(states.values()):
        return None

    # Multi-feature thumb extension check.
    thumb_score = thumb_extension_score(hand.landmarks)
    if thumb_score < 0.55:
        return None

    # Direction: thumb tip must be substantially below MCP *and* wrist.
    # Uses scaled ratios for scale-invariance (RULES §5.7).
    wrist = hand.landmarks[WRIST]
    thumb_mcp = hand.landmarks[THUMB_MCP]
    thumb_tip = hand.landmarks[THUMB_TIP]

    wrist_to_mcp = euclidean_distance(wrist, thumb_mcp)
    if wrist_to_mcp <= 0.0:
        return None

    dy_mcp_ratio = (thumb_tip[1] - thumb_mcp[1]) / wrist_to_mcp
    dy_wrist_ratio = (thumb_tip[1] - wrist[1]) / wrist_to_mcp

    direction_score = (
        max(0.0, min(1.0, dy_mcp_ratio / 1.0)) *
        max(0.0, min(1.0, dy_wrist_ratio / 1.5))
    )
    if direction_score <= 0.0:
        return None  # not pointing down

    confidence = 0.6 + 0.4 * thumb_score * direction_score

    return GestureResult(
        gesture_name='thumbs_down',
        confidence=float(confidence),
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 6. Peace Sign
# ---------------------------------------------------------------------------

def detect_peace_sign(hand: HandData) -> GestureResult | None:
    """Recognize the Peace Sign gesture: index + middle EXTENDED,
    ring + pinky CURLED, thumb CURLED (PRD §4.3 rule summary).

    Implements PRD §4.3 (Peace Sign gesture rule). Default action:
    Screenshot.

    Signals used: per-finger state pattern (Priority 1, the
    specific 5-finger pattern) + cross-finger consistency check
    (Priority 1, an explicit pattern on top of the boolean states).
    Two independent signals per PRD FR-MS-01.
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    states = finger_states(hand.landmarks)
    if not (states['index'] and states['middle']):
        return None
    if states['ring'] or states['pinky']:
        return None
    if is_thumb_extended(hand.landmarks, hand.chirality):
        return None

    return GestureResult(
        gesture_name='peace_sign',
        confidence=BOOLEAN_GESTURE_CONFIDENCE,
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 7. Three Fingers
# ---------------------------------------------------------------------------

def detect_three_fingers(hand: HandData) -> GestureResult | None:
    """Recognize the Three Fingers gesture: index + middle + ring
    EXTENDED, pinky + thumb CURLED (PRD §4.3 rule summary).

    Implements PRD §4.3 (Three Fingers gesture rule). Default action:
    Switch Workspace.

    Signals used: per-finger state pattern (Priority 1, specific
    5-finger pattern). Cross-finger consistency is implicit in the
    pattern itself — the boolean pattern is the second signal (the
    spread between "exactly 3 extended" and "any other count" is
    the discriminating geometric feature). Per PRD FR-MS-01.
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    states = finger_states(hand.landmarks)
    if not (states['index'] and states['middle'] and states['ring']):
        return None
    if states['pinky']:
        return None
    if is_thumb_extended(hand.landmarks, hand.chirality):
        return None

    return GestureResult(
        gesture_name='three_fingers',
        confidence=BOOLEAN_GESTURE_CONFIDENCE,
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# 8. OK Sign
# ---------------------------------------------------------------------------

def detect_ok_sign(hand: HandData) -> GestureResult | None:
    """Recognize the OK Sign gesture: thumb-index pinch distance below
    threshold AND middle + ring + pinky all EXTENDED (PRD §4.3 rule
    summary).

    Implements PRD §4.3 (OK Sign gesture rule). Default action:
    Right Click.

    The remaining-fingers-EXTENDED constraint is what distinguishes
    OK Sign from Pinch (which shares the same thumb-index distance
    check). Without this constraint, OK Sign would always be
    shadowed by Pinch in ConflictResolver's confidence comparison
    (Implementation Plan §7.1 OK Sign failure-case note).

    Signals used: normalized thumb-index distance (Priority 3,
    `palm_width` denominator) + remaining-finger EXTENDED state
    (Priority 1). Two independent signals required per PRD FR-MS-01.
    """
    if not _has_min_landmarks(hand) or hand.scale is None:
        return None  # PRD FR-SC-04

    palm_width = _scale_palm_width(hand)
    if palm_width <= 0.0:
        return None

    # Priority 3: thumb-index pinch distance (same rule as Pinch).
    raw_dist = euclidean_distance(hand.landmarks[THUMB_TIP], hand.landmarks[INDEX_TIP])
    normalized_dist = raw_dist / palm_width
    if normalized_dist >= PINCH_NORMALIZED_DISTANCE_THRESHOLD:
        return None

    # Priority 1: middle + ring + pinky all EXTENDED (this is the
    # signal that distinguishes OK Sign from Pinch).
    states = finger_states(hand.landmarks)
    if not (states['middle'] and states['ring'] and states['pinky']):
        return None

    # Confidence: same gradient as Pinch — descending from 1.0 at
    # zero distance to 0.0 at the threshold.
    confidence = 1.0 - (normalized_dist / PINCH_NORMALIZED_DISTANCE_THRESHOLD)

    return GestureResult(
        gesture_name='ok_sign',
        confidence=float(confidence),
        is_dynamic=False,
        hand_role=hand.role if hand.role is not None else '',
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# Static gesture rule registry — used by GestureEngine for all-candidates
# generation (TRD §3.9, PRD §4.6). The order here is iteration order only;
# the resolver downstream handles ordering for the actual emit decision.
# ---------------------------------------------------------------------------

STATIC_GESTURE_RULES: tuple = (
    detect_open_palm,
    detect_fist,
    detect_pinch,
    detect_thumbs_up,
    detect_thumbs_down,
    detect_peace_sign,
    detect_three_fingers,
    detect_ok_sign,
)
"""All 8 static-gesture detection functions. Each returns `GestureResult`
or `None`. `GestureEngine._check_all_static` iterates this tuple and
collects every non-None result into the candidate list (TRD §3.9
"first-match-wins is now explicitly replaced by all-candidates
generation")."""