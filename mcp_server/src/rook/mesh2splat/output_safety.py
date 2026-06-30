from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


MANIFEST_NAME = "manifest.json"
CAPTURE_GLB_NAME = "capture.glb"
CAPTURE_PLY_NAME = "capture.ply"


@dataclass(frozen=True)
class RunPaths:
    run_directory: Path
    manifest: Path
    capture_glb: Path
    capture_ply: Path


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    run_directory: Path
    manifest_path: Path
    artifact_paths: tuple[Path, ...] = ()
    status: str = "created"
    warnings: tuple[dict[str, object], ...] = ()
    selected_executable: dict[str, object] | None = None
    output_names: dict[str, str] | None = None
    cleanup: dict[str, object] | None = None


@dataclass(frozen=True)
class CleanupResult:
    deleted: list[str]
    warnings: list[dict[str, object]]
    preserved: list[str]


def validate_output_directory(path: str) -> Path:
    output_directory = Path(path)
    if not output_directory.is_absolute():
        raise ValueError("output directory must be an absolute path")

    resolved = output_directory.resolve(strict=False)
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("output path must be a directory")
    return resolved


def create_run_directory(
    output_directory: Path, *, now: datetime, run_id: str
) -> RunPaths:
    output_directory.mkdir(parents=True, exist_ok=True)
    run_directory = output_directory / _run_directory_name(now, run_id)
    run_directory.mkdir()

    return RunPaths(
        run_directory=run_directory,
        manifest=run_directory / MANIFEST_NAME,
        capture_glb=run_directory / CAPTURE_GLB_NAME,
        capture_ply=run_directory / CAPTURE_PLY_NAME,
    )


def exclusive_write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as file:
        file.write(data)


def temp_capture_ply_path(run_directory: Path, run_id: str) -> Path:
    return run_directory / f".capture-{run_id[:8]}.ply.tmp"


def publish_temp_file_no_overwrite(temp_path: Path, final_path: Path) -> None:
    if _is_symlink_or_reparse_point(temp_path) or not temp_path.is_file():
        raise ValueError("temporary output path must be a regular file")

    try:
        os.link(temp_path, final_path)
    except FileExistsError:
        raise
    except OSError:
        _copy_temp_file_no_overwrite(temp_path, final_path)
    temp_path.unlink()


def create_manifest(manifest: RunManifest) -> None:
    manifest_path = _owned_manifest_path(manifest)
    with manifest_path.open("x", encoding="utf-8") as file:
        json.dump(_manifest_payload(manifest), file, indent=2, sort_keys=True)
        file.write("\n")


def update_manifest(manifest: RunManifest) -> None:
    manifest_path = _owned_manifest_path(manifest)
    run_directory = _resolved_run_directory(manifest)

    fd, temp_name = tempfile.mkstemp(
        prefix=".manifest-",
        suffix=".tmp",
        dir=run_directory,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(_manifest_payload(manifest), file, indent=2, sort_keys=True)
            file.write("\n")
        os.replace(temp_path, manifest_path)
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def cleanup_manifest_files(
    manifest: RunManifest,
    *,
    preserve_debug_artifacts: bool,
    preserve_manifest: bool = False,
    delete_artifact_paths: tuple[Path, ...] | None = None,
) -> CleanupResult:
    run_directory = _resolved_run_directory(manifest)
    manifest_artifact_paths = tuple(manifest.artifact_paths)
    manifest_artifact_keys = {
        _manifest_path_key(path) for path in manifest_artifact_paths
    }
    if delete_artifact_paths is None:
        artifact_paths = manifest_artifact_paths
    else:
        artifact_paths = tuple(delete_artifact_paths)

    paths = (
        (() if preserve_manifest else (manifest.manifest_path,))
        + artifact_paths
    )
    deleted: list[str] = []
    warnings: list[dict[str, object]] = []
    preserved: list[str] = []
    for path in paths:
        if path != manifest.manifest_path and _manifest_path_key(path) not in manifest_artifact_keys:
            if not path.exists() and not path.is_symlink():
                continue
            warnings.append(
                _cleanup_warning(
                    "cleanup_skipped_unmanifested_path",
                    "Cleanup skipped path not listed in manifest artifacts",
                    path.resolve(strict=False),
                )
            )
            continue
        resolved = path.resolve(strict=False)
        if _is_symlink_or_reparse_point(path):
            warnings.append(
                _cleanup_warning(
                    "cleanup_skipped_reparse_point",
                    "Cleanup skipped symlink or reparse-point path",
                    resolved,
                )
            )
            continue
        if not _is_inside_directory(resolved, run_directory):
            warnings.append(
                _cleanup_warning(
                    "cleanup_skipped_outside_run_directory",
                    "Cleanup skipped path outside run directory",
                    resolved,
                )
            )
            continue
        if not path.is_file():
            if path.exists():
                warnings.append(
                    _cleanup_warning(
                        "cleanup_skipped_non_regular_file",
                        "Cleanup skipped non-regular file",
                        resolved,
                    )
                )
            continue
        if preserve_debug_artifacts:
            preserved.append(str(resolved))
            continue
        path.unlink()
        deleted.append(str(resolved))
    return CleanupResult(deleted=deleted, warnings=warnings, preserved=preserved)


def _run_directory_name(now: datetime, run_id: str) -> str:
    short_run_id = run_id[:8]
    return f"mesh2splat-{now:%Y%m%d-%H%M%S}-{short_run_id}"


def _manifest_payload(manifest: RunManifest) -> dict[str, object]:
    payload: dict[str, object] = {
        "runId": manifest.run_id,
        "status": manifest.status,
        "runDirectory": str(manifest.run_directory),
        "manifestPath": str(manifest.manifest_path),
        "artifactPaths": [str(path) for path in manifest.artifact_paths],
        "warnings": [dict(warning) for warning in manifest.warnings],
    }
    if manifest.selected_executable is not None:
        payload["selectedExecutable"] = _jsonable(manifest.selected_executable)
    if manifest.output_names is not None:
        payload["outputNames"] = dict(manifest.output_names)
    if manifest.cleanup is not None:
        payload["cleanup"] = _jsonable(manifest.cleanup)
    return payload


def _copy_temp_file_no_overwrite(temp_path: Path, final_path: Path) -> None:
    created_final = False
    try:
        with temp_path.open("rb") as source, final_path.open("xb") as destination:
            created_final = True
            shutil.copyfileobj(source, destination)
    except FileExistsError:
        raise
    except Exception:
        if created_final:
            try:
                final_path.unlink()
            except FileNotFoundError:
                pass
        raise


def _manifest_path_key(path: Path) -> str:
    return str(path.resolve(strict=False)).lower()


def _cleanup_warning(code: str, message: str, path: Path) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        "path": str(path),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _resolved_run_directory(manifest: RunManifest) -> Path:
    run_directory = manifest.run_directory
    if _is_symlink_or_reparse_point(run_directory):
        raise ValueError("run directory must not be a symlink or reparse point")
    if not run_directory.is_dir():
        raise ValueError("run directory must exist")
    return run_directory


def _owned_manifest_path(manifest: RunManifest) -> Path:
    run_directory = _resolved_run_directory(manifest)
    manifest_path = manifest.manifest_path.resolve(strict=False)
    if (
        manifest_path.parent != run_directory
        or manifest_path.name != MANIFEST_NAME
        or not _is_inside_directory(manifest_path, run_directory)
    ):
        raise ValueError("manifest path must be inside the run directory")
    return manifest_path


def _is_inside_directory(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _is_symlink_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        file_attributes = os.lstat(path).st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
