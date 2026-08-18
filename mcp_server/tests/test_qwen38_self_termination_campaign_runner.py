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
    / "2026-08-18-qwen38-self-termination-campaign-v3.json"
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


def test_v3_protocol_requires_closed_python_environment_custody():
    runner = _runner()
    protocol = _protocol()

    assert runner.validate_protocol(protocol) is protocol

    missing = json.loads(json.dumps(protocol))
    del missing["pythonEnvironment"]["dllPathEntries"]
    with pytest.raises(ValueError, match="python_environment_contract_invalid"):
        runner.validate_protocol(missing)

    open_contract = json.loads(json.dumps(protocol))
    open_contract["pythonEnvironment"]["unexpected"] = True
    with pytest.raises(ValueError, match="python_environment_contract_invalid"):
        runner.validate_protocol(open_contract)

    invalid_summary = json.loads(json.dumps(protocol))
    invalid_summary["pythonEnvironment"]["manifestRoots"]["rookPackage"][
        "manifestSha256"
    ] = "not-a-digest"
    with pytest.raises(ValueError, match="python_environment_manifest_invalid"):
        runner.validate_protocol(invalid_summary)


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


def test_python_runtime_environment_uses_explicit_windows_import_and_dll_paths(
    tmp_path: Path,
):
    runner = _runner()
    protocol = _protocol()
    protocol["pythonEnvironment"] = {
        "manifestRoots": {},
        "pythonPathEntries": ["C:/runtime/site-packages", "C:/runtime/win32/lib"],
        "dllPathEntries": ["C:/runtime", "C:/runtime/pywin32_system32"],
    }

    environment = runner.python_runtime_environment(
        protocol,
        {"PATH": "C:/Windows/System32"},
        tmp_path / "adapter" / "src",
    )

    assert environment["PYTHONPATH"].split(";") == [
        (tmp_path / "adapter" / "src").as_posix(),
        "C:/runtime/site-packages",
        "C:/runtime/win32/lib",
    ]
    assert environment["PATH"].split(";")[:3] == [
        "C:/runtime",
        "C:/runtime/pywin32_system32",
        "C:/Windows/System32",
    ]


def test_recursive_python_environment_manifest_detects_any_file_drift(
    tmp_path: Path,
):
    runner = _runner()
    kernel = tmp_path / "kernel"
    rook = tmp_path / "rook"
    kernel.mkdir()
    rook.mkdir()
    (kernel / "python.exe").write_bytes(b"python")
    (rook / "module.py").write_text("value = 1\n")
    expected = {
        "kernel": runner.directory_manifest(kernel),
        "rook": runner.directory_manifest(rook),
    }
    protocol = {
        "pythonEnvironment": {
            "manifestRoots": {
                name: {"path": item["root"], **item["summary"]}
                for name, item in expected.items()
            }
        }
    }

    admitted = runner.capture_python_environment_custody(protocol)
    assert admitted["mismatches"] == []

    (rook / "module.py").write_text("value = 2\n")
    drifted = runner.capture_python_environment_custody(protocol)
    assert drifted["mismatches"] == ["rook"]
    with pytest.raises(RuntimeError, match="python_environment_drift:rook"):
        runner.require_python_environment_custody(drifted)


def test_python_environment_manifest_covers_directories_and_single_dlls(
    tmp_path: Path,
):
    runner = _runner()
    package = tmp_path / "package"
    package.mkdir()
    (package / "module.py").write_bytes(b"value = 1\n")
    dll = tmp_path / "pythoncom311.dll"
    dll.write_bytes(b"dll")

    package_manifest = runner.path_manifest(package)
    dll_manifest = runner.path_manifest(dll)

    assert package_manifest["entries"] == {
        "module.py": {
            "sha256": hashlib.sha256(b"value = 1\n").hexdigest().upper(),
            "bytes": 10,
        }
    }
    assert dll_manifest["entries"] == {
        "pythoncom311.dll": {
            "sha256": hashlib.sha256(b"dll").hexdigest().upper(),
            "bytes": 3,
        }
    }


def test_preflight_source_imports_versioned_rook_adapter_in_normal_kernel():
    source = (ROOT / "scripts" / "prime_goal_kernel_preflight.ts").read_text()

    assert 'name: "rook-full"' in source
    assert 'importName: "rook_full"' in source
    assert "import rook_full as _rook_full_module" in source
    assert '"rookFullFile": _rook_full_module.__file__' in source


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

    reused_parent = [
        {"processId": 10, "parentProcessId": 1, "creationDate": "new", "commandLine": "other"},
        {"processId": 13, "parentProcessId": 10, "creationDate": "e", "commandLine": "unrelated child"},
    ]
    assert runner.extend_owned_processes(tracked, reused_parent, set()) == tracked


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


