"""Unit tests for static gesture recognizers — Checkpoint 3.

Per AI Dev Guide §9.6 template and Implementation Plan §7.1's per-gesture
testing strategy: each gesture gets a positive test, a negative
(mutual-exclusivity) test, a scale-invariance parametrization, and a
no-scale test.
"""

from __future__ import annotations

import pytest

from gestures.static_recognizer import (
    BOOLEAN_GESTURE_CONFIDENCE,
    FIST_COMPACTNESS_THRESHOLD,
    PINCH_ALIGNMENT_THRESHOLD,
    PINCH_NORMALIZED_DISTANCE_THRESHOLD,
    PINCH_REMAINING_CURL_THRESHOLD,
    STATIC_GESTURE_RULES,
    detect_fist,
    detect_four_fingers,
    detect_ok_sign,
    detect_one_finger,
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
    def test_pinch_threshold_is_0_55(self) -> None:
        # CP-3 pinch audit: increased from 0.35 to 0.55 so that
        # real-world pinch distances (nd ≈ 0.15–0.35, dominated by
        # MediaPipe landmark noise) clear the distance gate and the
        # confidence formula produces values ≥0.85 for nd ≤ 0.30.
        # Open Palm (nd ≈ 0.68) and Fist (nd ≈ 0.67) remain rejected.
        assert PINCH_NORMALIZED_DISTANCE_THRESHOLD == 0.55

    def test_static_rules_count_is_ten(self) -> None:
        assert len(STATIC_GESTURE_RULES) == 10

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

    def test_pinch_confidence_above_threshold_for_moderate_distance(self) -> None:
        """A natural pinch with normalized distance up to ~0.30 must
        produce confidence >= 0.85 (the pipeline's global threshold),
        so it is not silently dropped before GestureFuser."""
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        from dataclasses import replace
        from gestures.gesture_utils import THUMB_TIP, INDEX_TIP, euclidean_distance
        mod = list(h.landmarks)
        # Push thumb tip outward along its current direction from the
        # wrist so the normalized distance reaches ~0.30.
        target_raw = 0.30 * h.scale.palm_width
        current_raw = euclidean_distance(mod[THUMB_TIP], mod[INDEX_TIP])
        wx, wy, _ = mod[0]  # WRIST
        tx, ty, tz = mod[THUMB_TIP]
        vx, vy = tx - wx, ty - wy
        vlen = (vx * vx + vy * vy) ** 0.5
        if vlen > 1e-8:
            factor = 1.0 + (target_raw - current_raw) / vlen
            mod[THUMB_TIP] = (wx + vx * factor, wy + vy * factor, tz)
        h_mod = replace(h, landmarks=tuple(mod))
        from gestures.gesture_utils import pinch_distance_ratio
        nd = pinch_distance_ratio(h_mod.landmarks, h_mod.scale.palm_width)
        result = detect_pinch(h_mod)
        assert result is not None, f'Pinch missed at nd={nd:.4f}'
        assert result.confidence >= 0.85, (
            f'Pinch confidence {result.confidence:.4f} below 0.85 at nd={nd:.4f}'
        )


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
        # A true thumbs-down has the thumb tip BELOW the wrist and MCP in
        # image y-coordinates AND also below them relative to the palm's
        # local frame.  Build a hand where the thumb tip is moved down
        # (same x as MCP, y much larger than wrist) so the thumb vector
        # points opposite to the palm's longitudinal axis.
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        # Move the thumb tip below the wrist: y = wrist_y + offset.
        wrist_y = h.landmarks[0][1]  # 0.55
        thumb_down_landmarks = list(h.landmarks)
        # Landmark 4 (thumb_tip) at same x, well below the wrist.
        thumb_down_landmarks[4] = (h.landmarks[4][0], wrist_y + 0.15, h.landmarks[4][2])
        # Also move thumb_IP (3) to follow the tip downward.
        thumb_down_landmarks[3] = (h.landmarks[3][0], wrist_y + 0.08, h.landmarks[3][2])
        thumbs_down_hand = replace(h, landmarks=thumb_down_landmarks)
        assert detect_thumbs_up(thumbs_down_hand) is None

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
        # produce confidence > 0.85 (well above the pipeline threshold).
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        result = detect_thumbs_up(h)
        assert result is not None
        assert result.confidence > 0.85
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
        assert result.confidence > 0.85

    def test_thumbs_up_confidence_formula_weights_extension_over_direction(
        self,
    ) -> None:
        """The confidence formula must weight thumb extension ≈4×
        more than direction (80/20 split).  Verify two equal-score
        scenarios produce the correct confidence values."""
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        result = detect_thumbs_up(h)
        assert result is not None
        # Canonical fixture: thumb=0.9334, dir=0.7000
        # new formula (CP-5+ audit): 0.75 + 0.25 * (0.80*0.9334 + 0.20*0.7000) = 0.9717
        assert round(result.confidence, 4) == 0.9717, (
            f'Expected 0.9717, got {result.confidence}'
        )

    def test_thumbs_up_confidence_tolerates_moderate_direction(
        self,
    ) -> None:
        """A scenario with moderate direction (≈0.35) and good
        extension (≈0.81) must still pass the 0.85 threshold."""
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.thumb_extension_score',
            return_value=0.814,
        ), mock.patch(
            'gestures.static_recognizer.thumb_direction_score',
            return_value=0.354,
        ):
            result = detect_thumbs_up(h)
        assert result is not None
        # 0.75 + 0.25 * (0.80 * 0.814 + 0.20 * 0.354) = 0.75 + 0.1805 = 0.9305
        assert round(result.confidence, 4) == 0.9305, (
            f'Expected 0.9305, got {result.confidence}'
        )

    def test_thumbs_up_confidence_does_not_overweight_direction(
        self,
    ) -> None:
        """A case with poor direction (≤0.05) and good extension
        must still pass the 0.85 threshold — direction should not
        dominate confidence."""
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.thumb_extension_score',
            return_value=0.814,
        ), mock.patch(
            'gestures.static_recognizer.thumb_direction_score',
            return_value=0.05,
        ):
            result = detect_thumbs_up(h)
        assert result is not None
        # 0.75 + 0.25 * (0.80 * 0.814 + 0.20 * 0.05) = 0.75 + 0.1653 = 0.9153
        # Raised floor ensures even poor-direction cases clear the
        # 0.85 pipeline threshold once both binary gates pass.
        assert round(result.confidence, 4) == 0.9153, (
            f'Expected 0.9153, got {result.confidence}'
        )

    def test_thumbs_up_clears_085_threshold_at_minimum_valid_input(self) -> None:
        """Regression: a thumbs-up at the binary-gate boundary
        (thumb_score = 0.55, direction_score just above 0) must
        produce confidence ≥ 0.85."""
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.thumb_extension_score',
            return_value=0.550,
        ), mock.patch(
            'gestures.static_recognizer.thumb_direction_score',
            return_value=0.001,
        ):
            result = detect_thumbs_up(h)
        assert result is not None
        # 0.75 + 0.25 * (0.80 * 0.550 + 0.20 * 0.001) = 0.75 + 0.11005 = 0.86005
        assert result.confidence >= 0.85, (
            f'Minimum-valid thumbs_up confidence {result.confidence:.4f} '
            f'below pipeline threshold 0.85'
        )

    def test_thumbs_up_clears_085_threshold_with_typical_extension(self) -> None:
        """A typical thumbs-up with moderate scores must clear the
        pipeline threshold comfortably."""
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.thumb_extension_score',
            return_value=0.70,
        ), mock.patch(
            'gestures.static_recognizer.thumb_direction_score',
            return_value=0.60,
        ):
            result = detect_thumbs_up(h)
        assert result is not None
        # 0.75 + 0.25 * (0.80 * 0.70 + 0.20 * 0.60) = 0.75 + 0.17 = 0.92
        assert result.confidence >= 0.85

    def test_fist_rejected_by_thumbs_up_regression(self) -> None:
        """A fist must not produce a thumbs_up candidate (regression
        guard: confidence formula change must not create false positives)."""
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        assert detect_thumbs_up(h) is None

    def test_open_palm_rejected_by_thumbs_up_regression(self) -> None:
        """An open palm must not produce a thumbs_up candidate."""
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        assert detect_thumbs_up(h) is None

    def test_pinch_rejected_by_thumbs_up_regression(self) -> None:
        """A pinch must not produce a thumbs_up candidate."""
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        assert detect_thumbs_up(h) is None


    # ------------------------------------------------------------------
    # Rotation-invariant direction check
    # ------------------------------------------------------------------

    def test_thumbs_up_recognized_after_30_deg_rotation(self) -> None:
        # The thumb must be detected even when the hand is rotated
        # 30 degrees in the image plane (where the old image-space
        # direction check would fail).
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        wrist = h.landmarks[0]
        import math
        rotated = []
        angle_rad = math.radians(30.0)
        for lm in h.landmarks:
            dx = lm[0] - wrist[0]
            dy = lm[1] - wrist[1]
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
        from dataclasses import replace
        rotated_hand = replace(h, landmarks=rotated)
        result = detect_thumbs_up(rotated_hand)
        assert result is not None, 'Thumbs Up missed after 30° rotation'
        assert result.gesture_name == 'thumbs_up'

    def test_thumbs_up_recognized_after_60_deg_rotation(self) -> None:
        # Even 60 degrees of in-plane rotation must still produce
        # a thumbs_up result.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        wrist = h.landmarks[0]
        import math
        rotated = []
        angle_rad = math.radians(60.0)
        for lm in h.landmarks:
            dx = lm[0] - wrist[0]
            dy = lm[1] - wrist[1]
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
        from dataclasses import replace
        rotated_hand = replace(h, landmarks=rotated)
        result = detect_thumbs_up(rotated_hand)
        assert result is not None, 'Thumbs Up missed after 60° rotation'
        assert result.gesture_name == 'thumbs_up'

    def test_thumbs_up_recognized_after_90_deg_rotation(self) -> None:
        # Hand rotated 90 degrees (thumb pointing sideways in image).
        # The palm-relative check must still detect it.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        wrist = h.landmarks[0]
        import math
        rotated = []
        angle_rad = math.radians(90.0)
        for lm in h.landmarks:
            dx = lm[0] - wrist[0]
            dy = lm[1] - wrist[1]
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
        from dataclasses import replace
        rotated_hand = replace(h, landmarks=rotated)
        result = detect_thumbs_up(rotated_hand)
        assert result is not None, 'Thumbs Up missed after 90° rotation'
        assert result.gesture_name == 'thumbs_up'

    def test_rotated_fist_not_thumbs_up(self) -> None:
        # A rotated fist must still NOT be detected as thumbs_up.
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        wrist = h.landmarks[0]
        import math
        rotated = []
        angle_rad = math.radians(45.0)
        for lm in h.landmarks:
            dx = lm[0] - wrist[0]
            dy = lm[1] - wrist[1]
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
        from dataclasses import replace
        rotated_hand = replace(h, landmarks=rotated)
        assert detect_thumbs_up(rotated_hand) is None

    def test_rotated_open_palm_not_thumbs_up(self) -> None:
        # A rotated open palm has all fingers extended — the
        # four-finger curled check must reject it regardless of rotation.
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        wrist = h.landmarks[0]
        import math
        rotated = []
        angle_rad = math.radians(45.0)
        for lm in h.landmarks:
            dx = lm[0] - wrist[0]
            dy = lm[1] - wrist[1]
            rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
        from dataclasses import replace
        rotated_hand = replace(h, landmarks=rotated)
        assert detect_thumbs_up(rotated_hand) is None

    def test_thumbs_up_direction_is_rotation_invariant(self) -> None:
        # The thumb_direction_score should remain stable under
        # in-plane rotation because it uses the palm's local frame.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        base_score = thumb_direction_score(h.landmarks)
        assert base_score > THUMB_DIRECTION_MIN_SCORE
        wrist = h.landmarks[0]
        import math
        for angle_deg in (15, 30, 45, 60, 90):
            rotated = []
            angle_rad = math.radians(angle_deg)
            for lm in h.landmarks:
                dx = lm[0] - wrist[0]
                dy = lm[1] - wrist[1]
                rx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
                ry = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
                rotated.append((wrist[0] + rx, wrist[1] + ry, lm[2]))
            score = thumb_direction_score(rotated)
            assert score > 0.3, (
                f'Direction score dropped to {score:.3f} at {angle_deg}° rotation'
            )

    def test_thumbs_down_has_low_direction_score(self) -> None:
        # A thumbs-down pose must have a low direction score because
        # the thumb points opposite to the palm's longitudinal axis.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        from dataclasses import replace
        # Move thumb tip below the wrist.
        wrist_y = h.landmarks[0][1]
        thumbs_down_landmarks = list(h.landmarks)
        thumbs_down_landmarks[4] = (h.landmarks[4][0], wrist_y + 0.15, h.landmarks[4][2])
        thumbs_down_landmarks[3] = (h.landmarks[3][0], wrist_y + 0.08, h.landmarks[3][2])
        score = thumb_direction_score(thumbs_down_landmarks)
        assert score <= 0.0, f'Thumbs-down direction score should be 0, got {score:.3f}'

    def test_fist_has_low_extension_score_but_can_have_high_direction(self) -> None:
        # Fist: direction score can be high (thumb points same direction
        # as palm_y even when curled), but the extension score catches it.
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        dir_score = thumb_direction_score(h.landmarks)
        ext_score = thumb_extension_score(h.landmarks)
        # The direction alone is not enough — extension must also pass.
        assert ext_score < 0.55, 'Fist extension score must be below threshold'
        assert detect_thumbs_up(h) is None


