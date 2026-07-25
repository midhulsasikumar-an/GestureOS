"""Unit tests for ActivationGate — Checkpoint 4.

Mirrors Implementation Plan §8's verbatim reference test cases:
  - `test_default_state_is_inactive`             — FR-AM-06
  - `test_open_palm_hold_toggles_state`          — TRD §5.3 reference
  - `test_non_open_palm_gesture_resets_hold_timer` — TRD §5.3 reference

Plus additional coverage for:
  - PRD FR-AM-07: configurable hold duration (0.5–3.0s) and validation
  - PRD §7.2: Closed Fist Hold method (off by default)
  - Explicit `toggle()` for keyboard-shortcut / tray-icon callers
  - Hold timer reset on non-qualifying gesture (no partial credit)
  - Hot-path-never-raises (RULES §6.4)
  - `reset()` lifecycle
  - Read-only introspection (`is_active`, `hold_in_progress`)
"""

from __future__ import annotations

import logging

import pytest

from gestures.activation_gate import (
    MIN_HOLD_DURATION_S,
    MAX_HOLD_DURATION_S,
    DEFAULT_HOLD_DURATION_S,
    OPEN_PALM_GESTURE,
    CLOSED_FIST_GESTURE,
    ActivationGate,
    ActivationMethod,
    TrackingState,
)


# ======================================================================
# Helpers
# ======================================================================

def make_gate(
    hold_duration_s: float = DEFAULT_HOLD_DURATION_S,
    enable_closed_fist: bool = False,
) -> ActivationGate:
    """Build an ActivationGate with sane defaults."""
    return ActivationGate(
        hold_duration_s=hold_duration_s,
        enable_closed_fist=enable_closed_fist,
    )


def hold_open_palm(
    gate: ActivationGate,
    t_start: float,
    duration_s: float,
    sample_hz: float = 60.0,
) -> None:
    """Feed `OPEN_PALM_GESTURE` to the gate for `duration_s` seconds.

    Samples at `sample_hz` so the gate's hold-elapsed check fires
    at the boundary. Mirrors a real per-frame feed from
    `CaptureThread`.
    """
    step = 1.0 / sample_hz
    t = t_start
    end = t_start + duration_s
    while t <= end + 1e-9:
        gate.feed_gesture(OPEN_PALM_GESTURE, t)
        t += step


# ======================================================================
# IP §8 reference test cases (verbatim)
# ======================================================================

class TestTrdReference:
    """Verbatim Implementation Plan §8 reference test cases."""

    def test_default_state_is_inactive(self) -> None:
        """FR-AM-06: default state on app launch is INACTIVE."""
        gate = make_gate()
        assert gate.state == TrackingState.INACTIVE
        assert gate.is_active is False

    def test_open_palm_hold_toggles_state(self) -> None:
        """TRD §5.3: Open Palm held ≥ hold_duration_s toggles state."""
        gate = make_gate(hold_duration_s=1.0)
        # Hold open palm for 1.1s starting at t=0 — clearly past 1.0s.
        hold_open_palm(gate, t_start=0.0, duration_s=1.1)
        assert gate.state == TrackingState.ACTIVE

    def test_non_open_palm_gesture_resets_hold_timer(self) -> None:
        """TRD §5.3: non-Open-Palm gesture resets hold with no
        partial credit."""
        gate = make_gate(hold_duration_s=1.0)
        # 0.5s of open palm — partial credit.
        hold_open_palm(gate, t_start=0.0, duration_s=0.5)
        # Pinch arrives mid-hold — resets the hold-timer per TRD §5.3.
        gate.feed_gesture('pinch', now=0.5)
        # Continue holding open palm from t=0.5 for another 0.7s —
        # that's only 0.7s of new open-palm (less than 1.0s), so the
        # state must NOT toggle.
        hold_open_palm(gate, t_start=0.5, duration_s=0.7)
        assert gate.state == TrackingState.INACTIVE
        # Now extend the hold to >1.0s total continuous open palm
        # AFTER the interruption: still no toggle, because the
        # interrupt at t=0.5 reset the hold-start.
        hold_open_palm(gate, t_start=1.2, duration_s=0.3)
        assert gate.state == TrackingState.INACTIVE


