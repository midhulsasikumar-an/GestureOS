"""pytest fixtures and shared test helpers for GestureOS.

Checkpoint 0 scaffold — extended at Checkpoint 2 with the canonical
test-hand and test-landmarks factories used by every CP-2 test file.

Per AI Development Guide §9.1 / TRD §13.2: fixtures are loaded from
JSON under tests/fixtures/, never hardcoded inline across multiple files.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

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


# ---------------------------------------------------------------------------
# Checkpoint 2 test factories
# ---------------------------------------------------------------------------
#
# These helpers produce a minimal valid `HandData` from a wrist position
# (and optional chirality/landmarks). They are deliberately lightweight:
# they do not require a real MediaPipe inference pass, so CP-2 unit tests
# can run without a camera (TRD §13.2).
#
# Conventions:
#   - Default chirality is 'Right' (the more common test chirality).
#   - Default confidence is 1.0 (caller can override).
#   - `role` is left as None unless the caller passes one — HandIdentityModule
#     tests pass a `role=None` input by default, which is the contract
#     TrackingModule emits.
#   - 21-landmark arrays can be either passed explicitly or built from a
#     wrist position via `make_landmarks_from_wrist` (default = a synthetic
#     open-palm-ish hand at the given wrist; rarely needed for CP-2 tests
#     which usually pass landmarks= directly from sample_landmarks.json).

def make_landmarks(
    base: list[tuple[float, float, float]] | None = None,
) -> list[tuple[float, float, float]]:
    """Return a 21-landmark list suitable for HandData.landmarks.

    If `base` is provided, it must already contain 21 entries and is
    returned as a list-of-tuples (JSON loads give lists). Otherwise a
    synthetic flat hand at the wrist is built — used only by tests
    that do not care about specific landmark geometry (e.g., identity-
    tracking tests that only inspect `landmarks[0]`).
    """
    if base is None:
        # Synthetic flat hand: wrist at (0.5, 0.5, 0), all other
        # landmarks stacked just above the wrist. Useful for tests
        # that don't depend on per-finger geometry.
        base = [[0.5, 0.5 - i * 0.005, 0.0] for i in range(21)]
    out: list[tuple[float, float, float]] = []
    for lm in base:
        if len(lm) >= 3:
            out.append((float(lm[0]), float(lm[1]), float(lm[2])))
        else:
            out.append((float(lm[0]), float(lm[1]), 0.0))
    if len(out) != 21:
        raise ValueError(
            f'make_landmarks: expected 21 landmarks, got {len(out)}'
        )
    return out


def make_hand(
    wrist: tuple[float, float] | tuple[float, float, float] = (0.5, 0.5),
    chirality: str = 'Right',
    confidence: float = 1.0,
    role: str | None = None,
    landmarks: list[tuple[float, float, float]] | None = None,
    **overrides: Any,
):
    """Construct a HandData with sensible defaults for tests.

    Imports HandData lazily so this conftest stays importable even
    when the models module is being refactored.
    """
    from models.data_models import HandData

    if landmarks is None:
        # Build a 21-landmark list with wrist at the requested position.
        # The remaining 20 landmarks are placed just above the wrist
        # (smaller y) so the hand "points up" — this matters for the
        # chirality-aware thumb extension test, which needs non-zero
        # vertical spread.
        wx, wy = wrist[0], wrist[1]
        landmarks = [(wx, wy, 0.0)] + [
            (wx + 0.01 * (i % 3 - 1), wy - 0.02 * (i // 3 + 1), 0.0)
            for i in range(20)
        ]
    else:
        landmarks = make_landmarks(landmarks)

    base = HandData(
        landmarks=landmarks,
        chirality=chirality,
        confidence=confidence,
        role=role,
    )
    if overrides:
        base = replace(base, **overrides)
    return base


def load_pose_landmarks(pose_name: str) -> list[tuple[float, float, float]]:
    """Load a named pose's 21-landmark list from sample_landmarks.json.

    Args:
        pose_name: key into sample_landmarks.json, e.g. 'open_palm_right'.
    """
    data = load_fixture('sample_landmarks.json')
    if pose_name not in data:
        raise KeyError(
            f'pose {pose_name!r} not found in sample_landmarks.json. '
            f'Available: {sorted(k for k in data.keys() if not k.startswith("_"))}'
        )
    raw = data[pose_name]
    return make_landmarks(raw)


def make_hand_for_pose(
    pose_name: str,
    chirality: str = 'Right',
    confidence: float = 1.0,
    role: str | None = None,
    wrist_offset: tuple[float, float] = (0.0, 0.0),
    **overrides: Any,
):
    """Build a HandData pre-loaded with a named pose's landmarks.

    `wrist_offset` translates the entire landmark set (useful for
    scale-invariance tests that vary the camera distance).
    """
    landmarks = load_pose_landmarks(pose_name)
    if wrist_offset != (0.0, 0.0):
        ox, oy = wrist_offset
        landmarks = [
            (lm[0] + ox, lm[1] + oy, lm[2]) for lm in landmarks
        ]
    return make_hand(
        wrist=(landmarks[0][0], landmarks[0][1]),
        chirality=chirality,
        confidence=confidence,
        role=role,
        landmarks=landmarks,
        **overrides,
    )


def make_wrist_only_hand(
    wrist: tuple[float, float],
    chirality: str = 'Right',
    confidence: float = 1.0,
    role: str | None = None,
):
    """Convenience: build a hand whose landmarks[0] is the given wrist.

    Used by HandIdentityModule tests that only care about wrist
    position, not per-finger geometry.
    """
    return make_hand(
        wrist=wrist,
        chirality=chirality,
        confidence=confidence,
        role=role,
    )


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_landmarks() -> dict:
    """All pose fixtures from sample_landmarks.json."""
    return load_fixture('sample_landmarks.json')


@pytest.fixture
def occlusion_sequence() -> list[dict]:
    """The frame sequence from occlusion_sequence.json."""
    return load_fixture('occlusion_sequence.json')['frames']