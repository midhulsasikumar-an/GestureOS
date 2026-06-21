# Product Requirements Document — GestureOS

**Version:** 1.2.0 — Revised Release
**Document Status:** Updated Draft
**Product Name:** GestureOS
**Classification:** Desktop Application / Computer Vision / Rule-Based AI
**Revision Date:** June 2026
**Changes in v1.2:** Scale-invariant recognition, hand scale estimation, gesture stability window, cooldown system (formalized), cursor smoothing (formalized), motion history buffer, temporary occlusion handling, primary hand selection, camera validation, lighting quality detection, context verification layer, calibration requirement, performance budgets, expanded diagnostics, error recovery requirements, engineering risk matrix, deployment requirements.

> This document supersedes PRD v1.1. All v1.1 requirements remain in force except where explicitly revised below. No requirement from v1.1 has been removed — v1.2 is additive and clarifying.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Vision](#2-product-vision)
3. [User Stories](#3-user-stories)
4. [Gesture Recognition Strategy](#4-gesture-recognition-strategy)
5. [Scale-Invariant Recognition Requirements](#5-scale-invariant-recognition-requirements)
6. [Activation Mode](#6-activation-mode)
7. [Functional Requirements](#7-functional-requirements)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [Technical Architecture](#9-technical-architecture)
10. [Runtime State Flow](#10-runtime-state-flow)
11. [Storage Design](#11-storage-design)
12. [Debugging & Diagnostics](#12-debugging--diagnostics)
13. [Recommended Project Structure](#13-recommended-project-structure)
14. [Development Checkpoints](#14-development-checkpoints)
15. [Calibration Requirement](#15-calibration-requirement)
16. [Performance Budgets](#16-performance-budgets)
17. [Testing Plan](#17-testing-plan)
18. [Risks & Challenges](#18-risks--challenges)
19. [Engineering Risks & Mitigation Matrix](#19-engineering-risks--mitigation-matrix)
20. [Deployment Requirements](#20-deployment-requirements)
21. [Success Metrics & Acceptance Criteria](#21-success-metrics--acceptance-criteria)
22. [UI Requirements](#22-ui-requirements)

---

## 1. Executive Summary

GestureOS is a real-time gesture recognition system that enables users to control their computers entirely through hand gestures captured via a standard webcam. It operates as an intelligent operating layer sitting between the user and the OS, translating natural hand movements into precise, context-aware system commands.

> **Core Mission:** Eliminate the dependency on physical input devices by providing a fast, accurate, and extensible touchless interaction layer for desktop operating systems — using only rule-based geometric recognition, zero machine learning models, full local processing, and recognition that remains reliable regardless of the user's distance from the camera.

### 1.1 Key Highlights

- Real-time hand tracking at 25+ FPS with sub-100ms detection latency
- Rule-based recognition: 8+ static and 8+ dynamic gestures using landmark geometry
- **Scale-invariant recognition** — gestures work identically whether the user is close to or far from the camera (v1.2)
- Activation Mode: prevents accidental triggers during natural hand movement
- Persistent hand identity tracking — hands maintain roles even when they cross
- **Gesture stability and cooldown systems** prevent flicker and double-triggers (v1.2)
- **Cursor smoothing** via configurable filtering (v1.2, formalizes v1.1 smoothing requirement)
- Context-aware gesture mapping adapting to the active application, with **context stability verification** (v1.2)
- Multi-profile support: Presentation, Productivity, Gaming, Accessibility
- Full local processing — zero cloud dependency, maximum privacy
- No ML models required — all recognition is deterministic and rule-based

### 1.2 Target Platforms

| Windows 10/11 | macOS 12+ | Ubuntu 20.04+ | Python 3.9+ |
|---|---|---|---|

---

## 2. Product Vision

### 2.1 Vision Statement

> To redefine human-computer interaction by making touchless, gesture-based control as natural, reliable, and productive as traditional keyboard-and-mouse input — and accessible to everyone, regardless of their distance from the camera or their environment's lighting conditions.

### 2.2 Problem Statement

Traditional input devices impose physical and ergonomic constraints on users. This creates barriers for:

- Users with motor impairments or repetitive strain injuries
- Presenters who need slide control without returning to a laptop
- Professionals operating in sterile or cleanroom environments
- Streamers and content creators requiring hands-free interaction
- Individuals seeking more intuitive HCI paradigms

### 2.3 Solution Overview

GestureOS leverages MediaPipe Hands for landmark detection and applies deterministic geometric rules to classify gestures. No ML model training is required — recognition logic is fully transparent, explainable, and tuneable through configuration parameters. Critically, recognition is **scale-invariant**: it does not depend on raw pixel measurements that change as the user moves closer to or farther from the camera.

### 2.4 Value Proposition

| Value Driver | Description |
|---|---|
| Hands-Free Control | Complete OS interaction without touching physical peripherals |
| Accessibility | Enables users with limited mobility to interact naturally |
| Safe Activation Mode | Gestures are ignored unless the user explicitly activates tracking |
| Distance-Independent | Works the same whether the user sits close or stands far from the camera |
| Presentation Control | Advance slides and control media from across the room |
| Productivity | Execute complex shortcuts with single intuitive gestures |
| Privacy-First | All processing is local — no cloud upload, no data collection |
| Zero ML Overhead | Rule-based recognition — no training, no model files, fully transparent |

---

## 3. User Stories

### 3.1 Primary User Personas

**Persona A — The Presenter (Maya, 34, Marketing Manager)**
Maya delivers weekly client presentations and needs to control her deck from across the room — sometimes near the screen, sometimes at the back of the room. She activates GestureOS with an Open Palm hold, swipes to advance slides, and deactivates when fielding questions to avoid accidental triggers during natural conversation gestures. Her gestures must work the same near or far from the camera.

**Persona B — The Accessibility User (Rajan, 45, Software Architect)**
Rajan suffers from repetitive strain injury. He uses GestureOS as his primary pointing device, relying on index-finger cursor tracking and pinch-to-click. He activates tracking when at his desk and deactivates during calls. He needs smooth, jitter-free cursor movement.

**Persona C — The Developer/Enthusiast (Priya, 22, CS Student)**
Priya wants to explore gesture-based HCI. She configures GestureOS shortcuts for her coding workflow and uses the debug overlay to understand landmark geometry, finger angles, and normalized distances to tune gesture thresholds.

### 3.2 User Stories

| ID | As a... | I want to... | Priority |
|---|---|---|---|
| US-01 | Presenter | control my slides with hand swipes so I can stay away from my laptop | P0 |
| US-02 | Accessibility user | move the cursor with my index finger so I can avoid using a mouse | P0 |
| US-03 | Any user | activate gesture tracking intentionally so accidental movements are ignored | P0 |
| US-04 | Any user | receive visual feedback of detected gestures so I know when gestures are triggered | P0 |
| US-05 | Any user | configure gesture sensitivity so I can reduce accidental triggers | P0 |
| US-06 | Educator | pause and resume video playback with an open palm | P1 |
| US-07 | Developer | see landmark IDs, angles, and normalized distances on screen so I can tune gesture rules | P1 |
| US-08 | Power user | export and import gesture profiles across machines | P1 |
| US-09 | Any user | launch applications with gestures so I can access tools faster | P1 |
| US-10 | Any user | assign different roles to left and right hands independently | P2 |
| US-11 | Presenter (far from camera) | have my gestures recognized the same way whether I'm close to or far from the camera | P0 |
| US-12 | Any user | have a smooth, non-jittery cursor instead of one that shakes | P0 |
| US-13 | Any user | run a calibration wizard so the system adapts to my camera position and space | P1 |
| US-14 | Any user | be warned if my lighting or camera quality is too poor for reliable tracking | P1 |
| US-15 | Multi-hand user | designate a primary/dominant hand so extra hands in frame don't interfere | P2 |

---

## 4. Gesture Recognition Strategy

> **Recognition Philosophy:** GestureOS uses exclusively rule-based geometric recognition. Every gesture is defined by measurable relationships between MediaPipe landmarks — distances, angles, relative positions, and motion vectors. No trained models. No training data. Rules are transparent, tuneable, and deterministic. **As of v1.2, all geometric rules are also scale-invariant — see Section 5.**

### 4.1 MediaPipe Landmark Reference

MediaPipe Hands returns 21 landmarks per hand, each with normalized x, y, z coordinates (0.0–1.0 within the bounding box).

| ID | Landmark Name | Role in Recognition |
|---|---|---|
| 0 | Wrist | Anchor point for distance/motion/scale calculations |
| 4 | Thumb Tip | Pinch detection, Thumbs Up/Down |
| 8 | Index Finger Tip | Cursor control, Pinch detection |
| 12 | Middle Finger Tip | Peace sign, combined gestures |
| 16 | Ring Finger Tip | Three-finger gestures |
| 20 | Pinky Tip | Open Palm confirmation |
| 5 | Index MCP | Knuckle reference, palm-width measurement |
| 6 | Index PIP | Intermediate joint, bend angle calculation |
| 9 | Middle MCP | Knuckle reference, palm-width measurement |
| 13 | Ring MCP | Knuckle reference |
| 17 | Pinky MCP | Knuckle reference, fist compactness, palm-width measurement |

### 4.2 Finger State Detection

A finger is classified as **EXTENDED** or **CURLED** before evaluating any gesture. As of v1.2, this classification uses **finger angle**, not just tip-vs-PIP vertical position, to remain reliable across hand orientations and distances (see Section 5.2).

**Example finger-state vector for Open Palm:**

```
Thumb  = Open
Index  = Open
Middle = Open
Ring   = Open
Pinky  = Open
```

**Example finger-state vector for "L" pose (Thumb + Index open, rest closed):**

```
Thumb  = Open
Index  = Open
Middle = Closed
Ring   = Closed
Pinky  = Closed
```

### 4.3 Static Gesture Recognition

| Gesture | Rule Summary | Default Action |
|---|---|---|
| Open Palm | All five fingers EXTENDED; spread factor (normalized) above threshold | Pause / Stop |
| Closed Fist | All four fingers CURLED; palm compactness (normalized) below threshold | Hold / Drag start |
| Pinch | Normalized Thumb↔Index distance below threshold | Click / Select |
| Thumbs Up | Thumb EXTENDED upward via angle check, other fingers CURLED | Confirm / Vol Up |
| Thumbs Down | Thumb EXTENDED downward via angle check, other fingers CURLED | Cancel / Vol Down |
| Peace Sign | Index + Middle EXTENDED, Ring + Pinky CURLED, Thumb CURLED | Screenshot |
| Three Fingers | Index + Middle + Ring EXTENDED, Pinky + Thumb CURLED | Switch Workspace |
| OK Sign | Normalized Thumb↔Index distance below threshold AND Middle/Ring/Pinky EXTENDED | Right Click |

### 4.4 Dynamic Gesture Recognition

Dynamic gestures track the wrist landmark (ID 0) position over a rolling time window (Section 9 — Motion History Buffer). A gesture triggers when the trajectory satisfies **normalized** velocity and direction thresholds.

| Gesture | Rule Summary | Default Action |
|---|---|---|
| Swipe Right | Normalized rightward wrist displacement > threshold within time window; velocity > threshold | Next slide / track / forward |
| Swipe Left | Normalized leftward wrist displacement > threshold within time window | Previous slide / track / back |
| Swipe Up | Normalized upward wrist displacement > threshold, predominantly vertical | Scroll up / Volume up |
| Swipe Down | Normalized downward wrist displacement > threshold, predominantly vertical | Scroll down / Volume down |
| Wave | ≥2 direction reversals in x within time window | Show Desktop |
| Circular Motion | Trajectory bounding box roughly square; angular progression ≥270° | Open App Launcher |

All dynamic gesture rules are evaluated against **normalized-by-hand-scale** displacement, not raw normalized-frame coordinates alone — see Section 5.4.

---

## 5. Scale-Invariant Recognition Requirements

> **Problem:** A user's distance from the camera changes constantly during normal use. Raw pixel distances between landmarks (e.g., thumb tip to index tip) shrink or grow purely as a function of distance, not gesture shape. A Pinch performed close to the camera might measure 30px between thumb and index tip; the same Pinch performed farther away might measure only 12px. If gesture rules use raw pixel or raw-frame-normalized thresholds, recognition becomes unreliable as the user moves.

**This is a mandatory, non-negotiable requirement.** GestureOS must not depend on raw pixel distances or unscaled normalized-frame distances for any gesture decision.

### 5.1 Recognition Priority Order

All gesture rules must be implemented using the following priority order, preferring higher-priority signals whenever they are sufficient to make a confident determination:

**Priority 1 — Finger State Logic**
Boolean EXTENDED/CURLED per finger. Inherently scale-invariant since it is a relative joint-position comparison, not a distance measurement.

```
Example finger state vector:
Thumb  = Open
Index  = Open
Middle = Closed
Ring   = Closed
Pinky  = Closed
```

**Priority 2 — Finger & Joint Angles**
Angles formed between adjacent bone segments at each joint. Angles are inherently scale-invariant — they do not change with distance from camera, only with hand pose.

```
Example:
Index Finger Angle  = 175°  (nearly straight = extended)
Middle Finger Angle = 35°   (sharply bent = curled)
```

**Priority 3 — Normalized Distances**
Any distance measurement (e.g., thumb tip to index tip for Pinch) must be expressed as a ratio relative to a hand-scale reference, never as a raw value.

```
Example:
ThumbIndexDistance ÷ PalmWidth  =  0.18   (consistent regardless of camera distance)
```

**Priority 4 — Motion Trajectories**
Dynamic gesture displacement and velocity must also be normalized by hand scale before threshold comparison (Section 5.4).

```
Example — Swipe Right evaluated on:
  Direction (sign of horizontal displacement)
  Velocity (normalized displacement ÷ elapsed time)
  Time Window (bounded buffer, see Section 9)
```

### 5.2 Rule: Avoid Raw Pixel Thresholds

**Explicitly forbidden:** any gesture rule that compares a landmark distance directly against a fixed pixel or fixed frame-normalized-coordinate threshold without first dividing by a hand-scale reference.

```python
# WRONG — breaks at different camera distances
def detect_pinch_BAD(landmarks):
    dist = euclidean_distance(landmarks[4], landmarks[8])
    return dist < 0.05   # 0.05 of FRAME width — varies with hand distance

# CORRECT — scale-invariant
def detect_pinch_GOOD(landmarks, palm_width):
    dist = euclidean_distance(landmarks[4], landmarks[8])
    normalized_dist = dist / palm_width
    return normalized_dist < 0.35   # consistent regardless of distance from camera
```

### 5.3 Finger Angle Calculation

Finger extension state must be computed via the angle at the PIP joint (the angle between the MCP→PIP segment and the PIP→Tip segment), not solely via vertical tip-vs-PIP comparison, because vertical-only comparison fails when the hand is rotated relative to the camera.

```python
def finger_angle(mcp, pip, tip):
    v1 = (mcp.x - pip.x, mcp.y - pip.y)
    v2 = (tip.x - pip.x, tip.y - pip.y)
    dot = v1[0]*v2[0] + v1[1]*v2[1]
    mag1 = (v1[0]**2 + v1[1]**2) ** 0.5
    mag2 = (v2[0]**2 + v2[1]**2) ** 0.5
    cos_angle = dot / (mag1 * mag2)
    return degrees(acos(clamp(cos_angle, -1.0, 1.0)))

def is_finger_extended_by_angle(mcp, pip, tip, angle_threshold=160):
    return finger_angle(mcp, pip, tip) >= angle_threshold
```

### 5.4 Normalized Motion Trajectories

Dynamic gesture velocity and displacement must be divided by the current hand scale (Section 6) before being compared to thresholds, so that a swipe performed close to the camera and the same swipe performed far away both register as the same gesture.

```python
def normalized_displacement(p_start, p_end, hand_scale):
    raw_dx = p_end.x - p_start.x
    raw_dy = p_end.y - p_start.y
    return raw_dx / hand_scale, raw_dy / hand_scale
```

---

## 6. Hand Scale Estimation

> GestureOS must continuously calculate a hand-scale reference value used to normalize every distance and motion measurement described in Section 5.

### 6.1 Required Measurements (computed every frame, per detected hand)

| Measurement | Definition | Used For |
|---|---|---|
| Palm Width | Distance between Index MCP (5) and Pinky MCP (17) | Primary normalization denominator for distance-based gestures (e.g., Pinch) |
| Palm Height | Distance between Wrist (0) and Middle MCP (9) | Secondary normalization reference, used for vertically-oriented checks |
| Hand Bounding Box | Min/max x and y across all 21 landmarks | Used for Circular Motion's bounding-box check and overlay rendering |
| Estimated Hand Scale | `(Palm Width + Palm Height) / 2`, smoothed across recent frames | The single reference value fed into Sections 5.2–5.4 |

```python
def estimate_hand_scale(landmarks):
    palm_width  = euclidean_distance(landmarks[5], landmarks[17])
    palm_height = euclidean_distance(landmarks[0], landmarks[9])
    raw_scale = (palm_width + palm_height) / 2
    return raw_scale
```

### 6.2 Functional Requirements

- **FR-SC-01:** Hand scale must be recalculated every frame for every detected hand
- **FR-SC-02:** Hand scale must be smoothed (e.g., simple moving average over the last 5 frames) to avoid scale-estimation jitter feeding noise into every downstream gesture rule
- **FR-SC-03:** All Priority 3 (Normalized Distances) and Priority 4 (Motion Trajectories) rules in Section 5 must consume the smoothed hand scale, not a single-frame raw value
- **FR-SC-04:** If hand scale cannot be computed (e.g., fewer than 21 landmarks present): skip gesture evaluation for that hand that frame — do not fall back to a raw-pixel rule

---

## 7. Activation Mode

> **Problem:** Users move their hands naturally during calls, conversations, and general work. Without an activation gate, these movements produce constant false triggers. GestureOS must only process gestures when the user explicitly intends to interact. **This requirement is mandatory for release — GestureOS must not execute gestures continuously by default.**

### 7.1 Activation State Machine

GestureOS has two tracking states: **INACTIVE** and **ACTIVE**. Gesture recognition and action dispatch are suppressed in INACTIVE state. The overlay still shows hand landmarks in INACTIVE state to confirm the camera is working.

```
class TrackingState(Enum):
    INACTIVE = 'inactive'   # gestures ignored, landmarks shown
    ACTIVE   = 'active'     # full pipeline enabled
```

**Example — Zoom Call Scenario:**

```
User is on a Zoom call, gesturing naturally while speaking.

[INACTIVE] GestureOS detects hands but ignores all gestures.
           Hand movement is ignored entirely.

User holds Open Palm for 1 second → ACTIVE state entered.
Overlay badge flashes: "Tracking ON"

User performs Swipe Right → Next slide action triggered.

User holds Open Palm for 1 second → INACTIVE state entered.
Overlay badge flashes: "Tracking OFF"

User continues Zoom call — no further gesture processing.
```

### 7.2 Activation Methods

| Method | Trigger | Notes |
|---|---|---|
| Open Palm Hold | Open Palm held for 1.0 second (configurable) | Primary method; works without keyboard access |
| Keyboard Shortcut | Ctrl + Alt + G (configurable) | Useful when hands are on keyboard |
| System Tray Toggle | Click tray icon → Toggle Tracking | Accessible via mouse or touchpad at any time |
| Closed Fist Hold | Closed Fist held for 1.5 seconds (configurable, off by default) | Alternative toggle for users who prefer fist |

### 7.3 Activation Requirements

- **FR-AM-01:** Gesture processing pipeline must be fully bypassed when state is INACTIVE
- **FR-AM-02:** Hand landmark rendering in the overlay must continue in INACTIVE state
- **FR-AM-03:** Activation state must persist across context switches
- **FR-AM-04:** State change must be logged with timestamp
- **FR-AM-05:** Visual indicator must clearly distinguish ACTIVE vs INACTIVE state in overlay
- **FR-AM-06:** Default state on app launch is INACTIVE
- **FR-AM-07:** Hold duration for Open Palm activation is configurable (0.5s – 3.0s)

---

## 8. Functional Requirements

### 8.1 Hand Tracking System

- **FR-HT-01:** System must support USB and built-in webcam input via OpenCV VideoCapture
- **FR-HT-02:** System must detect one or two hands simultaneously within each frame
- **FR-HT-03:** System must extract 21 3D landmarks per detected hand using MediaPipe Hands
- **FR-HT-04:** System must provide per-hand confidence scores (0.0–1.0)
- **FR-HT-05:** System must identify hand chirality (left/right) per MediaPipe output
- **FR-HT-06:** System must handle hand occlusion gracefully (see Section 8.1.2 — Temporary Occlusion Handling)
- **FR-HT-07:** All landmark coordinates must be normalized (0.0–1.0) within the webcam frame

#### 8.1.1 Hand Identity Tracking

> **Problem:** When two hands cross or briefly overlap, MediaPipe may reassign hand IDs or swap left/right labels. GestureOS must maintain persistent identity so that if the left hand is assigned to volume control and the right hand to cursor, those roles survive a crossing event.

```
Example:

Left Hand:  Volume Control
Right Hand: Cursor Control

Hands cross temporarily.

System preserves assigned roles — Left Hand remains
Volume Control, Right Hand remains Cursor Control,
even after crossing.
```

- **FR-HT-08:** System must assign a persistent role ID (HAND_A, HAND_B) to each hand on first detection
- **FR-HT-09:** Role assignment must persist for at least 2 seconds after hand loss (re-identification window)
- **FR-HT-10:** Re-identification uses proximity matching — the re-appearing hand is assigned to the nearest last-known position
- **FR-HT-11:** If re-identification is ambiguous, system must log a warning and default to chirality-based assignment
- **FR-HT-12:** Hand role assignments must be displayed in the debug overlay

#### 8.1.2 Temporary Occlusion Handling *(New in v1.2)*

> **Problem:** A finger or hand becomes briefly hidden (e.g., behind another finger, briefly out of frame edge). Without tolerance, the gesture state is immediately invalidated, causing flicker and dropped gestures mid-interaction.

```
Example:

Gesture: Open Palm, in progress
Index finger briefly occluded → confidence drops

Without occlusion handling: gesture immediately lost,
   user must restart the gesture from scratch.

With occlusion handling: previous finger-state is
   retained for up to 300ms while confidence is low,
   bridging brief interruptions.
```

- **FR-OC-01:** If hand-detection confidence drops below the detection threshold for a single hand, the system must retain that hand's last-known finger-state and trajectory data for up to 300ms (configurable) before clearing it
- **FR-OC-02:** If detection recovers within the retention window, tracking resumes seamlessly without restarting gesture stability timers (Section 8.2) or trajectory buffers (Section 9)
- **FR-OC-03:** If detection does not recover within the retention window, the hand is treated as lost: trajectory cleared, role released into the re-identification window (FR-HT-09)

#### 8.1.3 Primary Hand Selection *(New in v1.2)*

> **Problem:** Additional hands may enter the frame (e.g., a second person, or the user's own hand resting in view without intent to gesture). Without a primary-hand concept, extra hands can interfere with single-hand workflows.

- **FR-PH-01:** Settings must expose a "Dominant Hand Mode" toggle: Off (both hands active, default) / Left Primary / Right Primary
- **FR-PH-02:** When Dominant Hand Mode is set to Left or Right, only the matching chirality's hand is evaluated for gestures; other detected hands are tracked (shown in overlay) but never produce a GestureResult
- **FR-PH-03:** If the designated primary hand leaves the frame, the system does not automatically promote a secondary hand — it waits for the primary hand's return (consistent with FR-HT-09's re-identification window)

### 8.2 Gesture Stability Requirement *(New in v1.2)*

> **Problem:** A gesture may appear for only a single frame due to transient pose noise, causing a false trigger.

```
Example:

Gesture detected
for 200ms
before activation

If Open Palm is detected for only 1 frame (~33ms) and
then disappears, it must NOT trigger. Only a gesture
that remains valid continuously for the stability
window is accepted.
```

- **FR-GS-01:** Every static gesture must remain the highest-confidence match for a continuous stability window (default 200ms, configurable 100–500ms) before it is accepted and passed downstream
- **FR-GS-02:** If the gesture changes or disappears before the stability window elapses, the partial hold is discarded — no partial credit carries to a different gesture
- **FR-GS-03:** The stability window is tracked independently per hand role (HAND_A / HAND_B)
- **FR-GS-04:** Dynamic gestures are exempt from the stability window (they already require a multi-frame trajectory by definition) but are still subject to the Cooldown System (Section 8.3)

### 8.3 Cooldown System *(Formalized in v1.2)*

> **Problem:** A single Swipe Right gesture, performed once, can be re-detected across several consecutive frames of the same physical motion, causing the same action to fire 2–3 times.

```
Example:

Swipe Right
Cooldown = 1000ms

User performs one swipe → action fires once.
Cooldown timer starts (1000ms).
Any further "swipe_right" detections for that hand
role within 1000ms are suppressed, even if the
underlying trajectory rule would otherwise re-match.
```

- **FR-CD-01:** Every gesture type must support a configurable cooldown period (default 500ms for static gestures, 1000ms for dynamic gestures — these defaults differ because dynamic gestures span a longer physical motion)
- **FR-CD-02:** Cooldown is tracked per (hand_role, gesture_name) pair — a cooldown on Swipe Right for HAND_A does not suppress Swipe Left or affect HAND_B
- **FR-CD-03:** Cooldown timers are visible in the Developer Mode debug overlay (Section 12.2)

### 8.4 Cursor Control Module

> **Problem:** Raw hand-tracking position is inherently noisy frame-to-frame, producing a visibly shaky cursor — one of the most common complaints in gesture-control products.

```
Raw Hand Position
        ↓
  Smoothing Layer
        ↓
  Cursor Position
```

- **FR-CC-01:** Index fingertip (landmark 8) position controls cursor by default
- **FR-CC-02:** Hand coordinate space must map to full screen resolution via configurable edge buffers
- **FR-CC-03:** Cursor movement must be smoothed using one of the following acceptable methods: Moving Average, Exponential Smoothing (default), or One Euro Filter (optional, for advanced low-latency/low-jitter tuning)
- **FR-CC-04:** Sensitivity multiplier adjustable (0.1x – 5.0x, default 1.5x)
- **FR-CC-05:** Screen edge clamping must prevent cursor leaving display bounds
- **FR-CC-06:** Calibration mode lets user define active tracking zone (Section 15)
- **FR-CC-07:** Multi-monitor support with per-display coordinate mapping

### 8.5 Motion History Buffer *(New in v1.2)*

> Dynamic gestures (swipes, wave, circular motion) must not rely on a single frame of motion data — they require a buffered history of recent positions to evaluate direction, velocity, and pattern.

- **FR-MH-01:** System must store the previous N frames of wrist position per hand role, where N is recommended at 15–30 frames (time-bounded equivalently to the 500–1500ms dynamic gesture window already defined in Section 4.4)
- **FR-MH-02:** Buffer is implemented as a fixed-capacity rolling structure (oldest entries evicted as new ones arrive) — memory usage must not grow unbounded
- **FR-MH-03:** Buffer entries store (x, y, timestamp) at minimum; hand-scale-normalized x/y per Section 5.4 is computed at evaluation time, not stored pre-normalized, so a change in hand scale mid-buffer doesn't retroactively corrupt earlier samples
- **FR-MH-04:** Buffer is used by Swipe (all 4 directions), Wave, and Circular Motion recognition exclusively — static gestures do not consult this buffer

### 8.6 System Command Engine

| Command Type | Supported Commands | Implementation |
|---|---|---|
| Mouse Control | Left/right/double click, drag-and-drop, scroll | PyAutoGUI / pynput |
| Keyboard Shortcuts | Enter, Escape, Tab, Alt+Tab, Ctrl+C/V/Z/S | pynput keyboard controller |
| Volume Control | Volume up/down, mute toggle | pynput + platform APIs |
| Brightness | Brightness increase/decrease | Platform-specific |
| System Actions | Screenshot, lock screen, show desktop | pyautogui / OS calls |
| Application Launch | Open configured apps via gesture + profile | subprocess.Popen() |

### 8.7 Context-Aware Action Engine

#### 8.7.1 Context Detection

- **FR-CA-01:** System queries the active foreground window title and process name every 250ms
- **FR-CA-02:** Context uses process-name pattern matching (e.g., chrome.exe → 'chrome')
- **FR-CA-03:** Context switch takes effect within one frame of application focus change, subject to the Context Verification Layer (Section 8.7.3)

#### 8.7.2 Context Mapping Table

| Active App | Gesture | Action | Key Sent |
|---|---|---|---|
| Browser | Swipe Left | Navigate Back | ALT + Left |
| Browser | Swipe Right | Navigate Forward | ALT + Right |
| PowerPoint | Swipe Left | Previous Slide | Page Up |
| PowerPoint | Swipe Right | Next Slide | Page Down |
| PowerPoint | Open Palm | Blank Screen | B key |
| Media Player | Open Palm | Play / Pause | Space |
| Media Player | Swipe Left | Previous Track | CTRL + Left |
| Media Player | Swipe Right | Next Track | CTRL + Right |
| VS Code | Three Fingers | Open Terminal | CTRL + ` |
| Any App | Wave | Show Desktop | WIN + D |

#### 8.7.3 Context Verification Layer *(New in v1.2)*

> **Problem:** Rapid window switching (e.g., Alt-Tabbing quickly, or a notification briefly stealing focus) can cause the wrong action to execute against a context the user didn't intend to target.

```
Example:

Window active for 200ms
before context switch is accepted

User Alt-Tabs through 3 windows in 150ms, landing on
Chrome. Because the intermediate windows were each
focused for under 200ms, they are never registered
as the active context — only Chrome, once it has held
focus continuously for 200ms, becomes the resolved
context.
```

- **FR-CV-01:** A newly detected foreground window must hold focus continuously for at least 200ms (configurable) before ContextEngine accepts it as the new resolved context
- **FR-CV-02:** Until the verification window elapses, the previously resolved context remains active for gesture mapping purposes
- **FR-CV-03:** This requirement applies on top of, not instead of, the existing 250ms polling interval (FR-CA-01) — polling determines when to check, verification determines when to commit

### 8.8 Gesture Mapping Manager

- **FR-GM-01:** GUI for mapping any gesture to any system command
- **FR-GM-02:** Mappings stored in mappings.json — gesture_name, context, action_type, action_params
- **FR-GM-03:** Conflict detection warns when two mappings share the same gesture in the same context
- **FR-GM-04:** Export produces a portable .json file importable on any supported system
- **FR-GM-05:** Recommend maximum 8–12 active gesture mappings per profile to avoid cognitive overload

### 8.9 User Profiles

| Profile | Optimized Gesture Set |
|---|---|
| Presentation Mode | Swipe for slide control, pinch to laser pointer, open palm to pause |
| Productivity Mode | Shortcuts for copy/paste/undo, app switching, cursor fine control |
| Gaming Mode | Directional swipes, fist for action, configurable combos |
| Accessibility Mode | Simplified set, large tolerance zones, extended cooldowns, slow cursor |

### 8.10 Visual Feedback System

- **FR-VF-01:** Hand skeleton rendered as overlay on webcam preview using landmark lines
- **FR-VF-02:** Detected gesture name shown with confidence percentage
- **FR-VF-03:** Triggered action badge flashes for 500ms then fades out
- **FR-VF-04:** FPS counter, active profile, active context, and tracking state (ACTIVE/INACTIVE) persistently visible
- **FR-VF-05:** Overlay toggleable via keyboard shortcut without closing app
- **FR-VF-06:** ACTIVE state indicator shown in green; INACTIVE in grey
- **FR-VF-07:** *(New in v1.2)* Lighting quality and camera quality warnings (Sections 8.11, 8.12) must surface in the overlay, not only in a separate settings dialog, so users notice degraded conditions in real time

### 8.11 Camera Validation System *(New in v1.2)*

> GestureOS must validate the camera's capability at startup and continuously during operation, warning the user when conditions fall below minimum requirements rather than silently degrading.

- **FR-CV2-01:** At startup, system must check: camera is available and opens successfully; reported FPS capability; reported resolution
- **FR-CV2-02:** If actual measured FPS falls below the minimum requirement (25 FPS, per Section 16) for more than 5 continuous seconds during operation, display a non-blocking "Low FPS Detected" warning in the overlay
- **FR-CV2-03:** If camera resolution is below the documented minimum (640x480), warn the user during the onboarding wizard and recommend a different device if available
- **FR-CV2-04:** Camera validation results are logged at startup (INFO level) for diagnostics regardless of whether thresholds are met

### 8.12 Lighting Quality Detection *(New in v1.2)*

> Poor lighting is a primary real-world cause of degraded MediaPipe confidence and false gesture rejection. GestureOS must detect this condition and inform the user rather than leaving them to guess why recognition feels unreliable.

- **FR-LQ-01:** System must monitor average frame brightness (e.g., mean luminance of the captured frame) on a rolling basis
- **FR-LQ-02:** If MediaPipe hand-detection confidence is below threshold AND average frame brightness is below a documented low-light threshold for a sustained period (e.g., 3 seconds), display a "Low Lighting Detected" warning in the overlay (FR-VF-07)
- **FR-LQ-03:** The warning must be dismissible per-session but reappears in future sessions if conditions recur (it is not a one-time nag, since lighting conditions change session to session)
- **FR-LQ-04:** Lighting warnings are advisory only — they never block gesture processing, only inform the user of a likely cause for degraded accuracy

---

## 9. Technical Architecture

*(Updated in v1.2 to incorporate scale estimation, stability, cooldown, smoothing, and motion-history components into the pipeline.)*

```
Camera Input
   ↓  (BGR frame, 640x480, target FPS)
Frame Processor  (resize, flip, RGB convert)
   ↓
Camera Validation Check  (FPS/resolution monitoring, Section 8.11)
   ↓
MediaPipe Detector  (landmark extraction, chirality, confidence)
   ↓
Lighting Quality Check  (brightness monitoring, Section 8.12)
   ↓
Hand Identity Tracker  (persistent role assignment + occlusion tolerance)
   ↓
Hand Scale Estimator  (palm width/height, bounding box, Section 6)
   ↓
Primary Hand Filter  (Dominant Hand Mode, Section 8.1.3)
   ↓
Activation Mode Gate  [INACTIVE → stop here | ACTIVE → continue]
   ↓
Gesture Recognizer  (scale-invariant static rules + normalized motion-history trajectory)
   ↓
Gesture Stability Filter  (200ms hold requirement, Section 8.2)
   ↓
Context Detector + Verification Layer  (active window, 200ms stability, Section 8.7.3)
   ↓
Action Mapper  (gesture + context → action lookup in mappings.json)
   ↓
Cooldown Filter  (per gesture+hand, Section 8.3)
   ↓
Command Executor  (PyAutoGUI / pynput dispatch)
   ↓
Cursor Smoothing Layer  (applies only to continuous cursor-control path, Section 8.4)
   ↓
Diagnostics Logger  (structured event log)
   ↓
Overlay Renderer  (landmarks, gesture badge, status bar, quality warnings)
```

### 9.1 Component Responsibilities

| Component | Responsibility | Technology |
|---|---|---|
| CameraModule | Webcam frame capture and buffering | OpenCV VideoCapture |
| FrameProcessor | Resize, flip, BGR→RGB, normalize | OpenCV / NumPy |
| CameraValidator | FPS/resolution monitoring against minimums (8.11) | Pure Python + OpenCV props |
| HandDetector | MediaPipe Hands inference + chirality | MediaPipe 0.10+ |
| LightingMonitor | Frame brightness analysis (8.12) | OpenCV / NumPy |
| HandIdentityTracker | Persistent role assignment, re-identification, occlusion tolerance (8.1.1, 8.1.2) | Pure Python deque |
| HandScaleEstimator | Palm width/height, smoothed scale reference (Section 6) | Pure Python geometry |
| PrimaryHandFilter | Dominant Hand Mode filtering (8.1.3) | Pure Python |
| ActivationGate | INACTIVE/ACTIVE state machine | Python Enum + timer |
| StaticRecognizer | Scale-invariant finger-state/angle rules | Pure Python geometry |
| DynamicRecognizer | Motion history buffer + normalized velocity/direction analysis | Pure Python + deque |
| StabilityFilter | 200ms continuous-hold requirement (8.2) | Pure Python timer |
| ContextDetector | Active window process name detection + 200ms verification (8.7.3) | pywin32 / Xlib / AppKit |
| ActionMapper | Gesture + context → action lookup | JSON rule loader |
| CooldownFilter | Per (hand, gesture) cooldown enforcement (8.3) | Pure Python timer dict |
| CommandExecutor | Dispatch OS-level input events | PyAutoGUI / pynput |
| CursorSmoother | EMA / Moving Average / One Euro Filter (8.4) | Pure Python / NumPy |
| ProfileManager | Load/save/switch profiles from JSON files | Python json module |
| OverlayRenderer | Draw skeleton, badges, status bar, quality warnings | PyQt6 / OpenCV |
| DiagnosticsLogger | Structured event logging, debug overlay data | Python logging module |
| SettingsManager | Persist and validate settings.json | Python json / dataclass |

### 9.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.10+ | Ecosystem breadth for CV and OS automation |
| Computer Vision | OpenCV 4.8+ | Frame capture, processing, overlay rendering, brightness analysis |
| Hand Tracking | MediaPipe 0.10+ | Real-time 21-landmark detection, no training |
| OS Automation | PyAutoGUI + pynput | Cross-platform mouse/keyboard control |
| GUI Framework | PyQt6 | Native look-and-feel, system tray, widgets |
| Config Storage | JSON files | Human-readable, version-controllable, portable |
| Logging | Python logging module | Structured log output, file + console handlers |
| Build System | PyInstaller | Single-file executable distribution |

---

## 10. Runtime State Flow

*(Updated in v1.2 with scale estimation, stability, and verification stages.)*

| Stage | Description / Output | Error Behavior |
|---|---|---|
| 1. Frame Captured | OpenCV reads a BGR frame from the webcam buffer | Camera unavailable: emit CameraError, log, retry after 2s |
| 2. Frame Processed | Flip, resize, BGR→RGB | Frame is None: skip frame, log warning |
| 3. Camera Validated | FPS/resolution checked against minimums (8.11) | Below minimum: surface overlay warning, continue processing |
| 4. Hand Detected | MediaPipe returns hands with 21 landmarks each | No hands: clear trajectory buffers, reset hold timers |
| 5. Lighting Checked | Frame brightness analyzed (8.12) | Low light + low confidence: surface overlay warning, continue |
| 6. Identity Assigned | HandIdentityTracker maps hands to HAND_A/HAND_B, tolerates brief occlusion | Ambiguous: log warning, fall back to chirality |
| 7. Scale Estimated | Palm width/height computed and smoothed (Section 6) | Cannot compute: skip gesture evaluation this frame for that hand |
| 8. Primary Hand Filtered | Dominant Hand Mode applied if enabled (8.1.3) | N/A — pass-through if disabled |
| 9. Activation Gate | INACTIVE → render only; ACTIVE → continue | N/A — gate always evaluates |
| 10. Gesture Evaluated | Scale-invariant static rules + normalized motion-history trajectory | Below confidence: discard, do not trigger |
| 11. Stability Checked | Gesture must hold 200ms continuously (8.2) | Held <200ms: discard, no partial credit |
| 12. Context Resolved + Verified | Active window queried, held 200ms before commit (8.7.3) | OS query fails: use last known context |
| 13. Action Mapped | (gesture, context) looked up in mappings.json | No mapping: log info, no action |
| 14. Cooldown Checked | Per (hand, gesture) timer (8.3) | Within cooldown: suppress |
| 15. Action Executed | CommandExecutor dispatches OS input event; cursor path also passes through smoothing (8.4) | Dispatch fails: log error, continue |
| 16. Event Logged | Structured log entry written | Logging failure must not crash main loop |
| 17. Overlay Rendered | Landmarks, gesture badge, status, quality warnings drawn | Overlay hidden: skip render |

---

## 11. Storage Design

> **Storage Philosophy:** GestureOS uses JSON files as the primary persistence layer. JSON is human-readable, version-controllable, easily diffed, and requires no database engine. SQLite remains an optional future enhancement only if query complexity justifies it (unchanged from v1.1).

### 11.1 File Layout

```
~/.gestureos/
├── settings.json        # All user-configurable settings
├── profiles.json        # All profile definitions and metadata
├── mappings/
│   ├── default.json
│   ├── presentation.json
│   ├── productivity.json
│   └── <profile_name>.json
└── logs/
    ├── gestureos.log
    └── diagnostics.log
```

### 11.2 settings.json Schema *(v1.2 — expanded)*

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

### 11.3 profiles.json Schema

```json
{
  "profiles": [
    { "id": "productivity", "name": "Productivity Mode", "is_default": true },
    { "id": "presentation", "name": "Presentation Mode", "is_default": false }
  ]
}
```

### 11.4 Mapping File Schema (per profile)

```json
{
  "profile_id": "presentation",
  "mappings": [
    {
      "gesture": "swipe_right",
      "context": "global",
      "action_type": "keyboard",
      "action_params": { "key": "page_down" },
      "enabled": true
    },
    {
      "gesture": "swipe_right",
      "context": "chrome",
      "action_type": "keyboard",
      "action_params": { "hotkey": ["alt", "right"] },
      "enabled": true
    }
  ]
}
```

---

## 12. Debugging & Diagnostics

### 12.1 Logging System

Log events across these categories:

- Camera Events (startup, disconnect, FPS/resolution validation results)
- Tracking Events (hand detected/lost, occlusion retained/expired, scale estimation)
- Gesture Events (candidate detected, stability passed/failed, cooldown suppressed, triggered)
- Context Events (context resolved, verification held/rejected)
- Action Events (executed, failed)
- Errors / Warnings

```
[12:31:44] Gesture Detected: Swipe Right
[12:31:44] Context: Chrome
[12:31:44] Action: Next Tab
[12:31:44] Status: Success
```

### 12.2 Developer Mode

When enabled, display:

- Landmark IDs and coordinates
- **Finger states (Open/Closed) and finger angles** *(v1.2)*
- **Normalized distances (e.g., ThumbIndexDistance ÷ PalmWidth)** *(v1.2)*
- **Hand scale estimate (palm width, palm height, bounding box)** *(v1.2)*
- Motion vectors
- Confidence scores
- Cooldown timers (per hand, per gesture)
- **Gesture stability timer progress** *(v1.2)*
- Gesture state machine status

### 12.3 Debug Overlay

Display:

- FPS
- Active profile / Active context
- Gesture name + confidence
- Tracking state (ACTIVE/INACTIVE)
- **Lighting quality warning indicator** *(v1.2)*
- **Camera quality (FPS/resolution) warning indicator** *(v1.2)*

### 12.4 Error Recovery Requirements

| Error Condition | Required Behavior |
|---|---|
| Camera Disconnect | Auto reconnect |
| Invalid Configuration | Load default settings (per-field, see Section 11.2 validation) |
| Gesture Mapping Failure | Log warning, continue running |
| Camera Below Minimum FPS/Resolution | Warn user, continue running in degraded mode |
| Sustained Low Lighting | Warn user, continue running |
| Hand Scale Cannot Be Computed | Skip gesture evaluation for that hand/frame only |

---

## 13. Recommended Project Structure

```
gestureos/
├── app/
├── camera/
├── tracking/
│   ├── hand_identity.py
│   ├── hand_scale.py          # NEW in v1.2
│   └── occlusion_handler.py   # NEW in v1.2
├── gestures/
│   ├── static_recognizer.py
│   ├── dynamic_recognizer.py
│   ├── stability_filter.py    # NEW in v1.2
│   ├── cooldown_filter.py     # NEW in v1.2
│   └── motion_history.py      # NEW in v1.2
├── context/
│   └── verification.py        # NEW in v1.2
├── actions/
├── profiles/
├── overlay/
├── settings/
├── diagnostics/
│   ├── camera_validator.py    # NEW in v1.2
│   └── lighting_monitor.py    # NEW in v1.2
├── calibration/                # NEW in v1.2
├── ui/
├── tests/
├── assets/
└── main.py
```

> Folder-by-folder responsibilities are detailed exhaustively in the companion Technical Requirements Document (TRD), which is the authoritative source for implementation-level structure.

---

## 14. Development Checkpoints

> GestureOS is a single product developed through sequential checkpoints. Each checkpoint builds on the previous one and has defined acceptance criteria. All checkpoints contribute to the same final release.

| Checkpoint | Focus | Key Deliverables | Duration |
|---|---|---|---|
| CP-1 | Core Hand Tracking | Camera module, MediaPipe integration, landmark overlay, FPS benchmark, **camera validation** | 2 Weeks |
| CP-2 | Gesture Recognition | Static/dynamic gestures, **scale-invariant rules, hand scale estimation**, confidence logic, **stability + cooldown**, activation gate | 4 Weeks |
| CP-3 | System Control | Cursor control + **smoothing**, clicks, scroll, keyboard shortcuts, volume control | 2 Weeks |
| CP-4 | Context-Aware Engine | Active window detection, **context verification layer**, context mapping, browser + presentation controls | 2 Weeks |
| CP-5 | GUI and Profiles | Settings panel, profiles, mapping manager, **calibration wizard** | 3 Weeks |
| CP-6 | Robustness | **Occlusion handling, primary hand selection, lighting detection**, error recovery | 2 Weeks |
| CP-7 | Optimization & Release | Testing, **performance budget validation**, packaging, documentation | 2 Weeks |

### Checkpoint Acceptance Criteria (key additions, v1.2)

**CP-2 additions:**
- Pinch gesture recognized correctly at both 30cm and 100cm from camera (validates scale invariance)
- A gesture held for only 1 frame does not trigger; a gesture held 200ms+ does
- Repeated single swipe motion fires exactly one action, not multiple

**CP-3 additions:**
- Cursor movement visibly smoothed — no frame-to-frame jitter under static hand-hold test

**CP-4 additions:**
- Rapid Alt-Tab sequence (3 switches in <200ms) does not cause a misdirected action

**CP-5 additions:**
- Calibration wizard completes and visibly adjusts tracking zone, sensitivity, and cursor speed

**CP-6 additions:**
- Briefly covering the index finger for <300ms does not drop an in-progress gesture
- Dominant Hand Mode correctly ignores a second hand entering frame
- Lighting warning appears within 3s of moving to a darkened room and disappears within a reasonable interval after lights return

---

## 15. Calibration Requirement

> GestureOS must provide a calibration wizard so the system adapts to the user's physical setup rather than assuming a one-size-fits-all configuration.

### 15.1 Calibration Wizard — Required Steps

| Step | Purpose | User Action |
|---|---|---|
| Camera Position | Confirm the camera can see the user's full gesture range | User waves hand across intended gesture area; system confirms visibility |
| Sensitivity | Tune gesture confidence threshold to the user's gesture style | User performs each static gesture; system suggests a threshold |
| Cursor Speed | Tune cursor_speed_multiplier to the user's preference | User moves hand; system shows live cursor response, user adjusts a slider |
| Tracking Area | Define the active screen-mapping zone (FR-CC-06) | User marks the corners of their intended gesture zone |

### 15.2 Functional Requirements

- **FR-CAL-01:** Calibration wizard is offered during first-run onboarding and is re-accessible anytime from Settings
- **FR-CAL-02:** Calibration results are persisted to settings.json immediately upon completion
- **FR-CAL-03:** Skipping calibration is allowed — system falls back to documented defaults for all four parameters
- **FR-CAL-04:** Calibration wizard must complete in under 3 minutes per PRD usability requirement (Section 8 / NFR-US-01, unchanged)

---

## 16. Performance Budgets

> Formalizes resource-usage requirements that v1.1 expressed only as FPS targets.

| Metric | Target (Normal Operation) |
|---|---|
| FPS | ≥ 25 |
| Detection Latency | < 100 ms |
| End-to-End Action Latency | < 150 ms |
| CPU Usage | < 20% (single core average) |
| Memory Usage | < 300 MB |

> **Note:** This tightens the v1.1 CPU budget (previously < 30%) to < 20% based on real-world profiling expectations once scale estimation, stability filtering, and motion-history buffering are added to the pipeline. If CP-7 performance testing shows < 20% is not achievable without degrading FPS below 25, CPU budget is the parameter to revisit — FPS and latency are the higher-priority constraints.

---

## 17. Testing Plan

### 17.1 Unit Testing

- Framework: pytest
- Coverage target: ≥ 80% line coverage
- Modules: StaticRecognizer, DynamicRecognizer, ActionMapper, ProfileManager, ActivationGate, ContextDetector, **HandScaleEstimator, StabilityFilter, CooldownFilter, OcclusionHandler** *(v1.2)*
- All tests use mock landmark data — no live webcam required
- **New in v1.2:** scale-invariance must be explicitly tested by running the same gesture fixture through the recognizer at multiple synthetic hand-scale values and asserting identical recognition results

### 17.2 Gesture Accuracy Testing

- Record 100 samples per gesture from 5 different users
- Evaluate precision, recall, and F1 per gesture class
- Test under 3 lighting conditions: bright, dim, backlit
- **New in v1.2:** test at 3 camera distances: close (~30cm), medium (~75cm), far (~150cm) — accuracy must not degrade meaningfully across distances
- Acceptance: ≥ 95% accuracy on held-out test set, at every tested distance

### 17.3 Performance Testing

- Profile FPS, CPU, and memory over 30-minute continuous session
- Acceptance: meets all Section 16 performance budgets simultaneously, not just FPS in isolation

### 17.4 Integration Testing

- Validate full pipeline: gesture input to OS action in < 150ms end-to-end
- Test context switching with rapid Alt-Tab sequences to validate the Context Verification Layer
- Test activation gate: confirm no actions fire in INACTIVE state
- **New in v1.2:** test occlusion tolerance — briefly blank a finger landmark mid-gesture and confirm the gesture is not dropped within the 300ms retention window

### 17.5 User Acceptance Testing

| Test Scenario | Participants | Pass Criteria |
|---|---|---|
| Control full presentation using only gestures, moving toward/away from camera | 5 presenters | Zero failed slide transitions regardless of distance |
| Browse web hands-free for 10 minutes | 5 general users | < 3 false triggers total |
| Perform 15 common tasks hands-free | 5 accessibility users | ≥ 80% task completion |
| Use GestureOS during a video call | 5 users | Zero unintended triggers while inactive |
| Complete calibration wizard | 5 first-time users | Wizard completed in < 3 minutes, user reports correct cursor behavior afterward |

---

## 18. Risks & Challenges

| Risk | Severity | Impact | Mitigation |
|---|---|---|---|
| Lighting Variation | High | Poor detection in low light or backlit environments | Lighting Quality Detection (8.12), brightness preprocessing toggle |
| Similar Gesture Confusion | High | Open Palm vs Three Fingers misclassification | Multi-rule confidence scoring with sufficient margin |
| Background Gesture Triggers | High | Natural hand movements during calls fire unintended commands | Activation Mode (Section 7) |
| Multi-Hand Ambiguity | High | Hands cross; system swaps HAND_A and HAND_B roles | Hand Identity Tracker with proximity re-identification |
| **Scale Sensitivity** | **High** | **Gesture recognition breaks as user moves closer/farther from camera** | **Scale-Invariant Recognition (Section 5), Hand Scale Estimation (Section 6)** |
| Camera Quality Differences | Medium | Low-res cameras reduce landmark accuracy | Camera Validation System (8.11), minimum 640x480 |
| User Fatigue (Gorilla Arm) | Medium | Extended arm-raised usage causes physical fatigue | Gestures usable at desk height; usage break reminders |
| Gesture Overload | Medium | Too many mapped gestures reduce discoverability | Recommend 8–12 gestures per profile |
| OS API Compatibility | Low | pyautogui behavior differs across platforms | Platform-specific executor adapters |
| Performance on Low-End Hardware | Medium | FPS drops below 25 on older CPUs | Low-res mode, configurable FPS target, Performance Budgets (Section 16) |

---

## 19. Engineering Risks & Mitigation Matrix

> A dedicated, engineering-focused risk register distinct from the product-level risks in Section 18.

| Risk | Severity | Mitigation |
|---|---|---|
| Cursor Jitter | High | Cursor Smoothing (Section 8.4) — EMA / Moving Average / One Euro Filter |
| Gesture Flicker | High | Gesture Stability Requirement (Section 8.2) |
| Double Trigger | High | Cooldown System (Section 8.3) |
| Scale Sensitivity | High | Finger Angles + Normalized Distances (Section 5) |
| Hand Crossing | Medium | Hand Identity Tracking (Section 8.1.1) |
| Lighting Issues | Medium | Lighting Quality Detection (Section 8.12) |
| Camera Disconnect | Medium | Auto Reconnect (Section 12.4) |
| Context Errors | Medium | Context Verification Layer (Section 8.7.3) |
| CPU Usage | Medium | Performance Budget (Section 16) |
| Brief Occlusion Drops Gesture | Medium | Temporary Occlusion Handling (Section 8.1.2) |
| Extra Hands Interfere | Low | Primary Hand Selection (Section 8.1.3) |

---

## 20. Deployment Requirements

### 20.1 Packaging

- PyInstaller used to produce a native executable per target OS, bundling Python runtime and all dependencies (no separate Python install required by end users)

### 20.2 Installer

- Windows: Inno Setup-based installer producing a single-file GestureOS_Setup.exe, creating a Start Menu entry and optional auto-start registry key
- macOS / Linux installer equivalents are addressed at the implementation level in the companion TRD

### 20.3 Release Deliverables

Every release must include:

- **GestureOS.exe** (or platform-equivalent packaged executable)
- **Installer** (platform-appropriate)
- **Documentation** — user guide, gesture reference card, calibration walkthrough
- **Default Configurations** — factory-default settings.json, profiles.json, and mappings/*.json bundled and copied into ~/.gestureos/ on first launch

### 20.4 Release Acceptance Gate

- All checkpoints (Section 14) must meet their acceptance criteria
- Performance Budgets (Section 16) verified on reference hardware
- No P0 bugs open
- Release deliverables (Section 20.3) confirmed present in the build artifact

---

## 21. Success Metrics & Acceptance Criteria

### 21.1 Product KPIs

| Metric | Target | Measurement Method |
|---|---|---|
| Gesture Recognition Accuracy | ≥ 95% | Automated test suite, 100 samples per gesture |
| **Scale Invariance** | **Accuracy stable within 3% across near/medium/far distances** | **Section 17.2 distance testing** |
| End-to-End Latency | < 150 ms | Gesture start to OS action timestamp diff |
| Sustained FPS | ≥ 25 FPS | 30-minute benchmark on reference hardware |
| CPU Usage | < 20% | Performance Budget testing (Section 16) |
| Memory Usage | < 300 MB | Performance Budget testing (Section 16) |
| False Trigger Rate | < 5% | Monitored over 1-hour passive session |
| **Double-Trigger Rate** | **0% for single physical gestures** | **Cooldown system validation (Section 8.3)** |
| User Satisfaction Score | ≥ 80% | Post-UAT SUS survey |
| Session Crash Rate | < 1 per 8h | Stress test crash log count |
| Activation Misfire Rate | 0% in INACTIVE | No actions dispatched during INACTIVE state |

### 21.2 Launch Acceptance Criteria

> All P0 user stories implemented and verified. All checkpoint acceptance criteria met, including v1.2 additions (scale invariance, stability, cooldown, smoothing, occlusion tolerance, primary hand selection, calibration, performance budgets). Automated test suite passes with ≥ 80% coverage. Performance Budgets (Section 16) met on reference hardware. No P0 bugs open. User documentation, gesture reference card, and calibration walkthrough complete. Activation Mode verified to produce 0% false triggers in INACTIVE state. Deployment Requirements (Section 20.3) confirmed present.

---

## 22. UI Requirements

*(Unchanged from v1.1, extended with calibration and quality-warning surfaces.)*

### 22.1 Application Windows

**Main Control Panel**
- System tray icon with menu: Open, Toggle Tracking, Switch Profile, Settings, Quit
- Status bar: Active profile, FPS counter, webcam status indicator
- Gesture mapping table: scrollable list of current gesture-action pairs
- Quick-toggle switches for tracking on/off and overlay visibility

**Calibration Wizard** *(New in v1.2 — see Section 15 for full requirements)*
- Step 1: Camera Position check
- Step 2: Sensitivity tuning
- Step 3: Cursor Speed tuning
- Step 4: Tracking Area definition

**Settings Panel**
- Camera tab: Device selector, resolution, FPS target, **camera validation status** *(v1.2)*
- Gesture tab: Confidence threshold slider, cooldown sliders (static/dynamic), stability window slider, **scale-related thresholds (advanced)** *(v1.2)*
- Cursor tab: Speed multiplier, smoothing method selector + factor, calibration wizard launcher
- Profiles tab: Create, rename, delete, import, export profiles
- About tab: Version, licenses, GitHub link

### 22.2 Visual Overlay

- Semi-transparent overlay window, always on top, non-interactive
- Shows webcam preview (quarter-screen, top-right corner by default)
- Hand skeleton rendered in green with landmark dots
- Gesture label badge fades in on detection, fades out after stability+display duration
- Action badge flashes briefly below gesture label
- FPS + context label in top-left corner of overlay
- **Lighting/camera quality warning badge** when applicable *(v1.2)*

> **UI Design Principle:** The overlay and control panel must not obstruct user workflow. Default to compact, minimal UI with full detail accessible on demand. Power users can expand; novice users can keep it simple.

---

*End of GestureOS PRD v1.2*
