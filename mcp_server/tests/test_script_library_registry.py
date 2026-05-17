import json
from pathlib import Path

from rook import script_library


def _write_artifact(root: Path, domain: str, script_id: str, manifest: dict, code: str = "print('{}')\n") -> Path:
    artifact_dir = root / domain / script_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "script.py").write_text(code, encoding="utf-8", newline="\n")
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


def test_compute_file_sha256_uses_current_script_bytes(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("print('first')\n", encoding="utf-8")
    first_hash = script_library.compute_file_sha256(script)
    script.write_text("print('second')\n", encoding="utf-8")
    second_hash = script_library.compute_file_sha256(script)

    assert first_hash.startswith("sha256:")
    assert second_hash.startswith("sha256:")
    assert first_hash != second_hash


def test_static_scan_rejects_blocking_rhinoscriptsyntax_get_call():
    scan = script_library.scan_script_text("import rhinoscriptsyntax as rs\nrs.GetPoint('pick')\n")

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "blocking_ui"
    assert scan["findings"][0]["severity"] == "reject"


def test_structural_scan_rejects_binary_script_bytes(tmp_path):
    script = tmp_path / "script.py"
    script.write_bytes(b"print('ok')\x00\n")

    scan = script_library.scan_script_file(script)

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "binary_or_nul_bytes"
    assert scan["findings"][0]["severity"] == "reject"


def test_structural_scan_rejects_hidden_invisible_text(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("print('ok')\u200b\n", encoding="utf-8")

    scan = script_library.scan_script_file(script)

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "hidden_invisible_text"
    assert scan["findings"][0]["severity"] == "reject"


def test_entrypoint_path_traversal_is_not_executable(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    code = "print('{\"layers\": []}')\n"
    script_hash = script_library.hash_text(code)
    manifest = _manifest(content_hash=script_hash, entrypoint="../outside.py")
    _write_artifact(repo_root, "rhino", "extract-layers", manifest, code)
    (repo_root / "rhino" / "outside.py").write_text(code, encoding="utf-8")

    search = script_library.search_scripts(query="layers", repo_library_root=repo_root, project_scripts_root=None)

    assert search["results"][0]["executable"] is False
    assert search["results"][0]["refusal_reason"] == "invalid_manifest"


def test_repo_validated_script_requires_matching_lock_hash(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    code = "print('{\"layers\": []}')\n"
    script_hash = script_library.hash_text(code)
    manifest = _manifest(content_hash=script_hash)
    _write_artifact(repo_root, "rhino", "extract-layers", manifest, code)

    search = script_library.search_scripts(query="layers", repo_library_root=repo_root, project_scripts_root=None)

    assert search["results"][0]["executable"] is False
    assert search["results"][0]["refusal_reason"] == "missing_trust_anchor"


def test_repo_validated_script_is_executable_when_manifest_lock_hash_and_scan_match(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    code = "print('{\"layers\": []}')\n"
    script_hash = script_library.hash_text(code)
    manifest = _manifest(content_hash=script_hash)
    _write_artifact(repo_root, "rhino", "extract-layers", manifest, code)
    lock = {
        "version": 1,
        "artifacts": {
            "repo:rhino:extract-layers:0.1.0": {
                "content_hash": script_hash,
                "static_scan": {"status": "passed", "content_hash": script_hash},
            }
        },
    }
    (repo_root / "rook-library.lock.json").write_text(json.dumps(lock), encoding="utf-8")

    search = script_library.search_scripts(query="layers", repo_library_root=repo_root, project_scripts_root=None)

    assert search["results"][0]["executable"] is True
    assert search["results"][0]["refusal_reason"] is None
    assert search["results"][0]["content_hash"] == script_hash


def test_project_candidate_is_searchable_but_not_executable(tmp_path):
    project_root = tmp_path / ".rook" / "scripts"
    artifact_dir = project_root / "captured-audit"
    artifact_dir.mkdir(parents=True)
    manifest = _manifest(
        script_id="captured-audit",
        state="candidate",
        source="project",
        content_hash="sha256:project",
    )
    (artifact_dir / "script.py").write_text("print('{\"layers\": []}')\n", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    search = script_library.search_scripts(query="audit", repo_library_root=None, project_scripts_root=project_root)

    assert search["results"][0]["source"] == "project"
    assert search["results"][0]["executable"] is False
    assert search["results"][0]["refusal_reason"] == "project_source_not_executable_in_v1"


def test_capture_script_artifact_writes_project_captured_manifest_and_evidence(tmp_path):
    project_scripts_root = tmp_path / ".rook" / "scripts"
    result = script_library.capture_script_artifact(
        script_id="audit-layer-names",
        script_source="print('{\"layers\": []}')\n",
        description="Captured script that audited layer names.",
        domain="rhino",
        observed_inputs={"prompt": "audit layer names"},
        observed_output={"layers": []},
        session_id="session-123",
        notes="Works on the reference project and should be parameterized before validation.",
        mutation="read_only",
        project_scripts_root=project_scripts_root,
    )

    assert result["success"] is True
    artifact_dir = project_scripts_root / "audit-layer-names"
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((artifact_dir / "evidence.json").read_text(encoding="utf-8"))
    script_hash = script_library.compute_file_sha256(artifact_dir / "script.py")

    assert manifest["state"] == "captured"
    assert manifest["source"] == "project"
    assert manifest["content_hash"] == script_hash
    assert evidence["session_id"] == "session-123"
    assert evidence["observed_output"] == {"layers": []}
    assert result["executable"] is False
    assert result["refusal_reason"] == "project_source_not_executable_in_v1"


def test_capture_rejects_invalid_script_id(tmp_path):
    result = script_library.capture_script_artifact(
        script_id="../bad",
        script_source="print('{}')\n",
        description="Invalid id.",
        project_scripts_root=tmp_path / ".rook" / "scripts",
    )

    assert result["success"] is False
    assert result["refusal_reason"] == "invalid_id"


def test_capture_records_static_scan_findings_without_blocking_capture(tmp_path):
    project_scripts_root = tmp_path / ".rook" / "scripts"
    result = script_library.capture_script_artifact(
        script_id="interactive-candidate",
        script_source="import rhinoscriptsyntax as rs\nrs.GetPoint('pick')\n",
        description="Captured interactive script.",
        project_scripts_root=project_scripts_root,
    )

    findings = json.loads((project_scripts_root / "interactive-candidate" / "findings.json").read_text(encoding="utf-8"))
    assert result["success"] is True
    assert findings["static_scan"]["status"] == "failed"
    assert findings["static_scan"]["findings"][0]["code"] == "blocking_ui"


def test_capture_refuses_existing_artifact_id_without_overwrite(tmp_path):
    project_scripts_root = tmp_path / ".rook" / "scripts"
    first = script_library.capture_script_artifact(
        script_id="audit-layer-names",
        script_source="print('{\"first\": true}')\n",
        description="First capture.",
        project_scripts_root=project_scripts_root,
    )
    second = script_library.capture_script_artifact(
        script_id="audit-layer-names",
        script_source="print('{\"second\": true}')\n",
        description="Second capture should not overwrite.",
        project_scripts_root=project_scripts_root,
    )

    assert first["success"] is True
    assert second["success"] is False
    assert second["refusal_reason"] == "artifact_already_exists"
    assert (project_scripts_root / "audit-layer-names" / "script.py").read_text(encoding="utf-8") == "print('{\"first\": true}')\n"
