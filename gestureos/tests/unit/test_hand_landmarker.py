"""Unit tests for HandLandmarker (tracking/hand_landmarker.py) — CP-1.

Tests cover:
  - MODEL_COMPLEXITY constant is 0 (per user config)
  - HandLandmarker accepts ModelManager for RULES §13.2 compliance (CP-1)
  - Normal detection path with full handedness metadata (Tasks API)
  - No hand detected returns []
  - Handedness metadata missing entirely returns []
  - Handedness count mismatch returns []
  - Malformed hand (< 21 landmarks) is silently skipped
  - MediaPipe exception returns [] and auto-reinit path
  - No model_manager logged error (CP-1 graceful degradation)

Per TRD §13.2: no live camera. MediaPipe results are mocked with
named tuples matching the Tasks API shape.
"""

from __future__ import annotations

import collections
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from models.data_models import HandData
from tracking.hand_landmarker import (
    LANDMARKS_PER_HAND,
    MAX_NUM_HANDS,
    MIN_DETECTION_CONFIDENCE,
    MIN_PRESENCE_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
    REINIT_AFTER_CONSECUTIVE_ERRORS,
    TrackingModule,
)


# ======================================================================
# Mock helpers — Tasks API shape
# ======================================================================

_Landmark = collections.namedtuple('Landmark', ['x', 'y', 'z'])
_Classification = collections.namedtuple('Classification', ['category_name', 'score'])
_Results = collections.namedtuple(
    'Results',
    ['hand_landmarks', 'handedness'],
    defaults=(None, None),
)


def _make_landmarks(count: int = LANDMARKS_PER_HAND) -> list:
    """Build a list of mock landmark objects with .x, .y, .z attributes."""
    return [_Landmark(0.5, 0.5, 0.0) for _ in range(count)]


def _make_handedness(category_name: str = 'Left', score: float = 0.95) -> list:
    """Build a mock handedness entry (list of Classification)."""
    return [_Classification(category_name=category_name, score=score)]


def _make_results(
    hand_count: int = 1,
    handedness_count: int | None = None,
    chirality: str = 'Left',
    confidence: float = 0.95,
    malformed: bool = False,
    hand_landmarks_none: bool = False,
    handedness_none: bool = False,
) -> _Results:
    """Build a mock Tasks API results object.

    Tasks API shape:
        result.hand_landmarks = [list_of_NormalizedLandmark, ...]
        result.handedness    = [list_of_Classification, ...]
    """
    if handedness_count is None:
        handedness_count = hand_count

    hand_landmarks = None if hand_landmarks_none else [
        _make_landmarks(5 if malformed else LANDMARKS_PER_HAND)
        for _ in range(hand_count)
    ]

    handedness = None if handedness_none else [
        _make_handedness(category_name=chirality, score=confidence)
        for _ in range(handedness_count)
    ]

    return _Results(
        hand_landmarks=hand_landmarks,
        handedness=handedness,
    )


# ======================================================================
# Fixture: mock ModelManager
# ======================================================================

@pytest.fixture
def mock_mgr() -> MagicMock:
    """Return a ModelManager mock pre-configured as available."""
    mgr = MagicMock()
    mgr.is_hand_landmarker_available.return_value = True
    return mgr


# ======================================================================
# Construction
# ======================================================================