# ======================================================================
# FR-AM-07: configurable hold duration
# ======================================================================

class TestConfigurableHoldDuration:
    def test_default_hold_duration(self) -> None:
        gate = make_gate()
        assert gate.hold_duration_s == DEFAULT_HOLD_DURATION_S

    def test_minimum_hold_duration_accepted(self) -> None:
        gate = make_gate(hold_duration_s=MIN_HOLD_DURATION_S)
        assert gate.hold_duration_s == MIN_HOLD_DURATION_S

    def test_maximum_hold_duration_accepted(self) -> None:
        gate = make_gate(hold_duration_s=MAX_HOLD_DURATION_S)
        assert gate.hold_duration_s == MAX_HOLD_DURATION_S

    def test_below_minimum_rejected(self) -> None:
        with pytest.raises(ValueError):
            make_gate(hold_duration_s=MIN_HOLD_DURATION_S - 0.01)

    def test_above_maximum_rejected(self) -> None:
        with pytest.raises(ValueError):
            make_gate(hold_duration_s=MAX_HOLD_DURATION_S + 0.01)

    def test_short_hold_duration_toggles_faster(self) -> None:
        """FR-AM-07: shorter hold durations should require less hold
        time to toggle."""
        gate = make_gate(hold_duration_s=MIN_HOLD_DURATION_S)
        hold_open_palm(gate, t_start=0.0, duration_s=MIN_HOLD_DURATION_S + 0.05)
        assert gate.state == TrackingState.ACTIVE


# ======================================================================
# PRD §7.2: Closed Fist Hold (off by default)
# ======================================================================

class TestClosedFistHold:
    def test_disabled_by_default(self) -> None:
        gate = make_gate(enable_closed_fist=False)
        hold_open_palm(gate, t_start=0.0, duration_s=1.5)
        gate.feed_gesture(CLOSED_FIST_GESTURE, now=1.5)
        # Closed fist does NOT trigger toggle when disabled.
        assert gate.state == TrackingState.ACTIVE  # still INACTIVE→ACTIVE via open_palm first
        gate.reset()
        # Now test with disabled closed fist from a clean INACTIVE state.
        assert gate.state == TrackingState.INACTIVE
        gate.feed_gesture(CLOSED_FIST_GESTURE, now=0.0)
        for _ in range(60):
            gate.feed_gesture(CLOSED_FIST_GESTURE, now=0.01 * (_ + 1))
        assert gate.state == TrackingState.INACTIVE

    def test_enabled_when_requested(self) -> None:
        gate = make_gate(hold_duration_s=0.5, enable_closed_fist=True)
        # Hold closed fist for 0.6s.
        for i in range(60):
            gate.feed_gesture(CLOSED_FIST_GESTURE, now=i * 0.01)
        assert gate.state == TrackingState.ACTIVE


# ======================================================================
# Explicit toggle() — keyboard shortcut + tray icon
# ======================================================================

class TestExplicitToggle:
    def test_toggle_flips_state(self) -> None:
        gate = make_gate()
        assert gate.state == TrackingState.INACTIVE
        gate.toggle()
        assert gate.state == TrackingState.ACTIVE
        gate.toggle()
        assert gate.state == TrackingState.INACTIVE

    def test_toggle_clears_in_progress_hold(self) -> None:
        """Calling toggle() while a hold is in progress must cancel
        the hold (so the next hold starts fresh)."""
        gate = make_gate(hold_duration_s=1.0)
        # Begin a partial hold.
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.5)
        assert gate.hold_in_progress is not None
        # Toggle externally.
        gate.toggle()
        assert gate.state == TrackingState.ACTIVE
        assert gate.hold_in_progress is None
        # A subsequent partial hold should NOT auto-toggle back.
        gate.feed_gesture(OPEN_PALM_GESTURE, now=2.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=2.5)
        assert gate.state == TrackingState.ACTIVE

    def test_toggle_with_explicit_method(self) -> None:
        gate = make_gate()
        gate.toggle(ActivationMethod(name='tray_toggle'))
        assert gate.state == TrackingState.ACTIVE


