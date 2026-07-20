"""StaticGestureEngine — Checkpoint 3 / V2.0 rename of GestureEngine.

Implements TRD §3.9 (GestureEngine), PRD §4.6 (Candidate
Generation stage), and TRD §8 (Google MediaPipe Gesture Recognizer
integration).

CP-3: the engine runs the MediaPipe Gesture Recognizer (via
``ModelManager.recognize_gesture()``) alongside the custom geometric
recognizers for every eligible hand.  Candidates from both sources
are returned in a single list and disambiguated by ``GestureFuser``.

V2.0: this module replaces `gesture_engine.py`. The class is renamed
to `StaticGestureEngine` to distinguish it from the future
`DynamicGestureEngine` (CP-6+). All behavior from V1.x is preserved;
no logic has changed.

The engine evaluates every registered rule (8 static + 6 dynamic +
MediaPipe ML) on the per-frame input and returns ALL qualifying
candidates. Selection between competing candidates is the job of
``GestureFuser`` (formerly ``ConflictResolver``).
"""

from __future__ import annotations

import logging
from typing import Any

from gestures.dynamic_recognizer import DYNAMIC_GESTURE_RULES
from gestures.motion_history_service import MotionHistoryService
from gestures.static_recognizer import STATIC_GESTURE_RULES
from models.data_models import GestureResult, HandData
from settings.settings_manager import Settings


logger = logging.getLogger('gestureos')


class StaticGestureEngine:
    """Per-frame gesture candidate generation.

    CP-3: accepts an optional ``ModelManager`` reference.  When
    provided, ``evaluate()`` runs the MediaPipe Gesture Recognizer
    alongside the custom geometric recognizers.  When ``None``
    (backward-compatible default), only the custom recognizers are
    used.

    V2.0 rename of GestureEngine. Handles both static and dynamic
    rule evaluation. The dynamic recognizer integration will be
    split into DynamicGestureEngine in a future checkpoint.
    """

    def __init__(
        self,
        settings: Settings,
        model_manager: Any | None = None,
    ) -> None:
        self.settings = settings
        self.model_manager = model_manager
        self.motion_history = MotionHistoryService(
            max_frames=settings.motion_history_frames,
        )

    def update_motion_history(self, hands: list[HandData], now: float) -> None:
        for hand in hands:
            if hand.role is None:
                continue
            if not hand.landmarks:
                continue
            self.motion_history.update(hand.role, hand.landmarks[0], now)

    def evaluate(
        self,
        hands: list[HandData],
        now: float,
    ) -> list[GestureResult]:
        try:
            return self._evaluate_impl(hands, now)
        except Exception as exc:
            logger.error(
                'static_gesture_engine',
                extra={'extras': {
                    'event': 'evaluate_failed',
                    'hand_count': len(hands),
                    'error': str(exc),
                }},
            )
            return []

    def _evaluate_impl(
        self,
        hands: list[HandData],
        now: float,
    ) -> list[GestureResult]:
        candidates: list[GestureResult] = []
        for hand in hands:
            if not hand.gesture_eligible:
                continue
            hand_candidates = self._check_all_static(hand, now)
            hand_candidates.extend(self._check_all_dynamic(hand, now))
            # CP-3: MediaPipe Gesture Recognizer integration (TRD §8).
            # Runs alongside the custom recognizers; candidates from
            # both sources are disambiguated downstream by GestureFuser.
            mp_result = self._check_mediapipe(hand)
            if mp_result is not None:
                hand_candidates.append(mp_result)
            candidates.extend(hand_candidates)
        threshold = self.settings.gesture_confidence_threshold
        qualifying = [c for c in candidates if c.confidence >= threshold]
        if candidates:
            logger.debug(
                'static_gesture_engine',
                extra={'extras': {
                    'event': 'candidates_evaluated',
                    'total': len(candidates),
                    'qualifying': len(qualifying),
                    'hand_count': len(hands),
                }},
            )
        return qualifying

    def _check_all_static(
        self,
        hand: HandData,
        now: float,
    ) -> list[GestureResult]:
        results: list[GestureResult] = []
        for detect_fn in STATIC_GESTURE_RULES:
            try:
                result = detect_fn(hand)
            except Exception as exc:
                logger.error(
                    'static_gesture_engine',
                    extra={'extras': {
                        'event': 'static_recognizer_error',
                        'recognizer': detect_fn.__name__,
                        'error': str(exc),
                    }},
                )
                continue
            if result is not None:
                results.append(result)
        return results

    def _check_mediapipe(
        self,
        hand: HandData,
    ) -> GestureResult | None:
        """Run the MediaPipe Gesture Recognizer on one hand.

        Returns a ``GestureResult`` with the ML-recognised gesture
        (tagged with the hand's role and ``source='mediapipe'``), or
        ``None`` when the model is not available, inference fails,
        or no gesture is recognised.

        The result's ``hand_role`` is set to the detected hand's role
        so that ``GestureFuser`` can group candidates per role.
        """
        if self.model_manager is None:
            return None
        try:
            result = self.model_manager.recognize_gesture(hand.landmarks)
        except Exception:  # noqa: BLE001 — hot-path defensive
            logger.error(
                'static_gesture_engine',
                extra={'extras': {
                    'event': 'mediapipe_recognizer_error',
                    'role': hand.role,
                }},
            )
            return None
        if result is None:
            return None
        # Tag with the hand's role so GestureFuser can group by role.
        result.hand_role = hand.role if hand.role is not None else ''
        return result

    def _check_all_dynamic(
        self,
        hand: HandData,
        now: float,
    ) -> list[GestureResult]:
        if hand.role is None:
            return []
        buffer = self.motion_history.get(hand.role)
        if len(buffer) < 2:
            return []
        hand_scale = float(hand.scale.smoothed_scale) if hand.scale is not None else 0.0
        results: list[GestureResult] = []
        for detect_fn in DYNAMIC_GESTURE_RULES:
            try:
                result = detect_fn(buffer, hand_scale)
            except Exception as exc:
                logger.error(
                    'static_gesture_engine',
                    extra={'extras': {
                        'event': 'dynamic_recognizer_error',
                        'recognizer': detect_fn.__name__,
                        'error': str(exc),
                    }},
                )
                continue
            if result is not None:
                result.hand_role = hand.role
                results.append(result)
        return results
