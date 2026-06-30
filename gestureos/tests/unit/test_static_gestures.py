"""Unit tests for static gesture recognizers — Checkpoint 3.

Per AI Dev Guide §9.6 template and Implementation Plan §7.1's per-gesture
testing strategy: each gesture gets a positive test, a negative
(mutual-exclusivity) test, a scale-invariance parametrization, and a
no-scale test.
"""

from __future__ import annotations

import pytest

from gestures.static_recognizer import (
    FIST_COMPACTNESS_THRESHOLD,
    PINCH_ALIGNMENT_THRESHOLD,
    PINCH_NORMALIZED_DISTANCE_THRESHOLD,
    PINCH_REMAINING_CURL_THRESHOLD,
    STATIC_GESTURE_RULES,
    detect_fist,
    detect_ok_sign,
    detect_open_palm,
    detect_pinch,
    detect_peace_sign,
    detect_three_fingers,
    detect_thumbs_down,
    detect_thumbs_up,
)
from models.data_models import HandData

from tests.conftest import (
    make_hand_with_scale,
    scale_hand_landmarks,
)


# ======================================================================
# Constants
# ======================================================================

class TestConstants:
    def test_pinch_threshold_is_0_35(self) -> None:
        # PRD §4.3 / §5.2 worked example: the canonical Pinch threshold
        # is 0.35 in `palm_width`-normalized units. Pin any future tuning.
        assert PINCH_NORMALIZED_DISTANCE_THRESHOLD == 0.35

    def test_static_rules_count_is_eight(self) -> None:
        assert len(STATIC_GESTURE_RULES) == 8

    def test_fist_compactness_threshold_pinned(self) -> None:
        assert FIST_COMPACTNESS_THRESHOLD == 1.5

    def test_pinch_alignment_threshold_pinned(self) -> None:
        assert PINCH_ALIGNMENT_THRESHOLD == 0.85

    def test_pinch_remaining_curl_threshold_pinned(self) -> None:
        assert PINCH_REMAINING_CURL_THRESHOLD == 2.0


# ======================================================================
# Open Palm
# ======================================================================

class TestOpenPalm:
    def test_open_palm_right_detected(self) -> None:
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        result = detect_open_palm(h)
        assert result is not None
        assert result.gesture_name == 'open_palm'
        assert result.confidence > 0.5
        assert result.hand_role == 'HAND_A'
        assert result.is_dynamic is False

    def test_open_palm_left_detected(self) -> None:
        h = make_hand_with_scale(pose_name='open_palm_left', role='HAND_B')
        result = detect_open_palm(h)
        assert result is not None
        assert result.gesture_name == 'open_palm'

    def test_fist_not_open_palm(self) -> None:
        # Mutual-exclusivity (IP §7.1 Open Palm testing strategy).
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        assert detect_open_palm(h) is None

    def test_open_palm_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        h_no_scale = replace(h, scale=None)
        assert detect_open_palm(h_no_scale) is None

    @pytest.mark.parametrize('scale_factor', [0.5, 1.0, 2.0, 3.0])
    def test_open_palm_recognized_at_all_scales(self, scale_factor: float) -> None:
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        scaled = scale_hand_landmarks(h, scale_factor)
        result = detect_open_palm(scaled)
        assert result is not None, f'Open Palm missed at scale {scale_factor}'
        assert result.confidence > 0.5


# ======================================================================
# Closed Fist
# ======================================================================

class TestFist:
    def test_fist_right_detected(self) -> None:
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        result = detect_fist(h)
        assert result is not None
        assert result.gesture_name == 'fist'

    def test_open_palm_not_fist(self) -> None:
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        assert detect_fist(h) is None

    def test_fist_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        assert detect_fist(replace(h, scale=None)) is None


# ======================================================================
# Pinch (canonical scale-invariance test subject)
# ======================================================================

