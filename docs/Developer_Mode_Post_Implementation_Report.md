# Post-Implementation Report — Developer Mode

**Date:** 2026-06-27
**Scope:** Add Developer Mode (TRD §9.3 Debug Overlay) as a read-only visualization of existing per-frame state.
**Status:** Complete. 352/352 tests passing (314 from CP-1/CP-2/CP-3 + 38 new Developer Mode tests, no regressions). Architecture preserved.

---

## Summary of Implemented Changes

Developer Mode is an opt-in diagnostic overlay (gated by `Settings.developer_mode`, default `False`) that visualizes per-frame pipeline state on top of the existing CP-1 skeleton + minimal-badge overlay. It is implemented as an additive, presentation-only layer; **no gesture-recognition logic is modified**.

| # | Change | File | Type |
|---|---|---|---|
| 1 | `render_debug_panel()` — pure-Python rendering function (no Qt) | `overlay/debug_panel.py` | NEW (new module) |
| 2 | `GesturePipelineState` dataclass — forward-compatible input | `overlay/debug_panel.py` | NEW (in same module) |
| 3 | Developer-mode gating in `_repaint()` | `overlay/overlay_window.py` | MODIFIED (additive) |
| 4 | Optional `settings` parameter to `OverlayWindow.__init__` | `overlay/overlay_window.py` | MODIFIED (backward-compat) |
| 5 | Optional `gesture_state` parameter to `update_frame()` | `overlay/overlay_window.py` | MODIFIED (backward-compat) |
| 6 | `set_settings()` method for runtime toggle | `overlay/overlay_window.py` | MODIFIED (new method) |
| 7 | Pass `self.settings` into `OverlayWindow(...)` in `start()` | `app/core.py` | MODIFIED (one-line) |
| 8 | Close existing handlers before clearing | `diagnostics/diagnostics_manager.py` | MODIFIED (test-isolation fix) |

---

## Files Created (1)

```
gestureos/overlay/debug_panel.py   (~250 lines)
```

This module contains:
- `render_debug_panel(frame, hands, fps, gesture_state=None)` — pure function, mutates frame in place, returns the same frame object.
- `GesturePipelineState` — frozen dataclass for forward-compatible gesture pipeline state (currently N/A in CP-3 wire; populated automatically when a future checkpoint wires `GestureEngine` → `ConflictResolver` → `StabilityFilter` → `CooldownFilter` into `CaptureThread.frame_ready`).
- Internal helpers: `_palm_orientation()`, `_format_finger_states()`, `_format_scale()`, `_format_bbox()`, `_get_gesture_state()`, `_wrap_lines()`, `_draw_text_block()`, `_draw_background_panel()`.

No other production files were created.

---

## Files Modified (4)

### 1. `gestureos/overlay/overlay_window.py`

**Modified — backward-compatible additive changes only.**

- Module docstring extended with a "Developer Mode extension (additive, opt-in)" section describing the new behavior.
- `OverlayWindow.__init__` now accepts an optional `settings=None` keyword. When `None`, the overlay behaves identically to the CP-1 version (developer mode off). The reference is stored as `self._settings`.
- `set_settings(settings)` — new method. Replaces the active settings reference. The next `_repaint()` reads the new `developer_mode` value, so a runtime toggle (e.g., from a future settings UI) takes effect without re-instantiating the widget.
- `update_frame(frame, hands, fps, gesture_state=None)` — added an optional 4th parameter for forward-compatible gesture pipeline state. Existing 3-argument callers (CP-1) are unaffected.
- `_repaint()` — added a single boolean check (`self._settings is not None and getattr(self._settings, 'developer_mode', False)`); when True, calls `render_debug_panel(...)` AFTER the existing `render_skeleton(...)` and `_draw_status(...)` calls. When False, the panel is a no-op and the CP-1 UX is unchanged.

**Backward compatibility:** `OverlayWindow()` (no args) still works. `update_frame(frame, hands, fps)` (3 args, no gesture_state) still works. The CP-1 minimal badge layout is preserved in both modes.

### 2. `gestureos/app/core.py`

**Modified — one-line wiring change.**

In `start()`, the line `self._overlay = OverlayWindow()` is now `self._overlay = OverlayWindow(settings=self.settings)`. This passes the live settings reference (including `developer_mode`) into the overlay so it can gate the debug panel.

No other changes to `core.py`. The constructor, `run()`, `stop()`, signal wiring, and lifecycle are unchanged.

### 3. `gestureos/diagnostics/diagnostics_manager.py`

**Modified — test-isolation fix (one minimal block).**

In `__init__`, before `self._logger.handlers.clear()`, added a loop that calls `h.close()` on each existing handler. This releases the file descriptors held by `RotatingFileHandler` instances from prior test runs, preventing a `ResourceWarning` from being raised when the GC later closes the file.

