"""Hand landmark detection via MediaPipe Hand Landmarker.

Implements TRD §3.2 (HandLandmarker). Wraps `MediaPipe Hand Landmarker`
via `ModelManager` (the sole model owner per RULES §13.2), converts
frames to RGB, runs inference, and builds `list[HandData]` objects
with chirality and confidence populated.

V2.0 rename of hand_detector.py. The class name `TrackingModule` is
retained as a public alias for CP-0 migration; future checkpoints may
introduce a `HandLandmarker` alias. The canonical name in the
Implementation Plan and TRD is `HandLandmarker`; this module exposes
both names to keep tests and the app from changing every checkpoint.

RULES §2.4: tracking/ does not import from recognizer, conflict_resolver,
or executor.
RULES §2.9: tracking/ does not import mediapipe directly. The
MediaPipe Hand Landmarker handle is obtained from `ModelManager`.
RULES §13.2: the Hand Landmarker is loaded only by `ModelManager`.
The detector below uses `model_manager.get_hand_landmarker()` to
obtain the inference handle.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from models.data_models import HandData
from tracking.errors import TrackingInitError


logger = logging.getLogger('gestureos')


MAX_NUM_HANDS: int = 2
MODEL_COMPLEXITY: int = 0
MIN_DETECTION_CONFIDENCE: float = 0.5
MIN_TRACKING_CONFIDENCE: float = 0.4
LANDMARKS_PER_HAND: int = 21
REINIT_AFTER_CONSECUTIVE_ERRORS: int = 5

STATUS_ACCEPTED: str = 'accepted'
STATUS_RETAINED: str = 'retained'
STATUS_FILTERED: str = 'filtered'
STATUS_DISCARDED: str = 'discarded'

REASON_HANDEDNESS_MISSING: str = 'handedness_missing'
REASON_MALFORMED_LANDMARKS: str = 'malformed_landmarks'
REASON_DOMINANT_HAND_MODE: str = 'dominant_hand_mode'
REASON_OCCLUSION_BRIDGE: str = 'occlusion_bridge'


class HandLandmarker:
    """Wraps MediaPipe Hand Landmarker (via ModelManager) and produces `list[HandData]`.

    CP-1 (per Implementation Plan §5 Task 1.2): the Hand Landmarker
    model handle is owned by `ModelManager`. This class does NOT
    import `mediapipe`; it calls `model_manager.get_hand_landmarker()`
    to obtain the inference handle. RULES §13.2 compliance.

    The public name `TrackingModule` is preserved as a backward-
    compatible alias for tests and call sites that were updated in
    the CP-0 rename but have not yet migrated to the canonical
    `HandLandmarker` name (CP-3 will converge on `HandLandmarker`).
    """

    def __init__(
        self,
        model_manager: Any | None = None,
        max_num_hands: int = MAX_NUM_HANDS,
        model_complexity: int = MODEL_COMPLEXITY,
        min_detection_confidence: float = MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = MIN_TRACKING_CONFIDENCE,
        reinit_after_errors: int = REINIT_AFTER_CONSECUTIVE_ERRORS,
    ) -> None:
        self.model_manager = model_manager
        self.max_num_hands = max_num_hands
        self.model_complexity = model_complexity
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.reinit_after_errors = reinit_after_errors
        self._hands: Any = None
        self._consecutive_errors = 0

    def initialize(self) -> None:
        """Initialize the MediaPipe Hand Landmarker via ModelManager.

        CP-1: the model handle is obtained from `ModelManager`. If
        the model is not available (e.g., the bundled `.task` file
        is missing), `initialize()` logs an ERROR and leaves
        `_hands` as None; subsequent `detect()` calls return [].
        """
        if self.model_manager is None:
            logger.error(
                'tracking',
                extra={'extras': {
                    'event': 'model_manager_missing',
                    'hint': 'HandLandmarker requires a ModelManager; '
                            'no model access possible without it.',
                }},
            )
            self._hands = None
            return

        landmarker = self.model_manager.get_hand_landmarker()
        if landmarker is None:
            logger.error(
                'tracking',
                extra={'extras': {
                    'event': 'hand_landmarker_unavailable',
                    'hint': 'ModelManager could not provide a Hand '
                            'Landmarker handle; check assets/models/.',
                }},
            )
            self._hands = None
            return

        self._hands = landmarker
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
        except Exception as exc:
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
                close_fn = getattr(self._hands, 'close', None)
                if callable(close_fn):
                    close_fn()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass
            self._hands = None

    def detect(self, rgb_frame: np.ndarray) -> list[HandData]:
        """Run hand detection on an RGB frame.

        Returns 0–2 `HandData` objects. `role`, `scale`, and
        `gesture_eligible` are NOT populated at this stage — that is
        Checkpoint 2's responsibility.

        The method is part of the hot-path (TRD §15 / RULES §6.4):
        it never raises. Internal errors are logged and an empty
        list is returned; only `TrackingInitError` is allowed to
        propagate (after the auto-reload path is exhausted).
        """
        if self._hands is None:
            self.initialize()

        if self._hands is None:
            return []

        try:
            results = self._hands.process(rgb_frame)
            self._consecutive_errors = 0
        except Exception as exc:  # noqa: BLE001 — error path per TRD §3.2
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
                        f'MediaPipe Hand Landmarker failed to '
                        f'reinitialize after {self.reinit_after_errors} '
                        f'consecutive errors'
                    )
            return []

        if results.multi_hand_landmarks is None:
            return []

        handedness_list = results.multi_handedness
        if handedness_list is None:
            logger.warning(
                'tracking',
                extra={'extras': {
                    'event': 'mediapipe_hand_count_mismatch',
                    'reason': REASON_HANDEDNESS_MISSING,
                    'landmarks_count': len(results.multi_hand_landmarks),
                    'handedness_count': 0,
                }},
            )
            return [
                self._build_handdata(
                    hand_landmarks=lm,
                    handedness_classification=None,
                    discarded=REASON_HANDEDNESS_MISSING,
                )
                for lm in results.multi_hand_landmarks
            ]

        if len(results.multi_hand_landmarks) != len(handedness_list):
            logger.warning(
                'tracking',
                extra={'extras': {
                    'event': 'mediapipe_hand_count_mismatch',
                    'landmarks_count': len(results.multi_hand_landmarks),
                    'handedness_count': len(handedness_list),
                }},
            )
            out: list[HandData] = []
            n = min(len(results.multi_hand_landmarks), len(handedness_list))
            for i in range(n):
                out.append(
                    self._build_handdata(
                        hand_landmarks=results.multi_hand_landmarks[i],
                        handedness_classification=(
                            handedness_list[i].classification[0]
                        ),
                        discarded=None,
                    )
                )
            for i in range(n, len(results.multi_hand_landmarks)):
                out.append(
                    self._build_handdata(
                        hand_landmarks=results.multi_hand_landmarks[i],
                        handedness_classification=None,
                        discarded=REASON_HANDEDNESS_MISSING,
                    )
                )
            return out

        out: list[HandData] = []
        for hand_landmarks, handedness in zip(
            results.multi_hand_landmarks, handedness_list
        ):
            out.append(
                self._build_handdata(
                    hand_landmarks=hand_landmarks,
                    handedness_classification=handedness.classification[0],
                    discarded=None,
                )
            )
        return out

    def _build_handdata(
        self,
        hand_landmarks: Any,
        handedness_classification: Any | None,
        discarded: str | None,
    ) -> HandData:
        if len(hand_landmarks.landmark) != LANDMARKS_PER_HAND:
            logger.warning(
                'tracking',
                extra={'extras': {
                    'event': 'malformed_hand_discarded',
                    'landmark_count': len(hand_landmarks.landmark),
                }},
            )
            if discarded is None:
                discarded = REASON_MALFORMED_LANDMARKS
            return HandData(
                landmarks=[],
                chirality=None,
                confidence=0.0,
                status=STATUS_DISCARDED,
                status_reason=discarded,
            )
        landmarks: list[tuple[float, float, float]] = [
            (lm.x, lm.y, lm.z) for lm in hand_landmarks.landmark
        ]
        if handedness_classification is None:
            chirality: str | None = None
            confidence = 0.0
        else:
            chirality = handedness_classification.label
            confidence = float(handedness_classification.score)
        if discarded is not None:
            return HandData(
                landmarks=landmarks,
                chirality=chirality,
                confidence=confidence,
                status=STATUS_DISCARDED,
                status_reason=discarded,
            )
        return HandData(
            landmarks=landmarks,
            chirality=chirality,
            confidence=confidence,
            status=STATUS_ACCEPTED,
            status_reason=None,
        )


# Backward-compatible alias. CP-0 migrated call sites from
# `TrackingModule` (the V1.x name) to `TrackingModule` (the V2.0
# intermediate). CP-1 introduces the canonical `HandLandmarker`
# name; both names point to the same class for the rest of V1.
TrackingModule = HandLandmarker