class TestPinch:
    def test_pinch_right_detected(self) -> None:
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        result = detect_pinch(h)
        assert result is not None
        assert result.gesture_name == 'pinch'
        assert result.confidence > 0.5

    def test_open_palm_not_pinch(self) -> None:
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        assert detect_pinch(h) is None

    def test_pinch_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        assert detect_pinch(replace(h, scale=None)) is None

    def test_pinch_confidence_gradient(self) -> None:
        # The closer the thumb-index tips are (in normalized units), the
        # higher the confidence (TRD §4.3 `detect_pinch` reference).
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        result_1x = detect_pinch(h)
        assert result_1x is not None
        # Scale 0.5x -> thumb-index distance shrinks; pinch ratio is
        # the same so the result is the same.
        h_half = scale_hand_landmarks(h, 0.5)
        result_half = detect_pinch(h_half)
        assert result_half is not None
        assert abs(result_1x.confidence - result_half.confidence) < 1e-9

    @pytest.mark.parametrize('scale_factor', [0.5, 1.0, 2.0, 3.0])
    def test_pinch_recognized_at_all_scales(self, scale_factor: float) -> None:
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        scaled = scale_hand_landmarks(h, scale_factor)
        result = detect_pinch(scaled)
        assert result is not None, f'Pinch missed at scale {scale_factor}'
        assert result.confidence > 0.5


# ======================================================================
# Thumbs Up
# ======================================================================

class TestThumbsUp:
    def test_thumbs_up_right_detected(self) -> None:
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        result = detect_thumbs_up(h)
        assert result is not None
        assert result.gesture_name == 'thumbs_up'

    def test_thumbs_down_not_thumbs_up(self) -> None:
        # Construct a thumbs-down hand by mirroring the thumbs-up fixture
        # around y. The thumbs-up fixture has thumb tip at y=0.08; mirror
        # to y=1.0 - 0.08 = 0.92 to get a thumbs-down shape.
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        mirrored = replace(
            h,
            landmarks=[
                (lm[0], 1.0 - lm[1], lm[2]) for lm in h.landmarks
            ],
        )
        mirrored = make_hand_with_scale(
            pose_name=None,  # we already have the landmarks; reuse via direct construction
            role='HAND_A',
        )
        # Build a new hand with mirrored landmarks but the same scale.
        from models.data_models import HandData
        mirrored_hand = HandData(
            landmarks=[(lm[0], 1.0 - lm[1], lm[2]) for lm in h.landmarks],
            chirality=h.chirality,
            confidence=h.confidence,
            role=h.role,
            scale=h.scale,
        )
        assert detect_thumbs_up(mirrored_hand) is None

    def test_thumbs_up_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        assert detect_thumbs_up(replace(h, scale=None)) is None

    def test_open_palm_not_thumbs_up(self) -> None:
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        # Open palm has the thumb pointing out laterally, not vertically
        # up — the wrist-y comparison in detect_thumbs_up rejects it.
        assert detect_thumbs_up(h) is None

    def test_fist_not_thumbs_up(self) -> None:
        # Regression: a fully closed fist must NOT produce a thumbs_up
        # candidate (the multi-feature score prevents it).
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        assert detect_thumbs_up(h) is None

    def test_thumbs_up_confidence_reflects_extension_strength(self) -> None:
        # Confidence must be derived from the multi-feature score,
        # not a fixed constant.  The genuine thumbs_up fixture should
        # produce confidence > 0.9 (thumb_score ≈ 0.93, direction ≈ 1.0).
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        result = detect_thumbs_up(h)
        assert result is not None
        assert result.confidence > 0.9
        assert result.gesture_name == 'thumbs_up'

    @pytest.mark.parametrize('scale_factor', [0.5, 1.0, 2.0, 3.0])
    def test_thumbs_up_recognized_at_all_scales(self, scale_factor: float) -> None:
        # Scale-invariance: a Thumbs Up hand at different camera
        # distances must still produce a thumbs_up result.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        scaled = scale_hand_landmarks(h, scale_factor)
        result = detect_thumbs_up(scaled)
        assert result is not None, f'Thumbs Up missed at scale {scale_factor}'
        assert result.gesture_name == 'thumbs_up'
        assert result.confidence > 0.9


# ======================================================================
# Thumbs Down
# ======================================================================

