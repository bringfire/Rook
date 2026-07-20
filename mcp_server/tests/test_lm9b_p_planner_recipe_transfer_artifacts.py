from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLANNER_FIXTURES = ROOT / "scripts" / "lm9b_p_fixtures"
COMPILER_FIXTURES = ROOT / "scripts" / "lm9b_c_fixtures"


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SUPPORT = _load_script("lm9b_p_planner_recipe_transfer_support")
ARTIFACTS = _load_script("lm9b_p_planner_recipe_transfer_artifacts")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_bytes())


def test_corrected_authority_preserves_facts_not_placeholder_bytes() -> None:
    for filename in ("task_envelope.json", "environment_snapshot.json"):
        corrected = _json(PLANNER_FIXTURES / filename)
        historical = _json(COMPILER_FIXTURES / filename)
        assert corrected["payload"] == historical["payload"]
        assert (PLANNER_FIXTURES / filename).read_bytes() != (
            COMPILER_FIXTURES / filename
        ).read_bytes()
        assert corrected["artifact_fingerprint"] == SUPPORT.fingerprint_without(
            corrected, "artifact_fingerprint"
        )


def test_value_binding_fingerprints_cover_schema_and_resolved_value() -> None:
    for filename in ("task_envelope.json", "environment_snapshot.json"):
        artifact = _json(PLANNER_FIXTURES / filename)
        for binding in artifact["value_bindings"]:
            resolved = SUPPORT.resolve_json_pointer(
                artifact["payload"], binding["json_pointer"]
            )
            subject = {"schema": binding["value_schema"], "value": resolved}
            assert binding["typed_value_fingerprint"] == SUPPORT.fingerprint(subject)


def test_payload_schema_registry_binds_both_complete_schemas() -> None:
    registry = _json(PLANNER_FIXTURES / "payload_schema_registry.json")
    assert registry["schema"] == "rook.payload_schema_registry:v1"
    assert [item["schema_id"] for item in registry["entries"]] == [
        "rook.lm9b_c.r01_environment_payload:v1",
        "rook.lm9b_c.r01_task_payload:v1",
    ]
    for entry in registry["entries"]:
        assert entry["schema_fingerprint"] == SUPPORT.fingerprint(
            entry["schema_document"]
        )
    assert registry["registry_fingerprint"] == SUPPORT.fingerprint_without(
        registry, "registry_fingerprint"
    )


def test_planning_policy_remains_exact_historical_control() -> None:
    assert (PLANNER_FIXTURES / "planning_policy.json").read_bytes() == (
        COMPILER_FIXTURES / "planning_policy.json"
    ).read_bytes()


def test_capability_registry_is_closed_available_unavailable_control() -> None:
    registry = _json(PLANNER_FIXTURES / "capability_registry.json")
    assert set(registry) == {
        "schema",
        "registry_id",
        "registry_session_id",
        "observed_at",
        "expires_at",
        "entries",
        "registry_fingerprint",
    }
    assert registry["registry_fingerprint"] == SUPPORT.fingerprint_without(
        registry, "registry_fingerprint"
    )
    assert [entry["capability_code"] for entry in registry["entries"]] == [
        "construct_parametric_geometry",
        "manage_document_layers",
    ]
    assert all(
        set(entry)
        == {
            "capability_code",
            "availability",
            "implementation_refs",
            "constraints_fingerprint",
        }
        for entry in registry["entries"]
    )
    assert registry["entries"][0]["availability"] == "available"
    assert registry["entries"][0]["implementation_refs"]
    assert registry["entries"][1]["availability"] == "unavailable"
    assert registry["entries"][1]["implementation_refs"] == []


def test_production_authority_loader_reauthenticates_all_companions() -> None:
    authority = ARTIFACTS.load_planner_authority_context(PLANNER_FIXTURES)
    assert set(authority.artifacts) == {
        "task_envelope",
        "environment_snapshot",
        "planning_policy",
    }
    assert len(authority.payload_schema_registry["entries"]) == 2
    assert len(authority.vocabularies) == 5
    assert authority.evaluated_at == "2026-07-20T11:00:00Z"
    assert authority.attempt_context["context_fingerprint"] == SUPPORT.fingerprint_without(
        authority.attempt_context, "context_fingerprint"
    )


@pytest.mark.parametrize(
    ("filename", "field", "value", "message"),
    [
        ("environment_snapshot.json", "expires_at", "2026-07-20T10:59:59Z", "stale"),
        ("planning_policy.json", "expires_at", "2026-07-20T10:59:59Z", "stale"),
        ("capability_registry.json", "expires_at", "2026-07-20T10:59:59Z", "stale"),
        (
            "environment_snapshot.json",
            "environment_session_id",
            "wrong-session",
            "session mismatch",
        ),
    ],
)
def test_authority_admission_is_bound_to_frozen_time_and_sessions(
    tmp_path: Path, filename: str, field: str, value: str, message: str
) -> None:
    copied = tmp_path / "fixtures"
    shutil.copytree(PLANNER_FIXTURES, copied)
    artifact = _json(copied / filename)
    artifact[field] = value
    fingerprint_field = (
        "registry_fingerprint" if filename == "capability_registry.json" else "artifact_fingerprint"
    )
    artifact[fingerprint_field] = SUPPORT.fingerprint_without(artifact, fingerprint_field)
    (copied / filename).write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        ARTIFACTS.load_planner_authority_context(copied)
