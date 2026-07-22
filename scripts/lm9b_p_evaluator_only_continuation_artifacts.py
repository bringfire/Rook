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
PROVIDER_PROFILE_ID = "litellm.completion.tool_calling.no_parallel:v1"
EVALUATOR_MODEL = "gpt-5.4"
EVALUATOR_TEMPERATURE = 0.0
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
    input_manifest_bytes: bytes
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


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


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

    identity_value = MappingProxyType(
        {
            "source_root": str(root),
            "root_manifest_raw_sha256": pins.root_manifest_raw_sha256.casefold(),
            "checkpoint_aggregate_identity": pins.checkpoint_aggregate_identity,
            "historical_commit_sha": pins.historical_commit_sha,
            "historical_classification": pins.historical_classification,
            "historical_checkpoint_2": pins.historical_checkpoint_2,
            "recipe_raw_sha256": pins.recipe_raw_sha256,
            "ratified_recipe_fingerprint": pins.ratified_recipe_fingerprint,
            "historical_recipe_fingerprint": pins.historical_recipe_fingerprint,
        }
    )
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
            "schema": "rook.lm9b_p.evaluator_continuation_source_binding:v1",
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
    instrument_identity = {
        "instrument_fingerprint": instrument.instrument_fingerprint,
        "protocol_identity": dict(instrument.protocol_identity),
        "historical_rubric_raw_sha256": next(
            row["source_raw_sha256"]
            for row in instrument.allowed_delta_rows
            if row["role"] == "evaluation_rubric"
        ),
        "historical_rubric_fingerprint": next(
            row["source_canonical_fingerprint"]
            for row in instrument.allowed_delta_rows
            if row["role"] == "evaluation_rubric"
        ),
        "corrected_rubric_raw_sha256": _sha256(instrument.corrected_rubric_bytes),
        "corrected_rubric_fingerprint": SUPPORT.fingerprint(
            _object(instrument.corrected_rubric_bytes, "corrected rubric")
        ),
        "rendered_evaluator_request_raw_sha256": instrument.rendered_request.raw_sha256,
        "provider_call_request_raw_sha256": _sha256(
            instrument.provider_call_request_bytes
        ),
    }
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
    if source_binding.pop("schema") != (
        "rook.lm9b_p.evaluator_continuation_source_binding:v1"
    ):
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
    "UNSEALED_SCHEMA_ID",
    "VerifiedContinuationPreflight",
    "VerifiedHistoricalSource",
    "_verify_historical_source",
    "assemble_continuation_instrument",
    "bind_attempt",
    "verify_historical_source",
    "verify_preflight_archive",
    "write_preflight_archive",
)
