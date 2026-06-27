"""Camera FPS / resolution validation.

Implements TRD §3.2 (CameraValidator, new in v1.2).  At Checkpoint 1
this checkpoint exposes only the **measurement** API — the user-facing
warning surface (overlay badge, "Low FPS Detected" banner) is added in
Checkpoint 8's overlay work, per the Implementation Plan §5.

RULES §9: never uses `print()`; all status flows through `logging`.
"""

from __future__ import annotations

import logging
from collections import deque

from models.data_models import CameraQuality


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.2)
# ---------------------------------------------------------------------------

MIN_FPS: float = 25.0
MIN_RESOLUTION: tuple[int, int] = (640, 480)
SUSTAINED_LOW_FPS_S: float = 5.0
FRAME_HISTORY_MAXLEN: int = 90  # ~3s at 30 FPS


class CameraValidator:
    """Continuously measures camera performance against documented minimums.

    Per TRD §3.2:
      - Inputs: per-frame timestamps from CaptureThread
      - Outputs: `CameraQuality(fps_ok, resolution_ok, measured_fps)`
        recomputed roughly once per second (cheap rolling average)
      - Dependency: OpenCV only (for the camera's CAP_PROP_* queries)
      - Error handling: never raises — degraded measurement still
        returns a best-effort `CameraQuality`

    The validator measures actual inter-frame timing rather than trusting
    `cv2.CAP_PROP_FPS` because some webcams misreport their capability
    (this is called out as a Checkpoint 1 risk in the Implementation Plan §5).
    """

    def __init__(
        self,
        min_fps: float = MIN_FPS,
        min_resolution: tuple[int, int] = MIN_RESOLUTION,
        sustained_low_fps_s: float = SUSTAINED_LOW_FPS_S,
    ) -> None:
        self.MIN_FPS = min_fps
        self.MIN_RESOLUTION = min_resolution
        self.SUSTAINED_LOW_FPS_S = sustained_low_fps_s
        self.frame_timestamps: deque[float] = deque(maxlen=FRAME_HISTORY_MAXLEN)
        self.low_fps_since: float | None = None

    # -- Recording -----------------------------------------------------------

    def record_frame(self, now: float) -> None:
        """Record the timestamp of a frame just delivered by the camera."""
        self.frame_timestamps.append(float(now))

    def reset(self) -> None:
        """Reset the rolling timestamp buffer (used on camera reconnect)."""
        self.frame_timestamps.clear()
        self.low_fps_since = None

    # -- Measurement ---------------------------------------------------------

    def measured_fps(self) -> float:
        """Compute measured FPS from the rolling timestamp buffer.

        Uses inter-frame timing, NOT the camera's self-reported FPS, so
        drivers that misreport are exposed as the real value.
        """
        if len(self.frame_timestamps) < 2:
            return 0.0
        span = self.frame_timestamps[-1] - self.frame_timestamps[0]
        if span <= 0:
            return 0.0
        return (len(self.frame_timestamps) - 1) / span

    def resolution_ok(self, resolution: tuple[int, int]) -> bool:
        """Return True if `resolution` meets the minimum requirements."""
        w, h = resolution
        return w >= self.MIN_RESOLUTION[0] and h >= self.MIN_RESOLUTION[1]

    # -- Quality check -------------------------------------------------------

    # Tolerance for sustained-low comparison: float drift over many
    # accumulated frame timestamps can lose sub-microsecond precision,
    # so we treat the window as satisfied once we're within a tiny
    # tolerance of SUSTAINED_LOW_FPS_S.
    _SUSTAINED_WINDOW_TOLERANCE_S: float = 1e-6

    def check(self, now: float, resolution: tuple[int, int] | None = None) -> CameraQuality:
        """Compute a CameraQuality snapshot.

        Args:
            now: current timestamp (seconds) — used to decide if the
                sustained-low window has elapsed since the drop started.
            resolution: (width, height) the camera is delivering. If None,
                resolution_ok defaults to True (not validated this call).
        """
        fps = self.measured_fps()

        # Sustained-low tracking: only flip fps_ok to False once we've
        # been below threshold continuously for SUSTAINED_LOW_FPS_S seconds.
        # We start optimistic (fps_ok=True) and let the sustained-window
        # logic be the sole authority on flagging.
        if fps == 0.0:
            fps_ok = True
        else:
            if fps < self.MIN_FPS:
                # The low condition started no later than the oldest frame
                # currently in the rolling buffer (could be earlier, but
                # we don't have visibility past the buffer's maxlen).
                # Use the oldest timestamp as a conservative start time.
                self.low_fps_since = self.low_fps_since or self.frame_timestamps[0]
            else:
                self.low_fps_since = None

            sustained_low = (
                self.low_fps_since is not None
                and (now - self.low_fps_since)
                >= (self.SUSTAINED_LOW_FPS_S - self._SUSTAINED_WINDOW_TOLERANCE_S)
            )
            fps_ok = not sustained_low

        if resolution is None:
            resolution_ok_value = True
        else:
            resolution_ok_value = self.resolution_ok(resolution)

        quality = CameraQuality(
            fps_ok=fps_ok,
            resolution_ok=resolution_ok_value,
            measured_fps=fps,
        )
        return quality