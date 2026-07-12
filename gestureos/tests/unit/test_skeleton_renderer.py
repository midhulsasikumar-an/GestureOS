"""Unit tests for skeleton_renderer.py — CP-2 mirror support.

Tests cover:
  - _denormalize with mirror=False (default)
  - _denormalize with mirror=True
  - render_skeleton mirror=False preserves existing behaviour
  - render_skeleton mirror=True mirrors x pixel positions
"""

from __future__ import annotations

import numpy as np

from models.data_models import HandData
from overlay.skeleton_renderer import _denormalize, render_skeleton


# ======================================================================
# _denormalize
# ======================================================================

class TestDenormalize:
    """Normalised → pixel-space coordinate conversion."""

    def test_default_no_mirror(self) -> None:
        pts = _denormalize([(0.25, 0.50, 0.0), (0.75, 0.50, 0.0)], 800, 600)
        assert pts == [(200, 300), (600, 300)]

    def test_mirror_flips_x(self) -> None:
        pts = _denormalize([(0.25, 0.50, 0.0)], 800, 600, mirror=True)
        # 0.25 → (1 - 0.25) * 800 = 600
        assert pts == [(600, 300)]

    def test_mirror_left_becomes_right(self) -> None:
        """x=0.1 (far left) becomes far right when mirrored."""
        pts = _denormalize([(0.1, 0.5, 0.0)], 1000, 500, mirror=True)
        assert pts == [(900, 250)]

    def test_mirror_edge_cases(self) -> None:
        pts = _denormalize(
            [(0.0, 0.5, 0.0), (1.0, 0.5, 0.0)],
            800, 600, mirror=True,
        )
        # x=0.0 → (1-0) * 800 = 800
        # x=1.0 → (1-1) * 800 = 0
        assert pts == [(800, 300), (0, 300)]

    def test_y_unchanged_when_mirroring(self) -> None:
        """mirror=True must not affect y-coordinates."""
        pts = _denormalize([(0.3, 0.7, 0.0)], 640, 480, mirror=True)
        assert pts[0][1] == int(round(0.7 * 480))


# ======================================================================
# render_skeleton — mirror parameter
# ======================================================================

class TestRenderSkeletonMirror:
    """Functional tests on an actual small frame."""

    SAMPLE_LMS = [(0.2, 0.3, 0.0) for _ in range(21)]

    def make_hand(self, landmarks=None) -> HandData:
        lms = landmarks if landmarks is not None else self.SAMPLE_LMS
        return HandData(
            landmarks=lms,
            chirality='Left',
            confidence=0.95,
        )

    def test_no_mirror_renders_at_original_x(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        hand = self.make_hand()
        render_skeleton(frame, [hand], mirror=False)
        # The wrist (landmark[0]) at x=0.2 → 0.2 * 200 = 40 should
        # be drawn. Check a 5×5 region around (40, 30) for non-zero.
        wrist_patch = frame[25:35, 35:45]
        assert np.any(wrist_patch > 0)

    def test_mirror_renders_at_flipped_x(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        hand = self.make_hand()
        render_skeleton(frame, [hand], mirror=True)
        # Wrist at x=0.2 → mirrored x = (1-0.2) * 200 = 160.
        wrist_patch = frame[25:35, 155:165]
        assert np.any(wrist_patch > 0), \
            "mirror=True should render skeleton at mirrored x positions"

    def test_mirror_originally_left_now_right(self) -> None:
        """A hand at x=0.1 (far left) renders near the right edge
        when mirror=True."""
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        left_lms = [(0.1, 0.5, 0.0) for _ in range(21)]
        hand = self.make_hand(left_lms)
        render_skeleton(frame, [hand], mirror=True)
        # Mirrored x = (1-0.1) * 200 = 180
        wrist_patch = frame[45:55, 175:185]
        assert np.any(wrist_patch > 0)

    def test_no_mirror_and_mirror_produce_different_positions(self) -> None:
        """Same landmarks produce different pixel positions with and
        without mirror, confirming the mirror flag is active."""
        frame_a = np.zeros((100, 200, 3), dtype=np.uint8)
        frame_b = np.zeros((100, 200, 3), dtype=np.uint8)
        hand = self.make_hand()
        render_skeleton(frame_a, [hand], mirror=False)
        render_skeleton(frame_b, [hand], mirror=True)
        assert not np.array_equal(frame_a, frame_b)

    def test_malformed_hand_skipped(self) -> None:
        """Hand with ≠21 landmarks should be skipped regardless of mirror."""
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        bad_hand = self.make_hand([(0.5, 0.5, 0.0)])  # only 1 landmark
        render_skeleton(frame, [bad_hand], mirror=True)
        assert np.all(frame == 0)
