"""Actions — gesture-to-action dispatch layer (CP-5).

Provides:
  - ``CommandRouter``: gesture → ``Action`` translation
  - ``ProfileManager``: profile load/validate/save/resolve
  - ``Executor``: platform-agnostic action-dispatch facade
  - ``WindowsExecutor``: concrete OS implementation for Windows 10/11

Thread safety: all classes in this package are stateless (read-only
after construction) and safe to call from any thread.
"""

from __future__ import annotations

from actions.executors.windows_executor import WindowsExecutor
from actions.profile_manager import ProfileManager
from actions.router import CommandRouter


__all__ = [
    'CommandRouter',
    'Executor',
    'ProfileManager',
    'WindowsExecutor',
]


class Executor:
    """Platform-agnostic action-dispatch facade.

    Dispatches an ``Action`` to the platform-specific backend
    (currently ``WindowsExecutor``).  Every call returns an
    ``ActionResult`` — the facade never raises.

    Usage::

        executor = Executor()
        result = executor.execute(action)
        if not result.success:
            log.warning("Action failed: %s", result.error)
    """

    def __init__(self, backend: WindowsExecutor | None = None) -> None:
        """Initialise the executor facade.

        Args:
            backend: Platform-specific executor backend.  When
                ``None``, a ``WindowsExecutor`` is created.
        """
        self._backend = backend or WindowsExecutor()

    def execute(self, action) -> Any:  # noqa: ANN401 — returns ActionResult
        """Execute an action through the platform backend.

        Args:
            action: The ``Action`` to dispatch.

        Returns:
            ``ActionResult`` — always defined, never raises.
        """
        return self._backend.execute(action)
