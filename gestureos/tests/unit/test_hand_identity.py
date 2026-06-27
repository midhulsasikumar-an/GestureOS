"""Unit tests for HandIdentityModule — CP-2.

Per TRD §13.2 / Implementation Plan §6: no live camera required.
Tests feed synthetic HandData lists through `assign_roles()` and
verify role persistence, the 2-second re-identification window, the
proximity threshold, the chirality-fallback tie-break, and the
"too many hands" truncation behaviour.
"""

from __future__ import annotations

import pytest

from tracking.hand_identity import (
    MATCH_THRESHOLD,
    MAX_ROLES,
    REID_WINDOW_S,
    ROLE_A,
    ROLE_B,
    HandIdentityModule,
)

from tests.conftest import make_hand_for_pose, make_wrist_only_hand


# ======================================================================
# Construction
# ======================================================================

class TestConstruction:
    def test_default_constants(self) -> None:
        m = HandIdentityModule()
        assert m.reid_window_s == REID_WINDOW_S == 2.0
        assert m.match_threshold == MATCH_THRESHOLD == 0.15
        assert m.max_roles == MAX_ROLES == 2

    def test_custom_constants(self) -> None:
        m = HandIdentityModule(reid_window_s=1.0, match_threshold=0.2, max_roles=3)
        assert m.reid_window_s == 1.0
        assert m.match_threshold == 0.2
        assert m.max_roles == 3

    def test_remembered_roles_starts_empty(self) -> None:
        assert HandIdentityModule().remembered_roles == {}


# ======================================================================
# Basic role assignment
# ======================================================================

class TestBasicAssignment:
    def test_two_hands_get_distinct_roles(self) -> None:
        m = HandIdentityModule()
        out = m.assign_roles(
            [
                make_wrist_only_hand((0.2, 0.5), chirality='Left'),
                make_wrist_only_hand((0.8, 0.5), chirality='Right'),
            ],
            now=0.0,
        )
        assert {h.role for h in out} == {ROLE_A, ROLE_B}

    def test_single_hand_gets_role_a(self) -> None:
        m = HandIdentityModule()
        out = m.assign_roles(
            [make_wrist_only_hand((0.5, 0.5), chirality='Right')],
            now=0.0,
        )
        assert len(out) == 1
        assert out[0].role == ROLE_A

    def test_empty_input_returns_empty(self) -> None:
        m = HandIdentityModule()
        assert m.assign_roles([], now=0.0) == []

    def test_output_does_not_mutate_input(self) -> None:
        m = HandIdentityModule()
        original = [
            make_wrist_only_hand((0.2, 0.5), chirality='Left'),
        ]
        original_role = original[0].role
        m.assign_roles(original, now=0.0)
        assert original[0].role == original_role  # input role unchanged


# ======================================================================
# Roles preserved across frames (proximity matching)
# ======================================================================

