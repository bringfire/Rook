from __future__ import annotations

import ctypes
import hashlib
import json
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
