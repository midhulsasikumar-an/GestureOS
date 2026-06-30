# Pre-Implementation Report — Checkpoint 4+ Tracking Stabilization Pass

**Date:** 2026-06-29
**Status:** Approved. All changes scoped to media/camera/tracking modules; no changes to GestureEngine, ConflictResolver, ActivationGate, or pipeline ordering.

---

## 1. Background and Motivation

CP-1's Post-Implementation Report identified that intermittent hand tracking
manifests as a hand "tracked one frame, gone the next". Two distinct causes
were confirmed by the CP-1 line-by-line pipeline comparison:

1. **`MODEL_COMPLEXITY = 0`** is intentional and works for steady-state
   detection at 1280×720. It is, however, the lighter, less accurate graph,
   and a single CP-1 finding notes that "complexity 0 is materially faster
   with comparable accuracy" — the *comparable* qualifier covers easy
   poses only. Under partial occlusion / wrist rotation the heavier
   `model_complexity = 1` graph (MediaPipe's documented default for ≤2 hands)
   retains tracking more reliably.

2. **Whole-frame loss on hand/handedness count mismatch** in
   `tracking/hand_detector.py:182-192`. When MediaPipe returns valid
   landmarks but no handedness metadata (a rare but documented internal
   state), the current code discards the entire frame's detections. The
   debug panel never shows why a frame went dark, and the operator has no
   signal that the cause is "chirality metadata missing" rather than
   "no hand in frame".

A third latent issue surfaced during the review: there is currently no
field in `HandData` for the per-hand tracking confidence. The debug
panel conflates detection and tracking into a single `hand.confidence`
field (line 351 of `overlay/debug_panel.py`). With the per-hand
diagnostic discipline now requested, we need to expose the tracking
state explicitly even when MediaPipe's API does not surface a separate
tracking score.

## 2. Goals and Non-Goals

### Goals (this pass)

- Raise MediaPipe tracking fidelity on partial-occlusion / rotated-hand
  scenarios without changing pipeline ordering.
- Eliminate whole-frame loss when landmarks are valid but handedness
  is missing or mismatched. Continue processing with `chirality=None`
  and log the event so future debug can attribute the loss.
- Surface per-hand tracking state to Developer Mode: hands detected,
  detection confidence, tracking confidence, hand status
  (`accepted` / `retained` / `filtered` / `discarded`), and discard
  reason.

### Non-Goals (deliberately out of scope)

- No changes to `GestureEngine`, `ConflictResolver`, `StabilityFilter`,
  `CooldownFilter`, or `ActivationGate`.
- No changes to pipeline ordering in `CaptureThread._run_gesture_pipeline`.
- No changes to chirality-fallback policy in `HandIdentityModule`.
- No addition of new Settings fields (per-hand status is read-only
  diagnostic state, not user-configurable).

## 3. Plan

### 3.1 `MODEL_COMPLEXITY = 1`

**File:** `gestureos/tracking/hand_detector.py`
**Change:** One constant. `MODEL_COMPLEXITY: int = 1` (was `0`).
**Docstring update:** explain rationale — heavier graph is the
MediaPipe-documented default for ≤2 hands; 1280×720 pixel density
absorbs the additional CPU cost; tracking under partial occlusion
and wrist rotation is materially more reliable.

**Validation:** Manual smoke-test that `TrackingModule().initialize()`
accepts `model_complexity=1` and that synthetic 1280×720 frames
process without error. Confirm the `mediapipe_initialized` log line
emits `model_complexity=1`.

### 3.2 Graceful handedness-mismatch path

**File:** `gestureos/tracking/hand_detector.py`
**Change:** Replace the count-mismatch whole-frame discard at
lines 182-192 with a per-hand pass that:

1. Iterates over `results.multi_hand_landmarks` directly.
2. If `multi_handedness` is `None` or has fewer entries than the
   landmarks list, emits each hand with `chirality=None` and
   `confidence=0.0`.
3. If `multi_handedness` has more entries than the landmarks list,
   iterates the shorter list and logs the mismatch.
4. Logs the event (`mediapipe_hand_count_mismatch`) at WARN level
   with the per-list counts.

**Effect on downstream:** `HandIdentityModule.assign_roles()` already
handles `chirality=None` correctly — it falls back to proximity-only
matching in Phase 1, then Phase 2, then Phase 3 (chirality fallback,
which gracefully no-ops when neither chirality is present), then
Phase 4 (chirality re-pin, also a no-op without chiralities). The
identity path stays alive.

`OcclusionHandler` and `HandScaleEstimator` are chirality-agnostic.
`PrimaryHandFilter` is the only place chirality is consumed downstream
of identity. When `dominant_hand_mode` is `off` (the default), the
filter sets `gesture_eligible=True` for every hand regardless of
chirality, so a `chirality=None` hand remains eligible. When the
operator has explicitly chosen a dominant-hand mode, the missing
chirality is treated as a "this is not the primary hand" condition
and `gesture_eligible=False` is set — which is exactly the behaviour
we want (an unidentified hand should not be promoted to primary on
its own).

### 3.3 Hand status surface

**Files:**
- `gestureos/models/data_models.py` — extend `HandData` with
  `tracking_confidence: float | None = None` (only when MediaPipe
  exposes a per-hand score) and `status: str = 'accepted'` and
  `status_reason: str | None = None` for the diagnostic state.
- `gestureos/tracking/hand_detector.py` — populate the new fields.
- `gestureos/tracking/hand_identity.py` — set `status='retained'`
  on bridged hands (retained copy keeps its own status flag).
- `gestureos/tracking/primary_hand_filter.py` — set
  `status='filtered'` and `status_reason='dominant_hand_mode'` on
  the non-matching hand.
- `gestureos/tracking/occlusion_handler.py` — set
  `status='retained'` and `status_reason='occlusion_bridge'`.
- `gestureos/overlay/debug_panel.py` — render the new fields.
- `gestureos/overlay/overlay_window.py` — pass the same gesture
  state shape (no change required; per-hand data is on the
  HandData list, not on the gesture state).

**Status enum:**
```
'accepted'   — hand passed the pipeline
'retained'   — hand is from the OcclusionHandler bridge
'filtered'   — hand was demoted by PrimaryHandFilter
'discarded'  — hand was rejected by TrackingModule (hand_count_mismatch path)
```

### 3.4 HandData dataclass change — backward-compat

The two new fields have defaults, so existing constructors and
factories continue to work. `dataclasses.replace()` will pick up the
defaults automatically. Tests that construct `HandData` literally
(e.g., `HandData(landmarks=..., chirality=..., confidence=...)`)
keep compiling.

## 4. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `MODEL_COMPLEXITY = 1` regresses FPS on reference hardware | The CP-1 Post report noted "25 FPS with one hand, ≥ 22 with two hands" — the heavier model costs ≈ 5–8 ms at 720p. The cap of 30 FPS is well above the application's actual rendering pace. We log measured FPS per the existing `capture_thread` debug line and a manual smoke-test verifies the value. |
| `chirality=None` hands break `HandIdentityModule` chirality-pinning | `HandIdentityModule` already tolerates `chirality != 'Left'` and `!= 'Right'` — Phase 1 and Phase 2 are chirality-agnostic. Phase 4 (`_chirality_pinning_required`) explicitly returns `False` when `chiralities != ['Left', 'Right']`. |
| New HandData fields break `dataclasses.replace` callers | All new fields have defaults. `dataclasses.replace()` is the standard mechanism; callers that pass only `landmarks/chirality/confidence` continue to work. |
| The `status` field is duplicated with `is_retained` / `gesture_eligible` | They are intentionally separate: `is_retained` and `gesture_eligible` are pipeline-side flags with semantic content (control flow), while `status` is a diagnostic enum. Operator can read both and they don't conflict. |
| The MediaPipe 0.10.14 API does not expose a separate tracking score | The per-hand `handedness.classification[0].score` is the only score surfaced. We populate `detection_confidence = hand.confidence` and set `tracking_confidence = None` (with a "(not exposed by MediaPipe 0.10.14)" note in the panel). A future MediaPipe upgrade that exposes a separate tracking field can populate it without a dataclass change. |

## 5. Tests

### Existing tests to verify

- `tests/unit/test_hand_identity.py` — 15 tests; must remain green
  (chirality-agnostic contract is preserved).
- `tests/unit/test_occlusion_handler.py` — 16 tests; must remain green.
- `tests/unit/test_primary_hand_filter.py` — 17 tests; must remain green.
- `tests/unit/test_debug_panel.py` — 30+ tests; must remain green
  (panel still renders with the new fields).
- `tests/integration/test_pipeline_end_to_end.py` — must remain green.

### New tests

- `tests/unit/test_hand_detector.py` — new file. Unit tests for
  `TrackingModule.detect()` against a fake MediaPipe results object
  (mocked). Verifies:
  - `MODEL_COMPLEXITY` constant is `1`.
  - Whole-frame count-mismatch path produces hands with
    `chirality=None` instead of dropping the frame.
  - Per-hand status is set to `'accepted'` or `'discarded'` correctly.
  - Malformed hand (≠21 landmarks) is still dropped with the
    existing `malformed_hand_discarded` log event.
- `tests/unit/test_debug_panel.py` — extend with cases that:
  - Render a hand with `status='accepted'` and verify the panel
    runs without error.
  - Render a hand with `status='retained'` and `'filtered'`.
  - Render a hand with `status='discarded'` and a `status_reason`.
  - Render a hand with `tracking_confidence=None` and verify the
    panel does not crash.

## 6. Performance Validation

- Run the full test suite (currently 404 tests) and confirm green.
- Run a manual smoke-test of `TrackingModule().initialize()` against
  the real `mediapipe 0.10.14` and confirm `model_complexity=1`
  appears in the `mediapipe_initialized` log line.
- The hot path is unchanged: `TrackingModule.detect()` is still O(N)
  per hand and the new `status` field is a single string assignment
  per hand. `HandData` grows by 3 fields (~80 bytes per hand). At
  30 FPS × 2 hands × 80 bytes = 4.8 KB/sec — negligible.

## 7. Files Touched

```
gestureos/models/data_models.py          (HandData: +3 fields, all with defaults)
gestureos/tracking/hand_detector.py      (MODEL_COMPLEXITY=1, mismatch path, status)
gestureos/tracking/hand_identity.py      (status='retained' on bridged hands)
gestureos/tracking/occlusion_handler.py  (status='retained' + reason on bridged copies)
gestureos/tracking/primary_hand_filter.py (status='filtered' + reason on demoted)
gestureos/overlay/debug_panel.py         (render new fields)
gestureos/tests/unit/test_hand_detector.py    (new)
gestureos/tests/unit/test_debug_panel.py      (extend)
docs/CP4_Tracking_Stabilization_Pre_Implementation_Report.md   (this file)
docs/CP4_Tracking_Stabilization_Post_Implementation_Report.md  (after the work)
```

No changes to: `GestureEngine`, `ConflictResolver`, `StabilityFilter`,
`CooldownFilter`, `ActivationGate`, `CaptureThread._run_gesture_pipeline`
ordering, or any Settings field.

## 8. Approval Gate

This is the Pre-Implementation Report. No production code or test
changes will be made until this report is reviewed. On approval the
implementation proceeds section-by-section as listed in §7.
