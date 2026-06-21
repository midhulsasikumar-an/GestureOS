# Technical Requirements Document — GestureOS

**Document Type:** Technical Requirements Document (TRD)
**Source of Truth:** GestureOS PRD v1.2 (Final)
**Version:** 1.1.0
**Audience:** Engineering team, AI coding agents, QA
**Language/Runtime:** Python 3.11+
**Date:** June 2026

> **Document Scope:** This TRD translates GestureOS PRD v1.2 into an implementation blueprint. It does not introduce new product features and does not alter PRD requirements. Every functional and non-functional requirement, gesture rule, checkpoint, and acceptance criterion defined in the PRD — including all v1.2 additions (scale invariance, hand scale estimation, stability/cooldown, cursor smoothing, motion history, occlusion handling, primary hand selection, camera validation, lighting detection, context verification, calibration, performance budgets) — is treated as fixed. This document answers **HOW** the system is engineered to satisfy those requirements.
>
> **Changes from TRD v1.0:** This revision adds five new components (HandScaleEstimator, StabilityFilter, CooldownFilter, OcclusionHandler, CameraValidator/LightingMonitor), rewrites GestureEngine's internals around scale-invariant math, formalizes CursorController as its own component, adds the Context Verification Layer to ContextEngine, and adds a new Calibration subsystem. All TRD v1.0 components not mentioned as changed remain as previously specified.

---

## Table of Contents

