"""Unit tests for MotionHistoryService — CP-2.

Per TRD §13.2: no live camera required. Tests feed synthetic (x, y,
timestamp) tuples into the buffer and verify FIFO eviction, raw
(unnormalized) storage (PRD FR-MH-03), per-role independence, and the
`clear()` / `reset()` lifecycle.
"""

from __future__ import annotations

import pytest

from gestures.motion_history_service import (
    DEFAULT_MAX_FRAMES,
    DEFAULT_ROLES,
    MotionHistoryService,
)


# ======================================================================
# Construction
# ======================================================================

class TestConstruction:
    def test_default_max_frames(self) -> None:
        buf = MotionHistoryService()
        assert buf.max_frames == DEFAULT_MAX_FRAMES

    def test_default_roles_allocated(self) -> None:
        buf = MotionHistoryService()
        # Per the TRD §4.5 reference, the buffer pre-allocates HAND_A
        # and HAND_B so the first frame does not allocate a deque.
        assert 'HAND_A' in buf.roles()
        assert 'HAND_B' in buf.roles()

    def test_custom_max_frames(self) -> None:
        buf = MotionHistoryService(max_frames=5)
        assert buf.max_frames == 5

    def test_custom_roles(self) -> None:
        buf = MotionHistoryService(roles=('LEFT', 'RIGHT'))
        assert buf.roles() == ['LEFT', 'RIGHT']

    def test_invalid_max_frames_raises(self) -> None:
        with pytest.raises(ValueError):
            MotionHistoryService(max_frames=0)
        with pytest.raises(ValueError):
            MotionHistoryService(max_frames=-1)


# ======================================================================
# Update / get
# ======================================================================

class TestUpdate:
    def test_single_sample_round_trips(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.3, 0.4), now=0.0)
        samples = buf.get('HAND_A')
        assert len(samples) == 1
        x, y, t_ms = samples[0]
        assert x == pytest.approx(0.3)
        assert y == pytest.approx(0.4)
        assert t_ms == pytest.approx(0.0)  # now=0.0 -> 0 ms

    def test_timestamp_in_milliseconds(self) -> None:
        # `now` is in seconds; storage is in milliseconds.
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.0, 0.0), now=1.5)
        _, _, t_ms = buf.get('HAND_A')[0]
        assert t_ms == pytest.approx(1500.0)

    def test_3d_input_drops_z(self) -> None:
        # The buffer stores (x, y, timestamp_ms). 3D input has its z
        # component dropped (motion-history is 2D by design).
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.3, 0.4, 0.99), now=0.0)
        x, y, _ = buf.get('HAND_A')[0]
        assert x == pytest.approx(0.3)
        assert y == pytest.approx(0.4)

    def test_role_auto_creation(self) -> None:
        # Updating a role that wasn't pre-allocated creates its deque.
        buf = MotionHistoryService(roles=('HAND_A',))
        buf.update('HAND_C', (0.0, 0.0), now=0.0)
        assert 'HAND_C' in buf.roles()
        assert len(buf.get('HAND_C')) == 1


# ======================================================================
# Capacity / FIFO eviction (PRD FR-MH-02)
# ======================================================================

class TestCapacity:
    def test_eviction_beyond_capacity(self) -> None:
        buf = MotionHistoryService(max_frames=3)
        # Push 5 samples; only the last 3 should remain.
        for i in range(5):
            buf.update('HAND_A', (float(i), 0.0), now=i / 30.0)
        samples = buf.get('HAND_A')
        assert len(samples) == 3
        # First remaining sample should be the 3rd one pushed (i=2).
        assert samples[0][0] == pytest.approx(2.0)
        assert samples[-1][0] == pytest.approx(4.0)

    def test_capacity_is_per_role(self) -> None:
        # Each role has its own independent deque; full on one role
        # must NOT evict samples from another.
        buf = MotionHistoryService(max_frames=2)
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        buf.update('HAND_A', (0.1, 0.0), now=0.1)
        buf.update('HAND_A', (0.2, 0.0), now=0.2)  # evicts (0.0, 0.0)
        buf.update('HAND_B', (1.0, 1.0), now=0.3)
        assert len(buf.get('HAND_A')) == 2
        assert len(buf.get('HAND_B')) == 1
        assert buf.get('HAND_A')[0][0] == pytest.approx(0.1)
        assert buf.get('HAND_B')[0][0] == pytest.approx(1.0)

    def test_unbounded_growth_blocked(self) -> None:
        # The PRD FR-MH-02 invariant: memory usage must not grow
        # unbounded. Push 1000 samples; len must stay at capacity.
        buf = MotionHistoryService(max_frames=20)
        for i in range(1000):
            buf.update('HAND_A', (float(i), 0.0), now=i / 30.0)
        assert len(buf.get('HAND_A')) == 20
        # Total sample count (across all roles) is also bounded.
        assert len(buf) == 20


