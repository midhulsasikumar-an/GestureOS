"""pytest fixtures and shared test helpers for GestureOS.

Checkpoint 0 scaffold — empty fixture file.  Subsequent checkpoints add
per-component fixtures here:
  - Checkpoint 1: sample_frames/ for TrackingModule tests
  - Checkpoint 2: sample_landmarks.json, occlusion_sequence.json
  - Checkpoint 3: gesture landmark fixtures (open_palm_right.json, …)
  - etc.

Per AI Development Guide §9.1 / TRD §13.2: fixtures are loaded from
JSON under tests/fixtures/, never hardcoded inline across multiple files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures'


def load_fixture(name: str) -> dict | list:
    """Load a JSON fixture file from tests/fixtures/.

    Args:
        name: Filename (e.g., 'open_palm_right.json').

    Returns:
        Parsed JSON content.

    Raises:
        FileNotFoundError: if the fixture does not exist.
    """
    path = _FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f'Fixture not found: {path}. '
            f'Create it under tests/fixtures/ before calling load_fixture().'
        )
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
