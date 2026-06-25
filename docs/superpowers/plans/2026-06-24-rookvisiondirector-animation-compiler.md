# RookVisionDirector Animation Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Python-only compiler that turns a high-level object-motion authoring spec into a validated baked replay track consumed by native `/director/replay`, with zero native or C# changes.

**Architecture:** A pure math module (`director_motion.py`) compiles per-object keyframe tracks (relative TRS deltas, easing, quaternion slerp, S→R→T-about-pivot composition) into per-frame nested-4×4 matrices. An orchestrator (`director_compiler.py`) validates the spec, normalizes the timeline, expands groups, resolves live source state via an injected `call_native`, builds `object_frames` (via the motion module) and `camera_frames` (via the existing `camera_planner`), and returns `{track, provenance}`. A thin MCP tool `rhino_director_compile_motion` wraps it. Replay remains the sole executor.

**Tech Stack:** Python 3 (stdlib only — `math`, `uuid`, `dataclasses`-free), pytest. Reuses `mcp_server/src/rook/timeline.py`, `camera_planner.py`, and the native routes `/director/object-states`, `/director/view-state`, `/director/curve-samples` via injected `call_native`.

## Global Constraints

- **No native / C# / runtime change.** Only new Python modules + tests + one `server.py` tool registration. No production change to `director.py`; no imports of private (`_`-prefixed) helpers from `director.py`.
- **Output track must satisfy the merged native parser** (`DirectorReplayHandler.cpp` / `DirectorFrame.cpp`): `transform_semantics == "absolute_from_source"`; `animated_object_ids` unique, non-empty, ≤ 256; `frame_count` in 1..3000; `camera_frames`/`object_frames` length == `frame_count`, `frame_index == i+1` in order; each frame's `object_id` set exactly equals `animated_object_ids`; per-object `source_state.bbox_*` identical across frames; `transform` is a **nested 4×4** (list of 4 rows × 4 cols, `[i][j] → m_xform[i][j]`, translation in column 3) and must be **invertible**; `source_state.validation_strength == "bbox_only"` with required `bbox_min`/`bbox_max`.
- **Caps pre-mirrored** so replay never first-surfaces a limit: objects ≤ 256, frames ≤ 3000, `1000/fps ≤ 250ms` (fps ≥ 4), `frame_count*(1000/fps) ≤ 60000ms`.
- **fps is a positive integer** (matches `timeline.py`); fractional fps rejected; the fps-None path rejected (`track.fps` must be concrete).
- **Rotation is shortest-arc only**; `|angle_degrees| ≤ 180`; multi-turn/spin deferred.
- **Group names must not parse as Rhino UUIDs** (§4.1 of the spec); `target` resolves group-first then UUID.
- MCP `inputSchema` must avoid `enum`/`oneOf`/`anyOf`/`allOf`/`not` (OpenAI-rejected keywords).
- Spec reference: `docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-compiler-design.md`.

---

### Task 1: Easing functions (`director_motion.py`)

**Files:**
- Create: `mcp_server/src/rook/director_motion.py`
- Test: `mcp_server/tests/test_director_motion.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `EASING_NAMES: frozenset[str]` = `{"linear","ease_in","ease_out","ease_in_out"}`
  - `apply_easing(name: str, u: float) -> float` — maps segment progress `u∈[0,1]`; assumes `name` is valid (membership is enforced by the caller in Task 2). Endpoints fixed: `f(0)=0`, `f(1)=1`.

- [ ] **Step 1: Write the failing test**

```python
# mcp_server/tests/test_director_motion.py
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_motion as dm


@pytest.mark.parametrize("name", sorted(dm.EASING_NAMES))
def test_easing_pins_endpoints(name):
    assert dm.apply_easing(name, 0.0) == pytest.approx(0.0)
    assert dm.apply_easing(name, 1.0) == pytest.approx(1.0)


def test_easing_linear_is_identity():
    assert dm.apply_easing("linear", 0.25) == pytest.approx(0.25)


def test_easing_in_starts_slow():
    # ease_in is below the linear line in the first half
    assert dm.apply_easing("ease_in", 0.5) < 0.5


def test_easing_out_starts_fast():
    assert dm.apply_easing("ease_out", 0.5) > 0.5


