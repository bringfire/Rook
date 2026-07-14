"""One-shot composition of an immutable content-addressed validation program."""

from __future__ import annotations

import ast
import inspect
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib import metadata as importlib_metadata
from importlib import util as importlib_util
from importlib.machinery import ModuleSpec, PathFinder
from pathlib import Path, PurePosixPath
from types import FunctionType, MappingProxyType
from typing import cast

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement

from .budget import BudgetManifest
from .canonical_json import (
    canonical_fingerprint as _reference_canonical_fingerprint,
    canonical_json_bytes as _reference_canonical_json_bytes,
    normalized_source_fingerprint,
    sha256_prefixed,
    utf16_sort_key,
)
from .kernel_schemas import (
    FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT,
    KERNEL_OWNED_REPORT_PATHS,
    KERNEL_REPORT_FIELD_ROLES,
    PROGRAM_MANIFEST_SCHEMA_FINGERPRINT,
    PROGRAM_MANIFEST_SCHEMA_ID,
    REPORT_BUDGET_RECEIPT_PATH,
    REPORT_FINGERPRINT_PATH,
)
from .owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    JsonValue,
    count_json_nodes,
    own_trusted_json,
)
from .phase_contract import (
    ExportTypeSpec,
    ImmutableCallableRecord,
    ImplementationSource,
    InputBinding,
    InvocationInputSpec,
    IssueSpec,
    ParserProfileSpec,
    PhaseSpec,
    ProgramCompositionError,
    ProgramConstantSpec,
    ProvidedOutput,
    ReportProjectionSpec,
    RuntimeBinding,
    RuntimeComponentSpec,
    RuntimeDependencySpec,
    SchemaEvaluatorSpec,
    ValidationProgramContribution,
)
from .schema_profile import AdmittedSchema, SchemaProfile


KERNEL_ABI_VERSION = "rook.validation_kernel:v1"
PROGRAM_SEAL_PROFILE = "rook.validation_program_seal:v1"
REFERENCE_CANONICALIZER_ID = "rook.reference_canonicalizer:jcs_v1"
REPORT_PROJECTION_INPUT_ENVELOPE = (
    "program_identity",
    "invocation_evidence",
    "phase_specs",
    "phase_results",
)

_MACHINE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_MODULE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,255}\Z")
_FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DISTRIBUTION_NAME_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\Z")
_CARDINALITIES = frozenset(("exactly_one", "zero_or_one", "many"))
_OUTPUT_STATUSES = frozenset(("passed", "blocked", "failed"))
_ISSUE_CLASSIFICATIONS = frozenset(("diagnostic", "compile_blocker"))
_RUNTIME_BINDING_KINDS = frozenset(
    (
        "tokenizer",
        "parser",
        "canonicalizer",
        "ledger",
        "schema",
        "schema_evaluator",
        "runner",
        "export_type",
        "report_projection",
    )
)
_OWNED_VALUE_TYPES = (
    JsonNull,
    JsonBoolean,
    JsonString,
    JsonNumber,
    JsonArray,
    JsonObject,
)
_FIXED_KERNEL_MODULES = (
    "rook.validation_kernel.owned_json",
    "rook.validation_kernel.canonical_json",
    "rook.validation_kernel.budget",
    "rook.validation_kernel.control",
    "rook.validation_kernel.parser",
    "rook.validation_kernel.schema_profile",
    "rook.validation_kernel.phase_contract",
    "rook.validation_kernel.kernel_schemas",
    "rook.validation_kernel.program",
)
_UNSTABLE_DISTRIBUTION_FILES = frozenset(
    ("direct_url.json", "installer", "record", "requested")
)
_SAFE_IMPORTLIB_SUBMODULE_MEMBERS = MappingProxyType(
    {
        "importlib.machinery": frozenset(("ModuleSpec", "PathFinder")),
        "importlib.metadata": frozenset(
            (
                "Distribution",
                "PackageNotFoundError",
                "distribution",
                "packages_distributions",
                "version",
            )
        ),
        "importlib.util": frozenset(("resolve_name",)),
    }
)
_SAFE_IMPORTLIB_SUBMODULES = frozenset(_SAFE_IMPORTLIB_SUBMODULE_MEMBERS)
_BUDGET_LIMIT_KEYS = frozenset(
    (
        "recipe_input_bytes",
        "validation_bundle_input_bytes",
        "container_depth",
        "number_token_chars",
        "parsed_nodes",
        "object_members",
        "array_items",
        "decoded_string_bytes",
        "parser_work_units",
        "semantic_references",
        "schema_evaluation_shape_units",
        "diagnostics",
        "compile_blockers",
        "kernel_phase_work_units",
        "report_canonical_bytes",
        "report_projection_fields",
        "report_seal_work_units",
    )
)
_SEALED_PROGRAM_TOKEN = object()


def _fail(message: str) -> None:
    raise ProgramCompositionError(message)


def _require_machine_id(value: object, field_name: str) -> str:
    if type(value) is not str or not _MACHINE_ID_RE.fullmatch(value):
        _fail(f"{field_name} must be an ASCII machine identifier")
    return value


def _require_module_name(value: object, field_name: str) -> str:
    if type(value) is not str or not _MODULE_NAME_RE.fullmatch(value):
        _fail(f"{field_name} must be an ASCII Python module name")
    return value


def _require_fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or not _FINGERPRINT_RE.fullmatch(value):
        _fail(f"{field_name} must be lowercase prefixed SHA-256")
    return value


def _require_exact_tuple(value: object, field_name: str) -> tuple[object, ...]:
    if type(value) is not tuple:
        _fail(f"{field_name} must be an exact tuple")
    return value


def _sorted_strings(
    value: object,
    field_name: str,
    *,
    machine_ids: bool = False,
    allowed: frozenset[str] | None = None,
    nonempty: bool = False,
) -> tuple[str, ...]:
    raw = _require_exact_tuple(value, field_name)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if type(item) is not str:
            _fail(f"{field_name} entries must be exact strings")
        if machine_ids:
            _require_machine_id(item, field_name)
        else:
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                _fail(f"{field_name} entries must contain Unicode scalar values")
        if allowed is not None and item not in allowed:
            _fail(f"{field_name} contains an unsupported value")
        if item in seen:
            _fail(f"duplicate {field_name} identity: {item}")
        seen.add(item)
        normalized.append(item)
    if nonempty and not normalized:
        _fail(f"{field_name} cannot be empty")
    return tuple(sorted(normalized, key=utf16_sort_key))


def _host_json(value: JsonValue) -> object:
    return json.loads(_reference_canonical_json_bytes(value))


def _owned_object(value: object, context: str) -> JsonObject:
    try:
        owned = own_trusted_json(value)
    except (TypeError, ValueError) as error:
        raise ProgramCompositionError(f"{context} is not closed JSON") from error
    if type(owned) is not JsonObject:
        _fail(f"{context} must be an object")
    return owned


def _fingerprinted_object(value: dict[str, object], field_name: str) -> dict[str, object]:
    fingerprint = _reference_canonical_fingerprint(_owned_object(value, field_name))
    return {**value, field_name: fingerprint}


def _module_spec_without_import(module_name: str) -> ModuleSpec | None:
    search_path: list[str] | None = None
    parts = module_name.split(".")
    spec: ModuleSpec | None = None
    for index in range(1, len(parts) + 1):
        qualified_name = ".".join(parts[:index])
        loaded = sys.modules.get(qualified_name)
        loaded_spec = getattr(loaded, "__spec__", None)
        spec = (
            loaded_spec
            if isinstance(loaded_spec, ModuleSpec)
            else PathFinder.find_spec(qualified_name, search_path)
        )
        if spec is None:
            return None
        if index != len(parts):
            locations = spec.submodule_search_locations
            if locations is None:
                return None
            search_path = list(locations)
    return spec


def _read_module_source(module_name: str) -> tuple[bytes, str, Path]:
    _require_module_name(module_name, "source module")
    module = sys.modules.get(module_name)
    source_path = getattr(module, "__file__", None) if module is not None else None
    if type(source_path) is not str:
        spec = _module_spec_without_import(module_name)
        source_path = spec.origin if spec is not None else None
    if type(source_path) is not str:
        _fail(f"implementation source has no Python file: {module_name}")
    path = Path(source_path)
    if path.suffix.lower() not in (".py", ".pyw"):
        _fail(f"implementation source is not Python source: {module_name}")
    try:
        raw = path.read_bytes()
        source = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as error:
        raise ProgramCompositionError(
            f"implementation source is not readable strict UTF-8: {module_name}"
        ) from error
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return raw, normalized, path.resolve()


def implementation_source_for_module(module_name: str) -> ImplementationSource:
    """Capture a claimed source identity for later fixed-seal recomputation."""

    raw, _, _ = _read_module_source(module_name)
    return ImplementationSource(
        module_name=module_name,
        source_fingerprint=normalized_source_fingerprint(raw),
    )


def _validate_module_function(function: object) -> FunctionType:
    if inspect.ismethod(function):
        _fail("bound methods cannot be runtime bindings")
    if type(function) is not FunctionType:
        if callable(function):
            _fail("arbitrary callable instances cannot be runtime bindings")
        _fail("runtime binding target must be callable")
    if function.__closure__ is not None:
        _fail("closures cannot be runtime bindings")
    if (
        function.__qualname__ != function.__name__
        or function.__code__.co_qualname != function.__name__
        or function.__name__ == "<lambda>"
    ):
        _fail("runtime bindings must be named module-level functions")
    _require_module_name(function.__module__, "runtime callable module")
    return function


def _validate_runtime_callable(target: object) -> FunctionType:
    if type(target) is ImmutableCallableRecord:
        function = _validate_module_function(target.function)
        if type(target.state) is not JsonObject:
            _fail("immutable callable record state must be an owned JSON object")
        return function
    return _validate_module_function(target)


def _target_source_module(target: object) -> str:
    return _validate_runtime_callable(target).__module__


def runtime_implementation_fingerprint(target: object) -> str:
    """Fingerprint an allowed callable from source and any sealed record state."""

    function = _validate_runtime_callable(target)
    raw, _, _ = _read_module_source(function.__module__)
    source_fingerprint = normalized_source_fingerprint(raw)
    identity: dict[str, object] = {
        "callable_kind": (
            "immutable_callable_record"
            if type(target) is ImmutableCallableRecord
            else "module_function"
        ),
        "function_module": function.__module__,
        "function_qualname": function.__qualname__,
        "source_fingerprint": source_fingerprint,
    }
    if type(target) is ImmutableCallableRecord:
        identity["state_canonical_json"] = _reference_canonical_json_bytes(
            target.state
        ).decode("utf-8")
    return _reference_canonical_fingerprint(
        _owned_object(identity, "runtime callable identity")
    )


def _stable_distribution_path(value: object) -> str | None:
    text = str(value).replace("\\", "/")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or re.match(r"^[A-Za-z]:", text) is not None
        or text.startswith("//")
        or ".." in path.parts
    ):
        return None
    lowered_parts = tuple(part.lower() for part in path.parts)
    if "__pycache__" in lowered_parts or path.suffix.lower() in (".pyc", ".pyo"):
        return None
    if path.name.lower() in _UNSTABLE_DISTRIBUTION_FILES:
        return None
    return path.as_posix()


