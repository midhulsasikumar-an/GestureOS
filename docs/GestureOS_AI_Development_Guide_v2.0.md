# AI Development Guide — GestureOS

**Document Type:** AI Development Guide (Engineering Constitution)
**Source Documents:** GestureOS PRD v2.0, GestureOS TRD v2.0, Implementation Plan v2.0
**Source of Truth:** Architecture Freeze Specification v1.0 (2026-07-04)
**Version:** 2.0.0
**Audience:** AI coding agents, human developers, code reviewers
**Date:** July 2026

> **Major Changes from v1.1:**
> - Architecture updated to match the frozen V1 design: MediaPipe Gesture Recognizer + custom geometric fallback, GestureGate (merged stability/cooldown), GestureFuser (V1 pass-through), CommandRouter (split from ActionEngine), ActionExecutor (absorbed CursorController), ModelManager (new), ExtensionRegistry (new), MotionHistoryService (elevated).
> - ML governance rules added: V1 permits only MediaPipe Gesture Recognizer; all model loading via ModelManager; graceful degradation required.
> - Extension System standards added: code-level ABC interfaces via ExtensionRegistry; no hot-loading in V1.
> - Component names throughout updated to match the frozen architecture.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Environment Setup](#2-environment-setup)
3. [Dependency Reference](#3-dependency-reference)
4. [Repository Structure](#4-repository-structure)
5. [Architecture Rules](#5-architecture-rules)
6. [Coding Standards](#6-coding-standards)
7. [Static Gesture Engine Standards](#7-static-gesture-engine-standards)
8. [ML Model Integration Standards](#8-ml-model-integration-standards)
9. [Extension System Standards](#9-extension-system-standards)
10. [Logging Standards](#10-logging-standards)
11. [Testing Standards](#11-testing-standards)
12. [Debugging Standards](#12-debugging-standards)
13. [AI Prompting Rules](#13-ai-prompting-rules)
14. [Code Review Standards](#14-code-review-standards)
15. [Security & Privacy Standards](#15-security-privacy-standards)
16. [Performance Standards](#16-performance-standards)
17. [Definition of Done](#17-definition-of-done)
18. [Maintenance Standards](#18-maintenance-standards)

---

## 1. Project Overview

### 1.1 What GestureOS Is

GestureOS is a Windows desktop application that acts as an intelligent gesture-based operating layer between the user and the operating system, enabling touchless computer control via webcam-based hand gesture recognition. It translates hand gestures captured by a standard webcam into OS-level actions through a modular AI-assisted pipeline.

**V1 Recognition:** Google's MediaPipe Gesture Recognizer handles 5 of 8 static gestures natively. The remaining 3 (Pinch, Three Fingers, OK Sign) are recognized by lightweight custom geometric fallback recognizers operating on the same MediaPipe landmarks. All processing is local, on-device, CPU-first.

**V2 Recognition (future):** A Dynamic Gesture Engine will be added, using a lightweight temporal model on MediaPipe landmark sequences (LSTM, GRU, or 1D CNN — final selection during V2 benchmarking).

### 1.2 Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Computer Vision | OpenCV |
| Hand Tracking | MediaPipe Hand Landmarker |
| Gesture Recognition (V1 primary) | MediaPipe Gesture Recognizer |
| Gesture Recognition (V1 fallback) | Custom geometric recognizers |
| Numerical Computing | NumPy |
| GUI Framework | PyQt6 |
| OS Automation | PyAutoGUI, pynput |
| Windows Context Detection | pywin32 |
| Testing | pytest |
| Packaging | PyInstaller |

### 1.3 Architectural Philosophy

1. **Local-only.** No network calls in the core pipeline. All ML inference on-device. All persistence is local JSON files.
2. **Modular.** Every pipeline stage is an independent component with a single responsibility. Code-level extension points via ExtensionRegistry.
3. **Fail-soft.** Any single-module failure degrades gracefully. ML model failure → custom-fallback mode. Camera glitch → auto-reconnect.
4. **ML governance.** Only the MediaPipe Gesture Recognizer is permitted in V1. All model lifecycle owned by ModelManager.
5. **Configuration over code.** Gesture-to-action behavior and all tunable parameters live in JSON, not in source.

---

## 2. Environment Setup

### 2.1 Python Version

**Python 3.11+** is required. Do not target earlier versions.

### 2.2 Virtual Environment

A virtual environment is mandatory for all development work.

```bash
python3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2.3 Dependency Installation

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 2.4 Requirements Management

- `requirements.txt` pins **exact versions** (`==`)
- Any change to `requirements.txt` is a deliberate, reviewed action
- A new dependency is only added if it is already named in TRD §1.2's technology stack, or if its addition is explicitly approved

### 2.5 MediaPipe Model Files

The MediaPipe Gesture Recognizer model file (`gesture_recognizer.task`) must be:
- Downloaded from Google's official MediaPipe model repository
- Placed in `gestureos/assets/models/`
- Verified present at application startup (ModelManager logs the verification)

If the model file is missing, ModelManager must report `is_gesture_model_available() == False` and engage fallback-only mode.

---

## 3. Dependency Reference

| Package | Version | Purpose |
|---|---|---|
| `opencv-python` | 4.8.x | Camera capture, preprocessing |
| `mediapipe` | 0.10.x | Hand Landmarker + Gesture Recognizer |
| `numpy` | 1.26.x | Vectorized geometry for custom fallback recognizers |
| `PyQt6` | 6.6.x | GUI, overlay, calibration wizard |
| `pyautogui` | 0.9.x | Cross-platform OS automation |
| `pynput` | 1.7.x | Low-latency mouse/keyboard dispatch |
| `pywin32` | 306 (Windows-only) | Windows active-window detection |
| `pytest` | 7.4.x | Test framework |
| `pyinstaller` | 6.x | Packaging into native Windows executable |

---

## 4. Repository Structure

```
gestureos/
├── main.py
├── app/
│   ├── core.py
│   └── capture_thread.py
├── camera/
│   ├── camera_module.py
│   └── errors.py
├── tracking/
│   ├── hand_landmarker.py
│   ├── hand_identity.py
│   ├── occlusion_handler.py
│   ├── hand_scale.py
│   ├── primary_hand_filter.py
│   └── errors.py
├── gestures/
│   ├── static_gesture_engine.py
│   ├── dynamic_gesture_engine.py     # V2 stub in V1
│   ├── motion_history_service.py
│   ├── gesture_gate.py
│   ├── gesture_fuser.py
│   ├── activation_gate.py
│   └── gesture_utils.py
├── context/
│   ├── context_engine.py
│   └── adapters/
│       ├── base.py
│       └── windows_adapter.py
├── actions/
│   ├── command_router.py
│   ├── action_executor.py
│   └── executors/
│       ├── base.py
│       └── windows_executor.py
├── models/
│   ├── data_models.py
│   └── model_manager.py
├── ext/
│   ├── base.py
│   └── registry.py
├── profiles/
│   └── profile_manager.py
├── calibration/
│   ├── calibration_manager.py
│   └── tracking_zone.py
├── overlay/
│   ├── overlay_window.py
│   ├── skeleton_renderer.py
│   └── debug_panel.py
├── settings/
│   └── settings_manager.py
├── diagnostics/
│   ├── diagnostics_manager.py
│   ├── log_format.py
│   ├── camera_validator.py
│   └── lighting_monitor.py
├── ui/
│   ├── main_window.py
│   ├── settings_panel.py
│   ├── mapping_editor.py
│   ├── profile_panel.py
│   ├── onboarding_wizard.py
│   ├── calibration_wizard.py
│   └── tray_icon.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── performance/
├── assets/
│   ├── icons/
│   ├── default_mappings/
│   ├── context_map.json
│   └── models/
│       └── gesture_recognizer.task
├── requirements.txt
├── pyinstaller.spec
└── pytest.ini
```

### 4.1 Folder-by-Folder Reference

#### `app/`
- **Purpose:** Top-level orchestration
- **Allowed:** `GestureOSApp` (orchestrator), `CaptureThread` (QThread)
- **Forbidden:** Any gesture-recognition logic, any direct landmark geometry math

#### `camera/`
- **Purpose:** Webcam access in isolation
- **Allowed:** `CameraModule`, camera-specific exceptions
- **Forbidden:** No PyQt6 imports. No MediaPipe imports.

#### `tracking/`
- **Purpose:** MediaPipe integration and hand analysis
- **Allowed:** `HandLandmarker`, `HandIdentityModule`, `OcclusionHandler`, `HandScaleEstimator`, `PrimaryHandFilter`
- **Forbidden:** No gesture-rule logic (except custom fallback recognizers in `gestures/`)

#### `gestures/`
- **Purpose:** All recognition logic
- **Allowed:** `StaticGestureEngine`, `DynamicGestureEngine` (V2 stub), `GestureGate`, `GestureFuser`, `ActivationGate`, `MotionHistoryService`, `GestureUtils`
- **Forbidden:** No camera access. No OS-automation imports.

#### `context/`
- **Purpose:** Active-window detection
- **Allowed:** `ContextEngine`, platform-specific `ContextAdapter` subclasses
- **Forbidden:** No gesture logic. No action-dispatch logic.

#### `actions/`
- **Purpose:** Command routing and OS dispatch
- **Allowed:** `CommandRouter`, `ActionExecutor` (with internal `CursorController` and `CommandDispatch`)
- **Forbidden:** No gesture-recognition logic. No camera/MediaPipe imports.

#### `models/`
- **Purpose:** Data models and ML model lifecycle
- **Allowed:** Dataclasses (`HandData`, `HandScale`, `GestureResult`, `Action`, etc.), `ModelManager`
- **Forbidden:** No other component may load ML models

#### `ext/`
- **Purpose:** Extension interfaces and registration
- **Allowed:** ABCs in `base.py`, `ExtensionRegistry` in `registry.py`
- **Forbidden:** No hot-loading code in V1

#### `profiles/`, `calibration/`, `overlay/`, `settings/`, `diagnostics/`, `ui/`, `tests/`, `assets/`
- Unchanged from prior structure (see TRD §9 for details)

---

## 5. Architecture Rules

These rules are derived directly from TRD §2 and TRD §3's Component Boundary Rule.

### 5.1 Separation of Concerns

Every component has exactly one job, matching its TRD §3 specification.

**Rule:** If you are writing code in `gestures/` and you find yourself calling `pyautogui` or `pynput` directly, stop. Recognition decides *what gesture occurred*; it never decides *what to do about it*.

### 5.2 Single Responsibility Principle

Each class matches one TRD §3 component entry.

- `HandLandmarker` extracts landmarks. It does not classify gestures.
- `ModelManager` loads and manages ML model handles. It does not perform recognition.
- `StaticGestureEngine` classifies gestures. It does not load models directly (it queries `ModelManager`).
- `GestureGate` filters candidates by stability and cooldown. It does not perform classification.
- `GestureFuser` fuses results from multiple engines. It does not perform classification.
- `CommandRouter` maps gestures to actions. It does not dispatch OS events.
- `ActionExecutor` dispatches OS events. It does not perform mapping.

### 5.3 Dependency Direction

Data flows in one direction through the pipeline:

```
Camera → HandLandmarker → Analysis → MotionHistoryService
  → StaticGestureEngine → GestureGate → GestureFuser
  → ActivationGate → CommandRouter → ActionExecutor
```

A component may only depend on (import from) components *earlier* in this chain, never later.

```
ALLOWED:    gestures/ imports from tracking/ and models/
FORBIDDEN:  tracking/ imports from gestures/
FORBIDDEN:  camera/ imports from anything except models/ and stdlib/third-party
FORBIDDEN:  gestures/static_gesture_engine.py imports from actions/
FORBIDDEN:  Any component imports mediapipe.tasks directly (use ModelManager)
```

### 5.4 Module Boundaries

A component's only "interface" to the rest of the system is the data object(s) it produces. A component must never reach into another component's internal state.

### 5.5 No Circular Imports

- `models/data_models.py` must never import from any other project module
- `ext/base.py` and `ext/registry.py` may be imported by any component (they define interfaces)
- `models/model_manager.py` may be imported by `gestures/` and `tracking/` (it provides model access)

### 5.6 State Management Rules

- **Pipeline state lives in `CaptureThread`-owned objects only**
- **The GUI thread never mutates pipeline state directly**
- **Cross-thread communication is exclusively via Qt signals**
- **No global mutable state**

### 5.7 ML Governance Rules

- Only the MediaPipe Gesture Recognizer and MediaPipe Hand Landmarker may be loaded in V1
- All ML model loading, caching, and unloading must go through `ModelManager`
- No component other than `ModelManager` may instantiate or hold references to ML model objects
- ML inference failures must not crash the pipeline; ModelManager tracks failures and triggers auto-reload

### 5.8 Extension System Rules

- All extension points in V1 are code-level interfaces (ABCs in `ext/base.py`)
- All built-in implementations must be registered via `ExtensionRegistry` at startup
- No hot-loading, no filesystem discovery, no dynamic plugin installation in V1
- Each extension implementation must fully implement its declared ABC

---

## 6. Coding Standards

### 6.1 Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Classes | `PascalCase` | `StaticGestureEngine`, `GestureGate` |
| Functions / methods | `snake_case` | `classify()`, `recognize_gesture()` |
| Variables | `snake_case` | `palm_width`, `hand_scale` |
| Constants | `UPPER_SNAKE_CASE` | `MIN_FPS`, `REID_WINDOW_S` |
| Gesture name strings | `snake_case` | `'open_palm'`, `'pinch'`, `'ok_sign'` |

### 6.2 Type Hints

Mandatory on every function signature. Python 3.11+ union syntax: `X | None`, `list[X]`.

### 6.3 Dataclasses

Every shared data object is a `@dataclass`. Use `dataclasses.replace()` for updates, never in-place mutation.

### 6.4 Error Handling

- **Hot-path components never raise.** `StaticGestureEngine.classify()`, `HandIdentityModule.assign_roles()`, etc. must catch internal errors and return safe defaults.
- **Cold-path components raise specific typed exceptions.**
- **ML inference exceptions are caught by ModelManager** and converted to `None` results; the Static Gesture Engine does not see raw MediaPipe exceptions.

### 6.5 Documentation

Every public class and public method has a docstring stating what it does and which PRD requirement it implements.

---

## 7. Static Gesture Engine Standards

### 7.1 Two-Stage Recognition

The Static Gesture Engine has two stages:

1. **MediaPipe query:** Always attempted first if the model is available
2. **Custom fallback:** Run for the 3 MediaPipe-uncovered gestures (Pinch, Three Fingers, OK Sign)

Both stages can emit candidates. The fuser/Gate handles multi-candidate scenarios.

### 7.2 Custom Fallback Recognizer Rules

Every custom fallback recognizer must:

1. **Use shared primitives** from `gesture_utils.py` (`euclidean_distance`, `finger_angle`, `finger_states`)
2. **Apply multi-signal discipline** (combine ≥2 independent geometric features per FR-MS-01)
3. **Be scale-invariant** (no raw pixel thresholds; normalize by `hand.scale.palm_width`)
4. **Handle missing scale** by returning `None` (FR-SC-04)
5. **Declare signals used** in the docstring (FR-MS-03)
6. **Return `None` (not `0.0`)** when the gesture does not match
7. **Never raise** — hot-path safety

### 7.3 Adding a New Custom Fallback Recognizer

```python
# 1. Add to gesture_utils.py if new primitives needed
# 2. Implement the recognizer function
def detect_new_gesture(hand: HandData) -> GestureResult | None:
    """Recognize the New Gesture.
    
    Implements PRD §5 fallback for [gesture not covered by MediaPipe].
    
    Signals used: [list signals — multi-signal per FR-MS-01].
    """
    if hand.scale is None:
        return None
    # ... recognition logic
    return GestureResult(
        gesture_name='new_gesture',
        confidence=...,
        is_dynamic=False,
        hand_role=hand.role,
        timestamp=time.time(),
        source='custom_fallback',  # important for diagnostics
    )

# 3. Register in StaticGestureEngine.__init__
self.fallback_recognizers = {
    'pinch': detect_pinch,
    'three_fingers': detect_three_fingers,
    'ok_sign': detect_ok_sign,
    'new_gesture': detect_new_gesture,  # add here
}
```

### 7.4 Testing Custom Fallback Recognizers

Every custom fallback recognizer requires:
- Positive test (gesture detected with high confidence)
- Negative test (gesture not detected in unrelated pose)
- Scale-invariance test (parametrized 0.5x, 1.0x, 2.0x, 3.0x)
- `hand.scale is None` test (returns `None`)

### 7.5 Do Not Implement Custom Fallbacks for MediaPipe-Covered Gestures

The 5 gestures covered by MediaPipe (Open Palm, Closed Fist, Thumbs Up, Thumbs Down, Peace Sign) do NOT have custom fallback implementations. They are recognized exclusively via the MediaPipe model. If the model is unavailable, these gestures are unavailable, and a user-visible warning is shown.

---

## 8. ML Model Integration Standards

### 8.1 Permitted Models (V1)

| Model | Purpose | Permission |
|---|---|---|
| MediaPipe Hand Landmarker | 21-landmark extraction | ✅ Approved |
| MediaPipe Gesture Recognizer | Static gesture classification | ✅ Approved |
| Any other model | — | ❌ Not approved in V1 |

### 8.2 Model Access Pattern

All ML model access goes through `ModelManager`. No component may:

- Import `mediapipe.tasks.python.vision.gesture_recognizer` directly
- Import `mediapipe.tasks.python.vision.hand_landmarker` directly
- Hold a reference to a model object outside of ModelManager
- Load or unload a model

```python
# CORRECT
class StaticGestureEngine:
    def __init__(self, model_manager: ModelManager, settings: Settings):
        self.model_manager = model_manager  # pass through
    
    def classify(self, hand: HandData) -> GestureResult | None:
        return self.model_manager.recognize_gesture(hand.landmarks)

# INCORRECT
import mediapipe as mp

class StaticGestureEngine:
    def __init__(self):
        self.model = mp.tasks.vision.GestureRecognizer.create_from_model_path(...)  # FORBIDDEN
```

### 8.3 Model Loading Failure Handling

If `ModelManager._load_gesture_model()` fails:
- `_gesture_model` remains `None`
- `is_gesture_model_available()` returns `False`
- `StaticGestureEngine` continues to operate with custom fallbacks only
- `DiagnosticsManager` logs the failure and the fallback mode engagement

### 8.4 Inference Failure Handling

If `ModelManager.recognize_gesture()` throws:
- The exception is caught internally
- `None` is returned to the caller
- `_consecutive_failures` is incremented
- After 3 consecutive failures, auto-reload is attempted
- If auto-reload fails, fallback mode is engaged

### 8.5 V2 Model Governance

V2 will introduce additional models. Permitted V2 candidates:
- LSTM on 63-dim landmark features
- GRU on 63-dim landmark features
- 1D CNN on landmark sequences

Explicitly NOT approved for V2:
- ViT on raw images
- Any CNN on raw pixel data

The same ModelManager governance applies to V2 models.

---

## 9. Extension System Standards

### 9.1 V1 Scope

V1 implements code-level extension only via Python ABCs in `ext/base.py`.

### 9.2 Adding a New Extension Point

1. Define the ABC in `ext/base.py` with `@abstractmethod` decorators
2. Update TRD §10 if it's a significant new extension surface
3. Update `ExtensionRegistry` documentation

### 9.3 Registering a Built-in Implementation

At application startup, all built-in implementations are registered:

```python
from ext.registry import ExtensionRegistry
from ext.base import GestureRecognizerBase, ActionExecutorBase, ContextAdapterBase

registry = ExtensionRegistry.get_instance()

# Register built-in implementations
registry.register('static_gesture_engine.mediapipe', MediaPipeGestureEngine(model_manager))
registry.register('static_gesture_engine.custom_fallback', CustomFallbackEngine())
registry.register('action_executor.windows', WindowsExecutor())
registry.register('context_adapter.windows', WindowsContextAdapter())
```

### 9.4 Querying the Registry

```python
mediapipe_engine = ExtensionRegistry.get_instance().get('static_gesture_engine.mediapipe')
```

### 9.5 Implementing a Custom Extension (V1)

A developer who wants to add a custom gesture recognizer:

1. Create a new file in `gestures/` (e.g., `gestures/my_custom_recognizer.py`)
2. Implement the `GestureRecognizerBase` ABC
3. Register it in `main.py` or wherever extensions are registered:

```python
from gestures.my_custom_recognizer import MyCustomRecognizer
ExtensionRegistry.get_instance().register('static_gesture_engine.my_custom', MyCustomRecognizer())
```

### 9.6 V2 Extension (Forward Reference)

V2 will add:
- Filesystem-based plugin discovery (`~/.gestureos/plugins/`)
- Versioned plugin manifests
- Sandboxed execution
- Public SDK for third-party plugins

---

## 10. Logging Standards

All component logging uses `DiagnosticsManager`'s structured helpers.

### 10.1 ML Event Categories (New in V2.0)

| Category | Required Events | Level |
|---|---|---|
| **ML Events** | Model loaded, load failed, inference timeout, auto-reload triggered, fallback mode engaged | INFO (loaded) / WARNING (fallback) / ERROR (load failed, persistent failures) |

### 10.2 Existing Categories (Retained)

| Category | Required Events | Level |
|---|---|---|
| **Camera Events** | Camera started, frame dropped, sustained low FPS | INFO / WARN / ERROR |
| **Tracking Events** | Hand detected/lost, occlusion bridged/expired, scale estimation skipped | DEBUG / WARN |
| **Gesture Events** | Candidate detected, stability check, cooldown check, gesture triggered | INFO / DEBUG |
| **Fuser Events** | Fused result, multi-candidate resolution | INFO / DEBUG |
| **Context Events** | Context resolved, verification pending/committed | INFO / WARN |
| **Activation Events** | State changed, method used | INFO |

### 10.3 Log Format

```
[TIMESTAMP] [LEVEL] [CATEGORY] Message  {key: value, ...}
```

### 10.4 Worked Examples

```
[12:31:42.103] [INFO]  [camera]     Camera started  {device: 0, resolution: '640x480', fps: 30}
[12:31:42.500] [INFO]  [ml]         Model loaded  {model: 'gesture_recognizer'}
[12:31:44.210] [INFO]  [gesture]    Gesture candidate  {gesture: 'open_palm', confidence: 0.91, source: 'mediapipe', hand: 'HAND_A'}
[12:31:44.211] [DEBUG] [gesture]    Stability check passed  {gesture: 'open_palm', held_ms: 210}
[12:31:44.213] [DEBUG] [gesture]    Cooldown check passed  {gesture: 'open_palm', hand: 'HAND_A'}
[12:31:44.214] [INFO]  [fuser]      Fused result  {gesture: 'open_palm', hand: 'HAND_A', candidates_in: 2}
[12:31:44.215] [INFO]  [action]     Action executed  {type: 'keyboard', params: 'space', status: 'success'}
[12:31:50.004] [WARN]  [ml]         Model load failed  {model: 'gesture_recognizer', error: 'file_not_found'}
[12:31:50.005] [WARN]  [ml]         Fallback mode engaged  {available_gestures: ['pinch', 'three_fingers', 'ok_sign']}
```

---

## 11. Testing Standards

### 11.1 Unit Testing

- No live camera or hardware required
- Tests mirror source layout
- Synthetic landmark data via fixtures
- **ML model tests must mock ModelManager** — never instantiate real MediaPipe models in tests

```python
# CORRECT: Mock ModelManager
def test_static_gesture_engine_uses_mediapipe(mock_model_manager):
    mock_model_manager.recognize_gesture.return_value = GestureResult(
        gesture_name='open_palm', confidence=0.91, is_dynamic=False,
        hand_role='HAND_A', timestamp=0.0, source='mediapipe'
    )
    engine = StaticGestureEngine(mock_model_manager, settings)
    hands = [make_hand(landmarks=open_palm_landmarks)]
    results = engine.classify(hands)
    assert any(r.gesture_name == 'open_palm' for r in results)

# CORRECT: Test fallback when model unavailable
def test_static_gesture_engine_fallback_when_model_unavailable(mock_model_manager):
    mock_model_manager.is_gesture_model_available.return_value = False
    mock_model_manager.recognize_gesture.return_value = None
    engine = StaticGestureEngine(mock_model_manager, settings)
    hands = [make_hand(landmarks=pinch_landmarks, scale=HandScale(...))]
    results = engine.classify(hands)
    assert any(r.gesture_name == 'pinch' and r.source == 'custom_fallback' for r in results)
```

### 11.2 Integration Testing

- Integration tests exercise a full vertical slice
- ML model integration tests use mocked ModelManager with controlled responses
- Real model integration is verified in manual testing, not CI

### 11.3 Coverage Targets

| Module Group | Target |
|---|---|
| `gestures/` | ≥ 80% |
| `actions/` | ≥ 80% |
| `models/` | ≥ 80% (including ModelManager) |
| `ext/` | ≥ 80% |
| `profiles/`, `settings/`, `tracking/` | ≥ 80% |

---

## 12. Debugging Standards

### 12.1 Bug Classification

| Priority | Definition | Examples |
|---|---|---|
| **P0** | Crashes, data corruption, action fires while INACTIVE | Capture thread crash, model corruption |
| **P1** | Core feature broken, but app stable | Specific gesture never triggers, fallback mode broken |
| **P2** | Feature works with degraded quality | Wrong confidence threshold, edge case mishandled |
| **P3** | Cosmetic / rare edge cases | Debug panel formatting |

**Special rule:** Any ML model failure that causes a system crash (rather than graceful degradation) is automatically P0, regardless of trigger frequency.

### 12.2 ML-Specific Debugging

When debugging ML-related issues:

1. Check `ModelManager.is_gesture_model_available()` first
2. Check `ModelManager._consecutive_failures` count
3. Verify the model file exists at the configured path
4. Check logs for `ml` category events
5. Test with `ModelManager` in mock mode (bypass real inference)

---

## 13. AI Prompting Rules

### 13.1 What the AI Must Always Do

1. **Respect architecture.** Before writing code, identify which TRD §3 component(s) the task touches.
2. **Respect folder boundaries.** Cross-check planned file location against Section 4.1.
3. **Route ML access through ModelManager.** Never import MediaPipe tasks modules directly outside of ModelManager.
4. **Register extensions.** Any new extension implementation must be registered via ExtensionRegistry.
5. **Add logging.** Any new event matching Section 10 categories gets a `DiagnosticsManager` call.
6. **Add tests.** Per Section 11.
7. **Cite source documents.** Any new function's docstring references the PRD requirement ID or TRD section.
8. **Handle ML failures gracefully.** If writing code that interacts with ModelManager, ensure the code path handles `is_gesture_model_available() == False` and `recognize_gesture() == None`.

### 13.2 What the AI Must Never Do

- Import MediaPipe tasks modules outside of `models/model_manager.py`
- Load ML models in any component other than `ModelManager`
- Add a new ML model to V1 (only MediaPipe Gesture Recognizer is permitted)
- Implement custom fallback recognizers for the 5 MediaPipe-covered gestures (Open Palm, Closed Fist, Thumbs Up, Thumbs Down, Peace Sign)
- Create `macos_executor.py`, `linux_executor.py`, `macos_adapter.py`, `linux_adapter.py` in V1
- Add hot-loadable plugin code in V1
- Mutate a `Settings` object in place from a non-owning thread
- Mark a task "done" without corresponding tests passing

### 13.3 Prompt Examples

#### Good Prompt

> "Implement the custom fallback recognizer for Three Fingers in `gestures/static_gesture_engine.py` per PRD §5. It should use `finger_states()` from `gesture_utils.py` to check that Index, Middle, and Ring are EXTENDED while Pinky and Thumb are CURLED. Add unit tests including scale-invariance parametrization and a test for the `hand.scale is None` case."

#### Bad Prompt

> "Add a new gesture for wiggling fingers."

A new gesture not in the PRD requires product sign-off (Section 7's framing rule), and dynamic gestures are V2 scope.

#### ML Integration Prompt

> "Add a test that verifies the Static Gesture Engine correctly handles the case when ModelManager reports the gesture model is unavailable. The test should mock ModelManager, configure it to return `is_gesture_model_available() == False`, and assert that the engine still returns Pinch results via the custom fallback path."

---

## 14. Code Review Standards

Every change passes this checklist before merge.

### 14.1 Architecture & Boundaries

- [ ] Change is scoped to the correct TRD §3 component(s)
- [ ] No file was created or edited outside its folder's Allowed Responsibilities
- [ ] No new import violates the dependency direction
- [ ] No component reaches into another component's private internals

### 14.2 ML Integration (V2.0 Specific)

- [ ] No component imports `mediapipe.tasks` directly (only `models/model_manager.py` does)
- [ ] No component holds a reference to an ML model object outside ModelManager
- [ ] All ML inference failures are caught and handled gracefully
- [ ] `is_gesture_model_available()` is checked before attempting inference
- [ ] No new ML model has been added (only MediaPipe Gesture Recognizer is permitted in V1)
- [ ] ML events are logged through `DiagnosticsManager` in the `ml` category

### 14.3 Custom Fallback Recognizer Checks

- [ ] No raw-pixel or raw-frame-normalized threshold exists
- [ ] `hand.scale is None` is handled by returning `None`
- [ ] Multi-signal discipline is followed (≥2 independent signals)
- [ ] Docstring declares the signals used
- [ ] Function returns `None` (not `0.0` confidence) when the gesture does not match
- [ ] No custom fallback for MediaPipe-covered gestures (Open Palm, Closed Fist, Thumbs Up, Thumbs Down, Peace Sign)

### 14.4 Extension System Checks

- [ ] All extension implementations are registered via `ExtensionRegistry`
- [ ] All extension implementations fully implement their declared ABC
- [ ] No hot-loading code introduced in V1

### 14.5 Coding Standards

- [ ] Naming matches Section 6.1 conventions
- [ ] Type hints present on every function signature
- [ ] Hot-path functions never raise; cold-path functions raise specific typed exceptions
- [ ] Every public class/method has a docstring citing the PRD requirement ID or TRD section

### 14.6 Logging

- [ ] ML events are logged through `DiagnosticsManager` in the `ml` category
- [ ] No bare `print()` or ad-hoc `logging.getLogger()` call
- [ ] Routine outcomes are not logged at WARN/ERROR

### 14.7 Testing

- [ ] New functions have unit tests
- [ ] New ML integration code has ModelManager-mocked tests
- [ ] Custom fallback recognizers have scale-invariance tests
- [ ] Coverage for touched modules remains ≥ 80%
- [ ] Full test suite passes

### 14.8 Platform Scope (V1 Windows-Only)

- [ ] No new code imports platform-specific macOS or Linux libraries
- [ ] No new executor or adapter subclass for macOS or Linux was created
- [ ] Windows-specific API calls are contained in `actions/executors/windows_executor.py` or `context/adapters/windows_adapter.py`

---

## 15. Security & Privacy Standards

### 15.1 Core Privacy Rules

1. **No frame, landmark, or gesture data is ever written to disk.** Frames exist only in memory for the duration of one pipeline pass.
2. **Log files never contain raw landmark coordinates or frame images**, even in `developer_mode`.
3. **No HTTP client library is imported anywhere in the core pipeline** (`camera/`, `tracking/`, `gestures/`, `context/`, `actions/`, `models/`).
4. **Webcam permission is requested via native OS dialogs only.**
5. **`~/.gestureos/` data is never encrypted at rest**, and this is intentional.

### 15.2 ML Model Privacy

1. **No ML model telemetry.** MediaPipe inference runs entirely on-device. No data is sent to Google or any third party.
2. **Model files are bundled with the application.** No runtime model downloads.
3. **No model fine-tuning or weight updates at runtime.** Models are static and versioned.

---

## 16. Performance Standards

### 16.1 Targets

| Metric | Target | Priority |
|---|---|---|
| FPS | ≥ 25 | Highest |
| Detection Latency | < 100 ms | High |
| End-to-End Action Latency | < 150 ms | High |
| CPU Usage | < 20% (single core average) | Lowest |
| Memory Usage | < 300 MB | Medium |

### 16.2 ML Inference Cost

MediaPipe Gesture Recognizer inference runs on the CaptureThread. Per-frame inference must not exceed the per-frame latency budget (TRD §15).

If profiling shows the budget is exceeded, an alternating-frame inference strategy (skip every other frame for recognizer while landmarker runs every frame) is the prescribed mitigation.

### 16.3 Performance Discipline for New Code

Any new per-frame pipeline stage must be evaluated for its marginal cost against these budgets.

---

## 17. Definition of Done

### 17.1 Feature Complete

An individual feature is complete when:
1. Its behavior matches its PRD requirement ID exactly
2. Its TRD-specified implementation is followed exactly
3. It has dedicated unit tests
4. It is exercised by an integration test where meaningful
5. It introduces no violation of this guide's Core Principles
6. It is logged per Section 10's requirements
7. Code review (Section 14) is complete

### 17.2 Module Complete

A module is complete when:
1. It is implemented exactly per its TRD §3 specification
2. Every method satisfies Feature Complete
3. Unit test coverage ≥ 80%
4. The module respects its folder's Allowed/Forbidden Responsibilities
5. The module's public interface is fully documented

### 17.3 Checkpoint Complete

A checkpoint is Done when:
1. All Deliverables exist
2. All Modules match their TRD §3 specification
3. All Acceptance Criteria pass
4. Unit test coverage meets or exceeds 80%
5. No regressions in prior checkpoints
6. No scope creep
7. Any Gap is documented

### 17.4 Project Complete

V1 is Done when:
1. All 9 checkpoints (CP-0 through CP-8) are individually Done
2. Every PRD v2.0 functional and non-functional requirement is implemented
3. Every PRD v2.0 Success Metric is met on reference hardware
4. ML model fallback path is tested and verified
5. No requirement, architecture decision, or feature was altered

---

## 18. Maintenance Standards

### 18.1 Versioning

- PRD/TRD/Implementation Plan/AI Dev Guide version bumps follow MAJOR.MINOR.PATCH
- Code commits reference the requirement/section they implement
- A code change that requires a documentation change must update the document in the same change set

### 18.2 Documentation Updates

This guide and the source documents are living documents:
- Any change to repository structure updates this guide's Section 4
- Any new logging category updates Section 10
- Any new ML governance rule updates Section 8
- Any new extension point updates Section 9

### 18.3 Refactoring Rules

- A refactor is behavior-preserving by definition
- A refactor's verification is: full existing test suite passes unchanged
- A refactor never crosses a folder boundary
- A refactor is performed in isolation from feature work or bug fixes

### 18.4 Deprecation Rules

- A deprecated gesture, setting, or component is never silently removed
- A deprecated item is marked, kept functional for at least one full checkpoint cycle
- Removing a deprecated gesture is a product decision (PRD scope change)

### 18.5 ML Model Updates

- An ML model version bump is a deliberate, reviewed action
- The bundled model file is updated in `assets/models/`
- The PyInstaller spec is verified to bundle the updated model
- ModelManager's load logic is tested with the new model file
- The model version is logged at INFO level on successful load

---

*End of GestureOS AI Development Guide v2.0*
