# Implementation Plan — GestureOS

**Document Type:** Implementation Plan (Execution Roadmap)
**Source Documents:** GestureOS PRD v2.0, GestureOS TRD v2.0, GestureOS AI Development Guide v2.0, RULES.md v2.0
**Source of Truth:** Architecture Freeze Specification v1.0 (2026-07-04)
**Version:** 2.0.1
**Audience:** Engineering team, AI coding agents, project management
**Date:** July 2026

> **Major Changes from v2.0.0:**
> - Restructured to reflect actual repository state. The V2.0 architecture documentation was finalized in July 2026 but the codebase remains on a V1.x checkpoint structure. This plan bridges that gap with an expanded CP-0 that migrates the repository to V2.0 compliance.
> - All existing components are marked as **Completed**, **Partially Completed**, or **Pending** based on the July 2026 codebase audit. No existing work is discarded — it is migrated, renamed, or refactored in place.
> - CP-0 expanded to include all repository restructuring, file renaming, new directory creation, ModelManager, ExtensionRegistry, ABC interfaces, shared datamodel updates, naming migration, and documentation compliance tasks.
> - 10 checkpoints total (CP-0 through CP-9). CP-9 is a new architecture certification checkpoint.
> - Every task from PRD v2.0, TRD v2.0, AI Development Guide v2.0, and RULES.md v2.0 is assigned to exactly one checkpoint in dependency order.

---

## Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [Repository State Assessment](#2-repository-state-assessment)
3. [Development Strategy](#3-development-strategy)
4. [Checkpoint 0 — Foundation & Repository Migration](#4-checkpoint-0--foundation--repository-migration)
5. [Checkpoint 1 — Core Platform & ML Foundation](#5-checkpoint-1--core-platform--ml-foundation)
6. [Checkpoint 2 — Hand Analysis Layer](#6-checkpoint-2--hand-analysis-layer)
7. [Checkpoint 3 — Static Gesture Engine](#7-checkpoint-3--static-gesture-engine)
8. [Checkpoint 4 — Activation & Command Routing](#8-checkpoint-4--activation--command-routing)
9. [Checkpoint 5 — Action Execution](#9-checkpoint-5--action-execution)
10. [Checkpoint 6 — GUI & Calibration](#10-checkpoint-6--gui--calibration)
11. [Checkpoint 7 — Diagnostics & Developer Mode](#11-checkpoint-7--diagnostics--developer-mode)
12. [Checkpoint 8 — Testing, Optimization & Packaging](#12-checkpoint-8--testing-optimization--packaging)
13. [Checkpoint 9 — V2 Architecture Certification](#13-checkpoint-9--v2-architecture-certification)
14. [V2 Forward Reference](#14-v2-forward-reference)
15. [Risk Management](#15-risk-management)
16. [Definition of Done](#16-definition-of-done)

---

## 1. Executive Overview

### 1.1 Project Summary

GestureOS is a Windows desktop application that acts as an intelligent gesture-based operating layer between the user and the operating system, enabling touchless control via webcam-based hand gesture recognition (PRD §1–3). V1 recognition is **AI-assisted**: Google's MediaPipe Gesture Recognizer is the primary engine for static gesture classification, with lightweight custom geometric fallback recognizers for the 3 gestures MediaPipe does not cover (Pinch, Three Fingers, OK Sign). All processing is local. No cloud dependency. No telemetry.

This Implementation Plan sequences the V1 build into 10 checkpoints (CP-0 through CP-9), each producing a working, testable increment. The plan accounts for the current repository state: a V1.x codebase that must be migrated to the V2.0 architecture before new implementation can proceed.

### 1.2 Development Philosophy

- **Foundation before features.** The capture-and-recognition pipeline (camera → tracking → analysis → recognition) must exist and be provably correct before any action-dispatch or UI work begins.
- **ML model lifecycle established early.** ModelManager is built in CP-0, not retrofitted later. Custom fallback recognizers are built alongside MediaPipe integration in CP-3.
- **One source of truth per concern.** The PRD defines *what*; the TRD defines *how*. This plan adds *when* and *in what order*.
- **Testable increments.** Every checkpoint ends in a runnable, demonstrable state.
- **Configuration over hardcoding.** The JSON configuration system is built in CP-0.
- **Existing code is migrated, not discarded.** All V1.x code that has a V2.0 counterpart is renamed/refactored in place.

### 1.3 Core Principles

1. No checkpoint begins before its dependencies' Definition of Done is met.
2. No ML model may be loaded or instantiated outside of `ModelManager`.
3. Every component built must match its TRD §3 specification exactly.
4. Every PRD functional requirement must be traceable to at least one checkpoint.
5. Privacy and local-only processing is structural from the start — no network-capable imports in the core pipeline.
6. All extension implementations must be registered via `ExtensionRegistry`.
7. All ML inference failures must be caught and handled gracefully (never crash the pipeline).

### 1.4 Status Legend

| Status | Meaning |
|---|---|
| ✅ **Completed** | Exists in codebase and matches V2.0 requirements |
| ⚠️ **Partially Completed** | Exists but requires rename, refactor, or extension |
| 🔲 **Pending** | Does not exist; must be created |
| 🗑️ **Deprecate** | Exists but will be removed or archived |

---

## 2. Repository State Assessment

### 2.1 Existing Component Inventory (Pre-Migration)

#### Tracking Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| Hand Landmarker | `tracking/hand_detector.py` | `TrackingModule` | ⚠️ Partially Completed | Rename file to `hand_landmarker.py`, class to `HandLandmarker`, inject ModelManager |
| Hand Identity | `tracking/hand_identity.py` | `HandIdentityModule` | ✅ Completed | Keep unchanged |
| Occlusion Handler | `tracking/occlusion_handler.py` | `OcclusionHandler` | ✅ Completed | Keep unchanged |
| Hand Scale Estimator | `tracking/hand_scale.py` | `HandScaleEstimator` | ✅ Completed | Keep unchanged |
| Primary Hand Filter | `tracking/primary_hand_filter.py` | `PrimaryHandFilter` | ✅ Completed | Keep unchanged |
| Tracking errors | `tracking/errors.py` | — | 🔲 Pending | Create (extract `TrackingInitError` from `hand_detector.py`) |
| Tracking `__init__.py` | `tracking/__init__.py` | — | ✅ Completed | Keep (empty, exists) |

#### Gesture Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| GestureEngine | `gestures/gesture_engine.py` | `GestureEngine` | ⚠️ Partially Completed | Replace with `StaticGestureEngine`; old file deleted after migration |
| Static Recognizer | `gestures/static_recognizer.py` | (functions) | ⚠️ Partially Completed | Absorb 3 fallback recognizers into `StaticGestureEngine`; remove 5 MediaPipe-covered recognizers |
| Dynamic Recognizer | `gestures/dynamic_recognizer.py` | (functions) | ⚠️ Partially Completed | Rename to `dynamic_gesture_engine.py`; make V2 stub |
| Motion History | `gestures/motion_history.py` | `MotionHistoryBuffer` | ⚠️ Partially Completed | Rename to `motion_history_service.py`, class to `MotionHistoryService`, elevate to first-class service |
| Stability Filter | `gestures/stability_filter.py` | `StabilityFilter` | ✅ Completed | Merge into `GestureGate`; delete original |
| Cooldown Filter | `gestures/cooldown_filter.py` | `CooldownFilter` | ✅ Completed | Merge into `GestureGate`; delete original |
| Conflict Resolver | `gestures/conflict_resolver.py` | `ConflictResolver` | ⚠️ Partially Completed | Rename to `gesture_fuser.py`, class to `GestureFuser` |
| Activation Gate | `gestures/activation_gate.py` | `ActivationGate` | ✅ Completed | Keep unchanged |
| Gesture Utils | `gestures/gesture_utils.py` | (functions) | ✅ Completed | Keep unchanged |

#### Camera Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| Camera Module | `camera/camera_module.py` | `CameraModule` | ✅ Completed | Keep unchanged |
| Camera Errors | `camera/errors.py` | `CameraUnavailableError` | ✅ Completed | Keep unchanged |
| Camera `__init__.py` | `camera/__init__.py` | — | ✅ Completed | Keep (empty, exists) |

#### App Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| App Core | `app/core.py` | `GestureOSApp` | ⚠️ Partially Completed | Rewire with new component names, inject ModelManager |
| Capture Thread | `app/capture_thread.py` | `CaptureThread` | ⚠️ Partially Completed | Rewire pipeline with new component ordering |
| App `__init__.py` | `app/__init__.py` | — | ✅ Completed | Keep (empty, exists) |

#### Models Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| Data Models | `models/data_models.py` | Various | ⚠️ Partially Completed | Add `source` field to `GestureResult` |
| ModelManager | `models/model_manager.py` | — | 🔲 Pending | Create (ML model lifecycle) |

#### Settings Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| Settings Manager | `settings/settings_manager.py` | `SettingsManager` | ✅ Completed | Add `ml_model_path` field |
| Settings dataclass | (same file) | `Settings` | ⚠️ Partially Completed | Add `ml_model_path`, `dynamic_window_ms` range update |

#### Diagnostics Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| Diagnostics Manager | `diagnostics/diagnostics_manager.py` | `DiagnosticsManager` | ✅ Completed | Add `ml` category helpers |
| Log Format | `diagnostics/log_format.py` | `LogFormatter` | ✅ Completed | Keep unchanged |
| Camera Validator | `diagnostics/camera_validator.py` | `CameraValidator` | ✅ Completed | Keep unchanged |
| Pipeline Diagnostics | `diagnostics/pipeline_diagnostics.py` | `PipelineDiagnosticsCollector` | ✅ Completed | Keep unchanged |
| Lighting Monitor | `diagnostics/lighting_monitor.py` | — | 🔲 Pending | Create per TRD §3.12 |

#### Overlay Layer
| Component | File | Class | Status | V2.0 Action |
|---|---|---|---|---|
| Overlay Window | `overlay/overlay_window.py` | `OverlayWindow` | ✅ Completed | Add ML fallback mode indicator (CP-7) |
| Skeleton Renderer | `overlay/skeleton_renderer.py` | (function) | ✅ Completed | Keep unchanged |
| Debug Panel | `overlay/debug_panel.py` | (function) | ⚠️ Partially Completed | Add ML model status display |

#### Tests
| Component | File | Status | V2.0 Action |
|---|---|---|---|
| conftest.py | `tests/conftest.py` | ✅ Completed | Keep unchanged |
| Unit tests (17 files) | `tests/unit/` | ⚠️ Partially Completed | Rename to match new module names; add ModelManager tests |
| Integration test (1 file) | `tests/integration/` | ⚠️ Partially Completed | Update pipeline wiring references |
| Fixtures (5 JSON) | `tests/fixtures/` | ✅ Completed | Add gesture recognizer fixtures |

#### Infrastructure / Config
| Component | File | Status | V2.0 Action |
|---|---|---|---|
| requirements.txt | `requirements.txt` | ✅ Completed | Keep unchanged |
| pytest.ini | `pytest.ini` | ✅ Completed | Keep unchanged |
| pyinstaller.spec | `pyinstaller.spec` | ⚠️ Partially Completed | Finalize with MediaPipe model bundling in CP-8 |
| Default mappings | `assets/default_mappings/default.json` | ✅ Completed | Keep unchanged |

### 2.2 Missing Directories (Must Create in CP-0)

| Directory | Purpose | TRD §9 Ref |
|---|---|---|
| `gestureos/ext/` | Extension interfaces and registry | §9, §10 |
| `gestureos/context/` | Active window detection | §9, §3.12 |
| `gestureos/context/adapters/` | Platform-specific context adapters | §9, §3.12 |
| `gestureos/actions/` | Command routing and OS dispatch | §9, §3.13/3.14 |
| `gestureos/actions/executors/` | Platform-specific action executors | §9, §3.14 |
| `gestureos/profiles/` | Profile persistence | §9, §3.17 |
| `gestureos/calibration/` | Calibration business logic | §9, §12 |
| `gestureos/ui/` | Application windows | §9 |
| `gestureos/assets/models/` | ML model files | §9, AI Dev Guide §2.5 |

### 2.3 Missing Files (Must Create)

| File | Component | Source Doc |
|---|---|---|
| `models/model_manager.py` | ModelManager | TRD §3.15, RULES §13.2 |
| `ext/base.py` | ABC interfaces | TRD §10.2, AI Dev Guide §9.2 |
| `ext/registry.py` | ExtensionRegistry | TRD §3.16, RULES §14.2 |
| `context/context_engine.py` | ContextEngine | TRD §3.12, PRD §8.6 |
| `context/adapters/base.py` | ContextAdapterBase ABC | TRD §10.2, AI Dev Guide §9.2 |
| `context/adapters/windows_adapter.py` | WindowsContextAdapter | TRD §3.12 |
| `actions/command_router.py` | CommandRouter | TRD §3.13, RULES §7.5 |
| `actions/action_executor.py` | ActionExecutor | TRD §3.14, RULES §7.1 |
| `actions/executors/base.py` | ActionExecutorBase ABC | TRD §10.2 |
| `actions/executors/windows_executor.py` | WindowsExecutor | TRD §3.14 |
| `profiles/profile_manager.py` | ProfileManager | TRD §3.17 |
| `calibration/calibration_manager.py` | CalibrationManager | TRD §12 |
| `calibration/tracking_zone.py` | TrackingZone | TRD §12 |
| `diagnostics/lighting_monitor.py` | LightingMonitor | TRD §3.12 |
| `gestures/gesture_gate.py` | GestureGate | TRD §3.9 |
| `gestures/static_gesture_engine.py` | StaticGestureEngine | TRD §3.8 |
| `gestures/dynamic_gesture_engine.py` | DynamicGestureEngine (V2 stub) | TRD §3.8 |
| `gestures/gesture_fuser.py` | GestureFuser | TRD §3.10 |
| `gestures/motion_history_service.py` | MotionHistoryService | TRD §3.7 |
| `tracking/hand_landmarker.py` | HandLandmarker (renamed) | TRD §3.2 |
| `assets/models/gesture_recognizer.task` | MediaPipe model file | AI Dev Guide §2.5 |

### 2.4 File Renames Required

| Old Path | New Path | Reason |
|---|---|---|
| `tracking/hand_detector.py` | `tracking/hand_landmarker.py` | TRD §9 naming |
| `gestures/gesture_engine.py` | `gestures/static_gesture_engine.py` | TRD §9 naming (after content migrated) |
| `gestures/static_recognizer.py` | (deleted) | Absorbed into `static_gesture_engine.py` as fallback path |
| `gestures/dynamic_recognizer.py` | `gestures/dynamic_gesture_engine.py` | TRD §9 naming |
| `gestures/motion_history.py` | `gestures/motion_history_service.py` | TRD §9 naming |
| `gestures/stability_filter.py` | (deleted) | Merged into `gesture_gate.py` |
| `gestures/cooldown_filter.py` | (deleted) | Merged into `gesture_gate.py` |
| `gestures/conflict_resolver.py` | `gestures/gesture_fuser.py` | TRD §9 naming |

---

## 3. Development Strategy

### 3.1 Foundation-First Approach

```
CP-0: Repository Restructuring, ModelManager, ExtensionRegistry, ABCs, Renames
  ↓
CP-1: Camera → HandLandmarker (MediaPipe) → Overlay
  ↓
CP-2: Identity → Occlusion → Scale → PrimaryHand → MotionHistoryService
  ↓
CP-3: StaticGestureEngine (MediaPipe + 3 fallbacks) → GestureGate → GestureFuser
  ↓
CP-4: ActivationGate → CommandRouter → ContextEngine
  ↓
CP-5: ActionExecutor (Cursor + Dispatch) → WindowsExecutor
  ↓
CP-6: ProfileManager → Settings UI → Calibration Wizard → System Tray
  ↓
CP-7: LightingMonitor → Full Developer Mode → ML Fallback Indicator
  ↓
CP-8: Performance Testing → Coverage Audit → PyInstaller Packaging
  ↓
CP-9: Architecture Certification → RULES Compliance Audit → Documentation Freeze
```

### 3.2 Why This Order Is Mandatory

| Layer | Why It Must Come Before the Next |
|---|---|
| CP-0 → CP-1 | No component may load ML models without ModelManager (RULES §13.2) |
| Camera → Hand Landmarker | No landmarks without a working capture loop |
| Hand Landmarker → Analysis | Analysis components consume `HandData.landmarks` |
| Analysis → Motion History | Motion History records landmark data per hand role |
| Motion History → Static Gesture | Static Gesture Engine uses MotionHistoryService |
| Static Gesture → Gate → Fuser | Sequential filtering; each stage consumes the previous output |
| Fuser → Activation → Router → Executor | Activation is the safety gate; Router maps to actions; Executor dispatches |

### 3.3 Testing Philosophy

- Unit tests use synthetic/mock data (no live camera required)
- ML model tests must mock `ModelManager` — never instantiate real MediaPipe models in tests (AI Dev Guide §11.1)
- Integration tests from CP-3 onward (when full pipeline is wired)
- Performance testing in CP-8
- ML model fallback testing in CP-3 (simulate model load failure)

### 3.4 Cross-Reference: Requirement Sources

| Source Document | Requirements Count | Primary Checkpoint |
|---|---|---|
| PRD v2.0 §5 (Gesture Strategy) | 8 gestures, 2-stage recognition | CP-3 |
| PRD v2.0 §6 (Scale-Invariance) | 4 priority levels, no raw pixels | CP-2, CP-3 |
| PRD v2.0 §7 (Activation) | 7 FR-AM requirements | CP-4 |
| PRD v2.0 §8.1 (Hand Tracking) | 7 FR-HT requirements | CP-1, CP-2 |
| PRD v2.0 §8.2 (Gesture Gate) | 6 FR-GG requirements | CP-3 |
| PRD v2.0 §8.3 (Cursor) | 7 FR-CC requirements | CP-5 |
| PRD v2.0 §8.4 (Motion History) | 3 FR-MH requirements | CP-2 |
| PRD v2.0 §8.6 (Context) | 3 FR-CA requirements | CP-4 |
| PRD v2.0 §8.12 (ML Degradation) | 4 FR-ML requirements | CP-1, CP-3 |
| TRD v2.0 §3 (Components) | 17 component specs | CP-0 through CP-5 |
| TRD v2.0 §9 (Folder Structure) | Complete directory tree | CP-0 |
| TRD v2.0 §10 (Extensions) | 4 ABC interfaces | CP-0 |
| AI Dev Guide §2.5 (Model Files) | gesture_recognizer.task | CP-0 |
| RULES §2 (Architecture) | 10 rules | CP-0, CP-9 |
| RULES §13 (ML Governance) | 9 rules | CP-0, CP-9 |
| RULES §14 (Extensions) | 5 rules | CP-0, CP-9 |

---

## 4. Checkpoint 0 — Foundation & Repository Migration

### Status: ✅ Complete -- CP-0 migration executed and verified 2026-07-05

### Objective

Migrate the repository from V1.x layout to complete V2.0 architecture compliance. Create all missing directories, files, ABC interfaces, and infrastructure components required by the Architecture Freeze Specification. Rename all V1.x components to their V2.0 names. Establish ModelManager and ExtensionRegistry as first-class infrastructure. The repository must match TRD §9 folder structure by the end of this checkpoint.

### Prerequisites / Dependencies

- None (this is the root checkpoint)

### Architecture Changes

| Change | Justification |
|---|---|
| Add `ext/` directory | TRD §9, RULES §14 — extension system must exist before any component is built |
| Add `context/` and `context/adapters/` | TRD §9 — required for CP-4 ContextEngine |
| Add `actions/` and `actions/executors/` | TRD §9 — required for CP-4/CP-5 routing and dispatch |
| Add `profiles/`, `calibration/`, `ui/` | TRD §9 — required for CP-6 user-facing features |
| Add `assets/models/` | AI Dev Guide §2.5 — ML model storage location |
| Add `tracking/errors.py` | TRD §3.2 — extract TrackingInitError from hand_detector.py |

### Repository / Folder & File Changes

#### Create Directories (7 new)
```
gestureos/ext/
gestureos/context/
gestureos/context/adapters/
gestureos/actions/
gestureos/actions/executors/
gestureos/profiles/
gestureos/calibration/
gestureos/ui/
gestureos/assets/models/
```

#### Rename Files (5 renames)
| From | To |
|---|---|
| `tracking/hand_detector.py` | `tracking/hand_landmarker.py` |
| `gestures/motion_history.py` | `gestures/motion_history_service.py` |
| `gestures/dynamic_recognizer.py` | `gestures/dynamic_gesture_engine.py` |
| `gestures/conflict_resolver.py` | `gestures/gesture_fuser.py` |
| `gestures/gesture_engine.py` | `gestures/static_gesture_engine.py` |

#### Delete Files (3 deletions — content absorbed or replaced)
| File | Reason |
|---|---|
| `gestures/stability_filter.py` | Merged into `gesture_gate.py` (creates new file) |
| `gestures/cooldown_filter.py` | Merged into `gesture_gate.py` (creates new file) |
| `gestures/static_recognizer.py` | Custom fallback logic absorbed into `static_gesture_engine.py`; MediaPipe-covered gestures removed |

#### Delete Directories (1 removal)
| Directory | Reason |
|---|---|
| `handtrack/` (repo root) | Legacy V1.x code, deprecated per AI Dev Guide §17 |

#### Update Existing Files (5 modifications)
| File | Change |
|---|---|
| `models/data_models.py` | Add `source: str = 'unknown'` field to `GestureResult` per TRD §7.2 |
| `settings/settings_manager.py` | Add `ml_model_path: str = 'models/gesture_recognizer.task'` to `Settings` dataclass; add validation for field range per TRD §8.2 |
| `main.py` | Update `__version__` to `"2.0.0-dev+cp0"`, `__checkpoint__` to `"0"` |
| `app/core.py` | Inject ModelManager reference; update import paths for renamed modules; wire new pipeline component ordering (CP-1 will finalize) |
| `app/capture_thread.py` | Update import paths for renamed modules; prepare pipeline for CP-1 wiring |

#### Create Files (9 new files)
| File | Purpose |
|---|---|
| `models/model_manager.py` | ML model lifecycle per TRD §3.15 |
| `ext/base.py` | ABC interfaces per TRD §10.2 |
| `ext/registry.py` | ExtensionRegistry per TRD §3.16 |
| `gestures/gesture_gate.py` | Merged StabilityGate + CooldownGate per TRD §3.9 |
| `gestures/motion_history_service.py` | Elevated first-class service per TRD §3.7 (new file; old `motion_history.py` renamed to this) |
| `tracking/errors.py` | Extract `TrackingInitError` from `hand_detector.py` per TRD §3.2 |
| `diagnostics/lighting_monitor.py` | Lighting quality detection per TRD §3.12 (scaffold; full implementation in CP-7) |

#### Download Required Artifact
| Artifact | Location | Source |
|---|---|---|
| `gesture_recognizer.task` | `assets/models/gesture_recognizer.task` | Google MediaPipe official model repository (AI Dev Guide §2.5) |

### Implementation Tasks

#### Task 0.1 — Create missing directories
```
gestureos/ext/
gestureos/context/
gestureos/context/adapters/
gestureos/actions/
gestureos/actions/executors/
gestureos/profiles/
gestureos/calibration/
gestureos/ui/
gestureos/assets/models/
```
Add `__init__.py` files (empty) to each new Python package directory.

#### Task 0.2 — Create ext/base.py (Extension ABC Interfaces)
Per TRD §10.2 and AI Dev Guide §9.2, define these ABCs:
- `GestureRecognizerBase` — abstract method `recognize(hand: HandData, motion: MotionHistoryService) -> list[GestureResult]`
- `ActionExecutorBase` — abstract method `execute(action: Action) -> ActionResult`
- `ContextAdapterBase` — abstract method `get_active_process_name() -> str`
- `PipelineFilterBase` — abstract methods `before_recognition(hands) -> list[HandData]` and `after_recognition(results) -> list[GestureResult]`

RULES §14.1: All extension points are code-level interfaces via Python ABCs. No hot-loading in V1.

#### Task 0.3 — Create ext/registry.py (ExtensionRegistry)
Per TRD §3.16 and RULES §14.2:
- Singleton pattern via `get_instance()` class method
- `register(name: str, implementation: Any) -> None` — raises `ValueError` on duplicate
- `get(interface_name: str) -> Any` — raises `KeyError` if not found
- Thread-safe for read operations

#### Task 0.4 — Create models/model_manager.py (ModelManager)
Per TRD §3.15, PRD §8.12 (FR-ML-01..04), and RULES §13.2:
- Sole owner of all ML model handles
- `__init__(self, diagnostics: DiagnosticsManager, model_path: str = "models/gesture_recognizer.task")`
- `is_gesture_model_available() -> bool`
- `recognize_gesture(landmarks: list) -> GestureResult | None`
- `record_inference_failure() -> None`
- `reload_gesture_model() -> bool`
- Load MediaPipe Gesture Recognizer at startup; handle load failure gracefully (set `gesture_model_available=False`)
- After 3 consecutive inference failures, trigger auto-reload; if reload fails, engage fallback-only mode
- Log all ML events through DiagnosticsManager using `ml` category (RULES §9.4)

#### Task 0.5 — Update models/data_models.py
Per TRD §7.2:
- Add `source: str = 'unknown'` field to `GestureResult` dataclass
- Valid values: `'mediapipe'`, `'custom_fallback'`, `'dynamic_engine'` (V2)
- No other dataclass changes required (HandData already has all fields per TRD §7.1)

#### Task 0.6 — Update settings/settings_manager.py
Per TRD §8.1 and PRD §12.2:
- Add `ml_model_path: str = 'models/gesture_recognizer.task'` to `Settings` dataclass
- Add `dynamic_window_ms: int = 750` field (already exists but add to validators)
- Add validation: `ml_model_path` is non-empty string; fallback to `'models/gesture_recognizer.task'` per TRD §8.2
- Update `_INT_RANGES` for `motion_history_frames` to (10, 60) per TRD §8.2 (currently (10, 40))

#### Task 0.7 — Rename hand_detector.py → hand_landmarker.py
Per TRD §3.2 and §9:
- Rename file to `tracking/hand_landmarker.py`
- Rename class `TrackingModule` → `HandLandmarker`
- Keep all existing functionality; add `model_manager: ModelManager` parameter to `__init__`
- Move `TrackingInitError` to `tracking/errors.py`
- Update all imports across the codebase

#### Task 0.8 — Rename and elevate motion_history.py → motion_history_service.py
Per TRD §3.7:
- Rename file to `gestures/motion_history_service.py`
- Rename class `MotionHistoryBuffer` → `MotionHistoryService`
- Add new API methods:
  - `get_window(role: str, duration_ms: int) -> list[tuple]` — time-windowed query
  - `get_hold_duration(role: str) -> float` — for stability check
- Keep existing `update()`, `get()`, `clear()` methods
- Keep PRD FR-MH-03 contract: store raw (unnormalized) data; normalization at read time

#### Task 0.9 — Rename dynamic_recognizer.py → dynamic_gesture_engine.py
Per TRD §3.8:
- Rename file to `gestures/dynamic_gesture_engine.py`
- Wrap all 6 dynamic recognizer functions in a `DynamicGestureEngine` class
- The class raises `NotImplementedError` on all methods (V2 stub per Implementation Plan v2.0.0 §7)
- Keep existing recognizer logic available for V2 development

#### Task 0.10 — Rename conflict_resolver.py → gesture_fuser.py
Per TRD §3.10:
- Rename file to `gestures/gesture_fuser.py`
- Rename class `ConflictResolver` → `GestureFuser`
- V1 behavior: pass-through (TRD §3.10: "Strict pass-through... returns its input unchanged")
- Keep existing `resolve()` logic (it's already pass-through with confidence-based selection)
- Update docstring to cite TRD §3.10

#### Task 0.11 — Create gesture_gate.py (merged Stability + Cooldown)
Per TRD §3.9:
- Create `gestures/gesture_gate.py` with:
  - `GestureGate` facade class
  - `StabilityGate` internal class (from `stability_filter.py`)
  - `CooldownGate` internal class (from `cooldown_filter.py`)
- Import existing logic from `stability_filter.py` and `cooldown_filter.py` (before they are deleted)
- `GestureGate.check(role, candidates, now) -> list[GestureResult]` applies stability then cooldown
- Design note from TRD: "Although combined, the two stages remain independently testable classes behind the GestureGate facade."

#### Task 0.12 — Deprecate and remove old gesture files
After creating `gesture_gate.py` and confirming all logic is preserved:
- Delete `gestures/stability_filter.py`
- Delete `gestures/cooldown_filter.py`

#### Task 0.13 — Rename gesture_engine.py → static_gesture_engine.py (scaffold)
Per TRD §3.8:
- Rename file to `gestures/static_gesture_engine.py`
- Rename class `GestureEngine` → `StaticGestureEngine`
- **Scaffold only in CP-0:** Replace the existing all-candidates logic with the two-stage architecture:
  - Stage 1: MediaPipe query via `ModelManager.recognize_gesture()`
  - Stage 2: Custom fallback recognizers (3 gestures: Pinch, Three Fingers, OK Sign)
- The custom fallback recognizer functions (`detect_pinch`, `detect_three_fingers`, `detect_ok_sign`) are ported from `static_recognizer.py` into the new file
- The 5 MediaPipe-covered gesture recognizers (`detect_open_palm`, `detect_fist`, `detect_thumbs_up`, `detect_thumbs_down`, `detect_peace_sign`) are **removed** — they must only be recognized via the MediaPipe model (AI Dev Guide §7.5, RULES §5.1)

#### Task 0.14 — Deprecate static_recognizer.py
After porting the 3 custom fallback recognizers to `static_gesture_engine.py`:
- Delete `gestures/static_recognizer.py`
- The 5 MediaPipe-covered recognizer functions in that file are not recreated

#### Task 0.15 — Create tracking/errors.py
Per TRD §3.2:
- Extract `TrackingInitError` class from `hand_landmarker.py` (formerly `hand_detector.py`)
- Place in `tracking/errors.py`
- Update import in `hand_landmarker.py` to import from `tracking.errors`

#### Task 0.16 — Create diagnostics/lighting_monitor.py (scaffold)
Per TRD §3.12:
- Create `LightingMonitor` class with:
  - `check(frame_brightness) -> LightingQuality` scaffold
  - Full implementation deferred to CP-7
- Add `LightingQuality` to `models/data_models.py` if not already present (it is — TRD §7.4)

#### Task 0.17 — Update app/core.py wiring
Per TRD §2.2:
- Inject `ModelManager` instance
- Replace `TrackingModule` with `HandLandmarker`
- Replace `GestureEngine` with `StaticGestureEngine`
- Replace `ConflictResolver` with `GestureFuser`
- Wire `GestureGate` (removing separate `StabilityFilter` and `CooldownFilter`)
- Register all built-in implementations with `ExtensionRegistry` at startup (AI Dev Guide §9.3)

#### Task 0.18 — Update app/capture_thread.py pipeline
Per TRD §2.2 and §5.1:
- Update import paths for all renamed modules
- Replace separate stability/cooldown pipeline stages with `GestureGate` single call
- Update pipeline ordering to match TRD §5.1:
  `Camera → HandLandmarker → HandIdentityModule → OcclusionHandler → HandScaleEstimator → PrimaryHandFilter → MotionHistoryService → StaticGestureEngine → GestureGate → GestureFuser → ActivationGate → CommandRouter → ActionExecutor`
- Note: CommandRouter and ActionExecutor are wired in CP-4/CP-5; pipeline runs up to ActivationGate in CP-3

#### Task 0.19 — Remove legacy handtrack/ directory
Per AI Development Guide §18.4 (Deprecation Rules):
- Archive or delete `handtrack/` at repository root
- It contains legacy V1.x code (`VolumeHandControl.py`, `HandTrackingModule.py`) that has no place in the V2.0 architecture

#### Task 0.20 — Update main.py metadata
- `__version__` → `"2.0.0-dev+cp0"`
- `__checkpoint__` → `"0"`

#### Task 0.21 — Download MediaPipe Gesture Recognizer model
Per AI Dev Guide §2.5:
- Download `gesture_recognizer.task` from Google's official MediaPipe model repository
- Place in `gestureos/assets/models/gesture_recognizer.task`
- This file is required for ModelManager to load at startup; if absent, `is_gesture_model_available()` returns `False`

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| Repository skeleton matches TRD §9 exactly | All 15 directories exist | |
| All extension ABCs defined in `ext/base.py` | 4 ABC classes | |
| `ExtensionRegistry` implements singleton pattern | `get_instance()` works | |
| `ModelManager` loads/reloads/unloads ML models | `is_gesture_model_available()` works | |
| `GestureResult.source` field exists | `source: str = 'unknown'` | |
| `Settings.ml_model_path` field exists | Default `'models/gesture_recognizer.task'` | |
| All 5 file renames complete | Old paths do not exist; new paths exist | |
| No circular imports across any module | `python -c "import gestureos"` succeeds | |
| Old static_recognizer.py deleted | File removed | |
| Old stability_filter.py deleted | File removed | |
| Old cooldown_filter.py deleted | File removed | |
| `gesture_gate.py` contains merged stability + cooldown | `GestureGate.check()` works | |
| `handtrack/` removed from repo root | Directory no longer exists | |
| `TrackingInitError` in `tracking/errors.py` | Importable from `tracking.errors` | |
| `gesture_recognizer.task` in `assets/models/` | File exists | |
| All tests from old structure still pass | `pytest tests/` passes | |

### Definition of Done

1. All 15 directories from TRD §9 exist
2. All 21 new files from Tasks 0.1–0.21 exist
3. All 5 file renames completed
4. All 3 deleted files removed
5. `gesture_recognizer.task` present at `assets/models/gesture_recognizer.task`
6. `ModelManager` unit tests pass (including fallback scenarios)
7. `ExtensionRegistry` unit tests pass (register/get/duplicate/not-found)
8. `pytest tests/` passes with zero failures
9. No component outside the scaffolded folders has been created
10. Repository structure reproduces TRD §9 exactly

### Deliverables

```
gestureos/
├── main.py                          (updated version)
├── requirements.txt                 (unchanged)
├── pyinstaller.spec                 (stub, unchanged)
├── pytest.ini                       (unchanged)
├── app/
│   ├── __init__.py
│   ├── core.py                      (updated wiring)
│   └── capture_thread.py            (updated pipeline)
├── camera/
│   ├── __init__.py
│   ├── camera_module.py
│   └── errors.py
├── tracking/
│   ├── __init__.py
│   ├── hand_landmarker.py           (RENAMED from hand_detector.py)
│   ├── hand_identity.py
│   ├── occlusion_handler.py
│   ├── hand_scale.py
│   ├── primary_hand_filter.py
│   └── errors.py                    (NEW — extracted TrackingInitError)
├── gestures/
│   ├── static_gesture_engine.py     (RENAMED from gesture_engine.py, rewritten)
│   ├── dynamic_gesture_engine.py    (RENAMED from dynamic_recognizer.py)
│   ├── motion_history_service.py    (RENAMED from motion_history.py, elevated)
│   ├── gesture_gate.py              (NEW — merged stability + cooldown)
│   ├── gesture_fuser.py             (RENAMED from conflict_resolver.py)
│   ├── activation_gate.py
│   └── gesture_utils.py
├── context/                         (NEW directory)
│   ├── __init__.py
│   ├── context_engine.py            (scaffold; full in CP-4)
│   └── adapters/
│       ├── __init__.py
│       ├── base.py                  (scaffold; full in CP-4)
│       └── windows_adapter.py       (scaffold; full in CP-4)
├── actions/                         (NEW directory)
│   ├── __init__.py
│   ├── command_router.py            (scaffold; full in CP-4)
│   ├── action_executor.py           (scaffold; full in CP-5)
│   └── executors/
│       ├── __init__.py
│       ├── base.py                  (scaffold; full in CP-5)
│       └── windows_executor.py      (scaffold; full in CP-5)
├── models/
│   ├── data_models.py               (updated with source field)
│   └── model_manager.py             (NEW)
├── ext/                             (NEW directory)
│   ├── base.py                      (NEW — ABC interfaces)
│   └── registry.py                  (NEW — ExtensionRegistry)
├── profiles/                        (NEW directory)
│   ├── __init__.py
│   └── profile_manager.py           (scaffold; full in CP-6)
├── calibration/                     (NEW directory)
│   ├── __init__.py
│   ├── calibration_manager.py       (scaffold; full in CP-6)
│   └── tracking_zone.py             (scaffold; full in CP-6)
├── overlay/
│   ├── __init__.py
│   ├── overlay_window.py
│   ├── skeleton_renderer.py
│   └── debug_panel.py
├── settings/
│   └── settings_manager.py          (updated with ml_model_path)
├── diagnostics/
│   ├── diagnostics_manager.py
│   ├── log_format.py
│   ├── camera_validator.py
│   ├── pipeline_diagnostics.py
│   └── lighting_monitor.py          (NEW scaffold)
├── ui/                              (NEW directory)
│   ├── __init__.py
│   ├── main_window.py               (scaffold; full in CP-6)
│   ├── settings_panel.py            (scaffold; full in CP-6)
│   ├── mapping_editor.py            (scaffold; full in CP-6)
│   ├── profile_panel.py             (scaffold; full in CP-6)
│   ├── onboarding_wizard.py         (scaffold; full in CP-6)
│   ├── calibration_wizard.py        (scaffold; full in CP-6)
│   └── tray_icon.py                 (scaffold; full in CP-6)
├── tests/
│   ├── conftest.py
│   ├── fixtures/                    (unchanged, add new fixtures)
│   ├── unit/
│   │   └── test_model_manager.py    (NEW)
│   │   └── test_extension_registry.py (NEW)
│   │   └── ... (existing tests, updated imports)
│   └── integration/
│       └── test_pipeline_end_to_end.py (updated imports)
├── assets/
│   ├── default_mappings/
│   │   └── default.json
│   └── models/                      (NEW directory)
│       └── gesture_recognizer.task   (NEW — MediaPipe model file)
└── requirements.txt                 (unchanged)
```

---

## 5. Checkpoint 1 — Core Platform & ML Foundation

### Status: ⚠️ Partially Completed (file renames done in CP-0, integration pending)

### Objective

Stand up the capture-and-detection loop with the ML model lifecycle and extension system foundations fully integrated. Wire CameraModule → HandLandmarker → ModelManager → ExtensionRegistry → minimal Overlay. FPS counter and ML model status visible in overlay.

### Prerequisites / Dependencies

CP-0 must be Done.

### Architecture Changes

- `CameraModule` remains unchanged (already matches TRD §3.1)
- `HandLandmarker` now takes `ModelManager` in constructor (TRD §3.2)
- `ModelManager` loads both MediaPipe models (Hand Landmarker + Gesture Recognizer) at startup
- `ExtensionRegistry` populated with all built-in implementations at startup
- Minimal overlay shows skeleton + FPS + ML model status

### Repository / Folder & File Changes

#### Modify Existing Files
| File | Change |
|---|---|
| `camera/camera_module.py` | Verify TRD §3.1 compliance; add `reported_resolution` property if missing |
| `tracking/hand_landmarker.py` | Wire `ModelManager` for MediaPipe model access; update `initialize()` to use `model_manager.get_hand_landmarker()` |
| `app/core.py` | Finalize `GestureOSApp` wiring with ModelManager, ExtensionRegistry; register built-in implementations |
| `app/capture_thread.py` | Verify pipeline runs Camera → HandLandmarker → Overlay; FPS counter working |
| `overlay/overlay_window.py` | Add ML model status line (LOADED / FALLBACK_ONLY / N/A) |
| `overlay/skeleton_renderer.py` | Verify unchanged |
| `ext/registry.py` | Populate with built-in implementations at app startup |

#### Create Files
| File | Purpose |
|---|---|
| (none — all CP-1 deliverables created in CP-0) | |

### Implementation Tasks

#### Task 1.1 — Verify CameraModule TRD §3.1 compliance
- Confirm `open()`, `read_frame()`, `reconnect()`, `release()` methods work
- Confirm frame preprocessing (flip, resize) per TRD §3.1
- Add `reported_resolution` property if not present
- Verify no imports from other pipeline modules (RULES §2.5)

#### Task 1.2 — Wire HandLandmarker to ModelManager
- Update `HandLandmarker.__init__` to accept `model_manager: ModelManager`
- Replace direct `mp.solutions.hands.Hands(...)` instantiation with `model_manager.get_hand_landmarker()`
- Keep existing detection logic, chirality extraction, and error handling
- Ensure `TrackingInitError` path uses the error class from `tracking/errors.py`

#### Task 1.3 — Verify ModelManager completeness
- Confirm `get_hand_landmarker()` method exists (returns MediaPipe Hand Landmarker handle)
- Confirm `recognize_gesture(landmarks)` method exists (returns `GestureResult | None`)
- Confirm `is_gesture_model_available()`, `record_inference_failure()`, `reload_gesture_model()` exist
- Test with available model: `is_gesture_model_available() == True`
- Test with missing model: `is_gesture_model_available() == False`, fallback mode logged
- Test auto-reload after 3 consecutive inference failures

#### Task 1.4 — Populate ExtensionRegistry at startup
In `GestureOSApp.__init__` or `main.py`, register built-in implementations:
```python
registry = ExtensionRegistry.get_instance()
registry.register('static_gesture_engine.mediapipe', MediaPipeGestureEngine(model_manager))
registry.register('static_gesture_engine.custom_fallback', CustomFallbackEngine())
registry.register('action_executor.windows', WindowsExecutor())
registry.register('context_adapter.windows', WindowsContextAdapter())
```

#### Task 1.5 — Update overlay for ML model status
- Add `ML Model: LOADED` / `ML Model: FALLBACK_ONLY` / `ML Model: N/A` line to overlay badge
- Status read from `ModelManager.is_gesture_model_available()`
- Color coding: green for LOADED, yellow for FALLBACK_ONLY, red for N/A

#### Task 1.6 — Update CaptureThread pipeline
- Wire: `CameraModule.read_frame()` → `HandLandmarker.detect()` → emit `frame_ready` signal
- FPS measurement via `CameraValidator`
- Confirm no gesture recognition runs at this stage (CP-3 scope)

#### Task 1.7 — Update unit tests for renamed modules
- Rename test files to match new module names:
  - `test_hand_detector.py` → `test_hand_landmarker.py`
  - `test_gesture_engine.py` → `test_static_gesture_engine.py`
  - `test_conflict_resolver.py` → `test_gesture_fuser.py`
  - `test_motion_history.py` → `test_motion_history_service.py`
- Add `test_model_manager.py` with fallback scenario tests
- Add `test_extension_registry.py`

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| MediaPipe detects hand landmarks on live webcam | ≥ 25 FPS | |
| ModelManager loads both MediaPipe models | `is_gesture_model_available() == True` | |
| ModelManager handles missing model file | `is_gesture_model_available() == False`, fallback logged | |
| ExtensionRegistry populated with built-in implementations | 4 entries registered | |
| FPS counter visible in overlay | Shows measured FPS | |
| ML model status visible in overlay | LOADED / FALLBACK_ONLY / N/A | |
| No gesture recognition runs | Pipeline stops after HandLandmarker | |
| All tests pass | `pytest tests/` | |

### Definition of Done

1. All Acceptance Criteria pass
2. ModelManager unit tests pass (including fallback scenarios)
3. ExtensionRegistry unit tests pass
4. PyInstaller smoke-build succeeds with MediaPipe models bundled (TRD §12)
5. FPS counter and ML status visible in overlay
6. No gesture recognition logic has been introduced

### Deliverables

Same file tree as CP-0, with all modules now fully wired and integrated.

---

## 6. Checkpoint 2 — Hand Analysis Layer

### Status: ⚠️ Partially Completed (4 of 6 components exist; 2 partially)

### Objective

Build every component that transforms raw landmarks into analyzed, normalized data for the recognition layer. HandIdentityModule, OcclusionHandler, HandScaleEstimator, PrimaryHandFilter, MotionHistoryService, and shared geometry primitives.

### Prerequisites / Dependencies

CP-1 must be Done.

### Architecture Changes

- HandIdentityModule: unchanged from V1.x (already matches TRD §3.3)
- OcclusionHandler: unchanged (already matches TRD §3.4)
- HandScaleEstimator: unchanged (already matches TRD §3.5)
- PrimaryHandFilter: unchanged (already matches TRD §3.6)
- MotionHistoryService: elevated from `MotionHistoryBuffer` with new API methods per TRD §3.7
- gesture_utils.py: unchanged (already matches TRD §4.3)

### Repository / Folder & File Changes

#### Modify Existing Files
| File | Change |
|---|---|
| `tracking/hand_identity.py` | Verify TRD §3.3 compliance; no changes expected |
| `tracking/occlusion_handler.py` | Verify TRD §3.4 compliance; no changes expected |
| `tracking/hand_scale.py` | Verify TRD §3.5 compliance; no changes expected |
| `tracking/primary_hand_filter.py` | Verify TRD §3.6 compliance; no changes expected |
| `gestures/motion_history_service.py` | Add `get_window()`, `get_hold_duration()` per TRD §3.7 API |
| `gestures/gesture_utils.py` | Verify TRD §4.3 compliance; no changes expected |
| `app/capture_thread.py` | Wire CP-2 pipeline stages |
| `settings/settings_manager.py` | Verify `motion_history_frames`, `occlusion_retention_ms`, `dominant_hand_mode` fields exist |

#### Create Files
| File | Purpose |
|---|---|
| `tests/fixtures/sample_landmarks.json` | Already exists; add more poses if needed |

### Implementation Tasks

#### Task 2.1 — Verify HandIdentityModule (✅ Already Completed)
- Confirm `assign_roles()` per TRD §3.3
- Confirm re-identification window (2s), match threshold (0.15), chirality fallback
- Confirm >2 hands truncated to 2 highest-confidence
- Confirm `remembered_roles` property for debug overlay

#### Task 2.2 — Verify OcclusionHandler (✅ Already Completed)
- Confirm `bridge_gaps()` per TRD §3.4
- Confirm 300ms retention window (configurable)
- Confirm `is_retained` flag set on bridged hands
- Confirm hard timeout: window expired → release to re-identification

#### Task 2.3 — Verify HandScaleEstimator (✅ Already Completed)
- Confirm `estimate()` per TRD §3.5
- Confirm palm width (landmark 5 ↔ 17), palm height (0 ↔ 9)
- Confirm 5-frame moving average
- Confirm FR-SC-04: `hand.scale is None` → skip evaluation

#### Task 2.4 — Verify PrimaryHandFilter (✅ Already Completed)
- Confirm `filter()` per TRD §3.6
- Confirm modes: `off`, `left`, `right`
- Confirm `gesture_eligible` flag set per chirality
- Confirm no promotion of secondary hand when primary absent

#### Task 2.5 — Elevate MotionHistoryService (⚠️ Partially Completed)
Per TRD §3.7, add these methods to `MotionHistoryService`:
- `update(role, landmarks, wrist_pos, now)` — already exists
- `get_window(role, duration_ms) -> list[tuple]` — NEW: time-windowed query
- `get_hold_duration(role) -> float` — NEW: for stability check
- `clear(role)` — already exists
- Verify PRD FR-MH-03: store raw (unnormalized) data; normalization at read time

#### Task 2.6 — Verify gesture_utils.py (✅ Already Completed)
- Confirm `finger_states()`, `euclidean_distance()`, `finger_angle()`, `is_finger_extended()`
- Confirm scale-invariant primitives: `normalized_distance()`, `pinch_distance_ratio()`
- Confirm `fist_compactness_ratio()`, `thumb_index_alignment_ratio()`, `remaining_fingers_curled_score()`
- No camera, MediaPipe, or OS-automation imports (RULES §4.1)

#### Task 2.7 — Wire CaptureThread for CP-2
Add to the per-frame pipeline (after HandLandmarker):
```
HandIdentityModule.assign_roles() → OcclusionHandler.bridge_gaps() → HandScaleEstimator.estimate() → PrimaryHandFilter.filter() → MotionHistoryService.update()
```
Store processed hands for overlay.

#### Task 2.8 — Update Settings validation
Confirm these fields exist with correct ranges per TRD §8.2:
- `motion_history_frames`: 10–60 (default 30)
- `occlusion_retention_ms`: 100–1000 (default 300)
- `dominant_hand_mode`: `off` | `left` | `right` (default `off`)

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| Hand scale computed correctly against fixtures | Correct palm_width/palm_height | |
| Role assignment preserved across hand-crossing | Roles stable through crossing test | |
| 200ms occlusion bridged; 400ms occlusion released | Window respected | |
| Dominant Hand Mode correctly filters | Non-matching hands ineligible | |
| MotionHistoryService stores raw landmarks | Normalization at read time | |
| MotionHistoryService.get_window(duration_ms) returns correct window | Time-filtered results | |
| Coverage ≥ 80% for `tracking/` | pytest --cov=tracking | |
| No raw-pixel thresholds in this checkpoint's code | grep for absolute pixel values | |
| All CP-1 tests still pass | pytest tests/ | |

### Definition of Done

1. All Acceptance Criteria pass
2. `HandData` objects flowing out have `scale`, `role`, `gesture_eligible`, `is_retained`, `status` correctly populated
3. No raw-pixel thresholds in checkpoint's code
4. Coverage ≥ 80% for `tracking/`

### Deliverables

All tracking analysis components verified and wired. MotionHistoryService elevated.

---

## 7. Checkpoint 3 — Static Gesture Engine

### Status: 🔲 Pending (architecture must be rewritten)

### Objective

Implement the Static Gesture Engine with two-stage recognition (MediaPipe Gesture Recognizer → custom geometric fallback), GestureGate (merged stability + cooldown), and GestureFuser (V1 pass-through).

### Prerequisites / Dependencies

CP-2 must be Done.

### Architecture Changes

- StaticGestureEngine replaces old GestureEngine per TRD §3.8:
  - Stage 1: Query MediaPipe Gesture Recognizer via `ModelManager.recognize_gesture()`
  - Stage 2: Run 3 custom fallback recognizers (Pinch, Three Fingers, OK Sign)
  - The 5 MediaPipe-covered gestures (Open Palm, Fist, Thumbs Up, Thumbs Down, Peace Sign) are recognized ONLY by the MediaPipe model (AI Dev Guide §7.5)
- GestureGate merges StabilityFilter + CooldownFilter per TRD §3.9
- GestureFuser (V1 pass-through) per TRD §3.10
- DynamicGestureEngine is a V2 stub (raises NotImplementedError)

### Repository / Folder & File Changes

#### Modify Existing Files
| File | Change |
|---|---|
| `gestures/static_gesture_engine.py` | Finalize two-stage recognition; remove 5 MediaPipe-covered gesture recognizers; port 3 custom fallback recognizers from old `static_recognizer.py` |
| `gestures/gesture_gate.py` | Finalize `GestureGate.check()` with internal `StabilityGate` and `CooldownGate` |
| `gestures/gesture_fuser.py` | Verify V1 pass-through behavior; update docstrings |
| `gestures/dynamic_gesture_engine.py` | Verify V2 stub raises `NotImplementedError` |
| `app/capture_thread.py` | Wire CP-3 pipeline stages after CP-2 stages |
| `models/data_models.py` | Verify `GestureResult.source` field is populated correctly |
| `ext/registry.py` | Register `static_gesture_engine.mediapipe` and `static_gesture_engine.custom_fallback` |

### Implementation Tasks

#### Task 3.1 — Finalize static_gesture_engine.py
Per TRD §3.8 and PRD §5:

- `__init__(self, model_manager: ModelManager, settings: Settings)` — receives ModelManager and Settings
- `classify(hands: list[HandData]) -> list[GestureResult]`:
  - For each gesture-eligible hand:
    - **Stage 1:** Call `model_manager.recognize_gesture(hand.landmarks)`
      - Map MediaPipe class names to internal gesture names per TRD §3.8.1:
        - `OPEN_PALM` → `open_palm`
        - `CLOSED_FIST` → `fist`
        - `THUMB_UP` → `thumbs_up`
        - `THUMB_DOWN` → `thumbs_down`
        - `VICTORY` → `peace_sign`
      - Return `GestureResult` with `source='mediapipe'`
      - Skip if `is_gesture_model_available() == False`
    - **Stage 2:** Run custom fallback recognizers for 3 gestures:
      - `detect_pinch()` — uses `euclidean_distance(thumb_tip, index_tip) / palm_width < 0.35` plus multi-signal (TRD §3.8.2)
      - `detect_three_fingers()` — Index + Middle + Ring EXTENDED, Pinky + Thumb CURLED
      - `detect_ok_sign()` — pinch distance AND Middle + Ring + Pinky EXTENDED
      - All return `GestureResult` with `source='custom_fallback'`
      - All return `None` when `hand.scale is None` (FR-SC-04)
  - Apply confidence threshold from `settings.gesture_confidence_threshold`
  - Return all qualifying candidates

#### Task 3.2 — Remove 5 MediaPipe-covered gesture recognizers
Per AI Dev Guide §7.5 and RULES §5.1:
- Do NOT implement custom fallback for Open Palm, Closed Fist, Thumbs Up, Thumbs Down, Peace Sign
- These gestures are recognized exclusively via the MediaPipe model
- If MediaPipe model is unavailable, these gestures are unavailable (FR-ML-04: user-visible warning via overlay)

#### Task 3.3 — Finalize gesture_gate.py
Per TRD §3.9:
- `GestureGate.__init__(self, settings: Settings)` — reads stability window and cooldown durations
- `GestureGate.check(self, role: str, candidates: list[GestureResult], now: float) -> list[GestureResult]`:
  - **Stage 1 — StabilityGate internal:** Verify gesture held continuously for `gesture_stability_window_ms` per hand role
    - Dynamic gestures (V2) exempt per FR-GG-04
    - Reset on gesture change mid-hold (no partial credit per FR-GG-02)
  - **Stage 2 — CooldownGate internal:** Per-(role, gesture_name) cooldown timer
    - Static gesture cooldown: `gesture_cooldown_static_ms` (default 500ms)
    - Dynamic gesture cooldown: `gesture_cooldown_dynamic_ms` (default 1000ms)
    - Independent per (hand_role, gesture_name) pair per FR-GG-06
- Both internal classes have their own unit tests (TRD: "remain independently testable classes")

#### Task 3.4 — Finalize gesture_fuser.py
Per TRD §3.10:
- V1 behavior: pass-through (single-engine input)
- Group candidates by hand role, take highest-confidence per role
- Never raises; defensive try/except returns input unchanged
- Input treated as immutable (RULES §4.7)

#### Task 3.5 — Verify dynamic_gesture_engine.py (V2 stub)
- All methods raise `NotImplementedError`
- Class is not instantiated or wired in V1 pipeline
- File exists only as an architectural placeholder

#### Task 3.6 — Wire CaptureThread for CP-3
Add to the per-frame pipeline (after CP-2 stages):
```
MotionHistoryService.update() → StaticGestureEngine.classify() → GestureGate.check() → GestureFuser.fuse()
```
The fused results are emitted via `gesture_detected` signal but NOT dispatched (ActivationGate blocks in CP-4).

#### Task 3.7 — Update ExtensionRegistry registrations
Register:
- `'static_gesture_engine.mediapipe'` → `MediaPipeGestureEngine(model_manager)`
- `'static_gesture_engine.custom_fallback'` → `CustomFallbackEngine()`

#### Task 3.8 — Update DiagnosticsManager with ml category events
Add helpers for:
- `log_ml_event(event, details, level)` — model loaded/load failed/inference timeout/auto-reload/fallback mode
- Events per RULES §9.4 and AI Dev Guide §10.1

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| MediaPipe covers 5 of 8 static gestures | ≥ 95% accuracy | |
| Custom fallback covers Pinch, Three Fingers, OK Sign | ≥ 95% accuracy | |
| 3 custom fallback recognizers scale-invariant | Test at 0.5x, 1.0x, 2.0x, 3.0x scale | |
| Gesture Gate stability: 1 frame → no trigger; 200ms → trigger | Hold window respected | |
| Gesture Gate cooldown: repeated single gesture fires once | Cooldown respected | |
| Gesture Fuser returns single winner per hand | Pass-through verified | |
| ModelManager fallback: without model, 3 fallback gestures recognized | Fallback path works | |
| No custom fallback for MediaPipe-covered gestures | Only 3 fallback recognizers exist | |
| Coverage ≥ 80% for `gestures/` | pytest --cov=gestures | |
| No raw-pixel thresholds in custom fallback recognizers | All distances normalized | |
| V2 DynamicGestureEngine stub raises NotImplementedError | Confirmed | |

### Definition of Done

1. All 8 static gestures recognized correctly (5 via MediaPipe, 3 via custom fallback)
2. Scale-invariance tests pass for 3 custom fallback gestures
3. Gesture Gate test_single_frame_flicker and test_cooldown_suppresses_repeated_trigger pass
4. ModelManager fallback scenario test passes
5. Coverage ≥ 80% for `gestures/`
6. No raw-pixel thresholds in custom fallback recognizers
7. V2 DynamicGestureEngine confirmed as stub

---

## 8. Checkpoint 4 — Activation & Command Routing

### Status: ⚠️ Partially Completed (ActivationGate exists; CommandRouter + ContextEngine missing)

### Objective

Implement the Activation Gate (INACTIVE/ACTIVE state machine), Command Router (gesture-to-action mapping), and Context Engine (active window detection). Wire first end-to-end integration test.

### Prerequisites / Dependencies

CP-3 must be Done.

### Architecture Changes

- ActivationGate: already exists and matches TRD §3.11 — verify and wire into pipeline
- CommandRouter: NEW per TRD §3.13 — split from old ActionEngine concept
- ContextEngine: NEW per TRD §3.12 — active window detection with verification layer
- WindowsContextAdapter: NEW per TRD §3.12 — V1 Windows-only

### Repository / Folder & File Changes

#### Modify Existing Files
| File | Change |
|---|---|
| `gestures/activation_gate.py` | Verify TRD §3.11 compliance; wire into CaptureThread |
| `app/capture_thread.py` | Wire ActivationGate after GestureFuser; add CommandRouter and ContextEngine slots (CP-5 finalizes dispatch) |
| `overlay/overlay_window.py` | Add ACTIVE/INACTIVE indicator per FR-AM-05 and FR-VF-06 |

#### Create Files
| File | Purpose |
|---|---|
| `actions/command_router.py` | Full implementation per TRD §3.13 |
| `context/context_engine.py` | Full implementation per TRD §3.12 |
| `context/adapters/base.py` | ContextAdapterBase ABC |
| `context/adapters/windows_adapter.py` | WindowsContextAdapter per TRD §3.12 |
| `tests/integration/test_pipeline_end_to_end.py` | First full-pipeline integration test |

### Implementation Tasks

#### Task 4.1 — Verify ActivationGate (✅ Already Completed)
Per TRD §3.11 and PRD §7:
- Binary INACTIVE/ACTIVE state machine
- Open Palm held 1s (configurable 0.5–3.0s per FR-AM-07) toggles state
- Default state on launch is INACTIVE (FR-AM-06)
- Hold-timer resets on non-qualifying gesture (no partial credit)
- `toggle()` method for keyboard shortcut (Ctrl+Alt+G) and tray icon
- State change logged with timestamp (FR-AM-04)
- Wire `feed_gesture()` to receive cooldown-cleared candidates

#### Task 4.2 — Create context/context_engine.py
Per TRD §3.12 and PRD §8.6:
- `resolve(now: float) -> str` — returns current context name
- Poll OS every 250ms for active foreground window
- Context Verification Layer: 200ms continuous focus before accepting new context (PRD §8.6.1)
- On OS query failure, return last known context (never crash)
- Uses `WindowsContextAdapter` for V1 only

#### Task 4.3 — Create context/adapters/base.py
Per TRD §10.2:
- `ContextAdapterBase` ABC with abstract method `get_active_process_name() -> str`
- Docstring: "Return the name of the active foreground process."

#### Task 4.4 — Create context/adapters/windows_adapter.py
Per TRD §3.12:
- `WindowsContextAdapter(ContextAdapterBase)` — implements `get_active_process_name()` using `pywin32`
- V1 only: no macOS/Linux adapters created (RULES §1.2, §1.3, §8.5)

#### Task 4.5 — Create actions/command_router.py
Per TRD §3.13 and RULES §7.5:
- `__init__(self, profile_manager, context_engine)` — receives ContextEngine and ProfileManager
- `route(self, gesture: GestureResult) -> Action | None`:
  1. Obtain current context from ContextEngine
  2. Look up (gesture, context) → action in active profile's mapping table
  3. Final cooldown re-check
  4. Build and return `Action` object (does NOT execute — RULES §7.5)
- Only module permitted to resolve GestureResult → Action

#### Task 4.6 — Wire CaptureThread for CP-4
Add to the per-frame pipeline (after CP-3 stages):
```
GestureFuser output → ActivationGate.feed_gesture() → if ACTIVE: CommandRouter.route()
```
Note: CP-3 runs regardless of activation state (FR-AM-01 bypasses DISPATCH only — recognition must run to detect toggle gesture).

#### Task 4.7 — Update overlay with activation state indicator
Per FR-VF-06:
- ACTIVE state → green text
- INACTIVE state → grey text
- Skeleton continues rendering in both states (FR-AM-02)

#### Task 4.8 — Create first integration test
`test_pipeline_end_to_end.py`:
- Mock camera feed with synthetic hand landmarks
- Full pipeline: Camera → HandLandmarker → ... → CommandRouter
- Verify that a gesture in mock feed → CommandRouter emits an Action (not yet dispatched)

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| Activation Gate blocks all processing when INACTIVE | FR-AM-01 | |
| Open Palm held 1s toggles state | FR-AM-07 | |
| Default state on launch is INACTIVE | FR-AM-06 | |
| CommandRouter correctly maps (gesture, context) → action | Mapping table works | |
| ContextEngine resolves active window | Process name returned | |
| Context Verification Layer (200ms) respected | Rapid switches rejected | |
| Integration test passes | Full pipeline verified | |
| No actions dispatched (CP-5 scope) | Pipeline stops at CommandRouter | |

### Definition of Done

1. All Acceptance Criteria pass
2. First integration test passes
3. Manual validation of Zoom-call scenario (no triggers while INACTIVE)
4. Activation state visible in overlay

---

## 9. Checkpoint 5 — Action Execution

### Status: 🔲 Pending

### Objective

Implement OS-level dispatch: cursor movement (with smoothing), mouse clicks, keyboard shortcuts, scroll, and system commands via ActionExecutor and WindowsExecutor.

### Prerequisites / Dependencies

CP-4 must be Done.

### Architecture Changes

- ActionExecutor absorbs CursorController per TRD §3.14
- WindowsExecutor is the only V1 executor (RULES §1.1)
- Only module permitted to call OS-level APIs (RULES §7.1)

### Repository / Folder & File Changes

#### Create Files
| File | Purpose |
|---|---|
| `actions/action_executor.py` | Full implementation per TRD §3.14 |
| `actions/executors/base.py` | ActionExecutorBase ABC per TRD §10.2 |
| `actions/executors/windows_executor.py` | WindowsExecutor per TRD §3.14 |

#### Modify Existing Files
| File | Change |
|---|---|
| `app/capture_thread.py` | Wire CommandRouter output to ActionExecutor |
| `ext/registry.py` | Register `action_executor.windows` |

### Implementation Tasks

#### Task 5.1 — Create actions/executors/base.py
Per TRD §10.2:
- `ActionExecutorBase` ABC with abstract method `execute(action: Action) -> ActionResult`
- Must NOT raise; return `ActionResult(success=False, ...)` on error

#### Task 5.2 — Create actions/executors/windows_executor.py
Per TRD §3.14:
- `WindowsExecutor(ActionExecutorBase)` — implements `execute()` using PyAutoGUI and pynput
- V1 only: no macOS/Linux executors created (RULES §8.5)

#### Task 5.3 — Create actions/action_executor.py
Per TRD §3.14:
- Internal `CursorController` subsystem:
  - Index fingertip → screen coordinate mapping with edge buffers (FR-CC-02)
  - Exponential Moving Average smoothing (FR-CC-03, default `smoothing_alpha=0.7`)
  - Sensitivity multiplier (FR-CC-04, 0.1x–5.0x)
  - Screen edge clamping (FR-CC-05)
- Internal `CommandDispatch` subsystem:
  - Mouse: left/right/double click, drag-and-drop, scroll
  - Keyboard: Enter, Escape, Tab, Alt+Tab, Ctrl+C/V/Z/S
  - System: volume up/down, mute, screenshot, lock screen, show desktop
- Implementation order: Cursor → Mouse → Keyboard → Scroll → System
- Only module permitted to call OS-level APIs (RULES §7.1, §7.3)

#### Task 5.4 — Wire CaptureThread for CP-5
Add to the per-frame pipeline (after CP-4):
```
CommandRouter.route() → ActionExecutor.execute()
```
The `gesture_detected` signal feeds CommandRouter; ActionExecutor dispatches.

#### Task 5.5 — Update ExtensionRegistry
Register:
- `'action_executor.windows'` → `WindowsExecutor()`

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| Cursor follows index fingertip across full screen | Smooth tracking | |
| Pinch triggers left click; OK Sign triggers right click | Correct dispatch | |
| 5+ keyboard shortcuts functional | Ctrl+C, Ctrl+V, Alt+Tab, etc. | |
| Cursor visibly smoothed under static hand-hold test | Variance reduction | |
| No stuck modifier keys across 10+ rapid dispatches | Clean release | |

### Definition of Done

1. All Acceptance Criteria pass on Windows
2. No stuck-modifier-key state across 10+ rapid hotkey dispatches
3. Cursor smoothing test passes (variance reduction)

---

## 10. Checkpoint 6 — GUI & Calibration

### Status: 🔲 Pending

### Objective

Build user-facing configuration surfaces: Settings panel, Profile manager, Mapping editor, Calibration Wizard, Main window, System tray icon.

### Prerequisites / Dependencies

CP-5 must be Done.

### Architecture Changes

- ProfileManager: new per TRD §3.17
- CalibrationManager + TrackingZone: new per TRD §12
- All UI files in `ui/` directory
- ExtensionRegistry integration visible in UI settings

### Repository / Folder & File Changes

#### Create Files
| File | Purpose |
|---|---|
| `profiles/profile_manager.py` | Profile persistence per TRD §3.17 |
| `ui/main_window.py` | Main control panel |
| `ui/settings_panel.py` | Settings panel with camera/gesture/cursor/ML tabs |
| `ui/mapping_editor.py` | Gesture mapping table |
| `ui/profile_panel.py` | Profile CRUD UI |
| `ui/onboarding_wizard.py` | First-run onboarding |
| `ui/calibration_wizard.py` | 4-step calibration per PRD §16 |
| `ui/tray_icon.py` | System tray icon with menu |
| `calibration/calibration_manager.py` | Calibration business logic per TRD §12 |
| `calibration/tracking_zone.py` | TrackingZone data model per PRD §16 |

#### Modify Existing Files
| File | Change |
|---|---|
| `overlay/overlay_window.py` | Add overlay toggle via keyboard shortcut |

### Implementation Tasks

#### Task 6.1 — Create profiles/profile_manager.py
Per TRD §3.17:
- Load/save profiles from JSON files
- CRUD operations: create, rename, delete, export, import
- Active profile management
- Mapping conflict detection (PRD FR-GM-03)
- Settings schema extended with `active_profile`

#### Task 6.2 — Create ui/main_window.py
- Main control panel with status bar (profile, FPS, webcam status)
- Gesture mapping table
- Quick-toggle switches
- Link to settings panel, calibration wizard

#### Task 6.3 — Create ui/settings_panel.py
Per PRD §23.1:
- Camera tab: device selector, resolution, FPS target, camera validation status
- Gesture tab: confidence threshold, cooldown sliders, stability window slider
- Cursor tab: speed multiplier, smoothing method, calibration wizard launcher
- ML tab (NEW in V2.0): model status, fallback mode indicator
- Profiles tab: create, rename, delete, import, export
- About tab: version, licenses

#### Task 6.4 — Create ui/mapping_editor.py
Per PRD §8.7:
- GUI for mapping any gesture to any system command
- Conflict detection (FR-GM-03)
- Export/import mapping files (FR-GM-04)

#### Task 6.5 — Create ui/profile_panel.py
- Profile CRUD
- Profile activation

#### Task 6.6 — Create calibration/calibration_manager.py
Per PRD §16:
- 4-step calibration: Camera Position, Sensitivity, Cursor Speed, Tracking Area
- Results persisted to settings.json immediately (FR-CAL-02)
- Skipping calibration allowed (FR-CAL-03)
- Must complete in under 3 minutes (FR-CAL-04)

#### Task 6.7 — Create calibration/tracking_zone.py
- `TrackingZone` dataclass (already in `models/data_models.py`)
- `map_to_screen()` coordinate transform

#### Task 6.8 — Create ui/onboarding_wizard.py
- First-run experience
- Camera check
- Quick gesture demo
- Links to calibration wizard

#### Task 6.9 — Create ui/calibration_wizard.py
Per PRD §23.1:
- Step 1: Camera Position check
- Step 2: Sensitivity tuning
- Step 3: Cursor Speed tuning
- Step 4: Tracking Area definition

#### Task 6.10 — Create ui/tray_icon.py
Per PRD §23.1:
- System tray icon with menu: Open, Toggle Tracking, Switch Profile, Settings, Quit

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| Settings panel reads/writes settings.json correctly | Round-trip verified | |
| Profiles can be created, switched, exported, imported | Full CRUD | |
| Mapping editor shows all current mappings | Table populated | |
| System tray with Toggle/Switch Profile/Quit | Menu functional | |
| Calibration wizard functional for cursor tracking zone | 4 steps complete | |
| ML tab shows model status (LOADED / FALLBACK_ONLY) | Status read from ModelManager | |

### Definition of Done

1. All Acceptance Criteria pass
2. Mapping editor with conflict detection
3. Calibration wizard completes in under 3 minutes

---

## 11. Checkpoint 7 — Diagnostics & Developer Mode

### Status: ⚠️ Partially Completed (DiagnosticsManager exists; LightingMonitor + full Developer Mode pending)

### Objective

Complete the full Debugging & Diagnostics system: LightingMonitor, CameraValidator warning surfacing in overlay, full Developer Mode debug panel with ML model status indicators, fallback mode indicator in overlay.

### Prerequisites / Dependencies

CP-6 must be Done.

### Architecture Changes

- LightingMonitor: new per TRD §3.12
- Developer Mode: enhanced per TRD §11.3
- ML fallback indicator: per FR-VF-08

### Repository / Folder & File Changes

#### Modify Existing Files
| File | Change |
|---|---|
| `diagnostics/lighting_monitor.py` | Full implementation (currently scaffold) |
| `overlay/debug_panel.py` | Add ML model status line, pipeline diagnostics |
| `overlay/overlay_window.py` | Add fallback mode indicator per FR-VF-08 |

#### Create Files
| File | Purpose |
|---|---|
| `tests/integration/test_ml_fallback_indicator.py` | Verify fallback indicator appears when model unavailable |

### Implementation Tasks

#### Task 7.1 — Implement lighting_monitor.py
Per TRD §3.12:
- Monitor frame brightness (mean luminance)
- Correlate with MediaPipe detection confidence
- Surface sustained low-light warning via DiagnosticsManager
- `check(frame: np.ndarray) -> LightingQuality` per TRD §6.4

#### Task 7.2 — Surface CameraValidator warnings in overlay
- Low FPS warning badge when sustained below 25 FPS for 5s
- Resolution warning when below 640×480

#### Task 7.3 — Add ML model status to Developer Mode panel
Per TRD §11.3:
- Show: `ML Model Status: LOADED` or `ML Model Status: FALLBACK_ONLY`
- Show: `last_inference: Xms ago, conf: Y.ZZ`
- Show: `gesture_recognizer: OK` or `gesture_recognizer: UNAVAILABLE`

#### Task 7.4 — Add fallback mode indicator to overlay
Per FR-VF-08:
- When `ModelManager.is_gesture_model_available() == False`, show warning badge
- Text: "FALLBACK MODE — limited gestures available"
- Visible in both INACTIVE and ACTIVE states

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| Lighting warning appears within 3s of dark room | Threshold triggered | |
| Developer Mode panel shows ML model status | LOADED / FALLBACK_ONLY | |
| Fallback mode indicator appears when model unavailable | Confirmed | |
| Developer Mode panel data matches actual gesture decisions | Verified | |
| Camera FPS warning appears when below 25 FPS | Confirmed | |

### Definition of Done

1. All Acceptance Criteria pass
2. Full Developer Mode panel per TRD §11.3
3. ML fallback indicator verified

---

## 12. Checkpoint 8 — Testing, Optimization & Packaging

### Status: 🔲 Pending

### Objective

Execute the full test pyramid against the complete, feature-frozen system. Validate performance budgets. Package for Windows release.

### Prerequisites / Dependencies

CP-7 must be Done.

### Architecture Changes

- None (feature-frozen)
- All changes are testing, optimization, and packaging only

### Repository / Folder & File Changes

#### Create Files
| File | Purpose |
|---|---|
| `tests/performance/test_fps_and_memory.py` | Performance test per TRD §15.4 |
| `installer/windows/installer.iss` | Inno Setup installer script |

#### Modify Existing Files
| File | Change |
|---|---|
| `pyinstaller.spec` | Finalize with MediaPipe model bundling per TRD §14.2 |
| `requirements.txt` | Verify pinned versions; no changes unless required |

### Implementation Tasks

#### Task 8.1 — Coverage audit
- Target: ≥ 80% line coverage across all module groups per AI Dev Guide §11.3
- Module groups: `gestures/`, `actions/`, `models/`, `ext/`, `profiles/`, `settings/`, `tracking/`

#### Task 8.2 — Performance testing
Per TRD §15 and PRD §17:
- 30-min continuous session with profiling
- 4-hour memory growth test
- Verify all 5 budgets: FPS ≥ 25, detection latency < 100ms, end-to-end < 150ms, CPU < 20%, memory < 300MB
- Implement alternating-frame inference if budget exceeded (TRD §15.3)

#### Task 8.3 — Gesture accuracy testing
Per PRD §18.2:
- 100 samples per gesture from 5 different users
- 3 lighting conditions: bright, dim, backlit
- 3 camera distances: close (~30cm), medium (~75cm), far (~150cm)
- Acceptance: ≥ 95% accuracy at every distance

#### Task 8.4 — ML fallback verification
- Verify system operates correctly when MediaPipe model is unavailable
- 3 custom fallback gestures continue to work
- User-visible warning appears in overlay
- Auto-reload triggers after 3 consecutive inference failures

#### Task 8.5 — PyInstaller packaging
Per TRD §14:
- Finalize `pyinstaller.spec` with MediaPipe model bundling (`datas` directive)
- `hiddenimports` for `pynput.keyboard._win32`, `pynput.mouse._win32`, MediaPipe task modules
- Verify model files bundled correctly
- Startup self-check passes (TRD §14.3)

#### Task 8.6 — Windows installer
- Inno Setup-based installer producing `GestureOS_Setup.exe`
- Start Menu entry
- Optional auto-start

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| Coverage ≥ 80% across all module groups | pytest --cov | |
| FPS ≥ 25 on reference hardware | 30-min session | |
| Gesture accuracy ≥ 95% at all 3 distances | Confirmed | |
| 4-hour memory growth < 10MB/hour | Confirmed | |
| Windows installer builds successfully | `GestureOS_Setup.exe` | |
| Packaged artifact passes startup self-check | Confirmed | |
| No P0 bugs open | Bug tracker | |

### Definition of Done

1. All 5 PRD §17 performance budgets met simultaneously on reference hardware
2. Gesture accuracy ≥ 95% at all 3 distances
3. 4-hour memory growth < 10MB/hour
4. All UAT scenarios pass
5. Windows installer builds successfully
6. Packaged artifact passes startup self-check
7. No P0 bugs open

---

## 13. Checkpoint 9 — V2 Architecture Certification

### Status: 🔲 Pending (NEW checkpoint)

### Objective

Certify that the entire repository is fully compliant with the V2.0 Architecture Freeze Specification. Perform a cross-document requirements traceability audit. Verify every RULES.md rule is followed. Freeze all documentation.

### Prerequisites / Dependencies

CP-8 must be Done.

### Architecture Changes

- None (this is a verification-only checkpoint)
- No code, file, or architecture changes permitted

### Implementation Tasks

#### Task 9.1 — RULES.md compliance audit
Verify every rule in RULES.md v2.0 is followed:
- §1 (Platform): No macOS/Linux code in V1
- §2 (Architecture): Pipeline order, module boundaries, ModelManager exclusivity, ExtensionRegistry exclusivity
- §3 (Configuration): Named constants, no magic numbers, ML config via ModelManager
- §4 (GestureFuser): Sole authority, no bypass, immutability
- §5 (Recognition): MediaPipe primary, 3 custom fallbacks only, scale-invariance, multi-signal
- §6 (Multi-Signal): State containers, MotionHistoryService as sole temporal store
- §7 (Command Router / Executor): ActionExecutor exclusive OS access, no mapping in executor
- §8 (File/Module): Accepted file structure, no catch-all utils, no cross-platform files in V1
- §9 (Logging): No print(), correct levels, no raw landmarks at INFO+
- §10 (Checkpoint Discipline): No scope creep
- §11 (Implementation Reporting): Pre/post reports exist
- §12 (Performance): Frame-loop efficiency, allocation-light hot path
- §13 (ML Governance): Only MediaPipe permitted, ModelManager exclusivity, no runtime downloads
- §14 (Extension System): Code-level ABCs only, no hot-loading in V1

#### Task 9.2 — PRD v2.0 requirements traceability
- Map every PRD FR- requirement ID to a checkpoint deliverable
- Verify every requirement is implemented
- Document any gaps

#### Task 9.3 — TRD v2.0 component verification
- Verify every TRD §3 component matches its specification exactly
- Verify TRD §9 folder structure matches exactly
- Verify TRD §7 data models match exactly
- Verify TRD §8 configuration design matches exactly

#### Task 9.4 — AI Development Guide compliance
- Verify §4 repository structure matches
- Verify §5 architecture rules are followed
- Verify §6 coding standards (naming, type hints, dataclasses)
- Verify §7 Static Gesture Engine standards
- Verify §8 ML Model Integration standards
- Verify §9 Extension System standards
- Verify §10 Logging standards
- Verify §11 Testing standards

#### Task 9.5 — Documentation freeze
- All 5 source documents (PRD, TRD, Implementation Plan, AI Dev Guide, RULES) are frozen
- Version bumps to 2.0.0-final
- Changelogs updated
- Documents archived to `docs/`

### Validation Checklist

| Check | Expected | Verified |
|---|---|---|
| All RULES.md rules verified | 0 violations | |
| All PRD FR- requirements traced | 100% coverage | |
| All TRD §3 components match spec | 17/17 verified | |
| TRD §9 folder structure matches | Exact match | |
| AI Development Guide §4 structure matches | Exact match | |
| No macOS/Linux code in V1 pipeline | Confirmed | |
| No component loads ML models outside ModelManager | Confirmed | |
| All extension implementations registered via ExtensionRegistry | Confirmed | |
| All ML events logged through DiagnosticsManager | Confirmed | |
| Documentation frozen and archived | Done | |

### Definition of Done

1. All RULES.md rules verified with 0 violations
2. 100% PRD FR- requirement traceability
3. TRD §3 component spec compliance confirmed (17/17)
4. TRD §9 folder structure match confirmed
5. AI Development Guide compliance confirmed
6. Documentation frozen and versioned to 2.0.0-final
7. Architecture Freeze Specification v1.0 compliance certificate issued

### Deliverables

- Compliance audit report
- Requirements traceability matrix
- Architecture Freeze compliance certificate

---

## 14. V2 Forward Reference

> V2 is explicitly out of scope for this implementation plan. The following components are documented as architectural placeholders only.

### V2 Component Targets

| Component | Description | V1 Status |
|---|---|---|
| Dynamic Gesture Engine | Lightweight temporal model on MediaPipe landmark sequences | Stub in `gestures/dynamic_gesture_engine.py` |
| Gesture Fuser (V2) | Full static + dynamic fusion | Currently pass-through (V1) |
| Hot-loadable plugins | Filesystem discovery, version negotiation, sandboxed loading | V1 has code-level ExtensionRegistry only |
| Cross-platform expand | macOS/Linux adapters and executors | V1 Windows-only |

### V2 Architecture Changes

V2 will add the Dynamic Gesture Engine as a parallel recognition path feeding into the Gesture Fuser. The current V1 pipeline becomes one of two input paths to the Fuser. All other components remain unchanged.

### V2 Model Governance

Approved V2 candidate architectures (operating on 63-dim MediaPipe landmark features):
- LSTM (1-2 layers, 64-dim hidden)
- GRU (1-2 layers)
- 1D CNN (3-4 conv layers)

Explicitly NOT approved:
- ViT on raw images
- Any CNN on raw pixel data

Final model selection occurs during V2 implementation after benchmarking on reference hardware.

### V2 Documentation Requirements

When V2 planning begins:
- New Architecture Change Request
- Updated PRD with V2 sections
- Updated TRD with Dynamic Gesture Engine spec
- Updated Implementation Plan with V2 checkpoints
- Final V2 model selection based on V2 benchmarking

---

## 15. Risk Management

| Risk | Severity | Probability | Mitigation | Checkpoint |
|---|---|---|---|---|
| MediaPipe model not bundled | High | Medium | Explicit PyInstaller datas; early smoke-build | CP-0, CP-8 |
| MediaPipe inference exceeds per-frame budget | Medium-High | Medium | Alternating-frame inference strategy (TRD §15.3) | CP-3 |
| Custom fallback accuracy gap vs MediaPipe | Medium | Medium | Scale-invariance testing; threshold tuning | CP-3 |
| Model load failure at startup | Medium | Low | ModelManager fallback to custom-only mode | CP-0, CP-1 |
| Cursor jitter | High | High (inherent) | EMA smoothing mandatory (FR-CC-03) | CP-5 |
| Activation gate misconfiguration | High | Low | Default INACTIVE; explicit tests | CP-4 |
| PyInstaller + MediaPipe bundling | High | Medium | Known issue; explicit datas entry | CP-0, CP-8 |
| Custom fallback and MediaPipe produce conflicting results | Low | Medium | Fuser picks max confidence; both can fire for different gestures | CP-3 |
| V2 model selection uncertainty | Low | N/A (V2) | Three candidates documented; benchmarking during V2 | V2 |
| File rename breaks existing tests | Medium | High | Update all imports in same change set as rename | CP-0 |
| Migration from V1.x misses a component | High | Low | Comprehensive audit in CP-9 certification | CP-9 |

---

## 16. Definition of Done

### 16.1 Checkpoint Definition of Done

A checkpoint is Done when:
1. All Deliverables exist in the specified locations
2. All Modules match TRD §3 specification
3. All Acceptance Criteria pass
4. Unit test coverage ≥ 80% for new/modified modules
5. No regressions in prior checkpoints' tests
6. No scope creep
7. Code review confirms architectural discipline
8. Any Gap encountered is documented

### 16.2 V1 Project Definition of Done

GestureOS V1 is Done when:
1. All 10 checkpoints (CP-0 through CP-9) are individually Done
2. Every PRD v2.0 functional and non-functional requirement is implemented
3. Every TRD v2.0 component specification is matched exactly
4. Every RULES.md v2.0 rule is followed
5. Every AI Development Guide v2.0 standard is met
6. CP-9 Architecture Certification is complete
7. ML model fallback path is tested and verified
8. Documentation is frozen and archived

---

*End of GestureOS Implementation Plan v2.0.1*