# ======================================================================
# Hold-timer semantics
# ======================================================================

class TestHoldTimerSemantics:
    def test_unknown_gesture_does_not_start_hold(self) -> None:
        gate = make_gate(hold_duration_s=0.5)
        for i in range(60):
            gate.feed_gesture('swipe_right', now=i * 0.01)
        assert gate.state == TrackingState.INACTIVE

    def test_changing_gesture_resets_hold(self) -> None:
        """TRD §5.3: changing qualifying gesture mid-hold resets the
        hold (no partial credit)."""
        gate = make_gate(hold_duration_s=1.0, enable_closed_fist=True)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.4)
        # Switch to closed fist (eligible) — resets hold-start.
        gate.feed_gesture(CLOSED_FIST_GESTURE, now=0.5)
        # Another 0.7s of closed fist — only 0.7s of new hold, not enough.
        for i in range(70):
            gate.feed_gesture(CLOSED_FIST_GESTURE, now=0.5 + i * 0.01)
        assert gate.state == TrackingState.INACTIVE

    def test_boundary_uses_greater_or_equal(self) -> None:
        """TRD §3.10 reference: `>=` boundary (matches StabilityFilter)."""
        gate = make_gate(hold_duration_s=1.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.999)
        assert gate.state == TrackingState.INACTIVE
        gate.feed_gesture(OPEN_PALM_GESTURE, now=1.0)
        assert gate.state == TrackingState.ACTIVE


# ======================================================================
# frame_feed_gestures — frame-level feed for multi-hand fix
# ======================================================================

class TestFrameFeedGestures:
    def test_single_toggle_gesture_starts_hold(self) -> None:
        gate = make_gate(hold_duration_s=1.0)
        gate.frame_feed_gestures([OPEN_PALM_GESTURE], now=0.0)
        assert gate.hold_in_progress is not None
        assert gate.hold_in_progress[0] == OPEN_PALM_GESTURE

    def test_multiple_winners_one_toggle(self) -> None:
        """Non-toggle + toggle: only the toggle gesture is fed."""
        gate = make_gate(hold_duration_s=1.0)
        gate.frame_feed_gestures(['circular_motion', OPEN_PALM_GESTURE], now=0.0)
        assert gate.hold_in_progress is not None
        assert gate.hold_in_progress[0] == OPEN_PALM_GESTURE

    def test_multiple_toggle_gestures_feeds_first(self) -> None:
        """Two toggle gestures: only the first is fed (should be
        impossible in practice, but guard against it)."""
        gate = make_gate(hold_duration_s=1.0, enable_closed_fist=True)
        gate.frame_feed_gestures([OPEN_PALM_GESTURE, CLOSED_FIST_GESTURE], now=0.0)
        assert gate.hold_in_progress is not None
        assert gate.hold_in_progress[0] == OPEN_PALM_GESTURE

    def test_no_toggle_gesture_resets_hold(self) -> None:
        """Only non-toggle gestures resets any in-progress hold."""
        gate = make_gate(hold_duration_s=1.0)
        # Start a hold.
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.0)
        assert gate.hold_in_progress is not None
        # Frame with no toggle gesture resets it.
        gate.frame_feed_gestures(['circular_motion', 'swipe_right'], now=0.5)
        assert gate.hold_in_progress is None

    def test_empty_list_resets_hold(self) -> None:
        """Empty list (no hands detected) resets any in-progress hold."""
        gate = make_gate(hold_duration_s=1.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.0)
        assert gate.hold_in_progress is not None
        gate.frame_feed_gestures([], now=0.5)
        assert gate.hold_in_progress is None

    def test_two_hand_scenario_hold_reaches_toggle(self) -> None:
        """Reproduce the exact multi-hand bug: non-toggle + toggle
        interleaved every frame for 60 frames. The hold timer must
        reach 1.0s and toggle the gate to ACTIVE.

        Before the fix, this scenario would never toggle because
        the per-winner for-loop would reset the hold on the non-toggle
        entry, then restart it on the toggle entry — every frame."""
        gate = make_gate(hold_duration_s=1.0)
        step = 1.0 / 60.0
        now = 0.0
        for _ in range(90):
            gate.frame_feed_gestures(['circular_motion', OPEN_PALM_GESTURE], now)
            now += step
        # After 90 frames (~1.5 s), the hold should have satisfied
        # the 1.0 s duration and toggled the gate.
        assert gate.state == TrackingState.ACTIVE

    def test_two_hand_single_hand_hold_still_works(self) -> None:
        """Single-hand scenario: one toggle gesture per frame, same
        as before the fix."""
        gate = make_gate(hold_duration_s=1.0)
        step = 1.0 / 60.0
        now = 0.0
        for _ in range(70):
            gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
            now += step
        assert gate.state == TrackingState.ACTIVE

    def test_frame_feed_hot_path_never_raises(self) -> None:
        gate = make_gate()
        gate.frame_feed_gestures([], now=0.0)  # empty list — no crash


