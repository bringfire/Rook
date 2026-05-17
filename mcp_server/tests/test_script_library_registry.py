import json
from pathlib import Path

from rook import script_library


def _write_artifact(root: Path, domain: str, script_id: str, manifest: dict, code: str = "print('{}')\n") -> Path:
    artifact_dir = root / domain / script_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "script.py").write_text(code, encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return artifact_dir


def _manifest(script_id: str = "extract-layers", **overrides) -> dict:
    base = {
        "id": script_id,
        "version": "0.1.0",
        "description": "Extract layer names and properties from the active Rhino document.",
        "tags": ["layers", "audit"],
        "trigger_phrases": ["list layers", "extract layers"],
        "state": "validated",
        "source": "repo",
        "domain": "rhino",
        "entrypoint": "script.py",
        "execution": "run_as_is",
        "mutation": "read_only",
        "content_hash": "sha256:test-manifest-value",
        "parameters_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "output_schema": {
            "type": "object",
            "required": ["layers"],
            "properties": {"layers": {"type": "array"}},
        },
        "requires": {"rhino": "8", "rook_capabilities": ["rhino_execute"]},
        "safety": {
            "static_scan": "passed",
            "blocking_ui": "none",
            "network": "none",
            "filesystem": "none",
        },
        "evidence": {"validated_at": "2026-05-17", "validation_method": "bootstrap_unit_fixture"},
    }
    base.update(overrides)
    return base


def test_discover_repo_artifact_loads_required_manifest_fields(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    manifest = _manifest()
    _write_artifact(repo_root, "rhino", "extract-layers", manifest)

    artifacts = script_library.discover_artifacts(repo_library_root=repo_root, project_scripts_root=None)

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.script_id == "extract-layers"
    assert artifact.source == "repo"
    assert artifact.domain == "rhino"
    assert artifact.description == "Extract layer names and properties from the active Rhino document."
    assert artifact.entrypoint_path == repo_root / "rhino" / "extract-layers" / "script.py"


def test_missing_required_manifest_field_is_reported(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    manifest = _manifest()
    del manifest["description"]
    _write_artifact(repo_root, "rhino", "extract-layers", manifest)

    artifacts = script_library.discover_artifacts(repo_library_root=repo_root, project_scripts_root=None)

    assert len(artifacts) == 1
    assert artifacts[0].valid is False
    assert "missing_required_field:description" in artifacts[0].validation_errors


def test_project_artifact_discovery_uses_project_source(tmp_path):
    project_root = tmp_path / ".rook" / "scripts"
    artifact_dir = project_root / "captured-audit"
    artifact_dir.mkdir(parents=True)
    manifest = _manifest(
        script_id="captured-audit",
        state="captured",
        source="project",
        content_hash="sha256:project-audit",
    )
    (artifact_dir / "script.py").write_text("print('{}')\n", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    artifacts = script_library.discover_artifacts(repo_library_root=None, project_scripts_root=project_root)

    assert len(artifacts) == 1
    assert artifacts[0].script_id == "captured-audit"
    assert artifacts[0].source == "project"
    assert artifacts[0].domain == "rhino"


def test_default_project_scripts_root_uses_current_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert script_library.default_project_scripts_root() == tmp_path / ".rook" / "scripts"
