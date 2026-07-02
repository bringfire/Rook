#!/usr/bin/env python
"""LM5K first worker model probe — evidence harness, never a CI gate.

Runs the golden repair-workflow envelope against a three-slot model panel
through the production LiteLLMWorkerTransport and the LM5J adapter, then
evaluates loaded responses through the LM5B/C/D/F spine. Writes evidence
artifacts to a gitignored probe_runs/ directory.

Doctrine: probe results are evidence, not pass/fail. See
docs/superpowers/specs/2026-07-02-lm5k-first-worker-model-probe-design.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SLOTS = ("local", "cheap", "ceiling")
SLOT_LABELS = {
    "local": "local_worker_candidate",
    "cheap": "cheap_cloud_worker_candidate",
    "ceiling": "ceiling_worker_candidate",
}
ENV_VARS = {
    "local": "ROOK_PROBE_LOCAL_WORKER",
    "cheap": "ROOK_PROBE_CHEAP_CLOUD_WORKER",
    "ceiling": "ROOK_PROBE_CEILING_WORKER",
}
GENERATION_PARAMS = {"temperature": 0}
DEFAULT_ATTEMPTS = 5
SCENARIO_WORKFLOW_ID = "lm5k_first_probe"

_LOCAL_PREFIXES = ("ollama_chat/", "ollama/")


def parse_candidate_spec(spec: str) -> tuple[str, str | None]:
    """'model[@api_base]' -> (model, api_base or None)."""
    model, sep, api_base = spec.partition("@")
    if not model:
        raise ValueError(f"invalid candidate spec: {spec!r}")
    return model, (api_base if sep and api_base else None)


def profile_inferred_local(
    worker_model: str, profile_api_base: str | None
) -> tuple[str, str | None] | None:
    """Safe profile inference for the LOCAL slot only (spec 4.1 rule 3)."""
    if worker_model.startswith(_LOCAL_PREFIXES):
        return worker_model, profile_api_base
    if worker_model.startswith("openai/") and profile_api_base:
        return worker_model, profile_api_base
    return None


def resolve_slot(
    slot: str,
    cli_value: str | None,
    env_value: str | None,
    profile_worker: str,
    profile_api_base: str | None,
    skipped: bool,
) -> dict:
    """Resolve one panel slot. status None means resolved-and-runnable."""
    base = {"slot": slot, "label": SLOT_LABELS[slot]}
    if skipped:
        return {**base, "model": None, "api_base": None,
                "source": "skip", "status": "skipped"}
    if cli_value:
        model, api_base = parse_candidate_spec(cli_value)
        return {**base, "model": model, "api_base": api_base,
                "source": "cli", "status": None}
    if env_value:
        model, api_base = parse_candidate_spec(env_value)
        return {**base, "model": model, "api_base": api_base,
                "source": "env", "status": None}
    if slot == "local":
        inferred = profile_inferred_local(profile_worker, profile_api_base)
        if inferred is not None:
            model, api_base = inferred
            return {**base, "model": model, "api_base": api_base,
                    "source": "profile", "status": None}
    return {**base, "model": None, "api_base": None,
            "source": "none", "status": "unavailable"}


def classify_candidate_status(adapter_statuses: list) -> str:
    """For an attempted candidate: transport_error iff ALL attempts were.

    An attempted candidate has at least one attempt by definition —
    all([]) is vacuously true and would fabricate transport_error from
    zero evidence, so empty input is a caller error.
    """
    if not adapter_statuses:
        raise ValueError("attempted candidate requires at least one attempt")
    if all(status == "transport_error" for status in adapter_statuses):
        return "transport_error"
    return "ran"


def attempt_metrics(attempt: Mapping[str, Any]) -> tuple[bool, bool]:
    """(strict_loadable, spine_passed) for one attempt record."""
    strict = attempt["adapter_status"] == "response_loaded"
    spine = strict and attempt.get("evaluation_passed") is True
    return strict, spine


def build_probe_context():
    """Golden scenario: the compiled repair workflow, per LM5J's integration
    test, with this probe's workflow_id."""
    import copy

    from rook.agent.local_worker_turn_context import (
        WorkerAllowedAction,
        WorkerKnowledgePacket,
        build_local_worker_turn_context,
    )
    from rook.agent.plan_graph_workflow_contract import (
        BindStepSpec,
        ExpectedNodeRef,
        InitialNodeParams,
        ProducerStepSpec,
        RookWorkflowContract,
        VerifierStepSpec,
        WorkflowNodeRule,
        WorkflowTemplateRef,
        compile_workflow_contract,
    )

    contract = RookWorkflowContract(
        workflow_id=SCENARIO_WORKFLOW_ID,
        template=WorkflowTemplateRef(
            descriptor={
                "domain": "grasshopper",
                "operation": "create_verify_repair_verify",
                "language": "csharp",
            },
            expected_template_id="gh_csharp_create_verify_repair_verify",
        ),
        initial_params=(
            InitialNodeParams(
                node_id="create_script",
                execution_params={
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM5KFirstProbe",
                    "x": 350,
                    "y": 1420,
                },
            ),
        ),
        expected_refs=(
            ExpectedNodeRef(
                node_id="create_script",
                execution_ref="gh_create_csharp_script:v1",
            ),
            ExpectedNodeRef(
                node_id="repair_same_component",
                execution_ref="gh_update_script:v1",
            ),
        ),
        rules=(
            WorkflowNodeRule(
                node_id="create_script",
                steps_by_seen_count=(ProducerStepSpec(node_id="create_script"),),
            ),
            WorkflowNodeRule(
                node_id="verify_create",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_create",
                        source_node_id="create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                node_id="repair_same_component",
                steps_by_seen_count=(
                    BindStepSpec(
                        node_id="repair_same_component",
                        base_params={
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        bindings={"guid": ("repair_anchor", "component_guid")},
                    ),
                    ProducerStepSpec(node_id="repair_same_component"),
                ),
            ),
            WorkflowNodeRule(
                node_id="verify_repair",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_repair",
                        source_node_id="repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=("done",),
        max_steps=6,
        metadata={"trace": {"slice": "LM5K"}},
    )
    scaffold = compile_workflow_contract(contract)
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts["repair_anchor"] = {"component_guid": "component-123"}
    graph.memory.facts["component_guid"] = "component-123"
    return build_local_worker_turn_context(
        scaffold,
        graph,
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script components use body-style code",
                content={"source": "probe fixture", "trust": "high"},
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={"type": "object", "required": ["code", "mode"]},
            ),
        ),
    )


def _default_transport_factory(resolution: Mapping[str, Any]):
    from rook.agent.local_worker_model_transport import LiteLLMWorkerTransport

    return LiteLLMWorkerTransport(
        model=resolution["model"],
        profile_api_base=resolution["api_base"],
        generation_params=GENERATION_PARAMS,
    )


def run_candidate(
    resolution: Mapping[str, Any],
    attempts: int,
    run_dir: Path,
    capture_raw: bool,
    transport_factory=None,
) -> dict:
    """Run N attempts for one resolved candidate. Returns the candidate
    summary; appends one line per attempt to run_dir/attempts.jsonl."""
    from rook.agent.local_worker_adapter import run_local_worker_adapter
    from rook.agent.local_worker_scenario_evaluation import (
        LocalWorkerScenarioExpectation,
        evaluate_local_worker_scenario_result,
    )
    from rook.agent.local_worker_turn_harness import run_local_worker_turn
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    factory = transport_factory or _default_transport_factory
    transport = factory(resolution)
    context = build_probe_context()

    schema_versions = _schema_versions()
    adapter_statuses: list = []
    strict_count = 0
    spine_count = 0
    attempts_path = run_dir / "attempts.jsonl"

    for index in range(attempts):
        payload = dict(render_local_worker_turn_request_payload(context))
        record = run_local_worker_adapter(payload, transport)
        adapter_statuses.append(record.status)

        harness_status = None
        disposition = None
        evaluation_passed = None
        if record.status == "response_loaded":
            harness_record = run_local_worker_turn(
                context, lambda received: record.response
            )
            harness_status = harness_record.status
            disposition = (
                harness_record.disposition.disposition
                if harness_record.disposition is not None
                else None
            )
            result = evaluate_local_worker_scenario_result(
                LocalWorkerScenarioExpectation(
                    scenario_id="lm5k_first_probe_golden",
                    category="live_probe",
                    expected_status="completed",
                    expected_disposition="candidate_action_request",
                    expected_attempt_valid=True,
                    expected_action_id="draft_repair_params",
                    expected_response_kind="action_request",
                    expected_workflow_id=context.workflow.workflow_id,
                    expected_contract_fingerprint=(
                        context.workflow.contract_fingerprint
                    ),
                ),
                harness_record,
            )
            evaluation_passed = result.passed

        captured_raw_path = None
        raw_output = getattr(transport, "last_raw_output", None)
        if capture_raw and isinstance(raw_output, str):
            raw_dir = run_dir / "raw"
            raw_dir.mkdir(exist_ok=True)
            raw_file = raw_dir / f"{resolution['slot']}-{index}.txt"
            raw_file.write_text(raw_output, encoding="utf-8")
            captured_raw_path = raw_file.relative_to(run_dir).as_posix()

        info = getattr(transport, "last_call_info", None)
        attempt = {
            "run_id": run_dir.name,
            "candidate_slot": resolution["label"],
            "resolved_model": resolution["model"],
            "resolution_source": resolution["source"],
            "attempt_index": index,
            "adapter_status": record.status,
            "failure_reason": record.failure_reason,
            "raw_output_excerpt": record.raw_output_excerpt,
            "harness_status": harness_status,
            "disposition": disposition,
            "evaluation_passed": evaluation_passed,
            "latency_ms": info.latency_ms if info else None,
            "prompt_tokens": info.prompt_tokens if info else None,
            "completion_tokens": info.completion_tokens if info else None,
            "cost_usd": info.cost_usd if info else None,
            "captured_raw_path": captured_raw_path,
            **schema_versions,
        }
        strict, spine = attempt_metrics(attempt)
        strict_count += int(strict)
        spine_count += int(spine)
        with attempts_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(attempt) + "\n")

    return {
        "slot": resolution["slot"],
        "label": resolution["label"],
        "model": resolution["model"],
        "source": resolution["source"],
        "status": classify_candidate_status(adapter_statuses),
        "attempts": attempts,
        "strict_loadable": strict_count,
        "spine_passed": spine_count,
        "adapter_statuses": adapter_statuses,
    }


