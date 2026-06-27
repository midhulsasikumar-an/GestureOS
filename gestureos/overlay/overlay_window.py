"""Minimal PyQt6 overlay window for Checkpoint 1.

Implements a deliberately simple version of TRD §3.15 (OverlayEngine):
shows the live webcam preview with hand skeletons drawn on top, plus a
small status overlay with the current measured FPS and detected hand
count.

At Checkpoint 1 there is no gesture badge, no profile/context/state
indicators, no quality-warning badges — those are added by later
checkpoints per the Implementation Plan §5 (full status bar comes in
once profile/context concepts exist).

RULES §3.3: any tunable values used here should be named constants; we
keep this minimal version without separate config.py because at CP-1
there are no tunables yet.  Future checkpoints will introduce config.py.
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


def _bgr_to_qimage(frame: np.ndarray) -> QImage:
    """Convert a BGR frame to a QImage for Qt display."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    return QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()


def _draw_status(frame: np.ndarray, fps: float, hand_count: int) -> np.ndarray:
    """Draw an FPS + hand-count badge in the top-left corner."""
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
    cv2.putText(
        frame, text, (x0 + 6, y1 - baseline - 4),
        cv2.FONT_HERSHEY_SIMPLEX, STATUS_FONT_SCALE,
        STATUS_TEXT_COLOR, 1, cv2.LINE_AA,
    )
    return frame


class OverlayWindow(QWidget):
    """Minimal webcam preview with skeleton + status overlay.

    Public API:
        update_frame(frame, hands, fps) — call from a Qt slot connected
            to CaptureThread's frame_ready signal. Stores the latest
            payload and triggers a repaint.
        show() / close() / isVisible() — standard QWidget accessors.

    The repaint is driven by a QTimer at REFRESH_INTERVAL_MS (~30 FPS)
    so paint events are coalesced and bounded regardless of how often
    upstream signals arrive.  This keeps the main thread free of
    allocation-heavy paint logic (RULES §12.1).
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._latest_frame: np.ndarray | None = None
        self._latest_hands: list[HandData] = []
        self._latest_fps: float = 0.0

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

    def update_frame(
        self,
        frame: np.ndarray,
        hands: Iterable[HandData],
        fps: float,
    ) -> None:
        """Store the latest payload for the next paint cycle.

        Called from a Qt slot connected to CaptureThread.frame_ready.
        """
        self._latest_frame = frame
        self._latest_hands = list(hands)
        self._latest_fps = float(fps)

    # -- Internal paint loop -------------------------------------------------

    def _repaint(self) -> None:
        if self._latest_frame is None:
            return
        frame = self._latest_frame.copy()
        from overlay.skeleton_renderer import render_skeleton

        frame = render_skeleton(frame, self._latest_hands)
        frame = _draw_status(frame, self._latest_fps, len(self._latest_hands))
        qimg = _bgr_to_qimage(frame)
        self._image_label.setPixmap(QPixmap.fromImage(qimg))

    # -- Lifecycle -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt naming
        self._refresh_timer.stop()
        super().closeEvent(event)