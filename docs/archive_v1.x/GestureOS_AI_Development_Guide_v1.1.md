# AI Development Guide — GestureOS

**Document Type:** AI Development Guide (Engineering Constitution)
**Source Documents:** GestureOS PRD v1.3, GestureOS TRD v1.2, GestureOS Implementation Plan v1.1
**Version:** 1.1.0
**Audience:** AI coding agents, human developers, code reviewers
**Date:** June 2026
**Changes in v1.1:** Windows-primary platform scope (§1.1, §3, §12.8); ConflictResolver added to SRP examples (§5.2), dependency direction (§5.3), module boundary example (§5.4), gestures/ folder Allowed list (§4.1); Multi-Signal Recognition discipline added as mandatory validation rule (§7.2), acceptance criterion (§7.4), step in §7.1, and code-review check (§12.2); worked example docstring updated with FR-MS-03 signals-used declaration (§7.5); Reference Hardware Baseline cited explicitly as PRD §16.1 (§14.3); new §12.8 Platform Scope review checklist section.

> **Purpose of This Document:** The PRD defines *what* to build. The TRD defines *how* it is architected. The Implementation Plan defines *when* and *in what order*. This guide defines the **rules of engagement** for every individual unit of work — every prompt, every pull request, every bug fix — so that after hundreds of AI-assisted coding sessions, the codebase still looks like it was written by one disciplined team, not patched together by hundreds of disconnected decisions. This guide does not introduce new features, alter architecture, or override anything in the three source documents. Where this guide is more specific than the source documents, it is filling in *engineering convention*, not product or architecture decisions — and is clearly marked as such.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Environment Setup](#2-environment-setup)
3. [Dependency Reference](#3-dependency-reference)
4. [Repository Structure](#4-repository-structure)
5. [Architecture Rules](#5-architecture-rules)
6. [Coding Standards](#6-coding-standards)
7. [Gesture Development Standards](#7-gesture-development-standards)
8. [Logging Standards](#8-logging-standards)
9. [Testing Standards](#9-testing-standards)
10. [Debugging Standards](#10-debugging-standards)
11. [AI Prompting Rules](#11-ai-prompting-rules)
12. [Code Review Standards](#12-code-review-standards)
13. [Security & Privacy Standards](#13-security--privacy-standards)
14. [Performance Standards](#14-performance-standards)
15. [Definition of Done](#15-definition-of-done)
16. [Maintenance Standards](#16-maintenance-standards)

---

## 1. Project Overview

### 1.1 What GestureOS Is

GestureOS is a desktop application that acts as an intelligent gesture-based operating layer between the user and the operating system, enabling touchless computer control via webcam-based hand gesture recognition (PRD §1–2). It translates hand gestures captured by a standard webcam into OS-level actions — cursor movement, clicks, keyboard shortcuts, scrolling, and system commands — through a pipeline that is entirely **rule-based geometric analysis**, not machine learning (PRD §4, TRD §1.1).

As of PRD v1.2, recognition is additionally **scale-invariant**: gesture accuracy does not degrade as the user's distance from the camera changes, because every distance and velocity measurement is normalized against a continuously-estimated hand-scale reference rather than compared to fixed pixel or frame-normalized thresholds (PRD §5–6, TRD §4).

As of PRD v1.3, the **primary release target is Windows 10/11**. macOS and Linux remain part of the long-term product roadmap but are deferred to a Future Expansion phase after the Windows release ships. The adapter-pattern architecture (TRD §11) remains in place for all platforms — only the initial build and validation scope has changed. GestureOS is also **not intended to fully replace mouse and keyboard usage** — it is designed for short to medium-duration interactions (presentations, media control, accessibility scenarios) rather than all-day continuous use (PRD §2.3.1).

### 1.2 Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Computer Vision | OpenCV |
| Hand Tracking | MediaPipe Hands |
| Numerical Computing | NumPy |
| GUI Framework | PyQt6 |
| OS Automation | PyAutoGUI, pynput |
| Windows Context Detection | pywin32 |
| Testing | pytest |
| Packaging | PyInstaller |

(Full version pins and per-package purpose: Section 3.)

### 1.3 Architectural Philosophy

These five principles, established in TRD §1.1, are non-negotiable and govern every line of code written for this project:

1. **Deterministic over probabilistic.** Every gesture decision must be traceable to an explicit geometric rule with named thresholds. No opaque models, no trained classifiers, no "it usually works" logic.
2. **Scale-invariant by construction.** Every distance or velocity measurement used in a gesture rule is normalized against a live hand-scale reference before comparison to any threshold. A raw-pixel or raw-frame-normalized comparison is a code-review-blocking defect, not a style preference (TRD §4.3).
3. **Local-only.** No network calls in the core pipeline. All persistence is local JSON files. This is enforced structurally, not just by policy (Section 13).
4. **Fail-soft.** Any single-module failure degrades gracefully and is logged or surfaced as a warning — it never crashes the main loop.
5. **Configuration over code.** Gesture-to-action behavior, and every tunable threshold, lives in JSON, not in source.

> **Why this matters for AI-assisted development specifically:** An AI coding agent operating across hundreds of prompts has no persistent memory of *why* a decision was made three sessions ago. These five principles are the load-bearing constraints that every future prompt — yours or another agent's — must check new code against. If a proposed change violates one of these five principles, it is wrong, regardless of how reasonable it looks in isolation.

---

## 2. Environment Setup

### 2.1 Python Version

**Python 3.11+** is required (TRD §1.3). Do not target, test against, or add compatibility shims for earlier versions. Earlier versions are not a supported environment for this project, full stop — there is no "best effort" support tier.

### 2.2 Virtual Environment

A virtual environment is mandatory for all development work — never install project dependencies into a system-wide Python installation.

```bash
# Create the virtual environment (once, per machine)
python3.11 -m venv .venv

# Activate it — every new terminal session, before any project command
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

An AI coding agent must verify the virtual environment is active (e.g., by checking `sys.prefix` or the `VIRTUAL_ENV` environment variable) before running any `pip install` command. Installing into the wrong environment is a common, easily-avoided source of "works on my machine" bugs.

### 2.3 Dependency Installation

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

On Windows, `pywin32` requires an additional post-install step that some environments need run explicitly:

```bash
python -m pywin32_postinstall -install
```

### 2.4 Requirements Management

- `requirements.txt` pins **exact versions** (`==`), not minimum versions (`>=`), per the Implementation Plan's Checkpoint 0 rationale: "Pin exact versions... before any OS-specific code exists, so every later checkpoint builds against an identical dependency set on all platforms."
- Any change to `requirements.txt` is a deliberate, reviewed action — never an incidental side effect of `pip install <package>` without updating the pinned file to match.
- A new dependency is only added if it is already named in TRD §1.3's technology stack, or if its addition is explicitly approved as part of a documented architecture change (Section 16.3 — Refactoring Rules). An AI agent must not silently introduce a new third-party package to solve a problem that the existing stack already has a documented way to solve.

### 2.5 Development Setup Checklist

Before writing any code in a fresh checkout:

1. Virtual environment created and activated (2.2)
2. `pip install -r requirements.txt` completed without errors (2.3)
3. `pytest` runs (even against an empty or near-empty test suite) without collection errors
4. `python main.py` launches without import errors (or fails with a clear, expected error if the checkpoint you're working in hasn't reached that point of integration yet — see Implementation Plan §2 for what should exist at each checkpoint)
5. A camera device is available for any work touching `camera/` or `tracking/` — unit tests must never require this (Section 9.1), but manual verification during development does

---

## 3. Dependency Reference

| Package | Version | Purpose |
|---|---|---|
| `opencv-python` | 4.8.x | Camera capture (`CameraModule`), frame preprocessing, brightness analysis for `LightingMonitor` (TRD §3.1, §3.4) |
| `mediapipe` | 0.10.x | 21-landmark hand detection (`TrackingModule`) — the sole source of raw landmark data for the entire recognition pipeline (TRD §3.3) |
| `numpy` | 1.26.x | Vectorized geometry math for gesture rules, scale normalization (TRD §1.3, §4) |
| `PyQt6` | 6.6.x | GUI framework: main window, settings, overlay, calibration wizard, system tray (TRD §1.3, §8 `ui/` and `overlay/`) |
| `pyautogui` | 0.9.x | Cross-platform OS automation: screenshot, simple dispatch fallback (TRD §11.3) |
| `pynput` | 1.7.x | Low-latency mouse/keyboard dispatch — the primary path for cursor movement and clicks (TRD §3.14, §11.3) |
| `pywin32` | 306 (Windows-only) | Windows active-window detection for `WindowsContextAdapter` (TRD §11.2). **Primary release target is Windows (PRD §1.2) — this is the only ContextAdapter implementation built for the initial release.** |
| `pytest` | 7.4.x | Test framework — unit, integration, and performance test suites (TRD §13) |
| `pyinstaller` | 6.x | Packaging into a native Windows executable for the initial release (TRD §12). macOS/Linux packaging is deferred to Future Expansion (PRD §1.2). |

> **Platform-conditional installs:** `pywin32` is Windows-only and must be installed conditionally (`pywin32; sys_platform == 'win32'` in `requirements.txt`). Equivalent platform-specific packages for macOS (`pyobjc`) and Linux (`python-xlib`) are architecturally specified in TRD §11.2 for Future Expansion (PRD §1.2) but are **not installed or activated for the initial Windows release** — do not add their `requirements.txt` entries until the Future Expansion packaging checkpoint begins. Adding them prematurely introduces untested import paths into the CI environment.

> **Version-pin discipline:** If a dependency needs to be upgraded (e.g., a MediaPipe security patch), this is a deliberate action: update the pin in `requirements.txt`, re-run the full test suite (Section 9), and re-run the Checkpoint 1 PyInstaller smoke-build (Implementation Plan §5, Risks row 2) specifically because MediaPipe version changes have historically been the most likely source of packaging breakage (TRD §16).

---

## 4. Repository Structure

The complete structure below is reproduced exactly from TRD §8, the single source of truth for file layout. **No AI coding session may create a file or folder outside this structure without first updating this guide and the TRD together** — an undocumented folder is itself an architecture violation, not a convenience.

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
│   ├── hand_detector.py
│   ├── hand_identity.py
│   ├── occlusion_handler.py
│   ├── hand_scale.py
│   ├── primary_hand_filter.py
│   └── errors.py
├── gestures/
│   ├── static_recognizer.py
│   ├── dynamic_recognizer.py
│   ├── motion_history.py
│   ├── gesture_engine.py
│   ├── stability_filter.py
│   ├── cooldown_filter.py
│   ├── activation_gate.py
│   └── gesture_utils.py
├── context/
│   ├── context_engine.py
│   └── adapters/
│       ├── base.py
│       ├── windows_adapter.py
│       ├── macos_adapter.py
│       └── linux_adapter.py
├── actions/
│   ├── action_engine.py
│   ├── cursor_controller.py
│   └── executors/
│       ├── base.py
│       ├── windows_executor.py
│       ├── macos_executor.py
│       └── linux_executor.py
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
├── models/
│   └── data_models.py
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
│   └── context_map.json
├── requirements.txt
├── pyinstaller.spec
└── pytest.ini
```

### 4.1 Folder-by-Folder Reference

For each folder: Purpose, Allowed Responsibilities, Forbidden Responsibilities, Example Files. This expands TRD §8.1's responsibility table with the explicit "forbidden" framing AI agents need to self-check against before writing code.

#### `app/`
- **Purpose:** Top-level orchestration. Owns the thread that runs the per-frame pipeline and wires every component together.
- **Allowed:** `GestureOSApp` (the orchestrator class), `CaptureThread` (the `QThread` subclass running the frame loop).
- **Forbidden:** Any gesture-recognition logic, any direct landmark geometry math, any OS-dispatch logic. If you find yourself writing an `if gesture_name == 'pinch':` branch in `app/`, that logic belongs in `gestures/` or `actions/`.
- **Example Files:** `core.py`, `capture_thread.py`

#### `camera/`
- **Purpose:** Webcam access in isolation.
- **Allowed:** `CameraModule`, camera-specific exceptions.
- **Forbidden:** No PyQt6 imports. No MediaPipe imports. No knowledge of gestures, actions, or UI.
- **Example Files:** `camera_module.py`, `errors.py`

#### `tracking/`
- **Purpose:** MediaPipe integration and hand identity persistence — turning raw frames into analyzed `HandData`.
- **Allowed:** `TrackingModule`, `HandIdentityModule`, `OcclusionHandler`, `HandScaleEstimator`, `PrimaryHandFilter`.
- **Forbidden:** No gesture-rule logic (no `detect_open_palm`-style functions belong here — that's `gestures/`). No OS-dispatch logic.
- **Example Files:** `hand_detector.py`, `hand_identity.py`, `occlusion_handler.py`, `hand_scale.py`, `primary_hand_filter.py`

#### `gestures/`
- **Purpose:** All recognition logic — the rule-based engine.
- **Allowed:** Pure functions implementing gesture rules, plus `GestureEngine`/`ConflictResolver`/`ActivationGate`/`StabilityFilter`/`CooldownFilter` classes.
- **Forbidden:** No camera access. No OS-automation imports (`pyautogui`, `pynput` must never appear in this folder). No PyQt6 imports.
- **Example Files:** `static_recognizer.py`, `dynamic_recognizer.py`, `motion_history.py`, `gesture_engine.py`, `conflict_resolver.py`, `stability_filter.py`, `cooldown_filter.py`, `activation_gate.py`, `gesture_utils.py`

#### `context/`
- **Purpose:** Active-window detection, OS-specific via the adapter pattern.
- **Allowed:** `ContextEngine` plus one `ContextAdapter` subclass per OS under `adapters/`.
- **Forbidden:** No gesture logic. No action-dispatch logic. Platform-specific code must live only inside its named adapter file — never branch on `platform.system()` inside `context_engine.py` itself.
- **Example Files:** `context_engine.py`, `adapters/windows_adapter.py`, `adapters/macos_adapter.py`, `adapters/linux_adapter.py`

#### `actions/`
- **Purpose:** Mapping resolution and OS command dispatch.
- **Allowed:** `ActionEngine`, `CursorController`, plus one `CommandExecutor` subclass per OS under `executors/`.
- **Forbidden:** No gesture-recognition logic. No camera or MediaPipe imports. Platform-specific dispatch code lives only in its named executor file.
- **Example Files:** `action_engine.py`, `cursor_controller.py`, `executors/windows_executor.py`

#### `profiles/`
- **Purpose:** Profile and mapping-file persistence.
- **Allowed:** `ProfileManager` only — reads/writes JSON.
- **Forbidden:** No interpretation of *what a mapping means* (that's `ActionEngine`'s job at resolution time) — `ProfileManager` treats mappings as opaque data it loads, validates structurally, and hands off.
- **Example Files:** `profile_manager.py`

#### `calibration/`
- **Purpose:** Calibration wizard's business logic (distinct from its UI).
- **Allowed:** `CalibrationManager`, `TrackingZone`.
- **Forbidden:** No PyQt6 widget code (that's `ui/calibration_wizard.py`). Does not write JSON directly — persists via `SettingsManager`.
- **Example Files:** `calibration_manager.py`, `tracking_zone.py`

#### `overlay/`
- **Purpose:** Always-on-top visual feedback window.
- **Allowed:** PyQt6 widgets only, read-only consumers of signals emitted from `app/`.
- **Forbidden:** No business logic — the overlay draws what it's told, it never decides what a gesture means or whether an action should fire.
- **Example Files:** `overlay_window.py`, `skeleton_renderer.py`, `debug_panel.py`

#### `settings/`
- **Purpose:** Typed settings persistence.
- **Allowed:** `SettingsManager`, the `Settings` dataclass.
- **Forbidden:** No knowledge of *what* a setting controls behaviorally — `SettingsManager` validates types and ranges, it does not implement the behavior those settings configure.
- **Example Files:** `settings_manager.py`

#### `diagnostics/`
- **Purpose:** Logging and the data feed for the debug overlay, plus camera/lighting quality monitoring.
- **Allowed:** `DiagnosticsManager`, log-formatting helpers, `CameraValidator`, `LightingMonitor`.
- **Forbidden:** No UI imports. No gesture-recognition logic — these components observe and report, they do not decide.
- **Example Files:** `diagnostics_manager.py`, `log_format.py`, `camera_validator.py`, `lighting_monitor.py`

#### `models/`
- **Purpose:** Shared data objects used across every component boundary.
- **Allowed:** Dataclass definitions only — `HandData`, `HandScale`, `GestureResult`, `Action`, `ActionResult`, `Profile`, `CameraQuality`, `LightingQuality`.
- **Forbidden:** Zero business logic. A dataclass method that does real computation (not a simple derived-property accessor) is a sign the logic belongs in the component that produces or consumes that object, not in `models/`.
- **Example Files:** `data_models.py`

#### `ui/`
- **Purpose:** Normal (non-overlay) application windows: settings, profiles, tray, wizards.
- **Allowed:** PyQt6 widgets. May import any other component **read-only** to display its state.
- **Forbidden:** No UI component may hold a direct reference to a `CaptureThread`-owned object — all cross-thread communication is via Qt signals (TRD §2.2; Implementation Plan §11, Definition of Done item 3).
- **Example Files:** `main_window.py`, `settings_panel.py`, `mapping_editor.py`, `calibration_wizard.py`, `tray_icon.py`

#### `tests/`
- **Purpose:** All automated tests, mirroring the source layout under `unit/`/`integration/`/`performance/`.
- **Allowed:** pytest files and fixtures only.
- **Forbidden:** No production code. A helper function used only by tests belongs in `tests/conftest.py` or a `tests/fixtures/` module, never copy-pasted into a production file "just for testing convenience."
- **Example Files:** `conftest.py`, `unit/test_static_gestures.py`, `integration/test_pipeline_end_to_end.py`, `performance/test_fps_and_memory.py`

#### `assets/`
- **Purpose:** Static resources copied to `~/.gestureos/` on first launch.
- **Allowed:** Icons, default mapping JSON files, `context_map.json`.
- **Forbidden:** No Python code.
- **Example Files:** `default_mappings/productivity.json`, `context_map.json`, `icons/app_icon.ico`
## 5. Architecture Rules

These rules are derived directly from TRD §2 (System Architecture) and TRD §3's Component Boundary Rule. They are not suggestions — a pull request or AI-generated change that violates any rule in this section should be rejected in review (Section 12), regardless of whether the code "works."

### 5.1 Separation of Concerns

Every component has exactly one job, matching its TRD §3 specification's Responsibilities field. The eight pipeline domains — Camera, Tracking, Analysis (hand identity/scale/occlusion/primary-hand), Recognition, Activation, Actions, Context, GUI — are kept strictly separate (Implementation Plan §2.2's Foundation-First rationale exists *because* of this separation).

**Rule:** If you are writing code in `gestures/` and you find yourself calling `pyautogui` or `pynput` directly, stop. Gesture recognition decides *what gesture occurred*; it never decides *what to do about it*. That is `actions/`'s job, mediated by `ActionEngine`.

### 5.2 Single Responsibility Principle

Each class matches one TRD §3 component entry. Do not add a second responsibility to an existing class because it's "related" or "convenient." For example:

- `CameraValidator` measures FPS/resolution quality. It does not also manage camera reconnection — that's `CameraModule`'s job (TRD §3.1 vs §3.2 are deliberately separate classes despite both being "camera-adjacent").
- **`CameraModule`** validates camera hardware and **`CameraValidator`** monitors running performance (TRD §3.1 vs §3.2) are deliberately separate classes despite both being "camera-adjacent", because they answer different questions at different moments in the pipeline lifecycle.
- **`StabilityFilter`** and **`CooldownFilter`** are separate classes (TRD §3.10, §3.11) even though both are timer-based gates sitting in sequence in the pipeline, because they answer different questions ("has this gesture been held long enough?" vs. "has enough time passed since this gesture last fired?") and are independently configurable, independently testable, and independently disabled-for-dynamic-gestures (stability) vs. always-active (cooldown).
- **`GestureEngine`** and **`ConflictResolver`** are separate classes (TRD §3.9, §3.9.1) even though they are sequentially adjacent, because they do distinct things: `GestureEngine` generates *all* qualifying candidates per hand per frame; `ConflictResolver` selects *one winner* per hand when multiple candidates exist (PRD §4.6). Combining them would make it impossible to unit-test candidate generation and conflict resolution independently, and would re-introduce the original "first-match-wins" implicit ordering that PRD §4.6 explicitly replaced with documented, auditable confidence-based selection.

### 5.3 Dependency Direction

Data flows in one direction through the pipeline (TRD §2.1, §5.1): Camera → Tracking → Analysis → Recognition → **Conflict Resolution** → Activation → Context → Actions → Diagnostics/Overlay. A component may only depend on (import from) components *earlier* in this chain, never later.

```
ALLOWED:    gestures/ imports from tracking/ and models/
FORBIDDEN:  tracking/ imports from gestures/
FORBIDDEN:  camera/ imports from anything except models/ and stdlib/third-party
FORBIDDEN:  gestures/conflict_resolver.py imports from actions/ or context/
```

The only exceptions, explicitly carved out by TRD §3's Component Boundary Rule:
- `overlay/` and `ui/` may depend on everything else, **read-only**, since they exist to visualize/configure state, not produce it.
- Every component may depend on `models/` (the shared data objects) and `settings/`/`diagnostics/` (the cross-cutting concerns, Implementation Plan §2.4).

### 5.4 Module Boundaries

A component's only "interface" to the rest of the system is the data object(s) it produces, as documented in its TRD §3 entry's Outputs field. A component must never reach into another component's internal state — e.g., `ActionEngine` must never inspect `GestureEngine`'s internal trajectory buffer directly; it only ever receives a finished, conflict-resolved `GestureResult` object that has already passed through `ConflictResolver`, `StabilityFilter`, and `CooldownFilter`.

**Rule:** If implementing a feature requires reaching past a component's public method/dataclass interface into its private internals, the feature is mis-scoped — either the public interface needs a deliberate, reviewed extension (update the TRD), or the feature belongs in a different component.

### 5.5 No Circular Imports

The dependency direction in 5.3 already prevents circular imports by construction, *if followed*. Concretely:

- `models/data_models.py` must never import from any other project module — it is the leaf of the dependency graph that everything else points to.
- `settings/settings_manager.py` and `diagnostics/diagnostics_manager.py` must never import from `gestures/`, `actions/`, `context/`, `tracking/`, or `camera/` — those components import *them*, never the reverse.
- If you encounter a situation that seems to require a circular import (Component A needs something from B, and B needs something from A), this is a signal that a piece of shared logic needs to be extracted into `models/` or a new shared utility module — not a signal to add a deferred/local import to work around the cycle.

### 5.6 State Management Rules

- **Pipeline state lives in `CaptureThread`-owned objects only**, per TRD §2.2's threading model. `GestureEngine`'s trajectory buffers, `HandIdentityModule`'s `last_seen` dict, `ActivationGate`'s current state — all of this lives on objects owned and mutated exclusively by the capture thread.
- **The GUI thread never mutates pipeline state directly.** Settings changes from the UI go through `SettingsManager.update()`, which performs an atomic object-swap (TRD §16 Technical Risk row 5: "Settings updates are applied via an atomic object-swap... rather than in-place field mutation, which is safe under Python's GIL without explicit locks"). An AI agent adding a new settings field must follow this same atomic-swap pattern, never partial in-place mutation of a live `Settings` object that the capture thread might be reading mid-mutation.
- **Cross-thread communication is exclusively via Qt signals** (TRD §2.2). A `CaptureThread` method must never call a `QWidget` method directly, and a `QWidget`'s slot must never call into `GestureEngine`/`TrackingModule`/etc. directly — it reads pre-packaged data objects delivered via signal.
- **No global mutable state.** Every stateful object is owned by exactly one parent (typically `GestureOSApp` in `app/core.py`) and passed explicitly to the methods that need it. Module-level mutable globals (e.g., a bare dict at the top of a file used as ad-hoc shared state) are forbidden — they are untestable, untraceable, and the first thing that breaks under hundreds of incremental AI-driven changes.
## 6. Coding Standards

### 6.1 Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Classes | `PascalCase` | `HandScaleEstimator`, `CooldownFilter` |
| Functions / methods | `snake_case` | `detect_open_palm()`, `finger_angle()` |
| Variables | `snake_case` | `palm_width`, `hand_scale` |
| Constants | `UPPER_SNAKE_CASE` | `MIN_FPS`, `REID_WINDOW_S` |
| Private/internal methods | leading underscore | `_check_static()`, `_ema()` |
| Module-level files | `snake_case.py` matching the primary class they contain | `hand_scale.py` contains `HandScaleEstimator` |
| Gesture name strings | `snake_case`, matching the PRD's gesture identifiers exactly | `'open_palm'`, `'swipe_right'`, `'ok_sign'` — never `'OpenPalm'` or `'open-palm'` |
| Boolean variables/flags | `is_`/`has_`/verb-phrase prefix | `is_dynamic`, `gesture_eligible`, `fps_ok` |

**Gesture name strings are a contract, not a convenience.** They appear in `mappings/*.json`, in `GestureResult.gesture_name`, in log lines, and in test fixtures. A typo or casing inconsistency between these locations silently breaks gesture mapping resolution with no exception raised (TRD §3.13: "no mapping found... not logged as a warning unless `developer_mode`"). When adding or referencing a gesture name, copy it from the PRD's gesture table (PRD §4.3/§4.4) exactly — never paraphrase it.

### 6.2 Type Hints

Type hints are mandatory on every function signature and dataclass field — not optional, not "for the important stuff only." This codebase uses Python 3.11+'s union syntax (`X | None`, not `Optional[X]`) and built-in generics (`list[X]`, not `List[X]`) consistently, matching every code example throughout the TRD.

```python
# CORRECT — matches TRD conventions exactly
def detect_pinch(hand: HandData) -> GestureResult | None:
    ...

def assign_roles(self, hands: list[HandData], now: float) -> list[HandData]:
    ...

# WRONG — do not use typing.Optional/typing.List even though they still work
from typing import Optional, List
def detect_pinch(hand: HandData) -> Optional[GestureResult]:
    ...
```

### 6.3 Dataclasses

Every shared data object is a `@dataclass`, per TRD §6's exact pattern. Follow this structure precisely:

```python
@dataclass
class HandScale:
    palm_width: float
    palm_height: float
    bounding_box: tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
    smoothed_scale: float

@dataclass
class HandData:
    landmarks: list[tuple[float, float, float]]   # 21 (x, y, z), normalized
    chirality: str                                  # 'Left' | 'Right'
    confidence: float
    role: str | None = None                         # 'HAND_A' | 'HAND_B'
    scale: HandScale | None = None
    gesture_eligible: bool = True
    is_retained: bool = False
```

Rules:
- Required fields (no default) come before fields with defaults, standard Python dataclass ordering.
- A comment documenting the valid value set is required for any field with a constrained string domain (e.g., `# 'Left' | 'Right'`), since Python's type system can't express this directly without introducing an `Enum` — and TRD §6 deliberately uses plain `str` with a documenting comment for these fields, so new dataclasses should match that established pattern rather than introducing `Enum` inconsistently.
- Dataclasses are modified via `dataclasses.replace()`, never in-place mutation, when a component needs to "update" one (see the `HandScaleEstimator.estimate()` pattern in TRD §3.7: `return replace(hand, scale=HandScale(...))`). This keeps the State Management Rules (5.6) — no component accidentally mutates a `HandData` object another component is still holding a reference to.
- A dataclass in `models/` contains **zero business logic** beyond simple derived-property accessors (Section 4.1, `models/` Forbidden Responsibilities).

### 6.4 Error Handling

Every component's error-handling behavior must match its TRD §3 specification's Error Handling field exactly — this is not an area where an AI agent should improvise based on what "seems reasonable."

**The two governing patterns, used consistently throughout the TRD:**

1. **Hot-path components never raise.** `GestureEngine.evaluate()`, `HandIdentityModule.assign_roles()`, and every other function called every single frame must catch their own internal errors, log appropriately, and return a safe default (`None`, an empty list, or an unchanged input) rather than propagate an exception up into the capture loop. TRD §3.9 states this explicitly: "must never raise — this is the hottest path in the pipeline."
2. **Cold-path components (startup, file I/O) raise typed, specific exceptions** that calling code catches deliberately. `CameraModule.open()` raises `CameraUnavailableError`, not a bare `Exception` or an unhandled `cv2` exception — this lets `app/core.py` catch the specific failure and respond correctly (TRD §3.1).

```python
# CORRECT — hot path, never raises, degrades to a safe value
def detect_pinch(hand: HandData) -> GestureResult | None:
    if hand.scale is None:
        return None  # PRD FR-SC-04: skip evaluation, don't guess
    raw_dist = euclidean_distance(hand.landmarks[4], hand.landmarks[8])
    normalized_dist = raw_dist / hand.scale.palm_width
    if normalized_dist >= 0.35:
        return None
    ...

# CORRECT — cold path, raises a specific typed exception
def open(self) -> bool:
    self.cap = cv2.VideoCapture(self.device_index)
    if not self.cap.isOpened():
        raise CameraUnavailableError(self.device_index)
    ...

# WRONG — swallowing an exception silently in a cold-path component
def open(self) -> bool:
    try:
        self.cap = cv2.VideoCapture(self.device_index)
    except Exception:
        pass  # NEVER do this — the caller has no idea the camera failed to open
    return True
```

**Never use a bare `except:` or `except Exception:` without either re-raising, logging, or explicitly documenting why total suppression is correct for that specific call site** (e.g., `DiagnosticsManager`'s own logging calls are deliberately wrapped to never raise into calling code, per TRD §3.16 — that is a documented, intentional exception, not a default pattern to copy elsewhere).

### 6.5 Logging

See Section 8 for the full logging standard. The coding-standard-level rule: **every component logs through `DiagnosticsManager`'s structured helper methods, never through a bare `print()` or an ad-hoc `logging.getLogger(__name__)` call configured independently.** This keeps the log format (TRD §9.1) and category taxonomy (TRD §9.2) consistent across the entire codebase.

### 6.6 Documentation

Every public class and public method has a docstring stating: what it does, and — for anything implementing a specific PRD requirement — which requirement ID it implements. This is not boilerplate; it is the traceability mechanism that lets a future AI session (or human) verify a change against the PRD without re-reading the entire document.

```python
class StabilityFilter:
    """Requires a static gesture to remain the highest-confidence match for
    a continuous hold window before accepting it as valid.

    Implements PRD FR-GS-01 through FR-GS-04 (Gesture Stability Requirement).
    Dynamic gestures are exempt per FR-GS-04 and pass through unchanged.
    """
```

### 6.7 Commenting Standards

- Comments explain **why**, not **what** — the code already says what it does; a comment earns its place by explaining a non-obvious reason.
- Any threshold, magic number, or tuned constant requires a comment citing its source (a PRD section, or "tuned empirically, see Checkpoint 9 accuracy testing").
- Implementation notes that explain a deliberate, non-obvious design decision (the kind the TRD calls out explicitly, e.g., "normalization happens at read-time, not write-time... because hand_scale itself is a per-frame smoothed value") must be preserved verbatim or near-verbatim when code is refactored — losing this context is how a future change accidentally reintroduces a bug that was already solved once.

```python
def update(self, role: str, wrist_pos: tuple, now: float):
    # Store RAW (unnormalized) position + timestamp. Normalization by
    # hand_scale happens at evaluation time, not at storage time -- this
    # matters because hand_scale is itself a per-frame smoothed value, and
    # storing pre-normalized data would "bake in" whatever scale was current
    # at storage time, corrupting comparisons if scale drifts mid-buffer.
    # (PRD FR-MH-03)
    self.buffers[role].append((wrist_pos[0], wrist_pos[1], now * 1000))
```

### 6.8 Full Worked Example

A complete, standards-compliant new function, as a single reference example tying together 6.1–6.7:

```python
def detect_three_fingers(hand: HandData) -> GestureResult | None:
    """Recognize the Three Fingers static gesture: index, middle, and ring
    extended; pinky and thumb curled.

    Implements PRD §4.3 (Three Fingers gesture rule).

    Returns None if the hand's scale has not been estimated yet (PRD
    FR-SC-04), or if the finger-state pattern does not match.
    """
    if hand.scale is None:
        return None  # cannot safely evaluate without a scale reference

    states = finger_states(hand.landmarks)
    thumb_open = is_thumb_extended(hand.landmarks, hand.chirality)

    matches = (
        states['index'] and states['middle'] and states['ring']
        and not states['pinky'] and not thumb_open
    )
    if not matches:
        return None

    return GestureResult(
        gesture_name='three_fingers',
        confidence=0.9,  # boolean-rule match; see Section 7.2 for confidence guidance
        is_dynamic=False,
        hand_role=hand.role,
        timestamp=time.time(),
    )
```
## 7. Gesture Development Standards

This section governs adding a **new** gesture, or modifying an **existing** one. It exists because gestures are the highest-risk surface for architecture drift — they are the most frequently touched code, the most tempting place to take a "quick" shortcut, and the exact place where the scale-invariance discipline (Section 1.3, Principle 2) is most likely to be silently violated under time pressure.

> **Before adding any gesture: check whether it is already defined in the PRD.** PRD §4.3/§4.4 define the complete, closed set of 14 gestures (8 static, 6 dynamic) for this product. A request to "add a new gesture" that is not already named in the PRD is a **product decision**, not an implementation task — per this guide's governing rule ("Do not invent features"), an AI agent must flag this as a PRD gap requiring product-owner sign-off, not silently implement it. This section's standards apply to implementing or modifying gestures that **are** already PRD-defined.

### 7.1 Required Steps

For any gesture (new or modified), in this exact order:

1. **Locate the gesture's PRD definition.** PRD §4.3 (static) or §4.4 (dynamic) gives the rule summary and default action. Implementation Plan §7.1/§7.2 gives the full Purpose/Recognition Logic/Dependencies/Failure Cases/Testing Strategy breakdown — read the corresponding entry before writing any code.
2. **Identify which priority tier of signal the rule uses**, per PRD §5.1's mandatory priority order:
   - Priority 1: Finger State Logic (boolean EXTENDED/CURLED)
   - Priority 2: Finger & Joint Angles
   - Priority 3: Normalized Distances (always `raw_distance / hand_scale`, never raw)
   - Priority 4: Motion Trajectories (always normalized by hand scale, TRD §4.4)

   Prefer the lowest-numbered (simplest, most scale-robust) priority tier that is sufficient to distinguish the gesture from every other gesture in the set.
3. **Implement using only the shared primitives in `gestures/gesture_utils.py`** (`euclidean_distance()`, `finger_angle()`, `finger_states()`) and, for dynamic gestures, `MotionHistoryBuffer`. Do not write a new, parallel distance or angle calculation inline — if `gesture_utils.py` doesn't yet have the primitive you need, add it there, not inline in the gesture function.
4. **Write the function in the correct file:** static gestures in `gestures/static_recognizer.py`, dynamic gestures in `gestures/dynamic_recognizer.py`. Function name is `detect_<gesture_name>` matching the gesture's `snake_case` identifier exactly (Section 6.1).
5. **Register the gesture with `GestureEngine`** by adding it to the `STATIC_GESTURE_RULES` (or dynamic equivalent) list in `gestures/gesture_engine.py` so it is included in the all-candidates generation pass (TRD §3.9). The `ConflictResolver` downstream handles cases where multiple registered rules match simultaneously — do not add artificial early-exit logic inside `GestureEngine` to prevent multiple matches, as that would reintroduce the old "first-match-wins" implicit ordering that PRD §4.6 explicitly replaced.
6. **Add fixture data** under `tests/fixtures/` — a recorded or synthetically-constructed landmark set (static) or trajectory (dynamic) representing a clear, unambiguous instance of the gesture.
7. **Write unit tests** per Section 7.3 below before considering the gesture done.
8. **Add the gesture to the default mapping files** (`assets/default_mappings/*.json`) only if the PRD's profile descriptions (PRD §8.9) call for it in that profile — do not add a gesture to every profile by default just because it now exists.

### 7.2 Validation Rules

Every gesture implementation must satisfy all of the following before it can be considered complete — these are not best-effort guidelines, they are gate conditions:

- **No raw-pixel or raw-frame-normalized threshold.** Every distance comparison divides by `hand.scale.palm_width` or `hand.scale.palm_height` first (PRD §5.2's explicit worked example of the forbidden pattern). Every dynamic-gesture displacement/velocity comparison divides by `hand_scale` first (TRD §4.4). This is checked by code review (Section 12) and by the mandatory scale-invariance test (7.3).
- **Multi-signal discipline is mandatory (PRD §4.5, FR-MS-01–03).** Every static gesture rule combines at least two independent geometric signals before producing a candidate `GestureResult` — a finger-state pattern alone, or a single normalized-distance check alone, is not sufficient. Every dynamic gesture rule combines at least velocity, direction, and motion-history shape — single-frame displacement alone is never sufficient. The gesture function's docstring must explicitly list the signals it combines (FR-MS-03), e.g.: `"""Signals used: finger-state (EXTENDED/CURLED), normalized thumb-index distance, remaining-finger state."""`
- **`hand.scale is None` is handled by returning `None` immediately**, not by falling back to an unnormalized calculation (PRD FR-SC-04). There is no acceptable fallback path that bypasses normalization.
- **The function never raises.** Per Section 6.4's hot-path rule — malformed input degrades to `None`, it never propagates an exception.
- **Confidence is a meaningful, graded value, not always a fixed constant**, where the geometry naturally supports it (e.g., Pinch's confidence scales with how far below the 0.35 threshold the normalized distance falls, TRD §4.3's `detect_pinch` reference implementation: `confidence = 1.0 - (normalized_dist / 0.35)`). Where the rule is a pure boolean match with no natural gradient (e.g., Three Fingers' finger-state pattern match), a fixed high-confidence constant (e.g., `0.9`) is acceptable and matches the pattern already used for similar boolean-rule gestures.
- **Mutual exclusivity with confusable gestures is explicitly tested**, not assumed. Implementation Plan §7.1 names the specific known-confusable pairs (Peace Sign vs. Three Fingers; Pinch vs. OK Sign; Thumbs Up vs. Thumbs Down) — any new or modified gesture must be checked against its documented confusable neighbor(s).

### 7.3 Testing Rules

Per TRD §13.2/§13.3 and Implementation Plan §7's per-gesture Testing Strategy entries, every gesture requires, at minimum:

1. **A positive unit test** against a clear, unambiguous fixture, asserting the gesture is detected with confidence above `gesture_confidence_threshold` (default 0.85).
2. **At least one negative test** against a confusable-neighbor fixture, asserting the gesture is *not* falsely detected (e.g., `test_fist_not_open_palm`).
3. **For static gestures only:** if the gesture involves a normalized-distance check (Priority 3), a scale-invariance test parametrized across multiple synthetic hand-scale values, per the TRD §4.6 pattern:

```python
@pytest.mark.parametrize("scale_factor", [0.5, 1.0, 2.0, 3.0])
def test_<gesture>_recognized_at_all_scales(<gesture>_landmarks_base, scale_factor):
    scaled_hand = scale_hand_landmarks(<gesture>_landmarks_base, scale_factor)
    result = detect_<gesture>(scaled_hand)
    assert result is not None
    assert result.confidence > 0.5
```

4. **For dynamic gestures only:** a too-slow rejection test and a wrong-direction (e.g., too-vertical for a horizontal swipe) rejection test, per the TRD §13's `test_swipe_right_rejected_if_too_slow` / `test_swipe_right_rejected_if_too_vertical` pattern.
5. **`hand.scale is None` test** asserting the function returns `None` rather than raising or guessing.

### 7.4 Acceptance Criteria

A gesture implementation is acceptable for merge when:

- All Section 7.3 tests exist and pass
- The gesture's behavior matches its PRD §4.3/§4.4 rule summary exactly — no embellishment, no "improvement" on the documented rule without a flagged PRD-change request
- Code review (Section 12) confirms no raw-pixel threshold exists anywhere in the new code
- **The gesture function's docstring explicitly lists the signals it combines (PRD FR-MS-03)** — "signals used: X, Y" must appear in every `detect_*` function's docstring; a function without this is incomplete regardless of whether its logic is correct
- **The gesture combines at least two independent signals (PRD FR-MS-01 for static, FR-MS-02 for dynamic)** — confirmed by reading the docstring and the implementation against the multi-signal table in PRD §4.5
- **`ConflictResolver` compatibility verified**: the gesture function returns `None` cleanly when it does not match (not `0.0` confidence, not a special sentinel — literally `None`), so that `GestureEngine`'s all-candidates list remains uncontaminated by zero-confidence entries that `ConflictResolver` would then have to filter out downstream
- The gesture's accuracy, when later validated in Checkpoint 9's multi-distance UAT (Implementation Plan §13), is expected to meet the PRD §21.1 KPI of ≥95% accuracy stable within 3% across near/medium/far camera distances — a gesture implementation that structurally cannot meet this (e.g., uses an un-normalized threshold) must not be merged regardless of how it performs in ad-hoc manual testing at a single distance

### 7.5 Worked Example — Adding/Modifying a Static Gesture

This example walks through implementing **OK Sign** (PRD §4.3) from scratch, illustrating every step in 7.1–7.3.

```python
# gestures/static_recognizer.py

def detect_ok_sign(hand: HandData) -> GestureResult | None:
    """Recognize the OK Sign gesture: thumb-index pinch distance below
    threshold, AND middle/ring/pinky all extended (this is what
    distinguishes it from Pinch, where the other three fingers are
    unconstrained).

    Implements PRD §4.3 (OK Sign gesture rule). Default action: Right Click.

    Signals used: normalized thumb-index distance (Priority 3, palm_width
    denominator) + remaining-finger EXTENDED state (Priority 1). Two
    independent signals required per PRD FR-MS-01.
    """
    if hand.scale is None:
        return None  # PRD FR-SC-04

    # Priority 3: normalized distance, never raw (PRD §5.2)
    raw_dist = euclidean_distance(hand.landmarks[4], hand.landmarks[8])
    normalized_dist = raw_dist / hand.scale.palm_width
    if normalized_dist >= 0.35:
        return None

    # Priority 1: finger state, distinguishes this from Pinch
    states = finger_states(hand.landmarks)
    if not (states['middle'] and states['ring'] and states['pinky']):
        return None

    confidence = 1.0 - (normalized_dist / 0.35)
    return GestureResult(
        gesture_name='ok_sign',
        confidence=confidence,
        is_dynamic=False,
        hand_role=hand.role,
        timestamp=time.time(),
    )
```

```python
# tests/unit/test_static_gestures.py

def test_ok_sign_detected(ok_sign_landmarks):
    hand = estimate_scale(ok_sign_landmarks)  # test helper applying HandScaleEstimator
    result = detect_ok_sign(hand)
    assert result is not None
    assert result.gesture_name == 'ok_sign'

def test_ok_sign_not_confused_with_pinch(ok_sign_landmarks):
    """Mutual-exclusivity check per Implementation Plan §7.1: OK Sign and
    Pinch share the same thumb-index distance check, so the three-finger
    constraint must correctly disambiguate them."""
    hand = estimate_scale(ok_sign_landmarks)
    ok_result = detect_ok_sign(hand)
    pinch_result = detect_pinch(hand)
    assert ok_result is not None
    assert pinch_result is None or pinch_result.gesture_name != ok_result.gesture_name

@pytest.mark.parametrize("scale_factor", [0.5, 1.0, 2.0, 3.0])
def test_ok_sign_recognized_at_all_scales(ok_sign_landmarks, scale_factor):
    scaled_hand = scale_hand_landmarks(ok_sign_landmarks, scale_factor)
    result = detect_ok_sign(scaled_hand)
    assert result is not None
    assert result.confidence > 0.5

def test_ok_sign_returns_none_without_scale(ok_sign_landmarks_no_scale):
    result = detect_ok_sign(ok_sign_landmarks_no_scale)
    assert result is None
```
## 8. Logging Standards

Every component logs through `DiagnosticsManager`'s structured helper methods (Section 6.5), using the exact format established in TRD §9.1:

```
[TIMESTAMP] [LEVEL] [MODULE] Message  {key: value, ...}
```

### 8.1 What Must Be Logged, By Category

This table is the authoritative checklist, reproduced and consolidated from TRD §9.2 and PRD §12.1. Every new component that participates in one of these categories must emit the corresponding events — silently omitting a required log event is a Definition-of-Done failure (Implementation Plan §16.2, Feature DoD item 3).

| Category | Required Events | Level |
|---|---|---|
| **Camera Events** | Camera started (device, resolution, fps); frame dropped; sustained low FPS; camera disconnected; reconnect attempt | INFO (started, quality check) / WARN (dropped frame, sustained low FPS) / ERROR (disconnected after exhausting retries) |
| **Tracking Events** | Hand detected/lost; occlusion bridged/expired; scale estimation skipped; re-identification ambiguous | DEBUG (per-hand detail) / WARN (occlusion bridged, re-id ambiguous, scale skipped) |
| **Gesture Events** | Candidate detected; stability check passed/failed; cooldown suppressed/passed; gesture triggered | INFO (triggered) / DEBUG (candidate, stability/cooldown internal checks) |
| **Action Events** | Action executed (success); action dispatch failed | INFO (success) / ERROR (failed) |
| **Context Events** | Context resolved; verification pending/committed; context query failed (using cache) | INFO (resolved, committed) / WARN (query failed) |
| **Activation Events** | State changed (inactive↔active), method used | INFO |
| **Lighting Events** | Lighting check result; sustained low-light warning | DEBUG (routine check) / WARN (sustained warning) |
| **Profile Events** | Profile loaded; mapping conflict detected | INFO (loaded) / WARN (conflict) |
| **Settings Events** | Invalid field reverted to default; settings file corrupted | WARN |
| **Errors** | Any caught exception in a cold-path component (Section 6.4) | ERROR |
| **Warnings** | Any degraded-but-continuing condition | WARN |

### 8.2 Log Level Discipline

Reproduced from TRD §9.1 — this is the binding policy, not a suggestion:

- **DEBUG:** high-frequency, expected-noise events. File-only, never console. Only emitted when `developer_mode` is true.
- **INFO:** state changes and successful operations worth a permanent record (camera started, gesture detected, action executed).
- **WARN:** recoverable problems — degraded but continuing.
- **ERROR:** failed operations that required falling back or surfacing to the user.

**A component must never log at INFO or above for an expected, common, non-noteworthy event.** For example, "no mapping found for this gesture+context" is the *normal* outcome of pressing a gesture with no configured action — TRD §3.13 is explicit that this is "not logged as a warning unless `developer_mode`." Logging every routine no-op at WARN/ERROR floods the log file and trains developers to ignore warnings, which is worse than not logging at all.

### 8.3 Worked Examples

```
[12:31:42.103] [INFO]  [camera]     Camera started  {device: 0, resolution: '640x480', fps: 30}
[12:31:44.210] [INFO]  [gesture]    Gesture detected  {gesture: 'swipe_right', confidence: 0.91, hand: 'HAND_A'}
[12:31:44.211] [DEBUG] [gesture]    Stability check passed  {gesture: 'swipe_right', held_ms: 210}
[12:31:44.212] [INFO]  [context]    Context resolved  {process: 'chrome.exe', context: 'chrome'}
[12:31:44.213] [DEBUG] [gesture]    Cooldown check passed  {gesture: 'swipe_right', hand: 'HAND_A'}
[12:31:44.214] [INFO]  [action]     Action executed  {type: 'keyboard', params: 'alt+right', status: 'success'}
[12:31:50.004] [WARN]  [camera]     Sustained low FPS  {measured_fps: 18.3, duration_s: 5.2}
[12:31:55.900] [INFO]  [activation] State changed  {from: 'inactive', to: 'active', method: 'open_palm_hold'}
[12:32:01.004] [WARN]  [tracking]   Hand occluded, bridging  {role: 'HAND_A', retained_ms: 120}
[12:32:05.004] [ERROR] [action]     Action dispatch failed  {type: 'keyboard', error: 'permission_denied'}
```

Calling code:

```python
# CORRECT — through DiagnosticsManager's structured helper
self.diagnostics.log_gesture_detected(
    gesture='swipe_right', confidence=0.91, hand_role='HAND_A',
)

# WRONG — bare print, no structure, no category, no log file
print(f"detected swipe_right with confidence 0.91")

# WRONG — ad-hoc logging.getLogger call bypassing the shared format/categories
import logging
logging.getLogger(__name__).info("gesture detected: swipe_right")
```

### 8.4 Adding a New Loggable Event

When a new component or feature introduces a new kind of event to log:

1. Identify which existing category (8.1) it belongs to — most new events fit an existing category.
2. If it genuinely doesn't fit any existing category, add a new category to `diagnostics/log_format.py` and to the table in Section 8.1 of this guide (keep them in sync — this guide is not a static artifact, see Section 16.2).
3. Add a structured helper method to `DiagnosticsManager` following the existing naming pattern (`log_<event>`, e.g., `log_gesture_detected`, `log_camera_event`).
4. Never construct a raw log string inline at the call site — always go through a named helper method, so the format stays centralized and consistent.
## 9. Testing Standards

### 9.1 Unit Testing

- **No live camera or hardware required**, ever, for a unit test (TRD §13.2's foundational rule). Every unit test operates on synthetic or recorded fixture data under `tests/fixtures/`.
- One test file per production module, mirroring the source layout: `gestures/static_recognizer.py` → `tests/unit/test_static_gestures.py`.
- Tests are independent and order-agnostic — no test may depend on another test having run first or having left behind state.
- Mock/synthetic data lives in `tests/fixtures/` as JSON, loaded via `conftest.py` fixtures — never hardcoded as inline literals scattered across multiple test files (a fixture used by more than one test file belongs in `conftest.py` or a shared fixtures module).

```python
# tests/conftest.py — shared fixture pattern, per TRD §13.2
@pytest.fixture
def open_palm_landmarks():
    """21 landmarks representing a clear open-palm pose, right hand."""
    return _load_fixture('open_palm_right.json')
```

### 9.2 Integration Testing

- Integration tests exercise a full vertical slice of the pipeline (Camera-equivalent mock → ... → Action dispatch), using a synthetic frame source and mocked OS-dispatch calls (`patch('actions.executors.base.CommandExecutor.dispatch')`), never real camera input or real OS-level side effects.
- Integration tests are only meaningful from the point in the build where the pipeline forms a closed chain — per Implementation Plan §2.3, this is from the Activation checkpoint onward. Adding an integration test for a feature whose dependencies aren't fully wired yet produces a test that can't actually verify what it claims to.
- One integration test file per cross-cutting concern: `test_pipeline_end_to_end.py`, `test_context_switching.py`, `test_occlusion_tolerance.py`.

```python
# tests/integration/test_pipeline_end_to_end.py — TRD §13.4 pattern
def test_swipe_right_in_chrome_triggers_forward_navigation(mock_camera_feed, mock_context_chrome):
    app = build_test_app(camera=mock_camera_feed, context=mock_context_chrome)
    app.activation_gate.state = TrackingState.ACTIVE
    with patch('actions.executors.base.CommandExecutor.dispatch') as mock_dispatch:
        for frame in mock_camera_feed.swipe_right_sequence():
            app.process_frame(frame)
        mock_dispatch.assert_called_once()
        assert mock_dispatch.call_args[0][0].params == {'hotkey': ['alt', 'right']}
```

### 9.3 Performance Testing

- Performance tests are the **only** test category permitted to run against real camera hardware and a real 30-minute/4-hour session (TRD §13.4's "less frequently than unit/integration — nightly or pre-release, not on every commit").
- All five PRD §16 Performance Budget targets are asserted **simultaneously** in a single test, not in isolation — a build that passes an FPS-only check while silently exceeding the memory budget is not a passing build.

```python
# tests/performance/test_fps_and_memory.py — TRD §13.6 / Implementation Plan §13 pattern
def test_performance_budgets_all_met(running_app_30min_session):
    session = running_app_30min_session
    avg_fps = sum(session.fps_log) / len(session.fps_log)
    avg_cpu = sum(session.cpu_samples) / len(session.cpu_samples)
    peak_memory_mb = max(session.memory_samples)
    assert avg_fps >= 25
    assert avg_cpu < 20
    assert peak_memory_mb < 300
```

### 9.4 Regression Testing

- Every bug fix (Section 10) includes a regression test reproducing the original failure, added *before* the fix and confirmed to fail against the pre-fix code, then confirmed to pass after the fix (Implementation Plan §16.1, checkpoint DoD item 5: "No regressions in prior checkpoints' Acceptance Criteria").
- The full existing test suite is run after every change, not just the tests for the module being changed — a change in `tracking/hand_scale.py` can silently break a `gestures/` test that depends on its output shape.
- CI must run the full unit + integration suite (not performance, which is nightly/pre-release per 9.3) on every commit/PR.

### 9.5 Coverage Targets

Per TRD §13.7: **≥80% line coverage** for `gestures/`, `actions/`, `profiles/`, `settings/`, `tracking/`. New components introduced for any feature are held to the same 80% bar — there is no "this module is too simple to need tests" exception; even a simple module can have an off-by-one or sign error.

| Module Group | Coverage Target | Notes |
|---|---|---|
| `gestures/` | ≥80% | Every gesture's positive + negative + (where applicable) scale-invariance tests count toward this |
| `actions/` | ≥80% | `CommandExecutor` platform-specific code may be partially covered by integration tests instead of pure unit tests where mocking the OS call is more practical |
| `profiles/`, `settings/` | ≥80% | |
| `tracking/` | ≥80% | |
| `context/adapters/*`, `actions/executors/*` (platform-specific) | Best-effort unit coverage; primary verification via integration testing against a real or mocked OS, per TRD §13.7's explicit carve-out |

### 9.6 Testing Templates

**New static gesture test template** (see Section 7.5 for a fully worked example):

```python
def test_<gesture>_detected(<gesture>_landmarks):
    hand = estimate_scale(<gesture>_landmarks)
    result = detect_<gesture>(hand)
    assert result is not None
    assert result.gesture_name == '<gesture>'

def test_<gesture>_not_confused_with_<confusable_neighbor>(<gesture>_landmarks):
    ...

@pytest.mark.parametrize("scale_factor", [0.5, 1.0, 2.0, 3.0])
def test_<gesture>_recognized_at_all_scales(<gesture>_landmarks, scale_factor):
    ...

def test_<gesture>_returns_none_without_scale(<gesture>_landmarks_no_scale):
    ...
```

**New component unit test template** (general TRD §3-component pattern):

```python
def test_<component>_<expected_behavior>():
    component = <Component>(<minimal required config>)
    result = component.<method_under_test>(<input>)
    assert result == <expected>

def test_<component>_handles_<documented_error_case>():
    """Verify the Error Handling behavior documented in TRD §3.<N>."""
    component = <Component>(<config>)
    result = component.<method_under_test>(<malformed_or_edge_case_input>)
    assert result == <documented_safe_default>  # never assert an exception was raised,
                                                    # unless this IS a cold-path component
                                                    # per Section 6.4
```
## 10. Debugging Standards

### 10.1 Bug Classification

Every bug is classified before any fix work begins. Classification determines response urgency and the rigor required for root-cause analysis (10.2).

| Priority | Definition | Examples (GestureOS-specific) |
|---|---|---|
| **P0 — Critical** | Crashes the application, corrupts persisted data, or causes an action to fire while `ActivationGate.state == INACTIVE` (a direct violation of PRD §7's mandatory safety requirement) | Capture thread crash; `settings.json` corrupted by a failed atomic write; a gesture action dispatches during INACTIVE state |
| **P1 — High** | A core feature is broken or produces materially wrong output, but the application remains stable | A specific gesture never triggers regardless of correct execution; scale-invariance is broken for one gesture (accuracy degrades >3% across distances, violating the PRD §21.1 KPI); context resolution permanently stuck on the wrong app |
| **P2 — Medium** | A feature works but with degraded quality, or an edge case is mishandled | Occlusion handling works but the 300ms window is measurably off by a noticeable margin; cursor smoothing has more lag than expected at certain `alpha` values; a quality warning badge doesn't dismiss correctly |
| **P3 — Low** | Cosmetic, rare-edge-case, or non-functional-requirement-adjacent issues | Debug panel formatting slightly misaligned; a log message's wording is unclear; minor UI spacing issue in the settings panel |

**Classification rule:** Any bug that violates one of the five Architectural Philosophy principles (Section 1.3) — especially scale-invariance or the activation-gate safety guarantee — is automatically **at least P1**, regardless of how rare the triggering condition seems, because these are the principles the entire product's reliability claim rests on.

### 10.2 Root Cause Analysis Process

1. **Reproduce first, theorize second.** Do not propose a fix before the bug has been reliably reproduced (10.3). A fix for a bug you can't reproduce is a guess, and guesses accumulate as silent technical debt across hundreds of AI-assisted sessions.
2. **Identify the failing pipeline stage.** Use the Runtime State Flow (TRD §5.1/§5.2) as a checklist — at which of the 17 stages does behavior diverge from expected? The Developer Mode debug panel (Section 8, TRD §9.3) exists specifically to make this diagnosis possible without adding ad-hoc print statements.
3. **Trace the responsible component**, using TRD §3's component-to-stage mapping. A bug "in gesture recognition" almost always narrows to one specific component (e.g., `StabilityFilter` vs. `GestureEngine` vs. the specific `detect_*` rule function) — find which one before writing any fix code.
4. **Check whether the bug is a code defect or a requirement gap.** If the code does exactly what the PRD/TRD say it should, and the *result* is still wrong, the bug may actually be a documentation gap (an under-specified threshold, an ambiguous rule) — this is escalated per Section 11's "respect architecture" rule, not silently patched with an undocumented behavior change.
5. **Identify the minimal fix scope.** Per Section 11.4 ("Avoid rewriting unrelated modules"), a bug fix touches the component(s) actually responsible — it does not opportunistically refactor neighboring code "while we're in here."

### 10.3 Reproduction Process

1. Capture the exact conditions: which gesture, which hand role, what camera distance/lighting if relevant, what `Settings` values were active, what the `developer_mode` debug panel showed at the time (if available).
2. Convert the reported conditions into a fixture under `tests/fixtures/` — a recorded or synthetically-constructed landmark set / trajectory / settings configuration that reproduces the bug deterministically.
3. Write a failing test reproducing the bug **before** touching any production code (this becomes the regression test per Section 9.4).
4. If the bug cannot be reproduced via a unit-level fixture (e.g., it depends on real-world camera noise or timing), escalate to an integration-level reproduction, and if that's still insufficient, document it as a manual-reproduction-only bug with explicit steps — this is rare and should prompt asking whether the underlying behavior needs better automated observability (a gap in diagnostics, Section 8) rather than accepting "can't reproduce in CI" indefinitely.

### 10.4 Verification Process

1. The new regression test (10.3) fails against the pre-fix code — confirmed, not assumed.
2. The fix is implemented, scoped per 10.2 step 5.
3. The regression test now passes.
4. The **full** test suite (unit + integration, per Section 9.4) is re-run and passes — not just the test file for the affected module.
5. For P0/P1 bugs specifically: a manual verification pass confirms the fix in a realistic running session, not just at the unit-test level, since the bug's real-world severity warrants direct confirmation beyond automated coverage.
6. The bug's classification (10.1) and root cause (10.2) are recorded in the fix's commit message or PR description, so future debugging sessions can search prior fixes for similar patterns.

### 10.5 Regression Prevention

- Every fixed bug leaves behind a permanent regression test (10.3/10.4) — this is non-negotiable, not "nice to have if there's time."
- If a bug's root cause was a violation of one of this guide's standards (e.g., a raw-pixel threshold slipped through review, Section 7.2), the relevant section of this guide is checked for whether the rule needs to be stated more explicitly, and Section 12's review checklist is checked for whether it needs an additional explicit check item.
- A P0 or P1 bug whose root cause was a missed case in the Risk Management matrix (Implementation Plan §15.1) should result in that risk's "Validation" column being strengthened, not just the immediate bug being patched.

### 10.6 Worked Example

**Bug report:** "Pinch gesture stops triggering when I move farther from the camera."

```
Classification: P1 (scale-invariance violation, Section 10.1's automatic-P1 rule)

Root Cause Analysis:
  Stage check (TRD §5.1): Gesture Candidate stage produces no candidate
  when the user is far from camera, despite Hand Scale Estimated stage
  completing successfully (confirmed via Developer Mode debug panel —
  HandScale.smoothed_scale is populated and reasonable).

  Component trace: gestures/static_recognizer.py, detect_pinch()

  Finding: detect_pinch() was modified in a recent commit to compare
  raw_dist directly against 0.04 instead of computing
  normalized_dist = raw_dist / hand.scale.palm_width first — a raw-pixel
  threshold reintroduced in violation of PRD §5.2 / Section 7.2 of this
  guide.

Reproduction:
  tests/fixtures/pinch_far.json (already existed from Checkpoint 3,
  TRD §13.3) reproduces this exactly — confirms the bug is fully
  covered by existing fixture infrastructure, the regression was a
  pure code defect, not a missing test gap.

Fix:
  Restored the normalized_dist = raw_dist / hand.scale.palm_width line.
  Scope: single function, gestures/static_recognizer.py only — no
  other file touched.

Verification:
  tests/unit/test_scale_invariance.py::test_pinch_recognized_close_and_far
  now passes. Full suite re-run, all green. Manual verification at
  30cm and 150cm confirms fix in a live session.

Regression Prevention:
  This specific failure mode (a normalization step silently dropped
  during a later edit) is now explicitly called out in Section 12's
  review checklist as its own line item, not just covered by the
  general "no raw-pixel threshold" rule.
```
## 11. AI Prompting Rules

This section governs how AI coding agents — including future instances of the same model family answering future prompts — must behave when working on GestureOS. These rules exist because the failure mode this guide defends against is not any single bad change, but **slow architectural drift across hundreds of individually-reasonable-looking prompts**, each one slightly bending a rule because it was locally convenient.

### 11.1 What the AI Must Always Do

1. **Respect architecture.** Before writing code, identify which TRD §3 component(s) the task touches, and confirm the planned change matches that component's documented Responsibilities, Inputs, Outputs, Dependencies, and Error Handling. If the task seems to require behavior outside a component's documented scope, that's a signal to either pick the correct component or flag a gap (11.5) — not to quietly expand the component's job.
2. **Respect folder boundaries.** Cross-check the planned file location against Section 4.1's Allowed/Forbidden Responsibilities table before creating or editing a file. A change that requires importing `pyautogui` into a file under `gestures/` is structurally wrong, no matter how small.
3. **Add logging.** Any new event matching one of Section 8.1's categories gets a corresponding `DiagnosticsManager` call. This is not optional polish — it's how the next debugging session (Section 10) will be able to diagnose what this code did.
4. **Add tests.** Per Section 9 — no new function ships without unit tests, no new cross-cutting behavior ships without an integration test where one is meaningful (Section 9.2's "from Activation checkpoint onward" caveat applies).
5. **Avoid rewriting unrelated modules.** A prompt asking to "fix the swipe-left cooldown" touches `gestures/cooldown_filter.py` and possibly `gestures/dynamic_recognizer.py` — it does not touch `overlay/debug_panel.py`'s formatting, even if the AI notices something it would "improve" there while looking around. Unrelated improvements are a separate, explicitly-requested task.
6. **Explain assumptions.** When a prompt is ambiguous about which gesture, which threshold, which checkpoint's scope applies, the AI states its interpretation explicitly before or alongside the change, so a human reviewer can catch a wrong assumption immediately rather than discovering it three prompts later.
7. **Cite source documents.** Any new function's docstring references the PRD requirement ID or TRD section it implements (Section 6.6) — this is what keeps hundreds of future prompts traceable back to a single source of truth instead of devolving into tribal knowledge.
8. When implementing a new gesture:
For every newly implemented gesture, the AI must document:
- Gesture name and purpose
- Recognition logic
- Geometric features used
  - Finger joint angles
  - Finger states
  - Relative landmark distances
  - Palm orientation
  - Motion history (if applicable)
- Confidence calculation
- Conflict-resolution behavior
- Temporal validation requirements (hold time, debounce, cooldown, etc.)
- Performance impact
- Configuration constants added or modified
- Test cases and expected behavior

### 11.2 What the AI Must Never Do

- Invent a new gesture, action type, profile, or UI screen not already named in the PRD (Section 7's framing rule, restated generally: a new *feature* is a product decision, flagged for sign-off, never silently implemented).
- Change an existing architecture decision (e.g., switching `CursorController`'s default smoothing method, restructuring the threading model, replacing JSON config with a database) without an explicit, separate architecture-change request and corresponding TRD update.
- Add a new third-party dependency not already in TRD §1.3's stack (Section 2.4) to solve a problem the existing stack already addresses.
- Introduce a raw-pixel or raw-frame-normalized threshold anywhere in `gestures/` (Section 7.2 — this is the single most-repeated rule in this guide because it is the single most likely silent regression).
- Implement a gesture rule using only a single geometric signal — every `detect_*` function must combine at least two independent signals (PRD FR-MS-01/FR-MS-02) and declare them in its docstring (FR-MS-03). A function that checks only one signal is incomplete regardless of how accurate it appears in casual testing.
- Merge `GestureEngine`'s candidate-generation responsibility with `ConflictResolver`'s winner-selection responsibility back into a single class or a single function using short-circuit `or` logic — this reverts a deliberate, documented architecture decision (TRD §3.9/§3.9.1, PRD §4.6) and silently reintroduces implicit first-match-wins ordering.
- Create `MacOSExecutor`, `LinuxExecutor`, `MacOSContextAdapter`, or `LinuxContextAdapter` implementation files — these are Future Expansion deliverables (PRD §1.2, TRD §11.5) not in scope for the initial Windows release. The ABCs exist and are documented; the concrete implementations do not yet exist and must not be created until Future Expansion work is explicitly authorized.
- Add `pyobjc`, `python-xlib`, or any macOS/Linux-specific library to `requirements.txt` for the initial release build.
- Suppress an exception with a bare `except: pass` (Section 6.4).
- Mutate a `Settings` object in place from a non-owning thread (Section 5.6).
- Mark a task "done" without the corresponding tests passing (Section 9) and the corresponding Definition of Done (Section 15) satisfied.

### 11.3 Prompt Examples

#### Good Prompt

> "Implement the Swipe Up gesture in `gestures/dynamic_recognizer.py` per PRD §4.4 and Implementation Plan §7.2. It should mirror the existing `detect_swipe_right` implementation, rotated to the vertical axis, using the same `hand_scale`-normalized displacement/velocity pattern. Add unit tests per Section 9.6's dynamic-gesture template, including the too-slow and too-diagonal rejection cases."

**Why this is good:** names the exact file, cites the exact PRD/Implementation-Plan sections, names the existing pattern to mirror (preventing reinvention), and explicitly requires the test cases this guide mandates.

#### Bad Prompt

> "Make swipes feel more responsive."

**Why this is bad:** no file scope, no acceptance criteria, no reference to which gesture(s) or which specific quality ("responsive" could mean lower cooldown, lower stability window, lower confidence threshold, or a smoothing change — each is a different component and a different tradeoff against the Risk Matrix in Implementation Plan §15). An AI agent receiving this prompt should ask a clarifying question rather than guess which of several plausible, materially-different changes was intended.

#### Feature Prompt

> "Implement the Calibration Wizard's Step 3 (Cursor Speed) per TRD §10.2. It binds directly to `cursor_speed_multiplier` for a live preview while the wizard is open, and persists via `CalibrationManager.complete()` only when the user finishes or explicitly accepts — per FR-CAL-03, if the user skips, no partial settings are written. Scope: `ui/calibration_wizard.py` and `calibration/calibration_manager.py` only. Add a unit test confirming skip-mid-flow does not persist anything."

**Why this is good:** scoped to a specific PRD/TRD subsection, names the specific files, restates the relevant requirement ID, and specifies the edge-case test that matters most for this feature.

#### Refactoring Prompt

> "Extract the repeated `euclidean_distance(landmarks[4], landmarks[8]) / hand.scale.palm_width` pattern used in both `detect_pinch` and `detect_ok_sign` into a shared helper `thumb_index_distance_ratio(hand)` in `gestures/gesture_utils.py`. Do not change either function's threshold or behavior — this is a pure extraction. Re-run the existing test suites for both gestures to confirm no behavior change."

**Why this is good:** explicitly scopes the refactor as behavior-preserving, names the exact target location (`gesture_utils.py`, per Section 7.1 step 3's "shared primitives" rule), and requires re-running existing tests as the verification step rather than writing new ones (since no new behavior was introduced).

#### Bug Fix Prompt

> "Bug: Pinch gesture stops triggering at camera distances beyond ~1 meter. Reproduce using `tests/fixtures/pinch_far.json`. Follow the Debugging Standards in Section 10 — classify, reproduce with a failing test first, then fix. Suspect `gestures/static_recognizer.py::detect_pinch` may have a missing or incorrect scale-normalization step; verify against PRD §5.2's worked example before changing anything."

**Why this is good:** points to a specific, existing fixture for reproduction, explicitly invokes the guide's own debugging process, and gives a starting hypothesis without prematurely committing to a fix — letting the AI confirm root cause before acting, per Section 10.2's "reproduce first, theorize second" rule.

### 11.4 Scope Discipline

Every prompt response should be answerable with: "I touched exactly these files, for exactly this reason, and here is how I verified it didn't break anything else." If an AI agent cannot produce that summary at the end of a task, the task was scoped too broadly, or executed too loosely, and should be reconsidered before being marked complete.

### 11.5 Flagging Gaps Instead of Inventing

When a prompt's request cannot be satisfied without either (a) inventing a new requirement, or (b) changing an existing architecture decision, the correct response is to **stop and flag it as a gap**, following the same pattern established in the Implementation Plan's Gap Register (Implementation Plan, Appendix A): describe the gap precisely, state why it can't be resolved by implementation alone, and recommend it for product-owner/architect review. This applies even under time pressure, even when the "obvious" answer seems low-risk — the entire point of this guide is that low-risk-seeming, ungoverned decisions are exactly what accumulate into architectural drift across hundreds of sessions.
## 12. Code Review Standards

Every change — whether authored by a human or an AI agent — passes this checklist before merge. This consolidates the rules established throughout Sections 1–11 into a single reviewable list.

### 12.1 Architecture & Boundaries

- [ ] Change is scoped to the correct TRD §3 component(s); no component has gained an undocumented second responsibility (Section 5.2)
- [ ] No file was created or edited outside its folder's Allowed Responsibilities (Section 4.1)
- [ ] No new import violates the dependency direction (Section 5.3) — earlier-pipeline-stage code never imports from later-stage code
- [ ] No component reaches into another component's private internals (Section 5.4)
- [ ] No new circular import was introduced (Section 5.5)
- [ ] Any pipeline state mutation happens only on the owning thread; any cross-thread communication uses Qt signals, not direct calls (Section 5.6)

### 12.2 Scale Invariance (Gesture Code Specifically)

- [ ] Every new or modified distance comparison in `gestures/` divides by `hand.scale.palm_width`/`palm_height` before comparison — **no raw-pixel or raw-frame-normalized threshold exists anywhere** (Section 7.2; this is the single highest-priority check item, given its history as a recurring regression pattern, Section 10.6)
- [ ] Every new or modified dynamic-gesture displacement/velocity calculation is normalized by `hand_scale` (TRD §4.4)
- [ ] `hand.scale is None` is handled by returning `None`, not by falling back to an unnormalized path (PRD FR-SC-04)
- [ ] Every new or modified `detect_*` function combines **at least two independent geometric signals** (PRD FR-MS-01/FR-MS-02) and its docstring explicitly names them (FR-MS-03)
- [ ] New gesture functions return `None` (not `0.0` confidence, not a sentinel object) when the gesture does not match — required for clean `ConflictResolver` candidate-list compatibility (TRD §3.9.1)

### 12.3 Coding Standards

- [ ] Naming matches Section 6.1's conventions, including exact gesture-name-string matching against the PRD
- [ ] Type hints present on every function signature and dataclass field, using `X | None` / `list[X]` syntax (Section 6.2)
- [ ] New shared data objects are `@dataclass`, modified via `dataclasses.replace()`, not in-place mutation (Section 6.3)
- [ ] Hot-path functions never raise; cold-path functions raise specific typed exceptions, never bare `Exception` (Section 6.4)
- [ ] No bare `except: pass` without explicit, documented justification
- [ ] Every public class/method has a docstring citing the PRD requirement ID or TRD section it implements (Section 6.6)

### 12.4 Logging

- [ ] Every new loggable event (Section 8.1) is logged through `DiagnosticsManager`'s structured helpers, at the correct level (Section 8.2)
- [ ] No bare `print()` or ad-hoc `logging.getLogger()` call was introduced (Section 8.3)
- [ ] Routine, expected, non-noteworthy outcomes are not logged at WARN/ERROR (Section 8.2)

### 12.5 Testing

- [ ] New functions have unit tests; new gestures have the full Section 7.3 test set including scale-invariance parametrization where applicable
- [ ] New gestures have a `test_conflict_resolver.py`-compatible test confirming they return `None` cleanly when they do not match (not a zero-confidence result)
- [ ] New cross-cutting behavior has an integration test, where the pipeline is sufficiently wired for one to be meaningful (Section 9.2)
- [ ] Bug fixes include a regression test that fails pre-fix and passes post-fix (Section 9.4/10.3)
- [ ] Coverage for touched modules remains ≥80% (Section 9.5)
- [ ] Full test suite (not just the touched module's tests) passes

### 12.6 Scope Discipline

- [ ] The change touches only the files necessary for its stated purpose — no opportunistic edits to unrelated modules (Section 11.1 item 5)
- [ ] If the change required a judgment call on an ambiguous requirement, that assumption is stated explicitly in the PR description (Section 11.1 item 6)
- [ ] No new feature, gesture, or architecture decision was introduced without a flagged gap and explicit sign-off (Section 11.2, 11.5)

### 12.7 Documentation Sync

- [ ] If the change affects repository structure, naming conventions, or any rule in this guide, this guide itself is updated in the same change (Section 16.2)
- [ ] If the change reveals a gap in the PRD/TRD/Implementation Plan, it is added to the Gap Register pattern (Implementation Plan, Appendix A), not silently resolved

### 12.8 Platform Scope (Windows-Primary)

- [ ] No new code imports `pyobjc`, `AppKit`, `python-xlib`, or any macOS/Linux-specific library — these are Future Expansion scope (PRD §1.2) and must not appear in the initial-release codebase
- [ ] No new executor or adapter subclass for macOS or Linux was created — `MacOSExecutor`, `LinuxExecutor`, `MacOSContextAdapter`, `LinuxContextAdapter` are Future Expansion deliverables (TRD §11.5), not current-release deliverables
- [ ] Any Windows-specific API call is contained within `actions/executors/windows_executor.py` or `context/adapters/windows_adapter.py` — never inlined into `action_engine.py`, `context_engine.py`, or any platform-agnostic module

---

## 13. Security & Privacy Standards

GestureOS's privacy posture is structural, not a policy statement — per TRD §14, "no data leaves the device" must remain mechanically true, and this guide's job is to keep it that way across every future change.

### 13.1 Core Privacy Rules

1. **No frame, landmark, or gesture data is ever written to disk.** Frames exist only in memory for the duration of one pipeline pass. A change that adds frame/landmark persistence for any reason (debugging convenience, future feature exploration, etc.) is a privacy-architecture change requiring explicit sign-off, not a routine code change.
2. **Log files never contain raw landmark coordinates or frame images, even in `developer_mode`.** Section 8's logged events are gesture names, confidence scores, and timestamps — never the underlying coordinate data. The Debug Overlay (Section 8, TRD §9.3) may *display* landmark coordinates live on-screen, but display is not persistence — nothing the debug panel shows is written to the log file.
3. **No HTTP client library is imported anywhere in the core pipeline** (`camera/`, `tracking/`, `gestures/`, `context/`, `actions/`). This is enforced by an automated CI check (TRD §12.3's pattern), not review discipline alone — an AI agent must never add `requests`, `urllib`, `socket`, `aiohttp`, or any equivalent import to these folders.
4. **Webcam permission is requested via native OS dialogs only.** GestureOS never implements its own permission UI or attempts to bypass/cache around an OS permission denial.
5. **`~/.gestureos/` data is never encrypted at rest, and this is intentional**, not an oversight — there is no secret material stored there (TRD §14.4). Do not add encryption "for safety" without recognizing this as a deliberate prior architecture decision being reconsidered, which itself requires sign-off, not unilateral action.

### 13.2 Enforcement Mechanism

A CI lint rule scans for forbidden imports (`requests`, `urllib.request`, `http.client`, `socket`, `aiohttp`) in every file under the core-pipeline folders, with a narrow, explicitly-named exception list (TRD §12.3's pattern: e.g., an "check for updates" link in onboarding UI that opens a browser, never an in-process network call). Any new file under `camera/`, `tracking/`, `gestures/`, `context/`, or `actions/` is automatically subject to this check — an AI agent does not need to remember to run it manually, but should be aware it exists and will fail CI if violated.

### 13.3 Sensitive-Data Checklist for New Features

Before merging any feature that touches user data:

- [ ] Does this feature write any new data to disk? If so, confirm it belongs in the existing `settings.json` / `profiles.json` / `mappings/*.json` / `logs/` categories, not a new ad-hoc persistence path.
- [ ] Does this feature transmit any data anywhere? If yes, this is a privacy-architecture change requiring explicit product-owner sign-off — it cannot ship as a routine feature addition.
- [ ] Does this feature's logging (Section 8) accidentally include raw coordinate or image data? Check against 13.1 item 2 specifically.

---

## 14. Performance Standards

All targets below are reproduced exactly from PRD §16 (Performance Budgets) — they are not subject to reinterpretation, only to the explicit tie-breaking priority the PRD itself states.

### 14.1 Targets

| Metric | Target | Priority if Conflict |
|---|---|---|
| FPS | ≥ 25 | Highest priority — never sacrificed for CPU/memory savings |
| Detection Latency | < 100 ms | High priority |
| End-to-End Action Latency | < 150 ms | High priority |
| CPU Usage | < 20% (single core average) | Lowest priority of the five — PRD §16 explicitly states: "If... < 20% is not achievable without degrading FPS below 25, CPU budget is the parameter to revisit — FPS and latency are the higher-priority constraints" |
| Memory Usage | < 300 MB | Medium priority |

### 14.2 Performance Discipline for New Code

- Any new per-frame pipeline stage (i.e., anything added to the `CaptureThread`'s loop, not a one-time setup cost) must be evaluated for its marginal cost against these budgets, following the analysis pattern in TRD §15.2: is the addition O(1)/negligible (most additions should be), or does it require dedicated profiling?
- Use the `cProfile` harness pattern (TRD §15.3) to measure, rather than assume, the cost of any addition whose complexity isn't obviously negligible.
- A new per-frame stage that does meaningful image-array work (anything beyond simple scalar/dict/timestamp comparisons) is the kind of addition that specifically warrants profiling before merge — vectorize with NumPy/OpenCV rather than per-pixel Python loops, matching the existing pattern used by `LightingMonitor`'s brightness calculation (TRD §3.4: "cheap, vectorized... `cv2.cvtColor` to grayscale, then `.mean()`").
- Performance regressions are caught by the Section 9.3 performance test suite, which must be re-run (not just unit/integration tests) for any change touching a per-frame pipeline stage before that change is considered verified.

### 14.3 Where the Budget Comes From

These five numbers trace to PRD §16.2 and are measured against the **Reference Hardware Baseline defined in PRD §16.1: Intel Core i5 8th Gen or equivalent, 8 GB RAM, 720p webcam**. This is the single authoritative hardware definition for these targets — results measured on other hardware are informational, not pass/fail. The ≥25 FPS and <100ms detection latency targets are the foundational interactivity requirements (PRD §7.1); <150ms end-to-end makes gesture-to-action feel responsive; <300MB/<20% CPU ensures GestureOS remains a lightweight background presence on the reference hardware rather than competing for resources with the user's actual work. Any change that would require relaxing one of these numbers is a product-level tradeoff discussion, not an implementation detail to quietly accept.
## 15. Definition of Done

This section restates and operationalizes the Implementation Plan's three-tier Definition of Done (Implementation Plan §16) at the day-to-day development level, adding the explicit "Module Complete" tier this guide's structure calls for.

### 15.1 Feature Complete

An individual feature (a single gesture, a single settings field, a single platform adapter, a single UI screen) is complete when:

1. Its behavior matches its PRD requirement ID exactly — no embellishment beyond the documented rule (Section 7.4, Implementation Plan §16.2 item 1)
2. Its TRD-specified implementation details (data model fields, error handling pattern, dependencies) are followed exactly (Implementation Plan §16.2 item 2)
3. It has dedicated unit tests covering both its success path and documented failure cases (Section 9.1, Implementation Plan §16.2 item 3)
4. It is exercised by an integration test if the pipeline has reached a stage where one is meaningful (Section 9.2, Implementation Plan §16.2 item 4)
5. It introduces no violation of this guide's Core Principles (Section 1.3) — no raw-pixel threshold, no untracked network call, no cross-thread violation (Implementation Plan §16.2 item 5)
6. It is logged per Section 8's requirements
7. Code review (Section 12) is complete with all applicable checklist items satisfied

### 15.2 Module Complete

A module (one TRD §3 component, e.g., `HandScaleEstimator`, `ContextEngine`) is complete when:

1. It is implemented exactly per its TRD §3 specification: Responsibilities, Inputs, Outputs, Dependencies, and Error Handling all match
2. Every method/function in the module independently satisfies Section 15.1's Feature Complete bar
3. Unit test coverage for the module is ≥80% (Section 9.5)
4. The module respects its folder's Allowed/Forbidden Responsibilities (Section 4.1) with zero violations
5. The module's public interface (the data objects it produces/consumes) is fully documented per Section 6.6, such that another component can be built against it without reading the module's internals
6. Any cross-cutting concern the module participates in (logging categories, settings fields) is fully wired, not partially stubbed

### 15.3 Checkpoint Complete

Reproduced from Implementation Plan §16.1 (Checkpoint Definition of Done) — a checkpoint is Done when:

1. All Deliverables exist as files in the locations specified by that checkpoint's Files section
2. All Modules implemented match their TRD §3 specification exactly
3. All Acceptance Criteria pass, verified by the checkpoint's Testing Strategy
4. Unit test coverage meets or exceeds 80% for any new or modified module in scope
5. No regressions in prior checkpoints' Acceptance Criteria
6. No scope creep — no file belonging to a later checkpoint was created prematurely
7. Any Gap encountered is documented, not silently resolved
8. Code review confirms architectural discipline throughout

### 15.4 Project Complete

Reproduced from Implementation Plan §16.3 (Project Definition of Done) — GestureOS as a whole is Done when:

1. All 11 checkpoints (Checkpoint 0–10) have individually met their Definition of Done, in dependency order
2. Every PRD v1.2 functional and non-functional requirement is implemented and verified
3. Every PRD v1.2 Success Metric (PRD §21.1) is met on reference hardware
4. PRD §20.4's Release Acceptance Gate is satisfied
5. Every Gap raised during implementation has a documented disposition — resolved with sign-off, or formally accepted as a known limitation
6. No requirement, architecture decision, or feature from the PRD or TRD was altered, removed, or silently reinterpreted during implementation

---

## 16. Maintenance Standards

### 16.1 Versioning

GestureOS's source documents follow `MAJOR.MINOR.PATCH` versioning, and code changes are tracked against the document version they implement:

- **PRD/TRD/Implementation Plan version bumps** follow the pattern already established across this project's history: a MINOR bump (e.g., PRD v1.1 → v1.2) accompanies a batch of new requirements or formalized behavior; document content is never silently edited without a version bump.
- **Code commits reference the requirement/section they implement** (Section 6.6's docstring rule extends to commit messages: "Implements PRD §4.4 Swipe Up" is a correctly-traceable commit message; "fix swipe" is not).
- **A code change that requires a PRD/TRD/Implementation Plan change must update the source document first** (or in the same change set), never leave the documents stale relative to the actual implementation — a guide and source documents that drift out of sync with the code they describe become actively harmful, since future AI sessions will trust the (now-wrong) document over tribal knowledge of what actually shipped.

### 16.2 Documentation Updates

This guide, and the three source documents above it, are living documents that must be kept in sync with the codebase:

- Any change to repository structure (Section 4) updates this guide's Section 4 **and** TRD §8 in the same change set.
- Any new logging category (Section 8.4) updates this guide's Section 8.1 table.
- Any new architecture rule discovered necessary through a bug's root-cause analysis (Section 10.5) is added to Section 5 or 12 as appropriate.
- Any gap formally resolved (Implementation Plan Appendix A pattern) is removed from "open" status and its resolution is reflected in the relevant source document.
- **This guide is reviewed for staleness at the close of every checkpoint** (Implementation Plan §15.2's recommended cadence, applied here), alongside that checkpoint's own Definition of Done review.

### 16.3 Refactoring Rules

- A refactor is **behavior-preserving by definition** — if a "refactor" prompt changes observable behavior (a threshold, a default value, a log message's content), it is not a refactor, it is a feature change or bug fix, and must be scoped, tested, and reviewed as one (Section 11.3's Refactoring Prompt example shows the correct framing: "Do not change either function's threshold or behavior — this is a pure extraction").
- A refactor's verification is: full existing test suite passes unchanged, with no new test required (since no new behavior exists) — only updated tests if the refactor changed an internal structure the tests were inappropriately coupled to (e.g., tests calling a private method that got renamed during extraction).
- A refactor never crosses a folder boundary (Section 4.1) — moving logic from `gestures/` to `tracking/` is an architecture change, not a refactor, even if the code itself is unchanged, because it alters which component owns that responsibility.
- A refactor is performed in isolation from any feature work or bug fix in the same change — mixing "I refactored X while fixing Y" makes both the refactor and the fix harder to review and harder to revert independently if either turns out to be wrong.

### 16.4 Deprecation Rules

- A deprecated gesture, setting, or component is never silently removed. It is marked deprecated (a docstring note + a log WARN if still invoked), kept functional for at least one full checkpoint cycle (Implementation Plan §3's checkpoint structure) to allow dependent code and any persisted user configuration to migrate, and only removed in a subsequent, explicitly-scoped removal change.
- A settings field that becomes obsolete (e.g., a tuning parameter for a removed feature) follows `SettingsManager`'s existing per-field-fallback pattern (TRD §7.1) during the deprecation window — the field is still accepted and validated if present in an existing user's `settings.json`, but is no longer read by any active component, and a new installation's default `settings.json` no longer includes it.
- Removing a deprecated gesture or feature is itself a product decision (PRD scope change), not an implementation cleanup task — it requires the same sign-off process as adding a new feature (Section 7's framing rule, applied in reverse), since it changes what the product PRD §4.3/§4.4 promises to recognize.

---

*End of GestureOS AI Development Guide v1.0.0*

> **A closing note on the purpose of this document:** every rule above exists because of a specific, named failure mode this project's architecture is vulnerable to — scale-invariance regressions, activation-safety violations, architectural drift across hundreds of incremental changes, silent feature invention, and documentation/code divergence. This guide is not bureaucracy for its own sake. An AI agent or developer who understands *why* each rule exists, not just *that* it exists, will apply good judgment correctly even in the cases this guide didn't anticipate — and will know to flag a gap, per Section 11.5, when it encounters one.
