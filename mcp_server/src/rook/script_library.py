"""Durable Rhino script artifact registry and execution policy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


MAX_SCRIPT_BYTES = 256 * 1024
INVISIBLE_TEXT_RE = re.compile("[\u200b\u200c\u200d\ufeff\u202a-\u202e\u2066-\u2069]")
BLOCKING_UI_RE = re.compile(r"\b(?:rhinoscriptsyntax|rs)\.Get[A-Z][A-Za-z0-9_]*\s*\(")
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