# ======================================================================
# Raw (unnormalized) storage — PRD FR-MH-03
# ======================================================================

class TestRawUnnormalizedStorage:
    def test_storage_does_not_normalize(self) -> None:
        # PRD FR-MH-03: storage is raw; normalization happens at read
        # time. Push a sample whose (x, y) is large; it must be stored
        # verbatim, not divided by any implicit scale.
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.95, 0.95), now=0.0)
        x, y, _ = buf.get('HAND_A')[0]
        assert x == pytest.approx(0.95)
        assert y == pytest.approx(0.95)

    def test_storage_does_not_normalize_against_scale_argument(self) -> None:
        # The buffer takes (wrist_pos, now) and never sees a hand_scale
        # argument. Storage is definitively raw.
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.123, 0.456), now=0.0)
        x, y, _ = buf.get('HAND_A')[0]
        # If the buffer were secretly normalizing by something, x and y
        # would have been mutated. They must not.
        assert x == pytest.approx(0.123)
        assert y == pytest.approx(0.456)


# ======================================================================
# clear / reset
# ======================================================================

class TestClear:
    def test_clear_single_role(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        buf.update('HAND_B', (1.0, 1.0), now=0.0)
        buf.clear('HAND_A')
        assert buf.get('HAND_A') == []
        assert len(buf.get('HAND_B')) == 1

    def test_clear_unknown_role_is_safe(self) -> None:
        buf = MotionHistoryService()
        buf.clear('NEVER_SEEN')  # must not raise

    def test_reset_clears_all_roles(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        buf.update('HAND_B', (1.0, 1.0), now=0.0)
        buf.reset()
        assert buf.get('HAND_A') == []
        assert buf.get('HAND_B') == []


# ======================================================================
# get_window — CP-2 (Tracking Stabilisation), TRD §3.7
# ======================================================================

class TestGetWindow:
    """Time-windowed query (TRD §3.7 MotionHistoryService.get_window)."""

    def test_empty_role_returns_empty(self) -> None:
        buf = MotionHistoryService()
        assert buf.get_window('HAND_A', 200) == []

    def test_unknown_role_returns_empty(self) -> None:
        buf = MotionHistoryService()
        assert buf.get_window('NEVER_SEEN', 200) == []

    def test_negative_duration_returns_empty(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.5, 0.5), now=0.0)
        assert buf.get_window('HAND_A', -1) == []

    def test_zero_duration_returns_most_recent(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.3, 0.4), now=0.0)
        buf.update('HAND_A', (0.5, 0.6), now=0.1)
        window = buf.get_window('HAND_A', 0)
        assert len(window) == 1
        assert window[0][0] == pytest.approx(0.5)

    def test_wide_window_returns_all_samples(self) -> None:
        buf = MotionHistoryService(max_frames=10)
        for i in range(5):
            buf.update('HAND_A', (float(i) / 10, 0.5), now=i / 30.0)
        # 5 samples spanning ~133ms (4/30 = 0.133s). A 500ms window
        # should return all 5.
        window = buf.get_window('HAND_A', 500)
        assert len(window) == 5

    def test_narrow_window_returns_subset(self) -> None:
        buf = MotionHistoryService(max_frames=10)
        # Push samples with increasing timestamps.
        for i in range(6):
            buf.update('HAND_A', (float(i) / 10, 0.5), now=i / 30.0)
        # 6 samples over 167ms (5/30 = 0.167s). A 50ms window from
        # the most recent (0.167s) should include only the last 1–2
        # samples.
        window = buf.get_window('HAND_A', 50)
        assert 1 <= len(window) <= 2
        # The most recent sample's x should be 0.5 (i=5).
        assert window[-1][0] == pytest.approx(0.5)

    def test_window_is_deterministic(self) -> None:
        """Same buffer + same duration → same result regardless
        of when the caller invokes the method (window is measured
        against the buffer's most-recent sample, not time.time())."""
        buf = MotionHistoryService(max_frames=10)
        for i in range(4):
            buf.update('HAND_A', (float(i) / 10, 0.5), now=i / 30.0)
        r1 = buf.get_window('HAND_A', 80)
        r2 = buf.get_window('HAND_A', 80)
        assert r1 == r2


