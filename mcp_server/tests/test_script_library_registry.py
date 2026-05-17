import json
from pathlib import Path

import pytest

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


def test_static_scan_rejects_imported_blocking_input_call():
    scan = script_library.scan_script_text("from rhinoscriptsyntax import GetPoint\nGetPoint('pick')\n")

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "blocking_ui"
    assert scan["findings"][0]["severity"] == "reject"


def test_static_scan_rejects_imported_unsafe_calls():
    cases = [
        ("from os import system\nsystem('echo unsafe')\n", "subprocess"),
        ("from os import remove\nremove('model.3dm')\n", "filesystem_access"),
        ("import importlib\nimportlib.import_module('os')\n", "dynamic_execution"),
    ]

    for code, finding_code in cases:
        scan = script_library.scan_script_text(code)
        assert scan["status"] == "failed"
        assert any(finding["code"] == finding_code for finding in scan["findings"])


def test_static_scan_rejects_denylist_bypass_examples():
    cases = [
        ("import Rhino\nRhino.RhinoApp.RunScript('_Line', False)\n", "unsupported_call"),
        ("import pathlib\npathlib.Path('model.3dm').unlink()\n", "unsupported_call"),
        ("import shutil\nshutil.rmtree('folder')\n", "unsupported_import"),
        ("import io\nio.open('file.txt')\n", "unsupported_import"),
        ("import os\ngetattr(os, 'system')('echo unsafe')\n", "unsupported_call"),
    ]

    for code, finding_code in cases:
        scan = script_library.scan_script_text(code)
        assert scan["status"] == "failed"
        assert any(finding["code"] == finding_code for finding in scan["findings"])


def test_static_scan_rejects_obvious_rhino_mutation_call():
    scan = script_library.scan_script_text("import rhinoscriptsyntax as rs\nrs.AddPoint(0, 0, 0)\n")

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "rhino_mutation_or_unsupported"
    assert scan["findings"][0]["severity"] == "reject"


def test_static_scan_rejects_scriptcontext_object_mutation_call():
    scan = script_library.scan_script_text("import scriptcontext as sc\nsc.doc.Objects.Delete(object_id, True)\n")

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "rhino_doc_object_mutation"
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


def test_structural_scan_rejects_internal_symlink_entrypoint(tmp_path):
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    target = artifact_dir / "target.py"
    target.write_text("print('{\"layers\": []}')\n", encoding="utf-8")
    link = artifact_dir / "script.py"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable on this filesystem: {exc}")

    scan = script_library.scan_script_file(link)

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "symlink_entrypoint"
    assert scan["findings"][0]["severity"] == "reject"


def test_structural_scan_does_not_read_rejected_symlink(tmp_path):
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    target = artifact_dir / "target.py"
    target.write_bytes(b"print('target')\x00\n")
    link = artifact_dir / "script.py"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable on this filesystem: {exc}")

    scan = script_library.scan_script_file(link)

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "symlink_entrypoint"
    assert all(finding["code"] != "binary_or_nul_bytes" for finding in scan["findings"])


def test_structural_scan_does_not_read_oversized_script(tmp_path):
    script = tmp_path / "script.py"
    script.write_bytes(b"x" * (script_library.MAX_SCRIPT_BYTES + 1) + b"\x00")

    scan = script_library.scan_script_file(script)

    assert scan["status"] == "failed"
    assert scan["findings"][0]["code"] == "oversized_script"
    assert all(finding["code"] != "binary_or_nul_bytes" for finding in scan["findings"])


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


def test_repo_validated_script_requires_structured_non_empty_schemas(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    code = "print('{\"layers\": []}')\n"
    script_hash = script_library.hash_text(code)
    manifest = _manifest(content_hash=script_hash, parameters_schema={}, output_schema={})
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

    assert search["results"][0]["executable"] is False
    assert search["results"][0]["refusal_reason"] == "invalid_executable_schema"


def test_repo_validated_script_with_rhino_mutation_is_not_executable(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    code = "import rhinoscriptsyntax as rs\nrs.AddPoint(0, 0, 0)\nprint('{\"layers\": []}')\n"
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

    assert search["results"][0]["executable"] is False
    assert search["results"][0]["refusal_reason"] == "failed_static_scan"
    assert search["results"][0]["static_scan_summary"]["findings"][0]["code"] == "rhino_mutation_or_unsupported"


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

    search = script_library.search_scripts(
        query="audit",
        source="project",
        repo_library_root=None,
        project_scripts_root=project_root,
    )

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


def test_checked_in_extract_layers_artifact_is_executable():
    repo_root = Path(__file__).resolve().parents[2] / "scripts" / "rook-library"

    search = script_library.search_scripts(query="layers", repo_library_root=repo_root, project_scripts_root=None)
    matching = [result for result in search["results"] if result["id"] == "extract-layers"]

    assert len(matching) == 1
    assert matching[0]["source"] == "repo"
    assert matching[0]["state"] == "validated"
    assert matching[0]["mutation"] == "read_only"
    assert matching[0]["executable"] is True
    assert matching[0]["refusal_reason"] is None


def test_installer_packages_repo_script_library():
    installer_path = Path(__file__).resolve().parents[2] / "installer" / "RookSetup.iss"
    installer_text = installer_path.read_text(encoding="utf-8")

    assert 'Source: "{#ScriptsDir}\\rook-library\\*"' in installer_text
    assert 'DestDir: "{app}\\scripts\\rook-library"' in installer_text
