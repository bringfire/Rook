# Durable Rhino Script Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build v1 durable Rhino script artifacts with repo-trusted read-only execution, project-local capture, broad discovery, and strict MCP-mediated execution.

**Architecture:** Add a focused Python script-library module under the MCP server that owns artifact discovery, manifest validation, static scanning, trust-anchor verification, capture writes, and library execution wrapping. Wire three MCP tools through `mcp_server/src/rook/server.py`: `script_library_search`, `capture_script_artifact`, and `run_library_script`. Use filesystem artifacts as source of truth, a repo-level lock file as the external trust anchor for executable repo scripts, and treat project-local artifacts as searchable references only.

**Tech Stack:** Python standard library, existing Rook MCP server patterns, `pytest`, existing Rhino `/execute` endpoint, JSON manifests and lock files, no new external dependencies.

---

## Spec Reference

Use `docs/superpowers/specs/2026-05-17-durable-rhino-script-artifacts-design.md` as the controlling design. The invariant to preserve in every task is:

```text
Discovery is broad.
Execution is narrow.
Manifest state is not self-certifying.
```

## File Map

- Create `mcp_server/src/rook/script_library.py`
  - Owns artifact path resolution, manifest loading, schema checks, script hashing, repo lock verification, static scan, search summaries, project-local capture, execution wrapping, output parsing, and policy envelopes.
- Modify `mcp_server/src/rook/server.py`
  - Registers the three MCP tools and dispatches them to `script_library.py`.
- Modify `mcp_server/src/rook/targeting.py`
  - Adds explicit targeting policies so discovery and capture do not require Rhino, while `run_library_script` requires a Rhino target but is treated as read-risk in v1.
- Create `mcp_server/tests/test_script_library_registry.py`
  - Unit tests for manifest validation, discovery, source/state policy, hash freshness, trust lock behavior, static scan behavior, and search refusal reasons.
- Create `mcp_server/tests/test_script_library_mcp.py`
  - MCP-level tests for tool registration, targeting policy, `script_library_search`, `capture_script_artifact`, and `run_library_script`.
- Create `scripts/rook-library/README.md`
  - Documents the repo-shipped durable script artifact layout and lock-file rule.
- Create `scripts/rook-library/rook-library.lock.json`
  - Maintainer-controlled v1 trust anchor for repo-shipped executable artifacts.
- Create `scripts/rook-library/rhino/extract-layers/manifest.json`
  - First read-only validated repo artifact manifest.
- Create `scripts/rook-library/rhino/extract-layers/script.py`
  - First read-only Rhino script that emits structured JSON.

## Policy Decisions For V1

- Repo library root: `scripts/rook-library`.
- Repo artifact path: `scripts/rook-library/<domain>/<script-id>/`.
- Project artifact path: `.rook/scripts/<script-id>/`.
- Project root resolution: MCP callers may pass `project_root`; otherwise project-local intake resolves relative to `Path.cwd()`, not the Rook install root.
- Trust anchor: `scripts/rook-library/rook-library.lock.json`.
- Lock key format: `<source>:<domain>:<id>:<version>`, for example `repo:rhino:extract-layers:0.1.0`.
- Executable v1 policy: `source == "repo"`, `state == "validated"`, `execution == "run_as_is"`, `mutation == "read_only"`, `content_hash` matches the script bytes, the lock file has the same content hash for the key, and the static scan passes for the current script bytes.
- Project-local artifacts are searchable but never executable by `run_library_script` in v1.
- `run_library_script` rejects ambiguous IDs when `source` is omitted and the same ID exists in more than one source.
- `run_library_script` accepts `expected_mutation`, defaulting to `read_only`; v1 rejects anything except `read_only`.
- Library scripts print one JSON object to stdout. `run_library_script` parses stdout, validates against the artifact output schema subset, and treats output-schema failure as `success: false` and `verified: false`.
- Parameters are validated against the artifact `parameters_schema` subset before Rhino execution.

## Task 1: Registry Model, Manifest Validation, And Discovery

**Files:**
- Create: `mcp_server/src/rook/script_library.py`
- Test: `mcp_server/tests/test_script_library_registry.py`

- [ ] **Step 1: Write failing tests for manifest loading and discovery**

Add `mcp_server/tests/test_script_library_registry.py` with these initial tests:

```python
import json
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py -q
```

Expected: failure with `ImportError` or `AttributeError` because `rook.script_library` and `discover_artifacts` do not exist.

- [ ] **Step 3: Implement the registry data model and discovery**

Create `mcp_server/src/rook/script_library.py` with this base implementation:

