# GestureOS — RULES.md
**Version:** v2.0
**Last Updated:** 2026-07-04
**Scope:** All contributors and AI coding assistants working on the GestureOS codebase
**Source of Truth:** Architecture Freeze Specification v1.0 (2026-07-04)

---

## Overview

These rules govern code generation, architectural decisions, and module interactions for GestureOS. They are binding for all human contributors and AI assistants. Rules are grouped by domain. Violations will be flagged in code review.

GestureOS V1 ships a modular, AI-assisted static gesture recognition pipeline using Google's MediaPipe Gesture Recognizer as the primary engine with custom geometric fallback for the gestures the MediaPipe model does not cover. V2 extends this with a Dynamic Gesture Engine for temporal/motion-based gestures.

All ML inference runs on-device (local-only, CPU-first, no cloud, no telemetry). Approved on-device models are governed by the ML Governance rules in Section 13.

---

## Section 1 — Platform Rules

**1.1** GestureOS targets **Windows 10/11 only** in V1. All code must be compatible with this platform.

**1.2** Do not write macOS-specific code (`AppKit`, `Quartz`, `osascript`, `NSEvent`, etc.) in V1.

**1.3** Do not write Linux-specific code (`xdotool`, `ydotool`, `X11`, `evdev`, etc.) in V1.

**1.4** OS interaction must use `pywin32`, `ctypes` (Windows), `keyboard`, or `mouse` libraries only.

**1.5** Assume `os.name == 'nt'` is always `True`. Do not add platform detection branches.

**1.6** macOS and Linux support are V2 expansion scope. Their adapter/executor interfaces may be defined in V1 code (as ABCs) but no V1 implementation may import or instantiate them.

---

## Section 2 — Architecture Rules

**2.1** The processing pipeline is strictly ordered:

```
Camera Module
  → Hand Landmarker (MediaPipe)
  → Hand Identity Module
  → Occlusion Handler
  → Hand Scale Estimator
  → Primary Hand Filter
  → Motion History Service
  → Static Gesture Engine
  → Gesture Gate (Stability + Cooldown)
  → Gesture Fuser
  → Activation Gate
  → Command Router
  → Action Executor
```

No stage may invoke a later stage directly. Data flows one way; cross-stage communication is via the data objects defined in TRD §6.

**2.2** Each module has a single responsibility. See the module boundary table in the AI Development Guide.

**2.3** `static_gesture_engine.py` must not import from `command_router.py` or `action_executor.py` and must not call any OS API.

**2.4** `hand_landmarker.py` must not import from `static_gesture_engine.py`, `gesture_fuser.py`, or `command_router.py`.

**2.5** `camera_module.py` must not import from any other pipeline module.

**2.6** `config.py` must contain only constants and configuration data. No logic, no imports from pipeline modules.

**2.7** `gesture_fuser.py` must not call OS APIs and must not perform gesture classification. Its sole responsibility is fusing/selecting among already-classified gesture signals.

**2.8** `command_router.py` must not call OS APIs directly. It builds `Action` objects; the `action_executor.py` is the only module permitted to dispatch them.

**2.9** `model_manager.py` is the sole owner of all ML model handles. No other component may load, cache, or unload ML models.

**2.10** `extension_registry.py` is the sole mechanism for registering and querying extension point implementations. Hard-coded dispatch to concrete classes is forbidden outside the registry.

---

## Section 3 — Configuration Rules

**3.1** All numeric thresholds, ratios, distances, and timing values must be defined as named constants in `config.py`.

**3.2** No magic numbers are permitted inline in any module. Violations will be rejected at review.

**3.3** Constant names must be descriptive and uppercase with underscores (e.g., `PINCH_DISTANCE_THRESHOLD`).

**3.4** Adding a new constant to `config.py` does not require a version bump to this file.

**3.5** ML model-related configuration (model file paths, confidence thresholds, model version) must be defined in `config.py` and consumed only via `model_manager.py`.

