# Post-Implementation Report — Activation Gate Bugfix + Keyboard Shortcut

**Date:** 2026-07-25
**Branch:** `checkpoint_2`
**Based on:** CP4 Activation (Post) + two-hand hold-timer root-cause analysis

---

## Changes

### 1. `frame_feed_gestures()` in `gestureos/gestures/activation_gate.py` (new method)

Replaces the per-winner `for winner in winners: feed_gesture(...)` pattern with a single frame-level decision:

```python
def frame_feed_gestures(self, gesture_names: list[str], now: float) -> None
```

- Scans `gesture_names` for the first qualifying toggle gesture
- Feeds that one gesture via `_feed_gesture_impl` (unchanged hold logic)
- If no toggle gesture is found, resets the hold (non-qualifying frame per TRD §5.3)
- Follows existing hot-path discipline (try/except, never raises)
- Added `_frame_feed_gestures_impl` for testability

**Root cause fixed:** The old `for winner in winners:` loop reset the hold timer on the first winner (non-toggle `circular_motion`) then restarted it on the second winner (`open_palm`) — every frame. `frame_feed_gestures` makes one feed decision per frame regardless of winner count.

### 2. `capture_thread.py:534-538` (call site)

Replaced:
```python
for winner in winners:
    self._activation_gate.feed_gesture(winner.gesture_name, now)
```
With:
```python
self._activation_gate.frame_feed_gestures(
    [w.gesture_name for w in winners], now,
)
```

### 3. `test_pipeline_end_to_end.py` (mirror change)

- `Pipeline.tick()` updated to call `frame_feed_gestures` instead of the for-loop
- `test_gate_receives_names_while_stability_blocks_dispatch` updated to count `frame_feed_gestures` calls instead of `feed_gesture` calls

### 4. `core.py` — Ctrl+Alt+G keyboard listener

- Added `import pynput.keyboard` (already in `requirements.txt`)
- Added `_keyboard_listener`, `_ctrl_pressed`, `_alt_pressed` attributes
- `_on_key_press`/`_on_key_release` track modifier key state and call `self.activation_gate.toggle()` on Ctrl+Alt+G
- `_start_keyboard_listener()` starts a `pynput.keyboard.Listener` (daemon thread)
- Called from `start()` after `_wire_capture_signals()`
- `_stop_keyboard_listener()` stops the listener
- Called from `stop()` before capture thread shutdown

### 5. New unit tests in `test_activation_gate.py`

| Test | What it verifies |
|------|-----------------|
| `test_single_toggle_gesture_starts_hold` | One toggle starts hold |
| `test_multiple_winners_one_toggle` | Non-toggle + toggle feeds only toggle |
| `test_multiple_toggle_gestures_feeds_first` | Two toggles feeds first |
| `test_no_toggle_gesture_resets_hold` | Non-toggles reset in-progress hold |
| `test_empty_list_resets_hold` | Empty list resets hold |
| `test_two_hand_scenario_hold_reaches_toggle` | Exact bug reproduction: 90 frames of alternating non-toggle+toggle → gate toggles |
| `test_two_hand_single_hand_hold_still_works` | Single-hand case still works |
| `test_frame_feed_hot_path_never_raises` | Empty list doesn't crash |

## Deviations from Pre-Implementation Plan

- **Keyboard listener thread safety**: The `pynput` listener callbacks (`on_press`/`on_release`) may be called from the listener's internal thread. `_ctrl_pressed` and `_alt_pressed` are booleans (atomic writes in CPython), and `toggle()` is already thread-safe (single attribute writes). No additional synchronization needed.

## Test Results

```
701 passed in 3.91s
```

- 693 prior tests — all pass
- 8 new unit tests — all pass
- 1 previously-failing integration test (`test_gate_receives_names_while_stability_blocks_dispatch`) now passes

## Rollback

```bash
git checkout -- gestureos/gestures/activation_gate.py \
                 gestureos/app/capture_thread.py \
                 gestureos/app/core.py \
                 gestureos/tests/integration/test_pipeline_end_to_end.py \
                 gestureos/tests/unit/test_activation_gate.py
```
