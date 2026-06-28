# Pre-Implementation Report — Checkpoint 3 (Gesture Recognition Layer)

**Date:** 2026-06-27
**Scope:** Implement Checkpoint 3 per Implementation Plan §7 / TRD §3.9–§3.11 / PRD §4.3–§4.6 + §4.5 Multi-Signal Recognition + §8.2 Stability + §8.3 Cooldown.
**Architectural stance:** Build only CP-3's six in-scope modules. No activation gating (CP-4), no action dispatch (CP-5), no context engine (CP-6), no UI changes (CP-7/8). The deliverable is a working `GestureEngine` that produces confidence-scored, conflict-resolved, stability-cooldown-filtered gesture candidates ready for CP-4 to consume.

---

## Objective

Implement every gesture rule defined in the PRD — 8 static, 6 dynamic — using exclusively scale-invariant geometric logic, plus the supporting pipeline that turns raw landmark frames into a single, de-noised, debounced `GestureResult` per hand role per emission. Per Implementation Plan §7:

> Implement every gesture rule defined in the PRD (8 static, 6 dynamic) using exclusively scale-invariant geometric logic, plus the Gesture Stability Window and Cooldown System that prevent flicker and double-triggers. This is the checkpoint where the product's core value proposition — reliable, distance-independent, rule-based gesture control — becomes real and testable end-to-end at the recognition level.

The data boundary produced by this checkpoint is a sequence of stability-passed, cooldown-cleared `GestureResult` objects — exactly what CP-4's `ActivationGate.feed_gesture()` consumes (per TRD §5.3) and what CP-3.10's per-frame state diagram positions at "Stability Check → Context Resolution → Action Mapping → Cooldown Check".

---

## Current Checkpoint

**Checkpoint 3 — Gesture Recognition Layer** (Implementation Plan §7; PRD §4.3–§4.6 + §4.5 + §8.2 + §8.3; TRD §3.9 + §3.9.1 + §3.10 + §3.11).

CP-1 and CP-2 are **Done**: 146/146 tests passing across Camera/Tracking/Hand Analysis modules.

---

## Files to be Created

### Production modules (6)

| File | TRD / Plan Ref | Responsibility |
|---|---|---|
| `gestureos/gestures/static_recognizer.py` | TRD §3.9 / IP §7.1 | 8 static-gesture `detect_*` functions (Open Palm, Closed Fist, Pinch, Thumbs Up, Thumbs Down, Peace Sign, Three Fingers, OK Sign). All use multi-signal discipline (PRD FR-MS-01). |
| `gestureos/gestures/dynamic_recognizer.py` | TRD §3.9 / IP §7.2 | 6 dynamic-gesture `detect_*` functions (Swipe × 4, Wave, Circular Motion). All use multi-signal discipline (PRD FR-MS-02). |
| `gestureos/gestures/gesture_engine.py` | TRD §3.9 (updated v1.2) | `GestureEngine` orchestrator: per-frame loop calling `_check_all_static()` + `_check_all_dynamic()`, returns ALL qualifying candidates (not first-match-wins, per PRD §4.6). |
| `gestureos/gestures/conflict_resolver.py` | TRD §3.9.1 (new in v1.1) | `ConflictResolver`: per-role winner selection using confidence (FR-CR-02) and fixed tie-break priority (FR-CR-03). |
| `gestureos/gestures/stability_filter.py` | TRD §3.10 | `StabilityFilter`: per-role hold timer for static gestures (FR-GS-01..03); dynamic exempt (FR-GS-04). |
| `gestureos/gestures/cooldown_filter.py` | TRD §3.11 | `CooldownFilter`: per-(role, gesture_name) cooldown timer (FR-CD-01..02); debug-overlay accessor (FR-CD-03). |

### Tests (6)

