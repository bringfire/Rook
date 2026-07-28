from __future__ import annotations

import ast
import base64
import copy
import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
import weakref
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_governed_resolution_archive_evidence as ARCHIVE_EVIDENCE
import lm9b_p_governed_resolution_artifacts as ARTIFACTS
import lm9b_p_governed_resolution_support as SUPPORT
import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as PLANNER_SUPPORT


OBSERVED_COMMIT_SHA = "e81b12cca0eb750a7f3e730d2376085a915d43dd"
OBSERVED_PREFLIGHT_FINGERPRINT = (
    "sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856"
)
OBSERVED_INSTRUMENT_FINGERPRINT = (
    "sha256:0b57f30954c375df34b28ba394f2ef281c09388c209e688586187d8759f26d11"
)
OBSERVED_ATTEMPT_FINGERPRINT = (
    "sha256:bd350d895f0e34a67aa7ebe59e1e8c4b3b5b3f4e715aa6d81d5874561af10e42"
)
OBSERVED_ATTEMPT_ID = "governed-resolution-e81b12cca0eb-replacement-01"
OBSERVED_RESOLUTION_ROOT = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-27-governed-resolution-operational"
)
OBSERVED_PREFLIGHT_ARCHIVE = (
    OBSERVED_RESOLUTION_ROOT / f"{OBSERVED_ATTEMPT_ID}-preflight"
)
OBSERVED_DESTINATION = OBSERVED_RESOLUTION_ROOT / OBSERVED_ATTEMPT_ID
OBSERVED_STAGING = OBSERVED_RESOLUTION_ROOT / f".{OBSERVED_ATTEMPT_ID}.staging"
OBSERVED_MARKER_SHA256 = (
    "sha256:c307db9cf7220df203086c2ce348cdad4bf2def1029653d2125ba6341632a501"
)
OBSERVED_CANDIDATE_CHECKSUMS_SHA256 = (
    "sha256:ee01977cce93887f48cc6a2f13cc33a8e24d00a38ab002f59519c67b03a97999"
)
_OBSERVED_INITIAL_REQUEST_SHA256 = (
    "sha256:c1af3a9bc8b7e9f93fc137140a91155e2fe8297ff2ceb5da8b2e882982563f98"
)
_OBSERVED_PREFLIGHT_CHECKSUMS_SCHEMA_ID = (
    "rook.lm9b_p.governed_resolution_preflight_checksums:v1"
)
_OBSERVED_PREFLIGHT_SCHEMA_ID = "rook.lm9b_p.governed_resolution_preflight:v1"
_PREFLIGHT_MEMBERS = frozenset(
    {"record.json", "initial-request.json", "checksums.json"}
)


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strict_object(raw: bytes, label: str) -> dict[str, object]:
    value = PLANNER_SUPPORT.parse_archive_json(raw)
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _path_has_reparse_ambiguity(path: Path) -> bool:
    current = path
    while True:
        try:
            info = os.lstat(current)
        except OSError:
            return True
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or bool(
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            return True
        if current.parent == current:
            return False
        current = current.parent


def _flat_snapshot(path: Path, *, expected: frozenset[str]) -> tuple[Path, dict[str, bytes], tuple[object, ...]]:
    archive = Path(path)
    if not archive.is_absolute() or _path_has_reparse_ambiguity(archive):
        raise ValueError("forensic evidence path is not a physical absolute path")
    archive = archive.resolve()
    rows: list[tuple[object, ...]] = []
    members: dict[str, bytes] = {}
    names: set[str] = set()
    with os.scandir(archive) as stream:
        for entry in stream:
            names.add(entry.name)
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                raise ValueError("forensic evidence membership is not file-only")
            raw = Path(entry.path).read_bytes()
            info = entry.stat(follow_symlinks=False)
            members[entry.name] = raw
            rows.append(
                (
                    entry.name,
                    "file",
                    len(raw),
                    getattr(info, "st_dev", None),
                    getattr(info, "st_ino", None),
                    _sha256(raw),
                )
            )
    if names != set(expected):
        raise ValueError("forensic evidence membership is not closed")
    root_info = os.lstat(archive)
    identity: tuple[object, ...] = (
        str(archive),
        getattr(root_info, "st_dev", None),
        getattr(root_info, "st_ino", None),
        tuple(sorted(rows)),
    )
    return archive, members, identity


def _recursive_snapshot(path: Path) -> tuple[dict[str, bytes], tuple[object, ...]]:
    root = Path(path)
    if not root.is_absolute() or _path_has_reparse_ambiguity(root):
        raise ValueError("forensic staging path is not a physical absolute path")
    root = root.resolve()
    files: dict[str, bytes] = {}
    rows: list[tuple[object, ...]] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as stream:
            entries = sorted(stream, key=lambda item: item.name)
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            info = entry.stat(follow_symlinks=False)
            attributes = getattr(info, "st_file_attributes", 0)
            if entry.is_symlink() or bool(
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                raise ValueError("forensic staging contains a reparse entry")
            if entry.is_dir(follow_symlinks=False):
                rows.append(
                    (
                        relative,
                        "directory",
                        getattr(info, "st_dev", None),
                        getattr(info, "st_ino", None),
                    )
                )
                visit(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                raw = Path(entry.path).read_bytes()
                files[relative] = raw
                rows.append(
                    (
                        relative,
                        "file",
                        len(raw),
                        getattr(info, "st_dev", None),
                        getattr(info, "st_ino", None),
                        _sha256(raw),
                    )
                )
            else:
                raise ValueError("forensic staging contains a non-file entry")

    visit(root)
    root_info = os.lstat(root)
    identity: tuple[object, ...] = (
        str(root),
        getattr(root_info, "st_dev", None),
        getattr(root_info, "st_ino", None),
        tuple(rows),
    )
    return files, identity


_GIT_PATHS = (
    "mcp_server/src/rook/__init__.py",
    "mcp_server/src/rook/agent/__init__.py",
    "mcp_server/src/rook/agent/model_profiles.py",
    "mcp_server/src/rook/validation_kernel/__init__.py",
    "mcp_server/src/rook/validation_kernel/api.py",
    "mcp_server/src/rook/validation_kernel/budget.py",
    "mcp_server/src/rook/validation_kernel/canonical_json.py",
    "mcp_server/src/rook/validation_kernel/conformance.py",
    "mcp_server/src/rook/validation_kernel/control.py",
    "mcp_server/src/rook/validation_kernel/invocation.py",
    "mcp_server/src/rook/validation_kernel/kernel_schemas.py",
    "mcp_server/src/rook/validation_kernel/owned_json.py",
    "mcp_server/src/rook/validation_kernel/parser.py",
    "mcp_server/src/rook/validation_kernel/phase_contract.py",
    "mcp_server/src/rook/validation_kernel/phase_engine.py",
    "mcp_server/src/rook/validation_kernel/program.py",
    "mcp_server/src/rook/validation_kernel/reporting.py",
    "mcp_server/src/rook/validation_kernel/schema_profile.py",
    "scripts/lm9_semantic_typed_values.py",
    "scripts/lm9_typed_fact_carrier_artifacts.py",
    "scripts/lm9_typed_fact_carrier_qualification.py",
    "scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json",
    "scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json",
    "scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json",
    "scripts/lm9b_c_compiler_sufficiency_probe.py",
    "scripts/lm9b_p_evaluator_only_continuation_artifacts.py",
    "scripts/lm9b_p_fixtures/planner_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_artifacts.py",
    "scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json",
    "scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_probe.py",
    "scripts/lm9b_p_governed_resolution_support.py",
    "scripts/lm9b_p_planner_recipe_transfer_artifacts.py",
    "scripts/lm9b_p_planner_recipe_transfer_support.py",
    "scripts/lm9b_p_readiness_contract.py",
)


_HISTORICAL_EXACT_PRODUCER_PATHS = (
    "mcp_server/src/rook/__init__.py",
    "mcp_server/src/rook/agent/__init__.py",
    "mcp_server/src/rook/agent/model_profiles.py",
    "mcp_server/src/rook/validation_kernel/__init__.py",
    "mcp_server/src/rook/validation_kernel/api.py",
    "mcp_server/src/rook/validation_kernel/budget.py",
    "mcp_server/src/rook/validation_kernel/canonical_json.py",
    "mcp_server/src/rook/validation_kernel/conformance.py",
    "mcp_server/src/rook/validation_kernel/control.py",
    "mcp_server/src/rook/validation_kernel/invocation.py",
    "mcp_server/src/rook/validation_kernel/kernel_schemas.py",
    "mcp_server/src/rook/validation_kernel/owned_json.py",
    "mcp_server/src/rook/validation_kernel/parser.py",
    "mcp_server/src/rook/validation_kernel/phase_contract.py",
    "mcp_server/src/rook/validation_kernel/phase_engine.py",
    "mcp_server/src/rook/validation_kernel/program.py",
    "mcp_server/src/rook/validation_kernel/reporting.py",
    "mcp_server/src/rook/validation_kernel/schema_profile.py",
    "scripts/lm9_semantic_typed_values.py",
    "scripts/lm9_typed_fact_carrier_artifacts.py",
    "scripts/lm9_typed_fact_carrier_qualification.py",
    "scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json",
    "scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json",
    "scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json",
    "scripts/lm9b_c_compiler_sufficiency_probe.py",
    "scripts/lm9b_p_evaluator_only_continuation_artifacts.py",
    "scripts/lm9b_p_fixtures/planner_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json",
    "scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_support.py",
    "scripts/lm9b_p_planner_recipe_transfer_artifacts.py",
    "scripts/lm9b_p_readiness_contract.py",
)


_HISTORICAL_EXACT_DATA_PATHS = (
    "scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json",
    "scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json",
    "scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json",
    "scripts/lm9b_p_fixtures/planner_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json",
    "scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json",
)


_HISTORICAL_ARTIFACT_PRODUCER_ROOTS = (
    "_load_verified_resolution_sources_unsealed",
    "_seal_resolution_source_loader",
    "_resolution_sources_snapshot",
    "assemble_resolution_instrument",
    "_verify_historical_carrier_qualification_compatibility_unsealed",
    "_seal_compatibility_verifier",
    "_compatibility_snapshot",
    "readiness_route_identity_projection",
    "_launch_invocation_contract",
    "_load_current_resolution_sources",
    "_callable_source_fingerprint",
)

_CURRENT_ONLY_HISTORICAL_ARTIFACT_CAPABILITIES = frozenset(
    {
        "ARCHIVE_EVIDENCE",
        "ARCHIVE_EVIDENCE_PROFILE_PATH",
        "_resolution_archive_resource_contract",
    }
)

_CURRENT_MIGRATED_HISTORICAL_ARTIFACT_CAPABILITIES = frozenset(
    {"RESOLUTION_ARCHIVE_MEMBERS"}
)


_SOURCE_BINDINGS = (
    ("archive.public_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_sealed_resolution_checkpoint"),
    ("archive.seal_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "seal_resolution_checkpoint"),
    ("decision.blocker_projection_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_artifacts.py", "derive_probe_explicit_blockers"),
    ("decision.call_ledger_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_resolution_call_ledger"),
    ("decision.classifier_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_artifacts.py", "derive_evaluated_recipe_classification"),
    ("evaluator.parser_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "derive_planner_evaluation_result"),
    ("evaluator.provider_request_builder_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_evaluator_provider_call_request"),
    ("evaluator.renderer_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "render_planner_revision_evaluation_request"),
    ("isolation.gate_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "evaluate_resolution_isolation"),
    ("launch_invocation.builder_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "build_resolution_invocation_binding"),
    ("launch_invocation.verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_resolution_invocation_binding"),
    ("planner.call_plan_builder_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_provider_call_plan"),
    ("planner.controller_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "run_planner_session"),
    ("planner.feedback_renderer_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_mechanical_feedback_message"),
    ("planner.mechanical_gate_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "evaluate_mechanical_gate"),
    ("planner.provider_request_builder_source_fingerprint", "scripts/lm9b_p_planner_recipe_transfer_support.py", "build_planner_provider_call_request"),
    ("planner.revision_renderer_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "render_planner_revision_request"),
    ("preflight.public_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_resolution_preflight"),
    ("preflight.reservation_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "reserve_resolution_staging"),
    ("preflight.writer_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "write_resolution_preflight"),
    ("readiness.role_adapter_binding.litellm_adapter_call_source_fingerprint", "scripts/lm9b_c_compiler_sufficiency_probe.py", "LiteLLMProvider.__call__"),
    ("readiness.role_adapter_binding.litellm_request_projection_source_fingerprint", "scripts/lm9b_c_compiler_sufficiency_probe.py", "build_litellm_completion_request_bytes"),
    ("readiness.route_identity_projection_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "readiness_route_identity_projection"),
    ("readiness.verifier_source_fingerprint", "scripts/lm9b_p_readiness_contract.py", "verify_launch_readiness"),
    ("ready_proof.consumer_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "consume_resolution_ready_proof"),
    ("ready_proof.issuer_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "issue_resolution_ready_proof"),
    ("ready_proof.snapshot_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "verify_sealed_resolution_checkpoint"),
    ("verified_inputs.carrier_compatibility_verifier_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "_verify_historical_carrier_qualification_compatibility_unsealed"),
    ("verified_inputs.physical_source_loader_source_fingerprint", "scripts/lm9b_p_governed_resolution_artifacts.py", "_load_verified_resolution_sources_unsealed"),
    ("verified_inputs.pure_input_assembler_source_fingerprint", "scripts/lm9b_p_governed_resolution_support.py", "_build_resolution_inputs_capability.derive"),
)


def _mapping_path(value: Mapping[str, object], dotted: str) -> object:
    current: object = value
    for part in dotted.split("."):
        if type(current) is not dict:
            raise ValueError(f"historical instrument path is absent: {dotted}")
        current = current.get(part)
    return current


def _git_blob(repo: Path, relative: str) -> tuple[bytes, str]:
    raw = subprocess.run(
        ["git", "show", f"{OBSERVED_COMMIT_SHA}:{relative}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    blob = subprocess.run(
        ["git", "rev-parse", f"{OBSERVED_COMMIT_SHA}:{relative}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return raw, blob


def _git_blob_map(repo: Path) -> tuple[dict[str, bytes], tuple[Mapping[str, object], ...]]:
    blobs: dict[str, bytes] = {}
    rows: list[Mapping[str, object]] = []
    for relative in _GIT_PATHS:
        raw, blob_id = _git_blob(repo, relative)
        blobs[relative] = raw
        rows.append(
            MappingProxyType(
                {
                    "path": relative,
                    "git_blob_id": blob_id,
                    "byte_length": len(raw),
                    "raw_sha256": _sha256(raw),
                }
            )
        )
    return blobs, tuple(rows)


def _source_bytes(raw: bytes, qualified_name: str) -> bytes:
    text = raw.decode("utf-8")
    tree = ast.parse(text)
    parts = qualified_name.split(".")
    nodes: list[ast.AST] = list(tree.body)
    selected: ast.AST | None = None
    for part in parts:
        selected = next(
            (
                node
                for node in nodes
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == part
            ),
            None,
        )
        if selected is None:
            raise ValueError(f"historical callable is absent: {qualified_name}")
        nodes = list(getattr(selected, "body", ()))
    assert selected is not None and selected.end_lineno is not None
    decorators = getattr(selected, "decorator_list", ())
    start = min(
        [selected.lineno, *(item.lineno for item in decorators)]
    )
    lines = text.splitlines(keepends=True)
    return "".join(lines[start - 1 : selected.end_lineno]).encode("utf-8")


def _set_mapping_path(value: dict[str, object], dotted: str, replacement: object) -> None:
    current: object = value
    parts = dotted.split(".")
    for part in parts[:-1]:
        if type(current) is not dict or type(current.get(part)) is not dict:
            raise ValueError(f"historical instrument path is absent: {dotted}")
        current = current[part]
    if type(current) is not dict or parts[-1] not in current:
        raise ValueError(f"historical instrument path is absent: {dotted}")
    current[parts[-1]] = replacement


def _git_object_at(repo: Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def _top_level_symbol_table(raw: bytes) -> Mapping[str, ast.AST]:
    tree = ast.parse(raw.decode("utf-8"))
    symbols: dict[str, ast.AST] = {}
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            names = [
                item.id
                for target in targets
                for item in ast.walk(target)
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
            ]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
            ]
        for name in names:
            if name in symbols:
                raise ValueError(
                    f"historical Git producer symbol is ambiguous: {name}"
                )
            symbols[name] = node
    return MappingProxyType(symbols)


def _top_level_node(raw: bytes, name: str) -> ast.AST:
    node = _top_level_symbol_table(raw).get(name)
    if node is not None:
        return node
    raise ValueError(f"historical Git producer symbol is absent: {name}")


def _top_level_bootstrap_nodes(raw: bytes) -> tuple[ast.AST, ...]:
    declarative = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Assign,
        ast.AnnAssign,
        ast.Import,
        ast.ImportFrom,
    )
    return tuple(
        node
        for node in ast.parse(raw.decode("utf-8")).body
        if not isinstance(node, declarative)
    )


def _top_level_bootstrap_identity(raw: bytes) -> tuple[str, ...]:
    return tuple(
        ast.dump(node, include_attributes=False)
        for node in _top_level_bootstrap_nodes(raw)
    )


def _node_identity(raw: bytes, name: str) -> str:
    return ast.dump(_top_level_node(raw, name), include_attributes=False)


def _reachable_artifact_producer_symbols(
    raw: bytes,
    roots: tuple[str, ...],
) -> tuple[frozenset[str], frozenset[str]]:
    symbols = _top_level_symbol_table(raw)
    if any(
        root not in symbols
        or not isinstance(symbols[root], (ast.FunctionDef, ast.AsyncFunctionDef))
        for root in roots
    ):
        raise ValueError("historical Git producer artifact root is absent")
    included: set[str] = set()
    executed: set[str] = set()
    pending_execution = list(roots)
    pending_values = [
        item.id
        for node in _top_level_bootstrap_nodes(raw)
        for item in ast.walk(node)
        if isinstance(item, ast.Name)
        and isinstance(item.ctx, ast.Load)
        and item.id in symbols
    ]
    while pending_execution or pending_values:
        if pending_execution:
            symbol = pending_execution.pop()
            if symbol in executed:
                continue
            executed.add(symbol)
            included.add(symbol)
            node = symbols[symbol]
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.Call)
                    and isinstance(item.func, ast.Name)
                    and item.func.id in symbols
                    and isinstance(
                        symbols[item.func.id],
                        (ast.FunctionDef, ast.AsyncFunctionDef),
                    )
                ):
                    pending_execution.append(item.func.id)
                if (
                    isinstance(item, ast.Name)
                    and isinstance(item.ctx, ast.Load)
                    and item.id in symbols
                ):
                    pending_values.append(item.id)
            continue
        symbol = pending_values.pop()
        if symbol in included:
            continue
        included.add(symbol)
        node = symbols[symbol]
        if not isinstance(
            node,
            (ast.Assign, ast.AnnAssign, ast.ClassDef, ast.Import, ast.ImportFrom),
        ):
            continue
        for item in ast.walk(node):
            if (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id in symbols
                and isinstance(
                    symbols[item.func.id],
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                )
            ):
                pending_execution.append(item.func.id)
            if (
                isinstance(item, ast.Name)
                and isinstance(item.ctx, ast.Load)
                and item.id in symbols
            ):
                pending_values.append(item.id)
    return frozenset(included), frozenset(executed)


def _module_identity_without(raw: bytes, excluded: frozenset[str]) -> str:
    tree = ast.parse(raw.decode("utf-8"))
    retained: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in excluded:
                continue
        retained.append(node)
    tree.body = retained
    return ast.dump(tree, include_attributes=False)


class _StripArchiveResourceDelta(ast.NodeTransformer):
    def visit_Assign(self, node: ast.Assign) -> ast.AST | None:
        stored_names = {
            item.id
            for target in node.targets
            for item in ast.walk(target)
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
        }
        if "archive_resource_contract" in stored_names:
            return None
        return self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> ast.AST:
        retained = [
            (key, value)
            for key, value in zip(node.keys, node.values)
            if not (
                isinstance(key, ast.Constant)
                and key.value == "archive_resource"
            )
        ]
        node.keys = [key for key, _value in retained]
        node.values = [value for _key, value in retained]
        return self.generic_visit(node)


def _historical_manifest_builder_identity(raw: bytes, *, repaired: bool) -> str:
    node = copy.deepcopy(
        _top_level_node(raw, "assemble_task1_resolution_instrument")
    )
    if repaired:
        node = _StripArchiveResourceDelta().visit(node)
        assert node is not None
    return ast.dump(node, include_attributes=False)


def _assignment_expression(raw: bytes, name: str) -> ast.expr:
    node = _top_level_node(raw, name)
    if isinstance(node, ast.Assign):
        return node.value
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return node.value
    raise ValueError(f"historical Git producer assignment is invalid: {name}")


def _literal_assignment_value(
    raw: bytes,
    name: str,
    *,
    readiness_schema_id: str | None = None,
) -> object:
    expression = copy.deepcopy(_assignment_expression(raw, name))

    class Resolve(ast.NodeTransformer):
        def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
            if (
                readiness_schema_id is not None
                and isinstance(node.value, ast.Name)
                and node.value.id == "READINESS"
                and node.attr == "SCHEMA_ID"
            ):
                return ast.copy_location(ast.Constant(readiness_schema_id), node)
            return self.generic_visit(node)

    expression = Resolve().visit(expression)
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id in {"MappingProxyType", "frozenset"}
        and len(expression.args) == 1
        and not expression.keywords
    ):
        value = ast.literal_eval(expression.args[0])
        return dict(value) if expression.func.id == "MappingProxyType" else frozenset(value)
    return ast.literal_eval(expression)


def _verify_historical_git_producer_roots(
    *,
    repo: Path,
    git_blobs: Mapping[str, bytes],
) -> None:
    if set(git_blobs) != set(_GIT_PATHS):
        raise ValueError("historical Git producer set is incomplete or contains extras")
    current_commit = _current_commit(repo)
    current_blobs = {
        relative: _git_object_at(repo, current_commit, relative)
        for relative in _GIT_PATHS
    }
    for relative in _HISTORICAL_EXACT_PRODUCER_PATHS:
        if current_blobs[relative] != git_blobs[relative]:
            raise ValueError(
                f"historical Git producer bytes differ: {relative}"
            )
    for relative in _HISTORICAL_EXACT_DATA_PATHS:
        if (repo / relative).read_bytes() != git_blobs[relative]:
            raise ValueError(
                f"historical Git producer physical bytes differ: {relative}"
            )

    planner_path = "scripts/lm9b_p_planner_recipe_transfer_support.py"
    if _module_identity_without(
        current_blobs[planner_path], frozenset({"run_planner_session"})
    ) != _module_identity_without(
        git_blobs[planner_path], frozenset({"run_planner_session"})
    ):
        raise ValueError("historical Git producer planner support differs")

    artifacts_path = "scripts/lm9b_p_governed_resolution_artifacts.py"
    current_artifacts = current_blobs[artifacts_path]
    historical_artifacts = git_blobs[artifacts_path]
    if _top_level_bootstrap_identity(
        current_artifacts
    ) != _top_level_bootstrap_identity(historical_artifacts):
        raise ValueError("historical Git producer artifact bootstrap differs")
    current_reachable, current_executed = _reachable_artifact_producer_symbols(
        current_artifacts, _HISTORICAL_ARTIFACT_PRODUCER_ROOTS
    )
    historical_reachable, historical_executed = _reachable_artifact_producer_symbols(
        historical_artifacts, _HISTORICAL_ARTIFACT_PRODUCER_ROOTS
    )
    if (
        current_reachable - historical_reachable
        != _CURRENT_ONLY_HISTORICAL_ARTIFACT_CAPABILITIES
        or historical_reachable - current_reachable
    ):
        raise ValueError("historical Git producer artifact graph differs")
    historical_source_overrides = frozenset(
        symbol
        for _dotted, relative, symbol in _SOURCE_BINDINGS
        if relative == artifacts_path
    )
    for symbol in sorted(
        historical_reachable
        - {"assemble_task1_resolution_instrument"}
        - _CURRENT_MIGRATED_HISTORICAL_ARTIFACT_CAPABILITIES
    ):
        identities_differ = _node_identity(
            current_artifacts, symbol
        ) != _node_identity(historical_artifacts, symbol)
        source_override_only = (
            symbol in historical_source_overrides
            and symbol not in current_executed
            and symbol not in historical_executed
        )
        if identities_differ and not source_override_only:
            raise ValueError(
                f"historical Git producer artifact capability differs: {symbol}"
            )
    if _historical_manifest_builder_identity(
        current_artifacts, repaired=True
    ) != _historical_manifest_builder_identity(
        historical_artifacts, repaired=False
    ):
        raise ValueError("historical Git producer manifest builder differs")

    readiness_schema = _literal_assignment_value(
        git_blobs["scripts/lm9b_p_readiness_contract.py"], "SCHEMA_ID"
    )
    historical_contracts = _literal_assignment_value(
        historical_artifacts,
        "CONTRACT_IDS",
        readiness_schema_id=str(readiness_schema),
    )
    historical_ready = dict(
        _literal_assignment_value(historical_artifacts, "_READY_PROOF_VALUE")
    )
    historical_ready["contract_fingerprint"] = PLANNER_SUPPORT.fingerprint(
        historical_ready
    )
    constant_checks = (
        (
            ARTIFACTS.HISTORICAL_CARRIER_COMMIT,
            _literal_assignment_value(
                historical_artifacts, "HISTORICAL_CARRIER_COMMIT"
            ),
        ),
        (
            ARTIFACTS.PREFLIGHT_SCHEMA_ID,
            _literal_assignment_value(historical_artifacts, "PREFLIGHT_SCHEMA_ID"),
        ),
        (
            frozenset(ARTIFACTS._PREFLIGHT_MEMBERS),
            _literal_assignment_value(historical_artifacts, "_PREFLIGHT_MEMBERS"),
        ),
        (
            dict(ARTIFACTS.RESOLUTION_ARCHIVE_MEMBERS),
            _literal_assignment_value(
                historical_artifacts, "RESOLUTION_ARCHIVE_MEMBERS"
            ),
        ),
        (dict(ARTIFACTS.CONTRACT_IDS), historical_contracts),
        (dict(ARTIFACTS.READY_PROOF_CONTRACT), historical_ready),
    )
    if any(current != historical for current, historical in constant_checks):
        raise ValueError("historical Git producer manifest constants differ")


def _reconstruct_historical_instrument_and_request(
    *,
    repo: Path,
    git_blobs: Mapping[str, bytes],
) -> tuple[dict[str, object], bytes]:
    """Rebuild historical claims from Git roots and frozen prerequisite evidence."""

    _verify_historical_git_producer_roots(repo=repo, git_blobs=git_blobs)
    current_commit = _current_commit(repo)
    sources = ARTIFACTS._load_current_resolution_sources(current_commit)
    current = ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
        evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
    )
    # The current verifier replays the immutable prerequisite archives and the
    # reviewed forward-carrier fixtures.  Historical callable identities are
    # then replaced below from pinned Git blobs; historical code is never
    # imported or executed.
    manifest = copy.deepcopy(dict(current.contract_manifest))
    if type(manifest) is not dict:
        raise ValueError("current derived instrument manifest is malformed")
    manifest.pop("archive_resource", None)

    qualification = sources.carrier_qualification
    compatibility_value = {
        "schema": "rook.lm9b_p.carrier_forward_compatibility:v1",
        "historical_qualification_identity": (
            qualification.historical_qualification_identity
        ),
        "historical_commit_sha": qualification.historical_commit_sha,
        "consuming_commit_sha": OBSERVED_COMMIT_SHA,
        "comparison_rows": [dict(row) for row in qualification.comparison_rows],
    }
    compatibility_fingerprint = PLANNER_SUPPORT.fingerprint(compatibility_value)
    inputs = current.inputs
    inputs_identity = {
        "parent_recipe_raw_sha256": _sha256(inputs.parent_recipe_bytes),
        "successor_envelope_raw_sha256": _sha256(inputs.successor_envelope_bytes),
        "successor_envelope_fingerprint": inputs.successor_envelope[
            "artifact_fingerprint"
        ],
        "carrier_compatibility_fingerprint": compatibility_fingerprint,
        "migration_fingerprint": PLANNER_SUPPORT.fingerprint(
            inputs.migration_ledger
        ),
        "correspondence_fingerprint": PLANNER_SUPPORT.fingerprint(
            inputs.correspondence
        ),
        "policy_instance_fingerprint": inputs.policy_instance.instance_fingerprint,
        "evaluation_rubric_fingerprint": inputs.evaluation_rubric[
            "rubric_fingerprint"
        ],
        "carrier_support_fingerprint": inputs.carrier_support_instrument[
            "carrier_support_fingerprint"
        ],
        "reviewed_commit_sha": OBSERVED_COMMIT_SHA,
    }
    manifest["reviewed_commit_sha"] = OBSERVED_COMMIT_SHA
    manifest["carrier_forward_compatibility"] = {
        "fingerprint": compatibility_fingerprint,
        "consuming_commit_sha": OBSERVED_COMMIT_SHA,
    }
    verified_inputs = manifest.get("verified_inputs")
    if type(verified_inputs) is not dict:
        raise ValueError("derived historical verified-input contract is absent")
    verified_inputs["inputs_fingerprint"] = PLANNER_SUPPORT.fingerprint(
        inputs_identity
    )

    for dotted, relative, symbol in _SOURCE_BINDINGS:
        _set_mapping_path(
            manifest,
            dotted,
            _sha256(_source_bytes(git_blobs[relative], symbol)),
        )
    raw_bindings = {
        "readiness.role_adapter_binding.execution_module_raw_sha256": (
            "scripts/lm9b_p_governed_resolution_probe.py"
        ),
        "readiness.role_adapter_binding.litellm_provider_module_raw_sha256": (
            "scripts/lm9b_c_compiler_sufficiency_probe.py"
        ),
    }
    for dotted, relative in raw_bindings.items():
        _set_mapping_path(manifest, dotted, _sha256(git_blobs[relative]))
    diagnostic = {
        "contract": "source_defined_planner_diagnostics:v1",
        "submission_parser_source": _sha256(
            _source_bytes(
                git_blobs["scripts/lm9b_p_planner_recipe_transfer_support.py"],
                "derive_planner_submission_from_message",
            )
        ),
        "mechanical_gate_source": _mapping_path(
            manifest, "planner.mechanical_gate_source_fingerprint"
        ),
        "feedback_renderer_source": _mapping_path(
            manifest, "planner.feedback_renderer_source_fingerprint"
        ),
    }
    _set_mapping_path(
        manifest,
        "planner.diagnostic_vocabulary_fingerprint",
        PLANNER_SUPPORT.fingerprint(diagnostic),
    )
    return manifest, current.initial_request.raw_bytes


def _verify_historical_preflight_projection(
    *,
    repo: Path,
    archive: Path,
    members: Mapping[str, bytes],
    git_blobs: Mapping[str, bytes],
) -> tuple[dict[str, object], tuple[Mapping[str, object], ...]]:
    record = _strict_object(members["record.json"], "historical preflight")
    checksums = _strict_object(members["checksums.json"], "historical checksums")
    expected_checksums = {
        "schema": _OBSERVED_PREFLIGHT_CHECKSUMS_SCHEMA_ID,
        "members": [
            {"path": name, "raw_sha256": _sha256(members[name])}
            for name in ("initial-request.json", "record.json")
        ],
    }
    if checksums.get("schema") != _OBSERVED_PREFLIGHT_CHECKSUMS_SCHEMA_ID:
        raise ValueError("historical preflight checksum schema differs")
    if checksums != expected_checksums:
        raise ValueError("historical preflight checksum closure differs")
    if (
        set(record)
        != {
            "schema",
            "canonical_preflight_destination",
            "reviewed_commit_sha",
            "historical_qualification_identity",
            "carrier_compatibility_fingerprint",
            "instrument_fingerprint",
            "instrument_contracts",
            "initial_request_raw_sha256",
            "attempt",
            "preflight_fingerprint",
        }
        or record.get("schema") != _OBSERVED_PREFLIGHT_SCHEMA_ID
        or record.get("canonical_preflight_destination") != str(archive)
        or record.get("reviewed_commit_sha") != OBSERVED_COMMIT_SHA
    ):
        raise ValueError("historical preflight root reconstruction differs")
    expected_manifest, expected_initial_request = (
        _reconstruct_historical_instrument_and_request(
            repo=repo,
            git_blobs=git_blobs,
        )
    )
    manifest = record["instrument_contracts"]
    if (
        type(manifest) is not dict
        or manifest != expected_manifest
        or record.get("instrument_fingerprint")
        != PLANNER_SUPPORT.fingerprint(expected_manifest)
        or members["initial-request.json"] != expected_initial_request
        or record.get("initial_request_raw_sha256")
        != _sha256(expected_initial_request)
    ):
        raise ValueError("historical instrument reconstruction differs")
    attempt = record["attempt"]
    expected_attempt = {
        "attempt_id": OBSERVED_ATTEMPT_ID,
        "resolution_root": str(OBSERVED_RESOLUTION_ROOT),
        "canonical_destination": str(OBSERVED_DESTINATION),
        "staging_path": str(OBSERVED_STAGING),
        "attempt_fingerprint": OBSERVED_ATTEMPT_FINGERPRINT,
    }
    if type(attempt) is not dict or attempt != expected_attempt:
        raise ValueError("historical attempt binding differs")
    if PLANNER_SUPPORT.fingerprint(
        {
            "instrument_fingerprint": OBSERVED_INSTRUMENT_FINGERPRINT,
            "attempt_id": OBSERVED_ATTEMPT_ID,
            "canonical_destination": str(OBSERVED_DESTINATION),
        }
    ) != OBSERVED_ATTEMPT_FINGERPRINT:
        raise ValueError("historical attempt equation differs")
    expected_preflight = PLANNER_SUPPORT.fingerprint_without(
        record, "preflight_fingerprint"
    )
    if (
        record.get("preflight_fingerprint") != expected_preflight
        or expected_preflight != OBSERVED_PREFLIGHT_FINGERPRINT
        or record.get("instrument_fingerprint")
        != OBSERVED_INSTRUMENT_FINGERPRINT
        or record.get("initial_request_raw_sha256")
        != _OBSERVED_INITIAL_REQUEST_SHA256
    ):
        raise ValueError("historical preflight aggregate equation differs")
    return record, tuple()


@dataclass(frozen=True)
class _HistoricalPreflightSnapshot:
    archive_dir: Path
    record: Mapping[str, object]
    members: Mapping[str, bytes]
    git_manifest: tuple[Mapping[str, object], ...]
    physical_identity: tuple[object, ...]


@dataclass(frozen=True)
class _ForensicSourceCapabilitySnapshot:
    source: ForensicSourceSnapshot
    historical: _HistoricalPreflightSnapshot


@dataclass(frozen=True)
class ResolutionForensicReconstruction:
    observed_commit_sha: str
    forensic_commit_sha: str
    planner_call_count: int
    evaluator_call_count: int
    mechanical_status: str
    isolation_status: str
    reconstructed_classification: str
    candidate_recipe_raw_sha256: str
    runtime_call_projection_fingerprint: str
    authored_operational_accounting_fingerprint: str
    controller_conformance: str
    exact_timing_accounting: str
    cost_accounting: str
    cost_stop_compliance: str
    classification_scope: str
    original_attempt_state: str
    official_scientific_checkpoint: str
    ready_proof: str
    compiler_eligibility: bool
    gate_fingerprint: str
    isolation_fingerprint: str
    reconstruction_fingerprint: str


class VerifiedRuntimeCallProjection:
    """Opaque process-local proof that runtime roots derived the call rows."""

    def __new__(cls, *args: object, **kwargs: object) -> "VerifiedRuntimeCallProjection":
        del args, kwargs
        raise TypeError("VerifiedRuntimeCallProjection is closure-issued")


@dataclass(frozen=True)
class ForensicSourceSnapshot:
    staging_path: Path
    destination_path: Path
    preflight_members: Mapping[str, bytes]
    marker_bytes: bytes
    candidate_members: Mapping[str, bytes]
    before_identity: tuple[object, ...]


class VerifiedHistoricalResolutionPreflightForensics:
    __slots__ = ("__weakref__",)

    def __new__(cls) -> "VerifiedHistoricalResolutionPreflightForensics":
        raise TypeError("historical forensic preflight carriers are closure-issued")


class VerifiedResolutionForensicSource:
    __slots__ = ("__weakref__",)

    def __new__(cls) -> "VerifiedResolutionForensicSource":
        raise TypeError("resolution forensic source carriers are closure-issued")


def _build_forensic_capabilities():
    historical_issued: weakref.WeakKeyDictionary[
        VerifiedHistoricalResolutionPreflightForensics,
        _HistoricalPreflightSnapshot,
    ] = weakref.WeakKeyDictionary()
    source_issued: weakref.WeakKeyDictionary[
        VerifiedResolutionForensicSource,
        _ForensicSourceCapabilitySnapshot,
    ] = weakref.WeakKeyDictionary()

    def verify_historical(
        *,
        repo_root: Path,
        preflight_archive: Path,
        expected_preflight_fingerprint: str,
    ) -> VerifiedHistoricalResolutionPreflightForensics:
        snapshot = _verify_historical_resolution_preflight_forensics_unsealed(
            repo_root=repo_root,
            preflight_archive=preflight_archive,
            expected_preflight_fingerprint=expected_preflight_fingerprint,
        )
        issued = object.__new__(VerifiedHistoricalResolutionPreflightForensics)
        historical_issued[issued] = snapshot
        return issued

    def consume_historical(
        value: object,
    ) -> _HistoricalPreflightSnapshot:
        if type(value) is not VerifiedHistoricalResolutionPreflightForensics:
            raise TypeError("closure-issued historical forensic preflight required")
        snapshot = historical_issued.get(value)
        if snapshot is None:
            raise ValueError("historical forensic preflight was not issued")
        return snapshot

    def load_source(
        *,
        historical_preflight: object,
        staging_dir: Path,
        expected_marker_sha256: str,
        expected_candidate_checksums_sha256: str,
    ) -> VerifiedResolutionForensicSource:
        historical = consume_historical(historical_preflight)
        snapshot = _load_verified_resolution_forensic_source_unsealed(
            historical=historical,
            staging_dir=staging_dir,
            expected_marker_sha256=expected_marker_sha256,
            expected_candidate_checksums_sha256=(
                expected_candidate_checksums_sha256
            ),
        )
        issued = object.__new__(VerifiedResolutionForensicSource)
        source_issued[issued] = snapshot
        return issued

    def consume_source(value: object) -> _ForensicSourceCapabilitySnapshot:
        if type(value) is not VerifiedResolutionForensicSource:
            raise TypeError("closure-issued resolution forensic source required")
        snapshot = source_issued.get(value)
        if snapshot is None:
            raise ValueError("resolution forensic source was not issued")
        return snapshot

    return verify_historical, consume_historical, load_source, consume_source


def _verify_historical_resolution_preflight_forensics_unsealed(
    *,
    repo_root: Path,
    preflight_archive: Path,
    expected_preflight_fingerprint: str,
) -> _HistoricalPreflightSnapshot:
    """Verify the one consumed e81 preflight without executing historical code."""

    repo = Path(repo_root).resolve()
    archive_argument = Path(preflight_archive)
    if (
        expected_preflight_fingerprint != OBSERVED_PREFLIGHT_FINGERPRINT
        or not archive_argument.is_absolute()
        or archive_argument != OBSERVED_PREFLIGHT_ARCHIVE
    ):
        raise ValueError("historical forensic preflight pin differs")
    archive, members, before = _flat_snapshot(
        archive_argument, expected=_PREFLIGHT_MEMBERS
    )
    if archive != OBSERVED_PREFLIGHT_ARCHIVE:
        raise ValueError("historical forensic preflight location differs")
    git_blobs, git_manifest = _git_blob_map(repo)
    record, _rows = _verify_historical_preflight_projection(
        repo=repo,
        archive=archive,
        members=members,
        git_blobs=git_blobs,
    )
    _archive_after, members_after, after = _flat_snapshot(
        archive_argument, expected=_PREFLIGHT_MEMBERS
    )
    if after != before or members_after != members:
        raise ValueError("historical forensic preflight moved during verification")
    return _HistoricalPreflightSnapshot(
        archive_dir=archive,
        record=MappingProxyType(record),
        members=MappingProxyType(dict(members)),
        git_manifest=git_manifest,
        physical_identity=before,
    )


def _load_verified_resolution_forensic_source_unsealed(
    *,
    historical: _HistoricalPreflightSnapshot,
    staging_dir: Path,
    expected_marker_sha256: str,
    expected_candidate_checksums_sha256: str,
) -> _ForensicSourceCapabilitySnapshot:
    """Freeze one immutable copy of the consumed attempt's retained evidence."""

    if (
        expected_marker_sha256 != OBSERVED_MARKER_SHA256
        or expected_candidate_checksums_sha256
        != OBSERVED_CANDIDATE_CHECKSUMS_SHA256
    ):
        raise ValueError("forensic retained-source identity differs from pin")
    if os.path.lexists(OBSERVED_DESTINATION):
        raise ValueError("reserved governed-resolution destination is present")
    staging = Path(staging_dir)
    files, before = _recursive_snapshot(staging)
    directory_paths = {
        row[0]
        for row in before[-1]
        if isinstance(row, tuple) and len(row) >= 2 and row[1] == "directory"
    }
    if directory_paths != {
        ".archive-candidate",
        ".resolution-runtime",
        ".resolution-runtime/calls",
    }:
        raise ValueError("forensic staging directory membership is not closed")
    marker_relative = "post_dispatch_unsealed.json"
    candidate_prefix = ".archive-candidate/"
    runtime_prefix = ".resolution-runtime/"
    if marker_relative not in files:
        raise ValueError("forensic post-dispatch marker is absent")
    marker_raw = files[marker_relative]
    if _sha256(marker_raw) != expected_marker_sha256:
        raise ValueError("forensic post-dispatch marker fingerprint differs")
    marker = _strict_object(marker_raw, "post-dispatch marker")
    if (
        set(marker)
        != {
            "schema",
            "attempt_fingerprint",
            "attempt_id",
            "failure_locus",
            "forensic_hashes",
            "instrument_fingerprint",
            "preflight_fingerprint",
        }
        or marker.get("attempt_id") != OBSERVED_ATTEMPT_ID
        or marker.get("attempt_fingerprint") != OBSERVED_ATTEMPT_FINGERPRINT
        or marker.get("instrument_fingerprint") != OBSERVED_INSTRUMENT_FINGERPRINT
        or marker.get("preflight_fingerprint") != OBSERVED_PREFLIGHT_FINGERPRINT
        or marker.get("failure_locus")
        != "checkpoint_seal_failure:StrictJsonError"
    ):
        raise ValueError("forensic post-dispatch marker binding differs")
    forensic_rows = marker.get("forensic_hashes")
    if type(forensic_rows) is not list:
        raise ValueError("forensic post-dispatch hash rows are invalid")
    expected_files = {marker_relative}
    for row in forensic_rows:
        if (
            type(row) is not dict
            or set(row) != {"path", "sha256", "size"}
            or type(row.get("path")) is not str
            or row["path"] in expected_files
            or row["path"].startswith("/")
            or ".." in Path(row["path"]).parts
        ):
            raise ValueError("forensic post-dispatch hash row is invalid")
        relative = row["path"]
        expected_files.add(relative)
        raw = files.get(relative)
        if (
            raw is None
            or row.get("size") != len(raw)
            or row.get("sha256") != _sha256(raw)
        ):
            raise ValueError("forensic post-dispatch retained bytes differ")
    if set(files) != expected_files:
        raise ValueError("forensic staging file membership is not closed")
    candidate_members = {
        relative.removeprefix(candidate_prefix): raw
        for relative, raw in files.items()
        if relative.startswith(candidate_prefix)
    }
    expected_candidate_members = ARTIFACTS.resolution_archive_member_paths(
        candidate_present=True,
        isolation_evaluated=True,
        evaluator_dispatched=False,
    )
    if set(candidate_members) != set(expected_candidate_members):
        raise ValueError("forensic archive-candidate membership differs")
    checksum_raw = candidate_members.get("checksums.json")
    if (
        checksum_raw is None
        or _sha256(checksum_raw) != expected_candidate_checksums_sha256
    ):
        raise ValueError("forensic archive-candidate checksum identity differs")
    checksums = _strict_object(checksum_raw, "candidate checksums")
    checksum_rows = checksums.get("members")
    expected_checksum_rows = [
        {"path": name, "raw_sha256": _sha256(raw)}
        for name, raw in sorted(candidate_members.items())
        if name != "checksums.json"
    ]
    if (
        set(checksums) != {"schema", "members"}
        or checksum_rows != expected_checksum_rows
    ):
        raise ValueError("forensic archive-candidate checksum closure differs")
    runtime_members = {
        relative.removeprefix(runtime_prefix): raw
        for relative, raw in files.items()
        if relative.startswith(runtime_prefix)
    }
    if (
        runtime_members.get("preflight.json")
        != historical.members["record.json"]
        or runtime_members.get("initial-request.json")
        != historical.members["initial-request.json"]
        or not any(name.startswith("calls/") for name in runtime_members)
    ):
        raise ValueError("forensic runtime root evidence differs")
    instrument = _strict_object(
        candidate_members["instrument.json"], "candidate instrument"
    )
    if (
        instrument.get("preflight_record") != dict(historical.record)
        or instrument.get("instrument_fingerprint")
        != OBSERVED_INSTRUMENT_FINGERPRINT
        or instrument.get("contract_manifest")
        != historical.record["instrument_contracts"]
    ):
        raise ValueError("forensic candidate instrument differs from preflight")
    record = _strict_object(candidate_members["record.json"], "candidate record")
    if (
        record.get("attempt_id") != OBSERVED_ATTEMPT_ID
        or record.get("attempt_fingerprint") != OBSERVED_ATTEMPT_FINGERPRINT
        or record.get("preflight_fingerprint") != OBSERVED_PREFLIGHT_FINGERPRINT
        or record.get("instrument_fingerprint") != OBSERVED_INSTRUMENT_FINGERPRINT
        or record.get("canonical_destination") != str(OBSERVED_DESTINATION)
    ):
        raise ValueError("forensic candidate root binding differs")
    files_after, after = _recursive_snapshot(staging)
    if after != before or files_after != files:
        raise ValueError("forensic staging moved during source verification")
    public = ForensicSourceSnapshot(
        staging_path=staging.resolve(),
        destination_path=OBSERVED_DESTINATION,
        preflight_members=MappingProxyType(dict(historical.members)),
        marker_bytes=marker_raw,
        candidate_members=MappingProxyType(dict(candidate_members)),
        before_identity=before,
    )
    return _ForensicSourceCapabilitySnapshot(
        source=public, historical=historical
    )


(
    verify_historical_resolution_preflight_forensics,
    _consume_historical_preflight,
    load_verified_resolution_forensic_source,
    _consume_forensic_source,
) = _build_forensic_capabilities()


def _current_commit(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


_EXECUTION_CAPABILITY_SPECS = (
    (
        "rook_package",
        "rook",
        "mcp_server/src/rook/__init__.py",
    ),
    (
        "rook_agent_package",
        "rook.agent",
        "mcp_server/src/rook/agent/__init__.py",
    ),
    (
        "forensic_orchestrator",
        "lm9b_p_governed_resolution_forensics",
        "scripts/lm9b_p_governed_resolution_forensics.py",
    ),
    (
        "archive_resource_profile",
        "lm9b_p_governed_resolution_archive_evidence",
        "scripts/lm9b_p_governed_resolution_archive_evidence.py",
    ),
    (
        "resolution_evidence_reconstruction",
        "lm9b_p_governed_resolution_artifacts",
        "scripts/lm9b_p_governed_resolution_artifacts.py",
    ),
    (
        "resolution_request_and_isolation",
        "lm9b_p_governed_resolution_support",
        "scripts/lm9b_p_governed_resolution_support.py",
    ),
    (
        "planner_evidence_projection",
        "lm9b_p_planner_recipe_transfer_artifacts",
        "scripts/lm9b_p_planner_recipe_transfer_artifacts.py",
    ),
    (
        "planner_protocol_and_gate",
        "lm9b_p_planner_recipe_transfer_support",
        "scripts/lm9b_p_planner_recipe_transfer_support.py",
    ),
    (
        "historical_source_verifier",
        "lm9b_p_evaluator_only_continuation_artifacts",
        "scripts/lm9b_p_evaluator_only_continuation_artifacts.py",
    ),
    (
        "readiness_contract",
        "lm9b_p_readiness_contract",
        "scripts/lm9b_p_readiness_contract.py",
    ),
    (
        "typed_value_validation",
        "lm9_semantic_typed_values",
        "scripts/lm9_semantic_typed_values.py",
    ),
    (
        "typed_fact_carrier",
        "lm9_typed_fact_carrier_artifacts",
        "scripts/lm9_typed_fact_carrier_artifacts.py",
    ),
    (
        "typed_fact_qualification",
        "lm9_typed_fact_carrier_qualification",
        "scripts/lm9_typed_fact_carrier_qualification.py",
    ),
    (
        "litellm_request_projection",
        "lm9b_c_compiler_sufficiency_probe",
        "scripts/lm9b_c_compiler_sufficiency_probe.py",
    ),
    (
        "compiler_probe_artifact_types",
        "lm9b_c_compiler_sufficiency_artifacts",
        "scripts/lm9b_c_compiler_sufficiency_artifacts.py",
    ),
    (
        "compiler_probe_support_types",
        "lm9b_c_compiler_sufficiency_support",
        "scripts/lm9b_c_compiler_sufficiency_support.py",
    ),
    (
        "model_profile_projection",
        "rook.agent.model_profiles",
        "mcp_server/src/rook/agent/model_profiles.py",
    ),
    (
        "runtime_path_projection",
        "rook.runtime_paths",
        "mcp_server/src/rook/runtime_paths.py",
    ),
    (
        "grasshopper_preflight_types",
        "rook.gh_csharp_preflight",
        "mcp_server/src/rook/gh_csharp_preflight.py",
    ),
    (
        "validation_kernel_package",
        "rook.validation_kernel",
        "mcp_server/src/rook/validation_kernel/__init__.py",
    ),
    (
        "validation_kernel_api",
        "rook.validation_kernel.api",
        "mcp_server/src/rook/validation_kernel/api.py",
    ),
    (
        "validation_kernel_budget",
        "rook.validation_kernel.budget",
        "mcp_server/src/rook/validation_kernel/budget.py",
    ),
    (
        "validation_kernel_canonical_json",
        "rook.validation_kernel.canonical_json",
        "mcp_server/src/rook/validation_kernel/canonical_json.py",
    ),
    (
        "validation_kernel_conformance",
        "rook.validation_kernel.conformance",
        "mcp_server/src/rook/validation_kernel/conformance.py",
    ),
    (
        "validation_kernel_control",
        "rook.validation_kernel.control",
        "mcp_server/src/rook/validation_kernel/control.py",
    ),
    (
        "validation_kernel_invocation",
        "rook.validation_kernel.invocation",
        "mcp_server/src/rook/validation_kernel/invocation.py",
    ),
    (
        "validation_kernel_schemas",
        "rook.validation_kernel.kernel_schemas",
        "mcp_server/src/rook/validation_kernel/kernel_schemas.py",
    ),
    (
        "validation_kernel_owned_json",
        "rook.validation_kernel.owned_json",
        "mcp_server/src/rook/validation_kernel/owned_json.py",
    ),
    (
        "validation_kernel_parser",
        "rook.validation_kernel.parser",
        "mcp_server/src/rook/validation_kernel/parser.py",
    ),
    (
        "validation_kernel_phase_contract",
        "rook.validation_kernel.phase_contract",
        "mcp_server/src/rook/validation_kernel/phase_contract.py",
    ),
    (
        "validation_kernel_phase_engine",
        "rook.validation_kernel.phase_engine",
        "mcp_server/src/rook/validation_kernel/phase_engine.py",
    ),
    (
        "validation_kernel_program",
        "rook.validation_kernel.program",
        "mcp_server/src/rook/validation_kernel/program.py",
    ),
    (
        "validation_kernel_reporting",
        "rook.validation_kernel.reporting",
        "mcp_server/src/rook/validation_kernel/reporting.py",
    ),
    (
        "validation_kernel_schema_profile",
        "rook.validation_kernel.schema_profile",
        "mcp_server/src/rook/validation_kernel/schema_profile.py",
    ),
)


_FORENSIC_EXECUTION_RESOURCE_PATHS = (
    "scripts/lm9_typed_fact_carrier_contracts/semantic_value_schema_registry.json",
    "scripts/lm9_typed_fact_carrier_contracts/planner_task_typed_facts_payload_schema.json",
    "scripts/lm9_typed_fact_carrier_fixtures/radial_successor_task_envelope.json",
    "scripts/lm9b_p_fixtures/planner_recipe_probe_schema.json",
    "scripts/lm9b_p_fixtures/planner_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_contracts/archive_evidence_resource_profile.json",
    "scripts/lm9b_p_governed_resolution_contracts/isolation_policy.json",
    "scripts/lm9b_p_governed_resolution_contracts/planner_revision_evaluation_rubric.json",
    "scripts/lm9b_p_governed_resolution_probe.py",
)


_FORENSIC_EXECUTION_PATHS = tuple(
    dict.fromkeys(
        [relative for _capability, _module, relative in _EXECUTION_CAPABILITY_SPECS]
        + list(_FORENSIC_EXECUTION_RESOURCE_PATHS)
    )
)


_EXECUTION_CAPABILITY_OWNER_PATHS = {
    "archive_resource_profile": "ARCHIVE_EVIDENCE",
    "resolution_evidence_reconstruction": "ARTIFACTS",
    "resolution_request_and_isolation": "SUPPORT",
    "planner_evidence_projection": "PLANNER_ARTIFACTS",
    "planner_protocol_and_gate": "PLANNER_SUPPORT",
    "historical_source_verifier": "ARTIFACTS.CONT_ARTIFACTS",
    "readiness_contract": "ARTIFACTS.READINESS",
    "typed_value_validation": "ARTIFACTS.TYPED_VALUES",
    "typed_fact_carrier": "ARTIFACTS.CARRIER",
    "typed_fact_qualification": "ARTIFACTS.QUALIFICATION",
    "litellm_request_projection": "ARTIFACTS.PROVIDER_ADAPTER",
    "model_profile_projection": (
        "ARTIFACTS.CONT_ARTIFACTS.api_key_env_for_model"
    ),
    "validation_kernel_canonical_json": "PLANNER_SUPPORT.canonical_fingerprint",
    "validation_kernel_owned_json": "PLANNER_SUPPORT.own_trusted_json",
}


def _actual_capability_owner(capability_id: str, module_name: str) -> object:
    if capability_id == "forensic_orchestrator":
        module = sys.modules.get(__name__)
        if module is None or getattr(module, "__name__", None) != module_name:
            raise ValueError(f"execution capability owner differs: {capability_id}")
        return module
    owner_path = _EXECUTION_CAPABILITY_OWNER_PATHS.get(capability_id)
    if owner_path is None:
        return importlib.import_module(module_name)
    parts = owner_path.split(".")
    value: object = globals().get(parts[0])
    if value is None:
        raise ValueError(f"execution capability owner differs: {capability_id}")
    for part in parts[1:]:
        value = getattr(value, part, None)
        if value is None:
            raise ValueError(f"execution capability owner differs: {capability_id}")
    return value


def _actual_capability_module(capability_id: str, module_name: str) -> object:
    value = _actual_capability_owner(capability_id, module_name)
    if getattr(value, "__file__", None) is not None:
        module = value
    else:
        owner_module_name = getattr(value, "__module__", None)
        if type(owner_module_name) is not str:
            raise ValueError(f"execution capability owner differs: {capability_id}")
        module = sys.modules.get(owner_module_name)
    if module is None or getattr(module, "__name__", None) != module_name:
        raise ValueError(f"execution capability owner differs: {capability_id}")
    return module


def _capability_owner_projection(
    capability_id: str,
    module_name: str,
) -> tuple[str | None, str]:
    value = _actual_capability_owner(capability_id, module_name)
    owner_path = _EXECUTION_CAPABILITY_OWNER_PATHS.get(capability_id)
    if getattr(value, "__file__", None) is not None:
        identity = str(getattr(value, "__name__", ""))
    else:
        identity = str(getattr(value, "__qualname__", ""))
    if not identity:
        raise ValueError(f"execution callable alias differs: {capability_id}")
    return owner_path, identity


def _validate_execution_alias_snapshot(
    capability_id: str,
    module_name: str,
) -> tuple[str | None, str]:
    issued = _EXECUTION_ALIAS_SNAPSHOT.get(capability_id)
    if issued is None:
        raise ValueError(f"execution alias snapshot is absent: {capability_id}")
    current = _actual_capability_owner(capability_id, module_name)
    if current is not issued:
        raise ValueError(f"execution callable alias differs: {capability_id}")
    return _capability_owner_projection(capability_id, module_name)


def _module_callable_bindings(module: object) -> Mapping[str, object]:
    module_name = getattr(module, "__name__", None)
    if type(module_name) is not str:
        raise ValueError("execution capability module identity is absent")
    return MappingProxyType(
        {
            name: value
            for name, value in vars(module).items()
            if callable(value)
        }
    )


def _validate_execution_callable_snapshot(
    capability_id: str,
    module: object,
) -> tuple[str, ...]:
    issued = _EXECUTION_CALLABLE_SNAPSHOT.get(capability_id)
    if issued is None:
        raise ValueError(f"execution callable snapshot is absent: {capability_id}")
    current = _module_callable_bindings(module)
    if set(current) != set(issued) or any(
        current[name] is not issued[name] for name in issued
    ):
        raise ValueError(f"execution callable binding differs: {capability_id}")
    return tuple(sorted(issued))


def _execution_capability_ledger() -> tuple[Mapping[str, object], ...]:
    rows: list[Mapping[str, object]] = []
    for capability_id, module_name, relative in _EXECUTION_CAPABILITY_SPECS:
        owner_path, owner_identity = _validate_execution_alias_snapshot(
            capability_id, module_name
        )
        module = _actual_capability_module(capability_id, module_name)
        callable_names = _validate_execution_callable_snapshot(
            capability_id, module
        )
        module_path = getattr(module, "__file__", None)
        if type(module_path) is not str:
            raise ValueError(
                f"execution capability module path is absent: {capability_id}"
            )
        rows.append(
            MappingProxyType(
                {
                    "capability_id": capability_id,
                    "module_name": module_name,
                    "relative_path": relative,
                    "module_path": str(Path(module_path).resolve()),
                    "callable_names": callable_names,
                    "owner_path": owner_path,
                    "owner_identity": owner_identity,
                }
            )
        )
    return tuple(rows)


def _validate_execution_capability_ledger(
    rows: object,
) -> tuple[Mapping[str, object], ...]:
    if type(rows) not in {tuple, list}:
        raise TypeError("execution capability ledger rows are required")
    expected = {
        capability_id: (module_name, relative)
        for capability_id, module_name, relative in _EXECUTION_CAPABILITY_SPECS
    }
    observed: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "capability_id",
                "module_name",
                "relative_path",
                "module_path",
                "callable_names",
                "owner_path",
                "owner_identity",
            }
            or type(row.get("capability_id")) is not str
            or row["capability_id"] in observed
        ):
            raise ValueError("execution capability ledger is malformed")
        observed[row["capability_id"]] = row
    if set(observed) != set(expected):
        raise ValueError("execution capability ledger is incomplete or contains extras")
    for capability_id, (module_name, relative) in expected.items():
        row = observed[capability_id]
        owner_path, owner_identity = _validate_execution_alias_snapshot(
            capability_id, module_name
        )
        module = _actual_capability_module(capability_id, module_name)
        callable_names = _validate_execution_callable_snapshot(
            capability_id, module
        )
        actual_path = Path(getattr(module, "__file__", "")).resolve()
        if (
            row["module_name"] != module_name
            or row["relative_path"] != relative
            or Path(str(row["module_path"])).resolve() != actual_path
            or tuple(row["callable_names"]) != callable_names
            or row["owner_path"] != owner_path
            or row["owner_identity"] != owner_identity
        ):
            raise ValueError(
                f"execution capability owner differs: {capability_id}"
            )
    return tuple(observed[capability_id] for capability_id in expected)


def _verify_executing_checkout(repo: Path, commit: str) -> None:
    actual_root = _REPO_ROOT.resolve()
    if repo != actual_root:
        raise ValueError("forensic executing checkout root differs")
    if _current_commit(repo) != commit:
        raise ValueError("forensic reconstruction commit differs")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout
    if status:
        raise ValueError("forensic executing checkout is dirty")
    capability_ledger = _validate_execution_capability_ledger(
        _execution_capability_ledger()
    )
    for row in capability_ledger:
        if Path(str(row["module_path"])) != repo / str(row["relative_path"]):
            raise ValueError("forensic imported module checkout differs")
    for relative in _FORENSIC_EXECUTION_PATHS:
        worktree_raw = (repo / relative).read_bytes()
        reviewed_raw = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=repo,
            check=True,
            capture_output=True,
        ).stdout
        if worktree_raw != reviewed_raw:
            raise ValueError(f"forensic executing bytes differ: {relative}")


def _causalize_authored_call_row(
    row: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    causal = copy.deepcopy(dict(row))
    elapsed = causal.get("elapsed_ms")
    causal["elapsed_ms"] = None
    usage = causal.get("usage")
    cost = None
    if type(usage) is dict:
        cost = usage.pop("cost_usd", None)
    accounting = {
        "call_index": causal.get("call_index"),
        "elapsed_ms": elapsed,
        "cost_usd": cost,
        "authored_accounting_fingerprint": PLANNER_SUPPORT.fingerprint(
            {
                "call_index": causal.get("call_index"),
                "elapsed_ms": elapsed,
                "cost_usd": cost,
            }
        ),
        "verification_status": "authored_unverified",
    }
    return causal, accounting


def _runtime_response_projection(
    *,
    raw_response: bytes,
    role_contract: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    assistant = ARTIFACTS.PROVIDER_ADAPTER.project_litellm_assistant_message(
        raw_response
    )
    response = json.loads(raw_response)
    if type(response) is not dict:
        raise ValueError("runtime provider response is not an object")
    choices = response.get("choices")
    if type(choices) is not list or not choices or type(choices[0]) is not dict:
        raise ValueError("runtime provider response choice is invalid")
    usage = response.get("usage")
    if type(usage) is not dict:
        usage = {}
    else:
        usage = copy.deepcopy(usage)
        usage.pop("cost_usd", None)
    metadata = {
        "adapter": "litellm.completion",
        "model": role_contract["model"],
        "temperature": role_contract["temperature"],
        "transport_capture": "complete_litellm_objects_not_http_wire_bytes",
        "response_id": response.get("id"),
        "response_model": response.get("model"),
        "created": response.get("created"),
        "system_fingerprint": response.get("system_fingerprint"),
        "finish_reason": choices[0].get("finish_reason"),
        "model_identity": role_contract["model"],
        "profile_identity": role_contract["provider_profile"],
        "requested_model": role_contract["model"],
        "requested_profile": role_contract["provider_profile"],
    }
    return assistant, usage, metadata


def _derive_runtime_call_projection_value(
    *,
    runtime_call_files: Mapping[str, bytes],
    authored_call_ledger: Mapping[str, object],
    instrument_contracts: Mapping[str, object],
) -> dict[str, object]:
    """Derive every scientifically used call field from physical runtime roots."""

    if not isinstance(authored_call_ledger, Mapping) or set(authored_call_ledger) != {
        "schema",
        "calls",
    }:
        raise ValueError("authored forensic call ledger is malformed")
    if (
        authored_call_ledger.get("schema")
        != "rook.lm9b_p.governed_resolution_call_ledger:v1"
        or type(authored_call_ledger.get("calls")) is not list
    ):
        raise ValueError("authored forensic call ledger contract differs")
    authored_rows = authored_call_ledger["calls"]
    marker_names = sorted(
        name
        for name in runtime_call_files
        if name.endswith("-dispatch_started.json")
    )
    if len(marker_names) != len(authored_rows) or not marker_names:
        raise ValueError("runtime call marker cardinality differs")
    causal_rows: list[dict[str, object]] = []
    accounting_rows: list[dict[str, object]] = []
    expected_files: set[str] = set()
    for expected_index, marker_name in enumerate(marker_names):
        parts = marker_name.split("-", 2)
        if len(parts) != 3 or parts[2] != "dispatch_started.json":
            raise ValueError("runtime dispatch marker name is invalid")
        index_text, role = parts[0], parts[1]
        if index_text != f"{expected_index:02d}" or role not in {
            "planner",
            "planner_evaluator",
        }:
            raise ValueError("runtime call order or role differs")
        prefix = f"{index_text}-{role}"
        request_name = f"{prefix}-request.json"
        adapter_name = f"{prefix}-adapter-request.json"
        response_name = f"{prefix}-adapter-response.bin"
        error_name = f"{prefix}-adapter-error.bin"
        marker_raw = runtime_call_files[marker_name]
        request_raw = runtime_call_files.get(request_name)
        adapter_raw = runtime_call_files.get(adapter_name)
        if type(request_raw) is not bytes or type(adapter_raw) is not bytes:
            raise ValueError("runtime call request evidence is incomplete")
        marker = _strict_object(marker_raw, "runtime dispatch marker")
        role_key = "planner" if role == "planner" else "evaluator"
        role_contract = instrument_contracts.get(role_key)
        if type(role_contract) is not dict:
            raise ValueError("runtime role contract is absent")
        if (
            marker.get("call_index") != expected_index
            or marker.get("role") != role
            or marker.get("request_raw_sha256") != _sha256(request_raw)
            or marker.get("role_contract_fingerprint")
            != PLANNER_SUPPORT.fingerprint(role_contract)
        ):
            raise ValueError("runtime dispatch marker projection differs")
        request = ARCHIVE_EVIDENCE.materialize_resolution_provider_call_request(
            role=role,
            ordinal=(expected_index + 1 if role == "planner" else 1),
            raw_bytes=request_raw,
            profile=ARCHIVE_EVIDENCE.admit_resolution_archive_resource_profile(
                ARTIFACTS.ARCHIVE_EVIDENCE_PROFILE_PATH.read_bytes()
            ),
        )
        expected_adapter = (
            ARTIFACTS.PROVIDER_ADAPTER.build_litellm_completion_request_bytes(
                model=role_contract["model"],
                temperature=role_contract["temperature"],
                provider_request=request,
            )
        )
        if adapter_raw != expected_adapter:
            raise ValueError("runtime adapter request projection differs")
        row = {
            **marker,
            "dispatch_marker_raw_sha256": _sha256(marker_raw),
            "canonical_request_json": request_raw.decode("utf-8"),
            "provider_claimed_raw_request_b64": base64.b64encode(
                adapter_raw
            ).decode("ascii"),
            "provider_claimed_raw_request_sha256": _sha256(adapter_raw),
            "provider_raw_error_b64": None,
            "provider_raw_error_sha256": None,
            "raw_response_b64": None,
            "raw_response_sha256": None,
            "assistant_message": None,
            "usage": None,
            "provider_metadata": None,
            "outcome": None,
            "exception_type": None,
            "failure_type": None,
            "elapsed_ms": None,
            "terminal": True,
        }
        response_present = response_name in runtime_call_files
        error_present = error_name in runtime_call_files
        if response_present == error_present:
            raise ValueError("runtime terminal call branch is ambiguous")
        expected_files.update({marker_name, request_name, adapter_name})
        if response_present:
            raw_response = runtime_call_files[response_name]
            assistant, usage, metadata = _runtime_response_projection(
                raw_response=raw_response,
                role_contract=role_contract,
            )
            row.update(
                {
                    "raw_response_b64": base64.b64encode(raw_response).decode(
                        "ascii"
                    ),
                    "raw_response_sha256": _sha256(raw_response),
                    "assistant_message": assistant,
                    "usage": usage,
                    "provider_metadata": metadata,
                    "outcome": "returned",
                }
            )
            expected_files.add(response_name)
        else:
            raw_error = runtime_call_files[error_name]
            error = _strict_object(raw_error, "runtime adapter error")
            row.update(
                {
                    "provider_raw_error_b64": base64.b64encode(raw_error).decode(
                        "ascii"
                    ),
                    "provider_raw_error_sha256": _sha256(raw_error),
                    "outcome": "raised",
                    "exception_type": "ProviderCallFailure",
                    "failure_type": error.get("failure_type"),
                }
            )
            expected_files.add(error_name)
        authored = authored_rows[expected_index]
        if type(authored) is not dict:
            raise ValueError("authored forensic call row is malformed")
        authored_causal, accounting = _causalize_authored_call_row(authored)
        if authored_causal != row:
            raise ValueError("causal call projection differs from authored ledger")
        causal_rows.append(row)
        accounting_rows.append(accounting)
    if set(runtime_call_files) != expected_files:
        raise ValueError("runtime call file membership is not closed")
    value = {
        "schema": "rook.lm9b_p.verified_runtime_call_projection:v1",
        "planner_call_count": sum(
            1 for row in causal_rows if row["role"] == "planner"
        ),
        "evaluator_call_count": sum(
            1 for row in causal_rows if row["role"] == "planner_evaluator"
        ),
        "causal_rows": causal_rows,
        "unverified_operational_accounting": accounting_rows,
        "excluded_paths": [
            "calls[*].elapsed_ms",
            "calls[*].usage.cost_usd",
            "planner-session.calls[*].elapsed_ms",
            "planner-session.calls[*].usage.cost_usd",
            "planner-session.turns[*].elapsed_ms",
            "planner-session.turns[*].usage.cost_usd",
        ],
        "controller_conformance": "not_verified",
        "cost_stop_compliance": "not_verified",
    }
    value["projection_fingerprint"] = PLANNER_SUPPORT.fingerprint(value)
    return value


def _build_runtime_projection_capability():
    issued: weakref.WeakKeyDictionary[
        VerifiedRuntimeCallProjection, tuple[bytes, dict[str, object]]
    ] = weakref.WeakKeyDictionary()

    def derive(**kwargs: object) -> VerifiedRuntimeCallProjection:
        value = _derive_runtime_call_projection_value(**kwargs)
        raw = _canonical_bytes(value)
        projection = object.__new__(VerifiedRuntimeCallProjection)
        issued[projection] = (raw, copy.deepcopy(value))
        return projection

    def consume(value: object) -> Mapping[str, object]:
        if type(value) is not VerifiedRuntimeCallProjection:
            raise TypeError("closure-issued runtime call projection is required")
        retained = issued.get(value)
        if retained is None:
            raise ValueError("runtime call projection was not issued")
        raw, retained_value = retained
        projection = copy.deepcopy(retained_value)
        if _canonical_bytes(projection) != raw:
            raise ValueError("runtime call projection retained snapshot differs")
        if projection.get("projection_fingerprint") != PLANNER_SUPPORT.fingerprint_without(
            projection, "projection_fingerprint"
        ):
            raise ValueError("runtime call projection integrity differs")
        return MappingProxyType(projection)

    return derive, consume


(
    derive_verified_runtime_call_projection,
    _consume_verified_runtime_call_projection,
) = _build_runtime_projection_capability()


def _verify_causal_planner_transcript(
    *,
    causal_rows: tuple[Mapping[str, object], ...],
    inputs: SUPPORT.VerifiedResolutionInputs,
    initial_request_bytes: bytes,
    archive_resource_profile: object,
    candidate_recipe_bytes: bytes,
) -> dict[str, object]:
    messages: list[dict[str, object]] = [
        {"role": "system", "content": SUPPORT.REVISION_SYSTEM_PROMPT},
        {"role": "user", "content": initial_request_bytes.decode("utf-8")},
    ]
    accepted: bytes | None = None
    turns: list[dict[str, object]] = []
    accepted_gate: PLANNER_SUPPORT.MechanicalGateResult | None = None
    for ordinal, row in enumerate(causal_rows, 1):
        if row.get("role") != "planner":
            raise ValueError("forensic causal transcript contains a non-Planner call")
        request_raw = str(row["canonical_request_json"]).encode("utf-8")
        request = ARCHIVE_EVIDENCE.materialize_resolution_provider_call_request(
            role="planner",
            ordinal=ordinal,
            raw_bytes=request_raw,
            profile=archive_resource_profile,
        )
        rebuilt = PLANNER_SUPPORT.build_planner_provider_call_request(
            messages=messages,
            provider_timeout_s=request["provider_timeout_s"],
        )
        if rebuilt != request_raw:
            raise ValueError("forensic Planner request does not follow causal transcript")
        if row.get("outcome") != "returned":
            raise ValueError("retained Planner call did not return complete evidence")
        assistant = row.get("assistant_message")
        if type(assistant) is not dict:
            raise ValueError("forensic Planner assistant projection is absent")
        tool_arguments, recipe_bytes, rejection, tool_call_id = (
            PLANNER_SUPPORT.derive_planner_submission_from_message(assistant)
        )
        gate = rejection
        if recipe_bytes is not None:
            gate = PLANNER_SUPPORT.evaluate_mechanical_gate(
                recipe_bytes=recipe_bytes,
                authority=inputs.current_authority,
                recipe_schema=inputs.recipe_schema,
                normalization_profile=inputs.normalization_profile,
                exclusion_policy=inputs.exclusion_policy,
            )
        if gate is None or tool_arguments is None:
            raise ValueError("forensic Planner submission produced no gate")
        usage = copy.deepcopy(row.get("usage"))
        if type(usage) is dict:
            usage.pop("cost_usd", None)
        turns.append(
            {
                "turn_index": ordinal,
                "raw_response_sha256": row.get("raw_response_sha256"),
                "tool_arguments_sha256": _sha256(tool_arguments),
                "gate_status": gate.status,
                "usage": usage,
                "elapsed_ms": None,
            }
        )
        if gate.status == "mechanically_accepted":
            if ordinal != len(causal_rows) or recipe_bytes != candidate_recipe_bytes:
                raise ValueError("forensic accepted submission differs from candidate")
            accepted = recipe_bytes
            accepted_gate = gate
            continue
        messages.append(copy.deepcopy(assistant))
        messages.append(
            PLANNER_SUPPORT.build_planner_mechanical_feedback_message(
                gate, tool_call_id
            )
        )
    if accepted != candidate_recipe_bytes:
        raise ValueError("forensic causal transcript produced no accepted candidate")
    return {
        "schema": "rook.lm9b_p.governed_resolution_planner_session:v1",
        "termination": "mechanically_accepted",
        "call_count": len(causal_rows),
        "final_recipe_raw_sha256": _sha256(candidate_recipe_bytes),
        "calls": [copy.deepcopy(dict(row)) for row in causal_rows],
        "turns": turns,
        "accepted_gate": accepted_gate,
    }


def _planner_session_causal_projection(value: object) -> object:
    projected = copy.deepcopy(value)
    if type(projected) is not dict:
        return projected
    calls = projected.get("calls")
    if type(calls) is list:
        projected["calls"] = [
            _causalize_authored_call_row(row)[0]
            if isinstance(row, Mapping)
            else row
            for row in calls
        ]
    turns = projected.get("turns")
    if type(turns) is list:
        for row in turns:
            if type(row) is not dict:
                continue
            row["elapsed_ms"] = None
            usage = row.get("usage")
            if type(usage) is dict:
                usage.pop("cost_usd", None)
    return projected


def reconstruct_resolution_forensic_candidate(
    *,
    source: object,
    repo_root: Path,
    forensic_commit_sha: str,
) -> ResolutionForensicReconstruction:
    """Reconstruct one retained outcome without publishing or repairing it."""

    return _reconstruct_resolution_forensic_candidate_unsealed(
        capability=_consume_forensic_source(source),
        repo_root=repo_root,
        forensic_commit_sha=forensic_commit_sha,
        require_executing_checkout=True,
    )


def _reconstruct_resolution_forensic_candidate_unsealed(
    *,
    capability: _ForensicSourceCapabilitySnapshot,
    repo_root: Path,
    forensic_commit_sha: str,
    require_executing_checkout: bool,
) -> ResolutionForensicReconstruction:
    if type(capability) is not _ForensicSourceCapabilitySnapshot:
        raise TypeError("forensic source capability snapshot is required")
    frozen = capability.source
    historical = capability.historical
    repo = Path(repo_root).resolve()
    if type(forensic_commit_sha) is not str:
        raise ValueError("forensic reconstruction commit differs")
    if require_executing_checkout:
        _verify_executing_checkout(repo, forensic_commit_sha)
    elif _current_commit(repo) != forensic_commit_sha:
        raise ValueError("forensic reconstruction commit differs")
    if os.path.lexists(frozen.destination_path):
        raise ValueError("reserved governed-resolution destination appeared")
    _archive, preflight_members, preflight_identity = _flat_snapshot(
        historical.archive_dir, expected=_PREFLIGHT_MEMBERS
    )
    if (
        preflight_identity != historical.physical_identity
        or preflight_members != dict(historical.members)
    ):
        raise ValueError("historical preflight moved before reconstruction")
    staging_files, staging_identity = _recursive_snapshot(frozen.staging_path)
    if staging_identity != frozen.before_identity:
        raise ValueError("forensic staging moved before reconstruction")
    observed_candidate = {
        relative.removeprefix(".archive-candidate/"): raw
        for relative, raw in staging_files.items()
        if relative.startswith(".archive-candidate/")
    }
    if observed_candidate != dict(frozen.candidate_members):
        raise ValueError("forensic candidate bytes moved before reconstruction")

    profile, _profile_contract = ARTIFACTS._resolution_archive_resource_contract(
        forensic_commit_sha
    )
    call_ledger_value, call_shape = ARCHIVE_EVIDENCE.parse_resolution_call_ledger(
        frozen.candidate_members["call-ledger.json"],
        profile=profile,
    )
    shape = ARCHIVE_EVIDENCE.consume_resolution_call_shape(
        call_shape, profile=profile
    )
    if shape["planner_count"] != 6 or shape["evaluator_count"] != 0:
        raise ValueError("retained forensic call cardinality differs")
    parsed_members: dict[str, object] = {"call-ledger.json": call_ledger_value}
    for relative, raw in frozen.candidate_members.items():
        if relative == "call-ledger.json":
            continue
        parsed_members[relative] = ARCHIVE_EVIDENCE.parse_resolution_archive_member(
            raw,
            path=relative,
            profile=profile,
            call_shape=(
                call_shape
                if relative in {"planner-session.json", "evaluator.json"}
                else None
            ),
        )
    sources = ARTIFACTS._load_current_resolution_sources(forensic_commit_sha)
    current_instrument = ARTIFACTS.assemble_resolution_instrument(
        sources=sources,
        isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
        evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
    )
    inputs = current_instrument.inputs
    authored_authority = parsed_members["authority.json"]
    current_authority = ARTIFACTS._resolution_authority_record(inputs)
    if (
        type(authored_authority) is not dict
        or {
            key: value
            for key, value in authored_authority.items()
            if key != "inputs_fingerprint"
        }
        != {
            key: value
            for key, value in current_authority.items()
            if key != "inputs_fingerprint"
        }
        or parsed_members["migration.json"]
        != ARTIFACTS._resolution_migration_record(inputs)
        or parsed_members["correspondence.json"]
        != ARTIFACTS._resolution_correspondence_record(inputs)
    ):
        raise ValueError("forensic carrier compatibility projection differs")
    authored_source = parsed_members["source.json"]
    current_source = ARTIFACTS._resolution_source_record(inputs)
    source_exclusions = {
        "reviewed_commit_sha",
        "carrier_compatibility_fingerprint",
    }
    if (
        type(authored_source) is not dict
        or {
            key: value
            for key, value in authored_source.items()
            if key not in source_exclusions
        }
        != {
            key: value
            for key, value in current_source.items()
            if key not in source_exclusions
        }
    ):
        raise ValueError("forensic historical source projection differs")
    contracts = historical.record["instrument_contracts"]
    runtime_call_files = {
        relative.removeprefix(".resolution-runtime/calls/"): raw
        for relative, raw in staging_files.items()
        if relative.startswith(".resolution-runtime/calls/")
    }
    runtime_projection_proof = derive_verified_runtime_call_projection(
        runtime_call_files=runtime_call_files,
        authored_call_ledger=call_ledger_value,
        instrument_contracts=contracts,
    )
    runtime_projection = _consume_verified_runtime_call_projection(
        runtime_projection_proof
    )
    calls_value = runtime_projection["causal_rows"]
    call_ledger = tuple(
        MappingProxyType(dict(row))
        for row in calls_value
        if type(row) is dict
    )
    if len(call_ledger) != len(calls_value):
        raise ValueError("retained forensic call row is malformed")
    candidate_bytes = frozen.candidate_members["candidate-recipe.json"]
    causal_planner = _verify_causal_planner_transcript(
        causal_rows=call_ledger,
        inputs=inputs,
        initial_request_bytes=historical.members["initial-request.json"],
        archive_resource_profile=profile,
        candidate_recipe_bytes=candidate_bytes,
    )
    checkpoint_gate = PLANNER_SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=candidate_bytes,
        authority=inputs.current_authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if (
        checkpoint_gate.status != "mechanically_accepted"
        or checkpoint_gate.final_recipe_bytes != candidate_bytes
        or causal_planner["accepted_gate"] != checkpoint_gate
    ):
        raise ValueError("retained forensic mechanical reconstruction differs")
    isolation_result = SUPPORT.evaluate_resolution_isolation(
        inputs=inputs,
        candidate_recipe_bytes=candidate_bytes,
    )
    if isolation_result.status != "isolation_rejected":
        raise ValueError("retained forensic isolation reconstruction differs")
    decision_contract = contracts.get("decision")
    outcome_table = (
        decision_contract.get("outcome_table")
        if type(decision_contract) is dict
        else None
    )
    if (
        type(outcome_table) is not dict
        or outcome_table.get("isolation_rejected")
        != "probe_resolution_isolation_failure"
    ):
        raise ValueError("historical candidate-level outcome equation differs")
    classification = outcome_table["isolation_rejected"]
    expected_planner = {
        key: value
        for key, value in causal_planner.items()
        if key != "accepted_gate"
    }
    expected_gate = ARTIFACTS._gate_record(checkpoint_gate)
    expected_isolation = ARTIFACTS._isolation_record(isolation_result)
    expected_classification = ARTIFACTS._classification_record(
        classification=classification,
        derived_stop_cause="isolation_rejected",
        candidate_recipe_bytes=candidate_bytes,
    )
    authored_pairs = (
        ("checkpoint-gate.json", expected_gate),
        ("isolation.json", expected_isolation),
        ("classification.json", expected_classification),
    )
    if _planner_session_causal_projection(
        parsed_members["planner-session.json"]
    ) != _planner_session_causal_projection(expected_planner):
        raise ValueError("retained authored claim differs: planner-session.json")
    for relative, expected in authored_pairs:
        if parsed_members[relative] != expected:
            raise ValueError(f"retained authored claim differs: {relative}")
    value = {
        "observed_commit_sha": OBSERVED_COMMIT_SHA,
        "forensic_commit_sha": forensic_commit_sha,
        "planner_call_count": shape["planner_count"],
        "evaluator_call_count": shape["evaluator_count"],
        "mechanical_status": "accepted",
        "isolation_status": isolation_result.status,
        "reconstructed_classification": classification,
        "candidate_recipe_raw_sha256": _sha256(candidate_bytes),
        "runtime_call_projection_fingerprint": runtime_projection[
            "projection_fingerprint"
        ],
        "authored_operational_accounting_fingerprint": (
            PLANNER_SUPPORT.fingerprint(
                runtime_projection["unverified_operational_accounting"]
            )
        ),
        "controller_conformance": "not_verified",
        "exact_timing_accounting": "not_verified",
        "cost_accounting": "preserved_unverified",
        "cost_stop_compliance": "not_verified",
        "classification_scope": "candidate_level_deterministic_projection",
        "original_attempt_state": "post_dispatch_unsealed",
        "official_scientific_checkpoint": "absent",
        "ready_proof": "prohibited",
        "compiler_eligibility": False,
        "gate_fingerprint": PLANNER_SUPPORT.fingerprint(expected_gate),
        "isolation_fingerprint": isolation_result.result_fingerprint,
    }
    value["reconstruction_fingerprint"] = PLANNER_SUPPORT.fingerprint(value)
    result = ResolutionForensicReconstruction(**value)
    staging_after, after_identity = _recursive_snapshot(frozen.staging_path)
    if (
        after_identity != frozen.before_identity
        or staging_after != staging_files
        or os.path.lexists(frozen.destination_path)
    ):
        raise ValueError("forensic source moved during reconstruction")
    _archive_after, preflight_after, preflight_after_identity = _flat_snapshot(
        historical.archive_dir, expected=_PREFLIGHT_MEMBERS
    )
    if (
        preflight_after_identity != historical.physical_identity
        or preflight_after != preflight_members
    ):
        raise ValueError("historical preflight moved during reconstruction")
    return result


def _capture_execution_callable_snapshot() -> Mapping[str, Mapping[str, object]]:
    return MappingProxyType(
        {
            capability_id: _module_callable_bindings(
                _actual_capability_module(capability_id, module_name)
            )
            for capability_id, module_name, _relative in _EXECUTION_CAPABILITY_SPECS
        }
    )


def _capture_execution_alias_snapshot() -> Mapping[str, object]:
    return MappingProxyType(
        {
            capability_id: _actual_capability_owner(capability_id, module_name)
            for capability_id, module_name, _relative in _EXECUTION_CAPABILITY_SPECS
        }
    )


_EXECUTION_ALIAS_SNAPSHOT = _capture_execution_alias_snapshot()
_EXECUTION_CALLABLE_SNAPSHOT = _capture_execution_callable_snapshot()


__all__ = (
    "ForensicSourceSnapshot",
    "OBSERVED_ATTEMPT_FINGERPRINT",
    "OBSERVED_ATTEMPT_ID",
    "OBSERVED_CANDIDATE_CHECKSUMS_SHA256",
    "OBSERVED_COMMIT_SHA",
    "OBSERVED_DESTINATION",
    "OBSERVED_INSTRUMENT_FINGERPRINT",
    "OBSERVED_MARKER_SHA256",
    "OBSERVED_PREFLIGHT_ARCHIVE",
    "OBSERVED_PREFLIGHT_FINGERPRINT",
    "OBSERVED_STAGING",
    "ResolutionForensicReconstruction",
    "VerifiedHistoricalResolutionPreflightForensics",
    "VerifiedResolutionForensicSource",
    "load_verified_resolution_forensic_source",
    "reconstruct_resolution_forensic_candidate",
    "verify_historical_resolution_preflight_forensics",
)
