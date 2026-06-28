"""ActivationGate — INACTIVE / ACTIVE state machine for the gesture pipeline.

Implements TRD §5.3 (Activation Sub-State Machine) and PRD §7
(Activation Mode / FR-AM-01..07).

Responsibilities (TRD §5.3 + PRD §7):

  - Track a binary `TrackingState` enum (`INACTIVE` / `ACTIVE`) that
    gates the entire gesture pipeline.
  - Toggle the state when a qualifying Open Palm (or, when enabled,
    Closed Fist) gesture has been held continuously for
    `hold_duration_s` (default 1.0 s; configurable via
    `Settings.activation_hold_duration_s` — PRD §7.3 / FR-AM-07
    range 0.5–3.0 s).
  - Reset the hold-timer when a non-qualifying gesture appears
    mid-hold (TRD §5.3: "non-open-palm frames reset counter without
    partial credit").
  - Expose a `toggle()` method callable by:
      * a global keyboard shortcut listener (`Ctrl + Alt + G`),
      * the future CP-7 tray icon, and
      * integration tests.
  - Persist the activation state across context switches (FR-AM-03)
    by living on the `GestureOSApp` instance, not in any per-context
    state.
  - Default to `INACTIVE` on app launch (FR-AM-06).
  - Emit a timestamped, structured log line on every state transition
    (FR-AM-04) via `DiagnosticsManager.log_activation_state_changed`.

Out of scope (CP-5 / CP-7):
  - Performing actions in response to gestures (the gate only
    SUPPRESSES the dispatch path; downstream dispatch is CP-5).
  - The tray-icon UI itself (CP-7) — this checkpoint only exposes
    the callable `.toggle()` API the future tray icon will use.

RULES §2.2: `ActivationGate` does NOT depend on `ConflictResolver`,
`StabilityFilter`, `CooldownFilter`, or `GestureEngine`. It receives
already-stability-passed, already-cooldown-passed gesture names from
the pipeline (TRD §16: this ordering is a named risk and must be
preserved by the caller).

RULES §6.1: hold-timer state lives on the instance — no module-level
globals.

RULES §6.4: hot-path — `feed_gesture()` and `toggle()` never raise.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (PRD §7.3 / FR-AM-07, TRD §5.3)
# ---------------------------------------------------------------------------

MIN_HOLD_DURATION_S: float = 0.5
"""PRD §7.3 / FR-AM-07: minimum configurable hold duration (seconds)."""

MAX_HOLD_DURATION_S: float = 3.0
"""PRD §7.3 / FR-AM-07: maximum configurable hold duration (seconds)."""

DEFAULT_HOLD_DURATION_S: float = 1.0
"""PRD §7.3 default hold duration (seconds). Mirrors Settings default."""

OPEN_PALM_GESTURE: str = 'open_palm'
"""PRD-exact gesture name (`snake_case`) used by `detect_open_palm`."""

CLOSED_FIST_GESTURE: str = 'fist'
"""PRD-exact gesture name (`snake_case`) used by `detect_fist`.