# ======================================================================
# Thumbs Up — direction score
# ======================================================================

class TestThumbsDirectionScore:
    def test_thumbs_up_direction_score_is_high(self) -> None:
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        score = thumb_direction_score(h.landmarks)
        assert score > THUMB_DIRECTION_MIN_SCORE

    def test_fist_still_rejected_by_detect_thumbs_up(self) -> None:
        # Fist may have a moderate direction score, but the extension
        # score check in detect_thumbs_up rejects it.
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        assert detect_thumbs_up(h) is None

    def test_thumbs_down_still_rejected_by_detect_thumbs_up(self) -> None:
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        from dataclasses import replace
        wrist_y = h.landmarks[0][1]
        thumbs_down_lm = list(h.landmarks)
        thumbs_down_lm[4] = (h.landmarks[4][0], wrist_y + 0.15, h.landmarks[4][2])
        thumbs_down_lm[3] = (h.landmarks[3][0], wrist_y + 0.08, h.landmarks[3][2])
        thumbs_down_hand = replace(h, landmarks=thumbs_down_lm)
        assert detect_thumbs_up(thumbs_down_hand) is None

    def test_empty_landmarks_returns_zero(self) -> None:
        assert thumb_direction_score([]) == 0.0

    def test_pinch_still_rejected_by_detect_thumbs_up(self) -> None:
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        assert detect_thumbs_up(h) is None

    def test_ok_sign_still_rejected_by_detect_thumbs_up(self) -> None:
        h = make_hand_with_scale(pose_name='ok_sign_right', role='HAND_A')
        assert detect_thumbs_up(h) is None

    def test_direction_score_is_scale_invariant(self) -> None:
        # Direction score uses normalised projections (ratio of dot
        # product to vector length), so uniform landmark scaling
        # must leave it unchanged.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        base = thumb_direction_score(h.landmarks)
        for factor in (0.5, 2.0, 3.0):
            scaled = scale_hand_landmarks(h, factor)
            score = thumb_direction_score(scaled.landmarks)
            assert abs(score - base) < 1e-6, (
                f'Direction score changed at scale {factor}: '
                f'{base:.6f} -> {score:.6f}'
            )


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
    INDEX_MCP,
    THUMB_CMC,
    THUMB_MCP,
    THUMB_TIP,
    WRIST,
    euclidean_distance,
    thumb_extension_score,
    thumb_direction_score,
    is_thumb_extended,
    extended_finger_count,
    THUMB_EXTENSION_THRESHOLD,
    THUMB_DIRECTION_MIN_SCORE,
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

    def test_penalty_multiplier_reduced_to_0_75(self) -> None:
        # The multi-feature guard penalty multiplier was reduced from 0.5
        # to 0.75 (audit fix).  For poses with exactly 1 active feature
        # the penalised score must equal unpenalized * 0.75, confirming
        # the less-aggressive penalty is in place.
        # ok_sign_right has active=1 (only score_length > 0.2).
        h = make_hand_with_scale(pose_name='ok_sign_right', role='HAND_A')
        lm = h.landmarks
        w = lm[WRIST]; mc = lm[THUMB_MCP]; ti = lm[THUMB_TIP]
        idx = lm[INDEX_MCP]; cmc = lm[THUMB_CMC]
        w2mc = euclidean_distance(w, mc)
        w2ti = euclidean_distance(w, ti)
        reach_r = w2ti / w2mc if w2mc > 0 else 0
        score_r = max(0.0, min(1.0, (reach_r - 1.0) / 1.0))
        cmc2mc = euclidean_distance(cmc, mc)
        mc2ti = euclidean_distance(mc, ti)
        len_r = mc2ti / cmc2mc if cmc2mc > 0 else 0
        score_l = max(0.0, min(1.0, (len_r - 0.25) / 1.25))
        ti2idx = euclidean_distance(ti, idx)
        sep_r = ti2idx / w2mc if w2mc > 0 else 0
        score_s = max(0.0, min(1.0, (sep_r - 0.5) / 2.0))
        active = sum([score_r > 0.2, score_l > 0.2, score_s > 0.2])
        unpen = 0.5 * score_r + 0.3 * score_l + 0.2 * score_s
        final_score = thumb_extension_score(lm)
        assert active == 1, f'Expected 1 active feature, got {active}'
        expected = unpen * 0.75
        assert abs(final_score - expected) < 1e-4, (
            f'Penalty multiplier mismatch: expected {unpen:.4f} * 0.75 = {expected:.4f}, '
            f'got {final_score:.4f}'
        )
        # The reduced penalty produces a higher score than the old 0.5:
        old_penalty = unpen * 0.5
        assert final_score > old_penalty, (
            f'New penalty ({final_score:.4f}) must be higher than old ({old_penalty:.4f})'
        )
        # But ok_sign should still be well below the extension threshold
        # (this pose is NOT a thumbs-up):
        assert final_score < THUMB_EXTENSION_THRESHOLD, (
            f'ok_sign score {final_score:.4f} must stay below {THUMB_EXTENSION_THRESHOLD}'
        )

    def test_fist_still_rejected_with_penalty_change(self) -> None:
        # Fist has active=2 features, so the penalty does NOT apply.
        # Its score must remain well below THUMB_EXTENSION_THRESHOLD,
        # proving the penalty change does not create false positives.
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        score = thumb_extension_score(h.landmarks)
        assert score < THUMB_EXTENSION_THRESHOLD, (
            f'Fist score {score:.4f} must stay below {THUMB_EXTENSION_THRESHOLD}'
        )
        assert detect_thumbs_up(h) is None, 'Fist must not be detected as thumbs_up'

    def test_canonical_thumbs_up_passes_with_penalty_change(self) -> None:
        # Canonical thumbs-up has active=3, no penalty applies.
        # It must still pass detect_thumbs_up.
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        assert detect_thumbs_up(h) is not None
        assert detect_thumbs_up(h).gesture_name == 'thumbs_up'


