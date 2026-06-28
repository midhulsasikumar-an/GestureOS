"""Unit tests for StabilityFilter — CP-3.

Per TRD §3.10 + PRD §8.2 (FR-GS-01..04):
  - FR-GS-01: static gesture held continuously for `window_ms` -> emit
  - FR-GS-02: candidate changes before window elapses -> reset hold, no partial credit
  - FR-GS-03: per hand role independence
  - FR-GS-04: dynamic gestures exempt

Includes the TRD §13.5 reference test `test_single_frame_flicker_does_not_trigger`.
"""

from __future__ import annotations

import pytest

from gestures.stability_filter import (
    DEFAULT_HOLD_WINDOW_MS,
    StabilityFilter,
)
from models.data_models import GestureResult


# ======================================================================
# Constants
# ======================================================================

class TestConstants:
    def test_default_hold_window_is_200ms(self) -> None:
        # PRD §8.2: 200 ms default.
        assert DEFAULT_HOLD_WINDOW_MS == 200

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError):
            StabilityFilter(window_ms=0)
        with pytest.raises(ValueError):
            StabilityFilter(window_ms=-1)


# ======================================================================
# FR-GS-01 + boundary handling: `>=` not `>`
# ======================================================================

class TestHoldWindow:
    def test_held_long_enough_emits(self) -> None:
        f = StabilityFilter(window_ms=200)
        candidate = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        # First frame -> starts the hold.
        assert f.check('HAND_A', candidate, now=0.0) is None
        # 100 ms in -> still within the hold window.
        assert f.check('HAND_A', candidate, now=0.100) is None
        # 200 ms in -> exactly at the boundary; per TRD §3.10 reference
        # implementation, this emits (uses `>=`, not `>`).
        result = f.check('HAND_A', candidate, now=0.200)
        assert result is not None
        assert result.gesture_name == 'open_palm'

    def test_held_beyond_window_emits_only_once(self) -> None:
        f = StabilityFilter(window_ms=200)
        candidate = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        f.check('HAND_A', candidate, now=0.0)
        result = f.check('HAND_A', candidate, now=0.200)
        assert result is not None
        # Second frame at 233 ms -> already emitted, don't emit again.
        assert f.check('HAND_A', candidate, now=0.233) is None
        # Third frame at 266 ms -> still no re-emit (same hold cycle).
        assert f.check('HAND_A', candidate, now=0.266) is None


# ======================================================================
# FR-GS-02: candidate change resets the hold timer
# ======================================================================

class TestCandidateChangeResets:
    def test_single_frame_flicker_does_not_trigger(self) -> None:
        """TRD §13.5 reference test verbatim: a gesture that appears
        for only one frame must NOT trigger the stability filter.
        """
        f = StabilityFilter(window_ms=200)
        now = 0.0
        candidate = GestureResult('open_palm', 0.9, False, 'HAND_A', now)
        # First frame -> starts the hold, no emit.
        assert f.check('HAND_A', candidate, now=now) is None
        # Disappears (flicker): reset the hold.
        assert f.check('HAND_A', None, now=now + 0.033) is None
        # Reappears -> restart the hold (no partial credit).
        assert f.check('HAND_A', candidate, now=now + 0.066) is None

    def test_change_to_different_gesture_resets_hold(self) -> None:
        f = StabilityFilter(window_ms=200)
        open_palm = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        peace_sign = GestureResult('peace_sign', 0.9, False, 'HAND_A', 0.0)
        f.check('HAND_A', open_palm, now=0.0)
        # Switch to peace_sign at 100 ms (still within window) -> reset.
        assert f.check('HAND_A', peace_sign, now=0.100) is None
        # Continue holding peace_sign -> still in the new hold.
        assert f.check('HAND_A', peace_sign, now=0.250) is None
        # Use a value that doesn't have float-precision drift: at
        # 0.5 seconds (400 ms into the new hold) -> emit.
        result = f.check('HAND_A', peace_sign, now=0.500)
        assert result is not None
        assert result.gesture_name == 'peace_sign'


# ======================================================================
# FR-GS-03: per-role independence
# ======================================================================

