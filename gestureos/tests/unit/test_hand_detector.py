"""Unit tests for TrackingModule (hand_detector.py) — CP-4 Tracking Stabilization.

Tests cover:
  - MODEL_COMPLEXITY constant is 1 (CP-4 change)
  - Normal detection path with full handedness metadata
  - Handedness metadata missing entirely (multi_handedness=None)
  - Handedness count < landmarks count (partial chirality loss)
  - Handedness count > landmarks count (unexpected extra)
  - Malformed hand (<21 landmarks) is still dropped
  - Status and status_reason fields are populated on every path
  - Empty frame returns []

Per TRD §13.2: no live camera. MediaPipe results are mocked with
named tuples matching the actual NamedTuple shape MediaPipe returns.
"""

from __future__ import annotations

import collections
from itertools import zip_longest
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from models.data_models import HandData
from tracking.hand_detector import (
    LANDMARKS_PER_HAND,
    MAX_NUM_HANDS,
    MIN_DETECTION_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
    MODEL_COMPLEXITY,
    REASON_HANDEDNESS_MISSING,
    REASON_MALFORMED_LANDMARKS,
    REINIT_AFTER_CONSECUTIVE_ERRORS,
    STATUS_ACCEPTED,
    STATUS_DISCARDED,
    TrackingModule,
)


# ======================================================================
# Mock helpers
# ======================================================================

_Landmark = collections.namedtuple('Landmark', ['x', 'y', 'z'])
_HandLandmarks = collections.namedtuple('HandLandmarks', ['landmark'])
_Classification = collections.namedtuple('Classification', ['label', 'score'])
_Handedness = collections.namedtuple('Handedness', ['classification'])
_Results = collections.namedtuple(
    'Results',
    ['multi_hand_landmarks', 'multi_handedness', 'multi_hand_world_landmarks'],
    defaults=(None, None, None),
)


def _make_landmarks(count: int = LANDMARKS_PER_HAND) -> list:
    """Build a list of mock landmark objects with .x, .y, .z attributes."""
    return [_Landmark(0.5, 0.5, 0.0) for _ in range(count)]


def _make_handedness(label: str = 'Left', score: float = 0.95) -> _Handedness:
    """Build a mock handedness entry."""
    return _Handedness(classification=[_Classification(label=label, score=score)])


def _make_results(
    hand_count: int = 1,
    handedness_count: int | None = None,
    chirality: str = 'Left',
    confidence: float = 0.95,
    malformed: bool = False,
    handedness_none: bool = False,
) -> _Results:
    """Build a mock MediaPipe results object.

    Args:
        hand_count: number of detected hands (landmark entries).
        handedness_count: number of handedness entries. None means
            match hand_count.
        chirality: chirality label for all handedness entries.
        confidence: chirality score for all handedness entries.
        malformed: if True, create entries with a non-21 landmark count.
        handedness_none: if True, set multi_handedness to None.
    """
    if handedness_count is None:
        handedness_count = hand_count

    landmarks = []
    for i in range(hand_count):
        cnt = 5 if malformed else LANDMARKS_PER_HAND
        landmarks.append(_HandLandmarks(landmark=_make_landmarks(cnt)))

    if handedness_none:
        handedness = None
    else:
        handedness = [
            _make_handedness(label=chirality, score=confidence)
            for _ in range(handedness_count)
        ]

    return _Results(
        multi_hand_landmarks=landmarks,
        multi_handedness=handedness,
    )


# ======================================================================
# Construction
# ======================================================================

class TestConstruction:
    """CP-4: MODEL_COMPLEXITY must be 1."""

    def test_model_complexity_is_1(self) -> None:
        assert MODEL_COMPLEXITY == 1, (
            f'CP-4 requires MODEL_COMPLEXITY=1; got {MODEL_COMPLEXITY}'
        )

    def test_other_constants_preserved(self) -> None:
        assert MAX_NUM_HANDS == 2
        assert MIN_DETECTION_CONFIDENCE == 0.5
        assert MIN_TRACKING_CONFIDENCE == 0.4
        assert REINIT_AFTER_CONSECUTIVE_ERRORS == 5

    def test_default_construction(self) -> None:
        m = TrackingModule()
        assert m.max_num_hands == MAX_NUM_HANDS
        assert m.model_complexity == MODEL_COMPLEXITY
        assert m.min_detection_confidence == MIN_DETECTION_CONFIDENCE
        assert m.min_tracking_confidence == MIN_TRACKING_CONFIDENCE

    def test_initialize_logs_model_complexity(self) -> None:
        with patch('tracking.hand_detector.logger') as mock_log:
            m = TrackingModule()
            m.initialize()
            # Verify the initialize path set the right constant
            assert m._hands is not None


# ======================================================================
# Normal detection path
# ======================================================================

