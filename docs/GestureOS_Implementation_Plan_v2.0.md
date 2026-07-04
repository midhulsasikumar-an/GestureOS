# Implementation Plan — GestureOS

**Document Type:** Implementation Plan (Execution Roadmap)
**Source Documents:** GestureOS PRD v2.0, GestureOS TRD v2.0
**Source of Truth:** Architecture Freeze Specification v1.0 (2026-07-04)
**Version:** 2.0.0
**Audience:** Engineering team, AI coding agents, project management
**Date:** July 2026

> **Major Changes from v1.1:**
> - Restructured to match the V1/V2 architecture split. V1 focuses on static gesture recognition via MediaPipe + custom fallback. V2 (Dynamic Gesture Engine) is explicitly out of scope.
> - Renamed checkpoints to align with new component names: CP-1 is now "Core Hand Tracking + ML Foundation" (includes ModelManager + MediaPipe model integration), CP-2 is "Hand Analysis Layer", CP-3 is "Static Gesture Engine" (split from former gesture recognition), etc.
> - New checkpoint: CP-1.5 "ModelManager and Extension Foundation" to establish the ML lifecycle and extension registry as first-class infrastructure.
> - The 11-checkpoint sequence is consolidated into 9 engineering checkpoints (CP-0 through CP-8), with V2 scope documented as forward reference.
> - Component names throughout updated to match the frozen architecture.

---

## Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [Development Strategy](#2-development-strategy)
3. [Checkpoint Structure](#3-checkpoint-structure)
4. [Checkpoint 0 — Project Foundation](#4-checkpoint-0--project-foundation)
5. [Checkpoint 1 — Core Platform & ML Foundation](#5-checkpoint-1--core-platform--ml-foundation)
6. [Checkpoint 2 — Hand Analysis Layer](#6-checkpoint-2--hand-analysis-layer)
7. [Checkpoint 3 — Static Gesture Engine](#7-checkpoint-3--static-gesture-engine)
8. [Checkpoint 4 — Activation & Command Routing](#8-checkpoint-4--activation--command-routing)
9. [Checkpoint 5 — Action Execution](#9-checkpoint-5--action-execution)
10. [Checkpoint 6 — GUI & Calibration](#10-checkpoint-6--gui--calibration)
11. [Checkpoint 7 — Diagnostics & Developer Mode](#11-checkpoint-7--diagnostics--developer-mode)
12. [Checkpoint 8 — Testing, Optimization & Packaging](#12-checkpoint-8--testing-optimization--packaging)
13. [V2 Forward Reference](#13-v2-forward-reference)
14. [Risk Management](#14-risk-management)
15. [Definition of Done](#15-definition-of-done)

---

## 1. Executive Overview

### 1.1 Project Summary

GestureOS is a Windows desktop application that acts as an intelligent gesture-based operating layer between the user and the operating system, enabling touchless control via webcam-based hand gesture recognition (PRD §1–3). V1 recognition is **AI-assisted**: Google's MediaPipe Gesture Recognizer is the primary engine for static gesture classification, with lightweight custom geometric fallback recognizers for the 3 gestures MediaPipe does not cover (Pinch, Three Fingers, OK Sign). All processing is local. No cloud dependency. No telemetry.

This Implementation Plan sequences the V1 build into 9 checkpoints (CP-0 through CP-8), each producing a working, testable increment. The plan is designed for execution by AI coding agents working checkpoint-by-checkpoint.

### 1.2 Development Philosophy

- **Foundation before features.** The capture-and-recognition pipeline (camera → tracking → analysis → recognition) must exist and be provably correct before any action-dispatch or UI work begins.
- **ML model lifecycle established early.** ModelManager is built in CP-1, not retrofitted later. Custom fallback recognizers are built alongside MediaPipe integration in CP-3.
- **One source of truth per concern.** The PRD defines *what*; the TRD defines *how*. This plan adds *when* and *in what order*.
- **Testable increments.** Every checkpoint ends in a runnable, demonstrable state.
- **Configuration over hardcoding.** The JSON configuration system is built in CP-0.

### 1.3 Core Principles

1. No checkpoint begins before its dependencies' Definition of Done is met.
2. No ML model may be loaded or instantiated outside of `ModelManager`.
3. Every component built must match its TRD §3 specification exactly.
4. Every PRD functional requirement must be traceable to at least one checkpoint.
5. Privacy and local-only processing is structural from the start — no network-capable imports in the core pipeline.

---

## 2. Development Strategy

### 2.1 Foundation-First Approach

```
Camera
  ↓
Hand Landmarker (MediaPipe)
  ↓
Hand Analysis (identity, occlusion, scale, primary hand)
  ↓
Motion History Service
  ↓
Static Gesture Engine (MediaPipe + 3 custom fallbacks)
  ↓
Gesture Gate (stability + cooldown)
  ↓
Gesture Fuser
  ↓
Activation Gate
  ↓
Command Router
  ↓
Action Executor
```

### 2.2 Why This Order Is Mandatory

| Layer | Why It Must Come Before the Next |
|---|---|
| Camera → Hand Landmarker | No landmarks without a working capture loop |
| Hand Landmarker → Analysis | Analysis components consume `HandData.landmarks` |
| Analysis → Motion History | Motion History records landmark data per hand role |
| Motion History → Static Gesture | Static Gesture Engine reads from Motion History for stability checks |
| Static Gesture → Gate → Fuser | Sequential filtering; each stage consumes the previous output |
| Fuser → Activation → Router → Executor | Activation is the safety gate; Router maps to actions; Executor dispatches |

### 2.3 Testing Philosophy

- Unit tests use synthetic/mock data (no live camera required)
- Integration tests from CP-3 onward (when full pipeline is wired)
- Performance testing in CP-8
- ML model fallback testing in CP-3 (simulate model load failure)

---

## 3. Checkpoint Structure

### 3.1 Checkpoint Cross-Reference Table

| This Plan | PRD Reference | Focus |
|---|---|---|
| CP-0 | §1.2 (Platform) | Project scaffold, settings, logging, tests |
| CP-1 | §9 (Architecture) | Camera, Hand Landmarker, ModelManager, ExtensionRegistry |
| CP-2 | §8.1 (Hand Tracking), §6 (Scale) | Identity, occlusion, scale, primary hand, Motion History Service |
| CP-3 | §5 (Gesture Strategy), §8.2 (Gate) | Static Gesture Engine, Gesture Gate, Gesture Fuser |
| CP-4 | §7 (Activation), §8.5 (Context) | Activation Gate, Command Router, Context Engine |
| CP-5 | §8.3 (Cursor), §8.5 (System) | ActionExecutor, WindowsExecutor |
| CP-6 | §8.7 (Mappings), §16 (Calibration) | Settings UI, Profile UI, Calibration Wizard |
| CP-7 | §13 (Diagnostics) | Full debug overlay, ML status indicators, Developer Mode |
| CP-8 | §17 (Performance), §21 (Deployment) | Testing, optimization, PyInstaller packaging |

### 3.2 Standard Checkpoint Template

Every checkpoint includes: Purpose, Scope, Deliverables, Modules, Files, Dependencies, Risks, Acceptance Criteria, Testing Strategy, Definition of Done.

---

## 4. Checkpoint 0 — Project Foundation

### Purpose

Establish the repository structure, environment, configuration system, logging framework, and testing harness.

### Scope

**In scope:** Repository skeleton, Python environment, SettingsManager, DiagnosticsManager, pytest configuration.

**Out of scope:** Any camera, tracking, gesture, or UI code.

### Deliverables

1. Repository skeleton matching TRD §9 folder structure
2. `requirements.txt` with pinned versions (Python 3.11+, OpenCV, MediaPipe 0.10.x, NumPy, PyQt6, PyAutoGUI, pynput, pywin32, PyInstaller, pytest)
3. `models/data_models.py` with all dataclasses stubbed
4. `settings/settings_manager.py` implementing Settings dataclass and load/validate/atomic-write
5. `diagnostics/diagnostics_manager.py` with foundational logging pipeline
6. `ext/base.py` with extension interface ABCs (GestureRecognizerBase, ActionExecutorBase, ContextAdapterBase, PipelineFilterBase)
7. `ext/registry.py` implementing ExtensionRegistry
8. `pytest.ini` and `tests/conftest.py` scaffolding

### Files

```
gestureos/
├── main.py
├── requirements.txt
├── pyinstaller.spec (stub)
├── pytest.ini
├── models/
│   ├── data_models.py
│   └── model_manager.py (scaffold only)
├── settings/
│   └── settings_manager.py
├── diagnostics/
│   ├── diagnostics_manager.py
│   └── log_format.py
├── ext/
│   ├── base.py
│   └── registry.py
└── tests/
    ├── conftest.py
    └── unit/
        └── test_settings_manager.py
```

### Definition of Done

- All Deliverables exist
- Repository structure matches TRD §9
- CI pipeline is green
- No component outside the scaffolded folders has been created

---

## 5. Checkpoint 1 — Core Platform & ML Foundation

### Purpose

Stand up the capture-and-detection loop AND establish the ML model lifecycle and extension system foundations.

### Scope

**In scope:**
- CameraModule (per TRD §3.1)
- CameraValidator (startup + rolling FPS measurement)
- HandLandmarker (MediaPipe wrapper, renamed from TrackingModule)
- ModelManager (ML model lifecycle, load/cache/reload)
- ExtensionRegistry integration with all built-in implementations
- Minimal OverlayEngine showing skeleton + FPS + ML status
- CaptureThread orchestration: Camera → Landmarker → Overlay

**Out of scope:**
- Hand identity (CP-2)
- Any gesture recognition (CP-3)
- Activation gating (CP-4)
- Action dispatch (CP-5)

### Deliverables

1. `camera/camera_module.py` per TRD §3.1
2. `diagnostics/camera_validator.py` per TRD §3.2 (measurement only; surfacing in CP-7)
3. `tracking/hand_landmarker.py` per TRD §3.2 (renamed from `hand_detector.py`)
4. `models/model_manager.py` per TRD §3.15:
   - Load MediaPipe Hand Landmarker at startup
   - Load MediaPipe Gesture Recognizer at startup
   - Expose `is_gesture_model_available()`, `recognize_gesture()`, `record_inference_failure()`, `reload_gesture_model()`
5. `app/core.py` and `app/capture_thread.py` implementing the QThread split
6. Minimal `overlay/overlay_window.py` showing skeleton + FPS + ML model status
7. ExtensionRegistry populated with all built-in implementations at startup

### Files

```
gestureos/
├── app/
│   ├── core.py
│   └── capture_thread.py
├── camera/
│   ├── camera_module.py
│   └── errors.py
├── tracking/
│   ├── hand_landmarker.py
│   └── errors.py
├── models/
│   └── model_manager.py
├── overlay/
│   ├── overlay_window.py (minimal)
│   └── skeleton_renderer.py
├── diagnostics/
│   └── camera_validator.py
├── ext/
│   ├── base.py
│   └── registry.py (fully wired)
└── tests/
    ├── unit/
    │   ├── test_camera_validator.py
    │   └── test_model_manager.py
    └── fixtures/
        └── sample_frames/
```

### Dependencies

CP-0 must be Done.

### Risks

| Risk | Mitigation |
|---|---|
| MediaPipe model not bundled correctly | Early PyInstaller smoke-build in this checkpoint |
| ModelManager exception handling too aggressive | Test with intentionally missing model file |
| HandLandmarker rename breaks existing tests | Rename is part of this checkpoint; update test imports simultaneously |

### Acceptance Criteria

- MediaPipe detects hand landmarks on live webcam feed at ≥ 25 FPS
- ModelManager loads both MediaPipe models successfully at startup
- ModelManager reports `is_gesture_model_available() == True` when loaded
- ModelManager handles missing model file gracefully (fallback mode logged)
- ExtensionRegistry populated with all built-in implementations
- FPS counter and ML status visible in overlay

### Testing Strategy

```python
def test_model_manager_loads_successfully(tmp_path):
    mm = ModelManager(diagnostics=mock_diagnostics)
    assert mm.is_hand_landmarker_available()
    assert mm.is_gesture_model_available()

def test_model_manager_handles_missing_model(tmp_path, caplog):
    mm = ModelManager(diagnostics=mock_diagnostics, model_path=str(tmp_path / "nonexistent.task"))
    assert not mm.is_gesture_model_available()
    assert "model_load_failed" in caplog.text
```

### Definition of Done

- All Acceptance Criteria pass
- ModelManager unit tests pass (including fallback scenarios)
- ExtensionRegistry unit tests pass
- PyInstaller smoke-build succeeds with MediaPipe models bundled

---

## 6. Checkpoint 2 — Hand Analysis Layer

### Purpose

Build every component that transforms raw landmarks into analyzed, normalized data for the recognition layer.

### Scope

**In scope:**
- HandIdentityModule
- OcclusionHandler
- HandScaleEstimator
- PrimaryHandFilter
- MotionHistoryService (elevated from MotionHistoryBuffer)
- Shared geometry primitives in `gesture_utils.py`

**Out of scope:**
- Any gesture recognition logic (CP-3)

### Deliverables

1. `tracking/hand_identity.py` per TRD §3.3
2. `tracking/occlusion_handler.py` per TRD §3.4
3. `tracking/hand_scale.py` per TRD §3.5
4. `tracking/primary_hand_filter.py` per TRD §3.6
5. `gestures/motion_history_service.py` per TRD §3.7 (renamed and elevated)
6. `gestures/gesture_utils.py` shared geometry primitives
7. Settings schema extended with `motion_history_frames`, `occlusion_retention_ms`, `dominant_hand_mode`

### Files

```
gestureos/
├── tracking/
│   ├── hand_identity.py
│   ├── occlusion_handler.py
│   ├── hand_scale.py
│   └── primary_hand_filter.py
├── gestures/
│   ├── motion_history_service.py
│   └── gesture_utils.py
├── models/
│   └── data_models.py (HandData extended)
└── tests/
    ├── unit/
    │   ├── test_hand_identity.py
    │   ├── test_occlusion_handler.py
    │   ├── test_hand_scale.py
    │   ├── test_primary_hand_filter.py
    │   ├── test_motion_history_service.py
    │   └── test_gesture_utils.py
    └── fixtures/
        └── sample_landmarks.json
```

### Dependencies

CP-1 must be Done.

### Risks

| Risk | Mitigation |
|---|---|
| MotionHistoryService API different from old MotionHistoryBuffer | Provide migration shim; update callers |
| Hand scale estimation noise | 5-frame moving average; test stability under rotation |

### Acceptance Criteria

- Hand scale computed correctly against known-good fixtures
- Role assignment preserved across hand-crossing scenarios
- 150ms occlusion bridged; 400ms occlusion released
- Dominant Hand Mode correctly filters non-matching hands
- MotionHistoryService stores raw landmarks; normalization at read time
- Coverage ≥ 80% for `tracking/`

### Definition of Done

- All Acceptance Criteria pass
- `HandData` objects flowing out have `scale`, `role`, `gesture_eligible`, `is_retained`, `status` correctly populated
- No raw-pixel thresholds in this checkpoint's code

---

## 7. Checkpoint 3 — Static Gesture Engine

### Purpose

Implement the Static Gesture Engine (MediaPipe Gesture Recognizer + 3 custom fallbacks), Gesture Gate, and Gesture Fuser.

### Scope

**In scope:**
- StaticGestureEngine with two-stage recognition
- MediaPipe integration via ModelManager
- 3 custom fallback recognizers: `detect_pinch`, `detect_three_fingers`, `detect_ok_sign`
- GestureGate (merged stability + cooldown)
- GestureFuser (V1 pass-through)
- DynamicGestureEngine stub (V2 placeholder, not functional)

**Out of scope:**
- Activation gating (CP-4)
- Action dispatch (CP-5)
- Context resolution (CP-4)

### Deliverables

1. `gestures/static_gesture_engine.py` per TRD §3.8:
   - `classify(hands) -> list[GestureResult]`
   - Stage 1: MediaPipe query via ModelManager
   - Stage 2: Custom fallback recognizers
2. `gestures/dynamic_gesture_engine.py` (V2 stub only — raises NotImplementedError)
3. `gestures/gesture_gate.py` per TRD §3.9:
   - `class GestureGate` facade
   - `class StabilityGate` (internal)
   - `class CooldownGate` (internal)
4. `gestures/gesture_fuser.py` per TRD §3.10 (V1 pass-through)
5. ExtensionRegistry updated to register `static_gesture_engine.mediapipe` and `static_gesture_engine.custom_fallback`
6. DiagnosticsManager updated with `ml` category events

### Files

```
gestureos/
├── gestures/
│   ├── static_gesture_engine.py
│   ├── dynamic_gesture_engine.py (V2 stub)
│   ├── gesture_gate.py
│   ├── gesture_fuser.py
│   └── activation_gate.py (scaffold)
├── models/
│   └── data_models.py (GestureResult: add `source` field)
├── diagnostics/
│   └── diagnostics_manager.py (extended)
└── tests/
    ├── unit/
    │   ├── test_static_gesture_engine.py
    │   ├── test_gesture_gate.py
    │   ├── test_gesture_fuser.py
    │   └── test_custom_fallback_recognizers.py
    ├── integration/
    │   └── test_pipeline_through_recognition.py
    └── fixtures/
        ├── open_palm_right.json
        ├── fist_right.json
        ├── pinch_close.json
        ├── pinch_far.json
        ├── three_fingers.json
        └── ok_sign.json
```

### Dependencies

CP-2 must be Done.

### Risks

| Risk | Mitigation |
|---|---|
| MediaPipe inference exceeds per-frame budget | Profile early; implement alternating-frame strategy if needed |
| Custom fallback accuracy gap vs MediaPipe | Document; tune geometric thresholds in testing |
| ModelManager exception not properly caught | Defensive try/except in StaticGestureEngine |
| GestureGate complexity from merging two filters | Internal classes kept separate; facade is thin |

### Acceptance Criteria

- MediaPipe covers 5 of 8 static gestures with ≥ 95% accuracy
- Custom fallback covers Pinch, Three Fingers, OK Sign with ≥ 95% accuracy
- All 3 custom fallback recognizers are scale-invariant (test at 0.5x, 1.0x, 2.0x, 3.0x scale)
- Gesture Gate stability: gesture held 1 frame does not trigger; held 200ms triggers
- Gesture Gate cooldown: repeated single gesture fires exactly once
- Gesture Fuser returns single winner per hand (V1 pass-through verified)
- ModelManager fallback mode test: with model unavailable, system continues to recognize 3 fallback gestures

### Testing Strategy

```python
def test_mediapipe_recognizes_open_palm(open_palm_landmarks, mock_model_manager):
    engine = StaticGestureEngine(mock_model_manager, settings)
    hands = [make_hand(landmarks=open_palm_landmarks)]
    results = engine.classify(hands)
    assert any(r.gesture_name == 'open_palm' and r.source == 'mediapipe' for r in results)

def test_custom_fallback_for_pinch(mediapipe_unavailable, pinch_landmarks):
    # When MediaPipe returns None, custom fallback should still detect Pinch
    engine = StaticGestureEngine(mediapipe_unavailable, settings)
    hands = [make_hand(landmarks=pinch_landmarks, scale=HandScale(...))]
    results = engine.classify(hands)
    assert any(r.gesture_name == 'pinch' and r.source == 'custom_fallback' for r in results)

@pytest.mark.parametrize("scale_factor", [0.5, 1.0, 2.0, 3.0])
def test_pinch_scale_invariant(pinch_landmarks_base, scale_factor):
    scaled = scale_hand_landmarks(pinch_landmarks_base, scale_factor)
    result = detect_pinch(scaled)
    assert result is not None
```

### Definition of Done

- All 8 static gestures recognized correctly
- Scale-invariance tests pass for 3 custom fallback gestures
- Gesture Gate test_single_frame_flicker and test_cooldown_suppresses_repeated_trigger pass
- ModelManager fallback scenario test passes
- Coverage ≥ 80% for `gestures/`
- No raw-pixel thresholds in custom fallback recognizers

---

## 8. Checkpoint 4 — Activation & Command Routing

### Purpose

Implement the Activation Gate (safety) and Command Router (gesture-to-action mapping).

### Scope

**In scope:**
- ActivationGate (INACTIVE/ACTIVE state machine)
- CommandRouter (context resolution + mapping + routing)
- ContextEngine wiring (Windows only)
- First end-to-end integration test

**Out of scope:**
- ActionExecutor internals (CP-5)
- Full GUI (CP-6)

### Deliverables

1. `gestures/activation_gate.py` per TRD §3.11
2. `actions/command_router.py` per TRD §3.13
3. `context/context_engine.py` per TRD §3.12
4. `context/adapters/windows_adapter.py` (V1 only)
5. CaptureThread extended with full pipeline wiring
6. Overlay extended with ACTIVE/INACTIVE indicator
7. First integration test: `test_pipeline_end_to_end.py`

### Files

```
gestureos/
├── gestures/
│   └── activation_gate.py
├── actions/
│   └── command_router.py
├── context/
│   ├── context_engine.py
│   └── adapters/
│       ├── base.py
│       └── windows_adapter.py
├── app/
│   └── capture_thread.py (extended)
├── overlay/
│   └── overlay_window.py (extended)
└── tests/
    ├── unit/
    │   ├── test_activation_gate.py
    │   ├── test_command_router.py
    │   └── test_context_engine.py
    └── integration/
        └── test_pipeline_end_to_end.py
```

### Dependencies

CP-3 must be Done.

### Risks

| Risk | Mitigation |
|---|---|
| Activation Gate hold-timer confusion with Gesture Gate stability | Different time scales (1000ms vs 200ms); document ordering |
| CommandRouter context resolution latency | ContextEngine uses cached context with 200ms verification |

### Acceptance Criteria

- Activation Gate blocks all gesture processing when INACTIVE
- Open Palm held 1s toggles state
- Default state on launch is INACTIVE
- CommandRouter correctly maps (gesture, context) → action
- First integration test: gesture in mock camera feed → CommandRouter emits Action (not yet dispatched)

### Definition of Done

- All Acceptance Criteria pass
- First integration test passes
- Manual validation of Zoom-call scenario (no triggers while INACTIVE)

---

## 9. Checkpoint 5 — Action Execution

### Purpose

Implement OS-level dispatch: cursor movement (with smoothing), mouse clicks, keyboard shortcuts, scroll, system commands.

### Scope

**In scope:**
- ActionExecutor (with internal CursorController and CommandDispatch subsystems)
- WindowsExecutor (V1 only)
- Implementation order: Cursor → Mouse → Keyboard → Scroll → System

**Out of scope:**
- macOS/Linux executors (V2)
- UI (CP-6)

### Deliverables

1. `actions/action_executor.py` per TRD §3.14 (CursorController absorbed)
2. `actions/executors/base.py` and `actions/executors/windows_executor.py`
3. CaptureThread extended to wire CommandRouter output to ActionExecutor
4. ExtensionRegistry updated with `action_executor.windows`

### Files

```
gestureos/
├── actions/
│   ├── action_executor.py
│   └── executors/
│       ├── base.py
│       └── windows_executor.py
├── ext/
│   └── registry.py (extended)
└── tests/
    ├── unit/
    │   └── test_action_executor.py
    └── integration/
        └── test_action_dispatch.py
```

### Dependencies

CP-4 must be Done.

### Risks

| Risk | Mitigation |
|---|---|
| Cursor jitter | EMA smoothing mandatory (FR-CC-03) |
| Stuck modifier keys | Context-managed press/release pairs |
| pycaw unavailability | Catch and log; degrade that action only |

### Acceptance Criteria

- Cursor follows index fingertip across full screen
- Pinch triggers left click; OK Sign triggers right click
- 5+ keyboard shortcuts functional
- Cursor visibly smoothed under static hand-hold test

### Definition of Done

- All Acceptance Criteria pass on Windows
- No stuck-modifier-key state across 10+ rapid hotkey dispatches
- Cursor smoothing test passes (variance reduction)

---

## 10. Checkpoint 6 — GUI & Calibration

### Purpose

Build user-facing configuration surfaces: Settings, Profiles, Mapping Manager, Calibration Wizard.

### Scope

**In scope:**
- ProfileManager
- Settings panel, Profile panel, Mapping editor
- Calibration Wizard + CalibrationManager
- Main window, tray icon, onboarding wizard
- ExtensionRegistry integration visible in UI

**Out of scope:**
- Full debug panel (CP-7)
- Developer Mode data presentation (CP-7)

### Deliverables

1. `profiles/profile_manager.py` per TRD §3.17
2. `ui/settings_panel.py`, `ui/profile_panel.py`, `ui/mapping_editor.py`
3. `ui/main_window.py`, `ui/tray_icon.py`
4. `ui/onboarding_wizard.py`, `ui/calibration_wizard.py`
5. `calibration/calibration_manager.py`, `calibration/tracking_zone.py`

### Files

```
gestureos/
├── profiles/
│   └── profile_manager.py
├── calibration/
│   ├── calibration_manager.py
│   └── tracking_zone.py
├── ui/
│   ├── main_window.py
│   ├── settings_panel.py
│   ├── mapping_editor.py
│   ├── profile_panel.py
│   ├── onboarding_wizard.py
│   ├── calibration_wizard.py
│   └── tray_icon.py
└── tests/
    └── unit/
        └── test_profile_manager.py
```

### Dependencies

CP-5 must be Done.

### Acceptance Criteria

- Settings panel reads/writes settings.json correctly
- Profiles can be created, switched, exported, imported
- Mapping editor shows all current mappings
- System tray with Toggle/Switch Profile/Quit
- Calibration wizard functional for cursor tracking zone

---

## 11. Checkpoint 7 — Diagnostics & Developer Mode

### Purpose

Complete the full Debugging & Diagnostics system, Developer Mode debug panel, and ML status indicators.

### Scope

**In scope:**
- LightingMonitor
- CameraValidator warning surfacing in overlay
- Full Developer Mode debug panel
- ML fallback mode indicator in overlay

**Out of scope:**
- New pipeline stages

### Deliverables

1. `diagnostics/lighting_monitor.py` per TRD §3.12 (unchanged from prior implementation)
2. CameraValidator warning surfaced in overlay
3. `overlay/debug_panel.py` per TRD §11.3 (with ML model status line)
4. Fallback mode indicator in overlay (per FR-VF-08)

### Files

```
gestureos/
├── diagnostics/
│   └── lighting_monitor.py
├── overlay/
│   ├── debug_panel.py (with ML status)
│   └── overlay_window.py (extended with fallback indicator)
└── tests/
    ├── unit/
    │   └── test_lighting_monitor.py
    └── integration/
        └── test_ml_fallback_indicator.py
```

### Dependencies

CP-6 must be Done.

### Acceptance Criteria

- Lighting warning appears within 3s of dark room
- Developer Mode panel shows ML model status (LOADED / FALLBACK_ONLY)
- Fallback mode indicator appears in overlay when MediaPipe model is unavailable
- Developer Mode panel data matches actual gesture decisions

---

## 12. Checkpoint 8 — Testing, Optimization & Packaging

### Purpose

Execute the full test pyramid against the complete, feature-frozen system. Validate performance budgets. Package for Windows release.

### Scope

**In scope:**
- Coverage audit
- Performance testing (30-min and 4-hour sessions)
- Gesture accuracy testing (5 users, 3 distances, 3 lighting conditions)
- UAT scenarios
- PyInstaller packaging
- Windows installer

**Out of scope:**
- V2 features

### Deliverables

1. Coverage audit ≥ 80% across all module groups
2. `tests/performance/test_fps_and_memory.py` per TRD §15
3. 30-min and 4-hour continuous-session runs
4. Gesture accuracy testing per PRD §18.2
5. UAT per PRD §18.5
6. `pyinstaller.spec` finalized with MediaPipe model bundling verified
7. Windows installer (Inno Setup)
8. Release deliverables per PRD §21.3

### Files

```
gestureos/
├── tests/
│   └── performance/
│       └── test_fps_and_memory.py
├── installer/
│   └── windows/
│       └── installer.iss
└── docs/
    ├── user_guide.md
    ├── gesture_reference_card.md
    └── calibration_walkthrough.md
```

### Dependencies

CP-7 must be Done.

### Acceptance Criteria

- All 5 PRD §17 performance budgets met simultaneously on reference hardware
- Gesture accuracy ≥ 95% at all 3 distances
- 4-hour memory growth < 10MB/hour
- All 5 UAT scenarios pass
- Windows installer builds successfully
- Packaged artifact passes startup self-check
- No P0 bugs open

---

## 13. V2 Forward Reference

> V2 is explicitly out of scope for this implementation plan. The following components are documented as architectural placeholders only.

### V2 Component Targets

| Component | Description | V1 Status |
|---|---|---|
| DynamicGestureEngine | Lightweight temporal model on MediaPipe landmark sequences | Stub in `gestures/dynamic_gesture_engine.py` |
| GestureFuser (V2) | Full static + dynamic fusion | Currently pass-through |
| Hot-loadable plugins | Filesystem discovery, version negotiation, sandboxed loading | V1 has code-level ExtensionRegistry only |

### V2 Architecture Changes

V2 will add the Dynamic Gesture Engine as a parallel recognition path feeding into the Gesture Fuser. The current V1 pipeline becomes one of two input paths to the Fuser. All other components remain unchanged.

### V2 Documentation Requirements (When V2 Planning Begins)

- New Architecture Change Request
- Updated PRD with V2 sections
- Updated TRD with Dynamic Gesture Engine spec
- Updated Implementation Plan with V2 checkpoints
- Final V2 model selection (LSTM vs GRU vs 1D CNN) based on V2 benchmarking

---

## 14. Risk Management

| Risk | Severity | Probability | Mitigation | Checkpoint |
|---|---|---|---|---|
| MediaPipe model not bundled | High | Medium | Explicit PyInstaller datas; early smoke-build | CP-1 |
| MediaPipe inference exceeds per-frame budget | Medium-High | Medium | Alternating-frame strategy | CP-3 |
| Custom fallback accuracy gap | Medium | Medium | Scale-invariance testing; threshold tuning | CP-3 |
| Model load failure at startup | Medium | Low | ModelManager fallback to custom-only mode | CP-1, CP-3 |
| Cursor jitter | High | High (inherent) | EMA smoothing mandatory | CP-5 |
| Activation gate misconfiguration | High | Low | Default INACTIVE; explicit tests | CP-4 |
| PyInstaller + MediaPipe bundling | High | Medium | Known issue; explicit datas entry | CP-1, CP-8 |
| Custom fallback and MediaPipe produce conflicting results | Low | Medium | Fuser picks max confidence; both can fire for different gestures | CP-3 |
| V2 model selection uncertainty | Low | N/A (V2) | Three candidates documented; benchmarking during V2 | V2 |

---

## 15. Definition of Done

### 15.1 Checkpoint Definition of Done

A checkpoint is Done when:
1. All Deliverables exist in the specified locations
2. All Modules match TRD §3 specification
3. All Acceptance Criteria pass
4. Unit test coverage ≥ 80% for new/modified modules
5. No regressions in prior checkpoints' tests
6. No scope creep
7. Code review confirms architectural discipline
8. Any Gap encountered is documented

### 15.2 V1 Project Definition of Done

GestureOS V1 is Done when:
1. All 9 checkpoints (CP-0 through CP-8) are individually Done
2. Every PRD v2.0 functional and non-functional requirement is implemented
3. Every PRD v2.0 Success Metric is met on reference hardware
4. PRD v2.0 §21.4 Release Acceptance Gate is satisfied
5. ML model fallback path is tested and verified
6. No requirement, architecture decision, or feature from the PRD/TRD was altered

---

*End of GestureOS Implementation Plan v2.0*
