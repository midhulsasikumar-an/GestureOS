"""OcclusionHandler — bridges brief tracking interruptions.

Implements TRD §3.6 and PRD §8.1.2 / FR-OC-01..03.

Responsibilities (TRD §3.6):
    - When a previously-tracked hand role is missing or below detection-
      confidence threshold this frame, retain its last-known `HandData`
      (landmarks, finger states) for up to `occlusion_retention_ms`
      (default 300 ms).
    - If detection recovers within the window, resume seamlessly
      without resetting `StabilityFilter` or `DynamicRecognizer`
      trajectory state.
    - If the window expires, release the hand to `HandIdentityModule`'s
      normal re-identification path (PRD FR-OC-03).

Hard timeout (TRD §3.6 Error Handling): if a hand is occluded for
longer than the retention window, it is NOT silently retained forever
— this is a hard timeout, not a fallback-forever cache, to avoid stale
gesture state persisting indefinitely.

RULES §2.4: does not import from recognizer / conflict_resolver / executor.
RULES §6.4: hot-path — never raises.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Iterable

from models.data_models import HandData
from tracking.hand_detector import REASON_OCCLUSION_BRIDGE, STATUS_RETAINED


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.6, PRD FR-OC-01)
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_MS: int = 300
"""Default retention window in milliseconds (PRD FR-OC-01)."""

MIN_DETECTION_CONFIDENCE_THRESHOLD: float = 0.0
"""Hands below this confidence are treated as missing (PRD FR-OC-01).
The threshold is 0.0 because TrackingModule has already filtered at
its own min_detection_confidence; OcclusionHandler's job is just to
catch missing-in-this-frame hands, not low-confidence ones. Set higher
if the operator wants more aggressive occlusion behavior."""


class OcclusionHandler:
    """Retains last-known HandData for briefly-missing roles.

    Sits between `HandIdentityModule.assign_roles` and
    `HandScaleEstimator.estimate` in the per-frame pipeline (TRD §2.2,
    AI Dev Guide §4.1). Pure-Python; no camera, OS, or PyQt6 deps.
    """

    def __init__(
        self,
        retention_ms: int = DEFAULT_RETENTION_MS,
        min_detection_confidence: float = MIN_DETECTION_CONFIDENCE_THRESHOLD,
    ) -> None:
        if retention_ms <= 0:
            raise ValueError(f'retention_ms must be > 0; got {retention_ms}')

        self.retention_ms = int(retention_ms)
        self.retention_s = self.retention_ms / 1000.0
        self.min_detection_confidence = float(min_detection_confidence)

        # role -> (hand_data, lost_at_seconds). A hand role enters this
        # dict when it disappears from a frame; exits when either it
        # reappears (entry dropped) or the retention window expires
        # (entry dropped, role returns to normal re-identification).
        self._retained: dict[str, tuple[HandData, float]] = {}

        # Previous frame's roles + hand-data + timestamp, used to detect
        # newly-lost roles on the next frame. Initialized empty so the
        # very first call to `bridge_gaps()` does not crash on a missing
        # key (the TRD reference uses `_previous_roles` without
        # initialization — this implementation initializes explicitly to
        # make the first frame safe).
        self._previous_roles: set[str] = set()
        self._previous_hands: dict[str, HandData] = {}
        self._previous_now: dict[str, float] = {}

    # -- Public API ----------------------------------------------------------

    def bridge_gaps(
        self,
        current_hands: list[HandData],
        now: float,
    ) -> list[HandData]:
        """Augment `current_hands` with retained data for missing roles.

        Args:
            current_hands: per-frame hand detections from
                `HandIdentityModule.assign_roles`. Already role-tagged.
            now: current timestamp in seconds.

        Returns:
            A new list containing the input hands plus, for each role
            that is missing this frame but whose retention window has
            not yet expired, a `replace()`d copy of the last-known
            `HandData` with `is_retained=True`.
        """
        try:
            return self._bridge_gaps_impl(current_hands, now)
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'occlusion',
                extra={'extras': {
                    'event': 'bridge_gaps_failed',
                    'error': str(exc),
                }},
            )
            return list(current_hands)

    def _bridge_gaps_impl(
        self,
        current_hands: list[HandData],
        now: float,
    ) -> list[HandData]:
        # 1. Drop retained entries for roles that have reappeared.
        #    Also drop entries for hands that no longer pass the
        #    confidence threshold — those should not be retained either
        #    (TRD §3.6 mentions confidence-below-threshold as a trigger
        #    for retention, but the symmetric case — confidence dropping
        #    below threshold after reappearance — should also release).
        current_roles = {
            h.role for h in current_hands
            if h.role is not None and h.confidence >= self.min_detection_confidence
        }
        for role in list(self._retained):
            if role in current_roles:
                del self._retained[role]

        # 2. Detect newly-lost roles (in previous frame, missing now)
        #    and continue retention of any role already in the buffer.
        newly_lost = self._previous_roles - current_roles
        for role in newly_lost:
            if role not in self._retained:
                # First frame of the gap — start retention with the
                # last-known data. `lost_at` is set to the timestamp
                # of the PREVIOUS frame (when we last saw the hand),
                # not to the current `now` — otherwise the retention
                # window would always start at the current frame and
                # the "missing for 400 ms" test case would be measured
                # against a 0-second gap instead.
                prev = self._previous_hands.get(role)
                if prev is not None:
                    lost_at = self._previous_now.get(role, now)
                    self._retained[role] = (prev, lost_at)

        # 3. Emit retained hands whose window has not expired.
        result: list[HandData] = list(current_hands)
        for role in list(self._retained):
            data, lost_at = self._retained[role]
            if now - lost_at <= self.retention_s:
                # CP-4 Tracking Stabilization: mark the bridged copy
                # as 'retained' with reason 'occlusion_bridge' so the
                # Developer Mode debug panel can show the source of
                # the hand on every frame. The retained copy is a
                # distinct HandData (via `replace`); the input
                # `current_hands` list is not mutated.
                bridged = replace(
                    data,
                    is_retained=True,
                    status=STATUS_RETAINED,
                    status_reason=REASON_OCCLUSION_BRIDGE,
                )
                result.append(bridged)
                # Optional DEBUG: log the bridge event the first time we
                # emit a retained hand, to keep log volume low.
                logger.debug(
                    'occlusion',
                    extra={'extras': {
                        'event': 'bridged',
                        'role': role,
                        'elapsed_ms': int((now - lost_at) * 1000),
                    }},
                )
            else:
                # Window expired — release back to HandIdentityModule's
                # re-identification path (PRD FR-OC-03).
                logger.info(
                    'occlusion',
                    extra={'extras': {
                        'event': 'occlusion_window_expired',
                        'role': role,
                        'retention_ms': self.retention_ms,
                    }},
                )
                del self._retained[role]

        # 4. Update `previous_*` for the next frame.
        #    Use the result roles, NOT current_roles, because the
        #    bridged roles are also "tracked this frame" from the
        #    perspective of retention continuity.
        result_roles: set[str] = set()
        result_hands: dict[str, HandData] = {}
        result_now: dict[str, float] = {}
        for h in result:
            if h.role is None:
                continue
            result_roles.add(h.role)
            # Prefer the non-retained (real) hand over a retained copy
            # for `_previous_hands`, so if the real hand comes back we
            # have its freshest data.
            if not h.is_retained:
                result_hands[h.role] = h
                result_now[h.role] = now
            elif h.role not in result_hands:
                result_hands[h.role] = h
                # Don't overwrite result_now for a retained hand —
                # the gap-detection algorithm relies on the LAST REAL
                # sighting timestamp, not the bridged one.

        self._previous_roles = result_roles
        self._previous_hands = result_hands
        self._previous_now = result_now

        return result

    # -- Read-only introspection --------------------------------------------

    @property
    def retained_roles(self) -> dict[str, float]:
        """Read-only snapshot of currently-retained roles and the time
        they were lost (seconds). Used by tests and the debug overlay.
        """
        return {role: lost_at for role, (_, lost_at) in self._retained.items()}

    def reset(self) -> None:
        """Forget every retained role. Used on camera reconnect / pipeline restart."""
        self._retained.clear()
        self._previous_roles.clear()
        self._previous_hands.clear()
        self._previous_now.clear()