class TestConstruction:
    """Constants and default construction."""

    def test_model_complexity_removed(self) -> None:
        """MODEL_COMPLEXITY was removed from the Tasks API implementation.
        The old constant no longer exists; lite/full accuracy is baked
        into the .task model bundle."""
        with pytest.raises(ImportError):
            from tracking.hand_landmarker import MODEL_COMPLEXITY  # noqa: F401

    def test_other_constants_preserved(self) -> None:
        assert MAX_NUM_HANDS == 2
        assert MIN_DETECTION_CONFIDENCE == 0.5
        assert MIN_PRESENCE_CONFIDENCE == 0.5
        assert MIN_TRACKING_CONFIDENCE == 0.5
        assert REINIT_AFTER_CONSECUTIVE_ERRORS == 5

    def test_default_construction(self) -> None:
        m = TrackingModule()
        assert m.max_num_hands == MAX_NUM_HANDS
        assert m.min_detection_confidence == MIN_DETECTION_CONFIDENCE
        assert m.min_presence_confidence == MIN_PRESENCE_CONFIDENCE
        assert m.min_tracking_confidence == MIN_TRACKING_CONFIDENCE
        assert not hasattr(m, 'model_complexity')

    def test_construction_with_model_manager(self) -> None:
        mock_mgr = MagicMock()
        m = TrackingModule(model_manager=mock_mgr)
        assert m.model_manager is mock_mgr

    def test_initialize_without_model_manager_logs_and_sets_none(self) -> None:
        m = TrackingModule()
        with patch('tracking.hand_landmarker.logger') as mock_log:
            m.initialize()
        assert m._hands is None
        mock_log.error.assert_called_once()

    def test_initialize_with_mock_model_manager(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.is_hand_landmarker_available.return_value = True
        m = TrackingModule(model_manager=mock_mgr)
        with patch('tracking.hand_landmarker.logger') as mock_log:
            m.initialize()
        # Should forward config to ModelManager.
        mock_mgr.set_hand_landmarker_config.assert_called_once_with(
            num_hands=MAX_NUM_HANDS,
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_presence_confidence=MIN_PRESENCE_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        )
        assert m._hands is True
        mock_log.info.assert_called_once()


# ======================================================================
# Normal detection path
# ======================================================================

class TestNormalDetection:
    """Full handedness metadata — standard path."""

    def test_single_hand_accepted(self, mock_mgr) -> None:
        mock_mgr.process_hand_landmarker.return_value = _make_results(
            hand_count=1, chirality='Right', confidence=0.88,
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 1
        assert out[0].chirality == 'Right'
        assert out[0].confidence == pytest.approx(0.88)

    def test_two_hands_both_accepted(self, mock_mgr) -> None:
        mock_mgr.process_hand_landmarker.return_value = _Results(
            hand_landmarks=[
                _make_landmarks(),
                _make_landmarks(),
            ],
                handedness=[
                    _make_handedness(category_name='Left', score=0.91),
                    _make_handedness(category_name='Right', score=0.87),
                ],
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 2
        assert out[0].chirality == 'Left'
        assert out[1].chirality == 'Right'

    def test_no_hand_detected_returns_empty(self, mock_mgr) -> None:
        mock_mgr.process_hand_landmarker.return_value = _Results(
            hand_landmarks=None,
            handedness=None,
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []

    def test_process_returns_none_returns_empty(self, mock_mgr) -> None:
        mock_mgr.process_hand_landmarker.return_value = None
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []

    def test_per_hand_status_fields_populated(self, mock_mgr) -> None:
        """CP-2 (Tracking Stabilisation): every emitted hand carries
        `status='accepted'`, `status_reason=None`, and
        `tracking_confidence=None` (MediaPipe 0.10.14 does not surface
        a separate tracking score)."""
        mock_mgr.process_hand_landmarker.return_value = _make_results(
            hand_count=2,
            chirality='Left', confidence=0.91,
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 2
        for hand in out:
            assert hand.status == 'accepted'
            assert hand.status_reason is None
            assert hand.tracking_confidence is None


# ======================================================================
# Handedness missing — CP-2 Tracking Stabilisation: per-hand emission
# ======================================================================

class TestHandednessMissing:
    """CP-2 (Tracking Stabilisation): when handedness metadata is
    missing or count-mismatched, emit each hand with `chirality=None`
    and `confidence=0.0` instead of dropping the entire frame.
    This prevents the intermittent "tracked one frame, gone the next"
    perception that the V1.x whole-frame discard produced."""

    def test_hand_landmarks_none_returns_empty(self, mock_mgr) -> None:
        """hand_landmarks=None is still a genuine no-hand frame."""
        mock_mgr.process_hand_landmarker.return_value = _make_results(
            hand_landmarks_none=True,
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []

    def test_handedness_none_emits_hands_with_chirality_none(self, mock_mgr) -> None:
        """handedness=None with valid landmarks → emit hands with
        chirality=None, confidence=0.0, status='accepted'."""
        mock_mgr.process_hand_landmarker.return_value = _make_results(
            hand_count=2, handedness_none=True,
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 2
        for hand in out:
            assert hand.chirality is None
            assert hand.confidence == pytest.approx(0.0)
            assert hand.tracking_confidence is None
            assert hand.status == 'accepted'
            assert hand.status_reason is None

    def test_handedness_partial_missing_emits_all_hands(self, mock_mgr) -> None:
        """2 landmarks with 1 handedness entry → 2 hands with
        chirality=None, 0.0 confidence."""
        mock_mgr.process_hand_landmarker.return_value = _Results(
            hand_landmarks=[_make_landmarks(), _make_landmarks()],
            handedness=[_make_handedness(category_name='Left', score=0.95)],
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 2
        for hand in out:
            assert hand.chirality is None
            assert hand.confidence == pytest.approx(0.0)
            assert hand.status == 'accepted'

    def test_handedness_more_than_landmarks(self, mock_mgr) -> None:
        """1 landmark with 2 handedness entries → 1 hand with
        chirality=None, confidence=0.0 (the extra handedness entries
        are ignored; we iterate the shorter landmarks list)."""
        mock_mgr.process_hand_landmarker.return_value = _Results(
            hand_landmarks=[_make_landmarks()],
            handedness=[
                _make_handedness(category_name='Left', score=0.95),
                _make_handedness(category_name='Right', score=0.85),
            ],
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert len(out) == 1
        assert out[0].chirality is None
        assert out[0].confidence == pytest.approx(0.0)

    def test_malformed_hand_is_skipped(self, mock_mgr) -> None:
        """Malformed hand (<21 landmarks) still silently skipped
        regardless of handedness state."""
        mock_mgr.process_hand_landmarker.return_value = _make_results(
            hand_count=1, malformed=True,
        )
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []


# ======================================================================
# Error path: MediaPipe exception
# ======================================================================

class TestMediaPipeException:
    """Existing behaviour preserved: exception returns empty list and
    increments the consecutive-error counter."""

    def test_exception_returns_empty(self, mock_mgr) -> None:
        mock_mgr.process_hand_landmarker.side_effect = RuntimeError('graph error')
        m = TrackingModule(model_manager=mock_mgr)
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []

    def test_consecutive_errors_triggers_reinit(self, mock_mgr) -> None:
        mock_mgr.process_hand_landmarker.side_effect = RuntimeError('graph error')
        m = TrackingModule(model_manager=mock_mgr, reinit_after_errors=3)
        for _ in range(3):
            out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
            assert out == []
        out = m.detect(np.zeros((720, 1280, 3), dtype=np.uint8))
        assert out == []


# ======================================================================
# Status constants stability
# ======================================================================

class TestStatusConstants:
    def test_status_strings_pinned(self) -> None:
        from tracking.hand_landmarker import (
            REASON_DOMINANT_HAND_MODE,
            REASON_HANDEDNESS_MISSING,
            REASON_MALFORMED_LANDMARKS,
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
