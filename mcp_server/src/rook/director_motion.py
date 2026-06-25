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


def _strict_number(value, field):
    """Coerce a user-supplied scalar to float. Rejects bool (bool is an int subclass)
    and any non-(int|float) type, and rejects non-finite values, raising MotionError
    so director_compiler maps it to DirectorCompileError('invalid_keyframe')."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MotionError("invalid_keyframe", f"{field} must be a finite number")
    out = float(value)
    if not math.isfinite(out):
        raise MotionError("invalid_keyframe", f"{field} must be a finite number")
    return out


def _parse_scale(value):
    if value is None:
        return [1.0, 1.0, 1.0]
    if isinstance(value, (list, tuple)):
        if len(value) != 3:
            raise MotionError("invalid_keyframe", "scale vector must have 3 components")
        comps = [_strict_number(c, "scale component") for c in value]
    else:
        comps = [_strict_number(value, "scale")] * 3
    for c in comps:
        if c <= 0.0:
            raise MotionError("invalid_keyframe", "scale components must be > 0")
    return comps


def _parse_translate(value):
    if value is None:
        return [0.0, 0.0, 0.0]
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise MotionError("invalid_keyframe", "translate must be a 3-number array")
    return [_strict_number(c, "translate component") for c in value]


def _resolve_pivot(rotate, source_center):
    pivot = rotate.get("pivot", "object_center")
    if pivot == "object_center":
        return [float(c) for c in source_center]
    if isinstance(pivot, (list, tuple)) and len(pivot) == 3:
        return [_strict_number(c, "pivot component") for c in pivot]
    raise MotionError("invalid_keyframe", "pivot must be 'object_center' or a 3-number array")


def _parse_key(kf, source_center, default_easing):
    if not isinstance(kf, dict) or "t" not in kf:
        raise MotionError("invalid_keyframe", "keyframe must be an object with a 't'")
    t = _strict_number(kf["t"], "keyframe t")
    if t < 0.0 or t > 1.0:
        raise MotionError("invalid_keyframe", "keyframe t must be in 0..1")
    translate = _parse_translate(kf.get("translate"))
    scale = _parse_scale(kf.get("scale"))
    quat = _QUAT_IDENTITY
    pivot = None
    rotate = kf.get("rotate")
    if rotate is not None:
        if not isinstance(rotate, dict) or "axis" not in rotate or "angle_degrees" not in rotate:
            raise MotionError("invalid_keyframe", "rotate requires axis and angle_degrees")
        axis = rotate["axis"]
        if not isinstance(axis, (list, tuple)) or len(axis) != 3:
            raise MotionError("invalid_keyframe", "rotate.axis must be a 3-number array")
        axis = [_strict_number(c, "rotate.axis component") for c in axis]
        angle = _strict_number(rotate["angle_degrees"], "rotate.angle_degrees")
        if abs(angle) > 180.0:
            raise MotionError("invalid_keyframe", "rotate angle_degrees must satisfy |angle| <= 180")
        quat = _quat_from_axis_angle(axis, angle)
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
