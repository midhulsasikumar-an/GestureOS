"""ModelManager — sole owner of all ML model handles.

Implements TRD §3.15 (ModelManager) and AI Development Guide §8
(ML Model Integration Standards). The V1 permitted models are
exactly two: the MediaPipe Hand Landmarker and the MediaPipe
Gesture Recognizer. Every component that needs an ML model
obtains the handle exclusively through this class.

RULES §13.2: no component may load, cache, or hold an ML model
object outside this module. RULES §8.6: ML model files live in
`assets/models/`; this module is the only place that opens them.

API surface (per TRD §3.15 and Implementation Plan §5 Task 1.3):
  - get_hand_landmarker() -> object | None
  - recognize_gesture(landmarks) -> GestureResult | None
  - is_gesture_model_available() -> bool
  - record_inference_failure() -> None
  - reload_gesture_model() -> bool

Lifecycle states (TRD §5.2):
  - Available (model loaded successfully)
  - FallbackOnly (load failed or auto-reload failed after 3
    consecutive inference failures)
  - AutoReloading (transient, between detection of 3rd failure
    and the result of the reload attempt)

Diagnostics: every state transition is logged through the
`gestureos` logger using the `ml` category (AI Dev Guide §10.1).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.15 / AI Dev Guide §8.5)
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_FAILURES: int = 3
"""Number of consecutive inference failures that trigger an auto-reload.

