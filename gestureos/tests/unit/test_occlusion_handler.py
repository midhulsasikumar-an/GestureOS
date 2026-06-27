"""Unit tests for OcclusionHandler — CP-2.

Per TRD §13.2: no live camera required. Tests use synthetic hand
sequences and verify the 300 ms (configurable) bridge window, the
`is_retained=True` flag, the hard-timeout release, and the
integration with HandIdentityModule (covered by the occlusion_sequence
fixture).
"""

from __future__ import annotations

import pytest

from tracking.hand_identity import ROLE_A, ROLE_B
from tracking.occlusion_handler import (
    DEFAULT_RETENTION_MS,
    OcclusionHandler,
)

from tests.conftest import make_wrist_only_hand


# ======================================================================
# Construction
# ======================================================================

class TestConstruction:
    def test_default_retention(self) -> None:
        h = OcclusionHandler()
        assert h.retention_ms == DEFAULT_RETENTION_MS == 300
        assert h.retention_s == pytest.approx(0.3)

    def test_custom_retention(self) -> None:
        h = OcclusionHandler(retention_ms=500)
        assert h.retention_ms == 500
        assert h.retention_s == pytest.approx(0.5)

    def test_invalid_retention_raises(self) -> None:
        with pytest.raises(ValueError):
            OcclusionHandler(retention_ms=0)
        with pytest.raises(ValueError):
            OcclusionHandler(retention_ms=-1)

    def test_first_frame_does_not_crash(self) -> None:
        # TRD reference's `bridge_gaps` uses `self._previous_roles`
        # which is not initialized in the reference; this implementation
        # initializes to empty so the first call is safe.
        h = OcclusionHandler()
        out = h.bridge_gaps([], now=0.0)
        assert out == []


# ======================================================================
# Brief occlusion is bridged (PRD FR-OC-01..02)
# ======================================================================

class TestBriefOcclusionBridged:
    def test_150ms_occlusion_is_bridged(self) -> None:
        h = OcclusionHandler(retention_ms=300)
        # Frame 1: hand present
        present = [make_wrist_only_hand((0.5, 0.5), role='HAND_A')]
        h.bridge_gaps(present, now=0.0)

        # Frame 2: hand missing for 150 ms (still within window)
        bridged = h.bridge_gaps([], now=0.150)
        # The retained hand should be re-emitted with is_retained=True.
        assert len(bridged) == 1
        assert bridged[0].role == 'HAND_A'
        assert bridged[0].is_retained is True

    def test_50ms_occlusion_keeps_is_retained_flag(self) -> None:
        h = OcclusionHandler(retention_ms=300)
        h.bridge_gaps(
            [make_wrist_only_hand((0.5, 0.5), role='HAND_A')],
            now=0.0,
        )
        bridged = h.bridge_gaps([], now=0.05)
        assert any(h.is_retained for h in bridged)


# ======================================================================
# Occlusion window expires (PRD FR-OC-03)
# ======================================================================

class TestOcclusionWindowExpires:
    def test_400ms_occlusion_releases_role(self) -> None:
        h = OcclusionHandler(retention_ms=300)
        h.bridge_gaps(
            [make_wrist_only_hand((0.5, 0.5), role='HAND_A')],
            now=0.0,
        )
        # 400 ms > 300 ms window -> retention is released.
        released = h.bridge_gaps([], now=0.400)
        assert released == []
        # The retained buffer must be empty after expiry.
        assert h.retained_roles == {}

    def test_exactly_at_boundary_releases(self) -> None:
        # The hard timeout is "elapsed > retention_ms", so at exactly
        # 300 ms the hand is still bridged; at 300.001 ms it is released.
        h = OcclusionHandler(retention_ms=300)
        h.bridge_gaps(
            [make_wrist_only_hand((0.5, 0.5), role='HAND_A')],
            now=0.0,
        )
        just_before = h.bridge_gaps([], now=0.300)
        assert any(b.is_retained for b in just_before)
        just_after = h.bridge_gaps([], now=0.301)
        assert just_after == []


# ======================================================================
# Recovery within window
# ======================================================================

