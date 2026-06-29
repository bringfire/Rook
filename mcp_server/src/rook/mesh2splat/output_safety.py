from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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
    manifest: RunManifest, *, preserve_debug_artifacts: bool
) -> list[str]:
    if preserve_debug_artifacts:
        return []

    run_directory = _resolved_run_directory(manifest)
    deleted: list[str] = []
    for path in (manifest.manifest_path, *manifest.artifact_paths):
        resolved = path.resolve(strict=False)
        if not _is_inside_directory(resolved, run_directory):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        path.unlink()
        deleted.append(str(resolved))
    return deleted


def _run_directory_name(now: datetime, run_id: str) -> str:
    short_run_id = run_id[:8]
    return f"mesh2splat-{now:%Y%m%d-%H%M%S}-{short_run_id}"


def _manifest_payload(manifest: RunManifest) -> dict[str, object]:
    return {
        "runId": manifest.run_id,
        "status": manifest.status,
        "runDirectory": str(manifest.run_directory),
        "manifestPath": str(manifest.manifest_path),
        "artifactPaths": [str(path) for path in manifest.artifact_paths],
    }


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