class TestProximityMatching:
    def test_same_hands_next_frame_keep_roles(self) -> None:
        m = HandIdentityModule()
        f1 = [
            make_wrist_only_hand((0.2, 0.5), chirality='Left'),
            make_wrist_only_hand((0.8, 0.5), chirality='Right'),
        ]
        out1 = m.assign_roles(f1, now=0.0)
        left_role = next(h.role for h in out1 if h.chirality == 'Left')
        right_role = next(h.role for h in out1 if h.chirality == 'Right')

        # Frame 2: same hands, slightly shifted (within MATCH_THRESHOLD)
        f2 = [
            make_wrist_only_hand((0.21, 0.5), chirality='Left'),
            make_wrist_only_hand((0.79, 0.5), chirality='Right'),
        ]
        out2 = m.assign_roles(f2, now=0.033)
        assert next(h.role for h in out2 if h.chirality == 'Left') == left_role
        assert next(h.role for h in out2 if h.chirality == 'Right') == right_role

    def test_roles_preserved_across_crossing(self) -> None:
        # PRD §8.1.1's canonical hand-crossing test: the two hands
        # cross in front of the camera. After the crossing, the hand
        # that was previously on the LEFT is now on the RIGHT and
        # vice-versa. Role assignment must still be preserved across
        # the crossing — i.e., the hand that was originally
        # HAND_A must still be HAND_A after the crossing.
        #
        # The crossing is structured so that proximity matching
        # AMBIGUOUSLY matches each role to either hand (both distances
        # are below the threshold); the chirality-fallback path is
        # then responsible for resolving the ambiguity.
        m = HandIdentityModule(match_threshold=0.20)
        f1 = [
            make_wrist_only_hand((0.30, 0.50), chirality='Left'),
            make_wrist_only_hand((0.70, 0.50), chirality='Right'),
        ]
        out1 = m.assign_roles(f1, now=0.0)
        roles_f1 = {h.chirality: h.role for h in out1}

        # Crossing frame: hands have swapped x-positions. They are
        # each within MATCH_THRESHOLD (0.20) of BOTH prior positions,
        # so proximity matching produces an ambiguous assignment.
        # The chirality-fallback path then resolves: Left -> HAND_A,
        # Right -> HAND_B.
        f2 = [
            make_wrist_only_hand((0.65, 0.50), chirality='Left'),
            make_wrist_only_hand((0.35, 0.50), chirality='Right'),
        ]
        out2 = m.assign_roles(f2, now=0.1)
        roles_f2 = {h.chirality: h.role for h in out2}
        assert roles_f1 == roles_f2

    def test_proximity_match_beyond_threshold_falls_back(self) -> None:
        # If the re-appearing hand is farther than MATCH_THRESHOLD
        # from any remembered role, no proximity match is attempted
        # and roles are reassigned fresh (no chirality fallback
        # because handedness is still distinct).
        m = HandIdentityModule(match_threshold=0.1)
        m.assign_roles(
            [
                make_wrist_only_hand((0.2, 0.5), chirality='Left'),
                make_wrist_only_hand((0.8, 0.5), chirality='Right'),
            ],
            now=0.0,
        )
        # 1 second later (within REID_WINDOW_S) but positions have
        # moved further than the threshold.
        out = m.assign_roles(
            [
                make_wrist_only_hand((0.5, 0.5), chirality='Left'),
                make_wrist_only_hand((0.5, 0.5), chirality='Right'),
            ],
            now=1.0,
        )
        # Both hands are still role-tagged (proximity fell through
        # to the new-role assignment in Phase 2).
        assert {h.role for h in out} == {ROLE_A, ROLE_B}


# ======================================================================
# Re-identification window (PRD FR-HT-09)
# ======================================================================

class TestReidWindow:
    def test_stale_role_history_cleared(self) -> None:
        m = HandIdentityModule(reid_window_s=1.0)
        m.assign_roles(
            [make_wrist_only_hand((0.2, 0.5), chirality='Left')],
            now=0.0,
        )
        # 2 seconds later (well outside REID_WINDOW_S=1.0)
        m.assign_roles(
            [make_wrist_only_hand((0.2, 0.5), chirality='Left')],
            now=2.0,
        )
        # The stale position should be gone — `_last_seen` was rebuilt
        # with only the new sighting.
        remembered = m.remembered_roles
        assert ROLE_A in remembered
        # The remembered position must be the NEW sighting, not the
        # original 2-second-old one (which has been GC'd).
        assert remembered[ROLE_A][2] == pytest.approx(2.0)

    def test_role_recovered_within_window(self) -> None:
        # Hand leaves at t=0, reappears at t=1.0 (within 2s window).
        m = HandIdentityModule(reid_window_s=2.0)
        out1 = m.assign_roles(
            [
                make_wrist_only_hand((0.2, 0.5), chirality='Left'),
                make_wrist_only_hand((0.8, 0.5), chirality='Right'),
            ],
            now=0.0,
        )
        left_role_f1 = next(h.role for h in out1 if h.chirality == 'Left')

        # Hand disappears at t=0.5 (the 1-hand frame goes through
        # HandIdentityModule but the hand is no longer seen; we
        # simulate this by feeding only the right hand).
        m.assign_roles(
            [make_wrist_only_hand((0.8, 0.5), chirality='Right')],
            now=0.5,
        )

        # Both hands return at t=1.0. Proximity should match the left
        # hand back to its remembered position (x=0.2, well within
        # MATCH_THRESHOLD).
        out3 = m.assign_roles(
            [
                make_wrist_only_hand((0.21, 0.5), chirality='Left'),
                make_wrist_only_hand((0.79, 0.5), chirality='Right'),
            ],
            now=1.0,
        )
        assert next(h.role for h in out3 if h.chirality == 'Left') == left_role_f1


