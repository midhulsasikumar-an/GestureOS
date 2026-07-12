"""Unit tests for camera_module.py — CP-2 handedness correction.

Tests cover:
  - read_frame() does NOT mirror the frame (flip removed)
  - read_frame() still applies resize when needed
  - No-op when frame is already at target resolution
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from camera.camera_module import CameraModule


# ======================================================================
# read_frame — no mirror
# ======================================================================

class TestReadFrameNoMirror:
    """CP-2 handedness correction: read_frame() must return the frame
    in its natural camera orientation without horizontal flipping."""

    @pytest.fixture
    def module(self) -> CameraModule:
        m = CameraModule(device_index=0, width=640, height=480, fps=30)
        # Pre-set _cap to avoid a real cv2.VideoCapture call.
        m._cap = MagicMock(spec=cv2.VideoCapture)
        m._native_width = 640
        m._native_height = 480
        return m

    def test_read_frame_does_not_call_flip(self, module) -> None:
        """Verify that cv2.flip is NOT called inside read_frame()."""
        raw_frame = np.arange(640 * 480 * 3, dtype=np.uint8).reshape((480, 640, 3))
        module._cap.read.return_value = (True, raw_frame.copy())  # type: ignore[attr-defined]

        # The old code called cv2.flip(frame, 1).  After the CP-2 fix
        # it should NOT call flip at all.  Use a sentinel to detect
        # any flip call.
        original_flip = cv2.flip
        flip_called: list[list] = []

        def _tracking_flip(mat, flip_code):  # noqa: ANN202
            flip_called.append([mat, flip_code])
            return original_flip(mat, flip_code)

        with patch('cv2.flip', side_effect=_tracking_flip):
            result = module.read_frame()

        assert result is not None
        assert flip_called == [], \
            "cv2.flip should NOT be called inside read_frame()"

    def test_read_frame_returns_raw_pixels(self, module) -> None:
        """The returned frame pixels must exactly match the camera raw
        output (no mirror/swap)."""
        raw = np.arange(640 * 480 * 3, dtype=np.uint8).reshape((480, 640, 3))
        module._cap.read.return_value = (True, raw.copy())  # type: ignore[attr-defined]
        result = module.read_frame()
        assert result is not None
        assert np.array_equal(result, raw)

    def test_read_frame_resize_when_needed(self) -> None:
        """When the camera outputs a different resolution, read_frame
        must still resize to the configured width/height."""
        m = CameraModule(device_index=0, width=320, height=240, fps=30)
        m._cap = MagicMock(spec=cv2.VideoCapture)
        m._native_width = 640
        m._native_height = 480

        raw = np.arange(640 * 480 * 3, dtype=np.uint8).reshape((480, 640, 3))
        m._cap.read.return_value = (True, raw)  # type: ignore[attr-defined]
        result = m.read_frame()
        assert result is not None
        assert result.shape == (240, 320, 3), \
            f"Expected (240, 320, 3), got {result.shape}"

    def test_consecutive_drops(self, module) -> None:
        module._cap.read.return_value = (False, None)  # type: ignore[attr-defined]
        result = module.read_frame()
        assert result is None
        assert module.consecutive_drops == 1


# ======================================================================
# Construction
# ======================================================================

class TestCameraModuleConstruction:
    """Basic construction and default values."""

    def test_default_params(self) -> None:
        m = CameraModule(device_index=1)
        assert m.device_index == 1
        assert m.width == 1280
        assert m.height == 720
        assert m.fps == 30
        assert m._cap is None
