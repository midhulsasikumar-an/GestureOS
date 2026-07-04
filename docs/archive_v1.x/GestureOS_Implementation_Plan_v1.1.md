# Implementation Plan — GestureOS

**Document Type:** Implementation Plan (Execution Roadmap)
**Source Documents:** GestureOS PRD v1.3 (product source of truth), GestureOS TRD v1.2 (technical source of truth)
**Version:** 1.1.0
**Audience:** Engineering team, AI coding agents, project management
**Date:** June 2026
**Changes in v1.1:** Re-scoped Checkpoints 5, 6, and 10 to Windows-primary per PRD v1.3 §1.2 (macOS/Linux deferred to Future Expansion, no longer in-scope deliverables for the initial release); added `ConflictResolver` to Checkpoint 3's deliverables per PRD §4.6/TRD §3.9.1; added Multi-Signal Recognition documentation requirement to Checkpoint 3 per PRD §4.5; added explicit Reference Hardware Baseline citation to Checkpoint 9 per PRD §16.1.

> **Traceability Notice:** Every checkpoint, module, file, and requirement in this plan is derived directly from PRD v1.3 and TRD v1.2. No new features, architecture decisions, or requirements have been introduced. Where the source documents are silent on an implementation-sequencing detail, this is explicitly marked as a **GAP** rather than filled in with an invented requirement. This plan re-sequences the PRD's 7 product checkpoints (CP-1–CP-7) into 11 engineering checkpoints (Checkpoint 0–10) to match the granularity needed for AI-assisted, file-level execution — the **Checkpoint Cross-Reference Table** in Section 3.1 maps every engineering checkpoint back to its PRD/TRD origin so this re-sequencing is fully auditable.

---

## Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [Development Strategy](#2-development-strategy)
3. [Checkpoint Structure](#3-checkpoint-structure)
4. [Checkpoint 0 — Project Foundation](#4-checkpoint-0--project-foundation)
5. [Checkpoint 1 — GestureOS Core Platform](#5-checkpoint-1--gestureos-core-platform)
6. [Checkpoint 2 — Hand Analysis Layer](#6-checkpoint-2--hand-analysis-layer)
7. [Checkpoint 3 — Gesture Recognition Layer](#7-checkpoint-3--gesture-recognition-layer)
8. [Checkpoint 4 — Activation Layer](#8-checkpoint-4--activation-layer)
9. [Checkpoint 5 — Action Layer](#9-checkpoint-5--action-layer)
10. [Checkpoint 6 — Context Engine](#10-checkpoint-6--context-engine)
11. [Checkpoint 7 — GUI Layer](#11-checkpoint-7--gui-layer)
12. [Checkpoint 8 — Diagnostics Layer](#12-checkpoint-8--diagnostics-layer)
13. [Checkpoint 9 — Testing & Optimization](#13-checkpoint-9--testing--optimization)
14. [Checkpoint 10 — Packaging & Deployment](#14-checkpoint-10--packaging--deployment)
15. [Risk Management](#15-risk-management)
16. [Definition of Done](#16-definition-of-done)

---

## 1. Executive Overview

### 1.1 Project Summary

GestureOS is a desktop application that acts as an intelligent gesture-based operating layer between the user and the operating system, enabling touchless control via webcam-based hand gesture recognition (PRD §1–2). Recognition is 100% rule-based geometric analysis of MediaPipe hand landmarks — no trained ML models (PRD §4, TRD §1.1). As of PRD v1.2, recognition is additionally **scale-invariant**, meaning gesture accuracy does not degrade as the user's distance from the camera changes (PRD §5–6).

This Implementation Plan sequences the build of GestureOS into 11 checkpoints (Checkpoint 0 through Checkpoint 10), each producing a working, testable increment of the system. The plan is designed for execution by AI coding agents working checkpoint-by-checkpoint, with each checkpoint's Definition of Done acting as a hard gate before the next checkpoint begins.

### 1.2 Development Philosophy

- **Foundation before features.** The capture-and-recognition pipeline (camera → tracking → analysis → recognition) must exist and be provably correct before any action-dispatch or UI work begins, because every later checkpoint consumes the data objects this pipeline produces (Section 2).
- **One source of truth per concern.** The PRD defines *what* and *why*; the TRD defines *how*. This plan adds *when* and *in what order* — it does not redefine requirements or architecture from either source document.
- **Testable increments, not a big-bang integration.** Every checkpoint ends in a runnable, demonstrable state (even if headless or developer-only), per the checkpoint structure already established in PRD §14 and reaffirmed here at finer granularity.
- **Configuration over hardcoding, enforced from Checkpoint 0.** Because TRD §1.1 establishes "configuration over code" as a core engineering principle, the JSON configuration system (TRD §7) is built in Checkpoint 0, not bolted on later — every checkpoint after it reads from, rather than hardcodes, its tunable parameters.

### 1.3 Core Principles

1. **No checkpoint begins before its dependencies' Definition of Done is met.** Dependencies are explicit per checkpoint (Section 3).
2. **No raw-pixel or raw-frame-normalized thresholds anywhere in gesture logic**, per the TRD §4.3 code-review rule — this is enforced starting at Checkpoint 2 and audited at every checkpoint touching `gestures/`.
3. **Every component built must match its TRD §3 specification exactly** — Responsibilities, Inputs, Outputs, Dependencies, and Error Handling are not subject to reinterpretation during implementation.
4. **Every functional requirement (FR-*) in the PRD must be traceable to at least one checkpoint's Deliverables.** Section 3.2 provides this traceability matrix.
5. **Privacy and local-only processing (PRD §8.4 NFR / TRD §14) is structural from the start** — no network-capable imports are introduced in any checkpoint touching the core pipeline.

### 1.4 Definition of Success

GestureOS implementation is successful when:

- All 11 checkpoints (Section 3) have met their individual Definition of Done
- All PRD v1.2 functional requirements (FR-*) and non-functional requirements (NFR-*) are implemented and verified
- All PRD v1.2 Success Metrics (PRD §21.1) are met on reference hardware
- The Project Definition of Done (Section 16.3) is satisfied
- A packaged, installable build exists for Windows, macOS, and Linux per PRD §20 / TRD §12

---

## 2. Development Strategy

### 2.1 Foundation-First Approach

This plan follows a strict bottom-up build order:

```
Camera
  ↓
Tracking            (MediaPipe landmark detection)
  ↓
Analysis            (finger states, angles, distances, scale, motion history)
  ↓
Recognition         (gesture rules consuming Analysis output)
  ↓
Activation           (gates whether Recognition output reaches Actions)
  ↓
Actions             (OS dispatch: cursor, mouse, keyboard, system)
  ↓
Context             (resolves which mapping applies before Action dispatch)
  ↓
GUI                  (Settings, Profiles, Calibration — operate on everything above)
```

### 2.2 Why This Order Is Mandatory, Not Arbitrary

Each layer in this chain consumes the data objects produced by the layer above it, per the data-object lifecycle defined in TRD §2.3 and §6.6. Building out of order means building against data that doesn't exist yet, or building UI for behavior that can't be verified.

| Layer | Why It Must Come Before the Next Layer |
|---|---|
| **Camera → Tracking** | Tracking (`TrackingModule`) consumes `np.ndarray` frames from `CameraModule` (TRD §3.1, §3.3). There is no landmark data to analyze without a working capture loop first. |
| **Tracking → Analysis** | The Hand Analysis Layer (`HandScaleEstimator`, finger-angle math, `HandIdentityModule`, `OcclusionHandler`) all consume `HandData.landmarks` (TRD §6.1). None of these can be meaningfully implemented or tested against synthetic data until the real shape and noise characteristics of MediaPipe output are understood from Checkpoint 1. |
| **Analysis → Recognition** | Every gesture rule in `gestures/static_recognizer.py` and `dynamic_recognizer.py` requires `HandData.scale` (TRD §3.7) to be populated for scale-invariant normalization (PRD §5, TRD §4). Building gesture rules before scale estimation exists would force raw-pixel thresholds — the exact anti-pattern PRD §5 and TRD §4.3 explicitly forbid. |
| **Recognition → Activation** | `ActivationGate.feed_gesture()` (TRD §5.3) consumes gesture names that have already passed `StabilityFilter` (TRD §16, Technical Risk row 3). Activation logic cannot be correctly tested without real gesture candidates to gate. |
| **Activation → Actions** | The Action Layer only ever receives a `GestureResult` once it has cleared Activation (PRD §10, pipeline stage 9 "Activation Check"). Building cursor/mouse/keyboard dispatch before the gate exists risks building and testing against ungated, noisy gesture data. |
| **Actions → Context** | `ActionEngine.resolve()` needs both Action dispatch (the executor side) and a context string (TRD §3.13). Context resolution is independent of Action dispatch internals, but the mapping *consumer* (ActionEngine) must exist first so Context Engine has something to feed. |
| **Context → GUI** | `ui/mapping_editor.py`, `ui/settings_panel.py`, and `ui/calibration_wizard.py` all visualize or configure behavior of every layer below — Settings tune Recognition/Activation/Actions, Mapping Editor configures Context+Action pairs, Calibration tunes Recognition thresholds and Cursor behavior. None of this UI can be meaningfully built, let alone tested, before the systems it configures exist and behave correctly headlessly. |

### 2.3 Testing Philosophy Across the Build

Per TRD §13.1's test pyramid, every checkpoint from Checkpoint 1 onward produces unit tests using synthetic/mock data (no live camera required for unit tests — TRD §13.2), with integration tests added once a full vertical slice of the pipeline exists (from Checkpoint 4 onward, once Activation closes the loop from Camera to Action dispatch). Performance testing (FPS/CPU/memory budgets, PRD §16) is deferred to Checkpoint 9 by design — measuring performance against an incomplete pipeline produces numbers that will need to be re-measured anyway once all stages are present.

### 2.4 Configuration and Logging as Cross-Cutting Concerns

`SettingsManager` (TRD §3.16, §7) and `DiagnosticsManager` (TRD §3.16, §9) are **not** a checkpoint of their own beyond their initial scaffolding in Checkpoint 0 — every other checkpoint extends their schemas and logging categories as it introduces new tunable parameters or events. This mirrors how the TRD itself treats these as cross-cutting components rather than pipeline stages (TRD §2.1 pipeline diagram does not list Settings/Diagnostics as numbered stages — they are read/written from every stage).

---

## 3. Checkpoint Structure

### 3.1 Checkpoint Cross-Reference Table

This plan's 11 checkpoints (Checkpoint 0–10) map to the PRD's 7 product checkpoints (CP-1–CP-7, PRD §14) as follows. This re-sequencing exists because the PRD's checkpoints are scoped at product-deliverable granularity, while AI-assisted file-level execution benefits from finer-grained, single-responsibility checkpoints. No PRD checkpoint content is added or removed — only re-partitioned.

| This Plan | PRD Checkpoint(s) | Rationale for Split/Mapping |
|---|---|---|
| Checkpoint 0 — Project Foundation | *(precedes CP-1; implied prerequisite, not explicitly numbered in PRD — see Gap G-1)* | Repo/config/logging/testing scaffolding has no dedicated PRD checkpoint. **GAP:** PRD §14 begins numbering at CP-1 and assumes foundational scaffolding exists; this plan makes it explicit as Checkpoint 0. |
| Checkpoint 1 — Core Platform | CP-1 (Core Hand Tracking) | Direct 1:1 mapping. |
| Checkpoint 2 — Hand Analysis Layer | CP-2 (Gesture Recognition), analysis portion only | PRD's CP-2 bundles analysis (finger states, scale) and recognition (gesture rules) together. This plan splits them because TRD §3 treats them as distinct component groups with a clean data-object boundary (`HandData` fully populated → `GestureResult`). |
| Checkpoint 3 — Gesture Recognition Layer | CP-2 (Gesture Recognition), recognition portion + stability/cooldown **+ ConflictResolver (PRD §4.6, added v1.1)** | Second half of PRD CP-2, isolated per the same rationale. Updated in v1.1 to include `ConflictResolver` and the Multi-Signal Recognition documentation requirement (PRD §4.5). |
| Checkpoint 4 — Activation Layer | CP-2 (Gesture Recognition), activation gate portion | PRD groups Activation Gate under CP-2's "activation gate" deliverable; this plan isolates it because Activation is architecturally a gate between Recognition and Actions (TRD §2.1), not part of recognition itself. |
| Checkpoint 5 — Action Layer | CP-3 (System Control) | Direct mapping, includes CursorController (TRD §3.14) per PRD §8.4/§8.5. **Re-scoped in v1.1: Windows executor only; macOS/Linux executors deferred to Future Expansion (PRD §1.2).** |
| Checkpoint 6 — Context Engine | CP-4 (Context-Aware Engine) | Direct 1:1 mapping, includes Context Verification Layer (PRD §8.7.3). **Re-scoped in v1.1: WindowsContextAdapter only; macOS/Linux adapters deferred to Future Expansion (PRD §1.2).** |
| Checkpoint 7 — GUI Layer | CP-5 (GUI and Profiles) | Direct mapping, includes Calibration Wizard (PRD §15, new in v1.2). |
| Checkpoint 8 — Diagnostics Layer | CP-6 (Robustness), diagnostics portion | PRD's CP-6 bundles occlusion/primary-hand/lighting robustness with diagnostics; this plan isolates the diagnostics/logging/debug-overlay portion here since it's cross-cutting (Section 2.4) and the remaining CP-6 robustness items are distributed to the checkpoints whose components they harden (Checkpoint 2 for occlusion/primary-hand, Checkpoint 1 for camera/lighting validation). |
| Checkpoint 9 — Testing & Optimization | CP-7 (Optimization & Release), testing portion | Direct mapping for the testing/performance half of PRD CP-7. **Updated in v1.1: Acceptance Criteria now cite PRD §16.1 Reference Hardware Baseline explicitly.** |
| Checkpoint 10 — Packaging & Deployment | CP-7 (Optimization & Release), packaging portion | Direct mapping for the packaging/deployment half of PRD CP-7, per PRD §20 Deployment Requirements. **Re-scoped in v1.1: Windows artifact only for initial release; macOS/Linux packaging deferred to Future Expansion (PRD §1.2).** |

### 3.2 Functional Requirement Traceability Matrix

This matrix confirms every PRD functional-requirement group is covered by at least one checkpoint. It is a coverage check, not a duplicate of the PRD itself.

| PRD Requirement Group | Primary Checkpoint(s) |
|---|---|
| FR-HT-01–07 (Hand Tracking) | Checkpoint 1 |
| FR-HT-08–12 (Hand Identity) | Checkpoint 2 |
| FR-OC-01–03 (Occlusion Handling) | Checkpoint 2 |
| FR-PH-01–03 (Primary Hand Selection) | Checkpoint 2 |
| FR-SC-01–04 (Hand Scale Estimation) | Checkpoint 2 |
| FR-MH-01–04 (Motion History Buffer) | Checkpoint 2 |
| Gesture rules (PRD §4 static + dynamic) | Checkpoint 3 |
| FR-MS-01–03 (Multi-Signal Recognition, PRD §4.5) | Checkpoint 3 |
| FR-CR-01–04 (Conflict Resolution, PRD §4.6) | Checkpoint 3 |
| FR-GS-01–04 (Gesture Stability) | Checkpoint 3 |
| FR-CD-01–03 (Cooldown System) | Checkpoint 3 |
| FR-AM-01–07 (Activation Mode) | Checkpoint 4 |
| FR-CC-01–07 (Cursor Control) | Checkpoint 5 |
| System Command Engine / Windows Action Layer (PRD §8.6) | Checkpoint 5 |
| FR-CA-01–03, FR-CV-01–03 (Context Detection + Verification) | Checkpoint 6 |
| FR-GM-01–05 (Gesture Mapping Manager) | Checkpoint 7 |
| FR-CAL-01–04 (Calibration) | Checkpoint 7 |
| FR-VF-01–07 (Visual Feedback) | Checkpoint 1 (basic), Checkpoint 8 (full debug overlay) |
| FR-CV2-01–04 (Camera Validation) | Checkpoint 1 (basic), Checkpoint 8 (full warning surfacing) |
| FR-LQ-01–04 (Lighting Quality) | Checkpoint 8 |
| Performance Budgets (PRD §16.1/§16.2) | Checkpoint 9 |
| Deployment Requirements / Windows-primary (PRD §20, §1.2) | Checkpoint 10 |

### 3.3 Standard Checkpoint Template

Every checkpoint below (Sections 4–14) follows this fixed template, as requested:

- **Purpose** — why this checkpoint exists, in product/engineering terms
- **Scope** — what is explicitly in and out of scope
- **Deliverables** — concrete artifacts produced
- **Modules** — TRD §3 components implemented or extended
- **Files** — exact file paths per TRD §8 folder structure
- **Dependencies** — which prior checkpoints must be Done first
- **Risks** — checkpoint-specific risks (cross-referenced to Section 15's matrix where applicable)
- **Acceptance Criteria** — drawn from PRD checkpoint acceptance criteria (§14) where they exist, extended only where the finer-grained split requires it
- **Testing Strategy** — per TRD §13's test pyramid
- **Definition of Done** — the hard gate before the next checkpoint begins
## 4. Checkpoint 0 — Project Foundation

### Purpose

Establish the repository structure, environment, configuration system, logging framework, and testing harness that every subsequent checkpoint depends on. No gesture or product logic is implemented here — this checkpoint exists purely to make every later checkpoint buildable and testable from day one, per Core Principle 4 (configuration over hardcoding, enforced from Checkpoint 0).

### Scope

**In scope:** repository skeleton (TRD §8 folder structure), Python environment and dependency pinning, `Settings` dataclass + `SettingsManager` scaffolding (schema only — full field set grows as later checkpoints add settings), `DiagnosticsManager` scaffolding (logging pipeline only — event categories grow as later checkpoints add them), pytest configuration and fixture scaffolding, CI skeleton.

**Out of scope:** any camera, tracking, gesture, or UI code. Any component-specific settings fields beyond the foundational ones already fully specified in TRD §7.1 (these belong to the checkpoint that introduces the behavior they configure).

### Deliverables

1. Full repository skeleton matching TRD §8 exactly (all folders created, `__init__.py` placeholders where needed for Python packaging)
2. `requirements.txt` pinning all TRD §1.3 stack dependencies (Python 3.11+, OpenCV, MediaPipe, NumPy, PyQt6, PyAutoGUI, pynput, pywin32 [Windows-conditional], PyInstaller, pytest)
3. `models/data_models.py` with all dataclasses from TRD §6 stubbed (fields present, no behavior yet beyond what's needed for type-correctness)
4. `settings/settings_manager.py` implementing the `Settings` dataclass (TRD §7.2) and the load/validate/atomic-write behavior described in TRD §7.1 (the per-field-fallback validation strategy)
5. A working `~/.gestureos/settings.json` round-trip: defaults written on first run, loaded and validated on subsequent runs
6. `diagnostics/diagnostics_manager.py` and `diagnostics/log_format.py` implementing the logging pipeline (TRD §9.1) with the `RotatingFileHandler` setup and the structured log-line format — but only the foundational categories (no `camera`, `gesture`, etc. categories yet; those are added by the checkpoints that introduce those events)
7. `pytest.ini` and `tests/conftest.py` scaffolding (empty fixture file ready for later checkpoints to populate per-component fixtures)
8. A CI configuration skeleton (lint + `node -c`/`python -m py_compile`-equivalent syntax check + `pytest` invocation, even though there are close to zero tests yet)

### Modules

This checkpoint scaffolds, but does not fully implement, the following TRD §3 components:
- `SettingsManager` (TRD §3.16) — foundational schema only
- `DiagnosticsManager` (TRD §3.16) — foundational logging pipeline only

No other TRD §3 component is touched in Checkpoint 0.

### Files

```
gestureos/
├── main.py                       # stub entry point (prints version, exits — full wiring in CP1+)
├── requirements.txt
├── pyinstaller.spec               # stub, fully built out in Checkpoint 10
├── pytest.ini
├── models/
│   └── data_models.py             # all TRD §6 dataclasses stubbed
├── settings/
│   └── settings_manager.py        # Settings dataclass + load/save/validate
├── diagnostics/
│   ├── diagnostics_manager.py     # logging setup
│   └── log_format.py              # structured log-line formatting helpers
├── tests/
│   ├── conftest.py                # scaffolding only
│   └── unit/
│       └── test_settings_manager.py
└── assets/
    └── default_mappings/
        └── default.json            # placeholder, fully populated in Checkpoint 7
```

### Dependencies

None — this is the first checkpoint.

### Risks

| Risk | Mitigation |
|---|---|
| Dependency version drift across the 3 target OSes (TRD §11) causing inconsistent behavior later | Pin exact versions in `requirements.txt` now, before any OS-specific code exists, so every later checkpoint builds against an identical dependency set on all platforms |
| Settings schema designed too narrowly, requiring breaking changes later | TRD §7.2's `Settings` dataclass already reflects the full v1.2 field set (PRD §11.2) — implement the complete schema now even though most fields aren't consumed by behavior until later checkpoints, avoiding schema churn |
| Atomic-write strategy (TRD §7.1) not implemented correctly, risking corruption discovered only much later | Unit test the atomic-write/per-field-fallback behavior exhaustively in this checkpoint (Section "Testing Strategy" below) since every later checkpoint trusts this behavior implicitly |

### Acceptance Criteria

- Running `python main.py` from a clean checkout produces no import errors and exits cleanly
- `~/.gestureos/settings.json` is created with documented defaults on first run (PRD §11.2 schema)
- Corrupting a single field in `settings.json` (e.g., setting `gesture_confidence_threshold` to `5.0`, an out-of-range value) results in that field reverting to default on next load, with all other fields preserved — verifying TRD §7.1's per-field validation strategy
- A log file is created at `~/.gestureos/logs/gestureos.log` matching the format in TRD §9.1
- `pytest` runs successfully (even with a minimal test count) in CI

### Testing Strategy

Per TRD §13.2 (no live camera or hardware required for unit tests):

```python
# tests/unit/test_settings_manager.py

def test_defaults_written_on_first_run(tmp_path):
    manager = SettingsManager(config_dir=tmp_path)
    settings = manager.load()
    assert settings.gesture_confidence_threshold == 0.85  # PRD §11.2 default

def test_invalid_field_reverts_to_default_others_preserved(tmp_path):
    (tmp_path / 'settings.json').write_text(json.dumps({
        'gesture_confidence_threshold': 5.0,   # invalid: out of 0.50-0.99 range
        'camera_index': 2,                      # valid, must be preserved
    }))
    manager = SettingsManager(config_dir=tmp_path)
    settings = manager.load()
    assert settings.gesture_confidence_threshold == 0.85  # reverted to default
    assert settings.camera_index == 2                      # preserved

def test_atomic_write_survives_interruption(tmp_path, monkeypatch):
    # Simulate a crash mid-write by raising inside the temp-file-write step;
    # the original settings.json must remain valid/untouched.
    ...
```

### Definition of Done

- All Deliverables above exist and pass their unit tests
- Repository structure exactly matches TRD §8 for every folder this checkpoint is responsible for
- No component outside `models/`, `settings/`, `diagnostics/` (foundational scope only), `tests/`, and root-level config files has been created — premature creation of later checkpoints' files is itself a Checkpoint 0 failure, since it indicates scope creep
- CI pipeline is green
## 5. Checkpoint 1 — GestureOS Core Platform

### Purpose

Stand up the foundational capture-and-detection loop: a working webcam feed, MediaPipe hand landmark detection, a basic visual overlay showing detected landmarks, FPS measurement, and a minimal developer dashboard. This is the first checkpoint that produces a visibly running, demonstrable application — per PRD CP-1 acceptance criteria (PRD §14.1) and the Foundation-First rationale in Section 2.2 of this plan (Camera → Tracking must exist before anything downstream can be built).

### Scope

**In scope:** `CameraModule`, `CameraValidator` (basic FPS/resolution checks only — full sustained-warning UX is Checkpoint 8), `TrackingModule`, a minimal `OverlayEngine` showing only the raw landmark skeleton + FPS counter (full status bar with profile/context/state comes in later checkpoints once those concepts exist), the `CaptureThread`/`app/core.py` orchestration loop wiring Camera → Tracking → Overlay.

**Out of scope:** hand identity (Checkpoint 2), any gesture recognition (Checkpoint 3), activation gating (Checkpoint 4), action dispatch (Checkpoint 5), context detection (Checkpoint 6), Settings/Profiles UI (Checkpoint 7), full diagnostics/lighting detection (Checkpoint 8).

### Deliverables

1. `CameraModule` fully implemented per TRD §3.1, including the reconnect-on-disconnect behavior (10 attempts, 2s interval)
2. `CameraValidator` implemented per TRD §3.2 — startup FPS/resolution check and the rolling `measured_fps()` calculation (the *surfacing* of sustained-low-FPS warnings to the user is deferred to Checkpoint 8's overlay work; this checkpoint only needs the underlying measurement to be correct and tested)
3. `TrackingModule` fully implemented per TRD §3.3, wrapping MediaPipe Hands and producing `list[HandData]` (without `role`, `scale`, or `gesture_eligible` populated yet — those fields are populated by Checkpoint 2's components)
4. `app/core.py` and `app/capture_thread.py` implementing the `CaptureThread`/main-thread split described in TRD §2.2, wired for Camera → Tracking → (basic) Overlay only at this stage
5. A minimal `overlay/overlay_window.py` + `overlay/skeleton_renderer.py` rendering the hand skeleton over the webcam preview and an FPS counter — this is intentionally the *simplest* version of the overlay described in TRD §3.15; full status bar, gesture badges, and quality warnings are added incrementally by later checkpoints
6. A minimal developer dashboard: at this stage, "dashboard" means the FPS counter and raw landmark count visible in the overlay (PRD does not define a separate dashboard window distinct from the overlay at this checkpoint — see Gap G-2 below)

> **GAP G-2:** The requested checkpoint structure asks for a "Developer Dashboard" deliverable in Checkpoint 1, but neither PRD nor TRD defines a dashboard UI distinct from the Overlay (PRD §22.2) and the Developer Mode debug panel (PRD §12.3, TRD §9.3). This plan treats Checkpoint 1's "dashboard" as the minimal FPS/landmark-count overlay only; the full Developer Mode debug panel (landmark IDs, angles, normalized distances, motion vectors) is correctly scoped to Checkpoint 8 per TRD §9.3, since it depends on data (finger angles, hand scale, motion history) that doesn't exist until Checkpoint 2/3.

### Modules

- `CameraModule` (TRD §3.1) — new, full implementation
- `CameraValidator` (TRD §3.2) — new, startup + rolling FPS measurement only
- `TrackingModule` (TRD §3.3) — new, full implementation
- `OverlayEngine` (TRD §3.15) — new, minimal version (skeleton + FPS only)

### Files

```
gestureos/
├── app/
│   ├── core.py                    # GestureOSApp: wires CameraModule -> TrackingModule -> Overlay
│   └── capture_thread.py          # CaptureThread(QThread)
├── camera/
│   ├── camera_module.py
│   └── errors.py                  # CameraUnavailableError
├── tracking/
│   └── hand_detector.py           # TrackingModule
├── diagnostics/
│   └── camera_validator.py        # CameraValidator (measurement only at this checkpoint)
├── overlay/
│   ├── overlay_window.py          # minimal: skeleton + FPS only
│   └── skeleton_renderer.py
├── models/
│   └── data_models.py             # HandData gains landmarks/chirality/confidence population
└── tests/
    ├── unit/
    │   └── test_camera_validator.py
    └── fixtures/
        └── sample_frames/          # recorded test frames for TrackingModule tests
```

### Dependencies

Checkpoint 0 must be Done (Settings/Diagnostics scaffolding, repo structure).

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Camera disconnect handling untested against real hardware quirks | Manual test plan: physically unplug webcam mid-session, verify 10-attempt/2s-interval reconnect behavior (TRD §3.1) before marking Done | Risk Matrix row "Camera Disconnect" (Section 15) |
| MediaPipe packaging/bundling issues not caught until Checkpoint 10 | Run a PyInstaller smoke-build at the end of this checkpoint specifically to catch the MediaPipe model-bundling issue early (TRD §12.2 implementation note), even though full packaging work is Checkpoint 10 | TRD §16 Technical Risk: "PyInstaller + MediaPipe packaging fragility" |
| FPS measurement inaccurate on cameras that misreport `cv2.CAP_PROP_FPS` | `CameraValidator.measured_fps()` already measures actual inter-frame timing rather than trusting the camera's self-reported FPS (TRD §3.2) — verify this with at least one camera known to misreport |

### Acceptance Criteria

Per PRD §14.1 (CP-1 acceptance criteria, unchanged by the re-sequencing in Section 3.1):

- MediaPipe detects hand landmarks on live webcam feed at ≥ 25 FPS
- Landmark overlay renders correctly on webcam preview
- Both hands tracked simultaneously (chirality labeling correct — role assignment is Checkpoint 2, but raw chirality from MediaPipe must already be correct here)
- FPS counter visible in overlay; measured FPS logged to `diagnostics.log`

### Testing Strategy

Per TRD §13.2/13.3, unit tests use recorded sample frames, not a live camera:

```python
# tests/unit/test_camera_validator.py
def test_sustained_low_fps_detected_after_5s():
    validator = CameraValidator()
    t = 0.0
    # Simulate 18 FPS for 6 seconds (below the 25 FPS minimum)
    while t < 6.0:
        validator.record_frame(t)
        t += 1/18
    quality = validator.check(now=t)
    assert quality.fps_ok is False

def test_brief_fps_dip_not_flagged():
    validator = CameraValidator()
    # Simulate a 1-second dip, well under the 5s sustained threshold
    ...
```

Manual/exploratory testing (not automatable without hardware): physical camera disconnect/reconnect, testing against 2–3 different webcam models for FPS-reporting accuracy.

### Definition of Done

- All Acceptance Criteria above pass on reference hardware (Intel Core i5, 8GB RAM, 720p webcam per PRD)
- Unit tests for `CameraValidator` pass
- The application runs continuously for at least 10 minutes without crashing or memory growth concerns (full 4-hour memory-budget testing is Checkpoint 9 — this is a basic smoke check only)
- A PyInstaller smoke-build succeeds with MediaPipe correctly bundled (Risks row 2)
## 6. Checkpoint 2 — Hand Analysis Layer

### Purpose

Build every component that transforms raw MediaPipe landmarks into the analyzed, normalized data that gesture recognition will consume: finger states, finger/joint angles, normalized distances, hand scale estimation, velocity/motion history, and persistent hand identity. This checkpoint exists as its own unit (rather than being folded into Checkpoint 3) because it produces a clean, independently-testable data-object boundary — a fully-populated `HandData` — per TRD §6.1's extended schema. Critically, this is where the scale-invariance requirement (PRD §5) becomes load-bearing infrastructure: no gesture rule in Checkpoint 3 can be correctly implemented until `HandData.scale` exists and is trustworthy.

### Scope

**In scope:** `HandIdentityModule`, `OcclusionHandler`, `HandScaleEstimator`, `PrimaryHandFilter`, the `MotionHistoryBuffer`, and the shared geometry utilities (`gesture_utils.py`: `euclidean_distance`, `finger_angle`, finger-state classification) that both this checkpoint and Checkpoint 3 depend on.

**Out of scope:** any gesture *recognition* rule (Open Palm, Pinch, Swipe, etc. — Checkpoint 3). This checkpoint produces the *inputs* to recognition, not recognition itself.

### Deliverables

1. `tracking/hand_identity.py` — `HandIdentityModule` per TRD §3.5, implementing persistent HAND_A/HAND_B role assignment, 2-second re-identification window, proximity-based matching, chirality-fallback tie-breaking (PRD FR-HT-08–12)
2. `tracking/occlusion_handler.py` — `OcclusionHandler` per TRD §3.6, implementing the 300ms (configurable) retention/bridging behavior for briefly-lost hands (PRD FR-OC-01–03)
3. `tracking/hand_scale.py` — `HandScaleEstimator` per TRD §3.7, computing palm width/height, bounding box, and the 5-frame smoothed scale reference (PRD §6, FR-SC-01–04)
4. `tracking/primary_hand_filter.py` — `PrimaryHandFilter` per TRD §3.8, implementing Dominant Hand Mode (off/left/right) (PRD FR-PH-01–03)
5. `gestures/motion_history.py` — `MotionHistoryBuffer` per TRD §3.9/§4.5, storing raw (unnormalized) wrist position history per hand role, 15–30 frame capacity (PRD FR-MH-01–04), with the critical design detail that normalization happens at read-time, not write-time (TRD §4.5 comment, PRD FR-MH-03)
6. `gestures/gesture_utils.py` — shared geometry primitives: `euclidean_distance()`, `finger_angle()` (PIP-joint angle calculation per TRD §4.3/§5.3), and `finger_states()` (the EXTENDED/CURLED classification dict)
7. Settings schema extended with this checkpoint's tunable fields: `motion_history_frames`, `occlusion_retention_ms`, `dominant_hand_mode` (already present in the TRD §7.2 `Settings` dataclass from Checkpoint 0's foundational schema — this checkpoint is the first to actually *consume* them)
8. Diagnostics logging extended with the `tracking` category events: hand detected/lost, occlusion bridged/expired, scale estimation skipped (TRD §9.2)

### Modules

- `HandIdentityModule` (TRD §3.5)
- `OcclusionHandler` (TRD §3.6)
- `HandScaleEstimator` (TRD §3.7)
- `PrimaryHandFilter` (TRD §3.8)
- `MotionHistoryBuffer` (TRD §4.5, part of the `GestureEngine` component group but introduced here since it has no recognition logic of its own — it is a pure data buffer)

### Files

```
gestureos/
├── tracking/
│   ├── hand_identity.py
│   ├── occlusion_handler.py
│   ├── hand_scale.py
│   └── primary_hand_filter.py
├── gestures/
│   ├── motion_history.py
│   └── gesture_utils.py
├── models/
│   └── data_models.py              # HandData gains: role, scale, gesture_eligible, is_retained
└── tests/
    ├── unit/
    │   ├── test_hand_identity.py
    │   ├── test_occlusion_handler.py
    │   └── (scale/primary-hand/motion-history unit tests, file names per TRD §8 layout)
    └── fixtures/
        ├── sample_landmarks.json    # known-good landmark sets per hand pose
        └── occlusion_sequence.json  # per TRD §13.2
```

### Dependencies

Checkpoint 1 must be Done — this checkpoint consumes `list[HandData]` as produced by `TrackingModule`.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Hand scale estimation noise (rapid hand rotation changing apparent palm width) destabilizes all downstream normalized measurements | 5-frame moving average smoothing is mandatory, not optional (TRD §3.7); explicitly test scale stability during simulated hand rotation, not just static-distance scenarios | TRD §16 Technical Risk row 1; PRD Risk Matrix "Scale Sensitivity" |
| Hand identity re-identification ambiguous during fast hand-crossing motion | Proximity-threshold (0.15 normalized units) and chirality-fallback are both implemented and unit-tested against a synthetic crossing sequence | PRD Risk Matrix "Hand Crossing"; TRD §3.5 Error Handling |
| Occlusion retention window masks a genuinely lost hand, causing stale gesture state to persist | Hard 300ms timeout enforced — `OcclusionHandler` never retains indefinitely (TRD §3.6 Error Handling); unit test specifically asserts release after window expiry | |

### Acceptance Criteria

The PRD does not define CP-2-equivalent acceptance criteria separately for analysis vs. recognition (PRD CP-2 bundles both — see Section 3.1 Cross-Reference Table). This plan derives analysis-specific criteria from the underlying functional requirements:

- Hand scale estimate (`palm_width`, `palm_height`, `smoothed_scale`) is computed correctly against known-good fixture landmarks, matching hand-calculated expected values within floating-point tolerance
- A simulated hand-crossing sequence preserves HAND_A/HAND_B role assignment correctly across the crossing event (PRD example, PRD §8.1.1)
- A simulated 150ms occlusion (within the 300ms window) does not cause hand data to be cleared; a simulated 400ms occlusion (beyond the window) does cause it to be cleared and the role released
- Dominant Hand Mode set to "left" correctly excludes a right-hand `HandData` from `gesture_eligible=True`, while still passing it through for overlay rendering (PRD FR-PH-02)
- Motion history buffer correctly evicts oldest entries beyond its configured capacity (PRD FR-MH-02) without unbounded growth

### Testing Strategy

Entirely unit-level per TRD §13.2/13.3 — no live camera, no integration test yet (the pipeline isn't end-to-end until Checkpoint 4 closes the loop through Activation).

```python
# tests/unit/test_hand_identity.py — per TRD §13's example, reused here as the
# canonical test for this checkpoint's most important correctness property
def test_roles_preserved_across_crossing():
    tracker = HandIdentityModule()
    hands_f1 = [make_hand(x=0.2), make_hand(x=0.8)]
    tracker.assign_roles(hands_f1, now=0.0)
    hands_f2 = [make_hand(x=0.75), make_hand(x=0.25)]  # crossed
    tracker.assign_roles(hands_f2, now=0.1)
    assert {h.role for h in hands_f2} == {'HAND_A', 'HAND_B'}

# tests/unit/test_occlusion_handler.py
def test_brief_occlusion_bridged():
    handler = OcclusionHandler(retention_ms=300)
    hand_present = [make_hand(role='HAND_A')]
    handler.bridge_gaps(hand_present, now=0.0)
    bridged = handler.bridge_gaps([], now=0.15)  # hand vanishes for 150ms
    assert any(h.role == 'HAND_A' and h.is_retained for h in bridged)

def test_occlusion_window_expires():
    handler = OcclusionHandler(retention_ms=300)
    handler.bridge_gaps([make_hand(role='HAND_A')], now=0.0)
    expired = handler.bridge_gaps([], now=0.4)  # 400ms, beyond window
    assert not any(h.role == 'HAND_A' for h in expired)
```

### Definition of Done

- All components in Deliverables implemented exactly per their TRD §3 specification
- All Acceptance Criteria pass
- Unit test coverage ≥ 80% for `tracking/` per TRD §13.7's coverage target
- No raw-pixel or raw-frame-normalized threshold exists anywhere in this checkpoint's code (Core Principle 2) — verified by code review against TRD §4.3's rule, even though full gesture-rule scale-invariance testing happens in Checkpoint 3
- `HandData` objects flowing out of this checkpoint's pipeline stage have `scale`, `role`, `gesture_eligible`, and `is_retained` correctly and consistently populated, ready for Checkpoint 3 to consume
## 7. Checkpoint 3 — Gesture Recognition Layer

### Purpose

Implement every gesture rule defined in the PRD (8 static, 6 dynamic) using exclusively scale-invariant geometric logic, plus the Gesture Stability Window and Cooldown System that prevent flicker and double-triggers. This is the checkpoint where the product's core value proposition — reliable, distance-independent, rule-based gesture control — becomes real and testable end-to-end at the recognition level.

### Scope

**In scope:** all 14 PRD-defined gestures, `GestureEngine` orchestration (updated to generate all candidates per PRD §4.6), `ConflictResolver` (new, PRD §4.6 / TRD §3.9.1), `StabilityFilter`, `CooldownFilter`, Multi-Signal Recognition documentation per PRD §4.5.

**Out of scope:** Activation gating (Checkpoint 4 — gestures are recognized here regardless of ACTIVE/INACTIVE state; the gate is applied downstream), any OS action dispatch (Checkpoint 5).

### Deliverables

1. `gestures/static_recognizer.py` — all 8 static gesture rules (Section 7.1 below), built on `gesture_utils.finger_angle()` and `finger_states()` from Checkpoint 2. Each rule must implement the multi-signal discipline per PRD §4.5/FR-MS-01 (at least two independent geometric signals before producing a candidate).
2. `gestures/dynamic_recognizer.py` — all 6 dynamic gesture rules (Section 7.2 below), built on `MotionHistoryBuffer` from Checkpoint 2. Each rule must implement the multi-signal discipline per PRD §4.5/FR-MS-02 (velocity + direction + trajectory shape, never single-frame displacement alone).
3. `gestures/gesture_engine.py` — `GestureEngine` per TRD §3.9 *(updated in v1.1 of this plan)*: generates ALL qualifying candidates per hand per frame (not "first-match-wins"), per PRD §4.6 Candidate Generation stage and TRD §3.9's updated `_check_all_static()` implementation.
4. `gestures/conflict_resolver.py` — `ConflictResolver` per TRD §3.9.1 *(new in v1.1 of this plan)*: resolves multiple candidates per hand to a single winner using confidence scoring and the fixed tie-break priority table (PRD FR-CR-01–04). File path: `gestures/conflict_resolver.py`.
5. `gestures/stability_filter.py` — `StabilityFilter` per TRD §3.10 (PRD §8.2 / FR-GS-01–04). Now receives `ConflictResolver`'s output (one winner per hand), not raw `GestureEngine` candidates directly.
6. `gestures/cooldown_filter.py` — `CooldownFilter` per TRD §3.11 (PRD §8.3 / FR-CD-01–03)
7. Settings schema fields consumed: `gesture_confidence_threshold`, `gesture_stability_window_ms`, `gesture_cooldown_static_ms`, `gesture_cooldown_dynamic_ms`, `dynamic_window_ms` (all already present in the Checkpoint 0 schema; first consumed here)
8. Diagnostics logging extended with the `gesture` category: candidate detected (may now include multiple candidates per frame), conflict resolved (winner selected), stability passed/failed, cooldown suppressed/passed (TRD §9.1 example log lines)
9. Multi-Signal Recognition documentation: each `detect_*` function's docstring explicitly states which PRD §4.5 signals it combines, per FR-MS-03.

### 7.1 Static Gestures — Per-Gesture Specification

Each gesture below follows: Purpose / Recognition Logic / Dependencies / Failure Cases / Testing Strategy.

---

**Open Palm**
*(PRD §4.3; default action: Pause / Stop; also the Activation Mode hold gesture, PRD §7.2 — though activation logic itself is Checkpoint 4)*

- **Purpose:** Primary "neutral/ready" gesture; also doubles as the Activation Mode toggle gesture.
- **Recognition Logic:** All five fingers EXTENDED (via PIP-joint angle, TRD §4.3) AND average fingertip spread, normalized by `palm_width`, above a tuned threshold (TRD §4.3 reference implementation, `detect_open_palm`).
- **Dependencies:** `finger_states()`, `HandData.scale.palm_width` (Checkpoint 2).
- **Failure Cases:** A loosely-closed fist with fingers barely extended must not false-positive — the spread check specifically guards against this (TRD §4.3 implementation note); a hand at an extreme rotation angle relative to the camera may under-report extension via the angle check if the rotation is severe enough to distort joint-angle geometry (documented limitation, not a defect — extreme rotation is an edge case the PRD does not require supporting).
- **Testing Strategy:** Unit test against `open_palm_right.json` / `open_palm_left.json` fixtures (both chiralities); explicit negative test with `open_palm_no_spread.json` (fingers extended but cramped together) per TRD §13's example test.

---

**Closed Fist**
*(PRD §4.3; default action: Hold / Drag start)*

- **Purpose:** Compact-hand gesture for hold/drag-initiation semantics.
- **Recognition Logic:** All four fingers (index–pinky) CURLED via angle check; thumb state unconstrained (PRD §4.3 rule summary: "Thumb state unconstrained").
- **Dependencies:** `finger_states()`.
- **Failure Cases:** A hand mid-transition between Open Palm and Fist could theoretically satisfy neither rule cleanly for a frame or two — this is precisely what the Stability Window (Section 7.3) exists to absorb, not something `detect_fist()` itself needs to handle.
- **Testing Strategy:** Unit test against `fist_right.json` fixture; cross-check that `detect_open_palm()` returns `False` against the same fixture (mutual exclusivity sanity check).

---

**Pinch**
*(PRD §4.3, §5.2 scale-invariance worked example; default action: Click / Select)*

- **Purpose:** Primary click/select gesture, also used as the mouse-click action trigger (Checkpoint 5 consumes this).
- **Recognition Logic:** `euclidean_distance(thumb_tip, index_tip) / palm_width < 0.35` (TRD §4.3 reference implementation, `detect_pinch`) — this is the PRD's canonical worked example of scale-invariant normalization (PRD §5.2).
- **Dependencies:** `gesture_utils.euclidean_distance()`, `HandData.scale.palm_width`.
- **Failure Cases:** Without normalization, this gesture is the PRD's explicit illustration of the scale-sensitivity failure mode (PRD §5, the 30px-vs-12px example) — implementing this gesture with a raw threshold is a Checkpoint 3 blocking defect, not a style preference.
- **Testing Strategy:** This gesture is the canonical scale-invariance test subject (TRD §13.3 `test_pinch_recognized_close_and_far`) — tested explicitly at multiple synthetic hand-scale values (TRD §4.6 `test_pinch_recognized_at_all_scales`, parametrized over `scale_factor` 0.5/1.0/2.0/3.0).

---

**Thumbs Up**
*(PRD §4.3; default action: Confirm / Volume Up)*

- **Purpose:** Affirmative/increase-value gesture.
- **Recognition Logic:** Thumb EXTENDED upward via angle check (not vertical tip-position comparison, per TRD §5.3's rotation-tolerant angle method); other four fingers CURLED.
- **Dependencies:** `finger_angle()`, thumb-specific extension logic (TRD §4.3 `is_thumb_extended`, which uses horizontal displacement relative to chirality rather than the angle method used for the other four fingers, since the thumb's joint geometry differs).
- **Failure Cases:** Confusable with Thumbs Down if "upward" vs. "downward" direction detection is ambiguous near a horizontal thumb orientation — direction is determined by comparing thumb-tip y-position to wrist y-position, which needs a sufficiently large angular displacement to be unambiguous.
- **Testing Strategy:** Unit test with both Thumbs Up and Thumbs Down fixtures, asserting mutual exclusivity.

---

**Thumbs Down**
*(PRD §4.3; default action: Cancel / Volume Down)*

- **Purpose:** Negative/decrease-value gesture.
- **Recognition Logic:** Mirror of Thumbs Up — thumb EXTENDED downward via angle check, other fingers CURLED.
- **Dependencies:** Same as Thumbs Up.
- **Failure Cases:** Same ambiguity risk as Thumbs Up, mirrored.
- **Testing Strategy:** Same as Thumbs Up, mirrored fixture.

---

**Peace Sign**
*(PRD §4.3; default action: Screenshot)*

- **Purpose:** Distinct two-finger gesture for a "capture" semantic action.
- **Recognition Logic:** Index + Middle EXTENDED, Ring + Pinky CURLED, Thumb CURLED (PRD §4.3 rule summary).
- **Dependencies:** `finger_states()`.
- **Failure Cases:** Most likely confusion target is Three Fingers if Ring is ambiguously extended (TRD §16 risk row "Similar Gesture Confusion" — PRD Risk Matrix, mitigated by multi-rule confidence scoring requiring sufficient margin, not just a boolean pass).
- **Testing Strategy:** Unit test with `peace_sign.json`; explicit negative test against a Three Fingers fixture to confirm no false-positive overlap.

---

**Three Fingers**
*(PRD §4.3; default action: Switch Workspace)*

- **Purpose:** Three-finger gesture for workspace/desktop switching.
- **Recognition Logic:** Index + Middle + Ring EXTENDED, Pinky + Thumb CURLED.
- **Dependencies:** `finger_states()`.
- **Failure Cases:** Confusable with Peace Sign (see above) and with a loosely-curled Open Palm if Pinky's curl is ambiguous — both guarded by confidence-margin scoring.
- **Testing Strategy:** Mutual-exclusivity unit tests against both Peace Sign and Open Palm fixtures.

---

**OK Sign**
*(PRD §4.3; default action: Right Click)*

- **Purpose:** Secondary click gesture, distinguishable from Pinch by the remaining three fingers' state.
- **Recognition Logic:** `euclidean_distance(thumb_tip, index_tip) / palm_width < 0.35` (same normalized-distance check as Pinch) **AND** Middle + Ring + Pinky all EXTENDED (PRD §4.3 rule summary — this is what distinguishes it from Pinch, where the other three fingers are unconstrained).
- **Dependencies:** Same as Pinch, plus `finger_states()` for the three-finger check.
- **Failure Cases:** Must be evaluated such that it does not get shadowed by Pinch's rule firing first if both conditions are independently checked — `GestureEngine`'s candidate-selection logic (TRD §3.9) must correctly disambiguate via the additional three-finger constraint, not simply match on the thumb-index distance alone.
- **Testing Strategy:** Unit test asserting OK Sign fixture produces `'ok_sign'`, not `'pinch'`, despite both satisfying the thumb-index distance check.

### 7.2 Dynamic Gestures — Per-Gesture Specification

All dynamic gestures consume the `MotionHistoryBuffer` (Checkpoint 2) and normalize displacement/velocity by `hand_scale` per TRD §4.4.

---

**Swipe Right**
*(PRD §4.4; default action: Next slide / track / forward)*

- **Purpose:** Primary "advance" gesture across presentation, media, and browser contexts.
- **Recognition Logic:** Normalized rightward wrist displacement > threshold (TRD §4.4 `detect_swipe_right`: `dx_threshold=2.5` hand-scales) within the time window; `abs(dy) < dy_max`; normalized velocity above minimum.
- **Dependencies:** `MotionHistoryBuffer.get(role)`, `HandData.scale.smoothed_scale`, `gesture_utils.normalized_displacement()`.
- **Failure Cases:** A diagonal motion exceeding `dy_max` must be rejected even if `dx` alone would qualify (TRD §13's `test_swipe_right_rejected_if_too_vertical`); a too-slow motion (large elapsed time, same total displacement) must be rejected by the velocity check independent of the distance check (`test_swipe_right_rejected_if_too_slow`).
- **Testing Strategy:** TRD §4.6/§13.3's parametrized scale-invariance test is mandatory for this gesture specifically (it's the TRD's canonical dynamic-gesture example); plus the too-slow and too-vertical rejection tests already specified in TRD §13.

---

**Swipe Left**
*(PRD §4.4; default action: Previous slide / track / back)*

- **Purpose:** Mirror of Swipe Right.
- **Recognition Logic:** Mirror of Swipe Right — leftward displacement.
- **Dependencies:** Same as Swipe Right.
- **Failure Cases:** Same class of failures, mirrored direction.
- **Testing Strategy:** Mirrored test suite of Swipe Right.

---

**Swipe Up**
*(PRD §4.4; default action: Scroll up / Volume up)*

- **Purpose:** Vertical-axis increase gesture.
- **Recognition Logic:** Normalized upward displacement (`first_y - last_y`, since y increases downward in image space) > threshold; predominantly vertical (`abs(dx) < dx_max`); velocity above minimum.
- **Dependencies:** Same primitives as Swipe Right/Left, rotated to the vertical axis.
- **Failure Cases:** Same diagonal-rejection and too-slow-rejection failure classes as the horizontal swipes.
- **Testing Strategy:** Same test pattern as Swipe Right, rotated to vertical axis assertions.

---

**Swipe Down**
*(PRD §4.4; default action: Scroll down / Volume down)*

- **Purpose:** Mirror of Swipe Up.
- **Recognition Logic:** Mirror of Swipe Up — downward displacement.
- **Dependencies:** Same as Swipe Up.
- **Failure Cases:** Same class, mirrored.
- **Testing Strategy:** Mirrored test suite of Swipe Up.

---

**Wave**
*(PRD §4.4; default action: Show Desktop)*

- **Purpose:** Distinct oscillating gesture for a "dismiss everything" semantic, deliberately requiring a different motion pattern than any swipe to avoid accidental triggering during normal swipe usage.
- **Recognition Logic:** ≥2 direction reversals in normalized x-displacement within the time window (PRD §4.4 rule summary).
- **Dependencies:** `MotionHistoryBuffer`, sign-change detection across consecutive buffer entries.
- **Failure Cases:** A single swipe followed immediately by a second swipe in the opposite direction (e.g., user swipes right, then quickly swipes left for a different purpose) could be misdetected as a Wave if the two motions fall within the same time window — this is a known ambiguity the PRD does not provide additional disambiguation rules for (see Gap G-3 below).
- **Testing Strategy:** Unit test with a recorded oscillating-trajectory fixture; explicit negative test with a single straight swipe trajectory to confirm no false Wave trigger.

> **GAP G-3:** Neither the PRD nor TRD specifies a disambiguation rule between "two consecutive opposite swipes" and "Wave." This is flagged as a gap rather than resolved with an invented tie-breaking rule. **Recommendation for product owner review (not implemented in this checkpoint without explicit sign-off):** consider requiring Wave's reversals to occur with a shorter inter-reversal interval than two independently-intentional swipes would typically have, or accept the ambiguity as a documented limitation given Wave's infrequent use (it maps only to "Show Desktop").

---

**Circular Motion**
*(PRD §4.4; default action: Open App Launcher)*

- **Purpose:** Distinct closed-loop gesture for launching the app picker, deliberately the most geometrically distinct dynamic gesture to minimize confusion with any swipe.
- **Recognition Logic:** Trajectory bounding box (from `MotionHistoryBuffer` points) roughly square (width ≈ height, normalized); angular progression around the bounding box's centroid ≥ 270° within the time window (PRD §4.4 rule summary).
- **Dependencies:** `MotionHistoryBuffer`, bounding-box computation, per-point angle-from-centroid computation.
- **Failure Cases:** A small, fast circular motion might fail the "roughly square bounding box" check if hand-scale normalization isn't applied to the bounding box dimensions consistently with how it's applied to swipe displacement — this gesture must use the same `hand_scale` normalization discipline as every other dynamic gesture (TRD §4.2's invariant applies universally, not just to swipes).
- **Testing Strategy:** Unit test with a recorded circular-trajectory fixture at multiple synthetic scales (same scale-invariance discipline as Swipe Right); negative test with a straight-line trajectory to confirm no false Circular Motion trigger.

### 7.3 Gesture Stability Window

*(PRD §8.2, FR-GS-01–04; TRD §3.10)*

- **Purpose:** Prevent single-frame pose noise from causing a false trigger (PRD's "Gesture Flicker" risk).
- **Recognition Logic:** A static gesture must remain the highest-confidence match continuously for 200ms (configurable 100–500ms) before being accepted; the hold timer is tracked per hand role independently; if the candidate gesture changes before the window elapses, the hold resets with no partial credit (FR-GS-02 — this is the specific behavior tested in TRD §13.5's `test_single_frame_flicker_does_not_trigger`).
- **Dependencies:** `GestureResult.is_dynamic` flag (dynamic gestures are exempt — FR-GS-04, since they're already inherently multi-frame).
- **Failure Cases:** A gesture held for exactly the boundary duration (e.g., held for precisely 200ms) must be handled consistently — implementation uses `>=`, not `>`, per TRD §3.10's reference implementation.
- **Testing Strategy:** TRD §13.5's exact test (`test_single_frame_flicker_does_not_trigger`) is the required minimum; additionally test the dynamic-gesture-exemption path explicitly.

### 7.4 Cooldown System

*(PRD §8.3, FR-CD-01–03; TRD §3.11)*

- **Purpose:** Prevent a single physical gesture motion from firing the same action multiple times across consecutive qualifying frames (PRD's "Double Trigger" risk).
- **Recognition Logic:** Per-(hand_role, gesture_name) last-trigger timestamp tracking; static gestures use `gesture_cooldown_static_ms` (default 500ms), dynamic gestures use `gesture_cooldown_dynamic_ms` (default 1000ms) — the PRD specifies different defaults because dynamic gestures span a longer physical motion (PRD §8.3 FR-CD-01 rationale).
- **Dependencies:** None beyond `Settings` and a timestamp dict — this is the simplest component in the checkpoint.
- **Failure Cases:** Cooldown on one gesture must not suppress a different gesture on the same hand, nor the same gesture on the other hand (FR-CD-02) — both are explicitly unit-tested.
- **Testing Strategy:** TRD §13.5's `test_cooldown_suppresses_repeated_trigger` is the required minimum; additionally test the cross-gesture and cross-hand independence explicitly.

### Modules

- `GestureEngine` (TRD §3.9) — updated: generates all candidates per PRD §4.6
- `ConflictResolver` (TRD §3.9.1) — new in v1.1
- `StabilityFilter` (TRD §3.10)
- `CooldownFilter` (TRD §3.11)

### Files

```
gestureos/
├── gestures/
│   ├── static_recognizer.py        # all 8 static gesture functions (multi-signal, FR-MS-01)
│   ├── dynamic_recognizer.py       # all 6 dynamic gesture functions (multi-signal, FR-MS-02)
│   ├── gesture_engine.py           # all-candidates generation (updated, PRD §4.6)
│   ├── conflict_resolver.py        # NEW: single winner per hand (PRD §4.6, TRD §3.9.1)
│   ├── stability_filter.py
│   └── cooldown_filter.py
└── tests/
    ├── unit/
    │   ├── test_static_gestures.py
    │   ├── test_dynamic_gestures.py
    │   ├── test_scale_invariance.py
    │   ├── test_conflict_resolver.py   # NEW in v1.1
    │   ├── test_stability_filter.py
    │   └── test_cooldown_filter.py
    └── fixtures/
        ├── open_palm_right.json, open_palm_left.json, open_palm_no_spread.json
        ├── fist_right.json
        ├── pinch_close.json, pinch_far.json
        ├── thumbs_up.json, thumbs_down.json
        ├── peace_sign.json, three_fingers.json, ok_sign.json
        └── (trajectory fixtures for all 6 dynamic gestures, including negative-case fixtures)
```

### Dependencies

Checkpoint 2 must be Done — every gesture rule in this checkpoint consumes `HandData.scale` and/or `MotionHistoryBuffer` output.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Gesture Flicker | Gesture Stability Requirement (Section 7.3) | Risk Matrix (Section 15) |
| Double Trigger | Cooldown System (Section 7.4) | Risk Matrix (Section 15) |
| Scale Sensitivity | Every rule normalized per TRD §4; Pinch and Swipe Right are the explicit scale-invariance test subjects | Risk Matrix (Section 15) |
| Wave/double-swipe ambiguity | Documented as Gap G-3, not silently resolved | This document, Section 7.2 |

### Acceptance Criteria

Per PRD §14.1's CP-2 acceptance criteria additions:

- Pinch gesture recognized correctly at both 30cm and 100cm from camera (validates scale invariance)
- A gesture held for only 1 frame does not trigger; a gesture held 200ms+ does
- Repeated single swipe motion fires exactly one action, not multiple
- All 8 static and 6 dynamic gestures individually pass their unit tests with ≥95% accuracy against their fixture sets (PRD §17.2 standard, applied per-gesture at unit-test scope here; full multi-user/multi-lighting accuracy validation is Checkpoint 9)
- Every detected gesture produces a confidence score.
- ConflictResolver correctly resolves competing gestures using confidence and priority.

### Testing Strategy

See per-gesture Testing Strategy entries above (Sections 7.1, 7.2) plus Sections 7.3/7.4. Aggregate coverage target: ≥80% for `gestures/` per TRD §13.7.

### Definition of Done

- All 14 gestures implemented exactly per their PRD §4.3/§4.4 rule summary, TRD §4 normalization discipline, and the multi-signal requirement (PRD FR-MS-01/FR-MS-02), with each gesture's docstring citing its combined signals (FR-MS-03)
- Every gesture's unit tests pass, including all documented Failure Cases above
- `test_scale_invariance.py` passes for both Pinch (static) and Swipe Right (dynamic) at minimum, per TRD §4.6/§13.3
- `ConflictResolver` passes `test_conflict_resolver.py` including the PRD §4.6 worked example test (two candidates, higher-confidence wins), the tie-break test (equal confidence, priority-table wins), and the cross-hand independence test (FR-CR-04)
- `GestureEngine` is verified to produce multiple candidates when two rules simultaneously match (not just one) — integration-tested via a fixture representing a transitional pose that satisfies both Peace Sign and Three Fingers
- `StabilityFilter` and `CooldownFilter` pass their TRD §13.5 reference tests (pipeline now receives `ConflictResolver`'s output, not raw `GestureEngine` candidates — verify the ordering is correct in `app/capture_thread.py`)
- Gap G-3 (Wave/swipe ambiguity) is documented in the codebase (code comment + this plan) rather than silently resolved
- No raw-pixel threshold exists anywhere in `gestures/` — final code-review checkpoint gate per Core Principle 2
## 8. Checkpoint 4 — Activation Layer

### Purpose

Implement the safety gate that prevents gestures from being acted upon unless the user has explicitly activated tracking — this is the checkpoint that closes the loop from Camera through to a gated, ready-to-dispatch gesture decision, making this the first point in the build where a genuine end-to-end integration test becomes possible (per Section 2.3's testing philosophy). PRD treats this as mandatory for release, not optional (PRD §7: "GestureOS must not execute gestures continuously by default").

### Scope

**In scope:** `ActivationGate` state machine, the three activation methods (Open Palm Hold, Keyboard Shortcut, Tray Toggle — Closed Fist Hold is configurable/off-by-default per PRD §7.2 but implemented alongside Open Palm Hold since it shares the same hold-timer mechanism), the INACTIVE/ACTIVE visual indicator in the overlay.

**Out of scope:** Tray icon UI itself is GUI work (Checkpoint 7) — this checkpoint implements the *toggle handler* `ActivationGate` exposes, which the Checkpoint 7 tray icon will call; similarly, the Keyboard Shortcut's global-hotkey *registration* mechanism is implemented here, but its configuration UI is Checkpoint 7.

### Deliverables

1. `gestures/activation_gate.py` — `ActivationGate` per TRD §5.3, implementing the INACTIVE↔ACTIVE state machine, the Open Palm (and optionally Closed Fist) hold-timer logic, and the `toggle()` method callable by keyboard shortcut or tray icon
2. Pipeline wiring in `app/core.py`: `ActivationGate.feed_gesture()` receives gesture candidates *after* they've passed `StabilityFilter` (Checkpoint 3) — this specific ordering is called out as a named risk in TRD §16 ("Stability window interacts with Activation Mode's hold timer in a non-obvious way") and must be preserved exactly as documented there
3. A global keyboard-shortcut listener (default `Ctrl+Alt+G`, configurable) wired to `ActivationGate.toggle()`
4. Overlay extended with the ACTIVE (green) / INACTIVE (grey) state indicator (PRD FR-VF-06) — this is the first overlay extension beyond Checkpoint 1's minimal skeleton+FPS view
5. Settings schema field consumed: `activation_hold_duration_s` (already present from Checkpoint 0 schema)
6. Diagnostics logging extended with the `activation` category: state changed, method used (TRD §9.1 example log line: `State changed {from: 'inactive', to: 'active', method: 'open_palm_hold'}`)

### Modules

- `ActivationGate` (TRD §3 — referenced throughout TRD §5.3, §7.3 / PRD §7)

### Files

```
gestureos/
├── gestures/
│   └── activation_gate.py
├── app/
│   └── core.py                     # extended: wires StabilityFilter output -> ActivationGate.feed_gesture()
├── overlay/
│   └── overlay_window.py           # extended: ACTIVE/INACTIVE indicator
└── tests/
    ├── unit/
    │   └── test_activation_gate.py
    └── integration/
        └── test_pipeline_end_to_end.py   # FIRST integration test in the build — see Testing Strategy
```

### Dependencies

Checkpoint 3 must be Done — `ActivationGate.feed_gesture()` consumes stability-passed `GestureResult` objects.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Activation hold-timer and Stability Window timers conflated or mis-ordered in pipeline wiring | TRD §16's explicit risk callout: "`ActivationGate.feed_gesture()` only receives gesture names that have already passed `StabilityFilter`... this ordering must be preserved in `app/core.py`'s pipeline wiring" — code review must verify this exact ordering, not just functional correctness | TRD §16 Technical Risk row 3 |
| Background Gesture Triggers (the core problem Activation Mode exists to solve) | This is the entire purpose of this checkpoint; validated via the PRD's own Zoom-call scenario (PRD §7.1) as an explicit test case | PRD Risk Matrix "Background Gesture Triggers" |
| Global keyboard shortcut conflicts with OS or other application shortcuts | **GAP G-4:** Neither PRD nor TRD specifies conflict-detection or a fallback behavior if `Ctrl+Alt+G` is already bound system-wide. Flagged as a gap; this checkpoint implements the shortcut as specified without inventing conflict-resolution logic. |

### Acceptance Criteria

Per PRD §14.1 CP-2 acceptance criteria (the activation-gate portion, isolated per Section 3.1's cross-reference):

- Activation gate blocks all gesture processing when in INACTIVE state
- Open Palm held 1s toggles state INACTIVE ↔ ACTIVE
- Default state on application launch is INACTIVE (FR-AM-06)
- Hand landmark rendering continues in the overlay during INACTIVE state (FR-AM-02) — gestures are gated, visibility is not

### Testing Strategy

This is the first checkpoint where a true integration test is meaningful (Section 2.3), since it's the first point where Camera → Tracking → Analysis → Recognition → Stability → Activation forms a complete, closed chain:

```python
# tests/unit/test_activation_gate.py
def test_default_state_is_inactive():
    gate = ActivationGate(hold_duration_s=1.0)
    assert gate.state == TrackingState.INACTIVE

def test_open_palm_hold_toggles_state():
    gate = ActivationGate(hold_duration_s=1.0)
    gate.feed_gesture('open_palm', now=0.0)
    gate.feed_gesture('open_palm', now=0.5)   # still holding, not yet 1.0s
    assert gate.state == TrackingState.INACTIVE
    gate.feed_gesture('open_palm', now=1.0)   # hold duration reached
    assert gate.state == TrackingState.ACTIVE

def test_non_open_palm_gesture_resets_hold_timer():
    gate = ActivationGate(hold_duration_s=1.0)
    gate.feed_gesture('open_palm', now=0.0)
    gate.feed_gesture('pinch', now=0.5)        # interrupts the hold
    gate.feed_gesture('open_palm', now=0.9)    # restarts the hold from here
    assert gate.state == TrackingState.INACTIVE  # only 0.4s into the new hold

# tests/integration/test_pipeline_end_to_end.py — per TRD §13.4 pattern
def test_gestures_ignored_while_inactive(mock_camera_feed):
    app = build_test_app(camera=mock_camera_feed)
    assert app.activation_gate.state == TrackingState.INACTIVE
    with patch('actions.executors.base.CommandExecutor.dispatch') as mock_dispatch:
        for frame in mock_camera_feed.swipe_right_sequence():
            app.process_frame(frame)
        mock_dispatch.assert_not_called()  # gated, even though gesture was valid
```

### Definition of Done

- All Acceptance Criteria pass
- `test_pipeline_end_to_end.py`'s INACTIVE-state suppression test passes — this is the checkpoint's most important correctness property
- Manual validation of the PRD §7.1 Zoom-call scenario: natural hand movement during simulated conversation does not trigger any logged gesture-to-action event while INACTIVE
- Unit test coverage ≥80% for the `ActivationGate` per TRD §13.7
## 9. Checkpoint 5 — Action Layer

### Purpose

Implement OS-level dispatch: cursor movement (with smoothing), mouse clicks, keyboard shortcuts, scroll, and system commands. This is the first checkpoint where GestureOS actually *does* something on the user's computer rather than only observing and recognizing — it is also the checkpoint where the platform-adapter pattern (TRD §11) is first exercised in earnest.

### Scope

**In scope:** `ActionEngine` (the resolve+dispatch core), `CursorController`, `CommandExecutor` and its Windows implementation (`WindowsExecutor`), the System Command Engine's full command set (PRD §8.6). *(Re-scoped per PRD v1.3 §1.2: only `WindowsExecutor` is built and validated in this checkpoint for the initial release. `MacOSExecutor`/`LinuxExecutor` remain documented at the interface level in TRD §11.3 for Future Expansion, but are not implementation deliverables of this checkpoint.)*

**Out of scope:** Action *mapping resolution by context* — at this checkpoint, `ActionEngine.resolve()` operates only against the `'global'` context fallback, since `ContextEngine` doesn't exist until Checkpoint 6; this checkpoint hardcodes/stubs a single always-`'global'` context input. Gesture Mapping Manager UI is Checkpoint 7. `MacOSExecutor`/`LinuxExecutor` implementation (Future Expansion, PRD §1.2).

### Deliverables

1. `actions/action_engine.py` — `ActionEngine` per TRD §3.13, implementing mapping-index lookup and dispatch routing (with `'global'`-only context for now, per Scope above)
2. `actions/cursor_controller.py` — `CursorController` per TRD §3.14, implementing the smoothing-method-pluggable cursor path (Exponential Moving Average default, Moving Average, One Euro Filter) per PRD §8.4/FR-CC-03
3. `actions/executors/base.py` + the Windows implementation — `CommandExecutor` ABC and `WindowsExecutor` per TRD §11.3, covering: mouse (click/double-click/drag/scroll), keyboard (hotkeys + single keys via context-managed press/release pairs to avoid stuck-key bugs per TRD §9.3 risk row), volume/brightness (`pycaw`), screenshot, lock screen, app launch. The `CommandExecutor` ABC is written platform-agnostically (per TRD §11.5) so `MacOSExecutor`/`LinuxExecutor` can be added later without changing this interface.
4. Implementation order within this checkpoint (see Section 9.1 below) — Cursor first, then Mouse, then Keyboard, then Scroll, then System, reflecting increasing platform-specific complexity and decreasing usage frequency in the gesture set
5. Settings schema fields consumed: `cursor_smoothing_method`, `cursor_smoothing_alpha`, `cursor_speed_multiplier` (already present from Checkpoint 0 schema)

### 9.1 Implementation Order Within This Checkpoint, and Why

The PRD does not itself specify a sub-order within "System Control" (PRD's CP-3 deliverable list is unordered: Cursor Control, Clicks, Scroll, Keyboard Shortcuts, Volume Control). This plan imposes the following explicit order and rationale, since the requested document structure calls for "explain implementation order" at this checkpoint:

1. **Cursor Engine first.** Cursor movement is the only *continuous* action in the system (every other action is a discrete one-shot dispatch) and is the most architecturally distinct (TRD §3.14's note on why `CursorController` is separated from `ActionEngine`'s general dispatch). Building it first establishes the smoothing-and-mapping pattern before any simpler discrete action is attempted.
2. **Mouse Engine (clicks) second.** Click/double-click are the simplest discrete dispatch — minimal parameters, no modifier-key complexity — and directly exercise `Pinch`/`OK Sign` gestures already built in Checkpoint 3, providing an immediate, demonstrable "gesture causes an OS action" milestone.
3. **Keyboard Engine third.** Hotkey dispatch introduces the context-managed press/release-pair complexity (TRD §9.3 risk: "stuck modifier key" bugs) that mouse dispatch doesn't have — sequencing it after the simpler mouse case isolates this added complexity for focused testing.
4. **Scroll Engine fourth.** Scroll is mechanically similar to mouse dispatch but maps from the vertical swipe gestures (Checkpoint 3) — sequenced after Keyboard since it's lower complexity than hotkey dispatch but benefits from the dispatch-pattern maturity established by the prior two engines.
5. **System Engine last.** Volume/brightness/screenshot/lock-screen/app-launch are used by the fewest gestures in the default mapping set, and (per TRD §11.3) each maps to a distinct Windows API (`pycaw` for volume, `ctypes`/`LockWorkStation` for lock screen, etc.) rather than a single uniform call pattern — sequencing them last means the dispatch architecture is already proven on the simpler, more uniform action types before tackling this internally-varied work. *(Note: this checkpoint's System Engine targets the Windows implementation only, per PRD v1.3 §1.2 — the original rationale's cross-OS divergence concern (`pycaw` vs `osascript` vs `amixer`) becomes relevant again only when Future Expansion work adds the macOS/Linux executors.)*

### Modules

- `ActionEngine` (TRD §3.13)
- `CursorController` (TRD §3.14)
- `CommandExecutor` + Windows implementation (TRD §11.3; ABC interface remains platform-agnostic for Future Expansion per TRD §11.5)

### Files

```
gestureos/
├── actions/
│   ├── action_engine.py
│   ├── cursor_controller.py
│   └── executors/
│       ├── base.py
│       ├── windows_executor.py
│       ├── macos_executor.py
│       └── linux_executor.py
├── calibration/
│   └── tracking_zone.py            # TrackingZone dataclass, consumed by CursorController
│                                     # (full CalibrationManager UI is Checkpoint 7; this
│                                     #  checkpoint needs the TrackingZone.map_to_screen()
│                                     #  math to exist for CursorController to function,
│                                     #  using documented defaults until calibration exists)
└── tests/
    ├── unit/
    │   └── test_action_engine.py
    └── integration/
        └── (cursor smoothing and mouse-dispatch tests, mocking pynput per TRD §13's pattern)
```

> **GAP G-5:** `TrackingZone` (TRD §10.1) is formally introduced as part of the Checkpoint 7 Calibration Subsystem, but `CursorController` (this checkpoint) requires *some* `TrackingZone` to map hand position to screen coordinates. This plan resolves the ordering by implementing `calibration/tracking_zone.py`'s data structure and math (`map_to_screen()`) in this checkpoint using documented full-frame defaults (top_left=(0,0), bottom_right=(1,1)), while the *wizard* that lets users calibrate a custom zone remains Checkpoint 7 work. This is a sequencing accommodation, not a new requirement — `TrackingZone`'s shape and math are taken verbatim from TRD §10.1.

### Dependencies

Checkpoint 4 must be Done — `ActionEngine` receives gated (post-Activation) `GestureResult` objects.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Cursor Jitter | `CursorController`'s smoothing layer is mandatory, not optional, per PRD FR-CC-03; EMA is the tested default | Risk Matrix (Section 15); TRD §3.14 implementation note on why EMA is default |
| Stuck modifier keys on rapid gesture sequences | Hotkey dispatch always uses context-managed press/release pairs (TRD §9.3); integration-tested by rapidly firing multiple hotkey actions in sequence and asserting no held-key state leaks | TRD §16 Technical Risk: "pynput/pyautogui platform inconsistencies" |
| Windows volume/brightness API (`pycaw`) behaves inconsistently across Windows builds, or is unavailable in a minimal/stripped Windows install | `WindowsExecutor` catches and logs its own failures independently (TRD §3.13 Error Handling pattern); a `pycaw` failure degrades that one action, not the whole app. (This risk simplifies in v1.1 of this plan since only one platform's API is in scope for this checkpoint — the original cross-platform divergence concern returns when Future Expansion adds macOS/Linux executors.) | |
| OS permission denial blocks all dispatch | Per TRD §11.4 — caught per-action, logged ERROR, one-time user notification; this checkpoint must implement that catch-and-notify behavior, not just let dispatch silently fail. (macOS Accessibility-permission denial, TRD §11.4's most severe example, is a Future Expansion concern — Windows requires no equivalent blanket synthetic-input permission, per TRD §11.4's permissions table.) | TRD §11.4 |

### Acceptance Criteria

Per PRD §14.1 CP-3 acceptance criteria:

- Cursor follows index fingertip across full screen resolution
- Pinch gesture triggers left click; OK Sign triggers right click
- Scroll up/down working via swipe gestures
- At least 5 keyboard shortcuts functional (Enter, Escape, Tab, Alt+Tab, Ctrl+C)
- Volume up/down functional via Thumbs Up/Down

Additionally, per this plan's checkpoint-template requirement:

- Cursor movement is visibly smoothed — no frame-to-frame jitter under a static-hand-hold test (this is pulled forward from PRD CP-3's acceptance-criteria addition since it's directly testable at this checkpoint without waiting for Checkpoint 9's full performance suite)

### Testing Strategy

Per TRD §13.4's integration pattern, mocking `CommandExecutor.dispatch` to avoid actually controlling the test machine's mouse/keyboard during CI:

```python
# tests/integration/test_action_dispatch.py
def test_pinch_triggers_left_click(mock_camera_feed):
    app = build_test_app(camera=mock_camera_feed)
    app.activation_gate.state = TrackingState.ACTIVE
    with patch('actions.executors.base.CommandExecutor.dispatch') as mock_dispatch:
        for frame in mock_camera_feed.pinch_sequence():
            app.process_frame(frame)
        mock_dispatch.assert_called_once()
        action = mock_dispatch.call_args[0][0]
        assert action.params == {'button': 'left', 'action': 'click'}

def test_cursor_smoothing_reduces_jitter():
    controller = CursorController(settings=test_settings(cursor_smoothing_alpha=0.3), tracking_zone=default_zone())
    noisy_positions = [(0.50, 0.50), (0.51, 0.49), (0.49, 0.51), (0.505, 0.495)]  # simulated jitter
    smoothed = [controller._ema(x, y, 0.3) for x, y in noisy_positions]
    # Assert smoothed trajectory has lower frame-to-frame variance than raw input
    assert variance(smoothed) < variance(noisy_positions)
```

### Definition of Done

- All Acceptance Criteria pass on Windows (the primary release target, PRD §1.2). `MacOSExecutor`/`LinuxExecutor` validation is out of scope for this checkpoint and deferred to the Future Expansion phase per PRD §1.2 — the prior "stub/mock for unavailable CI platforms" allowance from this checkpoint's earlier scope is no longer applicable since macOS/Linux are not implementation deliverables of this checkpoint at all.
- `TrackingZone` default-zone math (Gap G-5) is unit tested independent of the full Calibration Wizard
- No stuck-modifier-key state observed across a rapid-fire sequence of ≥10 hotkey dispatches in integration testing
## 10. Checkpoint 6 — Context Engine

### Purpose

Implement active-window detection and the Context Verification Layer, then wire `ActionEngine` (Checkpoint 5) to resolve mappings against real per-application context instead of the `'global'`-only stub used previously. This is the checkpoint that delivers the PRD's "context-aware operating layer" value proposition (PRD §2.3) — the same gesture now does different things in different applications.

### Scope

**In scope:** `ContextEngine` (TRD §3.12), the Windows `ContextAdapter` implementation (`WindowsContextAdapter`), the `context_map.json` lookup table, the Context Verification Layer's 200ms hold-before-commit logic, and rewiring `ActionEngine.resolve()` to use real context instead of the Checkpoint 5 `'global'`-only stub. *(Re-scoped per PRD v1.3 §1.2: only `WindowsContextAdapter` is built and validated in this checkpoint. `MacOSContextAdapter`/`LinuxContextAdapter` remain documented at the interface level in TRD §11.2 for Future Expansion.)*

**Out of scope:** Editing `context_map.json` via UI (Checkpoint 7's Mapping Editor, if in scope there — see Gap G-6 below). `MacOSContextAdapter`/`LinuxContextAdapter` implementation (Future Expansion, PRD §1.2).

### Deliverables

1. `context/context_engine.py` — `ContextEngine` per TRD §3.12, implementing the 250ms poll interval (FR-CA-01, unchanged from v1.1) plus the v1.2 Context Verification Layer (200ms hold-before-commit, FR-CV-01–03)
2. `context/adapters/base.py` + the Windows implementation — `ContextAdapter` ABC and `WindowsContextAdapter` (pywin32) per TRD §11.2. The ABC is written platform-agnostically so `MacOSContextAdapter`/`LinuxContextAdapter` can be added later without changing `ContextEngine` itself (TRD §11.5).
3. `assets/context_map.json` populated with the PRD's specified context mappings: Browser (chrome.exe/chrome/msedge.exe/firefox.exe → 'chrome'), PowerPoint (powerpnt.exe → 'powerpoint'), Media Players (vlc.exe, Spotify.exe → 'media_player'), VS Code (Code.exe/code → 'vscode')
4. `assets/default_mappings/*.json` populated with the PRD §8.7.2 context mapping table entries (Browser swipe-back/forward, PowerPoint swipe-slide, Media Player play/pause + track skip, VS Code terminal toggle)
5. `ActionEngine` rewired to consume `ContextEngine.resolve()`'s real output instead of Checkpoint 5's `'global'`-only stub

### Modules

- `ContextEngine` (TRD §3.12)
- `ContextAdapter` + Windows implementation (TRD §11.2; ABC interface remains platform-agnostic for Future Expansion)

### Files

```
gestureos/
├── context/
│   ├── context_engine.py
│   └── adapters/
│       ├── base.py
│       ├── windows_adapter.py
│       ├── macos_adapter.py
│       └── linux_adapter.py
├── assets/
│   ├── context_map.json
│   └── default_mappings/
│       ├── default.json            # global-context fallback mappings
│       ├── productivity.json
│       ├── presentation.json
│       ├── gaming.json
│       └── accessibility.json
└── tests/
    ├── unit/
    │   └── test_context_verification.py
    └── integration/
        └── test_context_switching.py
```

### Dependencies

Checkpoint 5 must be Done — `ActionEngine` must already exist and be functional against the `'global'` context before this checkpoint upgrades it to multi-context resolution.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Context Errors (rapid window switching causing wrong action) | Context Verification Layer (200ms hold-before-commit) is the entire purpose of this checkpoint's v1.2-specific work | Risk Matrix (Section 15); PRD §8.7.3 |
| Per-PID process-name resolution overhead on Windows (repeated `OpenProcess` calls) | Cache resolved process names per PID (TRD §9.2 implementation note) to avoid repeated expensive OS calls on every 250ms poll | |

> **Note (v1.1 of this plan):** The Wayland context-detection gap (formerly tracked as a risk in this section) applied to `LinuxContextAdapter`, which is no longer an implementation deliverable of this checkpoint per PRD v1.3 §1.2's platform-scope narrowing. This risk is retired from this checkpoint's active risk list and will resurface, scoped to whichever Future Expansion checkpoint implements Linux support, if and when that work begins.

### Acceptance Criteria

Per PRD §14.1 CP-4 acceptance criteria:

- Active window process name detected correctly on Windows (the primary release target, PRD §1.2). macOS/Linux detection accuracy, including the previously-documented Wayland limitation, is deferred to Future Expansion validation and is not an acceptance criterion for this checkpoint.
- Browser swipe gestures navigate forward/back independently of global swipe mapping
- PowerPoint swipe gestures advance/retreat slides
- Context switch takes effect within one frame once verification window elapses (~33ms at 30 FPS, per PRD — measured from the moment the 200ms verification window closes, not from the moment the OS focus event occurred)

Additionally, per PRD §14.1's CP-4 acceptance-criteria addition:

- Rapid Alt-Tab sequence (3 switches in <200ms) does not cause a misdirected action

### Testing Strategy

```python
# tests/unit/test_context_verification.py
def test_context_not_committed_before_verification_window():
    engine = ContextEngine(adapter=MockAdapter(process='chrome.exe'), context_map=test_map(),
                            verification_ms=200)
    engine.resolve(now=0.0)   # first poll, chrome.exe detected
    assert engine.committed_context == 'global'  # not yet verified

def test_context_committed_after_verification_window():
    engine = ContextEngine(adapter=MockAdapter(process='chrome.exe'), context_map=test_map(),
                            verification_ms=200)
    engine.resolve(now=0.0)
    result = engine.resolve(now=0.3)   # >200ms with same candidate context
    assert result == 'chrome'

def test_rapid_window_flapping_does_not_commit():
    """The PRD's explicit example: 3 Alt-Tab switches in 150ms, landing on
    Chrome, where intermediate windows never individually hold focus for
    200ms continuously."""
    adapter = SequenceAdapter(['app1.exe', 'app2.exe', 'chrome.exe'],
                               switch_times=[0.0, 0.05, 0.10])
    engine = ContextEngine(adapter=adapter, context_map=test_map(), verification_ms=200)
    for t in [0.0, 0.05, 0.10, 0.20, 0.30]:
        result = engine.resolve(now=t)
    assert result == 'chrome'  # only committed once it held focus 200ms continuously
    assert engine.committed_context != 'app1' and engine.committed_context != 'app2'

# tests/integration/test_context_switching.py — per TRD §13.4 exact pattern
def test_same_gesture_different_action_per_context(mock_camera_feed):
    app = build_test_app(camera=mock_camera_feed)
    app.activation_gate.state = TrackingState.ACTIVE
    app.context_engine._force_context('chrome')
    action_chrome = run_one_swipe_right(app)
    assert action_chrome.params == {'hotkey': ['alt', 'right']}
    app.context_engine._force_context('powerpoint')
    action_ppt = run_one_swipe_right(app)
    assert action_ppt.params == {'key': 'page_down'}
```

### Definition of Done

- All Acceptance Criteria pass, including the rapid-Alt-Tab non-misdirection test
- Context Engine correctly falls back to `'global'` for any process not present in `context_map.json`
- All four PRD-specified context categories (Browser, PowerPoint, Media Players, VS Code) have working end-to-end mappings from gesture → context → action
- *(Removed in v1.1 of this plan: the Wayland-degradation logging DoD item, since `LinuxContextAdapter` is no longer built in this checkpoint per PRD v1.3 §1.2 — this item moves to the Future Expansion checkpoint that eventually implements Linux support.)*

> **GAP G-6:** The requested checkpoint structure lists "Context Mapping" testing under this checkpoint but the *editing* of context mappings via UI is not explicitly assigned to either this checkpoint or Checkpoint 7 in the source documents — PRD §22.1 lists a "Mapping tab" for gesture-to-action mappings but does not explicitly describe a context-map editor UI (PRD §11.4/TRD §7.4 note that `context_map.json` "is user-editable but not exposed in the v1 Settings UI; advanced users may hand-edit it"). This plan treats `context_map.json` editing as explicitly out of UI scope for v1, consistent with that PRD note — no UI deliverable for it is scheduled in Checkpoint 7 either.
## 11. Checkpoint 7 — GUI Layer

### Purpose

Build the user-facing configuration surfaces: Settings panel, Profile management, Gesture Mapping Manager, and the Calibration Wizard. This checkpoint is sequenced last among the "core capability" checkpoints (per Section 2.2's Foundation-First rationale) precisely because every control this UI exposes must already work headlessly and be independently testable before a UI is built on top of it — building UI earlier risks designing screens around not-yet-stable APIs.

### Scope

**In scope:** `ProfileManager` (full implementation — only stubbed conceptually until now since nothing consumed real profile-switching before this checkpoint), `ui/settings_panel.py`, `ui/profile_panel.py`, `ui/mapping_editor.py`, `ui/calibration_wizard.py` + `calibration/calibration_manager.py`, `ui/main_window.py`, `ui/tray_icon.py` (the actual tray UI — `ActivationGate.toggle()` it calls was already built in Checkpoint 4), `ui/onboarding_wizard.py`.

**Out of scope:** Developer Mode's debug panel content (Checkpoint 8 — though the *toggle* for developer_mode lives in Settings here, the panel's actual data presentation is built in Checkpoint 8 once full diagnostics data exists).

### Deliverables

1. `profiles/profile_manager.py` — `ProfileManager` per TRD §3.16/PRD §11, fully implemented: load `profiles.json`, load/switch per-profile mapping files, export/import, conflict detection at load time (PRD FR-GM-03)
2. `ui/settings_panel.py` — full Settings UI covering every field in the TRD §7.2 `Settings` dataclass: Camera tab (device selector, resolution, FPS target, camera validation status), Gesture tab (confidence threshold, cooldown sliders for static/dynamic, stability window slider), Cursor tab (speed multiplier, smoothing method selector + factor, calibration wizard launcher), Profiles tab, About tab (PRD §22.1)
3. `ui/profile_panel.py` — create/rename/delete/import/export profile UI, wired to `ProfileManager`
4. `ui/mapping_editor.py` — `GestureMappingManager` UI per PRD §8.8/FR-GM-01–05: scrollable gesture-to-action mapping table, create/edit/delete mapping, conflict warning display
5. `calibration/calibration_manager.py` + `ui/calibration_wizard.py` — `CalibrationManager` per TRD §10.1 and the 4-step wizard flow per TRD §10.2 (Camera Position, Sensitivity, Cursor Speed, Tracking Area), replacing Checkpoint 5's default-zone stub (Gap G-5) with real user-calibrated `TrackingZone` data
6. `ui/main_window.py` — main control panel: tray menu, status bar, gesture mapping table view, quick-toggle switches (PRD §22.1)
7. `ui/tray_icon.py` — system tray icon with menu: Open, Toggle Tracking, Switch Profile, Settings, Quit (PRD §22.1)
8. `ui/onboarding_wizard.py` — first-run camera setup flow, distinct from the Calibration Wizard (onboarding handles camera *selection*; calibration handles gesture/cursor *tuning* — PRD treats these as related but distinct flows, FR-CAL-01 explicitly offers calibration "during first-run onboarding," implying onboarding and calibration are sequential steps of first-run, not the same screen)

### Modules

- `ProfileManager` (TRD §3.16) — first full implementation
- `CalibrationManager` (TRD §10.1)
- UI layer components (TRD §8 `ui/` folder) — all new

### Files

```
gestureos/
├── profiles/
│   └── profile_manager.py
├── calibration/
│   └── calibration_manager.py
├── ui/
│   ├── main_window.py
│   ├── settings_panel.py
│   ├── mapping_editor.py
│   ├── profile_panel.py
│   ├── onboarding_wizard.py
│   ├── calibration_wizard.py
│   └── tray_icon.py
├── assets/
│   └── icons/                       # app icon, tray icon
└── tests/
    └── unit/
        └── test_profile_manager.py
```

### Dependencies

Checkpoint 6 must be Done — Settings/Profile/Mapping UI all configure behavior across the full pipeline (Recognition, Activation, Actions, Context), which must all already be functional headlessly.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Calibration wizard's "suggest confidence threshold" heuristic suggests a poor value for atypical users | TRD §16's documented stance: the suggestion is a starting point, not locked in — manual override remains available in Settings after calibration completes | TRD §16 Technical Risk row 4 |
| GUI thread / CaptureThread cross-thread violations (UI accidentally touching pipeline objects directly) | Enforce TRD §2.2's signal-only communication discipline in code review — UI components read pipeline state only via Qt signals, never by holding direct references to `GestureEngine`/`TrackingModule`/etc. | TRD §2.2 |
| Calibration wizard exceeds the 3-minute completion target (FR-CAL-04) for less tech-savvy users | Enforced via UI flow design (4 short, guided steps) per TRD §10.2 — not a hard software timeout, validated in UAT (Checkpoint 9) rather than this checkpoint alone | PRD §17.5 UAT scenario "Complete calibration wizard" |

### Acceptance Criteria

Per PRD §14.1 CP-5 acceptance criteria:

- Settings panel reads and writes `settings.json` correctly
- Profiles can be created, switched, exported, and imported
- Mapping editor shows all current mappings; additions and deletions persist to JSON
- System tray icon with Toggle Tracking, Switch Profile, and Quit menu items
- Calibration wizard functional for cursor tracking zone

### Testing Strategy

UI components are tested primarily via their underlying manager classes (`ProfileManager`, `CalibrationManager`), since PyQt6 widget testing benefits less from the synthetic-data unit-test pattern used elsewhere (TRD §13.2's "no camera required" principle extends naturally to "no display required" for these tests):

```python
# tests/unit/test_profile_manager.py
def test_profile_switch_loads_correct_mappings(tmp_path):
    manager = ProfileManager(config_dir=tmp_path)
    manager.switch_to('presentation')
    mappings = manager.active_mappings()
    assert any(m['gesture'] == 'swipe_right' and m['context'] == 'global' for m in mappings)

def test_mapping_conflict_detected_keeps_first(tmp_path):
    # Two mappings for (swipe_right, chrome) in the same file
    write_conflicting_mapping_file(tmp_path)
    manager = ProfileManager(config_dir=tmp_path)
    with caplog_warning() as warnings:
        manager.switch_to('conflicting_profile')
    assert 'Mapping conflict' in warnings[0]

def test_export_import_round_trip(tmp_path):
    manager = ProfileManager(config_dir=tmp_path)
    exported_path = manager.export('productivity', tmp_path / 'export.json')
    manager2 = ProfileManager(config_dir=tmp_path / 'other_install')
    imported = manager2.import_from(exported_path)
    assert imported.id == 'productivity'
```

Manual/exploratory UAT-style testing (formalized in Checkpoint 9): full calibration wizard walkthrough timed against the 3-minute target.

### Definition of Done

- All Acceptance Criteria pass
- `ProfileManager` unit tests pass at ≥80% coverage (TRD §13.7)
- A full manual walkthrough of onboarding → calibration → profile switch → mapping edit → export/import succeeds without crashes
- No UI component holds a direct reference to a `CaptureThread`-owned object — verified by code review against TRD §2.2's threading discipline
## 12. Checkpoint 8 — Diagnostics Layer

### Purpose

Complete the full Debugging & Diagnostics system: the extended structured-logging categories introduced incrementally by every prior checkpoint are now joined by the remaining quality-monitoring components (`LightingMonitor`, full `CameraValidator` warning-surfacing), the complete Developer Mode debug panel, and the error-recovery policies that weren't already exercised by earlier checkpoints' own error handling. This checkpoint is sequenced after GUI (Checkpoint 7) because the Debug Overlay is a UI surface that depends on `OverlayEngine` already supporting the badge/status-bar rendering patterns established in Checkpoints 1 and 4.

### Scope

**In scope:** `LightingMonitor` (full implementation — TRD §3.4), `CameraValidator`'s warning-surfacing UX (the measurement logic was built in Checkpoint 1; this checkpoint adds the overlay-visible warning badge per FR-VF-07), the full Developer Mode debug panel (`overlay/debug_panel.py`), the remaining error-recovery policies from TRD §9.4 not already covered by individual components' own error handling.

**Out of scope:** Any new pipeline-stage component — this checkpoint is purely about observability of, and recovery around, components already built in Checkpoints 1–7.

### Deliverables

1. `diagnostics/lighting_monitor.py` — `LightingMonitor` per TRD §3.4, implementing brightness analysis correlated with hand-detection confidence, the 3-second sustained-low-light threshold, and the per-session-dismissible-but-recurring warning behavior (PRD FR-LQ-01–04)
2. `CameraValidator`'s warning now surfaced in the overlay (FR-VF-07) — wiring the already-functional measurement (Checkpoint 1) to a visible badge
3. `overlay/debug_panel.py` — the full Developer Mode panel per TRD §9.3: landmark IDs + coordinates, finger states + angles, normalized distances, hand scale (palm width/height/bounding box), motion vectors, confidence scores, cooldown timers, gesture stability timer progress, gesture state machine status per hand role (PRD §12.2)
4. `diagnostics/diagnostics_manager.py` extended with the full ring-buffer (TRD §3.16/§9.1) feeding the debug panel, capped at 200 events to bound memory (TRD §3.16 Error Handling)
5. Verification pass across TRD §9.4's full Error Recovery Policy Table — each row's recovery behavior is exercised by a dedicated test in this checkpoint, even where the underlying component (e.g., `CameraModule`'s reconnect logic) was already built in an earlier checkpoint, since this is the checkpoint responsible for diagnosability of failures, not just their existence

### Modules

- `LightingMonitor` (TRD §3.4) — new
- `CameraValidator` — extended (warning surfacing)
- `DiagnosticsManager` — extended (full ring buffer, all log categories now active)
- `OverlayEngine` — extended (debug panel, quality-warning badges)

### Files

```
gestureos/
├── diagnostics/
│   ├── lighting_monitor.py
│   └── diagnostics_manager.py      # extended: ring buffer for debug panel
├── overlay/
│   ├── debug_panel.py
│   └── overlay_window.py            # extended: quality-warning badges
└── tests/
    ├── unit/
    │   └── (lighting monitor unit tests)
    └── integration/
        └── (error-recovery policy verification tests, one per TRD §9.4 row)
```

### Dependencies

Checkpoint 7 must be Done — the debug panel and quality-warning badges extend `OverlayEngine`/`ui/` patterns established through Checkpoint 7.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Lighting Issues | `LightingMonitor`'s sustained 3-second dual-condition (brightness + confidence) check, advisory-only behavior (never blocks processing) | Risk Matrix (Section 15); PRD §8.12 |
| Debug panel rendering overhead degrading FPS when Developer Mode is enabled | Debug panel only renders when `developer_mode=true` (opt-in); performance impact of the panel itself is measured as part of Checkpoint 9's performance budget testing, not assumed safe here | TRD §15.2 (new pipeline stages' negligible-cost analysis covers the underlying data collection, but rendering cost is separate and must be measured) |
| Ring buffer unbounded growth if `maxlen` is misconfigured | `deque(maxlen=200)` is a hard cap, not a soft target — unit tested explicitly | TRD §3.16 Error Handling |

### Acceptance Criteria

The PRD's CP-6 acceptance criteria (PRD §14.1) bundle diagnostics with the robustness items already covered in Checkpoint 2 (occlusion, primary hand). The diagnostics-specific subset, applicable to this checkpoint:

- Lighting warning appears within 3s of moving to a darkened room and disappears within a reasonable interval after lights return
- Developer Mode panel displays all data items listed in PRD §12.2 correctly and matching the values used by the actual gesture decision that frame (TRD §3.4/§9.3's design principle: the panel must show the *same* data that drove the last action, not a separately-sampled value)
- Every row in TRD §9.4's Error Recovery Policy Table has a corresponding passing test demonstrating the documented recovery behavior

### Testing Strategy

```python
# tests/unit/test_lighting_monitor.py
def test_sustained_low_light_detected():
    monitor = LightingMonitor()
    dark_frame = synthetic_frame(brightness=30)  # well below 60 threshold
    t = 0.0
    quality = None
    while t < 3.5:
        quality = monitor.check(dark_frame, hand_confidence=0.4, now=t)
        t += 0.1
    assert quality.is_low is True

def test_brief_low_light_not_flagged():
    monitor = LightingMonitor()
    dark_frame = synthetic_frame(brightness=30)
    quality = monitor.check(dark_frame, hand_confidence=0.4, now=0.0)
    assert quality.is_low is False  # not sustained yet

# tests/integration/test_error_recovery_policies.py
# One test per TRD §9.4 row, e.g.:
def test_occlusion_window_expiry_releases_hand_to_reidentification():
    ...  # exercises OcclusionHandler + HandIdentityModule together,
         # verifying the documented recovery path end-to-end

def test_context_flapping_never_force_commits():
    ...  # exercises ContextEngine under sustained rapid switching,
         # verifying no timeout-forced commit occurs (TRD §9.4 explicit
         # "no timeout-forced commit, by design" row)
```

### Definition of Done

- All Acceptance Criteria pass
- Every row of TRD §9.4's Error Recovery Policy Table has a passing automated test
- Debug panel verified to show data consistent with the actual dispatched action in a side-by-side manual check (not just "panel renders without crashing")
- Ring buffer capacity is unit-tested at its 200-event boundary
## 13. Checkpoint 9 — Testing & Optimization

### Purpose

Execute the full test pyramid (TRD §13.1) against the complete, feature-frozen system: comprehensive unit coverage verification, full integration testing, performance/stress testing against the PRD §16 Performance Budgets, and multi-user/multi-distance/multi-lighting gesture-accuracy validation per PRD §17.2. This checkpoint exists separately from feature checkpoints because performance numbers measured against an incomplete pipeline (Section 2.3) would need to be re-measured anyway — this is the first point where measuring against the *real, complete* pipeline is meaningful.

### Scope

**In scope:** aggregating and verifying unit-test coverage across all checkpoints, building out the remaining integration tests not already required by earlier checkpoints, building the performance/stress test suite, executing PRD §17.2's multi-distance/multi-lighting accuracy testing, executing PRD §17.5's UAT scenarios.

**Out of scope:** fixing newly-discovered architectural defects by inventing new requirements — any gap discovered here that requires a product decision (not just a bug fix) is logged as a new Gap (continuing this document's G-numbering) for product-owner review, not silently resolved.

### Deliverables

1. Coverage audit across all of `gestures/`, `actions/`, `profiles/`, `settings/`, `tracking/` confirming ≥80% per TRD §13.7, with any shortfall addressed by adding tests (not by lowering the bar)
2. `tests/performance/test_fps_and_memory.py` fully implemented per TRD §13.6, asserting all five PRD §16 Performance Budget targets simultaneously: FPS ≥25, Detection Latency <100ms, End-to-End Action Latency <150ms, CPU <20%, Memory <300MB
3. Stress testing: 30-minute and 4-hour continuous-session runs (PRD §17.3/TRD §13.6) verifying sustained FPS and bounded memory growth (<10MB/hour, per PRD §21.1's "Memory Usage" KPI methodology even though the headline budget in §16 is an absolute 300MB ceiling — both are verified)
4. Gesture accuracy testing per PRD §17.2: 100 samples per gesture, 5 users, 3 lighting conditions (bright/dim/backlit), **3 camera distances (close ~30cm / medium ~75cm / far ~150cm)** — the distance dimension is the PRD v1.2-specific addition validating Checkpoint 2/3's scale-invariance work under real, not synthetic, conditions
5. UAT execution per PRD §17.5's five scenarios: full presentation control, 10-minute hands-free browsing, 15-task accessibility completion, video-call false-trigger check, calibration wizard timing
6. A finalized risk-acceptance review of every Gap (G-1 through G-6, see Sections 5–11 above) raised during implementation, each either resolved with explicit product-owner sign-off or formally accepted as a documented limitation for this release

### Modules

No new TRD §3 components — this checkpoint validates, optimizes, and (where performance budgets are missed) tunes existing components' internal parameters (e.g., adjusting `motion_history_frames` default if profiling shows a different value better balances accuracy vs. memory — within the PRD's already-specified valid range of 10–40, never outside it).

### Files

```
gestureos/
└── tests/
    ├── performance/
    │   └── test_fps_and_memory.py   # full implementation per TRD §13.6
    └── (coverage gaps filled across unit/ and integration/ as identified by the audit)
```

### Dependencies

Checkpoint 8 must be Done — this checkpoint tests the complete, fully-instrumented system.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| Performance budget (especially the tightened <20% CPU target, PRD §16 note) not achievable without degrading FPS | Per PRD §16's own explicit guidance: "If CP-7 [this plan's Checkpoint 9] performance testing shows <20% is not achievable without degrading FPS below 25, CPU budget is the parameter to revisit — FPS and latency are the higher-priority constraints." This is not a gap; the PRD already specifies the tie-breaking priority. | PRD §16 |
| GIL contention between CaptureThread and Qt event loop causing UI stutter under load | TRD §16's documented risk; profile with `cProfile` (TRD §15.3 harness) specifically during this checkpoint; only escalate to multiprocessing if profiling shows genuine contention, not preemptively | TRD §16 Technical Risk row 1 |
| Pipeline depth (17 stages, TRD §5.1) adds cumulative per-frame overhead even if individually cheap | Run the full TRD §15.3 profiling harness and verify cumulative overhead empirically rather than assuming the "each stage is cheap" analysis (TRD §15.2) holds in aggregate | TRD §16 Technical Risk row 2 |

### Acceptance Criteria

Per PRD §16.2 (Performance Targets) and §21.1 (Product KPIs), all measured simultaneously on the **Reference Hardware Baseline defined in PRD §16.1** (Intel Core i5 8th Gen or equivalent, 8 GB RAM, 720p webcam — this is the only hardware spec against which these targets are valid; results on other hardware are informational only):

| Metric | Target |
|---|---|
| FPS | ≥ 25 |
| Detection Latency | < 100 ms |
| End-to-End Action Latency | < 150 ms |
| CPU Usage | < 20% (single core average) |
| Memory Usage | < 300 MB |
| Gesture Recognition Accuracy | ≥ 95%, stable within 3% across near/medium/far distances |
| False Trigger Rate | < 5% |
| Double-Trigger Rate | 0% for single physical gestures |
| Session Crash Rate | < 1 per 8h |
| Activation Misfire Rate | 0% in INACTIVE |

Plus all PRD §17.5 UAT pass criteria (5 scenarios, see Deliverable 5 above).

### Testing Strategy

```python
# tests/performance/test_fps_and_memory.py — TRD §13.6 reference implementation
def test_performance_budgets_all_met(running_app_30min_session):
    session = running_app_30min_session
    avg_fps = sum(session.fps_log) / len(session.fps_log)
    avg_cpu = sum(session.cpu_samples) / len(session.cpu_samples)
    peak_memory_mb = max(session.memory_samples)
    assert avg_fps >= 25
    assert avg_cpu < 20
    assert peak_memory_mb < 300

def test_memory_growth_under_threshold(running_app_4h_session):
    start_mb, end_mb = running_app_4h_session.memory_samples
    growth_per_hour = (end_mb - start_mb) / 4
    assert growth_per_hour < 10
```

Gesture accuracy testing is executed as a manual/semi-automated protocol (cannot be a pure pytest unit test, since it requires real human subjects per PRD §17.2): a test coordinator records each of the 14 gestures × 5 users × 3 lighting conditions × 3 distances, logs detected-vs-intended gesture for each trial, and computes per-gesture precision/recall/F1 against the ≥95% accuracy bar.

### Definition of Done

- All Acceptance Criteria metrics pass simultaneously in a single 30-minute reference-hardware session
- 4-hour memory-growth test passes
- Gesture accuracy testing completed across the full 14-gesture × 5-user × 3-lighting × 3-distance matrix with results documented, and ≥95% accuracy achieved at every distance tested (the explicit scale-invariance validation gate)
- All 5 UAT scenarios pass with their documented participant counts and pass criteria
- Every open Gap (G-1 through G-6) has a documented disposition (resolved or formally accepted) before proceeding to Checkpoint 10
## 14. Checkpoint 10 — Packaging & Deployment

### Purpose

Produce the final, installable, native-executable build for the Windows primary release target, per PRD §20 Deployment Requirements and TRD §12 Packaging Strategy, and validate the release artifact end-to-end before it is considered shippable. *(Re-scoped per PRD v1.3 §1.2: macOS and Linux packaging are Future Expansion deliverables, not part of this checkpoint's release scope.)*

### Scope

**In scope:** PyInstaller spec finalization, Windows installer creation (Inno Setup), the startup self-check (TRD §10.5/§12.4), and final release-artifact validation for Windows.

**Out of scope:** any application code changes — this checkpoint packages what Checkpoint 9 already validated; if packaging surfaces a defect (e.g., the MediaPipe bundling issue flagged as a risk since Checkpoint 1), the fix happens in the relevant component's code, but no new feature work occurs here. macOS (`.dmg`/notarization) and Linux (AppImage/`.deb`) packaging — deferred to Future Expansion (PRD §1.2); the TRD §12.3 packaging spec for these platforms remains documented and ready to execute against when that phase begins.

### Deliverables

1. `pyinstaller.spec` finalized per TRD §12.2, with the MediaPipe model-file bundling explicitly verified (not just present in the spec — confirmed working in a built artifact, closing the loop on the risk flagged since Checkpoint 1)
2. Windows: Inno Setup installer script producing `GestureOS_Setup.exe` (Start Menu entry, optional auto-start registry key) per PRD §20.2/TRD §12.3
3. CI build pipeline per TRD §12 implementing the Windows build (the matrix build expands to include macOS/Linux runners when Future Expansion packaging work begins, per TRD §12.3's documented future targets)
4. Startup self-check (TRD §10.5/§12.4) verifying on first launch: MediaPipe model file present, ≥1 camera enumerable, `~/.gestureos/` writable, default mapping/profile JSON files copied successfully — with a specific diagnostic dialog (not a generic crash) on any failure
5. Final Release Deliverables package per PRD §20.3: the packaged executable/installer, user documentation, gesture reference card, calibration walkthrough, and default configuration files bundled and verified to be copied into `~/.gestureos/` on first launch

> **Deferred to Future Expansion (documented in TRD §12.3, not built in this checkpoint):** macOS code-signed, notarized `GestureOS.app` wrapped in a `.dmg` via `create-dmg`; Linux AppImage (primary) and `.deb` (secondary).

### Modules

No TRD §3 pipeline components — this checkpoint is exclusively packaging/build infrastructure.

### Files

```
gestureos/
├── pyinstaller.spec                # finalized
├── installer/
│   ├── windows/
│   │   └── installer.iss            # Inno Setup script (primary release target)
│   ├── macos/
│   │   └── create-dmg-config        # documented for Future Expansion — not built in this checkpoint
│   └── linux/
│       ├── AppImageBuilder.yml      # documented for Future Expansion — not built in this checkpoint
│       └── debian/                  # documented for Future Expansion — not built in this checkpoint
├── docs/
│   ├── user_guide.md
│   ├── gesture_reference_card.md
│   └── calibration_walkthrough.md
└── .github/workflows/ (or equivalent CI config)
    └── release_build.yml             # Windows build only for initial release;
                                       # expands to macOS/Linux matrix in Future Expansion phase
```

### Dependencies

Checkpoint 9 must be Done — packaging validates and ships what testing has already certified; packaging a non-validated build is explicitly out of order per this plan's Foundation-First philosophy applied to release readiness.

### Risks

| Risk | Mitigation | Cross-Ref |
|---|---|---|
| PyInstaller + MediaPipe packaging fragility (the build works from source but breaks when packaged) | This risk was deliberately surfaced early via a smoke-build in Checkpoint 1 (Section 5, Risks row 2) specifically so it would not be discovered for the first time at this late checkpoint; this checkpoint's job is final verification, not first discovery | TRD §16 Technical Risk row 2 |
| Windows installer silent-fail on some Windows 10 configurations (NSIS/Inno Setup edge cases with UAC or antivirus interference) | Test the installer on at least two distinct Windows 10/11 configurations before declaring Checkpoint Done; document any known per-configuration caveats in the release notes | |

> **Note (v1.1 of this plan):** The macOS notarization failure risk and Linux AppImage fragmentation risk tracked in previous drafts are retired from this checkpoint's active risk list, as those build targets are deferred to Future Expansion (PRD §1.2). They will resurface in whichever Future Expansion checkpoint adds macOS/Linux packaging.

### Acceptance Criteria

Per PRD §20.4 Release Acceptance Gate:

- All checkpoints (0–10, this plan's full sequence) have met their individual Definition of Done
- Performance Budgets (PRD §16) verified on reference hardware using the **packaged** artifact, not just the from-source build (this is a deliberate re-verification, since packaging can itself introduce performance regressions, e.g., from `--onefile` self-extraction overhead if that mode were mistakenly used instead of the recommended `--onedir`, TRD §10.1)
- No P0 bugs open
- Release deliverables (PRD §20.3) confirmed present in the build artifact: executable/installer, documentation, gesture reference card, calibration walkthrough, default configurations

### Testing Strategy

This checkpoint's testing is primarily artifact-level validation rather than unit/integration code testing:

```python
# tests/packaging/test_startup_self_check.py — run against the PACKAGED build, not source
def test_packaged_app_finds_mediapipe_model():
    result = run_packaged_executable(args=['--self-check'])
    assert 'MediaPipe model file: OK' in result.stdout

def test_packaged_app_creates_config_dir():
    clean_test_environment()  # no pre-existing ~/.gestureos/
    run_packaged_executable(args=['--self-check'])
    assert (test_home / '.gestureos' / 'settings.json').exists()
    assert (test_home / '.gestureos' / 'mappings' / 'default.json').exists()
```

Manual validation: full install → first-run onboarding → calibration → basic gesture-control session on a clean Windows machine (no prior GestureOS install, no Python install), performed by someone other than the implementing engineer to catch assumptions baked in from familiarity with the dev environment. *(macOS and Linux clean-machine validation is a Future Expansion deliverable, not required for this checkpoint.)*

### Definition of Done

- Windows build artifact (`GestureOS_Setup.exe`) builds successfully in CI
- Startup self-check passes on a clean Windows machine (no prior GestureOS install, no prior Python install)
- Performance Budgets (PRD §16.2, measured on the Reference Hardware Baseline in PRD §16.1) re-verified against the packaged Windows artifact specifically
- All PRD §20.3 Release Deliverables are present and verified in the Windows build artifact
- PRD §20.4 Release Acceptance Gate is fully satisfied — this is the final gate of the entire Implementation Plan for the initial Windows release
## 15. Risk Management

### 15.1 Consolidated Risk Matrix

This matrix consolidates every risk referenced across the checkpoint sections above, plus the requested explicit risk set (Cursor Jitter, Gesture Flicker, Scale Sensitivity, Camera Disconnect, Context Errors, Lighting Issues, Multiple Hands), drawing severity/mitigation directly from PRD §18/§19 and TRD §16 — no new risk severities or mitigations are invented here; this section organizes and cross-references what the source documents already establish, adding Probability and Validation columns as requested.

| Risk | Severity | Probability | Mitigation | Validation | Checkpoint |
|---|---|---|---|---|---|
| Cursor Jitter | High | High (inherent to any raw landmark tracking) | Cursor Smoothing — EMA default, Moving Average / One Euro Filter alternatives (PRD §8.4, TRD §3.14) | Static-hand-hold variance test (Checkpoint 5); subjective UAT feedback (Checkpoint 9) | CP 5 |
| Gesture Flicker | High | Medium (depends on user steadiness) | Gesture Stability Requirement — 200ms continuous hold (PRD §8.2, TRD §3.10) | `test_single_frame_flicker_does_not_trigger` (TRD §13.5) | CP 3 |
| Double Trigger | High | Medium | Cooldown System — per (hand, gesture) timer (PRD §8.3, TRD §3.11) | `test_cooldown_suppresses_repeated_trigger` (TRD §13.5) | CP 3 |
| Scale Sensitivity | High | High (inherent to any camera-distance-dependent system without normalization) | Finger Angles + Normalized Distances — Priority 1–4 recognition order (PRD §5, TRD §4) | Parametrized scale-invariance unit tests (TRD §4.6); 3-distance UAT accuracy testing (PRD §17.2, Checkpoint 9) | CP 2/3 |
| Gesture Conflict / Ambiguous Candidate | Medium | Medium (transitional hand poses between two gestures) | `ConflictResolver` (PRD §4.6, TRD §3.9.1) — confidence-based selection with fixed priority tie-break; previously an implicit "first-match" order, now explicit and tested | `test_conflict_resolver.py`: multi-candidate, tie-break, and cross-hand independence cases (Checkpoint 3) | CP 3 |
| Hand Crossing / Multiple Hands (Multi-Hand Ambiguity) | Medium | Medium | Hand Identity Tracking — persistent role assignment with proximity re-identification (PRD §8.1.1, TRD §3.5); Primary Hand Selection for unwanted extra hands (PRD §8.1.3, TRD §3.8) | Simulated crossing sequence test (TRD §13's canonical `test_roles_preserved_across_crossing`) | CP 2 |
| Lighting Issues | Medium | High (environment-dependent, outside the user's control in many cases) | Lighting Quality Detection — sustained brightness+confidence monitoring (PRD §8.12, TRD §3.4) | `test_sustained_low_light_detected` (Checkpoint 8) | CP 8 |
| Camera Disconnect | Medium | Low-Medium (hardware-dependent) | Auto Reconnect — 10 attempts, 2s interval (TRD §3.1) | Manual physical-disconnect test (Checkpoint 1) | CP 1 |
| Context Errors | Medium | Medium (common during normal multi-app workflows) | Context Verification Layer — 200ms hold-before-commit (PRD §8.7.3, TRD §3.12) | Rapid-Alt-Tab non-misdirection test (Checkpoint 6) | CP 6 |
| CPU Usage | Medium | Medium (depends on target hardware tier) | Performance Budget — <20% target, with FPS/latency prioritized; measured against PRD §16.1 Reference Hardware Baseline (Intel i5 8th Gen, 8GB RAM, 720p) | Full performance-budget test suite (Checkpoint 9) | CP 9 |
| Background Gesture Triggers | High | High (this is the default behavior without mitigation) | Activation Mode — gestures ignored unless explicitly activated (PRD §7) | Zoom-call scenario validation (Checkpoint 4) | CP 4 |
| Gesture Overload | Medium | Low (a design-discipline risk, not a runtime risk) | Recommend 8–12 gestures per profile (PRD §8.8/FR-GM-05) | Reviewed at default-mapping authoring time (Checkpoint 6) | CP 6 |
| Camera Quality Differences | Medium | Medium | Camera Validation System — startup + sustained FPS/resolution checks (PRD §8.11, TRD §3.2) | `test_sustained_low_fps_detected_after_5s` (Checkpoint 1) | CP 1 |
| User Fatigue (Gorilla Arm) | Medium | Medium (usage-pattern dependent, not directly software-mitigable) | Short/medium-duration interaction framing stated in PRD §2.3.1; gestures designed for desk-height use | UAT subjective feedback only — **GAP G-7:** neither PRD nor TRD specifies a concrete "usage break reminder" mechanism; flagged for product-owner decision | CP 9 (UAT only) |
| OS API Compatibility (Windows) | Low | Low (mitigated architecturally) | `WindowsExecutor`/`WindowsContextAdapter` encapsulate all Windows-specific API calls behind the platform-agnostic ABC interface (TRD §11); macOS/Linux API compatibility is a Future Expansion risk, not a current-release risk (PRD §1.2) | Windows integration testing (Checkpoint 5/6/9) | CP 5/6/9 |
| Performance on Low-End Hardware | Medium | Medium | Low-res mode, configurable FPS target (PRD §16, TRD §15); PRD §16.1 Reference Hardware Baseline is the measurement target — **GAP G-8:** no explicit sub-baseline hardware test spec | Performance budget testing on PRD §16.1 reference hardware | CP 9 |
| PyInstaller + MediaPipe Packaging Fragility | High (build-breaking if missed) | Medium (a known class of issue, not certain to recur) | Explicit `datas[]` bundling of MediaPipe model files (TRD §12.2); smoke-build verification starting at Checkpoint 1 | Packaged-build startup self-check (Checkpoint 10) | CP 1 (early detection), CP 10 (final verification) |
| GIL Contention (CaptureThread vs. Qt event loop) | Medium | Low-Medium (depends on how much pure-Python work ends up in the per-frame path) | Keep per-frame pure-Python logic O(1)/minimal; profile before considering multiprocessing | `cProfile` harness (TRD §15.3, Checkpoint 9) | CP 9 |

### 15.2 Risk Review Cadence

**GAP G-9:** Neither PRD nor TRD specifies a risk-review cadence (e.g., weekly engineering sync, per-checkpoint retrospective) — this is a project-management process detail outside either source document's scope. This plan recommends, but does not mandate without product-owner/engineering-lead sign-off, reviewing this risk matrix at the close of every checkpoint (i.e., as part of each checkpoint's Definition of Done review) rather than on a separate calendar cadence, since checkpoint boundaries already represent natural integration points.

---

## 16. Definition of Done

### 16.1 Checkpoint Definition of Done (General Template)

Every checkpoint (Sections 4–14 above) has its own specific Definition of Done, but all of them share this common baseline, derived from the per-checkpoint criteria already established:

A checkpoint is Done when, and only when:

1. **All Deliverables exist** as files in the locations specified by that checkpoint's Files section, matching the TRD §8 folder structure exactly
2. **All Modules implemented match their TRD §3 specification exactly** — Responsibilities, Inputs, Outputs, Dependencies, and Error Handling as documented, with no reinterpretation
3. **All Acceptance Criteria pass**, verified by the checkpoint's Testing Strategy
4. **Unit test coverage meets or exceeds 80%** for any new or modified module in scope, per TRD §13.7
5. **No regressions in prior checkpoints' Acceptance Criteria** — re-running each prior checkpoint's test suite still passes
6. **No scope creep** — no file or component belonging to a later checkpoint has been created prematurely (explicitly called out in Checkpoint 0's Definition of Done as a checkpoint-failure condition, and implicitly applicable to every checkpoint)
7. **Any Gap encountered is documented**, not silently resolved with an invented requirement (Core Principle, applied throughout)
8. **Code review confirms architectural discipline** — TRD §2.2's threading rules, TRD §4.3's scale-invariance rule, TRD §3's Component Boundary Rule are all respected

### 16.2 Feature Definition of Done

Distinct from a *checkpoint's* Definition of Done, an individual *feature* (e.g., a single gesture, a single settings field, a single platform adapter) is Done when:

1. The feature's behavior matches its PRD requirement ID (FR-* or NFR-*) exactly — traceable via Section 3.2's matrix
2. The feature's TRD-specified implementation (data model fields, error handling, dependencies) is followed exactly
3. The feature has dedicated unit test(s) covering both its success path and its documented Failure Cases (where the checkpoint section above enumerates them, as with every gesture in Checkpoint 3)
4. The feature is exercised by at least one integration test once the pipeline reaches a stage where integration testing is meaningful (from Checkpoint 4 onward, per Section 2.3)
5. The feature does not introduce a new raw-pixel threshold, a new untracked network call, a new cross-thread violation, or any other violation of this plan's Core Principles (Section 1.3)

### 16.3 Project Definition of Done

GestureOS as a whole is Done when:

1. **All 11 checkpoints (Checkpoint 0–10) have individually met their Definition of Done**, in the sequence defined by Section 2 (no checkpoint was started before its dependency was Done)
2. **Every PRD v1.2 functional and non-functional requirement is implemented and verified** — confirmed via Section 3.2's traceability matrix with no unaddressed row
3. **Every PRD v1.2 Success Metric (PRD §21.1) is met** on reference hardware, verified in Checkpoint 9, and re-verified against the packaged artifact in Checkpoint 10
4. **PRD §20.4's Release Acceptance Gate is satisfied**: all checkpoints Done, Performance Budgets verified on the packaged build, zero open P0 bugs, all Release Deliverables present
5. **Every Gap raised during implementation (G-1 through G-9, and any discovered during execution beyond this plan's authoring) has a documented disposition** — either resolved with explicit product-owner sign-off and reflected in a PRD/TRD revision, or formally accepted as a known limitation for this release, recorded in release documentation
6. **No requirement, architecture decision, or feature from the PRD or TRD was altered, removed, or silently reinterpreted during implementation** — any case where implementation reality diverged from the source documents was surfaced as a Gap and resolved through the proper channel (product-owner/architect review), not through unilateral implementation-time decisions

---

## Appendix A — Gap Register

A consolidated list of every Gap flagged throughout this plan, for product-owner/architect review:

| Gap ID | Description | Location | Status |
|---|---|---|---|
| G-1 | PRD §14 checkpoint numbering has no explicit "Checkpoint 0" equivalent for foundational scaffolding | Section 3.1 | Resolved in this plan (Checkpoint 0 added); recommend reflecting in next PRD revision |
| G-2 | "Developer Dashboard" requested in Checkpoint 1 has no PRD/TRD definition distinct from Overlay + Developer Mode debug panel | Section 5 | Resolved by scoping: minimal FPS/landmark-count view at CP1, full debug panel at CP8 |
| G-3 | No disambiguation rule specified between "Wave" and "two consecutive opposite swipes" | Section 7.2 | Open — requires product-owner decision before Checkpoint 3 closes, or formal acceptance as documented limitation |
| G-4 | No conflict-detection/fallback specified for the global activation keyboard shortcut colliding with OS/other app shortcuts | Section 8 | Open — low-severity, recommend accepting as documented limitation unless UAT surfaces real-world conflicts |
| G-5 | `TrackingZone` formally belongs to Checkpoint 7's Calibration Subsystem but `CursorController` (Checkpoint 5) requires it to function | Section 9 | Resolved by sequencing accommodation: default full-frame zone implemented at CP5, wizard-driven custom zone at CP7 |
| G-6 | `context_map.json` editing UI ownership not explicitly assigned by either source document | Section 10 | Resolved: explicitly out of v1 UI scope, consistent with TRD §7.4's note that it's "not exposed in the v1 Settings UI" |
| G-7 | No concrete "usage break reminder" mechanism specified for the Gorilla Arm fatigue risk | Section 15.1 | Open — requires product-owner decision |
| G-8 | No explicit low-end-hardware test machine specified beyond the mid-tier reference hardware spec | Section 15.1 | Open — requires product-owner/QA decision on whether low-end validation is in scope for this release |
| G-9 | No risk-review cadence specified by either source document | Section 15.2 | Open — process recommendation offered, requires engineering-lead sign-off |

---

*End of GestureOS Implementation Plan v1.0.0*
