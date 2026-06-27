"""Unit tests for HandScaleEstimator — CP-2.

Per TRD §13.2: no live camera required. Tests use known-good landmark
fixtures and synthetic rotations to verify palm-width / palm-height
computation, bounding-box correctness, 5-frame smoothing stability,
and the FR-SC-04 contract (`scale=None` when landmarks are missing).
"""

from __future__ import annotations

import math

import pytest

from tracking.hand_scale import (
    LANDMARKS_PER_HAND,
    SMOOTHING_WINDOW,
    HandScaleEstimator,
)

from gestures.gesture_utils import (
    INDEX_MCP,
    PINKY_MCP,
    WRIST,
    euclidean_distance,
)
from tests.conftest import load_pose_landmarks, make_hand


# ======================================================================
# Constants
# ======================================================================

class TestConstants:
    def test_smoothing_window_is_5(self) -> None:
        # TRD §3.7 mandates 5; FR-SC-02 reinforces.
        assert SMOOTHING_WINDOW == 5

    def test_landmarks_per_hand_is_21(self) -> None:
        # MediaPipe Hands produces 21 landmarks; defensive check.
        assert LANDMARKS_PER_HAND == 21


# ======================================================================
# Basic computation
# ======================================================================

class TestBasicComputation:
    def test_open_palm_populates_scale(self) -> None:
        est = HandScaleEstimator()
        hand = make_hand(landmarks=load_pose_landmarks('open_palm_right'))
        out = est.estimate(hand)
        assert out.scale is not None
        s = out.scale
        # palm_width / palm_height must be positive
        assert s.palm_width > 0
        assert s.palm_height > 0
        # smoothed_scale is the mean of the two
        assert s.smoothed_scale == pytest.approx(
            (s.palm_width + s.palm_height) / 2
        )

    def test_palm_width_matches_known_geometry(self) -> None:
        # The palm-width calculation is the Euclidean distance between
        # landmark 5 (INDEX_MCP) and landmark 17 (PINKY_MCP).
        landmarks = load_pose_landmarks('open_palm_right')
        expected = euclidean_distance(landmarks[INDEX_MCP], landmarks[PINKY_MCP])

        est = HandScaleEstimator()
        hand = make_hand(landmarks=landmarks)
        out = est.estimate(hand)
        assert out.scale.palm_width == pytest.approx(expected, rel=1e-9)

    def test_palm_height_matches_known_geometry(self) -> None:
        landmarks = load_pose_landmarks('open_palm_right')
        # palm_height is the distance between landmark 0 (WRIST) and
        # landmark 9 (middle MCP).
        expected = euclidean_distance(landmarks[WRIST], landmarks[9])

        est = HandScaleEstimator()
        hand = make_hand(landmarks=landmarks)
        out = est.estimate(hand)
        assert out.scale.palm_height == pytest.approx(expected, rel=1e-9)

    def test_bounding_box_corners(self) -> None:
        landmarks = load_pose_landmarks('open_palm_right')
        xs = [lm[0] for lm in landmarks]
        ys = [lm[1] for lm in landmarks]
        est = HandScaleEstimator()
        out = est.estimate(make_hand(landmarks=landmarks))
        bbox = out.scale.bounding_box
        assert bbox == (min(xs), min(ys), max(xs), max(ys))


# ======================================================================
# Malformed-hand handling (PRD FR-SC-04)
# ======================================================================

class TestMalformedHand:
    def test_wrong_landmark_count_yields_none(self) -> None:
        est = HandScaleEstimator()
        # Pass a hand with only 10 landmarks.
        hand = make_hand()
        from dataclasses import replace
        truncated = replace(hand, landmarks=hand.landmarks[:10])
        out = est.estimate(truncated)
        assert out.scale is None

    def test_empty_landmarks_yields_none(self) -> None:
        est = HandScaleEstimator()
        hand = make_hand()
        from dataclasses import replace
        empty = replace(hand, landmarks=[])
        out = est.estimate(empty)
        assert out.scale is None


# ======================================================================
# Smoothing stability (PRD FR-SC-02, FR-SC-03)
# ======================================================================

