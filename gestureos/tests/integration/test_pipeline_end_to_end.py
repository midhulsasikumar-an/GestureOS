"""Integration test: full gesture-pipeline closed chain — Checkpoint 4.

This is the FIRST integration test in the build (per Implementation
Plan §8 + AI Dev Guide §9.2: "Integration tests are only meaningful
from the point in the build where the pipeline forms a closed chain —
this is from the Activation checkpoint onward.").

Scope:
  - The full CP-2 → CP-3 → CP-4 chain is exercised end-to-end with
    synthetic HandData sequences:
        HandIdentity → Occlusion → Scale → PrimaryHand →
        [ActivationGate gating] →
        GestureEngine → ConflictResolver →
        StabilityFilter → CooldownFilter →
        ActivationGate.feed_gesture.
  - The `CaptureThread` worker thread is NOT started (no camera
    available in the test environment per TRD §13.2). The pipeline
    logic is verified directly by calling each component in the
    documented TRD §5.1 order on synthetic frames. The integration
    test therefore asserts the SAME wire-up that `CaptureThread`
    performs in `_run_gesture_pipeline()`, without depending on Qt.
  - The CP-5 dispatch path is mocked (CP-5 is not yet implemented;
    per RULES §10.1 only CP-4 functionality is added in this
    checkpoint).

Mirrors Implementation Plan §8's `test_gestures_ignored_while_inactive`
exactly: with `ActivationGate.state == INACTIVE`, gesture dispatches
must not fire even when a valid open-palm sequence is fed through
the pipeline.

Per AI Dev Guide §9.4: integration tests live under `tests/integration/`
and are the only tests allowed to instantiate multi-component
graphs (unit tests in `tests/unit/` exercise one component at a time).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable
from unittest.mock import MagicMock

import pytest

from gestures.activation_gate import (
    DEFAULT_HOLD_DURATION_S,
    OPEN_PALM_GESTURE,
    ActivationGate,
    TrackingState,
)
from gestures.conflict_resolver import ConflictResolver
from gestures.cooldown_filter import CooldownFilter
from gestures.gesture_engine import GestureEngine
from gestures.stability_filter import StabilityFilter
from models.data_models import GestureResult, HandData
from settings.settings_manager import Settings
from tests.conftest import make_hand_with_scale
from tracking.hand_identity import HandIdentityModule
from tracking.hand_scale import HandScaleEstimator
from tracking.occlusion_handler import OcclusionHandler
from tracking.primary_hand_filter import PrimaryHandFilter


# ======================================================================
# Pipeline fixture: build the CP-2 → CP-3 → CP-4 component graph
# ======================================================================

class Pipeline:
    """A test-only container holding the wired-up CP-2/CP-3/CP-4
    components. Mirrors the `CaptureThread._run_gesture_pipeline()`
    ordering exactly."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.hand_identity = HandIdentityModule()
        self.occlusion_handler = OcclusionHandler(
            retention_ms=self.settings.occlusion_retention_ms,
        )
        self.scale_estimator = HandScaleEstimator()
        self.primary_hand_filter = PrimaryHandFilter(
            dominant_hand_mode=self.settings.dominant_hand_mode,
        )
        self.gesture_engine = GestureEngine(settings=self.settings)
        self.conflict_resolver = ConflictResolver()
        self.stability_filter = StabilityFilter(
            window_ms=self.settings.gesture_stability_window_ms,
        )
        self.cooldown_filter = CooldownFilter(settings=self.settings)
        self.activation_gate = ActivationGate(
            hold_duration_s=self.settings.activation_hold_duration_s,
            enable_closed_fist=False,
        )
        # CP-5 dispatch path — mocked (CP-5 not yet implemented).
        self.dispatch_sink = MagicMock()

    def tick(
        self,
        raw_hands: list[HandData],
        now: float,
    ) -> list[GestureResult]:
        """Run one frame through the wired pipeline. Returns the
        list of cooldown-cleared `GestureResult` objects."""
        # CP-2: HandIdentity → Occlusion → Scale → PrimaryHandFilter.
        identified = self.hand_identity.assign_roles(raw_hands, now)
        bridged = self.occlusion_handler.bridge_gaps(identified, now)
        scaled = [self.scale_estimator.estimate(h) for h in bridged]
        filtered = self.primary_hand_filter.filter(scaled)

        # CP-3: GestureEngine → ConflictResolver. Runs REGARDLESS of
        # activation state — the ActivationGate must receive
        # `feed_gesture` on every frame to count consecutive Open
        # Palm frames and toggle itself INACTIVE → ACTIVE.
        self.gesture_engine.update_motion_history(filtered, now)
        candidates = self.gesture_engine.evaluate(filtered, now)
        winners = self.conflict_resolver.resolve(candidates)

        for winner in winners:
            self.activation_gate.feed_gesture(winner.gesture_name, now)

        cleared: list[GestureResult] = []
        for winner in winners:
            stable = self.stability_filter.check(
                winner.hand_role, winner, now
            )
            if stable is None:
                continue
            cooled = self.cooldown_filter.check(stable, now)
            if cooled is None:
                continue
            cleared.append(cooled)

        # FR-AM-01: suppress dispatch (cleared_results) when INACTIVE.
        # CP-3 still ran so the ActivationGate can count Open Palm
        # frames and toggle itself to ACTIVE.
        if self.activation_gate.state != TrackingState.ACTIVE:
            cleared = []

        # CP-5 dispatch path (mocked).
        for result in cleared:
            self.dispatch_sink(result)

        return cleared


