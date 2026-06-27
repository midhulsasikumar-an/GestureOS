# Pre-Implementation Report — Checkpoint 2 (Hand Analysis Layer)

**Date:** 2026-06-27
**Scope:** Implement the Hand Analysis Layer per Implementation Plan §6.
**Architectural stance:** Build only CP-2's six in-scope modules. No gesture-rule logic (CP-3), no activation gating (CP-4), no action dispatch (CP-5), no context engine (CP-6), no UI/overlay extension (CP-8).

---

## Objective

Build every component that transforms raw MediaPipe landmarks into the analyzed, normalized data that gesture recognition (CP-3) will consume. Per Implementation Plan §6:

> Build every component that transforms raw MediaPipe landmarks into the analyzed, normalized data that gesture recognition will consume: finger states, finger/joint angles, normalized distances, hand scale estimation, velocity/motion history, and persistent hand identity. […] This is where the scale-invariance requirement (PRD §5) becomes load-bearing infrastructure: no gesture rule in Checkpoint 3 can be correctly implemented until `HandData.scale` exists and is trustworthy.

The data boundary produced by this checkpoint is a fully-populated `HandData` (with `role`, `scale`, `gesture_eligible`, and `is_retained` set correctly), which is the contract CP-3 consumes.

---

## Current Checkpoint

**Checkpoint 2 — Hand Analysis Layer** (Implementation Plan §6; PRD §8.1.1, §8.1.2, §8.1.3, §6, §8.5; TRD §3.5, §3.6, §3.7, §3.8, §3.9/§4.5).

Checkpoint 1 is **Done**: 30/30 unit tests passing; the CP-1 tracking-quality hardening (camera resolution, MediaPipe config, RGB buffer reuse) is in place.

---

## Files to be Created

### Production modules (6)