def _active_runtime_requirements(
    distribution: importlib_metadata.Distribution,
    activated_extras: frozenset[str],
) -> list[dict[str, object]]:
    environment = default_environment()
    contexts = tuple(sorted({"", *activated_extras}, key=utf16_sort_key))
    records: list[dict[str, object]] = []
    for raw_requirement in distribution.requires or ():
        try:
            requirement = Requirement(raw_requirement)
            active = requirement.marker is None or any(
                requirement.marker.evaluate({**environment, "extra": extra})
                for extra in contexts
            )
        except (InvalidRequirement, KeyError, ValueError) as error:
            raise ProgramCompositionError(
                "runtime dependency requirement metadata cannot be normalized"
            ) from error
        if not active:
            continue
        records.append(
            {
                "distribution_name": _normalized_distribution_name(
                    requirement.name
                ),
                "extras": sorted(
                    (_normalized_distribution_name(extra) for extra in requirement.extras),
                    key=utf16_sort_key,
                ),
                "specifier": str(requirement.specifier),
                "url": requirement.url,
                "marker": (
                    str(requirement.marker)
                    if requirement.marker is not None
                    else None
                ),
            }
        )
    records.sort(
        key=lambda record: (
            utf16_sort_key(cast(str, record["distribution_name"])),
            utf16_sort_key(cast(str, record["specifier"])),
            utf16_sort_key(cast(str | None, record["marker"]) or ""),
            utf16_sort_key(",".join(cast(list[str], record["extras"]))),
            utf16_sort_key(cast(str | None, record["url"]) or ""),
        )
    )
    return records


def _installed_dependency_projection(
    distribution_name: str,
    *,
    activated_extras: frozenset[str] = frozenset(),
) -> dict[str, object]:
    if type(distribution_name) is not str or not distribution_name:
        _fail("runtime dependency name must be a nonempty exact string")
    normalized_name = _normalized_distribution_name(distribution_name)
    try:
        distribution = importlib_metadata.distribution(distribution_name)
    except importlib_metadata.PackageNotFoundError as error:
        raise ProgramCompositionError(
            f"runtime dependency is not installed: {distribution_name}"
        ) from error
    metadata_name = distribution.metadata.get("Name")
    if type(metadata_name) is not str:
        _fail(f"runtime dependency metadata has no canonical name: {distribution_name}")
    canonical_name = _normalized_distribution_name(metadata_name)
    if canonical_name != normalized_name:
        _fail(f"runtime dependency canonical name mismatch: {distribution_name}")
    version = distribution.version
    records: list[dict[str, object]] = []
    files = distribution.files or ()
    for package_path in files:
        relative_path = _stable_distribution_path(package_path)
        if relative_path is None:
            continue
        located = Path(distribution.locate_file(package_path))
        try:
            if not located.is_file():
                continue
            content = located.read_bytes()
        except OSError as error:
            raise ProgramCompositionError(
                f"runtime dependency file cannot be hashed: {distribution_name}/{relative_path}"
            ) from error
        records.append(
            {
                "path": relative_path,
                "sha256": sha256_prefixed(content),
                "size": len(content),
            }
        )
    records.sort(key=lambda record: utf16_sort_key(cast(str, record["path"])))
    if not records:
        _fail(f"runtime dependency has no stable file records: {distribution_name}")
    behavior_files = [
        {"path": record["path"], "sha256": record["sha256"]}
        for record in records
        if PurePosixPath(cast(str, record["path"])).suffix.lower()
        in (".dll", ".pyd", ".py", ".pyw", ".so")
    ]
    if not behavior_files:
        _fail(f"runtime dependency has no behavior-bearing files: {distribution_name}")
    identity = {
        "distribution_name": canonical_name,
        "version": version,
        "activated_extras": sorted(activated_extras, key=utf16_sort_key),
        "active_runtime_requirements": _active_runtime_requirements(
            distribution,
            activated_extras,
        ),
        "file_records": records,
        "behavior_files": behavior_files,
    }
    return _fingerprinted_object(identity, "distribution_fingerprint")


def runtime_dependency_spec(distribution_name: str) -> RuntimeDependencySpec:
    """Inspect one installed distribution for later seal-time recomputation."""

    projection = _installed_dependency_projection(distribution_name)
    return RuntimeDependencySpec(
        distribution_name=cast(str, projection["distribution_name"]),
        expected_version=cast(str, projection["version"]),
        behavior_files=tuple(
            cast(str, item["path"])
            for item in cast(list[dict[str, object]], projection["behavior_files"])
        ),
        distribution_fingerprint=cast(
            str, projection["distribution_fingerprint"]
        ),
    )


def _component_record_state(target: object) -> tuple[str | None, str | None]:
    if type(target) is not ImmutableCallableRecord:
        return None, None
    state_bytes = _reference_canonical_json_bytes(target.state)
    return state_bytes.decode("utf-8"), _reference_canonical_fingerprint(target.state)


def _runtime_component_manifest(
    component: RuntimeComponentSpec,
    target: object,
) -> dict[str, object]:
    state_json, state_fingerprint = _component_record_state(target)
    return {
        "component_id": component.component_id,
        "implementation_id": component.implementation_id,
        "implementation_fingerprint": component.implementation_fingerprint,
        "source_module": component.source_module,
        "callable_record_state_canonical_json": state_json,
        "callable_record_state_fingerprint": state_fingerprint,
    }


def _validate_component(component: object, context: str) -> RuntimeComponentSpec:
    if type(component) is not RuntimeComponentSpec:
        _fail(f"{context} must be an exact RuntimeComponentSpec")
    _require_machine_id(component.component_id, f"{context} component ID")
    _require_machine_id(component.implementation_id, f"{context} implementation ID")
    _require_fingerprint(
        component.implementation_fingerprint,
        f"{context} implementation fingerprint",
    )
    _require_module_name(component.source_module, f"{context} source module")
    return component


