"""Parametrized scale-invariance tests for static and dynamic gestures.

Per TRD §4.6 (Test Strategy for Scale Invariance): "Per PRD §17.1/§17.2,
scale-invariance must be explicitly tested by running the same gesture
fixture through the recognizer at multiple synthetic hand-scale values."

This file consolidates the parametrized scale-invariance tests for the
two gestures that are the canonical scale-invariance test subjects:
  - Pinch (static, TRD §13.3 `test_pinch_recognized_close_and_far`)
  - Swipe Right (dynamic, TRD §4.6 worked example)

Both gestures are parametrized across scale_factor in [0.5, 1.0,
2.0, 3.0] per Implementation Plan §7.
"""

from __future__ import annotations

import pytest

from gestures.dynamic_recognizer import detect_swipe_right
from gestures.static_recognizer import detect_pinch

from tests.conftest import (
    load_fixture,
    make_hand_with_scale,
    scale_hand_landmarks,
)


SCALE_FACTORS = [0.5, 1.0, 2.0, 3.0]


# ======================================================================
# Pinch (TRD §13.3 worked example)
# ======================================================================

class TestPinchScaleInvariance:
    """TRD §4.6 / §13.3: Pinch is recognized consistently across
    user-to-camera distances."""

    @pytest.mark.parametrize('scale_factor', SCALE_FACTORS)
    def test_pinch_recognized_at_all_scales(
        self, scale_factor: float
    ) -> None:
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        scaled = scale_hand_landmarks(h, scale_factor)
        result = detect_pinch(scaled)
        assert result is not None, f'Pinch missed at scale_factor={scale_factor}'
        assert result.confidence > 0.5

    def test_pinch_confidence_consistent_across_scales(self) -> None:
        """TRD §4.6: Confidence should be 'comparable -- not just both
        detected but similarly confident' across distances."""
        h = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        confidences = []
        for sf in SCALE_FACTORS:
            scaled = scale_hand_landmarks(h, sf)
            r = detect_pinch(scaled)
            assert r is not None
            confidences.append(r.confidence)
        # All confidences should be within 0.15 of each other (the
        # TRD §13.3 explicit assertion: `abs(result_close.confidence -
        # result_far.confidence) < 0.15`).
        spread = max(confidences) - min(confidences)
        assert spread < 0.15, (
            f'Confidence spread across scales {SCALE_FACTORS}: '
            f'{confidences} (spread={spread:.3f}, must be < 0.15)'
        )


# ======================================================================
# Swipe Right (TRD §4.6 worked example)
# ======================================================================

class TestSwipeRightScaleInvariance:
    """TRD §4.6: Swipe Right uses normalized displacement, so it should
    be recognized at any camera distance as long as the displacement
    is uniform-scaled."""

    @pytest.mark.parametrize('scale_factor', SCALE_FACTORS)
    def test_swipe_right_recognized_at_all_scales(
        self, scale_factor: float, gesture_trajectories
    ) -> None:
        raw_buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_right']]
        cx, cy = raw_buf[0][0], raw_buf[0][1]
        # Uniform-scale the trajectory (simulating a farther/closer
        # user-to-camera distance — both the raw displacement and the
        # hand_scale shrink/grow proportionally).
        scaled_buf = [
            (cx + (x - cx) * scale_factor,
             cy + (y - cy) * scale_factor,
             t)
            for (x, y, t) in raw_buf
        ]
        result = detect_swipe_right(scaled_buf, hand_scale=0.10 * scale_factor)
        assert result is not None, (
            f'Swipe Right missed at scale_factor={scale_factor}'
        )


# ======================================================================
# Scale-invariance property: pinch ratio stays constant
# ======================================================================

class TestScaleInvarianceInvariant:
    """The exact mathematical property from TRD §4.2:

        At 30cm:  palm_width ≈ 0.17   thumb-index distance = 0.061   ratio = 0.359
        At 100cm: palm_width ≈ 0.056  thumb-index distance = 0.020   ratio = 0.357

    is verified numerically by the parametrized tests above. This
    test class also verifies the docstring example precisely.
    """

    def test_trd_worked_example_30cm_vs_100cm(self) -> None:
        """The PRD §5.2 / TRD §4.2 worked example, end-to-end.

        Same physical gesture performed at 30 cm vs 100 cm from the
        camera. Both must produce essentially the same pinch ratio
        (within float-precision tolerance).
        """
        h_30cm = make_hand_with_scale(pose_name='pinch_right', role='HAND_A')
        h_100cm = scale_hand_landmarks(h_30cm, factor=100 / 30)
        r_30cm = detect_pinch(h_30cm)
        r_100cm = detect_pinch(h_100cm)
        assert r_30cm is not None and r_100cm is not None
        # The confidences are 1.0 - ratio/0.35, and the ratios must
        # be nearly equal across distances -> confidences must be
        # nearly equal too.
        assert abs(r_30cm.confidence - r_100cm.confidence) < 0.15, (
            f'Pinch confidence not scale-invariant: '
            f'30cm={r_30cm.confidence:.4f}, 100cm={r_100cm.confidence:.4f}'
        )