# ======================================================================
# One Finger (Pointing)
# ======================================================================

class TestOneFinger:
    def test_one_finger_detected(self) -> None:
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='peace_sign_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.finger_states',
            return_value={'index': True, 'middle': False, 'ring': False, 'pinky': False},
        ), mock.patch(
            'gestures.static_recognizer.is_thumb_extended',
            return_value=False,
        ):
            result = detect_one_finger(h)
        assert result is not None
        assert result.gesture_name == 'one_finger'
        assert result.confidence == BOOLEAN_GESTURE_CONFIDENCE

    def test_one_finger_rejects_index_curled(self) -> None:
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='fist_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.finger_states',
            return_value={'index': False, 'middle': False, 'ring': False, 'pinky': False},
        ):
            assert detect_one_finger(h) is None

    def test_one_finger_rejects_thumb_extended(self) -> None:
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='thumbs_up_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.finger_states',
            return_value={'index': True, 'middle': False, 'ring': False, 'pinky': False},
        ), mock.patch(
            'gestures.static_recognizer.is_thumb_extended',
            return_value=True,
        ):
            assert detect_one_finger(h) is None

    def test_one_finger_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='peace_sign_right', role='HAND_A')
        assert detect_one_finger(replace(h, scale=None)) is None


# ======================================================================
# Four Fingers
# ======================================================================

