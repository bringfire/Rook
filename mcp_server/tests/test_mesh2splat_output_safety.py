from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest


def fixed_now() -> datetime:
    return datetime(2026, 3, 8, 14, 5, 6)


def new_manifest(tmp_path: Path):
    from rook.mesh2splat.output_safety import RunManifest, create_run_directory

    paths = create_run_directory(
        tmp_path / "outputs",
        now=fixed_now(),
        run_id="abcdef1234567890",
    )
    return RunManifest(
        run_id="abcdef1234567890",
        run_directory=paths.run_directory,
        manifest_path=paths.manifest,
        artifact_paths=(paths.capture_glb, paths.capture_ply),
    )


def test_validate_output_directory_is_side_effect_free_before_native_capture(
    tmp_path: Path,
):
    from rook.mesh2splat.output_safety import validate_output_directory

    output_directory = tmp_path / "requested" / "mesh2splat"

    result = validate_output_directory(str(output_directory))

    assert result == output_directory.resolve()
    assert not output_directory.exists()


def test_validate_output_directory_rejects_relative_paths():
    from rook.mesh2splat.output_safety import validate_output_directory

    with pytest.raises(ValueError, match="absolute"):
        validate_output_directory("relative/out")


def test_validate_output_directory_rejects_existing_file_path(tmp_path: Path):
    from rook.mesh2splat.output_safety import validate_output_directory

    output_file = tmp_path / "not-a-directory"
    output_file.write_text("already here", encoding="utf-8")

    with pytest.raises(ValueError, match="directory"):
        validate_output_directory(str(output_file))


def test_missing_requested_output_directory_is_created_only_after_capture_succeeds(
    tmp_path: Path,
):
    from rook.mesh2splat.output_safety import (
        create_run_directory,
        validate_output_directory,
    )

    output_directory = tmp_path / "new-output-root"
    validated = validate_output_directory(str(output_directory))

    assert not output_directory.exists()

    paths = create_run_directory(
        validated,
        now=fixed_now(),
        run_id="1234567890",
    )

    assert output_directory.is_dir()
    assert paths.run_directory.is_dir()


def test_newly_created_parent_output_directory_is_retained_after_run_directory_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from rook.mesh2splat.output_safety import create_run_directory

    missing_parent = tmp_path / "later-created-root"
    original_mkdir = Path.mkdir

    def fail_run_directory_mkdir(self, *args, **kwargs):
        if self.name == "mesh2splat-20260308-140506-abcdef12":
            raise FileExistsError(self)
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_run_directory_mkdir)

    with pytest.raises(FileExistsError):
        create_run_directory(
            missing_parent,
            now=fixed_now(),
            run_id="abcdef1234567890",
        )

    assert missing_parent.is_dir()


def test_run_directory_and_fixed_output_names(tmp_path: Path):
    from rook.mesh2splat.output_safety import create_run_directory

    paths = create_run_directory(
        tmp_path,
        now=fixed_now(),
        run_id="abcdef1234567890",
    )

    assert paths.run_directory.name == "mesh2splat-20260308-140506-abcdef12"
    assert paths.manifest == paths.run_directory / "manifest.json"
    assert paths.capture_glb == paths.run_directory / "capture.glb"
    assert paths.capture_ply == paths.run_directory / "capture.ply"


def test_exclusive_creation_refuses_run_directory_collisions(tmp_path: Path):
    from rook.mesh2splat.output_safety import create_run_directory

    create_run_directory(tmp_path, now=fixed_now(), run_id="abcdef1234567890")

    with pytest.raises(FileExistsError):
        create_run_directory(
            tmp_path,
            now=fixed_now(),
            run_id="abcdef1234567890",
        )


def test_exclusive_write_bytes_refuses_file_collisions(tmp_path: Path):
    from rook.mesh2splat.output_safety import exclusive_write_bytes

    output_file = tmp_path / "capture.glb"

    exclusive_write_bytes(output_file, b"first")

    with pytest.raises(FileExistsError):
        exclusive_write_bytes(output_file, b"second")

    assert output_file.read_bytes() == b"first"


