"""Hand landmark detection via MediaPipe Hands.

Implements TRD §3.3 (TrackingModule).  Wraps `mediapipe.solutions.hands`,
converts frames to RGB, runs inference, and builds `list[HandData]`
objects with chirality and confidence populated.

At Checkpoint 1 this module does NOT populate `role`, `scale`, or
`gesture_eligible` — those are Checkpoint 2's responsibility (HandIdentityModule,
HandScaleEstimator, PrimaryHandFilter respectively, per Implementation Plan §6).

RULES §2.4: tracking/ does not import from recognizer, conflict_resolver,
or executor.

Tracking-quality tuning notes:
  - ``model_complexity`` is set to 1. This is the heavier MediaPipe
    Hands graph; at ≤2 hands and 1280×720 it absorbs the additional
    CPU cost and retains tracking more reliably through partial
    occlusion and wrist rotation. The CP-1 setting of 0 was
    intentional for latency, but the per-hand accuracy gain from 1
    outweighs the per-frame cost on the reference hardware (CP-4
    Tracking Stabilization pass).
  - ``min_tracking_confidence`` is 0.4 (vs MediaPipe's default 0.5)
    so the tracker keeps a hand through moderate rotation / partial
    finger closure instead of dropping it and forcing a full
    re-detection pass.
  - ``min_detection_confidence`` stays at 0.5 — too low and we accept
    false-positive hands; too high and we miss hands at frame edges.
  - Re-init threshold bumped from 3 to 5 consecutive exceptions.
    Brief driver-level stalls should not force a MediaPipe rebuild;
    only persistent failures trigger the recovery path.
  - Handedness-mismatch path (CP-4): when MediaPipe returns valid
    landmarks but no/insufficient handedness metadata, the previous
    implementation discarded the entire frame's detections. We now
    emit each hand with ``chirality=None`` and a ``discarded``
    status flag so the operator can see the cause. Downstream
    stages (HandIdentityModule, OcclusionHandler, HandScaleEstimator,
    PrimaryHandFilter) all already tolerate ``chirality=None``.
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
# 1 = heavier, more accurate graph. At ≤2 hands and 1280×720 the
# additional CPU cost is acceptable and the per-hand tracking
# reliability gain (under partial occlusion / wrist rotation) is
# worth it. The MediaPipe-documented default is also 1; CP-1 had
# overridden this to 0 for latency. CP-4 Tracking Stabilization
# restored the default.
MODEL_COMPLEXITY: int = 1
MIN_DETECTION_CONFIDENCE: float = 0.5
# Lower than MediaPipe's default (0.5) to keep tracking through rotation.
MIN_TRACKING_CONFIDENCE: float = 0.4
LANDMARKS_PER_HAND: int = 21
# Number of consecutive MediaPipe exceptions before we attempt re-init.
# Five frames at 30 FPS is ~167 ms of "missing", which is enough to
# distinguish a real stall from a transient driver glitch.
REINIT_AFTER_CONSECUTIVE_ERRORS: int = 5

# Status enum values used on `HandData.status` (CP-4 Tracking Stabilization).
# Kept here as the canonical source of truth; the debug panel and
# tracking tests import these constants.
STATUS_ACCEPTED: str = 'accepted'
STATUS_RETAINED: str = 'retained'
STATUS_FILTERED: str = 'filtered'
STATUS_DISCARDED: str = 'discarded'

# Status reason strings for diagnostic logs and the Developer Mode panel.
# Reason is `None` for 'accepted' hands.
REASON_HANDEDNESS_MISSING: str = 'handedness_missing'
REASON_MALFORMED_LANDMARKS: str = 'malformed_landmarks'
REASON_DOMINANT_HAND_MODE: str = 'dominant_hand_mode'
REASON_OCCLUSION_BRIDGE: str = 'occlusion_bridge'


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

        if results.multi_hand_landmarks is None:
            return []

        # CP-4 Tracking Stabilization: when handedness metadata is
        # missing or has a different count than the landmarks list,
        # we DO NOT drop the entire frame. Instead we iterate the
        # landmarks list and emit each hand with chirality=None and
        # confidence=0.0; downstream stages (HandIdentityModule,
        # OcclusionHandler, HandScaleEstimator, PrimaryHandFilter)
        # all tolerate chirality=None. The event is logged at WARN
        # level so future debug can attribute the loss.
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
            # Mismatch — emit the landmark-bearing hands with
            # chirality=None for any index past the shorter list. The
            # shorter list dictates how many we have full metadata for.
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
            # Any landmarks past the shorter list are emitted with
            # chirality=None.
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
        """Construct a HandData from one MediaPipe detection.

        Encapsulates the malformed-hand defensive path and the
        handedness-missing fallback. `discarded` is the reason
        string (matches `REASON_HANDEDNESS_MISSING` /
        `REASON_MALFORMED_LANDMARKS`) or `None` for a fully
        valid hand.

        CP-4: this method is the single point that populates the
        new `status` and `status_reason` fields. Every hand that
        leaves `detect()` has a non-empty `status` and an
        explanatory `status_reason` when the status is not
        `accepted`.
        """
        # Defensive: discard malformed hands. CP-1's `malformed_hand_discarded`
        # log event is preserved.
        if len(hand_landmarks.landmark) != LANDMARKS_PER_HAND:
            logger.warning(
                'tracking',
                extra={'extras': {
                    'event': 'malformed_hand_discarded',
                    'landmark_count': len(hand_landmarks.landmark),
                }},
            )
            # We still emit a HandData so the debug panel can show the
            # status, but with empty landmarks. This matches the spirit
            # of "don't silently drop" while not breaking the
            # `landmarks` length invariant downstream.
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
            chirality = handedness_classification.label  # 'Left' or 'Right'
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