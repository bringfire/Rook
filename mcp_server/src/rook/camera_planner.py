from __future__ import annotations

import math
import uuid
from typing import Any


class CameraPlanError(ValueError):
    pass


CAMERA_SOURCE_KINDS = {"active_view", "named_view", "explicit_camera", "camera"}


def _normalize(vector: list[float]) -> list[float] | None:
    length = math.sqrt(sum(float(v) * float(v) for v in vector))
    if length < 1e-9:
        return None
    return [float(v) / length for v in vector]


def _lerp(a: float, b: float, t: float) -> float:
    return float(a) + (float(b) - float(a)) * t


def _lerp_vec(a: list[float], b: list[float], t: float) -> list[float]:
    return [_lerp(a[i], b[i], t) for i in range(3)]


def _aspect_from_resolution(resolution: dict[str, int]) -> float:
    width = int(resolution.get("width", 0))
    height = int(resolution.get("height", 0))
    if width <= 0 or height <= 0:
        raise CameraPlanError("resolution width and height must be positive")
    return width / height


def normalize_camera_request(request: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(request.get("camera"), dict):
        camera_request = dict(request["camera"])
        strategy = camera_request.get("strategy")
        if strategy == "keyframes":
            if (
                not isinstance(camera_request.get("keyframes"), list)
                or not camera_request["keyframes"]
            ):
                raise CameraPlanError("camera.keyframes must be a non-empty array")
            return camera_request, "camera_strategy"
        if strategy == "curve_follow_target":
            return camera_request, "camera_strategy"
        raise CameraPlanError(
            "camera.strategy must be keyframes or curve_follow_target for this slice"
        )

    if "camera_keyframes" in request:
        keyframes = request.get("camera_keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            raise CameraPlanError("camera_keyframes must contain at least one keyframe")
        return {"strategy": "keyframes", "keyframes": keyframes}, "legacy_camera_keyframes"

    raise CameraPlanError("camera.keyframes or camera_keyframes is required")


def _validate_keyframe_source(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict) or not source.get("kind"):
        raise CameraPlanError("camera keyframe source.kind is required")
    source_kind = source["kind"]
    if source_kind not in CAMERA_SOURCE_KINDS:
        raise CameraPlanError(
            "camera keyframe source.kind must be active_view, named_view, or explicit_camera"
        )
    if source_kind == "named_view" and not source.get("name"):
        raise CameraPlanError("named_view camera keyframes require source.name")
    if source_kind in {"explicit_camera", "camera"}:
        _validate_resolved_camera(source.get("camera"), aspect=1.0)
    return dict(source)


def _validated_keyframes(
    camera_request: dict[str, Any], frame_count: int
) -> list[dict[str, Any]]:
    keyframes = camera_request.get("keyframes")
    if not isinstance(keyframes, list) or not keyframes:
        raise CameraPlanError("camera keyframes must contain at least one keyframe")

    validated = []
    for keyframe in keyframes:
        if not isinstance(keyframe, dict):
            raise CameraPlanError("camera keyframe entries must be objects")
        try:
            frame_index = int(keyframe.get("frame_index"))
        except (TypeError, ValueError) as ex:
            raise CameraPlanError("camera keyframe frame_index must be an integer") from ex
        if frame_index < 1 or frame_index > frame_count:
            raise CameraPlanError("camera keyframe frame_index must be inside 1..frame_count")
        validated.append(
            {
                "frame_index": frame_index,
                "source": _validate_keyframe_source(keyframe.get("source")),
            }
        )
    return sorted(validated, key=lambda item: item["frame_index"])


def validate_camera_request(
    request: dict[str, Any],
    *,
    frame_count: int,
    resolution: dict[str, int],
) -> dict[str, Any]:
    aspect = _aspect_from_resolution(resolution)
    camera_request, request_shape = normalize_camera_request(request)
    if camera_request.get("strategy") == "curve_follow_target":
        validated_curve = _validate_curve_follow_request(camera_request, aspect=aspect)
        validated_curve["request_shape"] = request_shape
        return validated_curve
    keyframes = _validated_keyframes(camera_request, frame_count)
    return {
        "strategy": "keyframes",
        "request_shape": request_shape,
        "keyframes": keyframes,
    }


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _strict_float(value: Any) -> float | None:
    if isinstance(value, bool) or type(value) not in (int, float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _finite_positive(value: Any) -> float | None:
    result = _coerce_float(value)
    if result is None or result <= 0:
        return None
    return result


def _valid_fov(value: Any) -> float | None:
    result = _coerce_float(value)
    if result is None or result <= 0 or result >= 180:
        return None
    return result


def _optional_lens_length(camera: dict[str, Any]) -> float | None:
    if "lens_length" not in camera or camera["lens_length"] is None:
        return None
    result = _finite_positive(camera["lens_length"])
    if result is None:
        raise CameraPlanError("camera.lens_length must be positive")
    return result


def _optional_fov_degrees(camera: dict[str, Any]) -> float | None:
    if "fov_degrees" not in camera or camera["fov_degrees"] is None:
        return None
    result = _valid_fov(camera["fov_degrees"])
    if result is None:
        raise CameraPlanError("camera.fov_degrees must be between 0 and 180")
    return result


def _point3(camera: dict[str, Any], field: str) -> list[float]:
    value = camera.get(field)
    if not isinstance(value, list) or len(value) != 3:
        raise CameraPlanError(f"camera.{field} must be a 3-number array")
    result = [_coerce_float(v) for v in value]
    if any(v is None for v in result):
        raise CameraPlanError(f"camera.{field} must be a 3-number array")
    return [float(v) for v in result]


def _strict_point3(value: Any, message: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise CameraPlanError(message)
    result = [_strict_float(v) for v in value]
    if any(v is None for v in result):
        raise CameraPlanError(message)
    return [float(v) for v in result]


def _validated_uuid_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CameraPlanError(f"camera.{field} must be a Rhino curve object UUID string")
    try:
        uuid.UUID(value.strip())
    except ValueError as ex:
        raise CameraPlanError(
            f"camera.{field} must be a Rhino curve object UUID string"
        ) from ex
    return value.strip()


def _validated_sampling(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CameraPlanError("camera.sampling is required")
    if value.get("mode") != "normalized_parameter":
        raise CameraPlanError("camera.sampling.mode must be normalized_parameter")
    start = _strict_float(value.get("start"))
    end = _strict_float(value.get("end"))
    if start is None or end is None:
        raise CameraPlanError("camera.sampling start and end must be finite numbers")
    if start < 0.0 or start > 1.0 or end < 0.0 or end > 1.0:
        raise CameraPlanError("camera.sampling start and end must be in 0..1")
    if end < start:
        raise CameraPlanError(
            "camera.sampling end must be greater than or equal to start"
        )
    return {"mode": "normalized_parameter", "start": start, "end": end}


def _validate_curve_follow_request(
    camera_request: dict[str, Any], *, aspect: float
) -> dict[str, Any]:
    curve_id = _validated_uuid_string(camera_request.get("curve_id"), "curve_id")
    target = _strict_point3(
        camera_request.get("target"),
        "camera.target must be a finite 3-number array",
    )
    up = _normalize(
        _strict_point3(
            camera_request.get("up"),
            "camera.up must be a finite 3-number array",
        )
    )
    if up is None:
        raise CameraPlanError("camera up vector became degenerate")
    sampling = _validated_sampling(camera_request.get("sampling"))
    lens_length = _optional_lens_length(camera_request)
    fov_degrees = _optional_fov_degrees(camera_request)
    if lens_length is None and fov_degrees is None:
        raise CameraPlanError("perspective camera requires lens_length or fov_degrees")
    return {
        "strategy": "curve_follow_target",
        "curve_id": curve_id,
        "target": target,
        "up": up,
        "sampling": sampling,
        "lens_length": lens_length,
        "fov_degrees": fov_degrees,
        "aspect": aspect,
        "optics_authority": "lens_length"
        if lens_length is not None
        else "fov_degrees",
    }


def _validate_resolved_camera(camera: Any, *, aspect: float) -> dict[str, Any]:
    if not isinstance(camera, dict):
        raise CameraPlanError("explicit_camera source requires camera object")

    projection = str(camera.get("projection", "")).lower()
    if projection == "parallel":
        raise CameraPlanError("parallel cameras are not supported by RookVisionDirector")
    if projection != "perspective":
        raise CameraPlanError(f"camera projection is unsupported: {projection}")

    location = _point3(camera, "location")
    target = _point3(camera, "target")
    up = _normalize(_point3(camera, "up"))
    if up is None:
        raise CameraPlanError("camera up vector became degenerate")

    direction = _normalize([target[i] - location[i] for i in range(3)])
    if direction is None:
        raise CameraPlanError("camera location and target must differ")

    lens_value = _optional_lens_length(camera)
    fov_value = _optional_fov_degrees(camera)
    if camera.get("lens_length") is None and camera.get("fov_degrees") is None:
        raise CameraPlanError("perspective camera requires lens_length or fov_degrees")

    near_clip = _finite_positive(camera.get("near_clip"))
    far_clip = _finite_positive(camera.get("far_clip"))
    if (camera.get("near_clip") is None) != (camera.get("far_clip") is None):
        raise CameraPlanError("camera near_clip and far_clip must be provided together")
    if camera.get("near_clip") is not None and near_clip is None:
        raise CameraPlanError("camera.near_clip must be positive")
    if camera.get("far_clip") is not None and far_clip is None:
        raise CameraPlanError("camera.far_clip must be positive")
    if near_clip is not None and far_clip is not None and near_clip >= far_clip:
        raise CameraPlanError("camera.near_clip must be less than camera.far_clip")

    normalized = dict(camera)
    normalized["projection"] = "perspective"
    normalized["location"] = location
    normalized["target"] = target
    normalized["up"] = up
    normalized["lens_length"] = lens_value
    normalized["fov_degrees"] = fov_value
    normalized["aspect"] = aspect
    if "near_clip" in camera:
        normalized["near_clip"] = near_clip
    if "far_clip" in camera:
        normalized["far_clip"] = far_clip
    return normalized


def _interpolate_camera(
    a: dict[str, Any], b: dict[str, Any], t: float, *, aspect: float
) -> dict[str, Any]:
    if a["projection"] != b["projection"]:
        raise CameraPlanError("camera projection cannot change during interpolation")

    camera = dict(a)
    camera["location"] = _lerp_vec(a["location"], b["location"], t)
    camera["target"] = _lerp_vec(a["target"], b["target"], t)
    up = _normalize(_lerp_vec(a["up"], b["up"], t))
    if up is None:
        raise CameraPlanError("camera up vector became degenerate during interpolation")
    camera["up"] = up

    if a.get("lens_length") is not None and b.get("lens_length") is not None:
        camera["lens_length"] = _lerp(float(a["lens_length"]), float(b["lens_length"]), t)
        camera["fov_degrees"] = None
    elif a.get("fov_degrees") is not None and b.get("fov_degrees") is not None:
        camera["lens_length"] = None
        camera["fov_degrees"] = _lerp(float(a["fov_degrees"]), float(b["fov_degrees"]), t)
    else:
        raise CameraPlanError("camera optics authority cannot change during interpolation")

    for field in ("parallel_scale", "near_clip", "far_clip"):
        av = a.get(field)
        bv = b.get(field)
        if av is None or bv is None:
            camera[field] = av if t < 0.5 else bv
        else:
            camera[field] = _lerp(float(av), float(bv), t)
    camera["aspect"] = aspect
    return _validate_resolved_camera(camera, aspect=aspect)


async def _resolve_keyframes(
    keyframes: list[dict[str, Any]],
    *,
    aspect: float,
    call_native,
    port: int | None,
) -> list[dict[str, Any]]:
    resolved = []
    for keyframe in keyframes:
        source = keyframe["source"]
        if source.get("kind") in {"explicit_camera", "camera"}:
            camera = _validate_resolved_camera(source.get("camera"), aspect=aspect)
            resolved.append(
                {
                    "frame_index": keyframe["frame_index"],
                    "source": {"kind": "explicit_camera", "camera": dict(camera)},
                    "camera": camera,
                    "provenance": {"source": "explicit_camera"},
                }
            )
            continue
        result = await call_native(
            "/director/view-state", "POST", {"source": source}, port=port
        )
        if not result.get("success"):
            raise CameraPlanError(f"camera resolution failed: {result.get('data')}")
        data = result["data"]
        resolved.append(
            {
                "frame_index": keyframe["frame_index"],
                "source": keyframe["source"],
                "camera": _validate_resolved_camera(data["camera"], aspect=aspect),
                "provenance": data.get("provenance"),
            }
        )
    return resolved


def interpolate_camera_frames(
    resolved_keyframes: list[dict[str, Any]],
    frame_count: int,
    *,
    aspect: float,
) -> list[dict[str, Any]]:
    keyframes = sorted(resolved_keyframes, key=lambda item: item["frame_index"])
    if len(keyframes) == 1:
        return [dict(keyframes[0]["camera"]) for _ in range(frame_count)]

    cameras = []
    for frame_index in range(1, frame_count + 1):
        previous = keyframes[0]
        next_key = keyframes[-1]
        for candidate in keyframes:
            if candidate["frame_index"] <= frame_index:
                previous = candidate
            if candidate["frame_index"] >= frame_index:
                next_key = candidate
                break
        if previous["frame_index"] == next_key["frame_index"]:
            cameras.append(dict(previous["camera"]))
            continue
        span = next_key["frame_index"] - previous["frame_index"]
        t = (frame_index - previous["frame_index"]) / span
        cameras.append(
            _interpolate_camera(previous["camera"], next_key["camera"], t, aspect=aspect)
        )
    return cameras


def _native_error_message(data: Any) -> str:
    if isinstance(data, dict):
        nested = data.get("error")
        if isinstance(nested, dict):
            return str(nested.get("code") or nested.get("message") or nested)
        return str(data.get("code") or data.get("message") or data)
    if data is None:
        return "curve sample resolution failed"
    return str(data)


def _sample_point(sample: dict[str, Any]) -> list[float]:
    return _strict_point3(
        sample.get("point"),
        "curve sample point must be a finite 3-number array",
    )


def _indexed_curve_samples(
    samples: Any, *, frame_count: int
) -> dict[int, dict[str, Any]]:
    if not isinstance(samples, list):
        raise CameraPlanError("curve sample response samples must be an array")
    indexed: dict[int, dict[str, Any]] = {}
    for sample in samples:
        if not isinstance(sample, dict):
            raise CameraPlanError("curve sample entries must be objects")
        frame_index = sample.get("frame_index")
        if isinstance(frame_index, bool) or type(frame_index) is not int:
            raise CameraPlanError("curve sample frame_index must be an integer")
        if frame_index < 1 or frame_index > frame_count:
            raise CameraPlanError(
                "curve sample frame_index must be inside 1..frame_count"
            )
        if frame_index in indexed:
            raise CameraPlanError("curve sample response contains duplicate frame_index")
        _sample_point(sample)
        indexed[frame_index] = sample
    missing = [index for index in range(1, frame_count + 1) if index not in indexed]
    if missing:
        raise CameraPlanError(
            f"curve sample response is missing frame_index {missing[0]}"
        )
    return indexed


def _reject_curve_follow_parallel_up(camera: dict[str, Any]) -> None:
    direction = _normalize(
        [camera["target"][i] - camera["location"][i] for i in range(3)]
    )
    if direction is None:
        raise CameraPlanError("camera location and target must differ")
    dot = abs(sum(direction[i] * camera["up"][i] for i in range(3)))
    if dot >= 0.999:
        raise CameraPlanError(
            "curve_follow_target up vector is parallel to the view direction"
        )


async def _resolve_curve_follow_target(
    camera_request: dict[str, Any],
    *,
    frame_count: int,
    aspect: float,
    call_native,
    port: int | None,
) -> dict[str, Any]:
    validated = _validate_curve_follow_request(camera_request, aspect=aspect)
    native_request = {
        "curve_id": validated["curve_id"],
        "frame_count": frame_count,
        "sampling": validated["sampling"],
    }
    result = await call_native(
        "/director/curve-samples", "POST", native_request, port=port
    )
    if not result.get("success"):
        raise CameraPlanError(
            f"curve sample resolution failed: {_native_error_message(result.get('data'))}"
        )
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    samples = _indexed_curve_samples(data.get("samples"), frame_count=frame_count)

    frames = []
    for frame_index in range(1, frame_count + 1):
        sample = samples[frame_index]
        camera = {
            "projection": "perspective",
            "location": _sample_point(sample),
            "target": validated["target"],
            "up": validated["up"],
            "lens_length": validated["lens_length"],
            "fov_degrees": validated["fov_degrees"],
            "aspect": aspect,
        }
        _reject_curve_follow_parallel_up(camera)
        frames.append(_validate_resolved_camera(camera, aspect=aspect))

    return {
        "strategy": "curve_follow_target",
        "frames": frames,
        "provenance": {
            "request_shape": "camera_strategy",
            "curve_id": validated["curve_id"],
            "target": validated["target"],
            "up": validated["up"],
            "sampling": validated["sampling"],
            "curve_sampling": data.get("provenance", {}),
            "aspect_authority": "output_resolution",
            "optics_authority": validated["optics_authority"],
        },
    }


async def resolve_camera_plan(
    request: dict[str, Any],
    *,
    frame_count: int,
    resolution: dict[str, int],
    call_native,
    port: int | None,
) -> dict[str, Any]:
    aspect = _aspect_from_resolution(resolution)
    validated = validate_camera_request(
        request,
        frame_count=frame_count,
        resolution=resolution,
    )
    if validated["strategy"] == "curve_follow_target":
        return await _resolve_curve_follow_target(
            request["camera"],
            frame_count=frame_count,
            aspect=aspect,
            call_native=call_native,
            port=port,
        )
    resolved_keyframes = await _resolve_keyframes(
        validated["keyframes"],
        aspect=aspect,
        call_native=call_native,
        port=port,
    )
    frames = interpolate_camera_frames(resolved_keyframes, frame_count, aspect=aspect)
    optics_authority = (
        "lens_length"
        if all(k["camera"].get("lens_length") is not None for k in resolved_keyframes)
        else "fov_degrees"
    )
    return {
        "strategy": "keyframes",
        "frames": frames,
        "provenance": {
            "strategy": "keyframes",
            "request_shape": validated["request_shape"],
            "aspect_authority": "output_resolution",
            "optics_authority": optics_authority,
            "keyframes": [
                {
                    "frame_index": keyframe["frame_index"],
                    "source": keyframe["source"],
                    "provenance": keyframe.get("provenance"),
                }
                for keyframe in resolved_keyframes
            ],
        },
    }