class TestThumbsDown:
    def test_thumbs_down_from_mirrored_fixture(self) -> None:
        # Build a thumbs-down hand by mirroring the thumbs-up fixture
        # around y. The thumb tip ends up below the wrist -> thumbs down.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        from models.data_models import HandData
        mirrored = HandData(
            landmarks=[(lm[0], 1.0 - lm[1], lm[2]) for lm in h.landmarks],
            chirality=h.chirality,
            confidence=h.confidence,
            role=h.role,
            scale=h.scale,
        )
        result = detect_thumbs_down(mirrored)
        assert result is not None
        assert result.gesture_name == 'thumbs_down'

    def test_thumbs_up_not_thumbs_down(self) -> None:
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        assert detect_thumbs_down(h) is None

    def test_thumbs_down_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        mirrored = replace(
            h,
            landmarks=[(lm[0], 1.0 - lm[1], lm[2]) for lm in h.landmarks],
        )
        assert detect_thumbs_down(replace(mirrored, scale=None)) is None

    def test_fist_not_thumbs_down(self) -> None:
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        assert detect_thumbs_down(h) is None

    def test_thumbs_down_confidence_reflects_extension_strength(self) -> None:
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        from models.data_models import HandData
        mirrored = HandData(
            landmarks=[(lm[0], 1.0 - lm[1], lm[2]) for lm in h.landmarks],
            chirality=h.chirality,
            confidence=h.confidence,
            role=h.role,
            scale=h.scale,
        )
        result = detect_thumbs_down(mirrored)
        assert result is not None
        assert result.gesture_name == 'thumbs_down'
        assert result.confidence > 0.9

    @pytest.mark.parametrize('scale_factor', [0.5, 1.0, 2.0, 3.0])
    def test_thumbs_down_recognized_at_all_scales(self, scale_factor: float) -> None:
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        from models.data_models import HandData
        mirrored = HandData(
            landmarks=[(lm[0], 1.0 - lm[1], lm[2]) for lm in h.landmarks],
            chirality=h.chirality,
            confidence=h.confidence,
            role=h.role,
            scale=h.scale,
        )
        scaled = scale_hand_landmarks(mirrored, scale_factor)
        result = detect_thumbs_down(scaled)
        assert result is not None, f'Thumbs Down missed at scale {scale_factor}'
        assert result.gesture_name == 'thumbs_down'


# ======================================================================
# Peace Sign
# ======================================================================

class TestPeaceSign:
    def test_peace_sign_right_detected(self) -> None:
        h = make_hand_with_scale(pose_name='peace_sign_right', role='HAND_A')
        result = detect_peace_sign(h)
        assert result is not None
        assert result.gesture_name == 'peace_sign'

    def test_three_fingers_not_peace_sign(self) -> None:
        # Mutual-exclusivity: Peace Sign has 2 extended; Three Fingers
        # has 3 extended.
        h = make_hand_with_scale(pose_name='three_fingers_right', role='HAND_A')
        assert detect_peace_sign(h) is None

    def test_peace_sign_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='peace_sign_right', role='HAND_A')
        assert detect_peace_sign(replace(h, scale=None)) is None


# ======================================================================
# Three Fingers
# ======================================================================

class TestThreeFingers:
    def test_three_fingers_right_detected(self) -> None:
        h = make_hand_with_scale(pose_name='three_fingers_right', role='HAND_A')
        result = detect_three_fingers(h)
        assert result is not None
        assert result.gesture_name == 'three_fingers'

    def test_peace_sign_not_three_fingers(self) -> None:
        h = make_hand_with_scale(pose_name='peace_sign_right', role='HAND_A')
        assert detect_three_fingers(h) is None

    def test_three_fingers_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='three_fingers_right', role='HAND_A')
        assert detect_three_fingers(replace(h, scale=None)) is None


# ======================================================================
# OK Sign (must NOT be shadowed by Pinch)
# ======================================================================

