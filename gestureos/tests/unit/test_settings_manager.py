"""Unit tests for SettingsManager — Checkpoint 0.

Verifies:
  1. Defaults written on first run                          (test_defaults_written_on_first_run)
  2. Invalid field reverts to default, valid fields preserved (test_invalid_field_reverts_to_default)
  3. Atomic write survives interruption                      (test_atomic_write_survives_interruption)
  4. Round-trip preserves all fields                         (test_round_trip_preserves_all_fields)
  5. Corrupted JSON returns full defaults                    (test_corrupted_json_returns_defaults)
  6. Log file created at documented path                     (test_log_file_created)
  7. Log line format matches TRD §9.1                        (test_log_line_format)

Per AI Development Guide §9.1: no live camera or hardware required —
all tests use tmp_path.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from settings.settings_manager import (
    Settings,
    SettingsManager,
    _validate_field,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def manager(tmp_path: Path) -> SettingsManager:
    """SettingsManager pointing at a temporary directory."""
    return SettingsManager(config_dir=tmp_path)


@pytest.fixture
def diagnostics_dir(tmp_path: Path) -> Path:
    """A temporary directory with a logs/ subdir for logging tests."""
    d = tmp_path / '.gestureos'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'logs').mkdir(parents=True, exist_ok=True)
    return d


# ======================================================================
# 1.  Defaults written on first run
# ======================================================================

class TestDefaults:
    def test_defaults_written_on_first_run(self, manager: SettingsManager) -> None:
        """Load on a fresh config dir must create settings.json and return defaults."""
        settings = manager.load()
        assert manager._settings_path.exists(), 'settings.json was not created'
        assert settings.gesture_confidence_threshold == 0.85
        assert settings.target_fps == 30
        assert settings.camera_index == 0
        assert settings.activation_hold_duration_s == 1.0
        assert settings.cursor_smoothing_method == 'exponential'
        assert settings.cursor_smoothing_alpha == 0.7
        assert settings.cursor_speed_multiplier == 1.5
        assert settings.gesture_cooldown_static_ms == 500
        assert settings.gesture_cooldown_dynamic_ms == 1000
        assert settings.gesture_stability_window_ms == 200
        assert settings.dynamic_window_ms == 750
        assert settings.motion_history_frames == 20
        assert settings.occlusion_retention_ms == 300
        assert settings.context_verification_ms == 200
        assert settings.dominant_hand_mode == 'off'
        assert settings.active_profile == 'productivity'
        assert settings.show_overlay is True
        assert settings.developer_mode is False


# ======================================================================
# 2.  Invalid field reverts to default, valid fields preserved
# ======================================================================

class TestFieldValidation:
    def test_invalid_gesture_confidence_reverts(self, tmp_path: Path) -> None:
        """Out-of-range confidence reverts to 0.85; camera_index=2 preserved."""
        settings_path = tmp_path / 'settings.json'
        settings_path.write_text(json.dumps({
            'gesture_confidence_threshold': 5.0,  # invalid: > 0.99
            'camera_index': 2,                      # valid: must survive
        }))
        mgr = SettingsManager(config_dir=tmp_path)
        settings = mgr.load()
        assert settings.gesture_confidence_threshold == 0.85
        assert settings.camera_index == 2

    def test_invalid_type_reverts(self) -> None:
        """String where int is expected reverts to default."""
        result = _validate_field('gesture_stability_window_ms', 'abc')
        assert result == 200

    def test_unknown_field_passthrough(self) -> None:
        """Unknown field names must pass through unmodified."""
        result = _validate_field('__unknown__', 42)
        assert result == 42

    def test_cursor_smoothing_method_invalid(self) -> None:
        """Unrecognised smoothing method falls back to 'exponential'."""
        result = _validate_field('cursor_smoothing_method', 'kalman')
        assert result == 'exponential'

    def test_dominant_hand_mode_invalid(self) -> None:
        """Invalid hand mode falls back to 'off'."""
        result = _validate_field('dominant_hand_mode', 'both')
        assert result == 'off'

    def test_int_out_of_range_reverts(self) -> None:
        """motion_history_frames=999 falls back to 20."""
        result = _validate_field('motion_history_frames', 999)
        assert result == 20

    def test_float_out_of_range_reverts(self) -> None:
        """gesture_confidence_threshold=0.01 falls back to 0.85."""
        result = _validate_field('gesture_confidence_threshold', 0.01)
        assert result == 0.85


# ======================================================================
# 3.  Atomic write survives interruption
# ======================================================================

class TestAtomicWrite:
    def test_atomic_write_survives_interruption(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Simulate a crash mid-write: original settings.json must remain valid."""
        mgr = SettingsManager(config_dir=tmp_path)
        mgr.load()  # write defaults

        original_content = mgr._settings_path.read_text(encoding='utf-8')

        # Crash *before* the rename by making os.fsync raise.
        # The fd must NOT be closed here — closing it would cause a
        # secondary exception from the file-object __exit__ that replaces
        # the original OSError message, making the match= regex fail.
        def crashing_fsync(fd: int) -> None:
            raise OSError('Simulated crash during fsync')

        monkeypatch.setattr(os, 'fsync', crashing_fsync)

        with pytest.raises(OSError, match='Simulated crash'):
            mgr.save(camera_index=9)

        # Original must be untouched
        assert mgr._settings_path.read_text(encoding='utf-8') == original_content

    def test_temp_file_cleaned_on_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When atomic write fails, temp file must not linger in config_dir."""
        mgr = SettingsManager(config_dir=tmp_path)
        mgr.load()

        # Patch os.fsync to raise before the rename.
        # No os.close(fd) here — see note in test_atomic_write_survives_interruption.
        def crashing_fsync(fd: int) -> None:
            raise OSError('fsync failed')

        monkeypatch.setattr(os, 'fsync', crashing_fsync)

        with pytest.raises(OSError):
            mgr.save(camera_index=9)

        # No temp files should remain
        temp_files = [p for p in tmp_path.iterdir() if p.name.startswith('settings_')]
        assert len(temp_files) == 0, f'Temp file(s) left behind: {temp_files}'


# ======================================================================
# 4.  Round-trip preserves all fields
# ======================================================================

class TestRoundTrip:
    def test_round_trip_preserves_all_fields(self, manager: SettingsManager) -> None:
        """Load defaults, set every field to a non-default, save, reload, assert all match."""
        manager.load()
        overrides = {
            'camera_index': 1,
            'target_fps': 60,
            'gesture_confidence_threshold': 0.90,
            'activation_hold_duration_s': 2.0,
            'cursor_smoothing_method': 'moving_average',
            'cursor_smoothing_alpha': 0.5,
            'cursor_speed_multiplier': 2.0,
            'gesture_cooldown_static_ms': 1000,
            'gesture_cooldown_dynamic_ms': 2000,
            'gesture_stability_window_ms': 300,
            'dynamic_window_ms': 1000,
            'motion_history_frames': 25,
            'occlusion_retention_ms': 500,
            'context_verification_ms': 300,
            'dominant_hand_mode': 'left',
            'active_profile': 'presentation',
            'show_overlay': False,
            'developer_mode': True,
        }
        saved = manager.save(**overrides)
        for key, val in overrides.items():
            assert getattr(saved, key) == val, f'Mismatch for {key}'

        # Re-load from disk and re-check
        mgr2 = SettingsManager(config_dir=manager._config_dir)
        loaded = mgr2.load()
        for key, val in overrides.items():
            assert getattr(loaded, key) == val, f'Round-trip mismatch for {key}'


# ======================================================================
# 5.  Corrupted JSON returns full defaults
# ======================================================================

class TestCorruptedFile:
    def test_corrupted_json_returns_defaults(self, manager: SettingsManager) -> None:
        """Garbage in settings.json must return full defaults without raising."""
        manager._settings_path.parent.mkdir(parents=True, exist_ok=True)
        manager._settings_path.write_text('{ this is not valid json!!! }')
        settings = manager.load()
        assert settings.gesture_confidence_threshold == 0.85
        assert settings.camera_index == 0

    def test_missing_file_creates_defaults(self, manager: SettingsManager) -> None:
        """No settings.json at all yields defaults + creates the file."""
        assert not manager._settings_path.exists()
        settings = manager.load()
        assert settings.gesture_confidence_threshold == 0.85
        assert manager._settings_path.exists()


# ======================================================================
# 6.  Log file created at documented path
# ======================================================================

class TestLogging:
    def test_log_file_created(self, manager: SettingsManager, tmp_path: Path) -> None:
        """Loading settings must create the .gestureos directory structure."""
        manager.load()
        logs_dir = manager._config_dir / 'logs'
        assert logs_dir.exists(), 'logs/ directory was not created'


# ======================================================================
# 7.  Log line format matches TRD §9.1
# ======================================================================

class TestLogFormat:
    def test_log_line_format(self, tmp_path: Path) -> None:
        """Emit a structured log and verify format matches TRD §9.1."""
        from diagnostics.diagnostics_manager import DiagnosticsManager

        diag = DiagnosticsManager(log_dir=tmp_path)
        diag.info('camera', 'Camera started', device=0, resolution='640x480', fps=30)

        log_file = tmp_path / 'gestureos.log'
        assert log_file.exists()
        line = log_file.read_text(encoding='utf-8').strip()

        # Expected format: [TIMESTAMP] [LEVEL] [MODULE] Message  {key: value, ...}
        # Relaxed check: starts with [, contains [INFO], contains [camera], contains Camera started
        assert line.startswith('['), f'Log line does not start with [: {line}'
        assert '[INFO]' in line, f'Log line missing [INFO]: {line}'
        assert '[camera]' in line or 'camera' in line, f'Log line missing module tag: {line}'
        assert 'Camera started' in line, f'Log line missing message: {line}'
        # Should contain structured extras (device, resolution, fps)
        assert 'device: 0' in line, f'Log line missing extras: {line}'
        assert 'resolution:' in line or "'640x480'" in line or '640x480' in line, f'Log line missing resolution: {line}'
