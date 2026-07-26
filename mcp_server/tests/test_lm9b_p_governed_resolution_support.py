from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
MCP_SRC = ROOT / "mcp_server" / "src"
for entry in (SCRIPTS, MCP_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import lm9_semantic_typed_values as TYPED_VALUES
import lm9b_p_governed_resolution_artifacts as ARTIFACTS
import lm9_typed_fact_carrier_artifacts as CARRIER


HISTORICAL_SOURCE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts\2026-07-22-visibility-intervention"
)
DERIVATIVE_ARCHIVE = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-22-evaluator-only-continuation"
    r"\derivatives\visibility-evaluator-01"
)
CARRIER_QUALIFICATION = Path(
    r"C:\Users\bring\rook-lm9b-p-attempts"
    r"\2026-07-23-typed-fact-carrier-post-merge"
    r"\d6330a61a21d56abf16af6ba3b8f1678ede2c3ec"
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _binding(envelope: dict[str, object], key: str) -> dict[str, object]:
    rows = envelope["value_bindings"]
    assert isinstance(rows, list)
    return next(row for row in rows if row["semantic_key"] == key)


def _reclose(envelope: dict[str, object]) -> bytes:
    envelope["artifact_fingerprint"] = TYPED_VALUES.fingerprint_without(
        envelope, "artifact_fingerprint"
    )
    return _canonical_bytes(envelope)


def _reclose_fact(envelope: dict[str, object], key: str) -> bytes:
    facts = envelope["payload"]["facts"]
    fact = facts[key]
    row = _binding(envelope, key)
    row["value_schema"] = fact["schema"]
    row["typed_value_fingerprint"] = TYPED_VALUES.fingerprint(fact)
    return _reclose(envelope)


def _load_with_successor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: bytes
) -> object:
    successor = tmp_path / "successor.json"
    successor.write_bytes(raw)
    monkeypatch.setattr(ARTIFACTS, "SUCCESSOR_ENVELOPE_PATH", successor)
    return ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=successor,
    )


AUTHORITY_MUTATIONS = (
    "missing_successor_key",
    "extra_successor_key",
    "wrong_delta_schema",
    "wrong_delta_pointer",
    "wrong_delta_unit_context",
    "wrong_task_session",
    "retained_typed_value",
    "retained_authority_kind",
    "retained_provenance",
)