The CP-4 PRD §7.2 table calls the alternative toggle method "Closed
Fist Hold" — the recognizer emits `fist` (per the static gesture
inventory in TRD §3.9.1). The label "Closed Fist" is the UX name;
the underlying gesture name remains `fist` for consistency with the
recognition pipeline."""


# ---------------------------------------------------------------------------
# TrackingState — the binary activation enum
# ---------------------------------------------------------------------------

class TrackingState(enum.Enum):
    """The activation gate's state. Per PRD §7.1 / FR-AM-06:

      - `INACTIVE`: default on launch. The downstream gesture-pipeline
        dispatch path MUST be suppressed while INACTIVE (FR-AM-01).
        The hand-skeleton overlay continues to render (FR-AM-02).
      - `ACTIVE`: user has confirmed intent. The gesture pipeline
        may proceed to dispatch.

    Transitions (TRD §5.3):
      INACTIVE -> ACTIVE: hold duration satisfied by Open Palm Hold
                          (and optionally Closed Fist Hold).
      ACTIVE    -> INACTIVE: next Open Palm Hold (or Closed Fist
                             Hold) satisfied, OR explicit toggle.
    """
    INACTIVE = 'inactive'
    ACTIVE = 'active'


@dataclass(frozen=True)
class ActivationMethod:
    """Records which activation method produced a state transition.

    Mirrors the structured-extras payload consumed by
    `DiagnosticsManager.log_activation_state_changed`. Frozen so it
    can be safely shared across threads (RULES §5.6).
    """
    name: str  # 'open_palm_hold' | 'closed_fist_hold' | 'keyboard_shortcut' | 'tray_toggle'


# ---------------------------------------------------------------------------
# ActivationGate
# ---------------------------------------------------------------------------

class ActivationGate:
    """The binary safety gate between the gesture pipeline and dispatch.

    Stateful — one instance per application. Owns:
      - `state: TrackingState` (current activation state)
      - `_hold_start: float | None` (timestamp when the current
        qualifying-hold began, or None when not currently holding)
      - `_hold_gesture: str | None` (which qualifying gesture is being
        held, or None when not currently holding)

    Thread model (RULES §5.6):
      - The gate is constructed once on `GestureOSApp` (main thread).
      - `feed_gesture()` is called from the `CaptureThread` worker
        thread via Qt signal / direct call from the orchestrator.
      - `toggle()` is called from the keyboard-shortcut listener thread
        (or, in tests, the main thread).
      - `state` and `_hold_*` are mutated only under the gate's
        internal invariant (single attribute writes are atomic in CPython
        for simple float/str/enum assignments, and the gate does not
        span multi-attribute critical sections).

    Hot-path discipline (RULES §6.4):
      - `feed_gesture()` and `toggle()` are wrapped in try/except and
        never raise.
      - The path is O(1) per call (no allocations beyond the optional
        log call's structured-extras dict).
    """

    def __init__(
        self,
        hold_duration_s: float = DEFAULT_HOLD_DURATION_S,
        enable_closed_fist: bool = False,
    ) -> None:
        if hold_duration_s < MIN_HOLD_DURATION_S or hold_duration_s > MAX_HOLD_DURATION_S:
            raise ValueError(
                f'hold_duration_s must be in [{MIN_HOLD_DURATION_S}, '
                f'{MAX_HOLD_DURATION_S}]; got {hold_duration_s}'
            )
        self.hold_duration_s = float(hold_duration_s)
        self.enable_closed_fist = bool(enable_closed_fist)

        # FR-AM-06: default state on launch is INACTIVE.
        self.state: TrackingState = TrackingState.INACTIVE

        # Hold-timer state (RULES §6.1 — instance attributes, not
        # module-level globals).
        self._hold_start: float | None = None
        self._hold_gesture: str | None = None

    # ------------------------------------------------------------------
    # Public API — gesture-driven transitions
    # ------------------------------------------------------------------

    def feed_gesture(self, gesture_name: str, now: float) -> None:
        """Feed a stability+cooldown-passed gesture name into the gate.

        Called from the CaptureThread pipeline AFTER `StabilityFilter`
        and `CooldownFilter` have accepted the candidate (TRD §16
        explicit risk: this ordering must be preserved by the caller).

        Args:
            gesture_name: PRD-exact gesture name (e.g. `open_palm`,
                `fist`, `swipe_right`). Unknown gesture names reset
                the hold timer (defensive — the pipeline only emits
                recognized names but we tolerate anything).
            now: current timestamp in seconds (e.g.
                `time.monotonic()`).

        Behavior (TRD §5.3):
          - If `gesture_name` is a qualifying toggle gesture
            (`open_palm`, or `fist` when `enable_closed_fist`), and
            no hold is currently in progress: start the hold.
          - If a hold IS in progress for the SAME gesture: check
            elapsed time against `hold_duration_s`. If satisfied,
            toggle state and clear the hold.
          - If a hold is in progress for a DIFFERENT gesture: reset
            (no partial credit — TRD §5.3).
          - If the gesture is not a qualifying toggle gesture: reset
            the hold.
        """
        try:
            self._feed_gesture_impl(gesture_name, now)
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'activation',
                extra={'extras': {
                    'event': 'feed_gesture_failed',
                    'gesture': gesture_name,
                    'error': str(exc),
                }},
            )

    def _feed_gesture_impl(self, gesture_name: str, now: float) -> None:
        if not self._is_toggle_gesture(gesture_name):
            # Non-qualifying gesture: reset hold (TRD §5.3 — no
            # partial credit on interruption).
            self._hold_start = None
            self._hold_gesture = None
            return

        if self._hold_gesture != gesture_name:
            # Different gesture (or fresh start): begin a new hold
            # window. Per TRD §5.3 any prior partial hold is discarded.
            self._hold_start = now
            self._hold_gesture = gesture_name
            return

        # Same gesture continues the hold. Check elapsed time.
        assert self._hold_start is not None  # invariant
        elapsed = now - self._hold_start
        if elapsed >= self.hold_duration_s:
            method = (
                ActivationMethod(name='closed_fist_hold')
                if gesture_name == CLOSED_FIST_GESTURE
                else ActivationMethod(name='open_palm_hold')
            )
            hold_elapsed_ms = int(elapsed * 1000)
            self._toggle_state(method, hold_elapsed_ms=hold_elapsed_ms)

    # ------------------------------------------------------------------
    # Public API — explicit transitions
    # ------------------------------------------------------------------

    def toggle(self, method: ActivationMethod | None = None) -> None:
        """Flip `state` immediately. Used by keyboard-shortcut and
        tray-icon callers (CP-7 will wire the tray icon UI).

        Args:
            method: which activation method triggered the toggle.
                Defaults to `keyboard_shortcut` when omitted (the most
                common programmatic caller). When provided, its `name`
                is forwarded to the state-change log.

        Hot-path discipline: never raises.
        """
        try:
            self._toggle_state(
                method or ActivationMethod(name='keyboard_shortcut')
            )
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'activation',
                extra={'extras': {
                    'event': 'toggle_failed',
                    'error': str(exc),
                }},
            )

    def _toggle_state(
        self,
        method: ActivationMethod,
        hold_elapsed_ms: int | None = None,
    ) -> None:
        """Common state-flip logic with structured logging.

        Mirrors the exact TRD §9.1 example log line:
          `[12:31:55.900] [INFO] [activation] State changed `
          `{from: 'inactive', to: 'active', method: 'open_palm_hold'}`

        When called from a hold-based toggle (`feed_gesture` path),
        `hold_elapsed_ms` includes the millisecond elapsed at the
        moment the hold satisfied — useful for manual verification
        that activation only fires after the configured duration.
        """
        previous = self.state
        new = (
            TrackingState.ACTIVE
            if previous == TrackingState.INACTIVE
            else TrackingState.INACTIVE
        )
        self.state = new
        self._hold_start = None
        self._hold_gesture = None
        extras: dict[str, object] = {
            'event': 'state_changed',
            'from': previous.value,
            'to': new.value,
            'method': method.name,
        }
        if hold_elapsed_ms is not None:
            extras['hold_elapsed_ms'] = hold_elapsed_ms
        logger.info(
            'activation',
            extra={'extras': extras},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_toggle_gesture(self, gesture_name: str) -> bool:
        """Return True if `gesture_name` may drive a hold-based toggle."""
        if gesture_name == OPEN_PALM_GESTURE:
            return True
        if gesture_name == CLOSED_FIST_GESTURE and self.enable_closed_fist:
            return True
        return False

    # ------------------------------------------------------------------
    # Read-only introspection
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """Convenience accessor: `True` iff `state == TrackingState.ACTIVE`."""
        return self.state == TrackingState.ACTIVE

    @property
    def hold_in_progress(self) -> tuple[str, float] | None:
        """Read-only snapshot of the current hold-timer state.

        Returns `(gesture_name, hold_start_seconds)` if a hold is in
        progress, else `None`. Used by tests and the future
        Developer Mode panel to display "Activation: holding Xms"
        feedback.
        """
        if self._hold_start is None or self._hold_gesture is None:
            return None
        return (self._hold_gesture, self._hold_start)

    def reset(self) -> None:
        """Clear hold-timer state and force the gate to INACTIVE.

        Used on camera reconnect / pipeline restart. The gate does
        NOT emit a state-change log for this reset because it is a
        cold-path lifecycle operation, not a user-driven transition.
        """
        self.state = TrackingState.INACTIVE
        self._hold_start = None
        self._hold_gesture = None