def test_manifest_creation_is_exclusive_and_update_replaces_owned_manifest(
    tmp_path: Path,
):
    from rook.mesh2splat.output_safety import (
        RunManifest,
        create_manifest,
        update_manifest,
    )

    manifest = new_manifest(tmp_path)

    create_manifest(manifest)

    with pytest.raises(FileExistsError):
        create_manifest(manifest)

    updated = RunManifest(
        run_id=manifest.run_id,
        run_directory=manifest.run_directory,
        manifest_path=manifest.manifest_path,
        artifact_paths=manifest.artifact_paths + (manifest.run_directory / "extra.txt",),
        status="updated",
    )
    update_manifest(updated)

    data = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert data["status"] == "updated"
    assert data["artifactPaths"][-1].endswith("extra.txt")
    assert not list(manifest.run_directory.glob("*.tmp"))


def test_manifest_payload_records_diagnostics_for_postmortems(tmp_path: Path):
    from rook.mesh2splat.output_safety import RunManifest, create_manifest

    manifest = new_manifest(tmp_path)
    diagnostic = RunManifest(
        run_id=manifest.run_id,
        run_directory=manifest.run_directory,
        manifest_path=manifest.manifest_path,
        artifact_paths=manifest.artifact_paths,
        status="failed:mesh2splat_timeout",
        warnings=({"code": "native_warn", "message": "native warning"},),
        selected_executable={
            "source": "explicit",
            "path": tmp_path / "Mesh2Splat.exe",
        },
        output_names={"glb": "capture.glb", "ply": "capture.ply"},
        cleanup={
            "preserveDebugArtifacts": False,
            "deleted": [str(manifest.run_directory / "capture.ply")],
            "warnings": [],
        },
    )

    create_manifest(diagnostic)

    data = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert data["status"] == "failed:mesh2splat_timeout"
    assert data["warnings"] == [{"code": "native_warn", "message": "native warning"}]
    assert data["selectedExecutable"] == {
        "source": "explicit",
        "path": str(tmp_path / "Mesh2Splat.exe"),
    }
    assert data["outputNames"] == {"glb": "capture.glb", "ply": "capture.ply"}
    assert data["cleanup"]["deleted"] == [str(manifest.run_directory / "capture.ply")]


def test_manifest_update_refuses_to_replace_manifest_outside_run_directory(
    tmp_path: Path,
):
    from rook.mesh2splat.output_safety import RunManifest, update_manifest

    run_directory = tmp_path / "run"
    run_directory.mkdir()
    outside_manifest = tmp_path / "manifest.json"
    outside_manifest.write_text("outside", encoding="utf-8")
    manifest = RunManifest(
        run_id="run",
        run_directory=run_directory,
        manifest_path=outside_manifest,
        artifact_paths=(),
    )

    with pytest.raises(ValueError, match="inside"):
        update_manifest(manifest)

    assert outside_manifest.read_text(encoding="utf-8") == "outside"


def test_capture_glb_and_ply_remain_exclusive_for_the_whole_run(tmp_path: Path):
    from rook.mesh2splat.output_safety import (
        create_run_directory,
        exclusive_write_bytes,
    )

    paths = create_run_directory(tmp_path, now=fixed_now(), run_id="abcdef12")

    exclusive_write_bytes(paths.capture_glb, b"glb")
    exclusive_write_bytes(paths.capture_ply, b"ply")

    with pytest.raises(FileExistsError):
        exclusive_write_bytes(paths.capture_glb, b"replace glb")
    with pytest.raises(FileExistsError):
        exclusive_write_bytes(paths.capture_ply, b"replace ply")

    assert paths.capture_glb.read_bytes() == b"glb"
    assert paths.capture_ply.read_bytes() == b"ply"


def test_publish_temp_file_no_overwrite_preserves_existing_destination(tmp_path: Path):
    from rook.mesh2splat.output_safety import publish_temp_file_no_overwrite

    temp_path = tmp_path / ".capture.ply.tmp"
    final_path = tmp_path / "capture.ply"
    temp_path.write_bytes(b"new ply")
    final_path.write_bytes(b"foreign ply")

    with pytest.raises(FileExistsError):
        publish_temp_file_no_overwrite(temp_path, final_path)

    assert temp_path.read_bytes() == b"new ply"
    assert final_path.read_bytes() == b"foreign ply"