```python
"""Durable Rhino script artifact registry and execution policy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .runtime_paths import RuntimePaths, resolve_runtime_paths


REPO_LIBRARY_RELATIVE = Path("scripts") / "rook-library"
PROJECT_SCRIPTS_RELATIVE = Path(".rook") / "scripts"
LOCK_FILENAME = "rook-library.lock.json"
SCRIPT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")

REQUIRED_MANIFEST_FIELDS = (
    "id",
    "version",
    "description",
    "state",
    "source",
    "domain",
    "entrypoint",
    "execution",
    "mutation",
    "content_hash",
    "parameters_schema",
    "output_schema",
    "requires",
    "safety",
    "evidence",
)

VALID_STATES = {"captured", "candidate", "validated", "promoted"}
VALID_SOURCES = {"repo", "project"}
VALID_DOMAINS = {"rhino", "grasshopper", "file", "mixed"}
VALID_EXECUTION = {"run_as_is", "adapt_and_run"}
VALID_MUTATION = {"read_only", "mutation"}


@dataclass(frozen=True)
class ScriptArtifact:
    script_id: str
    version: str
    description: str
    source: str
    domain: str
    state: str
    execution: str
    mutation: str
    root: Path
    manifest_path: Path
    entrypoint_path: Path
    manifest: dict[str, Any]
    valid: bool
    validation_errors: list[str] = field(default_factory=list)


def _now_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def default_repo_library_root(runtime_paths: RuntimePaths | None = None) -> Path:
    runtime_paths = runtime_paths or resolve_runtime_paths()
    return runtime_paths.install_root / REPO_LIBRARY_RELATIVE


def default_project_scripts_root(
    project_root: Path | str | None = None,
    runtime_paths: RuntimePaths | None = None,
) -> Path:
    if project_root is not None:
        return Path(project_root).expanduser().resolve() / PROJECT_SCRIPTS_RELATIVE
    return Path.cwd().resolve() / PROJECT_SCRIPTS_RELATIVE


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load_json(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"missing_file:{path.name}"]
    except json.JSONDecodeError as exc:
        return None, [f"invalid_json:{path.name}:{exc.lineno}"]
    if not isinstance(value, dict):
        return None, [f"invalid_json_type:{path.name}"]
    return value, []


def _validate_manifest(manifest: dict[str, Any], expected_source: str | None = None) -> list[str]:
    errors: list[str] = []
    for field_name in REQUIRED_MANIFEST_FIELDS:
        if field_name not in manifest:
            errors.append(f"missing_required_field:{field_name}")

    script_id = manifest.get("id")
    if not isinstance(script_id, str) or not SCRIPT_ID_RE.match(script_id):
        errors.append("invalid_id")

    for field_name in ("version", "description", "entrypoint", "content_hash"):
        if field_name in manifest and not isinstance(manifest[field_name], str):
            errors.append(f"invalid_string_field:{field_name}")

    if manifest.get("state") not in VALID_STATES:
        errors.append("invalid_state")
    if manifest.get("source") not in VALID_SOURCES:
        errors.append("invalid_source")
    if expected_source is not None and manifest.get("source") != expected_source:
        errors.append(f"source_mismatch:{expected_source}")
    if manifest.get("domain") not in VALID_DOMAINS:
        errors.append("invalid_domain")
    if manifest.get("execution") not in VALID_EXECUTION:
        errors.append("invalid_execution")
    if manifest.get("mutation") not in VALID_MUTATION:
        errors.append("invalid_mutation")

    for field_name in ("parameters_schema", "output_schema", "requires", "safety", "evidence"):
        if field_name in manifest and not isinstance(manifest[field_name], dict):
            errors.append(f"invalid_object_field:{field_name}")

    return errors


def _artifact_from_dir(artifact_dir: Path, expected_source: str) -> ScriptArtifact:
    manifest_path = artifact_dir / "manifest.json"
    manifest, errors = _load_json(manifest_path)
    manifest = manifest or {}
    errors.extend(_validate_manifest(manifest, expected_source=expected_source))

    entrypoint = manifest.get("entrypoint", "script.py")
    if isinstance(entrypoint, str):
        entrypoint_path = (artifact_dir / entrypoint).resolve()
        try:
            entrypoint_path.relative_to(artifact_dir.resolve())
        except ValueError:
            errors.append("entrypoint_outside_artifact")
    else:
        entrypoint_path = artifact_dir / "script.py"
    if not entrypoint_path.exists():
        errors.append("missing_entrypoint")

    return ScriptArtifact(
        script_id=str(manifest.get("id", artifact_dir.name)),
        version=str(manifest.get("version", "")),
        description=str(manifest.get("description", "")),
        source=str(manifest.get("source", expected_source)),
        domain=str(manifest.get("domain", "")),
        state=str(manifest.get("state", "")),
        execution=str(manifest.get("execution", "")),
        mutation=str(manifest.get("mutation", "")),
        root=artifact_dir,
        manifest_path=manifest_path,
        entrypoint_path=entrypoint_path,
        manifest=manifest,
        valid=not errors,
        validation_errors=errors,
    )


def discover_artifacts(
    repo_library_root: Path | str | None = None,
    project_scripts_root: Path | str | None = None,
) -> list[ScriptArtifact]:
    artifacts: list[ScriptArtifact] = []

    if repo_library_root is not None:
        repo_root = Path(repo_library_root)
        if repo_root.exists():
            for manifest_path in sorted(repo_root.glob("*/*/manifest.json")):
                artifacts.append(_artifact_from_dir(manifest_path.parent, "repo"))

    if project_scripts_root is not None:
        project_root = Path(project_scripts_root)
        if project_root.exists():
            for manifest_path in sorted(project_root.glob("*/manifest.json")):
                artifacts.append(_artifact_from_dir(manifest_path.parent, "project"))

    return artifacts
```

- [ ] **Step 4: Run registry tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py -q
```

Expected: all tests in `test_script_library_registry.py` pass.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server/src/rook/script_library.py mcp_server/tests/test_script_library_registry.py
git commit -m "feat: add script artifact registry discovery"
```

Expected: commit succeeds.

## Task 2: Static Scan, Trust Anchor, Search Policy, And Refusal Reasons

**Files:**
- Modify: `mcp_server/src/rook/script_library.py`
- Test: `mcp_server/tests/test_script_library_registry.py`

- [ ] **Step 1: Add failing tests for hash, lock, static scan, and search policy**

Append these tests to `mcp_server/tests/test_script_library_registry.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py -q
```

Expected: failure because `hash_text`, `scan_script_text`, and `search_scripts` do not exist.

- [ ] **Step 3: Implement scan, trust lock, executable policy, and search**

Append this implementation to `mcp_server/src/rook/script_library.py` and import `fnmatch` only if the final code uses it:

