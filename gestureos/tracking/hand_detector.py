"""Hand landmark detection via MediaPipe Hands.

Implements TRD §3.3 (TrackingModule).  Wraps `mediapipe.solutions.hands`,
converts frames to RGB, runs inference, and builds `list[HandData]`
objects with chirality and confidence populated.

At Checkpoint 1 this module does NOT populate `role`, `scale`, or
`gesture_eligible` — those are Checkpoint 2's responsibility (HandIdentityModule,
HandScaleEstimator, PrimaryHandFilter respectively, per Implementation Plan §6).

RULES §2.4: tracking/ does not import from recognizer, conflict_resolver,
or executor.

Tracking-quality tuning notes (manual validation, CP-1):
  - ``model_complexity`` defaults to 0 for ≤2 hands. MediaPipe's
    higher-complexity model (1) is intended for >2 hands and adds
    noticeable latency without accuracy benefit at our hand count.
  - ``min_tracking_confidence`` is lowered to 0.4 (vs MediaPipe's
    default 0.5) so the tracker keeps a hand through moderate
    rotation / partial finger closure instead of dropping it and
    forcing a full re-detection pass.
  - ``min_detection_confidence`` stays at 0.5 — too low and we accept
    false-positive hands; too high and we miss hands at frame edges.
  - Re-init threshold bumped from 3 to 5 consecutive exceptions.
    Brief driver-level stalls should not force a MediaPipe rebuild;
    only persistent failures trigger the recovery path.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from models.data_models import HandData


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.3)
# ---------------------------------------------------------------------------

MAX_NUM_HANDS: int = 2
# 0 = fast path for ≤2 hands (recommended); 1 = heavier model for ≥3 hands.
MODEL_COMPLEXITY: int = 0
MIN_DETECTION_CONFIDENCE: float = 0.5
# Lower than MediaPipe's default (0.5) to keep tracking through rotation.
MIN_TRACKING_CONFIDENCE: float = 0.4
LANDMARKS_PER_HAND: int = 21
# Number of consecutive MediaPipe exceptions before we attempt re-init.
# Five frames at 30 FPS is ~167 ms of "missing", which is enough to
# distinguish a real stall from a transient driver glitch.
REINIT_AFTER_CONSECUTIVE_ERRORS: int = 5


class TrackingInitError(Exception):
    """Raised when MediaPipe Hands cannot be initialized after retry."""


class TrackingModule:
    """Wraps MediaPipe Hands and produces `list[HandData]`.

    Per TRD §3.3:
      - Inputs: RGB `np.ndarray` frame
      - Outputs: `list[HandData]`, length 0–2
      - Dependencies: mediapipe, numpy
      - Error handling:
        * MediaPipe exception → log ERROR, return empty list for that frame
        * malformed hand (≠21 landmarks) → discard that hand only
        * N consecutive exceptions (REINIT_AFTER_CONSECUTIVE_ERRORS) →
          attempt one re-init
        * failing that → raise `TrackingInitError`
    """

    def __init__(
        self,
        max_num_hands: int = MAX_NUM_HANDS,
        model_complexity: int = MODEL_COMPLEXITY,
        min_detection_confidence: float = MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = MIN_TRACKING_CONFIDENCE,
        reinit_after_errors: int = REINIT_AFTER_CONSECUTIVE_ERRORS,
    ) -> None:
        self.max_num_hands = max_num_hands
        self.model_complexity = model_complexity
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.reinit_after_errors = reinit_after_errors
        self._hands: Any = None
        self._consecutive_errors = 0

    # -- Lifecycle -----------------------------------------------------------

    def initialize(self) -> None:
        """Initialize the MediaPipe Hands solution."""
        import mediapipe as mp

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=self.max_num_hands,
            model_complexity=self.model_complexity,
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
        )
        self._consecutive_errors = 0
        logger.info(
            'tracking',
            extra={'extras': {
                'event': 'mediapipe_initialized',
                'max_num_hands': self.max_num_hands,
                'model_complexity': self.model_complexity,
                'min_detection_confidence': self.min_detection_confidence,
                'min_tracking_confidence': self.min_tracking_confidence,
            }},
        )

    def reinitialize(self) -> bool:
        """Attempt one re-init after consecutive failures. Returns True on success."""
        try:
            self.close()
            self.initialize()
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort re-init
            logger.error(
                'tracking',
                extra={'extras': {
                    'event': 'mediapipe_reinit_failed',
                    'error': str(exc),
                }},
            )
            return False

    def close(self) -> None:
        """Release MediaPipe resources. Idempotent."""
        if self._hands is not None:
            try:
                self._hands.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass
            self._hands = None

    # -- Detection -----------------------------------------------------------

    def detect(self, rgb_frame: np.ndarray) -> list[HandData]:
        """Run hand detection on an RGB frame.

        Returns 0–2 `HandData` objects.  `role`, `scale`, and
        `gesture_eligible` are NOT populated at this checkpoint — that is
        Checkpoint 2's responsibility.
        """
        if self._hands is None:
            self.initialize()

        try:
            results = self._hands.process(rgb_frame)
            self._consecutive_errors = 0
        except Exception as exc:  # noqa: BLE001 — error path per TRD §3.3
            self._consecutive_errors += 1
            logger.error(
                'tracking',
                extra={'extras': {
                    'event': 'mediapipe_exception',
                    'consecutive_errors': self._consecutive_errors,
                    'error': str(exc),
                }},
            )
            if self._consecutive_errors >= self.reinit_after_errors:
                if self.reinitialize():
                    self._consecutive_errors = 0
                else:
                    raise TrackingInitError(
                        f'MediaPipe Hands failed to reinitialize after '
                        f'{self.reinit_after_errors} consecutive errors'
                    )
            return []

        if results.multi_hand_landmarks is None or results.multi_handedness is None:
            return []

        if len(results.multi_hand_landmarks) != len(results.multi_handedness):
            # MediaPipe gave us mismatched counts — discard this frame's detections
            logger.warning(
                'tracking',
                extra={'extras': {
                    'event': 'mediapipe_hand_count_mismatch',
                    'landmarks_count': len(results.multi_hand_landmarks),
                    'handedness_count': len(results.multi_handedness),
                }},
            )
            return []

        out: list[HandData] = []
        for hand_landmarks, handedness in zip(
            results.multi_hand_landmarks, results.multi_handedness
        ):
            # Defensive: discard malformed hands
            if len(hand_landmarks.landmark) != LANDMARKS_PER_HAND:
                logger.warning(
                    'tracking',
                    extra={'extras': {
                        'event': 'malformed_hand_discarded',
                        'landmark_count': len(hand_landmarks.landmark),
                    }},
                )
                continue

            landmarks: list[tuple[float, float, float]] = [
                (lm.x, lm.y, lm.z) for lm in hand_landmarks.landmark
            ]
            chirality = handedness.classification[0].label  # 'Left' or 'Right'
            confidence = float(handedness.classification[0].score)

            out.append(
                HandData(
                    landmarks=landmarks,
                    chirality=chirality,
                    confidence=confidence,
                )
            )

        return out