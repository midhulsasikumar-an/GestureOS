"""Tracking-layer exception types.

Implements TRD §3.2 (HandLandmarker) and the error-extraction task from
the Implementation Plan §2.2 (CP-0: `Add tracking/errors.py`).

The tracking layer is the MediaPipe Hand Landmarker integration. Its
errors must be distinct from the camera-layer errors in
`camera/errors.py` so that callers can disambiguate the failing
subsystem (camera hardware vs. ML inference initialization).

RULES §8.1: new modules are scoped to a single responsibility. This
module contains only tracking-layer exception classes; no behavior,
no imports from other pipeline layers.
"""


class TrackingInitError(Exception):
    """Raised when MediaPipe Hand Landmarker cannot be initialized.

    This error indicates a persistent failure of the underlying
    MediaPipe model handle after the configured number of
    consecutive-error retries (see TRD §3.2 — persistent failures
    auto-reload via ModelManager).

    The CaptureThread catches this exception and emits the
    `tracking_error` Qt signal, which the orchestrator surfaces to
    the overlay rather than crashing the application (RULES §11.2).
    """