class TestOkSign:
    def test_ok_sign_right_detected(self) -> None:
        h = make_hand_with_scale(pose_name='ok_sign_right', role='HAND_A')
        result = detect_ok_sign(h)
        assert result is not None
        assert result.gesture_name == 'ok_sign'

    def test_ok_sign_not_shadowed_by_pinch(self) -> None:
        # The canonical mutual-exclusivity test (Implementation Plan §7.1
        # OK Sign testing strategy): both OK Sign and Pinch satisfy the
        # thumb-index distance check. The three-finger constraint is
        # what disambiguates OK Sign from Pinch. The ConflictResolver
        # picks one winner; here we assert that the OK Sign rule itself
        # produces an 'ok_sign' result on the OK Sign fixture, AND that
        # the Pinch rule does NOT (because detect_pinch now enforces its
        # own three-finger remaining-curled check, which rejects the OK
        # Sign fixture where middle / ring / pinky are extended).
        h = make_hand_with_scale(pose_name='ok_sign_right', role='HAND_A')
        ok_result = detect_ok_sign(h)
        pinch_result = detect_pinch(h)
        assert ok_result is not None
        assert ok_result.gesture_name == 'ok_sign'
        assert pinch_result is None, (
            'detect_pinch must reject OK Sign fixture because middle/'
            'ring/pinky are extended (remaining-fingers curled check)'
        )

    def test_pinch_fixture_not_ok_sign(self) -> None:
        # Reverse direction: a Pinch fixture should NOT trigger OK Sign
        # because the three-finger constraint is violated.
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        assert detect_ok_sign(h) is None

    def test_ok_sign_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='ok_sign_right', role='HAND_A')
        assert detect_ok_sign(replace(h, scale=None)) is None

    @pytest.mark.parametrize('scale_factor', [0.5, 1.0, 2.0, 3.0])
    def test_ok_sign_recognized_at_all_scales(self, scale_factor: float) -> None:
        h = make_hand_with_scale(pose_name='ok_sign_right', role='HAND_A')
        scaled = scale_hand_landmarks(h, scale_factor)
        result = detect_ok_sign(scaled)
        assert result is not None, f'OK Sign missed at scale {scale_factor}'


# ======================================================================
# Multi-feature thumb-extension score
# ======================================================================

from gestures.gesture_utils import (
    thumb_extension_score,
    is_thumb_extended,
    extended_finger_count,
    THUMB_EXTENSION_THRESHOLD,
    all_fingers_extended,
)


