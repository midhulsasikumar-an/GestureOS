"""Unit tests for ConflictResolver — CP-3.

Per TRD §3.9.1 + PRD §4.6 (FR-CR-01..04):
  - FR-CR-01: single candidate per role -> pass-through
  - FR-CR-02: multiple candidates -> highest-confidence wins
  - FR-CR-03: tied at max confidence -> fixed priority table wins
  - FR-CR-04: independent per hand role
"""

from __future__ import annotations

import pytest

from gestures.conflict_resolver import (
    GESTURE_TIE_BREAK_PRIORITY,
    ConflictResolver,
)
from models.data_models import GestureResult


# ======================================================================
# Constants
# ======================================================================

class TestPriorityTable:
    def test_priority_table_covers_all_static_gestures(self) -> None:
        # All 8 static gestures have a priority entry.
        static_gestures = {
            'open_palm', 'fist', 'pinch', 'thumbs_up',
            'thumbs_down', 'peace_sign', 'three_fingers', 'ok_sign',
        }
        for g in static_gestures:
            assert g in GESTURE_TIE_BREAK_PRIORITY

    def test_priority_table_covers_all_dynamic_gestures(self) -> None:
        dynamic_gestures = {
            'swipe_right', 'swipe_left', 'swipe_up', 'swipe_down',
            'wave', 'circular_motion',
        }
        for g in dynamic_gestures:
            assert g in GESTURE_TIE_BREAK_PRIORITY

    def test_priority_order_pdr(self) -> None:
        # Pin / OK Sign < Thumbs < Peace < Three < Fist < Open Palm.
        # (PRD §4.6 FR-CR-03: fewer-required-extended-fingers wins.)
        assert GESTURE_TIE_BREAK_PRIORITY['pinch'] < GESTURE_TIE_BREAK_PRIORITY['thumbs_up']
        assert GESTURE_TIE_BREAK_PRIORITY['thumbs_up'] < GESTURE_TIE_BREAK_PRIORITY['peace_sign']
        assert GESTURE_TIE_BREAK_PRIORITY['peace_sign'] < GESTURE_TIE_BREAK_PRIORITY['three_fingers']
        assert GESTURE_TIE_BREAK_PRIORITY['three_fingers'] < GESTURE_TIE_BREAK_PRIORITY['open_palm']


# ======================================================================
# FR-CR-01: single candidate pass-through
# ======================================================================

class TestPassThrough:
    def test_single_candidate_passes_through_unchanged(self) -> None:
        resolver = ConflictResolver()
        candidate = GestureResult(
            gesture_name='open_palm',
            confidence=0.90,
            is_dynamic=False,
            hand_role='HAND_A',
            timestamp=0.0,
        )
        winners = resolver.resolve([candidate])
        assert len(winners) == 1
        assert winners[0] is candidate

    def test_empty_input_returns_empty(self) -> None:
        resolver = ConflictResolver()
        assert resolver.resolve([]) == []


# ======================================================================
# FR-CR-02: highest-confidence wins
# ======================================================================

class TestHighestConfidenceWins:
    def test_higher_confidence_wins(self) -> None:
        resolver = ConflictResolver()
        candidates = [
            GestureResult(
                gesture_name='peace_sign',
                confidence=0.81,
                is_dynamic=False,
                hand_role='HAND_A',
                timestamp=0.0,
            ),
            GestureResult(
                gesture_name='three_fingers',
                confidence=0.88,
                is_dynamic=False,
                hand_role='HAND_A',
                timestamp=0.0,
            ),
        ]
        winners = resolver.resolve(candidates)
        assert len(winners) == 1
        assert winners[0].gesture_name == 'three_fingers'

    def test_three_candidates_highest_wins(self) -> None:
        resolver = ConflictResolver()
        candidates = [
            GestureResult('open_palm', 0.70, False, 'HAND_A', 0.0),
            GestureResult('peace_sign', 0.85, False, 'HAND_A', 0.0),
            GestureResult('three_fingers', 0.80, False, 'HAND_A', 0.0),
        ]
        winners = resolver.resolve(candidates)
        assert winners[0].gesture_name == 'peace_sign'


# ======================================================================
# FR-CR-03: tie-break by priority table
# ======================================================================