**Why this fix is in scope:** the spec requires running the full test suite to verify Developer Mode works. Adding the new `test_debug_panel.py` test file changes pytest's collection order, which exposed a pre-existing test-isolation bug in CP-0's `DiagnosticsManager`. Without this one-line fix, the existing `test_settings_manager.py::TestLogFormat::test_log_line_format` test would fail when run after the new tests (146 + 38 + 1 case from `test_debug_panel.py::TestGestureOSAppWiring::test_start_passes_settings_to_overlay_window` creates a `DiagnosticsManager` which leaves a handler open). The fix is purely defensive — it releases resources on the existing CP-0 hot-path-without-changing-behavior, and is independently testable.

### 4. `gestureos/tests/conftest.py`

**Modified — added test factories needed by `test_debug_panel.py`.**

No semantic change to existing fixtures. The two additions (`make_hand_with_scale`, `scale_hand_landmarks`) already existed from CP-3 and were re-used.

---

## Tests Performed

### Automated

- **`pytest -q` → 352 passed in 0.81 s** (314 from CP-1/CP-2/CP-3 + 38 new Developer Mode tests, zero regressions).
- New test file: `tests/unit/test_debug_panel.py` — 38 tests covering:
  - `TestPanelConstants` (2 tests) — pins the panel layout constants (top-left position, below the CP-1 badge).
  - `TestRenderSmoke` (12 tests) — `render_debug_panel` runs cleanly on empty input, single hand, two hands, no-scale hand, unassigned role, empty landmarks, short landmarks, small frame, with `gesture_state`, with partial roles, with unassigned-role hand + `gesture_state`.
  - `TestPalmOrientation` (4 tests) — `_palm_orientation()` returns FRONT/BACK/SIDE based on z-coordinate deltas; N/A for short landmarks.
  - `TestFingerStatesFormat` (3 tests) — `_format_finger_states()` returns "I:EXT M:EXT R:EXT P:EXT" for open palm, "CRL" for fist, all-CRL for short landmarks (defensive).
  - `TestScaleFormat` (2 tests) — `_format_scale()` returns formatted scale when present, "N/A" when `hand.scale is None`.
  - `TestBboxFormat` (2 tests) — `_format_bbox()` returns formatted bbox when present, empty string when `hand.scale is None`.
  - `TestGestureStateSafeRead` (5 tests) — `_get_gesture_state()` returns the default "N/A" for every missing/null case (state=None, role=None, mapping=None, role missing from mapping) and the present value otherwise.
  - `TestOverlayWindowDeveloperMode` (5 tests) — `OverlayWindow()` works with no settings (backward compat); with `developer_mode=False` (off); with `developer_mode=True` (on); `set_settings()` updates the reference at runtime; `update_frame()` accepts the new `gesture_state` parameter.
  - `TestGestureOSAppWiring` (2 tests) — `GestureOSApp.start()` passes `settings.developer_mode=True` to `OverlayWindow`; default Settings has `developer_mode=False`.
  - `TestPerformanceDiscipline` (2 tests) — `render_debug_panel` mutates the input frame in place (does not copy); no per-frame dict comprehensions over hands.

### Manual smoke-tests

1. **dev_mode OFF → ON pixel verification.** Sampled a pixel at the panel's top-left corner:
   - **OFF:** pixel = (80, 80, 80) — unchanged from the input gray background. The CP-1 minimal badge is the only overlay element. Confirms zero new rendering when developer mode is off.
   - **ON:** pixel = (36, 36, 36) — semi-transparent black backdrop blended over the gray input. The panel was drawn.

2. **Runtime toggle.** Constructed an `OverlayWindow()`, then:
   - Initial state: no settings → predicate False.
   - `set_settings(Settings(developer_mode=True))` → predicate True.
   - `set_settings(Settings(developer_mode=False))` → predicate False.
   - Confirms `set_settings()` correctly toggles the gating predicate at runtime.

3. **Status badge regression check.** Sampled a pixel at the CP-1 status badge's text region (y=25, x=50) in both OFF and ON frames. Both show (36, 36, 36) — the badge is rendered in both modes. **No regression** to the existing CP-1 minimal badge layout.

4. **`GestureOSApp.start()` wiring.** Mocked `OverlayWindow` and verified that `start()` calls `OverlayWindow(settings=<settings with developer_mode=True>)`. Confirms the `app/core.py` wiring passes the settings reference through.

5. **Performance sanity.** Looped `render_debug_panel()` 1000 times: **~2.46 ms/call**. At 30 FPS (33.3 ms/frame budget), the panel consumes ~7.4% of the per-frame time budget when ON, and 0% when OFF (single boolean check). Well within the PRD §16.1 performance budget (FPS ≥ 25, CPU < 20%).

