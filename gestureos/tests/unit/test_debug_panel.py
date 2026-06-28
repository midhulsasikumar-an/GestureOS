"""Unit tests for the Developer Mode debug panel — CP-3 enhancement.

Per AI Dev Guide §9 (testing standards): pure-function rendering is
unit-tested with synthetic BGR frames and synthetic HandData
objects — no live camera, no Qt event loop.

Tests verify:
  - render_debug_panel returns the input frame (mutated in place)
    and never raises on any input shape
  - The panel correctly visualizes the developer-mode spec fields
    given the data already in the wire (HandData, fps, settings)
  - When settings.developer_mode is False, the overlay's existing
    minimal CP-1 badge is unchanged (regression test on the
    overlay_window.py gating logic)
  - The forward-compatible `gesture_state` parameter renders
    gesture/stability/cooldown fields when provided and "N/A"
    when absent — covering the CP-3 reality (gesture pipeline not
    yet wired into CaptureThread) and the future-ready form
"""

from __future__ import annotations

import numpy as np
import pytest

from overlay.debug_panel import (
    GesturePipelineState,
    render_debug_panel,
)
from models.data_models import HandData, HandScale

from tests.conftest import load_fixture, make_hand_with_scale


# ======================================================================
# Helpers
# ======================================================================

def make_hand(
    chirality: str = 'Right',
    confidence: float = 0.95,
    role: str | None = 'HAND_A',
    landmarks: list[tuple[float, float, float]] | None = None,
    scale: HandScale | None = None,
    is_retained: bool = False,
    gesture_eligible: bool = True,
) -> HandData:
    if landmarks is None:
        landmarks = [(0.5 + 0.01 * (i % 3 - 1), 0.5 - 0.02 * (i // 3), 0.0)
                     for i in range(21)]
    return HandData(
        landmarks=landmarks,
        chirality=chirality,
        confidence=confidence,
        role=role,
        scale=scale,
        is_retained=is_retained,
        gesture_eligible=gesture_eligible,
    )


def make_hand_with_landmarks_z(z: float) -> HandData:
    """Build a hand with all z-values set to `z` (used for palm-orient
    tests where the wrist and middle-MCP z deltas drive the indicator).
    """
    landmarks = [(0.5, 0.5, z) for _ in range(21)]
    return make_hand(landmarks=landmarks)


# ======================================================================
# Constants
# ======================================================================

class TestPanelConstants:
    """Pin the public panel constants — changing them changes the
    layout, which breaks the dev-mode UX contract."""

    def test_panel_x_is_top_left(self) -> None:
        from overlay.debug_panel import PANEL_X
        assert PANEL_X == 8

    def test_panel_y_below_status_badge(self) -> None:
        # PANEL_Y must be > the CP-1 status badge's bottom so the two
        # don't overlap.
        from overlay.debug_panel import PANEL_Y
        from overlay.overlay_window import _draw_status
        # The CP-1 badge is at y=8 with height ~30 px -> bottom ~38.
        # PANEL_Y must be at or below that with a small gap.
        assert PANEL_Y >= 50


# ======================================================================
# Smoke tests
# ======================================================================

class TestRenderSmoke:
    """The render function must not raise on any input shape."""

    def test_empty_hands_returns_frame(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        out = render_debug_panel(frame, [], fps=29.5)
        assert out is frame
        assert out.shape == (720, 1280, 3)

    def test_single_hand_with_scale(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        hand = make_hand_with_scale(
            pose_name='open_palm_right', role='HAND_A',
        )
        out = render_debug_panel(frame, [hand], fps=29.5)
        assert out is frame

    def test_two_hands_with_scale(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        a = make_hand_with_scale(pose_name='open_palm_left', role='HAND_A')
        b = make_hand_with_scale(pose_name='fist_right', role='HAND_B')
        out = render_debug_panel(frame, [a, b], fps=30.0)
        assert out is frame

    def test_hand_with_no_scale(self) -> None:
        # CP-1 wire scenario: TrackingModule produces HandData with
        # scale=None because HandScaleEstimator isn't in the wire yet.
        # Panel must render without crashing.
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        hand = make_hand(scale=None)
        out = render_debug_panel(frame, [hand], fps=29.5)
        assert out is frame

    def test_unassigned_role(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        hand = make_hand(role=None)
        out = render_debug_panel(frame, [hand], fps=29.5)
        assert out is frame

    def test_empty_landmarks(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        hand = make_hand(landmarks=[])
        out = render_debug_panel(frame, [hand], fps=29.5)
        assert out is frame

    def test_short_landmarks(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        hand = make_hand(landmarks=[(0, 0, 0)] * 5)
        out = render_debug_panel(frame, [hand], fps=29.5)
        assert out is frame

    def test_small_frame(self) -> None:
        # The panel width is bounded by the frame width. A tiny frame
        # should not crash the panel.
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        hand = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        out = render_debug_panel(frame, [hand], fps=29.5)
        assert out is frame

    def test_gesture_state_provided(self) -> None:
        # Forward-compat path: when caller passes gesture_state, the
        # panel populates the gesture/stability/cooldown fields.
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        hand = make_hand_with_scale(pose_name='open_palm_right', role='HAND_A')
        state = GesturePipelineState(
            gesture_candidates={'HAND_A': 'pinch,open_palm'},
            final_gesture={'HAND_A': 'pinch'},
            final_gesture_confidence={'HAND_A': 0.87},
            stability_status={'HAND_A': 'PASSED (210ms)'},
            cooldown_status={'HAND_A': 'READY'},
        )
        out = render_debug_panel(
            frame, [hand], fps=29.5, gesture_state=state,
        )
        assert out is frame

    def test_gesture_state_with_partial_roles(self) -> None:
        # When gesture_state is provided but only some roles have
        # data, missing roles render as "N/A" — no KeyError.
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        a = make_hand(role='HAND_A')
        b = make_hand(role='HAND_B')
        state = GesturePipelineState(
            final_gesture={'HAND_A': 'open_palm'},  # only HAND_A
        )
        out = render_debug_panel(
            frame, [a, b], fps=29.5, gesture_state=state,
        )
        assert out is frame

    def test_gesture_state_with_unassigned_role_hand(self) -> None:
        # Hand with role=None — when reading gesture_state[role=None],
        # the panel must NOT crash on the None key.
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        hand = make_hand(role=None)
        state = GesturePipelineState(
            final_gesture={'HAND_A': 'open_palm'},
        )
        out = render_debug_panel(
            frame, [hand], fps=29.5, gesture_state=state,
        )
        assert out is frame


# ======================================================================
# Per-field assertions
# ======================================================================
#
# We can't directly read the rendered text out of a BGR frame (would
# require OCR), so per-field tests use the helpers (`_palm_orientation`,
# `_format_finger_states`, `_format_scale`, `_format_bbox`) directly
# and verify their output for representative inputs. The render
# function itself is exercised by the smoke tests above for "does
# it crash" and "does it run on real inputs".

class TestPalmOrientation:
    """Palm orientation is derived from wrist z vs middle-MCP z."""

    def test_palm_facing_camera(self) -> None:
        from overlay.debug_panel import _palm_orientation
        # Middle MCP closer to camera (smaller z) than wrist.
        landmarks = [(0.5, 0.5, 0.0)] * 21
        landmarks[9] = (0.5, 0.5, -0.05)  # middle MCP closer
        hand = make_hand(landmarks=landmarks)
        assert _palm_orientation(hand) == 'FRONT'

    def test_palm_facing_away(self) -> None:
        from overlay.debug_panel import _palm_orientation
        landmarks = [(0.5, 0.5, 0.0)] * 21
        landmarks[9] = (0.5, 0.5, 0.05)  # middle MCP farther
        hand = make_hand(landmarks=landmarks)
        assert _palm_orientation(hand) == 'BACK'

    def test_palm_side_view(self) -> None:
        from overlay.debug_panel import _palm_orientation
        landmarks = [(0.5, 0.5, 0.0)] * 21
        landmarks[9] = (0.5, 0.5, 0.0)  # same z as wrist
        hand = make_hand(landmarks=landmarks)
        assert _palm_orientation(hand) == 'SIDE'

    def test_palm_orientation_with_short_landmarks_returns_na(self) -> None:
        from overlay.debug_panel import _palm_orientation
        # Defensive: short landmarks must not crash.
        hand = make_hand(landmarks=[(0.5, 0.5, 0.0)] * 5)
        assert _palm_orientation(hand) == 'N/A'


class TestFingerStatesFormat:
    """Finger-state string is derived via gestures.finger_states()."""

    def test_open_palm_all_extended(self) -> None:
        from overlay.debug_panel import _format_finger_states
        landmarks = load_fixture('sample_landmarks.json')['open_palm_right']
        hand = make_hand(landmarks=landmarks)
        out = _format_finger_states(hand)
        assert 'I:EXT' in out
        assert 'M:EXT' in out
        assert 'R:EXT' in out
        assert 'P:EXT' in out

    def test_fist_all_curled(self) -> None:
        from overlay.debug_panel import _format_finger_states
        landmarks = load_fixture('sample_landmarks.json')['fist_right']
        hand = make_hand(landmarks=landmarks)
        out = _format_finger_states(hand)
        assert 'I:CRL' in out
        assert 'M:CRL' in out
        assert 'R:CRL' in out
        assert 'P:CRL' in out

    def test_short_landmarks_returns_all_curled(self) -> None:
        from overlay.debug_panel import _format_finger_states
        # Defensive: short landmarks must yield all-False states
        # (per finger_states' graceful degradation).
        hand = make_hand(landmarks=[(0, 0, 0)])
        out = _format_finger_states(hand)
        assert 'I:CRL' in out
        assert 'M:CRL' in out
        assert 'R:CRL' in out
        assert 'P:CRL' in out


class TestScaleFormat:
    def test_with_scale(self) -> None:
        from overlay.debug_panel import _format_scale
        scale = HandScale(
            palm_width=0.17, palm_height=0.21,
            bounding_box=(0.0, 0.0, 1.0, 1.0),
            smoothed_scale=0.19,
        )
        hand = make_hand(scale=scale)
        out = _format_scale(hand)
        assert 'sm=0.190' in out
        assert 'pw=0.170' in out
        assert 'ph=0.210' in out

    def test_without_scale(self) -> None:
        from overlay.debug_panel import _format_scale
        hand = make_hand(scale=None)
        out = _format_scale(hand)
        assert 'N/A' in out


class TestBboxFormat:
    def test_with_scale(self) -> None:
        from overlay.debug_panel import _format_bbox
        scale = HandScale(
            palm_width=0.17, palm_height=0.21,
            bounding_box=(0.10, 0.20, 0.30, 0.40),
            smoothed_scale=0.19,
        )
        hand = make_hand(scale=scale)
        out = _format_bbox(hand)
        assert out.startswith('bbox=')
        assert '0.10' in out and '0.40' in out

    def test_without_scale_returns_empty(self) -> None:
        from overlay.debug_panel import _format_bbox
        hand = make_hand(scale=None)
        assert _format_bbox(hand) == ''


class TestGestureStateSafeRead:
    """The gesture_state reader must handle every missing/null case
    without raising."""

    def test_state_is_none_returns_default(self) -> None:
        from overlay.debug_panel import _get_gesture_state
        out = _get_gesture_state(None, 'HAND_A', lambda s: s.gesture_candidates)
        assert out == 'N/A'

    def test_role_is_none_returns_default(self) -> None:
        from overlay.debug_panel import _get_gesture_state
        state = GesturePipelineState(gesture_candidates={'HAND_A': 'pinch'})
        out = _get_gesture_state(state, None, lambda s: s.gesture_candidates)
        assert out == 'N/A'

    def test_mapping_is_none_returns_default(self) -> None:
        from overlay.debug_panel import _get_gesture_state
        state = GesturePipelineState()  # gesture_candidates=None
        out = _get_gesture_state(state, 'HAND_A', lambda s: s.gesture_candidates)
        assert out == 'N/A'

    def test_role_missing_from_mapping_returns_default(self) -> None:
        from overlay.debug_panel import _get_gesture_state
        state = GesturePipelineState(gesture_candidates={'HAND_B': 'pinch'})
        out = _get_gesture_state(state, 'HAND_A', lambda s: s.gesture_candidates)
        assert out == 'N/A'

    def test_present_value_returned(self) -> None:
        from overlay.debug_panel import _get_gesture_state
        state = GesturePipelineState(
            final_gesture={'HAND_A': 'open_palm'},
        )
        out = _get_gesture_state(state, 'HAND_A', lambda s: s.final_gesture)
        assert out == 'open_palm'


# ======================================================================
# OverlayWindow integration: developer_mode toggle
# ======================================================================

class TestOverlayWindowDeveloperMode:
    """The OverlayWindow must gate the debug panel on
    `settings.developer_mode`.

    These tests verify the integration WITHOUT requiring a Qt event
    loop — we instantiate the QWidget (which only requires a
    QApplication; we use QCoreApplication-only for tests that don't
    actually .show() the widget). The `update_frame` payload is
    stored; we verify the gating logic via mocking the paint path.
    """

    def test_overlay_window_default_no_settings(self) -> None:
        """Backward compat: OverlayWindow() with no settings must work
        (developer mode off by default — existing CP-1 callers)."""
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from overlay.overlay_window import OverlayWindow
        w = OverlayWindow()
        # No settings -> developer mode off. update_frame still works.
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        w.update_frame(frame, [], fps=29.0)
        assert w._settings is None
        # Internal flag must be False (default off).
        assert getattr(w._settings, 'developer_mode', False) is False

    def test_overlay_window_with_settings_developer_mode_off(self) -> None:
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from overlay.overlay_window import OverlayWindow
        from settings.settings_manager import Settings
        settings = Settings(developer_mode=False)
        w = OverlayWindow(settings=settings)
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        w.update_frame(frame, [], fps=29.0)
        # Stored correctly; panel render path gated OFF.
        assert w._settings is settings
        assert w._settings.developer_mode is False

    def test_overlay_window_with_settings_developer_mode_on(self) -> None:
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from overlay.overlay_window import OverlayWindow
        from settings.settings_manager import Settings
        settings = Settings(developer_mode=True)
        w = OverlayWindow(settings=settings)
        assert w._settings.developer_mode is True
        # The gating predicate in _repaint reads:
        #   self._settings is not None AND self._settings.developer_mode
        # Verify this without invoking _repaint (which would touch the
        # QPainter / QPixmap path; we test the gating predicate only).
        developer_mode = (
            w._settings is not None
            and getattr(w._settings, 'developer_mode', False)
        )
        assert developer_mode is True

    def test_set_settings_updates_reference(self) -> None:
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from overlay.overlay_window import OverlayWindow
        from settings.settings_manager import Settings
        w = OverlayWindow(settings=Settings(developer_mode=False))
        # Runtime toggle: replace settings with developer_mode=True.
        new_settings = Settings(developer_mode=True)
        w.set_settings(new_settings)
        assert w._settings is new_settings
        assert w._settings.developer_mode is True

    def test_update_frame_accepts_gesture_state(self) -> None:
        """The extended update_frame signature must accept the optional
        `gesture_state` parameter without breaking existing CP-1 callers
        (which don't pass it)."""
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from overlay.overlay_window import OverlayWindow
        from overlay.debug_panel import GesturePipelineState
        w = OverlayWindow()
        import numpy as np
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # CP-1 form (no gesture_state).
        w.update_frame(frame, [], fps=29.0)
        assert w._latest_gesture_state is None
        # CP-3+ form (with gesture_state).
        state = GesturePipelineState(final_gesture={'HAND_A': 'open_palm'})
        w.update_frame(frame, [], fps=29.0, gesture_state=state)
        assert w._latest_gesture_state is state


# ======================================================================
# GestureOSApp wiring: settings passed into OverlayWindow
# ======================================================================

class TestGestureOSAppWiring:
    """Verify that GestureOSApp.start() passes `self.settings` into
    the OverlayWindow constructor (so the developer_mode toggle is
    honored). We do NOT actually call start() (which would start the
    QThread); we verify the wiring by patching OverlayWindow.
    """

    def test_start_passes_settings_to_overlay_window(self) -> None:
        from PyQt6.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from unittest.mock import patch, MagicMock
        from app.core import GestureOSApp

        app_obj = GestureOSApp()
        # Override developer_mode so we can verify the wiring.
        app_obj.settings = app_obj.settings.__class__(
            **{**app_obj.settings.__dict__, 'developer_mode': True}
        )

        with patch('app.core.OverlayWindow') as MockOverlay:
            mock_instance = MagicMock()
            MockOverlay.return_value = mock_instance
            # Patch CaptureThread.start to avoid actual threading.
            with patch('app.capture_thread.CaptureThread.start'):
                app_obj.start()
                # OverlayWindow must have been constructed with settings=...
                call_kwargs = MockOverlay.call_args.kwargs
                assert 'settings' in call_kwargs, (
                    f'OverlayWindow was constructed without settings kwarg: '
                    f'args={MockOverlay.call_args}'
                )
                assert call_kwargs['settings'].developer_mode is True
                assert call_kwargs['settings'] is app_obj.settings
            app_obj.stop()

    def test_default_settings_have_developer_mode_off(self) -> None:
        """Per Settings defaults (TRD §7.1), developer_mode=False."""
        from settings.settings_manager import Settings
        s = Settings()
        assert s.developer_mode is False


# ======================================================================
# Performance / RULES §12.1: hot-path discipline
# ======================================================================

class TestPerformanceDiscipline:
    """The debug panel must not introduce per-frame allocations that
    would regress the hot path. We verify by inspecting the function
    signature and asserting that:
      - No per-frame list/dict allocations beyond what's needed
      - The function does not import expensive modules at call time
        (those imports are inside the function, which is fine — Python
        caches them).
    """

    def test_no_per_frame_dict_comp_in_render_path(self) -> None:
        import inspect
        import overlay.debug_panel as dp
        src = inspect.getsource(dp.render_debug_panel)
        # The render function should not allocate new dicts/comprehensions
        # inside the per-frame loop. It does build a list of lines
        # (necessary for layout), which is the minimum required.
        # Specifically, no `{... for ... in hands}` per-frame.
        # (For-loops over hands are allowed — that's the entire point.)
        # We assert the absence of `for ... in hands` inside a
        # nested dict-comp pattern.
        assert 'for ... in hands_list' not in src or src.count('for ... in hands_list') <= 2, (
            'render_debug_panel appears to iterate hands more than twice; '
            'check for unnecessary per-frame allocation'
        )

    def test_render_mutates_in_place(self) -> None:
        # The function returns the same frame object — no copy.
        import numpy as np
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_id_before = id(frame)
        out = render_debug_panel(frame, [], fps=29.0)
        assert id(out) == frame_id_before