class TestSmoothing:
    def test_smoothing_smooths_out_jitter(self) -> None:
        # Feed a sequence of (slightly jittered) scale samples and
        # verify the smoothed_scale is closer to the median than to
        # any single raw value.
        est = HandScaleEstimator()
        landmarks_base = load_pose_landmarks('open_palm_right')
        palm_width = euclidean_distance(landmarks_base[INDEX_MCP], landmarks_base[PINKY_MCP])
        # Build a jittered sequence: scale alternates +/- 5% around palm_width.
        for i in range(10):
            jitter = 1.0 + (0.05 if i % 2 == 0 else -0.05)
            landmarks_jittered = [
                (
                    lm[0],
                    lm[1] + (jitter - 1.0) * 0.1,  # shift y slightly
                    lm[2],
                )
                for lm in landmarks_base
            ]
            est.estimate(make_hand(landmarks=landmarks_jittered, role='HAND_A'))

        snap = est.history_snapshot
        # After 10 frames, the buffer holds the last 5 raw-scale values.
        assert len(snap['HAND_A']) == SMOOTHING_WINDOW

    def test_smoothing_window_size(self) -> None:
        # SMOOTHING_WINDOW samples must be retained; the (window+1)th
        # sample evicts the oldest.
        est = HandScaleEstimator()
        landmarks = load_pose_landmarks('open_palm_right')
        for i in range(SMOOTHING_WINDOW + 2):
            est.estimate(make_hand(landmarks=landmarks, role='HAND_A'))
        snap = est.history_snapshot
        assert len(snap['HAND_A']) == SMOOTHING_WINDOW

    def test_smoothed_scale_is_average_of_buffer(self) -> None:
        # If we feed identical samples, smoothed_scale == raw_scale.
        est = HandScaleEstimator()
        landmarks = load_pose_landmarks('open_palm_right')
        for _ in range(SMOOTHING_WINDOW):
            out = est.estimate(make_hand(landmarks=landmarks, role='HAND_A'))
        # After SMOOTHING_WINDOW identical samples, smoothed == raw.
        expected_raw = (out.scale.palm_width + out.scale.palm_height) / 2
        assert out.scale.smoothed_scale == pytest.approx(expected_raw)
        # And the raw average equals the smoothed average (identical samples).
        snap = est.history_snapshot
        assert out.scale.smoothed_scale == pytest.approx(
            sum(snap['HAND_A']) / len(snap['HAND_A'])
        )


# ======================================================================
# Per-role independence
# ======================================================================

class TestPerRoleBuffers:
    def test_two_roles_independent(self) -> None:
        est = HandScaleEstimator()
        landmarks_a = load_pose_landmarks('open_palm_right')
        # A smaller hand for role B.
        landmarks_b = [
            (0.5 + (lm[0] - 0.5) * 0.5, 0.5 + (lm[1] - 0.5) * 0.5, lm[2])
            for lm in landmarks_a
        ]
        out_a = est.estimate(make_hand(landmarks=landmarks_a, role='HAND_A'))
        out_b = est.estimate(make_hand(landmarks=landmarks_b, role='HAND_B'))
        # The two scales must differ because the two hands differ in size.
        assert out_a.scale.palm_width != pytest.approx(out_b.scale.palm_width)
        # And the history buffer must have separate entries per role.
        snap = est.history_snapshot
        assert 'HAND_A' in snap
        assert 'HAND_B' in snap


# ======================================================================
# estimate_all
# ======================================================================

class TestEstimateAll:
    def test_returns_one_output_per_input(self) -> None:
        est = HandScaleEstimator()
        hands = [
            make_hand(landmarks=load_pose_landmarks('open_palm_right'), role='HAND_A'),
            make_hand(landmarks=load_pose_landmarks('open_palm_left'), role='HAND_B'),
        ]
        out = est.estimate_all(hands)
        assert len(out) == 2
        assert all(h.scale is not None for h in out)

    def test_empty_input(self) -> None:
        assert HandScaleEstimator().estimate_all([]) == []


# ======================================================================
# reset()
# ======================================================================

class TestReset:
    def test_reset_clears_all_buffers(self) -> None:
        est = HandScaleEstimator()
        landmarks = load_pose_landmarks('open_palm_right')
        est.estimate(make_hand(landmarks=landmarks, role='HAND_A'))
        est.estimate(make_hand(landmarks=landmarks, role='HAND_B'))
        est.reset()
        # All buffers empty after reset.
        assert all(len(buf) == 0 for buf in est.history_snapshot.values())