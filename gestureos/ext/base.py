"""Abstract base classes for the GestureOS extension framework.

Implements the four V2.0 ABC interfaces that all extension points
must inherit from. Per RULES §2.1, every component that plugs into
the pipeline exposes one of these interfaces.

Checkpoint 0: interfaces are defined with full signatures but all
method bodies are STUBBED (raise NotImplementedError). Concrete
implementations arrive in their respective checkpoints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class GestureRecognizerBase(ABC):
    """Base class for all gesture recognizers (static and dynamic).

    Per TRD §3.9 (GestureEngine), every recognizer accepts per-frame
    landmark data and returns zero or more GestureResult candidates.
    Concrete subclasses implement `recognize()`.

    RULES §2.3: recognizers never raise on hot-path input; they
    return an empty list for unrecognized input.
    """

    @abstractmethod
    def recognize(self, hand_data: Any, **kwargs: Any) -> list[Any]:
        """Run recognition on per-frame hand data.

        Args:
            hand_data: component-specific hand data object (HandData
                for static recognizers, MotionHistoryBuffer for
                dynamic recognizers).
            **kwargs: additional per-recognizer parameters (e.g.
                hand_scale for dynamic gestures).

        Returns:
            list of GestureResult candidates (empty if none match).
        """
        ...


class ActionExecutorBase(ABC):
    """Base class for all action executors.

    Per TRD §3.13 (ActionDispatcher), executors receive resolved
    Action objects and execute them against the OS or application.

    RULES §2.8: executors never call recognizer modules or
    manipulate camera/tracking state.
    """

    @abstractmethod
    def execute(self, action: Any) -> Any:
        """Execute a resolved action.

        Args:
            action: an Action object with action_type and params.

        Returns:
            ActionResult indicating success/failure.
        """
        ...


class ContextAdapterBase(ABC):
    """Base class for all context adapters.

    Per TRD §3.14 (ContextEngine), adapters monitor a specific
    source of contextual information (active window, audio, etc.)
    and compute a context fingerprint.

    RULES §2.10: adapters are stateless (or hold only connection-
    scoped state) and must be safe to call from any thread.
    """

    @abstractmethod
    def get_context(self, **kwargs: Any) -> dict[str, Any]:
        """Return the current context fingerprint for this adapter.

        Returns:
            dict mapping context keys to values. An empty dict
            means "no context available" (not an error).
        """
        ...


class PipelineFilterBase(ABC):
    """Base class for all pipeline filters.

    Per TRD §3.10-3.12, filters sit between gesture recognition and
    action dispatch. They transform or suppress gesture results.

    RULES §6.4: hot-path — never raises. Defensive wrapping is
    the base class's responsibility.
    """

    @abstractmethod
    def filter(self, results: Any, **kwargs: Any) -> Any:
        """Apply filter logic to gesture results.

        Args:
            results: list of GestureResult objects (or per-role
                candidates).
            **kwargs: per-filter parameters (e.g. `now` timestamp).

        Returns:
            Filtered results. The type matches the input type
            (list of GestureResult or single GestureResult | None).
        """
        ...