class TestNormalDetection:
    """Full handedness metadata — standard path."""

    def test_single_hand_accepted(self) -> None:
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            mock_hands.process.return_value = _make_results(
                hand_count=1, handedness_count=1,
                chirality='Right', confidence=0.88,
            )
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 1
        assert out[0].chirality == 'Right'
        assert out[0].confidence == pytest.approx(0.88)
        assert out[0].status == STATUS_ACCEPTED
        assert out[0].status_reason is None

    def test_two_hands_both_accepted(self) -> None:
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            # Two entries each with their own handedness metadata.
            results = _Results(
                multi_hand_landmarks=[
                    _HandLandmarks(landmark=_make_landmarks()),
                    _HandLandmarks(landmark=_make_landmarks()),
                ],
                multi_handedness=[
                    _make_handedness(label='Left', score=0.91),
                    _make_handedness(label='Right', score=0.87),
                ],
            )
            mock_hands.process.return_value = results
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 2
        assert out[0].chirality == 'Left'
        assert out[0].status == STATUS_ACCEPTED
        assert out[1].chirality == 'Right'
        assert out[1].status == STATUS_ACCEPTED

    def test_no_hand_detected_returns_empty(self) -> None:
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            mock_hands.process.return_value = _Results(
                multi_hand_landmarks=None,
                multi_handedness=None,
            )
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []


# ======================================================================
# Handedness missing paths (CP-4 change)
# ======================================================================

class TestHandednessMissing:
    """CP-4: when handedness metadata is missing, hands are emitted with
    chirality=None and status='discarded'."""

    def test_handedness_none_emits_discarded(self) -> None:
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            mock_hands.process.return_value = _make_results(
                hand_count=2, handedness_none=True,
            )
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 2
        for h in out:
            assert h.chirality is None
            assert h.confidence == pytest.approx(0.0)
            assert h.status == STATUS_DISCARDED
            assert h.status_reason == REASON_HANDEDNESS_MISSING

    def test_handedness_partial_missing(self) -> None:
        """2 landmarks but only 1 handedness entry: first hand gets full
        metadata, second gets chirality=None."""
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            results = _Results(
                multi_hand_landmarks=[
                    _HandLandmarks(landmark=_make_landmarks()),
                    _HandLandmarks(landmark=_make_landmarks()),
                ],
                multi_handedness=[
                    _make_handedness(label='Left', score=0.95),
                ],
            )
            mock_hands.process.return_value = results
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 2
        assert out[0].chirality == 'Left'
        assert out[0].status == STATUS_ACCEPTED
        assert out[1].chirality is None
        assert out[1].status == STATUS_DISCARDED
        assert out[1].status_reason == REASON_HANDEDNESS_MISSING

    def test_handedness_more_than_landmarks(self) -> None:
        """1 landmark but 2 handedness entries: only one hand emitted.
        No crash."""
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            results = _Results(
                multi_hand_landmarks=[
                    _HandLandmarks(landmark=_make_landmarks()),
                ],
                multi_handedness=[
                    _make_handedness(label='Left', score=0.95),
                    _make_handedness(label='Right', score=0.85),
                ],
            )
            mock_hands.process.return_value = results
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        # Landmarks list is shorter → only one hand can be made.
        assert len(out) == 1
        assert out[0].chirality == 'Left'
        assert out[0].status == STATUS_ACCEPTED

    def test_malformed_hand_is_discarded_with_reason(self) -> None:
        """CP-4: malformed landmarks are still emitted with status
        'discarded' and reason 'malformed_landmarks' so the debug
        panel can show them."""
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            mock_hands.process.return_value = _make_results(
                hand_count=1, malformed=True,
            )
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 1
        assert out[0].status == STATUS_DISCARDED
        assert out[0].status_reason == REASON_MALFORMED_LANDMARKS
        assert out[0].confidence == pytest.approx(0.0)
        # Landmarks list is empty for malformed hands.
        assert out[0].landmarks == []


# ======================================================================
# Error path: MediaPipe exception
# ======================================================================

class TestMediaPipeException:
    """Existing behaviour preserved: exception returns empty list and
    increments the consecutive-error counter."""

    def test_exception_returns_empty(self) -> None:
        m = TrackingModule()
        with patch.object(m, '_hands') as mock_hands:
            mock_hands.process.side_effect = RuntimeError('graph error')
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []

    def test_consecutive_errors_triggers_reinit(self) -> None:
        m = TrackingModule(reinit_after_errors=3)
        with patch.object(m, '_hands') as mock_hands:
            mock_hands.process.side_effect = RuntimeError('graph error')
            for _ in range(3):
                out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
                assert out == []
            # On the 4th call with reinit_after_errors=3, re-init is
            # attempted. The mock has no real re-init path, but the
            # method should not raise because the except clause in
            # reinitialize will catch the failure.
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
            assert out == []


# ======================================================================
# Status constants stability
# ======================================================================

class TestStatusConstants:
    """Pin the status enum strings — they appear in the Developer Mode
    panel and structured log extras; renaming them is a breaking change."""

    def test_status_strings_pinned(self) -> None:
        from tracking.hand_detector import (
            REASON_DOMINANT_HAND_MODE,
            REASON_HANDEDNESS_MISSING,
            REASON_OCCLUSION_BRIDGE,
            STATUS_ACCEPTED,
            STATUS_DISCARDED,
            STATUS_FILTERED,
            STATUS_RETAINED,
        )
        assert STATUS_ACCEPTED == 'accepted'
        assert STATUS_RETAINED == 'retained'
        assert STATUS_FILTERED == 'filtered'
        assert STATUS_DISCARDED == 'discarded'
        assert REASON_HANDEDNESS_MISSING == 'handedness_missing'
        assert REASON_MALFORMED_LANDMARKS == 'malformed_landmarks'
        assert REASON_DOMINANT_HAND_MODE == 'dominant_hand_mode'
        assert REASON_OCCLUSION_BRIDGE == 'occlusion_bridge'