def _validate_budget(budget: object) -> tuple[BudgetManifest, dict[str, object]]:
    if type(budget) is not BudgetManifest:
        _fail("budget manifest must be an exact BudgetManifest")
    _require_machine_id(budget.profile_id, "budget profile ID")
    if type(budget.limits) is not JsonObject:
        _fail("budget limits must be an owned JSON object")
    limits_host = _host_json(budget.limits)
    if type(limits_host) is not dict or set(limits_host) != _BUDGET_LIMIT_KEYS:
        _fail("budget limit table is not exact")
    if any(type(limit) is not int or limit < 0 for limit in limits_host.values()):
        _fail("budget limits must be nonnegative exact integers")
    canonical_bytes = cast(int, limits_host["report_canonical_bytes"])
    projection_fields = cast(int, limits_host["report_projection_fields"])
    seal_work_units = cast(int, limits_host["report_seal_work_units"])
    required_seal_work = projection_fields + 2 * ((canonical_bytes + 63) // 64)
    if seal_work_units < required_seal_work:
        _fail("report seal allowance is insufficient for the fixed maxima")
    expected_limits_fingerprint = _reference_canonical_fingerprint(
        _owned_object(
            {
                "profile_id": budget.profile_id,
                "limits": limits_host,
                "admission_order": "bundle_then_recipe_v1",
                "accounting_rules": "lm9a_kernel_controlled_v1",
                "seal_algorithm": "fixed_report_seal_v1",
            },
            "budget identity",
        )
    )
    if budget.limits_fingerprint != expected_limits_fingerprint:
        _fail("budget limits fingerprint mismatch")
    manifest = {
        "profile_id": budget.profile_id,
        "limits": limits_host,
        "limits_fingerprint": budget.limits_fingerprint,
    }
    return budget, _fingerprinted_object(manifest, "budget_fingerprint")


def _validate_parser_profile(
    profile: object,
) -> tuple[ParserProfileSpec, tuple[tuple[str, RuntimeComponentSpec], ...]]:
    if type(profile) is not ParserProfileSpec:
        _fail("parser profile must be an exact ParserProfileSpec")
    _require_machine_id(profile.profile_id, "parser profile ID")
    fields_and_kinds = (
        ("tokenizer", profile.tokenizer),
        ("parser", profile.parser),
        ("canonicalizer", profile.canonicalizer),
        ("ledger", profile.ledger),
    )
    for kind, component in fields_and_kinds:
        _validate_component(component, f"parser profile {kind}")
    for value, name in (
        (profile.tokenizer_version, "tokenizer version"),
        (profile.parser_version, "parser version"),
        (profile.owned_value_abi, "owned value ABI"),
        (profile.canonicalization_version, "canonicalization version"),
    ):
        _require_machine_id(value, name)
    return profile, fields_and_kinds


def _schema_profile_manifest(spec: SchemaEvaluatorSpec) -> dict[str, object]:
    profile = spec.profile
    identity_fingerprint = _reference_canonical_fingerprint(profile.identity)
    if profile.profile_fingerprint != identity_fingerprint:
        _fail(f"schema profile fingerprint mismatch: {profile.profile_id}")
    identity = _host_json(profile.identity)
    if type(identity) is not dict:
        _fail(f"schema profile identity is not an object: {profile.profile_id}")
    evaluator_identity = identity.get("evaluator")
    limits_identity = identity.get("limits")
    expected_limits = {
        "schema_nodes": profile.schema_node_limit,
        "local_references": profile.local_reference_limit,
        "local_reference_depth": profile.reference_depth_limit,
        "per_evaluation_shape_units": profile.per_evaluation_shape_limit,
        "combinator_alternatives": profile.combinator_alternative_limit,
        "combinator_depth": profile.combinator_depth_limit,
    }
    if (
        identity.get("profile_id") != profile.profile_id
        or identity.get("allowed_keywords") != list(profile.allowed_keywords)
        or identity.get("forbidden_keywords") != list(profile.forbidden_keywords)
        or type(limits_identity) is not dict
        or any(limits_identity.get(key) != value for key, value in expected_limits.items())
        or type(evaluator_identity) is not dict
        or evaluator_identity.get("evaluator_id") != profile.evaluator_id
        or evaluator_identity.get("type_checker_id") != profile.type_checker_id
        or evaluator_identity.get("format_policy_id") != profile.format_policy_id
        or evaluator_identity.get("reference_policy_id") != profile.reference_policy_id
        or evaluator_identity.get("metaschema_id") != profile.metaschema_id
        or evaluator_identity.get("metaschema_fingerprint")
        != profile.metaschema_fingerprint
    ):
        _fail(f"schema profile identity fields mismatch: {profile.profile_id}")
    expected_dependencies = [
        {"distribution": name, "version": version}
        for name, version in profile.runtime_dependencies
    ]
    if evaluator_identity.get("runtime_dependencies") != expected_dependencies:
        _fail(f"schema profile runtime dependency identity mismatch: {profile.profile_id}")
    return {
        "profile_id": profile.profile_id,
        "allowed_keywords": list(
            sorted(profile.allowed_keywords, key=utf16_sort_key)
        ),
        "forbidden_keywords": list(
            sorted(profile.forbidden_keywords, key=utf16_sort_key)
        ),
        "limits": expected_limits,
        "runtime_dependencies": expected_dependencies,
        "metaschema_id": profile.metaschema_id,
        "metaschema_fingerprint": profile.metaschema_fingerprint,
        "evaluator_id": profile.evaluator_id,
        "type_checker_id": profile.type_checker_id,
        "format_policy_id": profile.format_policy_id,
        "reference_policy_id": profile.reference_policy_id,
        "identity_fingerprint": identity_fingerprint,
    }


def _validate_schema_profiles(
    candidates: object,
) -> tuple[
    tuple[SchemaEvaluatorSpec, ...],
    dict[str, dict[str, object]],
    tuple[tuple[str, RuntimeComponentSpec], ...],
]:
    raw = _require_exact_tuple(candidates, "schema evaluator profiles")
    by_id: dict[str, SchemaEvaluatorSpec] = {}
    manifests: dict[str, dict[str, object]] = {}
    components: list[tuple[str, RuntimeComponentSpec]] = []
    for candidate in raw:
        if type(candidate) is not SchemaEvaluatorSpec:
            _fail("schema evaluator profile entries must be exact SchemaEvaluatorSpec values")
        if type(candidate.profile) is not SchemaProfile:
            _fail("schema evaluator profile must contain an exact SchemaProfile")
        profile_id = _require_machine_id(
            candidate.profile.profile_id, "schema profile ID"
        )
        if profile_id in by_id:
            _fail(f"duplicate schema profile identity: {profile_id}")
        component = _validate_component(
            candidate.evaluator, f"schema evaluator {profile_id}"
        )
        if (
            component.component_id != profile_id
            or component.implementation_id != candidate.profile.evaluator_id
        ):
            _fail(f"schema evaluator component mismatch: {profile_id}")
        by_id[profile_id] = candidate
        manifests[profile_id] = _schema_profile_manifest(candidate)
        components.append(("schema_evaluator", component))
    ordered_ids = sorted(by_id, key=utf16_sort_key)
    return (
        tuple(by_id[profile_id] for profile_id in ordered_ids),
        manifests,
        tuple(components),
    )


def _validate_schemas(
    candidates: object,
    profile_ids: frozenset[str],
) -> tuple[tuple[AdmittedSchema, ...], dict[str, dict[str, object]]]:
    raw = _require_exact_tuple(candidates, "schemas")
    by_id: dict[str, AdmittedSchema] = {}
    manifests: dict[str, dict[str, object]] = {}
    for candidate in raw:
        if type(candidate) is not AdmittedSchema:
            _fail("schema entries must be exact AdmittedSchema values")
        schema_id = _require_machine_id(candidate.schema_id, "schema ID")
        if schema_id in by_id:
            _fail(f"duplicate schema identity: {schema_id}")
        if candidate.profile_id not in profile_ids:
            _fail(f"schema references an unknown schema profile: {schema_id}")
        actual_fingerprint = _reference_canonical_fingerprint(candidate.value)
        if candidate.schema_fingerprint != actual_fingerprint:
            _fail(f"schema fingerprint mismatch: {schema_id}")
        if candidate.schema_nodes != count_json_nodes(candidate.value):
            _fail(f"schema node identity mismatch: {schema_id}")
        by_id[schema_id] = candidate
        manifests[schema_id] = {
            "schema_id": schema_id,
            "schema_fingerprint": candidate.schema_fingerprint,
            "profile_id": candidate.profile_id,
            "schema_nodes": candidate.schema_nodes,
            "local_reference_count": candidate.local_reference_count,
            "maximum_reference_depth": candidate.maximum_reference_depth,
        }
    ordered_ids = sorted(by_id, key=utf16_sort_key)
    return tuple(by_id[schema_id] for schema_id in ordered_ids), manifests


def _validate_invocation_inputs(
    candidates: object,
) -> tuple[tuple[InvocationInputSpec, ...], dict[str, InvocationInputSpec], list[dict[str, object]]]:
    raw = _require_exact_tuple(candidates, "invocation inputs")
    by_name: dict[str, InvocationInputSpec] = {}
    manifests: dict[str, dict[str, object]] = {}
    for candidate in raw:
        if type(candidate) is not InvocationInputSpec:
            _fail("invocation input entries must be exact InvocationInputSpec values")
        name = _require_machine_id(candidate.input_name, "invocation input name")
        if name in by_name:
            _fail(f"duplicate invocation input identity: {name}")
        _require_machine_id(candidate.value_type, "invocation input type")
        if candidate.cardinality not in _CARDINALITIES:
            _fail(f"invalid invocation input cardinality: {name}")
        by_name[name] = candidate
        manifests[name] = _fingerprinted_object(
            {
                "input_name": name,
                "value_type": candidate.value_type,
                "cardinality": candidate.cardinality,
            },
            "input_fingerprint",
        )
    names = sorted(by_name, key=utf16_sort_key)
    return tuple(by_name[name] for name in names), by_name, [manifests[name] for name in names]


def _validate_program_constants(
    candidates: object,
) -> tuple[tuple[ProgramConstantSpec, ...], dict[str, ProgramConstantSpec], list[dict[str, object]]]:
    raw = _require_exact_tuple(candidates, "program constants")
    by_name: dict[str, ProgramConstantSpec] = {}
    manifests: dict[str, dict[str, object]] = {}
    for candidate in raw:
        if type(candidate) is not ProgramConstantSpec:
            _fail("program constant entries must be exact ProgramConstantSpec values")
        name = _require_machine_id(candidate.constant_name, "program constant name")
        if name in by_name:
            _fail(f"duplicate program constant identity: {name}")
        _require_machine_id(candidate.value_type, "program constant type")
        if candidate.cardinality not in _CARDINALITIES:
            _fail(f"invalid program constant cardinality: {name}")
        if type(candidate.value) not in _OWNED_VALUE_TYPES:
            _fail(f"program constant must be exact owned JSON: {name}")
        value_fingerprint = _reference_canonical_fingerprint(candidate.value)
        by_name[name] = candidate
        manifests[name] = _fingerprinted_object(
            {
                "constant_name": name,
                "value_type": candidate.value_type,
                "cardinality": candidate.cardinality,
                "value_fingerprint": value_fingerprint,
            },
            "constant_fingerprint",
        )
    names = sorted(by_name, key=utf16_sort_key)
    return tuple(by_name[name] for name in names), by_name, [manifests[name] for name in names]


def _validate_runners(
    candidates: object,
) -> tuple[tuple[RuntimeComponentSpec, ...], dict[str, RuntimeComponentSpec]]:
    raw = _require_exact_tuple(candidates, "runners")
    by_id: dict[str, RuntimeComponentSpec] = {}
    for candidate in raw:
        component = _validate_component(candidate, "runner")
        if component.component_id in by_id:
            _fail(f"duplicate runner identity: {component.component_id}")
        by_id[component.component_id] = component
    names = sorted(by_id, key=utf16_sort_key)
    return tuple(by_id[name] for name in names), by_id


def _validate_issues(
    candidates: object,
) -> tuple[tuple[IssueSpec, ...], dict[str, IssueSpec], list[dict[str, object]]]:
    raw = _require_exact_tuple(candidates, "issue vocabulary")
    by_code: dict[str, IssueSpec] = {}
    manifests: dict[str, dict[str, object]] = {}
    for candidate in raw:
        if type(candidate) is not IssueSpec:
            _fail("issue vocabulary entries must be exact IssueSpec values")
        code = _require_machine_id(candidate.code, "issue code")
        if candidate.classification not in _ISSUE_CLASSIFICATIONS:
            _fail(f"invalid issue classification: {code}")
        if code in by_code:
            _fail(f"duplicate issue identity: {code}")
        by_code[code] = candidate
        manifests[code] = _fingerprinted_object(
            {"code": code, "classification": candidate.classification},
            "issue_fingerprint",
        )
    codes = sorted(by_code, key=utf16_sort_key)
    return tuple(by_code[code] for code in codes), by_code, [manifests[code] for code in codes]


def _validate_export_types(
    candidates: object,
) -> tuple[tuple[ExportTypeSpec, ...], dict[str, ExportTypeSpec]]:
    raw = _require_exact_tuple(candidates, "export types")
    by_type: dict[str, ExportTypeSpec] = {}
    for candidate in raw:
        if type(candidate) is not ExportTypeSpec:
            _fail("export type entries must be exact ExportTypeSpec values")
        export_type = _require_machine_id(candidate.export_type, "export type")
        component = _validate_component(candidate.validator, f"export type {export_type}")
        if component.component_id != export_type:
            _fail(f"export validator binding mismatch: {export_type}")
        if export_type in by_type:
            _fail(f"duplicate export type identity: {export_type}")
        by_type[export_type] = candidate
    names = sorted(by_type, key=utf16_sort_key)
    return tuple(by_type[name] for name in names), by_type


def _normalize_input_binding(binding: object, phase_name: str) -> InputBinding:
    if type(binding) is not InputBinding:
        _fail(f"phase {phase_name} input bindings must be exact InputBinding values")
    _require_machine_id(binding.input_name, f"phase {phase_name} input name")
    _require_machine_id(binding.expected_type, f"phase {phase_name} expected type")
    if binding.cardinality not in _CARDINALITIES:
        _fail(f"phase {phase_name} has an invalid input cardinality")
    expected_fields = {
        "invocation_input": ("source_input",),
        "program_constant": ("source_constant",),
        "phase_output": ("source_phase", "source_output"),
    }
    if binding.source_kind not in expected_fields:
        _fail(f"phase {phase_name} has an unknown input source kind")
    fields = {
        "source_input": binding.source_input,
        "source_constant": binding.source_constant,
        "source_phase": binding.source_phase,
        "source_output": binding.source_output,
    }
    required = expected_fields[binding.source_kind]
    if any(fields[name] is None for name in required) or any(
        value is not None for name, value in fields.items() if name not in required
    ):
        _fail(f"phase {phase_name} has ambiguous input binding fields")
    for name in required:
        _require_machine_id(fields[name], f"phase {phase_name} {name}")
    return binding


def _normalize_output(output: object, phase_name: str) -> ProvidedOutput:
    if type(output) is not ProvidedOutput:
        _fail(f"phase {phase_name} outputs must be exact ProvidedOutput values")
    _require_machine_id(output.output_name, f"phase {phase_name} output name")
    _require_machine_id(output.output_type, f"phase {phase_name} output type")
    if output.cardinality not in _CARDINALITIES:
        _fail(f"phase {phase_name} has an invalid output cardinality")
    permitted = _sorted_strings(
        output.permitted_on_statuses,
        f"phase {phase_name} permitted status",
        allowed=_OUTPUT_STATUSES,
        nonempty=True,
    )
    required = _sorted_strings(
        output.required_on_statuses,
        f"phase {phase_name} required status",
        allowed=_OUTPUT_STATUSES,
    )
    if not set(required).issubset(permitted):
        _fail(f"phase {phase_name} required status is not permitted")
    return replace(
        output,
        permitted_on_statuses=cast(tuple, permitted),
        required_on_statuses=cast(tuple, required),
    )


def _phase_manifest(phase: PhaseSpec) -> dict[str, object]:
    binding_manifests: list[dict[str, object]] = []
    for binding in phase.input_bindings:
        binding_manifests.append(
            _fingerprinted_object(
                {
                    "input_name": binding.input_name,
                    "source_kind": binding.source_kind,
                    "source_input": binding.source_input,
                    "source_constant": binding.source_constant,
                    "source_phase": binding.source_phase,
                    "source_output": binding.source_output,
                    "expected_type": binding.expected_type,
                    "cardinality": binding.cardinality,
                },
                "binding_fingerprint",
            )
        )
    output_manifests: list[dict[str, object]] = []
    for output in phase.provided_outputs:
        output_manifests.append(
            _fingerprinted_object(
                {
                    "output_name": output.output_name,
                    "output_type": output.output_type,
                    "cardinality": output.cardinality,
                    "permitted_on_statuses": list(output.permitted_on_statuses),
                    "required_on_statuses": list(output.required_on_statuses),
                },
                "output_fingerprint",
            )
        )
    return _fingerprinted_object(
        {
            "phase_name": phase.phase_name,
            "ordering_after": list(phase.ordering_after),
            "input_bindings": binding_manifests,
            "provided_outputs": output_manifests,
            "runner_id": phase.runner_id,
            "permitted_diagnostic_codes": list(
                phase.permitted_diagnostic_codes
            ),
            "permitted_blocker_codes": list(phase.permitted_blocker_codes),
        },
        "phase_fingerprint",
    )


def _validate_phases(
    candidates: object,
    *,
    invocation_inputs: Mapping[str, InvocationInputSpec],
    constants: Mapping[str, ProgramConstantSpec],
    runners: Mapping[str, RuntimeComponentSpec],
    issues: Mapping[str, IssueSpec],
    export_types: Mapping[str, ExportTypeSpec],
) -> tuple[
    tuple[PhaseSpec, ...],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    tuple[str, ...],
    list[dict[str, object]],
]:
    raw = _require_exact_tuple(candidates, "phases")
    by_name: dict[str, PhaseSpec] = {}
    for candidate in raw:
        if type(candidate) is not PhaseSpec:
            _fail("phase entries must be exact PhaseSpec values")
        name = _require_machine_id(candidate.phase_name, "phase name")
        if name in by_name:
            _fail(f"duplicate phase identity: {name}")
        _require_machine_id(candidate.runner_id, f"phase {name} runner ID")
        if candidate.runner_id not in runners:
            _fail(f"phase {name} references an unknown runner")
        ordering = _sorted_strings(
            candidate.ordering_after,
            f"phase {name} ordering producer",
            machine_ids=True,
        )
        bindings_raw = _require_exact_tuple(
            candidate.input_bindings, f"phase {name} input bindings"
        )
        bindings: dict[str, InputBinding] = {}
        for raw_binding in bindings_raw:
            binding = _normalize_input_binding(raw_binding, name)
            if binding.input_name in bindings:
                _fail(f"duplicate input identity in phase {name}: {binding.input_name}")
            bindings[binding.input_name] = binding
        outputs_raw = _require_exact_tuple(
            candidate.provided_outputs, f"phase {name} provided outputs"
        )
        outputs: dict[str, ProvidedOutput] = {}
        for raw_output in outputs_raw:
            output = _normalize_output(raw_output, name)
            if output.output_name in outputs:
                _fail(f"duplicate output identity in phase {name}: {output.output_name}")
            if output.output_type not in export_types:
                _fail(f"phase {name} references an unknown export type")
            outputs[output.output_name] = output
        diagnostic_codes = _sorted_strings(
            candidate.permitted_diagnostic_codes,
            f"phase {name} diagnostic code",
            machine_ids=True,
        )
        blocker_codes = _sorted_strings(
            candidate.permitted_blocker_codes,
            f"phase {name} blocker code",
            machine_ids=True,
        )
        for code in diagnostic_codes:
            issue = issues.get(code)
            if issue is None or issue.classification != "diagnostic":
                _fail(f"phase {name} references an unknown diagnostic code")
        for code in blocker_codes:
            issue = issues.get(code)
            if issue is None or issue.classification != "compile_blocker":
                _fail(f"phase {name} references an unknown blocker code")
        by_name[name] = replace(
            candidate,
            ordering_after=ordering,
            input_bindings=tuple(
                bindings[input_name]
                for input_name in sorted(bindings, key=utf16_sort_key)
            ),
            provided_outputs=tuple(
                outputs[output_name]
                for output_name in sorted(outputs, key=utf16_sort_key)
            ),
            permitted_diagnostic_codes=diagnostic_codes,
            permitted_blocker_codes=blocker_codes,
        )

    output_lookup = {
        phase_name: {output.output_name: output for output in phase.provided_outputs}
        for phase_name, phase in by_name.items()
    }
    data_dependencies: dict[str, tuple[str, ...]] = {}
    scheduling_dependencies: dict[str, tuple[str, ...]] = {}
    for phase_name, phase in by_name.items():
        for predecessor in phase.ordering_after:
            if predecessor not in by_name:
                _fail(f"phase {phase_name} references an unknown ordering producer")
            if predecessor == phase_name:
                _fail("phase scheduling cycle detected")
        data: set[str] = set()
        for binding in phase.input_bindings:
            if binding.source_kind == "invocation_input":
                source = invocation_inputs.get(cast(str, binding.source_input))
                if source is None:
                    _fail(f"phase {phase_name} references an unknown invocation input")
                if (
                    source.value_type != binding.expected_type
                    or source.cardinality != binding.cardinality
                ):
                    _fail(f"phase {phase_name} invocation input type or cardinality mismatch")
            elif binding.source_kind == "program_constant":
                source = constants.get(cast(str, binding.source_constant))
                if source is None:
                    _fail(f"phase {phase_name} references an unknown program constant")
                if (
                    source.value_type != binding.expected_type
                    or source.cardinality != binding.cardinality
                ):
                    _fail(f"phase {phase_name} program constant type or cardinality mismatch")
            else:
                source_phase = cast(str, binding.source_phase)
                if source_phase not in by_name:
                    _fail(f"phase {phase_name} references a missing producer")
                source_output = output_lookup[source_phase].get(
                    cast(str, binding.source_output)
                )
                if source_output is None:
                    _fail(f"phase {phase_name} references an unknown output")
                if source_output.output_type != binding.expected_type:
                    _fail(f"phase {phase_name} producer/consumer type mismatch")
                if source_output.cardinality != binding.cardinality:
                    _fail(f"phase {phase_name} producer/consumer cardinality mismatch")
                data.add(source_phase)
        data_tuple = tuple(sorted(data, key=utf16_sort_key))
        scheduling = tuple(
            sorted(data.union(phase.ordering_after), key=utf16_sort_key)
        )
        data_dependencies[phase_name] = data_tuple
        scheduling_dependencies[phase_name] = scheduling

    dependents: dict[str, list[str]] = {name: [] for name in by_name}
    indegree = {name: len(dependencies) for name, dependencies in scheduling_dependencies.items()}
    for phase_name, dependencies in scheduling_dependencies.items():
        for dependency in dependencies:
            dependents[dependency].append(phase_name)
    ready = sorted(
        (name for name, degree in indegree.items() if degree == 0),
        key=utf16_sort_key,
    )
    execution_order: list[str] = []
    while ready:
        current = ready.pop(0)
        execution_order.append(current)
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort(key=utf16_sort_key)
    if len(execution_order) != len(by_name):
        _fail("phase scheduling cycle detected")

    ordered_names = sorted(by_name, key=utf16_sort_key)
    ordered_phases = tuple(by_name[name] for name in ordered_names)
    return (
        ordered_phases,
        {name: data_dependencies[name] for name in ordered_names},
        {name: scheduling_dependencies[name] for name in ordered_names},
        tuple(execution_order),
        [_phase_manifest(by_name[name]) for name in ordered_names],
    )


def _is_json_pointer(value: object) -> bool:
    if type(value) is not str or not value.startswith("/"):
        return False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    index = 0
    while index < len(value):
        if value[index] == "~":
            if index + 1 == len(value) or value[index + 1] not in "01":
                return False
            index += 2
            continue
        index += 1
    return True


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _host_pointer(root: object, pointer: str) -> object | None:
    current = root
    if pointer == "":
        return current
    for raw_token in pointer.split("/")[1:]:
        token = _decode_pointer_token(raw_token)
        if type(current) is not dict or token not in current:
            return None
        current = current[token]
    return current


_AMBIGUOUS_SCHEMA_BRANCH_KEYWORDS = frozenset(
    ("allOf", "anyOf", "oneOf", "if", "then", "else", "not")
)
_AMBIGUOUS_OBJECT_SCHEMA_KEYWORDS = frozenset(
    ("patternProperties", "unevaluatedProperties")
)
_OBJECT_SCHEMA_KEYWORDS = frozenset(
    (
        "additionalProperties",
        "maxProperties",
        "minProperties",
        "properties",
        "required",
    )
) | _AMBIGUOUS_OBJECT_SCHEMA_KEYWORDS
_REFERENCE_ANNOTATION_KEYWORDS = frozenset(
    (
        "$comment",
        "$id",
        "$ref",
        "$schema",
        "default",
        "deprecated",
        "description",
        "examples",
        "readOnly",
        "title",
        "writeOnly",
    )
)


def _resolve_schema_reference(
    root: object,
    current: object,
    seen_references: set[str],
) -> tuple[object | None, str | None]:
    while type(current) is dict and type(current.get("$ref")) is str:
        if any(
            key not in _REFERENCE_ANNOTATION_KEYWORDS
            for key in current
        ):
            return None, "ambiguous"
        reference = cast(str, current["$ref"])
        if not reference.startswith("#") or reference in seen_references:
            return None, "ambiguous"
        seen_references.add(reference)
        current = _host_pointer(root, reference[1:])
        if current is None:
            return None, "missing"
    if type(current) is not dict:
        return None, "closed_or_scalar"
    if any(keyword in current for keyword in _AMBIGUOUS_SCHEMA_BRANCH_KEYWORDS):
        return None, "ambiguous"
    return current, None


def _object_schema_closure_error(schema: dict[str, object]) -> str | None:
    declared_type = schema.get("type")
    if type(declared_type) is list:
        if len(declared_type) != 1:
            return "ambiguous"
        declared_type = declared_type[0]
    if declared_type is None and any(
        keyword in schema for keyword in _OBJECT_SCHEMA_KEYWORDS
    ):
        return "ambiguous"
    if declared_type != "object":
        return None
    if any(keyword in schema for keyword in _AMBIGUOUS_OBJECT_SCHEMA_KEYWORDS):
        return "ambiguous"
    if schema.get("additionalProperties") is not False:
        return "open_object"
    return None


def _resolve_schema_instance_path(
    schema: AdmittedSchema,
    path: str,
) -> tuple[dict[str, object] | None, str | None]:
    root = _host_json(schema.value)
    current: object = root
    seen_references: set[str] = set()
    for raw_token in path.split("/")[1:]:
        current, error = _resolve_schema_reference(
            root,
            current,
            seen_references,
        )
        if error is not None or type(current) is not dict:
            return None, error
        closure_error = _object_schema_closure_error(current)
        if closure_error is not None:
            return None, closure_error
        token = _decode_pointer_token(raw_token)
        declared_type = current.get("type")
        if type(declared_type) is list:
            if len(declared_type) != 1:
                return None, "ambiguous"
            declared_type = declared_type[0]
        properties = current.get("properties")
        if declared_type == "object":
            if type(properties) is not dict or token not in properties:
                return None, "missing"
            current = properties[token]
            continue
        if declared_type == "array":
            if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                return None, "missing"
            index = int(token)
            prefix_items = current.get("prefixItems")
            if type(prefix_items) is list and index < len(prefix_items):
                current = prefix_items[index]
                continue
            items = current.get("items")
            if type(items) is not dict:
                return None, "missing"
            current = items
            continue
        if declared_type is None and (
            type(properties) is dict
            or "items" in current
            or "prefixItems" in current
        ):
            return None, "ambiguous"
        return None, "closed_or_scalar"
    current, error = _resolve_schema_reference(root, current, seen_references)
    if error is not None or type(current) is not dict:
        return None, error
    closure_error = _object_schema_closure_error(current)
    if closure_error is not None:
        return None, closure_error
    return cast(dict[str, object], current), None


def _validate_report_projection(
    candidate: object,
    *,
    phase_names: frozenset[str],
    schemas: Mapping[str, AdmittedSchema],
) -> ReportProjectionSpec:
    if type(candidate) is not ReportProjectionSpec:
        _fail("report projection must be an exact ReportProjectionSpec")
    _require_machine_id(candidate.projection_id, "report projection ID")
    _require_machine_id(candidate.implementation_id, "report projection implementation ID")
    _require_fingerprint(
        candidate.implementation_fingerprint,
        "report projection implementation fingerprint",
    )
    _require_module_name(candidate.source_module, "report projection source module")
    _require_machine_id(candidate.output_schema_id, "report output schema ID")
    _require_fingerprint(candidate.output_schema_fingerprint, "report output schema fingerprint")
    schema = schemas.get(candidate.output_schema_id)
    if schema is None or schema.schema_fingerprint != candidate.output_schema_fingerprint:
        _fail("report projection output schema identity mismatch")
    if candidate.input_envelope_fields != REPORT_PROJECTION_INPUT_ENVELOPE:
        _fail("report projection input envelope is not exact")
    if not _is_json_pointer(candidate.report_fingerprint_path):
        _fail("report fingerprint path is invalid")
    if not _is_json_pointer(candidate.budget_receipt_path):
        _fail("budget receipt path is invalid")
    if candidate.report_fingerprint_path != REPORT_FINGERPRINT_PATH:
        _fail("report fingerprint path does not match the fixed role")
    if candidate.budget_receipt_path != REPORT_BUDGET_RECEIPT_PATH:
        _fail("fixed budget receipt path does not match the candidate")
    excluded = _sorted_strings(
        candidate.fingerprint_excluded_paths,
        "report fingerprint exclusion",
    )
    if excluded != (candidate.report_fingerprint_path,):
        _fail("report fingerprint exclusion must name only the report fingerprint path")
    required = _sorted_strings(
        candidate.required_for_compile_phases,
        "required-for-compile phase",
        machine_ids=True,
    )
    if any(name not in phase_names for name in required):
        _fail("report projection contains an unknown required-for-compile phase")
    kernel_paths = _sorted_strings(
        candidate.kernel_owned_paths,
        "kernel-owned report path",
        nonempty=True,
    )
    if any(not _is_json_pointer(path) for path in kernel_paths):
        _fail("kernel-owned report path is invalid")
    if kernel_paths != KERNEL_OWNED_REPORT_PATHS:
        _fail("candidate does not match the fixed kernel-owned report paths")
    for role_name, path, expected_type in KERNEL_REPORT_FIELD_ROLES:
        role_schema, role_error = _resolve_schema_instance_path(schema, path)
        if (
            role_error is not None
            or type(role_schema) is not dict
            or role_schema.get("type") != expected_type
        ):
            _fail(
                f"{role_name.replace('_', ' ')} path does not match the output schema"
            )
    if (
        type(candidate.outer_envelope_field_count) is not int
        or candidate.outer_envelope_field_count
        != FIXED_REPORT_OUTER_ENVELOPE_FIELD_COUNT
    ):
        _fail("fixed outer envelope field count does not match the bootstrap role")
    writable = _sorted_strings(
        candidate.writable_body_paths,
        "projection-writable body path",
    )
    if any(not _is_json_pointer(path) for path in writable):
        _fail("projection-writable body path is invalid")
    for writable_path in writable:
        if any(_paths_overlap(writable_path, kernel_path) for kernel_path in kernel_paths):
            _fail("projection-writable body path overlaps a kernel-owned path")
        _, path_error = _resolve_schema_instance_path(schema, writable_path)
        if path_error == "ambiguous":
            _fail("projection-writable path has an ambiguous schema branch")
        if path_error == "closed_or_scalar":
            _fail("projection-writable path traverses a closed or scalar schema branch")
        if path_error == "open_object":
            _fail("projection-writable path is not explicitly closed")
        if path_error is not None:
            _fail("projection-writable path does not exist in the output schema")
    shells_raw = _require_exact_tuple(candidate.mandatory_shells, "mandatory shells")
    shells: dict[str, tuple[str, str]] = {}
    for shell in shells_raw:
        if (
            type(shell) is not tuple
            or len(shell) != 2
            or type(shell[0]) is not str
            or shell[1] not in ("object", "array")
            or not _is_json_pointer(shell[0])
        ):
            _fail("mandatory shell declaration is invalid")
        path = shell[0]
        if path in shells:
            _fail(f"duplicate mandatory shell identity: {path}")
        if not any(
            path == writable_path or path.startswith(writable_path + "/")
            for writable_path in writable
        ):
            _fail("mandatory shell is outside projection-writable body paths")
        shell_schema, shell_error = _resolve_schema_instance_path(schema, path)
        if (
            shell_error is not None
            or type(shell_schema) is not dict
            or shell_schema.get("type") != shell[1]
        ):
            _fail("mandatory shell does not match the output schema container")
        shells[path] = cast(tuple[str, str], shell)
    return replace(
        candidate,
        fingerprint_excluded_paths=excluded,
        required_for_compile_phases=required,
        kernel_owned_paths=kernel_paths,
        writable_body_paths=writable,
        mandatory_shells=tuple(
            shells[path] for path in sorted(shells, key=utf16_sort_key)
        ),
    )


def _validate_runtime_bindings(
    candidates: object,
    *,
    components: tuple[tuple[str, RuntimeComponentSpec], ...],
    schemas: tuple[AdmittedSchema, ...],
) -> dict[tuple[str, str], object]:
    expected: dict[tuple[str, str], RuntimeComponentSpec | AdmittedSchema] = {}
    for kind, component in components:
        key = (kind, component.component_id)
        if key in expected:
            _fail(f"duplicate runtime component identity: {kind}/{component.component_id}")
        expected[key] = component
    for schema in schemas:
        key = ("schema", schema.schema_id)
        if key in expected:
            _fail(f"duplicate runtime component identity: schema/{schema.schema_id}")
        expected[key] = schema

    raw = _require_exact_tuple(candidates, "runtime bindings")
    supplied: dict[tuple[str, str], RuntimeBinding] = {}
    for candidate in raw:
        if type(candidate) is not RuntimeBinding:
            _fail("runtime binding entries must be exact RuntimeBinding values")
        if candidate.binding_kind not in _RUNTIME_BINDING_KINDS:
            _fail("runtime binding has an unknown kind")
        _require_machine_id(candidate.binding_id, "runtime binding ID")
        _require_fingerprint(
            candidate.implementation_fingerprint,
            "runtime binding fingerprint",
        )
        key = (candidate.binding_kind, candidate.binding_id)
        if key in supplied:
            _fail(f"duplicate runtime binding identity: {candidate.binding_kind}/{candidate.binding_id}")
        supplied[key] = candidate
    missing = set(expected).difference(supplied)
    extra = set(supplied).difference(expected)
    if missing:
        _fail("missing runtime binding")
    if extra:
        _fail("extra runtime binding")

    captured: dict[tuple[str, str], object] = {}
    for key in sorted(expected, key=lambda item: (utf16_sort_key(item[0]), utf16_sort_key(item[1]))):
        declaration = expected[key]
        binding = supplied[key]
        if type(declaration) is AdmittedSchema:
            if (
                binding.implementation_fingerprint != declaration.schema_fingerprint
                or binding.target is not declaration
            ):
                _fail("runtime schema binding fingerprint or payload mismatch")
        else:
            target_function = _validate_runtime_callable(binding.target)
            if target_function.__module__ != declaration.source_module:
                _fail("runtime binding source module mismatch")
            if binding.implementation_fingerprint != declaration.implementation_fingerprint:
                _fail("runtime binding fingerprint mismatch")
            actual_fingerprint = runtime_implementation_fingerprint(binding.target)
            if actual_fingerprint != declaration.implementation_fingerprint:
                _fail("runtime component fingerprint mismatch")
        captured[key] = binding.target
    return captured


def _analysis_nodes(
    tree: ast.Module,
    *,
    module_scope_only: bool,
) -> tuple[ast.AST, ...]:
    if not module_scope_only:
        return tuple(ast.walk(tree))

    nodes: list[ast.AST] = []

    class ModuleScopeVisitor(ast.NodeVisitor):
        def generic_visit(self, node: ast.AST) -> None:
            nodes.append(node)
            super().generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            nodes.append(node)
            for decorator in node.decorator_list:
                self.visit(decorator)
            self.visit(node.args)
            if node.returns is not None:
                self.visit(node.returns)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            nodes.append(node)
            for decorator in node.decorator_list:
                self.visit(decorator)
            self.visit(node.args)
            if node.returns is not None:
                self.visit(node.returns)

        def visit_Lambda(self, node: ast.Lambda) -> None:
            nodes.append(node)
            self.visit(node.args)

    ModuleScopeVisitor().visit(tree)
    return tuple(nodes)


def _assignment_names(target: ast.expr) -> tuple[str, ...]:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, ast.Starred):
        return _assignment_names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return tuple(
            name
            for element in target.elts
            for name in _assignment_names(element)
        )
    return ()


