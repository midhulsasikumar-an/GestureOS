"""HandScaleEstimator — per-frame hand-scale reference.

Implements TRD §3.7 and PRD §6 / FR-SC-01..04.

Responsibilities (TRD §3.7):
    - Compute palm width (landmark 5 ↔ 17) every frame
    - Compute palm height (landmark 0 ↔ 9) every frame
    - Compute bounding box (min_x, min_y, max_x, max_y) every frame
    - Maintain a 5-frame moving average of the raw scale value to
      suppress per-frame estimation jitter (PRD FR-SC-02)
    - Populate `HandData.scale: HandScale` with `palm_width`,
      `palm_height`, `bounding_box`, `smoothed_scale`

Scale-invariance contract (PRD §5, TRD §4.2):
    Every distance-based gesture rule in CP-3 divides its raw landmark
    distance by `HandData.scale.smoothed_scale`. Because palm
    width/height shrink and grow by the same camera-distance factor as
    any other landmark-to-landmark distance, the ratio is invariant to
    the user's distance from the camera.

RULES §2.4: does not import from recognizer / conflict_resolver / executor.
RULES §6.4: hot-path — never raises.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import replace
from typing import Iterable

from models.data_models import HandData, HandScale
from gestures.gesture_utils import euclidean_distance, WRIST, INDEX_MCP, PINKY_MCP


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.7, PRD FR-SC-02)
# ---------------------------------------------------------------------------

# Window length for the per-role moving-average smoothing. PRD FR-SC-02
# mandates smoothing ("e.g., simple moving average over the last 5
# frames"); TRD §3.7 hard-codes 5 frames.
SMOOTHING_WINDOW: int = 5

# Required number of landmarks for a valid HandScale computation.
# Anything fewer than 21 is malformed and yields `scale=None` per
# PRD FR-SC-04 ("skip evaluation, don't guess").
LANDMARKS_PER_HAND: int = 21


class HandScaleEstimator:
    """Computes and smooths a per-hand scale reference.

    Smooths independently per hand role. If a hand arrives with a role
    that has not yet been seen, the buffer for that role is auto-created.
    """

    def __init__(
        self,
        smoothing_window: int = SMOOTHING_WINDOW,
    ) -> None:
        if smoothing_window <= 0:
            raise ValueError(f'smoothing_window must be > 0; got {smoothing_window}')
        self.smoothing_window = int(smoothing_window)
        # role -> deque[float] of recent raw-scale samples.
        # Lazily populated per role (the TRD reference pre-allocates
        # only HAND_A/HAND_B; this implementation is more general).
        self._history: dict[str, deque[float]] = {}

    # -- Public API ----------------------------------------------------------

    def estimate(self, hand: HandData) -> HandData:
        """Compute `HandData.scale` for one hand. Returns a new HandData.

        Returns the input unchanged (modulo a defensive `scale=None`
        assignment for malformed hands) when landmark data is missing
        — this is the PRD FR-SC-04 contract: skip evaluation, don't guess.

        Never raises (RULES §6.4 hot-path).
        """
        try:
            return self._estimate_impl(hand)
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'hand_scale',
                extra={'extras': {
                    'event': 'estimate_failed',
                    'role': hand.role,
                    'error': str(exc),
                }},
            )
            return replace(hand, scale=None)

    def estimate_all(self, hands: list[HandData]) -> list[HandData]:
        """Apply `estimate()` to every hand in the list. Returns a new list."""
        return [self.estimate(h) for h in hands]

    # -- Internal implementation --------------------------------------------

    def _estimate_impl(self, hand: HandData) -> HandData:
        if len(hand.landmarks) != LANDMARKS_PER_HAND:
            # Malformed (should not happen post-TrackingModule but we
            # never assume on the hot path).
            logger.warning(
                'hand_scale',
                extra={'extras': {
                    'event': 'malformed_hand_scale_skipped',
                    'landmark_count': len(hand.landmarks),
                }},
            )
            return replace(hand, scale=None)

        palm_width = euclidean_distance(
            hand.landmarks[INDEX_MCP], hand.landmarks[PINKY_MCP]
        )
        palm_height = euclidean_distance(
            hand.landmarks[WRIST], hand.landmarks[9]  # landmark 9 = middle MCP
        )
        raw_scale = (palm_width + palm_height) / 2.0

        xs = [lm[0] for lm in hand.landmarks]
        ys = [lm[1] for lm in hand.landmarks]
        bbox = (min(xs), min(ys), max(xs), max(ys))

        # Per-role smoothing buffer. Use 'UNASSIGNED' as a sentinel if
        # hand.role is None (this happens if OcclusionHandler didn't
        # run yet, or HandIdentityModule hasn't been wired). The
        # sentinel avoids a KeyError without polluting the real-role
        # buffers.
        role = hand.role if hand.role is not None else '__unassigned__'
        hist = self._history.get(role)
        if hist is None:
            hist = deque(maxlen=self.smoothing_window)
            self._history[role] = hist
        hist.append(raw_scale)
        smoothed = sum(hist) / len(hist)

        return replace(
            hand,
            scale=HandScale(
                palm_width=palm_width,
                palm_height=palm_height,
                bounding_box=bbox,
                smoothed_scale=smoothed,
            ),
        )

    # -- Read-only introspection --------------------------------------------

    @property
    def history_snapshot(self) -> dict[str, tuple[float, ...]]:
        """Read-only view of the rolling-scale buffers, used by tests
        and the debug overlay (PRD §12.3 implicit).
        """
        return {role: tuple(buf) for role, buf in self._history.items()}

    def reset(self) -> None:
        """Clear all smoothing history. Used on camera reconnect / pipeline restart."""
        for buf in self._history.values():
            buf.clear()