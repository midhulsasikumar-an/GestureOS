"""Unit tests for MotionHistoryBuffer — CP-2.

Per TRD §13.2: no live camera required. Tests feed synthetic (x, y,
timestamp) tuples into the buffer and verify FIFO eviction, raw
(unnormalized) storage (PRD FR-MH-03), per-role independence, and the
`clear()` / `reset()` lifecycle.
"""

from __future__ import annotations

import pytest

from gestures.motion_history import (
    DEFAULT_MAX_FRAMES,
    DEFAULT_ROLES,
    MotionHistoryBuffer,
)


# ======================================================================
# Construction
# ======================================================================

class TestConstruction:
    def test_default_max_frames(self) -> None:
        buf = MotionHistoryBuffer()
        assert buf.max_frames == DEFAULT_MAX_FRAMES

    def test_default_roles_allocated(self) -> None:
        buf = MotionHistoryBuffer()
        # Per the TRD §4.5 reference, the buffer pre-allocates HAND_A
        # and HAND_B so the first frame does not allocate a deque.
        assert 'HAND_A' in buf.roles()
        assert 'HAND_B' in buf.roles()

    def test_custom_max_frames(self) -> None:
        buf = MotionHistoryBuffer(max_frames=5)
        assert buf.max_frames == 5

    def test_custom_roles(self) -> None:
        buf = MotionHistoryBuffer(roles=('LEFT', 'RIGHT'))
        assert buf.roles() == ['LEFT', 'RIGHT']

    def test_invalid_max_frames_raises(self) -> None:
        with pytest.raises(ValueError):
            MotionHistoryBuffer(max_frames=0)
        with pytest.raises(ValueError):
            MotionHistoryBuffer(max_frames=-1)


# ======================================================================
# Update / get
# ======================================================================

class TestUpdate:
    def test_single_sample_round_trips(self) -> None:
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.3, 0.4), now=0.0)
        samples = buf.get('HAND_A')
        assert len(samples) == 1
        x, y, t_ms = samples[0]
        assert x == pytest.approx(0.3)
        assert y == pytest.approx(0.4)
        assert t_ms == pytest.approx(0.0)  # now=0.0 -> 0 ms

    def test_timestamp_in_milliseconds(self) -> None:
        # `now` is in seconds; storage is in milliseconds.
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.0, 0.0), now=1.5)
        _, _, t_ms = buf.get('HAND_A')[0]
        assert t_ms == pytest.approx(1500.0)

    def test_3d_input_drops_z(self) -> None:
        # The buffer stores (x, y, timestamp_ms). 3D input has its z
        # component dropped (motion-history is 2D by design).
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.3, 0.4, 0.99), now=0.0)
        x, y, _ = buf.get('HAND_A')[0]
        assert x == pytest.approx(0.3)
        assert y == pytest.approx(0.4)

    def test_role_auto_creation(self) -> None:
        # Updating a role that wasn't pre-allocated creates its deque.
        buf = MotionHistoryBuffer(roles=('HAND_A',))
        buf.update('HAND_C', (0.0, 0.0), now=0.0)
        assert 'HAND_C' in buf.roles()
        assert len(buf.get('HAND_C')) == 1


# ======================================================================
# Capacity / FIFO eviction (PRD FR-MH-02)
# ======================================================================

class TestCapacity:
    def test_eviction_beyond_capacity(self) -> None:
        buf = MotionHistoryBuffer(max_frames=3)
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
        buf = MotionHistoryBuffer(max_frames=2)
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
        buf = MotionHistoryBuffer(max_frames=20)
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
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.95, 0.95), now=0.0)
        x, y, _ = buf.get('HAND_A')[0]
        assert x == pytest.approx(0.95)
        assert y == pytest.approx(0.95)

    def test_storage_does_not_normalize_against_scale_argument(self) -> None:
        # The buffer takes (wrist_pos, now) and never sees a hand_scale
        # argument. Storage is definitively raw.
        buf = MotionHistoryBuffer()
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
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        buf.update('HAND_B', (1.0, 1.0), now=0.0)
        buf.clear('HAND_A')
        assert buf.get('HAND_A') == []
        assert len(buf.get('HAND_B')) == 1

    def test_clear_unknown_role_is_safe(self) -> None:
        buf = MotionHistoryBuffer()
        buf.clear('NEVER_SEEN')  # must not raise

    def test_reset_clears_all_roles(self) -> None:
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        buf.update('HAND_B', (1.0, 1.0), now=0.0)
        buf.reset()
        assert buf.get('HAND_A') == []
        assert buf.get('HAND_B') == []


# ======================================================================
# Read-only introspection
# ======================================================================

class TestIntrospection:
    def test_get_returns_fresh_copy(self) -> None:
        # The returned list is a fresh copy; mutating it must not
        # affect the underlying deque.
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        samples = buf.get('HAND_A')
        samples.clear()
        assert len(buf.get('HAND_A')) == 1

    def test_snapshot_isolates_roles(self) -> None:
        buf = MotionHistoryBuffer()
        buf.update('HAND_A', (0.0, 0.0), now=0.0)
        snap = buf.snapshot()
        snap['HAND_A'].clear()
        assert len(buf.get('HAND_A')) == 1

    def test_get_unknown_role_returns_empty(self) -> None:
        buf = MotionHistoryBuffer()
        assert buf.get('NEVER_SEEN') == []

    def test_default_roles_constant(self) -> None:
        # Pin the public constant.
        assert DEFAULT_ROLES == ('HAND_A', 'HAND_B')