Per TRD §5.2: after 3 consecutive failures the Gesture Recognizer
enters AutoReloading. If the reload itself fails, the manager
transitions to FallbackOnly (custom geometric recognizers only).
"""


class ModelManager:
    """Singleton-style manager that loads, caches, and serves ML models.

    The class is a singleton; use `get_instance()` to obtain the
    shared instance. Tests that need a fresh state should call
    `reset_instance()` between tests.

    Usage:
        mgr = ModelManager.get_instance()
        mgr.load_all()
        if mgr.is_gesture_model_available():
            result = mgr.recognize_gesture(landmarks)
        landmarker = mgr.get_hand_landmarker()

    RULES §13.2: every component that needs an ML model must
    obtain the handle through ModelManager. Direct model file
    access is prohibited.
    """

    _instance: ModelManager | None = None

    def __init__(self, models_dir: Path | None = None) -> None:
        if ModelManager._instance is not None:
            raise RuntimeError(
                'ModelManager is a singleton. Use get_instance().'
            )
        self._models_dir: Path = (
            models_dir
            or Path(__file__).resolve().parent.parent / 'assets' / 'models'
        )
        # MediaPipe Hand Landmarker handle (V2.0 Tasks API).
        self._hand_landmarker: object | None = None
        # MediaPipe Gesture Recognizer handle (V2.0 Tasks API).
        self._gesture_model: object | None = None
        # Auto-reload bookkeeping (TRD §5.2).
        self._consecutive_failures: int = 0
        # Hand Landmarker configuration (set via set_hand_landmarker_config
        # or load_hand_landmarker kwargs). Used in VIDEO mode for temporal
        # tracking across frames.
        self._hl_num_hands: int = 2
        self._hl_min_detection_confidence: float = 0.5
        self._hl_min_presence_confidence: float = 0.5
        self._hl_min_tracking_confidence: float = 0.5
        # Monotonically increasing timestamp (ms) for VIDEO mode.
        self._hl_timestamp_ms: int = 0
        # Cached RGB frame from the most recent Hand Landmarker call,
        # used by the Gesture Recognizer which requires image input
        # (MediaPipe Tasks API contract).
        self._latest_frame: np.ndarray | None = None

    # -- Singleton ----------------------------------------------------------

    @classmethod
    def get_instance(cls, models_dir: Path | None = None) -> ModelManager:
        if cls._instance is None:
            cls._instance = cls(models_dir=models_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Test-only: destroy the singleton."""
        cls._instance = None

    # -- Directory ----------------------------------------------------------

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    @property
    def hand_landmarker_path(self) -> Path:
        """Default bundled Hand Landmarker model path.

        The MediaPipe `HandLandmarker` Tasks API loads its model
        from a `.task` file. V1 ships with one bundled model at
        `gestureos/assets/models/hand_landmarker.task`. The
        application does not generate this file at runtime; PyInstaller
        bundles it via `datas` (TRD §14.2).
        """
        return self._models_dir / 'hand_landmarker.task'

    @property
    def gesture_recognizer_path(self) -> Path:
        """Default bundled Gesture Recognizer model path (TRD §8.1)."""
        return self._models_dir / 'gesture_recognizer.task'

    def ensure_model_directory(self) -> None:
        self._models_dir.mkdir(parents=True, exist_ok=True)

    # -- Hand Landmarker configuration --------------------------------------

    def set_hand_landmarker_config(
        self,
        num_hands: int | None = None,
        min_detection_confidence: float | None = None,
        min_presence_confidence: float | None = None,
        min_tracking_confidence: float | None = None,
    ) -> None:
        """Override the default Hand Landmarker configuration.

        Called by ``HandLandmarker.initialize()`` with the values
        from the detector instance. The config takes effect on the
        *next* call to ``load_hand_landmarker()`` (or reload if the
        model is already loaded and the config differs).

        Args:
            num_hands: Maximum number of hands to detect (default 2).
            min_detection_confidence: Min confidence for palm detection.
            min_presence_confidence: Min confidence for hand presence.
            min_tracking_confidence: Min IoU threshold for tracking.
        """
        if num_hands is not None:
            self._hl_num_hands = int(num_hands)
        if min_detection_confidence is not None:
            self._hl_min_detection_confidence = float(min_detection_confidence)
        if min_presence_confidence is not None:
            self._hl_min_presence_confidence = float(min_presence_confidence)
        if min_tracking_confidence is not None:
            self._hl_min_tracking_confidence = float(min_tracking_confidence)

    # -- Load all -----------------------------------------------------------

    def load_all(self) -> None:
        """Load every V1 model. Idempotent: re-running after success is a no-op.

        CP-1 wiring point: called once at application startup from
        `GestureOSApp.__init__()` (or `start()`). If a model file
        is missing, the manager logs an ERROR and continues — the
        pipeline degrades gracefully (HandLandmarker → empty list;
        StaticGestureEngine → custom-fallback recognizers only).
        """
        self.ensure_model_directory()
        self.load_hand_landmarker()
        self.load_gesture_recognizer()

    # -- Hand Landmarker ----------------------------------------------------

    def load_hand_landmarker(self) -> bool:
        """Load the MediaPipe Hand Landmarker model file.

        Reads the configuration from ``set_hand_landmarker_config()``
        (or defaults). The model is created in ``VIDEO`` running mode
        for temporal tracking across frames.

        Returns True on success, False on failure (file missing or
        model load error). On failure, `get_hand_landmarker()`
        returns None and the HandLandmarker detector will log an
        ERROR and skip inference.
        """
        model_path = self.hand_landmarker_path
        if not model_path.exists():
            logger.error(
                'ml',
                extra={'extras': {
                    'event': 'model_not_found',
                    'model': 'hand_landmarker',
                    'path': str(model_path),
                    'hint': 'Bundle hand_landmarker.task in assets/models/.',
                }},
            )
            self._hand_landmarker = None
            return False

        try:
            import mediapipe as mp  # local import — ModelManager is the only
                                    # component that imports mediapipe per
                                    # RULES §2.9 / §13.2 / AI Dev Guide §8.2.

            BaseOptions = mp.tasks.BaseOptions
            HandLandmarker = mp.tasks.vision.HandLandmarker
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=VisionRunningMode.VIDEO,
                num_hands=self._hl_num_hands,
                min_hand_detection_confidence=self._hl_min_detection_confidence,
                min_hand_presence_confidence=self._hl_min_presence_confidence,
                min_tracking_confidence=self._hl_min_tracking_confidence,
            )
            self._hand_landmarker = HandLandmarker.create_from_options(options)
            # Reset timestamp counter on fresh load.
            self._hl_timestamp_ms = 0
            logger.info(
                'ml',
                extra={'extras': {
                    'event': 'model_loaded',
                    'model': 'hand_landmarker',
                    'path': str(model_path),
                    'running_mode': 'VIDEO',
                    'num_hands': self._hl_num_hands,
                    'min_detection_confidence': self._hl_min_detection_confidence,
                    'min_presence_confidence': self._hl_min_presence_confidence,
                    'min_tracking_confidence': self._hl_min_tracking_confidence,
                }},
            )
            return True
        except Exception as exc:  # noqa: BLE001 — graceful degradation
            logger.error(
                'ml',
                extra={'extras': {
                    'event': 'model_load_failed',
                    'model': 'hand_landmarker',
                    'error': str(exc),
                }},
            )
            self._hand_landmarker = None
            return False

    def get_hand_landmarker(self) -> object | None:
        """Return the MediaPipe Hand Landmarker handle, or None if unavailable.

        Per RULES §13.2 this is the only way for a component to
        obtain a Hand Landmarker handle. Callers must treat the
        returned object as opaque (do not access attributes not
        documented in the MediaPipe Tasks API).
        """
        return self._hand_landmarker

    def is_hand_landmarker_available(self) -> bool:
        return self._hand_landmarker is not None

    def process_hand_landmarker(self, frame: np.ndarray) -> Any | None:
        """Run Hand Landmarker inference on a raw RGB frame.

        Converts the frame to ``mp.Image`` and calls the Tasks API
        ``.detect_for_video()`` method with a monotonically increasing
        timestamp (ms). The model must have been loaded in ``VIDEO``
        running mode.

        This keeps the ``import mediapipe`` confined to ModelManager
        (RULES §2.9 / §13.2).

        Args:
            frame: RGB ``np.ndarray`` of shape ``(H, W, 3)``.

        Returns:
            A ``HandLandmarkerResult`` (Tasks API) with ``hand_landmarks``
            and ``handedness`` attributes, or ``None`` if the model is
            unavailable or inference fails.
        """
        if self._hand_landmarker is None:
            return None
        try:
            import mediapipe as mp

            # Cache the frame for the Gesture Recognizer, which runs on
            # the same frame later in the pipeline but doesn't receive
            # it directly (MediaPipe Tasks API requires mp.Image input).
            self._latest_frame = frame

            # Monotonically increasing timestamp (ms) per VIDEO mode contract.
            # Using time.monotonic() ensures strict monotonicity even when the
            # system clock jumps.
            self._hl_timestamp_ms = max(
                int(time.monotonic() * 1000),
                self._hl_timestamp_ms + 1,
            )
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            return self._hand_landmarker.detect_for_video(
                mp_image, self._hl_timestamp_ms,
            )
        except Exception as exc:  # noqa: BLE001 — graceful degradation
            logger.error(
                'ml',
                extra={'extras': {
                    'event': 'hand_landmarker_inference_error',
                    'error': str(exc),
                }},
            )
            return None

    # -- Gesture Recognizer -------------------------------------------------

    def load_gesture_recognizer(self) -> bool:
        """Load the MediaPipe Gesture Recognizer model file.

        Returns True on success, False on failure. On failure,
        `is_gesture_model_available()` returns False and the
        StaticGestureEngine falls back to the custom geometric
        recognizers for the 3 MediaPipe-uncovered gestures
        (Pinch, Three Fingers, OK Sign).
        """
        model_path = self.gesture_recognizer_path
        if not model_path.exists():
            logger.warning(
                'ml',
                extra={'extras': {
                    'event': 'model_not_found',
                    'model': 'gesture_recognizer',
                    'path': str(model_path),
                    'hint': 'Bundle gesture_recognizer.task in assets/models/.',
                }},
            )
            self._gesture_model = None
            return False

        try:
            import mediapipe as mp

            BaseOptions = mp.tasks.BaseOptions
            GestureRecognizer = mp.tasks.vision.GestureRecognizer
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = mp.tasks.vision.GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=VisionRunningMode.IMAGE,
            )
            self._gesture_model = GestureRecognizer.create_from_options(options)
            self._consecutive_failures = 0
            logger.info(
                'ml',
                extra={'extras': {
                    'event': 'model_loaded',
                    'model': 'gesture_recognizer',
                    'path': str(model_path),
                }},
            )
            return True
        except Exception as exc:  # noqa: BLE001 — graceful degradation
            logger.error(
                'ml',
                extra={'extras': {
                    'event': 'model_load_failed',
                    'model': 'gesture_recognizer',
                    'error': str(exc),
                }},
            )
            self._gesture_model = None
            return False

    def get_gesture_recognizer(self) -> object | None:
        """Return the raw Gesture Recognizer handle, or None if unavailable.

        Prefer `recognize_gesture()` (the high-level API) unless
        the caller needs the raw handle (e.g., for low-level
        configuration). Direct handle access is logged as
        informational and is permitted only to model-aware
        components such as StaticGestureEngine (CP-3).
        """
        return self._gesture_model

    def is_gesture_model_available(self) -> bool:
        """True iff the Gesture Recognizer is loaded and ready for inference.

        TRD §3.15 canonical name. Callers MUST check this before
        calling `recognize_gesture()`. When False, the Static
        Gesture Engine operates in custom-fallback mode.
        """
        return self._gesture_model is not None

    def recognize_gesture(
        self,
        landmarks: list[tuple[float, float, float]],
    ) -> Any | None:
        """Run one inference and return a `GestureResult` (or None on failure).

        This is the high-level API used by `StaticGestureEngine`
        (CP-3). The raw MediaPipe result is mapped to the
        internal `GestureResult` shape. On any error, the failure
        is logged and `None` is returned; the consecutive-failure
        counter is incremented; auto-reload is triggered after
        `MAX_CONSECUTIVE_FAILURES`.

        The Gesture Recognizer (``gesture_recognizer.task``) is a
        MediaPipe Tasks API model that expects ``mp.Image`` input,
        not raw landmarks. The latest RGB frame is obtained from the
        cache populated by :meth:`process_hand_landmarker`, which runs
        earlier in the same frame cycle.

        Args:
            landmarks: list of 21 normalized (x, y, z) MediaPipe
                landmarks produced by the Hand Landmarker. Used to
                match which detected hand in the GestureRecognizer
                result corresponds to the caller's hand (multi-hand
                support).

        Returns:
            A `GestureResult` (gesture_name, confidence,
            is_dynamic=False, hand_role, timestamp, source) on
            successful inference; None when the model is not
            available, when no gesture is recognized, or on
            inference error.
        """
        # Defer imports to avoid hard dependency on
        # `models.data_models` at module import time; data_models
        # does not import mediapipe (AI Dev Guide §5.5).
        from models.data_models import GestureResult

        if not self.is_gesture_model_available():
            return None
        if self._latest_frame is None:
            return None

        try:
            import mediapipe as mp

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=self._latest_frame,
            )
            result = self._gesture_model.recognize(mp_image)
        except Exception as exc:  # noqa: BLE001 — hot-path defensive
            logger.error(
                'ml',
                extra={'extras': {
                    'event': 'inference_error',
                    'error': str(exc),
                }},
            )
            self.record_inference_failure()
            return None

        self._consecutive_failures = 0

        # The MediaPipe result is a `GestureRecognizerResult`
        # with:
        #   gestures: list[list[Category]]
        #     outer list = per hand, inner list = per category score
        #   hand_landmarks: list[list[NormalizedLandmark]]
        #     outer list = per hand, inner list = 21 landmarks
        # `Category.category_name` is the class string and
        # `Category.score` is the confidence. We pick the
        # top-scoring gesture for the hand that best matches the
        # caller's landmarks; if none, return None.
        mp_gestures = getattr(result, 'gestures', None) or []
        mp_hand_landmarks = getattr(result, 'hand_landmarks', None) or []

        if not mp_gestures:
            return None

        # Match the caller's hand to a detected hand by comparing
        # wrist positions (landmarks[0]). For a single detected hand
        # this is trivial; for multiple hands we pick the closest.
        caller_wrist = (landmarks[0][0], landmarks[0][1]) if landmarks else None
        hand_idx = 0
        if caller_wrist is not None and len(mp_gestures) > 1 and len(mp_hand_landmarks) >= len(mp_gestures):
            best_dist = float('inf')
            for i in range(len(mp_gestures)):
                if i < len(mp_hand_landmarks) and mp_hand_landmarks[i]:
                    dw = mp_hand_landmarks[i][0]
                    dx = caller_wrist[0] - dw.x
                    dy = caller_wrist[1] - dw.y
                    dist = dx * dx + dy * dy
                    if dist < best_dist:
                        best_dist = dist
                        hand_idx = i

        cat_list = mp_gestures[hand_idx]
        if not cat_list:
            return None
        top = cat_list[0]
        if not getattr(top, 'category_name', None):
            return None

        # Map MediaPipe class names to internal names. The mapping
        # is canonical (TRD §3.8.1). Unknown classes are passed
        # through lowercased to support future MediaPipe model
        # versions adding new categories.
        gesture_name = _MP_TO_INTERNAL.get(
            top.category_name, top.category_name.lower()
        )

        return GestureResult(
            gesture_name=gesture_name,
            confidence=float(getattr(top, 'score', 0.0) or 0.0),
            is_dynamic=False,
            hand_role='',  # populated by StaticGestureEngine per hand
            timestamp=time.time(),
            source='mediapipe',
        )

    def record_inference_failure(self) -> None:
        """Record a single failed inference and possibly trigger auto-reload.

        Called by the StaticGestureEngine (or by `recognize_gesture`
        itself) every time a MediaPipe call throws. After
        `MAX_CONSECUTIVE_FAILURES` consecutive failures the manager
        attempts a reload; if the reload fails the manager stays
        in `FallbackOnly` mode and the overlay is updated by the
        orchestrator (CP-8).
        """
        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            logger.warning(
                'ml',
                extra={'extras': {
                    'event': 'auto_reload_triggered',
                    'consecutive_failures': self._consecutive_failures,
                }},
            )
            if not self.reload_gesture_model():
                logger.warning(
                    'ml',
                    extra={'extras': {
                        'event': 'fallback_only_mode_engaged',
                        'hint': 'Gesture Recognizer could not be reloaded; '
                                'custom geometric fallback only.',
                    }},
                )

    def reload_gesture_model(self) -> bool:
        """Unload and reload the Gesture Recognizer.

        Returns True on successful reload, False otherwise. The
        caller (typically `record_inference_failure`) decides
        whether to enter FallbackOnly mode on False.
        """
        self._gesture_model = None
        return self.load_gesture_recognizer()

    @property
    def consecutive_failures(self) -> int:
        """Read-only accessor for the consecutive-failure counter.

        Used by tests and the Developer Mode debug panel.
        """
        return self._consecutive_failures

    def shutdown(self) -> None:
        """Release all loaded model handles. Idempotent."""
        for attr in ('_hand_landmarker', '_gesture_model'):
            handle = getattr(self, attr, None)
            if handle is None:
                continue
            try:
                close_fn = getattr(handle, 'close', None)
                if callable(close_fn):
                    close_fn()
            except Exception:  # noqa: BLE001 — shutdown is best-effort
                pass
            setattr(self, attr, None)
        self._consecutive_failures = 0


# Canonical MediaPipe class name → internal gesture name mapping.
# Source: TRD §3.8.1 (MediaPipe-to-Internal Gesture Mapping). This
# mapping is consulted by `recognize_gesture` to convert MediaPipe's
# CamelCase class names to our `snake_case` internal names. The
# fallback (`lowercase`) keeps the manager forward-compatible with
# future MediaPipe model versions that may add new categories
# without requiring a code change.
_MP_TO_INTERNAL: dict[str, str] = {
    'Open_Palm': 'open_palm',
    'Closed_Fist': 'fist',
    'Thumb_Up': 'thumbs_up',
    'Thumb_Down': 'thumbs_down',
    'Victory': 'peace_sign',
    'Pointing_Up': 'pointing_up',
}

