"""Unit tests for dynamic gesture recognizers — Checkpoint 3.

Per AI Dev Guide §9.6 + Implementation Plan §7.2: each dynamic gesture
gets a positive test, a too-slow rejection test, a too-diagonal
rejection test, and a scale-invariance parametrization where applicable.
"""

from __future__ import annotations

import pytest

from gestures.dynamic_recognizer import (
    DYNAMIC_GESTURE_RULES,
    SWIPE_HORIZONTAL_DX_THRESHOLD_HAND_SCALES,
    SWIPE_VERTICAL_DY_THRESHOLD_HAND_SCALES,
    WAVE_MIN_REVERSALS,
    WAVE_MIN_TOTAL_AMPLITUDE_HAND_SCALES,
    detect_circular_motion,
    detect_swipe_down,
    detect_swipe_left,
    detect_swipe_right,
    detect_swipe_up,
    detect_wave,
    normalized_displacement,
)
from tests.conftest import load_fixture


# ======================================================================
# Constants
# ======================================================================

class TestConstants:
    def test_dynamic_rules_count_is_six(self) -> None:
        assert len(DYNAMIC_GESTURE_RULES) == 6

    def test_horizontal_swipe_threshold_pinned(self) -> None:
        # TRD §4.4 reference: `dx_threshold=2.5` hand-scales.
        assert SWIPE_HORIZONTAL_DX_THRESHOLD_HAND_SCALES == 2.5

    def test_vertical_swipe_threshold_pinned(self) -> None:
        assert SWIPE_VERTICAL_DY_THRESHOLD_HAND_SCALES == 2.5

    def test_wave_min_reversals_pinned(self) -> None:
        # PRD §4.4 Wave rule: "≥2 direction reversals".
        assert WAVE_MIN_REVERSALS == 2

    def test_wave_min_amplitude_pinned(self) -> None:
        # ≥1.0 hand-scales peak-to-peak x-amplitude required to
        # distinguish deliberate Wave from camera-noise jitter.
        assert WAVE_MIN_TOTAL_AMPLITUDE_HAND_SCALES == 1.0


# ======================================================================
# Swipe Right
# ======================================================================

