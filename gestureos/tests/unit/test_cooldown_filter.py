"""Unit tests for CooldownFilter — CP-3.

Per TRD §3.11 + PRD §8.3 (FR-CD-01..03):
  - FR-CD-01: per-(role, gesture_name) cooldown; static vs dynamic
    use different durations
  - FR-CD-02: cooldown on (HAND_A, gesture_X) does NOT suppress a
    different gesture on HAND_A, nor the same gesture on HAND_B
  - FR-CD-03: `remaining_ms()` accessor for the debug overlay
"""

from __future__ import annotations

import pytest

from gestures.cooldown_filter import CooldownFilter
from models.data_models import GestureResult
from settings.settings_manager import Settings


# ======================================================================
# Helpers
# ======================================================================

def make_settings(**overrides) -> Settings:
    """Build a Settings instance with custom cooldown overrides."""
    defaults = {
        'gesture_cooldown_static_ms': 500,
        'gesture_cooldown_dynamic_ms': 1000,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_result(
    gesture_name: str,
    hand_role: str = 'HAND_A',
    is_dynamic: bool = False,
    confidence: float = 0.9,
) -> GestureResult:
    return GestureResult(
        gesture_name=gesture_name,
        confidence=confidence,
        is_dynamic=is_dynamic,
        hand_role=hand_role,
        timestamp=0.0,
    )


# ======================================================================
# FR-CD-01: basic suppression
# ======================================================================

class TestBasicSuppression:
    def test_first_trigger_fires(self) -> None:
        """TRD §13.5 `test_cooldown_suppresses_repeated_trigger` first
        half: the first trigger fires."""
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        result = make_result('pinch')
        assert f.check(result, now=0.0) is not None

    def test_second_trigger_within_cooldown_suppressed(self) -> None:
        """TRD §13.5 second half: the same trigger within the cooldown
        window is suppressed."""
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        first = make_result('pinch')
        assert f.check(first, now=0.0) is not None
        # 100 ms later -> still within 500 ms cooldown -> suppress.
        second = make_result('pinch')
        assert f.check(second, now=0.100) is None

    def test_second_trigger_after_cooldown_fires(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        first = make_result('pinch')
        assert f.check(first, now=0.0) is not None
        # 600 ms later -> past the 500 ms cooldown -> fires again.
        second = make_result('pinch')
        assert f.check(second, now=0.600) is not None


# ======================================================================
# FR-CD-01: static vs dynamic cooldown durations
# ======================================================================

class TestStaticVsDynamicCooldown:
    def test_static_uses_static_cooldown(self) -> None:
        f = CooldownFilter(make_settings(
            gesture_cooldown_static_ms=500,
            gesture_cooldown_dynamic_ms=1000,
        ))
        first = make_result('pinch', is_dynamic=False)
        assert f.check(first, now=0.0) is not None
        # 400 ms later -> within 500 ms static cooldown -> suppress.
        second = make_result('pinch', is_dynamic=False)
        assert f.check(second, now=0.400) is None
        # 600 ms later -> past static cooldown -> fires.
        third = make_result('pinch', is_dynamic=False)
        assert f.check(third, now=0.600) is not None

    def test_dynamic_uses_dynamic_cooldown(self) -> None:
        f = CooldownFilter(make_settings(
            gesture_cooldown_static_ms=500,
            gesture_cooldown_dynamic_ms=1000,
        ))
        first = make_result('swipe_right', is_dynamic=True)
        assert f.check(first, now=0.0) is not None
        # 600 ms later -> within 1000 ms dynamic cooldown -> suppress.
        second = make_result('swipe_right', is_dynamic=True)
        assert f.check(second, now=0.600) is None
        # 1100 ms later -> past dynamic cooldown -> fires.
        third = make_result('swipe_right', is_dynamic=True)
        assert f.check(third, now=1.100) is not None


# ======================================================================
# FR-CD-02: cross-gesture independence
# ======================================================================

class TestCrossGestureIndependence:
    def test_different_gesture_on_same_hand_not_suppressed(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        # Pinch on HAND_A at t=0 -> fires.
        assert f.check(make_result('pinch', hand_role='HAND_A'), now=0.0) is not None
        # Peace Sign on HAND_A at t=0.1 (pinch still in cooldown) -> NOT suppressed.
        # Different gesture, same hand — independence per FR-CD-02.
        assert f.check(
            make_result('peace_sign', hand_role='HAND_A'), now=0.1
        ) is not None

    def test_same_gesture_on_different_hand_not_suppressed(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        # Pinch on HAND_A at t=0 -> fires.
        assert f.check(make_result('pinch', hand_role='HAND_A'), now=0.0) is not None
        # Pinch on HAND_B at t=0.1 (HAND_A's pinch still in cooldown)
        # -> NOT suppressed (different hand, FR-CD-02).
        assert f.check(
            make_result('pinch', hand_role='HAND_B'), now=0.1
        ) is not None


# ======================================================================
# FR-CD-03: remaining_ms accessor
# ======================================================================

class TestRemainingMsAccessor:
    def test_no_cooldown_means_remaining_is_zero(self) -> None:
        f = CooldownFilter(make_settings())
        # No prior trigger -> 0 ms remaining.
        assert f.remaining_ms('HAND_A', 'pinch', now=0.0) == 0

    def test_after_trigger_remaining_equals_cooldown(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        f.check(make_result('pinch'), now=0.0)
        # Immediately after -> full cooldown remaining.
        assert f.remaining_ms('HAND_A', 'pinch', now=0.0) == 500

    def test_after_half_cooldown_remaining_halved(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        f.check(make_result('pinch'), now=0.0)
        # After 250 ms -> 250 ms remaining.
        remaining = f.remaining_ms('HAND_A', 'pinch', now=0.250)
        assert remaining == 250

    def test_after_full_cooldown_remaining_is_zero(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        f.check(make_result('pinch'), now=0.0)
        # After 600 ms -> past cooldown -> 0 remaining.
        assert f.remaining_ms('HAND_A', 'pinch', now=0.600) == 0

    def test_remaining_does_not_go_negative(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        f.check(make_result('pinch'), now=0.0)
        # Long after cooldown -> 0 (never negative).
        assert f.remaining_ms('HAND_A', 'pinch', now=100.0) == 0

    def test_remaining_for_unknown_pair_is_zero(self) -> None:
        f = CooldownFilter(make_settings())
        assert f.remaining_ms('HAND_NEVER_SEEN', 'anything', now=0.0) == 0


# ======================================================================
# reset()
# ======================================================================

class TestReset:
    def test_reset_clears_all_cooldowns(self) -> None:
        f = CooldownFilter(make_settings(gesture_cooldown_static_ms=500))
        f.check(make_result('pinch'), now=0.0)
        f.reset()
        # After reset, a new trigger fires immediately.
        assert f.check(make_result('pinch'), now=0.100) is not None


# ======================================================================
# TRD §13.5 reference test verbatim
# ======================================================================

class TestTrdReferenceTest:
    def test_cooldown_suppresses_repeated_trigger(self) -> None:
        """TRD §13.5 reference test verbatim."""
        settings = Settings(gesture_cooldown_static_ms=500)
        f = CooldownFilter(settings)
        result = GestureResult('pinch', 0.9, False, 'HAND_A', 0.0)
        # First trigger fires.
        assert f.check(result, now=0.0) is not None
        # Within cooldown, suppressed.
        assert f.check(result, now=0.1) is None
        # After cooldown, fires again.
        assert f.check(result, now=0.6) is not None