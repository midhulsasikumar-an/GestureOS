"""CaptureThread — owns the camera loop on a worker QThread.

Implements the threading model from TRD §2.2: the worker thread owns the
camera loop and runs the per-frame pipeline synchronously, then emits
Qt signals that the main thread consumes for UI updates.

Pipeline at Checkpoint 4 (TRD §5.1 + §16):

    read_frame
      → CameraValidator.record_frame
      → RGB convert
      → TrackingModule.detect
      → HandIdentityModule.assign_roles          (CP-2)
      → OcclusionHandler.bridge_gaps             (CP-2)
      → HandScaleEstimator.estimate (per hand)   (CP-2)
      → PrimaryHandFilter.filter                 (CP-2)
      → [if ActivationGate.state == ACTIVE]
            StaticGestureEngine.update_motion_history
            StaticGestureEngine.evaluate
            GestureFuser.resolve
            GestureGate.process  (Stability + Cooldown)
      → emit gesture_detected(cleared_results)

Context engine (Checkpoint 6+) and action dispatch (Checkpoint 5+)
slots are added incrementally by their respective checkpoints. The
`gesture_detected` signal is the wire that feeds CP-5 — CP-4 only
EMITS the cleared `GestureResult` list; it does NOT dispatch it.

RULES §12.1: the frame loop is kept allocation-light — no per-frame list
or dict allocations beyond the HandData list produced by `detect()`.
A persistent RGB conversion buffer is reused across frames to avoid a
new ndarray allocation on every iteration.
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from camera.camera_module import CameraModule
from camera.errors import CameraUnavailableError
from diagnostics.camera_validator import CameraValidator
from gestures.activation_gate import ActivationGate, TrackingState
from gestures.gesture_fuser import GestureFuser
from gestures.gesture_gate import GestureGate
from gestures.static_gesture_engine import StaticGestureEngine
from models.data_models import GestureResult, HandData
from settings.settings_manager import Settings
from tracking.hand_landmarker import TrackingModule, TrackingInitError
from tracking.hand_identity import HandIdentityModule
from tracking.hand_scale import HandScaleEstimator
from tracking.occlusion_handler import OcclusionHandler
from tracking.primary_hand_filter import PrimaryHandFilter

from diagnostics.pipeline_diagnostics import PipelineDiagnosticsCollector


logger = logging.getLogger('gestureos')


# Number of consecutive dropped frames that triggers a reconnect attempt
_DROP_RECONNECT_THRESHOLD = 10


class CaptureThread(QThread):
    """Background QThread that runs the per-frame capture pipeline.

    Signals (TRD §2.2 + Checkpoint 4):
        frame_ready(frame, hands, fps)        — payload for the overlay
        gesture_detected(results)             — NEW at CP-4: per-frame
                                                 list of cooldown-cleared
                                                 GestureResult objects
                                                 (empty list if none).
                                                 Consumed by the
                                                 orchestrator to drive
                                                 ActivationGate.feed_gesture
                                                 (FR-AM-04) and, in
                                                 CP-5+, action dispatch.
        camera_error(error_message)           — hard camera failure
        tracking_error(error_message)          — TrackingInitError after retries
        state_changed(running: bool)           — lifecycle transitions
    """

    frame_ready = pyqtSignal(object, object, float, object)
    """(frame, hands, fps, gesture_state) — payload for the overlay.

    `gesture_state` is a `SimpleNamespace` with the same attribute
    names as `GesturePipelineState` (from `overlay/debug_panel.py`):
      - `.gesture_candidates: dict[str, str] | None`
      - `.final_gesture: dict[str, str] | None`
      - `.final_gesture_confidence: dict[str, float] | None`
      - `.stability_status: dict[str, str] | None`
      - `.cooldown_status: dict[str, str] | None`
    When the pipeline is not wired or the gate is INACTIVE and no
    gesture state is available, `gesture_state` is `None` (the
    overlay renders "N/A" for all fields).
    """
    gesture_detected = pyqtSignal(object)
    frame_gesture_names = pyqtSignal(object)
    camera_error = pyqtSignal(str)
    tracking_error = pyqtSignal(str)
    state_changed = pyqtSignal(bool)

    def __init__(
        self,
        camera: CameraModule,
        tracking: TrackingModule,
        validator: CameraValidator,
        settings: Settings,
        hand_identity: HandIdentityModule | None = None,
        occlusion_handler: OcclusionHandler | None = None,
        scale_estimator: HandScaleEstimator | None = None,
        primary_hand_filter: PrimaryHandFilter | None = None,
        gesture_engine: StaticGestureEngine | None = None,
        gesture_fuser: GestureFuser | None = None,
        gesture_gate: GestureGate | None = None,
        activation_gate: ActivationGate | None = None,
    ) -> None:
        super().__init__()
        self._camera = camera
        self._tracking = tracking
        self._validator = validator
        self._settings = settings
        # CP-2/CP-3/CP-4 pipeline components. Each is optional so the
        # existing CP-1 test paths and any caller that has not yet
        # wired the new modules continue to construct cleanly. When
        # any component is `None`, the corresponding pipeline stage
        # is skipped (and the gesture-emission stage is skipped
        # entirely, preserving CP-1/CP-2/CP-3 behavior exactly).
        self._hand_identity = hand_identity
        self._occlusion_handler = occlusion_handler
        self._scale_estimator = scale_estimator
        self._primary_hand_filter = primary_hand_filter
        self._gesture_engine = gesture_engine
        self._gesture_fuser = gesture_fuser
        self._gesture_gate = gesture_gate
        self._activation_gate = activation_gate
        self._running = False
        # Persistent RGB buffer reused every frame (RULES §12.1).
        # Sized lazily on the first frame so we honour the camera's
        # negotiated width/height even when the driver overrides the
        # requested resolution.
        self._rgb_buf: np.ndarray | None = None
        # Per-frame pipeline outputs emitted on gesture_detected.
        # Allocated once and mutated in place per frame to avoid
        # per-frame list allocations (RULES §12.1).
        self._cleared_results: list[GestureResult] = []
        # CP-2 processed hands (with scale, role populated). Forwarded
        # to the overlay on the frame_ready signal so Developer Mode
        # can display scale, hand-role, and eligibility info.
        self._latest_pipeline_hands: list[HandData] = []
        # CP-3/CP-4 gesture pipeline state for the Developer Mode
        # overlay. Built from stability/cooldown/cleared-results each
        # frame; forwarded as the 4th arg of frame_ready.
        self._latest_gesture_state: object | None = None
        # Pipeline Diagnostics collector (observational only).
        self._diags = PipelineDiagnosticsCollector()
        self._frame_counter: int = 0


    # -- Pipeline introspection ------------------------------------------------

    @property
    def pipeline_wired(self) -> bool:
        """True iff every CP-2/CP-3/CP-4 pipeline component is wired.

        Used by the integration test and by GestureOSApp to gate
        whether the gesture_detected signal will actually carry
        results. When False, the pipeline runs only the CP-1/CP-2
        stages (TrackingModule + per-frame overlay update).
        """
        return all([
            self._hand_identity is not None,
            self._occlusion_handler is not None,
            self._scale_estimator is not None,
            self._primary_hand_filter is not None,
            self._gesture_engine is not None,
            self._gesture_fuser is not None,
            self._gesture_gate is not None,
            self._activation_gate is not None,
        ])

    # -- Diagnostics helpers -------------------------------------------------

    @staticmethod
    def _find_rejection_info(
        hands: list[HandData],
    ) -> tuple[str | None, str | None]:
        """Scan a hand list for the first filtered/discarded hand.

        Returns (status_reason, role) of the first hand whose status
        is neither ``accepted`` nor ``retained``, or (None, None) when
        no rejection is found.  Purely observational; no side effects.
        """
        for h in hands:
            if h.status not in ('accepted', 'retained'):
                return h.status_reason, h.role
        return None, None

    # -- Lifecycle -----------------------------------------------------------

    def stop(self) -> None:
        """Request the worker loop to exit at the next iteration."""
        self._running = False

    def run(self) -> None:
        """Main worker loop. Runs until stop() is called or hard failure."""
        self._running = True
        self.state_changed.emit(True)
        try:
            self._camera.open()
            self._tracking.initialize()
        except (CameraUnavailableError, TrackingInitError) as exc:
            self.camera_error.emit(str(exc))
            self._running = False
            self.state_changed.emit(False)
            return

        # FPS measurement — rolling counter recomputed each frame from
        # the validator's measured_fps() so we never allocate a per-frame
        # struct (RULES §12.1).
        last_log_ts = 0.0
        try:
            while self._running:
                t0 = time.monotonic()
                frame = self._camera.read_frame()
                if frame is None:
                    if self._camera.consecutive_drops >= _DROP_RECONNECT_THRESHOLD:
                        if not self._camera.reconnect():
                            self.camera_error.emit(
                                'Camera unavailable after reconnect attempts'
                            )
                            break
                        self._validator.reset()
                        self._tracking.initialize()
                        # The native dimensions may have changed after
                        # reconnect — drop the cached RGB buffer so it
                        # is reallocated against the new shape.
                        self._rgb_buf = None
                    continue

                self._validator.record_frame(t0)

                # Camera validation (cheap; recomputed every frame but
                # internally cached — see CameraValidator.check()).
                quality = self._validator.check(
                    now=t0,
                    resolution=self._camera.reported_resolution,
                )

                # MediaPipe wants RGB. We reuse a single buffer instead
                # of allocating a fresh ndarray every frame (RULES §12.1).
                # The buffer is contiguous float-free uint8 so cv2.cvtColor
                # can write into it in place.
                if (
                    self._rgb_buf is None
                    or self._rgb_buf.shape[:2] != frame.shape[:2]
                ):
                    self._rgb_buf = np.empty(frame.shape, dtype=frame.dtype)
                cv2.cvtColor(frame, cv2.COLOR_BGR2RGB, dst=self._rgb_buf)

                # Pipeline Diagnostics: begin per-frame collection.
                self._frame_counter += 1
                self._diags.begin_frame(self._frame_counter)

                hands: list[HandData] = []
                try:
                    t_detect = time.monotonic()
                    hands = self._tracking.detect(self._rgb_buf)
                    detect_ms = (time.monotonic() - t_detect) * 1000
                    reject_reason, reject_role = self._find_rejection_info(hands)
                    self._diags.record_stage(
                        "TrackingModule.detect", [],
                        hands, detect_ms,
                        rejection_reason=reject_reason,
                        rejected_hand_role=reject_role,
                    )
                except TrackingInitError as exc:
                    self.tracking_error.emit(str(exc))
                    break

                # CP-2/CP-3/CP-4 pipeline. Each stage is conditionally
                # executed only when its component was wired in
                # `__init__`. The CP-1 path (no pipeline components)
                # still works exactly as before: hands are emitted
                # to the overlay unchanged.
                # Ordering is fixed and matches TRD §5.1 stage
                # numbering. The post-TrackingModule order is:
                #   HandIdentityModule → OcclusionHandler →
                #   HandScaleEstimator (per hand) →
                #   PrimaryHandFilter →
                #   [ActivationGate check] →
                #   StaticGestureEngine → GestureFuser →
                #   GestureGate.
                # TRD §16 risk: StabilityFilter × ActivationGate
                # ordering is load-bearing — ActivationGate only sees
                # names that have ALREADY passed GestureGate. The integration test
                # `test_pipeline_end_to_end.py` guards this ordering.
                cleared_results = self._run_gesture_pipeline(hands, t0)

                fps = self._validator.measured_fps()
                # Emit CP-2 processed hands (with scale + role) when
                # the pipeline is wired; fall back to raw tracking
                # hands when unwired (CP-1 path). The 4th arg carries
                # the gesture pipeline state for the Developer Mode
                # overlay (or None when no state is available).
                overlay_hands = (
                    self._latest_pipeline_hands
                    if self.pipeline_wired
                    else hands
                )
                self.frame_ready.emit(
                    frame, overlay_hands, fps, self._latest_gesture_state
                )
                # Always emit gesture_detected (possibly empty list)
                # so CP-5 consumers can rely on the signal firing
                # every frame. Empty list == "no gesture this frame".
                self.gesture_detected.emit(cleared_results)

                # Pipeline Diagnostics: structured DEBUG logging.
                diags = self._diags.frame_diagnostics
                if diags.stages:
                    for snap in diags.stages.values():
                        logger.debug(
                            'pipeline_stage',
                            extra={'extras': {
                                'frame': diags.frame_number,
                                'stage': snap.stage_name,
                                'input': snap.input_hand_count,
                                'output': snap.output_hand_count,
                                'time_ms': snap.processing_time_ms,
                                'rejection_reason': snap.rejection_reason,
                                'rejected_role': snap.rejected_hand_role,
                                'first_fail': diags.first_failing_stage,
                            }},
                        )
                    if diags.latest_rejection:
                        ev = diags.latest_rejection
                        logger.debug(
                            'pipeline_rejection',
                            extra={'extras': {
                                'frame': ev.frame_number,
                                'stage': ev.stage_name,
                                'reason': ev.reason,
                                'hand_role': ev.hand_role,
                            }},
                        )

                # Throttled status log — once per ~1s
                if t0 - last_log_ts >= 1.0:
                    last_log_ts = t0
                    logger.debug(
                        'capture_thread',
                        extra={'extras': {
                            'measured_fps': round(fps, 2),
                            'fps_ok': quality.fps_ok,
                            'resolution_ok': quality.resolution_ok,
                            'hands': len(hands),
                            'cleared_results': len(cleared_results),
                        }},
                    )

                # Frame pacing: cap the loop at the camera's target FPS
                # only when a frame iteration completed significantly
                # faster than the target. cap.read() already blocks for
                # the next frame, so this sleep is a backstop for the
                # rare case where CPU work is faster than the camera.
                target_period = 1.0 / max(1, self._settings.target_fps)
                elapsed = time.monotonic() - t0
                if elapsed < target_period:
                    time.sleep(target_period - elapsed)
        finally:
            self._camera.release()
            self._tracking.close()
            self._running = False
            self.state_changed.emit(False)

    # -- Pipeline implementation --------------------------------------------

    def _run_gesture_pipeline(
        self,
        hands: list[HandData],
        now: float,
    ) -> list[GestureResult]:
        """Run the CP-2/CP-3/CP-4 per-frame pipeline.

        Returns the list of cooldown-cleared `GestureResult` objects
        ready for downstream consumption (CP-5 dispatch + the
        orchestrator's ActivationGate feed). Returns an empty list
        when:
          - any CP-2/CP-3/CP-4 component is unwired (CP-1 path), or
          - the activation gate is INACTIVE (FR-AM-01: gesture
            processing pipeline must be bypassed), or
          - no gestures fired this frame.

        Hot-path discipline (RULES §6.4):
          - Each component owns its own hot-path-never-raises
            contract; this method does not double-wrap with try/except
            because adding it would mask real bugs without benefit.
          - The persistent `_cleared_results` list is cleared and
            refilled in place each frame to avoid per-frame list
            allocations (RULES §12.1).

        Ordering (TRD §5.1 stage 9 + TRD §16 explicit risk callout):
          HandIdentity → Occlusion → Scale → PrimaryHand →
          [ActivationGate.state == ACTIVE] →
          StaticGestureEngine.update_motion_history → StaticGestureEngine.evaluate →
          GestureFuser → GestureGate.process.
        """
        # CP-1 / unwired path — no gesture pipeline yet, or only a
        # partial wire-up from a future checkpoint. Preserve the
        # original behavior: emit raw hands (no scale/role) and
        # empty gesture state so the overlay shows "N/A".
        if not self.pipeline_wired:
            self._cleared_results.clear()
            self._latest_pipeline_hands = list(hands)
            self._latest_gesture_state = None
            return self._cleared_results

        # CP-2: HandIdentityModule → OcclusionHandler → ScaleEstimator
        # → PrimaryHandFilter. Always runs (even when INACTIVE) so
        # the overlay receives hands WITH scale and role populated.
        try:
            t0 = time.monotonic()
            identified = self._hand_identity.assign_roles(hands, now)
            self._diags.record_stage(
                "HandIdentityModule.assign_roles",
                hands, identified,
                (time.monotonic() - t0) * 1000,
            )

            t0 = time.monotonic()
            bridged = self._occlusion_handler.bridge_gaps(identified, now)
            self._diags.record_stage(
                "OcclusionHandler.bridge_gaps",
                identified, bridged,
                (time.monotonic() - t0) * 1000,
            )

            t0 = time.monotonic()
            scaled = [self._scale_estimator.estimate(h) for h in bridged]
            self._diags.record_stage(
                "HandScaleEstimator",
                bridged, scaled,
                (time.monotonic() - t0) * 1000,
            )

            t0 = time.monotonic()
            filtered = self._primary_hand_filter.filter(scaled)
            pf_ms = (time.monotonic() - t0) * 1000
            reject_reason, reject_role = self._find_rejection_info(filtered)
            self._diags.record_stage(
                "PrimaryHandFilter", scaled, filtered, pf_ms,
                rejection_reason=reject_reason,
                rejected_hand_role=reject_role,
            )
        except Exception as exc:  # noqa: BLE001 — defensive; per-component guards already exist
            logger.error(
                'capture_thread',
                extra={'extras': {
                    'event': 'cp2_pipeline_failed',
                    'error': str(exc),
                }},
            )
            self._cleared_results.clear()
            self._latest_pipeline_hands = list(hands)
            self._latest_gesture_state = None
            return self._cleared_results

        # Store the CP-2 processed hands for the overlay (these have
        # role, scale, and gesture_eligible populated — the overlay
        # renders scale values, hand roles, and gesture eligibility
        # from `hand_data`).
        self._latest_pipeline_hands = list(filtered)
        # Every CP-2 frame yields a base gesture state even when
        # INACTIVE (candidates/final/stability/cooldown are
        # "no result" placeholders rather than N/A).
        self._latest_gesture_state = self._build_gesture_state(
            candidates=[],
            winners=[],
            cleared_results=[],
            now=now,
        )

        # CP-3: StaticGestureEngine → GestureFuser. The winners are
        # fed into the ActivationGate's hold-timer BEFORE the
        # GestureGate filtering, because the gate counts consecutive
        # frames (TRD §5.3 "same discipline as StabilityFilter") and
        # needs to see the gesture name on EVERY frame — not just on
        # frames where the cooldown has elapsed (which would suppress
        # the gate's hold-timer for up to 500 ms per cooldown cycle).
        #
        # IMPORTANT: CP-3 runs REGARDLESS of activation state. The
        # ActivationGate MUST receive `feed_gesture` calls on every
        # frame so it can count consecutive Open Palm frames and
        # toggle itself from INACTIVE → ACTIVE (FR-AM-01 bypasses
        # the DISPATCH path only — gesture recognition must still
        # run to detect the toggle gesture).
        #
        # The gate check below (after CP-3) only suppresses the
        # `cleared_results` list when INACTIVE, preventing CP-5
        # action dispatch without blocking the recognition needed
        # for the hold-timer to work.
        try:
            t0 = time.monotonic()
            self._gesture_engine.update_motion_history(filtered, now)
            self._diags.record_stage(
                "GestureEngine.update_motion_history",
                filtered, filtered,
                (time.monotonic() - t0) * 1000,
            )

            t0 = time.monotonic()
            candidates = self._gesture_engine.evaluate(filtered, now)
            self._diags.record_stage(
                "GestureEngine.evaluate",
                filtered, candidates,
                (time.monotonic() - t0) * 1000,
            )

            t0 = time.monotonic()
            winners = self._gesture_fuser.resolve(candidates)
            self._diags.record_stage(
                "GestureFuser.resolve",
                candidates, winners,
                (time.monotonic() - t0) * 1000,
            )

            # Emit frame-level gesture names for repeat tracking
            # (pre-gesture-gate, so the tracker sees every frame even
            # when StabilityFilter blocks re-emission).
            winners_by_role: dict[str, str] = {}
            for w in winners:
                if w.gesture_name:
                    winners_by_role[w.hand_role] = w.gesture_name
            self.frame_gesture_names.emit(winners_by_role)

            # Feed the gate with the set of conflict-resolved winners
            # for this frame (pre-gesture-gate). Uses
            # ``frame_feed_gestures`` so that only one feed decision
            # is made per frame — preventing a multi-hand interleaving
            # bug where a non-toggle winner from one hand resets the
            # hold timer in the same frame that a toggle winner from
            # the other hand starts it.
            self._activation_gate.frame_feed_gestures(
                [w.gesture_name for w in winners], now,
            )

            # Apply GestureGate (StabilityFilter + CooldownFilter in one pass).
            self._cleared_results.clear()
            t0 = time.monotonic()
            self._cleared_results = self._gesture_gate.process(winners, now)
            gate_ms = (time.monotonic() - t0) * 1000
            self._diags.record_stage(
                "GestureGate", winners, self._cleared_results, gate_ms,
            )

            # Rebuild the gesture state with the richer CP-3/CP-4 data
            # (candidates, winners, stability, cooldown status).
            self._latest_gesture_state = self._build_gesture_state(
                candidates=candidates,
                winners=winners,
                cleared_results=self._cleared_results,
                now=now,
            )
        except Exception as exc:  # noqa: BLE001 — defensive
            logger.error(
                'capture_thread',
                extra={'extras': {
                    'event': 'cp3_pipeline_failed',
                    'error': str(exc),
                }},
            )
            self._cleared_results.clear()

        # FR-AM-01: suppress dispatch (cleared_results) when INACTIVE.
        # CP-3 still ran so the ActivationGate can count Open Palm
        # frames and toggle itself to ACTIVE on hold-timer satisfaction.
        if self._activation_gate.state != TrackingState.ACTIVE:
            self._cleared_results.clear()
            self._diags.record_rejection(
                "ActivationGate",
                reason="gate_inactive",
                hand_role=None,
            )

        return self._cleared_results

    # -- Gesture-state builder for Developer Mode overlay -------------------

    def _build_gesture_state(
        self,
        candidates: list[GestureResult],
        winners: list[GestureResult],
        cleared_results: list[GestureResult],
        now: float,
    ) -> SimpleNamespace:
        """Build a `SimpleNamespace` matching the `GesturePipelineState`
        shape consumed by `overlay/debug_panel.py`.

        The returned object has attributes:
          - `.gesture_candidates: dict[str, str] | None`
          - `.final_gesture: dict[str, str] | None`
          - `.final_gesture_confidence: dict[str, float] | None`
          - `.stability_status: dict[str, str] | None`
          - `.cooldown_status: dict[str, str] | None`

        Every attribute is a per-HAND-ROLE mapping. When no data is
        available for a given role, the debug panel's `_get_gesture_state`
        renders "N/A".
        """
        # Conflict-resolved winners (one per role) → "final gesture".
        final_gesture: dict[str, str] = {}
        final_gesture_confidence: dict[str, float] = {}
        for w in winners:
            if w.gesture_name:
                final_gesture[w.hand_role] = w.gesture_name
                final_gesture_confidence[w.hand_role] = w.confidence

        # Overwrite with cooldown-cleared results when available
        # (cleared_results are a subset of winners that passed every
        # gate — they are the "most final" state).
        for r in cleared_results:
            if r.gesture_name:
                final_gesture[r.hand_role] = r.gesture_name
                final_gesture_confidence[r.hand_role] = r.confidence

        # Stability status from GestureGate.stability.holds_in_progress.
        stability_status: dict[str, str] = {}
        if self._gesture_gate is not None:
            for role, (name, start_s) in self._gesture_gate.stability.holds_in_progress.items():
                elapsed_ms = int((now - start_s) * 1000)
                stability_status[role] = f"held {elapsed_ms}ms"

        # Cooldown status from GestureGate.cooldown.remaining_ms().
        cooldown_status: dict[str, str] = {}
        if self._gesture_gate is not None:
            for (role, gesture_name), last_ts in (
                self._gesture_gate.cooldown.last_trigger_snapshot.items()
            ):
                remaining = self._gesture_gate.cooldown.remaining_ms(
                    role, gesture_name, now
                )
                if remaining > 0:
                    cooldown_status[f"{role}:{gesture_name}"] = (
                        f"{remaining}ms remaining"
                    )

        # Raw candidates from GestureEngine (pre-ConflictResolver);
        # shown as "candidates" in the debug panel. When multiple
        # candidates exist for the same role, join them with " | ".
        gesture_candidates: dict[str, str] = {}
        # Candidate detail for source/confidence display.
        candidate_detail: dict[str, list[tuple[str, str, float]]] = {}
        for c in candidates:
            if not c.gesture_name:
                continue
            existing = gesture_candidates.get(c.hand_role, '')
            if existing:
                gesture_candidates[c.hand_role] = f"{existing} | {c.gesture_name}"
            else:
                gesture_candidates[c.hand_role] = c.gesture_name
            source = c.source if c.source else 'custom'
            candidate_detail.setdefault(c.hand_role, []).append(
                (c.gesture_name, source, c.confidence)
            )

        return SimpleNamespace(
            gesture_candidates=gesture_candidates or None,
            final_gesture=final_gesture or None,
            final_gesture_confidence=final_gesture_confidence or None,
            stability_status=stability_status or None,
            cooldown_status=cooldown_status or None,
            candidate_detail=candidate_detail or None,
            activation_state=(
                self._activation_gate.state.name
                if self._activation_gate is not None
                else 'INACTIVE'
            ),
            pipeline_diagnostics=self._diags.frame_diagnostics,
        )