| File | Mirrors | Coverage |
|---|---|---|
| `gestureos/tests/unit/test_static_gestures.py` | `static_recognizer.py` | Per-gesture positive + negative + scale-invariance + no-scale + mutual-exclusivity tests (per AI Dev Guide §9.6 template). |
| `gestureos/tests/unit/test_dynamic_gestures.py` | `dynamic_recognizer.py` | Per-gesture positive + too-slow + too-diagonal + scale-invariance + no-buffer tests. |
| `gestureos/tests/unit/test_scale_invariance.py` | both recognizers | Parametrized across scale factors 0.5/1.0/2.0/3.0 (TRD §4.6 / §13.3). |
| `gestureos/tests/unit/test_conflict_resolver.py` | `conflict_resolver.py` | PRD §4.6 worked example, tie-break priority, cross-hand independence (FR-CR-04), empty-input safety. |
| `gestureos/tests/unit/test_stability_filter.py` | `stability_filter.py` | TRD §13.5 `test_single_frame_flicker_does_not_trigger`, dynamic exemption (FR-GS-04), per-role independence (FR-GS-03), exact-boundary handling (`>=` not `>`). |
| `gestureos/tests/unit/test_cooldown_filter.py` | `cooldown_filter.py` | TRD §13.5 `test_cooldown_suppresses_repeated_trigger`, cross-gesture independence (FR-CD-02), cross-hand independence (FR-CD-02), `remaining_ms()` accessor (FR-CD-03). |

### Fixtures (3)

