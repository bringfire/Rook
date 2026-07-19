"""Frozen inputs, rendering, and evidence writing for LM9B-C."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from lm9b_c_compiler_sufficiency_support import (
    COMPILER_RESULT_SCHEMA,
    EVALUATION_REPORT_SCHEMA,
    CompilerSessionResult,
    EvaluatorAttemptResult,
    ObservationDecision,
    TerminalValidationResult,
)
from rook.validation_kernel.canonical_json import (
    canonical_fingerprint,
    sha256_prefixed,
)
from rook.validation_kernel.owned_json import own_trusted_json


MANIFEST_SCHEMA_ID = "rook.lm9b_c.input_manifest:v1"
COMPILER_RENDERER_ID = "lm9b_c.compiler_request_renderer:v2"
EVALUATOR_RENDERER_ID = "lm9b_c.evaluator_request_renderer:v2"


@dataclass(frozen=True)
class InputRecord:
    role: str
    relative_path: str
    raw_sha256: str
    canonical_fingerprint: str
    raw_bytes: bytes
    value: Mapping[str, object]


@dataclass(frozen=True)
class FrozenProbeInputs:
    fixture_dir: Path
    manifest: Mapping[str, object]
    records: tuple[InputRecord, ...]
    recipe_bytes: bytes
    recipe: Mapping[str, object]
    authority_artifacts: Mapping[str, Mapping[str, object]]
    authority_bytes: Mapping[str, bytes]
    implementation_context_bytes: bytes
    implementation_context: Mapping[str, object]
    exclusion_policy_bytes: bytes
    exclusion_policy: Mapping[str, object]
    evaluation_rubric_bytes: bytes
    evaluation_rubric: Mapping[str, object]
    contract_index: Mapping[str, object]


@dataclass(frozen=True)
class RenderedRequest:
    renderer_id: str
    system_prompt: bytes
    user_prompt: bytes

    @property
    def system_prompt_sha256(self) -> str:
        return sha256_prefixed(self.system_prompt)

    @property
    def user_prompt_sha256(self) -> str:
        return sha256_prefixed(self.user_prompt)


def _canonical(value: object) -> str:
    return canonical_fingerprint(own_trusted_json(value))


def _load_json(raw: bytes, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"{label} is not exact UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _without(value: Mapping[str, object], field: str) -> dict[str, object]:
    return {key: item for key, item in value.items() if key != field}


def walk_json(value: object):
    stack = [value]
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, dict):
            stack.extend(reversed(tuple(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))


def derive_contract_index(recipe: Mapping[str, object]) -> dict[str, object]:
    maintains = recipe["maintains"]
    postconditions = [
        postcondition["clause_id"]
        for maintained in maintains
        for postcondition in maintained["postconditions"]
    ]
    support_ids: set[str] = {
        item["assumption_id"] for item in recipe["assumptions"]
    }
    support_ids.update(item["derived_fact_id"] for item in recipe["derived_facts"])
    for item in walk_json(recipe):
        if isinstance(item, dict) and item.get("kind") == "artifact_value":
            support_ids.add(f'{item["artifact_id"]}:{item["json_pointer"]}')
    return {
        "recipe_fingerprint": recipe["recipe_fingerprint"],
        "maintains_clause_ids": [item["clause_id"] for item in maintains],
        "requires_clause_ids": [item["clause_id"] for item in recipe["requires"]],
        "invariant_clause_ids": [item["clause_id"] for item in recipe["invariants"]],
        "postcondition_clause_ids": postconditions,
        "shape_delegation_ids": [
            item["shape_id"] for item in recipe["shape"]["delegates"]
        ],
        "capability_ids": [
            item["capability_id"]
            for item in recipe["required_capabilities"]["entries"]
        ],
        "support_ids": sorted(support_ids),
    }


def derive_legal_trace_reference_catalog(
    contract_index: Mapping[str, object],
) -> dict[str, object]:
    """Project exactly the identifier vocabulary accepted by trace validation."""

    return {
        "capability_ids": list(contract_index["capability_ids"]),
        "maintains_clause_ids": list(contract_index["maintains_clause_ids"]),
        "material_support_ids": list(contract_index["support_ids"]),
        "postcondition_clause_ids": list(contract_index["postcondition_clause_ids"]),
        "requires_or_invariant_clause_ids": sorted(
            [
                *contract_index["requires_clause_ids"],
                *contract_index["invariant_clause_ids"],
            ]
        ),
        "shape_delegation_ids": list(contract_index["shape_delegation_ids"]),
    }


def load_frozen_inputs(fixture_dir: Path) -> FrozenProbeInputs:
    fixture_dir = Path(fixture_dir).resolve()
    manifest_raw = (fixture_dir / "input_manifest.json").read_bytes()
    manifest = _load_json(manifest_raw, "input manifest")
    if manifest.get("schema") != MANIFEST_SCHEMA_ID:
        raise ValueError("unexpected input manifest schema")
    if manifest.get("renderer_id") != COMPILER_RENDERER_ID:
        raise ValueError("input manifest binds an unexpected compiler renderer")

    rows = manifest.get("records")
    if not isinstance(rows, list) or not rows:
        raise ValueError("input manifest requires records")
    roles: set[str] = set()
    paths: set[str] = set()
    records: list[InputRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("input manifest records must be objects")
        role = row.get("role")
        relative_path = row.get("path")
        if not isinstance(role, str) or role in roles:
            raise ValueError("input manifest roles must be unique strings")
        if not isinstance(relative_path, str) or relative_path in paths:
            raise ValueError("input manifest paths must be unique strings")
        roles.add(role)
        paths.add(relative_path)
        path = (fixture_dir / relative_path).resolve()
        if path.parent != fixture_dir:
            raise ValueError("input manifest paths must be direct fixture children")
        raw = path.read_bytes()
        value = _load_json(raw, relative_path)
        raw_hash = sha256_prefixed(raw)
        canonical_hash = _canonical(value)
        if raw_hash != row.get("raw_sha256"):
            raise ValueError(f"raw hash mismatch for {relative_path}")
        if canonical_hash != row.get("canonical_fingerprint"):
            raise ValueError(f"canonical fingerprint mismatch for {relative_path}")
        records.append(
            InputRecord(
                role=role,
                relative_path=relative_path,
                raw_sha256=raw_hash,
                canonical_fingerprint=canonical_hash,
                raw_bytes=raw,
                value=value,
            )
        )
    by_role = {record.role: record for record in records}
    expected_roles = {
        "recipe",
        "authority.task_envelope",
        "authority.environment_snapshot",
        "authority.planning_policy",
        "implementation_context",
        "exclusion_policy",
        "evaluation_rubric",
    }
    if set(by_role) != expected_roles:
        raise ValueError("input manifest roles do not match the frozen probe boundary")

    authority_records = {
        role.removeprefix("authority."): record
        for role, record in by_role.items()
        if role.startswith("authority.")
    }
    for artifact_id, record in authority_records.items():
        artifact = record.value
        if artifact.get("artifact_id") != artifact_id:
            raise ValueError(f"authority artifact ID mismatch for {artifact_id}")
        expected = _canonical(_without(artifact, "artifact_fingerprint"))
        if artifact.get("artifact_fingerprint") != expected:
            raise ValueError(f"authority fingerprint mismatch for {artifact_id}")

    recipe_record = by_role["recipe"]
    recipe = recipe_record.value
    expected_recipe = _canonical(_without(recipe, "recipe_fingerprint"))
    if recipe.get("recipe_fingerprint") != expected_recipe:
        raise ValueError("recipe fingerprint does not match the frozen recipe")
    descriptors = [recipe["source_task"], *recipe["authority_artifacts"]]
    for descriptor in descriptors:
        artifact_id = descriptor["artifact_id"]
        record = authority_records.get(artifact_id)
        if record is None:
            raise ValueError(f"recipe authority descriptor is unbound: {artifact_id}")
        if descriptor["fingerprint"] != record.value["artifact_fingerprint"]:
            raise ValueError(f"recipe authority fingerprint mismatch: {artifact_id}")

    return FrozenProbeInputs(
        fixture_dir=fixture_dir,
        manifest=manifest,
        records=tuple(records),
        recipe_bytes=recipe_record.raw_bytes,
        recipe=recipe,
        authority_artifacts={
            artifact_id: record.value
            for artifact_id, record in authority_records.items()
        },
        authority_bytes={
            artifact_id: record.raw_bytes
            for artifact_id, record in authority_records.items()
        },
        implementation_context_bytes=by_role["implementation_context"].raw_bytes,
        implementation_context=by_role["implementation_context"].value,
        exclusion_policy_bytes=by_role["exclusion_policy"].raw_bytes,
        exclusion_policy=by_role["exclusion_policy"].value,
        evaluation_rubric_bytes=by_role["evaluation_rubric"].raw_bytes,
        evaluation_rubric=by_role["evaluation_rubric"].value,
        contract_index=derive_contract_index(recipe),
    )


def _semantic_source(inputs: FrozenProbeInputs) -> dict[str, object]:
    record_by_role = {record.role: record for record in inputs.records}
    return {
        "recipe": {
            "raw_sha256": record_by_role["recipe"].raw_sha256,
            "canonical_fingerprint": record_by_role["recipe"].canonical_fingerprint,
            "artifact": inputs.recipe,
        },
        "authority_artifacts": [
            {
                "artifact_id": artifact_id,
                "raw_sha256": record_by_role[f"authority.{artifact_id}"].raw_sha256,
                "canonical_fingerprint": record_by_role[
                    f"authority.{artifact_id}"
                ].canonical_fingerprint,
                "artifact": inputs.authority_artifacts[artifact_id],
            }
            for artifact_id in sorted(inputs.authority_artifacts)
        ],
        "authority_rule": (
            "Complete companions may contain unreferenced values. Only recipe-declared "
            "reference traversal authorizes a material compiler decision."
        ),
    }


def render_compiler_request(inputs: FrozenProbeInputs) -> RenderedRequest:
    system = """You are the bounded intelligent compiler in an offline empirical probe.

