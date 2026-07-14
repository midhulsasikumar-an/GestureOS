"""GestureFuser — per-role winner selection from gesture candidates.

V2.0 rename of ConflictResolver. Implements TRD §3.9.1 and PRD §4.6
(Conflict Resolution stage).

V2.0: the class is renamed to `GestureFuser`. All behavior from V1.x
is preserved (pass-through mode). The fuser resolves multiple
candidates for the same hand role to a single winner using:
  - FR-CR-01: pass-through when only one candidate exists
  - FR-CR-02: highest-confidence wins
  - FR-CR-03: fixed-priority tie-break
  - FR-CR-04: operates independently per hand role

CP-3 Gesture Fusion Priority (TRD §3.9.2):
  - MediaPipe results with confidence ≥ MEDIAPIPE_WIN_CONFIDENCE win
    unconditionally over custom recognizers for that role.
  - MediaPipe results below the threshold are removed from
    consideration (custom recognizers compete instead).
  - Same-gesture duplicates are eliminated (MP survives when
    confident, is removed otherwise).
"""

from __future__ import annotations

import logging
from typing import Iterable

from models.data_models import GestureResult


logger = logging.getLogger('gestureos')


#: CP-3 Gesture Fusion Priority: confidence threshold at which a
#: MediaPipe Gesture Recognizer candidate wins unconditionally over
#: all custom geometric recognizers for the same hand role.
#: Below this threshold the MediaPipe candidate is removed and custom
#: recognizers compete normally (TRD §3.9.2).
MEDIAPIPE_WIN_CONFIDENCE: float = 0.80

GESTURE_TIE_BREAK_PRIORITY: dict[str, int] = {
    'pinch': 0,
    'ok_sign': 0,
    'thumbs_up': 1,
    'thumbs_down': 1,
    'peace_sign': 2,
    'three_fingers': 3,
    'fist': 4,
    'open_palm': 5,
    'wave': 6,
    'circular_motion': 7,
    'swipe_right': 8,
    'swipe_left': 8,
    'swipe_up': 8,
    'swipe_down': 8,
}


class GestureFuser:
    """Per-role winner selection from a list of GestureResult candidates.

    V2.0 rename of ConflictResolver. Stateless: the fuser holds no
    per-frame state.

    CP-3: ``_resolve_one_role()`` applies the MediaPipe Fusion Priority
    rules before falling back to confidence + tie-break.
    """

    def resolve(
        self,
        candidates: Iterable[GestureResult],
    ) -> list[GestureResult]:
        try:
            return self._resolve_impl(list(candidates))
        except Exception as exc:
            logger.error(
                'gesture_fuser',
                extra={'extras': {
                    'event': 'resolve_failed',
                    'input_count': len(list(candidates)) if candidates else 0,
                    'error': str(exc),
                }},
            )
            return list(candidates) if candidates else []

    def _resolve_impl(
        self,
        candidates: list[GestureResult],
    ) -> list[GestureResult]:
        if not candidates:
            return []
        by_role: dict[str, list[GestureResult]] = {}
        for c in candidates:
            role = c.hand_role
            if not role:
                logger.warning(
                    'gesture_fuser',
                    extra={'extras': {
                        'event': 'candidate_without_role_dropped',
                        'gesture_name': c.gesture_name,
                    }},
                )
                continue
            by_role.setdefault(role, []).append(c)
        winners: list[GestureResult] = []
        for role, role_candidates in by_role.items():
            winners.append(self._resolve_one_role(role, role_candidates))
        return winners

    def _resolve_one_role(
        self,
        role: str,
        role_candidates: list[GestureResult],
    ) -> GestureResult:
        # CP-3 Gesture Fusion Priority (TRD §3.9.2):
        # ---------------------------------------------------------------
        # 1. If a MediaPipe candidate has confidence >=
        #    MEDIAPIPE_WIN_CONFIDENCE (0.80), it wins unconditionally
        #    over all custom candidates for this role.
        # 2. If MediaPipe exists but confidence < threshold, remove
        #    the MediaPipe candidate from consideration and let the
        #    custom recognizers compete among themselves.
        # 3. If no custom candidates remain after removal, return the
        #    MediaPipe result as a fallback.
        mp_candidates = [
            c for c in role_candidates
            if getattr(c, 'source', '') == 'mediapipe'
        ]
        if mp_candidates:
            mp = mp_candidates[0]
            if mp.confidence >= MEDIAPIPE_WIN_CONFIDENCE:
                return mp
            # Low-confidence MP: remove from consideration.
            remaining = [
                c for c in role_candidates
                if c.source != 'mediapipe'
            ]
            if not remaining:
                return mp  # fallback
            role_candidates = remaining

        # Original resolution among (custom-only) candidates.
        if len(role_candidates) == 1:
            return role_candidates[0]
        max_confidence = max(c.confidence for c in role_candidates)
        tied = [c for c in role_candidates if c.confidence == max_confidence]
        if len(tied) == 1:
            return tied[0]
        tied.sort(
            key=lambda c: (
                GESTURE_TIE_BREAK_PRIORITY.get(c.gesture_name, 99),
                c.gesture_name,
            )
        )
        winner = tied[0]
        if len(tied) > 1:
            logger.debug(
                'gesture_fuser',
                extra={'extras': {
                    'event': 'tied_confidence_tie_break',
                    'role': role,
                    'winner': winner.gesture_name,
                    'losers': [c.gesture_name for c in tied[1:]],
                    'confidence': winner.confidence,
                }},
            )
        return winner
