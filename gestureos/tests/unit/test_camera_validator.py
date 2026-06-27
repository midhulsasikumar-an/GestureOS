"""Unit tests for CameraValidator — Checkpoint 1.

Per TRD §13.2/§13.3: no live camera required. All tests feed synthetic
timestamps and resolution values directly into CameraValidator.

Covers (per Implementation Plan §5 Testing Strategy):
  - test_measured_fps_zero_with_no_frames
  - test_measured_fps_correct_constant
  - test_sustained_low_fps_detected_after_5s
  - test_brief_fps_dip_not_flagged
  - test_high_fps_reports_ok
  - test_resolution_ok_meets_minimum
  - test_resolution_ok_below_minimum
  - test_check_uses_resolution_when_provided
  - test_check_default_resolution_ok_when_not_provided
  - test_reset_clears_history_and_low_state
"""

from __future__ import annotations

import pytest

from diagnostics.camera_validator import (
    MIN_FPS,
    MIN_RESOLUTION,
    SUSTAINED_LOW_FPS_S,
    CameraValidator,
)


# ======================================================================
# Measurement
# ======================================================================

class TestMeasuredFps:
    def test_measured_fps_zero_with_no_frames(self) -> None:
        """No frames recorded → 0.0."""
        v = CameraValidator()
        assert v.measured_fps() == 0.0

    def test_measured_fps_zero_with_one_frame(self) -> None:
        """Single frame cannot form a span → 0.0."""
        v = CameraValidator()
        v.record_frame(0.0)
        assert v.measured_fps() == 0.0

    def test_measured_fps_correct_constant(self) -> None:
        """30 frames over 1s → measured_fps ≈ 29 (n-1)/span."""
        v = CameraValidator()
        # 30 timestamps 1/30s apart → span = 29/30 ≈ 0.9667
        for i in range(30):
            v.record_frame(i / 30.0)
        measured = v.measured_fps()
        assert 28.0 < measured < 30.5, f'Expected ~29 FPS, got {measured}'


# ======================================================================
# Sustained-low detection (5s threshold)
# ======================================================================

class TestSustainedLowFps:
    def test_sustained_low_fps_detected_after_5s(self) -> None:
        """18 FPS for 6s → fps_ok becomes False after the 5s threshold."""
        v = CameraValidator(min_fps=25.0, sustained_low_fps_s=5.0)
        # 18 FPS for 6 seconds — generate timestamps without FP drift.
        dt = 1.0 / 18.0
        timestamps = [i * dt for i in range(int(18 * 6))]
        for ts in timestamps:
            v.record_frame(ts)
        quality = v.check(now=timestamps[-1] + dt)
        assert quality.fps_ok is False
        assert quality.measured_fps < 25.0

    def test_brief_fps_dip_not_flagged(self) -> None:
        """A short dip at 18 FPS (under 5s) does not flip fps_ok to False."""
        v = CameraValidator(min_fps=25.0, sustained_low_fps_s=5.0)
        dt = 1.0 / 18.0
        timestamps = [i * dt for i in range(18)]  # 1 second of dip
        for ts in timestamps:
            v.record_frame(ts)
        quality = v.check(now=timestamps[-1] + dt)
        assert quality.fps_ok is True, '1s dip must not be flagged'

    def test_high_fps_reports_ok(self) -> None:
        """30 FPS for 6s → fps_ok stays True."""
        v = CameraValidator(min_fps=25.0, sustained_low_fps_s=5.0)
        dt = 1.0 / 30.0
        timestamps = [i * dt for i in range(int(30 * 6))]
        for ts in timestamps:
            v.record_frame(ts)
        quality = v.check(now=timestamps[-1] + dt)
        assert quality.fps_ok is True


# ======================================================================
# Resolution validation
# ======================================================================

class TestResolution:
    def test_resolution_ok_meets_minimum(self) -> None:
        """Exact-minimum and above → True."""
        v = CameraValidator()
        assert v.resolution_ok((640, 480)) is True
        assert v.resolution_ok((1280, 720)) is True

    def test_resolution_ok_below_minimum(self) -> None:
        """Below minimum on either axis → False."""
        v = CameraValidator()
        assert v.resolution_ok((320, 480)) is False
        assert v.resolution_ok((640, 360)) is False

    def test_check_uses_resolution_when_provided(self) -> None:
        """check(resolution=...) propagates resolution_ok to CameraQuality."""
        v = CameraValidator()
        # No frames → fps is 0, fps_ok defaults to True
        quality = v.check(now=0.0, resolution=(1280, 720))
        assert quality.resolution_ok is True

    def test_check_default_resolution_ok_when_not_provided(self) -> None:
        """When resolution=None, resolution_ok defaults to True (not validated)."""
        v = CameraValidator()
        quality = v.check(now=0.0)
        assert quality.resolution_ok is True


# ======================================================================
# Reset
# ======================================================================

class TestReset:
    def test_reset_clears_history_and_low_state(self) -> None:
        """After reset, measured_fps is 0 and sustained-low tracking is gone."""
        v = CameraValidator(min_fps=25.0, sustained_low_fps_s=5.0)
        t = 0.0
        for _ in range(int(18 * 6)):
            v.record_frame(t)
            t += 1.0 / 18.0
        assert v.measured_fps() < 25.0
        v.reset()
        assert v.measured_fps() == 0.0
        assert v.low_fps_since is None


# ======================================================================
# Recovery: low → high transitions clear the sustained-low state
# ======================================================================

class TestRecovery:
    def test_recovery_clears_low_state(self) -> None:
        """Brief recovery clears low_fps_since; sustained-low tracking restarts."""
        v = CameraValidator(min_fps=25.0, sustained_low_fps_s=5.0)
        # 6s at 18 FPS — generate timestamps without FP drift.
        dt_low = 1.0 / 18.0
        low_timestamps = [i * dt_low for i in range(int(18 * 6))]
        for ts in low_timestamps:
            v.record_frame(ts)
        # Drive low_fps_since via check()
        quality = v.check(now=low_timestamps[-1] + dt_low)
        assert quality.fps_ok is False
        assert v.low_fps_since is not None
        # One second at high FPS — use a clear start time after the low sequence.
        dt_high = 1.0 / 60.0
        t_start = low_timestamps[-1] + dt_low
        high_timestamps = [t_start + i * dt_high for i in range(60)]
        for ts in high_timestamps:
            v.record_frame(ts)
        # Recovery: high FPS clears low_fps_since
        v.check(now=high_timestamps[-1] + dt_high)
        assert v.low_fps_since is None


# ======================================================================
# Public constants are sane
# ======================================================================

class TestConstants:
    def test_min_fps_25(self) -> None:
        assert MIN_FPS == 25.0

    def test_min_resolution_640x480(self) -> None:
        assert MIN_RESOLUTION == (640, 480)

    def test_sustained_low_5s(self) -> None:
        assert SUSTAINED_LOW_FPS_S == 5.0