def _has_indirect_assignment_target(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return False
    if isinstance(target, ast.Starred):
        return _has_indirect_assignment_target(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_has_indirect_assignment_target(element) for element in target.elts)
    return True


def _default_parameter_bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
) -> tuple[tuple[str, ast.expr], ...]:
    positional = (*node.args.posonlyargs, *node.args.args)
    positional_bindings = tuple(
        (argument.arg, default)
        for argument, default in zip(
            positional[-len(node.args.defaults) :],
            node.args.defaults,
            strict=True,
        )
    ) if node.args.defaults else ()
    keyword_bindings = tuple(
        (argument.arg, default)
        for argument, default in zip(
            node.args.kwonlyargs,
            node.args.kw_defaults,
            strict=True,
        )
        if default is not None
    )
    return positional_bindings + keyword_bindings


def _reject_dynamic_import_calls(
    module_name: str,
    nodes: tuple[ast.AST, ...],
) -> None:
    importlib_modules: set[str] = set()
    builtins_modules: set[str] = {"__builtins__"}
    dynamic_functions: set[str] = {"__import__"}
    getattr_functions: set[str] = {"getattr"}
    safe_importlib_bindings: dict[str, str] = {}
    safe_importlib_root_children: dict[str, dict[str, str]] = {}

    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    _fail(
                        f"dynamic import root is forbidden in sealed source: {module_name}"
                    )
                if alias.name.startswith("importlib.") and (
                    alias.name not in _SAFE_IMPORTLIB_SUBMODULES
                ):
                    _fail(
                        f"dynamic import capability is forbidden in sealed source: {module_name}"
                    )
                if alias.name in _SAFE_IMPORTLIB_SUBMODULES:
                    if alias.asname is None:
                        root_name, child_name = alias.name.split(".", 1)
                        safe_importlib_root_children.setdefault(root_name, {})[
                            child_name
                        ] = alias.name
                    else:
                        safe_importlib_bindings[alias.asname] = alias.name
                if alias.name == "builtins":
                    _fail(
                        f"dynamic import builtins root is forbidden in sealed source: {module_name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module == "importlib":
                for alias in node.names:
                    qualified_name = f"importlib.{alias.name}"
                    if qualified_name not in _SAFE_IMPORTLIB_SUBMODULES:
                        _fail(
                            f"dynamic import capability is forbidden in sealed source: {module_name}"
                        )
                    safe_importlib_bindings[
                        alias.asname or alias.name
                    ] = qualified_name
            if (
                node.level == 0
                and node.module is not None
                and node.module.startswith("importlib.")
                and node.module not in _SAFE_IMPORTLIB_SUBMODULES
            ):
                _fail(
                    f"dynamic import capability is forbidden in sealed source: {module_name}"
                )
            if node.level == 0 and node.module in _SAFE_IMPORTLIB_SUBMODULES:
                allowed_members = _SAFE_IMPORTLIB_SUBMODULE_MEMBERS[node.module]
                if any(alias.name not in allowed_members for alias in node.names):
                    _fail(
                        f"dynamic import capability is forbidden in sealed source: {module_name}"
                    )
            if node.level == 0 and node.module == "builtins":
                for alias in node.names:
                    if alias.name == "__import__":
                        dynamic_functions.add(alias.asname or alias.name)
                    if alias.name == "getattr":
                        getattr_functions.add(alias.asname or alias.name)

    if any(
        isinstance(node, ast.Name) and node.id == "__builtins__"
        for node in nodes
    ):
        _fail(f"dynamic import builtins authority is forbidden in sealed source: {module_name}")

    parents = {
        id(child): parent
        for parent in nodes
        for child in ast.iter_child_nodes(parent)
    }
    for node in nodes:
        if not isinstance(node, ast.Name):
            continue
        child_modules = safe_importlib_root_children.get(node.id)
        if child_modules is None:
            continue
        parent = parents.get(id(node))
        if not (
            isinstance(parent, ast.Attribute)
            and parent.value is node
            and parent.attr in child_modules
        ):
            _fail(
                f"dynamic import root use is forbidden in sealed source: {module_name}"
            )

    def safe_importlib_module(expression: ast.expr) -> str | None:
        if isinstance(expression, ast.Name):
            return safe_importlib_bindings.get(expression.id)
        if isinstance(expression, ast.Attribute) and isinstance(
            expression.value,
            ast.Name,
        ):
            return safe_importlib_root_children.get(
                expression.value.id,
                {},
            ).get(expression.attr)
        return None

    for node in nodes:
        if not isinstance(node, ast.expr):
            continue
        safe_module = safe_importlib_module(node)
        if safe_module is None:
            continue
        parent = parents.get(id(node))
        if not (
            isinstance(parent, ast.Attribute)
            and parent.value is node
            and parent.attr in _SAFE_IMPORTLIB_SUBMODULE_MEMBERS[safe_module]
        ):
            _fail(
                f"dynamic import capability is forbidden in sealed source: {module_name}"
            )

    def expression_role(expression: ast.expr) -> str | None:
        if isinstance(expression, ast.Name):
            if expression.id in dynamic_functions:
                return "dynamic_function"
            if expression.id in importlib_modules:
                return "importlib_module"
            if expression.id in builtins_modules:
                return "builtins_module"
            if expression.id in getattr_functions:
                return "getattr_function"
            return None
        if isinstance(expression, ast.Attribute):
            owner_role = expression_role(expression.value)
            if owner_role == "importlib_module" and expression.attr == "import_module":
                return "dynamic_function"
            if owner_role == "builtins_module" and expression.attr == "__import__":
                return "dynamic_function"
            if owner_role == "builtins_module" and expression.attr == "getattr":
                return "getattr_function"
            return None
        if isinstance(expression, ast.Subscript):
            if (
                not isinstance(expression.slice, ast.Constant)
                or type(expression.slice.value) is not str
            ):
                return None
            owner = expression.value
            if isinstance(owner, ast.Attribute) and owner.attr == "__dict__":
                owner = owner.value
            owner_role = expression_role(owner)
            attribute = cast(str, expression.slice.value)
            if owner_role == "importlib_module" and attribute == "import_module":
                return "dynamic_function"
            if owner_role == "builtins_module" and attribute == "__import__":
                return "dynamic_function"
            return None
        if isinstance(expression, ast.Call):
            if expression_role(expression.func) != "getattr_function":
                return None
            if (
                len(expression.args) < 2
                or not isinstance(expression.args[1], ast.Constant)
                or type(expression.args[1].value) is not str
            ):
                return None
            owner_role = expression_role(expression.args[0])
            attribute = cast(str, expression.args[1].value)
            if owner_role == "importlib_module" and attribute == "import_module":
                return "dynamic_function"
            if owner_role == "builtins_module" and attribute == "__import__":
                return "dynamic_function"
        return None

    changed = True
    while changed:
        changed = False
        for node in nodes:
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
            ):
                for name, default in _default_parameter_bindings(node):
                    role = expression_role(default)
                    if role is None:
                        continue
                    destination = {
                        "dynamic_function": dynamic_functions,
                        "importlib_module": importlib_modules,
                        "builtins_module": builtins_modules,
                        "getattr_function": getattr_functions,
                    }[role]
                    if name not in destination:
                        destination.add(name)
                        changed = True
            value: ast.expr | None = None
            targets: tuple[ast.expr, ...] = ()
            if isinstance(node, ast.Assign):
                value = node.value
                targets = tuple(node.targets)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value = node.value
                targets = (node.target,)
            elif isinstance(node, ast.NamedExpr):
                value = node.value
                targets = (node.target,)
            if value is None:
                continue
            role = expression_role(value)
            if role is None:
                continue
            for target in targets:
                if _has_indirect_assignment_target(target):
                    _fail(
                        f"dynamic import alias is forbidden in sealed source: {module_name}"
                    )
                for name in _assignment_names(target):
                    destination = {
                        "dynamic_function": dynamic_functions,
                        "importlib_module": importlib_modules,
                        "builtins_module": builtins_modules,
                        "getattr_function": getattr_functions,
                    }[role]
                    if name not in destination:
                        destination.add(name)
                        changed = True

    if any(
        isinstance(node, ast.expr)
        and expression_role(node) == "dynamic_function"
        for node in nodes
    ):
        _fail(f"dynamic import is forbidden in sealed source: {module_name}")