Lower the supplied semantic contract into the one admitted inert representation, or
report that the contract is insufficient. Use only the supplied semantic source and
implementation context. Do not invent material values, targets, authority, or verifier
truth. You may reconsider after mechanical container feedback within this same session.
Submit the terminal artifact only through submit_compiler_result. Do not request tools,
retrieval, execution, or hidden context. Do not include hidden reasoning.
""".encode("utf-8")
    payload = {
        "schema": "rook.lm9b_c.compiler_request:v1",
        "semantic_source": _semantic_source(inputs),
        "implementation_context": inputs.implementation_context,
        "legal_trace_reference_catalog": derive_legal_trace_reference_catalog(
            inputs.contract_index
        ),
        "terminal_result_schema": COMPILER_RESULT_SCHEMA,
    }
    user = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return RenderedRequest(
        renderer_id=COMPILER_RENDERER_ID,
        system_prompt=system,
        user_prompt=user,
    )


def _trace_projection(trace: TerminalValidationResult) -> dict[str, object]:
    return {
        "result_kind": trace.result_kind,
        "schema_valid": trace.schema_valid,
        "trace_valid": trace.trace_valid,
        "errors": [asdict(error) for error in trace.errors],
        "csharp_preflight_ok": trace.csharp_preflight_ok,
        "csharp_preflight_code": trace.csharp_preflight_code,
        "representation_contract_ok": trace.representation_contract_ok,
        "representation_contract_error_codes": list(
            trace.representation_contract_error_codes
        ),
        "csharp_compiled": trace.csharp_compiled,
    }


def render_evaluator_request(
    inputs: FrozenProbeInputs,
    terminal_result: Mapping[str, object],
    trace: TerminalValidationResult,
) -> RenderedRequest:
    system = """You are the independent evaluator for an offline compiler probe.

