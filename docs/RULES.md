# RULES.md — GestureOS Governance Document

**Status:** ACTIVE — HIGHEST PRIORITY DOCUMENT IN THIS REPOSITORY
**Version:** 1.0.0
**Date:** June 2026
**Applies To:** Every AI coding agent, every human developer, every commit, every pull request.

> **This document outranks every other document in this project, including `AI_GUIDE.md`.** If anything in `AI_GUIDE.md`, or in any individual prompt, conflicts with a rule stated here, **this document wins.** No exceptions, no judgment calls, no "in this specific case it's fine." A conflict between this document and any other artifact is itself a stop condition — see Rule 1.4.

This document does not explain *why* GestureOS is architected the way it is — that reasoning lives in `AI_GUIDE.md`. This document exists to make non-compliance **structurally difficult**, by requiring explicit reports, explicit checklists, and explicit sign-off gates before and after every unit of work. Treat every rule below as a gate, not a guideline.

---

## Table of Contents

1. [Document Priority Order](#1-document-priority-order)
2. [Mandatory Reading Requirements](#2-mandatory-reading-requirements)
3. [Scope Control Rules](#3-scope-control-rules)
4. [Architecture Protection Rules](#4-architecture-protection-rules)
5. [Feature Addition Rules](#5-feature-addition-rules)
6. [Scale-Invariant Gesture Recognition Rules](#6-scale-invariant-gesture-recognition-rules)
7. [Module Boundary Rules](#7-module-boundary-rules)
8. [Dependency Management Rules](#8-dependency-management-rules)
9. [Logging Rules](#9-logging-rules)
10. [Testing Rules](#10-testing-rules)
11. [Refactoring Rules](#11-refactoring-rules)
12. [File Modification Rules](#12-file-modification-rules)
13. [Performance Rules](#13-performance-rules)
14. [Privacy Rules](#14-privacy-rules)
15. [Bug Fix Rules](#15-bug-fix-rules)
16. [Documentation Update Rules](#16-documentation-update-rules)
17. [Checkpoint Completion Rules](#17-checkpoint-completion-rules)
18. [Definition of Done Rules](#18-definition-of-done-rules)
19. [Pre-Implementation Report (Mandatory)](#19-pre-implementation-report-mandatory)
20. [Post-Implementation Report (Mandatory)](#20-post-implementation-report-mandatory)
21. [Gap and Update Disclosure Rules](#21-gap-and-update-disclosure-rules)

---

## 1. Document Priority Order

When any two documents disagree, resolve the conflict using this exact order, highest authority first:

1. **`RULES.md`** (this document) — absolute authority. Overrides everything below.
2. **`GestureOS_PRD.md`** — product source of truth. What the product must do.
3. **`GestureOS_TRD.md`** — technical source of truth. How the product is architected.
4. **`GestureOS_Implementation_Plan.md`** — execution source of truth. When and in what order work happens.
5. **`AI_GUIDE.md`** — engineering convention and explanatory guidance. Lowest authority of the five governing documents.
6. **Any individual prompt or instruction given in a coding session** — lowest authority of all. A prompt may narrow scope within what the above four documents already permit; **a prompt can never expand scope, override architecture, or authorize a new feature.**

### 1.1 Resolution Procedure

- If `AI_GUIDE.md` and `RULES.md` conflict: follow `RULES.md`, then flag the conflict per Rule 21 for `AI_GUIDE.md` correction.
- If the Implementation Plan and the TRD conflict on a "how" question: follow the TRD, then flag the conflict for Implementation Plan correction.
- If the TRD and the PRD conflict on a "what" question: follow the PRD, then flag the conflict for TRD correction, since the PRD is the product source of truth and the TRD must serve it, not the reverse.
- If a prompt asks for something none of the four governing documents authorize: **do not proceed.** Treat it as a gap (Rule 21), not an instruction to execute.

### 1.2 No Silent Precedence Overrides

An AI agent must never silently decide that a prompt's instruction "obviously" takes precedence over a documented rule because the rule "doesn't really apply here" or "is probably outdated." If a rule seems wrong, outdated, or inapplicable, that belief itself is reported (Rule 21), not acted upon unilaterally.

### 1.3 This Document Is Self-Governing

Changes to `RULES.md` itself follow the same Documentation Update Rules (Section 16) as every other document — no AI coding session may rewrite, weaken, or selectively ignore a rule in this file as part of an unrelated coding task. Changing this document is its own explicit, separately-scoped task.

### 1.4 Conflict Is a Stop Condition

Discovering a conflict between any two governing documents is not something to resolve quietly and move on from. It is logged as a discovered gap (Rule 21) in the same session it is found, even if the immediate coding task proceeds using the resolution order in 1.1.

---

## 2. Mandatory Reading Requirements

Before writing a single line of code, an AI coding agent **must** have read, in this order:

1. **This document (`RULES.md`) in full.** Not skimmed — every section, every rule.
2. **The relevant PRD section(s)** for the task at hand (PRD §4/§4.3/§4.4 for any gesture work; the relevant `FR-*`/`NFR-*` requirement IDs for any other feature work).
3. **The relevant TRD §3 component specification(s)** for every component the task touches — Responsibilities, Inputs, Outputs, Dependencies, and Error Handling, read in full, not assumed from memory of a prior session.
4. **The relevant Implementation Plan checkpoint section** — to confirm the task is in-scope for the current checkpoint and that the checkpoint's stated dependencies are already satisfied.
5. **The relevant `AI_GUIDE.md` section(s)** — coding standards, naming conventions, and the specific domain-rule sections (e.g., Section 7 for any gesture work, Section 13 for any code touching user data).

### 2.1 No Task Begins Without Confirmed Reading

An AI coding agent must state, at the start of every Pre-Implementation Report (Section 19), which specific sections of which documents were consulted for this task. "I read the documents" is not sufficient — name the sections.

### 2.2 Re-Reading Is Required Per Session, Not Assumed From Memory

A new coding session — even one immediately following a prior session in the same conversation — re-confirms the relevant sections rather than relying on memory of what a prior session established. Documents may have been updated between sessions (Section 16); operating on stale memory of document content is a process violation.

### 2.3 Reading Requirement Scales With Task Risk

A trivial, single-line, clearly-scoped fix still requires reading the directly relevant TRD component spec and the relevant `AI_GUIDE.md` rule. A new feature, a new gesture, or any change touching `gestures/`, `actions/`, or the threading model requires reading the *full* relevant PRD section, TRD section, and Implementation Plan checkpoint — partial reading is not acceptable for higher-risk work.

---

## 3. Scope Control Rules

### 3.1 Scope Is Defined Before Code Is Written

Every task has an explicit, stated scope — the specific files expected to change — declared in the Pre-Implementation Report (Section 19) **before** any file is touched. Scope is not discovered retroactively by looking at what ended up changing.

### 3.2 No Scope Expansion Without Explicit Re-Authorization

If, during implementation, it becomes clear that additional files beyond the originally declared scope must change, **work stops**, the expanded scope is stated explicitly, and reasoning is given for why it's necessary. This is not a formality to skip when the expansion "seems obviously fine" — undisclosed scope expansion is exactly the failure mode this document exists to prevent.

### 3.3 No Opportunistic Changes

Noticing an unrelated improvement opportunity while working on a task does not authorize fixing it in the same change. Note it (Rule 21 — discovered gap, or a simple inline TODO with a reference to a future task), and leave it for a separately-scoped task.

### 3.4 No Checkpoint-Jumping

Work belonging to a later Implementation Plan checkpoint is never started early, even if it seems convenient, even if "it's basically the same file we're already touching." Per Implementation Plan §2's Foundation-First Approach, later checkpoints depend on earlier ones being fully Done — building ahead of that order produces code built against assumptions that haven't been verified yet.

### 3.5 No Checkpoint-Skipping or Reordering

The checkpoint sequence (Checkpoint 0 → 10, Implementation Plan §3) is followed in order. A task is only undertaken if its checkpoint's declared Dependencies (Implementation Plan, each checkpoint's "Dependencies" field) are already at Definition of Done.

### 3.6 Scope and File Count Are Reported, Not Estimated After the Fact

The Post-Implementation Report's Files Added/Modified/Removed fields (Section 20) must exactly match what actually changed — never a rounded-off or approximate summary.

---

## 4. Architecture Protection Rules

### 4.1 The Five Architectural Principles Are Immutable Without Sign-Off

These five principles (`AI_GUIDE.md` §1.3, derived from TRD §1.1) may never be silently violated or "temporarily" set aside for convenience:

1. Deterministic over probabilistic — no trained models, no opaque logic.
2. Scale-invariant by construction — see Section 6 of this document for the full enforcement rule.
3. Local-only — no network calls in the core pipeline.
4. Fail-soft — no single-module failure crashes the main loop.
5. Configuration over code — tunable behavior lives in JSON, not hardcoded.

A change that would violate any of these five is **not a routine code change.** It is an architecture-change request requiring explicit human sign-off and a corresponding TRD update (Rule 16), proposed and flagged, never executed unilaterally.

### 4.2 The Pipeline Order Is Immutable

The 17-stage Runtime State Flow (TRD §5.1) and its 8-domain Foundation-First build order (Implementation Plan §2.1: Camera → Tracking → Analysis → Recognition → Activation → Actions → Context → GUI) are fixed. No task may reorder pipeline stages, skip a stage, or introduce a new stage without an explicit, separately-reviewed TRD architecture change.

### 4.3 The Threading Model Is Immutable

`CaptureThread` owns pipeline state; the GUI thread owns UI; cross-thread communication is exclusively via Qt signals (TRD §2.2). No task may introduce a direct cross-thread call, a shared mutable global, or a lock-based workaround instead of the signal pattern, regardless of how small or "safe" it appears.

### 4.4 Component Responsibilities Are Immutable Without a TRD Update

Each TRD §3 component's Responsibilities, Inputs, Outputs, Dependencies, and Error Handling are fixed contracts. A task may not silently expand, narrow, or reinterpret a component's documented behavior. If a task seems to require a component to do something outside its documented scope, this is a TRD-update proposal (Rule 16), not a quiet implementation decision.

### 4.5 No New Architectural Patterns Without Approval

Introducing a new cross-cutting pattern not already established in the TRD — a new persistence mechanism, a new IPC mechanism, a new state-management approach, a new threading primitive — is an architecture change. It is proposed in a Pre-Implementation Report's Architecture Impact field (Section 19) and requires explicit confirmation before implementation, never assumed permitted because "it's a good idea."

### 4.6 Architecture Violations Are Automatically High-Severity

Any bug whose root cause is a violation of Rules 4.1–4.5 is automatically classified at the highest applicable bug severity tier (`AI_GUIDE.md` §10.1's P0/P1 framework) regardless of how narrow or rare its triggering condition is.
## 5. Feature Addition Rules

### 5.1 No Feature Exists Unless the PRD Names It

A "feature" is any new gesture, action type, profile, UI screen, settings field with new behavioral meaning, or product-visible capability. **No feature may be implemented unless it is already explicitly named in `GestureOS_PRD.md`.** This is the single most important rule in this document for preventing architecture and scope drift over hundreds of sessions.

### 5.2 Requests for Unauthorized Features Are Refused, Not Reinterpreted

If a prompt requests something that is not in the PRD, the correct response is:

1. State explicitly that the request is not present in the PRD.
2. Do **not** implement a "close enough" interpretation, a "minimal version," or a "harmless" stand-in.
3. Log it as a discovered gap with a Recommended PRD Update (Rule 21).
4. Stop and wait for explicit product-owner sign-off before any implementation proceeds.

### 5.3 The Gesture Set Is Closed

PRD §4.3/§4.4 define the complete, closed set of 14 gestures. No 15th gesture, no gesture variant, no "combo gesture," and no per-user custom gesture (explicitly removed from this product per PRD's ML-training removal, PRD §1) may be added without a PRD revision.

### 5.4 Profiles, Contexts, and Action Types Are Closed Sets

The four profiles (PRD §8.9: Presentation, Productivity, Gaming, Accessibility), the four named context categories (PRD §8.7.2: Browser, PowerPoint, Media Players, VS Code) plus `'global'`, and the four `action_type` values plus `cursor_move` (TRD §6.3) are closed sets. Adding a fifth of any of these is a PRD/TRD change, not an implementation task.

### 5.5 Settings Fields Require a Documented Purpose

A new settings field is only added if it configures behavior the PRD already requires and the TRD already specifies a tunable parameter for. A settings field added "for flexibility" with no corresponding documented behavior is forbidden — every field in `settings.json` traces to a specific TRD §7 schema entry and a specific consuming component.

### 5.6 Feature Sign-Off Is Explicit, Not Assumed From Silence

The absence of an objection to a proposed feature is not sign-off. Sign-off is an explicit, affirmative human confirmation, recorded before implementation begins.

---

## 6. Scale-Invariant Gesture Recognition Rules

This section exists because scale-invariance is GestureOS's core technical differentiator (PRD §5) and its single most-repeated regression pattern (`AI_GUIDE.md` §10.6's worked example: a normalization step silently dropped during a later edit). These rules are absolute and non-negotiable.

### 6.1 No Raw-Pixel or Raw-Frame-Normalized Threshold, Ever

Every distance comparison in `gestures/static_recognizer.py` divides the raw landmark distance by `hand.scale.palm_width` or `hand.scale.palm_height` **before** comparison to any threshold (PRD §5.2, TRD §4.3). There are zero exceptions to this rule. A pull request or AI-generated change containing a line of the shape `if euclidean_distance(a, b) < <constant>:` without a normalization division immediately preceding it is **rejected on sight**, no further review needed.

```python
# FORBIDDEN — automatic rejection, no exceptions
if euclidean_distance(landmarks[4], landmarks[8]) < 0.05:
    ...

# REQUIRED PATTERN
normalized_dist = euclidean_distance(landmarks[4], landmarks[8]) / hand.scale.palm_width
if normalized_dist < 0.35:
    ...
```

### 6.2 Every Dynamic Gesture Normalizes Displacement and Velocity

Every dynamic-gesture rule in `gestures/dynamic_recognizer.py` normalizes wrist displacement and velocity by `hand_scale` before threshold comparison (TRD §4.4). The same automatic-rejection standard from 6.1 applies.

### 6.3 `hand.scale is None` Has Exactly One Correct Response

If `hand.scale is None`, the function returns `None` immediately (PRD FR-SC-04). There is no fallback path, no "use a default scale," no raw-pixel emergency path. A function that attempts any calculation when `hand.scale is None` is a defect.

### 6.4 Every New or Modified Static Gesture Requires a Parametrized Scale Test

Per `AI_GUIDE.md` §7.3/§9.6's template, any static gesture using a Priority-3 (normalized distance) rule requires a test parametrized across at least `[0.5, 1.0, 2.0, 3.0]` synthetic scale factors, asserting recognition succeeds at every scale tested. **This test is not optional and its absence blocks merge.**

### 6.5 Every New or Modified Dynamic Gesture Requires Distance-Independence Verification

The same scale-invariance discipline applies to dynamic gestures, following the TRD §4.6 pattern of synthetically scaling a known-good trajectory fixture and confirming recognition is unaffected.

### 6.6 The Recognition Priority Order Is Mandatory

PRD §5.1's four-tier priority order (Finger State → Finger/Joint Angles → Normalized Distances → Motion Trajectories) governs which signal type a gesture rule uses. Prefer the lowest-numbered tier sufficient to distinguish the gesture from every other gesture in the set (`AI_GUIDE.md` §7.1 step 2).

### 6.7 Scale-Invariance Regressions Are Always P1 or Higher

Per `AI_GUIDE.md` §10.1's classification rule: any bug that breaks scale-invariance for any gesture is automatically at least P1, regardless of how narrow the triggering condition seems.

---

## 7. Module Boundary Rules

### 7.1 The TRD §8 / AI Guide §4 Folder Structure Is Fixed

No file or folder may be created outside the structure already defined in `GestureOS_TRD.md` §8 and reproduced in `AI_GUIDE.md` §4, without an explicit, separately-reviewed structure-change proposal.

### 7.2 Each Folder's Forbidden Responsibilities Are Hard Boundaries

`AI_GUIDE.md` §4.1's per-folder Forbidden Responsibilities list is enforced literally:

- `gestures/` never imports `pyautogui`, `pynput`, or any OS-dispatch library.
- `camera/` never imports PyQt6, MediaPipe, or anything with knowledge of gestures/actions/UI.
- `tracking/` never contains gesture-rule logic (`detect_*` functions belong in `gestures/` only).
- `models/` never contains business logic beyond simple derived-property accessors.
- `overlay/` never contains decision logic — it draws what it's told, it never decides.
- `ui/` never holds a direct reference to a `CaptureThread`-owned object.

A change that would place code in violation of any of the above is rejected, full stop, regardless of how minor the violating import or call appears.

### 7.3 Dependency Direction Is One-Way

Per `AI_GUIDE.md` §5.3: Camera → Tracking → Analysis → Recognition → Activation → Context → Actions → Diagnostics/Overlay. A component imports only from components earlier in this chain, plus `models/`, `settings/`, and `diagnostics/`. `overlay/` and `ui/` are the only read-only exceptions.

### 7.4 No Circular Imports, No Workarounds

If a task appears to require a circular import, this is a signal that shared logic must be extracted to `models/` or a new shared utility — never a signal to add a deferred/local import as a workaround (`AI_GUIDE.md` §5.5).

### 7.5 No Reaching Into Another Component's Internals

A component's only interface to the rest of the system is the data object(s) documented in its TRD §3 Outputs field. Reaching past a public interface into another component's private state is forbidden; if a feature requires it, the feature is mis-scoped (`AI_GUIDE.md` §5.4) and must be flagged (Rule 21), not implemented as a boundary violation.

---

## 8. Dependency Management Rules

### 8.1 The Stack Is Closed

The technology stack named in TRD §1.3 and reproduced in `AI_GUIDE.md` §3 (Python 3.11+, OpenCV, MediaPipe, NumPy, PyQt6, PyAutoGUI, pynput, pywin32, pytest, PyInstaller, plus the platform-specific `pyobjc`/`python-xlib` equivalents named in TRD §11.2) is the complete, closed dependency set.

### 8.2 No New Third-Party Package Without Explicit Justification and Sign-Off

A new dependency is added only if:

1. It is required to satisfy a PRD requirement that the existing stack cannot fulfill, **and**
2. This is stated explicitly in the Pre-Implementation Report's Dependencies field, **and**
3. Explicit sign-off is given before the dependency is added to `requirements.txt`.

A dependency added to solve a problem the existing stack already has a documented way to solve (e.g., adding a new HTTP library, a new GUI toolkit, a new image-processing library that duplicates OpenCV/NumPy functionality) is forbidden outright, not merely discouraged.

### 8.3 Exact Version Pinning Only

`requirements.txt` pins exact versions (`==`), never minimum-version ranges (`>=`), per Implementation Plan Checkpoint 0's rationale: every checkpoint and every platform must build against an identical dependency set.

### 8.4 Platform-Conditional Dependencies Use Explicit Markers

Windows-only, macOS-only, and Linux-only dependencies (`pywin32`, `pyobjc`, `python-xlib`) are installed via explicit `sys_platform` markers in `requirements.txt` — never installed unconditionally on a platform where they don't apply (`AI_GUIDE.md` §3).

### 8.5 Dependency Changes Are Verified Before Merge

Any change to `requirements.txt` requires, before merge:

1. A fresh `pip install -r requirements.txt` succeeding in a clean virtual environment.
2. The full unit + integration test suite passing against the updated dependency set.
3. If the change touches MediaPipe specifically: a PyInstaller smoke-build verifying the model-bundling issue (TRD §16, `AI_GUIDE.md` §2.4's version-pin discipline note) has not regressed.

### 8.6 Dependency Changes Are Reported

Every Post-Implementation Report's Dependency Changes field (Section 20) explicitly states whether `requirements.txt` was touched, and if so, exactly which package(s) and version(s) changed, added, or removed.
## 9. Logging Rules

### 9.1 Every Loggable Event Category Must Be Logged

Per `AI_GUIDE.md` §8.1's table, the following categories are mandatory wherever the relevant component produces a corresponding event: Camera Events, Tracking Events, Gesture Events, Action Events, Context Events, Activation Events, Lighting Events, Profile Events, Settings Events, Errors, Warnings. **Omitting a required log event for a new or modified component is a Definition-of-Done failure**, not a minor oversight to fix later.

### 9.2 All Logging Goes Through `DiagnosticsManager`

No component logs via bare `print()` or an independently-configured `logging.getLogger()` call. Every log call uses `DiagnosticsManager`'s structured helper methods, matching the format `[TIMESTAMP] [LEVEL] [MODULE] Message {key: value, ...}` (TRD §9.1).

### 9.3 Log Level Discipline Is Enforced

- **DEBUG:** high-frequency, expected-noise, file-only, only when `developer_mode` is true.
- **INFO:** state changes and successful operations worth a permanent record.
- **WARN:** recoverable, degraded-but-continuing conditions.
- **ERROR:** failed operations requiring fallback or user-facing surfacing.

Logging a routine, expected, non-noteworthy outcome at WARN or ERROR is forbidden (`AI_GUIDE.md` §8.2) — e.g., "no mapping found for this gesture+context" is a normal outcome, not a warning condition, except when `developer_mode` is enabled.

### 9.4 No Sensitive Data in Logs

Per Privacy Rules (Section 14), log files never contain raw landmark coordinates or frame image data, even in `developer_mode`. Only gesture names, confidence scores, timestamps, and similar non-raw derived values are logged.

### 9.5 New Log Categories Require Documentation Sync

If a new component introduces an event that doesn't fit any existing category in `AI_GUIDE.md` §8.1, the new category is added to that table **in the same change**, not left implicit in code alone (Rule 16).

### 9.6 Logging Coverage Is Verified, Not Assumed

The Pre-Implementation Report's Implementation Plan field (Section 19) states which logging categories the task will emit. The Post-Implementation Report's Testing Performed field (Section 20) confirms those log lines were actually observed during testing, not merely written in code and never exercised.

---

## 10. Testing Rules

### 10.1 No Function Ships Without Unit Tests

Per `AI_GUIDE.md` §9.1: every new function has unit tests using synthetic/fixture data only — never a live camera or hardware dependency for a unit test, ever.

### 10.2 Coverage Floor Is 80%, No Exceptions

Per TRD §13.7 / `AI_GUIDE.md` §9.5: `gestures/`, `actions/`, `profiles/`, `settings/`, `tracking/` maintain ≥80% line coverage at all times. A change that drops coverage below this floor for a touched module is not mergeable until coverage is restored. There is no "this module is too simple to need tests" exception.

### 10.3 Scale-Invariance Tests Are Mandatory for Gesture Work

Per Section 6.4/6.5 of this document — any static or dynamic gesture work without the required parametrized scale test is incomplete, regardless of how well it appears to work in manual testing.

### 10.4 Integration Tests Are Required Where Meaningful

Per `AI_GUIDE.md` §9.2: new cross-cutting behavior receives an integration test once the pipeline is sufficiently wired for one to be meaningful (from the Activation checkpoint onward, per Implementation Plan §2.3). Do not add an integration test against an incomplete pipeline chain that cannot actually verify the claimed behavior.

### 10.5 Bug Fixes Always Include a Regression Test

Per Section 15 of this document and `AI_GUIDE.md` §9.4/§10.3: a regression test reproducing the original failure is written **before** the fix, confirmed to fail against pre-fix code, and confirmed to pass after the fix. A bug fix submitted without a regression test is incomplete.

### 10.6 The Full Suite Runs Before Every Merge

Not just the tests for the touched module — the full unit + integration suite. A change in one module silently breaking an unrelated test elsewhere is exactly the failure mode full-suite verification exists to catch.

### 10.7 Performance Tests Are Reserved for Performance-Relevant Changes

Per `AI_GUIDE.md` §9.3/§14.2: any change adding or modifying a per-frame pipeline stage requires re-running the performance test suite (Section 13 of this document), not just unit/integration tests, before being considered verified.

### 10.8 Test Failures Are Never Silently Skipped or Marked `xfail` to Unblock Merge

A failing test is either fixed, or the underlying behavior change is explicitly justified and the test updated to match new, approved behavior — never disabled, skipped, or marked expected-failure as a workaround to merge faster.

---

## 11. Refactoring Rules

### 11.1 A Refactor Is Behavior-Preserving By Definition

Per `AI_GUIDE.md` §16.3: if a "refactor" changes any observable behavior — a threshold, a default value, a log message's content, an API's return value — it is not a refactor. It is a feature change or bug fix, and must be scoped, tested, and reported as one.

### 11.2 A Refactor Never Crosses a Folder Boundary

Moving logic from one folder to another (e.g., `gestures/` to `tracking/`) is an architecture change requiring Section 4's sign-off process, even if the code itself is unchanged — it alters which component owns that responsibility.

### 11.3 A Refactor's Verification Is the Existing Test Suite, Unchanged

The correct verification for a pure refactor is: the full existing test suite passes with no new tests required (since no new behavior exists). Tests are only updated if the refactor changed an internal structure the tests were inappropriately coupled to — and that coupling fix is itself called out explicitly in the Post-Implementation Report.

### 11.4 A Refactor Is Never Mixed With a Feature or Bug Fix in the Same Change

Mixing "I refactored X while fixing Y" makes both harder to review and harder to revert independently. A refactor that becomes necessary while fixing a bug is either done as a strictly prior, separately-reviewed change, or deferred and noted (Rule 21) rather than bundled in.

### 11.5 Refactors Still Require a Pre-Implementation Report

A refactor is implementation work like any other — it requires the full Pre/Post-Implementation Report cycle (Sections 19–20), with the Implementation Plan field explicitly stating "this is a behavior-preserving refactor" and the verification strategy confirming that claim.

---

## 12. File Modification Rules

### 12.1 Declared Scope Is Binding

Only files declared in the Pre-Implementation Report's Files Expected To Change field (Section 19) are modified, unless Rule 3.2's explicit re-authorization process is followed for any expansion.

### 12.2 No File Is Modified Without Understanding Its Current Contents

Before editing any file, its current, full, up-to-date contents are read — never edited based on assumption, memory of an earlier version, or a partial view. This is especially critical for files that may have changed since an earlier session in the same conversation.

### 12.3 New Files Follow Existing Naming and Structural Conventions

A new file's name, its location within the TRD §8 structure, and its internal code style match the conventions already established in `AI_GUIDE.md` §6 and the existing codebase — never a stylistic departure introduced because it seemed cleaner.

### 12.4 Deletions Are Explicit and Justified

A file is never silently deleted as a side effect of another change. File removal is explicitly declared in both the Pre-Implementation Report (as an expected change) and the Post-Implementation Report's Files Removed field, with justification.

### 12.5 Generated/Build Artifacts Are Never Hand-Edited

Files produced by a build or generation step (e.g., a PyInstaller output, a generated `.spec` file's compiled form) are never directly edited — the generating process or its source configuration is edited instead.

### 12.6 Configuration Files Follow Their Documented Schema Exactly

Edits to `settings.json`, `profiles.json`, `mappings/*.json`, or `context_map.json` structures (not user data, but the *schema* itself) must match TRD §7's documented schema exactly. A schema change is a TRD-update-requiring change (Rule 16), never an ad-hoc field addition.
## 13. Performance Rules

### 13.1 The Five Budgets Are Fixed

Reproduced exactly from PRD §16, no reinterpretation permitted:

| Metric | Target |
|---|---|
| FPS | ≥ 25 |
| Detection Latency | < 100 ms |
| End-to-End Action Latency | < 150 ms |
| CPU Usage | < 20% (single core average) |
| Memory Usage | < 300 MB |

### 13.2 The Only Permitted Tie-Break Is the One the PRD States

If a change cannot satisfy all five budgets simultaneously, the PRD's own stated priority applies: FPS and latency are never sacrificed for CPU savings (PRD §16's explicit note). CPU is the parameter revisited first. This is the only authorized tie-break — no other budget may be unilaterally relaxed.

### 13.3 New Per-Frame Pipeline Stages Require Cost Justification

Any addition to the `CaptureThread`'s per-frame loop states, in the Pre-Implementation Report's Risks field, whether the addition is expected to be O(1)/negligible or whether it requires dedicated profiling before merge (TRD §15.2's analysis pattern).

### 13.4 Image-Array Work Is Vectorized, Never Looped in Pure Python

Any new per-frame operation touching frame/image data uses NumPy/OpenCV vectorized operations, matching the existing pattern (e.g., `LightingMonitor`'s `cv2.cvtColor` + `.mean()`, TRD §3.4). A per-pixel Python loop on frame data is forbidden in the per-frame path.

### 13.5 Performance-Relevant Changes Require Profiling, Not Assumption

A change whose performance cost isn't obviously negligible is profiled with the `cProfile` harness (TRD §15.3) before being declared acceptable — "this should be fast" is not a verification method.

### 13.6 Performance Regressions Block Merge

A change that causes the full performance test suite (Section 10.7) to fail any of the five budgets is not merged until resolved, full stop — performance budget compliance is a gate, not a goal to aspire to.

---

## 14. Privacy Rules

### 14.1 No Frame, Landmark, or Gesture Data Is Ever Persisted

Per TRD §14: frames, landmarks, and raw gesture geometry exist only in memory for the duration of one pipeline pass. No feature may add persistence of this data, for any reason — debugging convenience, future feature exploration, telemetry — without this being treated as a privacy-architecture change requiring explicit sign-off, never a routine addition.

### 14.2 Log Files Never Contain Raw Coordinate or Image Data

Restated from Rule 9.4: logs contain gesture names, confidence scores, and timestamps — never raw landmarks or frames, even in `developer_mode`. The Debug Overlay may *display* this data live; it must never be written to a log file.

### 14.3 No Network-Capable Import in the Core Pipeline

`camera/`, `tracking/`, `gestures/`, `context/`, and `actions/` never import `requests`, `urllib`, `http.client`, `socket`, `aiohttp`, or any equivalent network library. This is enforced by an automated CI lint check (TRD §12.3); an AI agent must never add such an import to these folders under any framing ("just for an update check," "just for telemetry," "just for crash reporting") without this being escalated as an explicit privacy-architecture-change proposal first.

### 14.4 Webcam Permission Is Native-OS-Dialog Only

GestureOS never implements a custom permission UI and never attempts to bypass, cache around, or auto-retry past an OS-level permission denial.

### 14.5 `~/.gestureos/` Remains Unencrypted By Design

This is a deliberate, documented prior decision (TRD §14.4), not an oversight. Adding encryption is itself a privacy-architecture reconsideration requiring sign-off, not a routine "hardening" change.

### 14.6 Every Feature Touching User Data Passes the Sensitive-Data Checklist

Before merge, per `AI_GUIDE.md` §13.3: does this feature write any new data to disk (and if so, does it belong in an existing schema)? Does it transmit data anywhere (if yes, this is a privacy-architecture change requiring sign-off, full stop)? Does its logging accidentally include raw coordinate or image data?

---

## 15. Bug Fix Rules

### 15.1 Every Bug Is Classified Before Any Fix Work Begins

Per `AI_GUIDE.md` §10.1's P0/P1/P2/P3 framework. Classification is stated explicitly in the Pre-Implementation Report.

### 15.2 Architecture Violations Are Automatically P1 or Higher

Restated from Rule 4.6/6.7: any bug whose root cause is a violation of an Architecture Protection Rule (Section 4) or a Scale-Invariant Recognition Rule (Section 6) is automatically classified at P1 or higher, regardless of how rare its triggering condition appears.

### 15.3 Reproduce First, Theorize Second

No fix is proposed before the bug has been reliably reproduced, per `AI_GUIDE.md` §10.2's governing rule. A fix for an unreproduced bug is a guess, and guesses are forbidden — they accumulate as silent technical debt.

### 15.4 Root Cause Is Identified at the Component Level

The Runtime State Flow (TRD §5.1) is used as a diagnostic checklist to identify the specific failing pipeline stage, and TRD §3's component map is used to trace that stage to one specific, named, responsible component — not a vague "somewhere in gesture recognition."

### 15.5 A Bug May Reveal a Documentation Gap, Not Just a Code Defect

If the code does exactly what the PRD/TRD specify, and the result is still wrong, this is escalated per Rule 21 (Recommended PRD/TRD Update) — it is never silently patched with an undocumented behavior change that diverges from what the source documents state.

### 15.6 Fix Scope Is Minimal and Stated Explicitly

The fix touches only the component(s) actually responsible for the bug. Opportunistic adjacent changes are forbidden (Rule 3.3).

### 15.7 Every Fix Includes a Permanent Regression Test

Restated from Rule 10.5 — non-negotiable.

### 15.8 Fix Verification Follows the Full Process

1. Regression test fails against pre-fix code (confirmed, not assumed).
2. Fix implemented at minimal scope.
3. Regression test passes.
4. Full test suite passes.
5. For P0/P1 specifically: a manual verification pass in a realistic running session, beyond automated test coverage.

### 15.9 Fix Disposition Is Always Reported

The bug's classification and root cause are recorded in the Post-Implementation Report (Section 20), so future debugging sessions can search prior fixes for similar patterns.
## 16. Documentation Update Rules

### 16.1 Documents Are Kept in Sync With Code, Always

A code change that affects what a governing document describes updates that document **in the same change set** — never as a deferred follow-up, never left for "later cleanup." A document that drifts out of sync with the code it describes becomes actively harmful: future AI sessions will trust the (now-wrong) document over tribal knowledge of what actually shipped.

### 16.2 What Triggers a Mandatory Documentation Update

| Change Type | Document(s) That Must Update |
|---|---|
| New or changed product requirement | `PRD.md` |
| New or changed architecture, component spec, or data model | `TRD.md` |
| New or changed repository structure | `TRD.md` §8 **and** `AI_GUIDE.md` §4, both, same change |
| New or changed checkpoint scope, sequencing, or acceptance criteria | `Implementation_Plan.md` |
| New logging category | `AI_GUIDE.md` §8.1 table |
| New coding convention or pattern established by a non-trivial decision | `AI_GUIDE.md` relevant section |
| New rule discovered necessary through a bug's root-cause analysis | `RULES.md` and/or `AI_GUIDE.md`, as appropriate to the rule's nature |
| Any gap formally resolved | The relevant source document, removing it from "open" status |

### 16.3 No AI Session Edits `RULES.md` as a Side Effect

Changes to this document are their own explicit, separately-scoped task, never bundled into an unrelated feature or bug-fix change (restated from Rule 1.3).

### 16.4 Document Updates Are Verified for Consistency

After updating any governing document, a check is performed (at minimum, a targeted re-read of the changed section and any section that cross-references it) to confirm no contradiction was introduced between documents, per the Document Priority Order (Section 1).

### 16.5 Version Bumps Accompany Substantive Document Changes

Following the pattern already established across PRD v1.1→v1.2 and TRD v1.0→v1.1: a MINOR version bump accompanies a batch of new or formalized requirements; document content is never silently edited without a corresponding version increment.

### 16.6 Documentation Debt Is Never Accumulated Silently

If a documentation update is identified as necessary but cannot be completed in the current session (e.g., it requires product-owner input), it is explicitly logged as an open item per Rule 21 — never left as an implicit, undocumented gap between what the code does and what the documents say.

---

## 17. Checkpoint Completion Rules

### 17.1 Checkpoint Order Is Fixed

Checkpoint 0 → 10, as defined in Implementation Plan §3, executed strictly in sequence. Restated from Rule 3.4/3.5.

### 17.2 A Checkpoint's Definition of Done Is the Only Valid Completion Signal

A checkpoint is considered complete only when every item in its Implementation Plan Definition of Done section is satisfied — not when "most of it" works, not when the primary deliverable is functional but secondary items are deferred.

### 17.3 No Checkpoint Begins Before Its Dependencies Are Done

Every checkpoint's Implementation Plan "Dependencies" field names the prior checkpoint(s) that must already be at Definition of Done. This is verified explicitly before any work on a new checkpoint begins — not assumed because "the prior checkpoint was probably finished."

### 17.4 Checkpoint Acceptance Criteria Are Verified, Not Self-Certified by Code Existing

A checkpoint's Acceptance Criteria (Implementation Plan, each checkpoint section) are explicitly tested and confirmed — code existing that *should* satisfy a criterion is not the same as the criterion being verified to pass.

### 17.5 Regressions in Prior Checkpoints Block the Current Checkpoint

If work in the current checkpoint causes a prior checkpoint's Acceptance Criteria to start failing, this is treated with the same severity as a P0/P1 bug (Section 15) and is resolved before the current checkpoint can be considered complete — a checkpoint is never "done" while it has silently broken a previous one.

### 17.6 Checkpoint Completion Is Explicitly Reported

A Post-Implementation Report (Section 20) for any change that completes a checkpoint's final remaining item explicitly states which checkpoint was completed and confirms every Definition of Done item, not just the item that was the immediate focus of the session.

### 17.7 No Premature Checkpoint Declaration

A checkpoint is never declared complete based on partial verification ("the main path works, edge cases are probably fine"). Every Acceptance Criterion and every Testing Strategy item specified for that checkpoint in the Implementation Plan must be explicitly satisfied.

---

## 18. Definition of Done Rules

### 18.1 The Four Tiers Apply, in Order of Increasing Scope

Per `AI_GUIDE.md` §15: Feature Complete → Module Complete → Checkpoint Complete → Project Complete. A higher tier's completion requires every lower tier it contains to already be complete — a Checkpoint cannot be Complete while a Feature within it is not.

### 18.2 Feature Complete Requires All Seven Conditions

Per `AI_GUIDE.md` §15.1: behavior matches PRD exactly; TRD implementation details followed exactly; unit tests cover success and failure cases; integration test added where meaningful; no Core Principle violation introduced; logging requirements met; code review checklist satisfied.

### 18.3 Module Complete Requires All Six Conditions

Per `AI_GUIDE.md` §15.2: matches TRD §3 spec exactly; every method independently Feature Complete; ≥80% coverage; folder boundary respected with zero violations; public interface fully documented; cross-cutting concerns (logging, settings) fully wired, not stubbed.

### 18.4 Checkpoint Complete Requires All Eight Conditions

Per `AI_GUIDE.md` §15.3 / Implementation Plan §16.1, restated in Section 17 of this document.

### 18.5 Project Complete Requires All Six Conditions

Per `AI_GUIDE.md` §15.4 / Implementation Plan §16.3: all 11 checkpoints Done in order; every PRD requirement implemented and verified; every PRD Success Metric met on reference hardware; PRD §20.4 Release Acceptance Gate satisfied; every Gap has a documented disposition; no requirement, architecture decision, or feature was altered, removed, or silently reinterpreted during implementation.

### 18.6 "Done" Is Never Self-Declared Without Evidence

A claim of "Feature Complete," "Module Complete," "Checkpoint Complete," or "Project Complete" in any report (Sections 19–20) is accompanied by the specific evidence satisfying each condition of that tier — test results, coverage numbers, explicit confirmation of each Acceptance Criterion — not an unsupported assertion.
## 19. Pre-Implementation Report (Mandatory)

**Every coding task — feature, refactor, bug fix, or documentation change — begins with this report, completed in full, before any file is touched.** A task that proceeds to implementation without this report having been produced and reviewed is a process violation regardless of the quality of the resulting code.

### 19.1 Template

```markdown
# Pre-Implementation Report

## Task Reference
- Task description (as given):
- Documents consulted (specific sections, not just document names):
  - PRD:
  - TRD:
  - Implementation Plan:
  - AI Guide:
  - RULES.md: [confirm full document read]

## Task Understanding
- What is being asked for, in my own words:
- Which PRD requirement ID(s) / TRD section(s) this task implements or modifies:
- Which Implementation Plan checkpoint this task belongs to:
- Confirmation that this checkpoint's Dependencies (Rule 17.3) are already Done:

## Files Expected To Change
- New files to be created (full path, per TRD §8 structure):
- Existing files to be modified (full path):
- Files expected to be removed, if any (full path + justification):

## Dependencies
- New third-party dependencies required, if any (Rule 8.2 justification):
- Internal component dependencies (which TRD §3 components this task's code will call or be called by):
- Confirmation that no dependency direction rule (Section 7.3) is violated:

## Risks
- Architecture risks (does this touch any of the five Architectural Principles, Section 4.1?):
- Scale-invariance risk (does this touch gesture distance/velocity logic, Section 6?):
- Performance risk (does this add to the per-frame pipeline, Section 13.3?):
- Privacy risk (does this touch user data or persistence, Section 14?):
- Other risks specific to this task:

## Implementation Plan
- Step-by-step approach:
- Logging that will be added (which categories, per Section 9):
- Tests that will be written (unit / integration / scale-invariance / regression, per Section 10):

## Architecture Impact
- Does this introduce, modify, or remove any TRD §3 component? (If yes — STOP, this requires Section 4 sign-off before proceeding)
- Does this introduce a new architectural pattern not already in the TRD? (If yes — STOP, Rule 4.5 applies)
- Confirmation that this task requires no PRD/TRD/Implementation Plan/RULES.md change — OR explicit flag that it does (Section 21)
```

### 19.2 Report Review Is a Gate

The Pre-Implementation Report is reviewed (by a human, or as a self-check against this document's rules) before implementation begins. If any field reveals a Section 4 (Architecture), Section 5 (Feature), or Section 21 (Gap) trigger, implementation **does not proceed** until that trigger is resolved through its proper process.

---

## 20. Post-Implementation Report (Mandatory)

**Every coding task ends with this report, completed in full, before the task is considered done.** This report is the evidence required by Rule 18.6 — it is not a summary written for convenience, it is the verification record.

### 20.1 Template

```markdown
# Post-Implementation Report

## Implementation Summary
- What was actually built/changed (plain-language summary):
- Does this match the Pre-Implementation Report's stated plan? If not, what changed and why (Rule 3.2):

## Changes Made
- Detailed description of the actual changes, component by component:

## Files Added
- (full path, one per line)

## Files Modified
- (full path, one per line, with a one-line description of what changed in each)

## Files Removed
- (full path, one per line, with justification — empty if none)

## Dependency Changes
- requirements.txt changes, if any (package, version, added/removed/changed):
- Confirmation a clean install + full test suite passed against the updated dependency set (Rule 8.5):

## Architecture Impact
- Confirmation no TRD §3 component's documented contract was altered without sign-off (Rule 4.4):
- Confirmation no folder boundary was violated (Section 7):
- Confirmation no raw-pixel/raw-frame-normalized threshold was introduced, if this task touched `gestures/` (Section 6.1):

## Testing Performed
- Unit tests added/modified (file names, what they cover):
- Integration tests added/modified, if applicable:
- Scale-invariance tests added, if this task touched gesture recognition (Section 6.4/6.5):
- Regression test added, if this was a bug fix (Section 15.7):
- Full test suite result (pass/fail, coverage percentage for touched modules):
- Logging verified observed during testing (Rule 9.6):

## Known Issues
- Any remaining issue not fixed in this change, with severity classification (Section 15.1) and reasoning for deferral:

## Technical Risks
- Any risk introduced or newly understood as a result of this change:
- Cross-reference to Implementation Plan §15.1 Risk Matrix, if applicable:

## Documentation Impact
- Which governing document(s), if any, were updated in this change (Rule 16.2):
- Confirmation that no documentation debt was left unaddressed (Rule 16.6) — OR explicit listing of deferred documentation items, logged per Section 21:

## Future Checkpoint Impact
- Does this change affect the scope, risk, or readiness of any later checkpoint? If yes, describe:

## Developer Actions Required
- Any manual step a human developer must take (e.g., re-running a migration, manually verifying a platform-specific behavior, approving a flagged gap):

## New Requirements Discovered
(See Section 21 for the full disclosure rule — list here or state "None")

## Missing Requirements Identified
(See Section 21 — list here or state "None")

## Recommended PRD Updates
(See Section 21 — list here or state "None")

## Recommended TRD Updates
(See Section 21 — list here or state "None")

## Recommended AI Guide Updates
(See Section 21 — list here or state "None")

## Recommended Implementation Plan Updates
(See Section 21 — list here or state "None")
```

### 20.2 An Empty Report Is Not Acceptable

Every field in the template is addressed explicitly — "None" or "N/A" is an acceptable value for a field with nothing to report, but the field is never simply omitted. An omitted field is indistinguishable from an unconsidered field, and this document exists specifically to prevent things going unconsidered.

---

## 21. Gap and Update Disclosure Rules

This section formalizes the discovery-and-disclosure pattern already established by the Implementation Plan's Gap Register (Implementation Plan, Appendix A) and `AI_GUIDE.md` §11.5, and makes it **mandatory output**, not optional commentary, for every implementation task.

### 21.1 Six Categories of Disclosure Are Required at the End of Every Task

Every Post-Implementation Report explicitly addresses each of the following, even when the answer is "none found":

1. **New requirements discovered** — product behavior that turned out to be necessary during implementation but wasn't explicitly named in the PRD (e.g., an edge case the PRD's rule summary didn't anticipate).
2. **Missing requirements identified** — a gap in the PRD/TRD/Implementation Plan where the documents are silent on something the task needed to assume an answer for.
3. **Recommended PRD updates** — specific, proposed wording or section additions, not just "the PRD should mention X."
4. **Recommended TRD updates** — specific, proposed component spec or schema changes.
5. **Recommended AI Guide updates** — specific, proposed new rules, examples, or corrections to existing guidance.
6. **Recommended Implementation Plan updates** — specific, proposed checkpoint scope, sequencing, or risk-matrix changes.

### 21.2 Disclosure Happens Even If the Task Proceeded Using an Assumption

If a task had to make a judgment call to resolve an ambiguity (per `AI_GUIDE.md` §11.1 item 6 — "explain assumptions"), that judgment call is **always** disclosed here as either a Missing Requirement (21.1.2) or a candidate for one of the four Recommended Update categories (21.1.3–21.1.6) — never silently absorbed into the implementation as if the ambiguity never existed.

### 21.3 Disclosure Is Specific, Not Vague

"The PRD could be clearer about X" is not an acceptable disclosure. The required format is: *what* is missing or unclear, *where* it should be addressed (which document, ideally which section), and *what* the proposed resolution is, even if that proposal is just "needs product-owner input — here are the 2-3 plausible options I see."

### 21.4 No Implementation Proceeds Past a Gap Without Flagging It First

Per Rule 1.4 and `AI_GUIDE.md` §11.5: a gap discovered mid-task does not get silently resolved and mentioned only in passing in the final report. It is flagged at the point of discovery — work may continue on the unambiguous parts of the task, but the gap itself is never quietly implemented around.

### 21.5 The Gap Register Pattern Is the Model

Following Implementation Plan Appendix A's existing format, every disclosed gap across the project's lifetime is expected to accumulate into a single, consolidated, append-only register (Gap ID, Description, Location, Status), making every prior session's disclosures auditable by every future session — this is what prevents the same ambiguity from being independently (and differently) resolved by two different AI sessions months apart.

### 21.6 Disclosure Is Not Optional Even When the Task "Went Fine"

A clean, uneventful implementation still completes Section 21's six categories explicitly. The absence of friction during implementation is not evidence of the absence of a documentation gap — it may simply mean the gap wasn't hit this time.

---

*End of RULES.md v1.0.0*

> **This document has no expiration and no implicit sunset.** It governs every GestureOS coding session — human or AI, large task or small — until explicitly superseded by a new version through the same Documentation Update process (Section 16) it itself imposes on every other document in this project.
