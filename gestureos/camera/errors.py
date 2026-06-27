"""Custom exceptions raised by the camera pipeline.

Implements TRD §3.1 (CameraModule error handling).  All camera-side
failures funnel through `CameraUnavailableError` so callers can catch a
single exception type and apply the documented reconnect policy.
"""

from __future__ import annotations


class CameraUnavailableError(Exception):
    """Raised when the camera cannot be opened or repeatedly fails to read.

    Per TRD §3.1: `cv2.VideoCapture` fails to open → CameraUnavailableError;
    dropped frames are not a hard failure (they are counted silently);
    only after 10 consecutive reconnect attempts (2s interval) does the
    camera emit this error and keep the application running.
    """