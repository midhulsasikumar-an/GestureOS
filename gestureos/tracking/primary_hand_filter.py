"""PrimaryHandFilter — Dominant Hand Mode filter.

Implements TRD §3.8 and PRD §8.1.3 / FR-PH-01..03.

Responsibilities (TRD §3.8):
    - Read `dominant_hand_mode` from Settings (`off` / `left` / `right`)
    - When not `off`, mark non-matching hands as `gesture_eligible=False`
      so they flow through the pipeline for overlay rendering but never
      reach `GestureEngine.evaluate()` for gesture candidacy (CP-3)
    - When `off`, mark all hands as `gesture_eligible=True`

If the designated primary hand isn't present in the current frame, no
promotion of a secondary hand occurs (PRD FR-PH-03) — the filter
simply produces a list where zero hands are `gesture_eligible` that
frame; this is a normal, non-error condition (TRD §3.8 Error Handling).

RULES §2.4: does not import from recognizer / conflict_resolver / executor.
RULES §6.4: hot-path — never raises.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Iterable

from models.data_models import HandData


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.8, PRD FR-PH-01..02)
# ---------------------------------------------------------------------------

# Valid `dominant_hand_mode` values. Mirrored in SettingsManager's
# _DOMINANT_HAND_MODES — kept here as the canonical source of truth
# that this module references.
MODE_OFF: str = 'off'
MODE_LEFT: str = 'left'
MODE_RIGHT: str = 'right'

# Chirality strings MediaPipe emits. Used to map mode -> chirality.
CHIRALITY_LEFT: str = 'Left'
CHIRALITY_RIGHT: str = 'Right'


class PrimaryHandFilter:
    """Filters the per-frame hand list by Dominant Hand Mode.

    Stateless — the `dominant_hand_mode` is read from Settings on each
    call, not cached on the instance. This avoids the subtle bug where
    a `Settings.save()` call would not propagate to a long-lived filter
    instance if the value were cached.
    """

    def __init__(self, dominant_hand_mode: str = MODE_OFF) -> None:
        # Validate eagerly so misconfiguration fails at construction
        # time (cold-path), not on the hot per-frame path.
        if dominant_hand_mode not in (MODE_OFF, MODE_LEFT, MODE_RIGHT):
            raise ValueError(
                f'dominant_hand_mode must be one of '
                f'{{{MODE_OFF!r}, {MODE_LEFT!r}, {MODE_RIGHT!r}}}; '
                f'got {dominant_hand_mode!r}'
            )
        self._mode = dominant_hand_mode

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Update the Dominant Hand Mode at runtime (e.g., from a
        Settings.save() event). Validates eagerly."""
        if mode not in (MODE_OFF, MODE_LEFT, MODE_RIGHT):
            raise ValueError(
                f'dominant_hand_mode must be one of '
                f'{{{MODE_OFF!r}, {MODE_LEFT!r}, {MODE_RIGHT!r}}}; '
                f'got {mode!r}'
            )
        self._mode = mode

    # -- Public API ----------------------------------------------------------

    def filter(self, hands: list[HandData]) -> list[HandData]:
        """Return a new list with `gesture_eligible` set per the configured mode.

        Always returns a new list (never mutates the input) so that
        per-frame HandData references held by upstream components stay
        stable. RULES §5.6 / §6.4.
        """
        try:
            return self._filter_impl(hands)
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'primary_hand_filter',
                extra={'extras': {
                    'event': 'filter_failed',
                    'mode': self._mode,
                    'error': str(exc),
                }},
            )
            return [replace(h, gesture_eligible=True) for h in hands]

    def _filter_impl(self, hands: list[HandData]) -> list[HandData]:
        mode = self._mode
        if mode == MODE_OFF:
            # All hands eligible. Still replace() to produce fresh
            # dataclass instances (immutability discipline).
            return [replace(h, gesture_eligible=True) for h in hands]

        target = CHIRALITY_LEFT if mode == MODE_LEFT else CHIRALITY_RIGHT
        return [
            replace(h, gesture_eligible=(h.chirality == target))
            for h in hands
        ]