def test_publish_temp_file_no_overwrite_publishes_and_removes_temp(tmp_path: Path):
    from rook.mesh2splat.output_safety import publish_temp_file_no_overwrite

    temp_path = tmp_path / ".capture.ply.tmp"
    final_path = tmp_path / "capture.ply"
    temp_path.write_bytes(b"new ply")

    publish_temp_file_no_overwrite(temp_path, final_path)

    assert final_path.read_bytes() == b"new ply"
    assert not temp_path.exists()


def test_cleanup_deletes_only_regular_files_inside_current_run_directory(
    tmp_path: Path,
):
    from rook.mesh2splat.output_safety import cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    manifest.manifest_path.write_text("{}", encoding="utf-8")
    glb, ply = manifest.artifact_paths
    glb.write_bytes(b"glb")
    ply.write_bytes(b"ply")
    nested = manifest.run_directory / "nested"
    nested.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    malicious = type(manifest)(
        run_id=manifest.run_id,
        run_directory=manifest.run_directory,
        manifest_path=manifest.manifest_path,
        artifact_paths=manifest.artifact_paths + (nested, outside),
    )

    result = cleanup_manifest_files(
        malicious,
        preserve_debug_artifacts=False,
    )

    assert sorted(Path(path).name for path in result.deleted) == [
        "capture.glb",
        "capture.ply",
        "manifest.json",
    ]
    assert result.warnings == [
        {
            "code": "cleanup_skipped_non_regular_file",
            "message": "Cleanup skipped non-regular file",
            "path": str(nested.resolve(strict=False)),
        },
        {
            "code": "cleanup_skipped_outside_run_directory",
            "message": "Cleanup skipped path outside run directory",
            "path": str(outside.resolve(strict=False)),
        },
    ]
    assert not glb.exists()
    assert not ply.exists()
    assert not manifest.manifest_path.exists()
    assert nested.is_dir()
    assert outside.read_text(encoding="utf-8") == "outside"
    assert manifest.run_directory.is_dir()


def test_cleanup_can_preserve_manifest_while_deleting_artifacts(tmp_path: Path):
    from rook.mesh2splat.output_safety import cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    manifest.manifest_path.write_text("{}", encoding="utf-8")
    glb, ply = manifest.artifact_paths
    glb.write_bytes(b"glb")
    ply.write_bytes(b"ply")

    result = cleanup_manifest_files(
        manifest,
        preserve_debug_artifacts=False,
        preserve_manifest=True,
    )

    assert sorted(Path(path).name for path in result.deleted) == [
        "capture.glb",
        "capture.ply",
    ]
    assert result.warnings == []
    assert manifest.manifest_path.exists()
    assert not glb.exists()
    assert not ply.exists()


def test_cleanup_reports_skipped_manifest_paths(tmp_path: Path):
    from rook.mesh2splat.output_safety import RunManifest, cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    malicious = RunManifest(
        run_id=manifest.run_id,
        run_directory=manifest.run_directory,
        manifest_path=manifest.manifest_path,
        artifact_paths=(outside,),
    )

    result = cleanup_manifest_files(
        malicious,
        preserve_debug_artifacts=False,
        preserve_manifest=True,
    )

    assert result.deleted == []
    assert result.warnings == [
        {
            "code": "cleanup_skipped_outside_run_directory",
            "message": "Cleanup skipped path outside run directory",
            "path": str(outside.resolve(strict=False)),
        }
    ]
    assert outside.read_text(encoding="utf-8") == "outside"


def test_cleanup_reports_requested_paths_missing_from_manifest(tmp_path: Path):
    from rook.mesh2splat.output_safety import cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    unlisted = manifest.run_directory / "unlisted.tmp"
    unlisted.write_bytes(b"do not delete")

    result = cleanup_manifest_files(
        manifest,
        preserve_debug_artifacts=False,
        preserve_manifest=True,
        delete_artifact_paths=(unlisted,),
    )

    assert result.deleted == []
    assert result.warnings == [
        {
            "code": "cleanup_skipped_unmanifested_path",
            "message": "Cleanup skipped path not listed in manifest artifacts",
            "path": str(unlisted.resolve(strict=False)),
        }
    ]
    assert unlisted.read_bytes() == b"do not delete"