| File | Purpose |
|---|---|
| `gestureos/tests/fixtures/gesture_trajectories.json` | Trajectory samples for each of the 6 dynamic gestures (positions + timestamps). Used by `test_dynamic_gestures.py` and `test_scale_invariance.py`. |
| `gestureos/tests/fixtures/swipe_negative_cases.json` | Trajectories that must NOT trigger any swipe: too-slow swipe, too-diagonal swipe, single-frame displacement, etc. (per AI Dev Guide §7.3 item 4). |
| (CP-2's existing `sample_landmarks.json` is reused for static-gesture fixtures — no new static-landmark fixtures required.) |

### Files to be modified

**None.** Per CP-2's analysis:
- `models/data_models.py` — `GestureResult` already has the v1.0 schema (`gesture_name`, `confidence`, `is_dynamic`, `hand_role`, `timestamp`) that CP-3 consumes.
- `settings/settings_manager.py` — All CP-3 settings fields (`gesture_confidence_threshold`, `gesture_stability_window_ms`, `gesture_cooldown_static_ms`, `gesture_cooldown_dynamic_ms`) are already present and validated.
- `gestures/gesture_utils.py` and `gestures/motion_history.py` — CP-2 deliverables that CP-3 consumes (no edits required).
- `tracking/*` — CP-1/CP-2 deliverables; `HandData.scale.smoothed_scale` and `HandData.gesture_eligible` are already populated.

### Files NOT modified (explicitly out of scope for CP-3)

- `app/capture_thread.py` — CP-3 *describes* the pipeline wiring in §7 of the Implementation Plan but explicitly defers the actual threading-model changes to **Checkpoint 4 (Activation)** because the activation gate is the next stage that needs the pipeline wired in. CP-3 stops at the `GestureEngine.evaluate()` → `ConflictResolver.resolve()` → `StabilityFilter.check()` → `CooldownFilter.check()` chain — that's the deliverable boundary.
- `overlay/overlay_window.py` — unchanged. The debug overlay's gesture display is CP-8 (Diagnostics Layer) work.
- `app/core.py` — unchanged. Activation gate wiring is CP-4.
- `actions/*`, `context/*`, `ui/*` — CP-5+.

---

## PRD References

CP-3 implements the following PRD requirements (from §4.3 / §4.4 / §4.5 / §4.6 / §8.2 / §8.3):

- **FR-MS-01 / FR-MS-02 / FR-MS-03** (Multi-Signal Recognition discipline) — every `detect_*` function combines ≥2 independent signals and declares them in its docstring.
- **FR-CR-01 / FR-CR-02 / FR-CR-03 / FR-CR-04** (Conflict Resolution) — single winner per role; highest-confidence wins; fixed tie-break priority; per-role independence.
- **FR-GS-01 / FR-GS-02 / FR-GS-03 / FR-GS-04** (Gesture Stability) — 200ms hold window; no partial credit; per-role independence; dynamic exempt.
- **FR-CD-01 / FR-CD-02 / FR-CD-03** (Cooldown System) — per-(role, gesture_name) cooldown; cross-gesture + cross-hand independence; debug-overlay accessor.

CP-3 does **not** introduce any requirement from later checkpoints (no FR-AM-*, FR-AT-*, FR-AC-*, no ActivationGate wiring, no ActionEngine wiring, no ContextEngine wiring).

---

## TRD References

| Component | TRD section | Inputs | Outputs |
|---|---|---|---|
| `static_recognizer.detect_*` | §4.3 | `HandData` (one hand) | `GestureResult \| None` |
| `dynamic_recognizer.detect_*` | §4.4 | `MotionHistoryBuffer.get(role)` + `HandData.scale.smoothed_scale` | `GestureResult \| None` |
| `GestureEngine` | §3.9 | `list[HandData]`, `now: float`, `Settings` | `list[GestureResult]` (all qualifying candidates per hand) |
| `ConflictResolver` | §3.9.1 | `list[GestureResult]` | `list[GestureResult]` (≤1 per role) |
| `StabilityFilter` | §3.10 | `GestureResult \| None` per role, `now: float` | `GestureResult \| None` |
| `CooldownFilter` | §3.11 | `GestureResult`, `now: float`, `Settings` | `GestureResult \| None` |

---

## Dependencies

**No new dependencies.** All CP-3 modules are pure Python:
- `static_recognizer.py` uses `gesture_utils` (CP-2).
- `dynamic_recognizer.py` uses `gesture_utils` + `MotionHistoryBuffer` (CP-2).
- `gesture_engine.py` uses `Settings` (CP-0) + `HandData` (CP-0) + `GestureResult` (CP-0) + the recognizers above.
- `conflict_resolver.py`, `stability_filter.py`, `cooldown_filter.py` are pure-Python timers/dicts.

No `requirements.txt` change. Per AI Dev Guide §3, MediaPipe is not touched by CP-3.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Scale-invariance regression (raw-pixel threshold reintroduced) | Medium-High | Parametrized `test_scale_invariance.py` across 0.5/1.0/2.0/3.0× for Pinch + Swipe Right (TRD §4.6). Each gesture's `detect_*` docstring cites the normalized signal (FR-MS-03). Code-review checklist (AI Dev Guide §12.2) verified at completion. |
| Conflict resolution order-of-operations error | Medium | `test_conflict_resolver.py` covers the PRD §4.6 worked example exactly (peace_sign 0.81 vs three_fingers 0.88 on HAND_A → three_fingers wins), plus the tied-confidence tie-break case, plus the cross-hand independence case (FR-CR-04). |
| Stability window flicker on a transitional pose (e.g., mid-finger-curl during a fist-to-open transition) | Medium | TRD §13.5's `test_single_frame_flicker_does_not_trigger` is implemented verbatim. PRD FR-GS-02 (no partial credit) is encoded in `StabilityFilter.check()` and tested. |
| Cooldown suppressing a *different* gesture on the same hand | Low | `test_cooldown_filter.py` covers cross-gesture independence (FR-CD-02): one gesture on cooldown does NOT block a different gesture on the same hand. |
| Wave gesture ambiguity (Gap G-3) | Documented | Two consecutive opposite swipes vs. Wave: documented in `dynamic_recognizer.py:detect_wave` docstring + module-level comment as Gap G-3 (per Implementation Plan §7.2). NOT silently resolved. |
| Recognition too slow / too fast on real hardware | Low | CP-9 (Performance) is the dedicated checkpoint for FPS/CPU/memory budgets; CP-3 only needs unit-level correctness per PRD §17.2. |
| HandData.scale=None graceful degradation | Low | Every `detect_*` function checks `if hand.scale is None: return None` (PRD FR-SC-04); tested explicitly. |

---

## Validation Strategy

1. **Unit tests.** Per AI Dev Guide §9.6 template and Implementation Plan §7's per-gesture testing strategy, every gesture gets:
   - Positive test against a clear unambiguous fixture
   - Negative test against a confusable neighbor (mutual exclusivity)
   - Scale-invariance parametrization across 0.5/1.0/2.0/3.0 (static + dynamic gestures with normalized-distance / normalized-trajectory signals)
   - Too-slow + too-diagonal rejection tests for dynamic gestures (TRD §13)
   - `hand.scale is None` → `None` test for every gesture that uses normalized-distance

2. **Pipeline composition smoke-test.** Run the full chain on synthetic 2-hand data:
   ```
   synthetic_2_hand_frame -> GestureEngine.evaluate() ->
   ConflictResolver.resolve() -> StabilityFilter.check() per role ->
   CooldownFilter.check() per (role, gesture_name)
   ```
   Assert that the chain correctly produces one stability-passed / cooldown-cleared result per hand, and that two consecutive frames with different gestures correctly reset the stability hold timer.

3. **PRD §4.6 worked example.** Test the exact TRD example:
   ```
   candidates = [peace_sign 0.81, three_fingers 0.88] on HAND_A
   winners = [three_fingers]   # higher confidence, no tie
   ```

4. **Pipeline-vs-canonical integration.** The full chain (HandData → GestureEngine → ConflictResolver → StabilityFilter → CooldownFilter) is exercised end-to-end in a new test file `tests/unit/test_gesture_pipeline.py` to verify the per-stage contracts line up (e.g., GestureEngine returns `list[GestureResult]`, ConflictResolver consumes that exact shape, etc.).

5. **CP-1/CP-2 regression check.** `pytest -q` must continue to show 146/146 passing (the CP-1 + CP-2 tests) plus the new CP-3 tests.

6. **Manual validation (operator-side).** Documented in Post-Implementation Report, not executed at this checkpoint (live camera tests are deferred to Checkpoint 9's UAT per Implementation Plan §13).

---

## Rollback Strategy

CP-3 creates 9 new files (6 modules + 3 fixtures) and 6 new test files. None of the existing CP-1/CP-2 production code is modified. To roll back:

```bash
git clean -fd gestureos/gestures/static_recognizer.py \
              gestureos/gestures/dynamic_recognizer.py \
              gestureos/gestures/gesture_engine.py \
              gestureos/gestures/conflict_resolver.py \
              gestureos/gestures/stability_filter.py \
              gestureos/gestures/cooldown_filter.py \
              gestureos/tests/fixtures/gesture_trajectories.json \
              gestureos/tests/fixtures/swipe_negative_cases.json \
              gestureos/tests/unit/test_static_gestures.py \
              gestureos/tests/unit/test_dynamic_gestures.py \
              gestureos/tests/unit/test_scale_invariance.py \
              gestureos/tests/unit/test_conflict_resolver.py \
              gestureos/tests/unit/test_stability_filter.py \
              gestureos/tests/unit/test_cooldown_filter.py
```

CP-1 and CP-2 are unaffected by CP-3 (the only consumers of CP-2's modules are CP-3 itself, which is being deleted).

---

## Architecture Preservation Statement

- **RULES §2 (Architecture):** the pipeline order `Capture → Detect → Recognize → Resolve → Execute` is preserved. CP-3 implements the `Recognize` (GestureEngine) and the `Resolve` (ConflictResolver) stages. `Execute` is downstream (CP-5).
- **RULES §2.4:** `gestures/` modules do not import from `actions/` or `context/` or `ui/`. (Verified: CP-3's modules only depend on `models/`, `settings/`, and CP-2's `gestures/` siblings.)
- **RULES §2.7:** `conflict_resolver.py` does not perform gesture recognition or call OS APIs. (Verified: it operates purely on pre-classified `GestureResult` objects per TRD §3.9.1.)
- **RULES §3 (Configuration):** all thresholds and tunables are named `UPPER_SNAKE_CASE` constants (e.g., `PINCH_NORMALIZED_DISTANCE_THRESHOLD`, `SWIPE_RIGHT_DX_THRESHOLD_HAND_SCALES`, `STABILITY_HOLD_DEFAULT_MS`, `GESTURE_TIE_BREAK_PRIORITY`).
- **RULES §4 (ConflictResolver):** `ConflictResolver` is the sole authority for resolving multi-candidate conflicts. ConflictResolver does not import from `executor.py`. Inputs are treated as immutable (no in-place mutation; the resolver operates on the input list and returns a new list).
- **RULES §5 (Recognition):** every gesture uses scale-invariant math. No raw-pixel threshold. Every `detect_*` function returns `None` (not `0.0`) when not matched, so `GestureEngine`'s all-candidates list is not contaminated with zero-confidence entries.
- **RULES §6 (Multi-Signal and Temporal Rules):**
  - State containers are explicit per-instance (no globals); `GestureEngine` holds the `MotionHistoryBuffer`; `ConflictResolver` is stateless; `StabilityFilter` and `CooldownFilter` hold per-role / per-(role, gesture_name) dicts.
  - Velocity-based gestures compute velocity from normalized displacement / elapsed time across consecutive buffer entries (FR-MS-02).
  - No gesture triggers faster than the minimum debounce interval defined in `config.py`-style constants (Cooldown enforces this).
  - Temporal state is reset on hand loss / `scale is None` (covered by the existing CP-2 `OcclusionHandler.bridge_gaps()` contract: a `is_retained=True` hand is still passed to the recognizers; a fully-lost hand is filtered out by `PrimaryHandFilter`).
  - Multi-hand scenarios route through `ConflictResolver`, never through individual recognizers (recognizers are pure functions of one hand).
  - Recognizers never read or write temporal state belonging to a different gesture type — `MotionHistoryBuffer` is keyed by `hand_role`, not by gesture name; `CooldownFilter` is keyed by `(role, gesture_name)`.
  - When multiple signals are present simultaneously, the full resolver path is exercised: even a single-candidate frame goes through `ConflictResolver.resolve()` (FR-CR-01 pass-through). No single-signal shortcut.
- **RULES §9 (Logging):** all new components route through `logger = logging.getLogger('gestureos')` (consistent with CP-2's pattern); no `print()` statements. The `gesture` log category is added per TRD §9.2 (it did not exist before CP-3).
- **RULES §10 (Checkpoint Discipline):** no CP-4+ features are introduced. The pipeline stops at the cooldown-filtered `GestureResult`; the activation gate (CP-4), action dispatch (CP-5), and context engine (CP-6) are downstream consumers.
- **RULES §12 (Frame-Loop Efficiency):** all per-frame methods (`GestureEngine.evaluate()`, `ConflictResolver.resolve()`, `StabilityFilter.check()`, `CooldownFilter.check()`, every `detect_*`) are O(1) or O(hand-count) with bounded memory; no per-frame allocations beyond the candidates list itself.
- **AI Dev Guide §7 (Gesture Development Standards):** every `detect_*` docstring includes the explicit "Signals used: X, Y" line (FR-MS-03); every gesture uses `gestures/gesture_utils.py` primitives (no inline parallel math); function names match the PRD's `snake_case` identifiers exactly; `hand.scale is None` → `None` (FR-SC-04); never raises (hot-path).

---

## Out of Scope (Explicit Non-Goals)

The following are **not** part of CP-3 and will not be implemented in this report:

- `gestures/activation_gate.py` — CP-4.
- `actions/*`, `actions/executors/*`, `actions/cursor_controller.py` — CP-5.
- `context/*`, `context/adapters/*` — CP-6.
- `profiles/*`, `calibration/*`, `ui/*` — CP-7.
- `diagnostics/lighting_monitor.py` — CP-8.
- App/capture_thread.py pipeline wiring — CP-4 (which adds the activation gate as the next stage).
- Debug overlay extension (gesture state display in `overlay/`) — CP-8.
- PyQt6 UI surface changes.
- Default mapping files (`assets/default_mappings/*.json`) — CP-7 (although the gesture name strings used by CP-3 are the same strings that CP-7 will reference, so the contract is implicitly pinned by CP-3's tests).
- `MacOSExecutor`, `LinuxExecutor`, `MacOSContextAdapter`, `LinuxContextAdapter` — Future Expansion, explicitly prohibited by RULES §8.5 and AI Dev Guide §11.2.
- Performance benchmarks against real hardware — CP-9.

CP-3's deliverable is the recognized-gesture boundary: a stream of stability-passed, cooldown-cleared `GestureResult` objects, ready for CP-4's `ActivationGate.feed_gesture()` to consume.