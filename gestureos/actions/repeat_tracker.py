"""HeldGestureTracker — repeat-while-held logic for the action layer.

Tracks which gestures are currently held (per hand role) based on
frame-level gesture name feeds, and determines when repeat actions
should fire at a controlled rate.

Thread safety: this class is designed to be used from a single thread
(the main/Qt thread). feed_frame() and get_ready_repeats() are called
from the same thread context.
"""

from __future__ import annotations

# Gestures that support repeat-while-held behavior.
REPEATABLE_GESTURES: frozenset[str] = frozenset({
    'one_finger',
    'peace_sign',
})

# Delay before the first repeat fires (seconds).
INITIAL_REPEAT_DELAY_S: float = 0.5

# Interval between subsequent repeats (seconds).
REPEAT_INTERVAL_S: float = 0.25

#: Minimum interval for get_ready_repeats polling (seconds).
#: Callers should poll at or faster than this rate.
REPEAT_POLL_INTERVAL_S: float = 0.1


class HeldGestureTracker:
    """Tracks held gestures and determines when repeat actions should fire.

    Usage:
        tracker = HeldGestureTracker()
        tracker.feed_frame({'HAND_A': 'one_finger'}, time.monotonic())
        ...
        ready = tracker.get_ready_repeats(time.monotonic())
        for role, name in ready:
            dispatch_repeat_action(role, name)
    """

    def __init__(self) -> None:
        # Per-role tracking: role -> (gesture_name, first_seen_time,
        #                             last_repeat_time)
        self._held: dict[str, tuple[str, float, float]] = {}

    def feed_frame(
        self,
        gesture_names_by_role: dict[str, str],
        now: float,
    ) -> None:
        """Update held-gesture state from the current frame's winners.

        Args:
            gesture_names_by_role: Mapping of hand_role -> gesture_name
                for the current frame. Empty dict when no gesture is
                detected.
            now: Current monotonic time.
        """
        for role, name in gesture_names_by_role.items():
            if name in REPEATABLE_GESTURES:
                if role in self._held:
                    existing_name, first_seen, _ = self._held[role]
                    if existing_name != name:
                        self._held[role] = (name, now, now)
                else:
                    self._held[role] = (name, now, now)
            else:
                self._held.pop(role, None)

        for role in list(self._held.keys()):
            if role not in gesture_names_by_role:
                self._held.pop(role, None)

    def get_ready_repeats(self, now: float) -> list[tuple[str, str]]:
        """Return list of (role, gesture_name) pairs ready for repeat.

        A gesture is ready for repeat when:
        - It has been held beyond INITIAL_REPEAT_DELAY_S since first
          seen.
        - It has not been repeated within the last REPEAT_INTERVAL_S.

        Calling this method advances the last_repeat_time for ready
        pairs.
        """
        ready: list[tuple[str, str]] = []
        for role, (name, first_seen, last_repeat) in list(self._held.items()):
            elapsed_since_first = now - first_seen
            if elapsed_since_first < INITIAL_REPEAT_DELAY_S:
                continue
            elapsed_since_last = now - last_repeat
            if elapsed_since_last >= REPEAT_INTERVAL_S:
                ready.append((role, name))
                self._held[role] = (name, first_seen, now)
        return ready

    def is_held(self, role: str) -> bool:
        """Check if a repeatable gesture is currently held for role."""
        return role in self._held

    def current_gesture(self, role: str) -> str | None:
        """Get the currently held gesture name for a role, or None."""
        if role in self._held:
            return self._held[role][0]
        return None

    def reset(self) -> None:
        """Clear all held-gesture tracking state."""
        self._held.clear()