# ======================================================================
# >2 hands -> keep top 2 by confidence (TRD §3.5 Error Handling)
# ======================================================================

class TestTooManyHands:
    def test_three_hands_keeps_top_two(self) -> None:
        m = HandIdentityModule()
        out = m.assign_roles(
            [
                make_wrist_only_hand((0.2, 0.5), chirality='Left',  confidence=0.95),
                make_wrist_only_hand((0.8, 0.5), chirality='Right', confidence=0.90),
                make_wrist_only_hand((0.5, 0.5), chirality='Left',  confidence=0.70),
            ],
            now=0.0,
        )
        assert len(out) == 2
        assert {h.confidence for h in out} == {0.95, 0.90}

    def test_default_max_roles_is_two(self) -> None:
        # Pin the default; `max_roles` is the truncation limit and
        # must equal TrackingModule's max_num_hands default.
        assert MAX_ROLES == 2


# ======================================================================
# Chirality fallback (PRD FR-HT-11)
# ======================================================================

class TestChiralityFallback:
    def test_chirality_mirroring_recovers_roles(self) -> None:
        # Build a state where proximity matching in Phase 1 produces
        # both hands tagged with the same role (only possible if the
        # remember-state has been corrupted). The chirality fallback
        # then disambiguates.
        m = HandIdentityModule()
        # Manually corrupt: remember ROLE_A pointing at a left hand's
        # old position.
        m._last_seen[ROLE_A] = (0.2, 0.5, 0.0)  # type: ignore[attr-defined]
        # Pass two hands, both with positions close to (0.2, 0.5) —
        # proximity match will pick the closest for ROLE_A, but if
        # we force a near-ambiguous setup, the fallback should kick in.
        out = m.assign_roles(
            [
                make_wrist_only_hand((0.21, 0.5), chirality='Left',  confidence=0.9),
                make_wrist_only_hand((0.22, 0.5), chirality='Right', confidence=0.8),
            ],
            now=1.0,
        )
        # Both hands must come out role-tagged (Left -> A, Right -> B
        # by chirality-fallback convention).
        roles = {h.chirality: h.role for h in out}
        assert roles.get('Left') == ROLE_A
        assert roles.get('Right') == ROLE_B


# ======================================================================
# reset()
# ======================================================================

class TestReset:
    def test_reset_clears_remembered_roles(self) -> None:
        m = HandIdentityModule()
        m.assign_roles(
            [make_wrist_only_hand((0.2, 0.5), chirality='Left')],
            now=0.0,
        )
        m.reset()
        assert m.remembered_roles == {}


# ======================================================================
# Hot-path error handling (RULES §6.4)
# ======================================================================

class TestHotPathNeverRaises:
    def test_malformed_landmarks_does_not_crash(self) -> None:
        m = HandIdentityModule()
        # Hand with fewer than 1 landmark (defensive: TrackingModule
        # already discards these, but identity must not propagate an
        # exception if a degenerate one slips through).
        bad = make_wrist_only_hand((0.5, 0.5))
        bad_landmarks = bad.landmarks
        from dataclasses import replace as _replace
        bad = _replace(bad, landmarks=bad_landmarks[:0])  # empty list
        # Should NOT raise (RULES §6.4 hot-path-never-raises).
        out = m.assign_roles([bad], now=0.0)
        # Malformed hand is dropped, output is empty (Phase 1 filter).
        assert out == []