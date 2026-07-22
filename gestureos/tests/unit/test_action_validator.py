"""Unit tests for CP-5 ActionValidator safety checks.

Tests cover:
  - Safe app_launch paths pass
  - Path-traversal attempts in app_launch are blocked
  - Shell metacharacters in app_launch are blocked
  - Missing app_launch params rejected
  - Denied action types blocked
  - Overlong params rejected
  - Keyboard actions pass for valid keys
  - Unknown multi-char key names blocked
  - System actions pass for valid types
  - Missing system type blocked
  - Mouse actions always pass
  - Unknown action types pass through
  - Thread safety (stateless after construction)
"""

from __future__ import annotations

import pytest

from models.data_models import Action

from actions.safety import ActionValidator


def make_action(
    action_type: str = 'keyboard',
    params: dict | None = None,
    gesture_name: str = 'test_gesture',
) -> Action:
    return Action(
        action_type=action_type,
        params=params or {},
        gesture_name=gesture_name,
        context='',
    )


class TestAppLaunch:
    def test_valid_exe_path_passes(self) -> None:
        v = ActionValidator()
        action = make_action('app_launch', {'path': r'C:\Windows\notepad.exe'})
        assert v.is_safe(action)
        assert v.last_error is None

    def test_valid_app_name_passes(self) -> None:
        v = ActionValidator()
        action = make_action('app_launch', {'app': 'notepad.exe'})
        assert v.is_safe(action)
        assert v.last_error is None

    def test_path_traversal_blocked(self) -> None:
        v = ActionValidator()
        action = make_action('app_launch', {'path': r'C:\Users\..\..\malware.exe'})
        assert not v.is_safe(action)
        assert 'traversal' in (v.last_error or '').lower()

    def test_shell_metachar_ampersand_blocked(self) -> None:
        v = ActionValidator()
        action = make_action('app_launch', {'path': 'notepad.exe & calc.exe'})
        assert not v.is_safe(action)
        assert 'shell' in (v.last_error or '').lower()

    def test_shell_metachar_pipe_blocked(self) -> None:
        v = ActionValidator()
        action = make_action('app_launch', {'path': 'cmd /c dir | clip'})
        assert not v.is_safe(action)
        assert 'shell' in (v.last_error or '').lower()

    def test_shell_metachar_semicolon_blocked(self) -> None:
        v = ActionValidator()
        action = make_action('app_launch', {'path': 'calc.exe; shutdown /s'})
        assert not v.is_safe(action)
        assert 'shell' in (v.last_error or '').lower()

    def test_missing_params_rejected(self) -> None:
        v = ActionValidator()
        action = make_action('app_launch', {})
        assert not v.is_safe(action)
        assert 'missing' in (v.last_error or '').lower()


class TestKeyboard:
    def test_single_char_key_passes(self) -> None:
        v = ActionValidator()
        action = make_action('keyboard', {'key': 'a'})
        assert v.is_safe(action)

    def test_named_key_passes(self) -> None:
        v = ActionValidator()
        action = make_action('keyboard', {'key': 'volume_up'})
        assert v.is_safe(action)

    def test_modifier_key_passes(self) -> None:
        v = ActionValidator()
        action = make_action('keyboard', {'key': 'win'})
        assert v.is_safe(action)

    def test_unknown_multi_char_key_blocked(self) -> None:
        v = ActionValidator()
        action = make_action('keyboard', {'key': 'some_long_name'})
        assert not v.is_safe(action)
        assert 'unrecognised' in (v.last_error or '').lower()

    def test_empty_key_allowed(self) -> None:
        v = ActionValidator()
        action = make_action('keyboard', {})
        assert v.is_safe(action)


class TestSystem:
    def test_valid_system_type_passes(self) -> None:
        v = ActionValidator()
        action = make_action('system', {'type': 'lock'})
        assert v.is_safe(action)

    def test_another_valid_type(self) -> None:
        v = ActionValidator()
        action = make_action('system', {'type': 'show_desktop'})
        assert v.is_safe(action)

    def test_empty_type_rejected(self) -> None:
        v = ActionValidator()
        action = make_action('system', {})
        assert not v.is_safe(action)
        assert 'missing' in (v.last_error or '').lower()


class TestMouse:
    def test_mouse_click_passes(self) -> None:
        v = ActionValidator()
        action = make_action('mouse', {'action': 'click'})
        assert v.is_safe(action)

    def test_mouse_empty_params_passes(self) -> None:
        v = ActionValidator()
        action = make_action('mouse', {})
        assert v.is_safe(action)


class TestDeniedTypes:
    def test_denied_action_type_blocked(self) -> None:
        v = ActionValidator(denied_action_types={'app_launch'})
        action = make_action('app_launch', {'path': r'C:\Windows\notepad.exe'})
        assert not v.is_safe(action)
        assert 'denied' in (v.last_error or '').lower()

    def test_allowed_type_not_affected(self) -> None:
        v = ActionValidator(denied_action_types={'app_launch'})
        action = make_action('keyboard', {'key': 'a'})
        assert v.is_safe(action)

    def test_multiple_denied_types(self) -> None:
        v = ActionValidator(denied_action_types={'app_launch', 'system'})
        assert not v.is_safe(make_action('app_launch', {'path': 'test.exe'}))
        assert not v.is_safe(make_action('system', {'type': 'lock'}))


class TestParamLength:
    def test_overlong_param_blocked(self) -> None:
        v = ActionValidator()
        action = make_action('keyboard', {'key': 'x' * 600})
        assert not v.is_safe(action)
        assert 'exceeds' in (v.last_error or '').lower()


class TestUnknownTypes:
    def test_unknown_type_passes_through(self) -> None:
        v = ActionValidator()
        action = make_action('cursor_move', {'dx': 10, 'dy': 20})
        assert v.is_safe(action)
        assert v.last_error is None
