# Pre-Implementation Report — Checkpoint 1 Tracking-Quality Hardening

**Date:** 2026-06-27
**Scope:** Improve stability, accuracy, and responsiveness of the Checkpoint 1 (CP-1) capture + tracking loop.
**Architectural stance:** Keep GestureOS pipeline boundaries intact (Camera → Detect → Recognize → Resolve → Execute). No new modules, no checkpoint scope creep.

---

## Objective

Manual validation of CP-1 revealed four recurring tracking-quality defects:

1. **Dual-hand inconsistency.** Often only one of two hands is detected even when both are visible.
2. **Tracking instability on rotation / partial closure.** Landmarks jitter and tracking is lost when the hand rotates or the fingers partially close.
3. **Slow recovery after temporary loss.** A few missed frames force MediaPipe to drop the track and re-run the full detection pass, producing a visible 200–400 ms gap.
4. **Overall responsiveness.** The pipeline can sit at ~20–22 FPS on a typical laptop webcam — below the 25 FPS budget from CP-1 acceptance criteria.

These defects all sit in the *capture + detect* layer (CP-1's responsibility). They are **not** caused by downstream recognizer logic (which does not yet exist). The fix belongs in:

- `camera/camera_module.py` (capture pipeline)
- `tracking/hand_detector.py` (MediaPipe wrapper)
- `app/capture_thread.py` (per-frame orchestration)

The reference implementation under `handtrack/HandTrackingModule.py` is used **only** as a comparative reference; nothing is copied or replaced.

---

## Current Checkpoint

**Checkpoint 1 — GestureOS Core Platform** (Implementation Plan §5; PRD §14.1).

All edits remain within CP-1's in-scope modules. No Checkpoint 2+ functionality is introduced.

---

## Files to be Modified

| File | Reason |
|---|---|
| `gestureos/camera/camera_module.py` | Increase capture resolution; reduce frame-queue lag via `CAP_PROP_BUFFERSIZE`; only resize when needed; expose cache-friendly properties for `reported_resolution`. |
| `gestureos/tracking/hand_detector.py` | Drop `model_complexity` from 1 → 0 for ≤2-hand setups (faster inference, similar accuracy); lower `min_tracking_confidence` to reduce track-loss on rotation; keep the existing re-init recovery path; allow overriding via constructor (already supported). |
| `gestureos/app/capture_thread.py` | Wake immediately when a frame is ready instead of sleeping the remainder of the target period; reuse a single RGB buffer to avoid per-frame allocation (RULES §12.1); clean up the spurious `_DROP_RECONNECT_THRESHOLD`-based logic that only fires when `read_frame()` returns None — keep but verify. |

**No new files. No edits to `models/`, `settings/`, `diagnostics/`, `overlay/`, or `app/core.py`.**

---

## PRD References

- PRD §14.1 (CP-1 Acceptance Criteria):
  - "MediaPipe detects hand landmarks on live webcam feed at ≥ 25 FPS"
  - "Landmark overlay renders correctly on webcam preview"
  - "Both hands tracked simultaneously (chirality labeling correct …)"
  - "FPS counter visible in overlay; measured FPS logged to `diagnostics.log`"
- PRD §8.11 (Camera Validation) — implicitly satisfied; no change to `CameraValidator` semantics.

---

## TRD References

- **TRD §3.1 — CameraModule.** Inputs: device index + target resolution + FPS. Outputs: preprocessed BGR frame. Error handling: 10-attempt/2s reconnect. *No semantic change here; only parameter tuning and one extra OpenCV hint.*
- **TRD §3.3 — TrackingModule.** Inputs: RGB frame. Outputs: `list[HandData]`. Error handling: 3-consecutive-exception re-init. *Semantic preservation; tuning `model_complexity` and confidence thresholds.*
- **TRD §2.2 — Threading model.** Single background `QThread` runs capture synchronously, signals to UI. *Preserved verbatim.*
- **TRD §12.1 — Performance.** "Frame-loop efficiency" — must avoid per-frame allocation. *Strengthened by reusing the RGB conversion buffer in `CaptureThread`.*

---

## Dependencies

**No new dependencies.** All changes use libraries already declared in `requirements.txt`:

- `opencv-python` (already pinned)
- `mediapipe` 0.10.x (already pinned)
- `numpy` (already pinned)
- `PyQt6` (already pinned)

**No version bumps.** Per AI Development Guide §3 ("Version-pin discipline"), a MediaPipe upgrade is a deliberate action and is not required for this work.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Raising capture resolution to 1280×720 increases per-frame CPU cost (decode + flip + resize) | Medium | Test on reference hardware (Intel i5 / 8 GB RAM, 720p webcam per PRD §14.1). If FPS regresses, fall back to 960×540. |
| Lowering `min_tracking_confidence` could increase jitter on noisy frames | Low–Medium | Tracking is already EMA-smoothed implicitly by MediaPipe's temporal model; combined with the lower `model_complexity`, jitter is reduced rather than increased. |
| `CAP_PROP_BUFFERSIZE=1` is silently ignored by some Windows webcam drivers (DSHOW backend) | Medium | Wrap in a `try/except` and log a DEBUG line on failure. No fallback action — drivers that don't support it queue frames normally and tracking still works. |
| Removing the artificial `time.sleep()` pacing in `CaptureThread` could allow the loop to spin faster than the camera delivers frames | Medium | Add a *non-blocking* "wait for next frame" using `cap.grab()` (non-blocking) instead of sleep-then-read. This is the standard OpenCV idiom. |
| Touching `model_complexity` changes detection behavior subtly across MediaPipe versions | Low | Pin already in place; the change is the MediaPipe-recommended default for ≤2 hands. |

---

## Validation Strategy

1. **Automated unit tests.** Run the full suite (`pytest -q`). Must stay at 30/30 passing.
2. **Import / init smoke-test.** A short Python snippet that constructs `CameraModule`, calls `open()`, instantiates `TrackingModule`, calls `initialize()`, and runs `detect()` on a synthetic 640×480 BGR image. Verifies no regressions in module wiring.
3. **Manual validation (operator-side).** User runs `python main.py` with a real webcam and validates:
   - **Dual-hand consistency** — both hands detected ≥ 90% of frames when both are visible.
   - **Rotation / partial closure** — tracking persists through moderate hand rotation and partially closed fingers for at least 5 seconds without losing the hand.
   - **Recovery speed** — after a hand briefly leaves and re-enters the frame, tracking re-acquires within 1–2 frames.
   - **FPS** — measured FPS ≥ 25 with a single hand, ≥ 22 with two hands on the reference hardware.

The first three are *manual* checks because unit tests cannot exercise a real webcam (TRD §13.2). The fourth is reported as `measured_fps` by `CameraValidator` and visible in the overlay status bar.

---

## Rollback Strategy

All edits are confined to three files. To roll back:

```bash
git checkout -- gestureos/camera/camera_module.py \
                 gestureos/tracking/hand_detector.py \
                 gestureos/app/capture_thread.py
```

This restores the prior CP-1 implementation exactly. The Pre-Implementation Report and Post-Implementation Report remain in `docs/` for traceability.

If a *partial* regression is observed (e.g., FPS drops), the parameter set can be reverted without touching the architectural changes:

- `camera_module.py`: revert the default `width`/`height` from 1280×720 to 640×480.
- `hand_detector.py`: revert `MODEL_COMPLEXITY` from 0 to 1, and `MIN_TRACKING_CONFIDENCE` from 0.4 to 0.5.
- `capture_thread.py`: revert the `cap.grab()` retry loop to a simple `read_frame()`.

These three one-line reversions give the operator an emergency knob without needing to back out the full change set.

---

## Architecture Preservation Statement

The processing pipeline order **Capture → Detect → Recognize → Resolve → Execute** (RULES §2.1) is preserved. No new module is created, no new boundary is crossed, no CP-2+ feature is added. The diff is *parameter tuning + one micro-optimization* in three existing files.