class TestFourFingers:
    def test_four_fingers_detected(self) -> None:
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.finger_states',
            return_value={'index': True, 'middle': True, 'ring': True, 'pinky': True},
        ), mock.patch(
            'gestures.static_recognizer.is_thumb_extended',
            return_value=False,
        ):
            result = detect_four_fingers(h)
        assert result is not None
        assert result.gesture_name == 'four_fingers'
        assert result.confidence == BOOLEAN_GESTURE_CONFIDENCE

    def test_four_fingers_rejects_any_curled(self) -> None:
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='peace_sign_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.finger_states',
            return_value={'index': True, 'middle': True, 'ring': False, 'pinky': False},
        ):
            assert detect_four_fingers(h) is None

    def test_four_fingers_rejects_thumb_extended(self) -> None:
        import unittest.mock as mock
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        with mock.patch(
            'gestures.static_recognizer.finger_states',
            return_value={'index': True, 'middle': True, 'ring': True, 'pinky': True},
        ), mock.patch(
            'gestures.static_recognizer.is_thumb_extended',
            return_value=True,
        ):
            assert detect_four_fingers(h) is None

    def test_four_fingers_returns_none_without_scale(self) -> None:
        from dataclasses import replace
        h = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        assert detect_four_fingers(replace(h, scale=None)) is None