```python
MAX_SCRIPT_BYTES = 256 * 1024
INVISIBLE_TEXT_RE = re.compile("[\u200b\u200c\u200d\ufeff\u202a-\u202e\u2066-\u2069]")
BLOCKING_UI_RE = re.compile(r"\b(?:rhinoscriptsyntax\.)?Get[A-Z][A-Za-z0-9_]*\s*\(")
FILE_ACCESS_RE = re.compile(r"\b(open|Path|file)\s*\(")
NETWORK_RE = re.compile(r"\b(requests|urllib|socket|httpx)\b")
DANGEROUS_RE = re.compile(r"\b(exec|eval|compile|__import__)\s*\(")
SUBPROCESS_RE = re.compile(r"\b(subprocess|os\.system|popen)\b")


def hash_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def artifact_lock_key(artifact: ScriptArtifact) -> str:
    return f"{artifact.source}:{artifact.domain}:{artifact.script_id}:{artifact.version}"


def load_trust_lock(repo_library_root: Path | str) -> dict[str, Any]:
    lock_path = Path(repo_library_root) / LOCK_FILENAME
    lock, errors = _load_json(lock_path)
    if errors:
        return {"version": 1, "artifacts": {}, "_errors": errors}
    if not isinstance(lock.get("artifacts"), dict):
        lock["_errors"] = ["invalid_lock_artifacts"]
    return lock


def scan_script_text(code: str) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    invisible_match = INVISIBLE_TEXT_RE.search(code)
    if invisible_match:
        findings.append({
            "code": "hidden_invisible_text",
            "severity": "reject",
            "line": str(code.count("\n", 0, invisible_match.start()) + 1),
            "message": "Invisible Unicode control text is not allowed in library scripts.",
        })

    checks = [
        ("blocking_ui", BLOCKING_UI_RE, "Interactive Rhino input calls are not allowed in library execution."),
        ("filesystem_access", FILE_ACCESS_RE, "Filesystem access is not allowed unless declared and approved."),
        ("network_access", NETWORK_RE, "Network access is not allowed in v1 library scripts."),
        ("dynamic_execution", DANGEROUS_RE, "Dynamic Python execution is not allowed in library scripts."),
        ("subprocess", SUBPROCESS_RE, "Subprocess execution is not allowed in library scripts."),
    ]

    for code_name, pattern, message in checks:
        match = pattern.search(code)
        if match:
            line_no = code.count("\n", 0, match.start()) + 1
            findings.append({
                "code": code_name,
                "severity": "reject",
                "line": str(line_no),
                "message": message,
            })

    return {"status": "failed" if findings else "passed", "findings": findings}


def scan_script_file(path: Path) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return {
            "status": "failed",
            "findings": [{"code": "missing_entrypoint", "severity": "reject", "message": "Entrypoint file is missing."}],
        }
    if path.is_symlink():
        findings.append({"code": "symlink_entrypoint", "severity": "reject", "message": "Entrypoint symlinks are not allowed."})
    if stat.st_size > MAX_SCRIPT_BYTES:
        findings.append({"code": "oversized_script", "severity": "reject", "message": "Script exceeds the v1 size limit."})
    data = path.read_bytes()
    if b"\x00" in data:
        findings.append({"code": "binary_or_nul_bytes", "severity": "reject", "message": "Binary or NUL bytes are not allowed."})
        return {"status": "failed", "findings": findings}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        findings.append({"code": "non_utf8_script", "severity": "reject", "message": "Script must be valid UTF-8."})
        return {"status": "failed", "findings": findings}
    text_scan = scan_script_text(text)
    findings.extend(text_scan["findings"])
    return {"status": "failed" if findings else "passed", "findings": findings}


def _manifest_declared_hash(artifact: ScriptArtifact) -> str:
    value = artifact.manifest.get("content_hash")
    return value if isinstance(value, str) else ""


def evaluate_executability(
    artifact: ScriptArtifact,
    repo_library_root: Path | str | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    details: dict[str, Any] = {
        "policy": "v1_repo_validated_read_only",
        "validation_errors": list(artifact.validation_errors),
        "content_hash": None,
        "static_scan_summary": None,
    }

    if not artifact.valid:
        return False, "invalid_manifest", details
    if artifact.source != "repo":
        return False, "project_source_not_executable_in_v1", details
    if artifact.state != "validated":
        return False, f"{artifact.state}_state_not_executable_in_v1", details
    if artifact.execution != "run_as_is":
        return False, "adapt_reference_not_executable", details
    if artifact.mutation != "read_only":
        return False, "mutation_not_executable_in_v1", details

    actual_hash = compute_file_sha256(artifact.entrypoint_path)
    details["content_hash"] = actual_hash
    declared_hash = _manifest_declared_hash(artifact)
    if declared_hash != actual_hash:
        return False, "content_hash_mismatch", details

    if repo_library_root is None:
        repo_library_root = artifact.root.parents[1]
    trust_lock = load_trust_lock(repo_library_root)
    lock_errors = trust_lock.get("_errors")
    if lock_errors:
        details["lock_errors"] = lock_errors
        return False, "missing_trust_anchor", details

    lock_entry = trust_lock.get("artifacts", {}).get(artifact_lock_key(artifact))
    if not isinstance(lock_entry, dict):
        return False, "missing_trust_anchor", details
    if lock_entry.get("content_hash") != actual_hash:
        return False, "trust_anchor_hash_mismatch", details

    scan = scan_script_file(artifact.entrypoint_path)
    details["static_scan_summary"] = {
        "status": scan["status"],
        "content_hash": actual_hash,
        "findings_count": len(scan["findings"]),
    }
    lock_scan = lock_entry.get("static_scan", {})
    if isinstance(lock_scan, dict) and lock_scan.get("content_hash") == actual_hash:
        details["static_scan_summary"]["trust_anchor_scan_status"] = lock_scan.get("status")
    if scan["status"] != "passed":
        details["static_scan_summary"]["findings"] = scan["findings"]
        return False, "failed_static_scan", details

    return True, None, details


def _matches_query(artifact: ScriptArtifact, query: str | None) -> bool:
    if not query:
        return True
    needle = query.strip().lower()
    tags = artifact.manifest.get("tags", [])
    triggers = artifact.manifest.get("trigger_phrases", [])
    haystack = " ".join([
        artifact.script_id,
        artifact.description,
        " ".join(str(tag) for tag in tags if isinstance(tag, str)),
        " ".join(str(trigger) for trigger in triggers if isinstance(trigger, str)),
    ]).lower()
    return needle in haystack


def _artifact_summary(
    artifact: ScriptArtifact,
    repo_library_root: Path | str | None,
) -> dict[str, Any]:
    executable, refusal_reason, details = evaluate_executability(artifact, repo_library_root)
    return {
        "id": artifact.script_id,
        "version": artifact.version,
        "description": artifact.description,
        "source": artifact.source,
        "domain": artifact.domain,
        "state": artifact.state,
        "execution": artifact.execution,
        "mutation": artifact.mutation,
        "tags": artifact.manifest.get("tags", []),
        "trigger_phrases": artifact.manifest.get("trigger_phrases", []),
        "executable": executable,
        "refusal_reason": refusal_reason,
        "content_hash": details.get("content_hash") or artifact.manifest.get("content_hash"),
        "validation_errors": artifact.validation_errors,
        "static_scan_summary": details.get("static_scan_summary"),
        "manifest_path": str(artifact.manifest_path),
    }


def search_scripts(
    query: str | None = None,
    source: str | None = None,
    project_root: Path | str | None = None,
    repo_library_root: Path | str | None = None,
    project_scripts_root: Path | str | None = None,
) -> dict[str, Any]:
    if repo_library_root is None:
        repo_library_root = default_repo_library_root()
    if project_scripts_root is None:
        project_scripts_root = default_project_scripts_root(project_root=project_root)
    artifacts = discover_artifacts(repo_library_root=repo_library_root, project_scripts_root=project_scripts_root)
    filtered = [
        artifact
        for artifact in artifacts
        if (source is None or artifact.source == source) and _matches_query(artifact, query)
    ]
    return {
        "success": True,
        "query": query,
        "results": [_artifact_summary(artifact, repo_library_root) for artifact in filtered],
    }
```

- [ ] **Step 4: Run the focused registry tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py -q
```

Expected: all registry tests pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add mcp_server/src/rook/script_library.py mcp_server/tests/test_script_library_registry.py
git commit -m "feat: enforce script library trust policy"
```

Expected: commit succeeds.

## Task 3: Project-Local Capture

**Files:**
- Modify: `mcp_server/src/rook/script_library.py`
- Test: `mcp_server/tests/test_script_library_registry.py`

- [ ] **Step 1: Add failing capture tests**

Append these tests to `mcp_server/tests/test_script_library_registry.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py -q
```

Expected: failure because `capture_script_artifact` does not exist.

- [ ] **Step 3: Implement capture writes**

Append these helpers to `mcp_server/src/rook/script_library.py`:

```python
def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def capture_script_artifact(
    script_id: str,
    script_source: str,
    description: str,
    domain: str = "rhino",
    observed_inputs: dict[str, Any] | None = None,
    observed_output: Any | None = None,
    session_id: str | None = None,
    notes: str | None = None,
    mutation: str = "read_only",
    project_root: Path | str | None = None,
    project_scripts_root: Path | str | None = None,
) -> dict[str, Any]:
    if not isinstance(script_id, str) or not SCRIPT_ID_RE.match(script_id):
        return {"success": False, "refusal_reason": "invalid_id"}
    if not isinstance(script_source, str) or not script_source.strip():
        return {"success": False, "refusal_reason": "missing_script_source"}
    if not isinstance(description, str) or not description.strip():
        return {"success": False, "refusal_reason": "missing_description"}
    if domain not in VALID_DOMAINS:
        return {"success": False, "refusal_reason": "invalid_domain"}
    if mutation not in VALID_MUTATION:
        return {"success": False, "refusal_reason": "invalid_mutation"}

    project_scripts_root = (
        Path(project_scripts_root)
        if project_scripts_root is not None
        else default_project_scripts_root(project_root=project_root)
    )
    artifact_dir = project_scripts_root / script_id
    script_path = artifact_dir / "script.py"
    manifest_path = artifact_dir / "manifest.json"
    evidence_path = artifact_dir / "evidence.json"
    findings_path = artifact_dir / "findings.json"

    if artifact_dir.exists():
        return {
            "success": False,
            "id": script_id,
            "artifact_dir": str(artifact_dir),
            "refusal_reason": "artifact_already_exists",
        }
    try:
        artifact_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return {
            "success": False,
            "id": script_id,
            "artifact_dir": str(artifact_dir),
            "refusal_reason": "artifact_already_exists",
        }
    _atomic_write_text(script_path, script_source)
    script_hash = compute_file_sha256(script_path)
    scan = scan_script_text(script_source)

    manifest = {
        "id": script_id,
        "version": "0.1.0",
        "description": description.strip(),
        "tags": [],
        "trigger_phrases": [],
        "state": "captured",
        "source": "project",
        "domain": domain,
        "entrypoint": "script.py",
        "execution": "adapt_and_run",
        "mutation": mutation,
        "content_hash": script_hash,
        "parameters_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "output_schema": {},
        "requires": {"rhino": "8", "rook_capabilities": ["rhino_execute"]},
        "safety": {
            "static_scan": scan["status"],
            "blocking_ui": "present" if any(f["code"] == "blocking_ui" for f in scan["findings"]) else "none",
            "network": "present" if any(f["code"] == "network_access" for f in scan["findings"]) else "none",
            "filesystem": "present" if any(f["code"] == "filesystem_access" for f in scan["findings"]) else "none",
        },
        "evidence": {
            "captured_at": _now_iso_date(),
            "validation_method": "captured_session",
        },
    }
    evidence = {
        "session_id": session_id,
        "observed_inputs": observed_inputs or {},
        "observed_output": observed_output,
        "notes": notes or "",
        "captured_at": _now_iso_date(),
    }
    findings = {"static_scan": scan, "content_hash": script_hash}

    _atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _atomic_write_text(evidence_path, json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    _atomic_write_text(findings_path, json.dumps(findings, indent=2, sort_keys=True) + "\n")

    artifact = _artifact_from_dir(artifact_dir, "project")
    executable, refusal_reason, _details = evaluate_executability(artifact)
    return {
        "success": True,
        "id": script_id,
        "artifact_dir": str(artifact_dir),
        "state": "captured",
        "source": "project",
        "content_hash": script_hash,
        "static_scan_summary": {
            "status": scan["status"],
            "findings_count": len(scan["findings"]),
        },
        "executable": executable,
        "refusal_reason": refusal_reason,
    }
```

- [ ] **Step 4: Run capture tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py -q
```

Expected: all registry and capture tests pass.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add mcp_server/src/rook/script_library.py mcp_server/tests/test_script_library_registry.py
git commit -m "feat: capture local script artifacts"
```

Expected: commit succeeds.

## Task 4: MCP Tool Schemas And Search/Capture Dispatch

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_script_library_mcp.py`

- [ ] **Step 1: Add failing MCP tests for search and capture**

Create `mcp_server/tests/test_script_library_mcp.py`:

```python
import json

import pytest

from rook import script_library
from rook import server
from rook import targeting


def _decode_response(response):
    text = response[0].text
    if text.startswith("Error: "):
        return json.loads(text[len("Error: "):])
    return json.loads(text)


@pytest.mark.asyncio
async def test_script_library_search_tool_returns_executable_and_refusal_reason(monkeypatch):
    def fake_search_scripts(**kwargs):
        return {
            "success": True,
            "query": kwargs.get("query"),
            "results": [
                {
                    "id": "extract-layers",
                    "version": "0.1.0",
                    "description": "Extract layer names.",
                    "source": "repo",
                    "domain": "rhino",
                    "state": "validated",
                    "execution": "run_as_is",
                    "mutation": "read_only",
                    "executable": True,
                    "refusal_reason": None,
                },
                {
                    "id": "captured-audit",
                    "version": "0.1.0",
                    "description": "Captured audit.",
                    "source": "project",
                    "domain": "rhino",
                    "state": "captured",
                    "execution": "adapt_and_run",
                    "mutation": "read_only",
                    "executable": False,
                    "refusal_reason": "project_source_not_executable_in_v1",
                },
            ],
        }

    monkeypatch.setattr(script_library, "search_scripts", fake_search_scripts)

    response = await server.call_tool("script_library_search", {"query": "layers"})
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["results"][0]["executable"] is True
    assert payload["results"][1]["refusal_reason"] == "project_source_not_executable_in_v1"


@pytest.mark.asyncio
async def test_capture_script_artifact_tool_writes_captured_artifact(monkeypatch, tmp_path):
    captured = {}

    def fake_capture_script_artifact(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "id": kwargs["script_id"],
            "state": "captured",
            "source": "project",
            "executable": False,
            "refusal_reason": "project_source_not_executable_in_v1",
        }

    monkeypatch.setattr(script_library, "capture_script_artifact", fake_capture_script_artifact)

    response = await server.call_tool(
        "capture_script_artifact",
        {
            "id": "audit-layer-names",
            "script_source": "print('{}')\n",
            "description": "Captured layer audit.",
            "session_id": "session-123",
        },
    )
    payload = _decode_response(response)

    assert payload["success"] is True
    assert captured["script_id"] == "audit-layer-names"
    assert captured["script_source"] == "print('{}')\n"
    assert captured["session_id"] == "session-123"


def test_script_library_tools_have_explicit_targeting_policy():
    assert targeting.policy_for_tool("script_library_search") == targeting.RhinoToolPolicy(False, "read")
    assert targeting.policy_for_tool("capture_script_artifact") == targeting.RhinoToolPolicy(False, "mutate")
    assert targeting.policy_for_tool("run_library_script") == targeting.RhinoToolPolicy(True, "read")
```

- [ ] **Step 2: Run MCP tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_mcp.py -q
```

Expected: failure because the MCP tools are not registered or dispatched.

- [ ] **Step 3: Add MCP tool definitions**

Modify `mcp_server/src/rook/server.py` near the existing Rhino tool definitions, close to `rhino_execute`, and add three `Tool(...)` entries:

```python
        Tool(
            name="script_library_search",
            description=(
                "Search durable script artifacts across the repo library and project-local intake. "
                "Discovery is broad; results include executable and refusal_reason fields."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search text."},
                    "project_root": {
                        "type": "string",
                        "description": "Optional user project root for .rook/scripts discovery. Defaults to the MCP process working directory.",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["repo", "project"],
                        "description": "Optional source filter.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="capture_script_artifact",
            description=(
                "Capture a Rhino script as a project-local .rook/scripts artifact in captured state. "
                "Captured artifacts are searchable references and are not executable by run_library_script in v1."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Stable lowercase script id."},
                    "script_source": {"type": "string", "description": "Python script body to capture."},
                    "description": {"type": "string", "description": "Human-readable description."},
                    "domain": {
                        "type": "string",
                        "enum": ["rhino", "grasshopper", "file", "mixed"],
                        "description": "Artifact domain. Defaults to rhino.",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Optional user project root for .rook/scripts capture. Defaults to the MCP process working directory.",
                    },
                    "observed_inputs": {"type": "object", "description": "Observed inputs from the session."},
                    "observed_output": {"description": "Observed script output from the session."},
                    "session_id": {"type": "string", "description": "Source session identifier."},
                    "notes": {"type": "string", "description": "Agent notes and adaptation points."},
                    "mutation": {
                        "type": "string",
                        "enum": ["read_only", "mutation"],
                        "description": "Observed mutation level. Defaults to read_only.",
                    },
                },
                "required": ["id", "script_source", "description"],
            },
        ),
        Tool(
            name="run_library_script",
            description=(
                "Execute a validated repo-shipped durable script by stable id. "
                "V1 executes read-only repo artifacts only and refuses project-local, candidate, captured, or mutation scripts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Stable script id."},
                    "source": {
                        "type": "string",
                        "enum": ["repo", "project"],
                        "description": "Source to resolve. Required when an id exists in multiple sources.",
                    },
                    "parameters": {"type": "object", "description": "Script parameters. Defaults to empty object."},
                    "project_root": {
                        "type": "string",
                        "description": "Optional user project root used only for project-source ambiguity checks.",
                    },
                    "expected_mutation": {
                        "type": "string",
                        "enum": ["read_only", "mutation"],
                        "description": "Caller mutation consent. Defaults to read_only. V1 refuses mutation.",
                    },
                },
                "required": ["id"],
            },
        ),
```

- [ ] **Step 4: Add targeting policy entries**

Modify `mcp_server/src/rook/targeting.py`:

Add these names to `_ALL_KNOWN_TOOLS`:

```python
    "capture_script_artifact",
    "run_library_script",
    "script_library_search",
```

Add this name to `_RHINO_INDEPENDENT_READ_TOOLS`:

```python
    "script_library_search",
```

Add this name to `_RHINO_INDEPENDENT_MUTATE_TOOLS` because capture writes project-local files but does not require Rhino:

```python
    "capture_script_artifact",
```

Add this name to `_RHINO_READ_TOOLS` because v1 execution requires Rhino but is read-only by policy:

```python
    "run_library_script",
```

- [ ] **Step 5: Add MCP dispatch for search and capture**

Add `from . import script_library` near the top-level imports in `mcp_server/src/rook/server.py`.

Add these cases in `_call_tool_dispatch`, near `case "rhino_execute"`:

```python
        case "script_library_search":
            payload = script_library.search_scripts(
                query=arguments.get("query") if arguments else None,
                source=arguments.get("source") if arguments else None,
                project_root=arguments.get("project_root") if arguments else None,
            )
            result = {"success": payload.get("success", True), "data": payload}

        case "capture_script_artifact":
            payload = script_library.capture_script_artifact(
                script_id=arguments.get("id", "") if arguments else "",
                script_source=arguments.get("script_source", "") if arguments else "",
                description=arguments.get("description", "") if arguments else "",
                domain=arguments.get("domain", "rhino") if arguments else "rhino",
                project_root=arguments.get("project_root") if arguments else None,
                observed_inputs=arguments.get("observed_inputs") if arguments else None,
                observed_output=arguments.get("observed_output") if arguments else None,
                session_id=arguments.get("session_id") if arguments else None,
                notes=arguments.get("notes") if arguments else None,
                mutation=arguments.get("mutation", "read_only") if arguments else "read_only",
            )
            result = {"success": payload.get("success", False), "data": payload}
```

- [ ] **Step 6: Run MCP search/capture tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_mcp.py -q
```

Expected: search and capture MCP tests pass; any run-library test is not present yet.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/targeting.py mcp_server/tests/test_script_library_mcp.py
git commit -m "feat: expose script artifact search and capture tools"
```

Expected: commit succeeds.

## Task 5: `run_library_script` Resolution, Execution, Output Validation, And Runtime Envelope

