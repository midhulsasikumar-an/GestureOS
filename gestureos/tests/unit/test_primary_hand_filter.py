"""Unit tests for PrimaryHandFilter — CP-2.

Per TRD §13.2: no live camera required. Tests verify the three
Dominant Hand Mode values (`off` / `left` / `right`) and the
no-promotion contract (PRD FR-PH-03) when the designated primary
hand is missing.
"""

from __future__ import annotations

import pytest

from tracking.primary_hand_filter import (
    MODE_LEFT,
    MODE_OFF,
    MODE_RIGHT,
    PrimaryHandFilter,
)

from tests.conftest import make_wrist_only_hand


# ======================================================================
# Construction / validation
# ======================================================================

class TestConstruction:
    def test_default_mode_is_off(self) -> None:
        f = PrimaryHandFilter()
        assert f.mode == MODE_OFF

    def test_invalid_mode_raises_at_construction(self) -> None:
        with pytest.raises(ValueError):
            PrimaryHandFilter(dominant_hand_mode='both')

    def test_set_mode_validates(self) -> None:
        f = PrimaryHandFilter()
        with pytest.raises(ValueError):
            f.set_mode('both')

    def test_set_mode_updates(self) -> None:
        f = PrimaryHandFilter()
        f.set_mode(MODE_LEFT)
        assert f.mode == MODE_LEFT


# ======================================================================
# off: all hands eligible
# ======================================================================

class TestOffMode:
    def test_all_hands_eligible(self) -> None:
        f = PrimaryHandFilter(MODE_OFF)
        hands = [
            make_wrist_only_hand((0.2, 0.5), chirality='Left'),
            make_wrist_only_hand((0.8, 0.5), chirality='Right'),
        ]
        out = f.filter(hands)
        assert all(h.gesture_eligible for h in out)

    def test_off_returns_new_list(self) -> None:
        # Even in `off` mode the filter must return a new list, not
        # mutate the input (immutability discipline).
        f = PrimaryHandFilter(MODE_OFF)
        hands = [make_wrist_only_hand((0.5, 0.5), chirality='Right')]
        out = f.filter(hands)
        assert out is not hands
        assert hands[0].gesture_eligible is True  # input unchanged


# ======================================================================
# left: only Left eligible
# ======================================================================

class TestLeftMode:
    def test_left_hand_eligible(self) -> None:
        f = PrimaryHandFilter(MODE_LEFT)
        out = f.filter([
            make_wrist_only_hand((0.2, 0.5), chirality='Left'),
        ])
        assert out[0].gesture_eligible is True

    def test_right_hand_excluded(self) -> None:
        # PRD FR-PH-02: non-matching hands are still rendered (i.e.,
        # still in the output list) but gesture_eligible=False.
        f = PrimaryHandFilter(MODE_LEFT)
        out = f.filter([
            make_wrist_only_hand((0.8, 0.5), chirality='Right'),
        ])
        assert len(out) == 1
        assert out[0].gesture_eligible is False
        assert out[0].chirality == 'Right'

    def test_mixed_only_left_eligible(self) -> None:
        f = PrimaryHandFilter(MODE_LEFT)
        out = f.filter([
            make_wrist_only_hand((0.2, 0.5), chirality='Left'),
            make_wrist_only_hand((0.8, 0.5), chirality='Right'),
        ])
        eligible = {h.chirality for h in out if h.gesture_eligible}
        not_eligible = {h.chirality for h in out if not h.gesture_eligible}
        assert eligible == {'Left'}
        assert not_eligible == {'Right'}


# ======================================================================
# right: only Right eligible (mirror of left)
# ======================================================================

class TestRightMode:
    def test_right_hand_eligible(self) -> None:
        f = PrimaryHandFilter(MODE_RIGHT)
        out = f.filter([
            make_wrist_only_hand((0.8, 0.5), chirality='Right'),
        ])
        assert out[0].gesture_eligible is True

    def test_left_hand_excluded(self) -> None:
        f = PrimaryHandFilter(MODE_RIGHT)
        out = f.filter([
            make_wrist_only_hand((0.2, 0.5), chirality='Left'),
        ])
        assert len(out) == 1
        assert out[0].gesture_eligible is False

    def test_mixed_only_right_eligible(self) -> None:
        f = PrimaryHandFilter(MODE_RIGHT)
        out = f.filter([
            make_wrist_only_hand((0.2, 0.5), chirality='Left'),
            make_wrist_only_hand((0.8, 0.5), chirality='Right'),
        ])
        eligible = {h.chirality for h in out if h.gesture_eligible}
        not_eligible = {h.chirality for h in out if not h.gesture_eligible}
        assert eligible == {'Right'}
        assert not_eligible == {'Left'}


# ======================================================================
# No promotion when primary hand is missing (PRD FR-PH-03)
# ======================================================================

class TestNoPromotion:
    def test_no_hands_no_promotion(self) -> None:
        f = PrimaryHandFilter(MODE_LEFT)
        out = f.filter([])
        assert out == []

    def test_wrong_chirality_present_no_promotion(self) -> None:
        # PRD FR-PH-03: if the designated primary hand is absent, the
        # secondary hand is NOT promoted. In this test, MODE_LEFT is
        # set but only the RIGHT hand is present -> no eligible hands.
        f = PrimaryHandFilter(MODE_LEFT)
        out = f.filter([
            make_wrist_only_hand((0.8, 0.5), chirality='Right'),
        ])
        assert len(out) == 1
        assert out[0].gesture_eligible is False


# ======================================================================
# Constants
# ======================================================================

class TestConstants:
    def test_mode_constants_pinned(self) -> None:
        # Pin the public mode strings — they appear in Settings.json
        # and the operator-facing UI; renaming them is a breaking change.
        assert MODE_OFF == 'off'
        assert MODE_LEFT == 'left'
        assert MODE_RIGHT == 'right'