# ======================================================================
# No flicker on sustained hold — _hold_just_fired release guard
# ======================================================================

class TestNoFlicker:
    """After a hold-based toggle fires, the gate must not re-toggle
    while the user continues holding the same toggle gesture."""

    def test_sustained_hold_does_not_flicker(self) -> None:
        """Hold open_palm for 3.0s — the gate must toggle exactly
        once (at 1.0s) and remain in the new state."""
        gate = make_gate(hold_duration_s=1.0)
        step = 1.0 / 60.0
        now = 0.0
        # Track state transitions by inspecting state before/after.
        states_before: list[TrackingState] = []
        original_toggle = gate._toggle_state

        def tracking_toggle(method, hold_elapsed_ms=None, hold_based=False):
            states_before.append(gate.state)
            original_toggle(method, hold_elapsed_ms=hold_elapsed_ms, hold_based=hold_based)

        gate._toggle_state = tracking_toggle  # type: ignore[method-assign]

        for _ in range(180):  # 3.0 s
            gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
            now += step

        # Exactly one transition occurred (INACTIVE→ACTIVE at 1.0s).
        assert len(states_before) == 1
        assert states_before[0] == TrackingState.INACTIVE
        assert gate.state == TrackingState.ACTIVE

    def test_release_and_rehold_triggers_another_toggle(self) -> None:
        """Toggle → release (non-toggle frame) → re-hold → toggle
        back. The release resets _hold_just_fired so the second
        hold can fire."""
        gate = make_gate(hold_duration_s=1.0)
        step = 1.0 / 60.0
        now = 0.0

        # Hold to toggle INACTIVE → ACTIVE.
        for _ in range(70):
            gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
            now += step
        assert gate.state == TrackingState.ACTIVE

        # Release: non-toggle frame clears _hold_just_fired.
        gate.frame_feed_gestures(['pinch'], now)
        now += step
        assert gate.hold_in_progress is None

        # Re-hold to toggle ACTIVE → INACTIVE.
        for _ in range(70):
            gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
            now += step
        assert gate.state == TrackingState.INACTIVE

    def test_empty_frame_clears_just_fired(self) -> None:
        """An empty frame (no hands) after toggle clears
        _hold_just_fired, allowing a subsequent hold to start."""
        gate = make_gate(hold_duration_s=1.0)
        step = 1.0 / 60.0
        now = 0.0

        # Hold to toggle INACTIVE → ACTIVE.
        for _ in range(70):
            gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
            now += step
        assert gate.state == TrackingState.ACTIVE

        # Empty frame (no hands detected).
        gate.frame_feed_gestures([], now)
        now += step

        # Re-hold should start fresh.
        gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
        assert gate.hold_in_progress is not None

    def test_frame_feed_gestures_ignores_toggle_after_hold_fired(self) -> None:
        """After a hold-based toggle fires, frame_feed_gestures
        must ignore subsequent toggle gestures until a non-toggle
        frame resets _hold_just_fired.

        Uses frame_feed_gestures throughout (the correct path)
        so that _hold_just_fired is both set and checked at the
        frame level."""
        gate = make_gate(hold_duration_s=1.0)
        step = 1.0 / 60.0
        now = 0.0

        # Hold to toggle INACTIVE → ACTIVE via frame_feed_gestures.
        for _ in range(70):
            gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
            now += step
        assert gate.state == TrackingState.ACTIVE
        # _hold_just_fired is now True.

        # Continue feeding toggle gesture — frame_feed_gestures
        # should ignore it (no new hold started).
        gate.frame_feed_gestures([OPEN_PALM_GESTURE], now)
        assert gate.hold_in_progress is None


