"""WindowsExecutor — action dispatch for Windows 10/11.

Implements TRD §3.13 (ActionDispatcher) for the Windows platform.
All OS interaction goes through ctypes (built-in) — no external
dependencies beyond Python's standard library.

Supported action types:
  - ``keyboard`` : simulate key presses via ``SendInput``
  - ``mouse``    : simulate mouse clicks via ``mouse_event``
  - ``system``   : run OS-level commands (shutdown, lock, etc.)
  - ``app_launch``: launch applications via ``subprocess.Popen`` or
    ``os.startfile``

CP-5 safety contract: ``execute()`` never raises.  Every error is
caught and returned as ``ActionResult(success=False, error=...)``.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
import subprocess
from typing import Any

from models.data_models import Action, ActionResult


logger = logging.getLogger('gestureos')

# ---------------------------------------------------------------------------
# Windows virtual-key codes
# ---------------------------------------------------------------------------

VK_VOLUME_UP = 0xAF
VK_VOLUME_DOWN = 0xAE
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_ESCAPE = 0x1B
VK_TAB = 0x09
VK_SPACE = 0x20
VK_RETURN = 0x0D
VK_LWIN = 0x5B
VK_D = 0x44
VK_L = 0x4C
VK_X = 0x58
VK_UP = 0x26
VK_DOWN = 0x28
VK_LEFT = 0x25
VK_RIGHT = 0x27

# Mouse event flags (dwFlags for mouse_event)
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040

# SendInput / KEYBDINPUT flags
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_SCANCODE = 0x0008


# ---------------------------------------------------------------------------
# Key-name → VK code mapping
# ---------------------------------------------------------------------------

_KEY_NAME_TO_VK: dict[str, int] = {
    'volume_up': VK_VOLUME_UP,
    'volume_down': VK_VOLUME_DOWN,
    'media_play_pause': VK_MEDIA_PLAY_PAUSE,
    'media_next': VK_MEDIA_NEXT_TRACK,
    'media_prev': VK_MEDIA_PREV_TRACK,
    'escape': VK_ESCAPE,
    'tab': VK_TAB,
    'space': VK_SPACE,
    'enter': VK_RETURN,
    'up': VK_UP,
    'down': VK_DOWN,
    'left': VK_LEFT,
    'right': VK_RIGHT,
}

# Modifier-key names → VK codes (used for chorded hotkeys like Win+D).
_MODIFIER_VK: dict[str, int] = {
    'win': VK_LWIN,
    'ctrl': 0x11,
    'alt': 0x12,
    'shift': 0x10,
}


# ---------------------------------------------------------------------------
# System-action → command mapping
# ---------------------------------------------------------------------------

_SYSTEM_COMMANDS: dict[str, list[str]] = {
    'lock': ['rundll32.exe', 'user32.dll,LockWorkStation'],
    'shutdown': ['shutdown', '/s', '/t', '3'],
    'restart': ['shutdown', '/r', '/t', '3'],
    'sleep': ['rundll32.exe', 'powrprof.dll,SetSuspendState', 'Sleep'],
    'sign_out': ['shutdown', '/l'],
    'show_desktop': [],     # handled as Win+D key chord
    'toggle_gesture_control': [],  # no-op (internal state toggle)
}

#: Message displayed when the action is a no-op (e.g. internal toggles).
_NOOP_MESSAGE = 'noop'


# ---------------------------------------------------------------------------
# WindowsExecutor
# ---------------------------------------------------------------------------

class WindowsExecutor:
    """Windows-specific action executor.

    Dispatches an ``Action`` to the appropriate Windows API or OS
    command based on ``action.action_type``.  Every public method
    catches and returns errors as ``ActionResult`` — the executor
    never raises on the hot path.
    """

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, action: Action) -> ActionResult:
        """Execute an action.  Never raises.

        Args:
            action: The ``Action`` to dispatch.

        Returns:
            ``ActionResult`` indicating success or failure.
        """
        try:
            return self._dispatch(action)
        except Exception as exc:
            logger.error(
                'windows_executor',
                extra={'extras': {
                    'event': 'execute_failed',
                    'action_type': action.action_type,
                    'gesture': action.gesture_name,
                    'error': str(exc),
                }},
            )
            return ActionResult(success=False, action=action, error=str(exc))

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, action: Action) -> ActionResult:
        atype = action.action_type
        if atype == 'keyboard':
            return self._execute_keyboard(action)
        if atype == 'mouse':
            return self._execute_mouse(action)
        if atype == 'system':
            return self._execute_system(action)
        if atype == 'app_launch':
            return self._execute_app_launch(action)
        return ActionResult(
            success=False,
            action=action,
            error=f"Unknown action_type: {atype}",
        )

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def _execute_keyboard(self, action: Action) -> ActionResult:
        key_name = str(action.params.get('key', ''))
        if not key_name:
            return ActionResult(
                success=False, action=action,
                error='keyboard action missing "key" param',
            )
        if key_name in _KEY_NAME_TO_VK:
            vk = _KEY_NAME_TO_VK[key_name]
            self._press_key(vk)
        elif key_name in _MODIFIER_VK:
            vk = _MODIFIER_VK[key_name]
            self._press_key(vk)
        else:
            # Treat as a single-character key (first char only).
            vk = ord(key_name[0].upper())
            self._press_key(vk)
        return ActionResult(success=True, action=action, error=None)

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def _execute_mouse(self, action: Action) -> ActionResult:
        mouse_action = str(action.params.get('action', 'click'))
        if mouse_action == 'click':
            self._mouse_click(_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP)
        elif mouse_action == 'right_click':
            self._mouse_click(_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP)
        elif mouse_action == 'double_click':
            self._mouse_click(_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP)
            self._mouse_click(_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP)
        else:
            return ActionResult(
                success=False, action=action,
                error=f"Unknown mouse action: {mouse_action}",
            )
        return ActionResult(success=True, action=action, error=None)

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def _execute_system(self, action: Action) -> ActionResult:
        sys_type = str(action.params.get('type', ''))
        if not sys_type:
            return ActionResult(
                success=False, action=action,
                error='system action missing "type" param',
            )

        # Handle no-op actions (internal state toggles).
        if sys_type == 'toggle_gesture_control':
            return ActionResult(
                success=True, action=action, error=_NOOP_MESSAGE,
            )

        # Handle key-chord system actions.
        if sys_type == 'show_desktop':
            self._press_modifier_chord(VK_LWIN, VK_D)
            return ActionResult(success=True, action=action, error=None)

        # Handle command-based system actions.
        cmd = _SYSTEM_COMMANDS.get(sys_type)
        if cmd is None:
            return ActionResult(
                success=False, action=action,
                error=f"Unknown system action type: {sys_type}",
            )
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False, action=action,
                error=f"System command timed out: {sys_type}",
            )
        except subprocess.CalledProcessError as exc:
            return ActionResult(
                success=False, action=action,
                error=f"System command failed ({exc.returncode}): "
                      f"{exc.stderr.decode(errors='replace') if exc.stderr else str(exc)}",
            )
        return ActionResult(success=True, action=action, error=None)

    # ------------------------------------------------------------------
    # App launch
    # ------------------------------------------------------------------

    def _execute_app_launch(self, action: Action) -> ActionResult:
        path = str(action.params.get('path', action.params.get('app', '')))
        if not path:
            return ActionResult(
                success=False, action=action,
                error='app_launch action missing "path" or "app" param',
            )
        try:
            if os.path.isfile(path):
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(
                    path, shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as exc:
            return ActionResult(
                success=False, action=action,
                error=f"Failed to launch: {exc}",
            )
        return ActionResult(success=True, action=action, error=None)

    # ------------------------------------------------------------------
    # Low-level helpers (ctypes)
    # ------------------------------------------------------------------

    def _press_key(self, vk: int) -> None:
        """Press and release a single virtual key."""
        self._user32.keybd_event(vk, 0, 0, 0)
        self._user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)

    def _press_modifier_chord(self, mod_vk: int, key_vk: int) -> None:
        """Press a modifier+key chord (e.g. Win+D) and release."""
        self._user32.keybd_event(mod_vk, 0, 0, 0)
        self._user32.keybd_event(key_vk, 0, 0, 0)
        self._user32.keybd_event(key_vk, 0, _KEYEVENTF_KEYUP, 0)
        self._user32.keybd_event(mod_vk, 0, _KEYEVENTF_KEYUP, 0)

    def _mouse_click(self, down_flag: int, up_flag: int) -> None:
        """Send a mouse-button down/up event at the current cursor pos."""
        self._user32.mouse_event(down_flag, 0, 0, 0, 0)
        self._user32.mouse_event(up_flag, 0, 0, 0, 0)
