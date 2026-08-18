"""Causal checks for the versioned Qwen3.8 self-termination campaign runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "qwen38_self_termination_campaign_runner.py"
PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-self-termination-campaign-v2.json"
)
ADAPTER_PATH = (
    ROOT
    / "integrations"
    / "prime"
    / "skills"
    / "rook-full"
    / "src"
    / "rook_full"
    / "__init__.py"
)
SKILL_PATH = (
    ROOT / "integrations" / "prime" / "skills" / "prime-execute-grasshopper" / "SKILL.md"
)
CHECKPOINT_PATH = (
    ROOT
    / "integrations"
    / "prime"
    / "skills"
    / "prime-execute-grasshopper"
    / "references"
    / "checkpoint-protocol.md"
)


def _runner():
    spec = importlib.util.spec_from_file_location(
        "qwen38_self_termination_campaign_runner_for_tests",
        RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _protocol() -> dict:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def test_frozen_protocol_owns_exact_limits_and_corrected_skill_bootstrap():
    protocol = _protocol()

    assert protocol["limits"] == {
        "wallClockSecondsPerRun": 1800,
        "gatewayEventsPerRun": 150,
        "providerReportedTokensPerRun": 2_000_000,
        "primeGoalTokenBudget": 2_000_000,
    }
    assert protocol["prime"]["settings"] == {
        "enableBuiltinSkills": True,
        "packages": [],
        "extensions": [],
    }
    assert protocol["executionOrder"] == ["T3", "T1", "T2", "T4"]
    assert protocol["smokeTask"] == "T3"
    assert protocol["prime"]["runtimeBundle"] == {
        "root": "D:/prime-agent/.worktrees/mcp-error-merged-runtime/packages/coding-agent/dist",
        "subtrees": ["bundle", "skills"],
        "entryCount": 83,
        "totalBytes": 13975754,
        "manifestSha256": "78FEBC82B29F2729968A8475033E800DFA840BC99D425EDC8C0B684EF8A4A036",
    }


def test_frozen_protocol_pins_every_staged_versioned_input():
    versioned = _protocol()["versionedInputs"]

    assert versioned["skillSha256"] == hashlib.sha256(SKILL_PATH.read_bytes()).hexdigest().upper()
    assert versioned["checkpointSha256"] == hashlib.sha256(
        CHECKPOINT_PATH.read_bytes()
    ).hexdigest().upper()
    assert versioned["adapterInitSha256"] == hashlib.sha256(
        ADAPTER_PATH.read_bytes()
    ).hexdigest().upper()


def test_frozen_protocol_pins_model_blobs_and_serialized_tool_surface():
    protocol = _protocol()

    assert protocol["modelCustody"]["config"] == {
        "digest": "sha256:492b2922d38e553cabc2d319345644ed482874fbf5e5c9e4495cbf8e17b0cf5f",
        "size": 215,
    }
    assert len(protocol["modelCustody"]["layers"]) == 4
    assert protocol["toolSurface"] == {
        "profile": "full",
        "serializedCatalogCount": 382,
        "serializedCatalogBytes": 320743,
        "serializedCatalogSha256": "64796B23E123368F1F9CC509206A879783195223D81165C70D7226CB154B86FA",
    }


def test_tool_surface_validation_refuses_any_catalog_drift():
    runner = _runner()
    expected = _protocol()["toolSurface"]
    record = {
        "schema": "rook.experiment.tool_surface:v1",
        "profile": "full",
        "count": 382,
        "bytes": 320743,
        "sha256": "64796B23E123368F1F9CC509206A879783195223D81165C70D7226CB154B86FA",
    }
    assert runner.validate_tool_surface_record(record, expected) == record
    for field, value in (("count", 381), ("bytes", 1), ("sha256", "0" * 64)):
        with pytest.raises(ValueError, match="tool_surface_mismatch"):
            runner.validate_tool_surface_record(record | {field: value}, expected)


def test_operator_executor_boundary_distinguishes_payloads_from_failures():
    runner = _runner()

    payload = {"components": [], "flows": []}
    assert runner.operator_payload(payload, "snapshot") is payload
    assert runner.operator_envelope(payload) == {"success": True, "data": payload}

    failure = {"success": False, "data": {"error": "refused"}}
    assert runner.operator_envelope(failure) is failure
    with pytest.raises(RuntimeError, match="operator_call_failed:snapshot"):
        runner.operator_payload(failure, "snapshot")


@pytest.mark.parametrize(
    "field",
    [
        "wallClockSecondsPerRun",
        "gatewayEventsPerRun",
        "providerReportedTokensPerRun",
        "primeGoalTokenBudget",
    ],
)
def test_missing_or_nonpositive_enforcement_limit_refuses(field: str):
    runner = _runner()
    protocol = _protocol()
    del protocol["limits"][field]
    with pytest.raises(ValueError, match=f"limit_missing:{field}"):
        runner.validate_protocol(protocol)

    protocol = _protocol()
    protocol["limits"][field] = 0
    with pytest.raises(ValueError, match=f"limit_invalid:{field}"):
        runner.validate_protocol(protocol)


def test_provider_and_prime_budget_must_match():
    runner = _runner()
    protocol = _protocol()
    protocol["limits"]["primeGoalTokenBudget"] = 1_999_999

    with pytest.raises(ValueError, match="token_budget_mismatch"):
        runner.validate_protocol(protocol)


def test_temp_evidence_roots_refuse():
    runner = _runner()

    with pytest.raises(ValueError, match="durable_evidence_root_required"):
        runner.validate_evidence_root(
            Path("C:/Users/bring/AppData/Local/Temp/campaign")
        )

    assert runner.validate_evidence_root(
        Path("C:/UDEV/RookEvidence/campaign-v2")
    ) == Path("C:/UDEV/RookEvidence/campaign-v2")


def test_prime_command_seeds_budgeted_goal_and_uses_sealed_kernel(tmp_path: Path):
    runner = _runner()
    protocol = _protocol()
    command, environment = runner.build_prime_launch(
        protocol,
        task=protocol["tasks"]["T3"],
        row_root=tmp_path,
        target={"processId": 123, "documentSerialNumber": 456},
    )

    assert command == [
        protocol["prime"]["bashPath"],
        protocol["prime"]["launcherPath"],
        "--dist",
        "--cwd",
        str(tmp_path),
        "--offline",
        "--no-extensions",
        "--mode",
        "json",
        "--model",
        "ollama_chat/qwen3.8:27b",
        "--thinking",
        "medium",
        "--goal",
        protocol["tasks"]["T3"]["prompt"],
        "--goal-token-budget",
        "2000000",
        "Begin the active goal now.",
    ]
    assert "--no-skills" not in command
    assert environment["PRIME_AGENT_KERNEL_PYTHON"] == protocol["prime"][
        "sealedKernelPython"
    ]
    assert environment["ROOK_GATEWAY_CALL_LIMIT"] == "150"
    assert environment["PRIME_AGENT_CODING_AGENT_DIR"] == str(
        tmp_path / "agent"
    )


def test_monitor_enforces_provider_tokens_gateway_calls_and_wall_clock():
    runner = _runner()
    limits = runner.CampaignLimits.from_mapping(_protocol()["limits"])
    monitor = runner.RunMonitor(limits)

    message = {
        "type": "message_end",
        "message": {"usage": {"totalTokens": 1_500_000}},
    }
    assert monitor.consume_prime_line(json.dumps(message)) is None
    message["message"]["usage"]["totalTokens"] = 500_001
    assert monitor.consume_prime_line(json.dumps(message)) == "provider_token_ceiling"

    monitor = runner.RunMonitor(limits)
    assert monitor.observe_gateway_count(150) is None
    assert monitor.observe_gateway_count(151) == "gateway_call_ceiling"
    assert monitor.observe_elapsed(1799.9) is None
    assert monitor.observe_elapsed(1800.0) == "wall_clock_ceiling"


def test_owned_process_tracking_survives_descendant_reparenting():
    runner = _runner()
    initial = [
        {"processId": 10, "parentProcessId": 1, "creationDate": "a", "commandLine": "prime"},
        {"processId": 11, "parentProcessId": 10, "creationDate": "b", "commandLine": "node"},
        {"processId": 12, "parentProcessId": 11, "creationDate": "c", "commandLine": "kernel"},
        {"processId": 99, "parentProcessId": 1, "creationDate": "z", "commandLine": "unrelated"},
    ]
    tracked = runner.extend_owned_processes({}, initial, {10})
    assert tracked == {10: "a", 11: "b", 12: "c"}

    after_parent_exit = [
        {"processId": 12, "parentProcessId": 1, "creationDate": "c", "commandLine": "kernel"},
        {"processId": 99, "parentProcessId": 1, "creationDate": "z", "commandLine": "unrelated"},
    ]
    assert runner.live_owned_processes(tracked, after_parent_exit, "never-matches") == [12]


def test_pid_reuse_is_not_treated_as_owned_but_row_marker_is():
    runner = _runner()
    current = [
        {"processId": 10, "parentProcessId": 1, "creationDate": "new", "commandLine": "unrelated"},
        {
            "processId": 77,
            "parentProcessId": 1,
            "creationDate": "d",
            "commandLine": "python C:/UDEV/RookEvidence/campaign/T3/kernel.json",
        },
    ]

    assert runner.live_owned_processes(
        {10: "old"}, current, "C:/UDEV/RookEvidence/campaign/T3"
    ) == [77]


def test_goal_context_must_prove_exact_budget_before_row_is_admissible():
    runner = _runner()
    context = {
        "type": "goal_context",
        "goal": {
            "objective": "repair",
            "status": "active",
            "token_budget": 2_000_000,
        },
    }
    assert runner.goal_context_matches(context, "repair", 2_000_000)
    context["goal"]["token_budget"] = 123
    assert not runner.goal_context_matches(context, "repair", 2_000_000)


def test_goal_status_reads_primes_persisted_custom_goal_record(tmp_path: Path):
    runner = _runner()
    sessions = tmp_path / "agent" / "sessions"
    sessions.mkdir(parents=True)
    rows = [
        {
            "type": "custom",
            "customType": "thread_goal_state",
            "data": {"status": "active"},
        },
        {"type": "message", "message": {"role": "assistant"}},
        {
            "type": "custom",
            "customType": "thread_goal_state",
            "data": {"status": "complete"},
        },
    ]
    (sessions / "session.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    assert runner._goal_status(tmp_path) == "complete"


def test_preflight_requires_exact_kernel_imports_active_goal_and_completion(
    tmp_path: Path,
):
    runner = _runner()
    python = tmp_path / "Scripts" / "python.exe"
    goal_file = tmp_path / "Lib" / "site-packages" / "goal" / "__init__.py"
    rlm_file = tmp_path / "Lib" / "site-packages" / "rlm" / "__init__.py"
    record = {
        "schema": "rook.experiment.prime_goal_preflight:v1",
        "pythonExecutable": str(python),
        "goalFile": str(goal_file),
        "rlmFile": str(rlm_file),
        "goalPreimported": True,
        "getStatus": "active",
        "getTokenBudget": 2_000_000,
        "completeStatus": "complete",
        "requests": ["goal.get", "goal.complete"],
        "kernelClosed": True,
    }

    assert runner.validate_preflight_record(record, python, 2_000_000) == record
    for mutation in (
        {"goalPreimported": False},
        {"getStatus": "complete"},
        {"getTokenBudget": 10},
        {"completeStatus": "active"},
        {"requests": ["goal.get"]},
        {"kernelClosed": False},
    ):
        bad = record | mutation
        with pytest.raises(ValueError, match="preflight_invalid"):
            runner.validate_preflight_record(bad, python, 2_000_000)


def test_manifest_is_non_self_referential_and_independently_verifies(
    tmp_path: Path,
):
    runner = _runner()
    (tmp_path / "a.txt").write_text("alpha\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.json").write_text("{}\n", encoding="utf-8")
    manifest_path = tmp_path / "evidence-manifest.json"

    manifest = runner.write_evidence_manifest(tmp_path, manifest_path)

    assert manifest["entryCount"] == 2
    assert "evidence-manifest.json" not in manifest["entries"]
    assert runner.verify_evidence_manifest(tmp_path, manifest_path) == {
        "entryCount": 2,
        "mismatches": [],
    }

    (tmp_path / "late.txt").write_text("not admitted\n", encoding="utf-8")
    assert runner.verify_evidence_manifest(tmp_path, manifest_path)["mismatches"] == [
        "unexpected:late.txt"
    ]


def test_early_gate_failure_is_durably_finalized_and_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    evidence_root = tmp_path / "campaign"
    monkeypatch.setattr(runner, "validate_evidence_root", lambda path: evidence_root)
    monkeypatch.setattr(
        runner,
        "_runtime_custody",
        lambda protocol: (_ for _ in ()).throw(RuntimeError("custody_gate_failed")),
    )

    with pytest.raises(RuntimeError, match="custody_gate_failed"):
        runner.run_campaign(PROTOCOL_PATH, evidence_root, 268435457, None)

    failure = json.loads((evidence_root / "campaign-failure.json").read_text())
    summary = json.loads((evidence_root / "campaign-summary.json").read_text())
    verification = json.loads(
        (evidence_root / "manifest-verification.json").read_text()
    )
    assert failure["error"] == "custody_gate_failed"
    assert summary["status"] == "incomplete"
    assert verification["mismatches"] == []
    assert runner.verify_evidence_manifest(
        evidence_root, evidence_root / "evidence-manifest.json"
    )["mismatches"] == []


def test_smoke_gate_is_closed_and_only_pass_opens_varied_cohort():
    runner = _runner()
    pass_result = {
        "semanticStatus": "pass",
        "goalStatus": "complete",
        "budgetStatus": "pass",
        "custodyStatus": "pass",
    }
    assert runner.smoke_allows_cohort(pass_result)
    assert runner.cohort_after_smoke(_protocol(), pass_result) == ["T1", "T2", "T4"]

    for key in pass_result:
        failed = dict(pass_result)
        failed[key] = "fail"
        assert not runner.smoke_allows_cohort(failed)
        assert runner.cohort_after_smoke(_protocol(), failed) == []


def test_versioned_adapter_preserves_v5_bytes_and_adds_pre_dispatch_call_ceiling():
    payload = ADAPTER_PATH.read_bytes()
    text = payload.decode("ascii")

    assert "_CALL_LIMIT_ENV = \"ROOK_GATEWAY_CALL_LIMIT\"" in text
    assert "raise RuntimeError(\"rook_gateway_call_limit_exceeded\")" in text
    assert text.index("_reserve_gateway_call()") < text.index("await operation")
    assert "return result[\"data\"]" in text
    assert "except McpToolError as exc:" in text
    assert hashlib.sha256(payload).hexdigest().upper() != (
        "9B22757E30986F9FDB2FC3AFA10F95F2C98A4727E551132E58DA74E90235C371"
    )


@pytest.mark.asyncio
async def test_gateway_call_151_refuses_before_transport_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    mcp = types.ModuleType("mcp")
    mcp.ClientSession = object
    mcp.StdioServerParameters = object
    mcp_client = types.ModuleType("mcp.client")
    mcp_stdio = types.ModuleType("mcp.client.stdio")
    mcp_stdio.stdio_client = lambda *args, **kwargs: None
    rlm = types.ModuleType("rlm")
    rlm.McpIntegration = type("McpIntegration", (), {})
    rlm_base = types.ModuleType("rlm.mcp_base")
    rlm_base.McpToolError = type("McpToolError", (RuntimeError,), {})
    acceptance = types.SimpleNamespace(
        append_canonical_gateway_error_source_event=lambda *args, **kwargs: None,
        append_canonical_gateway_source_event=lambda *args, **kwargs: None,
    )
    rook = types.ModuleType("rook")
    rook.gh_behavioral_acceptance = acceptance
    for name, module in {
        "mcp": mcp,
        "mcp.client": mcp_client,
        "mcp.client.stdio": mcp_stdio,
        "rlm": rlm,
        "rlm.mcp_base": rlm_base,
        "rook": rook,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("ROOK_GATEWAY_CALL_LIMIT", "1")
    monkeypatch.setenv("ROOK_GH_AUTHORING_SOURCE_LOG", str(tmp_path / "source.jsonl"))

    spec = importlib.util.spec_from_file_location("rook_full_limit_test", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Awaitable:
        def __init__(self):
            self.entered = False

        def __await__(self):
            self.entered = True

            async def result():
                return {"success": True, "data": {"ok": True}}

            return result().__await__()

    first = Awaitable()
    assert await module._recorded_call("gh_snapshot", {}, first) == {"ok": True}
    assert first.entered is True

    refused = Awaitable()
    with pytest.raises(RuntimeError, match="rook_gateway_call_limit_exceeded"):
        await module._recorded_call("gh_snapshot", {}, refused)
    assert refused.entered is False
