# GestureOS — RULES.md
**Version:** v1.2
**Last Updated:** 2026-06-26
**Scope:** All contributors and AI coding assistants working on the GestureOS codebase

---

## Overview

These rules govern code generation, architectural decisions, and module interactions for GestureOS. They are binding for all human contributors and AI assistants. Rules are grouped by domain. Violations will be flagged in code review.

---

## Section 1 — Platform Rules

**1.1** GestureOS targets **Windows 10/11 only**. All code must be compatible with this platform.

**1.2** Do not write macOS-specific code (`AppKit`, `Quartz`, `osascript`, `NSEvent`, etc.).

**1.3** Do not write Linux-specific code (`xdotool`, `ydotool`, `X11`, `evdev`, etc.).

**1.4** OS interaction must use `pywin32`, `ctypes` (Windows), `keyboard`, or `mouse` libraries only.

**1.5** Assume `os.name == 'nt'` is always `True`. Do not add platform detection branches.

---

## Section 2 — Architecture Rules

**2.1** The processing pipeline is strictly ordered: **Capture → Detect → Recognize → Resolve → Execute**. No stage may invoke a later stage directly.

**2.2** Each module has a single responsibility. See the module boundary table in the AI Development Guide.

**2.3** `recognizer.py` must not import from `executor.py` or call any OS API.

**2.4** `detector.py` must not import from `recognizer.py`, `conflict_resolver.py`, or `executor.py`.

**2.5** `capture.py` must not import from any other pipeline module.

**2.6** `config.py` must contain only constants and configuration data. No logic, no imports from pipeline modules.

**2.7** `conflict_resolver.py` must not call OS APIs and must not perform gesture recognition. Its sole responsibility is arbitrating between concurrent gesture signals.

---

## Section 3 — Configuration Rules

**3.1** All numeric thresholds, ratios, distances, and timing values must be defined as named constants in `config.py`.

**3.2** No magic numbers are permitted inline in any module. Violations will be rejected at review.

**3.3** Constant names must be descriptive and uppercase with underscores (e.g., `PINCH_DISTANCE_THRESHOLD`).

**3.4** Adding a new constant to `config.py` does not require a version bump to this file.

---

## Section 4 — ConflictResolver Rules

**4.1** `ConflictResolver` is the sole authority for resolving conflicts between concurrent gesture signals.

**4.2** `ConflictResolver` must not be bypassed. All multi-gesture scenarios must route through it.

**4.3** `ConflictResolver` must not import from `executor.py`.

**4.4** `ConflictResolver` must not perform landmark analysis or geometric computation. It operates on pre-classified gesture signals only.

**4.5** Resolution logic must be deterministic. Given the same inputs, `ConflictResolver` must always produce the same output.

**4.6** All priority rules used by `ConflictResolver` must be documented in `config.py` or inline docstrings — not implicit in code logic.

**4.7** Inputs passed to `ConflictResolver` are **immutable**. The resolver and all functions it calls must treat gesture objects, landmark arrays, and signal lists as read-only. If a transformation is required, produce a new object; never mutate the original.

---

## Section 5 — Recognition Pipeline Rules

**5.1** Gesture recognition must be fully deterministic and rule-based. No ML model inference, no probabilistic classifiers.

**5.2** All geometric analysis must be based on normalized MediaPipe landmark coordinates.

**5.3** Finger extension, curl, and angle calculations must live in `recognizer.py` or a dedicated geometry utility module.

**5.4** A gesture may only be emitted by `recognizer.py` after all required conditions are confirmed (no partial gesture emission).

**5.5** Each gesture type must correspond to a named class or constant — no anonymous gesture dictionaries.

**5.6** **Multi-Feature Gesture Recognition.** Gesture recognition must be derived from multiple geometric features rather than relying on a single metric. Acceptable features include, but are not limited to: finger joint angles, finger states (extended, curled, partially bent), relative landmark distances, palm orientation, and motion history. Single-metric recognition should be avoided whenever a multi-feature approach provides greater robustness.

**5.7** **Scale-Invariance.** Gesture recognition must not depend on absolute pixel measurements. All geometric analysis must use normalized landmark coordinates, relative (inter-landmark) measurements, and scale-independent calculations. Recognition behavior must remain consistent regardless of the user's distance from the camera.

**5.8 Recognition Confidence**

Gesture recognizers shall assign a deterministic confidence score to each candidate gesture.
Confidence scoring must be explainable and derived from rule-based geometric analysis.
ConflictResolver shall use confidence scores together with configured priority rules when selecting the final gesture.

---

## Section 6 — Multi-Signal and Temporal Rules

**6.1** Gestures that require temporal validation (e.g., hold-to-confirm) must track state across frames using a dedicated state object, not global variables.

**6.2** Frame-to-frame state must not be stored in function arguments or return values. Use explicit state containers.

**6.3** Velocity-based gestures (e.g., swipe) must derive velocity from the delta of normalized landmark positions across consecutive frames.

