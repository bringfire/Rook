from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .bridge import call_rhino


ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")

_RESERVED_WINDOWS_TOKENS = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_LOCK_WAIT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.01
_MALFORMED_LOCK_STALE_SECONDS = 5.0


class CanvasDirectorError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or code
        super().__init__(self.message)

    def to_data(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def validate_canvas_director_id(value: Any, *, kind: str = "export") -> str:
    code = "invalid_spec_id" if kind == "spec" else "invalid_export_id"
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise CanvasDirectorError(code, f"Invalid CanvasDirector {kind} id.")
    if value.lower() in _RESERVED_WINDOWS_TOKENS:
        raise CanvasDirectorError(code, f"Reserved CanvasDirector {kind} id.")
    return value


def _validate_restricted_canonical_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool)):
        return

    if isinstance(value, int):
        if value < _INT64_MIN or value > _INT64_MAX:
            raise CanvasDirectorError("invalid_input", "Canonical JSON integers must fit signed int64.")
        return

    if isinstance(value, float):
        raise CanvasDirectorError("invalid_input", "Canonical JSON does not allow non-integer numbers.")

    if isinstance(value, list):
        for item in value:
            _validate_restricted_canonical_value(item)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise CanvasDirectorError(
                    "invalid_input",
                    "Canonical JSON object keys must be ASCII strings.",
                )
            _validate_restricted_canonical_value(item)
        return

    raise CanvasDirectorError("invalid_input", "Unsupported value in canonical JSON payload.")


