"""Shared document helpers for Director v3 worker package flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class DirectorWorkerError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self)}


def norm_path(value: str) -> str:
    return str(Path(value)).replace("\\", "/").casefold()


async def native_call(call_native, endpoint: str, method: str,
                      data: dict | None, port: int | None,
                      error_code: str, error_cls) -> Any:
    envelope = await call_native(endpoint, method, data, port=port)
    if not isinstance(envelope, dict) or not envelope.get("success"):
        detail = envelope.get("data") if isinstance(envelope, dict) else envelope
        raise error_cls(error_code, f"{endpoint} failed: {detail}")
    return envelope.get("data")


async def get_document(call_native, port: int | None, error_cls) -> dict[str, Any]:
    data = await native_call(
        call_native, "/document", "GET", None, port,
        "document_open_failed", error_cls)
    return data if isinstance(data, dict) else {}


def enforce_save_copy_evidence(evidence: dict[str, Any], error_cls) -> None:
    required = (
        "path_before", "path_after", "title_before", "title_after",
        "modified_before", "modified_after", "save_small_used")
    missing_fields = [key for key in required if key not in evidence]
    if missing_fields:
        raise error_cls(
            "save_copy_invariant_violation",
            "save-copy evidence incomplete (old native build?); "
            f"missing: {missing_fields}")
    if (evidence["path_before"] != evidence["path_after"]
            or evidence["title_before"] != evidence["title_after"]
            or evidence["modified_before"] != evidence["modified_after"]
            or evidence["save_small_used"] is not False):
        raise error_cls(
            "save_copy_invariant_violation",
            f"save-copy changed document state: {evidence}")


async def open_package_document(call_native, package_root: Path, target: Path, *,
                                port: int | None, error_cls,
                                mode: str) -> None:
    """Open a package document with package-aware dirty-doc protection.

    mode="fail_closed" preserves Slice 2 prepare semantics: a same-path
    alreadyOpen response cannot prove a reload, so it fails. mode="require_fresh"
    double-hops through the other package file to force a real reload.
    """
    if mode not in ("fail_closed", "require_fresh"):
        raise ValueError(f"unknown mode: {mode}")

    package_root = Path(package_root)
    target = Path(target)
    scene = package_root / "scene.3dm"
    prepared = package_root / "prepared.3dm"
    package_norms = {norm_path(str(scene)), norm_path(str(prepared))}

    live = await get_document(call_native, port, error_cls)
    live_norm = norm_path(live.get("path") or "")
    if bool(live.get("modified")) and live_norm not in package_norms:
        raise error_cls(
            "document_not_saved",
            "the current document has unsaved changes; opening the take "
            "copy would silently discard them — save the document first")

    async def _open(path: Path) -> dict[str, Any]:
        data = await native_call(
            call_native, "/document/open", "POST", {"path": str(path)},
            port, "document_open_failed", error_cls)
        return data if isinstance(data, dict) else {}

    opened = await _open(target)
    if opened.get("alreadyOpen"):
        if mode == "fail_closed":
            raise error_cls(
                "take_copy_not_pristine",
                "the take copy was already the active document and Rhino "
                "did not reload it from disk; close the document in Rhino, "
                "then re-run")
        via = scene if norm_path(str(target)) == norm_path(str(prepared)) else prepared
        if not via.is_file():
            raise error_cls(
                "take_copy_not_pristine",
                f"cannot force-reload {target.name}: intermediate "
                f"{via.name} is missing from the package")
        await _open(via)
        await _open(target)

    after = await get_document(call_native, port, error_cls)
    if norm_path(after.get("path") or "") != norm_path(str(target)):
        raise error_cls(
            "wrong_document",
            f"active document is {after.get('path')!r}; expected {target}")
