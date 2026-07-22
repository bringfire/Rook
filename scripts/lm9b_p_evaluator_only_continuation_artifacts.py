"""Artifacts for the LM9B-P evaluator-only derivative continuation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence


_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _import_path in (_SCRIPTS_DIR, _MCP_SRC):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

import lm9b_p_planner_recipe_transfer_artifacts as PLANNER_ARTIFACTS
import lm9b_p_planner_recipe_transfer_support as SUPPORT
import lm9b_p_readiness_contract as READINESS
from rook.agent.model_profiles import api_key_env_for_model


PREFLIGHT_SCHEMA_ID = "rook.lm9b_p.evaluator_continuation_preflight:v1"
DERIVATIVE_SCHEMA_ID = "rook.lm9b_p.evaluator_continuation_derivative:v1"
UNSEALED_SCHEMA_ID = (
    "rook.lm9b_p.evaluator_continuation_post_dispatch_unsealed:v1"
)
PREFLIGHT_CHECKSUMS_SCHEMA_ID = (
    "rook.lm9b_p.evaluator_continuation_preflight_checksums:v1"
)
ALLOWED_DELTA_SCHEMA_ID = (
    "rook.lm9b_p.evaluator_continuation_allowed_delta_manifest:v1"
)
SOURCE_BINDING_SCHEMA_ID = (
    "rook.lm9b_p.evaluator_continuation_source_binding:v1"
)
PROVIDER_PROFILE_ID = "litellm.completion.tool_calling.no_parallel:v1"
EVALUATOR_MODEL = "gpt-5.4"
EVALUATOR_TEMPERATURE = 0.0
CORRECTED_RUBRIC_PATH = (
    _SCRIPTS_DIR / "lm9b_p_fixtures" / "planner_evaluation_rubric.json"
)
ATTEMPT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9A-Fa-f]{64}$")
_PREFLIGHT_MEMBERS = {
    "record.json": "preflight_record",
    "source-binding.json": "source_binding",
    "allowed-delta-manifest.json": "allowed_delta_manifest",
    "mechanical-gate.json": "mechanical_gate",
    "rendered-evaluator-request.json": "rendered_evaluator_request",
    "provider-call-request.json": "provider_call_request",
}
_SOURCE_IDENTITY_KEYS = {
    "source_root",
    "root_manifest_raw_sha256",
    "checkpoint_aggregate_identity",
    "historical_commit_sha",
    "historical_classification",
    "historical_checkpoint_2",
    "recipe_raw_sha256",
    "ratified_recipe_fingerprint",
    "historical_recipe_fingerprint",
}
_INSTRUMENT_IDENTITY_KEYS = {
    "instrument_fingerprint",
    "protocol_identity",
    "historical_rubric_raw_sha256",
    "historical_rubric_fingerprint",
    "corrected_rubric_raw_sha256",
    "corrected_rubric_fingerprint",
    "rendered_evaluator_request_raw_sha256",
    "provider_call_request_raw_sha256",
}
_PROTOCOL_IDENTITY_KEYS = {
    "schema",
    "renderer_id",
    "report_schema_fingerprint",
    "recommendation_meanings_fingerprint",
    "parser_contract_id",
    "blocker_contract_id",
    "classifier_contract_id",
    "provider_request_builder_id",
    "preflight_archive_contract_id",
    "system_prompt_raw_sha256",
    "tool_schema_fingerprint",
    "model",
    "provider_profile",
    "adapter_path",
    "temperature",
    "max_completion_tokens",
    "provider_timeout_s",
    "max_attempts",
    "reviewed_commit_sha",
    "corrected_rubric_raw_sha256",
    "corrected_rubric_fingerprint",
}
_ATTEMPT_IDENTITY_KEYS = {
    "attempt_id",
    "attempt_fingerprint",
    "derivative_root",
    "canonical_destination",
    "canonical_staging",
}
_DELTA_ROW_KEYS = {
    "role",
    "relative_path",
    "source_raw_sha256",
    "source_canonical_fingerprint",
    "instrument_raw_sha256",
    "instrument_canonical_fingerprint",
    "disposition",
}


@dataclass(frozen=True)
class HistoricalSourcePins:
    source_root: Path
    root_manifest_raw_sha256: str
    checkpoint_aggregate_identity: str
    historical_commit_sha: str
    historical_classification: str
    historical_checkpoint_2: str
    recipe_raw_sha256: str
    ratified_recipe_fingerprint: str
    historical_recipe_fingerprint: str


PRODUCTION_SOURCE_PINS = HistoricalSourcePins(
    source_root=Path(
        r"C:\Users\bring\rook-lm9b-p-attempts\2026-07-22-visibility-intervention"
    ),
    root_manifest_raw_sha256=(
        "sha256:ac7716b7d5a61e2e6359bc0e01e145d7d17e0871ff03d1d5329710541d274c90"
    ),
    checkpoint_aggregate_identity=(
        "sha256:c57c88c61715588a2071d97d73e65f41447754868d18dc8517708734d92a081e"
    ),
    historical_commit_sha="15df78ee665cf8ff433a4af20e364365b779143b",
    historical_classification="probe_inconclusive",
    historical_checkpoint_2="not_evaluated",
    recipe_raw_sha256=(
        "sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af"
    ),
    ratified_recipe_fingerprint=(
        "sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a"
    ),
    historical_recipe_fingerprint=(
        "sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a"
    ),
)


@dataclass(frozen=True)
class VerifiedHistoricalSource:
    pins: HistoricalSourcePins
    source_root: Path
    root_manifest_bytes: bytes
    root_manifest_rows: tuple[tuple[str, str], ...]
    checkpoint_checksums_bytes: bytes
    original_identity_bytes: bytes
    original_classification_bytes: bytes
    final_recipe_bytes: bytes
    final_recipe_identity_bytes: bytes
    input_manifest_bytes: bytes | None
    input_records: tuple[PLANNER_ARTIFACTS.PlannerInputRecord, ...]
    identity_value: Mapping[str, object]


@dataclass(frozen=True)
class ContinuationInstrument:
    source: VerifiedHistoricalSource
    inputs: PLANNER_ARTIFACTS.FrozenPlannerInputs
    gate_result: SUPPORT.MechanicalGateResult
    rendered_request: PLANNER_ARTIFACTS.RenderedRequest
    provider_call_request_bytes: bytes
    corrected_rubric_bytes: bytes
    allowed_delta_rows: tuple[Mapping[str, object], ...]
    protocol_identity: Mapping[str, object]
    instrument_fingerprint: str


@dataclass(frozen=True)
class AttemptBinding:
    attempt_id: str
    derivative_root: Path
    destination: Path
    staging_path: Path
    attempt_fingerprint: str


@dataclass(frozen=True)
class VerifiedContinuationPreflight:
    archive_dir: Path
    record: Mapping[str, object]
    preflight_fingerprint: str
    instrument_fingerprint: str
    attempt_id: str
    attempt_fingerprint: str
    derivative_root: Path
    destination: Path
    staging_path: Path
    rendered_request_bytes: bytes
    provider_call_request_bytes: bytes


@dataclass(frozen=True)
class SealedDerivative:
    archive_dir: Path
    derivative_archive_identity: str
    classification: str
    identity: Mapping[str, object]
    state: str = "sealed"


@dataclass(frozen=True)
class PostDispatchUnsealed:
    staging_dir: Path
    attempt_id: str
    attempt_fingerprint: str
    failure_locus: str
    classification: None = None
    state: str = "post_dispatch_unsealed"


_SOURCE_INPUT_PATHS = (
    "attempt_context.json",
    "radial_brief.txt",
    "task_envelope.json",
    "environment_snapshot.json",
    "planning_policy.json",
    "payload_schema_registry.json",
    "capability_registry.json",
    "semantic_authority_code_vocabulary.json",
    "semantic_capability_code_vocabulary.json",
    "worker_slot_code_vocabulary.json",
    "semantic_materiality_code_vocabulary.json",
    "semantic_value_schema_registry.json",
    "planner_recipe_probe_schema.json",
    "recipe_normalization_profile.json",
    "planner_authoring_contract.json",
    "planner_exclusion_policy.json",
    "planner_evaluation_rubric.json",
)
_DERIVATIVE_REQUIRED_ROLES = {
    "identity.json": "identity",
    "source/binding.json": "source_binding",
    "source/SHA256-MANIFEST.txt": "source_root_manifest",
    "source/checkpoint-checksums.json": "source_checkpoint_checksums",
    "source/original-identity.json": "source_original_identity",
    "source/original-classification.json": "source_original_classification",
    "source/final-recipe.json": "source_final_recipe",
    "source/final-recipe-identity.json": "source_final_recipe_identity",
    **{
        f"source/inputs/{path}": f"source_input:{path}"
        for path in _SOURCE_INPUT_PATHS
    },
    "instrument/allowed-delta-manifest.json": "instrument_allowed_delta",
    "instrument/corrected-evaluator-rubric.json": "instrument_corrected_rubric",
    "instrument/protocol-identity.json": "instrument_protocol_identity",
    "instrument/mechanical-gate.json": "instrument_mechanical_gate",
    "preflight/record.json": "preflight_record",
    "preflight/rendered-evaluator-request.json": "preflight_rendered_request",
    "preflight/provider-call-request.json": "preflight_provider_request",
    "launch/invocation-binding.json": "launch_invocation_binding",
    "readiness/readiness-record.json": "readiness_record",
    "readiness/credential-preflight.json": "readiness_credential_preflight",
    "readiness/verification.json": "readiness_verification",
    "dispatch/dispatch-started.json": "dispatch_started",
    "evaluator/attempt/capture.json": "evaluator_attempt_capture",
    "evaluator/attempt/provider-call-request.json": (
        "evaluator_attempt_provider_request"
    ),
    "evaluator/result.json": "evaluator_result",
    "decision/classification.json": "decision_classification",
    "boundary.json": "boundary",
}
_DERIVATIVE_CHECKSUMS_SCHEMA_ID = (
    "rook.lm9b_p.evaluator.continuation_derivative_checksums:v1"
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(_builtins(value), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _builtins(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _builtins(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_builtins(item) for item in value]
    return value


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _object(raw: bytes, label: str) -> dict[str, object]:
    value = SUPPORT.parse_archive_json(raw)
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _parse_root_manifest(raw: bytes) -> tuple[tuple[str, str], ...]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("historical root manifest is not UTF-8") from exc
    if text.endswith("\r\n"):
        body = text[:-2]
        if "\n" in body.replace("\r\n", "") or "\r" in body.replace(
            "\r\n", ""
        ):
            raise ValueError("historical root manifest has mixed line endings")
        lines = body.split("\r\n")
    elif text.endswith("\n"):
        body = text[:-1]
        if "\r" in body:
            raise ValueError("historical root manifest has mixed line endings")
        lines = body.split("\n")
    else:
        raise ValueError("historical root manifest must be line terminated")
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        if len(line) < 67 or line[64:66] != "  ":
            raise ValueError("historical root manifest row is malformed")
        digest, relative = line[:64], line[66:]
        if not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError("historical root manifest digest is malformed")
        if (
            not relative
            or "\\" in relative
            or relative.startswith("/")
            or Path(relative).is_absolute()
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or relative == "SHA256-MANIFEST.txt"
            or relative in seen
        ):
            raise ValueError("historical root manifest path is unsafe or duplicate")
        seen.add(relative)
        rows.append((relative, "sha256:" + digest.casefold()))
    if not rows or tuple(path for path, _digest in rows) != tuple(
        sorted(path for path, _digest in rows)
    ):
        raise ValueError("historical root manifest must be nonempty and sorted")
    return tuple(rows)


def _require_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ValueError(f"{label} shape is invalid")


def _historical_source_identity(
    pins: HistoricalSourcePins,
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "source_root": str(Path(pins.source_root).resolve()),
            "root_manifest_raw_sha256": (
                pins.root_manifest_raw_sha256.casefold()
            ),
            "checkpoint_aggregate_identity": pins.checkpoint_aggregate_identity,
            "historical_commit_sha": pins.historical_commit_sha,
            "historical_classification": pins.historical_classification,
            "historical_checkpoint_2": pins.historical_checkpoint_2,
            "recipe_raw_sha256": pins.recipe_raw_sha256,
            "ratified_recipe_fingerprint": pins.ratified_recipe_fingerprint,
            "historical_recipe_fingerprint": (
                pins.historical_recipe_fingerprint
            ),
        }
    )


def _verify_historical_source(pins: HistoricalSourcePins) -> VerifiedHistoricalSource:
    root = Path(pins.source_root).resolve()
    if not root.is_dir():
        raise ValueError("historical source root is unavailable")
    manifest_path = root / "SHA256-MANIFEST.txt"
    manifest_bytes = manifest_path.read_bytes()
    if _sha256(manifest_bytes) != pins.root_manifest_raw_sha256.casefold():
        raise ValueError("historical root manifest identity mismatch")
    manifest_rows = _parse_root_manifest(manifest_bytes)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual_files != {path for path, _digest in manifest_rows}:
        raise ValueError("historical root manifest file set mismatch")
    for relative, expected_digest in manifest_rows:
        if _stream_sha256(root / Path(relative)) != expected_digest:
            raise ValueError(f"historical source file mismatch: {relative}")

    checkpoint = root / "checkpoint-1"
    PLANNER_ARTIFACTS.verify_sealed_planner_checkpoint_archive(
        checkpoint,
        expected_aggregate_identity=pins.checkpoint_aggregate_identity,
    )
    identity_bytes = (checkpoint / "identity.json").read_bytes()
    classification_bytes = (checkpoint / "checkpoint/classification.json").read_bytes()
    recipe_bytes = (checkpoint / "planner/final_recipe.json").read_bytes()
    recipe_identity_bytes = (
        checkpoint / "planner/final_recipe_identity.json"
    ).read_bytes()
    input_manifest_bytes = (checkpoint / "inputs/manifest.json").read_bytes()
    checkpoint_checksums_bytes = (checkpoint / "checksums.json").read_bytes()
    identity = _object(identity_bytes, "historical identity")
    classification = _object(classification_bytes, "historical classification")
    recipe_identity = _object(recipe_identity_bytes, "historical recipe identity")
    input_manifest = _object(input_manifest_bytes, "historical input manifest")
    if identity.get("git_commit_sha") != pins.historical_commit_sha:
        raise ValueError("historical commit mismatch")
    if (
        classification.get("classification") != pins.historical_classification
        or classification.get("checkpoint_2") != pins.historical_checkpoint_2
    ):
        raise ValueError("historical classification mismatch")
    if _sha256(recipe_bytes) != pins.recipe_raw_sha256:
        raise ValueError("historical final recipe byte identity mismatch")
    if (
        recipe_identity.get("raw_sha256") != pins.recipe_raw_sha256
        or recipe_identity.get("mechanical_status") != "mechanically_accepted"
        or recipe_identity.get("ratified_recipe_fingerprint")
        != pins.ratified_recipe_fingerprint
        or recipe_identity.get("historical_recipe_fingerprint")
        != pins.historical_recipe_fingerprint
    ):
        raise ValueError("historical final recipe identity mismatch")
    if input_manifest.get("schema") != "rook.lm9b_p.planner_input_manifest:v1":
        raise ValueError("historical input manifest schema mismatch")
    manifest_records = input_manifest.get("records")
    if not isinstance(manifest_records, list):
        raise ValueError("historical input manifest records are invalid")
    input_records: list[PLANNER_ARTIFACTS.PlannerInputRecord] = []
    roles: set[str] = set()
    paths: set[str] = set()
    for row in manifest_records:
        if type(row) is not dict or set(row) != {
            "role",
            "path",
            "raw_sha256",
            "canonical_fingerprint",
        }:
            raise ValueError("historical input manifest row is invalid")
        role = row["role"]
        relative = row["path"]
        if (
            not isinstance(role, str)
            or not isinstance(relative, str)
            or role in roles
            or relative in paths
        ):
            raise ValueError("historical input identity is duplicate or malformed")
        raw = (checkpoint / "inputs" / relative).read_bytes()
        record = PLANNER_ARTIFACTS.planner_input_record_from_bytes(
            role=role,
            relative_path=relative,
            raw_bytes=raw,
        )
        if (
            record.raw_sha256 != row["raw_sha256"]
            or record.canonical_fingerprint != row["canonical_fingerprint"]
        ):
            raise ValueError(f"historical input manifest mismatch: {role}")
        roles.add(role)
        paths.add(relative)
        input_records.append(record)
    if len(input_records) != 17:
        raise ValueError("historical input manifest cardinality mismatch")

    joined = _object(
        (root / "joined-aggregate/aggregate.json").read_bytes(),
        "historical joined aggregate",
    )
    checkpoint_1 = joined.get("checkpoint_1")
    checkpoint_2 = joined.get("checkpoint_2")
    if (
        not isinstance(checkpoint_1, dict)
        or checkpoint_1.get("aggregate_identity")
        != pins.checkpoint_aggregate_identity
        or checkpoint_1.get("classification") != pins.historical_classification
        or not isinstance(checkpoint_2, dict)
        or checkpoint_2.get("outcome") != pins.historical_checkpoint_2
        or joined.get("aggregate_outcome") != pins.historical_classification
        or joined.get("handoff") is not None
        or joined.get("lm9b_c_archive") is not None
        or joined.get("execution_permitted") is not False
    ):
        raise ValueError("historical joined aggregate boundary mismatch")

    identity_value = _historical_source_identity(pins)
    return VerifiedHistoricalSource(
        pins=pins,
        source_root=root,
        root_manifest_bytes=manifest_bytes,
        root_manifest_rows=manifest_rows,
        checkpoint_checksums_bytes=checkpoint_checksums_bytes,
        original_identity_bytes=identity_bytes,
        original_classification_bytes=classification_bytes,
        final_recipe_bytes=recipe_bytes,
        final_recipe_identity_bytes=recipe_identity_bytes,
        input_manifest_bytes=input_manifest_bytes,
        input_records=tuple(input_records),
        identity_value=identity_value,
    )


def verify_historical_source() -> VerifiedHistoricalSource:
    return _verify_historical_source(PRODUCTION_SOURCE_PINS)


def _verified_historical_source_from_derivative(
    archive: Path,
) -> VerifiedHistoricalSource:
    """Reconstruct the production-pinned source solely from derivative bytes."""

    pins = PRODUCTION_SOURCE_PINS
    expected_identity = _historical_source_identity(pins)
    binding = _object(
        (archive / "source/binding.json").read_bytes(),
        "derivative source binding",
    )
    if (
        binding.pop("schema", None) != SOURCE_BINDING_SCHEMA_ID
        or binding != dict(expected_identity)
    ):
        raise ValueError("derivative source binding differs from production pins")

    manifest_bytes = (archive / "source/SHA256-MANIFEST.txt").read_bytes()
    if _sha256(manifest_bytes) != pins.root_manifest_raw_sha256.casefold():
        raise ValueError("derivative source manifest differs from production pins")
    manifest_rows = _parse_root_manifest(manifest_bytes)
    root_rows = dict(manifest_rows)
    source_copies = {
        "checkpoint-1/checksums.json": "source/checkpoint-checksums.json",
        "checkpoint-1/identity.json": "source/original-identity.json",
        "checkpoint-1/checkpoint/classification.json": (
            "source/original-classification.json"
        ),
        "checkpoint-1/planner/final_recipe.json": "source/final-recipe.json",
        "checkpoint-1/planner/final_recipe_identity.json": (
            "source/final-recipe-identity.json"
        ),
        **{
            f"checkpoint-1/inputs/{relative}": f"source/inputs/{relative}"
            for relative in _SOURCE_INPUT_PATHS
        },
    }
    for historical_path, derivative_path in source_copies.items():
        raw = (archive / derivative_path).read_bytes()
        if _sha256(raw) != root_rows.get(historical_path):
            raise ValueError(
                f"derivative source differs from production: {historical_path}"
            )

    checkpoint_checksums_bytes = (
        archive / "source/checkpoint-checksums.json"
    ).read_bytes()
    checkpoint_checksums = _object(
        checkpoint_checksums_bytes,
        "derivative source checkpoint checksums",
    )
    if checkpoint_checksums.get("aggregate_identity") != (
        pins.checkpoint_aggregate_identity
    ):
        raise ValueError("derivative source checkpoint identity mismatch")
    identity_bytes = (archive / "source/original-identity.json").read_bytes()
    classification_bytes = (
        archive / "source/original-classification.json"
    ).read_bytes()
    recipe_bytes = (archive / "source/final-recipe.json").read_bytes()
    recipe_identity_bytes = (
        archive / "source/final-recipe-identity.json"
    ).read_bytes()
    identity = _object(identity_bytes, "derivative historical identity")
    classification = _object(
        classification_bytes,
        "derivative historical classification",
    )
    recipe_identity = _object(
        recipe_identity_bytes,
        "derivative historical recipe identity",
    )
    if identity.get("git_commit_sha") != pins.historical_commit_sha:
        raise ValueError("derivative historical commit mismatch")
    if (
        classification.get("classification")
        != pins.historical_classification
        or classification.get("checkpoint_2")
        != pins.historical_checkpoint_2
    ):
        raise ValueError("derivative historical classification mismatch")
    if _sha256(recipe_bytes) != pins.recipe_raw_sha256:
        raise ValueError("derivative historical recipe bytes mismatch")
    if (
        recipe_identity.get("raw_sha256") != pins.recipe_raw_sha256
        or recipe_identity.get("mechanical_status")
        != "mechanically_accepted"
        or recipe_identity.get("ratified_recipe_fingerprint")
        != pins.ratified_recipe_fingerprint
        or recipe_identity.get("historical_recipe_fingerprint")
        != pins.historical_recipe_fingerprint
    ):
        raise ValueError("derivative historical recipe identity mismatch")

    input_bytes = {
        relative: (archive / "source/inputs" / relative).read_bytes()
        for relative in _SOURCE_INPUT_PATHS
    }
    input_records = PLANNER_ARTIFACTS.planner_input_records_from_bytes(
        input_bytes
    )
    return VerifiedHistoricalSource(
        pins=pins,
        source_root=Path(pins.source_root).resolve(),
        root_manifest_bytes=manifest_bytes,
        root_manifest_rows=manifest_rows,
        checkpoint_checksums_bytes=checkpoint_checksums_bytes,
        original_identity_bytes=identity_bytes,
        original_classification_bytes=classification_bytes,
        final_recipe_bytes=recipe_bytes,
        final_recipe_identity_bytes=recipe_identity_bytes,
        input_manifest_bytes=None,
        input_records=input_records,
        identity_value=expected_identity,
    )


def _gate_value(gate: SUPPORT.MechanicalGateResult) -> dict[str, object]:
    return {
        "schema": "rook.lm9b_p.evaluator_continuation_mechanical_gate:v1",
        "status": gate.status,
        "diagnostics": [
            {"code": row.code, "path": row.path, "message": row.message}
            for row in gate.diagnostics
        ],
        "final_recipe_raw_sha256": (
            _sha256(gate.final_recipe_bytes)
            if gate.final_recipe_bytes is not None
            else None
        ),
        "recipe_value_fingerprint": gate.recipe_value_fingerprint,
        "ratified_recipe_fingerprint": gate.ratified_recipe_fingerprint,
        "historical_recipe_fingerprint": gate.historical_recipe_fingerprint,
    }


def assemble_continuation_instrument(
    source: VerifiedHistoricalSource,
    *,
    corrected_rubric_bytes: bytes,
    reviewed_commit_sha: str,
) -> ContinuationInstrument:
    if type(source) is not VerifiedHistoricalSource:
        raise TypeError("verified historical source is required")
    if not re.fullmatch(r"[0-9a-f]{40}", reviewed_commit_sha):
        raise ValueError("reviewed commit SHA is invalid")
    replacement = PLANNER_ARTIFACTS.planner_input_record_from_bytes(
        role="evaluation_rubric",
        relative_path="planner_evaluation_rubric.json",
        raw_bytes=corrected_rubric_bytes,
    )
    records: list[PLANNER_ARTIFACTS.PlannerInputRecord] = []
    delta_rows: list[Mapping[str, object]] = []
    for archived in source.input_records:
        instrument = replacement if archived.role == "evaluation_rubric" else archived
        disposition = (
            "replaced_evaluator_rubric"
            if archived.role == "evaluation_rubric"
            else "byte_identical"
        )
        if disposition == "byte_identical" and instrument.raw_bytes != archived.raw_bytes:
            raise ValueError("non-rubric instrument input differs from sealed source")
        records.append(instrument)
        delta_rows.append(
            MappingProxyType(
                {
                    "role": archived.role,
                    "relative_path": archived.relative_path,
                    "source_raw_sha256": archived.raw_sha256,
                    "source_canonical_fingerprint": archived.canonical_fingerprint,
                    "instrument_raw_sha256": instrument.raw_sha256,
                    "instrument_canonical_fingerprint": instrument.canonical_fingerprint,
                    "disposition": disposition,
                }
            )
        )
    replaced = [
        row
        for row in delta_rows
        if row["disposition"] == "replaced_evaluator_rubric"
    ]
    if (
        len(replaced) != 1
        or replacement.raw_sha256 == replaced[0]["source_raw_sha256"]
    ):
        raise ValueError("instrument must replace exactly the historical evaluator rubric")
    inputs = PLANNER_ARTIFACTS.frozen_planner_inputs_from_records(
        records,
        source_dir=source.source_root / "checkpoint-1/inputs",
    )
    gate = SUPPORT.evaluate_mechanical_gate(
        recipe_bytes=source.final_recipe_bytes,
        authority=inputs.authority,
        recipe_schema=inputs.recipe_schema,
        normalization_profile=inputs.authority.normalization_profile,
        exclusion_policy=inputs.exclusion_policy,
    )
    if (
        gate.status != "mechanically_accepted"
        or gate.final_recipe_bytes != source.final_recipe_bytes
        or gate.ratified_recipe_fingerprint != source.pins.ratified_recipe_fingerprint
        or gate.historical_recipe_fingerprint
        != source.pins.historical_recipe_fingerprint
    ):
        raise ValueError("sealed recipe did not pass the continuation mechanical gate")
    rendered = PLANNER_ARTIFACTS.render_planner_evaluator_request(
        inputs,
        gate_result=gate,
    )
    provider_request = SUPPORT.build_planner_evaluator_provider_call_request(
        system_prompt=SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT,
        user_prompt=rendered.raw_bytes.decode("utf-8"),
    )
    protocol = MappingProxyType(
        {
            "schema": "rook.lm9b_p.evaluator_continuation_protocol_identity:v1",
            "renderer_id": PLANNER_ARTIFACTS.PLANNER_EVALUATOR_RENDERER_ID,
            "report_schema_fingerprint": SUPPORT.fingerprint(
                SUPPORT.PLANNER_EVALUATION_REPORT_SCHEMA
            ),
            "recommendation_meanings_fingerprint": SUPPORT.fingerprint(
                SUPPORT.PLANNER_EVALUATION_RECOMMENDATION_MEANINGS
            ),
            "parser_contract_id": "lm9b_p.planner_evaluation_parser:v1",
            "blocker_contract_id": "lm9b_p.explicit_blocker_projection:v1",
            "classifier_contract_id": "lm9b_p.evaluated_recipe_classification:v1",
            "provider_request_builder_id": (
                "lm9b_p.planner_evaluator_provider_call_builder:v1"
            ),
            "preflight_archive_contract_id": PREFLIGHT_SCHEMA_ID,
            "system_prompt_raw_sha256": _sha256(
                SUPPORT.PLANNER_EVALUATOR_SYSTEM_PROMPT.encode("utf-8")
            ),
            "tool_schema_fingerprint": SUPPORT.fingerprint(
                SUPPORT.planner_evaluator_tool_definition()
            ),
            "model": EVALUATOR_MODEL,
            "provider_profile": PROVIDER_PROFILE_ID,
            "adapter_path": "litellm.completion",
            "temperature": EVALUATOR_TEMPERATURE,
            "max_completion_tokens": SUPPORT.PLANNER_EVALUATOR_MAX_COMPLETION_TOKENS,
            "provider_timeout_s": SUPPORT.PLANNER_EVALUATOR_PROVIDER_TIMEOUT_S,
            "max_attempts": 1,
            "reviewed_commit_sha": reviewed_commit_sha,
            "corrected_rubric_raw_sha256": replacement.raw_sha256,
            "corrected_rubric_fingerprint": replacement.canonical_fingerprint,
        }
    )
    delta_value = [dict(row) for row in delta_rows]
    instrument_fingerprint = SUPPORT.fingerprint(
        {
            "source": dict(source.identity_value),
            "allowed_delta": delta_value,
            "protocol": dict(protocol),
            "reviewed_commit_sha": reviewed_commit_sha,
            "rendered_evaluator_request_raw_sha256": rendered.raw_sha256,
            "provider_call_request_raw_sha256": _sha256(provider_request),
        }
    )
    return ContinuationInstrument(
        source=source,
        inputs=inputs,
        gate_result=gate,
        rendered_request=rendered,
        provider_call_request_bytes=provider_request,
        corrected_rubric_bytes=corrected_rubric_bytes,
        allowed_delta_rows=tuple(delta_rows),
        protocol_identity=protocol,
        instrument_fingerprint=instrument_fingerprint,
    )


def _instrument_identity_value(
    instrument: ContinuationInstrument,
) -> dict[str, object]:
    rubric_row = next(
        row
        for row in instrument.allowed_delta_rows
        if row["role"] == "evaluation_rubric"
    )
    return {
        "instrument_fingerprint": instrument.instrument_fingerprint,
        "protocol_identity": dict(instrument.protocol_identity),
        "historical_rubric_raw_sha256": rubric_row["source_raw_sha256"],
        "historical_rubric_fingerprint": rubric_row[
            "source_canonical_fingerprint"
        ],
        "corrected_rubric_raw_sha256": _sha256(
            instrument.corrected_rubric_bytes
        ),
        "corrected_rubric_fingerprint": SUPPORT.fingerprint(
            _object(instrument.corrected_rubric_bytes, "corrected rubric")
        ),
        "rendered_evaluator_request_raw_sha256": (
            instrument.rendered_request.raw_sha256
        ),
        "provider_call_request_raw_sha256": _sha256(
            instrument.provider_call_request_bytes
        ),
    }


def bind_attempt(
    *,
    instrument_fingerprint: str,
    attempt_id: str,
    derivative_root: Path,
    destination: Path,
) -> AttemptBinding:
    if not isinstance(attempt_id, str) or not 1 <= len(attempt_id) <= 64:
        raise ValueError("attempt ID length is invalid")
    if ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is None:
        raise ValueError("attempt ID grammar is invalid")
    raw_root = Path(derivative_root)
    raw_destination = Path(destination)
    if not raw_root.is_absolute() or not raw_destination.is_absolute():
        raise ValueError("derivative paths must be absolute")
    if ".." in raw_root.parts or ".." in raw_destination.parts:
        raise ValueError("derivative paths must be canonical and traversal-free")
    root = raw_root.resolve()
    canonical_destination = raw_destination.resolve(strict=False)
    if raw_root != root or raw_destination != canonical_destination:
        raise ValueError("derivative paths must already be canonical")
    if not root.is_dir():
        raise ValueError("derivative root must already exist")
    attributes = getattr(os.lstat(root), "st_file_attributes", 0)
    if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise ValueError("derivative root must not be a reparse point")
    if canonical_destination.parent != root:
        raise ValueError("final destination must be a direct child of derivative root")
    if root.drive.casefold() != canonical_destination.drive.casefold():
        raise ValueError("derivative root and destination must share a volume")
    if canonical_destination.name.startswith(".continuation-staging-"):
        raise ValueError("final destination uses the reserved staging prefix")
    if canonical_destination.exists():
        raise FileExistsError(f"derivative destination exists: {canonical_destination}")
    attempt_fingerprint = SUPPORT.fingerprint(
        {
            "instrument_fingerprint": instrument_fingerprint,
            "attempt_id": attempt_id,
            "canonical_destination": str(canonical_destination),
        }
    )
    staging = root / (
        f".continuation-staging-{attempt_id}-"
        f"{attempt_fingerprint.removeprefix('sha256:')}"
    )
    if staging.exists():
        raise FileExistsError(f"continuation staging exists: {staging}")
    return AttemptBinding(
        attempt_id=attempt_id,
        derivative_root=root,
        destination=canonical_destination,
        staging_path=staging,
        attempt_fingerprint=attempt_fingerprint,
    )


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != raw:
        raise OSError(f"preflight write verification failed: {path.name}")


def _file_row(path: str, role: str, raw: bytes) -> dict[str, object]:
    return {
        "path": path,
        "role": role,
        "raw_sha256": _sha256(raw),
        "byte_length": len(raw),
    }


def write_preflight_archive(
    *,
    output_dir: Path,
    reviewed_commit_sha: str,
    launch_eligibility: str,
    instrument: ContinuationInstrument,
    attempt: AttemptBinding,
) -> VerifiedContinuationPreflight:
    if launch_eligibility not in {
        "development_non_operational",
        "operator_review_candidate",
    }:
        raise ValueError("preflight launch eligibility is invalid")
    output = Path(output_dir).resolve(strict=False)
    output.mkdir(parents=False, exist_ok=False)
    source_binding = _json_bytes(
        {
            "schema": SOURCE_BINDING_SCHEMA_ID,
            **dict(instrument.source.identity_value),
        }
    )
    delta = _json_bytes(
        {
            "schema": ALLOWED_DELTA_SCHEMA_ID,
            "rows": [dict(row) for row in instrument.allowed_delta_rows],
        }
    )
    gate = _json_bytes(_gate_value(instrument.gate_result))
    sidecars: dict[str, bytes] = {
        "source-binding.json": source_binding,
        "allowed-delta-manifest.json": delta,
        "mechanical-gate.json": gate,
        "rendered-evaluator-request.json": instrument.rendered_request.raw_bytes,
        "provider-call-request.json": instrument.provider_call_request_bytes,
    }
    sidecar_rows = [
        _file_row(path, _PREFLIGHT_MEMBERS[path], raw)
        for path, raw in sorted(sidecars.items())
    ]
    source_identity = dict(instrument.source.identity_value)
    instrument_identity = _instrument_identity_value(instrument)
    attempt_identity = {
        "attempt_id": attempt.attempt_id,
        "attempt_fingerprint": attempt.attempt_fingerprint,
        "derivative_root": str(attempt.derivative_root),
        "canonical_destination": str(attempt.destination),
        "canonical_staging": str(attempt.staging_path),
    }
    without_fingerprint = {
        "schema_id": PREFLIGHT_SCHEMA_ID,
        "reviewed_commit_sha": reviewed_commit_sha,
        "clean_checkout": True,
        "launch_eligibility": launch_eligibility,
        "source": source_identity,
        "instrument": instrument_identity,
        "attempt": attempt_identity,
        "files": sidecar_rows,
    }
    preflight_fingerprint = SUPPORT.fingerprint(without_fingerprint)
    record = {**without_fingerprint, "preflight_fingerprint": preflight_fingerprint}
    record_bytes = _json_bytes(record)
    members = {"record.json": record_bytes, **sidecars}
    checksum_rows = [
        _file_row(path, _PREFLIGHT_MEMBERS[path], raw)
        for path, raw in sorted(members.items())
    ]
    checksums = {
        "schema_id": PREFLIGHT_CHECKSUMS_SCHEMA_ID,
        "records": checksum_rows,
    }
    checksums["aggregate_identity"] = SUPPORT.fingerprint(checksums)
    for relative, raw in members.items():
        _write_exclusive(output / relative, raw)
    _write_exclusive(output / "checksums.json", _json_bytes(checksums))
    return verify_preflight_archive(
        output,
        expected_preflight_fingerprint=preflight_fingerprint,
    )


def verify_preflight_archive(
    archive_dir: Path,
    *,
    expected_preflight_fingerprint: str,
) -> VerifiedContinuationPreflight:
    archive = Path(archive_dir).resolve()
    if not archive.is_dir():
        raise ValueError("preflight archive directory is unavailable")
    actual_files = {
        path.relative_to(archive).as_posix()
        for path in archive.rglob("*")
        if path.is_file()
    }
    expected_files = set(_PREFLIGHT_MEMBERS) | {"checksums.json"}
    if actual_files != expected_files:
        raise ValueError("preflight archive file set is invalid")
    checksums = _object((archive / "checksums.json").read_bytes(), "preflight checksums")
    _require_keys(
        checksums,
        {"schema_id", "records", "aggregate_identity"},
        "preflight checksums",
    )
    if checksums["schema_id"] != PREFLIGHT_CHECKSUMS_SCHEMA_ID:
        raise ValueError("preflight checksum schema mismatch")
    rows = checksums["records"]
    if not isinstance(rows, list):
        raise ValueError("preflight checksum records are invalid")
    by_path: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if type(row) is not dict or set(row) != {
            "path",
            "role",
            "raw_sha256",
            "byte_length",
        }:
            raise ValueError("preflight checksum row is invalid")
        path = row["path"]
        if not isinstance(path, str) or path in by_path:
            raise ValueError("preflight checksum path is duplicate or invalid")
        by_path[path] = row
    if list(by_path) != sorted(by_path) or set(by_path) != set(_PREFLIGHT_MEMBERS):
        raise ValueError("preflight checksum closure is invalid")
    for relative, role in _PREFLIGHT_MEMBERS.items():
        raw = (archive / relative).read_bytes()
        row = by_path[relative]
        if (
            row["role"] != role
            or row["raw_sha256"] != _sha256(raw)
            or row["byte_length"] != len(raw)
        ):
            raise ValueError(f"preflight checksum mismatch: {relative}")
    expected_aggregate = SUPPORT.fingerprint(
        {"schema_id": PREFLIGHT_CHECKSUMS_SCHEMA_ID, "records": rows}
    )
    if checksums["aggregate_identity"] != expected_aggregate:
        raise ValueError("preflight aggregate identity mismatch")

    record = _object((archive / "record.json").read_bytes(), "preflight record")
    _require_keys(
        record,
        {
            "schema_id",
            "preflight_fingerprint",
            "reviewed_commit_sha",
            "clean_checkout",
            "launch_eligibility",
            "source",
            "instrument",
            "attempt",
            "files",
        },
        "preflight record",
    )
    if record["schema_id"] != PREFLIGHT_SCHEMA_ID:
        raise ValueError("preflight record schema mismatch")
    supplied = record["preflight_fingerprint"]
    without = {key: value for key, value in record.items() if key != "preflight_fingerprint"}
    if supplied != SUPPORT.fingerprint(without) or supplied != expected_preflight_fingerprint:
        raise ValueError("preflight fingerprint mismatch")
    if record["clean_checkout"] is not True or record["launch_eligibility"] not in {
        "development_non_operational",
        "operator_review_candidate",
    }:
        raise ValueError("preflight checkout or launch eligibility is invalid")
    if record["files"] != [
        _file_row(
            path,
            _PREFLIGHT_MEMBERS[path],
            (archive / path).read_bytes(),
        )
        for path in sorted(path for path in _PREFLIGHT_MEMBERS if path != "record.json")
    ]:
        raise ValueError("preflight sidecar binding mismatch")
    source = record["source"]
    instrument = record["instrument"]
    attempt = record["attempt"]
    if not all(isinstance(value, dict) for value in (source, instrument, attempt)):
        raise ValueError("preflight identity sections are invalid")
    assert isinstance(source, dict)
    assert isinstance(instrument, dict)
    assert isinstance(attempt, dict)
    _require_keys(source, _SOURCE_IDENTITY_KEYS, "preflight source identity")
    _require_keys(
        instrument,
        _INSTRUMENT_IDENTITY_KEYS,
        "preflight instrument identity",
    )
    _require_keys(attempt, _ATTEMPT_IDENTITY_KEYS, "preflight attempt identity")
    protocol = instrument["protocol_identity"]
    if not isinstance(protocol, dict):
        raise ValueError("preflight protocol identity is invalid")
    _require_keys(protocol, _PROTOCOL_IDENTITY_KEYS, "preflight protocol identity")
    reviewed_commit = record["reviewed_commit_sha"]
    if (
        not isinstance(reviewed_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", reviewed_commit) is None
        or protocol["reviewed_commit_sha"] != reviewed_commit
    ):
        raise ValueError("preflight reviewed commit identity is invalid")

    source_binding = _object(
        (archive / "source-binding.json").read_bytes(),
        "preflight source binding",
    )
    _require_keys(
        source_binding,
        {"schema"} | _SOURCE_IDENTITY_KEYS,
        "preflight source binding",
    )
    if source_binding.pop("schema") != SOURCE_BINDING_SCHEMA_ID:
        raise ValueError("preflight source binding schema mismatch")
    if source_binding != source:
        raise ValueError("preflight source binding identity mismatch")

    delta = _object(
        (archive / "allowed-delta-manifest.json").read_bytes(),
        "preflight allowed delta",
    )
    _require_keys(delta, {"schema", "rows"}, "preflight allowed delta")
    if delta["schema"] != ALLOWED_DELTA_SCHEMA_ID or not isinstance(
        delta["rows"], list
    ):
        raise ValueError("preflight allowed delta identity is invalid")
    delta_rows = delta["rows"]
    if len(delta_rows) != 17:
        raise ValueError("preflight allowed delta cardinality is invalid")
    replacements: list[Mapping[str, object]] = []
    seen_roles: set[str] = set()
    seen_paths: set[str] = set()
    for row in delta_rows:
        if not isinstance(row, dict):
            raise ValueError("preflight allowed delta row is invalid")
        _require_keys(row, _DELTA_ROW_KEYS, "preflight allowed delta row")
        role = row["role"]
        relative = row["relative_path"]
        if (
            not isinstance(role, str)
            or not isinstance(relative, str)
            or role in seen_roles
            or relative in seen_paths
        ):
            raise ValueError("preflight allowed delta row identity is invalid")
        seen_roles.add(role)
        seen_paths.add(relative)
        if row["disposition"] == "replaced_evaluator_rubric":
            replacements.append(row)
        elif row["disposition"] != "byte_identical" or (
            row["source_raw_sha256"] != row["instrument_raw_sha256"]
            or row["source_canonical_fingerprint"]
            != row["instrument_canonical_fingerprint"]
        ):
            raise ValueError("preflight allowed delta exceeds the rubric replacement")
    if (
        len(replacements) != 1
        or replacements[0]["role"] != "evaluation_rubric"
        or replacements[0]["source_raw_sha256"]
        != instrument["historical_rubric_raw_sha256"]
        or replacements[0]["source_canonical_fingerprint"]
        != instrument["historical_rubric_fingerprint"]
        or replacements[0]["instrument_raw_sha256"]
        != instrument["corrected_rubric_raw_sha256"]
        or replacements[0]["instrument_canonical_fingerprint"]
        != instrument["corrected_rubric_fingerprint"]
        or instrument["historical_rubric_raw_sha256"]
        == instrument["corrected_rubric_raw_sha256"]
    ):
        raise ValueError("preflight rubric delta identity is invalid")

    rendered = (archive / "rendered-evaluator-request.json").read_bytes()
    provider = (archive / "provider-call-request.json").read_bytes()
    SUPPORT.materialize_planner_evaluator_provider_call_request(provider)
    if instrument.get("rendered_evaluator_request_raw_sha256") != _sha256(rendered):
        raise ValueError("preflight rendered request identity mismatch")
    if instrument.get("provider_call_request_raw_sha256") != _sha256(provider):
        raise ValueError("preflight provider request identity mismatch")
    expected_instrument_fingerprint = SUPPORT.fingerprint(
        {
            "source": source,
            "allowed_delta": delta_rows,
            "protocol": protocol,
            "reviewed_commit_sha": reviewed_commit,
            "rendered_evaluator_request_raw_sha256": _sha256(rendered),
            "provider_call_request_raw_sha256": _sha256(provider),
        }
    )
    if instrument["instrument_fingerprint"] != expected_instrument_fingerprint:
        raise ValueError("preflight instrument identity mismatch")

    try:
        expected_attempt = bind_attempt(
            instrument_fingerprint=expected_instrument_fingerprint,
            attempt_id=attempt["attempt_id"],
            derivative_root=Path(attempt["derivative_root"]),
            destination=Path(attempt["canonical_destination"]),
        )
    except (TypeError, OSError, ValueError) as exc:
        raise ValueError("preflight destination identity is invalid") from exc
    if (
        attempt["attempt_fingerprint"] != expected_attempt.attempt_fingerprint
        or Path(attempt["canonical_staging"]) != expected_attempt.staging_path
    ):
        raise ValueError("preflight attempt identity is invalid")
    return VerifiedContinuationPreflight(
        archive_dir=archive,
        record=MappingProxyType(record),
        preflight_fingerprint=supplied,
        instrument_fingerprint=instrument["instrument_fingerprint"],
        attempt_id=attempt["attempt_id"],
        attempt_fingerprint=attempt["attempt_fingerprint"],
        derivative_root=Path(attempt["derivative_root"]),
        destination=Path(attempt["canonical_destination"]),
        staging_path=Path(attempt["canonical_staging"]),
        rendered_request_bytes=rendered,
        provider_call_request_bytes=provider,
    )


def reserve_staging(attempt: AttemptBinding) -> Path:
    """Atomically reserve the preflight-bound direct-child staging directory."""

    if attempt.staging_path.parent != attempt.derivative_root:
        raise ValueError("staging reservation escaped the derivative root")
    if attempt.destination.exists():
        raise FileExistsError(f"derivative destination exists: {attempt.destination}")
    attempt.staging_path.mkdir(parents=False, exist_ok=False)
    return attempt.staging_path


def write_static_derivative_snapshot(
    *,
    staging: Path,
    source: VerifiedHistoricalSource,
    instrument: ContinuationInstrument,
    preflight_record_bytes: bytes,
    allowed_delta_bytes: bytes,
    mechanical_gate_bytes: bytes,
    rendered_request_bytes: bytes,
    provider_request_bytes: bytes,
    invocation_binding_bytes: bytes,
    readiness_record_bytes: bytes,
    credential_preflight_bytes: bytes,
    readiness_verification_bytes: bytes,
) -> None:
    input_by_path = {record.relative_path: record.raw_bytes for record in source.input_records}
    if set(input_by_path) != set(_SOURCE_INPUT_PATHS):
        raise ValueError("continuation source input snapshot is incomplete")
    members: dict[str, bytes] = {
        "source/binding.json": _json_bytes(
            {
                "schema": SOURCE_BINDING_SCHEMA_ID,
                **dict(source.identity_value),
            }
        ),
        "source/SHA256-MANIFEST.txt": source.root_manifest_bytes,
        "source/checkpoint-checksums.json": source.checkpoint_checksums_bytes,
        "source/original-identity.json": source.original_identity_bytes,
        "source/original-classification.json": source.original_classification_bytes,
        "source/final-recipe.json": source.final_recipe_bytes,
        "source/final-recipe-identity.json": source.final_recipe_identity_bytes,
        "instrument/allowed-delta-manifest.json": allowed_delta_bytes,
        "instrument/corrected-evaluator-rubric.json": (
            instrument.corrected_rubric_bytes
        ),
        "instrument/protocol-identity.json": _json_bytes(
            dict(instrument.protocol_identity)
        ),
        "instrument/mechanical-gate.json": mechanical_gate_bytes,
        "preflight/record.json": preflight_record_bytes,
        "preflight/rendered-evaluator-request.json": rendered_request_bytes,
        "preflight/provider-call-request.json": provider_request_bytes,
        "launch/invocation-binding.json": invocation_binding_bytes,
        "readiness/readiness-record.json": readiness_record_bytes,
        "readiness/credential-preflight.json": credential_preflight_bytes,
        "readiness/verification.json": readiness_verification_bytes,
        "evaluator/attempt/provider-call-request.json": provider_request_bytes,
    }
    for relative, raw in input_by_path.items():
        members[f"source/inputs/{relative}"] = raw
    for relative, raw in members.items():
        _write_exclusive(staging / relative, raw)
    for relative, raw in members.items():
        if (staging / relative).read_bytes() != raw:
            raise OSError(f"staged snapshot readback mismatch: {relative}")


def write_dispatch_started(
    *,
    staging: Path,
    attempt_id: str,
    attempt_fingerprint: str,
    provider_call_request_bytes: bytes,
) -> bytes:
    raw = _json_bytes(
        {
            "schema": "rook.lm9b_p.evaluator.continuation_dispatch_started:v1",
            "attempt_id": attempt_id,
            "attempt_fingerprint": attempt_fingerprint,
            "provider_call_request_raw_sha256": _sha256(
                provider_call_request_bytes
            ),
        }
    )
    _write_exclusive(staging / "dispatch/dispatch-started.json", raw)
    return raw


def _attempt_members(
    attempt: object,
    *,
    quiescent: bool,
) -> tuple[dict[str, object], dict[str, bytes]]:
    outcome = getattr(attempt, "outcome", None)
    turn = getattr(attempt, "provider_turn", None)
    adapter_request = getattr(turn, "raw_request", None)
    response = getattr(turn, "raw_response", None)
    usage = getattr(turn, "usage", None)
    metadata = getattr(turn, "provider_metadata", None)
    if adapter_request is None:
        adapter_request = getattr(attempt, "raw_request", None)
    error = getattr(attempt, "raw_error", None)
    assistant = getattr(turn, "assistant_message", None)
    tool_arguments: list[bytes] = []
    if isinstance(assistant, Mapping):
        calls = assistant.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                function = call.get("function") if isinstance(call, dict) else None
                argument = function.get("arguments") if isinstance(function, dict) else None
                if isinstance(argument, str):
                    tool_arguments.append(argument.encode("utf-8"))
    optional: dict[str, bytes] = {}
    for relative, raw in (
        ("evaluator/attempt/adapter-request.bin", adapter_request),
        ("evaluator/attempt/response.bin", response),
        ("evaluator/attempt/error.bin", error),
    ):
        if isinstance(raw, bytes):
            optional[relative] = raw
    if isinstance(usage, Mapping):
        optional["evaluator/attempt/usage.json"] = _json_bytes(usage)
    if isinstance(assistant, Mapping):
        optional["evaluator/attempt/assistant-message.json"] = _json_bytes(
            assistant
        )
    for index, raw in enumerate(tool_arguments):
        optional[f"evaluator/attempt/tool-arguments/{index:03d}.bin"] = raw
    capture = {
        "schema": "rook.lm9b_p.evaluator.continuation_attempt_capture:v1",
        "outcome": outcome,
        "elapsed_ms": getattr(attempt, "elapsed_ms", None),
        "exception_type": getattr(attempt, "exception_type", None),
        "exception_message": getattr(attempt, "exception_message", None),
        "failure_type": getattr(attempt, "failure_type", None),
        "has_adapter_request": isinstance(adapter_request, bytes),
        "has_response": isinstance(response, bytes),
        "has_error": isinstance(error, bytes),
        "has_usage": isinstance(usage, Mapping),
        "has_assistant_message": isinstance(assistant, Mapping),
        "provider_metadata": dict(metadata) if isinstance(metadata, Mapping) else None,
        "tool_argument_indexes": list(range(len(tool_arguments))),
        "quiescent": quiescent,
    }
    return capture, optional


def _derivative_optional_roles(capture: Mapping[str, object]) -> dict[str, str]:
    optional: dict[str, str] = {}
    for field, relative, role in (
        ("has_adapter_request", "evaluator/attempt/adapter-request.bin", "adapter_request"),
        ("has_response", "evaluator/attempt/response.bin", "response"),
        ("has_error", "evaluator/attempt/error.bin", "error"),
        ("has_usage", "evaluator/attempt/usage.json", "usage"),
        (
            "has_assistant_message",
            "evaluator/attempt/assistant-message.json",
            "assistant_message",
        ),
    ):
        if type(capture.get(field)) is not bool:
            raise ValueError("derivative attempt capture flags are invalid")
        if capture[field]:
            optional[relative] = f"evaluator_attempt_{role}"
    indexes = capture.get("tool_argument_indexes")
    if (
        not isinstance(indexes, list)
        or indexes != list(range(len(indexes)))
    ):
        raise ValueError("derivative tool argument indexes are invalid")
    for index in indexes:
        optional[f"evaluator/attempt/tool-arguments/{index:03d}.bin"] = (
            f"evaluator_attempt_tool_argument:{index}"
        )
    return optional


def seal_derivative_archive(
    *,
    staging: Path,
    destination: Path,
    preflight: VerifiedContinuationPreflight,
    instrument: ContinuationInstrument,
    evaluator: SUPPORT.PlannerEvaluationResult,
    attempt: object,
    classification: str,
) -> SealedDerivative:
    if evaluator.quiescent is not True or getattr(attempt, "outcome", None) not in {
        "returned",
        "raised",
    }:
        raise ValueError("evaluator attempt is not complete and quiescent")
    capture, optional = _attempt_members(attempt, quiescent=evaluator.quiescent)
    result_value = {
        "schema": "rook.lm9b_p.evaluator.continuation_evaluator_result:v1",
        "termination": evaluator.termination,
        "recommendation": evaluator.recommendation,
        "evidence": list(evaluator.evidence),
        "quiescent": evaluator.quiescent,
    }
    decision_value = {
        "schema": "rook.lm9b_p.evaluator.continuation_classification:v1",
        "classification": classification,
        "semantic_recommendation": evaluator.recommendation,
    }
    boundary = {
        "schema": "rook.lm9b_p.evaluator.continuation_boundary:v1",
        "derivative_observation": True,
        "replaces_historical_result": False,
        "planner_entry": "absent",
        "compiler_entry": "absent",
        "checkpoint_2": "not_evaluated",
        "execution_permitted": False,
    }
    identity_subject = {
        "preflight_fingerprint": preflight.preflight_fingerprint,
        "instrument_fingerprint": preflight.instrument_fingerprint,
        "attempt_id": preflight.attempt_id,
        "attempt_fingerprint": preflight.attempt_fingerprint,
        "reviewed_commit_sha": preflight.record["reviewed_commit_sha"],
        "model": instrument.protocol_identity["model"],
        "provider_profile": instrument.protocol_identity["provider_profile"],
        "canonical_destination": str(destination),
        "evaluator_result": result_value,
        "classification": decision_value,
    }
    identity = {
        "schema_id": DERIVATIVE_SCHEMA_ID,
        **{
            key: value
            for key, value in identity_subject.items()
            if key not in {"evaluator_result", "classification"}
        },
        "derivative_subject_fingerprint": SUPPORT.fingerprint(identity_subject),
    }
    members = {
        "identity.json": _json_bytes(identity),
        "evaluator/attempt/capture.json": _json_bytes(capture),
        **optional,
        "evaluator/result.json": _json_bytes(result_value),
        "decision/classification.json": _json_bytes(decision_value),
        "boundary.json": _json_bytes(boundary),
    }
    for relative, raw in members.items():
        _write_exclusive(staging / relative, raw)

    expected_roles = {**_DERIVATIVE_REQUIRED_ROLES, **_derivative_optional_roles(capture)}
    actual_before_checksums = {
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file()
    }
    if actual_before_checksums != set(expected_roles):
        raise ValueError("derivative staging membership is invalid")
    checksum_rows = [
        _file_row(relative, expected_roles[relative], (staging / relative).read_bytes())
        for relative in sorted(expected_roles)
    ]
    checksums = {
        "schema": _DERIVATIVE_CHECKSUMS_SCHEMA_ID,
        "records": checksum_rows,
    }
    checksums["derivative_archive_identity"] = SUPPORT.fingerprint(checksums)
    _write_exclusive(staging / "checksums.json", _json_bytes(checksums))
    verified_staging = _verify_sealed_derivative_archive(
        staging,
        expected_derivative_identity=checksums["derivative_archive_identity"],
        require_canonical_destination=False,
        code_owned_rubric_bytes=instrument.corrected_rubric_bytes,
    )
    return finalize_derivative_archive(
        staging,
        destination,
        expected_derivative_identity=verified_staging.derivative_archive_identity,
        code_owned_rubric_bytes=instrument.corrected_rubric_bytes,
    )


def retain_post_dispatch_unsealed(
    *,
    staging: Path,
    preflight_fingerprint: str,
    instrument_fingerprint: str,
    attempt_id: str,
    attempt_fingerprint: str,
    failure_locus: str,
    exception: BaseException | None = None,
    state: str = "post_dispatch_unsealed",
) -> PostDispatchUnsealed:
    marker_path = staging / "post_dispatch_unsealed.json"
    try:
        partial = []
        for path in sorted(item for item in staging.rglob("*") if item.is_file()):
            if path == marker_path:
                continue
            relative = path.relative_to(staging).as_posix()
            raw = path.read_bytes()
            partial.append(
                {
                    "path": relative,
                    "raw_sha256": _sha256(raw),
                    "byte_length": len(raw),
                }
            )
        marker = {
            "schema_id": UNSEALED_SCHEMA_ID,
            "attempt_id": attempt_id,
            "attempt_fingerprint": attempt_fingerprint,
            "preflight_fingerprint": preflight_fingerprint,
            "instrument_fingerprint": instrument_fingerprint,
            "dispatch_started": (
                staging / "dispatch/dispatch-started.json"
            ).is_file(),
            "failure_locus": failure_locus,
            "state": state,
            "exception_type": type(exception).__name__ if exception else None,
            "exception_message": str(exception)[:2000] if exception else None,
            "partial_forensic_hashes": partial,
            "checksum_closed": False,
            "classification": None,
        }
        if not marker_path.exists():
            _write_exclusive(marker_path, _json_bytes(marker))
    except OSError:
        pass
    return PostDispatchUnsealed(
        staging_dir=staging,
        attempt_id=attempt_id,
        attempt_fingerprint=attempt_fingerprint,
        failure_locus=failure_locus,
        state=state,
    )


def _attempt_identity_from_tree(path: Path) -> tuple[str, str, str, str]:
    record = _object(
        (path / "preflight/record.json").read_bytes(),
        "derivative preflight record",
    )
    attempt = record.get("attempt")
    instrument = record.get("instrument")
    if not isinstance(attempt, dict) or not isinstance(instrument, dict):
        raise ValueError("derivative attempt identity is unavailable")
    values = (
        record.get("preflight_fingerprint"),
        instrument.get("instrument_fingerprint"),
        attempt.get("attempt_id"),
        attempt.get("attempt_fingerprint"),
    )
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError("derivative attempt identity is invalid")
    return values


def reconcile_derivative_rename(
    staging: Path,
    destination: Path,
    *,
    expected_derivative_identity: str,
    rename_exception: BaseException,
    code_owned_rubric_bytes: bytes | None = None,
) -> SealedDerivative | PostDispatchUnsealed:
    staging = Path(staging).resolve(strict=False)
    destination = Path(destination).resolve(strict=False)
    staging_exists = staging.is_dir()
    destination_exists = destination.is_dir()
    if destination_exists and not staging_exists:
        try:
            return _verify_sealed_derivative_archive(
                destination,
                expected_derivative_identity=expected_derivative_identity,
                require_canonical_destination=True,
                code_owned_rubric_bytes=code_owned_rubric_bytes,
            )
        except (OSError, ValueError):
            preflight, instrument, attempt_id, attempt = _attempt_identity_from_tree(
                destination
            )
            return retain_post_dispatch_unsealed(
                staging=destination,
                preflight_fingerprint=preflight,
                instrument_fingerprint=instrument,
                attempt_id=attempt_id,
                attempt_fingerprint=attempt,
                failure_locus="atomic_rename_ambiguous_destination",
                exception=rename_exception,
                state="ambiguous_unsealed",
            )
    if staging_exists:
        preflight, instrument, attempt_id, attempt = _attempt_identity_from_tree(
            staging
        )
        state = "ambiguous_unsealed" if destination_exists else (
            "post_dispatch_unsealed"
        )
        return retain_post_dispatch_unsealed(
            staging=staging,
            preflight_fingerprint=preflight,
            instrument_fingerprint=instrument,
            attempt_id=attempt_id,
            attempt_fingerprint=attempt,
            failure_locus=(
                "atomic_rename_ambiguous_both"
                if destination_exists
                else "atomic_rename"
            ),
            exception=rename_exception,
            state=state,
        )
    raise RuntimeError(
        "atomic rename left neither staging nor destination available"
    ) from rename_exception


def finalize_derivative_archive(
    staging: Path,
    destination: Path,
    *,
    expected_derivative_identity: str,
    code_owned_rubric_bytes: bytes | None = None,
) -> SealedDerivative | PostDispatchUnsealed:
    staging = Path(staging).resolve()
    destination = Path(destination).resolve(strict=False)
    if staging.parent != destination.parent:
        raise ValueError("staging and destination must share one direct-child root")
    _verify_sealed_derivative_archive(
        staging,
        expected_derivative_identity=expected_derivative_identity,
        require_canonical_destination=False,
        code_owned_rubric_bytes=code_owned_rubric_bytes,
    )
    try:
        if destination.exists():
            raise FileExistsError(f"derivative destination exists: {destination}")
        staging.rename(destination)
        return _verify_sealed_derivative_archive(
            destination,
            expected_derivative_identity=expected_derivative_identity,
            require_canonical_destination=True,
            code_owned_rubric_bytes=code_owned_rubric_bytes,
        )
    except BaseException as exc:
        return reconcile_derivative_rename(
            staging,
            destination,
            expected_derivative_identity=expected_derivative_identity,
            rename_exception=exc,
            code_owned_rubric_bytes=code_owned_rubric_bytes,
        )


def _verify_sealed_derivative_archive(
    archive_dir: Path,
    *,
    expected_derivative_identity: str | None = None,
    require_canonical_destination: bool,
    code_owned_rubric_bytes: bytes | None,
) -> SealedDerivative:
    archive = Path(archive_dir).resolve()
    if not archive.is_dir() or (archive / "post_dispatch_unsealed.json").exists():
        raise ValueError("sealed derivative archive is unavailable")
    actual = {
        path.relative_to(archive).as_posix()
        for path in archive.rglob("*")
        if path.is_file()
    }
    for relative in actual:
        lowered = relative.casefold()
        if (
            "compiler" in lowered
            or "handoff" in lowered
            or "checkpoint-2" in lowered
            or "successor-disposition" in lowered
        ):
            raise ValueError("sealed derivative contains forbidden boundary evidence")
    checksums = _object((archive / "checksums.json").read_bytes(), "derivative checksums")
    _require_keys(
        checksums,
        {"schema", "records", "derivative_archive_identity"},
        "derivative checksums",
    )
    if checksums["schema"] != _DERIVATIVE_CHECKSUMS_SCHEMA_ID or not isinstance(
        checksums["records"], list
    ):
        raise ValueError("derivative checksum schema is invalid")
    rows = checksums["records"]
    if checksums["derivative_archive_identity"] != SUPPORT.fingerprint(
        {"schema": checksums["schema"], "records": rows}
    ):
        raise ValueError("derivative archive identity mismatch")
    if (
        expected_derivative_identity is not None
        and checksums["derivative_archive_identity"] != expected_derivative_identity
    ):
        raise ValueError("unexpected derivative archive identity")
    capture = _object(
        (archive / "evaluator/attempt/capture.json").read_bytes(),
        "derivative attempt capture",
    )
    _require_keys(
        capture,
        {
            "schema",
            "outcome",
            "elapsed_ms",
            "exception_type",
            "exception_message",
            "failure_type",
            "has_adapter_request",
            "has_response",
            "has_error",
            "has_usage",
            "has_assistant_message",
            "provider_metadata",
            "tool_argument_indexes",
            "quiescent",
        },
        "derivative attempt capture",
    )
    if (
        capture["schema"]
        != "rook.lm9b_p.evaluator.continuation_attempt_capture:v1"
        or capture["outcome"] not in {"returned", "raised"}
        or capture["quiescent"] is not True
        or type(capture["elapsed_ms"]) is not int
        or capture["elapsed_ms"] < 0
    ):
        raise ValueError("derivative attempt capture is not complete and quiescent")
    if capture["outcome"] == "returned":
        if (
            capture["exception_type"] is not None
            or capture["exception_message"] is not None
            or capture["failure_type"] is not None
            or not isinstance(capture["provider_metadata"], dict)
            or capture["has_response"] is not True
            or capture["has_assistant_message"] is not True
        ):
            raise ValueError("returned evaluator attempt capture is invalid")
    elif (
        not isinstance(capture["exception_type"], str)
        or not isinstance(capture["exception_message"], str)
        or capture["provider_metadata"] is not None
        or capture["has_response"] is not False
        or capture["has_usage"] is not False
        or capture["has_assistant_message"] is not False
        or capture["tool_argument_indexes"] != []
    ):
        raise ValueError("raised evaluator attempt capture is invalid")
    expected_roles = {**_DERIVATIVE_REQUIRED_ROLES, **_derivative_optional_roles(capture)}
    if actual != set(expected_roles) | {"checksums.json"}:
        raise ValueError("sealed derivative archive file set is invalid")
    if [row.get("path") for row in rows] != sorted(expected_roles):
        raise ValueError("derivative checksum closure is invalid")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "role",
            "raw_sha256",
            "byte_length",
        }:
            raise ValueError("derivative checksum row is invalid")
        relative = row["path"]
        raw = (archive / relative).read_bytes()
        if (
            row["role"] != expected_roles[relative]
            or row["raw_sha256"] != _sha256(raw)
            or row["byte_length"] != len(raw)
        ):
            raise ValueError(f"derivative checksum mismatch: {relative}")

    identity = _object((archive / "identity.json").read_bytes(), "derivative identity")
    if identity.get("schema_id") != DERIVATIVE_SCHEMA_ID:
        raise ValueError("derivative identity schema mismatch")
    preflight_record = _object(
        (archive / "preflight/record.json").read_bytes(),
        "derivative preflight record",
    )
    supplied_preflight = preflight_record.get("preflight_fingerprint")
    if supplied_preflight != SUPPORT.fingerprint(
        {
            key: value
            for key, value in preflight_record.items()
            if key != "preflight_fingerprint"
        }
    ):
        raise ValueError("derivative preflight identity mismatch")
    verified_source = _verified_historical_source_from_derivative(archive)
    source_identity = dict(verified_source.identity_value)
    if source_identity != preflight_record.get("source"):
        raise ValueError("derivative source identity mismatch")
    recipe = verified_source.final_recipe_bytes
    protocol = _object(
        (archive / "instrument/protocol-identity.json").read_bytes(),
        "derivative protocol identity",
    )
    instrument_identity = preflight_record.get("instrument")
    if not isinstance(instrument_identity, dict):
        raise ValueError("derivative instrument identity mismatch")
    preflight_file_rows = preflight_record.get("files")
    if not isinstance(preflight_file_rows, list):
        raise ValueError("derivative preflight file bindings are invalid")
    preflight_files = {
        row.get("path"): row
        for row in preflight_file_rows
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    copied_preflight_files = {
        "source-binding.json": "source/binding.json",
        "allowed-delta-manifest.json": (
            "instrument/allowed-delta-manifest.json"
        ),
        "mechanical-gate.json": "instrument/mechanical-gate.json",
        "rendered-evaluator-request.json": (
            "preflight/rendered-evaluator-request.json"
        ),
        "provider-call-request.json": "preflight/provider-call-request.json",
    }
    if set(preflight_files) != set(copied_preflight_files):
        raise ValueError("derivative preflight file bindings are incomplete")
    for source_path, derivative_path in copied_preflight_files.items():
        raw = (archive / derivative_path).read_bytes()
        row = preflight_files[source_path]
        if (
            row.get("raw_sha256") != _sha256(raw)
            or row.get("byte_length") != len(raw)
        ):
            raise ValueError(f"derivative instrument copy drift: {source_path}")

    corrected_rubric = (
        archive / "instrument/corrected-evaluator-rubric.json"
    ).read_bytes()
    allowed_delta = _object(
        (archive / "instrument/allowed-delta-manifest.json").read_bytes(),
        "derivative allowed delta",
    )
    provider_request = (
        archive / "preflight/provider-call-request.json"
    ).read_bytes()
    rendered_request = (
        archive / "preflight/rendered-evaluator-request.json"
    ).read_bytes()

    code_owned_rubric = (
        CORRECTED_RUBRIC_PATH.read_bytes()
        if code_owned_rubric_bytes is None
        else code_owned_rubric_bytes
    )
    if type(code_owned_rubric) is not bytes:
        raise TypeError("code-owned corrected rubric bytes are required")
    expected_instrument = assemble_continuation_instrument(
        verified_source,
        corrected_rubric_bytes=code_owned_rubric,
        reviewed_commit_sha=preflight_record.get("reviewed_commit_sha"),
    )
    expected_delta = {
        "schema": ALLOWED_DELTA_SCHEMA_ID,
        "rows": [dict(row) for row in expected_instrument.allowed_delta_rows],
    }
    if corrected_rubric != code_owned_rubric:
        raise ValueError("derivative corrected rubric differs from code-owned rubric")
    if allowed_delta != expected_delta:
        raise ValueError("derivative allowed delta is not constructively derived")
    if _object(
        (archive / "instrument/mechanical-gate.json").read_bytes(),
        "derivative mechanical gate",
    ) != _gate_value(expected_instrument.gate_result):
        raise ValueError("derivative mechanical gate is not constructively derived")
    if protocol != dict(expected_instrument.protocol_identity):
        raise ValueError("derivative protocol differs from code-owned protocol")
    if rendered_request != expected_instrument.rendered_request.raw_bytes:
        raise ValueError("derivative rendered request is not constructively derived")
    if provider_request != expected_instrument.provider_call_request_bytes:
        raise ValueError("derivative provider request is not constructively derived")
    if instrument_identity != _instrument_identity_value(expected_instrument):
        raise ValueError("derivative instrument identity is not constructively derived")
    SUPPORT.materialize_planner_evaluator_provider_call_request(provider_request)
    if provider_request != (
        archive / "evaluator/attempt/provider-call-request.json"
    ).read_bytes():
        raise ValueError("derivative evaluator request differs from instrument")
    if capture["outcome"] == "returned" and (
        capture["provider_metadata"].get("model_identity")
        != protocol.get("model")
        or capture["provider_metadata"].get("profile_identity")
        != protocol.get("provider_profile")
    ):
        raise ValueError("evaluator attempt provider identity mismatch")

    readiness_record = _object(
        (archive / "readiness/readiness-record.json").read_bytes(),
        "derivative readiness record",
    )
    credential_preflight = _object(
        (archive / "readiness/credential-preflight.json").read_bytes(),
        "derivative readiness credential preflight",
    )
    _require_keys(
        credential_preflight,
        {"credential_present"},
        "derivative readiness credential preflight",
    )
    if not isinstance(credential_preflight["credential_present"], dict):
        raise ValueError("derivative readiness credential evidence is invalid")
    readiness_verification = _object(
        (archive / "readiness/verification.json").read_bytes(),
        "derivative readiness verification",
    )
    _require_keys(
        readiness_verification,
        {
            "schema",
            "verified_at",
            "route_manifest_fingerprint",
            "readiness_record_fingerprint",
            "reviewed_commit_sha",
            "credential_present",
            "decision",
        },
        "derivative readiness verification",
    )
    if readiness_verification["schema"] != (
        "rook.lm9b_p.evaluator.continuation_readiness_verification:v1"
    ):
        raise ValueError("derivative readiness verification schema is invalid")
    manifest = READINESS.derive_routes(
        READINESS.role_routes_from_models(
            {"planner_evaluator": EVALUATOR_MODEL}
        ),
        api_key_env_for_model,
    )
    credential_present = credential_preflight["credential_present"]
    if (
        readiness_verification["route_manifest_fingerprint"]
        != manifest.manifest_fingerprint
        or readiness_verification["readiness_record_fingerprint"]
        != readiness_record.get("record_fingerprint")
        or readiness_verification["reviewed_commit_sha"]
        != preflight_record.get("reviewed_commit_sha")
        or readiness_verification["credential_present"] != credential_present
    ):
        raise ValueError("derivative readiness bindings are invalid")
    readiness_decision = READINESS.verify_launch_readiness(
        record=readiness_record,
        manifest=manifest,
        head_sha=preflight_record.get("reviewed_commit_sha"),
        now_iso=readiness_verification["verified_at"],
        credential_present=credential_present,
    )
    expected_readiness_decision = {
        "ok": readiness_decision.ok,
        "failures": list(readiness_decision.failures),
    }
    if (
        readiness_verification["decision"] != expected_readiness_decision
        or not readiness_decision.ok
    ):
        raise ValueError("derivative readiness decision is invalid")

    invocation = _object(
        (archive / "launch/invocation-binding.json").read_bytes(),
        "derivative invocation binding",
    )
    _require_keys(
        invocation,
        {
            "schema",
            "supplied_preflight_fingerprint",
            "transmit",
            "reviewed_commit_sha",
            "readiness_record_fingerprint",
            "readiness_verification_fingerprint",
            "attempt_id",
            "attempt_fingerprint",
        },
        "derivative invocation binding",
    )
    attempt_binding = preflight_record.get("attempt")
    if not isinstance(attempt_binding, dict):
        raise ValueError("derivative preflight attempt binding is invalid")
    if invocation != {
        "schema": "rook.lm9b_p.evaluator.continuation_invocation_binding:v1",
        "supplied_preflight_fingerprint": supplied_preflight,
        "transmit": True,
        "reviewed_commit_sha": preflight_record.get("reviewed_commit_sha"),
        "readiness_record_fingerprint": readiness_record.get(
            "record_fingerprint"
        ),
        "readiness_verification_fingerprint": SUPPORT.fingerprint(
            readiness_verification
        ),
        "attempt_id": attempt_binding.get("attempt_id"),
        "attempt_fingerprint": attempt_binding.get("attempt_fingerprint"),
    }:
        raise ValueError("derivative invocation binding is invalid")

    dispatch = _object(
        (archive / "dispatch/dispatch-started.json").read_bytes(),
        "derivative dispatch record",
    )
    expected_dispatch = {
        "schema": "rook.lm9b_p.evaluator.continuation_dispatch_started:v1",
        "attempt_id": attempt_binding.get("attempt_id"),
        "attempt_fingerprint": attempt_binding.get("attempt_fingerprint"),
        "provider_call_request_raw_sha256": _sha256(provider_request),
    }
    if dispatch != expected_dispatch:
        raise ValueError("derivative dispatch binding is invalid")

    result = _object(
        (archive / "evaluator/result.json").read_bytes(),
        "derivative evaluator result",
    )
    _require_keys(
        result,
        {"schema", "termination", "recommendation", "evidence", "quiescent"},
        "derivative evaluator result",
    )
    if (
        result["schema"]
        != "rook.lm9b_p.evaluator.continuation_evaluator_result:v1"
        or result["termination"]
        not in {"valid_recommendation", "provider_failure", "timeout", "malformed"}
        or result["quiescent"] is not True
        or not isinstance(result["evidence"], list)
    ):
        raise ValueError("derivative evaluator result values are invalid")

    if capture["outcome"] == "returned":
        if capture["has_usage"] is not True:
            raise ValueError("returned evaluator usage evidence is unavailable")
        assistant_message = _object(
            (archive / "evaluator/attempt/assistant-message.json").read_bytes(),
            "derivative evaluator assistant message",
        )
        usage = _object(
            (archive / "evaluator/attempt/usage.json").read_bytes(),
            "derivative evaluator usage",
        )
        captured_tool_arguments: list[bytes] = []
        calls = assistant_message.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                function = call.get("function") if isinstance(call, dict) else None
                argument = (
                    function.get("arguments")
                    if isinstance(function, dict)
                    else None
                )
                if isinstance(argument, str):
                    captured_tool_arguments.append(argument.encode("utf-8"))
        archived_tool_arguments = [
            (
                archive
                / f"evaluator/attempt/tool-arguments/{index:03d}.bin"
            ).read_bytes()
            for index in capture["tool_argument_indexes"]
        ]
        if captured_tool_arguments != archived_tool_arguments:
            raise ValueError("evaluator tool arguments differ from assistant evidence")
        evaluator = SUPPORT.derive_planner_evaluation_result(
            outcome="returned",
            response=SUPPORT.ProviderTurn(
                raw_request=(
                    (
                        archive
                        / "evaluator/attempt/adapter-request.bin"
                    ).read_bytes()
                    if capture["has_adapter_request"]
                    else b""
                ),
                raw_response=(
                    archive / "evaluator/attempt/response.bin"
                ).read_bytes(),
                assistant_message=assistant_message,
                usage=usage,
                provider_metadata=capture["provider_metadata"],
            ),
        )
    else:
        evaluator = SUPPORT.derive_planner_evaluation_result(
            outcome="raised",
            exception_type=capture["exception_type"],
            failure_type=capture["failure_type"],
        )
    expected_result = {
        "schema": "rook.lm9b_p.evaluator.continuation_evaluator_result:v1",
        "termination": evaluator.termination,
        "recommendation": evaluator.recommendation,
        "evidence": list(evaluator.evidence),
        "quiescent": evaluator.quiescent,
    }
    if result != expected_result:
        raise ValueError(
            "derivative evaluator result is not derived from captured evidence"
        )

    if result["termination"] == "valid_recommendation":
        if (
            result["recommendation"]
            not in {
                "semantically_faithful",
                "semantically_unfaithful",
                "evaluation_inconclusive",
            }
            or not result["evidence"]
            or capture["outcome"] != "returned"
        ):
            raise ValueError("valid evaluator recommendation evidence is invalid")
        criteria = {
            "brief_fidelity",
            "provenance_fidelity",
            "material_authority",
            "unresolved_intent_honesty",
            "implementation_leakage",
        }
        if any(
            not isinstance(row, dict)
            or set(row) != {"criterion_id", "finding"}
            or row["criterion_id"] not in criteria
            or not isinstance(row["finding"], str)
            or not row["finding"]
            for row in result["evidence"]
        ):
            raise ValueError("evaluator recommendation evidence is malformed")
    elif result["recommendation"] is not None or result["evidence"] != []:
        raise ValueError("failed evaluator result carries a semantic recommendation")
    decision = _object(
        (archive / "decision/classification.json").read_bytes(),
        "derivative classification",
    )
    _require_keys(
        decision,
        {"schema", "classification", "semantic_recommendation"},
        "derivative classification",
    )
    if decision["schema"] != (
        "rook.lm9b_p.evaluator.continuation_classification:v1"
    ):
        raise ValueError("derivative classification schema mismatch")
    classification = PLANNER_ARTIFACTS.derive_evaluated_recipe_classification(
        evaluator,
        final_recipe_bytes=recipe,
    )
    if (
        decision.get("classification") != classification
        or decision.get("semantic_recommendation") != evaluator.recommendation
    ):
        raise ValueError("derivative classification is not mechanically derived")
    expected_boundary = {
        "schema": "rook.lm9b_p.evaluator.continuation_boundary:v1",
        "derivative_observation": True,
        "replaces_historical_result": False,
        "planner_entry": "absent",
        "compiler_entry": "absent",
        "checkpoint_2": "not_evaluated",
        "execution_permitted": False,
    }
    if _object((archive / "boundary.json").read_bytes(), "derivative boundary") != expected_boundary:
        raise ValueError("derivative boundary is invalid")
    identity_subject = {
        "preflight_fingerprint": supplied_preflight,
        "instrument_fingerprint": instrument_identity.get("instrument_fingerprint"),
        "attempt_id": preflight_record.get("attempt", {}).get("attempt_id"),
        "attempt_fingerprint": preflight_record.get("attempt", {}).get(
            "attempt_fingerprint"
        ),
        "reviewed_commit_sha": preflight_record.get("reviewed_commit_sha"),
        "model": protocol.get("model"),
        "provider_profile": protocol.get("provider_profile"),
        "canonical_destination": preflight_record.get("attempt", {}).get(
            "canonical_destination"
        ),
        "evaluator_result": result,
        "classification": decision,
    }
    expected_identity = {
        "schema_id": DERIVATIVE_SCHEMA_ID,
        **{
            key: value
            for key, value in identity_subject.items()
            if key not in {"evaluator_result", "classification"}
        },
        "derivative_subject_fingerprint": SUPPORT.fingerprint(identity_subject),
    }
    if identity != expected_identity:
        raise ValueError("derivative subject identity mismatch")
    canonical_destination_value = attempt_binding.get("canonical_destination")
    if not isinstance(canonical_destination_value, str):
        raise ValueError("derivative canonical destination is invalid")
    canonical_destination = Path(canonical_destination_value).resolve(
        strict=False
    )
    if str(canonical_destination) != canonical_destination_value:
        raise ValueError("derivative canonical destination is not canonical")
    if require_canonical_destination and archive != canonical_destination:
        raise ValueError("derivative archive location differs from its destination")
    return SealedDerivative(
        archive_dir=archive,
        derivative_archive_identity=checksums["derivative_archive_identity"],
        classification=classification,
        identity=MappingProxyType(identity),
    )


def verify_sealed_derivative_archive(
    archive_dir: Path,
    *,
    expected_derivative_identity: str | None = None,
) -> SealedDerivative:
    """Verify an official derivative at its identity-bound final destination."""

    return _verify_sealed_derivative_archive(
        archive_dir,
        expected_derivative_identity=expected_derivative_identity,
        require_canonical_destination=True,
        code_owned_rubric_bytes=None,
    )


__all__ = (
    "ALLOWED_DELTA_SCHEMA_ID",
    "ATTEMPT_ID_PATTERN",
    "AttemptBinding",
    "ContinuationInstrument",
    "DERIVATIVE_SCHEMA_ID",
    "EVALUATOR_MODEL",
    "EVALUATOR_TEMPERATURE",
    "HistoricalSourcePins",
    "PREFLIGHT_SCHEMA_ID",
    "PRODUCTION_SOURCE_PINS",
    "PROVIDER_PROFILE_ID",
    "PostDispatchUnsealed",
    "SealedDerivative",
    "UNSEALED_SCHEMA_ID",
    "VerifiedContinuationPreflight",
    "VerifiedHistoricalSource",
    "_verify_historical_source",
    "assemble_continuation_instrument",
    "bind_attempt",
    "finalize_derivative_archive",
    "reconcile_derivative_rename",
    "reserve_staging",
    "retain_post_dispatch_unsealed",
    "seal_derivative_archive",
    "verify_historical_source",
    "verify_preflight_archive",
    "verify_sealed_derivative_archive",
    "write_dispatch_started",
    "write_preflight_archive",
    "write_static_derivative_snapshot",
)
