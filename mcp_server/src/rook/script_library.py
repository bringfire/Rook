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
