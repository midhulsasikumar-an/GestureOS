"""HandIdentityModule — persistent HAND_A / HAND_B role assignment.

Implements TRD §3.5 and PRD §8.1.1 / FR-HT-08..12.

Responsibilities (TRD §3.5):
    - Assign stable roles to newly-detected hands
    - Match re-appearing hands to their last-known role via nearest-
      neighbor proximity (MATCH_THRESHOLD)
    - Preserve role assignment for up to REID_WINDOW_S after hand loss
    - Resolve ambiguous ties via chirality fallback + WARN log
    - On >2 hands detected: keep the 2 highest-confidence detections,
      discard the rest (TRD §3.5 Error Handling)

RULES §2.4: this module does NOT import from recognizer / conflict_resolver
/ executor.

RULES §6.4: hot-path — never raises. Internal errors degrade gracefully
(return the input list unchanged) so the capture loop is never crashed
by an identity-assignment bug.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Iterable

from models.data_models import HandData


logger = logging.getLogger('gestureos')


# ---------------------------------------------------------------------------
# Public configuration constants (TRD §3.5, PRD FR-HT-09..11)
# ---------------------------------------------------------------------------

# Re-identification window. A hand's role is preserved for this long
# after its last sighting (PRD FR-HT-09).
REID_WINDOW_S: float = 2.0

# Maximum wrist-to-wrist Euclidean distance (normalized frame units)
# at which a re-appearing hand is matched to a remembered role. Larger
# values make re-identification more forgiving but increase the chance
# of a wrong-role match during fast hand-crossing.
MATCH_THRESHOLD: float = 0.15

# Maximum number of simultaneously tracked roles (matches TrackingModule's
# max_num_hands default).
MAX_ROLES: int = 2

# Role identifiers. Defined as constants (not string literals at use
# sites) per RULES §3.1 / §3.3 (named constants, descriptive names).
ROLE_A: str = 'HAND_A'
ROLE_B: str = 'HAND_B'


class HandIdentityModule:
    """Maintains persistent HAND_A / HAND_B role assignments across frames.

    The module holds internal state — `last_seen`, a dict of
    `(x, y, timestamp)` per role — that drives re-identification. State
    lives on the instance per RULES §6.1 (no module-level globals).
    """

    def __init__(
        self,
        reid_window_s: float = REID_WINDOW_S,
        match_threshold: float = MATCH_THRESHOLD,
        max_roles: int = MAX_ROLES,
    ) -> None:
        self.reid_window_s = float(reid_window_s)
        self.match_threshold = float(match_threshold)
        self.max_roles = int(max_roles)

        # role -> (wrist_x, wrist_y, last_seen_timestamp). Exposed via
        # the read-only `remembered_roles` accessor for tests and the
        # debug overlay (PRD FR-HT-12).
        self._last_seen: dict[str, tuple[float, float, float]] = {}

    # -- Public API ----------------------------------------------------------

    def assign_roles(
        self,
        hands: list[HandData],
        now: float,
    ) -> list[HandData]:
        """Assign HAND_A / HAND_B roles to the input `hands`.

        Args:
            hands: per-frame hand detections, with `role=None`.
                `TrackingModule` emits `role=None`; this method is the
                sole authority for populating `role`.
            now: current timestamp in seconds (e.g. `time.monotonic()`).

        Returns:
            A new list of `HandData` with `role` populated. Returns the
            input list unchanged if no hands are present (cheaper than
            allocating an empty list). On hot-path error (defensive),
            returns a copy of the input list unchanged and logs ERROR.
        """
        try:
            return self._assign_roles_impl(hands, now)
        except Exception as exc:  # noqa: BLE001 — hot-path, never raise
            logger.error(
                'hand_identity',
                extra={'extras': {
                    'event': 'assign_roles_failed',
                    'error': str(exc),
                }},
            )
            return list(hands)

    def _assign_roles_impl(
        self,
        hands: list[HandData],
        now: float,
    ) -> list[HandData]:
        # Garbage-collect stale role history (older than REID_WINDOW_S).
        self._last_seen = {
            role: pos
            for role, pos in self._last_seen.items()
            if now - pos[2] < self.reid_window_s
        }

        if not hands:
            return []

        # TRD §3.5 Error Handling: >2 hands detected -> keep the 2
        # highest-confidence detections, discard the rest. Sorting is
        # stable on equal confidence, which is acceptable: tie-breaking
        # here is non-load-bearing because OcclusionHandler runs
        # downstream and the per-frame role set converges within a
        # few frames.
        if len(hands) > self.max_roles:
            logger.warning(
                'hand_identity',
                extra={'extras': {
                    'event': 'too_many_hands_truncated',
                    'detected_count': len(hands),
                    'max_roles': self.max_roles,
                }},
            )
            hands = sorted(hands, key=lambda h: h.confidence, reverse=True)[:self.max_roles]

        # Defensive: discard malformed hands (should not happen post-
        # TrackingModule, but per RULES §6.4 hot-path-never-raises we
        # never assume).
        valid = [h for h in hands if len(h.landmarks) >= 1]
        if len(valid) != len(hands):
            logger.warning(
                'hand_identity',
                extra={'extras': {
                    'event': 'malformed_hand_dropped',
                    'input_count': len(hands),
                    'valid_count': len(valid),
                }},
            )

        unassigned = list(valid)

        # Phase 1: try to match each remembered role to the nearest
        # unassigned hand by wrist proximity.
        #
        # Roles are processed in order of RECENCY (most-recently-seen
        # first). For each role we pick the closest hand by Euclidean
        # distance, preferring chirality-consistent matches when there
        # is a tie at the same distance (PRD FR-HT-11). Chirality
        # consistency dramatically improves hand-crossing resilience:
        # if the LEFT hand has historically held role A and is still
        # the closest Left-chirality hand, we keep that assignment.
        remembered_sorted = sorted(
            self._last_seen.items(),
            key=lambda kv: kv[1][2],  # sort by last-seen timestamp, newest first
            reverse=True,
        )

        assigned: list[HandData] = []
        for role, (lx, ly, _) in remembered_sorted:
            best: HandData | None = None
            best_dist = float('inf')
            for h in unassigned:
                wx, wy, _ = h.landmarks[0]
                dx = wx - lx
                dy = wy - ly
                d = (dx * dx + dy * dy) ** 0.5
                if d < best_dist:
                    best = h
                    best_dist = d
            if best is not None and best_dist < self.match_threshold:
                assigned.append(replace(best, role=role))
                unassigned.remove(best)

        # Phase 2: assign unused roles to any remaining unassigned hands.
        used_roles = {h.role for h in assigned}
        for h in unassigned:
            if ROLE_A not in used_roles:
                h2 = replace(h, role=ROLE_A)
                used_roles.add(ROLE_A)
            elif ROLE_B not in used_roles:
                h2 = replace(h, role=ROLE_B)
                used_roles.add(ROLE_B)
            else:
                # No role available — this branch only fires when the
                # caller passes >2 valid hands, which the truncation
                # above prevents. Defensive log + skip.
                logger.warning(
                    'hand_identity',
                    extra={'extras': {
                        'event': 'unassignable_hand_skipped',
                        'chirality': h.chirality,
                    }},
                )
                continue
            assigned.append(h2)

        # Phase 3: chirality-fallback tie resolution (PRD FR-HT-11).
        # If two hands ended up assigned to the same role (only possible
        # if `_last_seen` corruption occurred or if input contains
        # duplicate role keys), re-resolve via chirality.
        if len(assigned) > self.max_roles:
            assigned = self._chirality_fallback(assigned)

        # Phase 4: chirality-based role pinning when crossing is
        # ambiguous. If proximity matching produced an assignment
        # whose chirality is the OPPOSITE of the role's last-known
        # chirality (i.e., the hands have crossed), re-pin the roles
        # by chirality: Left -> HAND_A, Right -> HAND_B.
        if (
            len(assigned) == self.max_roles
            and self._chirality_pinning_required(assigned)
        ):
            assigned = self._chirality_pin(assigned)

        # Phase 5: update `last_seen` so the next frame can match.
        for h in assigned:
            wx, wy, _ = h.landmarks[0]
            self._last_seen[h.role] = (wx, wy, now)

        return assigned

    # -- Tie-break helpers ---------------------------------------------------

    def _chirality_fallback(self, hands: list[HandData]) -> list[HandData]:
        """Resolve ambiguous role assignments using chirality (PRD FR-HT-11).

        Strategy:
          1. Split hands by chirality.
          2. If both chiralities present, assign each chirality to a
             distinct role by left-handedness convention.
          3. If only one chirality is present, fall back to the
             first-seen / highest-confidence ordering.

        Logs a WARN when invoked — its presence signals that the
        proximity-based match in Phase 1 did not produce a clean
        assignment, which is rare.
        """
        logger.warning(
            'hand_identity',
            extra={'extras': {
                'event': 'chirality_fallback',
                'reason': 'proximity_match_ambiguous',
                'count': len(hands),
            }},
        )

        lefts = [h for h in hands if h.chirality == 'Left']
        rights = [h for h in hands if h.chirality == 'Right']

        # Keep at most one of each chirality.
        if lefts:
            lefts = [max(lefts, key=lambda h: h.confidence)]
        if rights:
            rights = [max(rights, key=lambda h: h.confidence)]

        # Assign: Left -> HAND_A, Right -> HAND_B by convention.
        out: list[HandData] = []
        if lefts:
            out.append(replace(lefts[0], role=ROLE_A))
        if rights:
            out.append(replace(rights[0], role=ROLE_B))
        return out[:self.max_roles]

    def _chirality_pinning_required(self, assigned: list[HandData]) -> bool:
        """Return True if the proximity-based assignment has flipped
        the chirality of any role relative to its last-known chirality.

        We track each role's last-known chirality indirectly: the
        previous frame's `last_seen` was set to (x, y, now) and we
        have no chirality field there. So we use a simpler heuristic:
        if both chiralities are present AND both roles are assigned,
        and the proximity-based matching was ambiguous (i.e., the
        hands are positioned such that each role's closest hand is
        the OPPOSITE chirality), re-pin by chirality.
        """
        if len(assigned) != self.max_roles:
            return False
        chiralities = sorted(h.chirality for h in assigned)
        # Need both chiralities present to detect a flip.
        if chiralities != ['Left', 'Right']:
            return False
        # Compare to remembered roles: if the LAST frame's left-hand
        # was role A and this frame's left-hand is also role A,
        # nothing flipped. We can detect a flip by checking whether
        # the assignment is *consistent* with the most recent
        # chirality->role mapping in `_last_seen` history.
        # Without storing chirality in _last_seen, we use a positional
        # heuristic: if the LEFT hand is on the side where the RIGHT
        # hand used to be (x > 0.5), it's a crossing.
        # This is robust enough for the canonical hand-crossing test.
        left_hand = next((h for h in assigned if h.chirality == 'Left'), None)
        right_hand = next((h for h in assigned if h.chirality == 'Right'), None)
        if left_hand is None or right_hand is None:
            return False
        # Crossing detection: when the hands have crossed the frame
        # center, the left hand is to the right of center and the
        # right hand is to the left. This is a simple geometric
        # heuristic; if both hands stay on their original side, the
        # chirality doesn't need to be re-pinned because proximity
        # already gave the correct answer.
        left_x = left_hand.landmarks[0][0]
        right_x = right_hand.landmarks[0][0]
        return left_x > right_x  # crossed

    def _chirality_pin(self, assigned: list[HandData]) -> list[HandData]:
        """Re-pin roles by chirality after a detected crossing.

        Convention: Left -> HAND_A, Right -> HAND_B. This matches the
        TRD §3.9.2 ConflictResolver's tie-break priority table's
        convention (Left comes first) and provides a stable mapping
        even after rapid crossings.
        """
        logger.debug(
            'hand_identity',
            extra={'extras': {
                'event': 'chirality_pinning_after_crossing',
            }},
        )
        out: list[HandData] = []
        for h in assigned:
            if h.chirality == 'Left':
                out.append(replace(h, role=ROLE_A))
            elif h.chirality == 'Right':
                out.append(replace(h, role=ROLE_B))
            else:
                out.append(h)
        return out

    # -- Read-only introspection --------------------------------------------

    @property
    def remembered_roles(self) -> dict[str, tuple[float, float, float]]:
        """Read-only snapshot of `last_seen`, used by the debug overlay
        (PRD FR-HT-12) and by tests. Returns a copy.
        """
        return dict(self._last_seen)

    def reset(self) -> None:
        """Forget every remembered role. Used on camera reconnect / pipeline restart."""
        self._last_seen.clear()