1. [Technical Overview](#1-technical-overview)
2. [System Architecture](#2-system-architecture)
3. [Component Architecture](#3-component-architecture)
4. [Scale-Invariant Recognition — Engineering Detail](#4-scale-invariant-recognition--engineering-detail)
5. [Runtime State Flow](#5-runtime-state-flow)
6. [Data Models](#6-data-models)
7. [Configuration Design](#7-configuration-design)
8. [Folder Structure](#8-folder-structure)
9. [Diagnostics Architecture](#9-diagnostics-architecture)
10. [Calibration Subsystem](#10-calibration-subsystem)
11. [Cross-Platform Strategy](#11-cross-platform-strategy)
12. [Packaging Strategy](#12-packaging-strategy)
13. [Testing Architecture](#13-testing-architecture)
14. [Security & Privacy Architecture](#14-security--privacy-architecture)
15. [Performance Budget Engineering](#15-performance-budget-engineering)
16. [Technical Risks](#16-technical-risks)
17. [Future Extensibility](#17-future-extensibility)

---

## 1. Technical Overview

GestureOS is implemented as a single-process, multi-threaded Python desktop application. A real-time capture-and-recognition loop runs on a dedicated worker thread; a PyQt6 event loop runs on the main thread for UI, overlay, and system tray. The two communicate via thread-safe Qt signals.

### 1.1 Engineering Principles

- **Deterministic over probabilistic:** every gesture decision must be traceable to an explicit geometric rule with named thresholds — no opaque models.
- **Scale-invariant by construction:** every distance or velocity measurement used in a gesture rule is normalized against a live hand-scale reference before comparison to any threshold. Raw pixel or raw-frame-normalized comparisons are treated as a code-review-blocking defect (Section 4).
- **Local-only:** no network calls in the core pipeline; all persistence is local JSON files.
- **Fail-soft:** any single-module failure (camera glitch, OS query failure, malformed mapping, low light, low FPS) degrades gracefully and is logged or surfaced as a warning — it never crashes the main loop.
- **Separation of concerns:** capture, recognition, context, action, and presentation are independent modules connected only through well-defined data objects (Section 6).
- **Configuration over code:** gesture-to-action behavior, plus all v1.2 stability/cooldown/smoothing parameters, lives in JSON, not in source.

### 1.2 What's New Relative to TRD v1.0

| Capability | PRD Source | New/Changed Component |
|---|---|---|
| Scale-invariant gesture math | PRD §5 | StaticRecognizer, DynamicRecognizer rewritten around HandScaleEstimator output |
| Hand scale estimation | PRD §6 | **HandScaleEstimator** (new) |
| Gesture stability window | PRD §8.2 | **StabilityFilter** (new) |
| Cooldown system | PRD §8.3 (formalized) | **CooldownFilter** (new, extracted from GestureEngine) |
| Cursor smoothing | PRD §8.4 (formalized) | **CursorController** (new, extracted from ActionEngine) |
| Motion history buffer | PRD §8.5 | DynamicRecognizer's trajectory deque, now a named, capacity-bounded component |
| Temporary occlusion handling | PRD §8.1.2 | **OcclusionHandler** (new, inside tracking/) |
| Primary hand selection | PRD §8.1.3 | **PrimaryHandFilter** (new, inside tracking/) |
| Context verification layer | PRD §8.7.3 | ContextEngine extended with a hold-timer |
| Camera validation | PRD §8.11 | **CameraValidator** (new, inside diagnostics/) |
| Lighting quality detection | PRD §8.12 | **LightingMonitor** (new, inside diagnostics/) |
| Calibration wizard | PRD §15 | **CalibrationManager** (new) + ui/calibration_wizard.py |
| Performance budgets | PRD §16 | Enforced via profiling harness, Section 15 |

### 1.3 Why This Stack (unchanged from v1.0)

| Technology | Used For | Why Chosen |
|---|---|---|
| Python 3.11+ | Application runtime | Fast iteration, mature CV/automation ecosystem |
| OpenCV | Camera capture, frame ops, brightness analysis | Cross-platform VideoCapture; also used for LightingMonitor's luminance calculation |
| MediaPipe | Hand landmark detection | Pre-trained, CPU-efficient 21-point model, no training needed |
| NumPy | Vector math for gesture rules, scale normalization | Vectorized distance/angle calculations |
| PyQt6 | GUI, overlay, system tray, calibration wizard | Native widgets, always-on-top overlay, mature threading model |
| PyAutoGUI | Simple cross-platform OS actions | Single API across all 3 target OSes |
| pynput | Low-latency key/mouse events, cursor dispatch | Lower dispatch latency than PyAutoGUI |
| pywin32 | Windows active-window detection | Required for ContextEngine on Windows |
| PyInstaller | Packaging | Single native executable per OS |
| pytest | Testing | Supports fixtures for mock landmark + synthetic-scale data |

---

## 2. System Architecture

### 2.1 High-Level Pipeline (v1.2)

```
┌──────────────────┐
│  Camera Input     │   CameraModule.read_frame()
└─────────┬─────────┘
          ▼
┌──────────────────┐
│  Frame Processing │   flip, resize, BGR→RGB
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Camera Validation │   CameraValidator.check() — FPS/res monitoring
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ MediaPipe         │   TrackingModule.detect()
│ Detection         │
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Lighting Check    │   LightingMonitor.check(frame)
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Hand Identity +   │   HandIdentityModule.assign_roles()
│ Occlusion Handling│   OcclusionHandler.bridge_gaps()
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Hand Scale        │   HandScaleEstimator.estimate()
│ Estimation        │
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Primary Hand      │   PrimaryHandFilter.filter()
│ Filtering         │
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Activation Gate   │   ActivationGate.is_active()
└─────────┬─────────┘
          │ INACTIVE → render only, skip below
          ▼
┌──────────────────┐
│ Gesture           │   GestureEngine.evaluate()
│ Recognition       │   (scale-invariant static + motion-history dynamic)
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Stability Filter  │   StabilityFilter.check(candidate)
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Context Engine +  │   ContextEngine.resolve() with verification hold-timer
│ Verification       │
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Action Mapping    │   ActionEngine.resolve()
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ Cooldown Filter   │   CooldownFilter.check(hand, gesture)
└─────────┬─────────┘
          ▼
┌──────────────────┐
│ OS Execution      │   CommandExecutor.dispatch()
│ (+ CursorController│   CursorController.smooth_and_move() for cursor path
│  for cursor path) │
└──────────────────┘
```

### 2.2 Threading Model (unchanged from v1.0)

A single background `QThread` (`CaptureThread`) owns the camera loop and runs every pipeline stage synchronously within one frame iteration. The main thread owns PyQt6's event loop, the overlay window, the settings UI, and the new Calibration Wizard. Cross-thread communication uses Qt signals exclusively.

```
┌──────────────────────────────┐        ┌────────────────────────────────┐
│      Main Thread (Qt)         │        │   CaptureThread (QThread)        │
│                                │        │                                   │
│  MainWindow / SettingsPanel   │◄───────│  while running:                  │
│  CalibrationWizard            │ signals │    frame = camera.read()         │
│  TrayIcon                     │         │    ... full pipeline (2.1) ...   │
│  OverlayRenderer (paint)      │  ─────► │    emit gesture_detected(result) │
│                                │ signal  │    emit quality_warning(kind)    │
│  Slots:                       │         │    emit state_changed(state)     │
│   on_gesture_detected(result) │         │                                   │
│   on_quality_warning(kind)    │         │                                   │
│   on_state_changed(state)     │         │                                   │
└──────────────────────────────┘        └────────────────────────────────┘
```

### 2.3 Data Flow Summary

| Stage | Owning Module | Data Object Produced |
|---|---|---|
| Camera | CameraModule | `np.ndarray` (BGR frame) |
| Frame Processing | CameraModule | `np.ndarray` (RGB frame) |
| Camera Validation | CameraValidator | `CameraQuality` (fps_ok, resolution_ok) |
| MediaPipe Detection | TrackingModule | raw MediaPipe result |
| Lighting Check | LightingMonitor | `LightingQuality` (brightness, is_low) |
| Identity + Occlusion | HandIdentityModule, OcclusionHandler | `list[HandData]` (role-tagged, gap-bridged) |
| Scale Estimation | HandScaleEstimator | `HandData.scale` populated |
| Primary Hand Filter | PrimaryHandFilter | `list[HandData]` (filtered) |
| Gesture Recognition | GestureEngine | `GestureResult \| None` |
| Stability Filter | StabilityFilter | `GestureResult \| None` (held candidates only) |
| Context + Verification | ContextEngine | `str` context id |
| Action Mapping | ActionEngine | `Action \| None` |
| Cooldown Filter | CooldownFilter | `Action \| None` (suppressed if in cooldown) |
| OS Execution | CommandExecutor, CursorController | `ActionResult` |

---

## 3. Component Architecture

Each component is a self-contained Python module exposing a small, explicit public API. Components communicate only through the data objects defined in Section 6.

> **Component Boundary Rule:** A component may only import from its own folder and the shared data-model module. It may NOT import PyQt6 widgets, the camera, or another component's internals. Exception: `overlay/` and `ui/`, which are UI-layer and may depend on everything else read-only.

### 3.1 CameraModule *(unchanged from v1.0)*

Wraps OpenCV's `VideoCapture`. Owns the camera device lifecycle: opening, reading, reconnecting, releasing.

- **Responsibilities:** open/configure device; yield BGR frames; detect disconnection and reconnect; apply flip + resize preprocessing.
- **Inputs:** device index, target resolution, target FPS (from Settings).
- **Outputs:** `np.ndarray` shape (H,W,3), BGR, flipped, resized.
- **Dependencies:** `opencv-python` only.
- **Error Handling:** `cv2.VideoCapture` fails to open → `CameraUnavailableError`; dropped frame → increment counter, skip; 10 consecutive drops → treat as disconnect, retry every 2s up to 10 attempts; after that, emit `CameraError`, keep app running.

```python
class CameraModule:
    def __init__(self, device_index: int, width=640, height=480, fps=30):
        self.device_index = device_index
        self.width, self.height, self.fps = width, height, fps
        self.cap = None
        self.consecutive_drops = 0

    def read_frame(self) -> np.ndarray | None:
        ret, frame = self.cap.read()
        if not ret:
            self.consecutive_drops += 1
            return None
        self.consecutive_drops = 0
        frame = cv2.flip(frame, 1)
        return cv2.resize(frame, (self.width, self.height))
```

---

### 3.2 CameraValidator *(new in v1.2, implements PRD §8.11)*

Continuously checks that the active camera meets minimum performance requirements, surfacing warnings rather than failing silently.

- **Responsibilities:** at startup, check camera opens, reports FPS capability, reports resolution; during operation, track a rolling measured-FPS average and flag sustained underperformance.
- **Inputs:** `CameraModule` instance (for `cv2.CAP_PROP_*` queries), a stream of per-frame timestamps from `CaptureThread`.
- **Outputs:** `CameraQuality(fps_ok: bool, resolution_ok: bool, measured_fps: float)`, recomputed roughly once per second (not every frame — this is a cheap rolling average, not a per-frame allocation).
- **Dependencies:** OpenCV only.
- **Error Handling:** if FPS queries are unsupported by a given camera driver (some webcams misreport), fall back to measuring actual inter-frame timing instead of trusting `cv2.CAP_PROP_FPS`; never raises — degraded measurement still returns a best-effort `CameraQuality`.

```python
class CameraValidator:
    MIN_FPS = 25
    MIN_RESOLUTION = (640, 480)
    SUSTAINED_LOW_FPS_S = 5.0

    def __init__(self):
        self.frame_timestamps = deque(maxlen=90)  # ~3s of history at 30fps
        self.low_fps_since: float | None = None

    def record_frame(self, now: float):
        self.frame_timestamps.append(now)

    def measured_fps(self) -> float:
        if len(self.frame_timestamps) < 2:
            return 0.0
        span = self.frame_timestamps[-1] - self.frame_timestamps[0]
        return (len(self.frame_timestamps) - 1) / span if span > 0 else 0.0

    def check(self, now: float) -> CameraQuality:
        fps = self.measured_fps()
        fps_ok = fps >= self.MIN_FPS
        if not fps_ok:
            self.low_fps_since = self.low_fps_since or now
        else:
            self.low_fps_since = None
        sustained_low = (self.low_fps_since is not None
                          and (now - self.low_fps_since) >= self.SUSTAINED_LOW_FPS_S)
        return CameraQuality(fps_ok=not sustained_low, resolution_ok=True, measured_fps=fps)
```

---

### 3.3 TrackingModule *(unchanged from v1.0)*

Wraps MediaPipe Hands. Converts raw output into `HandData` objects.

- **Responsibilities:** initialize MediaPipe Hands; convert frames to RGB; run inference; build `list[HandData]` with chirality + confidence.
- **Inputs:** RGB `np.ndarray` frame.
- **Outputs:** `list[HandData]`, length 0–2.
- **Dependencies:** `mediapipe`, `numpy`.
- **Error Handling:** MediaPipe exception → log ERROR, return empty list for that frame; malformed hand (≠21 landmarks) → discard that hand only; 3 consecutive exceptions → attempt one re-init; failing that → raise `TrackingInitError`.

---

### 3.4 LightingMonitor *(new in v1.2, implements PRD §8.12)*

Monitors frame brightness and correlates sustained low brightness with degraded MediaPipe confidence to surface an actionable warning.

- **Responsibilities:** compute mean luminance per frame (cheap, vectorized); track a rolling window of (luminance, mediapipe_confidence) pairs; raise a "Low Lighting Detected" condition when both are sustained-low together.
- **Inputs:** RGB frame, average per-hand `confidence` from `TrackingModule`'s most recent detection.
- **Outputs:** `LightingQuality(is_low: bool, mean_luminance: float)`.
- **Dependencies:** OpenCV/NumPy for luminance (`cv2.cvtColor` to grayscale, then `.mean()`).
- **Error Handling:** if no hand is currently detected, confidence is treated as N/A and the lighting check uses brightness alone (a dark room with no hand in frame is still worth flagging at the next gesture attempt); never raises.

```python
class LightingMonitor:
    LOW_BRIGHTNESS_THRESHOLD = 60   # 0-255 grayscale mean
    LOW_CONFIDENCE_THRESHOLD = 0.6
    SUSTAINED_S = 3.0

    def __init__(self):
        self.low_since: float | None = None

    def check(self, rgb_frame: np.ndarray, hand_confidence: float | None, now: float) -> LightingQuality:
        gray = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2GRAY)
        brightness = float(gray.mean())
        confidence_low = hand_confidence is not None and hand_confidence < self.LOW_CONFIDENCE_THRESHOLD
        brightness_low = brightness < self.LOW_BRIGHTNESS_THRESHOLD

        if brightness_low and (confidence_low or hand_confidence is None):
            self.low_since = self.low_since or now
        else:
            self.low_since = None

        is_low = self.low_since is not None and (now - self.low_since) >= self.SUSTAINED_S
        return LightingQuality(is_low=is_low, mean_luminance=brightness)
```

---

### 3.5 HandIdentityModule *(unchanged from v1.0)*

Maintains persistent hand identity (HAND_A / HAND_B) across frames per PRD §8.1.1.

- **Responsibilities:** assign stable roles; match via nearest-neighbor proximity; preserve role for up to 2s after loss; resolve ties via chirality fallback.
- **Inputs:** `list[HandData]` (role=None), internal `last_seen: dict[role -> (x,y,timestamp)]`.
- **Outputs:** `list[HandData]` (role populated).
- **Dependencies:** pure Python.
- **Error Handling:** >2 hands detected → keep 2 highest-confidence, discard rest, log WARN; stale history (>2s) cleared automatically; ambiguous tie → chirality fallback + WARN log.

```python
class HandIdentityModule:
    REID_WINDOW_S = 2.0
    MATCH_THRESHOLD = 0.15  # normalized units

    def assign_roles(self, hands: list[HandData], now: float) -> list[HandData]:
        self.last_seen = {r: v for r, v in self.last_seen.items()
                          if now - v[2] < self.REID_WINDOW_S}
        unassigned = list(hands)
        for role, (lx, ly, _) in list(self.last_seen.items()):
            best, best_dist = None, float('inf')
            for h in unassigned:
                wx, wy, _ = h.landmarks[0]
                d = ((wx-lx)**2 + (wy-ly)**2) ** 0.5
                if d < best_dist:
                    best, best_dist = h, d
            if best and best_dist < self.MATCH_THRESHOLD:
                best.role = role
                unassigned.remove(best)
        for h in unassigned:
            used_roles = {x.role for x in hands if x.role}
            h.role = 'HAND_A' if 'HAND_A' not in used_roles else 'HAND_B'
        for h in hands:
            wx, wy, _ = h.landmarks[0]
            self.last_seen[h.role] = (wx, wy, now)
        return hands
```

---

### 3.6 OcclusionHandler *(new in v1.2, implements PRD §8.1.2)*

Bridges brief tracking interruptions (a finger or whole hand briefly occluded) so gesture state isn't immediately invalidated by a single bad frame.

- **Responsibilities:** when a previously-tracked hand role is missing or below detection-confidence threshold this frame, retain its last-known `HandData` (landmarks, finger states) for up to `occlusion_retention_ms` (default 300ms); if detection recovers within the window, resume seamlessly without resetting `StabilityFilter` or `DynamicRecognizer` trajectory state; if the window expires, release the hand to `HandIdentityModule`'s normal re-identification path.
- **Inputs:** current frame's `list[HandData]` (post-identity-assignment), previous frame's retained `HandData` per role.
- **Outputs:** `list[HandData]` — either the real current-frame data, or a bridged "retained" `HandData` (flagged `is_retained=True` for diagnostics) when occlusion is active.
- **Dependencies:** pure Python. Sits between `HandIdentityModule` and `HandScaleEstimator` in the pipeline.
- **Error Handling:** if a hand is occluded for longer than the retention window, it is not silently retained forever — this is a hard timeout, not a fallback-forever cache, to avoid stale gesture state persisting indefinitely.

```python
class OcclusionHandler:
    def __init__(self, retention_ms: int = 300):
        self.retention_s = retention_ms / 1000.0
        self.retained: dict[str, tuple[HandData, float]] = {}  # role -> (data, lost_at)

    def bridge_gaps(self, current_hands: list[HandData], now: float) -> list[HandData]:
        current_roles = {h.role for h in current_hands}
        result = list(current_hands)

        # Detect newly-lost hands this frame, start retaining them
        for role, (data, _) in list(self.retained.items()):
            if role in current_roles:
                del self.retained[role]  # hand is back, drop the bridge

        # Any role we tracked last frame but is missing now: start/continue retention
        for role in self._previous_roles - current_roles:
            if role not in self.retained:
                self.retained[role] = (self._previous_hands[role], now)
            data, lost_at = self.retained[role]
            if now - lost_at <= self.retention_s:
                bridged = replace(data, is_retained=True)
                result.append(bridged)
            else:
                del self.retained[role]  # window expired, let it go

        self._previous_roles = {h.role for h in result}
        self._previous_hands = {h.role: h for h in current_hands}
        return result
```

---

### 3.7 HandScaleEstimator *(new in v1.2, implements PRD §6)*

Computes a smoothed hand-scale reference used to normalize every distance and motion measurement in `StaticRecognizer` and `DynamicRecognizer`. This is the component that makes recognition scale-invariant — see Section 4 for the full mathematical treatment.

- **Responsibilities:** compute palm width (landmark 5 ↔ 17), palm height (landmark 0 ↔ 9), and bounding box every frame per hand; maintain a 5-frame moving average of the raw scale value to suppress per-frame estimation jitter.
- **Inputs:** `HandData.landmarks` for one hand.
- **Outputs:** populates `HandData.scale: HandScale` with `palm_width`, `palm_height`, `bounding_box`, `smoothed_scale`.
- **Dependencies:** pure Python/NumPy geometry. No dependency on `gestures/`.
- **Error Handling:** if landmarks are missing or malformed (should not happen post-`TrackingModule` validation, but defensively checked): leave `HandData.scale = None`; downstream `GestureEngine` treats `scale=None` as "skip this hand this frame" (PRD FR-SC-04) rather than guessing.

```python
class HandScaleEstimator:
    SMOOTHING_WINDOW = 5

    def __init__(self):
        self.history: dict[str, deque[float]] = {'HAND_A': deque(maxlen=5), 'HAND_B': deque(maxlen=5)}

    def estimate(self, hand: HandData) -> HandData:
        if len(hand.landmarks) != 21:
            return replace(hand, scale=None)

        palm_width = euclidean_distance(hand.landmarks[5], hand.landmarks[17])
        palm_height = euclidean_distance(hand.landmarks[0], hand.landmarks[9])
        raw_scale = (palm_width + palm_height) / 2

        xs = [p[0] for p in hand.landmarks]
        ys = [p[1] for p in hand.landmarks]
        bbox = (min(xs), min(ys), max(xs), max(ys))

        hist = self.history[hand.role]
        hist.append(raw_scale)
        smoothed = sum(hist) / len(hist)

        return replace(hand, scale=HandScale(
            palm_width=palm_width, palm_height=palm_height,
            bounding_box=bbox, smoothed_scale=smoothed,
        ))
```

---

### 3.8 PrimaryHandFilter *(new in v1.2, implements PRD §8.1.3)*

Implements Dominant Hand Mode — restricts gesture evaluation to a single chirality when configured, while still tracking and rendering the secondary hand.

- **Responsibilities:** read `dominant_hand_mode` from Settings (`off` / `left` / `right`); when not `off`, mark non-matching hands as `gesture_eligible=False` (they still flow through the pipeline for overlay rendering, just never reach `GestureEngine.evaluate()` for gesture candidacy).
- **Inputs:** `list[HandData]` (post-scale-estimation), `Settings.dominant_hand_mode`.
- **Outputs:** `list[HandData]` (same list, `gesture_eligible` flag set per hand).
- **Dependencies:** pure Python.
- **Error Handling:** if the designated primary hand isn't present in the current frame, no promotion of a secondary hand occurs (PRD FR-PH-03) — the filter simply produces a list where zero hands are `gesture_eligible` that frame; this is a normal, non-error condition.

```python
class PrimaryHandFilter:
    def filter(self, hands: list[HandData], mode: str) -> list[HandData]:
        if mode == 'off':
            return [replace(h, gesture_eligible=True) for h in hands]
        target_chirality = 'Left' if mode == 'left' else 'Right'
        return [replace(h, gesture_eligible=(h.chirality == target_chirality)) for h in hands]
```

---

### 3.9 GestureEngine *(rewritten in v1.2 around scale-invariant math)*

The recognition core. Evaluates static finger-state/angle rules and motion-history-buffered dynamic rules, all normalized against `HandData.scale.smoothed_scale`. See Section 4 for the complete rule implementations.

- **Responsibilities:** compute per-finger EXTENDED/CURLED state via joint angle (PRD §5.3); evaluate static gesture rules using Priority 1→3 signals (finger state → angles → normalized distances); maintain the Motion History Buffer per hand role and evaluate dynamic rules using Priority 4 (normalized trajectories); return the single highest-confidence `GestureResult` candidate per hand per frame — confidence and cooldown/stability are applied downstream by `StabilityFilter` and `CooldownFilter`, not inside `GestureEngine` itself (this separation is new in v1.2 — v1.0 combined cooldown into the engine).
- **Inputs:** `list[HandData]` (role-tagged, scale-populated, gesture-eligible filtered), current timestamp.
- **Outputs:** `list[GestureResult]` (0–2 entries, one per gesture-eligible hand, raw candidates — not yet stability- or cooldown-filtered).
- **Dependencies:** NumPy for vectorized math. Reads `gesture_confidence_threshold` from Settings.
- **Error Handling:** `HandData.scale is None` → skip gesture evaluation for that hand entirely this frame (no exception, no fallback to raw pixels — PRD FR-SC-04); NaN/out-of-range landmark values → skip evaluation for that hand, log DEBUG; must never raise — this is the hottest path in the pipeline.

```python
class GestureEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.motion_history = MotionHistoryBuffer(max_frames=settings.motion_history_frames)

    def evaluate(self, hands: list[HandData], now: float) -> list[GestureResult]:
        results = []
        for hand in hands:
            if not hand.gesture_eligible or hand.scale is None:
                continue
            self.motion_history.update(hand.role, hand.landmarks[0], now)
            candidate = (self._check_static(hand) or self._check_dynamic(hand.role, now))
            if candidate and candidate.confidence >= self.settings.gesture_confidence_threshold:
                results.append(candidate)
        return results
```

---

### 3.10 StabilityFilter *(new in v1.2, implements PRD §8.2)*

Requires a static gesture to remain the highest-confidence match for a continuous hold window before it's accepted, eliminating single-frame flicker triggers.

- **Responsibilities:** track, per (hand_role), the gesture name first seen and the timestamp it started; on each frame, if the same gesture name is still the candidate, check elapsed time against `gesture_stability_window_ms`; once satisfied, emit the gesture exactly once (not every frame thereafter — see Cooldown interaction below); if the candidate gesture changes before the window elapses, reset the hold timer with no partial credit (PRD FR-GS-02).
- **Inputs:** `GestureResult | None` per hand (from `GestureEngine`), current timestamp.
- **Outputs:** `GestureResult | None` — only populated once the stability window is satisfied.
- **Dependencies:** pure Python.
- **Error Handling:** dynamic gestures bypass this filter entirely (PRD FR-GS-04 — they're already multi-frame by construction) — `StabilityFilter` checks `GestureResult.is_dynamic` and passes dynamic candidates straight through.

```python
class StabilityFilter:
    def __init__(self, window_ms: int = 200):
        self.window_s = window_ms / 1000.0
        self.hold_start: dict[str, tuple[str, float]] = {}  # role -> (gesture_name, start_time)
        self.already_emitted: dict[str, str] = {}  # role -> last-emitted gesture_name

    def check(self, role: str, candidate: GestureResult | None, now: float) -> GestureResult | None:
        if candidate is None:
            self.hold_start.pop(role, None)
            self.already_emitted.pop(role, None)
            return None
        if candidate.is_dynamic:
            return candidate  # dynamic gestures exempt, PRD FR-GS-04

        held_name, held_since = self.hold_start.get(role, (None, now))
        if candidate.gesture_name != held_name:
            self.hold_start[role] = (candidate.gesture_name, now)
            return None  # restart the hold, no partial credit (FR-GS-02)

        elapsed = now - held_since
        if elapsed >= self.window_s and self.already_emitted.get(role) != candidate.gesture_name:
            self.already_emitted[role] = candidate.gesture_name
            return candidate
        return None
```

---

### 3.11 CooldownFilter *(new in v1.2, extracted from GestureEngine per PRD §8.3)*

Enforces a per-(hand_role, gesture_name) cooldown so a single physical gesture motion cannot fire the same action multiple times.

- **Responsibilities:** track last-trigger timestamp per (role, gesture_name); on each stability-passed candidate, check elapsed time against the gesture-type-appropriate cooldown (`gesture_cooldown_static_ms` or `gesture_cooldown_dynamic_ms`); suppress if still within cooldown.
- **Inputs:** `GestureResult` (post-stability-filter), current timestamp, `Settings`.
- **Outputs:** `GestureResult | None`.
- **Dependencies:** pure Python.
- **Error Handling:** none required — this is a pure timer comparison with no failure modes; cooldown state is exposed read-only to `DiagnosticsManager` for the debug overlay (PRD FR-CD-03).

```python
class CooldownFilter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_trigger: dict[tuple[str, str], float] = {}

    def check(self, role: str, result: GestureResult, now: float) -> GestureResult | None:
        key = (role, result.gesture_name)
        cooldown_ms = (self.settings.gesture_cooldown_dynamic_ms if result.is_dynamic
                       else self.settings.gesture_cooldown_static_ms)
        last = self.last_trigger.get(key, 0)
        if (now - last) * 1000 < cooldown_ms:
            return None
        self.last_trigger[key] = now
        return result

    def remaining_ms(self, role: str, gesture_name: str, now: float) -> int:
        """Read-only accessor for the debug overlay (FR-CD-03)."""
        key = (role, gesture_name)
        last = self.last_trigger.get(key)
        if last is None:
            return 0
        cooldown_ms = self.settings.gesture_cooldown_static_ms  # approximation for display
        elapsed_ms = (now - last) * 1000
        return max(0, int(cooldown_ms - elapsed_ms))
```

---

### 3.12 ContextEngine *(extended in v1.2 with Context Verification Layer, PRD §8.7.3)*

Determines the active foreground application and resolves it to a normalized context string, now requiring sustained focus before committing to a context switch.

- **Responsibilities:** poll the OS for the active foreground window every 250ms (`FR-CA-01`, unchanged); resolve process name to context id via `context_map.json`; **new in v1.2:** require a newly-detected window to hold focus continuously for `context_verification_ms` (default 200ms) before accepting it as the resolved context — until then, the previously resolved context remains active.
- **Inputs:** none (polls OS on its own timer).
- **Outputs:** `str` context id (e.g. `'chrome'`, `'global'`).
- **Dependencies:** platform adapters (Section 11). Reads `context_verification_ms` from Settings.
- **Error Handling:** OS query fails → return cached context, log WARN, don't raise; process name not in `context_map.json` → resolves to `'global'`.

```python
class ContextEngine:
    POLL_INTERVAL_S = 0.25

    def __init__(self, adapter: ContextAdapter, context_map: dict, verification_ms: int = 200):
        self.adapter = adapter
        self.context_map = context_map
        self.verification_s = verification_ms / 1000.0
        self.committed_context = 'global'
        self.candidate_context: str | None = None
        self.candidate_since: float = 0.0
        self.last_poll = 0.0

    def resolve(self, now: float) -> str:
        if now - self.last_poll < self.POLL_INTERVAL_S:
            return self.committed_context
        self.last_poll = now
        try:
            process_name = self.adapter.get_active_process_name()
            new_context = self.context_map.get(process_name, 'global')
        except Exception:
            logger.warning('Context query failed, using cached context')
            return self.committed_context

        if new_context == self.committed_context:
            self.candidate_context = None
            return self.committed_context

        if new_context != self.candidate_context:
            self.candidate_context = new_context
            self.candidate_since = now
            return self.committed_context  # not yet verified (FR-CV-01)

        if (now - self.candidate_since) >= self.verification_s:
            self.committed_context = new_context  # verified, commit (FR-CV-02)
            self.candidate_context = None

        return self.committed_context
```

---

### 3.13 ActionEngine *(unchanged core logic from v1.0; now hands cursor actions to CursorController)*

Resolves a (gesture, context) pair to a concrete `Action` and dispatches it. Continuous cursor-movement actions are routed to `CursorController` (Section 3.14) instead of being dispatched directly, since cursor movement requires smoothing rather than a one-shot dispatch.

- **Responsibilities:** index active profile's mappings for O(1) lookup; resolve app-specific mapping first, fall back to `'global'`; dispatch via the correct executor; for `action_type == 'cursor_move'`, delegate to `CursorController` instead of `CommandExecutor` directly.
- **Inputs:** `GestureResult` (post-cooldown-filter), `context: str`, active profile mappings.
- **Outputs:** `ActionResult`.
- **Dependencies:** `CommandExecutor` (Section 11.3), `CursorController`.
- **Error Handling:** no mapping found → `ActionResult(success=False, action=None, error=None)`, not logged as warning unless `developer_mode`; executor raises → catch, log ERROR, `ActionResult(success=False, ...)`, continue pipeline.

---

### 3.14 CursorController *(new in v1.2, formalizes PRD §8.4)*

Owns the cursor-movement path specifically: raw index-fingertip position → smoothing → screen-space mapping → dispatch. Separated from `ActionEngine`'s general one-shot dispatch because cursor movement is continuous and stateful (it needs to remember the previous smoothed position), unlike a click or keypress.

- **Responsibilities:** map normalized index-fingertip (landmark 8) position to screen coordinates using calibrated edge buffers; apply the configured smoothing method (Exponential Moving Average by default, Moving Average, or One Euro Filter); apply `cursor_speed_multiplier`; clamp to screen bounds; support per-monitor mapping.
- **Inputs:** `HandData.landmarks[8]` (normalized), `Settings.cursor_smoothing_method`, `cursor_smoothing_alpha`, `cursor_speed_multiplier`, calibration data (Section 10) for tracking-zone bounds.
- **Outputs:** dispatches a cursor-move call via `pynput.mouse.Controller`; no data returned (terminal action).
- **Dependencies:** `pynput`. Reads calibration zone from `CalibrationManager`.
- **Error Handling:** if `pynput` dispatch raises (rare — typically only on permission-denied platforms): catch, log ERROR once per session (not every frame, to avoid log spam), suppress further cursor dispatch attempts for a short backoff period rather than retrying every single frame.

```python
class CursorController:
    def __init__(self, settings: Settings, tracking_zone: TrackingZone):
        self.settings = settings
        self.tracking_zone = tracking_zone
        self.smoothed_x: float | None = None
        self.smoothed_y: float | None = None
        self.mouse = pynput.mouse.Controller()

    def smooth_and_move(self, raw_x: float, raw_y: float, screen_w: int, screen_h: int):
        alpha = self.settings.cursor_smoothing_alpha
        if self.settings.cursor_smoothing_method == 'exponential':
            sx, sy = self._ema(raw_x, raw_y, alpha)
        elif self.settings.cursor_smoothing_method == 'moving_average':
            sx, sy = self._moving_average(raw_x, raw_y)
        else:  # 'one_euro'
            sx, sy = self._one_euro(raw_x, raw_y)

        mapped_x, mapped_y = self.tracking_zone.map_to_screen(sx, sy, screen_w, screen_h)
        clamped_x = max(0, min(screen_w - 1, mapped_x))
        clamped_y = max(0, min(screen_h - 1, mapped_y))
        self.mouse.position = (clamped_x, clamped_y)

    def _ema(self, raw_x, raw_y, alpha):
        if self.smoothed_x is None:
            self.smoothed_x, self.smoothed_y = raw_x, raw_y
        else:
            self.smoothed_x = alpha * raw_x + (1 - alpha) * self.smoothed_x
            self.smoothed_y = alpha * raw_y + (1 - alpha) * self.smoothed_y
        return self.smoothed_x, self.smoothed_y
```

> **Implementation Note — Why EMA Is the Default:** Exponential Moving Average requires O(1) memory (just the previous smoothed value) and is computationally trivial, making it the safest default for the performance budget (Section 15). Moving Average requires a small history buffer. One Euro Filter is more sophisticated (adapts smoothing strength to velocity, reducing both jitter at rest and lag during fast motion) but is offered as an advanced option, not the default, since it has more tunable parameters that could be misconfigured by non-expert users.

---

### 3.15 OverlayEngine *(extended in v1.2 with quality-warning surfaces)*

Renders the always-on-top visual feedback window. Now also renders lighting/camera quality warnings (PRD FR-VF-07) and, in Developer Mode, finger angles and normalized distances.

- **Responsibilities:** receive frame, `HandData`, `GestureResult`, `CameraQuality`, `LightingQuality` via Qt signals; draw hand skeleton; display gesture badge; display status bar (FPS, profile, context, ACTIVE/INACTIVE); display quality-warning badges when `CameraQuality.fps_ok == False` or `LightingQuality.is_low == True`; in Developer Mode, render the extended debug panel (Section 9.2).
- **Inputs:** Qt signals: `frame_ready`, `gesture_detected`, `state_changed`, `context_changed`, `quality_warning(kind: str)`.
- **Outputs:** rendered QWidget — terminal node.
- **Dependencies:** PyQt6. Read-only access to `DiagnosticsManager`.
- **Error Handling:** paint before first frame → placeholder; overlay hidden → stop repaint timer entirely (performance, not just correctness).

---

### 3.16 ProfileManager, SettingsManager, DiagnosticsManager *(structurally unchanged from v1.0; schemas extended)*

These three components retain their TRD v1.0 responsibilities, inputs, outputs, and error-handling behavior unchanged. Their schemas are extended per Section 7 (new settings fields) and Section 9 (new diagnostic event categories). See TRD v1.0 for their full original specification; this revision does not restate unchanged content.

---

## 4. Scale-Invariant Recognition — Engineering Detail

This section is the authoritative engineering reference for PRD §5 (Scale-Invariant Recognition Requirements). It is the single most important correctness property in the v1.2 recognition engine.

### 4.1 The Core Problem, Concretely

```
User at 30cm from camera:
  Thumb tip (4):  (0.52, 0.41)
  Index tip (8):  (0.58, 0.40)
  Raw distance:   0.061  (in frame-normalized units)

User at 100cm from camera (same physical gesture):
  Thumb tip (4):  (0.51, 0.50)
  Index tip (8):  (0.53, 0.50)
  Raw distance:   0.020

Same gesture. 3x difference in raw measured distance.
A fixed threshold (e.g., "trigger pinch if distance < 0.04")
works at 100cm but never triggers at 30cm, or vice versa.
```

### 4.2 The Fix: Normalize by Hand Scale

Every distance-based rule divides the raw landmark distance by `HandData.scale.smoothed_scale` (Section 3.7) before comparing to a threshold. Because palm width/height shrink and grow by the same camera-distance factor as any other landmark-to-landmark distance, the ratio is distance-invariant.

```
At 30cm:  palm_width ≈ 0.17   thumb-index distance = 0.061   ratio = 0.359
At 100cm: palm_width ≈ 0.056  thumb-index distance = 0.020   ratio = 0.357

Ratios match within noise tolerance — this is what makes the
rule scale-invariant.
```

### 4.3 Reference Implementation — Static Recognizer Rules

```python
# gestures/static_recognizer.py

def finger_angle(mcp: tuple, pip: tuple, tip: tuple) -> float:
    """Angle at the PIP joint, in degrees. ~180° = straight (extended),
    small angle = sharply bent (curled). Scale-invariant by construction
    since it's a ratio of vectors, not an absolute distance."""
    v1 = (mcp[0] - pip[0], mcp[1] - pip[1])
    v2 = (tip[0] - pip[0], tip[1] - pip[1])
    dot = v1[0]*v2[0] + v1[1]*v2[1]
    mag1 = (v1[0]**2 + v1[1]**2) ** 0.5
    mag2 = (v2[0]**2 + v2[1]**2) ** 0.5
    if mag1 == 0 or mag2 == 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))

def is_finger_extended(landmarks, mcp_id, pip_id, tip_id, angle_threshold=160) -> bool:
    return finger_angle(landmarks[mcp_id], landmarks[pip_id], landmarks[tip_id]) >= angle_threshold

FINGER_JOINTS = {
    'index':  (5, 6, 8),
    'middle': (9, 10, 12),
    'ring':   (13, 14, 16),
    'pinky':  (17, 18, 20),
}

def finger_states(landmarks) -> dict[str, bool]:
    return {name: is_finger_extended(landmarks, *joints)
            for name, joints in FINGER_JOINTS.items()}

def detect_open_palm(hand: HandData) -> GestureResult | None:
    states = finger_states(hand.landmarks)
    thumb_open = is_thumb_extended(hand.landmarks, hand.chirality)
    if not (thumb_open and all(states.values())):
        return None
    # Spread check, normalized by palm width (Priority 3)
    spread = average_fingertip_spread(hand.landmarks) / hand.scale.palm_width
    if spread < 0.55:  # tuned threshold, scale-invariant ratio
        return None
    return GestureResult('open_palm', confidence=min(1.0, spread / 0.7),
                          is_dynamic=False, hand_role=hand.role, timestamp=time.time())

def detect_pinch(hand: HandData) -> GestureResult | None:
    raw_dist = euclidean_distance(hand.landmarks[4], hand.landmarks[8])
    normalized_dist = raw_dist / hand.scale.palm_width   # Priority 3: normalized, not raw
    if normalized_dist >= 0.35:
        return None
    confidence = 1.0 - (normalized_dist / 0.35)
    return GestureResult('pinch', confidence=confidence, is_dynamic=False,
                          hand_role=hand.role, timestamp=time.time())
```

> **Code Review Rule:** Any new static gesture rule that computes `euclidean_distance(...)` and compares the result directly to a literal threshold without dividing by `hand.scale.palm_width` (or `palm_height`, where more appropriate — e.g., vertically-oriented checks) must be rejected in review. This is the single most important invariant in the gestures/ module.

### 4.4 Reference Implementation — Dynamic Recognizer Rules

```python
# gestures/dynamic_recognizer.py

def normalized_displacement(p_start: tuple, p_end: tuple, hand_scale: float) -> tuple[float, float]:
    raw_dx = p_end[0] - p_start[0]
    raw_dy = p_end[1] - p_start[1]
    return raw_dx / hand_scale, raw_dy / hand_scale

def detect_swipe_right(buffer: list[tuple], hand_scale: float,
                        dx_threshold=2.5, dy_max=1.0, vel_min=0.003) -> bool:
    """Thresholds are expressed in units of 'hand scales per
    time window', not raw frame-normalized units — this is what
    keeps swipe detection consistent at any camera distance."""
    if len(buffer) < 5:
        return False
    x0, y0, t0 = buffer[0]
    xN, yN, tN = buffer[-1]
    dx, dy = normalized_displacement((x0, y0), (xN, yN), hand_scale)
    elapsed_ms = max(tN - t0, 1)
    velocity = dx / elapsed_ms
    return dx > dx_threshold and abs(dy) < dy_max and velocity > vel_min
```

> **Why Thresholds Look Different From TRD v1.0:** In v1.0, `dx_threshold=0.25` was expressed directly in frame-normalized units (i.e., "25% of frame width"). In v1.2, displacement is first divided by `hand_scale` (a small fraction of frame width, e.g., ~0.1–0.2), so the equivalent threshold becomes a multiple of hand-scale units (e.g., `2.5`). The physical gesture being detected is identical — only the unit of measurement changed, specifically to remove the frame-width dependency that made v1.0's thresholds camera-distance-sensitive.

### 4.5 Motion History Buffer Implementation (PRD §8.5)

```python
# gestures/motion_history.py

class MotionHistoryBuffer:
    def __init__(self, max_frames: int = 20):
        self.max_frames = max_frames
        self.buffers: dict[str, deque] = {'HAND_A': deque(maxlen=max_frames),
                                           'HAND_B': deque(maxlen=max_frames)}

    def update(self, role: str, wrist_pos: tuple, now: float):
        # Store RAW (unnormalized) position + timestamp. Normalization by
        # hand_scale happens at evaluation time (detect_swipe_*), not at
        # storage time -- this matters because hand_scale itself is a
        # per-frame smoothed value (Section 3.7) and storing pre-normalized
        # data would "bake in" whatever scale was current at storage time,
        # corrupting comparisons if scale drifts mid-buffer (PRD FR-MH-03).
        self.buffers[role].append((wrist_pos[0], wrist_pos[1], now * 1000))

    def get(self, role: str) -> list[tuple]:
        return list(self.buffers[role])

    def clear(self, role: str):
        self.buffers[role].clear()
```

### 4.6 Test Strategy for Scale Invariance

Per PRD §17.1/§17.2, scale-invariance must be explicitly tested by running the same gesture fixture through the recognizer at multiple synthetic hand-scale values:

```python
# tests/unit/test_scale_invariance.py

@pytest.mark.parametrize("scale_factor", [0.5, 1.0, 2.0, 3.0])
def test_pinch_recognized_at_all_scales(pinch_landmarks_base, scale_factor):
    """Synthetically scale a known-good pinch gesture's landmarks around
    the wrist, simulating the user being closer/farther from camera,
    and assert recognition is unaffected."""
    scaled_hand = scale_hand_landmarks(pinch_landmarks_base, scale_factor)
    result = detect_pinch(scaled_hand)
    assert result is not None
    assert result.confidence > 0.5

def scale_hand_landmarks(hand: HandData, factor: float) -> HandData:
    wrist = hand.landmarks[0]
    scaled = [(wrist[0] + (x - wrist[0]) * factor,
               wrist[1] + (y - wrist[1]) * factor,
               z * factor) for x, y, z in hand.landmarks]
    estimator = HandScaleEstimator()
    return estimator.estimate(replace(hand, landmarks=scaled))
```

---

## 5. Runtime State Flow

### 5.1 Per-Frame State Diagram (v1.2)

```
Frame Captured
   │ frame is None? --Yes--> skip frame, loop
   ▼
Hand Detected
   │ 0 hands? --Yes--> clear trajectories, render, continue
   ▼
Camera Validated          (CameraValidator -- non-blocking, sets warning flag)
   ▼
Lighting Checked          (LightingMonitor -- non-blocking, sets warning flag)
   ▼
Identity Assigned + Occlusion Bridged
   │ ambiguous? --> log warning, chirality fallback
   ▼
Hand Scale Estimated
   │ scale is None? --Yes--> skip gesture eval for this hand, still render
   ▼
Primary Hand Filtered      (Dominant Hand Mode, if enabled)
   ▼
Activation Check
   │ INACTIVE --> render only, continue
   │ ACTIVE
   ▼
Gesture Candidate          (GestureEngine, scale-invariant rules)
   │ no candidate? --> render, continue
   ▼
Confidence Check
   │ below threshold? --> discard, render, continue
   ▼
Stability Check            (StabilityFilter -- static gestures only)
   │ <200ms held? --> discard (no partial credit), render, continue
   ▼
Context Resolution + Verification
   ▼
Action Mapping
   │ no mapping? --> log info, render, continue
   ▼
Cooldown Check              (CooldownFilter)
   │ within cooldown? --> suppress, render, continue
   ▼
Action Execution             (CommandExecutor or CursorController)
   ▼
Logging
   ▼
Overlay Render               (incl. quality warning badges)
```

### 5.2 State Transition Table

| Stage | Entry Condition | Exit / Next Stage | Failure Path |
|---|---|---|---|
| Frame Captured | Loop tick (target 30Hz) | → Hand Detected | frame=None → skip to next tick |
| Hand Detected | Valid RGB frame | → Camera Validated | 0 hands → clear trajectories, → Overlay Render |
| Camera Validated | Hands present | → Lighting Checked | Low FPS sustained 5s → set warning flag, continue (non-blocking) |
| Lighting Checked | Camera validated | → Identity Assigned | Low light sustained 3s → set warning flag, continue (non-blocking) |
| Identity Assigned | Lighting checked | → Hand Scale Estimated | Ambiguous match → chirality fallback, WARN log |
| Hand Scale Estimated | Identity assigned | → Primary Hand Filtered | scale=None → that hand skips gesture eval, still renders |
| Primary Hand Filtered | Scale estimated | → Activation Check | N/A — pass-through if Dominant Hand Mode off |
| Activation Check | Hand filtered | → Gesture Candidate (if ACTIVE) | INACTIVE → render only (open_palm still feeds hold-timer) |
| Gesture Candidate | ACTIVE confirmed | → Confidence Check (if rule matches) | No match → → Overlay Render |
| Confidence Check | Candidate produced | → Stability Check (if ≥ threshold) | Below threshold → discard, → Overlay Render |
| Stability Check | Confidence passed | → Context Resolution (if held 200ms, or is dynamic) | Held <200ms → discard, no partial credit |
| Context Resolution | Stability passed | → Action Mapping | OS query fails → cached context, continue |
| Action Mapping | Context resolved+verified | → Cooldown Check (if mapping exists) | No mapping → log info, → Overlay Render |
| Cooldown Check | Action resolved | → Action Execution (if cooldown elapsed) | Still cooling down → suppress, → Overlay Render |
| Action Execution | Cooldown cleared | → Logging | Executor raises → log ERROR, continue to Logging |
| Logging | Action attempted | → Overlay Render | Log write fails → silently dropped, never raises |
| Overlay Render | Always reached | → next Frame Captured | Overlay hidden → skip draw calls, still emit status signals |

### 5.3 Activation Sub-State Machine *(unchanged from v1.0)*

```
       hold/shortcut/tray toggle
    ┌─────────────────────────────┐
    │                               ▼
┌────────────┐                 ┌────────────┐
│  INACTIVE  │                 │   ACTIVE   │
└────────────┘                 └────────────┘
    ▲                               │
    └───────────────────────────────┘
       hold/shortcut/tray toggle

Default state on launch: INACTIVE  (FR-AM-06)
Both states render landmarks; only ACTIVE dispatches actions.
```

```python
class ActivationGate:
    def __init__(self, hold_duration_s: float):
        self.state = TrackingState.INACTIVE
        self.hold_duration_s = hold_duration_s
        self.hold_start = None

    def feed_gesture(self, gesture_name: str, now: float):
        if gesture_name != 'open_palm':
            self.hold_start = None
            return
        if self.hold_start is None:
            self.hold_start = now
        elif (now - self.hold_start) >= self.hold_duration_s:
            self.toggle()
            self.hold_start = None
```

---

## 6. Data Models

### 6.1 HandData *(extended in v1.2)*

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
    scale: HandScale | None = None                   # NEW v1.2 -- populated by HandScaleEstimator
    gesture_eligible: bool = True                     # NEW v1.2 -- set by PrimaryHandFilter
    is_retained: bool = False                          # NEW v1.2 -- True if from OcclusionHandler bridge
```

**Example instance:**

```python
HandData(
    landmarks=[(0.51, 0.73, 0.0), (0.49, 0.65, -0.01), ...],  # 21 entries
    chirality='Right',
    confidence=0.97,
    role='HAND_A',
    scale=HandScale(palm_width=0.17, palm_height=0.21,
                     bounding_box=(0.40, 0.55, 0.62, 0.78), smoothed_scale=0.19),
    gesture_eligible=True,
    is_retained=False,
)
```

### 6.2 GestureResult *(unchanged shape from v1.0)*

```python
@dataclass
class GestureResult:
    gesture_name: str
    confidence: float
    is_dynamic: bool
    hand_role: str
    timestamp: float
```

### 6.3 Action / ActionResult *(extended with cursor_move action_type)*

```python
@dataclass
class Action:
    action_type: str   # 'mouse' | 'keyboard' | 'system' | 'app_launch' | 'cursor_move'  (NEW: cursor_move)
    params: dict
    gesture_name: str
    context: str

@dataclass
class ActionResult:
    success: bool
    action: Action | None
    error: str | None
```

### 6.4 Quality Data Objects *(new in v1.2)*

```python
@dataclass
class CameraQuality:
    fps_ok: bool
    resolution_ok: bool
    measured_fps: float

@dataclass
class LightingQuality:
    is_low: bool
    mean_luminance: float
```

### 6.5 Profile, Settings *(Settings extended, see Section 7.1 for full schema-mirroring dataclass)*

`Profile` is unchanged from TRD v1.0. `Settings` gains the fields listed in PRD §11.2 — see Section 7.1 of this document for the complete dataclass.

### 6.6 Object Lifecycle Summary

| Object | Created By | Consumed By | Lifetime |
|---|---|---|---|
| HandData | TrackingModule, enriched by HandIdentityModule/OcclusionHandler/HandScaleEstimator/PrimaryHandFilter | GestureEngine, OverlayEngine | One frame (or bridged up to 300ms via OcclusionHandler) |
| GestureResult | GestureEngine | StabilityFilter, CooldownFilter, ActivationGate, ActionEngine, DiagnosticsManager | One frame, or held across the stability window inside StabilityFilter |
| CameraQuality | CameraValidator | OverlayEngine, DiagnosticsManager | One frame (recomputed ~1/sec) |
| LightingQuality | LightingMonitor | OverlayEngine, DiagnosticsManager | One frame (recomputed continuously, sustained-check internal) |
| Action | ActionEngine (from mapping) | CommandExecutor or CursorController | One dispatch |
| ActionResult | ActionEngine | DiagnosticsManager, OverlayEngine | One frame |
| Profile | ProfileManager | UI, ActionEngine (indirectly) | App session |
| Settings | SettingsManager | Every component | App session, atomically swapped on edit |

---

## 7. Configuration Design

### 7.1 settings.json — Full v1.2 Schema

```json
{
  "camera_index": 0,
  "target_fps": 30,
  "gesture_confidence_threshold": 0.85,
  "activation_hold_duration_s": 1.0,
  "cursor_smoothing_method": "exponential",
  "cursor_smoothing_alpha": 0.7,
  "cursor_speed_multiplier": 1.5,
  "gesture_cooldown_static_ms": 500,
  "gesture_cooldown_dynamic_ms": 1000,
  "gesture_stability_window_ms": 200,
  "dynamic_window_ms": 750,
  "motion_history_frames": 20,
  "occlusion_retention_ms": 300,
  "context_verification_ms": 200,
  "dominant_hand_mode": "off",
  "active_profile": "productivity",
  "show_overlay": true,
  "developer_mode": false
}
```

**Field Validation Rules (new/changed fields only — see TRD v1.0 for unchanged fields):**

| Field | Valid Range | Fallback if Invalid |
|---|---|---|
| `cursor_smoothing_method` | one of `exponential`, `moving_average`, `one_euro` | `exponential` |
| `gesture_cooldown_static_ms` | integer, 100–2000 | 500 |
| `gesture_cooldown_dynamic_ms` | integer, 200–3000 | 1000 |
| `gesture_stability_window_ms` | integer, 100–500 | 200 |
| `motion_history_frames` | integer, 10–40 | 20 |
| `occlusion_retention_ms` | integer, 100–1000 | 300 |
| `context_verification_ms` | integer, 50–1000 | 200 |
| `dominant_hand_mode` | one of `off`, `left`, `right` | `off` |

Validation strategy (per-field substitution, atomic file writes) is unchanged from TRD v1.0 Section 6.5.

### 7.2 Corresponding Settings Dataclass

```python
@dataclass
class Settings:
    camera_index: int = 0
    target_fps: int = 30
    gesture_confidence_threshold: float = 0.85
    activation_hold_duration_s: float = 1.0
    cursor_smoothing_method: str = 'exponential'
    cursor_smoothing_alpha: float = 0.7
    cursor_speed_multiplier: float = 1.5
    gesture_cooldown_static_ms: int = 500
    gesture_cooldown_dynamic_ms: int = 1000
    gesture_stability_window_ms: int = 200
    dynamic_window_ms: int = 750
    motion_history_frames: int = 20
    occlusion_retention_ms: int = 300
    context_verification_ms: int = 200
    dominant_hand_mode: str = 'off'
    active_profile: str = 'productivity'
    show_overlay: bool = True
    developer_mode: bool = False
```

### 7.3 profiles.json, mappings/*.json, context_map.json

Unchanged from TRD v1.0 Sections 6.2–6.4. The `cursor_move` action_type (Section 6.3 of this document) is the only addition to the mapping schema's `action_type` enum:

```json
{
  "gesture": "cursor_track",
  "context": "global",
  "action_type": "cursor_move",
  "action_params": {},
  "enabled": true
}
```

> **Note:** Cursor tracking is typically continuous (driven directly by index-fingertip position every frame while a hand is present and active) rather than gesture-triggered like a swipe or click. In most profiles, `cursor_move` is wired as an always-on background behavior in `CaptureThread` rather than a discrete mapping entry — the schema entry above exists for profiles that want to explicitly gate cursor control behind a specific gesture (e.g., Pinch-and-hold to drag).

---

## 8. Folder Structure

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
│   ├── occlusion_handler.py        # NEW v1.2
│   ├── hand_scale.py                # NEW v1.2
│   ├── primary_hand_filter.py       # NEW v1.2
│   └── errors.py
├── gestures/
│   ├── static_recognizer.py         # rewritten: angle + normalized-distance rules
│   ├── dynamic_recognizer.py        # rewritten: normalized trajectory rules
│   ├── motion_history.py            # NEW v1.2 (named buffer component)
│   ├── gesture_engine.py
│   ├── stability_filter.py          # NEW v1.2
│   ├── cooldown_filter.py           # NEW v1.2
│   ├── activation_gate.py
│   └── gesture_utils.py             # euclidean_distance, finger_angle, etc.
├── context/
│   ├── context_engine.py            # extended with verification hold-timer
│   └── adapters/
│       ├── base.py
│       ├── windows_adapter.py
│       ├── macos_adapter.py
│       └── linux_adapter.py
├── actions/
│   ├── action_engine.py
│   ├── cursor_controller.py         # NEW v1.2
│   └── executors/
│       ├── base.py
│       ├── windows_executor.py
│       ├── macos_executor.py
│       └── linux_executor.py
├── profiles/
│   └── profile_manager.py
├── calibration/                      # NEW v1.2
│   ├── calibration_manager.py
│   └── tracking_zone.py
├── overlay/
│   ├── overlay_window.py
│   ├── skeleton_renderer.py
│   └── debug_panel.py               # extended: angles, normalized distances, scale
├── settings/
│   └── settings_manager.py
├── diagnostics/
│   ├── diagnostics_manager.py
│   ├── log_format.py
│   ├── camera_validator.py          # NEW v1.2
│   └── lighting_monitor.py          # NEW v1.2
├── models/
│   └── data_models.py               # HandData, HandScale, GestureResult, Action,
│                                      # ActionResult, Profile, CameraQuality, LightingQuality
├── ui/
│   ├── main_window.py
│   ├── settings_panel.py
│   ├── mapping_editor.py
│   ├── profile_panel.py
│   ├── onboarding_wizard.py
│   ├── calibration_wizard.py        # NEW v1.2
│   └── tray_icon.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── sample_landmarks.json
│   ├── unit/
│   │   ├── test_static_gestures.py
│   │   ├── test_dynamic_gestures.py
│   │   ├── test_scale_invariance.py  # NEW v1.2
│   │   ├── test_hand_identity.py
│   │   ├── test_occlusion_handler.py # NEW v1.2
│   │   ├── test_stability_filter.py  # NEW v1.2
│   │   ├── test_cooldown_filter.py   # NEW v1.2
│   │   ├── test_activation_gate.py
│   │   ├── test_action_engine.py
│   │   ├── test_context_verification.py  # NEW v1.2
│   │   ├── test_profile_manager.py
│   │   └── test_settings_manager.py
│   ├── integration/
│   │   ├── test_pipeline_end_to_end.py
│   │   ├── test_context_switching.py
│   │   └── test_occlusion_tolerance.py    # NEW v1.2
│   └── performance/
│       └── test_fps_and_memory.py    # extended: CPU + memory budget assertions
├── assets/
│   ├── icons/
│   ├── default_mappings/
│   │   ├── default.json
│   │   ├── productivity.json
│   │   ├── presentation.json
│   │   ├── gaming.json
│   │   └── accessibility.json
│   └── context_map.json
├── requirements.txt
├── pyinstaller.spec
└── pytest.ini
```

### 8.1 Folder Responsibility Reference (new/changed folders only)

| Folder | Purpose | Allowed Contents |
|---|---|---|
| `tracking/occlusion_handler.py`, `hand_scale.py`, `primary_hand_filter.py` | Same domain as `tracking/` overall — landmark-adjacent processing prior to gesture evaluation | Pure Python + NumPy geometry. No PyQt6, no OS-automation imports. |
| `gestures/motion_history.py`, `stability_filter.py`, `cooldown_filter.py` | Recognition-pipeline filters that sit between raw rule evaluation and downstream action mapping | Pure Python timers/deques. No camera or OS-automation imports — consistent with the rest of `gestures/`. |
| `actions/cursor_controller.py` | The continuous cursor-movement dispatch path, distinct from one-shot `ActionEngine` dispatch | `pynput` only. May read calibration data but does not import `gestures/` directly — receives already-resolved positions from `app/core.py`. |
| `calibration/` | Calibration wizard's business logic (distinct from its UI, which lives in `ui/calibration_wizard.py`) | `CalibrationManager`, `TrackingZone`. Writes results to `settings/` via `SettingsManager`, doesn't write JSON directly itself. |
| `diagnostics/camera_validator.py`, `lighting_monitor.py` | Quality-monitoring components, grouped with diagnostics since their output is informational/advisory, not pipeline-blocking | OpenCV/NumPy only. |

All other folders retain their TRD v1.0 purpose and constraints unchanged.

---

## 9. Diagnostics Architecture

### 9.1 Logging Pipeline *(categories extended in v1.2)*

```
[12:31:42.103] [INFO]  [camera]     Camera started  {device: 0, resolution: '640x480', fps: 30}
[12:31:42.500] [INFO]  [camera]     Camera quality check  {fps_ok: true, measured_fps: 29.2}
[12:31:43.001] [INFO]  [lighting]   Lighting check  {brightness: 142, is_low: false}
[12:31:44.210] [INFO]  [gesture]    Gesture candidate  {gesture: 'swipe_right', confidence: 0.91, hand: 'HAND_A'}
[12:31:44.211] [DEBUG] [gesture]    Stability check passed  {gesture: 'swipe_right', held_ms: 210}
[12:31:44.212] [INFO]  [context]    Context resolved  {process: 'chrome.exe', context: 'chrome'}
[12:31:44.213] [DEBUG] [gesture]    Cooldown check passed  {gesture: 'swipe_right', hand: 'HAND_A'}
[12:31:44.214] [INFO]  [action]     Action executed  {type: 'keyboard', params: 'alt+right', status: 'success'}
[12:31:50.004] [WARN]  [camera]     Sustained low FPS  {measured_fps: 18.3, duration_s: 5.2}
[12:31:55.900] [INFO]  [activation] State changed  {from: 'inactive', to: 'active', method: 'open_palm_hold'}
[12:32:01.004] [WARN]  [tracking]   Hand occluded, bridging  {role: 'HAND_A', retained_ms: 120}
[12:32:01.300] [WARN]  [tracking]   Occlusion window expired  {role: 'HAND_A'}
[12:32:05.004] [ERROR] [action]     Action dispatch failed  {type: 'keyboard', error: 'permission_denied'}
```

### 9.2 Logger Categories (v1.2 additions)

| Category Tag | Emitting Component(s) | Typical Events |
|---|---|---|
| `camera` | CameraModule, CameraValidator | Camera started, frame dropped, sustained low FPS |
| `lighting` | LightingMonitor | Lighting check results, sustained low-light warning |
| `tracking` | TrackingModule, HandIdentityModule, OcclusionHandler, HandScaleEstimator | Hand detected/lost, occlusion bridged/expired, scale estimation skipped |
| `gesture` | GestureEngine, StabilityFilter, CooldownFilter | Candidate detected, stability passed/failed, cooldown suppressed/passed |
| `activation` | ActivationGate | State changed, method used |
| `context` | ContextEngine | Context resolved, verification pending/committed |
| `action` | ActionEngine, CursorController | Action executed, dispatch failed |
| `profile` | ProfileManager | Profile loaded, mapping conflict |
| `settings` | SettingsManager | Invalid field reverted, file corrupted |
| `calibration` | CalibrationManager | Calibration started/completed, step results |

### 9.3 Debug Overlay — Developer Mode (extended)

```
┌─────────────────────────────────────────────────────────────┐
│ FPS: 29 (OK)   Profile: Productivity   Context: Chrome         │
│ State: ACTIVE   Hand A: Right   Hand B: --                     │
│ Lighting: OK (142)   Camera: OK                                 │
│ Gesture: swipe_right (conf: 0.91)   Stability: held 210ms       │
│ Cooldown: 340ms remaining                                       │
│                                                                   │
│ [ webcam preview, landmark IDs + finger angles labeled ]         │
│                                                                   │
│ Landmark 0  (wrist):  x=0.51 y=0.73 z=0.00                      │
│ Landmark 8  (index):  x=0.43 y=0.29 z=-0.02                     │
│ Finger angles:  index=178° middle=42° ring=38° pinky=170°        │
│ Hand scale: palm_width=0.17 palm_height=0.21 smoothed=0.190      │
│ Normalized thumb-index dist: 0.083 (raw 0.0158 / palm_width 0.17)│
│                                                                   │
│ Motion history (HAND_A, 18/20 frames):                            │
│   normalized velocity: 0.0041 hand-scales/ms                      │
│                                                                   │
│ Gesture State Machine:                                            │
│   HAND_A: TRIGGERED (swipe_right) -> cooldown                     │
│   HAND_B: IDLE                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 9.4 Error Recovery Policy Table (v1.2 additions)

| Error Condition | Recovery Implementation | Owning Component |
|---|---|---|
| Sustained low camera FPS | Set non-blocking overlay warning; continue processing at degraded rate; no auto-retry needed since this isn't a connection failure | CameraValidator |
| Sustained low lighting | Set non-blocking overlay warning; advisory only, never blocks gesture processing | LightingMonitor |
| Hand scale cannot be computed | Skip gesture evaluation for that hand/frame only; do not fall back to raw-pixel rules | HandScaleEstimator → GestureEngine |
| Occlusion window expires | Release hand back to normal re-identification path (existing HandIdentityModule behavior) | OcclusionHandler |
| Context verification never settles (rapid flapping) | Previously committed context remains active indefinitely until a candidate holds for the full verification window — there is no timeout-forced commit, by design, since committing to a flapping window's context is worse than staying on the last stable one | ContextEngine |

All other error-recovery rows are unchanged from TRD v1.0 Section 8.3.

---

## 10. Calibration Subsystem

*(New in v1.2, implements PRD §15)*

### 10.1 CalibrationManager

- **Responsibilities:** orchestrate the 4-step calibration flow (Camera Position, Sensitivity, Cursor Speed, Tracking Area); persist results to `settings.json` (and a dedicated `tracking_zone` structure) on completion; support being skipped entirely (PRD FR-CAL-03).
- **Inputs:** live `HandData` stream during the wizard (routed from `CaptureThread` while the wizard is open), user interactions from `ui/calibration_wizard.py`.
- **Outputs:** updated `Settings` fields (`gesture_confidence_threshold`, `cursor_speed_multiplier`) and a `TrackingZone` object consumed by `CursorController`.
- **Dependencies:** `SettingsManager` for persistence. No dependency on `gestures/` internals — it observes already-computed `HandData` the same way `OverlayEngine` does.
- **Error Handling:** if calibration is interrupted (wizard closed mid-flow), no partial settings are written — calibration is all-or-nothing per session, falling back to whatever defaults or prior calibration already existed.

```python
@dataclass
class TrackingZone:
    top_left: tuple[float, float]      # normalized frame coordinates
    bottom_right: tuple[float, float]

    def map_to_screen(self, hand_x: float, hand_y: float, screen_w: int, screen_h: int) -> tuple[int, int]:
        zx0, zy0 = self.top_left
        zx1, zy1 = self.bottom_right
        # Map hand position within the calibrated zone to full screen space
        norm_x = (hand_x - zx0) / (zx1 - zx0) if zx1 != zx0 else 0.5
        norm_y = (hand_y - zy0) / (zy1 - zy0) if zy1 != zy0 else 0.5
        return int(norm_x * screen_w), int(norm_y * screen_h)

class CalibrationManager:
    def __init__(self, settings_manager: SettingsManager):
        self.settings_manager = settings_manager
        self.collected_gesture_samples: list[GestureResult] = []

    def suggest_confidence_threshold(self) -> float:
        """Step 2: based on observed confidence scores during the user's
        practice gestures, suggest a threshold with margin below the
        observed minimum confident match."""
        if not self.collected_gesture_samples:
            return 0.85  # default
        min_observed = min(g.confidence for g in self.collected_gesture_samples)
        return max(0.50, min_observed - 0.10)  # safety margin

    def complete(self, tracking_zone: TrackingZone, confidence_threshold: float,
                 cursor_speed: float):
        self.settings_manager.update(
            gesture_confidence_threshold=confidence_threshold,
            cursor_speed_multiplier=cursor_speed,
        )
        # TrackingZone persisted alongside settings, consumed by CursorController
        self.settings_manager.save_tracking_zone(tracking_zone)
```

### 10.2 Wizard Flow (UI-level, ui/calibration_wizard.py)

| Step | PRD Reference | UI Behavior | Manager Call |
|---|---|---|---|
| 1. Camera Position | §15.1 | Show live preview, ask user to wave across intended gesture area | `CalibrationManager` observes bounding-box coverage, confirms visibility |
| 2. Sensitivity | §15.1 | Prompt user to perform each static gesture once | `suggest_confidence_threshold()` after samples collected |
| 3. Cursor Speed | §15.1 | Show live cursor response to hand movement, user adjusts a slider | Direct binding to `cursor_speed_multiplier` for live preview |
| 4. Tracking Area | §15.1 | User marks corners of intended gesture zone (click-and-drag or hand-gesture corners) | Produces `TrackingZone(top_left, bottom_right)` |

- **FR-CAL-01 / FR-CAL-04:** wizard is offered at first-run onboarding and re-accessible from Settings; must complete in under 3 minutes — enforced informally via UI flow design (4 short steps), not a hard software timeout.
- **FR-CAL-02:** results persisted immediately via `CalibrationManager.complete()`.
- **FR-CAL-03:** a "Skip" button is present on every step; skipping at any point falls back to documented defaults for any steps not completed.

---

## 11. Cross-Platform Strategy

*(Unchanged from TRD v1.0 — included here for completeness since this is a single consolidated document.)*

### 11.1 Adapter Pattern

```
              ContextEngine / ActionEngine
                 (platform-agnostic)
                         │
                         ▼
        ContextAdapter (ABC) / CommandExecutor (ABC)
            │              │              │
    ┌───────▼──┐   ┌──────▼─────┐   ┌───▼────────┐
    │ Windows   │   │ macOS       │   │ Linux       │
    │ (pywin32) │   │ (pyobjc)    │   │ (Xlib)      │
    └───────────┘   └─────────────┘   └─────────────┘

    Selected once at startup via platform.system()
```

### 11.2 ContextAdapter Implementations

| Platform | Library / API | Notes |
|---|---|---|
| Windows | pywin32 (`win32gui`, `win32process`) | `GetForegroundWindow()` → PID → `GetModuleFileNameEx()`, cached per PID |
| macOS | pyobjc (`AppKit.NSWorkspace`) | `frontmostApplication()` returns active app directly |
| Linux | Xlib (`python-xlib`) | Queries `_NET_ACTIVE_WINDOW`; degrades to `'global'` on pure-Wayland sessions, logged once at INFO |

### 11.3 CommandExecutor Implementations

| Action Category | Library Used | Platform Notes |
|---|---|---|
| Cursor movement | `pynput.mouse.Controller` (via CursorController) | Lowest latency path, identical across OSes |
| Clicks (pinch/OK) | `pynput.mouse.Controller` | Consistent low-latency dispatch |
| Keyboard shortcuts | `pynput.keyboard.Controller` | Context-managed press/release pairs avoid stuck-key bugs |
| Volume/Brightness | `pycaw` (Win), `osascript` (macOS), `amixer`/`brightnessctl` (Linux) | Each OS executor implements independently behind shared interface |
| Screenshot | `pyautogui.screenshot()` | Cross-platform |
| Lock screen | `LockWorkStation` (Win), `osascript` (macOS), `loginctl` (Linux) | Non-fatal if denied, logged WARN |
| App launch | `subprocess.Popen()` | Path resolution differs per OS |

### 11.4 Permissions by Platform

| Platform | Required Permission | Failure Mode |
|---|---|---|
| Windows | Webcam access only | `CameraUnavailableError` → onboarding wizard |
| macOS | Camera + Accessibility (for synthetic input) | Camera denial → wizard; Accessibility denial → per-action dispatch failures, logged, one-time notification |
| Linux | Camera (`/dev/video*`), X11 access | Rare on logged-in desktop sessions; caught and logged if it occurs |

---

## 12. Packaging Strategy

*(Unchanged from TRD v1.0; MediaPipe bundling note remains critical for v1.2 since no new native dependencies were added.)*

### 12.1 Build Mode

One-folder (`--onedir`) is the recommended default for the installed application (faster startup than `--onefile`), wrapped in a per-platform installer so end users still experience a single download.

### 12.2 PyInstaller Spec (key excerpt)

```python
a = Analysis(
    ['main.py'],
    datas=[
        ('assets/icons', 'assets/icons'),
        ('assets/default_mappings', 'assets/default_mappings'),
        ('assets/context_map.json', 'assets'),
        (mediapipe_model_path(), 'mediapipe/modules'),  # critical — see note below
    ],
    hiddenimports=[
        'pynput.keyboard._win32', 'pynput.mouse._win32',
        'pynput.keyboard._darwin', 'pynput.mouse._darwin',
        'pynput.keyboard._xorg', 'pynput.mouse._xorg',
    ],
    excludes=['tkinter', 'matplotlib', 'scipy'],
)
```

> **Implementation Note — MediaPipe Bundling:** MediaPipe loads its hand-landmark model from a path relative to its installed package location. PyInstaller's static analysis does not always discover these data files automatically — they must be explicitly bundled via `datas`, or the packaged app will fail on first `TrackingModule` init despite working from source.

### 12.3 Per-Platform Output Artifact

| Platform | PyInstaller Output | Final Artifact |
|---|---|---|
| Windows | `GestureOS/` folder | Inno Setup → `GestureOS_Setup.exe` (Start Menu entry, optional auto-start) |
| macOS | `GestureOS.app` | Code-signed, notarized, wrapped in `.dmg` |
| Linux | `GestureOS/` folder | AppImage (primary), `.deb` (secondary) |

### 12.4 Startup Self-Check

On first launch: verify bundled MediaPipe model file exists; verify ≥1 camera device enumerable; verify `~/.gestureos/` writable; verify default mapping/profile JSON files were copied successfully. Any failure shows a specific diagnostic dialog rather than a generic crash.

---

## 13. Testing Architecture

### 13.1 Test Pyramid

```
        ▲
       ╱ ╲      performance/  (few, slow — nightly + pre-release)
      ╱───╲     - test_fps_and_memory.py (now also asserts CPU/memory budgets)
     ╱     ╲
    ╱───────╲   integration/  (moderate count, every PR)
   ╱         ╲  - test_pipeline_end_to_end.py
  ╱           ╲ - test_context_switching.py
 ╱─────────────╲- test_occlusion_tolerance.py        (NEW v1.2)
╱               ╲ unit/  (large count, every commit, <5s)
╲_________________╱ - test_static_gestures.py, test_dynamic_gestures.py
                      test_scale_invariance.py         (NEW v1.2)
                      test_hand_identity.py, test_occlusion_handler.py (NEW)
                      test_stability_filter.py (NEW), test_cooldown_filter.py (NEW)
                      test_activation_gate.py, test_action_engine.py
                      test_context_verification.py (NEW)
                      test_profile_manager.py, test_settings_manager.py
```

### 13.2 Unit Testing — Key New Fixtures

```python
# conftest.py additions for v1.2

@pytest.fixture
def pinch_landmarks_close():
    """Pinch gesture performed close to camera — larger raw distances."""
    return _load_fixture('pinch_close.json')

@pytest.fixture
def pinch_landmarks_far():
    """Same physical pinch, performed far from camera — smaller raw distances."""
    return _load_fixture('pinch_far.json')

@pytest.fixture
def occluded_hand_sequence():
    """A 15-frame sequence where landmarks are valid for frames 0-4,
    missing/low-confidence for frames 5-9 (simulated occlusion < 300ms
    at 30fps), then valid again for frames 10-14."""
    return _load_fixture('occlusion_sequence.json')
```

### 13.3 Example — Scale Invariance Unit Test

```python
def test_pinch_recognized_close_and_far(pinch_landmarks_close, pinch_landmarks_far):
    """Same gesture, different camera distance, must both recognize as pinch."""
    estimator = HandScaleEstimator()
    hand_close = estimator.estimate(pinch_landmarks_close)
    hand_far = estimator.estimate(pinch_landmarks_far)

    result_close = detect_pinch(hand_close)
    result_far = detect_pinch(hand_far)

    assert result_close is not None
    assert result_far is not None
    # Confidence should be comparable -- not just "both detected" but
    # similarly confident, proving the normalization is consistent
    assert abs(result_close.confidence - result_far.confidence) < 0.15
```

### 13.4 Example — Occlusion Tolerance Integration Test

```python
def test_gesture_survives_brief_occlusion(occluded_hand_sequence):
    handler = OcclusionHandler(retention_ms=300)
    stability = StabilityFilter(window_ms=200)
    engine = GestureEngine(settings=test_settings())

    results = []
    for frame_hands, t in occluded_hand_sequence:  # t in seconds, ~33ms apart
        bridged = handler.bridge_gaps(frame_hands, now=t)
        candidates = engine.evaluate(bridged, now=t)
        for c in candidates:
            stable = stability.check(c.hand_role, c, now=t)
            if stable:
                results.append(stable)

    # Despite ~150ms of simulated occlusion in the middle of the sequence
    # (within the 300ms retention window), the gesture should still
    # register exactly once.
    assert len(results) == 1
```

### 13.5 Example — Stability and Cooldown Unit Tests

```python
def test_single_frame_flicker_does_not_trigger():
    f = StabilityFilter(window_ms=200)
    now = 0.0
    candidate = GestureResult('open_palm', 0.9, False, 'HAND_A', now)
    assert f.check('HAND_A', candidate, now) is None       # first frame, starts hold
    assert f.check('HAND_A', None, now + 0.033) is None     # gesture disappears (flicker)
    # Re-appearing resets the hold -- no partial credit
    assert f.check('HAND_A', candidate, now + 0.066) is None

def test_cooldown_suppresses_repeated_trigger():
    settings = test_settings(gesture_cooldown_static_ms=500)
    f = CooldownFilter(settings)
    result = GestureResult('pinch', 0.9, False, 'HAND_A', 0.0)
    assert f.check('HAND_A', result, now=0.0) is not None     # first trigger fires
    assert f.check('HAND_A', result, now=0.1) is None          # within cooldown, suppressed
    assert f.check('HAND_A', result, now=0.6) is not None      # cooldown elapsed, fires again
```

### 13.6 Performance Testing — Budget Assertions (extended)

```python
def test_performance_budgets_all_met(running_app_30min_session):
    session = running_app_30min_session
    avg_fps = sum(session.fps_log) / len(session.fps_log)
    avg_cpu = sum(session.cpu_samples) / len(session.cpu_samples)
    peak_memory_mb = max(session.memory_samples)

    assert avg_fps >= 25, f'FPS {avg_fps} below target'
    assert avg_cpu < 20, f'CPU {avg_cpu}% exceeds 20% budget'
    assert peak_memory_mb < 300, f'Memory {peak_memory_mb}MB exceeds 300MB budget'
```

### 13.7 Coverage Target

Unchanged: ≥80% line coverage across `gestures/`, `actions/`, `profiles/`, `settings/`, `tracking/`. New v1.2 modules (`hand_scale.py`, `occlusion_handler.py`, `stability_filter.py`, `cooldown_filter.py`, `primary_hand_filter.py`, `cursor_controller.py`, `calibration_manager.py`) are held to the same 80% bar.

---

## 14. Security & Privacy Architecture

*(Unchanged from TRD v1.0 — restated briefly for document completeness; no v1.2 PRD changes affect privacy posture.)*

### 14.1 Data Flow Boundary

```
┌─────────────────────────────────────────────────────────┐
│                    GestureOS Process                       │
│                                                              │
│   Webcam → Frames → Landmarks → Gestures → Actions          │
│                  (never persisted to disk)                  │
│                                                              │
│   ~/.gestureos/  (settings, profiles, mappings, logs)       │
│                   ◄── the ONLY data written to disk         │
└─────────────────────────────────────────────────────────────┘
                              │
                              X   <- no outbound network call exists
                              ▼
                         (nothing)
```

- No frame, landmark, or gesture data is ever written to disk
- Log files contain gesture names, confidence, timestamps — never raw landmarks or frame images, even in `developer_mode`
- No HTTP client library imported anywhere in the core pipeline — enforced by CI lint rule scanning for forbidden imports (`requests`, `urllib`, `socket`, etc.)
- Lighting/camera-quality monitoring (new in v1.2) operates entirely in-memory on the current frame — no image data is logged or persisted as part of these checks

### 14.2 Permission Handling

Webcam access via OS-native permission dialog on first launch. macOS Accessibility permission requested on first synthetic-input dispatch attempt, not preemptively.

---

## 15. Performance Budget Engineering

*(New section in v1.1 TRD, implements PRD §16 — Performance Budgets.)*

### 15.1 Budget Targets (from PRD)

| Metric | Target |
|---|---|
| FPS | ≥ 25 |
| Detection Latency | < 100 ms |
| End-to-End Action Latency | < 150 ms |
| CPU Usage | < 20% (single core average) |
| Memory Usage | < 300 MB |

### 15.2 Where the New v1.2 Components Spend Budget

The pipeline grew from 8 stages (v1.0) to 17 stages (v1.2, Section 5.1). Each new stage must be evaluated for its marginal cost against the tightened 20% CPU budget.

| New Stage | Expected Cost | Mitigation if Over Budget |
|---|---|---|
| CameraValidator | Negligible — rolling average over a deque, recomputed ~1/sec, not every frame | N/A |
| LightingMonitor | Low — one `cv2.cvtColor` + `.mean()` per frame, both vectorized | Could be throttled to every 3rd frame if profiling shows otherwise |
| HandScaleEstimator | Negligible — two Euclidean distances + a 5-element moving average | N/A |
| OcclusionHandler | Negligible — dict lookups and timestamp comparisons only | N/A |
| StabilityFilter / CooldownFilter | Negligible — dict lookups and timestamp comparisons only | N/A |
| Context Verification | None — reuses the existing 250ms poll, adds only a timestamp comparison | N/A |

> **Engineering Judgment:** None of the v1.2 additions are expected to meaningfully threaten the performance budget on their own — they are all O(1) or small-constant-factor operations. The dominant cost in the pipeline remains MediaPipe inference (TrackingModule), which is unchanged in v1.2. The primary performance risk is therefore unchanged from TRD v1.0's risk register (Section 16), not newly introduced by these additions.

### 15.3 Profiling Harness

```python
# Run during CP-7 and on every release candidate
import cProfile, pstats

def profile_one_minute_session():
    profiler = cProfile.Profile()
    profiler.enable()
    run_capture_loop(duration_s=60)
    profiler.disable()
    stats = pstats.Stats(profiler).sort_stats('cumulative')
    stats.print_stats(20)  # top 20 functions by cumulative time
```

CI fails the release-candidate build if `test_performance_budgets_all_met` (Section 13.6) fails on the reference hardware profile (Intel Core i5, 8GB RAM, 720p webcam, per PRD).

---

## 16. Technical Risks

*(Extends TRD v1.0's risk register with v1.2-specific engineering risks; v1.0 risks not superseded remain valid and are not repeated here in full — see TRD v1.0 Section 13 for GIL contention, PyInstaller/MediaPipe packaging, Wayland gap, pynput inconsistencies, and Settings thread-safety, all still applicable unchanged.)*

| Risk | Severity | Technical Impact | Mitigation |
|---|---|---|---|
| Scale normalization introduces a new failure mode: `HandScale` estimation noise | Medium | If `smoothed_scale` is itself noisy (e.g., due to rapid hand rotation changing apparent palm width), normalized distances could become unstable even though raw distances were fine | 5-frame moving average (Section 3.7) specifically targets this; performance testing (§17.2 distance testing in PRD) should also validate stability during hand rotation, not just static distance |
| Pipeline depth increase (8→17 stages) adds per-frame Python call overhead | Low-Medium | More function calls per frame could add latency even if each is individually cheap | Profiling harness (15.3) run every release candidate; stages are simple enough that this is expected to remain well within the 150ms end-to-end budget, but must be verified, not assumed |
| Stability window (200ms) interacts with Activation Mode's hold timer (1000ms) in a non-obvious way | Low | Open Palm must simultaneously satisfy the 200ms stability window (to count as a valid "open_palm" gesture at all) AND the 1000ms activation hold — these are sequential, not conflicting, but an implementer could mistakenly conflate the two timers | `ActivationGate.feed_gesture()` (Section 5.3) only receives gesture names that have already passed `StabilityFilter` — this ordering must be preserved in `app/core.py`'s pipeline wiring, documented explicitly here to prevent reordering bugs |
| Calibration wizard's "suggest confidence threshold" heuristic could suggest a poor value for atypical users | Low | A user with unusually high gesture-to-gesture confidence variance might get a suggested threshold that's still prone to false negatives or positives | Suggested value is a starting point, not locked in — Settings UI still allows manual override after calibration; this is explicitly a heuristic, not a guarantee |
| CursorController and ActionEngine now have a split dispatch path (cursor vs. everything else) | Low | Two code paths for "doing an action" increases the surface area for inconsistent error handling or logging if not kept disciplined | Both paths funnel through the same `DiagnosticsManager` logging calls and the same `ActionResult` data shape (Section 6.3), keeping behavior consistent despite the split |

---

## 17. Future Extensibility

*(Extends TRD v1.0 Section 14 with v1.2-aware extension points. Out-of-scope items from TRD v1.0 — ML-based recognition, cloud sync, multi-user support — remain explicitly out of scope and are not restated.)*

### 17.1 New Extension Points Introduced by v1.2

| Component | Extension Point | Example Future Capability |
|---|---|---|
| `gestures/motion_history.py` | `MotionHistoryBuffer` is already generic over (x,y,timestamp) tuples — could be extended to store full per-finger landmark history, not just wrist position, without changing its public interface | Future gestures involving multi-finger motion patterns, not just whole-hand trajectory |
| `calibration/` | `CalibrationManager` already separates "collect samples" from "suggest settings" — a future auto-recalibration feature (e.g., periodic re-calibration suggestion if false-trigger rate climbs) could hook into the same suggestion logic | Adaptive recalibration prompts based on observed false-trigger telemetry (local-only, per Section 14's privacy constraints) |
| `tracking/hand_scale.py` | `HandScale` already exposes a bounding box, not just a scalar — a future feature could use bounding-box aspect ratio as an additional normalization signal | Detecting hand rotation/tilt as a distinct signal from scale, for gestures that care about orientation |
| `actions/cursor_controller.py` | The smoothing-method enum (`exponential` / `moving_average` / `one_euro`) is already pluggable — adding a 4th method is a one-function addition | Predictive smoothing (e.g., Kalman filter) for even lower perceived latency |

### 17.2 Explicitly Deferred (Unchanged Stance from TRD v1.0)

> Trained ML models for gesture recognition, cloud storage of mappings/settings, and multi-user/multi-account support remain explicitly out of architectural scope. SQLite remains a noted-but-unadopted future option per PRD §11.

---

*End of GestureOS TRD v1.1*
