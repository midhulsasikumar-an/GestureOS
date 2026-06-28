"""Unit tests for gesture_utils — CP-2 geometry primitives.

Per TRD §13.2: no live camera required. Tests load landmark fixtures
from tests/fixtures/sample_landmarks.json and exercise the scale-
invariant primitives in gestures/gesture_utils.py.
"""

from __future__ import annotations

import math

import pytest

from gestures.gesture_utils import (
    FINGER_JOINTS,
    FINGER_EXTENSION_ANGLE_DEG,
    INDEX_MCP,
    INDEX_TIP,
    MIDDLE_TIP,
    PINKY_MCP,
    PINKY_TIP,
    THUMB_TIP,
    WRIST,
    all_fingers_curled,
    all_fingers_extended,
    euclidean_distance,
    extended_finger_count,
    finger_angle,
    finger_states,
    is_finger_extended,
    is_thumb_extended,
    normalized_distance,
    pinch_distance_ratio,
)

from tests.conftest import load_pose_landmarks


# ======================================================================
# euclidean_distance
# ======================================================================

class TestEuclideanDistance:
    def test_zero_distance(self) -> None:
        assert euclidean_distance((0.0, 0.0), (0.0, 0.0)) == 0.0
        assert euclidean_distance((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == 0.0

    def test_axis_aligned_2d(self) -> None:
        # 3-4-5 right triangle
        assert euclidean_distance((0.0, 0.0), (3.0, 4.0)) == pytest.approx(5.0)

    def test_axis_aligned_3d(self) -> None:
        # 1-2-2 box -> diagonal sqrt(9) = 3
        assert euclidean_distance((0.0, 0.0, 0.0), (1.0, 2.0, 2.0)) == pytest.approx(3.0)

    def test_negative_coords(self) -> None:
        # Distance is always non-negative regardless of sign.
        assert euclidean_distance((-1.0, -1.0), (1.0, 1.0)) == pytest.approx(math.sqrt(8.0))

    def test_symmetric(self) -> None:
        a = (0.3, 0.7)
        b = (0.9, 0.2)
        assert euclidean_distance(a, b) == pytest.approx(euclidean_distance(b, a))


# ======================================================================
# finger_angle / is_finger_extended
# ======================================================================

class TestFingerAngle:
    def test_perfectly_straight_returns_180(self) -> None:
        # Collinear MCP-PIP-TIP along the y-axis, MCP below PIP below TIP
        mcp = (0.0, 0.0)
        pip = (0.0, 0.5)
        tip = (0.0, 1.0)
        # finger_angle computes the angle between vectors (mcp-pip)
        # and (tip-pip). For a perfectly straight finger these vectors
        # point in OPPOSITE directions -> 180 deg.
        angle = finger_angle(mcp, pip, tip)
        assert angle == pytest.approx(180.0, abs=1e-6)

    def test_fully_bent_returns_small_angle(self) -> None:
        # MCP and TIP at the same point -> vectors cancel -> 0 deg.
        mcp = (0.0, 0.5)
        pip = (0.0, 0.5)
        tip = (0.0, 0.5)
        angle = finger_angle(mcp, pip, tip)
        assert angle == pytest.approx(0.0, abs=1e-6)

    def test_right_angle_returns_90(self) -> None:
        # MCP to the left of PIP, TIP above PIP -> 90 deg.
        mcp = (-1.0, 0.0)
        pip = (0.0, 0.0)
        tip = (0.0, 1.0)
        angle = finger_angle(mcp, pip, tip)
        assert angle == pytest.approx(90.0, abs=1e-6)

    def test_zero_vector_returns_zero(self) -> None:
        # Degenerate case: mcp == pip. The function returns 0.0 instead
        # of crashing on ZeroDivisionError.
        assert finger_angle((0.0, 0.0), (0.0, 0.0), (1.0, 1.0)) == 0.0


class TestIsFingerExtended:
    def test_threshold_constant(self) -> None:
        # Pin the public constant to its reference value. Any future
        # tuning must be a deliberate change to this constant.
        assert FINGER_EXTENSION_ANGLE_DEG == 160.0

    def test_open_palm_fingers_are_extended(self) -> None:
        landmarks = load_pose_landmarks('open_palm_right')
        for name, (mcp, pip, tip) in FINGER_JOINTS.items():
            assert is_finger_extended(landmarks, mcp, pip, tip), (
                f'{name} should be EXTENDED in open_palm_right'
            )

    def test_fist_fingers_are_not_extended(self) -> None:
        landmarks = load_pose_landmarks('fist_right')
        for name, (mcp, pip, tip) in FINGER_JOINTS.items():
            assert not is_finger_extended(landmarks, mcp, pip, tip), (
                f'{name} should be CURLED in fist_right'
            )


# ======================================================================
# finger_states
# ======================================================================

class TestFingerStates:
    def test_open_palm_all_extended(self) -> None:
        states = finger_states(load_pose_landmarks('open_palm_right'))
        assert states == {'index': True, 'middle': True, 'ring': True, 'pinky': True}

    def test_fist_all_curled(self) -> None:
        states = finger_states(load_pose_landmarks('fist_right'))
        assert states == {'index': False, 'middle': False, 'ring': False, 'pinky': False}

    def test_peace_sign_two_extended(self) -> None:
        states = finger_states(load_pose_landmarks('peace_sign_right'))
        # Index and Middle extended; Ring and Pinky curled.
        assert states['index'] is True
        assert states['middle'] is True
        assert states['ring'] is False
        assert states['pinky'] is False

    def test_three_fingers_three_extended(self) -> None:
        states = finger_states(load_pose_landmarks('three_fingers_right'))
        assert states['index'] is True
        assert states['middle'] is True
        assert states['ring'] is True
        assert states['pinky'] is False

    def test_keys_are_complete(self) -> None:
        # The dict must always have all four finger keys, even if every
        # finger is curled.
        states = finger_states(load_pose_landmarks('fist_right'))
        assert set(states.keys()) == {'index', 'middle', 'ring', 'pinky'}


# ======================================================================
# is_thumb_extended (chirality-aware)
# ======================================================================

class TestIsThumbExtended:
    def test_right_hand_open_palm_thumb_extended(self) -> None:
        # Right-hand open palm: thumb tip is at index 4 (x=0.30, y=0.18).
        # Thumb MCP is at index 2 (x=0.39, y=0.34). dx = 0.30 - 0.39 = -0.09,
        # which is < -THUMB_EXTENSION_HORIZONTAL_DELTA (0.04), so EXTENDED.
        landmarks = load_pose_landmarks('open_palm_right')
        assert is_thumb_extended(landmarks, 'Right')

    def test_left_hand_open_palm_thumb_extended(self) -> None:
        # Left-hand open palm: thumb tip is mirrored, x=0.70, MCP x=0.61.
        # dx = 0.70 - 0.61 = 0.09 > THUMB_EXTENSION_HORIZONTAL_DELTA -> EXTENDED.
        landmarks = load_pose_landmarks('open_palm_left')
        assert is_thumb_extended(landmarks, 'Left')

    def test_fist_thumb_not_extended(self) -> None:
        # Fist fixture has thumb tip near MCP (x=0.42 vs MCP x=0.44,
        # dx = -0.02), which is within the threshold (0.04) -> CURLED.
        landmarks = load_pose_landmarks('fist_right')
        assert not is_thumb_extended(landmarks, 'Right')

    def test_laterally_extended_thumb_detected_both_chiralities(self) -> None:
        # The old displacement-only logic was chirality-dependent through
        # its horizontal displacement check.  The new multi-feature score
        # (thumb_extension_score) is chirality-agnostic: it measures
        # geometric extension (reach, length, and palm-separation ratios)
        # which are independent of which hand the thumb belongs to.
        # Construct a hand with the thumb extended laterally but with
        # negligible vertical displacement — the score must classify it
        # as extended for BOTH right and left chirality.
        landmarks = [
            (0.50, 0.50, 0.0),  # wrist
            (0.45, 0.45, 0.0),  # thumb CMC
            (0.40, 0.40, 0.0),  # thumb MCP
            (0.35, 0.35, 0.0),  # thumb IP
            (0.30, 0.39, 0.0),  # thumb TIP — lateral, negligible vertical
            *[(0.50, 0.50, 0.0)] * 16,
        ]
        right = is_thumb_extended(landmarks, 'Right')
        left = is_thumb_extended(landmarks, 'Left')
        # Both must be True because the thumb *is* geometrically extended
        # (the multi-feature score sees a high reach and length ratio).
        assert right is True
        assert left is True


# ======================================================================
# extended_finger_count
# ======================================================================

class TestExtendedFingerCount:
    def test_fist_count_is_zero(self) -> None:
        landmarks = load_pose_landmarks('fist_right')
        assert extended_finger_count(landmarks, 'Right') == 0

    def test_open_palm_count_is_five(self) -> None:
        landmarks = load_pose_landmarks('open_palm_right')
        assert extended_finger_count(landmarks, 'Right') == 5

    def test_peace_sign_count_is_two(self) -> None:
        landmarks = load_pose_landmarks('peace_sign_right')
        assert extended_finger_count(landmarks, 'Right') == 2

    def test_thumbs_up_count_is_one(self) -> None:
        landmarks = load_pose_landmarks('thumbs_up_right')
        assert extended_finger_count(landmarks, 'Right') == 1


# ======================================================================
# normalized_distance / pinch_distance_ratio
# ======================================================================

class TestNormalizedDistance:
    def test_basic_ratio(self) -> None:
        # 0.5 normalized units distance divided by 0.1 scale = 5.0
        assert normalized_distance((0.0, 0.0), (0.3, 0.4), 0.1) == pytest.approx(5.0)

    def test_scale_invariance_under_uniform_scaling(self) -> None:
        # Doubling both distance and scale must leave the ratio unchanged.
        d1 = normalized_distance((0.0, 0.0), (1.0, 0.0), 0.1)
        d2 = normalized_distance((0.0, 0.0), (2.0, 0.0), 0.2)
        assert d1 == pytest.approx(d2)

    def test_zero_scale_returns_inf(self) -> None:
        # Per RULES §6.4 hot-path-never-raises, a degenerate scale must
        # not crash the pipeline. Returns +inf so callers can detect.
        assert normalized_distance((0.0, 0.0), (1.0, 1.0), 0.0) == math.inf
        assert normalized_distance((0.0, 0.0), (1.0, 1.0), -1.0) == math.inf


class TestPinchDistanceRatio:
    def test_pinch_right_below_threshold(self) -> None:
        # The pinch fixture's thumb-tip / index-tip distance is small
        # relative to its palm_width. With a normalized scale, the
        # ratio must be < 0.35 (the canonical pinch threshold).
        landmarks = load_pose_landmarks('pinch_right')
        # palm_width: distance between landmarks 5 (INDEX_MCP) and 17 (PINKY_MCP)
        palm_width = euclidean_distance(landmarks[INDEX_MCP], landmarks[PINKY_MCP])
        ratio = pinch_distance_ratio(landmarks, palm_width)
        assert ratio < 0.35, f'Pinch fixture should yield ratio < 0.35, got {ratio}'

    def test_open_palm_above_threshold(self) -> None:
        # The open-palm fixture's thumb-tip / index-tip distance is
        # much larger than its palm_width; ratio must be > 0.35.
        landmarks = load_pose_landmarks('open_palm_right')
        palm_width = euclidean_distance(landmarks[INDEX_MCP], landmarks[PINKY_MCP])
        ratio = pinch_distance_ratio(landmarks, palm_width)
        assert ratio > 0.35

    def test_scale_invariance_uniform_rescale(self) -> None:
        # Synthetically double all landmark coordinates around the wrist
        # (simulating the user moving twice as far from the camera).
        # The pinch ratio MUST stay the same (PRD §5.2 worked example).
        base = load_pose_landmarks('pinch_right')
        wrist = base[WRIST]
        scaled = [
            (wrist[0] + (lm[0] - wrist[0]) * 2.0,
             wrist[1] + (lm[1] - wrist[1]) * 2.0,
             lm[2] * 2.0)
            for lm in base
        ]
        base_palm = euclidean_distance(base[INDEX_MCP], base[PINKY_MCP])
        scaled_palm = euclidean_distance(scaled[INDEX_MCP], scaled[PINKY_MCP])
        base_ratio = pinch_distance_ratio(base, base_palm)
        scaled_ratio = pinch_distance_ratio(scaled, scaled_palm)
        assert base_ratio == pytest.approx(scaled_ratio, rel=1e-9), (
            f'Scale invariance violated: {base_ratio} vs {scaled_ratio}'
        )


# ======================================================================
# Convenience predicates
# ======================================================================

class TestConveniencePredicates:
    def test_all_curled_true_for_fist(self) -> None:
        assert all_fingers_curled(load_pose_landmarks('fist_right'))

    def test_all_curled_false_for_open_palm(self) -> None:
        assert not all_fingers_curled(load_pose_landmarks('open_palm_right'))

    def test_all_extended_true_for_open_palm(self) -> None:
        assert all_fingers_extended(load_pose_landmarks('open_palm_right'), 'Right')
        assert all_fingers_extended(load_pose_landmarks('open_palm_left'), 'Left')

    def test_all_extended_false_for_fist(self) -> None:
        assert not all_fingers_extended(load_pose_landmarks('fist_right'), 'Right')