"""ExtensionRegistry — singleton registry for V2.0 extension points.

Implements TRD §3.15 (ExtensionRegistry). Provides a single
point of registration and lookup for all pluggable components:

  - Gesture recognizers (static and dynamic)
  - Action executors
  - Context adapters
  - Pipeline filters

RULES §2.9: the registry is the ONLY way to wire extensions into
the pipeline. Direct instantiation of extension classes outside of
tests is a RULES violation.

Thread model: the registry is populated once at startup (main thread)
and read-only thereafter. Read operations are not locked; writes
outside of startup must be synchronized by the caller.
"""

from __future__ import annotations

from typing import Any


class ExtensionRegistry:
    """Singleton registry for all V2.0 extension points.

    Usage:
        reg = ExtensionRegistry.get_instance()
        reg.register_recognizer('pinch', PinchRecognizer())
        reg.register_executor('click', ClickExecutor())

    Accessors return None for unregistered keys so callers can
    degrade gracefully (e.g. skip an unregistered gesture type).
    """

    _instance: ExtensionRegistry | None = None

    def __init__(self) -> None:
        if ExtensionRegistry._instance is not None:
            raise RuntimeError(
                'ExtensionRegistry is a singleton. Use get_instance().'
            )
        self._recognizers: dict[str, Any] = {}
        self._executors: dict[str, Any] = {}
        self._context_adapters: dict[str, Any] = {}
        self._filters: dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> ExtensionRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Test-only: clear the singleton so a fresh registry is
        created on the next get_instance() call."""
        cls._instance = None

    # -- Recognizers ----------------------------------------------------------

    def register_recognizer(self, name: str, recognizer: Any) -> None:
        self._recognizers[name] = recognizer

    def get_recognizer(self, name: str) -> Any | None:
        return self._recognizers.get(name)

    @property
    def recognizers(self) -> dict[str, Any]:
        return dict(self._recognizers)

    # -- Executors ------------------------------------------------------------

    def register_executor(self, action_type: str, executor: Any) -> None:
        self._executors[action_type] = executor

    def get_executor(self, action_type: str) -> Any | None:
        return self._executors.get(action_type)

    @property
    def executors(self) -> dict[str, Any]:
        return dict(self._executors)

    # -- Context adapters -----------------------------------------------------

    def register_context_adapter(self, name: str, adapter: Any) -> None:
        self._context_adapters[name] = adapter

    def get_context_adapter(self, name: str) -> Any | None:
        return self._context_adapters.get(name)

    @property
    def context_adapters(self) -> dict[str, Any]:
        return dict(self._context_adapters)

    # -- Pipeline filters -----------------------------------------------------

    def register_filter(self, name: str, filter_obj: Any) -> None:
        self._filters[name] = filter_obj

    def get_filter(self, name: str) -> Any | None:
        return self._filters.get(name)

    @property
    def filters(self) -> dict[str, Any]:
        return dict(self._filters)