---

## Section 4 — GestureFuser Rules

**4.1** `GestureFuser` is the sole authority for resolving conflicts between multiple gesture signals per hand per frame.

**4.2** `GestureFuser` must not be bypassed. All multi-signal scenarios must route through it.

**4.3** `GestureFuser` must not import from `command_router.py` or `action_executor.py`.

**4.4** `GestureFuser` must not perform landmark analysis or geometric computation. It operates on pre-classified `GestureResult` objects only.

**4.5** V1 resolution logic is pass-through (single-engine input). V2 resolution logic must be deterministic. Given the same inputs, `GestureFuser` must always produce the same output.

**4.6** All priority rules used by `GestureFuser` must be documented in `config.py` or inline docstrings — not implicit in code logic.

**4.7** Inputs passed to `GestureFuser` are **immutable**. The fuser and all functions it calls must treat gesture objects, landmark arrays, and signal lists as read-only. If a transformation is required, produce a new object; never mutate the original.

---

## Section 5 — Recognition Pipeline Rules

**5.1** Static gesture recognition in V1 uses Google's MediaPipe Gesture Recognizer as the primary engine, supplemented by approved geometric fallback recognizers for gestures the MediaPipe model does not cover (Pinch, Three Fingers, OK Sign). No other ML model is permitted in V1.

**5.2** All geometric fallback recognition must be based on normalized MediaPipe landmark coordinates.

**5.3** Custom fallback recognition functions must live in `static_gesture_engine.py` and must use shared primitives from `gesture_utils.py`.

**5.4** A gesture may only be emitted by `static_gesture_engine.py` after all required conditions are confirmed (no partial gesture emission).

**5.5** Each gesture type must correspond to a named class or constant — no anonymous gesture dictionaries.

**5.6** **Multi-Signal Gesture Recognition.** Every custom fallback recognizer must combine multiple independent geometric features (finger joint angles, finger states, relative landmark distances, palm orientation) rather than relying on a single metric. MediaPipe model results are trusted on their own confidence.

**5.7** **Scale-Invariance.** All custom fallback recognition must not depend on absolute pixel measurements. All geometric analysis must use normalized landmark coordinates, relative (inter-landmark) measurements, and scale-independent calculations. Recognition behavior must remain consistent regardless of the user's distance from the camera.

**5.8** **Recognition Confidence.** The Static Gesture Engine assigns a confidence score to each emitted `GestureResult`. MediaPipe results use the model's reported confidence. Custom fallback results use the existing deterministic geometric formula. The `GestureFuser` and `Command Router` use confidence scores together with priority rules.

**5.9** Dynamic gesture recognition (V2) will use a lightweight temporal model operating on MediaPipe landmark sequences. Candidate architectures: LSTM, GRU, 1D CNN. Final model selection occurs during V2 implementation after benchmarking. ViT and image-based architectures are not approved for V2.

---

## Section 6 — Multi-Signal and Temporal Rules

**6.1** Gestures that require temporal validation (e.g., hold-to-confirm) must track state across frames using a dedicated state object, not global variables.

**6.2** Frame-to-frame state must not be stored in function arguments or return values. Use explicit state containers.

**6.3** The `Motion History Service` is the sole store of per-hand temporal landmark history. Static and Dynamic engines (when present) read from it; no component maintains its own private temporal cache.

**6.4** No gesture may trigger an OS action faster than the minimum debounce interval defined in `config.py`.

**6.5** Temporal state must be reset when the hand leaves the frame or detection confidence drops below threshold.

**6.6** Multi-hand scenarios must be handled by per-role processing and the `GestureFuser`, not by individual gesture recognizers.

**6.7** Gesture recognizers must not read or write temporal state belonging to a different gesture type.

**6.8** When multiple signals are present simultaneously, the `GestureFuser` **must** apply its full resolution logic. Emitting any signal without consulting the fuser — even when only one signal appears active — is prohibited.

