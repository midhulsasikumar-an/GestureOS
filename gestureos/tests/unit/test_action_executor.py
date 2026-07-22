"""Unit tests for the CP-5 ActionExecutor / WindowsExecutor.

Test strategy:
  - The WindowsExecutor backend calls ctypes.windll.user32 functions.
    We mock ``ctypes.windll`` so tests never touch the OS.
  - The facade (``Executor``) delegates to the backend; we test
    delegation and error wrapping.
  - All OS-dependent paths (system commands via subprocess) are
    tested with monkeypatched ``subprocess.run``.

Tests cover:
  - Keyboard dispatch (named keys, modifier keys, single chars)
  - Mouse dispatch (click, right_click, double_click)
  - System dispatch (show_desktop, lock, shutdown, no-op)
  - App_launch dispatch (file path, shell command)
  - Unknown action_type
  - Missing required params
  - Executor facade delegation
  - Hot-path safety (execute never raises)
  - Unknown key handling
  - Permission error handling in system commands
  - Executor facade with custom backend
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models.data_models import Action, ActionResult

from actions import Executor
from actions.executors.windows_executor import WindowsExecutor


# ======================================================================
# Helpers
# ======================================================================

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


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def mock_user32() -> MagicMock:
    """Mock ctypes.windll.user32 so no real OS calls happen."""
    with patch('actions.executors.windows_executor.ctypes.windll') as mock:
        mock.user32 = MagicMock()
        yield mock.user32


@pytest.fixture
def executor(mock_user32: MagicMock) -> WindowsExecutor:  # noqa: ARG001
    return WindowsExecutor()


# ======================================================================
# Keyboard
# ======================================================================

class TestKeyboard:
    """Keyboard actions press named keys, modifiers, or single chars."""

    def test_named_key(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'volume_up'})
        result = executor.execute(action)
        assert result.success
        assert result.error is None
        # keybd_event called twice (down + up)
        assert mock_user32.keybd_event.call_count == 2

    def test_volume_down(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'volume_down'})
        result = executor.execute(action)
        assert result.success

    def test_media_play_pause(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'media_play_pause'})
        result = executor.execute(action)
        assert result.success

    def test_escape(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'escape'})
        result = executor.execute(action)
        assert result.success

    def test_single_character_key(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'a'})
        result = executor.execute(action)
        assert result.success

    def test_missing_key_param(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {})
        result = executor.execute(action)
        assert not result.success
        assert 'missing' in (result.error or '').lower()

    def test_unknown_key_name(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        # Unknown key names are treated as single characters (ord lookup).
        action = make_action('keyboard', {'key': 'some_long_name'})
        result = executor.execute(action)
        assert result.success
        # Should press the uppercase of the first char only.
        assert mock_user32.keybd_event.call_count == 2


# ======================================================================
# Mouse
# ======================================================================

class TestMouse:
    """Mouse actions simulate clicks at the current cursor position."""

    def test_left_click(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('mouse', {'action': 'click'})
        result = executor.execute(action)
        assert result.success
        # mouse_event called 2 times (down + up)
        assert mock_user32.mouse_event.call_count == 2

    def test_right_click(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('mouse', {'action': 'right_click'})
        result = executor.execute(action)
        assert result.success

    def test_double_click(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('mouse', {'action': 'double_click'})
        result = executor.execute(action)
        assert result.success
        # double_click = 2 pairs of down+up = 4 calls
        assert mock_user32.mouse_event.call_count == 4

    def test_unknown_mouse_action(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('mouse', {'action': 'hover'})
        result = executor.execute(action)
        assert not result.success
        assert 'unknown' in (result.error or '').lower()

    def test_missing_action_param_defaults_to_click(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('mouse', {})
        result = executor.execute(action)
        assert result.success
        assert mock_user32.mouse_event.call_count == 2


# ======================================================================
# System
# ======================================================================

class TestSystem:
    """System actions run OS commands or key chords."""

    def test_show_desktop(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('system', {'type': 'show_desktop'})
        result = executor.execute(action)
        assert result.success
        # Win+D chord: 4 keybd_event calls (mod down, key down, key up, mod up)
        assert mock_user32.keybd_event.call_count == 4

    def test_lock(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            action = make_action('system', {'type': 'lock'})
            result = executor.execute(action)
            assert result.success

    def test_toggle_gesture_control_is_noop(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('system', {'type': 'toggle_gesture_control'})
        result = executor.execute(action)
        assert result.success
        # No-op actions return error='noop' to indicate they were handled
        # but performed no OS operation.
        assert result.error == 'noop'

    def test_shutdown(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            action = make_action('system', {'type': 'shutdown'})
            result = executor.execute(action)
            assert result.success

    def test_missing_type_param(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('system', {})
        result = executor.execute(action)
        assert not result.success
        assert 'missing' in (result.error or '').lower()

    def test_unknown_system_type(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('system', {'type': 'nonexistent_action'})
        result = executor.execute(action)
        assert not result.success
        assert 'unknown' in (result.error or '').lower()

    def test_system_command_timeout(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        with patch('subprocess.run') as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired(cmd='cmd', timeout=10)
            action = make_action('system', {'type': 'lock'})
            result = executor.execute(action)
            assert not result.success
            assert 'timed' in (result.error or '').lower()


# ======================================================================
# App launch
# ======================================================================

class TestAppLaunch:
    """App_launch actions start applications."""

    def test_launch_by_path(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        with patch('os.path.isfile', return_value=True), \
             patch('os.startfile') as mock_startfile:
            action = make_action('app_launch', {'path': r'C:\Windows\notepad.exe'})
            result = executor.execute(action)
            assert result.success
            mock_startfile.assert_called_once()

    def test_launch_by_shell(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        with patch('os.path.isfile', return_value=False), \
             patch('subprocess.Popen') as mock_popen:
            action = make_action('app_launch', {'app': 'notepad.exe'})
            result = executor.execute(action)
            assert result.success
            mock_popen.assert_called_once()

    def test_missing_app_param(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('app_launch', {})
        result = executor.execute(action)
        assert not result.success
        assert 'missing' in (result.error or '').lower()

    def test_launch_failure(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        with patch('os.path.isfile', return_value=True), \
             patch('os.startfile', side_effect=PermissionError('Access denied')):
            action = make_action('app_launch', {'path': r'C:\Windows\system.exe'})
            result = executor.execute(action)
            assert not result.success
            assert 'Access denied' in (result.error or '')


# ======================================================================
# Unknown action_type
# ======================================================================

class TestUnknownActionType:
    """Unknown action types return an error."""

    def test_unknown_type(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('cursor_move', {})
        result = executor.execute(action)
        assert not result.success
        assert 'unknown' in (result.error or '').lower()


# ======================================================================
# Hot-path safety
# ======================================================================

class TestHotPathSafety:
    """execute() never raises — errors are returned as ActionResult."""

    def test_executor_never_raises(self) -> None:
        executor = WindowsExecutor()
        # A completely malformed Action should not cause a raise.
        action = Action(
            action_type='keyboard',
            params='not_a_dict',  # type: ignore[arg-type]
            gesture_name='test',
            context='',
        )
        result = executor.execute(action)
        # Should get an ActionResult (not an exception).
        assert isinstance(result, ActionResult)
        assert not result.success

    def test_none_params(self) -> None:
        executor = WindowsExecutor()
        action = Action(
            action_type='mouse',
            params=None,  # type: ignore[arg-type]
            gesture_name='test',
            context='',
        )
        result = executor.execute(action)
        assert isinstance(result, ActionResult)
        assert not result.success


# ======================================================================
# Executor facade
# ======================================================================

class TestExecutorFacade:
    """The Executor facade delegates to the platform backend."""

    def test_default_backend(self) -> None:
        executor = Executor()
        assert executor._backend is not None
        assert isinstance(executor._backend, WindowsExecutor)

    def test_custom_backend(self) -> None:
        mock_backend = MagicMock()
        mock_backend.execute.return_value = ActionResult(
            success=True, action=None, error=None,
        )
        executor = Executor(backend=mock_backend)
        action = make_action('keyboard', {'key': 'space'})
        result = executor.execute(action)
        assert result.success
        mock_backend.execute.assert_called_once_with(action)

    def test_delegation(self) -> None:
        with patch('actions.executors.windows_executor.ctypes.windll'):
            executor = Executor()
            action = make_action('keyboard', {'key': 'escape'})
            result = executor.execute(action)
            assert result.success


# ======================================================================
# Modifier key support
# ======================================================================

class TestModifierKeys:
    """Modifier keys (ctrl, alt, shift, win) are pressable."""

    def test_win_key(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'win'})
        result = executor.execute(action)
        assert result.success
        assert mock_user32.keybd_event.call_count == 2

    def test_ctrl_key(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'ctrl'})
        result = executor.execute(action)
        assert result.success

    def test_alt_key(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'alt'})
        result = executor.execute(action)
        assert result.success

    def test_shift_key(self, executor: WindowsExecutor, mock_user32: MagicMock) -> None:
        action = make_action('keyboard', {'key': 'shift'})
        result = executor.execute(action)
        assert result.success
