# Thumbs Up Pipeline Audit Report

## Test Results Summary

| Test Case | MediaPipe MP | Custom `detect_thumbs_up` | First Failing Stage | Reason |
|---|---|---|---|---|
| Canonical Thumbs Up (Right) | N/A (no model) | **PASS** (conf=0.861) | — | All checks pass |
| Left Thumbs Up (mirrored) | N/A (no model) | **PASS** (conf=0.861) | — | All checks pass |
| Thumbs Up +45° rotation | N/A (no model) | **PASS** (conf=0.861) | — | Rotation-invariant direction works |
| Thumbs Up +70° rotation | N/A (no model) | **PASS** (conf=0.861) | — | Rotation-invariant direction works |
| Thumbs Up +90° rotation | N/A (no model) | **PASS** (conf=0.861) | — | Rotation-invariant direction works |
| Closed Fist | N/A (no model) | **REJECT** | `detect_thumbs_up` — Signal 2 | `thumb_extension_score` = 0.364 < 0.55 |
| Open Palm | N/A (no model) | **REJECT** | `detect_thumbs_up` — Signal 1 | 4 non-thumb fingers extended |
| Pinch | N/A (no model) | **REJECT** | `detect_thumbs_up` — Signal 1 | Index finger extended (PIP=166°) |
| Left Thumbs Up +45° | N/A (no model) | **PASS** (conf=0.861) | — | All checks pass |

## Pipeline Stages (in order)

### Stage 0: PrimaryHandFilter (`primary_hand_filter.py`)
- Sets `hand.gesture_eligible = False` when `dominant_hand_mode` mismatches chirality.
- **Fails only when dominant_hand_mode is active and chirality is wrong.**

### Stage 1: StaticGestureEngine confidence threshold (`static_gesture_engine.py:108-109`)
- Drops candidates with `confidence < 0.85` (default).
- **Can reject a valid thumbs_up if combined score falls below 0.85.**

### Stage 2: `detect_thumbs_up()` — Signal 1: Finger curl check (`static_recognizer.py:382-384`)
- Requires all 4 non-thumb fingers curled (PIP angle < 160°).
- **Diagnostic data:** Synthetic thumbs-up has index=128.7°, middle=135.0°, ring=146.3°, pinky=149.0°. Real hands may exceed 160° on ring/pinky if not fully curled.

### Stage 3: `detect_thumbs_up()` — Signal 2: Thumb extension score (`static_recognizer.py:388-389`)
- Threshold: `thumb_extension_score >= 0.55`.
- **Most likely rejection point in real-world use.** The multi-feature score combines:
  - Reach ratio (50%): `dist(wrist,tip) / dist(wrist,mcp)`
  - Length ratio (30%): `dist(mcp,tip) / dist(cmc,mcp)`
  - Separation ratio (20%): `dist(tip,index_mcp) / dist(wrist,mcp)`
- **Critical penalty:** If fewer than 2 features have score > 0.2, the overall score is **halved** (gesture_utils.py:254-255).
- Fist scores 0.364 vs 0.55 threshold. Pinch scores 0.350.
- **On canonical thumbs-up:** all 3 features active, score = 0.933.

### Stage 4: `detect_thumbs_up()` — Signal 3: Direction score (`static_recognizer.py:395-397`)
- Uses `thumb_direction_score()` — palm-relative, **rotation-invariant** coordinate frame.
- Threshold: `> 0.0` (very permissive).
- **Diagnostic data:** Direction score = 0.7000 at all rotation angles (0°, 45°, 70°, 90°). Projection onto palm_y axis is always 1.0 even under rotation. Projection onto palm_z is 0.0 (synthetic fixtures have z=0).
- **This check is NOT the problem.** The old image-space direction check was already replaced with the rotation-invariant version.