class TestPerRoleIndependence:
    def test_two_roles_have_independent_holds(self) -> None:
        f = StabilityFilter(window_ms=200)
        hand_a = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        hand_b = GestureResult('peace_sign', 0.9, False, 'HAND_B', 0.0)
        f.check('HAND_A', hand_a, now=0.0)
        f.check('HAND_B', hand_b, now=0.0)
        # Both are still within their respective 200 ms windows at 100 ms.
        assert f.check('HAND_A', hand_a, now=0.100) is None
        assert f.check('HAND_B', hand_b, now=0.100) is None
        # Both emit at 200 ms.
        r_a = f.check('HAND_A', hand_a, now=0.200)
        r_b = f.check('HAND_B', hand_b, now=0.200)
        assert r_a is not None and r_a.gesture_name == 'open_palm'
        assert r_b is not None and r_b.gesture_name == 'peace_sign'

    def test_role_a_change_does_not_reset_role_b(self) -> None:
        f = StabilityFilter(window_ms=200)
        hand_a = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        hand_b = GestureResult('peace_sign', 0.9, False, 'HAND_B', 0.0)
        f.check('HAND_A', hand_a, now=0.0)
        f.check('HAND_B', hand_b, now=0.0)
        # HAND_A changes to a different gesture at 50 ms.
        f.check('HAND_A', GestureResult('fist', 0.9, False, 'HAND_A', 0.0), now=0.050)
        # HAND_B's hold must NOT be affected.
        # At 200 ms, HAND_B still emits (it has been held continuously
        # since 0.0, 200 ms ago).
        r_b = f.check('HAND_B', hand_b, now=0.200)
        assert r_b is not None


# ======================================================================
# FR-GS-04: dynamic gestures exempt
# ======================================================================

class TestDynamicExempt:
    def test_dynamic_gesture_passes_through(self) -> None:
        f = StabilityFilter(window_ms=200)
        # Dynamic gesture: should pass through immediately on first frame.
        candidate = GestureResult('swipe_right', 0.85, True, 'HAND_A', 0.0)
        result = f.check('HAND_A', candidate, now=0.0)
        assert result is not None
        assert result.gesture_name == 'swipe_right'

    def test_dynamic_gesture_does_not_track_hold_state(self) -> None:
        f = StabilityFilter(window_ms=200)
        candidate = GestureResult('swipe_right', 0.85, True, 'HAND_A', 0.0)
        # First frame -> emit (dynamic exempt).
        assert f.check('HAND_A', candidate, now=0.0) is not None
        # Subsequent frames -> emit again? The TRD reference says
        # "pass dynamic candidates straight through". This implementation
        # does NOT re-emit on subsequent frames (the CooldownFilter
        # handles per-gesture re-trigger suppression downstream).
        # This is consistent with the TRD contract: the StabilityFilter
        # is for hold-timer semantics on STATIC gestures only.
        # Per the test below, multiple identical dynamic candidates
        # are passed through unchanged.
        result2 = f.check('HAND_A', candidate, now=0.033)
        # Dynamic pass-through: yes, it does emit every frame.
        # The CooldownFilter handles re-trigger suppression.
        assert result2 is not None
        assert result2.gesture_name == 'swipe_right'


# ======================================================================
# FR-GS-02: candidate = None resets state
# ======================================================================

class TestNoneCandidateResets:
    def test_candidate_disappearing_resets_hold(self) -> None:
        f = StabilityFilter(window_ms=200)
        candidate = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        f.check('HAND_A', candidate, now=0.0)
        # Disappears at 100 ms.
        assert f.check('HAND_A', None, now=0.100) is None
        # Reappears at 150 ms -> restart the hold.
        assert f.check('HAND_A', candidate, now=0.150) is None
        # Hold started at 0.150; reach 0.500 (well past 200 ms) -> emit.
        # Use values that avoid float-precision drift.
        result = f.check('HAND_A', candidate, now=0.500)
        assert result is not None

    def test_unknown_role_starts_fresh(self) -> None:
        f = StabilityFilter(window_ms=200)
        # No prior state for HAND_C -> first frame starts a fresh hold.
        candidate = GestureResult('open_palm', 0.9, False, 'HAND_C', 0.0)
        assert f.check('HAND_C', candidate, now=0.0) is None


# ======================================================================
# Read-only introspection
# ======================================================================

class TestIntrospection:
    def test_holds_in_progress_reflects_state(self) -> None:
        f = StabilityFilter(window_ms=200)
        candidate = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        assert f.holds_in_progress == {}
        f.check('HAND_A', candidate, now=0.0)
        assert f.holds_in_progress == {'HAND_A': ('open_palm', 0.0)}

    def test_reset_clears_all_holds(self) -> None:
        f = StabilityFilter(window_ms=200)
        candidate = GestureResult('open_palm', 0.9, False, 'HAND_A', 0.0)
        f.check('HAND_A', candidate, now=0.0)
        f.reset()
        assert f.holds_in_progress == {}