def _schema_versions() -> dict:
    from rook.agent.local_worker_adapter import (
        LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
    )
    from rook.agent.local_worker_prompt_artifact import (
        LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        LOCAL_WORKER_PROMPT_TEXT_VERSION,
    )
    from rook.agent.local_worker_turn_request import (
        LOCAL_WORKER_TURN_REQUEST_SCHEMA,
    )
    from rook.agent.local_worker_turn_response import (
        LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    )

    return {
        "prompt_schema": LOCAL_WORKER_PROMPT_ARTIFACT_SCHEMA,
        "prompt_text_version": LOCAL_WORKER_PROMPT_TEXT_VERSION,
        "request_schema": LOCAL_WORKER_TURN_REQUEST_SCHEMA,
        "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "record_schema": LOCAL_WORKER_ADAPTER_RECORD_SCHEMA,
    }


def _git_short_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        sha = out.stdout.strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def build_manifest(
    run_id: str,
    panel: list,
    attempts: int,
    capture_raw: bool,
) -> dict:
    return {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_short_sha(),
        "scenario_workflow_id": SCENARIO_WORKFLOW_ID,
        "generation_params": dict(GENERATION_PARAMS),
        "attempts_per_candidate": attempts,
        "capture_raw": capture_raw,
        "panel": panel,
        **_schema_versions(),
    }


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("attempts must be a positive integer")
    return number