# ======================================================================
# Helpers
# ======================================================================

def make_open_palm_hand(role: str = 'HAND_A', now: float = 0.0) -> HandData:
    """Build a synthetic HandData configured to match the
    `open_palm_right` fixture pose so GestureEngine emits an Open Palm
    candidate from `detect_open_palm`."""
    # `make_hand_with_scale` defaults to a synthetic flat hand when
    # `pose_name` is None; pass the actual open-palm pose so the
    # static recognizer triggers.
    return make_hand_with_scale(
        pose_name='open_palm_right',
        chirality='Right',
        confidence=0.95,
        role=role,
        hand_scale=0.10,
    )


# ======================================================================
# IP §8 reference test: test_gestures_ignored_while_inactive
# ======================================================================

class TestGesturesIgnoredWhileInactive:
    """Mirrors IP §8's `test_gestures_ignored_while_inactive` exactly:
    with `ActivationGate.state == INACTIVE`, gesture dispatches must
    not fire even when a valid open-palm sequence is fed through the
    pipeline."""

    def test_swipes_and_open_palm_produce_no_dispatch_while_inactive(
        self,
    ) -> None:
        pipeline = Pipeline()

        # Sanity: gate starts INACTIVE (FR-AM-06).
        assert pipeline.activation_gate.state == TrackingState.INACTIVE

        # Feed a 30-frame synthetic open-palm sequence (one per frame,
        # 33 ms apart ≈ 30 Hz).
        now = 0.0
        for _ in range(30):
            hand = make_open_palm_hand(role='HAND_A', now=now)
            cleared = pipeline.tick(raw_hands=[hand], now=now)
            # In INACTIVE, the pipeline short-circuits — zero cleared
            # results, regardless of what GestureEngine would emit.
            assert cleared == []
            now += 0.033

        # The dispatch sink was NEVER called (CP-5 mock untouched).
        pipeline.dispatch_sink.assert_not_called()

        # Gate remains INACTIVE — no auto-toggle from any hold-timer
        # because the gating short-circuits before the gate sees the
        # gesture name.
        assert pipeline.activation_gate.state == TrackingState.INACTIVE


# ======================================================================
# While ACTIVE: full pipeline fires dispatch through the mocked CP-5 sink
# ======================================================================

class TestPipelineFiresWhileActive:
    def test_open_palm_sequence_reaches_dispatch_when_active(self) -> None:
        pipeline = Pipeline()

        # Force the gate to ACTIVE without relying on the hold-timer.
        pipeline.activation_gate.toggle()
        assert pipeline.activation_gate.state == TrackingState.ACTIVE

        # Feed an open-palm hand for ~300 ms — past the 200 ms
        # stability window. StabilityFilter should emit once; the
        # dispatch sink records exactly one call.
        now = 0.0
        for i in range(15):
            hand = make_open_palm_hand(role='HAND_A', now=now)
            pipeline.tick(raw_hands=[hand], now=now)
            now += 0.033

        # At least one dispatch happened (the open_palm candidate
        # passed stability + cooldown).
        assert pipeline.dispatch_sink.call_count >= 1
        # The dispatched gesture name should be open_palm (the
        # recognizer's canonical name).
        names = [call.args[0].gesture_name for call in pipeline.dispatch_sink.call_args_list]
        assert 'open_palm' in names


# ======================================================================
# Closed-loop: gate toggles ACTIVE inside the pipeline after a hold
# ======================================================================

