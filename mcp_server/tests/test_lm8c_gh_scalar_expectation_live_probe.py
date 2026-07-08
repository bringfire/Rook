from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8c_gh_scalar_expectation_live_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8c_gh_scalar_expectation_live_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_worker_shape() -> None:
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_overrides_are_exploratory_unless_explicitly_marked_canonical() -> None:
    args = PROBE._args(["--model", "qwen3:14b"])
    assert args.canonical_evidence is False


def test_cli_rejects_non_lm8c_surfaces() -> None:
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_canonical_evidence_requires_default_shape() -> None:
    args = PROBE._args(["--canonical-evidence"])
    assert PROBE._canonical_evidence_is_valid(args) is True

    for argv in (
        ["--canonical-evidence", "--model", "qwen3:14b"],
        ["--canonical-evidence", "--endpoint", "http://example.invalid/chat"],
        ["--canonical-evidence", "--temperature", "0.2"],
    ):
        assert PROBE._canonical_evidence_is_valid(PROBE._args(argv)) is False


def test_decision_record_hashes_guid_without_raw_guid() -> None:
    decision = PROBE._decision_record(
        decision="accepted",
        reason="verify_scalar_output_succeeded",
        phase="verify_scalar_output",
        canonical_evidence=True,
        scalar_runtime_ready=True,
        live_fixture_created=True,
        worker_publication_ran=True,
        live_set_value_dispatched=True,
        verify_scalar_output_ran=True,
        component_guid="GUID-SECRET",
        extra={"observed_output_after": 7.5},
    )

    rendered = json.dumps(decision, sort_keys=True)
    assert decision["component_guid_sha256"].startswith("sha256:")
    assert decision["guid_present"] is True
    assert "GUID-SECRET" not in rendered
    assert decision["decision"] == "accepted"


def test_run_probe_callable_exists_as_task_1_skeleton() -> None:
    signature = inspect.signature(PROBE._run_probe)

    assert list(signature.parameters) == [
        "model",
        "endpoint",
        "temperature",
        "timeout_s",
        "excerpt_chars",
        "run_root",
        "canonical_evidence",
        "tool_executor",
    ]
    with pytest.raises(NotImplementedError, match="LM8C live probe"):
        PROBE._run_probe(
            model="gemma4:12b-it-qat",
            endpoint="http://localhost:11434/api/chat",
            temperature=0,
            timeout_s=120,
            excerpt_chars=1200,
            run_root="probe_runs",
            canonical_evidence=True,
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"component_guid": "GUID-SECRET"},
        {"sourceGuid": "GUID-SECRET"},
    ],
)
def test_decision_record_rejects_guid_bearing_extra_keys(extra) -> None:
    with pytest.raises(ValueError, match="LM8C decision extra"):
        PROBE._decision_record(
            decision="accepted",
            reason="verify_scalar_output_succeeded",
            phase="verify_scalar_output",
            canonical_evidence=True,
            component_guid="GUID-SECRET",
            extra=extra,
        )


def test_decision_record_rejects_extra_that_overwrites_base_field() -> None:
    with pytest.raises(ValueError, match="LM8C decision extra"):
        PROBE._decision_record(
            decision="accepted",
            reason="verify_scalar_output_succeeded",
            phase="verify_scalar_output",
            canonical_evidence=True,
            extra={"decision": "rejected"},
        )


def test_manifest_records_lm8c_identity() -> None:
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8c_gh_scalar_expectation_live_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["expected_output_value"] == 7.5
    assert manifest["initial_scalar_value"] == 0.0
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False
