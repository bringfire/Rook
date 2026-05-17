"""Durable Rhino script artifact registry and execution policy."""

from __future__ import annotations

import ast
import hashlib
import json
import os
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

    artifact_root = Path(os.path.abspath(artifact_dir))
    entrypoint = manifest.get("entrypoint", "script.py")
    if isinstance(entrypoint, str):
        # Keep the lexical path for structural checks. Path.resolve() follows
        # symlinks, which would hide an entrypoint symlink before scan time.
        entrypoint_path = Path(os.path.abspath(artifact_dir / entrypoint))
        try:
            entrypoint_path.relative_to(artifact_root)
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

_RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS: frozenset[str] = frozenset({
    "GetBoolean",
    "GetBox",
    "GetColor",
    "GetCurveObject",
    "GetInteger",
    "GetLayer",
    "GetMeshObject",
    "GetObject",
    "GetObjects",
    "GetPoint",
    "GetPoints",
    "GetReal",
    "GetRectangle",
    "GetString",
    "GetSurfaceObject",
})
_NETWORK_MODULES = {"requests", "urllib", "socket", "httpx"}
_OS_SUBPROCESS_CALLS = {"system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"}
_OS_FILESYSTEM_CALLS = {
    "open",
    "remove",
    "unlink",
    "rmdir",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "mkdir",
    "makedirs",
    "chmod",
    "chown",
    "utime",
}
_DYNAMIC_EXECUTION_CALLS = {"exec", "eval", "compile", "__import__"}
_SCRIPTCONTEXT_MUTATION_METHODS = {
    "Add",
    "AddBrep",
    "AddCurve",
    "AddMesh",
    "AddPoint",
    "Delete",
    "Modify",
    "Replace",
    "Transform",
    "Purge",
    "Clear",
    "CommitChanges",
}
_ALLOWED_IMPORTS = {"json", "rhinoscriptsyntax", "scriptcontext"}
_ALLOWED_BUILTIN_CALLS = {"bool", "dict", "int", "len", "list", "print", "str"}
_ALLOWED_JSON_CALLS = {"dumps"}
_ALLOWED_SCRIPTCONTEXT_CHAINS = {
    ("scriptcontext", "doc", "Layers"),
    ("scriptcontext", "doc", "Layers", "__iter__"),
}


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


def _finding(code: str, line: int, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "reject",
        "line": str(line),
        "message": message,
    }


def _attribute_chain(node: ast.AST) -> list[str]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return []


def _mutation_targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    if isinstance(node, ast.AugAssign):
        return [node.target]
    if isinstance(node, ast.Delete):
        return list(node.targets)
    return []


def _target_has_attribute_or_subscript(node: ast.AST) -> bool:
    if isinstance(node, (ast.Attribute, ast.Subscript)):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_target_has_attribute_or_subscript(element) for element in node.elts)
    if isinstance(node, ast.Starred):
        return _target_has_attribute_or_subscript(node.value)
    return False


def _is_allowed_call(chain: list[str], module_aliases: dict[str, str]) -> bool:
    if not chain:
        return False
    if len(chain) == 1 and chain[0] in _ALLOWED_BUILTIN_CALLS:
        return True

    root = chain[0]
    module = module_aliases.get(root, root)
    normalized = tuple([module, *chain[1:]])
    if len(normalized) == 2 and normalized[0] == "json" and normalized[1] in _ALLOWED_JSON_CALLS:
        return True
    if normalized in _ALLOWED_SCRIPTCONTEXT_CHAINS:
        return True
    return False