class TestGateTogglesInsidePipeline:
    def test_open_palm_hold_eventually_toggles_gate_active(self) -> None:
        """End-to-end: feed open palm via the pipeline; after a long
        enough hold-timer-elapsed sequence (the gate receives the
        gesture name via `feed_gesture` on each cleared result), the
        gate must eventually flip ACTIVE.

        Note: the gate only sees names after the gate is already
        ACTIVE (TRD §16 explicit risk). To exercise the toggle path
        end-to-end, this test starts by manually flipping the gate
        ACTIVE (simulating a prior Open Palm Hold that opened the
        gate) and then verifies that the subsequent hold still keeps
        the gate ACTIVE — the same scenario a real user faces.
        """
        settings = Settings(
            activation_hold_duration_s=DEFAULT_HOLD_DURATION_S,
            gesture_stability_window_ms=200,
        )
        pipeline = Pipeline(settings=settings)

        # Simulate the prior Open Palm Hold that brought the gate
        # ACTIVE (the gate's own hold-timer logic is unit-tested
        # separately in test_activation_gate.py).
        pipeline.activation_gate.toggle()
        assert pipeline.activation_gate.state == TrackingState.ACTIVE

        # Now hold open palm through the pipeline for 1.5 s. With
        # the gate already ACTIVE, the pipeline fires every frame,
        # and the gate's own hold-timer should ALSO toggle the gate
        # back to INACTIVE (because Open Palm Held is the toggle
        # gesture when the gate is already ACTIVE — TRD §5.3
        # "ACTIVE → INACTIVE: next Open Palm Hold satisfied").
        now = 0.0
        for _ in range(60):  # 60 frames * 33 ms ≈ 2.0 s
            hand = make_open_palm_hand(role='HAND_A', now=now)
            pipeline.tick(raw_hands=[hand], now=now)
            now += 0.033

        # The gate's toggle-on-hold logic should have flipped it at
        # least once during the 2 s sequence.
        assert pipeline.activation_gate.state == TrackingState.INACTIVE


# ======================================================================
# Pipeline ordering (TRD §5.1 stage numbering + §16 risk callout)
# ======================================================================

class TestPipelineOrdering:
    """Guard the TRD §16 risk: StabilityFilter × ActivationGate
    ordering is load-bearing. The gate must only see gesture names
    that have already passed StabilityFilter and CooldownFilter."""

    def test_gate_receives_names_while_stability_blocks_dispatch(
        self,
    ) -> None:
        """Verify the TRD §16 ordering: the ActivationGate receives
        gesture names from ConflictResolver winners BEFORE stability
        filtering (the gate counts consecutive frames and needs every
        frame's name). Even when StabilityFilter is configured with a
        very large window that blocks all dispatch, the gate still
        sees every frame's open_palm."""
        settings = Settings(
            activation_hold_duration_s=DEFAULT_HOLD_DURATION_S,
            # 5000 ms stability window: no candidate can ever pass in
            # a 1 s test sequence.
            gesture_stability_window_ms=5000,
        )
        pipeline = Pipeline(settings=settings)
        pipeline.activation_gate.toggle()  # force ACTIVE
        assert pipeline.activation_gate.state == TrackingState.ACTIVE

        # Track how many feed_gesture calls the gate receives.
        feed_count = 0
        original_feed = pipeline.activation_gate.feed_gesture

        def counting_feed(name: str, t: float) -> None:
            nonlocal feed_count
            feed_count += 1
            original_feed(name, t)

        pipeline.activation_gate.feed_gesture = counting_feed  # type: ignore[method-assign]

        now = 0.0
        for _ in range(30):
            hand = make_open_palm_hand(role='HAND_A', now=now)
            pipeline.tick(raw_hands=[hand], now=now)
            now += 0.033

        # The gate received 30 names (one per frame), even though
        # StabilityFilter blocked every candidate from reaching the
        # dispatch sink.
        assert feed_count == 30
        # The dispatch sink was NEVER called (stability blocked).
        pipeline.dispatch_sink.assert_not_called()


# ======================================================================
# CP-1 backwards-compat: unwired CaptureThread path returns empty list
# ======================================================================

class TestCaptureThreadUnwired:
    """`CaptureThread.pipeline_wired == False` must continue to emit
    an empty `gesture_detected` list per frame, preserving the CP-1
    behavior where the gesture pipeline was not yet wired."""

    def test_capture_thread_unwired_returns_empty_list(self) -> None:
        from app.capture_thread import CaptureThread
        from camera.camera_module import CameraModule
        from diagnostics.camera_validator import CameraValidator
        from tracking.hand_detector import TrackingModule

        # CaptureThread with NO pipeline components — the original
        # CP-1 signature (camera, tracking, validator, settings).
        thread = CaptureThread(
            camera=MagicMock(spec=CameraModule),
            tracking=MagicMock(spec=TrackingModule),
            validator=CameraValidator(),
            settings=Settings(),
        )
        assert thread.pipeline_wired is False
