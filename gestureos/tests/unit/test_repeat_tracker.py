"""Unit tests for HeldGestureTracker — repeat-while-held logic.

Tests cover:
  - Non-repeatable gestures are never tracked.
  - Repeatable gesture starts tracking on first frame.
  - get_ready_repeats returns nothing before INITIAL_REPEAT_DELAY_S.
  - get_ready_repeats returns after initial delay + repeat interval.
  - Multiple calls produce multiple repeats at the right cadence.
  - Gesture change resets the hold timer.
  - Gesture release (role absent) clears tracking.
  - is_held / current_gesture introspection.
  - Reset clears all state.
  - Two roles are tracked independently.
"""

from __future__ import annotations

from actions.repeat_tracker import (
    INITIAL_REPEAT_DELAY_S,
    REPEAT_INTERVAL_S,
    HeldGestureTracker,
)


class TestNonRepeatable:
    def test_non_repeatable_gesture_not_tracked(self) -> None:
        tracker = HeldGestureTracker()
        tracker.feed_frame({'HAND_A': 'thumbs_up'}, 0.0)
        assert not tracker.is_held('HAND_A')

    def test_mixed_repeatable_and_non(self) -> None:
        tracker = HeldGestureTracker()
        tracker.feed_frame({'HAND_A': 'one_finger', 'HAND_B': 'thumbs_up'}, 0.0)
        assert tracker.is_held('HAND_A')
        assert tracker.current_gesture('HAND_A') == 'one_finger'
        assert not tracker.is_held('HAND_B')


class TestTrackingStart:
    def test_repeatable_gesture_starts_tracking(self) -> None:
        tracker = HeldGestureTracker()
        tracker.feed_frame({'HAND_A': 'peace_sign'}, 1.0)
        assert tracker.is_held('HAND_A')
        assert tracker.current_gesture('HAND_A') == 'peace_sign'

    def test_gesture_change_resets_timer(self) -> None:
        tracker = HeldGestureTracker()
        now = 0.0
        tracker.feed_frame({'HAND_A': 'one_finger'}, now)
        # Hold for a while.
        now += 0.6
        tracker.feed_frame({'HAND_A': 'one_finger'}, now)
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 1
        # Change gesture.
        now += 0.1
        tracker.feed_frame({'HAND_A': 'peace_sign'}, now)
        assert tracker.current_gesture('HAND_A') == 'peace_sign'
        # Not yet past initial delay for the new gesture.
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 0


class TestRelease:
    def test_role_absent_clears_tracking(self) -> None:
        tracker = HeldGestureTracker()
        tracker.feed_frame({'HAND_A': 'one_finger'}, 0.0)
        assert tracker.is_held('HAND_A')
        tracker.feed_frame({}, 0.5)
        assert not tracker.is_held('HAND_A')

    def test_release_and_rehold_restarts_timer(self) -> None:
        tracker = HeldGestureTracker()
        tracker.feed_frame({'HAND_A': 'one_finger'}, 0.0)
        tracker.feed_frame({}, 0.3)
        assert not tracker.is_held('HAND_A')
        # Re-hold.
        tracker.feed_frame({'HAND_A': 'one_finger'}, 0.5)
        # Not yet past initial delay.
        ready = tracker.get_ready_repeats(0.5 + INITIAL_REPEAT_DELAY_S - 0.1)
        assert len(ready) == 0
        # Past initial delay.
        ready = tracker.get_ready_repeats(0.5 + INITIAL_REPEAT_DELAY_S + 0.1)
        assert len(ready) == 1


class TestRepeatTiming:
    def test_no_repeats_before_initial_delay(self) -> None:
        tracker = HeldGestureTracker()
        now = 0.0
        tracker.feed_frame({'HAND_A': 'one_finger'}, now)
        now += INITIAL_REPEAT_DELAY_S - 0.1
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 0

    def test_repeat_after_initial_delay(self) -> None:
        tracker = HeldGestureTracker()
        now = 0.0
        tracker.feed_frame({'HAND_A': 'one_finger'}, now)
        now += INITIAL_REPEAT_DELAY_S + 0.1
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 1
        assert ready[0] == ('HAND_A', 'one_finger')

    def test_repeat_at_correct_cadence(self) -> None:
        tracker = HeldGestureTracker()
        now = 0.0
        tracker.feed_frame({'HAND_A': 'one_finger'}, now)
        # First repeat at initial delay.
        now = INITIAL_REPEAT_DELAY_S + 0.1
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 1
        first_repeat_time = now
        # Second repeat after REPEAT_INTERVAL_S.
        now = first_repeat_time + REPEAT_INTERVAL_S
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 1
        # Third repeat.
        now += REPEAT_INTERVAL_S
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 1

    def test_no_double_repeat_within_interval(self) -> None:
        tracker = HeldGestureTracker()
        now = 0.0
        tracker.feed_frame({'HAND_A': 'one_finger'}, now)
        now = INITIAL_REPEAT_DELAY_S + 0.1
        _ = tracker.get_ready_repeats(now)  # First repeat consumed.
        now += REPEAT_INTERVAL_S - 0.05  # Just before the next repeat.
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 0


class TestMultipleRoles:
    def test_two_roles_independent(self) -> None:
        tracker = HeldGestureTracker()
        now = 0.0
        tracker.feed_frame({'HAND_A': 'one_finger', 'HAND_B': 'peace_sign'}, now)
        now += INITIAL_REPEAT_DELAY_S + 0.1
        ready = tracker.get_ready_repeats(now)
        assert len(ready) == 2
        roles = {r for r, _ in ready}
        assert roles == {'HAND_A', 'HAND_B'}

    def test_one_role_released_other_continues(self) -> None:
        tracker = HeldGestureTracker()
        now = 0.0
        tracker.feed_frame({'HAND_A': 'one_finger', 'HAND_B': 'peace_sign'}, now)
        now += 0.3
        tracker.feed_frame({'HAND_A': 'one_finger'}, now)  # B released.
        assert tracker.is_held('HAND_A')
        assert not tracker.is_held('HAND_B')


class TestReset:
    def test_reset_clears_all(self) -> None:
        tracker = HeldGestureTracker()
        tracker.feed_frame({'HAND_A': 'one_finger', 'HAND_B': 'peace_sign'}, 0.0)
        assert tracker.is_held('HAND_A')
        assert tracker.is_held('HAND_B')
        tracker.reset()
        assert not tracker.is_held('HAND_A')
        assert not tracker.is_held('HAND_B')
