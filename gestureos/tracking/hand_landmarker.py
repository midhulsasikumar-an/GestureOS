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
MediaPipe Hand Landmarker handle is obtained and invoked through
`ModelManager`.
RULES §13.2: the Hand Landmarker is loaded only by `ModelManager`.
The detector below uses `model_manager.process_hand_landmarker()` to
run inference.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from models.data_models import HandData
from tracking.errors import TrackingInitError


logger = logging.getLogger('gestureos')


MAX_NUM_HANDS: int = 2
MIN_DETECTION_CONFIDENCE: float = 0.5
MIN_PRESENCE_CONFIDENCE: float = 0.5
MIN_TRACKING_CONFIDENCE: float = 0.5
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
    import `mediapipe`; it calls `model_manager.process_hand_landmarker()`
    to run inference. RULES §13.2 compliance.

    The public name `TrackingModule` is preserved as a backward-
    compatible alias for tests and call sites that were updated in
    the CP-0 rename but have not yet migrated to the canonical
    `HandLandmarker` name (CP-3 will converge on `HandLandmarker`).
    """

    def __init__(
        self,
        model_manager: Any | None = None,
        max_num_hands: int = MAX_NUM_HANDS,
        min_detection_confidence: float = MIN_DETECTION_CONFIDENCE,
        min_presence_confidence: float = MIN_PRESENCE_CONFIDENCE,
        min_tracking_confidence: float = MIN_TRACKING_CONFIDENCE,
        reinit_after_errors: int = REINIT_AFTER_CONSECUTIVE_ERRORS,
    ) -> None:
        self.model_manager = model_manager
        self.max_num_hands = max_num_hands
        self.min_detection_confidence = min_detection_confidence
        self.min_presence_confidence = min_presence_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.reinit_after_errors = reinit_after_errors
        self._hands: Any = None
        self._consecutive_errors = 0

    def initialize(self) -> None:
        """Forward configuration to ModelManager and prepare for inference.

        Calls ``model_manager.set_hand_landmarker_config()`` with the
        detector's ``max_num_hands`` / ``min_detection_confidence`` /
        ``min_presence_confidence`` / ``min_tracking_confidence`` values,
        then ensures the model is loaded in ``VIDEO`` running mode.

        The actual model handle lives in ModelManager; this method
        only checks availability. Inference is routed through
        ``model_manager.process_hand_landmarker()``.
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

        self._sync_config_to_model_manager()

        if not self.model_manager.is_hand_landmarker_available():
            # Config has been set; attempt to (re)load so the detector
            # runs with the correct parameters.
            if not self.model_manager.load_hand_landmarker():
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

        self._hands = True
        self._consecutive_errors = 0
        logger.info(
            'tracking',
            extra={'extras': {
                'event': 'mediapipe_initialized',
                'max_num_hands': self.max_num_hands,
                'min_detection_confidence': self.min_detection_confidence,
                'min_presence_confidence': self.min_presence_confidence,
                'min_tracking_confidence': self.min_tracking_confidence,
            }},
        )

    def _sync_config_to_model_manager(self) -> None:
        """Forward this detector's config to ModelManager.

        Called from ``initialize()`` so that ``load_hand_landmarker()``
        uses the correct ``num_hands``, detection/presence/tracking
        confidence thresholds instead of hardcoded defaults.
        """
        if self.model_manager is None:
            return
        self.model_manager.set_hand_landmarker_config(
            num_hands=self.max_num_hands,
            min_detection_confidence=self.min_detection_confidence,
            min_presence_confidence=self.min_presence_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
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
        """Release HandLandmarker reference. Idempotent.

        The actual MediaPipe handle is owned and released by
        ModelManager; this method only clears our reference.
        """
        self._hands = None

    def detect(self, rgb_frame: np.ndarray) -> list[HandData]:
        """Run hand detection on an RGB frame.

        Inference is delegated to ``ModelManager.process_hand_landmarker()``
        which converts the frame to ``mp.Image`` and calls the Tasks API
        ``.detect_for_video()`` method with a monotonically increasing
        timestamp (VIDEO running mode for temporal tracking).

        Returns 0–2 `HandData` objects. The old `multi_hand_landmarks` /
        `multi_handedness` (Solutions API) have been replaced with
        ``hand_landmarks`` / ``handedness`` (Tasks API). The result
        shape is equivalent: ``hand_landmarks[i]`` is a list of
        NormalizedLandmark objects, ``handedness[i]`` is a list of
        Classification entries.

        Behaviour is preserved from the last working implementation:
        - If either ``hand_landmarks`` or ``handedness`` is None → []
        - If lengths differ → []
        - Malformed hands (< 21 landmarks) → silently skipped
        """
        if self._hands is None:
            self.initialize()

        if self._hands is None:
            return []

        try:
            results = self.model_manager.process_hand_landmarker(rgb_frame)
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

        if results is None:
            return []

        # Tasks API attributes (not the old Solutions API multi_* names).
        hand_landmarks = getattr(results, 'hand_landmarks', None)
        handedness = getattr(results, 'handedness', None)

        # CP-2 (Tracking Stabilization): when landmarks are present
        # but handedness metadata is missing or length-mismatched, do
        # NOT discard the entire frame (the V1.x behaviour was to
        # `return []`, which produced intermittent "tracked one frame,
        # gone the next" perception). Instead, iterate over the
        # landmarks list and emit each hand with `chirality=None` and
        # `confidence=0.0` so the downstream analysis stages
        # (HandIdentityModule, HandScaleEstimator, PrimaryHandFilter)
        # can still process the frame. The event is logged at WARN
        # with the per-list counts so future debugging can attribute
        # the loss to MediaPipe's metadata path rather than to a
        # missing hand.
        if hand_landmarks is None:
            # Genuine no-hand case: nothing to emit.
            return []

        n_landmarks = len(hand_landmarks)
        n_handedness = len(handedness) if handedness is not None else 0

        if handedness is None or n_handedness != n_landmarks:
            logger.warning(
                'tracking',
                extra={'extras': {
                    'event': 'mediapipe_hand_count_mismatch',
                    'landmarks_count': n_landmarks,
                    'handedness_count': n_handedness,
                    'chirality_will_be': 'None',
                }},
            )
            # Build a fallback handedness list of the same length as
            # `hand_landmarks` so the per-hand pass can iterate
            # uniformly. Each entry is `(None, 0.0)` — see loop body.
            handedness_iter: list[tuple[str | None, float]] = [
                (None, 0.0)
            ] * n_landmarks
        else:
            handedness_iter = [
                (hd[0].category_name, float(hd[0].score))
                for hd in handedness
            ]

        out: list[HandData] = []
        for hl, (chirality, confidence) in zip(hand_landmarks, handedness_iter):
            # Skip malformed hands (preserved V1.x behaviour: emit nothing
            # for hands with ≠21 landmarks).
            if len(hl) != LANDMARKS_PER_HAND:
                logger.warning(
                    'tracking',
                    extra={'extras': {
                        'event': 'malformed_hand_discarded',
                        'landmark_count': len(hl),
                    }},
                )
                continue

            landmarks: list[tuple[float, float, float]] = [
                (lm.x, lm.y, lm.z) for lm in hl
            ]

            # CP-2 (Tracking Stabilization): populate the per-hand
            # `status` / `status_reason` / `tracking_confidence` fields
            # on every emitted hand.  `tracking_confidence` is left as
            # `None` because MediaPipe 0.10.14's Tasks API does not
            # surface a separate per-hand tracking score (the
            # `handedness[i][0].score` is the only score returned and
            # it carries presence + handedness combined). The
            # `status`/`status_reason` fields are populated here
            # (`accepted`) and may be overwritten by downstream
            # analysis stages (OcclusionHandler, PrimaryHandFilter).
            # `chirality` may legitimately be `None` (handedness-
            # missing path); `confidence` is `0.0` in that case to
            # reflect the absence of a real score.
            out.append(
                HandData(
                    landmarks=landmarks,
                    chirality=chirality,  # 'Left' | 'Right' | None (handedness-missing path)
                    confidence=confidence,
                    tracking_confidence=None,
                    status=STATUS_ACCEPTED,
                    status_reason=None,
                )
            )

        return out


# Backward-compatible alias. CP-0 migrated call sites from
# `TrackingModule` (the V1.x name) to `TrackingModule` (the V2.0
# intermediate). CP-1 introduces the canonical `HandLandmarker`
# name; both names point to the same class for the rest of V1.
TrackingModule = HandLandmarker
