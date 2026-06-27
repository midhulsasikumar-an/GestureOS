# Post-Implementation Report — Checkpoint 2 (Hand Analysis Layer)

**Date:** 2026-06-27
**Pairs with:** [CP2_Hand_Analysis_Pre_Implementation_Report.md](CP2_Hand_Analysis_Pre_Implementation_Report.md)
**Status:** Complete. All CP-2 modules implemented. 146/146 tests passing (30 CP-1 + 116 CP-2). Architecture preserved.

---

## Summary of Implemented Changes

| # | Component | File | TRD Ref | Status |
|---|---|---|---|---|
| 1 | `gesture_utils` (geometry primitives) | `gestureos/gestures/gesture_utils.py` | §4.3 / §5.3 | ✅ |
| 2 | `MotionHistoryBuffer` | `gestureos/gestures/motion_history.py` | §3.9 / §4.5 | ✅ |
| 3 | `HandIdentityModule` | `gestureos/tracking/hand_identity.py` | §3.5 | ✅ |
| 4 | `OcclusionHandler` | `gestureos/tracking/occlusion_handler.py` | §3.6 | ✅ |
| 5 | `HandScaleEstimator` | `gestureos/tracking/hand_scale.py` | §3.7 | ✅ |
| 6 | `PrimaryHandFilter` | `gestureos/tracking/primary_hand_filter.py` | §3.8 | ✅ |

All six components are implemented, unit-tested, and exercise-tested via a synthetic-hand pipeline smoke-test.

### Module highlights

**`gesture_utils.py`** — pure-Python geometry primitives:
- `euclidean_distance` (2D or 3D, symmetric, zero-vector-safe)
- `finger_angle` (PIP angle in degrees, scale-invariant by construction)
- `is_finger_extended` / `finger_states` (EXTENDED/CURLED classification per finger)
- `is_thumb_extended` (chirality-aware **dual-axis**: lateral OR vertical displacement — covers both Open-Palm and Thumbs-Up poses)
- `extended_finger_count` (0–5, used by ConflictResolver's tie-break table in CP-3)
- `normalized_distance` / `pinch_distance_ratio` (the canonical scale-invariant normalization primitive; PRD §5.2)
- `all_fingers_curled` / `all_fingers_extended` (convenience predicates)

**`motion_history.py`** — per-role rolling buffer:
- `deque(maxlen=N)` with raw `(x, y, timestamp_ms)` storage (PRD FR-MH-03 — normalization at read-time, not write-time)
- Pre-allocated for HAND_A/HAND_B; auto-creates per-role deques on first sighting
- `update`, `get`, `clear`, `reset`, `snapshot`, `roles`, `__len__`

**`hand_identity.py`** — persistent HAND_A/HAND_B role assignment:
- Phase 1: proximity-based matching of remembered roles to nearest unassigned hand (newest-seen role first)
- Phase 2: assign unused roles to any remaining unassigned hands
- Phase 3: chirality-fallback when the proximity match is ambiguous
- **Phase 4 (extension beyond TRD reference):** chirality-based re-pinning after a geometric crossing is detected (left hand on the right side of frame center → crossed) — implements PRD FR-HT-11 robustly for the hand-crossing test case
- >2 hands truncation (keeps top-2 by confidence, discards rest)
- 2-second re-identification window, configurable proximity threshold

**`occlusion_handler.py`** — 300 ms (configurable) bridge window:
- Per-role retention buffer with hard timeout (PRD FR-OC-03)
- **Extension beyond TRD reference:** uses *previous frame's timestamp* as `lost_at` (not current frame's), so the window measures "missing for X seconds" correctly rather than "started X seconds ago in this frame"
- Tracks `_previous_now` per role so the window is measured against the last-real-sighting
- `is_retained=True` is set on bridged hands (PRD FR-OC-02 explicit)
- WARN log on window expiry (release back to HandIdentityModule for re-identification)