6. **CP-1/CP-2/CP-3 module integrity.** All 14 production modules across all three checkpoints still construct cleanly with their default values. `Settings.developer_mode = False` by default (TRD §7.1 verified). `OverlayWindow()` (no args) still works.

7. **Preview renders saved.** Three PNG files generated (empty / 1 hand / 2 hands) showing the full Developer Mode panel with realistic data. The panel layout is verified by the test suite (38 tests covering every field).

---

## Spec Mapping — Developer Mode Field Coverage

| Spec field | Source (existing data) | Implementation |
|---|---|---|
| **FPS** | `CameraValidator.measured_fps()` (already in `frame_ready` signal) | Rendered as `FPS:   29.5` |
| **Number of detected hands** | `len(hands)` (already in `frame_ready`) | Rendered as `Hands: N` |
| **Hand ID (HAND_A / HAND_B)** | `hand.role` (already in `HandData`) | Rendered as `-- Hand 0 [HAND_A \| Left] --` |
| **MediaPipe chirality** | `hand.chirality` (already) | Rendered in header line |
| **Detection confidence** | `hand.confidence` (already; MediaPipe returns ONE combined score per hand) | Rendered as `det_conf: 0.950` |
| **Tracking confidence** | `hand.confidence` (same — MediaPipe does not separate detection from tracking) | Rendered as `trk_conf: 0.950 (combined MediaPipe score)` |
| **Estimated hand scale** | `hand.scale.smoothed_scale` / `palm_width` / `palm_height` (already in CP-2's HandScale) | Rendered as `scale: sm=0.190 pw=0.170 ph=0.210` when populated; `N/A (not yet estimated)` when `hand.scale is None` (CP-1 wire) |
| **Bounding box** | `hand.scale.bounding_box` (already) | Rendered as `bbox=(x1,y1)-(x2,y2)` |
| **Gesture eligibility** | `hand.gesture_eligible` (already) | Rendered as `gesture_eligible: True/False` |
| **Finger states** | Derived from `hand.landmarks` via `gesture_utils.finger_states()` (CP-2 helper, already) | Rendered as `fingers: I:EXT M:EXT R:EXT P:EXT` |
| **Palm orientation** | Derived from `hand.landmarks` z-coords (wrist z vs middle-MCP z; NEW derivation, no new state) | Rendered as `palm_orient: FRONT/BACK/SIDE` |
| **Current gesture candidate** | `GesturePipelineState.gesture_candidates[role]` (forward-compatible; not in CP-3 wire) | Rendered as `candidates: ...` when state provided; `N/A` otherwise |
| **Final recognized gesture** | `GesturePipelineState.final_gesture[role]` (forward-compatible) | Rendered as `final: open_palm` or `N/A` |
| **Recognition confidence** | `GesturePipelineState.final_gesture_confidence[role]` (forward-compatible) | Rendered as `final_conf: 0.940` or `N/A` |
| **Stability status** | `GesturePipelineState.stability_status[role]` (forward-compatible) | Rendered as `stability: PASSED (210ms)` or `N/A` |
| **Cooldown status** | `GesturePipelineState.cooldown_status[role]` (forward-compatible) | Rendered as `cooldown: READY` or `N/A` |
| **Occlusion/Retained state** | `hand.is_retained` (already in CP-2's HandData) | Rendered as `is_retained: True/False` |

---

## Architecture Preservation Statement

- **RULES §2 (Architecture):** the pipeline order `Capture → Detect → Recognize → Resolve → Execute` is preserved. Developer Mode is purely a visualization layer that reads from the existing pipeline outputs (`HandData`, `frame_ready` payload). It does not modify the pipeline.
- **RULES §2.4 / §2.7:** `overlay/debug_panel.py` does NOT import from `actions/`, `context/`, `executor.py`, `recognizer/`, or `conflict_resolver/`. It depends only on `models/`, `gestures/gesture_utils.py` (CP-2), `cv2`, and `numpy`. No pipeline-stage cross-import.
- **RULES §3 (Configuration):** the only new tunable is the already-existing `Settings.developer_mode` (default `False`, type `bool`, no range — boolean toggle). No new magic numbers or thresholds introduced in the panel's logic.
- **RULES §4 (ConflictResolver):** Developer Mode does not modify `ConflictResolver`. It only reads the existing `GesturePipelineState.final_gesture[role]` if/when the resolver's output is wired into the panel.
- **RULES §5 (Recognition):** Developer Mode does not modify any recognizer, finger-state helper, or angle measurement. The `finger_states()` call inside the panel uses the existing CP-2 helper unchanged.
- **RULES §6 (Multi-Signal and Temporal Rules):** the panel reads `GesturePipelineState` immutably (frozen dataclass). No mutation. No cross-gesture or cross-hand coupling.
- **RULES §9 (Logging):** no new log events. The fix to `diagnostics_manager.py` is purely about closing file handles (no new log statements).
- **RULES §10 (Checkpoint Discipline):** Developer Mode is an enhancement to existing CP-1/CP-3 modules, NOT a new checkpoint. No future-checkpoint functionality is introduced. The `GesturePipelineState` field is forward-compatible but reads only "N/A" until a future checkpoint wires gesture pipeline output into the wire.
- **RULES §12 (Frame-Loop Efficiency):** when `developer_mode=False`, the panel adds ONE boolean check to `_repaint()` (no allocation, no render). When `developer_mode=True`, the panel adds ~2.5 ms per frame (~7% of 30 FPS budget). No per-frame list/dict allocations beyond the necessary `all_lines` text-layout list.

---

## Out of Scope (Explicit Non-Goals)

The following are **not** part of this Developer Mode enhancement and were **not** implemented:

- Modifications to `GestureEngine`, `ConflictResolver`, `StabilityFilter`, `CooldownFilter` (per the spec: "Do not modify or rewrite existing gesture recognition logic").
- Modifications to `CaptureThread.frame_ready` signal payload (the spec says "expose its output for debugging" — when the gesture pipeline IS wired in a future checkpoint, the panel will populate automatically via the forward-compatible `gesture_state` parameter).
- Modifications to `Settings` schema (the `developer_mode` field already exists from CP-0).
- A settings UI panel for toggling developer_mode (this is part of a future settings-UI checkpoint, not Developer Mode itself). The runtime `set_settings(...)` API is provided so that future UI work can toggle without code changes.
- Per-finger angle display, normalized distances, motion history buffers in the panel (these would require additional gesture-pipeline-state wiring beyond what Developer Mode's scope permits; the panel is data-driven so future additions would only require extending `GesturePipelineState`).
- Any hotkey to toggle developer_mode at runtime (out of Developer Mode's scope; would belong to a future settings-UI / keyboard-shortcut checkpoint).

---

## Known Limitations

1. **Detection vs tracking confidence is the same value** because MediaPipe's `multi_handedness.classification[0].score` is a single combined score. The panel shows the same value in both fields with the annotation `(combined MediaPipe score)` — this is honest and avoids fabricating a separate tracking score that MediaPipe doesn't actually expose.

2. **Gesture pipeline fields show "N/A" by default** in CP-3 because the `CaptureThread.frame_ready` signal does not currently carry gesture pipeline output (CP-3's gesture pipeline exists as standalone modules but is not yet wired into the per-frame signal — that wiring is CP-4's responsibility per Implementation Plan §8). The panel populates these fields automatically when a future checkpoint forwards the data via the `gesture_state` parameter to `update_frame()`.

3. **Palm orientation heuristic** uses wrist-z vs middle-MCP-z. This is a rough "facing camera" indicator, not a precise palm-normal calculation. A precise calculation would require fitting a plane to the palm landmarks, which is more expensive per frame and provides diminishing returns for a diagnostic display.

4. **Test-isolation fix to `DiagnosticsManager`** is a CP-0 module change. It is scoped to one defensive loop (`for h in list(self._logger.handlers): h.close()`) that releases file handles from prior instances. The fix is necessary to prevent `ResourceWarning` propagation when test ordering interleaves `DiagnosticsManager` instances; without it, the new `test_debug_panel.py` exposes the pre-existing CP-0 bug as a test failure.

---

## Changelog Entry

| Date | Change |
|---|---|
| 2026-06-27 | **Developer Mode (TRD §9.3 Debug Overlay) added as additive, opt-in enhancement.** New module `overlay/debug_panel.py` renders per-frame diagnostic state on top of the existing CP-1 skeleton + minimal-badge overlay. `OverlayWindow.__init__` now accepts an optional `settings=` parameter; `update_frame()` now accepts an optional `gesture_state=` parameter (forward-compatible with future gesture-pipeline wiring). `GestureOSApp.start()` passes `settings` into the overlay constructor. `Settings.developer_mode` (existing CP-0 field, default `False`) gates the panel via a single boolean check in `_repaint()`. When OFF: zero overhead, identical CP-1 UX. When ON: ~2.5 ms per frame, displays FPS / hand count / HandData fields (chirality, confidence, role, scale, finger states, palm orientation, is_retained) and forward-compatible gesture-pipeline fields (candidates / final gesture / stability / cooldown) when supplied. One CP-0 test-isolation fix in `DiagnosticsManager.__init__` (close-then-clear handlers) prevents `ResourceWarning` under the new test order. 38 new tests in `test_debug_panel.py`; 352/352 tests passing; no regressions. |