Compare the terminal result directly with the complete semantic source, generic
implementation context, deterministic trace result, and frozen rubric. Do not repair the
compiler artifact, infer authority from its prose, or authorize execution. Submit exactly
one evaluation through submit_evaluation_result. Do not include hidden reasoning.
""".encode("utf-8")
    payload = {
        "schema": "rook.lm9b_c.evaluator_request:v1",
        "semantic_source": _semantic_source(inputs),
        "implementation_context": inputs.implementation_context,
        "terminal_result": terminal_result,
        "deterministic_trace_check": _trace_projection(trace),
        "evaluation_rubric": inputs.evaluation_rubric,
        "evaluation_report_schema": EVALUATION_REPORT_SCHEMA,
    }
    user = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return RenderedRequest(
        renderer_id=EVALUATOR_RENDERER_ID,
        system_prompt=system,
        user_prompt=user,
    )


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def write_probe_evidence(
    *,
    run_dir: Path,
    inputs: FrozenProbeInputs,
    compiler_request: RenderedRequest,
    compiler_session: CompilerSessionResult,
    evaluator_request: RenderedRequest | None,
    evaluator_result: EvaluatorAttemptResult | None,
    decision: ObservationDecision,
    run_metadata: Mapping[str, object],
) -> None:
    """Write complete local evidence without excerpts or semantic repair."""

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(
        run_dir / "manifest.json",
        {
            "schema": "rook.lm9b_c.run_manifest:v1",
            "run": dict(run_metadata),
            "input_manifest": inputs.manifest,
            "compiler_renderer": {
                "renderer_id": compiler_request.renderer_id,
                "system_prompt_sha256": compiler_request.system_prompt_sha256,
                "user_prompt_sha256": compiler_request.user_prompt_sha256,
            },
            "evaluator_renderer": (
                {
                    "renderer_id": evaluator_request.renderer_id,
                    "system_prompt_sha256": evaluator_request.system_prompt_sha256,
                    "user_prompt_sha256": evaluator_request.user_prompt_sha256,
                }
                if evaluator_request is not None
                else None
            ),
        },
    )
    _write_bytes(run_dir / "inputs" / "recipe.json", inputs.recipe_bytes)
    for artifact_id, raw in inputs.authority_bytes.items():
        _write_bytes(run_dir / "inputs" / "authority" / f"{artifact_id}.json", raw)
    _write_bytes(
        run_dir / "inputs" / "implementation_context" / "context.json",
        inputs.implementation_context_bytes,
    )
    _write_bytes(
        run_dir / "inputs" / "exclusion_policy.json",
        inputs.exclusion_policy_bytes,
    )
    _write_bytes(
        run_dir / "inputs" / "evaluation_rubric.json",
        inputs.evaluation_rubric_bytes,
    )
    _write_bytes(
        run_dir / "prompts" / "compiler_system.txt",
        compiler_request.system_prompt,
    )
    _write_bytes(
        run_dir / "prompts" / "compiler_user.json",
        compiler_request.user_prompt,
    )
    _write_json(run_dir / "schemas" / "compiler_result.json", COMPILER_RESULT_SCHEMA)
    _write_json(run_dir / "schemas" / "evaluation_report.json", EVALUATION_REPORT_SCHEMA)

    for turn in compiler_session.turns:
        turn_dir = run_dir / "compiler" / "turns" / f"turn-{turn.turn_number:02d}"
        _write_json(turn_dir / "controller_request.json", turn.controller_request)
        _write_bytes(turn_dir / "raw_request.json", turn.raw_provider_request)
        _write_bytes(turn_dir / "raw_response.json", turn.raw_provider_response)
        _write_json(turn_dir / "assistant_message.json", turn.assistant_message)
        _write_json(turn_dir / "usage.json", turn.usage)
        _write_json(turn_dir / "provider_metadata.json", turn.provider_metadata)
        _write_json(turn_dir / "feedback.json", {"codes": list(turn.feedback_codes)})
        _write_json(turn_dir / "timing.json", {"elapsed_s": turn.elapsed_s})
    _write_json(
        run_dir / "compiler" / "session_summary.json",
        compiler_session.to_summary(),
    )
    if compiler_session.control_evidence is not None:
        _write_json(
            run_dir / "compiler" / "control_failure.json",
            compiler_session.control_evidence,
        )
    if compiler_session.raw_control_request is not None:
        _write_bytes(
            run_dir / "compiler" / "raw_control_request.json",
            compiler_session.raw_control_request,
        )
    if compiler_session.raw_control_error is not None:
        _write_bytes(
            run_dir / "compiler" / "raw_control_error.json",
            compiler_session.raw_control_error,
        )
    if compiler_session.terminal_submission is not None:
        _write_json(
            run_dir / "compiler" / "terminal_result.json",
            compiler_session.terminal_submission,
        )
    _write_json(
        run_dir / "deterministic_trace_check.json",
        (
            _trace_projection(compiler_session.terminal_validation)
            if compiler_session.terminal_validation is not None
            else {"available": False}
        ),
    )

    evaluator_summary = {
        "attempted": evaluator_request is not None,
        "stop_reason": evaluator_result.stop_reason if evaluator_result else None,
        "validation_errors": (
            list(evaluator_result.validation_errors) if evaluator_result else []
        ),
        "control_error": evaluator_result.control_error if evaluator_result else None,
        "control_evidence": (
            evaluator_result.control_evidence if evaluator_result else None
        ),
        "usage": dict(evaluator_result.usage) if evaluator_result and evaluator_result.usage else None,
        "provider_metadata": (
            dict(evaluator_result.provider_metadata)
            if evaluator_result and evaluator_result.provider_metadata
            else None
        ),
        "elapsed_s": evaluator_result.elapsed_s if evaluator_result else None,
    }
    _write_json(run_dir / "evaluator" / "summary.json", evaluator_summary)
    if evaluator_request is not None:
        _write_bytes(
            run_dir / "evaluator" / "system_prompt.txt",
            evaluator_request.system_prompt,
        )
        _write_bytes(
            run_dir / "evaluator" / "request.json",
            evaluator_request.user_prompt,
        )
    if evaluator_result is not None and evaluator_result.raw_provider_response is not None:
        _write_bytes(
            run_dir / "evaluator" / "raw_response.json",
            evaluator_result.raw_provider_response,
        )
    if evaluator_result is not None and evaluator_result.raw_provider_request is not None:
        _write_bytes(
            run_dir / "evaluator" / "raw_request.json",
            evaluator_result.raw_provider_request,
        )
    if evaluator_result is not None and evaluator_result.raw_provider_error is not None:
        _write_bytes(
            run_dir / "evaluator" / "raw_error.json",
            evaluator_result.raw_provider_error,
        )
    if evaluator_result is not None and evaluator_result.report is not None:
        _write_json(run_dir / "evaluator" / "report.json", evaluator_result.report)
    _write_json(
        run_dir / "decision.json",
        {"outcome": decision.outcome, "reason_codes": list(decision.reason_codes)},
    )


__all__ = (
    "COMPILER_RENDERER_ID",
    "EVALUATOR_RENDERER_ID",
    "FrozenProbeInputs",
    "InputRecord",
    "RenderedRequest",
    "derive_contract_index",
    "derive_legal_trace_reference_catalog",
    "load_frozen_inputs",
    "render_compiler_request",
    "render_evaluator_request",
    "walk_json",
    "write_probe_evidence",
)
