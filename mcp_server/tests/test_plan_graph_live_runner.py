from __future__ import annotations

import ast
import asyncio
from pathlib import Path

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    LiveProducerRecord,
    Mismatch,
    build_live_producer_record,
    run_and_record_live_producer_node,
)
from rook.learning.plan_graph import NodeEvidence, PlanGraph, PlanGraphNode


def _evidence(tool_status="success", verified=True, artifact_status="usable", guid="guid-1"):
    return NodeEvidence(
        tool_status=tool_status,
        verified=verified,
        receipt={"artifact_status": artifact_status} if artifact_status else None,
        repair_anchor={"component_guid": guid} if guid else None,
    )


def _node(node_id="create", status="succeeded", evidence=None, params=None):
    meta = {}
    if params is not None:
        meta[EXECUTION_PARAMS_KEY] = params
    return PlanGraphNode(
        id=node_id, intent="create", metadata=meta, status=status, evidence=evidence
    )


def _result(applied, node_id="create", tool_name="gh_create_script",
            outcome_status="succeeded", reason=None, nodes=None):
    graph = PlanGraph(nodes=nodes if nodes is not None else {})
    return LiveProducerResult(
        graph=graph, applied=applied, node_id=node_id,
        tool_name=tool_name, outcome_status=outcome_status, reason=reason,
    )


class _Undeepcopyable:
    def __deepcopy__(self, memo):
        raise RuntimeError("cannot deepcopy")


class _FakeRunner:
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append((graph, node_id))
        return self._result


def test_clean_applied_record():
    node = _node(status="succeeded",
                 evidence=_evidence(verified=True, artifact_status="usable", guid="g1"),
                 params={"language": "csharp", "code": "A=1;"})
    rec = build_live_producer_record(_result(True, nodes={"create": node}))
    assert rec.applied is True
    assert rec.outcome_status == "succeeded"
    assert rec.node_status == "succeeded"
    assert rec.tool_status == "success"
    assert rec.verified is True
    assert rec.artifact_status == "usable"
    assert rec.repair_anchor_guid == "g1"
    assert rec.tool_name == "gh_create_script"
    assert rec.declared_params == {"language": "csharp", "code": "A=1;"}
    assert rec.evaluated is False and rec.passed is None and rec.mismatches == ()


def test_broken_applied_record():
    node = _node(status="succeeded",
                 evidence=_evidence(tool_status="failed", verified=False,
                                    artifact_status="created_with_errors", guid="g2"))
    rec = build_live_producer_record(_result(True, nodes={"create": node}))
    assert rec.verified is False
    assert rec.artifact_status == "created_with_errors"
    assert rec.outcome_status == "succeeded"
    assert rec.node_status == "succeeded"
    # The two-successes seam, recorded: tool failed functionally while the
    # producer node succeeded.
    assert rec.tool_status == "failed"


def test_not_applied_unknown_node_record():
    rec = build_live_producer_record(
        _result(False, node_id="missing", tool_name=None,
                outcome_status=None, reason="unknown_node", nodes={})
    )
    assert rec.applied is False
    assert rec.reason == "unknown_node"
    assert rec.node_status is None
    assert rec.tool_status is None
    assert rec.verified is None
    assert rec.artifact_status is None
    assert rec.repair_anchor_guid is None
    assert rec.declared_params is None


def test_not_applied_node_present_evidence_none():
    node = _node(status="pending", evidence=None,
                 params={"language": "csharp", "code": "x"})
    rec = build_live_producer_record(
        _result(False, outcome_status=None, reason="node_not_runnable",
                nodes={"create": node})
    )
    assert rec.node_status == "pending"  # graph-native read
    assert rec.tool_status is None
    assert rec.verified is None
    assert rec.artifact_status is None
    assert rec.repair_anchor_guid is None
    assert rec.reason == "node_not_runnable"
    assert rec.declared_params == {"language": "csharp", "code": "x"}


