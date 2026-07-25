"""CommandRouter — gesture-to-action translation.

Implements TRD §3.13 (ActionResolver). Converts a `GestureResult` into
an `Action` by looking up the gesture's name in the active profile's
mapping table. Pure translation logic: no OS calls, no side effects.

CP-5: the router is stateless and thread-safe. It reads from the
`Profile` dataclass and returns `Action | None` — callers decide
whether/how to dispatch the result.
"""

from __future__ import annotations

import logging
from typing import Any

from models.data_models import Action, GestureResult, Profile


logger = logging.getLogger('gestureos')

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Default built-in gesture-to-action mappings used when no profile is
#: provided. Each entry is a dict with the same shape as a profile
#: mapping row.
DEFAULT_MAPPINGS: list[dict[str, Any]] = [
    {'gesture': 'thumbs_up',  'action_type': 'keyboard',  'params': {'key': 'volume_up'}},
    {'gesture': 'thumbs_down','action_type': 'keyboard',  'params': {'key': 'volume_down'}},
    {'gesture': 'pinch',      'action_type': 'mouse',     'params': {'action': 'click'}},
    {'gesture': 'one_finger', 'action_type': 'keyboard',  'params': {'key': 'volume_up'}},
    {'gesture': 'peace_sign', 'action_type': 'keyboard',  'params': {'key': 'volume_down'}},
]

#: Required keys in a profile mapping dict.
_REQUIRED_KEYS: set[str] = {'gesture', 'action_type', 'params'}


class CommandRouter:
    """Gesture-to-action mapping router.

    The router's single public method, ``route()``, accepts a
    ``GestureResult`` and an optional ``Profile`` and returns an
    ``Action`` (or ``None`` if no mapping matches).

    Thread safety: the router is stateless.  It reads only its
    arguments and never mutates any shared state.
    """

    def __init__(
        self,
        mappings: list[dict[str, Any]] | None = None,
        validate_mappings: bool = True,
    ) -> None:
        """Initialise the router with a set of gesture-to-action mappings.

        Args:
            mappings: A list of mapping dicts, each containing at least
                ``'gesture'``, ``'action_type'``, and ``'params'`` keys.
                When ``None``, the built-in ``DEFAULT_MAPPINGS`` are used.
            validate_mappings: If ``True`` (default), malformed entries
                are logged and skipped at construction time.
        """
        self._mappings = list(mappings or DEFAULT_MAPPINGS)
        if validate_mappings:
            self._validate_and_prune()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        gesture: GestureResult,
        profile: Profile | None = None,
    ) -> Action | None:
        """Resolve a gesture to its mapped ``Action``.

        Args:
            gesture: The recognised gesture result.
            profile: An optional ``Profile`` whose mappings are
                consulted first.  When ``None`` (or when the profile
                has no match), the router's own ``_mappings`` are
                used as a fallback.

        Returns:
            An ``Action`` to dispatch, or ``None`` if no mapping
            matched the gesture.
        """
        # 1. Profile mappings (priority).
        if profile is not None and profile.mappings:
            mapping = self._find_mapping(gesture.gesture_name, profile.mappings)
            if mapping is not None:
                return self._build_action(gesture, mapping)

        # 2. Fall back to the router's own mapping table.
        mapping = self._find_mapping(gesture.gesture_name, self._mappings)
        if mapping is not None:
            return self._build_action(gesture, mapping)

        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _find_mapping(
        gesture_name: str,
        mappings: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Find the first mapping entry whose ``'gesture'`` matches."""
        for m in mappings:
            if m.get('gesture') == gesture_name:
                return m
        return None

    @staticmethod
    def _build_action(gesture: GestureResult, mapping: dict[str, Any]) -> Action:
        """Build an ``Action`` from a gesture result and a mapping."""
        return Action(
            action_type=mapping.get('action_type', 'system'),
            params=dict(mapping.get('params', {})),
            gesture_name=gesture.gesture_name,
            context='',
        )

    # ------------------------------------------------------------------
    # Construction validation
    # ------------------------------------------------------------------

    def _validate_and_prune(self) -> None:
        """Remove malformed entries from ``_mappings`` in place.

        A mapping is valid iff it contains all ``_REQUIRED_KEYS``
        and its ``'params'`` value is a dict.
        """
        valid: list[dict[str, Any]] = []
        for m in self._mappings:
            if not isinstance(m, dict):
                logger.warning(
                    'command_router',
                    extra={'extras': {
                        'event': 'mapping_skipped_not_a_dict',
                        'value': str(m),
                    }},
                )
                continue
            missing = _REQUIRED_KEYS - set(m.keys())
            if missing:
                logger.warning(
                    'command_router',
                    extra={'extras': {
                        'event': 'mapping_skipped_missing_keys',
                        'missing': sorted(missing),
                        'mapping': str(m),
                    }},
                )
                continue
            if not isinstance(m.get('params'), dict):
                logger.warning(
                    'command_router',
                    extra={'extras': {
                        'event': 'mapping_skipped_params_not_dict',
                        'mapping': str(m),
                    }},
                )
                continue
            valid.append(m)
        self._mappings = valid