### Stage 5: GestureFuser (`gesture_fuser.py:110-167`)
- If MediaPipe result has `confidence >= 0.80`, it wins unconditionally over custom recognizers.
- If MediaPipe result has `confidence < 0.80`, the MP result is removed; custom recognizers compete.
- **Potential failure if MP misclassifies thumbs-up as another gesture at >= 0.80 confidence.**

### Stage 6: GestureGate.StabilityFilter (`gesture_gate.py:52-75`)
- Requires 200ms of consistent gesture before emitting.
- **Potential failure due to landmark jitter or tracking flicker resetting the hold timer.**

### Stage 7: GestureGate.CooldownFilter (`gesture_gate.py:86-145`)
- Blocks same (role, gesture) for 500ms after emission.

### Stage 8: ActivationGate (`capture_thread.py:570-576`)
- When INACTIVE: all `cleared_results` are discarded (pipeline still runs for hold-timer).
- **Requires ACTIVE state — user must toggle via Open Palm hold or keyboard shortcut.**

## Root Cause Analysis

The **most likely first rejection point** for a valid thumbs-up in real-world use is:

**`detect_thumbs_up()` — Signal 2: `thumb_extension_score` < 0.55** (`static_recognizer.py:388-389`)

### Why this fails on real hands:

1. **Foreshortening in 2D projection:** When the hand is slightly rotated away from the camera, the thumb appears shorter in the image plane. The reach ratio and separation ratio drop because they rely on 2D Euclidean distances.

2. **Aggressive active-feature penalty** (`gesture_utils.py:254-255`): If only 1 of the 3 features has a score > 0.2, the overall score is **halved**. This can easily push a borderline thumbs-up from ~0.55 to ~0.27. Example: a hand where the thumb is close to the index MCP (low separation), or where the thumb-cmc/mcp geometry is tight (low length ratio).

3. **Separation ratio is inherently variable:** `dist(tip, index_mcp) / dist(wrist, mcp)` depends on the hand's natural anatomy. Hands with a shorter thumb or a thumb that naturally rests closer to the index finger will score lower on this 20%-weighted feature.

### Second most likely rejection point:

**StaticGestureEngine confidence threshold** (`static_gesture_engine.py:108-109`, default 0.85). The confidence formula is `0.6 + 0.4 * thumb_score * direction_score`. Even when both checks pass, if `thumb_score` is marginal (e.g., 0.60) and `direction_score` is moderate (e.g., 0.50), the confidence is `0.6 + 0.4 * 0.60 * 0.50 = 0.72`, which is below 0.85.

### Third most likely:

**GestureFuser MediaPipe priority** (`gesture_fuser.py:131-132`). If MediaPipe Gesture Recognizer returns a non-thumbs_up gesture (e.g., `fist` or `open_palm`) with confidence >= 0.80, it overrides the custom `detect_thumbs_up()` result entirely. The MP model's classification behavior cannot be analyzed without access to the actual `gesture_recognizer.task`.

## Recommended Fix

**Lower the `thumb_extension_score` threshold or reduce the active-feature penalty.** Specifically:

1. **Reduce the active-feature penalty multiplier** from `0.5` to `0.75` at `gesture_utils.py:255`. This still penalizes single-feature activations but avoids a catastrophic 50% score reduction that can push a genuine thumbs-up below threshold.

2. **Alternatively, lower the extension threshold** from `0.55` to `0.45` at `static_recognizer.py:388`. The fist fixture scores 0.364 and pinch scores 0.350, so a threshold of 0.45 still cleanly rejects non-thumbs-up poses while giving real thumbs-ups more margin.

3. **Consider reducing the confidence threshold** from `0.85` to `0.80` for thumbs_up specifically, or making the confidence formula more weighted toward the thumb_extension_score. The direction check is already very robust (rotation-invariant, permissive threshold).

**No changes needed** to:
- `thumb_direction_score()` — rotation invariance works correctly
- Finger-state PIP angle threshold (160°) — appropriate for rejecting non-curled poses
- `GestureFuser` — MP priority logic is correct
- `GestureGate` — timing parameters are sensible