# ======================================================================
# is_toggle_gesture public method
# ======================================================================

class TestIsToggleGesture:
    def test_open_palm_is_toggle(self) -> None:
        gate = make_gate()
        assert gate.is_toggle_gesture(OPEN_PALM_GESTURE) is True

    def test_fist_not_toggle_when_disabled(self) -> None:
        gate = make_gate(enable_closed_fist=False)
        assert gate.is_toggle_gesture(CLOSED_FIST_GESTURE) is False

    def test_fist_is_toggle_when_enabled(self) -> None:
        gate = make_gate(enable_closed_fist=True)
        assert gate.is_toggle_gesture(CLOSED_FIST_GESTURE) is True

    def test_other_gesture_not_toggle(self) -> None:
        gate = make_gate()
        assert gate.is_toggle_gesture('swipe_right') is False
        assert gate.is_toggle_gesture('pinch') is False


# ======================================================================
# Hot-path-never-raises (RULES §6.4)
# ======================================================================

class TestHotPathNeverRaises:
    def test_feed_gesture_does_not_raise_on_garbage_input(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        gate = make_gate()
        # None, empty string, malformed float — defensive path.
        with caplog.at_level(logging.ERROR, logger='gestureos'):
            gate.feed_gesture('', now=0.0)  # type: ignore[arg-type]
            gate.feed_gesture('open_palm', now=float('nan'))
        # The gate must remain in INACTIVE and the call must return
        # without raising.
        assert gate.state == TrackingState.INACTIVE

    def test_toggle_does_not_raise(self) -> None:
        gate = make_gate()
        # Repeated toggles — must remain stable.
        for _ in range(10):
            gate.toggle()
        # Either ACTIVE or INACTIVE — both are valid stable states.
        assert gate.state in (TrackingState.ACTIVE, TrackingState.INACTIVE)


# ======================================================================
# Reset / lifecycle
# ======================================================================

class TestReset:
    def test_reset_clears_state_to_inactive(self) -> None:
        gate = make_gate()
        gate.toggle()
        assert gate.state == TrackingState.ACTIVE
        gate.reset()
        assert gate.state == TrackingState.INACTIVE

    def test_reset_clears_in_progress_hold(self) -> None:
        gate = make_gate(hold_duration_s=1.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.5)
        assert gate.hold_in_progress is not None
        gate.reset()
        assert gate.hold_in_progress is None


# ======================================================================
# Read-only introspection
# ======================================================================

class TestIntrospection:
    def test_is_active_property(self) -> None:
        gate = make_gate()
        assert gate.is_active is False
        gate.toggle()
        assert gate.is_active is True

    def test_hold_in_progress_when_holding(self) -> None:
        gate = make_gate(hold_duration_s=1.0)
        gate.feed_gesture(OPEN_PALM_GESTURE, now=0.5)
        snap = gate.hold_in_progress
        assert snap is not None
        assert snap[0] == OPEN_PALM_GESTURE
        assert snap[1] == 0.5

    def test_hold_in_progress_none_when_not_holding(self) -> None:
        gate = make_gate()
        assert gate.hold_in_progress is None
        gate.toggle()  # toggles state but does not start a hold
        assert gate.hold_in_progress is None


# ======================================================================
# ActivationMethod dataclass
# ======================================================================

class TestActivationMethod:
    def test_frozen(self) -> None:
        m = ActivationMethod(name='open_palm_hold')
        with pytest.raises((AttributeError, Exception)):
            m.name = 'keyboard_shortcut'  # type: ignore[misc]

    def test_equality(self) -> None:
        a = ActivationMethod(name='tray_toggle')
        b = ActivationMethod(name='tray_toggle')
        c = ActivationMethod(name='open_palm_hold')
        assert a == b
        assert a != c