**Files:**
- Modify: `mcp_server/src/rook/script_library.py`
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_script_library_mcp.py`

- [ ] **Step 1: Add failing run-library tests**

Append these tests to `mcp_server/tests/test_script_library_mcp.py`:

```python
def _write_repo_executable(repo_root, script_id="extract-layers", code="print('{\"layers\": []}')\n"):
    artifact_dir = repo_root / "rhino" / script_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "script.py").write_text(code, encoding="utf-8")
    script_hash = script_library.compute_file_sha256(artifact_dir / "script.py")
    manifest = {
        "id": script_id,
        "version": "0.1.0",
        "description": "Extract layer names.",
        "tags": ["layers"],
        "trigger_phrases": ["list layers"],
        "state": "validated",
        "source": "repo",
        "domain": "rhino",
        "entrypoint": "script.py",
        "execution": "run_as_is",
        "mutation": "read_only",
        "content_hash": script_hash,
        "parameters_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "output_schema": {
            "type": "object",
            "required": ["layers"],
            "properties": {"layers": {"type": "array"}},
        },
        "requires": {"rhino": "8", "rook_capabilities": ["rhino_execute"]},
        "safety": {"static_scan": "passed", "blocking_ui": "none", "network": "none", "filesystem": "none"},
        "evidence": {"validated_at": "2026-05-17", "validation_method": "bootstrap_unit_fixture"},
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    lock = {
        "version": 1,
        "artifacts": {
            f"repo:rhino:{script_id}:0.1.0": {
                "content_hash": script_hash,
                "static_scan": {"status": "passed", "content_hash": script_hash},
            }
        },
    }
    (repo_root / "rook-library.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return artifact_dir


@pytest.mark.asyncio
async def test_run_library_script_refuses_project_source(monkeypatch, tmp_path):
    project_root = tmp_path / ".rook" / "scripts"
    artifact_dir = project_root / "captured-audit"
    artifact_dir.mkdir(parents=True)
    manifest = {
        "id": "captured-audit",
        "version": "0.1.0",
        "description": "Captured audit.",
        "state": "captured",
        "source": "project",
        "domain": "rhino",
        "entrypoint": "script.py",
        "execution": "adapt_and_run",
        "mutation": "read_only",
        "content_hash": "sha256:captured",
        "parameters_schema": {},
        "output_schema": {},
        "requires": {},
        "safety": {},
        "evidence": {},
    }
    (artifact_dir / "script.py").write_text("print('{}')\n", encoding="utf-8")
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("run_library_script must not call Rhino for project artifacts")

    payload = await script_library.run_library_script(
        script_id="captured-audit",
        source="project",
        parameters={},
        expected_mutation="read_only",
        call_rhino_func=fail_call_rhino,
        repo_library_root=tmp_path / "scripts" / "rook-library",
        project_scripts_root=project_root,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "project_source_not_executable_in_v1"


@pytest.mark.asyncio
async def test_run_library_script_executes_repo_validated_read_only_script(monkeypatch, tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    _write_repo_executable(repo_root)
    calls = []

    async def fake_call_rhino(path, method="GET", payload=None, **kwargs):
        calls.append((path, method, payload))
        assert path == "/execute"
        assert method == "POST"
        assert "ROOK_LIBRARY_PARAMETERS" in payload["code"]
        return {
            "success": True,
            "data": {
                "output": "{\"layers\": []}\\n",
                "stderr": "",
                "objectsCreated": 0,
                "objectIds": [],
                "objectCount": 3,
            },
        }

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters={},
        expected_mutation="read_only",
        call_rhino_func=fake_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is True
    assert payload["verified"] is True
    assert payload["validated_output"] == {"layers": []}
    assert payload["mutation"] == "read_only"
    assert payload["policy_decision"]["allowed"] is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_run_library_script_validates_parameters_before_execution(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    _write_repo_executable(repo_root)

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("run_library_script must validate parameters before calling Rhino")

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters={"unexpected": True},
        expected_mutation="read_only",
        call_rhino_func=fail_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "parameters_schema_validation_failed"


@pytest.mark.asyncio
async def test_run_library_script_treats_output_schema_failure_as_failed(tmp_path):
    repo_root = tmp_path / "scripts" / "rook-library"
    _write_repo_executable(repo_root)

    async def fake_call_rhino(path, method="GET", payload=None, **kwargs):
        return {"success": True, "data": {"output": "{\"wrong\": []}\\n", "objectsCreated": 0, "objectIds": []}}

    payload = await script_library.run_library_script(
        script_id="extract-layers",
        source="repo",
        parameters={},
        expected_mutation="read_only",
        call_rhino_func=fake_call_rhino,
        repo_library_root=repo_root,
        project_scripts_root=None,
    )

    assert payload["success"] is False
    assert payload["verified"] is False
    assert payload["refusal_reason"] == "output_schema_validation_failed"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_mcp.py -q
```

Expected: failure because `run_library_script` does not exist.

- [ ] **Step 3: Implement artifact resolution, execution wrapper, output parsing, and schema subset validation**

Append this implementation to `mcp_server/src/rook/script_library.py`:

```python
def resolve_artifact(
    script_id: str,
    source: str | None = None,
    repo_library_root: Path | str | None = None,
    project_scripts_root: Path | str | None = None,
) -> tuple[ScriptArtifact | None, str | None]:
    if repo_library_root is None:
        repo_library_root = default_repo_library_root()
    artifacts = discover_artifacts(repo_library_root=repo_library_root, project_scripts_root=project_scripts_root)
    matches = [artifact for artifact in artifacts if artifact.script_id == script_id]
    if source is not None:
        matches = [artifact for artifact in matches if artifact.source == source]
    if not matches:
        return None, "not_found"
    sources = {artifact.source for artifact in matches}
    if source is None and len(sources) > 1:
        return None, "ambiguous_id"
    if len(matches) > 1:
        return None, "ambiguous_id"
    return matches[0], None


def build_execution_code(artifact: ScriptArtifact, parameters: dict[str, Any]) -> str:
    params_json = json.dumps(parameters, sort_keys=True)
    script_body = artifact.entrypoint_path.read_text(encoding="utf-8")
    return (
        "# Rook durable script library execution wrapper\n"
        "import json\n"
        "\n"
        f"ROOK_LIBRARY_PARAMETERS = json.loads({json.dumps(params_json)})\n"
        "ROOK_LIBRARY_CONTEXT = {'script_id': "
        f"{json.dumps(artifact.script_id)}, 'version': {json.dumps(artifact.version)}}\n"
        "\n"
        f"{script_body}"
    )


def parse_library_stdout(output: str) -> tuple[Any | None, str | None]:
    stripped = (output or "").strip()
    if not stripped:
        return None, "empty_output"
    last_line = stripped.splitlines()[-1]
    try:
        return json.loads(last_line), None
    except json.JSONDecodeError:
        return None, "invalid_json_output"


def validate_schema_subset(value: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    if not schema:
        return True, []
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(value, dict):
        errors.append("expected_object")
        return False, errors
    if expected_type == "array" and not isinstance(value, list):
        errors.append("expected_array")
        return False, errors
    if isinstance(value, dict):
        for field_name in schema.get("required", []):
            if field_name not in value:
                errors.append(f"missing_required_output:{field_name}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            for field_name in value:
                if field_name not in properties:
                    errors.append(f"unexpected_property:{field_name}")
        if isinstance(properties, dict):
            for field_name, field_schema in properties.items():
                if field_name in value and isinstance(field_schema, dict):
                    field_type = field_schema.get("type")
                    if field_type == "array" and not isinstance(value[field_name], list):
                        errors.append(f"invalid_output_type:{field_name}:array")
                    if field_type == "object" and not isinstance(value[field_name], dict):
                        errors.append(f"invalid_output_type:{field_name}:object")
                    if field_type == "string" and not isinstance(value[field_name], str):
                        errors.append(f"invalid_output_type:{field_name}:string")
                    if field_type == "number" and not isinstance(value[field_name], (int, float)):
                        errors.append(f"invalid_output_type:{field_name}:number")
                    if field_type == "boolean" and not isinstance(value[field_name], bool):
                        errors.append(f"invalid_output_type:{field_name}:boolean")
    return not errors, errors


async def run_library_script(
    script_id: str,
    source: str | None,
    parameters: dict[str, Any] | None,
    expected_mutation: str,
    call_rhino_func: Callable[..., Awaitable[dict[str, Any]]],
    repo_library_root: Path | str | None = None,
    project_root: Path | str | None = None,
    project_scripts_root: Path | str | None = None,
) -> dict[str, Any]:
    parameters = parameters or {}
    expected_mutation = expected_mutation or "read_only"
    if expected_mutation != "read_only":
        return {
            "success": False,
            "verified": False,
            "script_id": script_id,
            "refusal_reason": "mutation_not_executable_in_v1",
            "policy_decision": {"allowed": False, "reason": "mutation_not_executable_in_v1"},
        }

    artifact, resolution_error = resolve_artifact(
        script_id=script_id,
        source=source,
        repo_library_root=repo_library_root,
        project_scripts_root=project_scripts_root or default_project_scripts_root(project_root=project_root),
    )
    if artifact is None:
        return {
            "success": False,
            "verified": False,
            "script_id": script_id,
            "refusal_reason": resolution_error,
            "policy_decision": {"allowed": False, "reason": resolution_error},
        }

    executable, refusal_reason, details = evaluate_executability(artifact, repo_library_root)
    if not executable:
        return {
            "success": False,
            "verified": False,
            "script_id": artifact.script_id,
            "version": artifact.version,
            "source": artifact.source,
            "content_hash": details.get("content_hash") or artifact.manifest.get("content_hash"),
            "static_scan_summary": details.get("static_scan_summary"),
            "refusal_reason": refusal_reason,
            "policy_decision": {"allowed": False, "reason": refusal_reason},
        }

    parameters_ok, parameter_errors = validate_schema_subset(parameters, artifact.manifest.get("parameters_schema", {}))
    if not parameters_ok:
        return {
            "success": False,
            "verified": False,
            "script_id": artifact.script_id,
            "version": artifact.version,
            "source": artifact.source,
            "content_hash": details.get("content_hash"),
            "mutation": artifact.mutation,
            "policy_decision": {"allowed": False, "reason": "parameters_schema_validation_failed"},
            "static_scan_summary": details.get("static_scan_summary"),
            "refusal_reason": "parameters_schema_validation_failed",
            "schema_errors": parameter_errors,
        }

    execution_code = build_execution_code(artifact, parameters)
    response = await call_rhino_func("/execute", "POST", {"code": execution_code})
    rhino_data = response.get("data", {}) if isinstance(response, dict) else {}
    rhino_success = bool(response.get("success")) if isinstance(response, dict) else False

    output_value, output_error = parse_library_stdout(str(rhino_data.get("output", "")))
    if not rhino_success:
        return {
            "success": False,
            "verified": False,
            "script_id": artifact.script_id,
            "version": artifact.version,
            "source": artifact.source,
            "content_hash": details.get("content_hash"),
            "mutation": artifact.mutation,
            "execution_substrate": "rhino_execute",
            "policy_decision": {"allowed": True, "reason": "repo_validated_read_only"},
            "static_scan_summary": details.get("static_scan_summary"),
            "verification_result": {"objectsCreated": rhino_data.get("objectsCreated")},
            "refusal_reason": "rhino_execute_failed",
            "error": rhino_data.get("error"),
            "stderr": rhino_data.get("stderr"),
        }
    if output_error is not None:
        return {
            "success": False,
            "verified": False,
            "script_id": artifact.script_id,
            "version": artifact.version,
            "source": artifact.source,
            "content_hash": details.get("content_hash"),
            "mutation": artifact.mutation,
            "execution_substrate": "rhino_execute",
            "policy_decision": {"allowed": True, "reason": "repo_validated_read_only"},
            "static_scan_summary": details.get("static_scan_summary"),
            "verification_result": {"objectsCreated": rhino_data.get("objectsCreated")},
            "refusal_reason": output_error,
        }

    schema_ok, schema_errors = validate_schema_subset(output_value, artifact.manifest.get("output_schema", {}))
    objects_created = int(rhino_data.get("objectsCreated") or 0)
    object_ids = rhino_data.get("objectIds") or []
    undeclared_mutation = objects_created != 0 or bool(object_ids)
    if undeclared_mutation:
        return {
            "success": False,
            "verified": False,
            "script_id": artifact.script_id,
            "version": artifact.version,
            "source": artifact.source,
            "content_hash": details.get("content_hash"),
            "mutation": artifact.mutation,
            "execution_substrate": "rhino_execute",
            "policy_decision": {"allowed": True, "reason": "repo_validated_read_only"},
            "static_scan_summary": details.get("static_scan_summary"),
            "verification_result": {"objectsCreated": objects_created, "objectIds": object_ids},
            "refusal_reason": "undeclared_mutation_detected",
        }
    if not schema_ok:
        return {
            "success": False,
            "verified": False,
            "script_id": artifact.script_id,
            "version": artifact.version,
            "source": artifact.source,
            "content_hash": details.get("content_hash"),
            "mutation": artifact.mutation,
            "execution_substrate": "rhino_execute",
            "policy_decision": {"allowed": True, "reason": "repo_validated_read_only"},
            "static_scan_summary": details.get("static_scan_summary"),
            "verification_result": {"objectsCreated": objects_created, "objectIds": object_ids},
            "refusal_reason": "output_schema_validation_failed",
            "schema_errors": schema_errors,
        }

    return {
        "success": True,
        "verified": True,
        "script_id": artifact.script_id,
        "version": artifact.version,
        "source": artifact.source,
        "content_hash": details.get("content_hash"),
        "policy_decision": {"allowed": True, "reason": "repo_validated_read_only"},
        "static_scan_summary": details.get("static_scan_summary"),
        "validated_output": output_value,
        "mutation": artifact.mutation,
        "execution_substrate": "rhino_execute",
        "verification_result": {"objectsCreated": objects_created, "objectIds": object_ids},
        "refusal_reason": None,
    }
```

- [ ] **Step 4: Wire the MCP dispatch case**

Add this case in `_call_tool_dispatch` in `mcp_server/src/rook/server.py`:

```python
        case "run_library_script":
            payload = await script_library.run_library_script(
                script_id=arguments.get("id", "") if arguments else "",
                source=arguments.get("source") if arguments else None,
                parameters=arguments.get("parameters", {}) if arguments else {},
                expected_mutation=arguments.get("expected_mutation", "read_only") if arguments else "read_only",
                call_rhino_func=call_rhino,
                project_root=arguments.get("project_root") if arguments else None,
            )
            result = {"success": payload.get("success", False), "data": payload}
```

- [ ] **Step 5: Run MCP run-library tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_mcp.py -q
```

Expected: all MCP tests pass.

- [ ] **Step 6: Run registry tests again**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py -q
```

Expected: all registry tests pass.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add mcp_server/src/rook/script_library.py mcp_server/src/rook/server.py mcp_server/tests/test_script_library_mcp.py
git commit -m "feat: execute trusted read-only library scripts"
```

Expected: commit succeeds.

## Task 6: Add First Repo-Shipped Validated Script Artifact

**Files:**
- Create: `scripts/rook-library/README.md`
- Create: `scripts/rook-library/rook-library.lock.json`
- Create: `scripts/rook-library/rhino/extract-layers/manifest.json`
- Create: `scripts/rook-library/rhino/extract-layers/script.py`
- Test: `mcp_server/tests/test_script_library_registry.py`

- [ ] **Step 1: Add failing test that the checked-in artifact is executable**

Append this test to `mcp_server/tests/test_script_library_registry.py`:

```python
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
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py::test_checked_in_extract_layers_artifact_is_executable -q
```

Expected: failure because the checked-in artifact does not exist.

- [ ] **Step 3: Create the repo library README**

Create `scripts/rook-library/README.md`:

```markdown
# Rook Script Library

This directory contains repo-shipped durable script artifacts.

V1 execution policy:

- Only repo artifacts with `state: "validated"` are eligible for `run_library_script`.
- Only `mutation: "read_only"` scripts are executable in v1.
- Project-local `.rook/scripts` artifacts are searchable references only.
- Manifest `content_hash` is not self-certifying. Executable artifacts must also match `rook-library.lock.json`.
- Skills and agents must call `run_library_script` for validated library execution.

Artifact layout:

```text
scripts/rook-library/
  rook-library.lock.json
  rhino/
    <script-id>/
      manifest.json
      script.py
```
```

- [ ] **Step 4: Create the `extract-layers` script**

Create `scripts/rook-library/rhino/extract-layers/script.py`:

```python
#! python 3
import json

import scriptcontext as sc


def _layer_to_dict(layer):
    color = layer.Color
    return {
        "name": layer.FullPath,
        "index": layer.Index,
        "id": str(layer.Id),
        "is_visible": bool(layer.IsVisible),
        "is_locked": bool(layer.IsLocked),
        "color": {
            "r": int(color.R),
            "g": int(color.G),
            "b": int(color.B),
        },
    }


layers = [_layer_to_dict(layer) for layer in sc.doc.Layers if layer is not None]
print(json.dumps({"layers": layers}, sort_keys=True))
```

- [ ] **Step 5: Compute the script hash**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -c "from pathlib import Path; from rook.script_library import compute_file_sha256; print(compute_file_sha256(Path('scripts/rook-library/rhino/extract-layers/script.py')))"
```

Expected: one line starting with `sha256:`. Use that exact value in both the manifest and lock file in the next step.

- [ ] **Step 6: Create manifest and lock file with the computed hash**

Run this generation command from the repo root:

```powershell
$env:PYTHONPATH='mcp_server/src'; python -c "import json; from pathlib import Path; from rook.script_library import compute_file_sha256; script=Path('scripts/rook-library/rhino/extract-layers/script.py'); h=compute_file_sha256(script); manifest={'content_hash': h, 'description': 'Extract layer names, ids, visibility, lock state, and display colors from the active Rhino document.', 'domain': 'rhino', 'entrypoint': 'script.py', 'evidence': {'validated_at': '2026-05-17', 'validation_method': 'bootstrap_unit_fixture'}, 'execution': 'run_as_is', 'id': 'extract-layers', 'mutation': 'read_only', 'output_schema': {'properties': {'layers': {'type': 'array'}}, 'required': ['layers'], 'type': 'object'}, 'parameters_schema': {'additionalProperties': False, 'properties': {}, 'type': 'object'}, 'requires': {'rhino': '8', 'rook_capabilities': ['rhino_execute']}, 'safety': {'blocking_ui': 'none', 'filesystem': 'none', 'network': 'none', 'static_scan': 'passed'}, 'source': 'repo', 'state': 'validated', 'tags': ['layers', 'audit', 'extract'], 'trigger_phrases': ['list layers', 'extract layers', 'audit layer names'], 'version': '0.1.0'}; lock={'artifacts': {'repo:rhino:extract-layers:0.1.0': {'content_hash': h, 'static_scan': {'content_hash': h, 'status': 'passed'}}}, 'version': 1}; Path('scripts/rook-library/rhino/extract-layers/manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8'); Path('scripts/rook-library/rook-library.lock.json').write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n', encoding='utf-8'); print(h)"
```

Expected: the command prints one `sha256:` value and writes both JSON files using that exact value.

- [ ] **Step 7: Run the checked-in artifact test**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py::test_checked_in_extract_layers_artifact_is_executable -q
```

Expected: the test passes.

- [ ] **Step 8: Run all script-library tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py mcp_server/tests/test_script_library_mcp.py -q
```

Expected: all script-library tests pass.

- [ ] **Step 9: Commit Task 6**

Run:

```powershell
git add scripts/rook-library mcp_server/tests/test_script_library_registry.py
git commit -m "feat: add extract layers library script"
```

Expected: commit succeeds.

## Task 7: Existing Safety Regression Coverage And Final Verification

**Files:**
- No new files unless the previous tasks reveal import ordering or formatting defects.

- [ ] **Step 1: Run direct execute safety regression tests**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_server_execute_safety.py -q
```

Expected: all tests pass. This confirms the existing `rhino_execute` blocking-input guard still works.

- [ ] **Step 2: Run contract hardening regression tests that exercise MCP dispatch patterns**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_server_contract_hardening.py -q
```

Expected: all tests pass. If this file is slow on the machine, keep the output and record the elapsed time in the final implementation note.

- [ ] **Step 3: Run all focused script-library tests together**

Run:

```powershell
$env:PYTHONPATH='mcp_server/src'; pytest mcp_server/tests/test_script_library_registry.py mcp_server/tests/test_script_library_mcp.py mcp_server/tests/test_server_execute_safety.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Verify no plan-only marker strings remain in runtime files**

Run:

```powershell
rg -n "test-manifest-value" mcp_server/src/rook/script_library.py mcp_server/src/rook/server.py mcp_server/tests scripts/rook-library
```

Expected: no output. If the registry tests contain intentionally synthetic hash strings, restrict the search to runtime files and checked-in artifacts:

```powershell
rg -n "test-manifest-value" mcp_server/src/rook/script_library.py mcp_server/src/rook/server.py scripts/rook-library
```

Expected: no output.

- [ ] **Step 5: Check git status**

Run:

```powershell
git status --short
```

Expected: no uncommitted files if every task commit succeeded.

## Implementation Notes

- Do not modify `.vcxproj` or `.vcxproj.filters`; this plan is Python MCP and docs only.
- Do not add external dependencies. The schema validator is intentionally a small JSON-schema subset for v1 output verification.
- Do not route validated library execution by reading script files in an agent and piping them to `rhino_execute`. The MCP path must be `run_library_script`.
- `capture_script_artifact` is intentionally permissive: static-scan findings are recorded, not used to block capture.
- `capture_script_artifact` refuses existing project-local ids with `artifact_already_exists`; replacement and versioning are future explicit workflows, not v1 silent overwrite behavior.
- `run_library_script` is intentionally strict: project source, captured state, candidate state, stale hash, missing lock entry, failed scan, non-read-only mutation, bad stdout JSON, and output-schema failure all return `success: false`.
- Structural script checks are part of execution-time policy: entrypoint traversal is invalid manifest state; symlink entrypoints, oversized files, binary/NUL bytes, non-UTF-8 scripts, and hidden Unicode control text are reject findings.
- The first artifact uses `scriptcontext` instead of `rhinoscriptsyntax.Get*` APIs and should remain read-only.
- The first artifact's `validation_method` is `bootstrap_unit_fixture`. Before release/shared promotion, run a live Rhino smoke through `run_library_script` and update the evidence to `live_smoke`; do not treat bootstrap fixture evidence as the long-term validation bar.

## Self-Review

- Spec coverage: the plan covers filesystem source of truth, broad search, explicit capture without silent overwrite, repo trust anchor, required manifest metadata, source enum, required schemas, parameter validation, hash verification, static scan freshness, structural scan rejects, targeting policy, project-local refusal, read-only-only execution, runtime envelopes, output validation, and MCP-mediated execution.
- Knowledge indexing: v1 search uses filesystem metadata directly. This keeps the knowledge store advisory by not making it an execution authority. A separate indexing job can consume the same manifest summaries after the execution substrate lands.
- Marker scan: runtime files and checked-in artifact files are verified in Task 7. Manifest and lock files are generated from the computed script hash so the executable artifact never contains a synthetic hash string.
- Type consistency: the module API names used by tests and server dispatch are `discover_artifacts`, `compute_file_sha256`, `hash_text`, `scan_script_text`, `search_scripts`, `capture_script_artifact`, and `run_library_script`.
