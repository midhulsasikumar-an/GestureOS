"""Structured log-line formatting for GestureOS.

Implements TRD §9.1 logging pipeline format:
  [TIMESTAMP] [LEVEL] [MODULE] Message  {key: value, ...}

This module provides the LogFormatter class used by DiagnosticsManager.
It deliberately avoids any external dependency beyond stdlib's logging,
keeping it safe for early-CP import.
"""

from __future__ import annotations

import logging


class LogFormatter(logging.Formatter):
    """Structured log formatter matching TRD §9.1's exact format.

    Format: [2026-01-15 14:30:22.123] [INFO] [camera] Camera started  {device: 0}

    Extra fields passed via the `extra` dict are appended as a compact
    JSON-like key: value suffix when present.
    """

    def __init__(self) -> None:
        super().__init__(
            fmt='[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(module)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        # Append structured extras if present and non-empty
        extras = getattr(record, 'extras', None)
        if extras and isinstance(extras, dict) and len(extras) > 0:
            pairs = ', '.join(f'{k}: {v!r}' for k, v in extras.items())
            base = f'{base}  {{{pairs}}}'
        return base