class TestTieBreakByPriority:
    def test_tied_pinch_vs_peace_sign(self) -> None:
        # Pinch (priority 0) beats Peace Sign (priority 2) at equal confidence.
        resolver = ConflictResolver()
        candidates = [
            GestureResult('peace_sign', 0.85, False, 'HAND_A', 0.0),
            GestureResult('pinch', 0.85, False, 'HAND_A', 0.0),
        ]
        winners = resolver.resolve(candidates)
        assert winners[0].gesture_name == 'pinch'

    def test_tied_thumbs_up_vs_open_palm(self) -> None:
        # Thumbs Up (priority 1) beats Open Palm (priority 5) at equal confidence.
        resolver = ConflictResolver()
        candidates = [
            GestureResult('open_palm', 0.90, False, 'HAND_A', 0.0),
            GestureResult('thumbs_up', 0.90, False, 'HAND_A', 0.0),
        ]
        winners = resolver.resolve(candidates)
        assert winners[0].gesture_name == 'thumbs_up'

    def test_three_way_tie_breaks_by_priority(self) -> None:
        resolver = ConflictResolver()
        candidates = [
            GestureResult('open_palm', 0.85, False, 'HAND_A', 0.0),
            GestureResult('three_fingers', 0.85, False, 'HAND_A', 0.0),
            GestureResult('peace_sign', 0.85, False, 'HAND_A', 0.0),
        ]
        winners = resolver.resolve(candidates)
        # peace_sign (priority 2) < three_fingers (3) < open_palm (5)
        assert winners[0].gesture_name == 'peace_sign'

    def test_tie_with_no_priority_entry_uses_default(self) -> None:
        # A gesture name not in the priority table gets default
        # priority 99 (last resort).
        resolver = ConflictResolver()
        candidates = [
            GestureResult('unknown_gesture', 0.85, False, 'HAND_A', 0.0),
            GestureResult('pinch', 0.85, False, 'HAND_A', 0.0),
        ]
        winners = resolver.resolve(candidates)
        assert winners[0].gesture_name == 'pinch'


# ======================================================================
# FR-CR-04: per-role independence
# ======================================================================

class TestPerRoleIndependence:
    def test_two_hands_resolved_independently(self) -> None:
        # HAND_A: pinch wins (high confidence)
        # HAND_B: open_palm wins (high confidence)
        # They must NOT affect each other.
        resolver = ConflictResolver()
        candidates = [
            GestureResult('pinch', 0.90, False, 'HAND_A', 0.0),
            GestureResult('three_fingers', 0.80, False, 'HAND_A', 0.0),
            GestureResult('open_palm', 0.85, False, 'HAND_B', 0.0),
            GestureResult('peace_sign', 0.70, False, 'HAND_B', 0.0),
        ]
        winners = resolver.resolve(candidates)
        assert len(winners) == 2
        by_role = {w.hand_role: w.gesture_name for w in winners}
        assert by_role['HAND_A'] == 'pinch'
        assert by_role['HAND_B'] == 'open_palm'

    def test_one_hand_with_multiple_candidates(self) -> None:
        # Only HAND_A has multiple candidates; HAND_B has none.
        resolver = ConflictResolver()
        candidates = [
            GestureResult('pinch', 0.85, False, 'HAND_A', 0.0),
            GestureResult('three_fingers', 0.85, False, 'HAND_A', 0.0),
        ]
        winners = resolver.resolve(candidates)
        assert len(winners) == 1
        assert winners[0].hand_role == 'HAND_A'

    def test_hand_a_high_conf_does_not_affect_hand_b(self) -> None:
        # FR-CR-04 explicit: a conflict on one hand never affects the
        # other hand. Verify by constructing two completely independent
        # role sets.
        resolver = ConflictResolver()
        candidates_a = [
            GestureResult('open_palm', 0.90, False, 'HAND_A', 0.0),
            GestureResult('fist', 0.92, False, 'HAND_A', 0.0),
        ]
        candidates_b = [
            GestureResult('peace_sign', 0.70, False, 'HAND_B', 0.0),
        ]
        winners = resolver.resolve(candidates_a + candidates_b)
        assert len(winners) == 2
        by_role = {w.hand_role: w.gesture_name for w in winners}
        # HAND_A: fist wins (0.92 > 0.90)
        assert by_role['HAND_A'] == 'fist'
        # HAND_B: peace_sign passes through (only candidate)
        assert by_role['HAND_B'] == 'peace_sign'


# ======================================================================
# PRD §4.6 worked example (TRD §3.9.2)
# ======================================================================

class TestTrdWorkedExample:
    def test_prd_worked_example(self) -> None:
        """PRD §4.6: peace_sign 0.81 vs three_fingers 0.88 -> three_fingers
        wins (higher confidence, no tie)."""
        resolver = ConflictResolver()
        candidates = [
            GestureResult(
                gesture_name='peace_sign',
                confidence=0.81,
                is_dynamic=False,
                hand_role='HAND_A',
                timestamp=0.0,
            ),
            GestureResult(
                gesture_name='three_fingers',
                confidence=0.88,
                is_dynamic=False,
                hand_role='HAND_A',
                timestamp=0.0,
            ),
        ]
        winners = resolver.resolve(candidates)
        assert winners == [candidates[1]]  # the three_fingers one


# ======================================================================
# Hot-path-never-raises (RULES §6.4)
# ======================================================================

class TestHotPathNeverRaises:
    def test_malformed_candidate_dropped(self) -> None:
        # A candidate with hand_role == '' is dropped with a warning,
        # never propagates an exception.
        resolver = ConflictResolver()
        candidates = [
            GestureResult('pinch', 0.85, False, '', 0.0),  # empty role
            GestureResult('peace_sign', 0.80, False, 'HAND_A', 0.0),
        ]
        winners = resolver.resolve(candidates)
        assert len(winners) == 1
        assert winners[0].gesture_name == 'peace_sign'