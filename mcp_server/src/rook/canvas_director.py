from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
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


def _ensure_under(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise CanvasDirectorError("export_write_failed", "Export path escapes director root.") from exc
    return resolved_path


def _director_root(project_root: str | os.PathLike[str]) -> Path:
    root = Path(project_root) / ".rook" / "director"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc
    return root


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


def save_canvas_export(
    project_root: str | os.PathLike[str],
    envelope: dict[str, Any],
    *,
    export_id: Any = None,
) -> dict[str, Any]:
    state, actual_hash = _verify_envelope(envelope)
    selected_export_id = validate_canvas_director_id(
        export_id if export_id is not None else state.get("export_id")
    )

    director_root = _director_root(project_root)
    exports_root = director_root / "exports"
    try:
        exports_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc
    export_path = _ensure_under(exports_root / f"{selected_export_id}.json", director_root)

    if export_path.exists():
        try:
            existing = json.loads(export_path.read_text(encoding="utf-8"))
            existing_state, existing_hash = _verify_envelope(existing)
        except CanvasDirectorError as exc:
            raise CanvasDirectorError("id_collision", "Existing canvas export is unverifiable.") from exc
        except Exception as exc:
            raise CanvasDirectorError("id_collision", "Existing canvas export is unreadable.") from exc

        if existing_hash == actual_hash and _canonical_json_bytes(existing_state) == _canonical_json_bytes(state):
            return {
                "export_id": selected_export_id,
                "export_path": export_path,
                "canvas_export_state_sha256": actual_hash,
                "idempotent": True,
            }

        raise CanvasDirectorError("id_collision", "Canvas export id already exists with different state.")

    try:
        _atomic_write_json(export_path, envelope)
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc

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
