"""Developer Mode debug overlay panel.

A pure-Python rendering function that overlays diagnostic information
onto a BGR frame. Activated by `Settings.developer_mode = True`
(per the existing settings schema, §TRD 7.1).

Implements TRD §9.3 (Debug Overlay — Developer Mode) as a minimal,
additive rendering layer that lives alongside the existing CP-1
skeleton + status-badge overlay in `overlay_window.py`. NO business
logic; this is a presentation-only module.

What this panel visualizes (per the Developer Mode spec):

    General:
        - FPS (from CameraValidator.measured_fps)
        - Number of detected hands
    For each detected hand:
        - Hand ID (HAND_A / HAND_B)              — `hand.role`
        - MediaPipe chirality                   — `hand.chirality`
        - Detection confidence                  — `hand.confidence`
                                                  (MediaPipe returns one combined score
                                                  per hand; shown as both detection and
                                                  tracking confidence with a note)
        - Tracking confidence                   — same combined score (see above)
        - Estimated hand scale                  — `hand.scale.smoothed_scale`,
                                                  palm_width, palm_height, bounding_box
                                                  (when populated by HandScaleEstimator)
        - Gesture eligibility                   — `hand.gesture_eligible`
        - Finger states                         — derived via `finger_states(hand.landmarks)`
        - Palm orientation                      — derived via wrist-vs-middle-MCP z
                                                  comparison (a rough "facing camera"
                                                  indicator)
        - Current gesture candidate             — populated when caller passes
                                                  `gesture_candidates` parameter
                                                  (currently N/A in CP-3 wire)
        - Final recognized gesture              — populated when caller passes
                                                  `final_gesture` parameter
                                                  (currently N/A in CP-3 wire)
        - Recognition confidence                — populated when caller passes
                                                  `final_gesture` parameter
                                                  (currently N/A in CP-3 wire)
        - Stability status                      — populated when caller passes
                                                  `stability_status` parameter
                                                  (currently N/A in CP-3 wire)
        - Cooldown status                       — populated when caller passes
                                                  `cooldown_status` parameter
                                                  (currently N/A in CP-3 wire)
        - Occlusion/Retained state              — `hand.is_retained`

Hot-path discipline (RULES §12.1): rendering a BGR frame with
~200-400 px of overlay text per hand is O(hand-count) and bounded —
no per-frame allocations beyond the cv2.putText call's internal
buffers. Performance impact on the overlay thread (separate from the
capture thread) is negligible.

RULES §2: this module does not import from `actions/`, `context/`, or
`executor.py`. It depends only on `models/`, `settings/`, and CP-2's
`gestures/gesture_utils.py` (for `finger_states`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import cv2
import numpy as np

from gestures.gesture_utils import (
    MIDDLE_MCP,
    WRIST,
    finger_states,
)
from models.data_models import HandData, HandScale


# ---------------------------------------------------------------------------
# Public configuration constants
# ---------------------------------------------------------------------------

PANEL_X: int = 8
PANEL_Y: int = 50                # below the existing minimal status badge
PANEL_FONT_SCALE: float = 0.5
PANEL_LINE_THICKNESS: int = 1
PANEL_TEXT_COLOR: tuple[int, int, int] = (255, 255, 255)   # BGR — white
PANEL_BG_COLOR: tuple[int, int, int] = (0, 0, 0)          # BGR — black
PANEL_BG_ALPHA: float = 0.55
PANEL_LINE_SPACING_PX: int = 18  # vertical spacing between text lines
PANEL_SECTION_GAP_PX: int = 8   # extra gap between sections (general / per-hand)
PANEL_INDENT_PX: int = 12       # horizontal indent for sub-fields
PANEL_RIGHT_MARGIN_PX: int = 8
PANEL_MIN_HEIGHT_PX: int = 60   # smallest drawable panel

#: A bounding cap on the panel width as a fraction of frame width. The
#: panel wraps lines that exceed this cap (defensive — typical field
#: text is much shorter than this).
PANEL_MAX_WIDTH_FRACTION: float = 0.42


# ---------------------------------------------------------------------------
# Optional per-frame gesture state (forward-compatible)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GesturePipelineState:
    """Optional per-hand gesture pipeline state passed into the
    Developer Mode panel.

    This is a forward-compatible input: when CP-4 wires
    `GestureEngine` → `ConflictResolver` → `StabilityFilter` →
    `CooldownFilter` results into the `CaptureThread.frame_ready`
    signal, the caller can pass that state here and the panel will
    render it automatically. Until then, the panel shows "N/A"
    for these fields.

    Designed as a frozen dataclass so it can be safely shared
    across threads (RULES §5.6 — capture thread owns this state,
    overlay thread reads a frozen snapshot).
    """
    # Per-hand-role (HAND_A / HAND_B) state. Missing roles render as
    # "N/A" so the panel never crashes on partial data.
    gesture_candidates: dict[str, str] | None = None      # role -> gesture_name(s)
    final_gesture: dict[str, str] | None = None          # role -> final gesture name
    final_gesture_confidence: dict[str, float] | None = None  # role -> conf
    stability_status: dict[str, str] | None = None       # role -> "held Xms" / "N/A"
    cooldown_status: dict[str, str] | None = None        # role -> "Xs remaining" / "ready"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _palm_orientation(hand: HandData) -> str:
    """Derive a rough palm-orientation indicator from existing landmark
    geometry (no new state).

    Uses wrist z vs middle-MCP z:
      - Middle MCP closer to camera (smaller z) than wrist: palm facing
        the camera ("FRONT").
      - Middle MCP farther from camera (larger z) than wrist: palm
        rotated away ("BACK").
      - Otherwise: indeterminate ("SIDE").

    This is a heuristic — MediaPipe does not expose a palm-normal
    vector directly. It is purely a presentation of existing data.
    """
    if len(hand.landmarks) <= max(WRIST, MIDDLE_MCP):
        return "N/A"
    wrist_z = hand.landmarks[WRIST][2]
    mid_mcp_z = hand.landmarks[MIDDLE_MCP][2]
    delta = mid_mcp_z - wrist_z
    # Threshold of 0.02 in normalized z is small enough to ignore
    # measurement noise but large enough to discriminate.
    if delta < -0.02:
        return "FRONT"
    if delta > 0.02:
        return "BACK"
    return "SIDE"


def _format_finger_states(hand: HandData) -> str:
    """Return a compact EXT/CURL string for the four non-thumb fingers."""
    states = finger_states(hand.landmarks)
    return (
        f"I:{('EXT' if states['index'] else 'CRL')} "
        f"M:{('EXT' if states['middle'] else 'CRL')} "
        f"R:{('EXT' if states['ring'] else 'CRL')} "
        f"P:{('EXT' if states['pinky'] else 'CRL')}"
    )


def _format_scale(hand: HandData) -> str:
    """Format the hand-scale sub-block. Returns "N/A" when scale is
    None (e.g., when HandScaleEstimator is not in the wire yet)."""
    if hand.scale is None:
        return "N/A (not yet estimated)"
    s: HandScale = hand.scale
    return (
        f"sm={s.smoothed_scale:.3f} "
        f"pw={s.palm_width:.3f} "
        f"ph={s.palm_height:.3f}"
    )


def _format_bbox(hand: HandData) -> str:
    if hand.scale is None:
        return ""
    bbox = hand.scale.bounding_box
    return (
        f"bbox=({bbox[0]:.2f},{bbox[1]:.2f})-"
        f"({bbox[2]:.2f},{bbox[3]:.2f})"
    )


def _get_gesture_state(
    state: GesturePipelineState | None,
    role: str | None,
    getter,
    default: str = "N/A",
) -> str:
    """Safely read a per-role field from GesturePipelineState.

    Returns `default` when the state is absent, when the role is
    None, or when the role is missing from the dict. Pure
    defensive read; no mutation.
    """
    if state is None or role is None:
        return default
    mapping = getter(state)
    if mapping is None:
        return default
    return str(mapping.get(role, default))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _measure_text_width(text: str, font_scale: float) -> int:
    """Return the pixel width that `text` would occupy when rendered."""
    (w, _h), _baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, PANEL_LINE_THICKNESS
    )
    return w


def _wrap_lines(lines: Sequence[str], max_width_px: int) -> list[str]:
    """Truncate any line that exceeds `max_width_px` with a trailing '…'.

    The Developer Mode panel is read-only diagnostic output; hard
    truncation is preferable to interactive word-wrapping (which would
    introduce allocation overhead per frame). Lines that fit are
    preserved as-is.
    """
    out: list[str] = []
    for line in lines:
        w = _measure_text_width(line, PANEL_FONT_SCALE)
        if w <= max_width_px:
            out.append(line)
            continue
        # Hard truncate. We approximate the visible-character count by
        # the ratio (cheap; avoids per-frame character-level width math).
        ratio = max_width_px / max(w, 1)
        cut = max(0, int(len(line) * ratio) - 1)
        out.append(line[:cut] + "…")
    return out


def _draw_text_block(
    frame: np.ndarray,
    lines: Sequence[str],
    x: int,
    y: int,
) -> int:
    """Render a list of lines top-to-bottom starting at (x, y).

    Returns the y-coordinate just below the last rendered line, so
    callers can stack additional blocks without recomputing layout.
    """
    cur_y = y
    for line in lines:
        cv2.putText(
            frame, line, (x, cur_y),
            cv2.FONT_HERSHEY_SIMPLEX, PANEL_FONT_SCALE,
            PANEL_TEXT_COLOR, PANEL_LINE_THICKNESS, cv2.LINE_AA,
        )
        cur_y += PANEL_LINE_SPACING_PX
    return cur_y


def _draw_background_panel(
    frame: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> None:
    """Draw a semi-transparent black backdrop behind a panel block.

    Mirrors the visual style of the existing CP-1 status badge
    (`_draw_status` in `overlay_window.py`): same BGR color,
    same alpha, same edge softness (none — hard rectangle, matches
    the rest of the overlay).
    """
    h, w = frame.shape[:2]
    x1 = min(x1, w)
    y1 = min(y1, h)
    if x1 <= x0 or y1 <= y0:
        return  # nothing to draw (frame too small for the panel)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), PANEL_BG_COLOR, -1)
    cv2.addWeighted(
        overlay[y0:y1, x0:x1], PANEL_BG_ALPHA,
        frame[y0:y1, x0:x1], 1.0 - PANEL_BG_ALPHA, 0,
        dst=frame[y0:y1, x0:x1],
    )


def render_debug_panel(
    frame: np.ndarray,
    hands: Iterable[HandData],
    fps: float,
    gesture_state: GesturePipelineState | None = None,
) -> np.ndarray:
    """Render the Developer Mode debug overlay onto `frame`.

    Args:
        frame: BGR frame (H, W, 3) uint8 — mutated in place AND returned.
        hands: per-frame HandData list (already post-TrackingModule
            in CP-1's wire; post-HandScaleEstimator in CP-2's wire;
            post-PrimaryHandFilter in CP-2's wire).
        fps: measured FPS from `CameraValidator.measured_fps()`.
        gesture_state: optional forward-compatible pipeline state. When
            None (the CP-3 wire situation), gesture-related fields
            render as "N/A". When provided by a future checkpoint that
            wires the gesture pipeline, the panel populates them
            automatically.

    Returns:
        The same `frame` object, mutated in place with the debug
        overlay drawn on top of whatever the existing skeleton + status
        badges have already drawn.
    """
    hands_list = list(hands)  # one-shot copy; we iterate twice
    h, w = frame.shape[:2]
    max_panel_width_px = int(w * PANEL_MAX_WIDTH_FRACTION)

    # Build the list of text lines to render (top-down).
    # Section 1: General
    activation_label = "INACTIVE"
    if gesture_state is not None:
        raw = getattr(gesture_state, 'activation_state', None)
        if raw is not None:
            activation_label = raw
    general_lines = [
        "=== DEVELOPER MODE ===",
        f"FPS:   {fps:5.1f}",
        f"Hands: {len(hands_list)}",
        f"State: {activation_label}",
    ]

    # Section 2: Per-hand detail. We render each hand as a sub-block
    # with consistent field order; this keeps the panel scannable.
    per_hand_lines: list[str] = []
    for i, hand in enumerate(hands_list):
        role = hand.role if hand.role is not None else "(unassigned)"
        chirality = hand.chirality if hand.chirality else "?"
        per_hand_lines.append(f"-- Hand {i} [{role} | {chirality}] --")
        per_hand_lines.append(
            f"  det_conf: {hand.confidence:.3f}  "
            f"trk_conf: {hand.confidence:.3f} (combined MediaPipe score)"
        )
        per_hand_lines.append(f"  gesture_eligible: {hand.gesture_eligible}")
        per_hand_lines.append(f"  is_retained: {hand.is_retained}")
        per_hand_lines.append(f"  scale: {_format_scale(hand)}")
        bbox_str = _format_bbox(hand)
        if bbox_str:
            per_hand_lines.append(f"  {bbox_str}")
        per_hand_lines.append(f"  palm_orient: {_palm_orientation(hand)}")
        per_hand_lines.append(f"  fingers: {_format_finger_states(hand)}")
        per_hand_lines.append(
            f"  candidates: {_get_gesture_state(gesture_state, hand.role, lambda s: s.gesture_candidates)}"
        )
        per_hand_lines.append(
            f"  final: {_get_gesture_state(gesture_state, hand.role, lambda s: s.final_gesture)}"
        )
        final_conf = _get_gesture_state(
            gesture_state, hand.role,
            lambda s: s.final_gesture_confidence,
        )
        if final_conf != "N/A":
            try:
                final_conf = f"{float(final_conf):.3f}"
            except (TypeError, ValueError):
                pass  # leave as-is
        per_hand_lines.append(f"  final_conf: {final_conf}")
        per_hand_lines.append(
            f"  stability: {_get_gesture_state(gesture_state, hand.role, lambda s: s.stability_status)}"
        )
        per_hand_lines.append(
            f"  cooldown: {_get_gesture_state(gesture_state, hand.role, lambda s: s.cooldown_status)}"
        )
        # Visual separator between hands (saves the reader from having
        # to scan column-aligned fields).
        if i != len(hands_list) - 1:
            per_hand_lines.append("")

    # Wrap long lines to fit the panel width.
    all_lines = _wrap_lines(general_lines, max_panel_width_px)
    if per_hand_lines:
        all_lines.append("")  # gap between General and Per-Hand sections
        all_lines.extend(_wrap_lines(per_hand_lines, max_panel_width_px))

    # Compute panel bounding box.
    line_count = max(len(all_lines), 1)
    panel_height = (
        PANEL_LINE_SPACING_PX * line_count + 2 * PANEL_SECTION_GAP_PX
    )
    panel_height = max(panel_height, PANEL_MIN_HEIGHT_PX)
    panel_width = max_panel_width_px

    # Position: top-left corner of the panel.
    x0, y0 = PANEL_X, PANEL_Y
    x1 = x0 + panel_width
    y1 = y0 + panel_height

    # Draw semi-transparent background (drawn FIRST so text is on top).
    _draw_background_panel(frame, x0, y0, x1, y1)

    # Render text.
    text_y = y0 + PANEL_LINE_SPACING_PX  # leave a small top margin
    for line in all_lines:
        if line == "":
            text_y += PANEL_SECTION_GAP_PX
            continue
        cv2.putText(
            frame, line, (x0 + 6, text_y),
            cv2.FONT_HERSHEY_SIMPLEX, PANEL_FONT_SCALE,
            PANEL_TEXT_COLOR, PANEL_LINE_THICKNESS, cv2.LINE_AA,
        )
        text_y += PANEL_LINE_SPACING_PX

    return frame