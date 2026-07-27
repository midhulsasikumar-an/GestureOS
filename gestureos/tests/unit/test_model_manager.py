"""Unit tests for ModelManager (models/model_manager.py) — CP-1.

Tests cover (per Implementation Plan §5 Task 1.3):
  - Singleton behaviour (get_instance, reset_instance)
  - load_all / load_gesture_recognizer success and failure
  - load_hand_landmarker success and failure
  - is_gesture_model_available() True/False
  - recognize_gesture with mocked MediaPipe result
  - recognize_gesture returning None on inference error
  - record_inference_failure triggers auto-reload after 3 failures
  - reload_gesture_model recovers from failure
  - Gesture name mapping (TRD §3.8.1)

Per AI Development Guide §11.1: ML model tests must mock ModelManager
and never instantiate real MediaPipe models.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from models.model_manager import (
    MAX_CONSECUTIVE_FAILURES,
    ModelManager,
    _MP_TO_INTERNAL,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    """Ensure each test gets a fresh ModelManager singleton."""
    ModelManager.reset_instance()
    yield
    ModelManager.reset_instance()


@pytest.fixture
def mgr() -> ModelManager:
    """Return a ModelManager with a temp models directory."""
    return ModelManager.get_instance(models_dir=Path('/tmp/gestureos_test_models'))


@contextmanager
def mock_mediapipe():
    """Mock the entire `mediapipe` module so that `import mediapipe as mp`
    inside ModelManager methods returns our fake.

    Must be used *before* calling any ModelManager method that imports
    mediapipe internally.
    """
    fake_mp = MagicMock(name='mediapipe')
    with patch.dict('sys.modules', {'mediapipe': fake_mp}):
        yield fake_mp


# ======================================================================
# Singleton behaviour
# ======================================================================

class TestSingleton:
    def test_get_instance_returns_same_instance(self) -> None:
        a = ModelManager.get_instance()
        b = ModelManager.get_instance()
        assert a is b

    def test_cannot_construct_directly(self) -> None:
        ModelManager.get_instance()  # establish singleton
        with pytest.raises(RuntimeError, match='singleton'):
            ModelManager()

    def test_reset_instance_clears(self) -> None:
        a = ModelManager.get_instance()
        ModelManager.reset_instance()
        b = ModelManager.get_instance()
        assert a is not b

    def test_get_instance_accepts_models_dir(self) -> None:
        path = Path('/tmp/test_models')
        mgr = ModelManager.get_instance(models_dir=path)
        assert mgr.models_dir == path


# ======================================================================
# Gesture recognizer load
# ======================================================================

class TestGestureRecognizerLoad:
    def test_initial_state_is_not_available(self, mgr) -> None:
        assert mgr.is_gesture_model_available() is False

    def test_load_fails_when_file_missing(self, mgr) -> None:
        assert mgr.load_gesture_recognizer() is False
        assert mgr.is_gesture_model_available() is False

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_load_succeeds(self, mock_exists, mgr) -> None:
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.GestureRecognizerOptions.return_value = MagicMock()
            fake_mp.tasks.vision.GestureRecognizer.create_from_options.return_value = MagicMock()
            result = mgr.load_gesture_recognizer()
            assert result is True
            assert mgr.is_gesture_model_available() is True

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_load_failure_sets_unavailable(self, mock_exists, mgr) -> None:
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.GestureRecognizerOptions.side_effect = RuntimeError('model corrupt')
            result = mgr.load_gesture_recognizer()
            assert result is False
            assert mgr.is_gesture_model_available() is False


# ======================================================================
# Hand landmarker load
# ======================================================================

class TestHandLandmarkerLoad:
    def test_initial_state_not_available(self, mgr) -> None:
        assert mgr.is_hand_landmarker_available() is False
        assert mgr.get_hand_landmarker() is None

    def test_load_fails_when_file_missing(self, mgr) -> None:
        assert mgr.load_hand_landmarker() is False
        assert mgr.get_hand_landmarker() is None

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_load_succeeds(self, mock_exists, mgr) -> None:
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.HandLandmarkerOptions.return_value = MagicMock()
            fake_mp.tasks.vision.HandLandmarker.create_from_options.return_value = MagicMock()
            result = mgr.load_hand_landmarker()
            assert result is True
            assert mgr.get_hand_landmarker() is not None
            assert mgr.is_hand_landmarker_available() is True
            # Verify VIDEO mode and all confidence params are passed.
            call_options = fake_mp.tasks.vision.HandLandmarkerOptions.call_args[1]
            assert call_options['running_mode'] == fake_mp.tasks.vision.RunningMode.VIDEO
            assert call_options['num_hands'] == 2
            assert call_options['min_hand_detection_confidence'] == 0.5
            assert call_options['min_hand_presence_confidence'] == 0.5
            assert call_options['min_tracking_confidence'] == 0.5

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_load_failure_returns_none(self, mock_exists, mgr) -> None:
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.HandLandmarkerOptions.side_effect = RuntimeError('model corrupt')
            result = mgr.load_hand_landmarker()
            assert result is False
            assert mgr.get_hand_landmarker() is None


    @patch('models.model_manager.Path.exists', return_value=True)
    def test_load_respects_config(self, mock_exists, mgr) -> None:
        """load_hand_landmarker reads config set by set_hand_landmarker_config."""
        mgr.set_hand_landmarker_config(
            num_hands=1,
            min_detection_confidence=0.3,
            min_presence_confidence=0.4,
            min_tracking_confidence=0.6,
        )
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.HandLandmarkerOptions.return_value = MagicMock()
            fake_mp.tasks.vision.HandLandmarker.create_from_options.return_value = MagicMock()
            mgr.load_hand_landmarker()
            call_options = fake_mp.tasks.vision.HandLandmarkerOptions.call_args[1]
            assert call_options['num_hands'] == 1
            assert call_options['min_hand_detection_confidence'] == 0.3
            assert call_options['min_hand_presence_confidence'] == 0.4
            assert call_options['min_tracking_confidence'] == 0.6


# ======================================================================
# recognize_gesture
# ======================================================================

class TestRecognizeGesture:
    def test_returns_none_when_no_model(self, mgr) -> None:
        result = mgr.recognize_gesture([(0.5, 0.5, 0.0)] * 21)
        assert result is None

    def _load_gesture_model(self, mgr) -> MagicMock:
        """Helper: load a fake gesture model and return the mock model handle."""
        with mock_mediapipe() as fake_mp:
            with patch('models.model_manager.Path.exists', return_value=True):
                fake_mp.tasks.vision.GestureRecognizerOptions.return_value = MagicMock()
                mock_model = MagicMock()
                fake_mp.tasks.vision.GestureRecognizer.create_from_options.return_value = mock_model
                mgr.load_gesture_recognizer()
                return mock_model

    def _set_latest_frame(self, mgr) -> None:
        import numpy as np
        mgr._latest_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    def test_recognize_success(self, mgr) -> None:
        mock_model = self._load_gesture_model(mgr)
        self._set_latest_frame(mgr)

        mock_category = MagicMock()
        mock_category.category_name = 'Open_Palm'
        mock_category.score = 0.92
        mock_result = MagicMock()
        mock_result.gestures = [[mock_category]]
        mock_model.recognize.return_value = mock_result

        result = mgr.recognize_gesture([(0.5, 0.5, 0.0)] * 21)
        assert result is not None
        assert result.gesture_name == 'open_palm'
        assert result.confidence == pytest.approx(0.92)
        assert result.is_dynamic is False
        assert result.source == 'mediapipe'

    def test_recognize_returns_none_on_inference_error(self, mgr) -> None:
        mock_model = self._load_gesture_model(mgr)
        self._set_latest_frame(mgr)

        mock_model.recognize.side_effect = RuntimeError('inference failed')
        result = mgr.recognize_gesture([(0.5, 0.5, 0.0)] * 21)
        assert result is None
        assert mgr.consecutive_failures == 1

    def test_recognize_returns_none_when_no_gestures(self, mgr) -> None:
        mock_model = self._load_gesture_model(mgr)
        self._set_latest_frame(mgr)

        mock_result = MagicMock()
        mock_result.gestures = []
        mock_model.recognize.return_value = mock_result
        result = mgr.recognize_gesture([(0.5, 0.5, 0.0)] * 21)
        assert result is None

    def test_pointing_up_maps_to_one_finger(self, mgr) -> None:
        """Regression: MediaPipe Pointing_Up must route as one_finger
        so the CommandRouter finds the profile mapping. CP-5+ audit fix."""
        mock_model = self._load_gesture_model(mgr)
        self._set_latest_frame(mgr)

        mock_category = MagicMock()
        mock_category.category_name = 'Pointing_Up'
        mock_category.score = 0.90
        mock_result = MagicMock()
        mock_result.gestures = [[mock_category]]
        mock_model.recognize.return_value = mock_result

        result = mgr.recognize_gesture([(0.5, 0.5, 0.0)] * 21)
        assert result is not None
        assert result.gesture_name == 'one_finger', (
            f'Pointing_Up should map to one_finger, got {result.gesture_name!r}'
        )

    def test_gesture_name_mapping_all_entries(self, mgr) -> None:
        mock_model = self._load_gesture_model(mgr)
        self._set_latest_frame(mgr)

        for mp_name, internal_name in _MP_TO_INTERNAL.items():
            mock_category = MagicMock()
            mock_category.category_name = mp_name
            mock_category.score = 0.90
            mock_result = MagicMock()
            mock_result.gestures = [[mock_category]]
            mock_model.recognize.return_value = mock_result

            result = mgr.recognize_gesture([(0.5, 0.5, 0.0)] * 21)
            assert result is not None
            assert result.gesture_name == internal_name, (
                f'MediaPipe class {mp_name!r} should map to '
                f'{internal_name!r}, got {result.gesture_name!r}'
            )


# ======================================================================
# Auto-reload / failure handling (TRD §5.2)
# ======================================================================

class TestAutoReload:
    def _load_gesture_model(self, mgr) -> MagicMock:
        with mock_mediapipe() as fake_mp:
            with patch('models.model_manager.Path.exists', return_value=True):
                fake_mp.tasks.vision.GestureRecognizerOptions.return_value = MagicMock()
                mock_model = MagicMock()
                fake_mp.tasks.vision.GestureRecognizer.create_from_options.return_value = mock_model
                mgr.load_gesture_recognizer()
                return mock_model

    def test_auto_reload_after_3_failures(self, mgr) -> None:
        # First load succeeds via the mock_mediapipe context
        self._load_gesture_model(mgr)

        # The subsequent reload call (inside record_inference_failure) also
        # needs mock_mediapipe active. We set up the context so that the
        # reload also succeeds.
        with mock_mediapipe() as fake_mp:
            with patch('models.model_manager.Path.exists', return_value=True):
                fake_mp.tasks.vision.GestureRecognizerOptions.return_value = MagicMock()
                fake_mp.tasks.vision.GestureRecognizer.create_from_options.return_value = MagicMock()

                for _ in range(MAX_CONSECUTIVE_FAILURES):
                    mgr.record_inference_failure()

                # The reload was attempted inside record_inference_failure,
                # and since the mock returns success, the model should be
                # available again.
                assert mgr.is_gesture_model_available() is True
                assert mgr.consecutive_failures == 0

    def test_auto_reload_failure_goes_to_fallback(self, mgr) -> None:
        self._load_gesture_model(mgr)

        with mock_mediapipe() as fake_mp:
            with patch('models.model_manager.Path.exists', return_value=True):
                # Make the next load attempt fail.
                fake_mp.tasks.vision.GestureRecognizerOptions.side_effect = RuntimeError('reload failed')

                for _ in range(MAX_CONSECUTIVE_FAILURES):
                    mgr.record_inference_failure()

                # After the reload attempt failed, model should be unavailable.
                assert mgr.is_gesture_model_available() is False

    def test_reload_recovers(self, mgr) -> None:
        """reload_gesture_model returns False with no model file."""
        assert mgr.reload_gesture_model() is False
        assert mgr.is_gesture_model_available() is False


# ======================================================================
# load_all
# ======================================================================

class TestLoadAll:
    def test_load_all_no_files(self, mgr) -> None:
        mgr.load_all()  # Should not raise
        assert mgr.is_gesture_model_available() is False
        assert mgr.is_hand_landmarker_available() is False


# ======================================================================
# Shutdown
# ======================================================================

class TestShutdown:
    def test_shutdown_releases_handles(self, mgr) -> None:
        with mock_mediapipe() as fake_mp:
            with patch('models.model_manager.Path.exists', return_value=True):
                fake_mp.tasks.vision.HandLandmarkerOptions.return_value = MagicMock()
                fake_mp.tasks.vision.GestureRecognizerOptions.return_value = MagicMock()
                fake_model = MagicMock()
                fake_mp.tasks.vision.HandLandmarker.create_from_options.return_value = fake_model
                fake_mp.tasks.vision.GestureRecognizer.create_from_options.return_value = fake_model

                mgr.load_all()
                assert mgr.is_hand_landmarker_available() is True
                assert mgr.is_gesture_model_available() is True

                mgr.shutdown()
                assert mgr.is_hand_landmarker_available() is False
                assert mgr.is_gesture_model_available() is False
                assert mgr.consecutive_failures == 0


# ======================================================================
# process_hand_landmarker
# ======================================================================

class TestProcessHandLandmarker:
    """Tests for ModelManager.process_hand_landmarker()."""

    def test_returns_none_when_not_loaded(self, mgr) -> None:
        result = mgr.process_hand_landmarker(
            np.zeros((480, 640, 3), dtype=np.uint8)
        )
        assert result is None

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_returns_result_when_loaded(self, mock_exists, mgr) -> None:
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.HandLandmarkerOptions.return_value = MagicMock()
            mock_detector = MagicMock(name='hand_landmarker')
            fake_mp.tasks.vision.HandLandmarker.create_from_options.return_value = (
                mock_detector
            )
            mgr.load_hand_landmarker()

            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            expected_result = object()
            mock_detector.detect_for_video.return_value = expected_result

            result = mgr.process_hand_landmarker(frame)
            assert result is expected_result
            # Verify mp.Image was created and passed to detect_for_video()
            # with a timestamp (int).
            args, _ = mock_detector.detect_for_video.call_args
            assert args is not None
            assert len(args) == 2
            # First arg is mp.Image mock, second is int timestamp.
            assert isinstance(args[1], int)
            mock_detector.detect_for_video.assert_called_once()

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_inference_error_returns_none(self, mock_exists, mgr) -> None:
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.HandLandmarkerOptions.return_value = MagicMock()
            mock_detector = MagicMock(name='hand_landmarker')
            fake_mp.tasks.vision.HandLandmarker.create_from_options.return_value = (
                mock_detector
            )
            mgr.load_hand_landmarker()

            mock_detector.detect_for_video.side_effect = RuntimeError('inference failed')
            result = mgr.process_hand_landmarker(
                np.zeros((480, 640, 3), dtype=np.uint8)
            )
            assert result is None

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_timestamp_monotonically_increasing(self, mock_exists, mgr) -> None:
        """Timestamps passed to detect_for_video must be strictly increasing."""
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.HandLandmarkerOptions.return_value = MagicMock()
            mock_detector = MagicMock(name='hand_landmarker')
            fake_mp.tasks.vision.HandLandmarker.create_from_options.return_value = (
                mock_detector
            )
            mock_detector.detect_for_video.return_value = object()
            mgr.load_hand_landmarker()

            timestamps: list[int] = []
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            for _ in range(10):
                mgr.process_hand_landmarker(frame)
                call_args = mock_detector.detect_for_video.call_args[0]
                timestamps.append(call_args[1])

            # Every timestamp must be strictly greater than the previous.
            for i in range(1, len(timestamps)):
                assert timestamps[i] > timestamps[i - 1], (
                    f'Timestamp at frame {i} ({timestamps[i]}) is not > '
                    f'frame {i - 1} ({timestamps[i - 1]})'
                )

    @patch('models.model_manager.Path.exists', return_value=True)
    def test_timestamp_reset_on_reload(self, mock_exists, mgr) -> None:
        """Timestamp counter resets after a fresh load_hand_landmarker."""
        with mock_mediapipe() as fake_mp:
            fake_mp.tasks.vision.HandLandmarkerOptions.return_value = MagicMock()
            mock_detector = MagicMock(name='hand_landmarker')
            fake_mp.tasks.vision.HandLandmarker.create_from_options.return_value = (
                mock_detector
            )
            mock_detector.detect_for_video.return_value = object()
            mgr.load_hand_landmarker()

            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            mgr.process_hand_landmarker(frame)
            ts_before = mgr._hl_timestamp_ms

            # Simulate a reload.
            mgr.load_hand_landmarker()
            assert mgr._hl_timestamp_ms == 0


# ======================================================================
# Gesture name mapping constant
# ======================================================================

class TestGestureMapping:
    def test_all_trd_mappings_present(self) -> None:
        """TRD §3.8.1: all 6 MediaPipe classes map to internal names."""
        expected = {
            'Open_Palm': 'open_palm',
            'Closed_Fist': 'fist',
            'Thumb_Up': 'thumbs_up',
            'Thumb_Down': 'thumbs_down',
            'Victory': 'peace_sign',
            'Pointing_Up': 'one_finger',  # CP-5+: normalize to canonical gesture name
        }
        assert _MP_TO_INTERNAL == expected