def test_easing_in_out_is_symmetric_about_midpoint():
    assert dm.apply_easing("ease_in_out", 0.5) == pytest.approx(0.5)
    assert dm.apply_easing("ease_in_out", 0.25) == pytest.approx(
        1.0 - dm.apply_easing("ease_in_out", 0.75)
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_motion.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.director_motion'`.

- [ ] **Step 3: Write minimal implementation**

```python
# mcp_server/src/rook/director_motion.py
"""Pure object-motion compilation for RookVisionDirector PR4.

No I/O, no native calls, no MCP. Compiles per-object keyframe tracks of
relative TRS deltas into per-frame nested-4x4 transform matrices consumed by
native /director/replay. See
docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-compiler-design.md
"""
from __future__ import annotations

import math

EASING_NAMES = frozenset({"linear", "ease_in", "ease_out", "ease_in_out"})


def apply_easing(name: str, u: float) -> float:
    """Map segment progress u in [0,1] -> eased progress. Endpoints fixed."""
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    if name == "linear":
        return u
    if name == "ease_in":
        return u * u
    if name == "ease_out":
        return 1.0 - (1.0 - u) * (1.0 - u)
    if name == "ease_in_out":
        # smoothstep
        return u * u * (3.0 - 2.0 * u)
    # Unknown names are rejected upstream (Task 2); be defensive.
    raise MotionError("invalid_keyframe", f"unknown easing: {name}")


class MotionError(ValueError):
    """Keyframe/motion-domain validation failure carrying a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_director_motion.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_motion.py mcp_server/tests/test_director_motion.py
git commit -m "feat(director): easing functions for animation compiler (PR4 Task 1)"
```

---

### Task 2: Object keyframe track compilation (`director_motion.py`)

**Files:**
- Modify: `mcp_server/src/rook/director_motion.py`
- Test: `mcp_server/tests/test_director_motion.py`

**Interfaces:**
- Consumes: `apply_easing`, `EASING_NAMES`, `MotionError` (Task 1).
- Produces:
  - `IDENTITY_4X4: list[list[float]]`
  - `compile_object_track(keyframes, *, frame_count, source_center, default_easing) -> list[list[list[float]]]`
    - `keyframes`: list of raw authoring keyframe dicts: `{"t": float, "translate"?: [3], "rotate"?: {"axis":[3], "angle_degrees": float, "pivot"?: "object_center"|[3]}, "scale"?: float|[3], "ease_from_previous"?: str}`.
    - `source_center`: `[x,y,z]` bbox center, used to resolve `pivot == "object_center"`.
    - Returns `frame_count` nested-4×4 matrices (one per frame, frame 1..N). Raises `MotionError` (codes `invalid_keyframe`, `inconsistent_pivot`).

- [ ] **Step 1: Write the failing test**

```python
# append to mcp_server/tests/test_director_motion.py

def _kf(t, **kw):
    kf = {"t": t}
    kf.update(kw)
    return kf


def test_single_translate_keyframe_pins_endpoints_and_holds_shape():
    # one keyframe at t=1 moving +10 in X; frame 1 = identity, frame N = full delta
    frames = dm.compile_object_track(
        [_kf(1.0, translate=[10, 0, 0])],
        frame_count=3, source_center=[0, 0, 0], default_easing="linear",
    )
    assert len(frames) == 3
    assert frames[0] == dm.IDENTITY_4X4              # frame 1 is source identity
    assert frames[1][0][3] == pytest.approx(5.0)     # linear midpoint
    assert frames[2][0][3] == pytest.approx(10.0)    # final, translation in column 3
    # nested 4x4 shape
    assert len(frames[2]) == 4 and all(len(row) == 4 for row in frames[2])


def test_hold_after_last_keyframe():
    # last keyframe at t=0.5; frames after hold the delta
    frames = dm.compile_object_track(
        [_kf(0.5, translate=[8, 0, 0])],
        frame_count=3, source_center=[0, 0, 0], default_easing="linear",
    )
    assert frames[1][0][3] == pytest.approx(8.0)   # t=0.5
    assert frames[2][0][3] == pytest.approx(8.0)   # t=1.0 holds


def test_scale_about_object_center_keeps_center_fixed():
    # scale 2x about object_center=(5,0,0): the center maps to itself
    frames = dm.compile_object_track(
        [_kf(1.0, scale=2.0)],
        frame_count=2, source_center=[5, 0, 0], default_easing="linear",
    )
    m = frames[1]
    # apply M to the center point (5,0,0,1) -> should stay (5,0,0)
    x = m[0][0] * 5 + m[0][3]
    assert x == pytest.approx(5.0)
    assert m[0][0] == pytest.approx(2.0)


def test_rotation_slerp_halfway_is_half_angle():
    # rotate 90deg about Z at t=1; frame at t=0.5 ~ 45deg
    frames = dm.compile_object_track(
        [_kf(1.0, rotate={"axis": [0, 0, 1], "angle_degrees": 90})],
        frame_count=3, source_center=[0, 0, 0], default_easing="linear",
    )
    half = frames[1]
    c = math.cos(math.radians(45))
    assert half[0][0] == pytest.approx(c, abs=1e-6)
    assert half[1][1] == pytest.approx(c, abs=1e-6)


def test_reject_scale_zero():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track([_kf(1.0, scale=0.0)], frame_count=2,
                                source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_angle_over_180():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [_kf(1.0, rotate={"axis": [0, 0, 1], "angle_degrees": 270})],
            frame_count=2, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_non_identity_t0():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [_kf(0.0, translate=[1, 0, 0]), _kf(1.0, translate=[5, 0, 0])],
            frame_count=2, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_duplicate_t():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [_kf(0.5, translate=[1, 0, 0]), _kf(0.5, translate=[2, 0, 0])],
            frame_count=3, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_out_of_range_t():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track([_kf(1.5, translate=[1, 0, 0])], frame_count=2,
                                source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"


def test_reject_inconsistent_pivot():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track(
            [
                _kf(0.5, rotate={"axis": [0, 0, 1], "angle_degrees": 30, "pivot": "object_center"}),
                _kf(1.0, rotate={"axis": [0, 0, 1], "angle_degrees": 60, "pivot": [9, 9, 9]}),
            ],
            frame_count=3, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "inconsistent_pivot"


def test_reject_unknown_easing():
    with pytest.raises(dm.MotionError) as ei:
        dm.compile_object_track([_kf(1.0, translate=[1, 0, 0], ease_from_previous="boing")],
                                frame_count=2, source_center=[0, 0, 0], default_easing="linear")
    assert ei.value.code == "invalid_keyframe"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_motion.py -v`
Expected: FAIL — `AttributeError: module 'rook.director_motion' has no attribute 'compile_object_track'`.

- [ ] **Step 3: Write minimal implementation**

Append to `mcp_server/src/rook/director_motion.py`:

```python
# --- linear algebra (nested 4x4 row-major; posed = M . source_point) ---

IDENTITY_4X4 = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


def _mat_id():
    return [row[:] for row in IDENTITY_4X4]


def _mat_mul(a, b):
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            out[i][j] = sum(a[i][k] * b[k][j] for k in range(4))
    return out


def _translation(v):
    m = _mat_id()
    m[0][3], m[1][3], m[2][3] = float(v[0]), float(v[1]), float(v[2])
    return m


def _scale_mat(s):
    m = _mat_id()
    m[0][0], m[1][1], m[2][2] = float(s[0]), float(s[1]), float(s[2])
    return m


def _normalize3(v):
    n = math.sqrt(sum(float(c) * float(c) for c in v))
    if n < 1e-12:
        return None
    return [float(c) / n for c in v]


def _quat_from_axis_angle(axis, angle_deg):
    a = _normalize3(axis)
    if a is None:
        raise MotionError("invalid_keyframe", "rotation axis is degenerate")
    half = math.radians(float(angle_deg)) / 2.0
    s = math.sin(half)
    return (math.cos(half), a[0] * s, a[1] * s, a[2] * s)


_QUAT_IDENTITY = (1.0, 0.0, 0.0, 0.0)


def _quat_slerp(q0, q1, t):
    dot = sum(q0[i] * q1[i] for i in range(4))
    if dot < 0.0:                      # shortest arc
        q1 = tuple(-c for c in q1)
        dot = -dot
    if dot > 0.9995:                   # near-parallel: nlerp
        out = tuple(q0[i] + t * (q1[i] - q0[i]) for i in range(4))
        n = math.sqrt(sum(c * c for c in out)) or 1.0
        return tuple(c / n for c in out)
    theta0 = math.acos(max(-1.0, min(1.0, dot)))
    theta = theta0 * t
    s0 = math.sin(theta0 - theta) / math.sin(theta0)
    s1 = math.sin(theta) / math.sin(theta0)
    return tuple(s0 * q0[i] + s1 * q1[i] for i in range(4))


def _quat_to_mat4(q):
    w, x, y, z = q
    m = _mat_id()
    m[0][0] = 1 - 2 * (y * y + z * z)
    m[0][1] = 2 * (x * y - z * w)
    m[0][2] = 2 * (x * z + y * w)
    m[1][0] = 2 * (x * y + z * w)
    m[1][1] = 1 - 2 * (x * x + z * z)
    m[1][2] = 2 * (y * z - x * w)
    m[2][0] = 2 * (x * z - y * w)
    m[2][1] = 2 * (y * z + x * w)
    m[2][2] = 1 - 2 * (x * x + y * y)
    return m


# --- keyframe parsing + track compilation ---

class _ParsedKey:
    __slots__ = ("t", "translate", "scale", "quat", "pivot", "ease")

    def __init__(self, t, translate, scale, quat, pivot, ease):
        self.t = t
        self.translate = translate
        self.scale = scale
        self.quat = quat
        self.pivot = pivot          # None if no rotation
        self.ease = ease


def _parse_scale(value):
    if value is None:
        return [1.0, 1.0, 1.0]
    if isinstance(value, (list, tuple)):
        if len(value) != 3:
            raise MotionError("invalid_keyframe", "scale vector must have 3 components")
        comps = [float(c) for c in value]
    else:
        comps = [float(value)] * 3
    for c in comps:
        if not math.isfinite(c) or c <= 0.0:
            raise MotionError("invalid_keyframe", "scale components must be finite and > 0")
    return comps


def _parse_translate(value):
    if value is None:
        return [0.0, 0.0, 0.0]
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise MotionError("invalid_keyframe", "translate must be a 3-number array")
    comps = [float(c) for c in value]
    if any(not math.isfinite(c) for c in comps):
        raise MotionError("invalid_keyframe", "translate components must be finite")
    return comps


def _resolve_pivot(rotate, source_center):
    pivot = rotate.get("pivot", "object_center")
    if pivot == "object_center":
        return [float(c) for c in source_center]
    if isinstance(pivot, (list, tuple)) and len(pivot) == 3:
        comps = [float(c) for c in pivot]
        if any(not math.isfinite(c) for c in comps):
            raise MotionError("invalid_keyframe", "pivot components must be finite")
        return comps
    raise MotionError("invalid_keyframe", "pivot must be 'object_center' or a 3-number array")


def _parse_key(kf, source_center, default_easing):
    if not isinstance(kf, dict) or "t" not in kf:
        raise MotionError("invalid_keyframe", "keyframe must be an object with a 't'")
    t = float(kf["t"])
    if not math.isfinite(t) or t < 0.0 or t > 1.0:
        raise MotionError("invalid_keyframe", "keyframe t must be in 0..1")
    translate = _parse_translate(kf.get("translate"))
    scale = _parse_scale(kf.get("scale"))
    quat = _QUAT_IDENTITY
    pivot = None
    rotate = kf.get("rotate")
    if rotate is not None:
        if not isinstance(rotate, dict) or "axis" not in rotate or "angle_degrees" not in rotate:
            raise MotionError("invalid_keyframe", "rotate requires axis and angle_degrees")
        angle = float(rotate["angle_degrees"])
        if not math.isfinite(angle) or abs(angle) > 180.0:
            raise MotionError("invalid_keyframe", "rotate angle_degrees must be finite and |angle| <= 180")
        quat = _quat_from_axis_angle(rotate["axis"], angle)
        pivot = _resolve_pivot(rotate, source_center)
    ease = kf.get("ease_from_previous", default_easing)
    if ease not in EASING_NAMES:
        raise MotionError("invalid_keyframe", f"unknown easing: {ease}")
    return _ParsedKey(t, translate, scale, quat, pivot, ease)


def _lerp(a, b, e):
    return a + (b - a) * e


def _lerp3(a, b, e):
    return [_lerp(a[i], b[i], e) for i in range(3)]


def _compose(translate, scale, quat, pivot):
    inner = _mat_mul(_quat_to_mat4(quat), _scale_mat(scale))
    if pivot is not None:
        inner = _mat_mul(_translation(pivot), _mat_mul(inner, _translation([-pivot[0], -pivot[1], -pivot[2]])))
    return _mat_mul(_translation(translate), inner)


def compile_object_track(keyframes, *, frame_count, source_center, default_easing):
    if not keyframes:
        raise MotionError("invalid_keyframe", "object track requires at least one keyframe")
    parsed = [_parse_key(kf, source_center, default_easing) for kf in keyframes]

    # unique + sorted t
    ts = [p.t for p in parsed]
    if len(set(ts)) != len(ts):
        raise MotionError("invalid_keyframe", "keyframe t values must be unique")
    parsed.sort(key=lambda p: p.t)

    # explicit t=0 must be identity
    if parsed[0].t == 0.0:
        p0 = parsed[0]
        if p0.translate != [0.0, 0.0, 0.0] or p0.scale != [1.0, 1.0, 1.0] or p0.quat != _QUAT_IDENTITY:
            raise MotionError("invalid_keyframe", "explicit t=0 keyframe must be identity")

    # Pivot for BOTH scale and rotation. Defaults to object_center (source_center)
    # so a scale-only or rotate-only keyframe transforms in place. Explicit rotate
    # pivots override and must be consistent across the target's keyframes.
    track_pivot = [float(c) for c in source_center]
    pivots = [p.pivot for p in parsed if p.pivot is not None]
    if pivots:
        track_pivot = pivots[0]
        for pv in pivots[1:]:
            if any(abs(pv[i] - track_pivot[i]) > 1e-9 for i in range(3)):
                raise MotionError("inconsistent_pivot", "rotation pivots differ within one target's keyframes")

    # prepend implicit identity at t=0 if absent (segment ease comes from destination)
    if parsed[0].t != 0.0:
        identity_key = _ParsedKey(0.0, [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], _QUAT_IDENTITY, None, "linear")
        parsed.insert(0, identity_key)

    frames = []
    for i in range(frame_count):
        t = 0.0 if frame_count == 1 else i / (frame_count - 1)
        frames.append(_sample(parsed, t, track_pivot))
    return frames


def _sample(parsed, t, track_pivot):
    # find bracketing keyframes
    if t <= parsed[0].t:
        a = b = parsed[0]
    elif t >= parsed[-1].t:
        a = b = parsed[-1]
    else:
        a = parsed[0]
        b = parsed[-1]
        for k in range(len(parsed) - 1):
            if parsed[k].t <= t <= parsed[k + 1].t:
                a, b = parsed[k], parsed[k + 1]
                break
    if a.t == b.t:
        translate, scale, quat = b.translate, b.scale, b.quat
    else:
        u = (t - a.t) / (b.t - a.t)
        e = apply_easing(b.ease, u)
        translate = _lerp3(a.translate, b.translate, e)
        scale = _lerp3(a.scale, b.scale, e)
        quat = _quat_slerp(a.quat, b.quat, e)
    # Always compose about the track pivot (identity rotation/scale + a pivot wrap
    # is a no-op, so pure-translate frames stay exact).
    return _compose(translate, scale, quat, track_pivot)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_director_motion.py -v`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_motion.py mcp_server/tests/test_director_motion.py
git commit -m "feat(director): object keyframe track compilation (PR4 Task 2)"
```

---

### Task 3: Spec validation — timeline, groups, targets, caps (`director_compiler.py`)

**Files:**
- Create: `mcp_server/src/rook/director_compiler.py`
- Test: `mcp_server/tests/test_director_compiler.py`

**Interfaces:**
- Consumes: `timeline.resolve_timeline` (existing); nothing from `director_motion` yet.
- Produces:
  - `class DirectorCompileError(Exception)` with `code: str`, `message: str`, `extra: dict`; method `to_data() -> dict` = `{"code", "message", **extra}`.
  - `resolve_compiler_timeline(spec) -> dict` = `{"fps": int, "frame_count": int, "duration_seconds": float}`.
  - `expand_targets(spec) -> dict[str, list[dict]]` mapping `object_id -> keyframes` (group expansion + target resolution + duplicate detection).
  - `validate_caps(object_count: int, frame_count: int, fps: int) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# mcp_server/tests/test_director_compiler.py
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_compiler as dc

U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"


def test_timeline_duration_shape():
    out = dc.resolve_compiler_timeline({"timeline": {"fps": 24, "duration_seconds": 5}})
    assert out == {"fps": 24, "frame_count": 120, "duration_seconds": 5.0}


def test_timeline_frame_count_shape():
    out = dc.resolve_compiler_timeline({"timeline": {"fps": 30, "frame_count": 90}})
    assert out["fps"] == 30 and out["frame_count"] == 90
    assert out["duration_seconds"] == pytest.approx(3.0)


def test_timeline_rejects_fps_none_path():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.resolve_compiler_timeline({"frame_count": 100})  # no timeline block
    assert ei.value.code == "invalid_timeline"


def test_timeline_rejects_fractional_fps():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.resolve_compiler_timeline({"timeline": {"fps": 23.976, "frame_count": 90}})
    assert ei.value.code == "invalid_timeline"


def test_expand_explicit_id():
    spec = {"motion": [{"target": U1, "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]}]}
    expanded = dc.expand_targets(spec)
    assert set(expanded) == {U1}


def test_expand_group_and_mixed():
    spec = {
        "groups": {"towers": [U1, U2]},
        "motion": [{"target": "towers", "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]}],
    }
    expanded = dc.expand_targets(spec)
    assert set(expanded) == {U1, U2}


def test_reject_uuid_shaped_group_name():
    spec = {"groups": {U1: [U2]}, "motion": [{"target": U1, "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "invalid_input"


def test_reject_unknown_group():
    spec = {"motion": [{"target": "ghosts", "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "unknown_group"


def test_reject_empty_group():
    spec = {"groups": {"empty": []}, "motion": [{"target": "empty", "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "empty_group"


def test_reject_bad_group_member():
    spec = {"groups": {"g": ["not-a-uuid"]}, "motion": [{"target": "g", "keyframes": [{"t": 1.0}]}]}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "invalid_input"


def test_reject_duplicate_object_target_across_motion():
    spec = {
        "groups": {"a": [U1]},
        "motion": [
            {"target": "a", "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]},
            {"target": U1, "keyframes": [{"t": 1.0, "translate": [0, 1, 0]}]},
        ],
    }
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.expand_targets(spec)
    assert ei.value.code == "duplicate_object_target"


def test_caps_objects():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=257, frame_count=10, fps=24)
    assert ei.value.code == "object_count_exceeds_cap"


def test_caps_frames():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=1, frame_count=3001, fps=24)
    assert ei.value.code == "frame_count_exceeds_cap"


def test_caps_dwell():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=1, frame_count=10, fps=3)  # 1000/3 > 250
    assert ei.value.code == "frame_dwell_exceeds_cap"


def test_caps_duration():
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.validate_caps(object_count=1, frame_count=2000, fps=24)  # 2000*41.6ms > 60000
    assert ei.value.code == "replay_duration_exceeds_cap"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_compiler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.director_compiler'`.

- [ ] **Step 3: Write minimal implementation**

```python
# mcp_server/src/rook/director_compiler.py
"""Animation compiler (PR4): compiles a high-level object-motion authoring spec
into the baked replay track consumed by native /director/replay. Python-only;
no native changes. See
docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-compiler-design.md
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from . import camera_planner, timeline
from .bridge import call_rhino


class DirectorCompileError(Exception):
    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_data(self) -> dict:
        return {"code": self.code, "message": self.message, **self.extra}


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        _uuid.UUID(value.strip())
        return True
    except (ValueError, AttributeError):
        return False


def resolve_compiler_timeline(spec: dict) -> dict:
    block = spec.get("timeline")
    if not isinstance(block, dict):
        raise DirectorCompileError(
            "invalid_timeline", "timeline block with fps is required (fps-None path unsupported)")
    fps = block.get("fps")
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise DirectorCompileError("invalid_timeline", "timeline.fps must be a positive integer")
    has_duration = "duration_seconds" in block
    has_frame_count = "frame_count" in block
    if has_duration == has_frame_count:
        raise DirectorCompileError(
            "invalid_timeline", "timeline needs exactly one of duration_seconds or frame_count")
    if has_duration:
        # reuse the verified timeline.py normalizer
        try:
            resolved = timeline.resolve_timeline({"timeline": {"fps": fps, "duration_seconds": block["duration_seconds"]}})
        except timeline.TimelineError as exc:
            raise DirectorCompileError("invalid_timeline", str(exc)) from exc
        return {"fps": resolved["fps"], "frame_count": resolved["frame_count"],
                "duration_seconds": float(resolved["duration_seconds"])}
    # {fps, frame_count}: compiler computes duration itself
    fc = block.get("frame_count")
    if isinstance(fc, bool) or not isinstance(fc, int) or fc < 1:
        raise DirectorCompileError("invalid_timeline", "timeline.frame_count must be a positive integer")
    return {"fps": fps, "frame_count": fc, "duration_seconds": fc / fps}


def _resolve_group(name: str, groups: dict) -> list[str]:
    members = groups[name]
    if not isinstance(members, list) or not members:
        raise DirectorCompileError("empty_group", f"group '{name}' resolves to no objects")
    out = []
    for m in members:
        if not _is_uuid(m):
            raise DirectorCompileError("invalid_input", f"group '{name}' member is not a valid object UUID: {m!r}")
        out.append(m)
    return out


def expand_targets(spec: dict) -> dict:
    groups = spec.get("groups") or {}
    if not isinstance(groups, dict):
        raise DirectorCompileError("invalid_input", "groups must be an object")
    for name in groups:
        if _is_uuid(name):
            raise DirectorCompileError("invalid_input", f"group name must not be UUID-shaped: {name!r}")

    motion = spec.get("motion")
    if not isinstance(motion, list) or not motion:
        raise DirectorCompileError("invalid_input", "motion must be a non-empty array")

    expanded: dict[str, list[dict]] = {}
    for entry in motion:
        if not isinstance(entry, dict) or "target" not in entry:
            raise DirectorCompileError("invalid_input", "motion entry must be an object with a target")
        target = entry["target"]
        keyframes = entry.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            raise DirectorCompileError("invalid_input", "motion entry requires a non-empty keyframes array")
        if isinstance(target, str) and target in groups:
            object_ids = _resolve_group(target, groups)
        elif _is_uuid(target):
            object_ids = [target.strip()]
        elif isinstance(target, str):
            raise DirectorCompileError("unknown_group", f"target is not a declared group or valid UUID: {target!r}")
        else:
            raise DirectorCompileError("invalid_input", "target must be a string (group name or object UUID)")
        for oid in object_ids:
            if oid in expanded:
                raise DirectorCompileError(
                    "duplicate_object_target",
                    f"object {oid} is claimed by more than one motion track", object_id=oid)
            expanded[oid] = keyframes
    return expanded


def validate_caps(object_count: int, frame_count: int, fps: int) -> None:
    if object_count > 256:
        raise DirectorCompileError("object_count_exceeds_cap", "animated objects exceed 256")
    if frame_count > 3000:
        raise DirectorCompileError("frame_count_exceeds_cap", "frame_count exceeds 3000")
    dwell_ms = 1000.0 / fps
    if dwell_ms > 250.0:
        raise DirectorCompileError("frame_dwell_exceeds_cap", "1000/fps exceeds 250ms (fps too low)")
    if frame_count * dwell_ms > 60000.0:
        raise DirectorCompileError("replay_duration_exceeds_cap", "frame_count*dwell exceeds 60000ms")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_director_compiler.py -v`
Expected: PASS (14 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_compiler.py mcp_server/tests/test_director_compiler.py
git commit -m "feat(director): compiler spec/timeline/group/cap validation (PR4 Task 3)"
```

---

### Task 4: Source-state resolution + object_frames (`director_compiler.py`)

**Files:**
- Modify: `mcp_server/src/rook/director_compiler.py`
- Test: `mcp_server/tests/test_director_compiler.py`

**Interfaces:**
- Consumes: `expand_targets`, `DirectorCompileError` (Task 3); `director_motion.compile_object_track`, `director_motion.MotionError` (Task 2).
- Produces:
  - `async resolve_source_states(call_native, object_ids, port) -> dict[str, dict]` mapping `object_id -> {"bbox_min","bbox_max","state_hash"}`.
  - `build_object_frames(expanded, source_states, frame_count, default_easing) -> list[dict]` — list of `{"frame_index", "object_transforms":[{"object_id","source_state","transform"}]}`, objects sorted by id, identical `source_state` across frames.

- [ ] **Step 1: Write the failing test**

```python
# append to mcp_server/tests/test_director_compiler.py
import asyncio


def _objstate(oid, bbox_min, bbox_max):
    return {"object_id": oid, "bbox_min": bbox_min, "bbox_max": bbox_max,
            "validation_strength": "bbox_only", "state_hash": None}


class FakeNative:
    def __init__(self, objects, *, object_states_ok=True):
        self.objects = objects
        self.object_states_ok = object_states_ok
        self.calls = []

    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, data))
        if endpoint == "/director/object-states":
            if not self.object_states_ok:
                return {"success": False, "data": {"code": "x", "message": "boom"}}
            return {"success": True, "data": {"objects": self.objects, "units": "Inches"}}
        raise AssertionError(f"unexpected endpoint {endpoint}")


def test_resolve_source_states_indexes_by_id():
    fake = FakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    states = asyncio.run(dc.resolve_source_states(fake, [U1], None))
    assert states[U1]["bbox_min"] == [0, 0, 0]


def test_resolve_source_states_missing_object_fails():
    fake = FakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.resolve_source_states(fake, [U1, U2], None))
    assert ei.value.code == "source_resolution_failed"


def test_resolve_source_states_native_failure():
    fake = FakeNative([], object_states_ok=False)
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.resolve_source_states(fake, [U1], None))
    assert ei.value.code == "source_resolution_failed"


def test_build_object_frames_every_object_every_frame():
    expanded = {U1: [{"t": 1.0, "translate": [4, 0, 0]}], U2: [{"t": 1.0, "translate": [0, 4, 0]}]}
    states = {U1: _objstate(U1, [0, 0, 0], [2, 2, 2]), U2: _objstate(U2, [0, 0, 0], [2, 2, 2])}
    frames = dc.build_object_frames(expanded, states, frame_count=3, default_easing="linear")
    assert len(frames) == 3
    for f in frames:
        ids = {ot["object_id"] for ot in f["object_transforms"]}
        assert ids == {U1, U2}
        for ot in f["object_transforms"]:
            assert ot["source_state"]["validation_strength"] == "bbox_only"
            assert ot["source_state"]["bbox_min"] == [0, 0, 0]
    # frame 1 is identity for both
    assert frames[0]["object_transforms"][0]["transform"][0][3] == pytest.approx(0.0)


def test_build_object_frames_propagates_motion_error_code():
    expanded = {U1: [{"t": 1.0, "scale": 0.0}]}
    states = {U1: _objstate(U1, [0, 0, 0], [2, 2, 2])}
    with pytest.raises(dc.DirectorCompileError) as ei:
        dc.build_object_frames(expanded, states, frame_count=2, default_easing="linear")
    assert ei.value.code == "invalid_keyframe"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_compiler.py -k "source_states or object_frames" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'resolve_source_states'`.

- [ ] **Step 3: Write minimal implementation**

Append to `mcp_server/src/rook/director_compiler.py` (add `from . import director_motion` to the imports at top):

```python
async def resolve_source_states(call_native, object_ids, port):
    result = await call_native("/director/object-states", "POST", {"object_ids": list(object_ids)}, port=port)
    if not result.get("success"):
        raise DirectorCompileError(
            "source_resolution_failed", f"object state resolution failed: {result.get('data')}")
    objects = (result.get("data") or {}).get("objects") or []
    by_id = {obj.get("object_id"): obj for obj in objects}
    states = {}
    for oid in object_ids:
        obj = by_id.get(oid)
        if obj is None:
            raise DirectorCompileError(
                "source_resolution_failed", f"object not resolved: {oid}", object_id=oid)
        states[oid] = {
            "bbox_min": obj["bbox_min"],
            "bbox_max": obj["bbox_max"],
            "state_hash": obj.get("state_hash"),
        }
    return states


def _bbox_center(bbox_min, bbox_max):
    return [(float(bbox_min[i]) + float(bbox_max[i])) / 2.0 for i in range(3)]


def build_object_frames(expanded, source_states, frame_count, default_easing):
    object_ids = sorted(expanded)
    # per-object per-frame matrices
    per_object = {}
    for oid in object_ids:
        st = source_states[oid]
        center = _bbox_center(st["bbox_min"], st["bbox_max"])
        try:
            per_object[oid] = director_motion.compile_object_track(
                expanded[oid], frame_count=frame_count, source_center=center, default_easing=default_easing)
        except director_motion.MotionError as exc:
            raise DirectorCompileError(exc.code, str(exc), object_id=oid) from exc

    frames = []
    for i in range(frame_count):
        transforms = []
        for oid in object_ids:
            st = source_states[oid]
            transforms.append({
                "object_id": oid,
                "source_state": {
                    "bbox_min": st["bbox_min"],
                    "bbox_max": st["bbox_max"],
                    "validation_strength": "bbox_only",
                    "state_hash": st["state_hash"],
                },
                "transform": per_object[oid][i],
            })
        frames.append({"frame_index": i + 1, "object_transforms": transforms})
    return frames
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_director_compiler.py -v`
Expected: PASS (Task 3 + Task 4 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_compiler.py mcp_server/tests/test_director_compiler.py
git commit -m "feat(director): source-state resolution + object_frames (PR4 Task 4)"
```

---

### Task 5: camera_frames + `compile_motion` assembly (`director_compiler.py`)

**Files:**
- Modify: `mcp_server/src/rook/director_compiler.py`
- Test: `mcp_server/tests/test_director_compiler.py`

**Interfaces:**
- Consumes: all Task 3/4 helpers; `camera_planner.validate_camera_request`, `camera_planner.resolve_camera_plan`, `camera_planner.CameraPlanError`; `timeline.normalize_director_request`, `timeline.TimelineError`.
- Produces:
  - `async build_camera_frames(spec, frame_count, resolution, duration_seconds, fps, call_native, port) -> list[dict]` — `[{"frame_index", "camera"}]`; default = single `active_view` keyframe (static hold).
  - `async compile_motion(arguments, *, call_native=call_rhino, port=None) -> dict` = `{"track", "provenance"}`.

- [ ] **Step 1: Write the failing test**

```python
# append to mcp_server/tests/test_director_compiler.py

class FullFakeNative(FakeNative):
    def __init__(self, objects, *, view_ok=True, **kw):
        super().__init__(objects, **kw)
        self.view_ok = view_ok

    async def __call__(self, endpoint, method="POST", data=None, port=None):
        self.calls.append((endpoint, data))
        if endpoint == "/director/object-states":
            if not self.object_states_ok:
                return {"success": False, "data": {"code": "x", "message": "boom"}}
            return {"success": True, "data": {"objects": self.objects, "units": "Inches"}}
        if endpoint == "/director/view-state":
            if not self.view_ok:
                return {"success": False, "data": {"code": "x", "message": "no view"}}
            return {"success": True, "data": {"camera": {
                "projection": "perspective", "location": [4, -4, 3], "target": [0, 0, 0],
                "up": [0, 0, 1], "lens_length": 35.0, "fov_degrees": None,
                "parallel_scale": None, "near_clip": None, "far_clip": None, "aspect": 1.7778},
                "provenance": {"source": "active_view"}}}
        raise AssertionError(f"unexpected endpoint {endpoint}")


def _spec(**over):
    spec = {
        "timeline": {"fps": 24, "frame_count": 3},
        "resolution": {"width": 1920, "height": 1080},
        "motion": [{"target": U1, "keyframes": [{"t": 1.0, "translate": [4, 0, 0]}]}],
    }
    spec.update(over)
    return spec


def test_compile_motion_default_camera_hold_produces_valid_track():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    out = asyncio.run(dc.compile_motion(_spec(), call_native=fake, port=None))
    track = out["track"]
    assert track["transform_semantics"] == "absolute_from_source"
    assert track["fps"] == 24
    assert track["frame_count"] == 3
    assert track["animated_object_ids"] == [U1]
    assert len(track["camera_frames"]) == 3
    assert len(track["object_frames"]) == 3
    assert track["camera_frames"][0]["frame_index"] == 1
    # provenance
    assert out["provenance"]["frame_count"] == 3
    assert out["provenance"]["group_expansion"] == {}


def test_compile_motion_track_passes_structural_native_rules():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2]),
                           _objstate(U2, [0, 0, 0], [2, 2, 2])])
    spec = _spec(groups={"g": [U1, U2]},
                 motion=[{"target": "g", "keyframes": [{"t": 1.0, "translate": [4, 0, 0]}]}])
    track = asyncio.run(dc.compile_motion(spec, call_native=fake, port=None))["track"]
    fc = track["frame_count"]
    assert len(track["camera_frames"]) == fc and len(track["object_frames"]) == fc
    aset = set(track["animated_object_ids"])
    assert len(aset) == len(track["animated_object_ids"]) <= 256
    for i, of in enumerate(track["object_frames"]):
        assert of["frame_index"] == i + 1
        ids = [ot["object_id"] for ot in of["object_transforms"]]
        assert set(ids) == aset and len(ids) == len(aset)
        for ot in of["object_transforms"]:
            m = ot["transform"]
            assert len(m) == 4 and all(len(r) == 4 for r in m)
    for i, cf in enumerate(track["camera_frames"]):
        assert cf["frame_index"] == i + 1


def test_compile_motion_camera_resolution_failure():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])], view_ok=False)
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.compile_motion(_spec(), call_native=fake, port=None))
    assert ei.value.code == "camera_resolution_failed"


def test_compile_motion_invalid_camera_spec():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    # a keyframes camera with an unsupported source kind -> invalid_camera
    bad = _spec(camera={"strategy": "keyframes",
                        "keyframes": [{"frame_index": 1, "source": {"kind": "bogus"}}]})
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.compile_motion(bad, call_native=fake, port=None))
    assert ei.value.code == "invalid_camera"


def test_compile_motion_source_failure_distinct_from_camera():
    fake = FullFakeNative([_objstate(U1, [0, 0, 0], [2, 2, 2])])
    spec = _spec(motion=[{"target": U2, "keyframes": [{"t": 1.0, "translate": [1, 0, 0]}]}])
    with pytest.raises(dc.DirectorCompileError) as ei:
        asyncio.run(dc.compile_motion(spec, call_native=fake, port=None))
    assert ei.value.code == "source_resolution_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_compiler.py -k compile_motion -v`
Expected: FAIL — `AttributeError: ... has no attribute 'compile_motion'`.

- [ ] **Step 3: Write minimal implementation**

Append to `mcp_server/src/rook/director_compiler.py`:

```python
_DEFAULT_RESOLUTION = {"width": 1920, "height": 1080}
_DEFAULT_CAMERA = {"strategy": "keyframes",
                   "keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]}


async def build_camera_frames(spec, frame_count, resolution, duration_seconds, fps, call_native, port):
    cam_spec = spec.get("camera")
    if not isinstance(cam_spec, dict):
        cam_spec = _DEFAULT_CAMERA
    request = {"timeline": {"fps": fps, "duration_seconds": duration_seconds}, "camera": cam_spec}
    try:
        normalized, _ = timeline.normalize_director_request(request)
    except timeline.TimelineError as exc:
        raise DirectorCompileError("invalid_camera", str(exc)) from exc
    try:
        camera_planner.validate_camera_request(normalized, frame_count=frame_count, resolution=resolution)
    except camera_planner.CameraPlanError as exc:
        raise DirectorCompileError("invalid_camera", str(exc)) from exc
    try:
        plan = await camera_planner.resolve_camera_plan(
            normalized, frame_count=frame_count, resolution=resolution, call_native=call_native, port=port)
    except camera_planner.CameraPlanError as exc:
        raise DirectorCompileError("camera_resolution_failed", str(exc)) from exc
    cam_frames = plan["frames"]
    return [{"frame_index": i + 1, "camera": cam_frames[i]} for i in range(frame_count)]


def _resolution(spec):
    res = spec.get("resolution") or _DEFAULT_RESOLUTION
    return res


async def compile_motion(arguments: dict, *, call_native=call_rhino, port: int | None = None) -> dict:
    if not isinstance(arguments, dict):
        raise DirectorCompileError("invalid_input", "compile request must be an object")
    default_easing = arguments.get("default_easing", "linear")

    tl = resolve_compiler_timeline(arguments)
    fps, frame_count, duration_seconds = tl["fps"], tl["frame_count"], tl["duration_seconds"]

    expanded = expand_targets(arguments)
    object_ids = sorted(expanded)
    validate_caps(object_count=len(object_ids), frame_count=frame_count, fps=fps)

    source_states = await resolve_source_states(call_native, object_ids, port)
    object_frames = build_object_frames(expanded, source_states, frame_count, default_easing)
    resolution = _resolution(arguments)
    camera_frames = await build_camera_frames(
        arguments, frame_count, resolution, duration_seconds, fps, call_native, port)

    track = {
        "transform_semantics": "absolute_from_source",
        "fps": fps,
        "frame_count": frame_count,
        "animated_object_ids": object_ids,
        "camera_frames": camera_frames,
        "object_frames": object_frames,
    }
    groups = arguments.get("groups") or {}
    referenced_groups = {}
    for entry in arguments["motion"]:
        tgt = entry.get("target")
        if isinstance(tgt, str) and tgt in groups:
            referenced_groups[tgt] = list(groups[tgt])
    provenance = {
        "frame_count": frame_count,
        "fps": fps,
        "duration_ms": frame_count * (1000.0 / fps),
        "animated_object_ids": object_ids,
        "group_expansion": referenced_groups,
        "segment_mapping": {
            oid: [{"t": float(kf["t"]), "ease_from_previous": kf.get("ease_from_previous", default_easing)}
                  for kf in expanded[oid]]
            for oid in object_ids
        },
        "warnings": [],
    }
    return {"track": track, "provenance": provenance}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_director_compiler.py tests/test_director_motion.py -v`
Expected: PASS (all compiler + motion tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/director_compiler.py mcp_server/tests/test_director_compiler.py
git commit -m "feat(director): camera_frames + compile_motion assembly (PR4 Task 5)"
```

---

### Task 6: MCP tool `rhino_director_compile_motion` (`server.py`)

**Files:**
- Modify: `mcp_server/src/rook/server.py` (add a `Tool(...)` near the `rhino_director_replay` Tool at ~3969; add a `case` near the `rhino_director_replay` case at ~20186; ensure `director_compiler` is imported)
- Test: `mcp_server/tests/test_director_mcp_tools.py`

**Interfaces:**
- Consumes: `director_compiler.compile_motion`, `director_compiler.DirectorCompileError` (Task 5).
- Produces: MCP tool `rhino_director_compile_motion` returning `{success, data}`; on `DirectorCompileError`, `data = exc.to_data()`.

- [ ] **Step 1: Write the failing test**

```python
# append to mcp_server/tests/test_director_mcp_tools.py

@pytest.mark.asyncio
async def test_compile_motion_tool_registered():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_compile_motion" in by_name
    schema = by_name["rhino_director_compile_motion"].inputSchema
    assert schema["type"] == "object"
    assert _find_rejected_schema_keywords(schema) == []
    assert "motion" in schema["properties"]
    assert "timeline" in schema["properties"]


@pytest.mark.asyncio
async def test_compile_motion_tool_dispatch_success():
    spec = {
        "timeline": {"fps": 24, "frame_count": 2},
        "motion": [{"target": "11111111-1111-1111-1111-111111111111",
                    "keyframes": [{"t": 1.0, "translate": [4, 0, 0]}]}],
    }

    async def fake_compile(arguments, *, port=None):
        assert arguments["timeline"]["fps"] == 24
        return {"track": {"frame_count": 2}, "provenance": {"frame_count": 2}}

    with patch("rook.server.director_compiler.compile_motion", new=fake_compile):
        out = await server.call_tool("rhino_director_compile_motion", spec)
    # IMPORTANT (see server._format_tool_result): success text IS the data, NOT a
    # {success, data} envelope. Parse the text directly as data.
    data = json.loads(out[0].text)
    assert data["track"]["frame_count"] == 2


@pytest.mark.asyncio
async def test_compile_motion_tool_dispatch_error_surfaces_code():
    async def boom(arguments, *, port=None):
        from rook import director_compiler
        raise director_compiler.DirectorCompileError("unknown_group", "nope", object_id="x")

    with patch("rook.server.director_compiler.compile_motion", new=boom):
        out = await server.call_tool("rhino_director_compile_motion", {"motion": []})
    # Failure text is "Error: " + json.dumps(data); strip the prefix then parse.
    text = out[0].text
    assert text.startswith("Error: ")
    payload = json.loads(text[len("Error: "):])
    assert payload["code"] == "unknown_group"
    assert payload["object_id"] == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_director_mcp_tools.py -k compile_motion -v`
Expected: FAIL — tool not registered.

- [ ] **Step 3: Write minimal implementation**

3a. Ensure the import exists at the top of `server.py` (search for `from rook import ... director` / `import director`; if `director_compiler` is not imported, add it next to the `director` import):

```python
from rook import director_compiler
```

3b. Add the Tool definition immediately after the `rhino_director_replay_cancel` Tool block (after ~line 3987, before the next `Tool(`):

```python
        Tool(
            name="rhino_director_compile_motion",
            description=(
                "RookVisionDirector: compile a high-level object-motion authoring spec "
                "(groups, normalized-t keyframes with relative TRS deltas + easing, timeline, "
                "optional camera) into a baked replay track. Compile-only: returns {track, "
                "provenance}; does not replay or mutate the document. Pass the returned track "
                "to rhino_director_replay."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "timeline": {"type": "object", "description": "fps (positive int) plus exactly one of duration_seconds or frame_count."},
                    "motion": {"type": "array", "items": {"type": "object"}, "description": "Per-target keyframe tracks; each {target, keyframes[]}."},
                    "groups": {"type": "object", "description": "Optional map of local group name -> [object UUIDs]. Names must not be UUID-shaped."},
                    "camera": {"type": "object", "description": "Optional camera_planner spec (keyframes|curve_follow_target). Omitted = hold active view."},
                    "resolution": {"type": "object", "description": "Optional {width,height}; defaults 1920x1080 (camera aspect only)."},
                    "default_easing": {"type": "string", "description": "Track-level default easing: linear|ease_in|ease_out|ease_in_out (default linear)."},
                },
                "required": ["timeline", "motion"],
            },
        ),
```

3c. Add the dispatch case immediately after the `rhino_director_replay_cancel` case (after ~line 20196):

```python
        case "rhino_director_compile_motion":
            try:
                result = {"success": True, "data": await director_compiler.compile_motion(arguments, port=port)}
            except director_compiler.DirectorCompileError as exc:
                result = {"success": False, "data": exc.to_data()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp_server && python -m pytest tests/test_director_mcp_tools.py -k compile_motion -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full new-module test set + commit**

Run: `cd mcp_server && python -m pytest tests/test_director_motion.py tests/test_director_compiler.py tests/test_director_mcp_tools.py -v`
Expected: PASS.

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_director_mcp_tools.py
git commit -m "feat(director): rhino_director_compile_motion MCP tool (PR4 Task 6)"
```

---

### Task 7: Live smoke gate (manual; Rhino up)

**Files:**
- None (manual verification + a short note appended to the spec's test-plan section if anything is learned).

This task is a manual gate, not an automated pytest, because it requires live Rhino and the native `/director/*` routes. It proves the emitted track actually replays. There is **no native change in this PR**, so this is a smoke, not the PR2 6/6 native gate.

**Preconditions (ask the user, do not self-launch Rhino):**
- Confirm Rhino is open with a **throwaway** document (never run against a real model).
- Confirm `python -m rook` MCP is connected (`/mcp` shows `rook`; `rhino_ping` → `pong`).

- [ ] **Step 1: Create two throwaway boxes and capture their object ids**

Use `rhino_create` twice (two boxes a few units apart) and record the returned object UUIDs as `<ID_A>` and `<ID_B>`.

- [ ] **Step 2: Compile a real motion spec**

Call `rhino_director_compile_motion` with:

```json
{
  "timeline": {"fps": 24, "frame_count": 24},
  "groups": {"pair": ["<ID_A>", "<ID_B>"]},
  "motion": [
    {"target": "pair", "keyframes": [
      {"t": 1.0, "translate": [0, 0, 20], "ease_from_previous": "ease_in_out"}
    ]},
    {"target": "<ID_A>", "keyframes": [
      {"t": 1.0, "rotate": {"axis": [0, 0, 1], "angle_degrees": 90}}
    ]}
  ]
}
```

Expected: `success: true`; `data.track` with `frame_count == 24`, `animated_object_ids` = the two ids, `camera_frames`/`object_frames` length 24. (Note: `<ID_A>` appears in both the group and a bare-id track → this should fail `duplicate_object_target`; use it to confirm the duplicate rule, then move the rotate into the group keyframes or a separate id to get a clean compile.)

- [ ] **Step 3: Replay the compiled track**

Call `rhino_director_replay` with `{"track": <data.track from step 2>}`.
Expected: `success: true`, `data.status == "completed"`, `data.restored == true`; the boxes visibly lift (and rotate) in the viewport and return to source.

- [ ] **Step 4: Record the result**

Note the outcome (pass/fail + any error code) in the PR description. If a defect surfaces that is adjacent to but outside PR4's scope, open a separate issue rather than widening this PR.

- [ ] **Step 5: Commit (only if a doc note was added)**

```bash
git add docs/superpowers/specs/2026-06-24-rookvisiondirector-animation-compiler-design.md
git commit -m "docs(director): record PR4 live smoke result (PR4 Task 7)"
```

---

## Final verification (before opening the PR)

- [ ] Run the full new test set: `cd mcp_server && python -m pytest tests/test_director_motion.py tests/test_director_compiler.py tests/test_director_mcp_tools.py -v` → all green.
- [ ] Run the broader director suite to confirm no regressions: `cd mcp_server && python -m pytest tests/ -k director -v`.
- [ ] Confirm `git diff origin/main --stat` shows only: `director_motion.py`, `director_compiler.py`, `server.py` (two small additions), the two new test files, and the spec/plan docs. **No** native (`src/RookNative`), C# (`src/Rook`), or `director.py` production changes.