| File | TRD Ref | Responsibility |
|---|---|---|
| `gestureos/tracking/hand_identity.py` | §3.5 | `HandIdentityModule`: persistent `HAND_A`/`HAND_B` role assignment, 2 s re-identification window, proximity-based matching, chirality-fallback tie-breaking. |
| `gestureos/tracking/occlusion_handler.py` | §3.6 | `OcclusionHandler`: 300 ms (configurable) retention of last-known `HandData` for a missing role, releasing the role back to `HandIdentityModule` if detection does not recover. |
| `gestureos/tracking/hand_scale.py` | §3.7 | `HandScaleEstimator`: palm width/height, bounding box, 5-frame smoothed scale; populates `HandData.scale`. |
| `gestureos/tracking/primary_hand_filter.py` | §3.8 | `PrimaryHandFilter`: Dominant-Hand-Mode filter (`off`/`left`/`right`); sets `gesture_eligible` flag. |
| `gestureos/gestures/motion_history.py` | §3.9/§4.5 | `MotionHistoryBuffer`: per-role `(x, y, timestamp_ms)` rolling buffer with raw (unnormalized) storage (normalization happens at read-time per FR-MH-03). |
| `gestureos/gestures/gesture_utils.py` | §4.3/§5.3 | `euclidean_distance()`, `finger_angle()`, `finger_states()`, plus a thumb-extension helper that uses chirality-aware horizontal displacement (per TRD §4.3's `is_thumb_extended` note). |

### Tests (6)

| File | Mirrors | Coverage target |
|---|---|---|
| `gestureos/tests/unit/test_hand_identity.py` | `tracking/hand_identity.py` | Roles preserved across crossing; stale history cleared; chirality fallback; >2 hands ⇒ keep top 2 by confidence. |
| `gestureos/tests/unit/test_occlusion_handler.py` | `tracking/occlusion_handler.py` | 150 ms occlusion bridged; 400 ms occlusion released; release clears retained buffer; `is_retained=True` is set on bridged hands. |
| `gestureos/tests/unit/test_hand_scale.py` | `tracking/hand_scale.py` | Palm width/height computed correctly; bbox computed correctly; 5-frame smoothing produces stable value under rotation; malformed-hand ⇒ `scale=None` (FR-SC-04). |
| `gestureos/tests/unit/test_primary_hand_filter.py` | `tracking/primary_hand_filter.py` | `off` ⇒ all eligible; `left` ⇒ only Left; `right` ⇒ only Right; missing primary ⇒ no promotion (FR-PH-03). |
| `gestureos/tests/unit/test_motion_history.py` | `gestures/motion_history.py` | FIFO eviction beyond capacity; raw (unnormalized) storage confirmed (FR-MH-03); independent per role; `clear()` empties a role. |
| `gestureos/tests/unit/test_gesture_utils.py` | `gestures/gesture_utils.py` | `euclidean_distance` correctness; `finger_angle` correctly identifies straight vs bent; `finger_states` EXTENDED/CURLED classification; chirality-aware thumb helper. |

### Fixtures (2)

| File | Purpose |
|---|---|
| `gestureos/tests/fixtures/sample_landmarks.json` | Known-good 21-landmark sets for the standard test poses (open_palm_left, open_palm_right, fist, pinch, peace_sign, three_fingers, ok_sign, thumbs_up, thumbs_down). Used by gesture_utils + scale tests. |
| `gestureos/tests/fixtures/occlusion_sequence.json` | A frame sequence that exercises HandIdentity + OcclusionHandler together (per TRD §13's example pattern). |

### Files to be modified

- `gestureos/tests/conftest.py` — extend the existing fixture loader helpers to expose `make_hand(...)` and `make_landmarks(...)` test factories (one per the AI Dev Guide §9.1 rule that "fixtures are loaded from JSON under tests/fixtures/, never hardcoded inline across multiple files").

**No edits to:**
- `gestureos/models/data_models.py` — `HandData` already exposes `role`, `scale`, `gesture_eligible`, `is_retained` per TRD §6.1's v1.2 schema (verified). No change required.
- `gestureos/settings/settings_manager.py` — `motion_history_frames`, `occlusion_retention_ms`, `dominant_hand_mode` already present in the `Settings` dataclass and validator (verified). No change required.
- `gestureos/tracking/hand_detector.py`, `gestureos/camera/camera_module.py`, `gestureos/app/capture_thread.py`, `gestureos/app/core.py` — CP-1 modules, unchanged.
- `gestureos/overlay/`, `gestureos/diagnostics/`, `gestureos/app/` — out of CP-2 scope.

---

## PRD References

CP-2 implements the following PRD requirements:

- **FR-HT-08 / FR-HT-09 / FR-HT-10 / FR-HT-11 / FR-HT-12** (Hand Identity)
- **FR-OC-01 / FR-OC-02 / FR-OC-03** (Temporary Occlusion Handling)
- **FR-PH-01 / FR-PH-02 / FR-PH-03** (Primary Hand Selection / Dominant Hand Mode)
- **FR-SC-01 / FR-SC-02 / FR-SC-03 / FR-SC-04** (Hand Scale Estimation; FR-SC-04 = "skip, don't guess" contract)
- **FR-MH-01 / FR-MH-02 / FR-MH-03 / FR-MH-04** (Motion History Buffer; FR-MH-03 = "normalize at read time, not at write time")

CP-2 does **not** introduce any requirement from later checkpoints (no FR-MS-*, no FR-GS-*, no FR-CD-*, no FR-CR-*, no FR-AT-*, no FR-AC-*, no FR-CA-*).

---

## TRD References

| Component | TRD section | Inputs | Outputs |
|---|---|---|---|
| `HandIdentityModule` | §3.5 | `list[HandData]` (role=None), `now: float` | `list[HandData]` (role populated) |
| `OcclusionHandler` | §3.6 | current `list[HandData]` (post-identity), `now: float` | `list[HandData]` (real or bridged with `is_retained=True`) |
| `HandScaleEstimator` | §3.7 | one `HandData` | same `HandData` with `scale=HandScale(...)` populated |
| `PrimaryHandFilter` | §3.8 | `list[HandData]` (post-scale), `mode: str` | `list[HandData]` (gesture_eligible flag set per hand) |
| `MotionHistoryBuffer` | §3.9 / §4.5 | `update(role, wrist_pos, now)`, `get(role)`, `clear(role)` | rolling buffer of `(x, y, timestamp_ms)` |
| `gesture_utils` | §4.3 / §5.3 | pure-Python helpers | numeric results + per-finger state dict |

---

## Dependencies

**No new dependencies.** All modules are pure Python (NumPy is already a dependency and is used only optionally; `math.atan2`/`math.hypot` cover the geometry). No `requirements.txt` change.

Optional NumPy usage is deferred to `HandScaleEstimator`'s bounding-box min/max (where it is convenient but not required) — keeping the modules dependency-light supports future testing portability.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hand-crossing re-identification failure | Medium | TRD §3.5's proximity-threshold (`MATCH_THRESHOLD = 0.15`) is explicitly tested with the PRD §8.1.1 crossing example. |
| Occlusion retention masks a genuinely lost hand indefinitely | Low | Hard 300 ms timeout is enforced and explicitly tested (`test_occlusion_window_expires`). Window is configurable via `occlusion_retention_ms` from `Settings`. |
| Scale-estimation noise destabilizes downstream rules | Medium | 5-frame moving-average smoothing is mandated by TRD §3.7 and FR-SC-02. Test `test_hand_scale_smoothed_under_rotation` exercises the smoothing path with a synthetic rotating-hand sequence. |
| Thumb-extension helper is incorrectly chirality-mirrored | Medium | The thumb helper uses `x`-displacement relative to a reference (MCP) joint rather than naive sign-comparison, exactly as TRD §4.3 specifies. Test `test_thumb_extension_uses_chirality` covers both chiralities. |
| `MotionHistoryBuffer` stores pre-normalized data, corrupting mid-buffer scale drift | Low | Storage path stores raw `(x, y)` only; normalization is computed at read-time. Test `test_motion_history_stores_raw_unnormalized` pins this contract. |
| `OcclusionHandler` retains a hand after role mismatch | Low | TRD §3.6 algorithm uses *role* as the key; if `HandIdentityModule` has reassigned the role, the retained entry is keyed to the old role and does not collide with the new role's data. Test `test_occlusion_does_not_collide_after_role_swap` covers this. |
| `MotionHistoryBuffer` unbounded growth | None | `deque(maxlen=N)` is bounded. Test `test_motion_history_evicts_oldest` pins this. |

---

## Validation Strategy

1. **Unit tests.** Per TRD §13.2 / §13.3, every component is unit-tested with synthetic data (no live camera). The Implementation Plan §6 Testing Strategy section gives the canonical tests; this report generalizes the same discipline to the new fixtures.
2. **Acceptance criteria (Implementation Plan §6):**
   - Scale estimate matches hand-calculated expected values within floating-point tolerance for known-good fixture landmarks.
   - Hand-crossing sequence preserves `HAND_A`/`HAND_B` roles.
   - 150 ms occlusion is bridged; 400 ms occlusion is released.
   - Dominant-Hand-Mode "left" excludes a right-hand from `gesture_eligible=True` while still passing it through for overlay rendering.
   - `MotionHistoryBuffer` evicts oldest entries beyond configured capacity.
3. **Import smoke-test.** A short Python snippet that imports every CP-2 module and constructs each class with default and custom parameters, confirming no wiring regressions.
4. **Pipeline-composition smoke-test.** A short script that runs the canonical CP-2 sequence on a synthetic 2-hand frame: `TrackingModule.detect → HandIdentityModule.assign_roles → OcclusionHandler.bridge_gaps → HandScaleEstimator.estimate → PrimaryHandFilter.filter`. Confirms the per-frame analysis pipeline wires correctly (the actual frame-loop integration is deferred to CP-3/Catch-up phase per Implementation Plan §3.2).
5. **Existing tests stay green.** `pytest -q` must continue to show 30/30 passing (no regression in CP-1).

---

## Rollback Strategy

This checkpoint creates 8 new files (6 modules + 2 fixtures) and adds 6 new test files plus a small `conftest.py` extension. None of the existing files are semantically modified. To roll back:

```bash
git clean -fd gestureos/gestures/ \
              gestureos/tests/fixtures/ \
              gestureos/tests/unit/test_hand_identity.py \
              gestureos/tests/unit/test_occlusion_handler.py \
              gestureos/tests/unit/test_hand_scale.py \
              gestureos/tests/unit/test_primary_hand_filter.py \
              gestureos/tests/unit/test_motion_history.py \
              gestureos/tests/unit/test_gesture_utils.py
git checkout -- gestureos/tests/conftest.py
```

If only one module's behaviour needs to be reverted, the per-file deletion above is sufficient. CP-1's behavior is untouched.

---

## Architecture Preservation Statement

- **RULES §2 (Architecture):** the pipeline order `Capture → Detect → Recognize → Resolve → Execute` is preserved. No CP-2 module performs gesture-rule evaluation, conflict resolution, or OS dispatch.
- **RULES §2.4:** `tracking/` modules do not import from `recognizer.py` / `conflict_resolver.py` / `executor.py`. `tracking/hand_identity.py`, `occlusion_handler.py`, `hand_scale.py`, `primary_hand_filter.py` import only from `models/`, `logging`, `dataclasses`, `collections`, `math` — all allowed by the AI Dev Guide §4.1 `tracking/` boundary.
- **RULES §2.5:** `tracking/` does not import from `recognizer` or `executor`. Confirmed above.
- **RULES §3 (Configuration):** all thresholds and tunables are named `UPPER_SNAKE_CASE` constants (e.g., `REID_WINDOW_S`, `MATCH_THRESHOLD`, `RETENTION_MS_DEFAULT`, `SMOOTHING_WINDOW`, `DEFAULT_MAX_FRAMES`).
- **RULES §5 (Recognition):** CP-2 does not implement any gesture rule — that is CP-3. CP-2 produces only the analyzed data objects that CP-3's recognizers consume.
- **RULES §6.6 (Temporal state):** the temporal state in `OcclusionHandler`, `HandIdentityModule`, and `MotionHistoryBuffer` is held in **explicit per-instance state containers** (instance attributes), never global variables and never function arguments.
- **RULES §9 (Logging):** all new components route through `logger = logging.getLogger('gestureos')` (consistent with the existing `hand_detector.py` pattern); no `print()` statements are introduced.
- **RULES §10 (Checkpoint Discipline):** no CP-3+ features are introduced. The `HandData` dataclass is **not** modified — its v1.2 schema (`role`, `scale`, `gesture_eligible`, `is_retained`) is already complete and is only populated by CP-2's components.
- **RULES §12 (Frame-Loop Efficiency):** all hot-path methods (`assign_roles`, `bridge_gaps`, `estimate`, `filter`) are allocation-light (operate on existing lists, return `replace()`-built dataclasses). No per-frame dict-of-deques-of-lists allocations beyond what TRD §3 already specifies.

---

## Out of Scope (Explicit Non-Goals)

The following are **not** part of CP-2 and will not be implemented in this report:

- Static / dynamic gesture rules (`static_recognizer.py`, `dynamic_recognizer.py`) — CP-3.
- `GestureEngine`, `ConflictResolver`, `StabilityFilter`, `CooldownFilter` — CP-3.
- `ActivationGate` — CP-4.
- `ActionEngine`, `CursorController`, `CommandExecutor` — CP-5.
- `ContextEngine` and Windows / macOS / Linux adapters — CP-6.
- `LightingMonitor`, debug-overlay panel — CP-8.
- `ProfileManager`, calibration UI — CP-7.
- Any PyQt6 UI surface changes.
- Any `app/capture_thread.py` pipeline-extension changes (the pipeline is wired CP-2-ready by leaving CP-1's pipeline alone; CP-3 wires `GestureEngine` into `CaptureThread.run()`).

CP-2's deliverable is the analyzed `HandData` boundary; CP-3 will be the first checkpoint to consume it for actual recognition.