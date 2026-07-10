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
"""

from __future__ import annotations

import logging
from typing import Iterable

from models.data_models import GestureResult


logger = logging.getLogger('gestureos')


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