@pytest.mark.parametrize("mutation", AUTHORITY_MUTATIONS)
def test_task2_authority_mutation_refuses_fully_reclosed_successor(
    mutation: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    envelope = json.loads(ARTIFACTS.SUCCESSOR_ENVELOPE_PATH.read_bytes())
    facts = envelope["payload"]["facts"]
    rows = envelope["value_bindings"]
    if mutation == "missing_successor_key":
        del facts["grid_spacing"]
        rows.remove(_binding(envelope, "grid_spacing"))
        raw = _reclose(envelope)
    elif mutation == "extra_successor_key":
        facts["unrelated_extra"] = {
            "schema": "rook.semantic_string:v1",
            "value": "extra",
            "unit": None,
            "unit_context_ref": None,
        }
        rows.append(
            {
                "authority_kind": "user_fact",
                "binding_id": "task-value.unrelated_extra",
                "json_pointer": "/facts/unrelated_extra",
                "provenance": {
                    "issuer_id": "lm9b-p-governed-resolution-fixture",
                    "issuer_kind": "deterministic_fixture",
                },
                "semantic_key": "unrelated_extra",
                "typed_value_fingerprint": TYPED_VALUES.fingerprint(
                    facts["unrelated_extra"]
                ),
                "value_schema": "rook.semantic_string:v1",
            }
        )
        rows.sort(key=lambda row: row["semantic_key"].encode("utf-16-be"))
        raw = _reclose(envelope)
    elif mutation == "wrong_delta_schema":
        facts["grid_spacing"] = {
            "schema": "rook.semantic_string:v1",
            "value": "2",
            "unit": None,
            "unit_context_ref": None,
        }
        raw = _reclose_fact(envelope, "grid_spacing")
    elif mutation == "wrong_delta_pointer":
        _binding(envelope, "grid_spacing")["json_pointer"] = "/facts/minimum_height"
        raw = _reclose(envelope)
    elif mutation == "wrong_delta_unit_context":
        facts["grid_spacing"]["unit_context_ref"] = {
            "kind": "artifact_value",
            "artifact_id": "environment_snapshot",
            "json_pointer": "/document/other_unit_context",
        }
        raw = _reclose_fact(envelope, "grid_spacing")
    elif mutation == "wrong_task_session":
        envelope["task_session_id"] = "other-task-session"
        raw = _reclose(envelope)
    elif mutation == "retained_typed_value":
        facts["element_kind"]["value"] = "sphere"
        raw = _reclose_fact(envelope, "element_kind")
    elif mutation == "retained_authority_kind":
        _binding(envelope, "element_kind")["authority_kind"] = "task_fact"
        raw = _reclose(envelope)
    else:
        _binding(envelope, "element_kind")["provenance"]["issuer_id"] = (
            "different-fixture-issuer"
        )
        raw = _reclose(envelope)

    with pytest.raises(ValueError):
        _load_with_successor(monkeypatch, tmp_path, raw)


def test_task2_authority_mutation_rejects_unreviewed_successor_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fully valid reclosed fixture is still not reviewed instrument input."""
    envelope = json.loads(ARTIFACTS.SUCCESSOR_ENVELOPE_PATH.read_bytes())
    envelope["issued_at"] = "2026-07-23T12:00:01Z"
    raw = _reclose(envelope)
    with pytest.raises(ValueError, match="reviewed (Git object|checkout)"):
        _load_with_successor(monkeypatch, tmp_path, raw)


def test_task2_authority_mutation_rejects_extra_carrier_contract() -> None:
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    object.__setattr__(
        sources,
        "exact_contract_bytes",
        {**sources.exact_contract_bytes, "extra": b"{}"},
    )
    with pytest.raises(ValueError, match="closure-issued"):
        ARTIFACTS.consume_verified_resolution_sources(sources)


def test_task2_authority_mutation_rejects_parent_established_unresolved_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = CARRIER.derive_authority_partition

    def overlapping_partition(**kwargs: object):
        value = original(**kwargs)
        overlap = value.required_delta_keys[0]
        return replace(
            value,
            parent_keys=tuple(
                sorted((*value.parent_keys, overlap), key=lambda key: key.encode("utf-16-be"))
            ),
        )

    monkeypatch.setattr(CARRIER, "derive_authority_partition", overlapping_partition)
    sources = ARTIFACTS.load_verified_resolution_sources(
        historical_source_dir=HISTORICAL_SOURCE,
        derivative_archive=DERIVATIVE_ARCHIVE,
        derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
        carrier_qualification_archive=CARRIER_QUALIFICATION,
        carrier_qualification_identity=(
            ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
        ),
        repo_root=ROOT,
        successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
    )
    with pytest.raises(ValueError, match="overlap"):
        ARTIFACTS.assemble_resolution_instrument(
            sources=sources,
            isolation_policy_path=ARTIFACTS.ISOLATION_POLICY_PATH,
            evaluation_rubric_path=ARTIFACTS.EVALUATION_RUBRIC_PATH,
        )


@pytest.mark.parametrize("role", ("authority.environment_snapshot", "authority.planning_policy"))
def test_task2_authority_mutation_rejects_replacement_historical_authority_source(
    role: str, tmp_path: Path
) -> None:
    replacement_source = tmp_path / role.replace(".", "-")
    replacement_source.mkdir()
    with pytest.raises(ValueError, match="historical source location"):
        ARTIFACTS.load_verified_resolution_sources(
            historical_source_dir=replacement_source,
            derivative_archive=DERIVATIVE_ARCHIVE,
            derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
            carrier_qualification_archive=CARRIER_QUALIFICATION,
            carrier_qualification_identity=(
                ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
            ),
            repo_root=ROOT,
            successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "typed_value_helper_drift",
        "carrier_artifact_helper_drift",
        "profile_drift",
        "registry_drift",
        "payload_schema_drift",
        "carrier_runtime_drift",
        "carrier_contract_identity_drift",
    ),
)
def test_task2_authority_mutation_rejects_carrier_instrument_drift(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if mutation in {"typed_value_helper_drift", "carrier_artifact_helper_drift"}:
        original = ARTIFACTS._git_object
        target = (
            "scripts/lm9_semantic_typed_values.py"
            if mutation == "typed_value_helper_drift"
            else "scripts/lm9_typed_fact_carrier_artifacts.py"
        )

        def changed_git_object(repo: Path, commit: str, relative_path: str) -> bytes:
            raw = original(repo, commit, relative_path)
            if commit != ARTIFACTS.HISTORICAL_CARRIER_COMMIT and relative_path == target:
                return raw + b"\n# drift"
            return raw

        monkeypatch.setattr(ARTIFACTS, "_git_object", changed_git_object)
    elif mutation == "profile_drift":
        monkeypatch.setattr(TYPED_VALUES, "PROFILE_ID", "rook.json_schema_profile:drift")
    elif mutation in {"registry_drift", "payload_schema_drift"}:
        changed = tmp_path / f"{mutation}.json"
        changed.write_bytes(b"{}")
        monkeypatch.setattr(
            CARRIER,
            "REGISTRY_PATH" if mutation == "registry_drift" else "PAYLOAD_SCHEMA_PATH",
            changed,
        )
    elif mutation == "carrier_runtime_drift":
        original_runtime = TYPED_VALUES.current_runtime_identity

        def changed_runtime():
            value = original_runtime()
            return replace(value, version=value.version + "-drift")

        monkeypatch.setattr(TYPED_VALUES, "current_runtime_identity", changed_runtime)
    else:
        monkeypatch.setattr(TYPED_VALUES, "HELPER_CONTRACT_ID", "lm9.typed_values:drift")

    with pytest.raises((TypeError, ValueError, subprocess.CalledProcessError)):
        ARTIFACTS.load_verified_resolution_sources(
            historical_source_dir=HISTORICAL_SOURCE,
            derivative_archive=DERIVATIVE_ARCHIVE,
            derivative_identity=ARTIFACTS.OFFICIAL_DERIVATIVE_IDENTITY,
            carrier_qualification_archive=CARRIER_QUALIFICATION,
            carrier_qualification_identity=(
                ARTIFACTS.HISTORICAL_CARRIER_QUALIFICATION_IDENTITY
            ),
            repo_root=ROOT,
            successor_envelope_path=ARTIFACTS.SUCCESSOR_ENVELOPE_PATH,
        )