---

## Section 7 — Command Router and Executor Rules

**7.1** `ActionExecutor` is the only module permitted to call OS-level APIs or dispatch system input events.

**7.2** All executable actions must be defined as named functions in `ActionExecutor`. No inline OS calls in other modules.

**7.3** `ActionExecutor` must validate that inputs are within safe ranges before dispatching. No raw pass-through of unvalidated gesture data.

**7.4** Actions that could cause irreversible OS state changes (e.g., file deletion, shutdown) are prohibited unless explicitly scoped in the PRD.

**7.5** `CommandRouter` is the only module that resolves a `GestureResult` to an `Action`. The `ActionExecutor` does not perform mapping; it only dispatches.

**7.6** The V1 `WindowsExecutor` is the only executor implementation permitted in V1. macOS and Linux executors are V2 scope.

---

## Section 8 — File and Module Creation Rules

**8.1** New modules may only be created if they fit within the established pipeline architecture. Propose the module and its responsibility before creating it.

**8.2** Do not create catch-all utility files (`utils.py`, `helpers.py`) without explicit approval. Utilities must be scoped to a specific domain.

**8.3** Test files must mirror the module they test: `test_static_gesture_engine.py` tests `static_gesture_engine.py`, etc.

**8.4** Do not create `__init__.py` files in module directories unless the package structure explicitly requires it.

**8.5** **Do not create `macos_executor.py`, `linux_executor.py`, `macos_adapter.py`, `linux_adapter.py`, or any file whose name or purpose implies a non-Windows platform target in V1.** GestureOS is Windows-only in V1. Such files are prohibited unconditionally and will be deleted on sight. (V2 will create these as part of cross-platform expansion.)

**8.6** Do not create ML model files, training scripts, or model-loading code outside of `model_manager.py` and the model storage directory. No component other than `ModelManager` may load, unload, or manage ML model handles.

**8.7** Do not create hot-loadable plugin systems, dynamic import mechanisms, or filesystem-based discovery code in V1. V1 uses code-level extension via the `ExtensionRegistry` only.

---

## Section 9 — Logging and Debugging Rules

**9.1** Use the `logging` module exclusively. `print()` statements are prohibited in committed code.

**9.2** Log levels must be appropriate: `DEBUG` for frame-by-frame data, `INFO` for lifecycle events, `WARNING` for recoverable errors, `ERROR` for failures.

**9.3** Do not log raw landmark arrays at `INFO` level or above — this creates unreadable output in production logs.

**9.4** All ML inference events (model loaded, model fallback activated, inference timeout, inference error) must be logged through the `DiagnosticsManager` structured helpers at the correct level.

---

## Section 10 — Checkpoint Discipline

**10.1** Code must not implement features beyond the current active checkpoint.

**10.2** If a task requires functionality from a future checkpoint (including any V2 component), stop and flag it rather than implementing it early.

**10.3** Each checkpoint must be completable and testable in isolation before proceeding to the next.

**10.4** **Documentation Synchronization.** If implementation reveals that requirements in the PRD, TRD, Implementation Plan, or AI Development Guide are missing, incorrect, or incomplete, the AI must stop and report the required documentation updates before continuing implementation. Code and documentation must remain synchronized at all times.

---

## Section 11 — Implementation Reporting

**11.1** **Pre-Implementation Report.** Before starting any non-trivial implementation task, the AI must produce a pre-implementation report containing at minimum: Objective, Current checkpoint, Files to be modified, PRD references, TRD references, Dependencies, Risks, Validation strategy, Rollback strategy.

**11.2** **Post-Implementation Report.** After completing an implementation task, the AI must produce a post-implementation report containing: Summary of implemented changes, Files modified, Dependencies added/removed/updated, Technical issues encountered, Tests performed, Known limitations, Required documentation updates, Readiness for the next checkpoint.

