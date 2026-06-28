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
  - CP-2 pipeline: HandIdentityModule, OcclusionHandler,
    HandScaleEstimator, PrimaryHandFilter
  - CP-3 pipeline: GestureEngine, ConflictResolver, StabilityFilter,
    CooldownFilter
  - CP-4: ActivationGate (the binary safety gate)

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

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from app.capture_thread import CaptureThread
from camera.camera_module import CameraModule
from diagnostics.camera_validator import CameraValidator
from diagnostics.diagnostics_manager import DiagnosticsManager
from gestures.activation_gate import ActivationGate, TrackingState
from gestures.conflict_resolver import ConflictResolver
from gestures.cooldown_filter import CooldownFilter
from gestures.gesture_engine import GestureEngine
from gestures.stability_filter import StabilityFilter
from overlay.overlay_window import OverlayWindow
from settings.settings_manager import Settings, SettingsManager
from tracking.hand_detector import TrackingModule
from tracking.hand_identity import HandIdentityModule
from tracking.hand_scale import HandScaleEstimator
from tracking.occlusion_handler import OcclusionHandler
from tracking.primary_hand_filter import PrimaryHandFilter


logger = logging.getLogger('gestureos')


class ActivationStateBridge(QObject):
    """A small Qt shim that re-emits activation-state changes as a Qt
    signal so the overlay (main thread) can update its indicator
    without depending on the ActivationGate implementation.

    The gate itself is not a QObject (kept framework-agnostic per
    RULES §2.5). The bridge lives on the main thread and listens
    to `ActivationGate.state` transitions via `_on_state_changed`.

    Checkpoint 4's wiring uses a simple polled check: each time
    `_on_gesture_detected` fires on the main thread, it inspects
    `app.activation_gate.state` and only emits `state_changed`
    when the value actually differs from the last emitted state.
    This is O(1), runs only when a gesture frame arrives, and
    avoids coupling the gate to Qt.
    """

    state_changed = pyqtSignal(str)  # 'ACTIVE' | 'INACTIVE'

    def __init__(self, gate: ActivationGate, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._gate = gate
        self._last_emitted: TrackingState | None = None

    def on_pipeline_tick(self) -> None:
        """Called from the orchestrator on every `gesture_detected` emit.

        If the gate's state has changed since the last emit, re-emit
        `state_changed`. Otherwise no-op (zero overhead on the steady
        state path)."""
        current = self._gate.state
        if current is not self._last_emitted:
            self._last_emitted = current
            self.state_changed.emit(current.name)


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

        # CP-2 pipeline.
        self._hand_identity = HandIdentityModule()
        self._occlusion_handler = OcclusionHandler(
            retention_ms=self.settings.occlusion_retention_ms,
        )
        self._scale_estimator = HandScaleEstimator()
        self._primary_hand_filter = PrimaryHandFilter(
            dominant_hand_mode=self.settings.dominant_hand_mode,
        )

        # CP-3 pipeline.
        self._gesture_engine = GestureEngine(settings=self.settings)
        self._conflict_resolver = ConflictResolver()
        self._stability_filter = StabilityFilter(
            window_ms=self.settings.gesture_stability_window_ms,
        )
        self._cooldown_filter = CooldownFilter(settings=self.settings)

        # CP-4: ActivationGate. Constructed in INACTIVE per FR-AM-06.
        # The hold-duration setting is read once at construction; the
        # gate does not re-read Settings on every frame.
        self.activation_gate = ActivationGate(
            hold_duration_s=self.settings.activation_hold_duration_s,
            enable_closed_fist=False,  # off by default per PRD §7.2
        )
        self._activation_bridge = ActivationStateBridge(self.activation_gate)

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
        self._capture_thread.gesture_detected.connect(self._on_gesture_detected)
        self._capture_thread.camera_error.connect(self._on_camera_error)
        self._capture_thread.tracking_error.connect(self._on_tracking_error)
        self._capture_thread.state_changed.connect(self._on_state_changed)
        # Activation state bridge → overlay indicator.
        self._activation_bridge.state_changed.connect(
            self._overlay.update_tracking_state
        )

    # -- Qt slots ------------------------------------------------------------

    def _on_frame_ready(
        self,
        frame,
        hands,
        fps: float,
        gesture_state: object | None = None,
    ) -> None:
        """Receive the latest frame, pipeline-processed hands, FPS,
        and (when available) the gesture pipeline state for the
        Developer Mode overlay.

        `gesture_state` is a `SimpleNamespace` matching the
        `GesturePipelineState` shape (from `overlay/debug_panel.py`).
        When `None`, the overlay renders "N/A" for all gesture fields.
        """
        if self._overlay is not None:
            self._overlay.update_frame(
                frame,
                hands,
                fps,
                gesture_state=gesture_state,
            )

    def _on_gesture_detected(self, results) -> None:
        """Receive cooldown-cleared gestures from the CaptureThread.

        The ActivationGate.hold-timer is already fed inside
        CaptureThread._run_gesture_pipeline() from the conflict-
        resolved winners (before stability/cooldown filtering), so
        this slot only notifies the activation bridge so the overlay
        indicator can update on state changes.

        The bridge is idempotent: it only re-emits `state_changed`
        when the gate's state actually differs from the last emitted
        state. This avoids a separate Qt signal wiring path for
        every state transition while keeping the indicator responsive
        within one paint cycle (~33 ms).

        `results` is `list[GestureResult]` (possibly empty) — not
        needed by this slot directly but preserved so CP-5's
        dispatch slot can consume it in a future checkpoint.
        """
        self._activation_bridge.on_pipeline_tick()

    @staticmethod
    def _capture_thread_frame_now(results) -> float:
        """Best-effort `now` for the current frame.

        Prefer `result.timestamp` when populated (the recognizers
        stamp `time.monotonic()` on emit). Fall back to a fresh
        monotonic read so the gate's hold-timer still has a sane
        reference if a future recognizer stops stamping timestamps.
        """
        import time as _time
        if results:
            try:
                return float(results[0].timestamp)
            except (AttributeError, TypeError, ValueError):
                pass
        return _time.monotonic()

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
        # Settings is passed so the overlay can honor the
        # `developer_mode` toggle (Developer Mode diagnostic panel)
        # without needing a separate API call.
        self._overlay = OverlayWindow(settings=self.settings)
        # Push the current activation state into the overlay so the
        # badge starts in the correct color (INACTIVE = grey).
        self._overlay.update_tracking_state(self.activation_gate.state.name)
        self._overlay.show()

        self._capture_thread = CaptureThread(
            camera=self._camera,
            tracking=self._tracking,
            validator=self._validator,
            settings=self.settings,
            hand_identity=self._hand_identity,
            occlusion_handler=self._occlusion_handler,
            scale_estimator=self._scale_estimator,
            primary_hand_filter=self._primary_hand_filter,
            gesture_engine=self._gesture_engine,
            conflict_resolver=self._conflict_resolver,
            stability_filter=self._stability_filter,
            cooldown_filter=self._cooldown_filter,
            activation_gate=self.activation_gate,
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