**6.4** No gesture may trigger an OS action faster than the minimum debounce interval defined in `config.py`.

**6.5** Temporal state must be reset when the hand leaves the frame or detection confidence drops below threshold.

**6.6** Multi-hand scenarios must be handled by `ConflictResolver`, not by individual gesture recognizers.

**6.7** Gesture recognizers must not read or write temporal state belonging to a different gesture type.

**6.8** When multiple signals are present simultaneously, `ConflictResolver` **must** apply the full priority resolution logic defined in `config.py`. Emitting any signal without consulting the resolver — even when only one signal appears active — is prohibited. Single-signal pass-through is not a valid shortcut; all signals must flow through the resolver's decision path.

---

## Section 7 — Executor Rules

**7.1** `executor.py` is the only module permitted to call OS-level APIs or dispatch system input events.

**7.2** All executable actions must be defined as named functions in `executor.py`. No inline OS calls in other modules.

**7.3** `executor.py` must validate that inputs are within safe ranges before dispatching. No raw pass-through of unvalidated gesture data.

**7.4** Actions that could cause irreversible OS state changes (e.g., file deletion, shutdown) are prohibited unless explicitly scoped in the PRD.

---

## Section 8 — File and Module Creation Rules

**8.1** New modules may only be created if they fit within the established pipeline architecture. Propose the module and its responsibility before creating it.

**8.2** Do not create catch-all utility files (`utils.py`, `helpers.py`) without explicit approval. Utilities must be scoped to a specific domain.

**8.3** Test files must mirror the module they test: `test_recognizer.py` tests `recognizer.py`, etc.

**8.4** Do not create `__init__.py` files in module directories unless the package structure explicitly requires it.

**8.5** **Do not create `macos_executor.py`, `linux_executor.py`, `macos_adapter.py`, `linux_adapter.py`, or any file whose name or purpose implies a non-Windows platform target.** GestureOS is Windows-only. Such files are prohibited unconditionally and will be deleted on sight.

---

## Section 9 — Logging and Debugging Rules

**9.1** Use the `logging` module exclusively. `print()` statements are prohibited in committed code.

**9.2** Log levels must be appropriate: `DEBUG` for frame-by-frame data, `INFO` for lifecycle events, `WARNING` for recoverable errors, `ERROR` for failures.

**9.3** Do not log raw landmark arrays at `INFO` level or above — this creates unreadable output in production logs.

---

## Section 10 — Checkpoint Discipline

**10.1** Code must not implement features beyond the current active checkpoint.

**10.2** If a task requires functionality from a future checkpoint, stop and flag it rather than implementing it early.

**10.3** Each checkpoint must be completable and testable in isolation before proceeding to the next.

**10.4** **Documentation Synchronization.** If implementation reveals that requirements in the PRD, TRD, Implementation Plan, or AI Development Guide are missing, incorrect, or incomplete, the AI must stop and report the required documentation updates before continuing implementation. Code and documentation must remain synchronized at all times.

---

## Section 11 — Implementation Reporting

**11.1** **Pre-Implementation Report.** Before starting any non-trivial implementation task, the AI must produce a pre-implementation report containing at minimum the following sections:
- Objective
- Current checkpoint
- Files to be modified
- PRD references
- TRD references
- Dependencies
- Risks
- Validation strategy
- Rollback strategy

**11.2** **Post-Implementation Report.** After completing an implementation task, the AI must produce a post-implementation report containing at minimum the following sections:
- Summary of implemented changes
- Files modified
- Dependencies added, removed, or updated
- Technical issues encountered
- Tests performed
- Known limitations
- Required documentation updates
- Readiness for the next checkpoint

---

## Section 12 — Performance Rules

**12.1** **Frame-Loop Efficiency.** The AI must avoid unnecessary allocations, redundant calculations, and other expensive operations inside the real-time frame-processing loop. Invariant work must be cached or moved outside the processing loop whenever practical. Frame-loop hot paths must remain allocation-light and free of repeated work that does not change between frames.

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-06-20 | Initial release |
| v1.1 | 2026-06-26 | Added Rule 4.7 (ConflictResolver input immutability); Rule 6.8 (Multi-Signal discipline — full resolver path required, no single-signal pass-through); Rule 8.5 (prohibition on macOS/Linux executor and adapter file creation); module boundary for `conflict_resolver.py` clarified in Rules 2.7 and 4.4 |
| v1.2 | 2026-06-26 | Added Rule 5.6 (Multi-Feature Gesture Recognition — require multiple geometric features, avoid single-metric recognition); Rule 5.7 (Scale-Invariance — prohibit absolute pixel measurements, require normalized/relative/scale-independent calculations); Rule 10.4 (Documentation Synchronization — AI must stop and report missing/incorrect docs before continuing); new Section 11 (Implementation Reporting — mandatory Pre-Implementation and Post-Implementation reports with required sections); new Section 12 (Performance Rules — Frame-Loop Efficiency, avoid unnecessary allocations and redundant calculations inside the real-time processing loop) |