class TestRecoveryWithinWindow:
    def test_hand_reappears_drops_bridge(self) -> None:
        h = OcclusionHandler(retention_ms=300)
        h.bridge_gaps(
            [make_wrist_only_hand((0.5, 0.5), role='HAND_A')],
            now=0.0,
        )
        # Brief gap
        bridged = h.bridge_gaps([], now=0.100)
        assert any(b.is_retained for b in bridged)

        # Hand returns — the retained entry must be dropped.
        recovered = h.bridge_gaps(
            [make_wrist_only_hand((0.51, 0.5), role='HAND_A')],
            now=0.150,
        )
        # Output has the real hand, no retained copy.
        assert len(recovered) == 1
        assert recovered[0].is_retained is False
        assert h.retained_roles == {}


# ======================================================================
# Multi-hand handling
# ======================================================================

class TestMultiHandOcclusion:
    def test_only_one_hand_occluded_is_bridged(self) -> None:
        h = OcclusionHandler(retention_ms=300)
        h.bridge_gaps(
            [
                make_wrist_only_hand((0.2, 0.5), role='HAND_A'),
                make_wrist_only_hand((0.8, 0.5), role='HAND_B'),
            ],
            now=0.0,
        )
        # Frame 2: only HAND_A present; HAND_B is missing.
        bridged = h.bridge_gaps(
            [make_wrist_only_hand((0.21, 0.5), role='HAND_A')],
            now=0.100,
        )
        # Output: real HAND_A + bridged HAND_B = 2 hands.
        assert len(bridged) == 2
        real = next(h for h in bridged if h.role == 'HAND_A')
        retained = next(h for h in bridged if h.role == 'HAND_B')
        assert real.is_retained is False
        assert retained.is_retained is True


# ======================================================================
# Hard timeout: never retains forever
# ======================================================================

class TestHardTimeout:
    def test_no_retained_after_window_expires_across_many_frames(self) -> None:
        h = OcclusionHandler(retention_ms=300)
        h.bridge_gaps(
            [make_wrist_only_hand((0.5, 0.5), role='HAND_A')],
            now=0.0,
        )
        # Many frames without the hand, each well past the window.
        for t in (0.4, 0.8, 1.2, 1.6, 2.0):
            result = h.bridge_gaps([], now=t)
            assert result == []
        # The retained buffer must be empty — no silent retention.
        assert h.retained_roles == {}


# ======================================================================
# reset()
# ======================================================================

class TestReset:
    def test_reset_clears_all_state(self) -> None:
        h = OcclusionHandler()
        h.bridge_gaps(
            [make_wrist_only_hand((0.5, 0.5), role='HAND_A')],
            now=0.0,
        )
        h.bridge_gaps([], now=0.1)  # start a bridge
        h.reset()
        assert h.retained_roles == {}
        # After reset, a fresh first-frame call must not crash and must
        # not magically produce a retained hand.
        out = h.bridge_gaps([], now=0.5)
        assert out == []


# ======================================================================
# Integration: occlusion_sequence fixture
# ======================================================================

class TestOcclusionSequenceIntegration:
    def test_full_sequence_keeps_roles_consistent(self, occlusion_sequence):
        # Apply the fixture frame-by-frame through HandIdentityModule
        # and OcclusionHandler and assert that HAND_A / HAND_B roles
        # stay consistent through the occlusion episode and the
        # crossing.
        from tracking.hand_identity import HandIdentityModule
        from dataclasses import replace as _replace

        identity = HandIdentityModule()
        occluder = OcclusionHandler(retention_ms=300)
        role_history: list[dict[str, str | None]] = []

        for frame in occlusion_sequence:
            t = frame['t']
            hands_in = [
                _replace(
                    make_wrist_only_hand(
                        tuple(h['wrist']),
                        chirality=h['chirality'],
                    ),
                    role=None,
                )
                for h in frame['hands']
            ]
            tagged = identity.assign_roles(hands_in, t)
            bridged = occluder.bridge_gaps(tagged, t)
            role_history.append({h.role: h.chirality for h in bridged})

        # Frame 0 (t=0.0): two hands -> both roles present.
        assert {ROLE_A, ROLE_B} == set(role_history[0].keys())

        # Frame 2 (t=0.066): right hand missing -> occluded.
        # After occlusion: still both roles in output (one retained).
        # ROLE_B's chirality must be Right.
        assert role_history[2].get('HAND_B') == 'Right'

        # Frame 4 (t=0.366): window expired -> no HAND_B.
        assert 'HAND_B' not in role_history[4]

        # Frame 6 (t=0.566): hands crossed. Roles preserved by
        # proximity.
        # HAND_A should still be the Left hand (it moved to x=0.75
        # which is closer to its old position 0.22 than to the
        # right hand's old position 0.79).
        assert role_history[6]['HAND_A'] == 'Left'