def test_cleanup_preserve_debug_artifacts_deletes_nothing(tmp_path: Path):
    from rook.mesh2splat.output_safety import cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    manifest.manifest_path.write_text("{}", encoding="utf-8")
    for path in manifest.artifact_paths:
        path.write_bytes(path.name.encode("utf-8"))

    deleted = cleanup_manifest_files(manifest, preserve_debug_artifacts=True)

    assert deleted.deleted == []
    assert deleted.warnings == []
    assert manifest.manifest_path.exists()
    assert all(path.exists() for path in manifest.artifact_paths)


def test_cleanup_refuses_outside_paths(tmp_path: Path):
    from rook.mesh2splat.output_safety import RunManifest, cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    malicious = RunManifest(
        run_id=manifest.run_id,
        run_directory=manifest.run_directory,
        manifest_path=manifest.manifest_path,
        artifact_paths=(outside,),
    )

    result = cleanup_manifest_files(
        malicious,
        preserve_debug_artifacts=False,
    )

    assert result.deleted == []
    assert result.warnings == [
        {
            "code": "cleanup_skipped_outside_run_directory",
            "message": "Cleanup skipped path outside run directory",
            "path": str(outside.resolve(strict=False)),
        }
    ]
    assert outside.read_text(encoding="utf-8") == "outside"


@pytest.mark.skipif(
    not hasattr(os, "symlink"),
    reason="symlink support is unavailable on this platform",
)
def test_cleanup_refuses_symlink_or_reparse_swaps(tmp_path: Path):
    from rook.mesh2splat.output_safety import RunManifest, cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = manifest.run_directory / "capture.glb"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    swapped = RunManifest(
        run_id=manifest.run_id,
        run_directory=manifest.run_directory,
        manifest_path=manifest.manifest_path,
        artifact_paths=(link,),
    )

    result = cleanup_manifest_files(swapped, preserve_debug_artifacts=False)

    assert result.deleted == []
    assert result.warnings == [
        {
            "code": "cleanup_skipped_reparse_point",
            "message": "Cleanup skipped symlink or reparse-point path",
            "path": str(link.resolve(strict=False)),
        }
    ]
    assert link.exists()
    assert outside.read_text(encoding="utf-8") == "outside"


@pytest.mark.skipif(
    not hasattr(os, "symlink"),
    reason="symlink support is unavailable on this platform",
)
def test_manifest_update_refuses_swapped_run_directory_symlink(tmp_path: Path):
    from rook.mesh2splat.output_safety import RunManifest, update_manifest

    manifest = new_manifest(tmp_path)
    outside_directory = tmp_path / "outside-run-target"
    outside_directory.mkdir()
    outside_manifest = outside_directory / "manifest.json"
    outside_manifest.write_text("outside manifest", encoding="utf-8")
    manifest.run_directory.rmdir()
    try:
        os.symlink(outside_directory, manifest.run_directory, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    swapped = RunManifest(
        run_id=manifest.run_id,
        run_directory=manifest.run_directory,
        manifest_path=manifest.manifest_path,
        artifact_paths=manifest.artifact_paths,
        status="updated",
    )

    with pytest.raises(ValueError, match="run directory"):
        update_manifest(swapped)

    assert outside_manifest.read_text(encoding="utf-8") == "outside manifest"


@pytest.mark.skipif(
    not hasattr(os, "symlink"),
    reason="symlink support is unavailable on this platform",
)
def test_cleanup_refuses_swapped_run_directory_symlink(tmp_path: Path):
    from rook.mesh2splat.output_safety import cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    outside_directory = tmp_path / "outside-run-target"
    outside_directory.mkdir()
    outside_file = outside_directory / "capture.glb"
    outside_file.write_bytes(b"outside")
    manifest.run_directory.rmdir()
    try:
        os.symlink(outside_directory, manifest.run_directory, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ValueError, match="run directory"):
        cleanup_manifest_files(manifest, preserve_debug_artifacts=False)

    assert outside_file.read_bytes() == b"outside"


def test_cleanup_does_not_recursively_delete_run_directory(tmp_path: Path):
    from rook.mesh2splat.output_safety import cleanup_manifest_files

    manifest = new_manifest(tmp_path)
    kept = manifest.run_directory / "nested" / "kept.txt"
    kept.parent.mkdir()
    kept.write_text("keep", encoding="utf-8")

    result = cleanup_manifest_files(manifest, preserve_debug_artifacts=False)

    assert result.deleted == []
    assert result.warnings == []
    assert manifest.run_directory.is_dir()
    assert kept.read_text(encoding="utf-8") == "keep"