class TestSwipeRight:
    def test_swipe_right_detected(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_right']]
        result = detect_swipe_right(buf, hand_scale=0.10)
        assert result is not None
        assert result.gesture_name == 'swipe_right'
        assert result.is_dynamic is True

    def test_swipe_left_not_swipe_right(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_left']]
        assert detect_swipe_right(buf, hand_scale=0.10) is None

    def test_swipe_right_rejected_if_too_slow(self, swipe_negative_cases) -> None:
        buf = [(s[0], s[1], s[2]) for s in swipe_negative_cases['too_slow_swipe_right']]
        assert detect_swipe_right(buf, hand_scale=0.10) is None

    def test_swipe_right_rejected_if_too_vertical(self, swipe_negative_cases) -> None:
        # The "too_vertical_swipe_right_attempt" trajectory is a fast
        # vertical motion, not a horizontal one.
        buf = [(s[0], s[1], s[2]) for s in swipe_negative_cases['too_vertical_swipe_right_attempt']]
        assert detect_swipe_right(buf, hand_scale=0.10) is None

    def test_swipe_right_rejected_with_insufficient_buffer(self) -> None:
        buf = [(0.30, 0.50, 0), (0.40, 0.50, 33)]
        assert detect_swipe_right(buf, hand_scale=0.10) is None

    def test_swipe_right_rejected_when_stationary(self, swipe_negative_cases) -> None:
        buf = [(s[0], s[1], s[2]) for s in swipe_negative_cases['stationary_hand']]
        assert detect_swipe_right(buf, hand_scale=0.10) is None

    @pytest.mark.parametrize('scale_factor', [0.5, 1.0, 2.0, 3.0])
    def test_swipe_right_recognized_at_all_scales(
        self, gesture_trajectories, scale_factor: float
    ) -> None:
        # Scale-invariance pattern from TRD §4.6: scale BOTH the
        # trajectory coordinates and the hand_scale by the same
        # factor. Normalized displacement is invariant under uniform
        # scaling (both numerator and denominator scale together).
        raw_buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_right']]
        cx, cy = raw_buf[0][0], raw_buf[0][1]
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
# Swipe Left (mirror of Swipe Right)
# ======================================================================

class TestSwipeLeft:
    def test_swipe_left_detected(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_left']]
        result = detect_swipe_left(buf, hand_scale=0.10)
        assert result is not None
        assert result.gesture_name == 'swipe_left'

    def test_swipe_right_not_swipe_left(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_right']]
        assert detect_swipe_left(buf, hand_scale=0.10) is None

    def test_swipe_left_rejected_if_too_slow(self, swipe_negative_cases) -> None:
        # Mirror the too-slow trajectory in x.
        buf = [(s[0], s[1], s[2]) for s in swipe_negative_cases['too_slow_swipe_right']]
        mirrored = [(1.0 - s[0], s[1], s[2]) for s in buf]
        assert detect_swipe_left(mirrored, hand_scale=0.10) is None


# ======================================================================
# Swipe Up
# ======================================================================

class TestSwipeUp:
    def test_swipe_up_detected(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_up']]
        result = detect_swipe_up(buf, hand_scale=0.10)
        assert result is not None
        assert result.gesture_name == 'swipe_up'

    def test_swipe_down_not_swipe_up(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_down']]
        assert detect_swipe_up(buf, hand_scale=0.10) is None

    def test_swipe_up_rejected_if_too_horizontal(self, gesture_trajectories) -> None:
        # A horizontal swipe is rejected by Swipe Up because abs(dx) would
        # exceed the dy_max.
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_right']]
        assert detect_swipe_up(buf, hand_scale=0.10) is None


# ======================================================================
# Swipe Down (mirror of Swipe Up)
# ======================================================================

class TestSwipeDown:
    def test_swipe_down_detected(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_down']]
        result = detect_swipe_down(buf, hand_scale=0.10)
        assert result is not None
        assert result.gesture_name == 'swipe_down'

    def test_swipe_up_not_swipe_down(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_up']]
        assert detect_swipe_down(buf, hand_scale=0.10) is None


# ======================================================================
# Wave
# ======================================================================

class TestWave:
    def test_wave_detected(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['wave']]
        result = detect_wave(buf, hand_scale=0.10)
        assert result is not None
        assert result.gesture_name == 'wave'

    def test_wave_rejected_for_monotonic_motion(self, swipe_negative_cases) -> None:
        # Monotonic rightward motion = 0 reversals -> not a wave.
        buf = [(s[0], s[1], s[2]) for s in swipe_negative_cases['monotonic_rightward_no_reversal']]
        assert detect_wave(buf, hand_scale=0.10) is None

    def test_wave_rejected_with_insufficient_buffer(self) -> None:
        buf = [(0.30, 0.50, 0), (0.40, 0.50, 33)]
        assert detect_wave(buf, hand_scale=0.10) is None

    def test_wave_rejected_for_low_amplitude(self) -> None:
        # Small zigzag with ≥2 reversals but only 0.01 raw amplitude,
        # which is 0.1 hand-scales at hand_scale=0.10 — well below
        # the 1.0 hand-scale threshold. Must be rejected even though
        # the reversal count is sufficient.
        buf = [
            (0.50, 0.50, 0),
            (0.51, 0.50, 33),
            (0.50, 0.50, 66),
            (0.51, 0.50, 100),
            (0.50, 0.50, 133),
        ]
        assert detect_wave(buf, hand_scale=0.10) is None

    def test_wave_rejected_for_low_amplitude_without_hand_scale(self) -> None:
        # When hand_scale is 0.0 the amplitude check returns None
        # (cannot verify the amplitude is meaningful).
        buf = [
            (0.30, 0.50, 0),
            (0.50, 0.50, 33),
            (0.30, 0.50, 66),
        ]
        assert detect_wave(buf, hand_scale=0.0) is None


# ======================================================================
# Circular Motion
# ======================================================================

class TestCircularMotion:
    def test_circular_motion_detected(self, gesture_trajectories) -> None:
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['circular_motion']]
        result = detect_circular_motion(buf, hand_scale=0.10)
        assert result is not None
        assert result.gesture_name == 'circular_motion'

    def test_circular_motion_rejected_for_straight_swipe(
        self, gesture_trajectories
    ) -> None:
        # A straight horizontal swipe is highly elongated (aspect >> 2)
        # and cannot form a circular bounding box.
        buf = [(s[0], s[1], s[2]) for s in gesture_trajectories['swipe_right']]
        assert detect_circular_motion(buf, hand_scale=0.10) is None

    def test_circular_motion_rejected_with_insufficient_buffer(self) -> None:
        buf = [(0.50, 0.50, 0), (0.55, 0.50, 33)]
        assert detect_circular_motion(buf, hand_scale=0.10) is None


# ======================================================================
# Hot-path-never-raises discipline (RULES §6.4)
# ======================================================================

class TestHotPathNeverRaises:
    @pytest.mark.parametrize('recognizer', [
        detect_swipe_right,
        detect_swipe_left,
        detect_swipe_up,
        detect_swipe_down,
        detect_wave,
        detect_circular_motion,
    ])
    def test_empty_buffer_returns_none(self, recognizer) -> None:
        # All dynamic recognizers must return None (not raise) on an
        # empty buffer. RULES §6.4.
        result = recognizer([], hand_scale=0.10)
        assert result is None

    @pytest.mark.parametrize('recognizer', [
        detect_swipe_right,
        detect_swipe_left,
        detect_swipe_up,
        detect_swipe_down,
        detect_wave,
        detect_circular_motion,
    ])
    def test_zero_hand_scale_returns_none(self, recognizer) -> None:
        # hand_scale <= 0 must short-circuit to None rather than
        # producing an inf/NaN result.
        buf = [(0.30, 0.50, 0), (0.40, 0.50, 33)]
        result = recognizer(buf, hand_scale=0.0)
        assert result is None


# ======================================================================
# Helpers
# ======================================================================

class TestNormalizedDisplacementHelper:
    def test_basic_normalization(self) -> None:
        # (0,0) -> (0.5, 0.5) at scale 0.1 = (5, 5)
        dx, dy = normalized_displacement((0.0, 0.0), (0.5, 0.5), 0.1)
        assert dx == pytest.approx(5.0)
        assert dy == pytest.approx(5.0)

    def test_scale_invariance(self) -> None:
        # Doubling both displacement and scale -> same ratio.
        dx1, dy1 = normalized_displacement((0, 0), (0.3, 0.4), 0.1)
        dx2, dy2 = normalized_displacement((0, 0), (0.6, 0.8), 0.2)
        assert dx1 == pytest.approx(dx2)
        assert dy1 == pytest.approx(dy2)

    def test_zero_scale_returns_inf(self) -> None:
        dx, dy = normalized_displacement((0, 0), (1, 1), 0)
        assert dx == float('inf')
        assert dy == float('inf')