def test_goal_context_accepts_primes_real_custom_message_and_goal_update_shapes():
    runner = _runner()
    objective = "repair"
    content = (
        "<goal_context>\n<objective>\nrepair\n</objective>\n"
        "- status: active\n- tokens used: 0\n- token budget: 2000000\n"
        "</goal_context>"
    )
    message = {
        "type": "message_start",
        "message": {"role": "custom", "customType": "goal_context", "content": content},
    }
    update = {
        "type": "goal_update",
        "goal": {"objective": objective, "status": "active", "tokenBudget": 2_000_000},
    }

    assert runner.goal_context_matches(message, objective, 2_000_000)
    assert runner.goal_context_matches(update, objective, 2_000_000)
    update["goal"]["tokenBudget"] = 7
    assert not runner.goal_context_matches(update, objective, 2_000_000)


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
    rook_full_file = tmp_path / "Lib" / "site-packages" / "rook_full" / "__init__.py"
    record = {
        "schema": "rook.experiment.prime_goal_preflight:v2",
        "pythonExecutable": str(python),
        "goalFile": str(goal_file),
        "rlmFile": str(rlm_file),
        "rookFullFile": str(rook_full_file),
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


def test_imported_smoke_recomputes_budget_from_retained_prime_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _protocol()
    root = tmp_path / "smoke"
    operator = root / "T3" / "operator"
    sessions = root / "T3" / "agent" / "sessions"
    operator.mkdir(parents=True)
    sessions.mkdir(parents=True)
    (root / "protocol.json").write_bytes(PROTOCOL_PATH.read_bytes())
    process = {
        "limitBreach": None,
        "providerReportedTokens": 1_000,
        "gatewayEvents": 4,
        "elapsedSeconds": 10.0,
        "stdoutEof": True,
        "ownedChildPids": [],
        "exitCode": 0,
    }
    outcome = {
        "semanticStatus": "pass",
        "goalStatus": "complete",
        "budgetStatus": "fail",
        "custodyStatus": "pass",
        "process": process,
        "target": {"task": "T3"},
    }
    (operator / "outcome.json").write_text(json.dumps(outcome) + "\n")
    (operator / "process-result.json").write_text(json.dumps(process) + "\n")
    (operator / "hidden-evaluation.json").write_text(
        json.dumps({"status": "pass"}) + "\n"
    )
    context = {
        "type": "goal_update",
        "goal": {
            "objective": protocol["tasks"]["T3"]["prompt"],
            "status": "active",
            "tokenBudget": 2_000_000,
        },
    }
    (operator / "prime.jsonl").write_text(json.dumps(context) + "\n")
    (sessions / "session.jsonl").write_text(
        json.dumps(
            {
                "type": "custom",
                "customType": "thread_goal_state",
                "data": {"status": "complete"},
            }
        )
        + "\n"
    )
    manifest_path = root / "evidence-manifest.json"
    runner.write_evidence_manifest(root, manifest_path)
    monkeypatch.setattr(runner, "validate_evidence_root", lambda path: root)
    monkeypatch.setattr(runner, "_process_snapshot", lambda: [])

    admitted = runner.admit_retained_smoke(protocol, root)

    assert {key: admitted[key] for key in (
        "semanticStatus", "goalStatus", "budgetStatus", "custodyStatus"
    )} == {
        "semanticStatus": "pass",
        "goalStatus": "complete",
        "budgetStatus": "pass",
        "custodyStatus": "pass",
    }
    assert admitted["retainedOriginalBudgetStatus"] == "fail"

    semantically_equal = tmp_path / "reformatted-protocol.json"
    semantically_equal.write_text(json.dumps(protocol, indent=2) + "\n")
    with pytest.raises(RuntimeError, match="retained_smoke_protocol_mismatch"):
        runner.admit_retained_smoke(protocol, root, semantically_equal)


def test_retained_smoke_process_scan_excludes_only_verifier_ancestry(
    monkeypatch: pytest.MonkeyPatch,
):
    runner = _runner()
    processes = [
        {"processId": 10, "parentProcessId": 1, "commandLine": "pwsh retained"},
        {"processId": 20, "parentProcessId": 10, "commandLine": "python retained"},
        {"processId": 30, "parentProcessId": 1, "commandLine": "python retained"},
    ]
    monkeypatch.setattr(runner.os, "getpid", lambda: 20)

    assert runner.retained_live_processes(processes, "retained") == [30]


def test_campaign_continuation_does_not_rerun_admitted_smoke(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    evidence_root = tmp_path / "continuation"
    retained_root = tmp_path / "retained"
    run_tasks: list[str] = []
    admitted = {
        "semanticStatus": "pass",
        "goalStatus": "complete",
        "budgetStatus": "pass",
        "custodyStatus": "pass",
        "retainedOriginalBudgetStatus": "fail",
    }
    monkeypatch.setattr(runner, "validate_evidence_root", lambda path: Path(path))
    monkeypatch.setattr(runner, "_runtime_custody", lambda protocol: {"ok": True})
    monkeypatch.setattr(runner, "_collect_tool_surface", lambda *args: {})
    monkeypatch.setattr(runner, "_run_preflight", lambda *args: {})
    monkeypatch.setattr(runner, "admit_retained_smoke", lambda *args: admitted)
    monkeypatch.setattr(
        runner,
        "capture_python_environment_custody",
        lambda protocol: {
            "schema": "rook.experiment.python_environment_custody:v1",
            "roots": {},
            "mismatches": [],
        },
    )
    monkeypatch.setattr(runner, "_copy_versioned_inputs", lambda *args: None)
    monkeypatch.setattr(runner, "_write_row_input_custody", lambda *args: None)

    def prepare(protocol, task, row_root, *args):
        (row_root / "operator").mkdir(exist_ok=True)
        return {"task": task["id"]}

    def run(protocol, task, row_root, target):
        run_tasks.append(task["id"])
        return {"task": task["id"]}

    monkeypatch.setattr(runner, "_prepare_target", prepare)
    monkeypatch.setattr(runner, "_run_prime_row", run)
    monkeypatch.setattr(
        runner,
        "_row_outcome",
        lambda *args: {
            "semanticStatus": "unproven",
            "goalStatus": "complete",
            "budgetStatus": "pass",
            "custodyStatus": "pass",
        },
    )

    result = runner.run_campaign(
        PROTOCOL_PATH, evidence_root, 268435457, None, retained_root
    )

    assert run_tasks == ["T1", "T2", "T4"]
    assert result["status"] == "complete"
    assert result["outcomes"]["T3"] == admitted


def test_post_row_python_environment_drift_stops_before_next_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    evidence_root = tmp_path / "campaign"
    prepared: list[str] = []
    custody_records = iter(
        [
            {"schema": "rook.experiment.python_environment_custody:v1", "roots": {}, "mismatches": []},
            {"schema": "rook.experiment.python_environment_custody:v1", "roots": {}, "mismatches": []},
            {"schema": "rook.experiment.python_environment_custody:v1", "roots": {}, "mismatches": ["kernel"]},
        ]
    )
    monkeypatch.setattr(runner, "validate_evidence_root", lambda path: Path(path))
    monkeypatch.setattr(runner, "_runtime_custody", lambda protocol: {"ok": True})
    monkeypatch.setattr(runner, "_collect_tool_surface", lambda *args: {})
    monkeypatch.setattr(runner, "_run_preflight", lambda *args: {})
    monkeypatch.setattr(
        runner, "capture_python_environment_custody", lambda protocol: next(custody_records)
    )
    monkeypatch.setattr(runner, "_copy_versioned_inputs", lambda *args: None)
    monkeypatch.setattr(runner, "_write_row_input_custody", lambda *args: None)

    def prepare(protocol, task, row_root, *args):
        prepared.append(task["id"])
        (row_root / "operator").mkdir(exist_ok=True)
        return {"task": task["id"]}

    monkeypatch.setattr(runner, "_prepare_target", prepare)
    monkeypatch.setattr(runner, "_run_prime_row", lambda *args: {})
    monkeypatch.setattr(
        runner,
        "_row_outcome",
        lambda *args: {
            "semanticStatus": "pass",
            "goalStatus": "complete",
            "budgetStatus": "pass",
            "custodyStatus": "pass",
        },
    )
    protocol = _protocol()
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n")

    with pytest.raises(RuntimeError, match="python_environment_drift:kernel"):
        runner.run_campaign(protocol_path, evidence_root, 268435457, None)

    assert prepared == ["T3"]
    assert json.loads((evidence_root / "campaign-failure.json").read_text())["error"] == (
        "python_environment_drift:kernel"
    )


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