def _canonical_json_bytes(value: Any) -> bytes:
    _validate_restricted_canonical_value(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canvas_export_state_sha256(state: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(state)).hexdigest()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as tmp:
            tmp_name = tmp.name
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
        Path(tmp_name).replace(path)
    except Exception:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise


def _canonical_json_bytes_unrestricted(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validate_json_payload(value: Any) -> None:
    try:
        json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CanvasDirectorError("spec_compile_failed", str(exc)) from exc


def _ensure_resolved_under(path: Path, root: Path, message: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise CanvasDirectorError("export_write_failed", message) from exc
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc


def _ensure_under(path: Path, root: Path, *, project_root: Path | None = None) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise CanvasDirectorError("export_write_failed", "Export path escapes director root.") from exc

    if project_root is not None:
        resolved_project_root = project_root.resolve()
        try:
            resolved_path.relative_to(resolved_project_root)
        except ValueError as exc:
            raise CanvasDirectorError("export_write_failed", "Export path escapes project root.") from exc

    return resolved_path


def _director_root(project_root: str | os.PathLike[str]) -> Path:
    project_path = Path(project_root)
    rook_root = project_path / ".rook"
    root = rook_root / "director"
    try:
        # On Windows, junctions may not be reported as symlinks by pathlib; the
        # final resolved export path is also checked against the project root.
        if rook_root.is_symlink() or root.is_symlink():
            raise CanvasDirectorError("export_write_failed", "Director path may not be a symlink.")
        if rook_root.exists():
            _ensure_resolved_under(rook_root, project_path, "Rook metadata root escapes project root.")
        if root.exists():
            _ensure_resolved_under(root, project_path, "Director path escapes project root.")
        root.mkdir(parents=True, exist_ok=True)
        if rook_root.is_symlink() or root.is_symlink():
            raise CanvasDirectorError("export_write_failed", "Director path may not be a symlink.")
        _ensure_resolved_under(rook_root, project_path, "Rook metadata root escapes project root.")
        _ensure_resolved_under(root, project_path, "Director path escapes project root.")
    except CanvasDirectorError:
        raise
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc
    return root


def _acquire_export_lock(lock_path: Path) -> None:
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        try:
            with lock_path.open("x", encoding="utf-8") as lock:
                lock.write(f"{os.getpid()}\n")
            return
        except FileExistsError:
            if _remove_stale_lock_if_possible(lock_path):
                continue
            if time.monotonic() >= deadline:
                raise CanvasDirectorError("export_write_failed", "Timed out waiting for export lock.")
            time.sleep(_LOCK_POLL_SECONDS)
        except OSError as exc:
            raise CanvasDirectorError("export_write_failed", str(exc)) from exc


def _release_export_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            int(pid),
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_pid(lock_path: Path) -> int | None:
    try:
        text = lock_path.read_text(encoding="utf-8").strip().splitlines()
        return int(text[0]) if text else None
    except Exception:
        return None


def _remove_stale_lock_if_possible(lock_path: Path) -> bool:
    pid = _lock_pid(lock_path)
    if pid is not None and _is_pid_alive(pid):
        return False

    if pid is None:
        try:
            age_seconds = time.time() - lock_path.stat().st_mtime
        except OSError:
            return False
        if age_seconds < _MALFORMED_LOCK_STALE_SECONDS:
            return False

    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _verify_envelope(envelope: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(envelope, dict):
        raise CanvasDirectorError("invalid_input", "Canvas export envelope must be an object.")

    state = envelope.get("canvas_export_state")
    if not isinstance(state, dict):
        raise CanvasDirectorError("invalid_input", "Canvas export state must be an object.")

    actual_hash = canvas_export_state_sha256(state)
    if envelope.get("canvas_export_state_sha256") != actual_hash:
        raise CanvasDirectorError("invalid_input", "Canvas export state hash mismatch.")

    if envelope.get("read_only") is not True:
        raise CanvasDirectorError("invalid_input", "Canvas export envelope must be read-only.")

    return state, actual_hash


def _load_existing_export(
    export_path: Path,
    *,
    wait_for_complete: bool = False,
) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + 5.0
    while True:
        try:
            existing = json.loads(export_path.read_text(encoding="utf-8"))
            return _verify_envelope(existing)
        except CanvasDirectorError as exc:
            raise CanvasDirectorError("id_collision", "Existing canvas export is unverifiable.") from exc
        except Exception as exc:
            if wait_for_complete and time.monotonic() < deadline:
                time.sleep(0.01)
                continue
            raise CanvasDirectorError("id_collision", "Existing canvas export is unreadable.") from exc


def _existing_export_result(
    export_path: Path,
    selected_export_id: str,
    state: dict[str, Any],
    actual_hash: str,
    *,
    wait_for_complete: bool = False,
) -> dict[str, Any]:
    existing_state, existing_hash = _load_existing_export(
        export_path,
        wait_for_complete=wait_for_complete,
    )

    if existing_hash == actual_hash and _canonical_json_bytes(existing_state) == _canonical_json_bytes(state):
        return {
            "export_id": selected_export_id,
            "export_path": export_path,
            "canvas_export_state_sha256": actual_hash,
            "idempotent": True,
        }

    raise CanvasDirectorError("id_collision", "Canvas export id already exists with different state.")


def save_canvas_export(
    project_root: str | os.PathLike[str],
    envelope: dict[str, Any],
    *,
    export_id: Any = None,
) -> dict[str, Any]:
    state, actual_hash = _verify_envelope(envelope)
    state_export_id = validate_canvas_director_id(state.get("export_id"))
    selected_export_id = validate_canvas_director_id(
        export_id if export_id is not None else state_export_id
    )
    if selected_export_id != state_export_id:
        raise CanvasDirectorError("invalid_export_id", "Export id does not match canvas export state.")

    project_path = Path(project_root)
    director_root = _director_root(project_path)
    exports_root = director_root / "exports"
    _ensure_under(exports_root, director_root, project_root=project_path)
    try:
        exports_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc
    export_path = _ensure_under(
        exports_root / f"{selected_export_id}.json",
        director_root,
        project_root=project_path,
    )
    lock_path = _ensure_under(
        export_path.with_name(f"{export_path.name}.lock"),
        director_root,
        project_root=project_path,
    )

    if export_path.exists():
        return _existing_export_result(export_path, selected_export_id, state, actual_hash)

    _acquire_export_lock(lock_path)
    try:
        if export_path.exists():
            return _existing_export_result(export_path, selected_export_id, state, actual_hash)

        try:
            _atomic_write_json(export_path, envelope)
        except OSError as exc:
            raise CanvasDirectorError("export_write_failed", str(exc)) from exc
    finally:
        _release_export_lock(lock_path)

    return {
        "export_id": selected_export_id,
        "export_path": export_path,
        "canvas_export_state_sha256": actual_hash,
        "idempotent": False,
    }


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise CanvasDirectorError("spec_compile_failed", "Numeric fields may not be booleans.")
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        try:
            out = float(value)
        except ValueError as exc:
            raise CanvasDirectorError(
                "spec_compile_failed",
                f"Invalid numeric field: {value!r}.",
            ) from exc
    else:
        raise CanvasDirectorError("spec_compile_failed", "Numeric fields must be numbers or numeric strings.")

    if not math.isfinite(out):
        raise CanvasDirectorError("spec_compile_failed", "Numeric fields must be finite.")
    return out


def _number_array(value: Any, *, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise CanvasDirectorError("spec_compile_failed", f"{field} must be a 3-number array.")
    return [_number(component) for component in value]


def _convert_rotate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CanvasDirectorError("spec_compile_failed", "Keyframe rotate must be an object.")
    if "axis" not in value or "angle_degrees" not in value:
        raise CanvasDirectorError("spec_compile_failed", "Keyframe rotate requires axis and angle_degrees.")

    rotate = dict(value)
    rotate["axis"] = _number_array(rotate["axis"], field="Keyframe rotate.axis")
    rotate["angle_degrees"] = _number(rotate["angle_degrees"])
    if "pivot" in rotate:
        pivot = rotate["pivot"]
        if pivot != "object_center":
            rotate["pivot"] = _number_array(pivot, field="Keyframe rotate.pivot")
    return rotate


def _convert_keyframes(entries: Any) -> list[dict[str, Any]]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise CanvasDirectorError("spec_compile_failed", "Motion keyframes must be an array.")

    converted: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise CanvasDirectorError("spec_compile_failed", "Motion keyframes must be objects.")
        keyframe = dict(entry)
        if "t" in keyframe:
            keyframe["t"] = _number(keyframe["t"])
        if "translate" in keyframe:
            translate = keyframe["translate"]
            if not isinstance(translate, list) or len(translate) != 3:
                raise CanvasDirectorError(
                    "spec_compile_failed",
                    "Keyframe translate must be a 3-number array.",
                )
            keyframe["translate"] = [_number(component) for component in translate]
        if "scale" in keyframe:
            scale = keyframe["scale"]
            if isinstance(scale, list):
                if len(scale) != 3:
                    raise CanvasDirectorError(
                        "spec_compile_failed",
                        "Keyframe scale array must have 3 components.",
                    )
                keyframe["scale"] = [_number(component) for component in scale]
            else:
                keyframe["scale"] = _number(scale)
        if "rotate" in keyframe:
            keyframe["rotate"] = _convert_rotate(keyframe["rotate"])
        converted.append(keyframe)
    return converted


def _convert_motion(entries: Any) -> list[dict[str, Any]]:
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise CanvasDirectorError("spec_compile_failed", "Payload motion must be an array.")

    converted: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise CanvasDirectorError("spec_compile_failed", "Motion entries must be objects.")
        motion_entry = dict(entry)
        motion_entry["keyframes"] = _convert_keyframes(motion_entry.get("keyframes"))
        converted.append(motion_entry)
    return converted


def compile_authoring_spec(envelope: Any, *, spec_id: Any = None) -> dict[str, Any]:
    state, actual_hash = _verify_envelope(envelope)
    payload = state.get("payload")
    if not isinstance(payload, dict):
        raise CanvasDirectorError("spec_compile_failed", "Canvas export state payload must be an object.")

    selected_spec_id = validate_canvas_director_id(
        spec_id
        if spec_id is not None
        else envelope.get("suggested_spec_id", state.get("export_id")),
        kind="spec",
    )
    timeline = payload.get("timeline")
    if not isinstance(timeline, dict):
        raise CanvasDirectorError("spec_compile_failed", "Payload timeline must be an object.")

    resolution = payload.get("resolution", {"width": 1920, "height": 1080})
    if not isinstance(resolution, dict):
        raise CanvasDirectorError("spec_compile_failed", "Payload resolution must be an object.")

    groups = payload.get("groups", {})
    if not isinstance(groups, dict):
        raise CanvasDirectorError("spec_compile_failed", "Payload groups must be an object.")

    camera = payload.get("camera")
    if camera is not None and not isinstance(camera, dict):
        raise CanvasDirectorError("spec_compile_failed", "Payload camera must be an object.")

    spec: dict[str, Any] = {
        "metadata_kind": "director_authoring_spec",
        "schema_version": 1,
        "spec_id": selected_spec_id,
        "source": {
            "canvas_export_state_sha256": actual_hash,
            "export_id": state.get("export_id"),
            "template_id": state.get("template_id"),
            "template_version": state.get("template_version"),
        },
        "timeline": dict(timeline),
        "resolution": dict(resolution),
        "groups": dict(groups),
        "motion": _convert_motion(payload.get("motion")),
    }
    if isinstance(camera, dict):
        spec["camera"] = dict(camera)
    if isinstance(payload.get("default_easing"), str):
        spec["default_easing"] = payload["default_easing"]
    return spec


def _raise_spec_write_failed(exc: Exception) -> None:
    raise CanvasDirectorError("spec_write_failed", str(exc)) from exc


def _existing_spec_result(spec_path: Path, selected_spec_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    try:
        existing = json.loads(spec_path.read_text(encoding="utf-8"))
        if _canonical_json_bytes_unrestricted(existing) == _canonical_json_bytes_unrestricted(spec):
            return {"spec_id": selected_spec_id, "spec_path": spec_path, "idempotent": True}
    except Exception as exc:
        raise CanvasDirectorError("id_collision", "Existing authoring spec is unreadable.") from exc
    raise CanvasDirectorError("id_collision", "Authoring spec id already exists with different content.")


def save_authoring_spec(
    project_root: str | os.PathLike[str],
    spec: dict[str, Any],
    *,
    spec_id: Any = None,
    replace: bool = False,
) -> dict[str, Any]:
    if not isinstance(spec, dict) or spec.get("metadata_kind") != "director_authoring_spec":
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec must be a director_authoring_spec.")
    _validate_json_payload(spec)

    selected_spec_id = validate_canvas_director_id(
        spec_id if spec_id is not None else spec.get("spec_id"),
        kind="spec",
    )
    if selected_spec_id != spec.get("spec_id"):
        raise CanvasDirectorError("invalid_spec_id", "Spec id does not match authoring spec.")

    project_path = Path(project_root)
    try:
        director_root = _director_root(project_path)
        specs_root = _ensure_under(director_root / "specs", director_root, project_root=project_path)
        specs_root.mkdir(parents=True, exist_ok=True)
        spec_path = _ensure_under(
            specs_root / f"{selected_spec_id}.json",
            director_root,
            project_root=project_path,
        )
        lock_path = _ensure_under(
            spec_path.with_name(f"{spec_path.name}.lock"),
            director_root,
            project_root=project_path,
        )
    except CanvasDirectorError as exc:
        if exc.code == "export_write_failed":
            _raise_spec_write_failed(exc)
        raise
    except OSError as exc:
        _raise_spec_write_failed(exc)

    if spec_path.exists() and not replace:
        return _existing_spec_result(spec_path, selected_spec_id, spec)

    try:
        _acquire_export_lock(lock_path)
        try:
            if spec_path.exists() and not replace:
                return _existing_spec_result(spec_path, selected_spec_id, spec)

            try:
                _atomic_write_json(spec_path, spec)
            except OSError as exc:
                _raise_spec_write_failed(exc)
            except ValueError as exc:
                raise CanvasDirectorError("spec_compile_failed", str(exc)) from exc
        finally:
            _release_export_lock(lock_path)
    except CanvasDirectorError as exc:
        if exc.code == "export_write_failed":
            _raise_spec_write_failed(exc)
        raise

    return {"spec_id": selected_spec_id, "spec_path": spec_path, "idempotent": False}


def build_compile_motion_request(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict) or spec.get("metadata_kind") != "director_authoring_spec":
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec must be a director_authoring_spec.")

    timeline = spec.get("timeline")
    if not isinstance(timeline, dict):
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec timeline must be an object.")

    motion = spec.get("motion")
    if not isinstance(motion, list) or not motion:
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec motion must be a non-empty array.")

    resolution = spec.get("resolution", {"width": 1920, "height": 1080})
    if not isinstance(resolution, dict):
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec resolution must be an object.")

    groups = spec.get("groups", {})
    if not isinstance(groups, dict):
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec groups must be an object.")

    request: dict[str, Any] = {
        "timeline": timeline,
        "resolution": resolution,
        "groups": groups,
        "motion": motion,
    }
    camera = spec.get("camera")
    if camera is not None and not isinstance(camera, dict):
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec camera must be an object.")
    if isinstance(camera, dict) and camera:
        request["camera"] = camera
    if isinstance(spec.get("default_easing"), str):
        request["default_easing"] = spec["default_easing"]
    return request


def build_run_inputs(envelope: Any, spec: Any) -> dict[str, Any]:
    state, actual_hash = _verify_envelope(envelope)
    if not isinstance(spec, dict) or spec.get("metadata_kind") != "director_authoring_spec":
        raise CanvasDirectorError("spec_compile_failed", "Authoring spec must be a director_authoring_spec.")
    _validate_json_payload(spec)
    source_spec_id = spec.get("spec_id")
    if not isinstance(source_spec_id, str):
        raise CanvasDirectorError("invalid_spec_id", "Authoring spec id is required.")
    source = spec.get("source")
    declared_export_hash = (
        source.get("canvas_export_state_sha256")
        if isinstance(source, dict)
        else None
    )
    if declared_export_hash is not None and declared_export_hash != actual_hash:
        raise CanvasDirectorError(
            "invalid_input",
            "Authoring spec source hash does not match canvas export envelope.",
        )

    source_spec_sha256 = hashlib.sha256(
        _canonical_json_bytes_unrestricted(spec)
    ).hexdigest()
    return {
        "director_authoring_spec": spec,
        "provenance": {
            "source_spec_id": source_spec_id,
            "source_spec_sha256": source_spec_sha256,
            "canvas_export_state_sha256": actual_hash,
            "template_version": state.get("template_version"),
        },
    }


async def extract_canvas_export(
    arguments: dict[str, Any],
    *,
    call_native=call_rhino,
    port: int | None = None,
) -> dict[str, Any]:
    body = dict(arguments)
    result = await call_native("/director/canvas/extract", "POST", body, port=port)

    if not isinstance(result, dict) or result.get("success") is not True:
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, dict) and isinstance(data.get("code"), str):
            code = data["code"]
            raise CanvasDirectorError(code, data.get("message") or code)
        raise CanvasDirectorError(
            "canvas_director_unavailable",
            "CanvasDirector extraction is unavailable.",
        )

    data = result.get("data")
    if not isinstance(data, dict):
        raise CanvasDirectorError("invalid_input", "CanvasDirector extraction returned invalid data.")

    _verify_envelope(data)
    return data
