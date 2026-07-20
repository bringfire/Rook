"""Frozen authority loading and R01-free LM9B-C handoff for LM9B-P."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from jsonschema import Draft202012Validator
from rook.validation_kernel.canonical_json import canonical_fingerprint, sha256_prefixed
from rook.validation_kernel.owned_json import own_trusted_json

from lm9b_p_planner_recipe_transfer_support import (
    NormalizationProfile,
    fingerprint,
    fingerprint_without,
    load_normalization_profile,
    parse_strict_json,
    resolve_json_pointer,
)


_VOCABULARY_FILES = {
    "semantic_authority_code_vocabulary": "semantic_authority_code_vocabulary.json",
    "semantic_capability_code_vocabulary": "semantic_capability_code_vocabulary.json",
    "worker_slot_code_vocabulary": "worker_slot_code_vocabulary.json",
    "semantic_materiality_code_vocabulary": "semantic_materiality_code_vocabulary.json",
    "semantic_value_schema_registry": "semantic_value_schema_registry.json",
}
_AUTHORITY_FILES = {
    "task_envelope": "task_envelope.json",
    "environment_snapshot": "environment_snapshot.json",
    "planning_policy": "planning_policy.json",
}


@dataclass(frozen=True)
class FrozenPlannerAuthority:
    fixture_dir: Path
    artifacts: Mapping[str, Mapping[str, object]]
    vocabularies: Mapping[str, Mapping[str, object]]
    payload_schema_registry: Mapping[str, object]
    capability_registry: Mapping[str, object]
    recipe_schema: Mapping[str, object]
    normalization_profile: NormalizationProfile
    attempt_context: Mapping[str, object]
    evaluated_at: str


@dataclass(frozen=True)
class Lm9bcHandoff:
    fixture_dir: Path
    manifest: Mapping[str, object]
    archived_recipe_bytes: bytes
    compiler_renderer_id: str
    attempt_context_fingerprint: str


def _object(path: Path) -> Mapping[str, object]:
    value = parse_strict_json(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must be an object")
    return value


def _verify_fingerprint(value: Mapping[str, object], field: str, label: str) -> None:
    if value.get(field) != fingerprint_without(value, field):
        raise ValueError(f"{label} fingerprint mismatch")


def _instant(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"invalid {label}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"invalid {label}")
    return parsed


def _require_fresh(
    value: Mapping[str, object], evaluated_at: datetime, label: str
) -> None:
    observed_field = "observed_at" if "observed_at" in value else "issued_at"
    observed = _instant(value[observed_field], f"{label} {observed_field}")
    expires = _instant(value["expires_at"], f"{label} expires_at")
    if not observed <= evaluated_at < expires:
        raise ValueError(f"{label} is stale at frozen evaluation time")


def load_planner_authority_context(fixture_dir: Path) -> FrozenPlannerAuthority:
    fixture_dir = Path(fixture_dir).resolve()
    attempt_context = _object(fixture_dir / "attempt_context.json")
    if set(attempt_context) != {
        "schema",
        "attempt_id",
        "evaluated_at",
        "trusted_clock_source",
        "task_session_id",
        "environment_session_id",
        "capability_registry_session_id",
        "context_fingerprint",
    } or attempt_context.get("schema") != "rook.lm9b_p.probe_attempt_context:v1":
        raise ValueError("invalid attempt context shape")
    _verify_fingerprint(attempt_context, "context_fingerprint", "attempt context")
    if attempt_context.get("trusted_clock_source") != "deterministic_fixture":
        raise ValueError("attempt context requires deterministic fixture clock")
    evaluated_at_text = attempt_context.get("evaluated_at")
    evaluated_at = _instant(evaluated_at_text, "attempt evaluated_at")
    assert isinstance(evaluated_at_text, str)
    artifacts = {
        artifact_id: _object(fixture_dir / filename)
        for artifact_id, filename in _AUTHORITY_FILES.items()
    }
    for artifact_id, artifact in artifacts.items():
        _verify_fingerprint(artifact, "artifact_fingerprint", artifact_id)

    vocabularies = {
        name: _object(fixture_dir / filename)
        for name, filename in _VOCABULARY_FILES.items()
    }
    for name, vocabulary in vocabularies.items():
        _verify_fingerprint(vocabulary, "vocabulary_fingerprint", name)

    payload_registry = _object(fixture_dir / "payload_schema_registry.json")
    _verify_fingerprint(payload_registry, "registry_fingerprint", "payload schema registry")
    payload_entries = {
        entry["schema_id"]: entry for entry in payload_registry["entries"]
    }
    if len(payload_entries) != len(payload_registry["entries"]):
        raise ValueError("duplicate payload schema ID")
    for artifact_id in ("task_envelope", "environment_snapshot"):
        artifact = artifacts[artifact_id]
        entry = payload_entries.get(artifact["payload_schema"])
        if entry is None:
            raise ValueError(f"payload schema is unbound: {artifact_id}")
        if entry["schema_fingerprint"] != fingerprint(entry["schema_document"]):
            raise ValueError(f"payload schema fingerprint mismatch: {artifact_id}")
        if artifact["payload_schema_fingerprint"] != entry["schema_fingerprint"]:
            raise ValueError(f"artifact payload schema mismatch: {artifact_id}")
        payload_errors = list(
            Draft202012Validator(entry["schema_document"]).iter_errors(
                artifact["payload"]
            )
        )
        if payload_errors:
            raise ValueError(f"artifact payload schema failed: {artifact_id}")
        pointers: set[str] = set()
        for binding in artifact["value_bindings"]:
            pointer = binding["json_pointer"]
            if pointer in pointers:
                raise ValueError(f"duplicate value binding pointer: {artifact_id}")
            pointers.add(pointer)
            resolved = resolve_json_pointer(artifact["payload"], pointer)
            expected = fingerprint(
                {"schema": binding["value_schema"], "value": resolved}
            )
            if binding["typed_value_fingerprint"] != expected:
                raise ValueError(f"typed value fingerprint mismatch: {artifact_id}")

    capability_registry = _object(fixture_dir / "capability_registry.json")
    _verify_fingerprint(capability_registry, "registry_fingerprint", "capability registry")
    if artifacts["task_envelope"].get("task_session_id") != attempt_context.get(
        "task_session_id"
    ):
        raise ValueError("task session mismatch")
    if artifacts["environment_snapshot"].get(
        "environment_session_id"
    ) != attempt_context.get("environment_session_id"):
        raise ValueError("environment session mismatch")
    if capability_registry.get("registry_session_id") != attempt_context.get(
        "capability_registry_session_id"
    ):
        raise ValueError("capability registry session mismatch")
    _require_fresh(artifacts["environment_snapshot"], evaluated_at, "environment snapshot")
    _require_fresh(artifacts["planning_policy"], evaluated_at, "planning policy")
    _require_fresh(capability_registry, evaluated_at, "capability registry")
    recipe_schema = _object(fixture_dir / "planner_recipe_probe_schema.json")
    profile = load_normalization_profile(fixture_dir / "recipe_normalization_profile.json")
    return FrozenPlannerAuthority(
        fixture_dir=fixture_dir,
        artifacts=artifacts,
        vocabularies=vocabularies,
        payload_schema_registry=payload_registry,
        capability_registry=capability_registry,
        recipe_schema=recipe_schema,
        normalization_profile=profile,
        attempt_context=attempt_context,
        evaluated_at=evaluated_at_text,
    )


def _load_lm9bc_artifacts_module():
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    path = Path(__file__).with_name("lm9b_c_compiler_sufficiency_artifacts.py")
    name = "lm9b_c_compiler_sufficiency_artifacts_for_lm9b_p"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("LM9B-C artifacts module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_bytes(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)


def build_lm9bc_handoff(
    *,
    accepted_recipe_bytes: bytes,
    accepted_recipe_fingerprint: str,
    planner_fixture_dir: Path,
    compiler_fixture_dir: Path,
    destination: Path,
) -> Lm9bcHandoff:
    """Build the LM9B-C boundary without reading R01 or its source manifest."""

    planner_fixture_dir = Path(planner_fixture_dir).resolve()
    compiler_fixture_dir = Path(compiler_fixture_dir).resolve()
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)

    planner_authority = load_planner_authority_context(planner_fixture_dir)

    recipe = parse_strict_json(accepted_recipe_bytes)
    if not isinstance(recipe, dict):
        raise ValueError("accepted recipe must be an object")
    if recipe.get("recipe_fingerprint") != accepted_recipe_fingerprint:
        raise ValueError("accepted recipe fingerprint mismatch")

    rows = (
        ("recipe", "accepted_recipe.json", accepted_recipe_bytes),
        ("authority.task_envelope", "task_envelope.json", (planner_fixture_dir / "task_envelope.json").read_bytes()),
        ("authority.environment_snapshot", "environment_snapshot.json", (planner_fixture_dir / "environment_snapshot.json").read_bytes()),
        ("authority.planning_policy", "planning_policy.json", (planner_fixture_dir / "planning_policy.json").read_bytes()),
        ("implementation_context", "implementation_context.json", (compiler_fixture_dir / "implementation_context.json").read_bytes()),
        ("exclusion_policy", "exclusion_policy.json", (compiler_fixture_dir / "exclusion_policy.json").read_bytes()),
        ("evaluation_rubric", "evaluation_rubric.json", (compiler_fixture_dir / "evaluation_rubric.json").read_bytes()),
    )
    records: list[dict[str, object]] = []
    for role, filename, raw in rows:
        value = parse_strict_json(raw)
        if not isinstance(value, dict):
            raise ValueError(f"handoff record is not an object: {role}")
        _write_bytes(destination / filename, raw)
        records.append(
            {
                "role": role,
                "path": filename,
                "raw_sha256": sha256_prefixed(raw),
                "canonical_fingerprint": canonical_fingerprint(own_trusted_json(value)),
            }
        )

    lm9bc = _load_lm9bc_artifacts_module()
    manifest = {
        "schema": lm9bc.MANIFEST_SCHEMA_ID,
        "renderer_id": lm9bc.COMPILER_RENDERER_ID,
        "probe_attempt_context": planner_authority.attempt_context,
        "records": records,
    }
    manifest_raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write_bytes(destination / "input_manifest.json", manifest_raw)
    return Lm9bcHandoff(
        fixture_dir=destination,
        manifest=manifest,
        archived_recipe_bytes=(destination / "accepted_recipe.json").read_bytes(),
        compiler_renderer_id=lm9bc.COMPILER_RENDERER_ID,
        attempt_context_fingerprint=planner_authority.attempt_context[
            "context_fingerprint"
        ],
    )


__all__ = (
    "FrozenPlannerAuthority",
    "Lm9bcHandoff",
    "build_lm9bc_handoff",
    "load_planner_authority_context",
)
