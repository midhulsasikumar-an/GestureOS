"""GestureOSApp — top-level application wiring per TRD §2.2.

The app owns:
  - a SettingsManager (Checkpoint 0)
  - a DiagnosticsManager (Checkpoint 0)
  - a CameraModule (Checkpoint 1)
  - a CameraValidator (Checkpoint 1)
  - a TrackingModule (Checkpoint 1)
  - an OverlayWindow (Checkpoint 1 — minimal version, lazy-constructed
    in `start()` AFTER `QApplication` exists, per Qt's contract)
  - a CaptureThread (Checkpoint 1) that runs the per-frame pipeline

Lifecycle:
  start()  → show overlay, start the capture thread
  stop()   → ask the capture thread to exit, wait, close the overlay
  run()    → convenience: QApplication + start() + exec() + stop()

Qt initialization rules enforced here:
  - `__init__` MUST NOT instantiate any QWidget. Qt's contract requires
    a `QApplication` to exist before any QWidget is constructed, and
    `QApplication` is created by the caller (or by `run()`) AFTER
    `GestureOSApp.__init__` returns. Constructing `OverlayWindow()`
    inside `__init__` raises "QWidget: Must construct a QApplication
    before a QWidget" — see CP-1 manual-validation finding.
  - The `OverlayWindow` is therefore constructed lazily in `start()`.
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from app.capture_thread import CaptureThread
from camera.camera_module import CameraModule
from diagnostics.camera_validator import CameraValidator
from diagnostics.diagnostics_manager import DiagnosticsManager
from overlay.overlay_window import OverlayWindow
from settings.settings_manager import Settings, SettingsManager
from tracking.hand_detector import TrackingModule


logger = logging.getLogger('gestureos')


class GestureOSApp:
    """Top-level controller. Wires components and drives the Qt event loop.

    Per RULES §11.2, app initialization failures (camera unavailable,
    tracking init failure) must NOT crash the process — they must surface
    to the user via the overlay and the log.  Camera/tracking error
    signals are connected to overlay update slots and logged here.
    """

    def __init__(
        self,
        settings_manager: SettingsManager | None = None,
        diagnostics: DiagnosticsManager | None = None,
        qapp: QApplication | None = None,
    ) -> None:
        # If no QApplication has been provided (or doesn't yet exist),
        # construct one NOW — but only this QApplication object itself,
        # NOT any QWidget. The caller can still construct us before
        # run(), and Qt's QApplication singleton means a later
        # QApplication.instance() check inside run() will return ours.
        if qapp is None and QApplication.instance() is None:
            qapp = QApplication(sys.argv)

        self._diagnostics = diagnostics or DiagnosticsManager()
        self._settings_mgr = settings_manager or SettingsManager()
        self.settings: Settings = self._settings_mgr.load()
        self._qapp = qapp

        # Non-Qt components built fresh per app instance (each owns its
        # own native handles).
        self._camera = CameraModule(
            device_index=self.settings.camera_index,
            fps=self.settings.target_fps,
        )
        self._validator = CameraValidator()
        self._tracking = TrackingModule()

        # OverlayWindow is a QWidget — DO NOT construct it here.
        # It is built lazily in start() after QApplication is verified
        # to exist (Qt's QWidget requires an extant QApplication).
        self._overlay: OverlayWindow | None = None

        self._capture_thread: CaptureThread | None = None

    # -- Wiring --------------------------------------------------------------

    def _wire_capture_signals(self) -> None:
        assert self._capture_thread is not None
        assert self._overlay is not None
        self._capture_thread.frame_ready.connect(self._on_frame_ready)
        self._capture_thread.camera_error.connect(self._on_camera_error)
        self._capture_thread.tracking_error.connect(self._on_tracking_error)
        self._capture_thread.state_changed.connect(self._on_state_changed)

    # -- Qt slots ------------------------------------------------------------

    def _on_frame_ready(self, frame, hands, fps: float) -> None:
        if self._overlay is not None:
            self._overlay.update_frame(frame, hands, fps)

    def _on_camera_error(self, message: str) -> None:
        logger.error('app', extra={'extras': {'event': 'camera_error', 'message': message}})

    def _on_tracking_error(self, message: str) -> None:
        logger.error('app', extra={'extras': {'event': 'tracking_error', 'message': message}})

    def _on_state_changed(self, running: bool) -> None:
        logger.info(
            'app',
            extra={'extras': {'event': 'capture_thread_state', 'running': running}},
        )

    # -- Public lifecycle ----------------------------------------------------

    def start(self) -> None:
        """Construct the overlay (now safe — QApplication exists) and
        start the capture thread."""
        # Defensive check: Qt requires QApplication before any QWidget.
        if QApplication.instance() is None:
            raise RuntimeError(
                'QApplication has not been created. Call QApplication(sys.argv) '
                'before GestureOSApp.start(), or use GestureOSApp.run().'
            )
        # Lazy construction of the only QWidget in this app.
        self._overlay = OverlayWindow()
        self._overlay.show()

        self._capture_thread = CaptureThread(
            camera=self._camera,
            tracking=self._tracking,
            validator=self._validator,
            settings=self.settings,
        )
        self._wire_capture_signals()
        self._capture_thread.start()

    def stop(self) -> None:
        """Stop the capture thread and close the overlay."""
        if self._capture_thread is not None and self._capture_thread.isRunning():
            self._capture_thread.stop()
            self._capture_thread.wait(timeout=3000)
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None

    def run(self) -> int:
        """Ensure QApplication exists, then start() + exec() + stop()."""
        if self._qapp is None:
            self._qapp = QApplication.instance() or QApplication(sys.argv)
        try:
            self.start()
            return self._qapp.exec()
        finally:
            self.stop()