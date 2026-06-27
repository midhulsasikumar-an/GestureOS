"""GestureOS application entry point.

Checkpoint 1 (GestureOS Core Platform).  Wires up `GestureOSApp`,
which composes CameraModule + TrackingModule + OverlayWindow + the
CaptureThread that runs the per-frame pipeline.

Run with:
    python main.py

Exit codes:
    0 — clean shutdown (user closed the overlay window)
    non-zero — fatal init failure (e.g. camera unavailable, tracked via Qt
               message box or a non-fatal log line in this checkpoint;
               full UI for error surfacing comes in Checkpoint 8).

Qt initialization order (per Qt's contract — QApplication MUST exist
before any QWidget is constructed):
    1. Create QApplication(sys.argv)
    2. Construct GestureOSApp(qapp=...) — does NOT touch any QWidget
    3. Call GestureOSApp.start() — lazily constructs OverlayWindow
    4. Call QApplication.exec() — runs the event loop
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from app.core import GestureOSApp


__version__ = "0.1.0+checkpoint1"
__checkpoint__ = "1"


def main() -> int:
    """Boot GestureOSApp and run the Qt event loop."""
    logging.basicConfig(level=logging.INFO)

    # QApplication must be constructed BEFORE any QWidget. We build it
    # here and pass it explicitly to GestureOSApp so the app can defer
    # all QWidget construction to start().
    qapp = QApplication.instance() or QApplication(sys.argv)

    try:
        app = GestureOSApp(qapp=qapp)
    except Exception as exc:  # noqa: BLE001 — top-level guard per RULES §11.2
        logging.error(
            'main',
            extra={'extras': {'event': 'init_failed', 'error': str(exc)}},
        )
        return 1

    logging.info(
        'main',
        extra={'extras': {'event': 'starting', 'version': __version__, 'checkpoint': __checkpoint__}},
    )
    return app.run()


if __name__ == "__main__":
    sys.exit(main())