def run_probe(args, transport_factory=None) -> Path:
    from rook.agent.model_profiles import get_models

    if (
        not isinstance(args.attempts, int)
        or isinstance(args.attempts, bool)
        or args.attempts <= 0
    ):
        raise ValueError("attempts must be a positive integer")

    models = get_models()
    resolutions = [
        resolve_slot(
            slot,
            cli_value=getattr(args, slot),
            env_value=os.environ.get(ENV_VARS[slot]) or None,
            profile_worker=models.worker,
            profile_api_base=models.api_base,
            skipped=slot in (args.skip or []),
        )
        for slot in SLOTS
    ]

    run_id = "lm5k-{}-{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        _git_short_sha(),
    )
    run_dir = Path(args.run_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    panel = []
    for resolution in resolutions:
        if resolution["status"] in ("skipped", "unavailable"):
            panel.append({**resolution, "attempts": 0,
                          "strict_loadable": 0, "spine_passed": 0})
            continue
        summary = run_candidate(
            resolution, args.attempts, run_dir, args.capture_raw,
            transport_factory=transport_factory,
        )
        panel.append({**resolution, **summary})

    manifest = build_manifest(run_id, panel, args.attempts, args.capture_raw)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"run: {run_dir}")
    for entry in panel:
        print(
            f"  {entry['slot']:8} {(entry['status'] or 'ran'):16} "
            f"{entry.get('model') or '-':40} "
            f"{entry.get('strict_loadable', 0)}/{entry.get('attempts', 0)} strict-loadable, "
            f"{entry.get('spine_passed', 0)}/{entry.get('attempts', 0)} spine-passing"
        )
    return run_dir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="LM5K first worker model probe (evidence, not CI)."
    )
    parser.add_argument("--local", help="local slot: MODEL[@API_BASE]")
    parser.add_argument("--cheap", help="cheap cloud slot: MODEL[@API_BASE]")
    parser.add_argument("--ceiling", help="ceiling slot: MODEL[@API_BASE]")
    parser.add_argument(
        "--skip", action="append", choices=list(SLOTS), default=[]
    )
    parser.add_argument(
        "--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS
    )
    parser.add_argument("--capture-raw", action="store_true")
    parser.add_argument("--run-dir", default="probe_runs")
    args = parser.parse_args(argv)
    run_probe(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
