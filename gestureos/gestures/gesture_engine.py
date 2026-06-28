"""GestureEngine — Checkpoint 3.

Implements TRD §3.9 (GestureEngine) and PRD §4.6 (Candidate
Generation stage).

The engine evaluates every registered rule (8 static + 6 dynamic) on
the per-frame input and returns ALL qualifying candidates. Selection
between competing candidates is the job of `ConflictResolver`
(§3.9.1) — the engine itself does NOT short-circuit on the first
match (this is the deliberate, documented change from the v1.0
"first-match-wins" implicit ordering per the TRD §3.9 implementation
note).

RULES §6.4: hot-path — never raises. `hand.scale is None` per hand
is handled by skipping that hand's static evaluation entirely (the
dynamic rules are unaffected — they consume `MotionHistoryBuffer`
which is scale-independent per PRD FR-MH-03).
"""

from __future__ import annotations

import logging
import time
from typing import Iterable

from gestures.dynamic_recognizer import DYNAMIC_GESTURE_RULES
from gestures.motion_history import MotionHistoryBuffer
from gestures.static_recognizer import STATIC_GESTURE_RULES
from models.data_models import GestureResult, HandData
from settings.settings_manager import Settings


logger = logging.getLogger('gestureos')


class GestureEngine:
    """Per-frame gesture candidate generation.

    The engine holds the `MotionHistoryBuffer` (the only stateful
    component consumed by the dynamic rules). All other state lives
    upstream (`HandIdentityModule`, `HandScaleEstimator`,
    `PrimaryHandFilter`); the engine itself does not track hand
    roles internally — the `HandData.role` value is set by the
    upstream modules and read by each `detect_*` rule.

    Construction-time parameters come from `Settings`:
      - `gesture_confidence_threshold` (PRD FR confidence floor)
      - `motion_history_frames` (buffer capacity for dynamic rules)
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.motion_history = MotionHistoryBuffer(
            max_frames=settings.motion_history_frames,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_motion_history(self, hands: list[HandData], now: float) -> None:
        """Append this frame's wrist positions to the per-role buffers.

        Called once per frame BEFORE `evaluate()`. Idempotent within
        a frame (a second call replaces the prior entry), but in
        practice the CaptureThread calls this exactly once per frame.

        Defensive: skips hands with `role is None` (untracked) or with
        empty landmarks (malformed input that should never reach here
        but is guarded against to keep the hot-path exception-free).
        """
        for hand in hands:
            if hand.role is None:
                continue
            if not hand.landmarks:
                continue
            self.motion_history.update(hand.role, hand.landmarks[0], now)

    def evaluate(
        self,
        hands: list[HandData],
        now: float,
    ) -> list[GestureResult]:
        """Evaluate every rule against the current frame and return
        ALL qualifying candidates (PRD §4.6).

        Args:
            hands: per-frame `HandData` list, post-HandIdentity,
                post-OcclusionBridge, post-ScaleEstimate,
                post-PrimaryHandFilter. `hand.gesture_eligible`
                must already be set (non-eligible hands are skipped).
            now: current timestamp in seconds (e.g.
                `time.monotonic()`).

        Returns:
            List of `GestureResult` objects — zero or more per hand.
            Conflicts between multiple candidates for the same role
            are NOT resolved here; that is `ConflictResolver`'s job.
        """
        try:
            return self._evaluate_impl(hands, now)
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'gesture_engine',
                extra={'extras': {
                    'event': 'evaluate_failed',
                    'hand_count': len(hands),
                    'error': str(exc),
                }},
            )
            return []

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _evaluate_impl(
        self,
        hands: list[HandData],
        now: float,
    ) -> list[GestureResult]:
        candidates: list[GestureResult] = []
        for hand in hands:
            # Skip non-eligible hands (Dominant Hand Mode off -> right).
            if not hand.gesture_eligible:
                continue
            # Skip hands without a scale (FR-SC-04). The motion
            # history has already been updated above by the caller;
            # we do NOT skip dynamic evaluation here because the
            # dynamic rules normalize against `hand_scale` only for
            # some rules (e.g., swipes) and can run without scale
            # for others (Wave, Circular Motion). The dynamic
            # rules handle `hand_scale <= 0` themselves and return
            # None in that case.
            hand_candidates = self._check_all_static(hand, now)
            hand_candidates.extend(self._check_all_dynamic(hand, now))
            candidates.extend(hand_candidates)

        # Optional confidence floor: drop sub-threshold candidates so
        # the downstream resolver + filters have less work. Note that
        # the engine does NOT filter by gesture name here — every
        # qualifying candidate is preserved regardless of identity
        # (PRD §4.6).
        threshold = self.settings.gesture_confidence_threshold
        qualifying = [c for c in candidates if c.confidence >= threshold]

        if candidates:
            logger.debug(
                'gesture_engine',
                extra={'extras': {
                    'event': 'candidates_evaluated',
                    'total': len(candidates),
                    'qualifying': len(qualifying),
                    'hand_count': len(hands),
                }},
            )

        return qualifying

    def _check_all_static(
        self,
        hand: HandData,
        now: float,
    ) -> list[GestureResult]:
        """Evaluate every static rule, return every match (PRD §4.6).

        Unlike v1.0's first-match-wins approach, this method
        iterates the entire rule registry and collects every non-None
        result into the candidates list. The downstream resolver
        picks a single winner per role (ConflictResolver).
        """
        results: list[GestureResult] = []
        for detect_fn in STATIC_GESTURE_RULES:
            try:
                result = detect_fn(hand)
            except Exception as exc:  # noqa: BLE001 — detect_fn must not raise, but defensive
                logger.error(
                    'gesture_engine',
                    extra={'extras': {
                        'event': 'static_recognizer_error',
                        'recognizer': detect_fn.__name__,
                        'error': str(exc),
                    }},
                )
                continue
            if result is not None:
                results.append(result)
        return results

    def _check_all_dynamic(
        self,
        hand: HandData,
        now: float,
    ) -> list[GestureResult]:
        """Evaluate every dynamic rule, return every match (PRD §4.6)."""
        if hand.role is None:
            return []
        buffer = self.motion_history.get(hand.role)
        if len(buffer) < 2:
            return []

        # The hand's smoothed_scale is the canonical normalization
        # reference for dynamic gestures (TRD §3.7 + §4.4). When
        # `scale is None` (FR-SC-04 — should not happen post-
        # HandScaleEstimator but defensively checked), dynamic rules
        # that require scale return None internally; rules that don't
        # (Wave, Circular Motion — purely shape-based) still work.
        hand_scale = float(hand.scale.smoothed_scale) if hand.scale is not None else 0.0

        results: list[GestureResult] = []
        for detect_fn in DYNAMIC_GESTURE_RULES:
            try:
                result = detect_fn(buffer, hand_scale)
            except Exception as exc:  # noqa: BLE001 — defensive
                logger.error(
                    'gesture_engine',
                    extra={'extras': {
                        'event': 'dynamic_recognizer_error',
                        'recognizer': detect_fn.__name__,
                        'error': str(exc),
                    }},
                )
                continue
            if result is not None:
                # Tag the dynamic result with the correct hand role
                # (the dynamic rules don't know which role called
                # them; the engine fills it in).
                result.hand_role = hand.role
                results.append(result)
        return results