def _absolute_imports(
    module_name: str,
    source: str,
    *,
    module_scope_only: bool = False,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        tree = ast.parse(source, filename=module_name)
    except SyntaxError as error:
        raise ProgramCompositionError(
            f"implementation source cannot be parsed: {module_name}"
        ) from error
    nodes = _analysis_nodes(tree, module_scope_only=module_scope_only)
    origin = _module_origin(module_name)
    guard_nodes = (
        tuple(ast.walk(tree))
        if origin is not None and origin.name.lower() == "__init__.py"
        else nodes
    )
    _reject_dynamic_import_calls(module_name, guard_nodes)
    imports: set[str] = set()
    package_aliases: dict[str, str] = {}
    referenced_packages: set[str] = set()

    def is_package(candidate: str) -> bool:
        candidate_origin = _module_origin(candidate)
        return (
            candidate_origin is not None
            and candidate_origin.name.lower() == "__init__.py"
        )

    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                local_name = alias.asname or alias.name.split(".", 1)[0]
                imported_name = alias.name if alias.asname else local_name
                if is_package(imported_name):
                    package_aliases[local_name] = imported_name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = (
                    module_name
                    if origin is not None and origin.name.lower() == "__init__.py"
                    else module_name.rpartition(".")[0]
                )
                if not package:
                    _fail(f"relative import has no package: {module_name}")
                relative = "." * node.level + (node.module or "")
                try:
                    base = importlib_util.resolve_name(relative, package)
                except (ImportError, ValueError) as error:
                    raise ProgramCompositionError(
                        f"relative import cannot be resolved: {module_name}"
                    ) from error
            else:
                base = node.module or ""
            if base:
                imports.add(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if is_package(base):
                    referenced_packages.add(base)
                candidate = f"{base}.{alias.name}" if base else alias.name
                if _module_origin(candidate) is not None:
                    imports.add(candidate)
                if is_package(candidate):
                    package_aliases[alias.asname or alias.name] = candidate
    for node in nodes:
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            continue
        package_name = package_aliases.get(node.value.id)
        if package_name is not None:
            referenced_packages.add(package_name)
    return (
        tuple(sorted(imports, key=utf16_sort_key)),
        tuple(sorted(referenced_packages, key=utf16_sort_key)),
    )


def _module_origin(module_name: str) -> Path | None:
    module = sys.modules.get(module_name)
    origin = getattr(module, "__file__", None) if module is not None else None
    if type(origin) is not str:
        spec = _module_spec_without_import(module_name)
        origin = spec.origin if spec is not None else None
    if type(origin) is not str or origin in ("built-in", "frozen"):
        return None
    return Path(origin).resolve()


def _module_import_root(module_name: str, source_path: Path) -> Path:
    levels = len(module_name.split("."))
    if source_path.name.lower() != "__init__.py":
        levels -= 1
    root = source_path.parent
    for _ in range(levels):
        root = root.parent
    return root


def _path_is_under(path: Path, roots: frozenset[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _derive_product_source_closure(
    entry_modules: frozenset[str],
) -> tuple[
    tuple[ImplementationSource, ...],
    dict[str, str],
    dict[str, tuple[str, ...]],
]:
    if not entry_modules:
        _fail("behavior source entry modules cannot be empty")
    source_roots: set[Path] = set()
    for module_name in entry_modules:
        _require_module_name(module_name, "behavior source entry module")
        _, _, source_path = _read_module_source(module_name)
        source_roots.add(_module_import_root(module_name, source_path))
    frozen_roots = frozenset(source_roots)

    pending: dict[str, bool] = {}
    processed: dict[str, bool] = {}
    normalized_sources: dict[str, str] = {}
    fingerprints: dict[str, str] = {}
    imports_by_module: dict[str, set[str]] = {}

    def is_product_source(module_name: str) -> bool:
        origin = _module_origin(module_name)
        return (
            origin is not None
            and origin.suffix.lower() in (".py", ".pyw")
            and _path_is_under(origin, frozen_roots)
        )

    def enqueue(module_name: str, *, full_behavior: bool) -> None:
        if not is_product_source(module_name):
            return
        previous = processed.get(module_name)
        if previous is True or (previous is False and not full_behavior):
            return
        pending[module_name] = pending.get(module_name, False) or full_behavior

    def enqueue_package_initializers(module_name: str) -> None:
        parts = module_name.split(".")
        for index in range(1, len(parts)):
            package_name = ".".join(parts[:index])
            origin = _module_origin(package_name)
            if (
                origin is not None
                and origin.name.lower() == "__init__.py"
                and _path_is_under(origin, frozen_roots)
            ):
                enqueue(package_name, full_behavior=False)

    for module_name in entry_modules:
        enqueue(module_name, full_behavior=True)
        enqueue_package_initializers(module_name)

    while pending:
        module_name = min(pending, key=utf16_sort_key)
        full_behavior = pending.pop(module_name)
        previous = processed.get(module_name)
        if previous is True or (previous is False and not full_behavior):
            continue
        raw, normalized, _ = _read_module_source(module_name)
        normalized_sources[module_name] = normalized
        fingerprints[module_name] = normalized_source_fingerprint(raw)
        imports, referenced_packages = _absolute_imports(
            module_name,
            normalized,
            module_scope_only=not full_behavior,
        )
        imports_by_module.setdefault(module_name, set()).update(imports)
        processed[module_name] = bool(previous) or full_behavior
        for imported in imports:
            if is_product_source(imported):
                enqueue(imported, full_behavior=True)
                enqueue_package_initializers(imported)
        for package_name in referenced_packages:
            enqueue(package_name, full_behavior=True)
            enqueue_package_initializers(package_name)

    names = sorted(normalized_sources, key=utf16_sort_key)
    sources = tuple(
        ImplementationSource(
            module_name=name,
            source_fingerprint=fingerprints[name],
        )
        for name in names
    )
    return (
        sources,
        normalized_sources,
        {
            name: tuple(sorted(imports, key=utf16_sort_key))
            for name, imports in imports_by_module.items()
        },
    )


def implementation_source_closure_for_modules(
    module_names: tuple[str, ...],
) -> tuple[ImplementationSource, ...]:
    """Derive the exact normalized product-source closure for behavior modules."""

    raw = _require_exact_tuple(module_names, "behavior source entry modules")
    entries: set[str] = set()
    for module_name in raw:
        name = _require_module_name(module_name, "behavior source entry module")
        if name in entries:
            _fail(f"duplicate behavior source entry module: {name}")
        entries.add(name)
    sources, _, _ = _derive_product_source_closure(frozenset(entries))
    return sources


def _validate_implementation_sources(
    candidates: object,
    expected_sources: tuple[ImplementationSource, ...],
) -> tuple[ImplementationSource, ...]:
    raw = _require_exact_tuple(candidates, "implementation sources")
    by_module: dict[str, ImplementationSource] = {}
    for candidate in raw:
        if type(candidate) is not ImplementationSource:
            _fail("implementation source entries must be exact ImplementationSource values")
        module_name = _require_module_name(candidate.module_name, "implementation source module")
        if module_name in by_module:
            _fail(f"duplicate implementation source identity: {module_name}")
        _require_fingerprint(candidate.source_fingerprint, "implementation source fingerprint")
        raw_source, _, _ = _read_module_source(module_name)
        actual = normalized_source_fingerprint(raw_source)
        if candidate.source_fingerprint != actual:
            _fail(f"source fingerprint mismatch: {module_name}")
        by_module[module_name] = candidate
    expected_by_module = {
        source.module_name: source for source in expected_sources
    }
    missing = set(expected_by_module).difference(by_module)
    extra = set(by_module).difference(expected_by_module)
    if missing:
        _fail("missing implementation source declaration")
    if extra:
        _fail("extra implementation source declaration")
    names = sorted(by_module, key=utf16_sort_key)
    return tuple(by_module[name] for name in names)


def _normalized_distribution_name(name: str) -> str:
    if type(name) is not str or not name:
        _fail("runtime dependency name must be a nonempty exact string")
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    if _DISTRIBUTION_NAME_RE.fullmatch(normalized) is None:
        _fail("runtime dependency name is not a valid PEP 503 identity")
    return normalized


def _package_distribution_map() -> dict[str, tuple[str, ...]]:
    return {
        package.casefold(): tuple(
            sorted(
                {
                    _normalized_distribution_name(distribution)
                    for distribution in distributions
                },
                key=utf16_sort_key,
            )
        )
        for package, distributions in importlib_metadata.packages_distributions().items()
    }


def _direct_imported_distributions(
    imports_by_module: Mapping[str, tuple[str, ...]],
    product_modules: frozenset[str],
) -> frozenset[str]:
    package_distributions = _package_distribution_map()
    distributions: set[str] = set()
    for module_name, imports in imports_by_module.items():
        for imported in imports:
            if imported in product_modules:
                continue
            top_level = imported.split(".", 1)[0]
            if top_level in sys.stdlib_module_names:
                continue
            owners = package_distributions.get(top_level.casefold(), ())
            if owners:
                distributions.update(owners)
                continue
            _fail(
                "import cannot be resolved to product, standard-library, or "
                f"distribution authority: {module_name}/{imported}"
            )
    return frozenset(distributions)


def _derive_runtime_dependency_projections(
    imports_by_module: Mapping[str, tuple[str, ...]],
    product_modules: frozenset[str],
    direct_distribution_names: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    required_extras: dict[str, set[str]] = {}

    def require(name: str, extras: tuple[str, ...] = ()) -> None:
        normalized_name = _normalized_distribution_name(name)
        normalized_extras = {
            _normalized_distribution_name(extra) for extra in extras
        }
        current = required_extras.setdefault(normalized_name, set())
        current.update(normalized_extras)

    for name in _direct_imported_distributions(
        imports_by_module,
        product_modules,
    ):
        require(name)
    seen_direct: set[str] = set()
    for name in direct_distribution_names:
        if type(name) is not str or not name:
            _fail("direct runtime dependency name must be a nonempty exact string")
        normalized_name = _normalized_distribution_name(name)
        if normalized_name in seen_direct:
            _fail(f"duplicate direct runtime dependency identity: {normalized_name}")
        seen_direct.add(normalized_name)
        require(normalized_name)

    projections: dict[str, dict[str, object]] = {}
    processed_extras: dict[str, frozenset[str]] = {}
    while True:
        pending = sorted(
            (
                name
                for name, extras in required_extras.items()
                if processed_extras.get(name) != frozenset(extras)
            ),
            key=utf16_sort_key,
        )
        if not pending:
            break
        name = pending[0]
        extras = frozenset(required_extras[name])
        projection = _installed_dependency_projection(
            name,
            activated_extras=extras,
        )
        projections[name] = projection
        processed_extras[name] = extras
        for requirement in cast(
            list[dict[str, object]],
            projection["active_runtime_requirements"],
        ):
            dependency_name = cast(str, requirement["distribution_name"])
            dependency_extras = tuple(cast(list[str], requirement["extras"]))
            require(dependency_name, dependency_extras)
            specifier = cast(str, requirement["specifier"])
            if specifier:
                try:
                    installed_version = importlib_metadata.version(dependency_name)
                except importlib_metadata.PackageNotFoundError as error:
                    raise ProgramCompositionError(
                        f"transitive runtime dependency is not installed: {dependency_name}"
                    ) from error
                parsed = Requirement(f"{dependency_name}{specifier}")
                if not parsed.specifier.contains(installed_version, prereleases=True):
                    _fail(
                        f"transitive runtime dependency version is incompatible: {dependency_name}"
                    )
    return projections


def _dependency_spec_from_projection(
    projection: Mapping[str, object],
) -> RuntimeDependencySpec:
    return RuntimeDependencySpec(
        distribution_name=cast(str, projection["distribution_name"]),
        expected_version=cast(str, projection["version"]),
        behavior_files=tuple(
            cast(str, item["path"])
            for item in cast(
                list[dict[str, object]],
                projection["behavior_files"],
            )
        ),
        distribution_fingerprint=cast(
            str,
            projection["distribution_fingerprint"],
        ),
    )


def runtime_dependency_closure_for_modules(
    module_names: tuple[str, ...],
    direct_distribution_names: tuple[str, ...],
) -> tuple[RuntimeDependencySpec, ...]:
    """Derive active installed distribution closure for exact behavior modules."""

    raw_modules = _require_exact_tuple(module_names, "behavior source entry modules")
    entries: set[str] = set()
    for module_name in raw_modules:
        name = _require_module_name(module_name, "behavior source entry module")
        if name in entries:
            _fail(f"duplicate behavior source entry module: {name}")
        entries.add(name)
    raw_distributions = _require_exact_tuple(
        direct_distribution_names,
        "direct runtime dependencies",
    )
    direct_names = tuple(
        cast(str, name)
        for name in raw_distributions
    )
    sources, _, imports_by_module = _derive_product_source_closure(
        frozenset(entries)
    )
    projections = _derive_runtime_dependency_projections(
        imports_by_module,
        frozenset(source.module_name for source in sources),
        direct_names,
    )
    return tuple(
        _dependency_spec_from_projection(projections[name])
        for name in sorted(projections, key=utf16_sort_key)
    )


def _validate_runtime_dependencies(
    candidates: object,
    schema_profiles: tuple[SchemaEvaluatorSpec, ...],
    expected_projections: Mapping[str, dict[str, object]],
) -> tuple[tuple[RuntimeDependencySpec, ...], list[dict[str, object]]]:
    raw = _require_exact_tuple(candidates, "runtime dependencies")
    by_name: dict[str, RuntimeDependencySpec] = {}
    for candidate in raw:
        if type(candidate) is not RuntimeDependencySpec:
            _fail("runtime dependency entries must be exact RuntimeDependencySpec values")
        name = candidate.distribution_name
        if type(name) is not str or not name:
            _fail("runtime dependency name must be a nonempty exact string")
        normalized_name = _normalized_distribution_name(name)
        if normalized_name in by_name:
            _fail(f"duplicate runtime dependency identity: {normalized_name}")
        if name != normalized_name:
            _fail(f"runtime dependency name is not PEP 503 normalized: {name}")
        _require_fingerprint(
            candidate.distribution_fingerprint,
            "runtime dependency fingerprint",
        )
        projection = expected_projections.get(normalized_name)
        if projection is None:
            by_name[normalized_name] = candidate
            continue
        if candidate.expected_version != projection["version"]:
            _fail(f"runtime dependency version mismatch: {name}")
        actual_behavior_files = tuple(
            cast(str, item["path"])
            for item in cast(list[dict[str, object]], projection["behavior_files"])
        )
        if candidate.behavior_files != actual_behavior_files:
            _fail(f"runtime dependency behavior-file projection mismatch: {name}")
        if candidate.distribution_fingerprint != projection["distribution_fingerprint"]:
            _fail(f"runtime dependency fingerprint mismatch: {name}")
        by_name[normalized_name] = candidate
    missing = set(expected_projections).difference(by_name)
    extra = set(by_name).difference(expected_projections)
    if missing:
        _fail("missing runtime dependency from derived closure")
    if extra:
        _fail("extra runtime dependency outside derived closure")
    for profile_spec in schema_profiles:
        for name, version in profile_spec.profile.runtime_dependencies:
            normalized_name = _normalized_distribution_name(name)
            if name != normalized_name:
                _fail("schema profile runtime dependency is not PEP 503 normalized")
            dependency = by_name.get(normalized_name)
            if dependency is None:
                _fail(f"missing runtime dependency required by schema profile: {name}")
            if dependency.expected_version != version:
                _fail(f"schema profile dependency version mismatch: {name}")
    names = sorted(by_name, key=utf16_sort_key)
    return (
        tuple(by_name[name] for name in names),
        [expected_projections[name] for name in names],
    )


def _kernel_bootstrap_identity() -> tuple[str, str, str]:
    source_identities: list[dict[str, str]] = []
    source_fingerprints: dict[str, str] = {}
    for module_name in _FIXED_KERNEL_MODULES:
        raw, _, _ = _read_module_source(module_name)
        fingerprint = normalized_source_fingerprint(raw)
        source_fingerprints[module_name] = fingerprint
        source_identities.append(
            {"module_name": module_name, "source_fingerprint": fingerprint}
        )
    build_fingerprint = _reference_canonical_fingerprint(
        _owned_object(
            {"kernel_abi_version": KERNEL_ABI_VERSION, "sources": source_identities},
            "kernel build identity",
        )
    )
    return (
        build_fingerprint,
        source_fingerprints["rook.validation_kernel.program"],
        runtime_implementation_fingerprint(_reference_canonical_json_bytes),
    )


def _python_runtime_manifest() -> dict[str, object]:
    identity = {
        "implementation": sys.implementation.name,
        "version": list(sys.version_info[:5]),
        "cache_tag": sys.implementation.cache_tag,
    }
    if type(identity["cache_tag"]) is not str:
        _fail("Python runtime cache tag is unavailable")
    return _fingerprinted_object(identity, "runtime_fingerprint")


@dataclass(frozen=True, slots=True, init=False, eq=False)
class SealedValidationProgram:
    """A non-deserializable immutable capability for one exact program."""

    program_id: str
    program_fingerprint: str
    manifest_bytes: bytes
    phases: tuple[PhaseSpec, ...]
    data_dependencies: Mapping[str, tuple[str, ...]]
    scheduling_dependencies: Mapping[str, tuple[str, ...]]
    execution_order: tuple[str, ...]
    runtime_binding_keys: tuple[tuple[str, str], ...]
    budget_manifest: BudgetManifest
    parser_profile: ParserProfileSpec
    schema_evaluator_profiles: tuple[SchemaEvaluatorSpec, ...]
    schemas: tuple[AdmittedSchema, ...]
    invocation_inputs: tuple[InvocationInputSpec, ...]
    program_constants: tuple[ProgramConstantSpec, ...]
    report_projection: ReportProjectionSpec
    _runtime_bindings: Mapping[tuple[str, str], object]
    _constant_bindings: Mapping[str, JsonValue]

    def __init__(self) -> None:
        raise TypeError("SealedValidationProgram values are created only by compose_and_seal_program")

    @classmethod
    def _create(
        cls,
        token: object,
        *,
        program_id: str,
        program_fingerprint: str,
        manifest_bytes: bytes,
        phases: tuple[PhaseSpec, ...],
        data_dependencies: dict[str, tuple[str, ...]],
        scheduling_dependencies: dict[str, tuple[str, ...]],
        execution_order: tuple[str, ...],
        runtime_bindings: dict[tuple[str, str], object],
        budget_manifest: BudgetManifest,
        parser_profile: ParserProfileSpec,
        schema_evaluator_profiles: tuple[SchemaEvaluatorSpec, ...],
        schemas: tuple[AdmittedSchema, ...],
        invocation_inputs: tuple[InvocationInputSpec, ...],
        program_constants: tuple[ProgramConstantSpec, ...],
        report_projection: ReportProjectionSpec,
    ) -> "SealedValidationProgram":
        if token is not _SEALED_PROGRAM_TOKEN:
            raise TypeError("invalid sealed-program issuer")
        sealed = object.__new__(cls)
        object.__setattr__(sealed, "program_id", program_id)
        object.__setattr__(sealed, "program_fingerprint", program_fingerprint)
        object.__setattr__(sealed, "manifest_bytes", bytes(manifest_bytes))
        object.__setattr__(sealed, "phases", tuple(phases))
        object.__setattr__(
            sealed,
            "data_dependencies",
            MappingProxyType(dict(data_dependencies)),
        )
        object.__setattr__(
            sealed,
            "scheduling_dependencies",
            MappingProxyType(dict(scheduling_dependencies)),
        )
        object.__setattr__(sealed, "execution_order", tuple(execution_order))
        captured_bindings = dict(runtime_bindings)
        object.__setattr__(
            sealed,
            "runtime_binding_keys",
            tuple(
                sorted(
                    captured_bindings,
                    key=lambda item: (
                        utf16_sort_key(item[0]),
                        utf16_sort_key(item[1]),
                    ),
                )
            ),
        )
        object.__setattr__(
            sealed, "_runtime_bindings", MappingProxyType(captured_bindings)
        )
        object.__setattr__(sealed, "budget_manifest", budget_manifest)
        object.__setattr__(sealed, "parser_profile", parser_profile)
        object.__setattr__(
            sealed, "schema_evaluator_profiles", tuple(schema_evaluator_profiles)
        )
        object.__setattr__(sealed, "schemas", tuple(schemas))
        object.__setattr__(sealed, "invocation_inputs", tuple(invocation_inputs))
        object.__setattr__(sealed, "program_constants", tuple(program_constants))
        object.__setattr__(sealed, "report_projection", report_projection)
        object.__setattr__(
            sealed,
            "_constant_bindings",
            MappingProxyType(
                {constant.constant_name: constant.value for constant in program_constants}
            ),
        )
        return sealed

    def resolve_runtime_binding(self, binding_kind: str, binding_id: str) -> object:
        """Resolve only from the immutable binding map captured at seal time."""

        return self._runtime_bindings[(binding_kind, binding_id)]

    def resolve_program_constant(self, constant_name: str) -> JsonValue:
        return self._constant_bindings[constant_name]

    def resolve_manifest_bytes(self, program_fingerprint: str) -> bytes:
        if program_fingerprint != self.program_fingerprint:
            raise KeyError(program_fingerprint)
        return self.manifest_bytes


def _compose_contribution(contribution: ValidationProgramContribution) -> SealedValidationProgram:
    program_id = _require_machine_id(contribution.program_id, "program ID")
    budget, budget_manifest = _validate_budget(contribution.budget_manifest)
    parser_profile, parser_components = _validate_parser_profile(
        contribution.parser_profile
    )
    schema_profiles, schema_profile_manifests, evaluator_components = (
        _validate_schema_profiles(contribution.schema_evaluator_profiles)
    )
    schemas, schema_manifests = _validate_schemas(
        contribution.schemas,
        frozenset(spec.profile.profile_id for spec in schema_profiles),
    )
    invocation_inputs, invocation_input_map, invocation_input_manifests = (
        _validate_invocation_inputs(contribution.invocation_inputs)
    )
    constants, constant_map, constant_manifests = _validate_program_constants(
        contribution.program_constants
    )
    runners, runner_map = _validate_runners(contribution.runners)
    issues, issue_map, issue_manifests = _validate_issues(
        contribution.issue_vocabulary
    )
    export_types, export_map = _validate_export_types(contribution.export_types)
    (
        phases,
        data_dependencies,
        scheduling_dependencies,
        execution_order,
        phase_manifests,
    ) = _validate_phases(
        contribution.phases,
        invocation_inputs=invocation_input_map,
        constants=constant_map,
        runners=runner_map,
        issues=issue_map,
        export_types=export_map,
    )
    schemas_by_id = {schema.schema_id: schema for schema in schemas}
    projection = _validate_report_projection(
        contribution.report_projection,
        phase_names=frozenset(phase.phase_name for phase in phases),
        schemas=schemas_by_id,
    )
    projection_component = RuntimeComponentSpec(
        component_id=projection.projection_id,
        implementation_id=projection.implementation_id,
        implementation_fingerprint=projection.implementation_fingerprint,
        source_module=projection.source_module,
    )
    components = (
        parser_components
        + evaluator_components
        + tuple(("runner", runner) for runner in runners)
        + tuple(("export_type", export_type.validator) for export_type in export_types)
        + (("report_projection", projection_component),)
    )
    runtime_bindings = _validate_runtime_bindings(
        contribution.runtime_bindings,
        components=components,
        schemas=schemas,
    )
    expected_source_modules = frozenset(
        _target_source_module(target)
        for (binding_kind, _), target in runtime_bindings.items()
        if binding_kind != "schema"
    )
    (
        expected_implementation_sources,
        _,
        source_imports,
    ) = _derive_product_source_closure(expected_source_modules)
    implementation_sources = _validate_implementation_sources(
        contribution.implementation_sources,
        expected_implementation_sources,
    )
    direct_profile_dependencies = tuple(
        sorted(
            {
                name
                for profile_spec in schema_profiles
                for name, _ in profile_spec.profile.runtime_dependencies
            },
            key=utf16_sort_key,
        )
    )
    expected_dependency_projections = _derive_runtime_dependency_projections(
        source_imports,
        frozenset(
            source.module_name for source in expected_implementation_sources
        ),
        direct_profile_dependencies,
    )
    runtime_dependencies, dependency_manifests = _validate_runtime_dependencies(
        contribution.runtime_dependencies,
        schema_profiles,
        expected_dependency_projections,
    )

    def component_manifest(kind: str, component: RuntimeComponentSpec) -> dict[str, object]:
        return _runtime_component_manifest(
            component,
            runtime_bindings[(kind, component.component_id)],
        )

    parser_manifest = {
        "profile_id": parser_profile.profile_id,
        "tokenizer": component_manifest("tokenizer", parser_profile.tokenizer),
        "parser": component_manifest("parser", parser_profile.parser),
        "canonicalizer": component_manifest(
            "canonicalizer", parser_profile.canonicalizer
        ),
        "ledger": component_manifest("ledger", parser_profile.ledger),
        "tokenizer_version": parser_profile.tokenizer_version,
        "parser_version": parser_profile.parser_version,
        "owned_value_abi": parser_profile.owned_value_abi,
        "canonicalization_version": parser_profile.canonicalization_version,
    }
    parser_manifest = _fingerprinted_object(
        parser_manifest, "profile_fingerprint"
    )
    complete_schema_profile_manifests: list[dict[str, object]] = []
    for spec in schema_profiles:
        manifest = schema_profile_manifests[spec.profile.profile_id]
        complete_schema_profile_manifests.append(
            {
                **manifest,
                "evaluator": component_manifest("schema_evaluator", spec.evaluator),
            }
        )
    runner_manifests = [
        component_manifest("runner", runner) for runner in runners
    ]
    export_manifests = []
    for export_type in export_types:
        entry = {
            "export_type": export_type.export_type,
            "validator": component_manifest("export_type", export_type.validator),
        }
        export_manifests.append(
            _fingerprinted_object(entry, "export_fingerprint")
        )
    projection_target = runtime_bindings[
        ("report_projection", projection.projection_id)
    ]
    projection_state_json, projection_state_fingerprint = _component_record_state(
        projection_target
    )
    projection_manifest = {
        "projection_id": projection.projection_id,
        "implementation_id": projection.implementation_id,
        "implementation_fingerprint": projection.implementation_fingerprint,
        "source_module": projection.source_module,
        "callable_record_state_canonical_json": projection_state_json,
        "callable_record_state_fingerprint": projection_state_fingerprint,
        "output_schema_id": projection.output_schema_id,
        "output_schema_fingerprint": projection.output_schema_fingerprint,
        "report_fingerprint_path": projection.report_fingerprint_path,
        "fingerprint_excluded_paths": list(projection.fingerprint_excluded_paths),
        "input_envelope_fields": list(projection.input_envelope_fields),
        "required_for_compile_phases": list(
            projection.required_for_compile_phases
        ),
        "kernel_owned_paths": list(projection.kernel_owned_paths),
        "budget_receipt_path": projection.budget_receipt_path,
        "writable_body_paths": list(projection.writable_body_paths),
        "mandatory_shells": [
            {"path": path, "container_kind": kind}
            for path, kind in projection.mandatory_shells
        ],
        "outer_envelope_field_count": projection.outer_envelope_field_count,
    }
    projection_manifest = _fingerprinted_object(
        projection_manifest, "projection_fingerprint"
    )
    kernel_build_fingerprint, seal_fingerprint, reference_jcs_fingerprint = (
        _kernel_bootstrap_identity()
    )
    manifest_without_program_fingerprint: dict[str, object] = {
        "schema": PROGRAM_MANIFEST_SCHEMA_ID,
        "program_id": program_id,
        "kernel_abi_version": KERNEL_ABI_VERSION,
        "kernel_build_fingerprint": kernel_build_fingerprint,
        "program_seal_profile": PROGRAM_SEAL_PROFILE,
        "program_seal_implementation_fingerprint": seal_fingerprint,
        "bootstrap_seal": {
            "manifest_schema_id": PROGRAM_MANIFEST_SCHEMA_ID,
            "manifest_schema_fingerprint": PROGRAM_MANIFEST_SCHEMA_FINGERPRINT,
            "canonicalization_version": "rook.canonical_json:v1",
            "reference_canonicalizer_id": REFERENCE_CANONICALIZER_ID,
            "reference_canonicalizer_fingerprint": reference_jcs_fingerprint,
            "hash_algorithm": "sha256",
            "hash_implementation_id": "python.hashlib.sha256:v1",
        },
        "budget_manifest": budget_manifest,
        "parser_profile": parser_manifest,
        "schema_evaluator_profiles": complete_schema_profile_manifests,
        "schemas": [schema_manifests[schema.schema_id] for schema in schemas],
        "invocation_inputs": invocation_input_manifests,
        "program_constants": constant_manifests,
        "phases": phase_manifests,
        "runners": runner_manifests,
        "issue_vocabulary": issue_manifests,
        "export_types": export_manifests,
        "report_projection": projection_manifest,
        "implementation_sources": [
            {
                "module_name": source.module_name,
                "source_fingerprint": source.source_fingerprint,
            }
            for source in implementation_sources
        ],
        "runtime_dependencies": dependency_manifests,
        "python_runtime": _python_runtime_manifest(),
    }
    manifest_value = _owned_object(
        manifest_without_program_fingerprint, "program manifest"
    )
    program_fingerprint = _reference_canonical_fingerprint(manifest_value)
    final_manifest = _owned_object(
        {
            **manifest_without_program_fingerprint,
            "program_fingerprint": program_fingerprint,
        },
        "final program manifest",
    )
    manifest_bytes = _reference_canonical_json_bytes(final_manifest)
    return SealedValidationProgram._create(
        _SEALED_PROGRAM_TOKEN,
        program_id=program_id,
        program_fingerprint=program_fingerprint,
        manifest_bytes=manifest_bytes,
        phases=phases,
        data_dependencies=data_dependencies,
        scheduling_dependencies=scheduling_dependencies,
        execution_order=execution_order,
        runtime_bindings=runtime_bindings,
        budget_manifest=budget,
        parser_profile=parser_profile,
        schema_evaluator_profiles=schema_profiles,
        schemas=schemas,
        invocation_inputs=invocation_inputs,
        program_constants=constants,
        report_projection=projection,
    )


class _ValidationProgramBuilder:
    """Private mutable staging object consumed exactly once by composition."""

    __slots__ = ("_contribution", "_consumed")

    def __init__(self, contribution: ValidationProgramContribution) -> None:
        self._contribution: ValidationProgramContribution | None = contribution
        self._consumed = False

    @property
    def consumed(self) -> bool:
        return self._consumed

    def seal(self) -> SealedValidationProgram:
        if self._consumed:
            raise RuntimeError("validation program builder has been consumed")
        contribution = self._contribution
        self._contribution = None
        self._consumed = True
        if contribution is None:
            raise RuntimeError("validation program builder has been consumed")
        return _compose_contribution(contribution)


def compose_and_seal_program(
    contribution: ValidationProgramContribution,
) -> SealedValidationProgram:
    """Validate all candidate authority, consume one builder, and return one program."""

    if type(contribution) is not ValidationProgramContribution:
        _fail("program contribution must be an exact ValidationProgramContribution")
    return _ValidationProgramBuilder(contribution).seal()


__all__ = (
    "KERNEL_ABI_VERSION",
    "PROGRAM_SEAL_PROFILE",
    "REPORT_PROJECTION_INPUT_ENVELOPE",
    "SealedValidationProgram",
    "compose_and_seal_program",
    "implementation_source_closure_for_modules",
    "implementation_source_for_module",
    "runtime_dependency_closure_for_modules",
    "runtime_dependency_spec",
    "runtime_implementation_fingerprint",
)