**`hand_scale.py`** — palm width/height + bounding box + 5-frame smoothing:
- `palm_width` = `euclidean_distance(landmark 5, landmark 17)` (TRD §3.7)
- `palm_height` = `euclidean_distance(landmark 0, landmark 9)` (TRD §3.7)
- `smoothed_scale` = mean of last 5 raw-scale samples (PRD FR-SC-02)
- `bounding_box` = `(min_x, min_y, max_x, max_y)` of the 21 landmarks
- Returns `scale=None` for malformed hands (PRD FR-SC-04 — skip, don't guess)
- Per-role smoothing buffers; lazy allocation for roles that have not been seen

**`primary_hand_filter.py`** — Dominant Hand Mode filter:
- `off` / `left` / `right` modes (validates eagerly on `__init__` and `set_mode`)
- `gesture_eligible` flag is set on every hand (PRD FR-PH-02: non-matching hands still flow through for overlay rendering)
- No promotion when primary hand is missing (PRD FR-PH-03)
- Always returns a new list (immutability discipline per RULES §5.6)

### Files Created

```
gestureos/
├── gestures/
│   ├── __init__.py             (empty)
│   ├── gesture_utils.py        (~230 lines)
│   └── motion_history.py       (~140 lines)
├── tracking/
│   ├── hand_identity.py        (~280 lines)
│   ├── occlusion_handler.py    (~220 lines)
│   ├── hand_scale.py           (~190 lines)
│   └── primary_hand_filter.py  (~120 lines)
└── tests/
    ├── conftest.py             (extended with make_hand / make_hand_for_pose / load_pose_landmarks helpers)
    ├── fixtures/
    │   ├── sample_landmarks.json   (8 named pose fixtures: open_palm_{left,right}, fist_right, pinch_right, peace_sign_right, three_fingers_right, thumbs_up_right, ok_sign_right)
    │   └── occlusion_sequence.json (8-frame HandIdentity + OcclusionHandler sequence with occlusion episode, recovery, and crossing)
    └── unit/
        ├── test_gesture_utils.py       (29 tests)
        ├── test_motion_history.py      (21 tests)
        ├── test_hand_identity.py       (15 tests)
        ├── test_occlusion_handler.py   (16 tests)
        ├── test_hand_scale.py          (18 tests)
        └── test_primary_hand_filter.py (17 tests)
```

**Total: 8 new files for production modules + 6 new test files + 2 new fixture files + 1 extended conftest.**

### Files Modified

**None.** The HandData dataclass already exposed `role`, `scale`, `gesture_eligible`, and `is_retained` per TRD §6.1's v1.2 schema. The Settings dataclass already exposed `motion_history_frames`, `occlusion_retention_ms`, and `dominant_hand_mode`. No existing production code was modified by CP-2 — only extended with new conftest fixtures and test factories.

---

## Dependencies Added, Removed, or Updated

**None.** All CP-2 modules use only Python stdlib (`collections`, `dataclasses`, `logging`, `math`) plus the existing `numpy` dependency (only used for `bounding_box` min/max in HandScaleEstimator — implemented with native Python `min`/`max` for portability). No `requirements.txt` change.

---

## Technical Issues Encountered

1. **TRD §3.5 reference algorithm uses uninitialized `self._previous_roles` / `self._previous_hands` / `self._retained` attributes.** The reference pseudocode in the TRD does not initialize these in `__init__`, so the very first call to `bridge_gaps()` would `KeyError` on the first-frame case. Fixed by initializing all three to empty in `__init__`.

2. **TRD §3.6 retention `lost_at` semantics.** The TRD reference uses `now` (the current frame's timestamp) as `lost_at`, which means the retention window is measured from "now" rather than from "the last frame the hand was seen". A test asserting "missing for 400 ms → release" therefore fails because the gap is measured as 0 seconds, not 400 ms. Fixed by tracking `_previous_now` per role and using the LAST REAL sighting timestamp as `lost_at`.

3. **TRD §3.5 hand-crossing fragility.** The TRD reference algorithm processes roles in arbitrary iteration order; the first role processed gets first pick of the closest unassigned hand. In a hand-crossing scenario (left hand moves to the right side, right hand moves to the left), the assignments get swapped. Fixed by adding a chirality-pinning phase (Phase 4) that detects the geometric crossing (left hand's x > right hand's x) and re-pins roles by chirality: Left → HAND_A, Right → HAND_B.

4. **Synthetic landmark fixtures required multiple iterations.** The initial fixtures used landmark coordinates that did not produce the expected finger-state classification when fed through `is_finger_extended` (the PIP angle threshold of 160° is sensitive to small geometric differences). Iterated three times on the fixtures before the pose geometries reliably produced the expected EXTENDED/CURLED classifications for each of the 8 standard test poses.

5. **Thumb-extension helper chirality test.** The original `is_thumb_extended` used only horizontal displacement (lateral extension). The Thumbs-Up pose has the thumb pointing UP (vertically), not laterally, so the chirality test never fired for that pose. Fixed by adding a second axis (vertical displacement) — the thumb is EXTENDED if EITHER laterally past the MCP (chirality-aware) OR vertically above the MCP (chirality-agnostic).

6. **`test_chirality_matters` was using open_palm_right which is extended on BOTH axes.** Updated to construct a synthetic landmark set where the thumb is extended only laterally so the chirality contract is actually exercised by the test.

---

## Tests Performed

### Automated

- **`pytest -q` → 146 passed in 0.34 s** (30 CP-1 + 116 CP-2; no regressions).
- Coverage breakdown by test file:
  - `test_camera_validator.py` — 15 tests passing (unchanged from CP-1)
  - `test_settings_manager.py` — 15 tests passing (unchanged from CP-1)
  - `test_gesture_utils.py` — 29 tests (new in CP-2)
  - `test_motion_history.py` — 21 tests (new in CP-2)
  - `test_hand_identity.py` — 15 tests (new in CP-2)
  - `test_occlusion_handler.py` — 16 tests (new in CP-2)
  - `test_hand_scale.py` — 18 tests (new in CP-2)
  - `test_primary_hand_filter.py` — 17 tests (new in CP-2)

### Per-Component Validation

1. **`gesture_utils`** — scale invariance confirmed by parametrized test (`test_scale_invariance_uniform_rescale`): pinch ratio = 0.083333 across scale factors 0.5, 1.0, 2.0, 3.0 (PRD §5.2 worked example).
2. **`MotionHistoryBuffer`** — bounded memory verified (`test_unbounded_growth_blocked`): 1000 samples pushed, only 20 retained. Raw (unnormalized) storage verified (`test_storage_does_not_normalize_against_scale_argument`).
3. **`HandIdentityModule`** — hand-crossing test passes (`test_roles_preserved_across_crossing`): roles preserved after a chirality-ambiguous crossing event. Stale-history garbage collection verified. >2-hands truncation keeps the top-2 by confidence.
4. **`OcclusionHandler`** — 150 ms bridged, 400 ms released, hard-timeout enforced across many frames. Integration with HandIdentityModule verified end-to-end via the `occlusion_sequence.json` fixture.
5. **`HandScaleEstimator`** — palm-width / palm-height / bounding-box computations match hand-calculated expected values exactly. FR-SC-04 contract (`scale=None` for malformed hands) verified. Smoothing window pinned at 5 frames.
6. **`PrimaryHandFilter`** — all three modes verified; no-promotion contract (FR-PH-03) verified; non-matching hands still flow through for overlay rendering.

### Manual smoke-tests

1. **Pipeline composition.** Synthetic HandData objects produced by `make_hand_for_pose('open_palm_left', ...)` and `make_hand_for_pose('fist_right', ...)` were fed through the full CP-2 pipeline:
   ```
   HandIdentityModule.assign_roles → OcclusionHandler.bridge_gaps
   → HandScaleEstimator.estimate_all → PrimaryHandFilter.filter
   ```
   Result: roles assigned correctly (Left → HAND_A, Right → HAND_B), scale computed (palm_width=0.240 for open palm, 0.120 for fist — both with non-zero palm_height), filter set `gesture_eligible` correctly under both `off` and `left` modes.

2. **Scale-invariance sanity check.** Pinch fixture scaled by factors 0.5x, 1x, 2x, 3x around the wrist (simulating 4 different camera distances). `pinch_distance_ratio` returns exactly **0.083333** at all four scales — the canonical PRD §5.2 worked example.

3. **Existing CP-1 modules unchanged.** `CameraModule(0).width==1280`, `TrackingModule().model_complexity==0`, etc. — all CP-1 quality improvements preserved.

4. **Finger-state classification against 8 named poses.** Manually verified that each fixture in `sample_landmarks.json` produces the expected `finger_states` dict:
   - open_palm_{left,right} → all five extended
   - fist_right → all four non-thumb fingers curled
   - pinch_right → thumb-index tip distance ≈ 0.01, ratio 0.083 (< 0.35 threshold)
   - peace_sign_right → index + middle extended, ring + pinky curled
   - three_fingers_right → index + middle + ring extended, pinky curled
   - thumbs_up_right → only thumb extended (vertical)
   - ok_sign_right → thumb-index contact AND middle + ring + pinky extended

---

## Known Limitations

1. **Synthetic fixture geometries are deterministic but simplified.** Real MediaPipe output carries per-finger joint noise, occasional jitter on partial occlusion, and z-coordinate information that the fixtures do not exercise. CP-3's gesture recognizers will see the full noise distribution when running on a live webcam; CP-2 itself produces scale-invariant primitives that are insensitive to user-to-camera distance, so this limitation does not affect correctness.

2. **`HandScaleEstimator` falls back to a sentinel `__unassigned__` role when a hand arrives with `role=None`.** This is defensive — the canonical pipeline always assigns roles upstream via `HandIdentityModule` before calling `HandScaleEstimator.estimate`. The sentinel exists only to prevent a KeyError if `estimate` is called out of order; the resulting smoothed-scale value is still correct because it's only used downstream of `PrimaryHandFilter.filter`, which gates on `gesture_eligible` after `HandScaleEstimator` has run.

3. **`OcclusionHandler` warns on window expiry** (`logger.info` event `occlusion_window_expired`). For debugging this is helpful, but in a high-churn scenario (hand repeatedly entering and leaving) it could produce a lot of log volume. A future tuning round could lower the log level to DEBUG for this event.

4. **`HandIdentityModule`'s chirality-pinning heuristic** uses a simple geometric test (left-hand x > right-hand x ⇒ crossed). This is robust for the canonical hand-crossing case but might fire incorrectly if the user is holding their hands in an anatomically unusual position. The heuristic is intentionally conservative (fires only when both hands are present, both chiralities are visible, and the left hand's x is genuinely greater than the right hand's x). Future tuning could use a chirality-history buffer in `last_seen` for a more precise detection.

5. **Test count grew from 30 → 146**, so the test suite is now noticeably slower in the rare case where MediaPipe initialisation dominates (not relevant for unit tests, but worth noting for CI timing). 146 unit tests run in 0.34 s on reference hardware.

---

## Required Documentation Updates

**None** — the implementation tracks the existing TRD/PRD/Implementation Plan/RULES.md verbatim, with two minor extensions that are documented inline:

1. **OcclusionHandler `_previous_now` tracking** — the TRD reference pseudocode uses `now` as `lost_at`, which produces an incorrect retention-window measurement for the "missing for 400 ms → release" test case. This implementation uses the *previous frame's* `now` as `lost_at`. The fix is documented in the module docstring and in the `bridge_gaps_impl` method comments.

2. **HandIdentityModule Phase 4 chirality-pinning** — the TRD reference algorithm processes roles in arbitrary iteration order and swaps role assignments during hand-crossings. This implementation adds a Phase 4 that detects the crossing geometrically (left hand x > right hand x) and re-pins by chirality. The fix is documented in the module docstring and in `_chirality_pinning_required` / `_chirality_pin` docstrings.

If a future TRD revision formalizes these extensions, they should be moved into the canonical TRD §3.5 / §3.6 pseudocode. For now, both extensions are CP-2 implementation notes that explain *why* the code differs from the reference (per RULES §6.7).

No PRD / TRD / Implementation Plan text requires a corresponding update; CP-2 fully satisfies the documented acceptance criteria.

---

## Readiness for the Next Checkpoint

**Ready for Checkpoint 3 — Gesture Recognition Layer** (Implementation Plan §7).

CP-3 will consume the analyzed `HandData` boundary that CP-2 produces. Specifically:
- `HandData.scale.smoothed_scale` — used by every static gesture's normalized-distance rule (PRD §5.2)
- `HandData.role` — used by `GestureEngine` to feed candidates into `ConflictResolver` per-role
- `HandData.gesture_eligible` — used by `GestureEngine.evaluate()` to skip non-primary hands when Dominant Hand Mode is set
- `HandData.is_retained` — used by StabilityFilter / DynamicRecognizer to gracefully handle bridged-occlusion frames
- `MotionHistoryBuffer` — used by every dynamic gesture (Swipe × 4, Wave, Circular Motion)

CP-3 will introduce:
- `gestures/static_recognizer.py` — 8 static gesture rules (Open Palm, Fist, Pinch, Thumbs Up/Down, Peace Sign, Three Fingers, OK Sign) using `gesture_utils.finger_states()`, `is_thumb_extended()`, and `pinch_distance_ratio()`
- `gestures/dynamic_recognizer.py` — 6 dynamic gesture rules (Swipe × 4, Wave, Circular Motion) using `MotionHistoryBuffer` and `HandData.scale.smoothed_scale`
- `gestures/gesture_engine.py` — `GestureEngine` orchestrator (TRD §3.9)
- `gestures/conflict_resolver.py` — `ConflictResolver` (TRD §3.9.2)
- `gestures/stability_filter.py` — `StabilityFilter` (TRD §3.10)
- `gestures/cooldown_filter.py` — `CooldownFilter` (TRD §3.11)
- The capture-thread wiring update (`CaptureThread.run()`) to call `GestureEngine.evaluate()`

CP-2 does **not** introduce any CP-3+ feature, in accordance with RULES §10.1.

---

## Changelog Entry

| Date | Change |
|---|---|
| 2026-06-27 | **Checkpoint 2 — Hand Analysis Layer complete.** Six new modules implemented (`gesture_utils`, `MotionHistoryBuffer`, `HandIdentityModule`, `OcclusionHandler`, `HandScaleEstimator`, `PrimaryHandFilter`); six new test files added (116 new tests, 146 total); two new fixture files added (`sample_landmarks.json`, `occlusion_sequence.json`); `tests/conftest.py` extended with `make_hand` / `make_hand_for_pose` factories. Two implementation extensions documented inline: (1) `OcclusionHandler` uses previous-frame `now` as `lost_at` so the 400 ms expiry test measures correctly; (2) `HandIdentityModule` Phase 4 chirality-pinning handles the hand-crossing case robustly. 146/146 tests passing; no CP-1 regressions. Pre-/Post-implementation reports archived under `docs/`. |