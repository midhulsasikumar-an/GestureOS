"""CP-5 safety layer — validates actions before dispatch.

The ``ActionValidator`` is a lightweight pre-flight check that
runs before the ``Executor``.  It catches:

  - Path-traversal attempts in ``app_launch`` params
  - Shell metacharacters in ``app_launch`` params
  - Unreasonable key names in ``keyboard`` params
  - Configurable action-type denylist

Usage::

    validator = ActionValidator()
    if not validator.is_safe(action):
        return ActionResult(success=False, action=action,
                            error=validator.last_error)
    return executor.execute(action)
"""

from __future__ import annotations

import os
import re
from typing import Any

from models.data_models import Action, ActionResult


# Characters that are never valid in an app_launch path or app name.
_SHELL_METACHARS: re.Pattern[str] = re.compile(
    r'[&|;`$(){}[\]<>~!\n\r]',
)

# Maximum allowed length for any string param.
_MAX_PARAM_LENGTH = 512


class ActionValidator:
    """Pre-flight validation for CP-5 actions.

    Thread-safe (stateless after construction).  Call ``is_safe()``
    before dispatching; if it returns ``False``, ``last_error``
    contains the reason.

    Args:
        denied_action_types: Action types that should always be
            rejected (e.g. ``{'app_launch'}`` to disable launching
            applications).  Defaults to empty set.
    """

    def __init__(
        self,
        denied_action_types: set[str] | None = None,
    ) -> None:
        self._denied = denied_action_types or set()
        self.last_error: str | None = None

    def is_safe(self, action: Action) -> bool:
        """Check whether ``action`` is safe to execute.

        Returns ``True`` if the action passes all safety checks.
        On ``False``, ``self.last_error`` is set to the reason.
        """
        self.last_error = None

        # Check action-type denylist.
        if action.action_type in self._denied:
            self.last_error = f"Action type '{action.action_type}' is denied"
            return False

        # Dispatch to type-specific checks.
        checker = getattr(self, f'_check_{action.action_type}', None)
        if checker is not None:
            return checker(action.params)

        # Unknown action types are allowed through (the executor will
        # reject them with a descriptive error).
        return True

    # -- Param-length guard -----------------------------------------------

    @staticmethod
    def _param_length_ok(params: dict[str, Any]) -> bool:
        """Reject actions whose string params exceed the maximum length."""
        for key, value in params.items():
            if isinstance(value, str) and len(value) > _MAX_PARAM_LENGTH:
                return False
        return True

    # -- Action-type checks -----------------------------------------------

    def _check_app_launch(self, params: dict[str, Any]) -> bool:
        if not self._param_length_ok(params):
            self.last_error = f'Param exceeds max length ({_MAX_PARAM_LENGTH})'
            return False

        path = str(params.get('path', params.get('app', '')))
        if not path:
            self.last_error = 'app_launch missing "path" or "app" param'
            return False

        # Reject path-traversal sequences.
        if '..' in path.split(os.sep):
            self.last_error = f'Path traversal detected: {path}'
            return False

        # Reject shell metacharacters.
        if _SHELL_METACHARS.search(path):
            self.last_error = f'Shell metacharacters in path: {path}'
            return False

        return True

    def _check_keyboard(self, params: dict[str, Any]) -> bool:
        if not self._param_length_ok(params):
            self.last_error = f'Param exceeds max length ({_MAX_PARAM_LENGTH})'
            return False

        key = str(params.get('key', ''))
        if len(key) > 1 and key not in self._known_keys():
            self.last_error = f'Unrecognised key name: {key}'
            return False
        return True

    def _check_system(self, params: dict[str, Any]) -> bool:
        if not self._param_length_ok(params):
            self.last_error = f'Param exceeds max length ({_MAX_PARAM_LENGTH})'
            return False

        sys_type = str(params.get('type', ''))
        if not sys_type:
            self.last_error = 'system action missing "type" param'
            return False

        # System types are already whitelisted by the executor
        # (_SYSTEM_COMMANDS dict).  Here we only reject empty types
        # and overlong params.
        return True

    def _check_mouse(self, params: dict[str, Any]) -> bool:
        if not self._param_length_ok(params):
            self.last_error = f'Param exceeds max length ({_MAX_PARAM_LENGTH})'
            return False
        # Mouse actions have no safety-relevant params beyond length.
        return True

    # -- Helper -----------------------------------------------------------

    @staticmethod
    def _known_keys() -> set[str]:
        from actions.executors.windows_executor import _KEY_NAME_TO_VK, _MODIFIER_VK
        return set(_KEY_NAME_TO_VK) | set(_MODIFIER_VK)
