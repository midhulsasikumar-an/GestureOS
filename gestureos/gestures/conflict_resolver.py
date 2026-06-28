"""ConflictResolver — per-role winner selection from gesture candidates.

Implements TRD §3.9.1 and PRD §4.6 (Conflict Resolution stage).

Resolves multiple candidates for the same hand role in the same frame
to a single winner using:

  - FR-CR-01: pass-through when only one candidate exists
  - FR-CR-02: highest-confidence wins when multiple candidates exist
  - FR-CR-03: fixed-priority tie-break when multiple candidates are
    tied at the same confidence (fewer-required-extended-fingers
    gestures are more geometrically specific and preferred)
  - FR-CR-04: operates independently per hand role

RULES §2.7: `ConflictResolver` does not perform gesture recognition
or call OS APIs. It operates purely on pre-classified `GestureResult`
objects produced by `GestureEngine`.

RULES §4.7 (ConflictResolver input immutability): inputs are treated
as read-only. The resolver returns a new list and never mutates
either the input list or any `GestureResult` it contains.

RULES §6.4: hot-path — never raises; defensive try/except returns the
input list unchanged on internal error.

RULES §6.8: even single-candidate frames pass through this resolver
(no single-signal shortcut). All signals flow through the resolver's
decision path.
"""

from __future__ import annotations

import logging
from typing import Iterable

from models.data_models import GestureResult


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.9.2 / PRD §4.6 FR-CR-03)
# ---------------------------------------------------------------------------

#: Fixed tie-break priority table (PRD §4.6 FR-CR-03, TRD §3.9.2):
#: "gestures requiring fewer extended fingers are more geometrically
#: specific and preferred over more general poses." Lower number =
#: higher priority (wins in a tie).
GESTURE_TIE_BREAK_PRIORITY: dict[str, int] = {
    # 0-1 fingers involved in the defining check
    'pinch': 0,
    'ok_sign': 0,
    # 1 finger extended
    'thumbs_up': 1,
    'thumbs_down': 1,
    # 2 fingers extended
    'peace_sign': 2,
    # 3 fingers extended
    'three_fingers': 3,
    # 4-5 fingers extended — most general, lowest priority
    'fist': 4,
    'open_palm': 5,
    # Dynamic gestures: lower priority than any static gesture because
    # they are inherently multi-frame and have a longer physical
    # motion (the user is more likely to intend them as deliberate
    # actions rather than transitional false positives).
    'wave': 6,
    'circular_motion': 7,
    'swipe_right': 8,
    'swipe_left': 8,
    'swipe_up': 8,
    'swipe_down': 8,
}
"""Fixed tie-break priority table. Lower number wins.

The values are not exposed to configuration because PRD §4.6
specifies the priority order is "documented in the TRD and is not
configurable per-profile, to keep conflict outcomes predictable and
testable" (FR-CR-03)."""


class ConflictResolver:
    """Per-role winner selection from a list of `GestureResult` candidates.

    Stateless: the resolver holds no per-frame state, so the same
    instance can be reused across frames without resetting anything.
    The tie-break priority table is class-level (immutable).
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        candidates: Iterable[GestureResult],
    ) -> list[GestureResult]:
        """Select a single winner per hand role.

        Args:
            candidates: per-frame candidates produced by
                `GestureEngine.evaluate()`. May be empty. May contain
                multiple candidates per role.

        Returns:
            A new list containing at most one `GestureResult` per
            hand role. The input list and its `GestureResult` objects
            are not mutated (RULES §4.7).
        """
        try:
            return self._resolve_impl(list(candidates))
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'conflict_resolver',
                extra={'extras': {
                    'event': 'resolve_failed',
                    'input_count': len(list(candidates)) if candidates else 0,
                    'error': str(exc),
                }},
            )
            return list(candidates) if candidates else []

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _resolve_impl(
        self,
        candidates: list[GestureResult],
    ) -> list[GestureResult]:
        if not candidates:
            return []

        # Step 1: group by hand_role. Candidates with `hand_role == ''`
        # are dropped — they are malformed (a recognizer that failed
        # to set its role; this should never happen in normal flow).
        by_role: dict[str, list[GestureResult]] = {}
        for c in candidates:
            role = c.hand_role
            if not role:
                logger.warning(
                    'conflict_resolver',
                    extra={'extras': {
                        'event': 'candidate_without_role_dropped',
                        'gesture_name': c.gesture_name,
                    }},
                )
                continue
            by_role.setdefault(role, []).append(c)

        # Step 2: per-role resolution (FR-CR-04: independent per role).
        winners: list[GestureResult] = []
        for role, role_candidates in by_role.items():
            winners.append(self._resolve_one_role(role, role_candidates))

        return winners

    def _resolve_one_role(
        self,
        role: str,
        role_candidates: list[GestureResult],
    ) -> GestureResult:
        """Resolve conflicts for a single hand role.

        Implements FR-CR-01 (single candidate pass-through),
        FR-CR-02 (highest-confidence wins), and FR-CR-03 (priority
        tie-break).
        """
        if len(role_candidates) == 1:
            return role_candidates[0]  # FR-CR-01: pass-through

        # FR-CR-02: strictly-highest confidence wins.
        max_confidence = max(c.confidence for c in role_candidates)
        tied = [c for c in role_candidates if c.confidence == max_confidence]
        if len(tied) == 1:
            return tied[0]

        # FR-CR-03: tied at max confidence — apply the priority table.
        # Sort by (priority, gesture_name) for determinism. Lower
        # priority number wins; ties on priority are broken by
        # gesture_name alphabetical order (deterministic but
        # arbitrary — both tied candidates are equally valid).
        tied.sort(
            key=lambda c: (
                GESTURE_TIE_BREAK_PRIORITY.get(c.gesture_name, 99),
                c.gesture_name,
            )
        )

        winner = tied[0]
        if len(tied) > 1:
            # Log the tie-break for observability (one log line per
            # affected role per frame; usually empty in practice).
            logger.debug(
                'conflict_resolver',
                extra={'extras': {
                    'event': 'tied_confidence_tie_break',
                    'role': role,
                    'winner': winner.gesture_name,
                    'losers': [c.gesture_name for c in tied[1:]],
                    'confidence': winner.confidence,
                }},
            )
        return winner