---

## Section 12 — Performance Rules

**12.1** **Frame-Loop Efficiency.** The AI must avoid unnecessary allocations, redundant calculations, and other expensive operations inside the real-time frame-processing loop. Invariant work must be cached or moved outside the processing loop whenever practical. Frame-loop hot paths must remain allocation-light and free of repeated work that does not change between frames.

**12.2** **ML Inference Cost.** MediaPipe Gesture Recognizer inference runs on the CaptureThread. Per-frame inference must not exceed the per-frame latency budget (TRD §15). If profiling shows the budget is exceeded, an alternating-frame inference strategy (skip every other frame for recognizer while landmarker runs every frame) is the prescribed mitigation.

---

## Section 13 — ML Governance Rules

**13.1** V1 permits exactly one ML model in production: Google's MediaPipe Gesture Recognizer. No other ML model may be added in V1.

**13.2** All ML models must be loaded, cached, and unloaded exclusively by `ModelManager`. No other component may instantiate or hold a reference to a model object.

**13.3** All ML inference must run on-device (CPU). No cloud inference, no remote model serving, no network calls related to model execution.

**13.4** All ML inference is deterministic given the same input. Stochastic inference (dropout at inference time, sampling, etc.) is prohibited.

**13.5** If the primary ML model (MediaPipe Gesture Recognizer) fails to load or is unavailable, the Static Gesture Engine MUST fall back to custom geometric recognizers for the uncovered gestures (Pinch, Three Fingers, OK Sign). For MediaPipe-covered gestures, the custom fallbacks are not implemented; in that case, those gestures are unavailable, and a clear user-visible warning is shown via the overlay.

**13.6** Model files must be bundled with the application at packaging time. Runtime model downloads are prohibited in V1.

**13.7** V2 will introduce a Dynamic Gesture Engine. V2 candidate architectures are: LSTM, GRU, 1D CNN — all operating on MediaPipe landmark sequences. Final model selection occurs during V2 implementation after benchmarking. Image-based architectures (ViT, CNN on raw pixels) are not approved for V2.

**13.8** No ML model may be trained, fine-tuned, or have its weights updated at runtime in V1 or V2. Models are static, versioned, and bundled.

**13.9** ML inference must not perform any I/O outside the model itself (no logging of model internals, no telemetry, no metrics uploads).

---

## Section 14 — Extension System Rules

**14.1** All extension points in V1 are code-level interfaces (Python ABCs in `ext/base.py`).

**14.2** All built-in extension implementations (MediaPipe recognizer, custom fallbacks, Windows executor, Windows context adapter) must be registered via `ExtensionRegistry` at application startup.

**14.3** No hot-loading, no filesystem-based discovery, no dynamic plugin installation in V1. These are V2 features.

**14.4** Extension points are defined in the AI Development Guide §5 and TRD §3. Adding a new extension point requires updating the Architecture Freeze Specification via a formal Architecture Change Request.

**14.5** Each extension implementation must implement its declared ABC fully. Partial implementations are prohibited.

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-06-20 | Initial release |
| v1.1 | 2026-06-26 | Added Rule 4.7 (ConflictResolver input immutability); Rule 6.8; Rule 8.5 |
| v1.2 | 2026-06-26 | Added Rules 5.6/5.7 (multi-feature, scale-invariance); 10.4; 11.x; 12.x |
| v2.0 | 2026-07-04 | Architecture rewrite per Architecture Freeze Specification v1.0. Renamed pipeline stages to match new architecture (HandLandmarker, StaticGestureEngine, GestureGate, GestureFuser, CommandRouter, ActionExecutor, MotionHistoryService). Removed blanket ML prohibition; added ML Governance (Section 13) permitting MediaPipe Gesture Recognizer only. Added Extension System rules (Section 14). Added ModelManager exclusivity (2.9/8.6). Updated all cross-references to use new component names. |
