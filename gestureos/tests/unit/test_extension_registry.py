"""Unit tests for ExtensionRegistry (ext/registry.py) — CP-1.

Tests cover:
  - Singleton behaviour (get_instance, reset_instance)
  - register/get recognizer, executor, context adapter, filter
  - Unregistered keys return None (not raise)
  - Property accessors return snapshot dicts
  - Registration does not raise on first registration

Per AI Development Guide §11.1: no live components required.
"""

from __future__ import annotations

import pytest

from ext.registry import ExtensionRegistry


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    ExtensionRegistry.reset_instance()
    yield
    ExtensionRegistry.reset_instance()


@pytest.fixture
def reg() -> ExtensionRegistry:
    return ExtensionRegistry.get_instance()


# ======================================================================
# Singleton behaviour
# ======================================================================

class TestSingleton:
    def test_get_instance_returns_same(self) -> None:
        a = ExtensionRegistry.get_instance()
        b = ExtensionRegistry.get_instance()
        assert a is b

    def test_cannot_construct_directly(self) -> None:
        ExtensionRegistry.get_instance()  # establish singleton
        with pytest.raises(RuntimeError, match='singleton'):
            ExtensionRegistry()

    def test_reset_instance_clears(self) -> None:
        a = ExtensionRegistry.get_instance()
        ExtensionRegistry.reset_instance()
        b = ExtensionRegistry.get_instance()
        assert a is not b


# ======================================================================
# Recognizers
# ======================================================================

class TestRecognizers:
    def test_register_and_get(self, reg) -> None:
        impl = object()
        reg.register_recognizer('test_recognizer', impl)
        assert reg.get_recognizer('test_recognizer') is impl

    def test_unregistered_returns_none(self, reg) -> None:
        assert reg.get_recognizer('nonexistent') is None

    def test_register_overwrites(self, reg) -> None:
        a, b = object(), object()
        reg.register_recognizer('key', a)
        reg.register_recognizer('key', b)
        assert reg.get_recognizer('key') is b

    def test_recognizers_property_returns_snapshot(self, reg) -> None:
        impl = object()
        reg.register_recognizer('r1', impl)
        snap = reg.recognizers
        assert snap == {'r1': impl}
        snap['r1'] = 'mutated'
        assert reg.get_recognizer('r1') is impl  # original unchanged


# ======================================================================
# Executors
# ======================================================================

class TestExecutors:
    def test_register_and_get(self, reg) -> None:
        impl = object()
        reg.register_executor('click', impl)
        assert reg.get_executor('click') is impl

    def test_unregistered_returns_none(self, reg) -> None:
        assert reg.get_executor('nonexistent') is None

    def test_executors_property_returns_snapshot(self, reg) -> None:
        impl = object()
        reg.register_executor('e1', impl)
        snap = reg.executors
        assert snap == {'e1': impl}


# ======================================================================
# Context adapters
# ======================================================================

class TestContextAdapters:
    def test_register_and_get(self, reg) -> None:
        impl = object()
        reg.register_context_adapter('windows', impl)
        assert reg.get_context_adapter('windows') is impl

    def test_unregistered_returns_none(self, reg) -> None:
        assert reg.get_context_adapter('nonexistent') is None

    def test_context_adapters_property_returns_snapshot(self, reg) -> None:
        impl = object()
        reg.register_context_adapter('c1', impl)
        snap = reg.context_adapters
        assert snap == {'c1': impl}


# ======================================================================
# Filters
# ======================================================================

class TestFilters:
    def test_register_and_get(self, reg) -> None:
        impl = object()
        reg.register_filter('stabilizer', impl)
        assert reg.get_filter('stabilizer') is impl

    def test_unregistered_returns_none(self, reg) -> None:
        assert reg.get_filter('nonexistent') is None

    def test_filters_property_returns_snapshot(self, reg) -> None:
        impl = object()
        reg.register_filter('f1', impl)
        snap = reg.filters
        assert snap == {'f1': impl}


# ======================================================================
# Mixed operations — all four registries independent
# ======================================================================

class TestMixed:
    def test_registries_are_independent(self, reg) -> None:
        reg.register_recognizer('shared_key', 'recognizer')
        reg.register_executor('shared_key', 'executor')
        reg.register_context_adapter('shared_key', 'adapter')
        reg.register_filter('shared_key', 'filter')

        assert reg.get_recognizer('shared_key') == 'recognizer'
        assert reg.get_executor('shared_key') == 'executor'
        assert reg.get_context_adapter('shared_key') == 'adapter'
        assert reg.get_filter('shared_key') == 'filter'

    def test_empty_registry_returns_empty_properties(self, reg) -> None:
        assert reg.recognizers == {}
        assert reg.executors == {}
        assert reg.context_adapters == {}
        assert reg.filters == {}
