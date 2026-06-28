"""Diagnostics and structured logging for GestureOS.

Implements TRD §9 (Diagnostics Architecture).  At Checkpoint 0 only the
foundational logging pipeline is scaffolded — the event categories
(camera, tracking, gesture, activation, context, action, lighting, etc.)
are added by the checkpoints that introduce the corresponding components.

At Checkpoint 4 the `activation` category gains its first dedicated
helper, `log_activation_state_changed`, called by `ActivationGate` on
every INACTIVE/ACTIVE transition (PRD §7.1 FR-AM-04, TRD §5.3 + §9.1).

Every component logs through DiagnosticsManager's structured helpers, not
through ad-hoc logging.getLogger calls (AI Development Guide §6.5, §8.3).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from diagnostics.log_format import LogFormatter


_LOG_DIR = Path.home() / '.gestureos' / 'logs'
_LOG_FILE = _LOG_DIR / 'gestureos.log'
_LOG_LEVEL = logging.DEBUG  # DEBUG-level file; console is INFO unless dev_mode

# Max 5 MB per log file, keep 3 backups
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


class DiagnosticsManager:
    """Central diagnostics hub: structured logging pipeline + ring buffer.

    Implements TRD §3.16 (DiagnosticsManager) and TRD §9 (Diagnostics
    Architecture).  All components emit log events through this class.

    At Checkpoint 0 the ring buffer for the debug panel is a stub —
    full implementation (200-event capped deque) is added in Checkpoint 8
    (Diagnostics Layer) alongside the Developer Mode debug panel.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or _LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger('gestureos')
        self._logger.setLevel(_LOG_LEVEL)
        # Close existing handlers before clearing so that previously
        # installed file handles (e.g., RotatingFileHandler instances
        # from prior test instances) are released. Without this,
        # Python's GC raises a ResourceWarning when the OLD handler's
        # underlying file is closed after handlers.clear() detaches it
        # from the logger (test-isolation fix for the existing
        # test_settings_manager.py::test_log_line_format).
        for h in list(self._logger.handlers):
            try:
                h.close()
            except Exception:
                pass
        self._logger.handlers.clear()

        # === File handler (all levels) ===
        from logging.handlers import RotatingFileHandler

        fh = RotatingFileHandler(
            self._log_dir / 'gestureos.log',
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding='utf-8',
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(LogFormatter())
        self._logger.addHandler(fh)

        # === Console handler (INFO+, structured) ===
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(LogFormatter())
        self._logger.addHandler(ch)

        # Suppress overly verbose third-party loggers
        logging.getLogger('mediapipe').setLevel(logging.WARNING)
        logging.getLogger('matplotlib').setLevel(logging.WARNING)

    # -- Structured helpers --------------------------------------------------

    @staticmethod
    def _log(
        logger: logging.Logger,
        level: int,
        module: str,
        message: str,
        **extras: object,
    ) -> None:
        """Emit a structured log record.

        The `module` param sets the log's category tag (e.g., 'camera',
        'gesture', 'activation').  Extras are serialised by LogFormatter.
        """
        logger.log(level, message, extra={'extras': {**extras, 'module': module}})

    def log_event(self, level: int, module: str, message: str, **extras: object) -> None:
        self._log(self._logger, level, module, message, **extras)

    def debug(self, module: str, message: str, **extras: object) -> None:
        self._log(self._logger, logging.DEBUG, module, message, **extras)

    def info(self, module: str, message: str, **extras: object) -> None:
        self._log(self._logger, logging.INFO, module, message, **extras)

    def warning(self, module: str, message: str, **extras: object) -> None:
        self._log(self._logger, logging.WARNING, module, message, **extras)

    def error(self, module: str, message: str, **extras: object) -> None:
        self._log(self._logger, logging.ERROR, module, message, **extras)

    def log_activation_state_changed(
        self,
        from_state: str,
        to_state: str,
        method: str,
    ) -> None:
        """Emit a structured INFO log for an activation-state transition.

        Implements the activation-category event introduced at
        Checkpoint 4 (TRD §9.2 + PRD §7.1 FR-AM-04). Mirrors the
        TRD §9.1 example log line:

            `[12:31:55.900] [INFO] [activation] State changed`
            ` {from: 'inactive', to: 'active', method: 'open_palm_hold'}`

        Args:
            from_state: previous tracking state (`'inactive'` /
                `'active'`).
            to_state: new tracking state (`'inactive'` / `'active'`).
            method: which activation method drove the transition
                (`'open_palm_hold'`, `'closed_fist_hold'`,
                `'keyboard_shortcut'`, `'tray_toggle'`).

        This helper is a thin wrapper over `info()` and exists so
        `ActivationGate` does not have to construct the extras dict
        itself — keeping the structured-log format defined in ONE
        place (here, alongside the other log helpers).
        """
        self.info(
            'activation',
            'State changed',
            event='state_changed',
            from_state=from_state,
            to_state=to_state,
            method=method,
        )

    # -- Convenience accessors ------------------------------------------------

    @property
    def logger(self) -> logging.Logger:
        return self._logger
