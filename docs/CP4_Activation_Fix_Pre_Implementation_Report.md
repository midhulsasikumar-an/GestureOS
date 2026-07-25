# Pre-Implementation Report — Activation Gate Bugfix + Keyboard Shortcut

**Date:** 2026-07-25
**Branch:** `checkpoint_2`
**Based on:** Post-Implementation Report (CP4)

---

## Root Cause

Per log analysis, `capture_thread.py:537` iterates `for winner in winners:` which produces up to 2 winners per frame (one per hand role). When HAND_A=`circular_motion` and HAND_B=`open_palm`:

1. First `feed_gesture('circular_motion')` → non-toggle → resets hold (`_hold_start = None`)
2. Second `feed_gesture('open_palm')` → starts new hold at current timestamp
3. Next frame repeats step 1 → timer never reaches 1.0s

Single-hand scenario works correctly because there is only one winner per frame.

## Fix: `frame_feed_gestures(gesture_names, now)`

Replace the per-winner for-loop with a single frame-level call:
- Scan all winners for the first qualifying toggle gesture
- Feed that one gesture (if found)
- If no toggle gesture is found across all winners, reset the hold (non-qualifying frame)

**Why this works:** The hold timer only needs to know "is the user performing a qualifying gesture this frame?" — not "which hand is doing it." A single feed per frame prevents the multi-hand interleaving that resets the timer.

**Existing behavior preserved:** Single-hand path is unchanged (same `_feed_gesture_impl` logic). Hold timing, cooldown, two-hand support, and toggle semantics are all preserved.

## Keyboard Shortcut: Ctrl+Alt+G

Use `pynput.keyboard.Listener` (already in `requirements.txt`, v1.7.7) to call `ActivationGate.toggle()` from a background listener thread. Per ActivationGate thread-safety rationale from CP4: single-attribute writes are atomic in CPython, safe cross-thread.

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `frame_feed_gestures` breaks existing single-hand toggle | Very Low | Implementation delegates to `_feed_gesture_impl` unchanged |
| `pynput` listener blocks on Windows | Low | Listener runs on daemon thread; `stop()` called on app shutdown |
| Two-hand setup still doesn't toggle | Very Low | Bug is reproducible in unit tests; same logic proven by log analysis |
| Keyboard shortcut fires when app doesn't have focus | Unchanged from design | Acceptable per PRD §7.3 (system-wide shortcut is intentional) |

## Test Plan

### Unit tests (`test_activation_gate.py`)
1. `test_frame_feed_single_toggle_gesture` — list with one toggle gesture starts hold
2. `test_frame_feed_multiple_winners_one_toggle` — list with non-toggle + toggle feeds only toggle
3. `test_frame_feed_no_toggle_gesture_resets_hold` — list of non-toggles resets hold
4. `test_frame_feed_empty_list_resets_hold` — empty list resets hold
5. `test_frame_feed_two_hand_scenario` — reproduces exact bug scenario: alternating non-toggle + open_palm per frame across 60 frames → gate toggles active

### Integration test (`test_pipeline_end_to_end.py`)
- Update `Pipeline.tick()` to call `frame_feed_gestures()` instead of the for-loop (mirrors production change)

### Keyboard shortcut test (manual)
- The `toggle()` method is already unit-tested. The listener wiring is a separate concern that requires an actual keyboard; covered by `test_toggle_flips_state` and `test_toggle_clears_in_progress_hold`.
