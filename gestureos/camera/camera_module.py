"""Camera capture pipeline.

Implements TRD §3.1 (CameraModule).  Wraps `cv2.VideoCapture`, owns the
device lifecycle (open / read / reconnect / release), applies the
documented flip + resize preprocessing, and emits a single typed error
on hard failure so callers can apply the 10-attempt/2s reconnect policy
in one place.

Default resolution is 1280x720 (matches the reference implementation in
``handtrack/`` and gives MediaPipe enough pixel density to track both
hands stably through rotation and partial occlusion). The driver may
negotiate a different actual resolution; ``read_frame()`` adapts and
only resizes when needed (RULES §12.1).

RULES §2.5: this module does not import from any other pipeline module
(recognition, conflict resolution, executor).  RULES §7.x does not apply
here — `CameraModule` does not dispatch OS input events.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import cv2
import numpy as np

from camera.errors import CameraUnavailableError


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.1)
# ---------------------------------------------------------------------------

RECONNECT_MAX_ATTEMPTS: int = 10
RECONNECT_INTERVAL_S: float = 2.0


class CameraModule:
    """Owns the camera device lifecycle and yields preprocessed BGR frames.

    Responsibilities (TRD §3.1):
      - open/configure the device (index, target resolution, target FPS)
      - read frames and apply flip + resize preprocessing
      - detect disconnection and attempt reconnect (10 attempts, 2s interval)
      - on hard failure, raise `CameraUnavailableError`; the caller keeps
        the application running

    Outputs:
      np.ndarray shape (height, width, 3), BGR, flipped (mirror), resized
      to the configured width × height.

    Error handling:
      - `cv2.VideoCapture` fails to open → CameraUnavailableError
      - dropped frame → increment counter, return None
      - 10 consecutive drops → treat as disconnect, retry every 2s up
        to 10 attempts; after that, raise CameraUnavailableError
    """

    def __init__(
        self,
        device_index: int,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
    ) -> None:
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap: cv2.VideoCapture | None = None
        self._native_width: int = 0
        self._native_height: int = 0
        self.consecutive_drops = 0

    # -- Public API ----------------------------------------------------------

    def open(self) -> None:
        """Open the camera device. Raises CameraUnavailableError on failure."""
        if self._cap is not None:
            return  # already open

        cap = cv2.VideoCapture(self.device_index)
        if not cap.isOpened():
            cap.release()
            raise CameraUnavailableError(
                f'Failed to open camera at index {self.device_index}'
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Request a 1-frame internal buffer so cap.read() returns the
        # freshest frame instead of a stale one queued from the driver.
        # Some Windows drivers (DSHOW / MSMF) silently ignore this property;
        # the call is best-effort and never fatal. See RULES §12.1
        # (frame-loop efficiency — never read stale frames).
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # noqa: BLE001 — driver quirk, not our problem
            pass

        # Discover what the driver actually negotiated. Many webcams
        # reject 1280x720 and silently fall back to a different mode;
        # we cache the native size so read_frame() can skip the resize
        # when it would be a no-op.
        self._native_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._native_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._cap = cap
        self.consecutive_drops = 0
        logger.info(
            'camera',
            extra={'extras': {
                'device_index': self.device_index,
                'requested_width': self.width,
                'requested_height': self.height,
                'requested_fps': self.fps,
                'actual_width': self._native_width,
                'actual_height': self._native_height,
            }},
        )

    def read_frame(self) -> np.ndarray | None:
        """Read one frame and apply flip+resize. Returns None on dropped frame.

        A None return signals a transient drop — callers should NOT treat
        this as a fatal error.  Only after the 10-attempt reconnect policy
        is exhausted is a hard failure raised.

        Optimization: if the driver returned the requested resolution
        natively, the resize is skipped (RULES §12.1). When the requested
        resolution differs, the resize still runs.
        """
        if self._cap is None:
            self.open()

        assert self._cap is not None
        ret, frame = self._cap.read()
        if not ret:
            self.consecutive_drops += 1
            return None

        self.consecutive_drops = 0
        frame = cv2.flip(frame, 1)  # mirror
        # Skip resize when the driver already returned our target shape.
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))
        return frame

    def reconnect(self) -> bool:
        """Attempt to reconnect up to RECONNECT_MAX_ATTEMPTS times.

        Returns True if the camera is back, False if all attempts failed.
        On failure the underlying capture handle is left released — the
        caller should keep the app running and surface a status to the
        user (overlay warning surface is Checkpoint 8).
        """
        logger.warning(
            'camera',
            extra={'extras': {
                'event': 'reconnect_start',
                'consecutive_drops': self.consecutive_drops,
                'max_attempts': RECONNECT_MAX_ATTEMPTS,
            }},
        )
        self.release()

        for attempt in range(1, RECONNECT_MAX_ATTEMPTS + 1):
            time.sleep(RECONNECT_INTERVAL_S)
            try:
                self.open()
                logger.info(
                    'camera',
                    extra={'extras': {
                        'event': 'reconnect_success',
                        'attempt': attempt,
                    }},
                )
                return True
            except CameraUnavailableError:
                logger.warning(
                    'camera',
                    extra={'extras': {
                        'event': 'reconnect_attempt_failed',
                        'attempt': attempt,
                    }},
                )
                continue

        logger.error(
            'camera',
            extra={'extras': {
                'event': 'reconnect_exhausted',
                'attempts': RECONNECT_MAX_ATTEMPTS,
            }},
        )
        return False

    def release(self) -> None:
        """Release the underlying capture handle. Idempotent."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self.consecutive_drops = 0

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def reported_fps(self) -> float:
        """Returns the camera's self-reported FPS via CAP_PROP_FPS.

        May be inaccurate on cameras that misreport — prefer
        `CameraValidator.measured_fps()` for actual measurement (TRD §3.2).
        """
        if self._cap is None:
            return 0.0
        return float(self._cap.get(cv2.CAP_PROP_FPS))

    @property
    def reported_resolution(self) -> tuple[int, int]:
        """Returns the camera's self-reported (width, height)."""
        if self._cap is None:
            return (0, 0)
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h)