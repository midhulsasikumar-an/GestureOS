"""Minimal PyQt6 overlay window for Checkpoint 1.

Implements a deliberately simple version of TRD §3.15 (OverlayEngine):
shows the live webcam preview with hand skeletons drawn on top, plus a
small status overlay with the current measured FPS and detected hand
count.

At Checkpoint 1 there is no gesture badge, no profile/context/state
indicators, no quality-warning badges — those are added by later
checkpoints per the Implementation Plan §5 (full status bar comes in
once profile/context concepts exist).

CP-4 adds an activation-state indicator to the existing status badge:
the badge text is rendered in green when the gesture pipeline is
ACTIVE and grey when INACTIVE (PRD §8.10 / FR-VF-06). The skeleton
overlay continues to render in both states (FR-AM-02). The state is
supplied via the new `update_tracking_state()` slot, connected to
the activation-state bridge in `GestureOSApp`. The badge layout is
otherwise unchanged from CP-1.

RULES §3.3: any tunable values used here should be named constants; we
keep this minimal version without separate config.py because at CP-1
there are no tunables yet.  Future checkpoints will introduce config.py.

Developer Mode extension (additive, opt-in):
    When `settings.developer_mode` is True, the existing minimal badge
    is augmented with a richer diagnostic panel that visualizes the
    per-frame pipeline state (FPS, hand count, HandData fields,
    finger states, palm orientation, scale, occlusion, and — when a
    caller-supplied `gesture_state` is forwarded — gesture pipeline
    outputs). When `settings.developer_mode` is False (default), the
    panel is a no-op and the existing CP-1 UX is unchanged.

    This module does NOT modify the gesture recognition pipeline; it
    only visualizes state that already exists in the wire. The
    `gesture_state` parameter is forward-compatible — when a future
    checkpoint wires gesture pipeline output into the
    `CaptureThread.frame_ready` signal, the panel populates
    automatically with no OverlayWindow changes required.
"""

from __future__ import annotations

import logging
from typing import Iterable

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from models.data_models import HandData


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants
# ---------------------------------------------------------------------------

WINDOW_TITLE = 'GestureOS Overlay'
STATUS_FONT_SCALE = 0.6
STATUS_TEXT_COLOR = (255, 255, 255)   # BGR — white
STATUS_BG_COLOR = (0, 0, 0)          # BGR — black
STATUS_BG_ALPHA = 0.55
REFRESH_INTERVAL_MS = 33              # ~30 FPS paint timer

# CP-4: activation-state indicator colors (PRD §8.10 / FR-VF-06).
# ACTIVE is green; INACTIVE is grey. Both are BGR tuples.
STATUS_TEXT_COLOR_ACTIVE = (60, 200, 60)     # BGR — green
STATUS_TEXT_COLOR_INACTIVE = (170, 170, 170)  # BGR — grey
STATUS_STATE_ACTIVE = 'ACTIVE'
STATUS_STATE_INACTIVE = 'INACTIVE'


