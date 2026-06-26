"""Type-safe settings management for GestureOS.

Implements TRD §7 (Configuration Design). The Settings dataclass mirrors
PRD §11.2's settings.json schema in full.  Atomic-write + per-field
validation ensures settings corruption never crashes or silently defaults
the entire config.

RULES §3 (Configuration Rules): all tunable thresholds/ratios/timings
must be defined as named constants here (they eventually live in
config.py, but at Checkpoint 0 the Settings class is the single source
of truth — per-module config.py is added per the 'Configuration over
code' principle, TRD §1.1/§5).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, fields as dataclass_fields
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Settings dataclass  (PRD §11.2 / TRD §7.2 full v1.2 schema)
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    """All user-configurable settings for GestureOS.

    Every field corresponds to exactly one key in settings.json.
    Default values match PRD §11.2 / TRD §7.1.
    """
    # ---- Camera ----
    camera_index: int = 0
    target_fps: int = 30
    # ---- Recognition ----
    gesture_confidence_threshold: float = 0.85
    activation_hold_duration_s: float = 1.0
    # ---- Cursor ----
    cursor_smoothing_method: str = 'exponential'
    cursor_smoothing_alpha: float = 0.7
    cursor_speed_multiplier: float = 1.5
    # ---- Cooldown ----
    gesture_cooldown_static_ms: int = 500
    gesture_cooldown_dynamic_ms: int = 1000
    # ---- Stability ----
    gesture_stability_window_ms: int = 200
    # ---- Dynamic / Motion ----
    dynamic_window_ms: int = 750
    motion_history_frames: int = 20
    # ---- Occlusion ----
    occlusion_retention_ms: int = 300
    # ---- Context ----
    context_verification_ms: int = 200
    # ---- Hand ----
    dominant_hand_mode: str = 'off'
    # ---- Profile & UI ----
    active_profile: str = 'productivity'
    show_overlay: bool = True
    developer_mode: bool = False


# ---------------------------------------------------------------------------
# Validation rules  (TRD §7.1 per-field fallback)
# ---------------------------------------------------------------------------

_FIELD_VALIDATORS: dict[str, tuple[type, Any]] = {
    'camera_index': (int, 0),
    'target_fps': (int, 30),
    'gesture_confidence_threshold': (float, 0.85),
    'activation_hold_duration_s': (float, 1.0),
    'cursor_smoothing_method': (str, 'exponential'),
    'cursor_smoothing_alpha': (float, 0.7),
    'cursor_speed_multiplier': (float, 1.5),
    'gesture_cooldown_static_ms': (int, 500),
    'gesture_cooldown_dynamic_ms': (int, 1000),
    'gesture_stability_window_ms': (int, 200),
    'dynamic_window_ms': (int, 750),
    'motion_history_frames': (int, 20),
    'occlusion_retention_ms': (int, 300),
    'context_verification_ms': (int, 200),
    'dominant_hand_mode': (str, 'off'),
    'active_profile': (str, 'productivity'),
    'show_overlay': (bool, True),
    'developer_mode': (bool, False),
}

# Constrained string domains (TRD §7.1)
_SMOOTHING_METHODS = ('exponential', 'moving_average', 'one_euro')
_DOMINANT_HAND_MODES = ('off', 'left', 'right')

_FLOAT_RANGES: dict[str, tuple[float, float]] = {
    'gesture_confidence_threshold': (0.50, 0.99),
}

_INT_RANGES: dict[str, tuple[int, int]] = {
    'gesture_cooldown_static_ms': (100, 2000),
    'gesture_cooldown_dynamic_ms': (200, 3000),
    'gesture_stability_window_ms': (100, 500),
    'motion_history_frames': (10, 40),
    'occlusion_retention_ms': (100, 1000),
    'context_verification_ms': (50, 1000),
}


def _validate_field(name: str, value: Any) -> Any:
    """Validate and coerce a single field; return the valid/default value.

    Implements TRD §7.1's per-field fallback strategy: invalid values
    are silently reverted to their documented default with no exception.
    """
    info = _FIELD_VALIDATORS.get(name)
    if info is None:
        return value  # unknown field, let caller handle
    expected_type, default = info

    # Type check
    if not isinstance(value, expected_type):
        return default

    # String domain check
    if name == 'cursor_smoothing_method' and value not in _SMOOTHING_METHODS:
        return default
    if name == 'dominant_hand_mode' and value not in _DOMINANT_HAND_MODES:
        return default

    # Float range check
    if name in _FLOAT_RANGES:
        lo, hi = _FLOAT_RANGES[name]
        if not (lo <= value <= hi):
            return default

    # Int range check
    if name in _INT_RANGES:
        lo, hi = _INT_RANGES[name]
        if not (lo <= value <= hi):
            return default

    return value


# ---------------------------------------------------------------------------
# SettingsManager
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path.home() / '.gestureos'
_SETTINGS_PATH = _CONFIG_DIR / 'settings.json'


class SettingsManager:
    """Load, validate, and persist Settings via atomic file writes.

    Implements TRD §3.16 (SettingsManager) + TRD §7.1 (per-field fallback
    validation + atomic write).  Every later checkpoint trusts these
    behaviors — they are unit-tested exhaustively in this checkpoint
    (tests/unit/test_settings_manager.py).
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir or _CONFIG_DIR
        self._settings_path = self._config_dir / 'settings.json'
        self._settings: Settings | None = None

    # -- Public API ----------------------------------------------------------

    @property
    def settings(self) -> Settings:
        """Return the cached Settings object (loads on first access)."""
        if self._settings is None:
            self._settings = self.load()
        return self._settings

    def load(self) -> Settings:
        """Load settings.json, validate per-field, and return a Settings.

        If the file does not exist: write defaults and return defaults.
        If the file is malformed JSON: return full defaults (no raise).
        Invalid individual fields: fall back per-field to default per TRD §7.1.
        """
        self._ensure_config_dir()

        if not self._settings_path.exists():
            self._write_defaults()
            self._settings = Settings()
            return self._settings

        try:
            raw: dict[str, Any] = json.loads(self._settings_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            # Corrupted or unreadable — return full defaults, do not overwrite
            # the corrupted file so data-recovery tools still have access.
            self._settings = Settings()
            return self._settings

        validated: dict[str, Any] = {}
        for field in dataclass_fields(Settings):
            raw_value = raw.get(field.name)
            if raw_value is None:
                validated[field.name] = field.default
            else:
                validated[field.name] = _validate_field(field.name, raw_value)

        self._settings = Settings(**validated)
        return self._settings

    def save(self, **overrides: Any) -> Settings:
        """Update settings fields, persist atomically, return new Settings.

        Any keyword argument matching a Settings field name is updated
        before writing.  All values are validated per-field before the
        write; invalid values are silently reverted to their default.
        """
        if self._settings is None:
            self._settings = self.load()

        raw: dict[str, Any] = {}
        for field in dataclass_fields(Settings):
            if field.name in overrides:
                raw[field.name] = _validate_field(field.name, overrides[field.name])
            else:
                raw[field.name] = getattr(self._settings, field.name)

        self._atomic_write(raw)
        self._settings = Settings(**raw)
        return self._settings

    def update(self, **overrides: Any) -> Settings:
        """Alias for save() — matches the convention used in TRD code examples."""
        return self.save(**overrides)

    # -- Internal helpers ----------------------------------------------------

    def _ensure_config_dir(self) -> None:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = self._config_dir / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)
        mappings_dir = self._config_dir / 'mappings'
        mappings_dir.mkdir(parents=True, exist_ok=True)

    def _write_defaults(self) -> None:
        raw = {field.name: getattr(Settings(), field.name) for field in dataclass_fields(Settings)}
        self._atomic_write(raw)

    def _atomic_write(self, data: dict[str, Any]) -> None:
        """Write data as JSON to a temp file, then rename over target.

        Atomic-rename on the same filesystem ensures the write either
        fully completes or does not touch the original file (TRD §7.1).
        """
        fd, tmp_path = tempfile.mkstemp(
            suffix='.json',
            prefix='settings_',
            dir=str(self._config_dir),
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(tmp_path, str(self._settings_path))
        except BaseException:
            # Clean up the temp file on any failure (OSError, write error, etc.)
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