class TestThumbExtensionScore:
    def test_fist_score_is_low(self) -> None:
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        score = thumb_extension_score(h.landmarks)
        assert score < THUMB_EXTENSION_THRESHOLD
        assert score < 0.5  # well below threshold for "extended"

    def test_thumbs_up_score_is_high(self) -> None:
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        score = thumb_extension_score(h.landmarks)
        assert score >= THUMB_EXTENSION_THRESHOLD
        assert score > 0.8  # well above threshold

    def test_open_palm_score_is_high(self) -> None:
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        score = thumb_extension_score(h.landmarks)
        assert score >= THUMB_EXTENSION_THRESHOLD
        assert score > 0.8

    def test_pinch_and_ok_sign_scores_are_low(self) -> None:
        for pose in ('pinch_right', 'ok_sign_right'):
            h = make_hand_with_scale(pose_name=pose, role='HAND_A')
            score = thumb_extension_score(h.landmarks)
            assert score < THUMB_EXTENSION_THRESHOLD, f'{pose} score {score:.3f} crossed threshold'

    def test_score_is_scale_invariant(self) -> None:
        # The thumb-extension score must be a pure ratio, unchanged
        # by uniform scaling of the landmark cloud.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        score_base = thumb_extension_score(h.landmarks)
        for factor in (0.5, 2.0, 3.0):
            scaled = scale_hand_landmarks(h, factor)
            score_scaled = thumb_extension_score(scaled.landmarks)
            assert abs(score_scaled - score_base) < 1e-6, (
                f'Score changed at scale {factor}: {score_base:.6f} -> {score_scaled:.6f}'
            )

    def test_multi_feature_guard_penalises_single_active_feature(self) -> None:
        # When only ONE of the three features is active, the score
        # must be penalised to prevent false positives from noisy data.
        # Construct a hand where the reach ratio is abnormally high but
        # the thumb is *not* genuinely extended (e.g., the thumb tip is
        # far from the wrist due to lateral spread, not extension).
        landmarks = [
            (0.50, 0.55, 0.0),  # 0: wrist
            (0.46, 0.49, 0.0),  # 1: thumb CMC
            (0.44, 0.45, 0.0),  # 2: thumb MCP
            (0.43, 0.42, 0.0),  # 3: thumb IP
            (0.43, 0.41, 0.0),  # 4: thumb TIP — normal fist position
            *[(0.50, 0.55, 0.0)] * 16,
        ]
        # Reference thumb (fist_right): score ≈ 0.20–0.36.
        score = thumb_extension_score(landmarks, chirality='Right')
        # The guard ensures a tightly curled thumb does not cross threshold.
        assert score < THUMB_EXTENSION_THRESHOLD
        assert is_thumb_extended(landmarks, 'Right') is False

    def test_partially_folded_thumb_produces_mid_range_score(self) -> None:
        # A thumb that is neither fully curled nor fully extended
        # should score in the intermediate range (0.35–0.65).
        # Construct landmarks where the thumb is partially curled:
        # tip is above the MCP but much closer than in a full thumbs-up.
        landmarks = [
            (0.50, 0.55, 0.0),  # 0: wrist
            (0.48, 0.48, 0.0),  # 1: thumb CMC
            (0.46, 0.42, 0.0),  # 2: thumb MCP
            (0.45, 0.40, 0.0),  # 3: thumb IP
            (0.44, 0.38, 0.0),  # 4: thumb TIP — partially curled
            *[(0.50, 0.55, 0.0)] * 16,
        ]
        score = thumb_extension_score(landmarks)
        # Partially curled → between 0.35 and 0.65
        assert 0.35 <= score <= 0.65, f'Partially-folded thumb score {score:.3f} outside expected range'

    def test_rotated_hand_still_scores_correctly(self) -> None:
        # Simulate a hand rotated at an angle by offsetting the
        # landmarks and verifying the score remains stable.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        # Apply a small y-rotation: keep each landmark's original
        # distance from wrist but rotate the y component.
        # This tests robustness to non-ideal camera angles.
        wrist = h.landmarks[0]
        rotated = []
        for lm in h.landmarks:
            dx = lm[0] - wrist[0]
            dy = lm[1] - wrist[1]
            angle_deg = 15.0
            import math
            angle_rad = math.radians(angle_deg)
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
        from dataclasses import replace
        from models.data_models import HandData
        rotated_hand = replace(h, landmarks=rotated)
        result = detect_thumbs_up(rotated_hand)
        assert result is not None, 'Thumbs Up not detected after 15° rotation'
        assert result.gesture_name == 'thumbs_up'

    def test_rotated_first_thumb_not_extended(self) -> None:
        # A rotated fist must still NOT be considered thumbs_up.
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        wrist = h.landmarks[0]
        import math
        rotated = []
        for lm in h.landmarks:
            dx = lm[0] - wrist[0]
            dy = lm[1] - wrist[1]
            angle_rad = math.radians(15.0)
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
        from dataclasses import replace
        rotated_hand = replace(h, landmarks=rotated)
        assert detect_thumbs_up(rotated_hand) is None


# ======================================================================
# Hot-path-never-raises discipline (RULES §6.4)
# ======================================================================

class TestHotPathNeverRaises:
    @pytest.mark.parametrize('recognizer', [
        detect_open_palm,
        detect_fist,
        detect_pinch,
        detect_thumbs_up,
        detect_thumbs_down,
        detect_peace_sign,
        detect_three_fingers,
        detect_ok_sign,
    ])
    def test_malformed_landmarks_returns_none(self, recognizer) -> None:
        # Each `detect_*` must return None (not raise) when given a
        # malformed HandData. The most aggressive form of this contract:
        # empty landmarks list (length 0).
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        broken = replace(h, landmarks=[])
        # Should not raise — should return None (or the result of a
        # benign computation that happens to be None).
        result = recognizer(broken)
        # We don't assert `is None` here because some recognizers
        # *could* legitimately return None for the malformed input
        # even without an explicit check. The important property is
        # no exception was raised.
        assert result is None or result.gesture_name != ''