def _bgr_to_qimage(frame: np.ndarray) -> QImage:
    """Convert a BGR frame to a QImage for Qt display."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    return QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()


def _draw_status(
    frame: np.ndarray,
    fps: float,
    hand_count: int,
    tracking_state: str = STATUS_STATE_INACTIVE,
) -> np.ndarray:
    """Draw an FPS + hand-count badge in the top-left corner.

    CP-4: the badge text color reflects the activation state
    (PRD §8.10 FR-VF-06):
      - ACTIVE   → green  (STATUS_TEXT_COLOR_ACTIVE)
      - INACTIVE → grey   (STATUS_TEXT_COLOR_INACTIVE)
    Backdrop and layout are unchanged from CP-1.
    """
    text = f'FPS: {fps:5.1f}   Hands: {hand_count}'
    (tw, th), baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, STATUS_FONT_SCALE, 1
    )
    x0, y0 = 8, 8
    x1, y1 = x0 + tw + 12, y0 + th + baseline + 10
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), STATUS_BG_COLOR, -1)
    cv2.addWeighted(overlay[0:y1 - y0, x0:x1], STATUS_BG_ALPHA,
                    frame[0:y1 - y0, x0:x1], 1 - STATUS_BG_ALPHA, 0,
                    dst=frame[0:y1 - y0, x0:x1])
    # CP-4: pick text color based on the current activation state.
    if tracking_state == STATUS_STATE_ACTIVE:
        text_color = STATUS_TEXT_COLOR_ACTIVE
    else:
        text_color = STATUS_TEXT_COLOR_INACTIVE
    cv2.putText(
        frame, text, (x0 + 6, y1 - baseline - 4),
        cv2.FONT_HERSHEY_SIMPLEX, STATUS_FONT_SCALE,
        text_color, 1, cv2.LINE_AA,
    )
    return frame


class OverlayWindow(QWidget):
    """Minimal webcam preview with skeleton + status overlay.

    Public API:
        update_frame(frame, hands, fps) — call from a Qt slot connected
            to CaptureThread's frame_ready signal. Stores the latest
            payload and triggers a repaint.
        update_frame(frame, hands, fps, gesture_state=None) — extended
            form for forward compatibility with the gesture pipeline.
            When `gesture_state` is provided, the Developer Mode panel
            populates the gesture/stability/cooldown fields.
        set_settings(settings) — update the settings reference at
            runtime (e.g., when the user toggles developer_mode via a
            future settings UI). When developer_mode is True, the
            next repaint will include the debug panel.
        show() / close() / isVisible() — standard QWidget accessors.

    The repaint is driven by a QTimer at REFRESH_INTERVAL_MS (~30 FPS)
    so paint events are coalesced and bounded regardless of how often
    upstream signals arrive.  This keeps the main thread free of
    allocation-heavy paint logic (RULES §12.1).

    Developer Mode is opt-in via `settings.developer_mode = True`.
    When False (the default), the existing minimal CP-1 badge is
    rendered unchanged — no new layout, no new computations, no
    performance impact beyond a single boolean check.
    """

    def __init__(self, settings=None) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._latest_frame: np.ndarray | None = None
        self._latest_hands: list[HandData] = []
        self._latest_fps: float = 0.0
        self._latest_gesture_state = None
        # CP-4: current activation state for the status-badge color.
        # Initialized to INACTIVE (matches `ActivationGate`'s default
        # on launch per FR-AM-06). Updated by `update_tracking_state`
        # from the activation-state bridge in `GestureOSApp`.
        self._latest_tracking_state: str = STATUS_STATE_INACTIVE

        # Settings is held as a reference (not copied) so that a future
        # settings UI can toggle developer_mode at runtime via
        # `set_settings(...)` and the next repaint reflects the change
        # without requiring any OverlayWindow API change.
        self._settings = settings

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(640, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._image_label)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._repaint)
        self._refresh_timer.start(REFRESH_INTERVAL_MS)

    # -- Public API ----------------------------------------------------------

    def set_settings(self, settings) -> None:
        """Replace the active settings reference.

        Called when the operator toggles settings (e.g., via the future
        settings panel — out of CP-1/3 scope). The next repaint reads
        the new `developer_mode` value, so no further state change is
        needed here.
        """
        self._settings = settings

    def update_frame(
        self,
        frame: np.ndarray,
        hands: Iterable[HandData],
        fps: float,
        gesture_state=None,
    ) -> None:
        """Store the latest payload for the next paint cycle.

        Called from a Qt slot connected to CaptureThread.frame_ready.
        `gesture_state` is optional — when provided, the Developer
        Mode panel populates the gesture/stability/cooldown fields
        from it; when absent, those fields render as "N/A".
        """
        self._latest_frame = frame
        self._latest_hands = list(hands)
        self._latest_fps = float(fps)
        self._latest_gesture_state = gesture_state

    def update_tracking_state(self, state: str) -> None:
        """CP-4: update the activation-state indicator color.

        Called from the activation-state bridge in `GestureOSApp`
        every time `ActivationGate.state` transitions. The next
        paint cycle renders the badge in green (ACTIVE) or grey
        (INACTIVE) per PRD §8.10 / FR-VF-06.

        Args:
            state: `'ACTIVE'` or `'INACTIVE'`. Any other value is
                treated as INACTIVE (defensive).
        """
        if state == STATUS_STATE_ACTIVE:
            self._latest_tracking_state = STATUS_STATE_ACTIVE
        else:
            self._latest_tracking_state = STATUS_STATE_INACTIVE

    # -- Internal paint loop -------------------------------------------------

    def _repaint(self) -> None:
        if self._latest_frame is None:
            return
        frame = self._latest_frame.copy()
        from overlay.skeleton_renderer import render_skeleton

        frame = render_skeleton(frame, self._latest_hands)
        frame = _draw_status(
            frame,
            self._latest_fps,
            len(self._latest_hands),
            tracking_state=self._latest_tracking_state,
        )

        # Developer Mode: opt-in, additive. Single boolean check;
        # no allocation when off (preserves CP-1 hot-path perf budget).
        developer_mode = (
            self._settings is not None
            and getattr(self._settings, 'developer_mode', False)
        )
        if developer_mode:
            from overlay.debug_panel import render_debug_panel
            frame = render_debug_panel(
                frame,
                self._latest_hands,
                self._latest_fps,
                gesture_state=self._latest_gesture_state,
            )

        qimg = _bgr_to_qimage(frame)
        self._image_label.setPixmap(QPixmap.fromImage(qimg))

    # -- Lifecycle -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt naming
        self._refresh_timer.stop()
        super().closeEvent(event)