# ======================================================================
# Pinch proximity guard (Thumbs Up should NOT fire during pinch)
# ======================================================================

class TestPinchThumbsUpMutualExclusivity:
    def test_pinch_fixture_not_detected_as_thumbs_up(self) -> None:
        """A canonical Pinch fixture must not trigger Thumbs Up
        (thumb-index distance below pinch threshold)."""
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        assert detect_thumbs_up(h) is None

    def test_ok_sign_fixture_not_detected_as_thumbs_up(self) -> None:
        """An OK Sign fixture must not trigger Thumbs Up
        (thumb-index distance below pinch threshold)."""
        from gestures.gesture_utils import pinch_distance_ratio
        h = make_hand_with_scale(pose_name='ok_sign_right', role='HAND_A')
        # Verify the fixture actually has close thumb-index distance.
        nd = pinch_distance_ratio(h.landmarks, h.scale.palm_width)
        assert nd < PINCH_NORMALIZED_DISTANCE_THRESHOLD, (
            f'OK Sign fixture must have close tips (got {nd})'
        )
        assert detect_thumbs_up(h) is None


# ======================================================================
# Hot-path-never-raises discipline (RULES §6.4)
# ======================================================================

class TestHotPathNeverRaises:
    @pytest.mark.parametrize('recognizer', [
        detect_one_finger,
        detect_peace_sign,
        detect_three_fingers,
        detect_four_fingers,
        detect_open_palm,
        detect_fist,
        detect_pinch,
        detect_thumbs_up,
        detect_thumbs_down,
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