def test_not_applied_params_copy_failed_declared_params_none():
    node = _node(status="ready", evidence=None, params={"bad": _Undeepcopyable()})
    rec = build_live_producer_record(
        _result(False, outcome_status=None, reason="params_copy_failed",
                nodes={"create": node})
    )
    assert rec.reason == "params_copy_failed"
    assert rec.declared_params is None  # deepcopy failed -> None, no crash
    assert rec.node_status == "ready"


def test_non_mapping_execution_params_declared_params_none():
    node = _node(status="ready", evidence=None, params=[("language", "csharp")])
    rec = build_live_producer_record(
        _result(False, outcome_status=None, reason="execution_params_invalid",
                nodes={"create": node})
    )
    assert rec.declared_params is None
    assert rec.reason == "execution_params_invalid"


def test_eval_no_expectation():
    node = _node(evidence=_evidence())
    rec = build_live_producer_record(_result(True, nodes={"create": node}), None)
    assert rec.evaluated is False
    assert rec.passed is None
    assert rec.mismatches == ()


def test_eval_all_none_expectation_vacuous_pass():
    node = _node(evidence=_evidence())
    rec = build_live_producer_record(_result(True, nodes={"create": node}),
                                     LiveProducerExpectation())
    assert rec.evaluated is True
    assert rec.passed is True
    assert rec.mismatches == ()


def test_eval_single_mismatch():
    node = _node(status="succeeded", evidence=_evidence(verified=True, artifact_status="usable"))
    rec = build_live_producer_record(
        _result(True, outcome_status="succeeded", nodes={"create": node}),
        LiveProducerExpectation(verified=False),
    )
    assert rec.evaluated is True
    assert rec.passed is False
    assert rec.mismatches == (Mismatch(field="verified", expected=False, observed=True),)


def test_eval_multiple_mismatches():
    # _evidence() default tool_status is "success"; expect "failed" -> mismatch.
    node = _node(status="succeeded", evidence=_evidence(verified=True, artifact_status="usable"))
    rec = build_live_producer_record(
        _result(True, outcome_status="succeeded", nodes={"create": node}),
        LiveProducerExpectation(
            verified=False, artifact_status="created_with_errors", tool_status="failed"
        ),
    )
    assert rec.passed is False
    assert {m.field for m in rec.mismatches} == {"verified", "artifact_status", "tool_status"}


def test_declared_params_deepcopy_isolation():
    params = {"nested": {"k": "v"}}
    node = _node(evidence=_evidence(), params=params)
    rec = build_live_producer_record(_result(True, nodes={"create": node}))
    rec.declared_params["nested"]["k"] = "MUTATED"
    assert params["nested"]["k"] == "v"  # graph metadata untouched


def test_run_and_record_wrapper_uses_runner_result():
    node = _node(status="succeeded", evidence=_evidence(verified=True, artifact_status="usable"))
    g = PlanGraph(nodes={"create": node})
    result = LiveProducerResult(graph=g, applied=True, node_id="create",
                                tool_name="gh_create_script", outcome_status="succeeded", reason=None)
    runner = _FakeRunner(result)
    exp = LiveProducerExpectation(outcome_status="succeeded", node_status="succeeded",
                                  verified=True, artifact_status="usable")
    rec = asyncio.run(run_and_record_live_producer_node(runner, g, "create", exp))
    assert runner.calls == [(g, "create")]
    assert rec.evaluated is True and rec.passed is True and rec.mismatches == ()
    assert rec.artifact_status == "usable"
    assert isinstance(rec, LiveProducerRecord)


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_runner_module_import_boundary():
    # Repo-root-relative path -> run from repo root (the focused gate does).
    imports = _direct_import_modules(
        "mcp_server/src/rook/agent/plan_graph_live_runner.py"
    )
    # Consumes the live kernel for the type + key, nothing heavier.
    assert "rook.agent.plan_graph_live" in imports
    # Must NOT couple back into the agent runtime / dispatcher / server / chat.
    assert "rook.agent.base_agent" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.server" not in imports
    assert "rook.agent.chat.chat_runner" not in imports
    assert "rook.agent.plan_graph_live_dispatch" not in imports
