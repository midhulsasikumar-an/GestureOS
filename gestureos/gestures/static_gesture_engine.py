"""StaticGestureEngine — Checkpoint 3 / V2.0 rename of GestureEngine.

Implements TRD §3.9 (GestureEngine) and PRD §4.6 (Candidate
Generation stage).

V2.0: this module replaces `gesture_engine.py`. The class is renamed
to `StaticGestureEngine` to distinguish it from the future
`DynamicGestureEngine` (CP-6+). All behavior from V1.x is preserved;
no logic has changed.

The engine evaluates every registered rule (8 static + 6 dynamic) on
the per-frame input and returns ALL qualifying candidates. Selection
between competing candidates is the job of `GestureFuser`
(formerly `ConflictResolver`).
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from gestures.dynamic_recognizer import DYNAMIC_GESTURE_RULES
from gestures.motion_history_service import MotionHistoryService
from gestures.static_recognizer import STATIC_GESTURE_RULES
from models.data_models import GestureResult, HandData
from settings.settings_manager import Settings


logger = logging.getLogger('gestureos')


class StaticGestureEngine:
    """Per-frame gesture candidate generation.

    V2.0 rename of GestureEngine. Handles both static and dynamic
    rule evaluation. The dynamic recognizer integration will be
    split into DynamicGestureEngine in a future checkpoint.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
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
