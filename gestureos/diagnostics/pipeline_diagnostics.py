"""Per-frame pipeline diagnostics collector — debugging hand-tracking dropouts.

This module provides a purely observational instrumentation layer that
records per-stage hand counts, timing, and rejection events without
modifying any recognition logic, thresholds, or pipeline architecture.

Designed as a standalone collector consumed by:
  - `CaptureThread` — wraps each `_run_gesture_pipeline()` stage call
  - `overlay/debug_panel.py` — renders the Pipeline Diagnostics section
  - `diagnostics/diagnostics_manager.py` — structured DEBUG logging

Hot-path discipline: per-frame allocation is bounded (one dataclass per
stage, ~11 stages max). No external dependencies beyond `dataclasses`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class RejectionEvent:
    """A hand removal / filter / rejection at a specific pipeline stage."""

    stage_name: str
    hand_role: str | None
    reason: str
    frame_number: int


@dataclass
class StageSnapshot:
    """Recorded state for one pipeline stage invocation on one frame."""

    stage_name: str
    input_hand_count: int
    output_hand_count: int
    processing_time_ms: float
    rejection_reason: str | None = None
    rejected_hand_role: str | None = None


@dataclass
class FrameDiagnostics:
    """Complete diagnostics snapshot for one frame."""

    frame_number: int
    stages: dict[str, StageSnapshot] = field(default_factory=dict)
    _rejection_events: list[RejectionEvent] = field(default_factory=list)

    # -- Derived properties --------------------------------------------------

    @property
    def first_failing_stage(self) -> str | None:
        """Return the name of the first stage where a hand was lost/rejected.

        A stage 'fails' when either:
          - output_hand_count < input_hand_count (hand was dropped), or
          - a rejection_reason is recorded (hand was filtered/discarded).

        Stages are evaluated in insertion order of the `stages` dict,
        which matches pipeline execution order.
        """
        for snap in self.stages.values():
            if snap.output_hand_count < snap.input_hand_count:
                return snap.stage_name
            if snap.rejection_reason is not None:
                return snap.stage_name
        return None

    @property
    def latest_rejection(self) -> RejectionEvent | None:
        """Return the most recent rejection event (or None)."""
        if self._rejection_events:
            return self._rejection_events[-1]
        return None

    @property
    def rejection_events(self) -> list[RejectionEvent]:
        """All rejection events for this frame (chronological)."""
        return list(self._rejection_events)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class PipelineDiagnosticsCollector:
    """Records per-stage diagnostics for one frame at a time.

    Usage::

        collector = PipelineDiagnosticsCollector()
        collector.begin_frame(frame_number=1423)

        t0 = time.monotonic()
        output = some_stage(input)
        dt = (time.monotonic() - t0) * 1000
        collector.record_stage("SomeStage", input, output, dt)

        diags = collector.frame_diagnostics
        print(diags.first_failing_stage)       # "SomeStage"
        print(diags.latest_rejection.reason)   # "handedness_missing"
    """

    def __init__(self) -> None:
        self._frame_number: int = 0
        self._stages: dict[str, StageSnapshot] = {}
        self._rejection_events: list[RejectionEvent] = []

    # -- Per-frame lifecycle -------------------------------------------------

    def begin_frame(self, frame_number: int) -> None:
        """Reset all per-frame state and start a new frame."""
        self._frame_number = frame_number
        self._stages.clear()
        self._rejection_events.clear()

    # -- Recording -----------------------------------------------------------

    def record_stage(
        self,
        stage_name: str,
        input_hands: list,
        output_hands: list,
        processing_time_ms: float,
        rejection_reason: str | None = None,
        rejected_hand_role: str | None = None,
    ) -> None:
        """Record a snapshot for one pipeline stage.

        Args:
            stage_name: Human-readable name (e.g. ``"TrackingModule.detect"``).
            input_hands: Incoming hand list (list[HandData] or similar).
            output_hands: Outgoing hand / result list.
            processing_time_ms: Wall-clock duration of the stage in ms.
            rejection_reason: If a hand was rejected at this stage, a short
                string explaining why (e.g. ``"handedness_missing"``).
            rejected_hand_role: The role of the rejected hand, if available
                (``"HAND_A"``, ``"HAND_B"``, or ``None``).
        """
        snap = StageSnapshot(
            stage_name=stage_name,
            input_hand_count=len(input_hands),
            output_hand_count=len(output_hands),
            processing_time_ms=round(processing_time_ms, 2),
            rejection_reason=rejection_reason,
            rejected_hand_role=rejected_hand_role,
        )
        self._stages[stage_name] = snap

        if rejection_reason is not None:
            event = RejectionEvent(
                stage_name=stage_name,
                hand_role=rejected_hand_role,
                reason=rejection_reason,
                frame_number=self._frame_number,
            )
            self._rejection_events.append(event)

    def record_rejection(
        self,
        stage_name: str,
        reason: str,
        hand_role: str | None = None,
    ) -> None:
        """Record a stand-alone rejection event without a stage snapshot.

        Used when a hand is rejected outside a stage boundary (e.g. the
        ActivationGate's INACTIVE suppression).  The event is appended to
        the frame's rejection list for display and logging.
        """
        event = RejectionEvent(
            stage_name=stage_name,
            hand_role=hand_role,
            reason=reason,
            frame_number=self._frame_number,
        )
        self._rejection_events.append(event)

    # -- Accessors -----------------------------------------------------------

    @property
    def frame_diagnostics(self) -> FrameDiagnostics:
        """Snapshot of the current frame's diagnostics."""
        return FrameDiagnostics(
            frame_number=self._frame_number,
            stages=dict(self._stages),
            _rejection_events=list(self._rejection_events),
        )

    @property
    def frame_number(self) -> int:
        return self._frame_number
