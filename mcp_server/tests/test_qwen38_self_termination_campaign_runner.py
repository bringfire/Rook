"""Causal checks for the versioned Qwen3.8 self-termination campaign runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
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
V4_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-self-termination-campaign-v4.json"
)
V5_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-self-termination-campaign-v5.json"
)
V6_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-self-termination-campaign-v6.json"
)
VARIED_COHORT_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-varied-product-cohort-v1.json"
)
VARIED_COHORT_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-varied-product-cohort-v1-adjudication.json"
)
VP2_EVIDENCE_REUSE_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-vp2-evidence-reuse-screening-v1.json"
)
VP2_EVIDENCE_REUSE_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-vp2-evidence-reuse-screening-v1-adjudication.json"
)
VP2_EVIDENCE_REUSE_SKILL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "inputs"
    / "2026-08-18-qwen38-vp2-evidence-reuse-screening-v1"
    / "prime-execute-grasshopper"
    / "SKILL.md"
)
VP2_STRATEGY_DISCIPLINE_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-18-qwen38-vp2-strategy-discipline-screening-v1.json"
)
VP2_CONNECTION_TRUTHFULNESS_RETEST_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-vp2-connection-truthfulness-retest-v2.json"
)
VP1_PROSPECTIVE_EFFICIENCY_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-vp1-prospective-efficiency-screen-v1.json"
)
VP1_PROSPECTIVE_EFFICIENCY_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-vp1-prospective-efficiency-screen-v1-adjudication.json"
)
VP4_PROFILE_STACK_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-vp4-profile-stack-prospective-screen-v1.json"
)
VP4_PROFILE_STACK_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-vp4-profile-stack-prospective-screen-v1-adjudication.json"
)
AUTHORING_LANE_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-native-python-authoring-lane-screen-v1.json"
)
AUTHORING_LANE_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-native-python-authoring-lane-screen-v1-adjudication.json"
)
AUTHORING_LANE_CAPABILITY_AUDIT_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-native-python-authoring-lane-capability-audit-v1.json"
)
PYTHON_LANE_CONFIRMATION_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-python-lane-point-lattice-confirmation-v1.json"
)
PYTHON_LANE_CONFIRMATION_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-python-lane-point-lattice-confirmation-v1-adjudication.json"
)
PRIME_UPSTREAM_SMOKE_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-prime-upstream-t3-compatibility-smoke-v1.json"
)
PRIME_UPSTREAM_SMOKE_V2_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-prime-upstream-t3-compatibility-smoke-v2.json"
)
PRIME_UPSTREAM_SMOKE_V3_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-prime-upstream-t3-compatibility-smoke-v3.json"
)
OPTIONAL_PYTHON_SKILL_PATH = (
    ROOT
    / "integrations"
    / "prime"
    / "skills"
    / "prime-execute-grasshopper-python"
    / "SKILL.md"
)
OPTIONAL_PYTHON_SKILL_CHECKPOINT_PATH = (
    OPTIONAL_PYTHON_SKILL_PATH.parent / "references" / "checkpoint-protocol.md"
)
OPTIONAL_PYTHON_CONFIRMATION_PROTOCOL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-optional-python-skill-sine-wave-confirmation-v1.json"
)
OPTIONAL_PYTHON_CONFIRMATION_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-qwen38-optional-python-skill-sine-wave-confirmation-v1-adjudication.json"
)
PRIME_UPSTREAM_SMOKE_ADJUDICATION_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "2026-08-19-prime-upstream-t3-compatibility-smoke-v1-adjudication.json"
)
PRIME_UPSTREAM_SMOKE_SKILL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "inputs"
    / "2026-08-19-prime-upstream-t3-compatibility-smoke-v1"
    / "prime-execute-grasshopper"
    / "SKILL.md"
)
PRIME_UPSTREAM_SMOKE_CHECKPOINT_PATH = (
    PRIME_UPSTREAM_SMOKE_SKILL_PATH.parent
    / "references"
    / "checkpoint-protocol.md"
)
AUTHORING_LANE_INPUT_ROOT = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "inputs"
    / "2026-08-19-qwen38-native-python-authoring-lane-screen-v1"
)
NATIVE_LANE_SKILL_PATH = (
    AUTHORING_LANE_INPUT_ROOT / "native" / "prime-execute-grasshopper" / "SKILL.md"
)
PYTHON_LANE_SKILL_PATH = (
    AUTHORING_LANE_INPUT_ROOT / "python" / "prime-execute-grasshopper" / "SKILL.md"
)
VP2_STRATEGY_DISCIPLINE_SKILL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "inputs"
    / "2026-08-18-qwen38-vp2-strategy-discipline-screening-v1"
    / "prime-execute-grasshopper"
    / "SKILL.md"
)
VP1_PROSPECTIVE_EFFICIENCY_SKILL_PATH = (
    ROOT
    / "docs"
    / "superpowers"
    / "experiments"
    / "inputs"
    / "2026-08-19-qwen38-vp1-prospective-efficiency-screen-v1"
    / "prime-execute-grasshopper"
    / "SKILL.md"
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

EVIDENCE_REUSE_RULE = (
    "Reuse successfully and unambiguously resolved session-local capability "
    "schemas, component-discovery facts, and component metadata. Request only "
    "missing facts. Refresh a resolved fact only when refusal, runtime or "
    "target-identity change, or contradictory live evidence gives a named reason "
    "to consider it stale."
)
STRATEGY_DISCIPLINE_RULE = (
    "Treat a component or subgraph failure as local first. Before abandoning a "
    "committed strategy, either attempt one bounded local repair or identify live "
    "evidence making a pivot preferable. Preserve unaffected committed work during "
    "a pivot. Further discovery must name the blocker it resolves."
)
KNOWN_TOOL_DISCOVERY_RULE = (
    "Tool names listed in this skill are already known. Read each required contract "
    "directly once; do not search for a known tool name. After `gh_edit` and one "
    "viable authoring contract are known, choose an implementation mode and create "
    "the smallest working scaffold. Further discovery must name the exact unresolved "
    "fact required by the next intended mutation—for example a component identity, "
    "parameter index, or required tool argument—and stop once that fact is resolved."
)
PROFILE_STACK_PROMPT = (
    "Create a compact adjustable stack of closed horizontal rectangular profiles "
    "for possible future lofting. Expose Width, Depth, integer Levels, and Level "
    "Spacing controls. Produce exactly Levels profiles. Their XY centroids must "
    "align on one vertical axis, and adjacent profiles must be separated evenly by "
    "Level Spacing in Z. Exercise at least one consequential control, observe its "
    "effect, and restore the chosen defaults. Inspect the final stack and stop when "
    "satisfied. Do not loft, surface, bake, or create downstream geometry."
)
CIRCULAR_LINE_ARRAY_PROMPT = (
    "Create an adjustable circular array of vertical line segments. Expose "
    "Radius, Count, Height, and Start Angle. Produce exactly Count evenly spaced "
    "vertical lines around the circle. Exercise Count and Height, observe the "
    "effects, restore defaults, obtain a final receipt-fenced observation, and "
    "stop when satisfied."
)
POINT_LATTICE_PROMPT = (
    "Create an adjustable rectangular lattice of points in the XY plane. "
    "Expose integer Columns, integer Rows, X Spacing, and Y Spacing controls. "
    "Produce exactly Columns × Rows points, starting at the origin, with adjacent "
    "columns separated by X Spacing and adjacent rows separated by Y Spacing; all "
    "Z coordinates must remain zero. Exercise Columns and Y Spacing independently, "
    "observe each effect, restore defaults, obtain a final receipt-fenced "
    "observation, and stop when satisfied. Do not create curves, surfaces, bake, "
    "or add downstream geometry."
)
BASELINE_SKILL_SHA256 = (
    "30CA98809CCE8F4BE5B1CC291DEB8820511B6B13A0D546CBA93848DBC9074B07"
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


def _v4_protocol() -> dict:
    protocol = _protocol()
    protocol["schema"] = "rook.experiment.qwen38_self_termination_campaign:v4"
    protocol["executionOrder"] = ["T3", "T2", "T4"]
    protocol["tasks"] = {
        task_id: protocol["tasks"][task_id] for task_id in protocol["executionOrder"]
    }
    protocol["prime"]["thinkingLevel"] = "low"
    protocol["precontactVerification"] = {
        "pythonPath": "C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe",
        "arguments": [
            "-m",
            "pytest",
            "mcp_server/tests/test_qwen38_self_termination_campaign_runner.py",
            "mcp_server/tests/test_gh_behavioral_acceptance.py",
            "-q",
        ],
    }
    return protocol


def _v5_protocol() -> dict:
    protocol = _v4_protocol()
    protocol["schema"] = "rook.experiment.qwen38_self_termination_campaign:v5"
    protocol["purpose"] = (
        "Test whether decision-relevance stopping guidance closes the observed "
        "low-thinking T4 completion tail without changing any other operational input."
    )
    protocol["smokeTask"] = "T4"
    protocol["executionOrder"] = ["T4"]
    protocol["tasks"] = {"T4": protocol["tasks"]["T4"]}
    protocol["focusedRetest"] = {
        "sourceEvidenceManifestSha256": (
            "99A1D37E45A4410CC668A53CB6ADD97A827C8080201C389C3F3BA9F5A4F9BF16"
        ),
        "onlyChangedOperationalInput": "versioned_prime_skill",
        "successCriteria": [
            "mechanically_healthy_helix",
            "important_controls_exercised_and_restored",
            "adequate_fresh_post_restore_checkpoint",
            "goal_complete",
            "budget_pass",
            "custody_pass",
        ],
        "decisionTelemetry": {
            "firstSufficientEvidence": "independent_post_run_timeline_adjudication",
            "formalCompletion": "persisted_goal_complete",
        },
        "evaluatorFeedbackDuringRun": False,
    }
    return protocol


def _v6_protocol() -> dict:
    protocol = _v5_protocol()
    protocol["schema"] = "rook.experiment.qwen38_self_termination_campaign:v6"
    protocol["purpose"] = (
        "Test whether Qwen completes from one model-facing receipt-fenced final "
        "checkpoint without a compensating status call."
    )
    protocol["focusedRetest"] = {
        "sourceEvidenceManifestSha256": (
            "336E1A539C25B1DEA4E3625B9E526FBC28033ABB7E8C5593C57AC36D17DC059C"
        ),
        "onlyChangedOperationalInput": "versioned_prime_instructions",
        "changedInstructionInputs": [
            "skillSha256",
            "checkpointSha256",
        ],
        "successCriteria": [
            "mechanically_healthy_helix",
            "important_controls_exercised_and_restored",
            "model_facing_receipt_wait_ready",
            "model_facing_receipt_fenced_snapshot",
            "no_later_gateway_call",
            "goal_complete",
            "budget_pass",
            "custody_pass",
        ],
        "decisionTelemetry": {
            "firstQualifiedEvidence": "receipt_fenced_snapshot_tool_result",
            "formalCompletion": "persisted_goal_complete",
            "perTurnInputOutput": "retained_prime_message_usage",
        },
        "evaluatorFeedbackDuringRun": False,
    }
    return protocol


def _varied_cohort_protocol() -> dict:
    return json.loads(VARIED_COHORT_PROTOCOL_PATH.read_text(encoding="utf-8"))


def _vp2_evidence_reuse_protocol() -> dict:
    return json.loads(VP2_EVIDENCE_REUSE_PROTOCOL_PATH.read_text(encoding="utf-8"))


def _vp2_strategy_discipline_protocol() -> dict:
    return json.loads(
        VP2_STRATEGY_DISCIPLINE_PROTOCOL_PATH.read_text(encoding="utf-8")
    )


def _authoring_lane_protocol() -> dict:
    return json.loads(AUTHORING_LANE_PROTOCOL_PATH.read_text(encoding="utf-8"))


def _python_lane_confirmation_protocol() -> dict:
    return json.loads(
        PYTHON_LANE_CONFIRMATION_PROTOCOL_PATH.read_text(encoding="utf-8")
    )


def _prime_upstream_smoke_protocol() -> dict:
    return json.loads(PRIME_UPSTREAM_SMOKE_PROTOCOL_PATH.read_text(encoding="utf-8"))


def _prime_upstream_smoke_v2_protocol() -> dict:
    return json.loads(
        PRIME_UPSTREAM_SMOKE_V2_PROTOCOL_PATH.read_text(encoding="utf-8")
    )


def _prime_upstream_smoke_v3_protocol() -> dict:
    return json.loads(
        PRIME_UPSTREAM_SMOKE_V3_PROTOCOL_PATH.read_text(encoding="utf-8")
    )


def _optional_python_confirmation_protocol() -> dict:
    return json.loads(
        OPTIONAL_PYTHON_CONFIRMATION_PROTOCOL_PATH.read_text(encoding="utf-8")
    )


def _skill_body(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    return content.split("---\n", 2)[2]


def test_optional_python_skill_packages_the_qualified_lane_without_native_drift():
    protocol = _optional_python_confirmation_protocol()
    packaged = OPTIONAL_PYTHON_SKILL_PATH.read_text(encoding="utf-8")

    assert hashlib.sha256(SKILL_PATH.read_bytes()).hexdigest().upper() == (
        "30CA98809CCE8F4BE5B1CC291DEB8820511B6B13A0D546CBA93848DBC9074B07"
    )
    assert _skill_body(OPTIONAL_PYTHON_SKILL_PATH) == _skill_body(
        PYTHON_LANE_SKILL_PATH
    )
    assert "name: prime-execute-grasshopper-python" in packaged
    assert (
        "Explicitly selected Python scripting lane for Grasshopper authoring"
        in packaged
    )
    assert protocol["optionalSkill"]["packageSha256"] == hashlib.sha256(
        OPTIONAL_PYTHON_SKILL_PATH.read_bytes()
    ).hexdigest().upper()
    assert protocol["optionalSkill"]["qualifiedFixtureSha256"] == (
        "E70095B557A2C55FDA33FCA7BC7830A4D2FD54F98E7B66A861AC87DB9C4B4AD6"
    )


def test_optional_python_skill_preserves_receipt_fenced_completion_order():
    content = OPTIONAL_PYTHON_SKILL_PATH.read_text(encoding="utf-8")
    receipt = content.index("Retain the `solve_readiness_receipt.receipt_id`")
    wait = content.index("call `gh_wait_for_solve_readiness`", receipt)
    snapshot = content.index("then call `gh_snapshot`", wait)
    complete = content.index("Call `goal.complete()`", snapshot)

    assert receipt < wait < snapshot < complete
    assert "Do not perform a later Rook mutation" in content


def test_optional_python_skill_is_explicitly_loaded_only_for_confirmation(tmp_path):
    runner = _runner()
    protocol = _optional_python_confirmation_protocol()
    task = protocol["tasks"]["PY1"]
    row_root = tmp_path / "row"
    runner._copy_versioned_inputs(protocol, task, row_root)
    command, _ = runner.build_prime_launch(
        protocol,
        task=task,
        row_root=row_root,
        target={"processId": 1, "documentSerialNumber": 2},
    )

    selected = row_root / "explicit-skills" / "prime-execute-grasshopper-python"
    assert command[command.index("--skill") + 1] == str(selected)
    assert command[-1] == (
        "/skill:prime-execute-grasshopper-python Begin the active goal now."
    )
    assert (selected / "SKILL.md").is_file()
    assert not (
        row_root
        / "agent"
        / "skills"
        / "prime-execute-grasshopper-python"
    ).exists()
    loading = runner.verify_prime_explicit_skill_loading(protocol, selected)
    assert loading["selectedSkillNames"] == ["prime-execute-grasshopper-python"]
    assert loading["unselectedSkillNames"] == []

    historical = _python_lane_confirmation_protocol()
    old_command, _ = runner.build_prime_launch(
        historical,
        task=historical["tasks"]["P2"],
        row_root=tmp_path / "historical",
        target={"processId": 1, "documentSerialNumber": 2},
    )
    assert "--skill" not in old_command
    assert not old_command[-1].startswith("/skill:")


def test_optional_python_confirmation_freezes_upstream_and_lane_custody():
    runner = _runner()
    protocol = _optional_python_confirmation_protocol()
    adjudication = json.loads(
        OPTIONAL_PYTHON_CONFIRMATION_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )

    assert runner.validate_protocol(protocol) is protocol
    assert protocol["schema"] == runner.OPTIONAL_PYTHON_CONFIRMATION_SCHEMA
    assert protocol["executionOrder"] == ["PY1"]
    assert protocol["prime"]["commit"] == (
        "739400844f8f3f280414b0c7b9c65797208815d3"
    )
    assert protocol["prime"]["thinkingLevel"] == "low"
    assert protocol["limits"] == {
        "wallClockSecondsPerRun": 1800,
        "gatewayEventsPerRun": 150,
        "providerReportedTokensPerRun": 2_000_000,
        "primeGoalTokenBudget": 1_900_000,
    }
    assert protocol["goalSkillCustody"] == _prime_upstream_smoke_v3_protocol()[
        "goalSkillCustody"
    ]
    assert protocol["upstreamCustody"] == _prime_upstream_smoke_v3_protocol()[
        "upstreamCustody"
    ]
    assert protocol["versionedInputs"]["adapterInitSha256"] == (
        "06F1CB4AA58FD8C4C6F61F96CE7B8A5F4FEF7B6B126D00C0550B2CB3AA0BBF74"
    )
    assert protocol["tasks"]["PY1"]["prompt"].startswith(
        "Create an adjustable sine-wave polyline in the XZ plane."
    )
    assert adjudication["tasks"].keys() == {"PY1"}
    assert protocol["confirmation"]["retries"] == 0
    assert protocol["confirmation"]["evaluatorFeedbackDuringRun"] is False


def test_optional_python_confirmation_rejects_selection_or_custody_drift():
    runner = _runner()
    protocol = _optional_python_confirmation_protocol()

    changed = json.loads(json.dumps(protocol))
    changed["optionalSkill"]["selectionMode"] = "default"
    with pytest.raises(ValueError, match="optional_python_confirmation_invalid"):
        runner.validate_protocol(changed)

    changed = json.loads(json.dumps(protocol))
    changed["prime"]["commit"] = "27b5be22cf0e0e81e324a59ebabbb41edfee6ec0"
    with pytest.raises(ValueError, match="optional_python_confirmation_invalid"):
        runner.validate_protocol(changed)

    changed = json.loads(json.dumps(protocol))
    changed["goalSkillCustody"]["sealedKernel"]["sha256"] = "A" * 64
    with pytest.raises(ValueError, match="optional_python_confirmation_invalid"):
        runner.validate_protocol(changed)


def test_optional_python_confirmation_uses_the_existing_silent_evaluator():
    runner = _runner()
    protocol = _optional_python_confirmation_protocol()

    environment = runner.offline_evaluator_environment(protocol, {})

    assert environment["PYTHONPATH"].split(";")[0] == (
        ROOT / "mcp_server" / "src"
    ).as_posix()
    evaluator = protocol["offlineEvaluator"]
    source = ROOT / evaluator["behavioralAcceptancePath"]
    assert hashlib.sha256(source.read_bytes()).hexdigest().upper() == (
        evaluator["behavioralAcceptanceSha256"]
    )


def test_prime_upstream_smoke_freezes_one_historical_t3_row():
    runner = _runner()
    historical = _protocol()
    current = _python_lane_confirmation_protocol()
    protocol = _prime_upstream_smoke_protocol()
    adjudication = json.loads(
        PRIME_UPSTREAM_SMOKE_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )

    assert runner.validate_protocol(protocol) is protocol
    assert protocol["schema"] == runner.PRIME_UPSTREAM_SMOKE_SCHEMA
    assert protocol["status"] == "frozen_precontact"
    assert protocol["executionOrder"] == ["T3"]
    assert protocol["smokeTask"] == "T3"
    assert protocol["tasks"] == {"T3": historical["tasks"]["T3"]}
    assert protocol["limits"] == historical["limits"]
    assert protocol["modelCustody"] == historical["modelCustody"]
    assert protocol["rookCustody"] == current["rookCustody"]
    assert protocol["toolSurface"] == current["toolSurface"]
    assert protocol["singleRowSmoke"] == {
        "retryCount": 0,
        "evaluatorFeedbackDuringRun": False,
        "comparisonKind": "compatibility_screen",
    }
    assert protocol["prime"]["sourceRoot"] == (
        "D:/prime-agent/.worktrees/rook-upstream-evaluation"
    )
    assert protocol["prime"]["commit"] == (
        "739400844f8f3f280414b0c7b9c65797208815d3"
    )
    assert protocol["prime"]["runtimeBundle"] == {
        "root": (
            "D:/prime-agent/.worktrees/rook-upstream-evaluation/"
            "packages/coding-agent/dist"
        ),
        "subtrees": ["bundle", "skills"],
        "entryCount": 84,
        "totalBytes": 13_990_452,
        "manifestSha256": (
            "4C5BC52CDAE882144E851600048711756E4BB28B400DF4A25B206D0F1263A106"
        ),
    }
    assert protocol["upstreamCustody"] == {
        "baseCommit": "f8f0036cc2da1a640aad990ae8dcb7c4820ce32e",
        "baseTree": "3ff69db27820afc0f3addc2089f6c04f10808d21",
        "patchCommit": "30a6621bca698ef14f64e5e45c5b1b6364148789",
        "patchTree": "05021548c143700b1b24045d29e712f784797798",
        "resultCommit": "739400844f8f3f280414b0c7b9c65797208815d3",
        "resultTree": "4d782187c6898aa8352045dd597bab6a3819029c",
        "dependencyLockSha256": (
            "C0AEC1FE34A5CFE0E601C8EFC1E5B0A96D4E8D76773633F76425F4F0829AA69D"
        ),
    }
    assert hashlib.sha256(PRIME_UPSTREAM_SMOKE_SKILL_PATH.read_bytes()).hexdigest().upper() == (
        historical["versionedInputs"]["skillSha256"]
    )
    assert protocol["versionedInputs"]["skillPath"] == (
        PRIME_UPSTREAM_SMOKE_SKILL_PATH.relative_to(ROOT).as_posix()
    )
    assert hashlib.sha256(
        PRIME_UPSTREAM_SMOKE_CHECKPOINT_PATH.read_bytes()
    ).hexdigest().upper() == historical["versionedInputs"]["checkpointSha256"]
    assert protocol["versionedInputs"]["checkpointPath"] == (
        PRIME_UPSTREAM_SMOKE_CHECKPOINT_PATH.relative_to(ROOT).as_posix()
    )
    assert protocol["versionedInputs"]["adapterInitSha256"] == (
        historical["versionedInputs"]["adapterInitSha256"]
    )
    assert protocol["offlineEvaluator"]["acceptanceArtifactSha256"] == hashlib.sha256(
        (ROOT / protocol["offlineEvaluator"]["acceptanceArtifactPath"]).read_bytes()
    ).hexdigest().upper()
    assert protocol["smokeAdjudication"]["sha256"] == hashlib.sha256(
        PRIME_UPSTREAM_SMOKE_ADJUDICATION_PATH.read_bytes()
    ).hexdigest().upper()
    assert adjudication["taskId"] == "T3"
    assert adjudication["runtimeFeedbackProvided"] is False


def test_prime_upstream_smoke_rejects_scope_and_branch_locality_drift(tmp_path):
    runner = _runner()
    protocol = _prime_upstream_smoke_protocol()

    changed = json.loads(json.dumps(protocol))
    changed["singleRowSmoke"]["retryCount"] = 1
    with pytest.raises(ValueError, match="prime_upstream_smoke_invalid"):
        runner.validate_protocol(changed)

    changed = json.loads(json.dumps(protocol))
    changed["executionOrder"].append("T1")
    changed["tasks"]["T1"] = _protocol()["tasks"]["T1"]
    with pytest.raises(ValueError, match="task_order_invalid"):
        runner.validate_protocol(changed)

    row_root = tmp_path / "row"
    target = {"processId": 1, "documentSerialNumber": 2}
    command, environment = runner.build_prime_launch(
        protocol,
        task=protocol["tasks"]["T3"],
        row_root=row_root,
        target=target,
    )
    expected_root = "D:/prime-agent/.worktrees/rook-upstream-evaluation"
    assert command[:2] == [
        protocol["prime"]["bashPath"],
        f"{expected_root}/prime-agent.sh",
    ]
    python_paths = environment["PYTHONPATH"].replace("\\", "/").split(";")
    assert python_paths[0] == (
        row_root / "agent" / "skills" / "rook-full" / "src"
    ).as_posix()
    assert python_paths[1] == f"{expected_root}/prime-agent-runtime/src"
    assert all("mcp-error-merged-runtime" not in item for item in python_paths)
    assert all("mcp-error-structured-content" not in item for item in python_paths)


def test_prime_upstream_preflight_requires_branch_local_prime_python():
    runner = _runner()
    root = Path("D:/prime-agent/.worktrees/rook-upstream-evaluation")
    python = Path("C:/Users/bring/.prime/agent/kernel-venv/Scripts/python.exe")
    record = {
        "schema": "rook.experiment.prime_goal_preflight:v2",
        "pythonExecutable": str(python),
        "goalFile": str(root / "packages/coding-agent/skills/goal/src/goal/__init__.py"),
        "rlmFile": str(root / "prime-agent-runtime/src/rlm/__init__.py"),
        "rookFullFile": (
            "C:/qualified-row/agent/skills/rook-full/src/rook_full/__init__.py"
        ),
        "goalPreimported": True,
        "getStatus": "active",
        "getTokenBudget": 2_000_000,
        "completeStatus": "complete",
        "requests": ["goal.get", "goal.complete"],
        "kernelClosed": True,
    }

    assert runner.validate_preflight_record(record, python, 2_000_000, root) == record
    record["rlmFile"] = (
        "D:/prime-agent/.worktrees/mcp-error-merged-runtime/"
        "prime-agent-runtime/src/rlm/__init__.py"
    )
    with pytest.raises(ValueError, match="preflight_invalid"):
        runner.validate_preflight_record(record, python, 2_000_000, root)


def test_prime_upstream_v2_preserves_v1_and_freezes_goal_equivalence():
    runner = _runner()
    v1 = _prime_upstream_smoke_protocol()
    v2 = _prime_upstream_smoke_v2_protocol()

    assert hashlib.sha256(PRIME_UPSTREAM_SMOKE_PROTOCOL_PATH.read_bytes()).hexdigest().upper() == (
        "512A0843FB8D59DC25F5C8C81B40C296C06DA7DA06778CA86AC82C6C2B711BCD"
    )
    assert runner.validate_protocol(v2) is v2
    assert v2["schema"] == runner.PRIME_UPSTREAM_SMOKE_V2_SCHEMA
    assert v2["precontactGate"] == {
        "mode": "model_free_only",
        "evidenceRoot": (
            "C:/UDEV/RookEvidence/"
            "2026-08-19-prime-upstream-t3-compatibility-smoke-v2"
        ),
        "actorContactAuthorized": False,
    }
    assert v2["goalSkillCustody"] == {
        "sealedKernel": {
            "path": (
                "C:/Users/bring/.prime/agent/kernel-venv/"
                "Lib/site-packages/goal/__init__.py"
            ),
            "sha256": (
                "9A6F39CCD05DD8A6F64E9F36F38C6ECCC9C333904CEA7F3CE7E95CEC48214D4A"
            ),
        },
        "upstreamSource": {
            "path": (
                "D:/prime-agent/.worktrees/rook-upstream-evaluation/"
                "packages/coding-agent/skills/goal/src/goal/__init__.py"
            ),
            "sha256": (
                "9A6F39CCD05DD8A6F64E9F36F38C6ECCC9C333904CEA7F3CE7E95CEC48214D4A"
            ),
        },
    }
    ignored = {
        "schema",
        "purpose",
        "goalSkillCustody",
        "precontactGate",
        "offlineEvaluator",
    }
    assert {key: value for key, value in v2.items() if key not in ignored} == {
        key: value
        for key, value in v1.items()
        if key not in {"schema", "purpose", "offlineEvaluator"}
    }
    assert v2["offlineEvaluator"]["runnerPath"] == v1["offlineEvaluator"]["runnerPath"]
    assert v2["offlineEvaluator"]["acceptanceArtifactPath"] == (
        v1["offlineEvaluator"]["acceptanceArtifactPath"]
    )
    assert v2["offlineEvaluator"]["acceptanceArtifactSha256"] == (
        v1["offlineEvaluator"]["acceptanceArtifactSha256"]
    )


def _goal_preflight_record(protocol: dict) -> dict:
    root = Path(protocol["prime"]["sourceRoot"])
    return {
        "schema": "rook.experiment.prime_goal_preflight:v2",
        "pythonExecutable": protocol["prime"]["sealedKernelPython"],
        "goalFile": protocol["goalSkillCustody"]["sealedKernel"]["path"],
        "rlmFile": str(root / "prime-agent-runtime" / "src" / "rlm" / "__init__.py"),
        "rookFullFile": (
            "C:/qualified-row/agent/skills/rook-full/src/rook_full/__init__.py"
        ),
        "goalPreimported": True,
        "getStatus": "active",
        "getTokenBudget": protocol["limits"]["primeGoalTokenBudget"],
        "completeStatus": "complete",
        "requests": ["goal.get", "goal.complete"],
        "kernelClosed": True,
    }


def test_prime_upstream_v2_preflight_admits_exact_installed_goal():
    runner = _runner()
    protocol = _prime_upstream_smoke_v2_protocol()
    record = _goal_preflight_record(protocol)

    assert runner.validate_preflight_record(
        record,
        Path(protocol["prime"]["sealedKernelPython"]),
        protocol["limits"]["primeGoalTokenBudget"],
        Path(protocol["prime"]["sourceRoot"]),
        protocol["goalSkillCustody"],
    ) == record

    record["goalFile"] = str(Path(record["goalFile"]).with_name("shadow.py"))
    with pytest.raises(ValueError, match="preflight_invalid"):
        runner.validate_preflight_record(
            record,
            Path(protocol["prime"]["sealedKernelPython"]),
            protocol["limits"]["primeGoalTokenBudget"],
            Path(protocol["prime"]["sourceRoot"]),
            protocol["goalSkillCustody"],
        )


@pytest.mark.parametrize("changed_side", ["sealedKernel", "upstreamSource"])
def test_goal_skill_equivalence_rejects_one_byte_drift(tmp_path, changed_side):
    runner = _runner()
    sealed = tmp_path / "sealed" / "goal" / "__init__.py"
    upstream = tmp_path / "prime" / "goal" / "src" / "goal" / "__init__.py"
    sealed.parent.mkdir(parents=True)
    upstream.parent.mkdir(parents=True)
    sealed.write_text("VALUE = 1\n", encoding="utf-8")
    upstream.write_bytes(sealed.read_bytes())
    digest = hashlib.sha256(sealed.read_bytes()).hexdigest().upper()
    custody = {
        "sealedKernel": {"path": str(sealed), "sha256": digest},
        "upstreamSource": {"path": str(upstream), "sha256": digest},
    }

    assert runner.verify_goal_skill_equivalence(custody)["equivalent"] is True
    Path(custody[changed_side]["path"]).write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="custody_mismatch:goal_skill"):
        runner.verify_goal_skill_equivalence(custody)


def test_goal_skill_equivalence_rejects_missing_file(tmp_path):
    runner = _runner()
    missing = tmp_path / "missing.py"
    custody = {
        "sealedKernel": {"path": str(missing), "sha256": "A" * 64},
        "upstreamSource": {"path": str(missing), "sha256": "A" * 64},
    }

    with pytest.raises(RuntimeError, match="custody_mismatch:goal_skill"):
        runner.verify_goal_skill_equivalence(custody)


def test_prime_upstream_v2_exposes_model_free_preflight_command(tmp_path):
    runner = _runner()

    args = runner._parser().parse_args(
        [
            "preflight",
            "--protocol",
            str(PRIME_UPSTREAM_SMOKE_V2_PROTOCOL_PATH),
            "--evidence-root",
            str(tmp_path / "evidence"),
        ]
    )

    assert args.command == "preflight"


def test_prime_upstream_v2_cannot_enter_live_campaign(tmp_path):
    runner = _runner()
    evidence_root = tmp_path / "v2-live-evidence"

    with pytest.raises(
        RuntimeError, match="precontact_protocol_not_live_executable"
    ):
        runner.run_campaign(
            PRIME_UPSTREAM_SMOKE_V2_PROTOCOL_PATH,
            evidence_root,
            268435457,
            None,
        )

    assert not evidence_root.exists()


def test_prime_upstream_v3_is_only_the_reviewable_live_contact_transition():
    runner = _runner()
    v2 = _prime_upstream_smoke_v2_protocol()
    v3 = _prime_upstream_smoke_v3_protocol()

    assert hashlib.sha256(PRIME_UPSTREAM_SMOKE_PROTOCOL_PATH.read_bytes()).hexdigest().upper() == (
        "512A0843FB8D59DC25F5C8C81B40C296C06DA7DA06778CA86AC82C6C2B711BCD"
    )
    assert hashlib.sha256(PRIME_UPSTREAM_SMOKE_V2_PROTOCOL_PATH.read_bytes()).hexdigest().upper() == (
        "D8F125BCFDC5E3D88E7845A6602FE46B52894652E3FF9FCB7D648FAF5B743687"
    )
    assert runner.validate_protocol(v3) is v3
    assert v3["schema"] == runner.PRIME_UPSTREAM_SMOKE_V3_SCHEMA
    assert v3["contactMode"] == {
        "mode": "single_t3_live_contact",
        "evidenceRoot": (
            "C:/UDEV/RookEvidence/"
            "2026-08-19-prime-upstream-t3-compatibility-smoke-v3"
        ),
        "actorContactAuthorized": True,
    }
    ignored = {
        "schema",
        "purpose",
        "precontactGate",
        "contactMode",
        "offlineEvaluator",
    }
    assert {key: value for key, value in v3.items() if key not in ignored} == {
        key: value for key, value in v2.items() if key not in ignored
    }
    assert v3["offlineEvaluator"] == (
        v2["offlineEvaluator"]
        | {
            "runnerSha256": (
                "7A81222EA54B0E70BA506EACA4EA805E9132945BC0C83AB1FDDD008ECF292085"
            )
        }
    )


def test_prime_upstream_v3_rejects_evidence_root_drift_before_creation(tmp_path):
    runner = _runner()
    evidence_root = tmp_path / "wrong-v3-evidence"

    with pytest.raises(RuntimeError, match="live_contact_evidence_root_invalid"):
        runner.run_campaign(
            PRIME_UPSTREAM_SMOKE_V3_PROTOCOL_PATH,
            evidence_root,
            268435457,
            None,
        )

    assert not evidence_root.exists()


def _committed_prime_test_repository(root: Path) -> Path:
    source = root / "prime-agent-runtime" / "src" / "rlm" / "mcp_base.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.name", "Prime Custody Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "prime@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "baseline"],
        check=True,
        capture_output=True,
    )
    return source


def test_prime_runtime_custody_rejects_modified_tracked_source(tmp_path):
    runner = _runner()
    source = _committed_prime_test_repository(tmp_path / "prime")

    runner.require_clean_prime_worktree(source.parents[3])
    source.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="custody_mismatch:prime_worktree_dirty"):
        runner.require_clean_prime_worktree(source.parents[3])


def test_prime_runtime_custody_rejects_untracked_source(tmp_path):
    runner = _runner()
    source = _committed_prime_test_repository(tmp_path / "prime")

    shadow = source.with_name("shadow.py")
    shadow.write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="custody_mismatch:prime_worktree_dirty"):
        runner.require_clean_prime_worktree(source.parents[3])


def test_vp2_evidence_reuse_skill_delta_is_exactly_one_reviewed_rule():
    baseline_skill = SKILL_PATH.read_bytes()
    experimental_skill = VP2_EVIDENCE_REUSE_SKILL_PATH.read_text(encoding="utf-8")

    assert hashlib.sha256(baseline_skill).hexdigest().upper() == BASELINE_SKILL_SHA256
    assert EVIDENCE_REUSE_RULE not in baseline_skill.decode("utf-8")
    assert experimental_skill.count(EVIDENCE_REUSE_RULE) == 1
    prior = experimental_skill.replace(
        EVIDENCE_REUSE_RULE + "\n\n", "", 1
    ).encode("utf-8")
    assert hashlib.sha256(prior).hexdigest().upper() == BASELINE_SKILL_SHA256


def test_vp2_strategy_discipline_skill_delta_is_exactly_one_reviewed_rule():
    source_skill = VP2_EVIDENCE_REUSE_SKILL_PATH.read_bytes()
    experimental_skill = VP2_STRATEGY_DISCIPLINE_SKILL_PATH.read_text(
        encoding="utf-8"
    )

    assert hashlib.sha256(SKILL_PATH.read_bytes()).hexdigest().upper() == (
        BASELINE_SKILL_SHA256
    )
    assert STRATEGY_DISCIPLINE_RULE not in source_skill.decode("utf-8")
    assert experimental_skill.count(EVIDENCE_REUSE_RULE) == 1
    assert experimental_skill.count(STRATEGY_DISCIPLINE_RULE) == 1
    prior = experimental_skill.replace(
        STRATEGY_DISCIPLINE_RULE + "\n\n", "", 1
    ).encode("utf-8")
    assert prior == source_skill


def test_vp2_strategy_screening_freezes_only_the_reviewed_skill_delta():
    runner = _runner()
    source = _vp2_evidence_reuse_protocol()
    screening = _vp2_strategy_discipline_protocol()

    assert runner.validate_protocol(screening) is screening
    assert screening["executionOrder"] == ["VP2"]
    assert screening["tasks"] == source["tasks"]
    for owner in (
        "prime",
        "limits",
        "pythonEnvironment",
        "modelCustody",
        "rookCustody",
        "offlineEvaluator",
        "toolSurface",
        "sourceCampaignProtocol",
        "continuationPolicy",
        "precontactVerification",
        "shadowAdjudication",
        "offlineEvaluator",
    ):
        assert screening[owner] == source[owner]
    assert screening["versionedInputs"]["skillPath"] == (
        VP2_STRATEGY_DISCIPLINE_SKILL_PATH.relative_to(ROOT).as_posix()
    )
    assert screening["versionedInputs"]["skillSha256"] == hashlib.sha256(
        VP2_STRATEGY_DISCIPLINE_SKILL_PATH.read_bytes()
    ).hexdigest().upper()
    assert screening["versionedInputs"]["checkpointSha256"] == (
        source["versionedInputs"]["checkpointSha256"]
    )
    assert screening["versionedInputs"]["adapterInitSha256"] == (
        source["versionedInputs"]["adapterInitSha256"]
    )

    normalized = json.loads(json.dumps(screening))
    normalized["purpose"] = source["purpose"]
    normalized["versionedInputs"]["skillPath"] = source["versionedInputs"][
        "skillPath"
    ]
    normalized["versionedInputs"]["skillSha256"] = source["versionedInputs"][
        "skillSha256"
    ]
    normalized["screeningRetest"] = source["screeningRetest"]
    assert normalized == source


def test_vp2_strategy_screening_contract_is_closed_to_one_silent_row():
    protocol = _vp2_strategy_discipline_protocol()

    assert protocol["screeningRetest"] == {
        "sourceProtocol": {
            "path": VP2_EVIDENCE_REUSE_PROTOCOL_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(
                VP2_EVIDENCE_REUSE_PROTOCOL_PATH.read_bytes()
            ).hexdigest().upper(),
        },
        "sourceEvidenceManifest": {
            "path": "C:/UDEV/RookEvidence/2026-08-18-qwen38-vp2-evidence-reuse-screening-v1/evidence-manifest.json",
            "sha256": "22E45CAE9517C8BFDEA395BBFF9B734574251C1C979EB6FCD8618F413E05F173",
        },
        "onlyChangedOperationalInput": "versioned_prime_skill",
        "sourceSkillSha256": hashlib.sha256(
            VP2_EVIDENCE_REUSE_SKILL_PATH.read_bytes()
        ).hexdigest().upper(),
        "rule": STRATEGY_DISCIPLINE_RULE,
        "baselineTelemetry": {
            "wholesaleDeletedCommittedComponents": 26,
            "committedComponentsPreservedDuringPivot": 0,
            "replacementStrategyDiscoveryCalls": 3,
            "gatewayCalls": 72,
            "cumulativeProviderTokens": 2092295,
        },
        "successCriteria": [
            "no_wholesale_deletion_without_live_evidence",
            "preserve_unaffected_committed_work_during_pivot",
            "fewer_than_3_replacement_strategy_discovery_calls",
            "fewer_than_2092295_cumulative_provider_tokens",
            "any_strategy_pivot_supported_by_live_evidence",
            "mechanically_healthy_canopy_without_material_regression",
            "receipt_fenced_final_snapshot_then_goal_complete",
            "budget_pass",
            "custody_pass",
        ],
        "evaluatorFeedbackDuringRun": False,
    }

    altered = json.loads(json.dumps(protocol))
    altered["screeningRetest"]["rule"] += " Prefer native components."
    with pytest.raises(ValueError, match="screening_retest_invalid"):
        _runner().validate_protocol(altered)


def _vp2_connection_truthfulness_retest_protocol() -> dict:
    return json.loads(
        VP2_CONNECTION_TRUTHFULNESS_RETEST_PROTOCOL_PATH.read_text(
            encoding="utf-8"
        )
    )


def _vp1_prospective_efficiency_protocol() -> dict:
    return json.loads(
        VP1_PROSPECTIVE_EFFICIENCY_PROTOCOL_PATH.read_text(encoding="utf-8")
    )


def test_vp1_prospective_skill_delta_is_exact_and_corrects_known_tool_example():
    source_skill = VP2_STRATEGY_DISCIPLINE_SKILL_PATH.read_text(encoding="utf-8")
    experimental_skill = VP1_PROSPECTIVE_EFFICIENCY_SKILL_PATH.read_text(
        encoding="utf-8"
    )

    assert experimental_skill.count(KNOWN_TOOL_DISCOVERY_RULE) == 1
    assert 'search_payload = await rook_full.search("gh_edit")' not in experimental_skill
    prior = experimental_skill.replace(KNOWN_TOOL_DISCOVERY_RULE + "\n\n", "", 1)
    prior = prior.replace(
        'tool_contract = await rook_full.read("gh_edit")',
        'search_payload = await rook_full.search("gh_edit")\n'
        'tool_contract = await rook_full.read("gh_edit")',
        1,
    )
    assert prior == source_skill


def test_vp1_prospective_screen_freezes_task_budget_and_primary_observations():
    runner = _runner()
    source = _vp2_connection_truthfulness_retest_protocol()
    varied = _varied_cohort_protocol()
    protocol = _vp1_prospective_efficiency_protocol()

    assert runner.validate_protocol(protocol) is protocol
    assert protocol["executionOrder"] == ["VP1"]
    assert protocol["tasks"] == {"VP1": varied["tasks"]["VP1"]}
    assert protocol["limits"] == source["limits"] | {"primeGoalTokenBudget": 1_900_000}
    assert protocol["prospectiveScreen"] == {
        "classification": "single_prospective_efficiency_screen",
        "sourceOperationalProtocol": {
            "path": VP2_CONNECTION_TRUTHFULNESS_RETEST_PROTOCOL_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(
                VP2_CONNECTION_TRUTHFULNESS_RETEST_PROTOCOL_PATH.read_bytes()
            ).hexdigest().upper(),
        },
        "taskSourceProtocol": {
            "path": VARIED_COHORT_PROTOCOL_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(VARIED_COHORT_PROTOCOL_PATH.read_bytes())
            .hexdigest()
            .upper(),
            "taskId": "VP1",
        },
        "changedOperationalInputs": [
            "task",
            "versioned_prime_skill",
            "prime_goal_token_budget",
            "shadow_adjudication_task_subset",
        ],
        "sourceSkillSha256": hashlib.sha256(
            VP2_STRATEGY_DISCIPLINE_SKILL_PATH.read_bytes()
        ).hexdigest().upper(),
        "rule": KNOWN_TOOL_DISCOVERY_RULE,
        "budgetSplit": {
            "providerCeilingTokens": 2_000_000,
            "primeGoalBudgetTokens": 1_900_000,
            "finalResponseReserveTokens": 100_000,
        },
        "primaryObservations": [
            "searches_for_skill_listed_tool_names",
            "duplicate_contract_reads",
            "gateway_calls_before_first_mutation",
            "provider_tokens_before_first_mutation",
            "named_reasons_for_further_discovery",
            "semantic_health",
            "final_receipt_fenced_evidence",
            "goal_complete",
        ],
        "evaluatorFeedbackDuringRun": False,
    }
    for owner in (
        "prime",
        "pythonEnvironment",
        "modelCustody",
        "rookCustody",
        "offlineEvaluator",
        "toolSurface",
        "sourceCampaignProtocol",
        "continuationPolicy",
        "precontactVerification",
    ):
        assert protocol[owner] == source[owner]
    adjudication = json.loads(
        VP1_PROSPECTIVE_EFFICIENCY_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )
    assert set(adjudication["tasks"]) == {"VP1"}
    assert protocol["shadowAdjudication"] == {
        "path": VP1_PROSPECTIVE_EFFICIENCY_ADJUDICATION_PATH.relative_to(
            ROOT
        ).as_posix(),
        "sha256": hashlib.sha256(
            VP1_PROSPECTIVE_EFFICIENCY_ADJUDICATION_PATH.read_bytes()
        ).hexdigest().upper(),
    }
    assert protocol["versionedInputs"]["skillPath"] == (
        VP1_PROSPECTIVE_EFFICIENCY_SKILL_PATH.relative_to(ROOT).as_posix()
    )
    assert protocol["versionedInputs"]["skillSha256"] == hashlib.sha256(
        VP1_PROSPECTIVE_EFFICIENCY_SKILL_PATH.read_bytes()
    ).hexdigest().upper()


def test_vp4_profile_stack_reuses_prospective_path_and_changes_only_task_evaluation():
    runner = _runner()
    source = _vp1_prospective_efficiency_protocol()
    protocol = json.loads(VP4_PROFILE_STACK_PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert runner.validate_protocol(protocol) is protocol
    assert protocol["executionOrder"] == ["VP4"]
    assert protocol["tasks"] == {
        "VP4": {
            "id": "VP4",
            "class": "parametric_profile_stack",
            "targetBaseline": "fresh_empty_grasshopper_document",
            "evaluator": "independent_shadow_judgment",
            "prompt": PROFILE_STACK_PROMPT,
            "targetFixture": {
                "schema": "rook.experiment.gh_target_fixture:v1",
                "baseline": "fresh_empty",
                "seedEdit": None,
                "seedExpectations": None,
                "preservation": None,
            },
        }
    }
    for owner in (
        "limits",
        "prime",
        "pythonEnvironment",
        "modelCustody",
        "rookCustody",
        "offlineEvaluator",
        "versionedInputs",
        "toolSurface",
        "sourceCampaignProtocol",
        "continuationPolicy",
        "precontactVerification",
    ):
        assert protocol[owner] == source[owner]
    assert protocol["versionedInputs"]["skillSha256"] == (
        "6C6A7AFF7B7A6F8B4C36F4F6E2ACCCC44D00443354662843523B92D4AB22A2DD"
    )
    assert protocol["prospectiveScreen"] == {
        "classification": "single_prospective_efficiency_screen",
        "sourceOperationalProtocol": {
            "path": VP1_PROSPECTIVE_EFFICIENCY_PROTOCOL_PATH.relative_to(
                ROOT
            ).as_posix(),
            "sha256": hashlib.sha256(
                VP1_PROSPECTIVE_EFFICIENCY_PROTOCOL_PATH.read_bytes()
            ).hexdigest().upper(),
        },
        "taskSourceProtocol": {
            "path": VP1_PROSPECTIVE_EFFICIENCY_PROTOCOL_PATH.relative_to(
                ROOT
            ).as_posix(),
            "sha256": hashlib.sha256(
                VP1_PROSPECTIVE_EFFICIENCY_PROTOCOL_PATH.read_bytes()
            ).hexdigest().upper(),
            "taskId": "VP1",
        },
        "changedOperationalInputs": [
            "task",
            "shadow_adjudication_task_subset",
        ],
        "sourceSkillSha256": source["versionedInputs"]["skillSha256"],
        "rule": KNOWN_TOOL_DISCOVERY_RULE,
        "budgetSplit": {
            "providerCeilingTokens": 2_000_000,
            "primeGoalBudgetTokens": 1_900_000,
            "finalResponseReserveTokens": 100_000,
        },
        "primaryObservations": [
            "searches_for_skill_listed_tool_names",
            "duplicate_contract_reads",
            "gateway_calls_before_first_mutation",
            "provider_tokens_before_first_mutation",
            "named_reasons_for_further_discovery",
            "total_mutation_and_commit_churn",
            "local_repair_behavior",
            "semantic_health",
            "final_receipt_fenced_evidence",
            "goal_complete",
        ],
        "evaluatorFeedbackDuringRun": False,
    }
    adjudication = json.loads(
        VP4_PROFILE_STACK_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )
    assert set(adjudication["tasks"]) == {"VP4"}
    assert protocol["shadowAdjudication"] == {
        "path": VP4_PROFILE_STACK_ADJUDICATION_PATH.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(
            VP4_PROFILE_STACK_ADJUDICATION_PATH.read_bytes()
        ).hexdigest().upper(),
    }


def _remove_authoring_lane_block(skill: str) -> str:
    start = "<!-- authoring-lane:start -->\n"
    end = "<!-- authoring-lane:end -->\n\n"
    assert skill.count(start) == 1
    assert skill.count(end) == 1
    prefix, remainder = skill.split(start, 1)
    _, suffix = remainder.split(end, 1)
    without_lane = prefix + suffix
    return without_lane.replace(
        'tool_contract = await rook_full.read("gh_edit")',
        'search_payload = await rook_full.search("gh_edit")\n'
        'tool_contract = await rook_full.read("gh_edit")',
        1,
    )


def test_authoring_lane_skills_are_closed_deltas_from_canonical_skill():
    canonical = SKILL_PATH.read_text(encoding="utf-8")
    native = NATIVE_LANE_SKILL_PATH.read_text(encoding="utf-8")
    python = PYTHON_LANE_SKILL_PATH.read_text(encoding="utf-8")

    assert hashlib.sha256(SKILL_PATH.read_bytes()).hexdigest().upper() == (
        BASELINE_SKILL_SHA256
    )
    assert _remove_authoring_lane_block(native) == canonical
    assert _remove_authoring_lane_block(python) == canonical
    assert 'search_payload = await rook_full.search("gh_edit")' not in native
    assert 'search_payload = await rook_full.search("gh_edit")' not in python

    native_block = native.split("<!-- authoring-lane:start -->", 1)[1].split(
        "<!-- authoring-lane:end -->", 1
    )[0]
    normalized_native_block = " ".join(native_block.split())
    assert "native-components authoring lane" in native_block
    assert "Script components are outside this row's admitted authoring lane" in (
        normalized_native_block
    )
    assert "Script components are unavailable" not in native_block
    for capability in (
        "gh_snapshot",
        "gh_library",
        "gh_batch_component_info",
        "gh_edit",
        "gh_errors",
        "gh_wait_for_solve_readiness",
    ):
        assert capability in native_block
    for forbidden in (
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
        "gh_update_script",
    ):
        assert forbidden not in native_block

    python_block = python.split("<!-- authoring-lane:start -->", 1)[1].split(
        "<!-- authoring-lane:end -->", 1
    )[0]
    assert "Python authoring lane" in python_block
    for capability in (
        "gh_snapshot",
        "gh_create_script",
        "gh_set_script_pins",
        "gh_update_script",
        "gh_edit",
        "gh_errors",
        "gh_wait_for_solve_readiness",
    ):
        assert capability in python_block
    assert 'language="python"' in python_block
    assert "C#" not in python_block
    assert "csharp" not in python_block.lower()


def test_authoring_lane_protocol_freezes_one_native_and_one_python_row():
    runner = _runner()
    source = json.loads(VP4_PROFILE_STACK_PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol = _authoring_lane_protocol()

    assert runner.validate_protocol(protocol) is protocol
    assert protocol["executionOrder"] == ["N", "P"]
    assert protocol["tasks"]["N"]["prompt"] == CIRCULAR_LINE_ARRAY_PROMPT
    assert protocol["tasks"]["P"]["prompt"] == CIRCULAR_LINE_ARRAY_PROMPT
    assert protocol["tasks"]["N"] | {"id": "P"} == protocol["tasks"]["P"]
    assert "prospectiveScreen" not in protocol

    for owner in (
        "limits",
        "prime",
        "pythonEnvironment",
        "modelCustody",
        "rookCustody",
        "offlineEvaluator",
        "toolSurface",
        "sourceCampaignProtocol",
        "continuationPolicy",
        "precontactVerification",
    ):
        assert protocol[owner] == source[owner]
    assert protocol["versionedInputs"] == {
        "skillPath": SKILL_PATH.relative_to(ROOT).as_posix(),
        "skillSha256": BASELINE_SKILL_SHA256,
        "checkpointPath": source["versionedInputs"]["checkpointPath"],
        "checkpointSha256": source["versionedInputs"]["checkpointSha256"],
        "adapterRoot": source["versionedInputs"]["adapterRoot"],
        "adapterInitSha256": source["versionedInputs"]["adapterInitSha256"],
    }

    experiment = protocol["authoringLaneExperiment"]
    assert experiment["classification"] == "paired_authoring_lane_product_screen"
    assert experiment["sourceOperationalProtocol"] == {
        "path": VP4_PROFILE_STACK_PROTOCOL_PATH.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(
            VP4_PROFILE_STACK_PROTOCOL_PATH.read_bytes()
        ).hexdigest().upper(),
    }
    assert experiment["canonicalSkill"] == {
        "path": SKILL_PATH.relative_to(ROOT).as_posix(),
        "sha256": BASELINE_SKILL_SHA256,
    }
    assert experiment["rowLanes"] == {
        "N": {
            "lane": "native",
            "skillPath": NATIVE_LANE_SKILL_PATH.relative_to(ROOT).as_posix(),
            "skillSha256": hashlib.sha256(
                NATIVE_LANE_SKILL_PATH.read_bytes()
            ).hexdigest().upper(),
            "startingCapabilities": [
                "gh_snapshot",
                "gh_library",
                "gh_batch_component_info",
                "gh_edit",
                "gh_errors",
                "gh_wait_for_solve_readiness",
            ],
            "scriptComponentsAdmitted": False,
        },
        "P": {
            "lane": "python",
            "skillPath": PYTHON_LANE_SKILL_PATH.relative_to(ROOT).as_posix(),
            "skillSha256": hashlib.sha256(
                PYTHON_LANE_SKILL_PATH.read_bytes()
            ).hexdigest().upper(),
            "startingCapabilities": [
                "gh_snapshot",
                "gh_create_script",
                "gh_set_script_pins",
                "gh_update_script",
                "gh_edit",
                "gh_errors",
                "gh_wait_for_solve_readiness",
            ],
            "scriptLanguage": "python",
            "nativeDiscovery": "controls_or_named_blocker_only",
        },
    }
    assert experiment["successCriteria"] == [
        "credible_result_or_honest_failure",
        "budget_and_custody_pass",
        "count_and_height_exercised_and_restored",
        "final_receipt_fenced_snapshot_before_goal_complete",
        "no_later_gateway_call",
        "no_search_for_listed_capabilities",
        "no_implementation_mode_switch",
        "first_commit_within_12_gateway_calls",
        "first_commit_within_200000_cumulative_tokens",
        "no_equivalent_repeated_mutation_without_named_material_reason",
        "no_efficiency_credit_if_semantic_or_evidence_quality_regresses",
    ]
    assert experiment["firstCommitTokenAttribution"] == {
        "measurement": (
            "cumulative_provider_tokens_through_the_assistant_turn_that_originated_"
            "the_ipython_execution_containing_the_first_committed_source_event"
        ),
        "requiredCitations": [
            "first_committed_source_event",
            "originating_assistant_turn_usage",
        ],
        "ambiguousMappingDisposition": "unproven",
    }
    assert experiment["evaluatorFeedbackDuringRun"] is False
    assert experiment["retriesPerRow"] == 0
    assert experiment["midCampaignTuning"] is False
    assert experiment["interpretation"] == "product_screen_not_pure_causal_proof"
    assert experiment["laneRestrictionEnforcement"] == (
        "model_facing_skill_guidance_only"
    )
    assert experiment["excludedFutureComparison"] == "python_vs_csharp"
    assert protocol["capabilityAudit"] == {
        "path": AUTHORING_LANE_CAPABILITY_AUDIT_PATH.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(
            AUTHORING_LANE_CAPABILITY_AUDIT_PATH.read_bytes()
        ).hexdigest().upper(),
    }

    adjudication = json.loads(
        AUTHORING_LANE_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )
    assert runner.validate_shadow_adjudication(adjudication, protocol) is adjudication
    assert protocol["shadowAdjudication"] == {
        "path": AUTHORING_LANE_ADJUDICATION_PATH.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(
            AUTHORING_LANE_ADJUDICATION_PATH.read_bytes()
        ).hexdigest().upper(),
    }


def test_authoring_lane_protocol_rejects_crossed_or_tampered_lane_custody():
    runner = _runner()
    protocol = _authoring_lane_protocol()

    crossed = json.loads(json.dumps(protocol))
    crossed["authoringLaneExperiment"]["rowLanes"]["N"]["skillPath"] = (
        crossed["authoringLaneExperiment"]["rowLanes"]["P"]["skillPath"]
    )
    with pytest.raises(ValueError, match="authoring_lane_experiment_invalid"):
        runner.validate_protocol(crossed)

    mismatched_prompt = json.loads(json.dumps(protocol))
    mismatched_prompt["tasks"]["P"]["prompt"] += " Prefer native components."
    with pytest.raises(ValueError, match="authoring_lane_experiment_invalid"):
        runner.validate_protocol(mismatched_prompt)

    expanded = json.loads(json.dumps(protocol))
    expanded["executionOrder"].append("X")
    expanded["tasks"]["X"] = json.loads(json.dumps(expanded["tasks"]["N"]))
    expanded["tasks"]["X"]["id"] = "X"
    with pytest.raises(ValueError, match="authoring_lane_experiment_invalid"):
        runner.validate_protocol(expanded)


def test_python_lane_confirmation_reuses_exact_fixture_and_runtime_custody():
    runner = _runner()
    source = _authoring_lane_protocol()
    protocol = _python_lane_confirmation_protocol()

    assert runner.validate_protocol(protocol) is protocol
    assert protocol["executionOrder"] == ["P2"]
    assert protocol["tasks"] == {
        "P2": {
            "id": "P2",
            "class": "rectangular_point_lattice",
            "targetBaseline": "fresh_empty_grasshopper_document",
            "evaluator": "independent_shadow_judgment",
            "prompt": POINT_LATTICE_PROMPT,
            "targetFixture": {
                "schema": "rook.experiment.gh_target_fixture:v1",
                "baseline": "fresh_empty",
                "seedEdit": None,
                "seedExpectations": None,
                "preservation": None,
            },
        }
    }
    for owner in (
        "limits",
        "prime",
        "pythonEnvironment",
        "modelCustody",
        "rookCustody",
        "offlineEvaluator",
        "toolSurface",
        "sourceCampaignProtocol",
        "continuationPolicy",
        "precontactVerification",
        "versionedInputs",
        "capabilityAudit",
    ):
        assert protocol[owner] == source[owner]

    experiment = protocol["authoringLaneExperiment"]
    assert experiment["classification"] == "single_python_lane_varied_confirmation"
    assert experiment["sourceOperationalProtocol"] == {
        "path": AUTHORING_LANE_PROTOCOL_PATH.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(
            AUTHORING_LANE_PROTOCOL_PATH.read_bytes()
        ).hexdigest().upper(),
    }
    assert experiment["changedOperationalInputs"] == [
        "task",
        "execution_order",
        "shadow_adjudication_task_set",
    ]
    assert experiment["rowLanes"] == {
        "P2": source["authoringLaneExperiment"]["rowLanes"]["P"]
    }
    assert experiment["pairedControls"] == {
        "sourceRow": "P",
        "freshIsolatedTarget": True,
        "unchangedOperationalInputs": [
            "python_lane_skill_fixture",
            "model",
            "thinking_level",
            "prime_revision_and_bootstrap",
            "rook_build",
            "rook_full_adapter",
            "budgets_and_reserve",
            "target_preparation",
            "silent_evaluator",
            "evidence_capture",
            "checkpoint_and_completion_discipline",
        ],
    }
    assert experiment["successCriteria"] == [
        "credible_result_or_honest_failure",
        "budget_and_custody_pass",
        "columns_and_y_spacing_independently_exercised_and_restored",
        "final_receipt_fenced_snapshot_before_goal_complete",
        "no_later_gateway_call",
        "no_search_for_listed_capabilities",
        "no_implementation_mode_switch",
        "first_commit_within_12_gateway_calls",
        "first_commit_within_200000_cumulative_tokens",
        "no_equivalent_repeated_mutation_without_named_material_reason",
        "no_efficiency_credit_if_semantic_or_evidence_quality_regresses",
    ]
    assert "diagnostic" not in " ".join(experiment["successCriteria"])
    assert experiment["firstCommitTokenAttribution"] == source[
        "authoringLaneExperiment"
    ]["firstCommitTokenAttribution"]
    assert experiment["evaluatorFeedbackDuringRun"] is False
    assert experiment["retriesPerRow"] == 0
    assert experiment["midCampaignTuning"] is False
    assert experiment["interpretation"] == (
        "single_varied_confirmation_not_general_proof"
    )
    assert experiment["excludedFutureComparison"] == "python_vs_csharp"

    adjudication = json.loads(
        PYTHON_LANE_CONFIRMATION_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )
    assert runner.validate_shadow_adjudication(adjudication, protocol) is adjudication
    assert protocol["shadowAdjudication"] == {
        "path": PYTHON_LANE_CONFIRMATION_ADJUDICATION_PATH.relative_to(
            ROOT
        ).as_posix(),
        "sha256": hashlib.sha256(
            PYTHON_LANE_CONFIRMATION_ADJUDICATION_PATH.read_bytes()
        ).hexdigest().upper(),
    }


def test_python_lane_confirmation_rejects_fixture_or_scope_drift():
    runner = _runner()
    protocol = _python_lane_confirmation_protocol()

    changed_fixture = json.loads(json.dumps(protocol))
    changed_fixture["authoringLaneExperiment"]["rowLanes"]["P2"][
        "skillSha256"
    ] = "A" * 64
    with pytest.raises(ValueError, match="authoring_lane_experiment_invalid"):
        runner.validate_protocol(changed_fixture)

    added_native_row = json.loads(json.dumps(protocol))
    added_native_row["executionOrder"].append("N")
    added_native_row["tasks"]["N"] = json.loads(
        json.dumps(added_native_row["tasks"]["P2"])
    )
    added_native_row["tasks"]["N"]["id"] = "N"
    with pytest.raises(ValueError, match="authoring_lane_experiment_invalid"):
        runner.validate_protocol(added_native_row)

    added_retry = json.loads(json.dumps(protocol))
    added_retry["authoringLaneExperiment"]["retriesPerRow"] = 1
    with pytest.raises(ValueError, match="authoring_lane_experiment_invalid"):
        runner.validate_protocol(added_retry)


def test_python_lane_confirmation_stages_the_unchanged_python_fixture(tmp_path: Path):
    runner = _runner()
    protocol = _python_lane_confirmation_protocol()
    row_root = tmp_path / "P2"

    runner._copy_versioned_inputs(protocol, protocol["tasks"]["P2"], row_root)

    staged = (
        row_root / "agent" / "skills" / "prime-execute-grasshopper" / "SKILL.md"
    )
    assert staged.read_bytes() == PYTHON_LANE_SKILL_PATH.read_bytes()


@pytest.mark.parametrize(
    ("task_id", "expected_path"),
    (("N", NATIVE_LANE_SKILL_PATH), ("P", PYTHON_LANE_SKILL_PATH)),
)
def test_copy_versioned_inputs_stages_the_exact_row_lane_skill(
    tmp_path: Path, task_id: str, expected_path: Path
):
    runner = _runner()
    protocol = _authoring_lane_protocol()
    row_root = tmp_path / task_id

    runner._copy_versioned_inputs(protocol, protocol["tasks"][task_id], row_root)

    staged = (
        row_root / "agent" / "skills" / "prime-execute-grasshopper" / "SKILL.md"
    )
    assert staged.read_bytes() == expected_path.read_bytes()


def test_vp2_connection_truthfulness_retest_admits_only_the_repaired_runtime_delta():
    runner = _runner()
    source = _vp2_strategy_discipline_protocol()
    protocol = _vp2_connection_truthfulness_retest_protocol()

    assert runner.validate_protocol(protocol) is protocol
    assert protocol["executionOrder"] == ["VP2"]
    assert protocol["tasks"] == source["tasks"]
    for owner in (
        "prime",
        "limits",
        "modelCustody",
        "versionedInputs",
        "toolSurface",
        "sourceCampaignProtocol",
        "continuationPolicy",
        "precontactVerification",
        "shadowAdjudication",
    ):
        assert protocol[owner] == source[owner]

    altered = json.loads(json.dumps(protocol))
    altered["versionedInputs"]["skillSha256"] = "A" * 64
    with pytest.raises(ValueError, match="screening_retest_invalid"):
        runner.validate_protocol(altered)

    altered = json.loads(json.dumps(protocol))
    altered["screeningRetest"]["onlyChangedOperationalInput"] = (
        "versioned_prime_skill"
    )
    with pytest.raises(ValueError, match="screening_retest_invalid"):
        runner.validate_protocol(altered)


def test_vp2_evidence_reuse_screening_freezes_only_the_reviewed_input_delta():
    runner = _runner()
    baseline = _varied_cohort_protocol()
    screening = _vp2_evidence_reuse_protocol()

    assert runner.validate_protocol(screening) is screening
    assert screening["executionOrder"] == ["VP2"]
    assert screening["tasks"] == {"VP2": baseline["tasks"]["VP2"]}
    assert screening["prime"] == baseline["prime"]
    assert screening["limits"] == baseline["limits"]
    assert screening["pythonEnvironment"] == baseline["pythonEnvironment"]
    assert screening["modelCustody"] == baseline["modelCustody"]
    assert screening["rookCustody"] == baseline["rookCustody"]
    assert screening["offlineEvaluator"] == baseline["offlineEvaluator"]
    assert screening["toolSurface"] == baseline["toolSurface"]
    assert screening["sourceCampaignProtocol"] == baseline["sourceCampaignProtocol"]
    assert screening["continuationPolicy"] == baseline["continuationPolicy"]
    assert screening["precontactVerification"] == baseline["precontactVerification"]
    assert screening["versionedInputs"]["skillPath"] == (
        VP2_EVIDENCE_REUSE_SKILL_PATH.relative_to(ROOT).as_posix()
    )
    assert screening["versionedInputs"]["skillSha256"] == hashlib.sha256(
        VP2_EVIDENCE_REUSE_SKILL_PATH.read_bytes()
    ).hexdigest().upper()
    assert screening["versionedInputs"]["skillSha256"] != (
        baseline["versionedInputs"]["skillSha256"]
    )
    assert screening["versionedInputs"]["checkpointSha256"] == (
        baseline["versionedInputs"]["checkpointSha256"]
    )
    assert screening["versionedInputs"]["adapterInitSha256"] == (
        baseline["versionedInputs"]["adapterInitSha256"]
    )

    normalized = json.loads(json.dumps(screening))
    normalized["purpose"] = baseline["purpose"]
    normalized["executionOrder"] = baseline["executionOrder"]
    normalized["tasks"] = baseline["tasks"]
    normalized["versionedInputs"]["skillPath"] = baseline["versionedInputs"][
        "skillPath"
    ]
    normalized["versionedInputs"]["skillSha256"] = baseline["versionedInputs"][
        "skillSha256"
    ]
    normalized["shadowAdjudication"] = baseline["shadowAdjudication"]
    del normalized["screeningRetest"]
    assert normalized == baseline


def test_vp2_screening_adjudication_is_the_exact_baseline_vp2_slice():
    runner = _runner()
    baseline = json.loads(
        VARIED_COHORT_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )
    screening_protocol = _vp2_evidence_reuse_protocol()
    screening = json.loads(
        VP2_EVIDENCE_REUSE_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )

    assert runner.validate_shadow_adjudication(
        screening, screening_protocol
    ) is screening
    assert screening["tasks"] == {"VP2": baseline["tasks"]["VP2"]}
    normalized = json.loads(json.dumps(screening))
    normalized["tasks"] = baseline["tasks"]
    assert normalized == baseline
    assert screening_protocol["shadowAdjudication"]["sha256"] == hashlib.sha256(
        VP2_EVIDENCE_REUSE_ADJUDICATION_PATH.read_bytes()
    ).hexdigest().upper()


def test_vp2_screening_contract_is_closed_to_one_silent_row():
    runner = _runner()
    protocol = _vp2_evidence_reuse_protocol()

    assert protocol["screeningRetest"] == {
        "sourceProtocol": {
            "path": VARIED_COHORT_PROTOCOL_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(
                VARIED_COHORT_PROTOCOL_PATH.read_bytes()
            ).hexdigest().upper(),
        },
        "sourceEvidenceManifest": {
            "path": "C:/UDEV/RookEvidence/2026-08-18-qwen38-varied-product-cohort-v1/evidence-manifest.json",
            "sha256": "3E62BE054F33AA87D8F1A6745BA7B0769419220A954A5667160CB89EB1EB4990",
        },
        "onlyChangedOperationalInput": "versioned_prime_skill",
        "sourceSkillSha256": BASELINE_SKILL_SHA256,
        "rule": EVIDENCE_REUSE_RULE,
        "baselineTelemetry": {
            "discoveryAndSchemaCalls": 36,
            "exactRepeatedSuccessfulSchemaReads": 6,
            "repeatedMetadataSelectorOccurrences": 25,
            "modelTurns": 46,
            "finalInputContextTokens": 85407,
            "cumulativeProviderInputTokens": 2012994,
        },
        "successCriteria": [
            "no_exact_repeated_successful_schema_read",
            "no_resolved_metadata_selector_repeat_without_named_stale_trigger",
            "fewer_than_36_discovery_and_schema_calls",
            "mechanically_healthy_canopy_without_material_regression",
            "receipt_fenced_final_snapshot_then_goal_complete",
            "budget_pass",
            "custody_pass",
        ],
        "evaluatorFeedbackDuringRun": False,
    }

    expanded = json.loads(json.dumps(protocol))
    expanded["executionOrder"] = ["VP1", "VP2"]
    expanded["tasks"]["VP1"] = _varied_cohort_protocol()["tasks"]["VP1"]
    with pytest.raises(ValueError, match="task_order_invalid"):
        runner.validate_protocol(expanded)


def _screening_with_manifest(protocol: dict, manifest_path: Path) -> dict:
    updated = json.loads(json.dumps(protocol))
    updated["screeningRetest"]["sourceEvidenceManifest"] = {
        "path": manifest_path.as_posix(),
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest().upper(),
    }
    return updated


def test_screening_precontact_retains_verified_source_evidence(tmp_path: Path):
    runner = _runner()
    source = tmp_path / "source"
    source.mkdir()
    (source / "result.json").write_text('{"status":"complete"}\n', encoding="utf-8")
    manifest_path = source / "evidence-manifest.json"
    runner.write_evidence_manifest(source, manifest_path)
    protocol = _screening_with_manifest(
        _vp2_evidence_reuse_protocol(), manifest_path
    )
    screening_root = tmp_path / "screening"
    screening_root.mkdir()

    result = runner.verify_screening_source_evidence(protocol, screening_root)

    assert result == {
        "schema": "rook.experiment.screening_source_evidence_verification:v1",
        "status": "pass",
        "manifestPath": manifest_path.as_posix(),
        "expectedSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest().upper(),
        "observedSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest().upper(),
        "evidenceRoot": source.as_posix(),
        "entryCount": 1,
        "mismatches": [],
        "reason": None,
    }
    assert json.loads(
        (screening_root / "screening-source-evidence-verification.json").read_text()
    ) == result


def test_screening_precontact_refuses_and_records_missing_source_manifest(
    tmp_path: Path,
):
    runner = _runner()
    protocol = _vp2_evidence_reuse_protocol()
    missing = tmp_path / "missing" / "evidence-manifest.json"
    protocol["screeningRetest"]["sourceEvidenceManifest"] = {
        "path": missing.as_posix(),
        "sha256": "A" * 64,
    }
    screening_root = tmp_path / "screening"
    screening_root.mkdir()

    with pytest.raises(RuntimeError, match="screening_source_manifest_missing"):
        runner.verify_screening_source_evidence(protocol, screening_root)

    retained = json.loads(
        (screening_root / "screening-source-evidence-verification.json").read_text()
    )
    assert retained["status"] == "fail"
    assert retained["reason"] == "screening_source_manifest_missing"
    assert retained["observedSha256"] is None


def test_screening_precontact_refuses_and_records_source_manifest_digest_drift(
    tmp_path: Path,
):
    runner = _runner()
    source = tmp_path / "source"
    source.mkdir()
    (source / "result.json").write_text('{"status":"complete"}\n', encoding="utf-8")
    manifest_path = source / "evidence-manifest.json"
    runner.write_evidence_manifest(source, manifest_path)
    protocol = _screening_with_manifest(
        _vp2_evidence_reuse_protocol(), manifest_path
    )
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    screening_root = tmp_path / "screening"
    screening_root.mkdir()

    with pytest.raises(RuntimeError, match="screening_source_manifest_digest_mismatch"):
        runner.verify_screening_source_evidence(protocol, screening_root)

    retained = json.loads(
        (screening_root / "screening-source-evidence-verification.json").read_text()
    )
    assert retained["status"] == "fail"
    assert retained["reason"] == "screening_source_manifest_digest_mismatch"
    assert retained["observedSha256"] != retained["expectedSha256"]


def test_screening_precontact_refuses_source_evidence_mismatch_before_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    source = tmp_path / "source"
    source.mkdir()
    payload = source / "result.json"
    payload.write_text('{"status":"complete"}\n', encoding="utf-8")
    manifest_path = source / "evidence-manifest.json"
    runner.write_evidence_manifest(source, manifest_path)
    protocol = _screening_with_manifest(
        _vp2_evidence_reuse_protocol(), manifest_path
    )
    payload.write_text('{"status":"altered"}\n', encoding="utf-8")
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    screening_root = tmp_path / "screening"
    prepared: list[str] = []

    monkeypatch.setattr(runner, "validate_evidence_root", lambda path: Path(path))
    monkeypatch.setattr(runner, "run_precontact_verification", lambda *args: {})
    monkeypatch.setattr(
        runner, "_prepare_target", lambda *args: prepared.append("target")
    )

    with pytest.raises(RuntimeError, match="screening_source_evidence_mismatch"):
        runner.run_campaign(protocol_path, screening_root, 268435457, None)

    assert prepared == []
    retained = json.loads(
        (screening_root / "screening-source-evidence-verification.json").read_text()
    )
    assert retained["status"] == "fail"
    assert retained["reason"] == "screening_source_evidence_mismatch"
    assert retained["mismatches"] == ["result.json"]


def test_varied_cohort_freezes_v6_runtime_and_exact_reviewed_evaluator_delta():
    runner = _runner()
    v6 = json.loads(V6_PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = _varied_cohort_protocol()

    assert runner.validate_protocol(cohort) is cohort
    assert cohort["executionOrder"] == ["VP1", "VP2", "VP3"]
    assert cohort["prime"] == v6["prime"]
    assert cohort["limits"] == v6["limits"]
    assert cohort["pythonEnvironment"] == v6["pythonEnvironment"]
    assert cohort["modelCustody"] == v6["modelCustody"]
    assert cohort["rookCustody"] == v6["rookCustody"]
    assert cohort["versionedInputs"] == v6["versionedInputs"]
    assert cohort["toolSurface"] == v6["toolSurface"]
    evaluator = cohort["offlineEvaluator"]
    evaluator_path = ROOT / evaluator["behavioralAcceptancePath"]
    assert evaluator["sourceCampaignProtocolSha256"] == hashlib.sha256(
        V6_PROTOCOL_PATH.read_bytes()
    ).hexdigest().upper()
    assert evaluator["behavioralAcceptanceSha256"] == hashlib.sha256(
        evaluator_path.read_bytes()
    ).hexdigest().upper()
    assert evaluator["reviewedCorrectionCommit"] == (
        "efe0615466b84079263fd190336831bfce59343a"
    )


def test_varied_cohort_tasks_are_distinct_closed_product_fixtures():
    runner = _runner()
    protocol = _varied_cohort_protocol()

    prompts = []
    for task_id in protocol["executionOrder"]:
        task = protocol["tasks"][task_id]
        assert runner.validate_target_fixture(task["targetFixture"]) is task[
            "targetFixture"
        ]
        prompts.append(task["prompt"].lower())
    assert protocol["tasks"]["VP1"]["targetFixture"]["baseline"] == (
        "seeded_working_definition"
    )
    assert protocol["tasks"]["VP2"]["targetFixture"]["baseline"] == "fresh_empty"
    assert protocol["tasks"]["VP3"]["targetFixture"]["baseline"] == "fresh_empty"
    assert sum("point row" in prompt for prompt in prompts) == 0
    assert sum("grid" in prompt for prompt in prompts) == 0
    assert sum("helix" in prompt for prompt in prompts) == 0


def test_varied_cohort_adjudication_is_shadow_only_and_closed():
    runner = _runner()
    protocol = _varied_cohort_protocol()
    adjudication = json.loads(
        VARIED_COHORT_ADJUDICATION_PATH.read_text(encoding="utf-8")
    )

    assert runner.validate_shadow_adjudication(adjudication, protocol) is adjudication
    assert hashlib.sha256(VARIED_COHORT_ADJUDICATION_PATH.read_bytes()).hexdigest().upper() == (
        protocol["shadowAdjudication"]["sha256"]
    )
    assert adjudication["evaluatorFeedbackDuringRun"] is False
    assert adjudication["evidenceLabels"] == ["observed", "inferred", "unresolved"]
    assert adjudication["aggregateScore"] is None
    assert set(adjudication["tasks"]) == {"VP1", "VP2", "VP3"}


def test_seed_preservation_uses_temp_id_mapping_and_closed_snapshot_facts():
    runner = _runner()
    fixture = _varied_cohort_protocol()["tasks"]["VP1"]["targetFixture"]
    seed_evidence = {
        "edit": {
            "success": True,
            "data": {
                "edit_summary": {
                    "temp_id_map": {
                        "T1": "C1",
                        "T2": "C2",
                        "T3": "C3",
                        "T4": "C4",
                        "T5": "C5",
                        "T6": "C6",
                    }
                }
            },
        },
        "snapshot": {
            "success": True,
            "data": {
                "components": [
                    {"id": "C1", "type": "NumberSlider", "nick": "Radius", "value": {"type": "slider", "val": 8}},
                    {
                        "id": "C2",
                        "type": "Component_Circle",
                        "nick": "Circle",
                        "componentGuid": "807b86e3-be8d-4970-92b5-f8cdcb45b06b",
                    },
                    {"id": "C3", "type": "NumberSlider", "nick": "Reference A", "value": {"type": "slider", "val": 2}},
                    {"id": "C4", "type": "NumberSlider", "nick": "Reference B", "value": {"type": "slider", "val": 3}},
                    {
                        "id": "C5",
                        "type": "Component_VariableAddition",
                        "nick": "A+B",
                        "componentGuid": "a0d62394-a118-422d-abb3-6af115c75b25",
                    },
                    {"id": "C6", "type": "Panel", "nick": "Reference Result", "value": {"type": "panel", "val": "5"}},
                ],
                "flows": ["C1.O0>C2.I1", "C3.O0>C5.I0", "C4.O0>C5.I1", "C5.O0>C6.I0"],
            },
        },
    }
    final_snapshot = json.loads(json.dumps(seed_evidence["snapshot"]["data"]))

    passed = runner.evaluate_seed_preservation(fixture, seed_evidence, final_snapshot)
    assert passed == {
        "schema": "rook.experiment.seed_preservation:v1",
        "status": "pass",
        "violations": [],
    }

    final_snapshot["components"] = [
        item for item in final_snapshot["components"] if item["id"] != "C4"
    ]
    final_snapshot["flows"].remove("C3.O0>C5.I0")
    changed = next(item for item in final_snapshot["components"] if item["id"] == "C1")
    changed["nick"] = "R"
    failed = runner.evaluate_seed_preservation(fixture, seed_evidence, final_snapshot)
    assert failed["status"] == "fail"
    assert failed["violations"] == [
        {"code": "protected_field_changed", "role": "radius_control", "field": "nick"},
        {"code": "protected_component_missing", "role": "reference_b"},
        {"code": "protected_flow_missing", "flow": "T3.O0>T5.I0"},
        {"code": "protected_incident_flows_changed", "role": "reference_a"},
        {"code": "protected_incident_flows_changed", "role": "reference_addition"},
    ]


def _complete_seed_preservation_evidence() -> dict:
    temp_id_map = {f"T{index}": f"C{index}" for index in range(1, 7)}
    components = [
        {"id": "C1", "type": "NumberSlider", "nick": "Radius", "value": {"type": "slider", "val": 8}},
        {"id": "C2", "type": "Component_Circle", "componentGuid": "807b86e3-be8d-4970-92b5-f8cdcb45b06b"},
        {"id": "C3", "type": "NumberSlider", "nick": "Reference A", "value": {"type": "slider", "val": 2}},
        {"id": "C4", "type": "NumberSlider", "nick": "Reference B", "value": {"type": "slider", "val": 3}},
        {"id": "C5", "type": "Component_VariableAddition", "componentGuid": "a0d62394-a118-422d-abb3-6af115c75b25"},
        {"id": "C6", "type": "Panel", "nick": "Reference Result"},
    ]
    flows = ["C1.O0>C2.I1", "C3.O0>C5.I0", "C4.O0>C5.I1", "C5.O0>C6.I0"]
    return {
        "edit": {"success": True, "data": {"edit_summary": {"temp_id_map": temp_id_map}}},
        "snapshot": {"success": True, "data": {"components": components, "flows": flows}},
    }


def test_seed_preservation_rejects_missing_baseline_field():
    runner = _runner()
    fixture = _varied_cohort_protocol()["tasks"]["VP1"]["targetFixture"]
    seed_evidence = _complete_seed_preservation_evidence()
    missing_baseline = json.loads(json.dumps(seed_evidence))
    del missing_baseline["snapshot"]["data"]["components"][1]["componentGuid"]
    with pytest.raises(ValueError, match="seed_preservation_evidence_invalid"):
        runner.evaluate_seed_preservation(
            fixture,
            missing_baseline,
            json.loads(json.dumps(seed_evidence["snapshot"]["data"])),
        )


def test_seed_preservation_withholds_missing_final_field():
    runner = _runner()
    fixture = _varied_cohort_protocol()["tasks"]["VP1"]["targetFixture"]
    seed_evidence = _complete_seed_preservation_evidence()
    missing_final = json.loads(json.dumps(seed_evidence["snapshot"]["data"]))
    del missing_final["components"][1]["componentGuid"]
    assert runner.evaluate_seed_preservation(
        fixture, seed_evidence, missing_final
    ) == {
        "schema": "rook.experiment.seed_preservation:v1",
        "status": "incomplete",
        "violations": [
            {
                "code": "protected_field_unobserved",
                "role": "original_circle",
                "field": "componentGuid",
            }
        ],
    }


def test_varied_cohort_continues_model_failures_but_stops_infrastructure_failures():
    runner = _runner()
    protocol = _varied_cohort_protocol()
    process = {
        "stdoutEof": True,
        "ownedChildPids": [],
        "exitCode": 0,
        "goalContextVerified": True,
        "thinkingLevelVerified": True,
        "limitBreach": None,
    }
    outcome = {
        "semanticStatus": "unproven",
        "goalStatus": "active",
        "budgetStatus": "fail",
        "custodyStatus": "pass",
        "actorFinalCheckpointStatus": "fail",
        "evaluationInfrastructureStatus": "pass",
        "process": process,
    }
    assert runner.varied_row_allows_continuation(protocol, outcome)

    budget_kill = json.loads(json.dumps(outcome))
    budget_kill["process"].update(
        {"exitCode": 1, "limitBreach": "provider_token_ceiling"}
    )
    assert runner.varied_row_allows_continuation(protocol, budget_kill)

    for changed in (
        {"stdoutEof": False},
        {"ownedChildPids": [999]},
        {"goalContextVerified": False},
        {"thinkingLevelVerified": False},
        {"exitCode": 1, "limitBreach": None},
    ):
        contaminated = json.loads(json.dumps(outcome))
        contaminated["process"].update(changed)
        assert not runner.varied_row_allows_continuation(protocol, contaminated)

    evaluation_failure = json.loads(json.dumps(outcome))
    evaluation_failure["evaluationInfrastructureStatus"] = "fail"
    assert not runner.varied_row_allows_continuation(protocol, evaluation_failure)


def test_row_telemetry_keeps_observation_and_inference_separate():
    runner = _runner()
    source_events = [
        {"sequence": 0, "target": "gh_library", "result": {"success": True}, "mutation": {"classification": "observational", "commit_status": "none"}},
        {"sequence": 1, "target": "gh_batch_component_info", "result": {"success": False}, "mutation": {"classification": "observational", "commit_status": "none"}},
        {"sequence": 2, "target": "gh_edit", "result": {"success": True}, "mutation": {"classification": "terminal", "commit_status": "committed"}},
        {"sequence": 3, "target": "gh_edit", "exception": {"type": "McpToolError"}, "mutation": {"classification": "observational", "commit_status": "none"}},
        {"sequence": 4, "target": "gh_snapshot", "result": {"success": True}, "mutation": {"classification": "observational", "commit_status": "none"}},
    ]
    prime_events = [
        {"type": "message_end", "timestamp": 10, "message": {"usage": {"input": 100, "output": 20, "totalTokens": 120}}},
        {"type": "message_end", "timestamp": 20, "message": {"usage": {"input": 130, "output": 10, "totalTokens": 140}}},
    ]

    telemetry = runner.summarize_row_telemetry(source_events, prime_events)

    assert telemetry["observed"]["gatewayCalls"] == 5
    assert telemetry["observed"]["discoveryCalls"] == 2
    assert telemetry["observed"]["mutationCalls"] == 2
    assert telemetry["observed"]["committedMutations"] == 1
    assert telemetry["observed"]["firstMutation"] == {
        "sequence": 2,
        "target": "gh_edit",
        "commitStatus": "committed",
    }
    assert telemetry["observed"]["firstCommittedMutation"] == {
        "sequence": 2,
        "target": "gh_edit",
    }
    assert telemetry["observed"]["refusedOrFailedCalls"] == 2
    assert telemetry["observed"]["perTurnUsage"] == [
        {"turn": 1, "timestamp": 10, "inputTokens": 100, "outputTokens": 20, "totalTokens": 120},
        {"turn": 2, "timestamp": 20, "inputTokens": 130, "outputTokens": 10, "totalTokens": 140},
    ]
    assert telemetry["inferred"] == {
        "candidateCorrectionMutations": 0,
        "qualification": "mutation_order_only_not_semantic_correction",
    }
    assert telemetry["unresolved"] == ["first_sufficient_fenced_evidence_turn"]


@pytest.mark.parametrize(
    "alias", ("gh_create_python_script", "gh_create_csharp_script")
)
def test_script_creation_aliases_count_as_first_committed_mutations(alias: str):
    runner = _runner()
    source_events = [
        {
            "sequence": 0,
            "target": "gh_snapshot",
            "result": {"success": True},
            "mutation": {"classification": "observational", "commit_status": "none"},
        },
        {
            "sequence": 1,
            "target": alias,
            "result": {"success": True},
            "mutation": {"classification": "terminal", "commit_status": "committed"},
        },
        {
            "sequence": 2,
            "target": "gh_edit",
            "result": {"success": True},
            "mutation": {"classification": "terminal", "commit_status": "committed"},
        },
    ]

    telemetry = runner.summarize_row_telemetry(source_events, [])

    assert telemetry["observed"]["mutationCalls"] == 2
    assert telemetry["observed"]["committedMutations"] == 2
    assert telemetry["observed"]["firstMutation"] == {
        "sequence": 1,
        "target": alias,
        "commitStatus": "committed",
    }
    assert telemetry["observed"]["firstCommittedMutation"] == {
        "sequence": 1,
        "target": alias,
    }
    assert telemetry["inferred"]["candidateCorrectionMutations"] == 1


def test_first_committed_mutation_does_not_credit_a_refused_attempt():
    runner = _runner()
    source_events = [
        {
            "sequence": 0,
            "target": "gh_create_python_script",
            "result": {"success": False},
            "mutation": {"classification": "observational", "commit_status": "none"},
        },
        {
            "sequence": 1,
            "target": "gh_edit",
            "result": {"success": True},
            "mutation": {"classification": "terminal", "commit_status": "committed"},
        },
    ]

    telemetry = runner.summarize_row_telemetry(source_events, [])

    assert telemetry["observed"]["mutationCalls"] == 2
    assert telemetry["observed"]["firstMutation"] == {
        "sequence": 0,
        "target": "gh_create_python_script",
        "commitStatus": "none",
    }
    assert telemetry["observed"]["firstCommittedMutation"] == {
        "sequence": 1,
        "target": "gh_edit",
    }


def test_prepare_target_stages_the_exact_task_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _varied_cohort_protocol()
    task = protocol["tasks"]["VP1"]
    row_root = tmp_path / "VP1"
    captured: list[str] = []

    def operator_command(_protocol, arguments, **_kwargs):
        captured.extend(arguments)
        fixture_path = Path(arguments[arguments.index("--fixture") + 1])
        assert json.loads(fixture_path.read_text(encoding="utf-8")) == task[
            "targetFixture"
        ]
        output = Path(arguments[arguments.index("--output") + 1])
        output.write_text(
            json.dumps({"task": "VP1", "targetFixtureSha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest().upper()}) + "\n",
            encoding="utf-8",
        )
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(runner, "_operator_command", operator_command)
    target = runner._prepare_target(protocol, task, row_root, 268435457, 123)

    assert captured[0] == "_operator-prepare"
    assert "--fixture" in captured
    assert target["task"] == "VP1"
    assert (row_root / "operator" / "task-fixture.json").is_file()


def test_varied_offline_normalizer_uses_reviewed_source_without_changing_live_path():
    runner = _runner()
    protocol = _varied_cohort_protocol()
    environment = runner.offline_evaluator_environment(protocol, {"PYTHONPATH": "ambient"})

    assert environment["PYTHONPATH"].split(";") == [
        (ROOT / "mcp_server" / "src").as_posix(),
        "ambient",
    ]
    _, live_environment = runner.build_prime_launch(
        protocol,
        task=protocol["tasks"]["VP2"],
        row_root=ROOT,
        target={"processId": 1, "documentSerialNumber": 2},
    )
    assert (ROOT / "mcp_server" / "src").as_posix() not in live_environment[
        "PYTHONPATH"
    ].split(";")


def test_varied_post_actor_evaluation_normalizes_offline_before_live_observation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _varied_cohort_protocol()
    task = protocol["tasks"]["VP2"]
    row_root = tmp_path / "VP2"
    operator = row_root / "operator"
    operator.mkdir(parents=True)
    calls: list[tuple[str, list[str]]] = []

    def offline(_protocol, arguments):
        calls.append(("offline", arguments))
        return types.SimpleNamespace(returncode=0, stderr="")

    def live(_protocol, arguments, **_kwargs):
        calls.append(("live", arguments))
        (operator / "hidden-evaluation.json").write_text(
            json.dumps({"status": "unproven"}) + "\n", encoding="utf-8"
        )
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(runner, "_offline_evaluator_command", offline)
    monkeypatch.setattr(runner, "_operator_command", live)

    status = runner._post_actor_evaluation(
        protocol, task, row_root, {"exitCode": 0}
    )

    assert status == "unproven"
    assert calls[0][0] == "offline"
    assert calls[0][1][0] == "_operator-normalize"
    assert calls[1][0] == "live"
    assert calls[1][1][0] == "_operator-evaluate"
    assert "--presealed" in calls[1][1]


def test_varied_campaign_runs_every_row_after_model_failure_and_seals_each(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _varied_cohort_protocol()
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    evidence_root = tmp_path / "cohort"
    run_tasks: list[str] = []

    monkeypatch.setattr(runner, "validate_evidence_root", lambda path: Path(path))
    monkeypatch.setattr(runner, "run_precontact_verification", lambda *args: {})
    monkeypatch.setattr(runner, "_runtime_custody", lambda *args: {"ok": True})
    monkeypatch.setattr(runner, "_collect_tool_surface", lambda *args: {})
    monkeypatch.setattr(runner, "_run_preflight", lambda *args: {})
    monkeypatch.setattr(
        runner,
        "capture_python_environment_custody",
        lambda protocol: {"roots": {}, "mismatches": []},
    )
    monkeypatch.setattr(runner, "_copy_versioned_inputs", lambda *args: None)
    monkeypatch.setattr(runner, "_write_row_input_custody", lambda *args: None)

    def prepare(_protocol, task, row_root, *_args):
        (row_root / "operator").mkdir(parents=True, exist_ok=True)
        return {"task": task["id"]}

    def run(_protocol, task, _row_root, _target):
        run_tasks.append(task["id"])
        return {
            "stdoutEof": True,
            "ownedChildPids": [],
            "exitCode": 0,
            "goalContextVerified": True,
            "thinkingLevelVerified": True,
            "limitBreach": None,
        }

    monkeypatch.setattr(runner, "_prepare_target", prepare)
    monkeypatch.setattr(runner, "_run_prime_row", run)
    monkeypatch.setattr(
        runner,
        "_row_outcome",
        lambda *args: {
            "semanticStatus": "unproven",
            "goalStatus": "active",
            "budgetStatus": "fail",
            "custodyStatus": "pass",
                "actorFinalCheckpointStatus": "fail",
                "evaluationInfrastructureStatus": "pass",
        },
    )

    result = runner.run_campaign(protocol_path, evidence_root, 268435457, None)

    assert run_tasks == ["VP1", "VP2", "VP3"]
    assert result["status"] == "complete"
    for task_id in protocol["executionOrder"]:
        row = evidence_root / task_id
        assert runner.verify_evidence_manifest(
            row, row / "evidence-manifest.json"
        )["mismatches"] == []


def test_varied_campaign_stops_before_next_target_on_process_custody_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _varied_cohort_protocol()
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol) + "\n", encoding="utf-8")
    evidence_root = tmp_path / "cohort"
    prepared: list[str] = []

    monkeypatch.setattr(runner, "validate_evidence_root", lambda path: Path(path))
    monkeypatch.setattr(runner, "run_precontact_verification", lambda *args: {})
    monkeypatch.setattr(runner, "_runtime_custody", lambda *args: {"ok": True})
    monkeypatch.setattr(runner, "_collect_tool_surface", lambda *args: {})
    monkeypatch.setattr(runner, "_run_preflight", lambda *args: {})
    monkeypatch.setattr(
        runner,
        "capture_python_environment_custody",
        lambda protocol: {"roots": {}, "mismatches": []},
    )
    monkeypatch.setattr(runner, "_copy_versioned_inputs", lambda *args: None)
    monkeypatch.setattr(runner, "_write_row_input_custody", lambda *args: None)

    def prepare(_protocol, task, row_root, *_args):
        prepared.append(task["id"])
        (row_root / "operator").mkdir(parents=True, exist_ok=True)
        return {"task": task["id"]}

    process = {
        "stdoutEof": False,
        "ownedChildPids": [],
        "exitCode": 1,
        "goalContextVerified": True,
        "thinkingLevelVerified": True,
        "limitBreach": None,
    }
    monkeypatch.setattr(runner, "_prepare_target", prepare)
    monkeypatch.setattr(runner, "_run_prime_row", lambda *args: process)
    monkeypatch.setattr(
        runner,
        "_row_outcome",
        lambda *args: {
            "semanticStatus": "incomplete",
            "goalStatus": "active",
            "budgetStatus": "pass",
                "custodyStatus": "fail",
                "evaluationInfrastructureStatus": "pass",
        },
    )

    with pytest.raises(RuntimeError, match="process_custody_failure:VP1"):
        runner.run_campaign(protocol_path, evidence_root, 268435457, None)

    assert prepared == ["VP1"]


def test_v6_protocol_freezes_one_low_thinking_receipt_fenced_t4_confirmation(
    tmp_path: Path,
):
    runner = _runner()
    protocol = _v6_protocol()

    assert runner.validate_protocol(protocol) is protocol
    command, _ = runner.build_prime_launch(
        protocol,
        task=protocol["tasks"]["T4"],
        row_root=tmp_path,
        target={"processId": 123, "documentSerialNumber": 456},
    )
    assert command[command.index("--thinking") + 1] == "low"
    assert protocol["executionOrder"] == ["T4"]


def test_frozen_v6_changes_only_focused_scope_and_versioned_instructions():
    runner = _runner()
    v5 = json.loads(V5_PROTOCOL_PATH.read_text(encoding="utf-8"))
    v6 = json.loads(V6_PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert runner.validate_protocol(v6) is v6
    assert v6["focusedRetest"] == _v6_protocol()["focusedRetest"]
    assert v6["tasks"] == v5["tasks"]
    assert v6["prime"] == v5["prime"]
    assert v6["limits"] == v5["limits"]
    assert v6["versionedInputs"]["skillSha256"] == BASELINE_SKILL_SHA256
    assert v6["versionedInputs"]["checkpointSha256"] == hashlib.sha256(
        CHECKPOINT_PATH.read_bytes()
    ).hexdigest().upper()

    normalized = json.loads(json.dumps(v6))
    normalized["schema"] = v5["schema"]
    normalized["purpose"] = v5["purpose"]
    normalized["versionedInputs"]["skillSha256"] = v5["versionedInputs"][
        "skillSha256"
    ]
    normalized["versionedInputs"]["checkpointSha256"] = v5[
        "versionedInputs"
    ]["checkpointSha256"]
    normalized["focusedRetest"] = v5["focusedRetest"]
    assert normalized == v5


def test_skill_and_checkpoint_require_one_receipt_fenced_final_observation():
    skill = SKILL_PATH.read_text(encoding="utf-8")
    checkpoint = CHECKPOINT_PATH.read_text(encoding="utf-8")

    for text in (skill, checkpoint):
        assert "gh_wait_for_solve_readiness" in text
        assert "readiness_receipt_id" in text
        assert "receipt-fenced" in text
    normalized_skill = " ".join(skill.split())
    assert "Do not substitute an unfenced snapshot or `gh_status`" in normalized_skill
    assert "If the wait or fenced snapshot refuses, report incomplete" in normalized_skill


def test_actor_final_checkpoint_requires_wait_snapshot_order_and_no_later_call():
    runner = _runner()
    receipt = {
        "receipt_id": "receipt-1",
        "status": "pending",
        "mutation_epoch": 7,
    }
    events = [
        {
            "sequence": 1,
            "target": "gh_edit",
            "arguments": {"epoch": 6},
            "dispatch": {"status": "dispatched"},
            "mutation": {
                "classification": "terminal",
                "commit_status": "committed",
                "solve_readiness_receipt": receipt,
            },
            "result": {"success": True, "data": {}},
        },
        {
            "sequence": 2,
            "target": "gh_wait_for_solve_readiness",
            "arguments": {"readiness_receipt_id": "receipt-1"},
            "dispatch": {"status": "dispatched"},
            "mutation": {"classification": "observational"},
            "result": {
                "success": True,
                "data": {
                    "wait_status": "ready",
                    "receipt": receipt | {"status": "ready"},
                },
            },
        },
        {
            "sequence": 3,
            "target": "gh_snapshot",
            "arguments": {
                "include_data": True,
                "readiness_receipt_id": "receipt-1",
            },
            "dispatch": {"status": "dispatched"},
            "mutation": {"classification": "observational"},
            "result": {"success": True, "data": {"epoch": 21}},
        },
    ]

    assert runner.audit_actor_final_checkpoint(events) == {
        "schema": "rook.experiment.actor_final_checkpoint:v1",
        "status": "pass",
        "reason": None,
        "receiptId": "receipt-1",
        "mutationSequence": 1,
        "waitSequence": 2,
        "snapshotSequence": 3,
        "gatewayEventCount": 3,
    }

    for changed, reason in (
        (events[:1] + events[2:], "final_receipt_wait_missing"),
        (
            events[:2]
            + [events[2] | {"arguments": {"include_data": True}}],
            "final_receipt_fenced_snapshot_missing",
        ),
        (
            events
            + [
                {
                    "sequence": 4,
                    "target": "gh_status",
                    "arguments": {},
                    "result": {"success": True, "data": {}},
                }
            ],
            "later_gateway_call",
        ),
    ):
        assert runner.audit_actor_final_checkpoint(changed)["reason"] == reason


def test_v5_protocol_freezes_one_low_thinking_t4_retest(tmp_path: Path):
    runner = _runner()
    protocol = _v5_protocol()

    assert runner.validate_protocol(protocol) is protocol
    command, _ = runner.build_prime_launch(
        protocol,
        task=protocol["tasks"]["T4"],
        row_root=tmp_path,
        target={"processId": 123, "documentSerialNumber": 456},
    )
    assert command[command.index("--thinking") + 1] == "low"
    assert protocol["smokeTask"] == "T4"
    assert protocol["executionOrder"] == ["T4"]

    expanded = json.loads(json.dumps(protocol))
    expanded["executionOrder"] = ["T4", "T2"]
    expanded["tasks"]["T2"] = _v4_protocol()["tasks"]["T2"]
    with pytest.raises(ValueError, match="focused_retest_invalid"):
        runner.validate_protocol(expanded)


def test_frozen_v5_changes_only_focused_scope_skill_and_success_contract():
    runner = _runner()
    v4 = json.loads(V4_PROTOCOL_PATH.read_text(encoding="utf-8"))
    v5 = json.loads(V5_PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert runner.validate_protocol(v5) is v5
    assert v5["focusedRetest"] == _v5_protocol()["focusedRetest"]
    assert v5["tasks"]["T4"]["prompt"] == v4["tasks"]["T4"]["prompt"]
    assert v5["versionedInputs"]["skillSha256"] == (
        "9656C6456E7AC318FA825D87FC7DE7BA2756804426749CBC9C16805289CC3D6D"
    )

    normalized = json.loads(json.dumps(v5))
    normalized["schema"] = v4["schema"]
    normalized["purpose"] = v4["purpose"]
    normalized["smokeTask"] = v4["smokeTask"]
    normalized["executionOrder"] = v4["executionOrder"]
    normalized["tasks"] = v4["tasks"]
    normalized["versionedInputs"]["skillSha256"] = v4["versionedInputs"][
        "skillSha256"
    ]
    del normalized["focusedRetest"]
    assert normalized == v4


def test_skill_requires_decision_relevant_uncertainty_before_another_observation():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert (
        "make another observation only to resolve a named material uncertainty "
        "whose outcome could change the completion decision"
    ) in skill
    assert (
        "Greater precision, repeated confirmation, or reassurance such as being "
        '"100% sure" is not material investigation.'
    ) in skill


def test_v4_protocol_freezes_low_thinking_and_three_row_screening_order(tmp_path: Path):
    runner = _runner()
    protocol = _v4_protocol()

    assert runner.validate_protocol(protocol) is protocol
    command, _ = runner.build_prime_launch(
        protocol,
        task=protocol["tasks"]["T3"],
        row_root=tmp_path,
        target={"processId": 123, "documentSerialNumber": 456},
    )
    assert command[command.index("--thinking") + 1] == "low"
    assert protocol["executionOrder"] == ["T3", "T2", "T4"]

    missing = json.loads(json.dumps(protocol))
    del missing["precontactVerification"]
    with pytest.raises(ValueError, match="precontact_verification_invalid"):
        runner.validate_protocol(missing)

    wrong_level = json.loads(json.dumps(protocol))
    wrong_level["prime"]["thinkingLevel"] = "medium"
    with pytest.raises(ValueError, match="thinking_level_invalid"):
        runner.validate_protocol(wrong_level)


def test_frozen_v4_protocol_changes_only_screening_order_thinking_and_test_custody():
    runner = _runner()
    v3 = _protocol()
    v4 = json.loads(V4_PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert runner.validate_protocol(v4) is v4
    assert v4["prime"]["thinkingLevel"] == "low"
    assert v4["executionOrder"] == ["T3", "T2", "T4"]
    assert {
        task_id: v4["tasks"][task_id]["prompt"] for task_id in v4["executionOrder"]
    } == {
        task_id: v3["tasks"][task_id]["prompt"] for task_id in v4["executionOrder"]
    }

    normalized = json.loads(json.dumps(v4))
    normalized["schema"] = v3["schema"]
    normalized["purpose"] = v3["purpose"]
    normalized["executionOrder"] = v3["executionOrder"]
    normalized["prime"]["thinkingLevel"] = v3["prime"]["thinkingLevel"]
    normalized["tasks"]["T1"] = v3["tasks"]["T1"]
    del normalized["precontactVerification"]
    assert normalized == v3


def test_precontact_verification_retains_complete_command_and_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _v4_protocol()
    observed: dict = {}

    def completed(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return types.SimpleNamespace(
            returncode=0,
            stdout=b"141 passed, 11 warnings in 7.00s\r\n",
            stderr=b"",
        )

    monkeypatch.setattr(runner.subprocess, "run", completed)

    record = runner.run_precontact_verification(protocol, tmp_path)

    assert observed["command"] == [
        protocol["precontactVerification"]["pythonPath"],
        *protocol["precontactVerification"]["arguments"],
    ]
    assert observed["kwargs"]["cwd"] == runner.ROOT
    assert (tmp_path / "precontact-tests.stdout.txt").read_bytes() == (
        b"141 passed, 11 warnings in 7.00s\r\n"
    )
    assert (tmp_path / "precontact-tests.stderr.txt").read_bytes() == b""
    assert record["exitCode"] == 0
    assert record["stdoutSha256"] == hashlib.sha256(
        b"141 passed, 11 warnings in 7.00s\r\n"
    ).hexdigest().upper()


def test_precontact_verification_failure_is_retained_and_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _v4_protocol()
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=1, stdout=b"1 failed\n", stderr=b"failure details\n"
        ),
    )

    with pytest.raises(RuntimeError, match="precontact_verification_failed:1"):
        runner.run_precontact_verification(protocol, tmp_path)

    assert (tmp_path / "precontact-tests.stdout.txt").read_bytes() == b"1 failed\n"
    assert json.loads((tmp_path / "precontact-verification.json").read_text())[
        "exitCode"
    ] == 1


def test_effective_thinking_level_is_read_from_the_retained_prime_session(
    tmp_path: Path,
):
    runner = _runner()
    sessions = tmp_path / "agent" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "session.jsonl").write_text(
        json.dumps({"type": "thinking_level_change", "thinkingLevel": "low"})
        + "\n",
        encoding="utf-8",
    )

    assert runner.prime_session_proves_thinking_level(tmp_path, "low")
    assert not runner.prime_session_proves_thinking_level(tmp_path, "medium")


def test_v4_row_custody_requires_effective_low_thinking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _v4_protocol()
    monkeypatch.setattr(runner, "_post_actor_evaluation", lambda *args: "pass")
    monkeypatch.setattr(runner, "_goal_status", lambda *args: "complete")
    process = {
        "limitBreach": None,
        "goalContextVerified": True,
        "providerReportedTokens": 100,
        "gatewayEvents": 1,
        "elapsedSeconds": 1.0,
        "stdoutEof": True,
        "ownedChildPids": [],
        "exitCode": 0,
        "thinkingLevelVerified": False,
    }

    assert runner._row_outcome(
        protocol, protocol["tasks"]["T3"], tmp_path, process
    )["custodyStatus"] == "fail"
    process["thinkingLevelVerified"] = True
    assert runner._row_outcome(
        protocol, protocol["tasks"]["T3"], tmp_path, process
    )["custodyStatus"] == "pass"


def test_v5_row_custody_requires_effective_low_thinking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _v5_protocol()
    monkeypatch.setattr(runner, "_post_actor_evaluation", lambda *args: "unproven")
    monkeypatch.setattr(runner, "_goal_status", lambda *args: "complete")
    process = {
        "limitBreach": None,
        "goalContextVerified": True,
        "providerReportedTokens": 100,
        "gatewayEvents": 1,
        "elapsedSeconds": 1.0,
        "stdoutEof": True,
        "ownedChildPids": [],
        "exitCode": 0,
        "thinkingLevelVerified": False,
    }

    assert runner._row_outcome(
        protocol, protocol["tasks"]["T4"], tmp_path, process
    )["custodyStatus"] == "fail"


def test_v6_row_custody_refuses_an_unfenced_actor_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    runner = _runner()
    protocol = _v6_protocol()
    operator = tmp_path / "operator"
    operator.mkdir()
    terminal = {
        "sequence": 1,
        "target": "gh_edit",
        "arguments": {"epoch": 6},
        "mutation": {
            "classification": "terminal",
            "commit_status": "committed",
            "solve_readiness_receipt": {
                "receipt_id": "receipt-1",
                "status": "pending",
            },
        },
        "result": {"success": True, "data": {}},
    }
    (operator / "source.jsonl").write_text(
        json.dumps({"schema": "header"}) + "\n" + json.dumps(terminal) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "_post_actor_evaluation", lambda *args: "unproven")
    monkeypatch.setattr(runner, "_goal_status", lambda *args: "complete")
    process = {
        "limitBreach": None,
        "goalContextVerified": True,
        "providerReportedTokens": 100,
        "gatewayEvents": 1,
        "elapsedSeconds": 1.0,
        "stdoutEof": True,
        "ownedChildPids": [],
        "exitCode": 0,
        "thinkingLevelVerified": True,
    }

    outcome = runner._row_outcome(
        protocol, protocol["tasks"]["T4"], tmp_path, process
    )

    assert outcome["custodyStatus"] == "fail"
    assert outcome["actorFinalCheckpointStatus"] == "fail"
    assert json.loads((operator / "actor-final-checkpoint.json").read_text())[
        "reason"
    ] == "final_receipt_wait_missing"


def test_campaign_completion_uses_the_frozen_row_count():
    runner = _runner()
    protocol = _v4_protocol()

    assert runner.campaign_completion_status(
        protocol, {task_id: {} for task_id in protocol["executionOrder"]}
    ) == "complete"
    assert runner.campaign_completion_status(protocol, {"T3": {}}) == (
        "stopped_at_smoke_gate"
    )


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
    versioned = json.loads(V6_PROTOCOL_PATH.read_text(encoding="utf-8"))[
        "versionedInputs"
    ]

    assert versioned["skillSha256"] == BASELINE_SKILL_SHA256
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


def _readiness_snapshot_refusal_event() -> dict:
    return {
        "arguments": {
            "include_data": False,
            "readiness_receipt_id": "ca581c2dbaf8246a8ccbc1100965ebda",
        },
        "dispatch": {"status": "dispatched", "target_call_count": 1},
        "exception": None,
        "ingress": "canonical_gateway",
        "mutation": {
            "classification": "unknown",
            "commit_evidence": None,
            "commit_status": "unknown",
            "solve_readiness_receipt": None,
        },
        "result": {
            "data": {"error": "readiness_snapshot_request_invalid"},
            "success": False,
        },
        "sequence": 71,
        "target": "gh_snapshot",
    }


def test_exact_readiness_snapshot_refusal_gets_offline_no_commit_projection():
    runner = _runner()
    event = _readiness_snapshot_refusal_event()
    trace = {"events": [event], "schema": "trace", "source_closure": {}}

    normalized = runner.normalize_known_readonly_refusals(trace)

    assert normalized["events"][0]["mutation"] == {
        "classification": "observational",
        "commit_evidence": None,
        "commit_status": "none",
        "solve_readiness_receipt": None,
    }
    assert trace["events"][0] == event


@pytest.mark.parametrize(
    "alter",
    [
        lambda event: event | {"target": "gh_status"},
        lambda event: event
        | {"arguments": event["arguments"] | {"max_preview_items": 20}},
        lambda event: event
        | {
            "result": {
                "success": False,
                "data": {
                    "error": "readiness_snapshot_request_invalid",
                    "message": "extra",
                },
            }
        },
    ],
)
def test_near_readiness_snapshot_refusals_remain_fail_closed(alter):
    runner = _runner()
    event = alter(_readiness_snapshot_refusal_event())
    trace = {"events": [event], "schema": "trace", "source_closure": {}}

    assert runner.normalize_known_readonly_refusals(trace) == trace


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


def test_prime_budget_may_reserve_final_response_inside_provider_ceiling():
    runner = _runner()
    protocol = _protocol()
    protocol["limits"]["primeGoalTokenBudget"] = 1_900_000

    assert runner.validate_protocol(protocol) is protocol
    limits = runner.CampaignLimits.from_mapping(protocol["limits"])
    assert limits.prime_goal_tokens == 1_900_000
    assert limits.provider_tokens == 2_000_000


def test_prime_budget_cannot_exceed_provider_ceiling():
    runner = _runner()
    protocol = _protocol()
    protocol["limits"]["primeGoalTokenBudget"] = 2_000_001

    with pytest.raises(ValueError, match="goal_budget_exceeds_provider_ceiling"):
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
        lambda *args: (_ for _ in ()).throw(RuntimeError("custody_gate_failed")),
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
    monkeypatch.setattr(runner, "_runtime_custody", lambda *args: {"ok": True})
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
    monkeypatch.setattr(runner, "_runtime_custody", lambda *args: {"ok": True})
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
