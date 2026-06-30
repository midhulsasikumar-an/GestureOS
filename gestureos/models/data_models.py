"""Shared data objects for GestureOS.

Implements TRD §6 (Data Models). Every cross-component data object lives
here as a frozen-styled @dataclass with no business logic beyond simple
derived-property accessors (AI Development Guide §4.1, §6.3, §6.6).

Checkpoint 0 (Project Foundation): all dataclasses are STUBBED. Fields
are present per the TRD schema; behavior arrives in the checkpoint that
introduces the component that produces or consumes each object. This
avoids premature coupling (Implementation Plan §4 Definition of Done:
'No component outside `models/`, `settings/`, `diagnostics/`, `tests/`,
and root-level config files has been created').
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# HandData and its v1.2 extensions
# ---------------------------------------------------------------------------

@dataclass
class HandScale:
    """Hand-scale reference used to normalize every distance/motion measurement.

    Implements TRD §3.7 (HandScaleEstimator) data shape. Smoothing happens
    upstream; this dataclass only holds the values produced.
    """
    palm_width: float
    palm_height: float
    bounding_box: tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
    smoothed_scale: float


@dataclass
class HandData:
    """Per-frame per-hand landmark container.

    Implements TRD §6.1 (extended in v1.2 with scale, gesture_eligible,
    is_retained; extended in CP-4 Tracking Stabilization with
    tracking_confidence, status, status_reason).
    """
    landmarks: list[tuple[float, float, float]]   # 21 (x, y, z), normalized
    chirality: str                                  # 'Left' | 'Right' | None
    confidence: float
    role: str | None = None                         # 'HAND_A' | 'HAND_B'
    scale: HandScale | None = None                   # NEW v1.2 — populated by HandScaleEstimator
    gesture_eligible: bool = True                     # NEW v1.2 — set by PrimaryHandFilter
    is_retained: bool = False                          # NEW v1.2 — True if from OcclusionHandler bridge
    # NEW CP-4 Tracking Stabilization — per-hand diagnostic state. All
    # fields have defaults so existing call sites and `dataclasses.replace`
    # usage continue to work. These fields are populated by the
    # tracking/CP-2 stages and consumed by the Developer Mode debug panel.
    #   tracking_confidence: a separate per-hand tracking score where
    #     MediaPipe exposes one; None when MediaPipe's API does not
    #     surface a separate score (MediaPipe 0.10.14 currently does
    #     not — `confidence` carries the combined presence + handedness
    #     score).
    #   status: 'accepted' | 'retained' | 'filtered' | 'discarded'.
    #   status_reason: short string explaining the status; None for
    #     'accepted'. Used by the debug panel and structured logs.
    tracking_confidence: float | None = None
    status: str = 'accepted'
    status_reason: str | None = None


# ---------------------------------------------------------------------------
# Recognition output
# ---------------------------------------------------------------------------

@dataclass
class GestureResult:
    """One gesture candidate emitted by GestureEngine.

    Implements TRD §6.2. At Checkpoint 0 this is a pure data carrier —
    no behavior, no defaults beyond the field declarations.
    """
    gesture_name: str
    confidence: float
    is_dynamic: bool
    hand_role: str
    timestamp: float


# ---------------------------------------------------------------------------
# Action dispatch
# ---------------------------------------------------------------------------

@dataclass
class Action:
    """Resolved action to be dispatched.

    Implements TRD §6.3. 'cursor_move' is the v1.2 addition for the
    CursorController dispatch path; all other action_types predate v1.2.
    """
    action_type: str   # 'mouse' | 'keyboard' | 'system' | 'app_launch' | 'cursor_move'
    params: dict
    gesture_name: str
    context: str


@dataclass
class ActionResult:
    """Result of an action dispatch attempt.

    Implements TRD §6.3.
    """
    success: bool
    action: Action | None
    error: str | None


# ---------------------------------------------------------------------------
# Quality monitoring (NEW v1.2)
# ---------------------------------------------------------------------------

@dataclass
class CameraQuality:
    """Camera quality snapshot produced by CameraValidator.

    Implements TRD §6.4.
    """
    fps_ok: bool
    resolution_ok: bool
    measured_fps: float


@dataclass
class LightingQuality:
    """Lighting quality snapshot produced by LightingMonitor.

    Implements TRD §6.4.
    """
    is_low: bool
    mean_luminance: float


# ---------------------------------------------------------------------------
# Calibration (NEW v1.2)
# ---------------------------------------------------------------------------

@dataclass
class TrackingZone:
    """Calibrated active-tracking zone, normalized 0..1 in frame coords.

    Implements TRD §10.1. map_to_screen() is a small derived property
    (coordinate transform) — allowed in models/ per AI Guide §6.3's
    'simple derived-property accessors' allowance.
    """
    top_left: tuple[float, float]      # normalized frame coordinates
    bottom_right: tuple[float, float]

    def map_to_screen(
        self,
        hand_x: float,
        hand_y: float,
        screen_w: int,
        screen_h: int,
    ) -> tuple[int, int]:
        """Map a hand position inside the calibrated zone to screen pixels."""
        zx0, zy0 = self.top_left
        zx1, zy1 = self.bottom_right
        norm_x = (hand_x - zx0) / (zx1 - zx0) if zx1 != zx0 else 0.5
        norm_y = (hand_y - zy0) / (zy1 - zy0) if zy1 != zy0 else 0.5
        return int(norm_x * screen_w), int(norm_y * screen_h)


# ---------------------------------------------------------------------------
# Profile (TRD v1.0 — unchanged shape in v1.2)
# ---------------------------------------------------------------------------

@dataclass
class Profile:
    """A user profile bundling a set of gesture-to-action mappings.

    Implements TRD §6.5 (Profile is unchanged from TRD v1.0). The actual
    mapping payloads are stored in profile-specific JSON files; this
    dataclass holds the metadata.
    """
    id: str
    name: str
    is_default: bool = False
    mappings: list[dict[str, Any]] = field(default_factory=list)