def _scan_ast_for_rejects(tree: ast.AST) -> list[dict[str, str]]:
    module_aliases: dict[str, str] = {}
    imported_names: dict[str, tuple[str, str]] = {}
    local_functions: set[str] = {
        node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    findings: list[dict[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".", 1)[0]
                local_name = alias.asname or root_module
                module_aliases[local_name] = alias.name
                if root_module not in _ALLOWED_IMPORTS:
                    findings.append(_finding("unsupported_import", getattr(node, "lineno", 1), f"Import '{alias.name}' is not allowed in v1 library scripts."))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root_module = module.split(".", 1)[0]
            if root_module not in _ALLOWED_IMPORTS:
                findings.append(_finding("unsupported_import", getattr(node, "lineno", 1), f"Import from '{module}' is not allowed in v1 library scripts."))
            for alias in node.names:
                imported_names[alias.asname or alias.name] = (module, alias.name)

    for node in ast.walk(tree):
        for target in _mutation_targets(node):
            if _target_has_attribute_or_subscript(target):
                findings.append(_finding(
                    "attribute_or_subscript_mutation",
                    getattr(node, "lineno", 1),
                    "Attribute and subscript assignment/delete targets are not allowed in v1 library scripts.",
                ))

        if not isinstance(node, ast.Call):
            continue
        line_no = getattr(node, "lineno", 1)
        func = node.func
        chain = _attribute_chain(func) if not isinstance(func, ast.Name) else [func.id]
        is_allowed_call = _is_allowed_call(chain, module_aliases)

        if isinstance(func, ast.Name):
            name = func.id
            imported = imported_names.get(name)
            if name in _DYNAMIC_EXECUTION_CALLS:
                findings.append(_finding("dynamic_execution", line_no, "Dynamic Python execution is not allowed in library scripts."))
                continue
            if name == "getattr":
                findings.append(_finding("unsupported_call", line_no, "Dynamic attribute calls are not allowed in v1 library scripts."))
                continue
            if name in {"open", "file", "Path"}:
                findings.append(_finding("filesystem_access", line_no, "Filesystem access is not allowed unless declared and approved."))
                continue
            if name in local_functions:
                continue
            if imported:
                module, original_name = imported
                if module == "rhinoscriptsyntax":
                    if original_name in _RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS:
                        findings.append(_finding("blocking_ui", line_no, "Interactive Rhino input calls are not allowed in library execution."))
                    else:
                        findings.append(_finding("rhino_mutation_or_unsupported", line_no, "rhinoscriptsyntax calls are not allowed in v1 read-only library scripts."))
                elif module == "os":
                    if original_name in _OS_SUBPROCESS_CALLS:
                        findings.append(_finding("subprocess", line_no, "Subprocess execution is not allowed in library scripts."))
                    elif original_name in _OS_FILESYSTEM_CALLS:
                        findings.append(_finding("filesystem_access", line_no, "Filesystem access is not allowed unless declared and approved."))
                elif module == "importlib" and original_name == "import_module":
                    findings.append(_finding("dynamic_execution", line_no, "Dynamic imports are not allowed in library scripts."))
                elif module == "pathlib" and original_name == "Path":
                    findings.append(_finding("filesystem_access", line_no, "Filesystem access is not allowed unless declared and approved."))
            elif not is_allowed_call:
                findings.append(_finding("unsupported_call", line_no, f"Call '{name}()' is not allowed in v1 library scripts."))

        if not chain:
            continue
        root = chain[0]
        module = module_aliases.get(root, root)
        leaf = chain[-1]

        if module == "rhinoscriptsyntax":
            if leaf in _RHINOSCRIPTSYNTAX_INTERACTIVE_CALLS:
                findings.append(_finding("blocking_ui", line_no, "Interactive Rhino input calls are not allowed in library execution."))
            else:
                findings.append(_finding("rhino_mutation_or_unsupported", line_no, "rhinoscriptsyntax calls are not allowed in v1 read-only library scripts."))
        elif module == "scriptcontext":
            if len(chain) >= 4 and chain[1] == "doc" and chain[2] == "Objects":
                findings.append(_finding("rhino_doc_object_mutation", line_no, "sc.doc.Objects calls are not allowed in v1 read-only library scripts."))
            elif len(chain) >= 4 and chain[1] == "doc" and leaf in _SCRIPTCONTEXT_MUTATION_METHODS:
                findings.append(_finding("rhino_doc_mutation", line_no, "Rhino document mutation calls are not allowed in v1 read-only library scripts."))
        elif module == "os":
            if leaf in _OS_SUBPROCESS_CALLS:
                findings.append(_finding("subprocess", line_no, "Subprocess execution is not allowed in library scripts."))
            elif leaf in _OS_FILESYSTEM_CALLS:
                findings.append(_finding("filesystem_access", line_no, "Filesystem access is not allowed unless declared and approved."))
        elif module == "importlib" and leaf == "import_module":
            findings.append(_finding("dynamic_execution", line_no, "Dynamic imports are not allowed in library scripts."))
        elif module.split(".", 1)[0] in _NETWORK_MODULES:
            findings.append(_finding("network_access", line_no, "Network access is not allowed in v1 library scripts."))
        elif not is_allowed_call:
            findings.append(_finding("unsupported_call", line_no, f"Call '{'.'.join(chain)}()' is not allowed in v1 library scripts."))

    return findings


def scan_script_text(code: str) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    invisible_match = INVISIBLE_TEXT_RE.search(code)
    if invisible_match:
        findings.append(_finding(
            "hidden_invisible_text",
            code.count("\n", 0, invisible_match.start()) + 1,
            "Invisible Unicode control text is not allowed in library scripts.",
        ))

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        findings.append(_finding("invalid_python_syntax", exc.lineno or 1, "Library scripts must parse as Python before execution."))
        return {"status": "failed", "findings": findings}

    findings.extend(_scan_ast_for_rejects(tree))

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
        return {"status": "failed", "findings": [{"code": "symlink_entrypoint", "severity": "reject", "message": "Entrypoint symlinks are not allowed."}]}
    if stat.st_size > MAX_SCRIPT_BYTES:
        return {"status": "failed", "findings": [{"code": "oversized_script", "severity": "reject", "message": "Script exceeds the v1 size limit."}]}

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


def _executable_schema_error(artifact: ScriptArtifact) -> str | None:
    parameters_schema = artifact.manifest.get("parameters_schema")
    output_schema = artifact.manifest.get("output_schema")
    if not isinstance(parameters_schema, dict) or not parameters_schema:
        return "invalid_executable_schema"
    if not isinstance(output_schema, dict) or not output_schema:
        return "invalid_executable_schema"
    if parameters_schema.get("type") != "object":
        return "invalid_executable_schema"
    if output_schema.get("type") != "object":
        return "invalid_executable_schema"
    return None


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
    schema_error = _executable_schema_error(artifact)
    if schema_error is not None:
        return False, schema_error, details

    scan = scan_script_file(artifact.entrypoint_path)
    details["static_scan_summary"] = {
        "status": scan["status"],
        "content_hash": None,
        "findings_count": len(scan["findings"]),
    }
    if scan["status"] != "passed":
        details["static_scan_summary"]["findings"] = scan["findings"]
        return False, "failed_static_scan", details

    actual_hash = compute_file_sha256(artifact.entrypoint_path)
    details["content_hash"] = actual_hash
    details["static_scan_summary"]["content_hash"] = actual_hash
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

    lock_scan = lock_entry.get("static_scan", {})
    if isinstance(lock_scan, dict) and lock_scan.get("content_hash") == actual_hash:
        details["static_scan_summary"]["trust_anchor_scan_status"] = lock_scan.get("status")

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
    context_json = json.dumps({"script_id": artifact.script_id, "version": artifact.version}, sort_keys=True)
    script_body = artifact.entrypoint_path.read_text(encoding="utf-8")
    return (
        "# Rook durable script library execution wrapper\n"
        "import json\n"
        "\n"
        f"ROOK_LIBRARY_PARAMETERS = json.loads({json.dumps(params_json)})\n"
        f"ROOK_LIBRARY_CONTEXT = json.loads({json.dumps(context_json)})\n"
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
    if parameters is None:
        parameters = {}
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