# ======================================================================
# get_hold_duration — CP-2 (Tracking Stabilisation), TRD §3.7
# ======================================================================

class TestGetHoldDuration:
    """Time-since-first-sample (TRD §3.7 MotionHistoryService.get_hold_duration)."""

    def test_empty_role_returns_zero(self) -> None:
        buf = MotionHistoryService()
        assert buf.get_hold_duration('HAND_A') == pytest.approx(0.0)

    def test_unknown_role_returns_zero(self) -> None:
        buf = MotionHistoryService()
        assert buf.get_hold_duration('NEVER_SEEN') == pytest.approx(0.0)

    def test_single_sample_returns_zero(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.5, 0.5), now=1.0)
        assert buf.get_hold_duration('HAND_A') == pytest.approx(0.0)

    def test_two_samples_returns_delta(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.5, 0.5), now=1.0)
        buf.update('HAND_A', (0.6, 0.6), now=1.5)
        # Duration = 1.5 - 1.0 = 0.5 seconds
        assert buf.get_hold_duration('HAND_A') == pytest.approx(0.5)

    def test_multiple_samples_longer_duration(self) -> None:
        buf = MotionHistoryService(max_frames=10)
        buf.update('HAND_A', (0.5, 0.5), now=0.0)
        buf.update('HAND_A', (0.6, 0.6), now=0.2)
        buf.update('HAND_A', (0.7, 0.7), now=0.5)
        buf.update('HAND_A', (0.8, 0.8), now=1.0)
        # Duration = 1.0 - 0.0 = 1.0 second
        assert buf.get_hold_duration('HAND_A') == pytest.approx(1.0)

    def test_per_role_independence(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.5, 0.5), now=0.0)
        buf.update('HAND_B', (0.9, 0.9), now=2.0)
        buf.update('HAND_A', (0.6, 0.6), now=3.0)
        # HAND_A duration = 3.0 - 0.0 = 3.0 seconds
        # HAND_B duration = 2.0 - 2.0 = 0.0 seconds (single sample)
        assert buf.get_hold_duration('HAND_A') == pytest.approx(3.0)
        assert buf.get_hold_duration('HAND_B') == pytest.approx(0.0)

class TestIntrospection:
    def test_get_returns_fresh_copy(self) -> None:
        # The returned list is a fresh copy; mutating it must not
        # affect the underlying deque.
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        samples = buf.get('HAND_A')
        samples.clear()
        assert len(buf.get('HAND_A')) == 1

    def test_snapshot_isolates_roles(self) -> None:
        buf = MotionHistoryService()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        snap = buf.snapshot()
        snap['HAND_A'].clear()
        assert len(buf.get('HAND_A')) == 1

    def test_get_unknown_role_returns_empty(self) -> None:
        buf = MotionHistoryService()
        assert buf.get('NEVER_SEEN') == []

    def test_default_roles_constant(self) -> None:
        # Pin the public constant.
        assert DEFAULT_ROLES == ('HAND_A', 'HAND_B')