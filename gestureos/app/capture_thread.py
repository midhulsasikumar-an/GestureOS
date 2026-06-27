"""CaptureThread — owns the camera loop on a worker QThread.

Implements the threading model from TRD §2.2: the worker thread owns the
camera loop and runs the per-frame pipeline synchronously, then emits
Qt signals that the main thread consumes for UI updates.

At Checkpoint 1 the per-frame pipeline is intentionally minimal:
    read_frame → CameraValidator.record_frame → RGB convert → TrackingModule.detect

Gesture recognition (Checkpoint 3+), activation gate (Checkpoint 4+),
context engine (Checkpoint 6+), and action dispatch (Checkpoint 5+)
slots are added incrementally by their respective checkpoints.

RULES §12.1: the frame loop is kept allocation-light — no per-frame list
or dict allocations beyond the HandData list produced by `detect()`.
A persistent RGB conversion buffer is reused across frames to avoid a
new ndarray allocation on every iteration.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from camera.camera_module import CameraModule
from camera.errors import CameraUnavailableError
from diagnostics.camera_validator import CameraValidator
from models.data_models import HandData
from settings.settings_manager import Settings
from tracking.hand_detector import TrackingModule, TrackingInitError


logger = logging.getLogger('gestureos')


# Number of consecutive dropped frames that triggers a reconnect attempt
_DROP_RECONNECT_THRESHOLD = 10


class CaptureThread(QThread):
    """Background QThread that runs the per-frame capture pipeline.

    Signals (TRD §2.2):
        frame_ready(frame, hands, fps) — payload for the overlay
        camera_error(error_message)    — hard camera failure
        tracking_error(error_message)   — TrackingInitError after retries
        state_changed(running: bool)    — lifecycle transitions
    """

    frame_ready = pyqtSignal(object, object, float)
    camera_error = pyqtSignal(str)
    tracking_error = pyqtSignal(str)
    state_changed = pyqtSignal(bool)

    def __init__(
        self,
        camera: CameraModule,
        tracking: TrackingModule,
        validator: CameraValidator,
        settings: Settings,
    ) -> None:
        super().__init__()
        self._camera = camera
        self._tracking = tracking
        self._validator = validator
        self._settings = settings
        self._running = False
        # Persistent RGB buffer reused every frame (RULES §12.1).
        # Sized lazily on the first frame so we honour the camera's
        # negotiated width/height even when the driver overrides the
        # requested resolution.
        self._rgb_buf: np.ndarray | None = None

    # -- Lifecycle -----------------------------------------------------------

    def stop(self) -> None:
        """Request the worker loop to exit at the next iteration."""
        self._running = False

    def run(self) -> None:
        """Main worker loop. Runs until stop() is called or hard failure."""
        self._running = True
        self.state_changed.emit(True)
        try:
            self._camera.open()
            self._tracking.initialize()
        except (CameraUnavailableError, TrackingInitError) as exc:
            self.camera_error.emit(str(exc))
            self._running = False
            self.state_changed.emit(False)
            return

        # FPS measurement — rolling counter recomputed each frame from
        # the validator's measured_fps() so we never allocate a per-frame
        # struct (RULES §12.1).
        last_log_ts = 0.0
        try:
            while self._running:
                t0 = time.monotonic()
                frame = self._camera.read_frame()
                if frame is None:
                    if self._camera.consecutive_drops >= _DROP_RECONNECT_THRESHOLD:
                        if not self._camera.reconnect():
                            self.camera_error.emit(
                                'Camera unavailable after reconnect attempts'
                            )
                            break
                        self._validator.reset()
                        self._tracking.initialize()
                        # The native dimensions may have changed after
                        # reconnect — drop the cached RGB buffer so it
                        # is reallocated against the new shape.
                        self._rgb_buf = None
                    continue

                self._validator.record_frame(t0)

                # Camera validation (cheap; recomputed every frame but
                # internally cached — see CameraValidator.check()).
                quality = self._validator.check(
                    now=t0,
                    resolution=self._camera.reported_resolution,
                )

                # MediaPipe wants RGB. We reuse a single buffer instead
                # of allocating a fresh ndarray every frame (RULES §12.1).
                # The buffer is contiguous float-free uint8 so cv2.cvtColor
                # can write into it in place.
                if (
                    self._rgb_buf is None
                    or self._rgb_buf.shape[:2] != frame.shape[:2]
                ):
                    self._rgb_buf = np.empty(frame.shape, dtype=frame.dtype)
                cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=self._rgb_buf)

                hands: list[HandData] = []
                try:
                    hands = self._tracking.detect(self._rgb_buf)
                except TrackingInitError as exc:
                    self.tracking_error.emit(str(exc))
                    break

                fps = self._validator.measured_fps()
                self.frame_ready.emit(frame, hands, fps)

                # Throttled status log — once per ~1s
                if t0 - last_log_ts >= 1.0:
                    last_log_ts = t0
                    logger.debug(
                        'capture_thread',
                        extra={'extras': {
                            'measured_fps': round(fps, 2),
                            'fps_ok': quality.fps_ok,
                            'resolution_ok': quality.resolution_ok,
                            'hands': len(hands),
                        }},
                    )

                # Frame pacing: cap the loop at the camera's target FPS
                # only when a frame iteration completed significantly
                # faster than the target. cap.read() already blocks for
                # the next frame, so this sleep is a backstop for the
                # rare case where CPU work is faster than the camera.
                target_period = 1.0 / max(1, self._settings.target_fps)
                elapsed = time.monotonic() - t0
                if elapsed < target_period:
                    time.sleep(target_period - elapsed)
        finally:
            self._camera.release()
            self._tracking.close()
            self._running = False
            self.state_changed.emit(False)