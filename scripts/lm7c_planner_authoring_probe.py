#!/usr/bin/env python
"""LM7C deterministic offline Planner authoring probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

from rook.agent.planner_worker_contract_request import (  # noqa: E402
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    MISSING_DESIRED_OUTPUT_ROUTE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
)
from rook.agent.workflow_validate import (  # noqa: E402
    validate_planner_worker_contract_request,
)


PROBE_SCHEMA = "rook.lm7c_planner_authoring_probe:v1"
PROMPT_PROFILE_SPARSE_V1 = "sparse_v1"
PROMPT_PROFILE_SHAPE_GUIDANCE_V2 = "shape_guidance_v2"
PROMPT_PROFILES = (
    PROMPT_PROFILE_SPARSE_V1,
    PROMPT_PROFILE_SHAPE_GUIDANCE_V2,
)

SPARSE_PROMPT_VERSION = "lm7c.planner_authoring_prompt:v1"
SHAPE_GUIDANCE_PROMPT_VERSION = "lm7d.planner_authoring_prompt_shape_guidance:v2"
PLANNER_AUTHORING_PROMPT_VERSION = SPARSE_PROMPT_VERSION
TEMPLATE_MENU_VERSION = "lm7c.template_menu:v1"
INTENT_COMPLETE_BRIEF_VERSION = "lm7c.intent_complete_brief:v1"
INTENT_INCOMPLETE_BRIEF_VERSION = "lm7c.intent_incomplete_brief:v1"
SCENARIOS = ("intent_complete", "intent_incomplete")

PARSE_PARSED = "parsed"
PARSE_FAILED = "parse_failed"

VALIDATION_VALID = "workflow_validate_valid"
VALIDATION_FAILED = "workflow_validate_failed"
VALIDATION_NOT_EVALUATED = "not_evaluated"

INTENT_CORRECT = "correct_declared"
INTENT_OVER_DECLARED = "over_declared"
INTENT_INVENTED = "invented"
INTENT_NOT_CLASSIFIABLE = "not_classifiable"

_PLACEHOLDER_PROVIDERS = {"fake", "ceiling-provider"}
_PLACEHOLDER_MODELS = {
    "fake-planner",
    "ceiling-planner-model",
}
_REJECTED_LOCAL_MODEL_PAIR = ("ollama", "gemma4:12b-it-qat")


@dataclass(frozen=True)
class ParseResult:
    parse_status: str
    payload: dict[str, Any] | None
    failure_reason: str | None


@dataclass(frozen=True)
class IntentDecisionResult:
    intent_decision: str
    failure_reason: str | None


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM7C deterministic offline Planner authoring probe."
    )
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--provider", default="ceiling-provider")
    parser.add_argument("--provider-command", default=None)
    parser.add_argument("--provider-timeout-s", type=float, default=120)
    parser.add_argument("--model", default="ceiling-planner-model")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--run-dir", default="probe_runs")
    parser.add_argument("--output-excerpt-chars", type=int, default=1200)
    parser.add_argument(
        "--prompt-profile",
        choices=PROMPT_PROFILES,
        default=PROMPT_PROFILE_SPARSE_V1,
    )
    parser.add_argument("--canonical-evidence", action="store_true")
    args = parser.parse_args(argv)
    if args.attempts <= 0:
        parser.error("attempts_must_be_positive")
    if args.output_excerpt_chars < 0:
        parser.error("output_excerpt_chars_must_be_non_negative")
    return args


def _planner_authoring_prompt(
    prompt_profile: str = PROMPT_PROFILE_SPARSE_V1,
) -> str:
    if prompt_profile == PROMPT_PROFILE_SPARSE_V1:
        return _sparse_planner_authoring_prompt()
    if prompt_profile == PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return _shape_guidance_planner_authoring_prompt()
    raise ValueError(f"unknown_prompt_profile:{prompt_profile}")


def _sparse_planner_authoring_prompt() -> str:
    return "\n".join(
        [
            f"version: {SPARSE_PROMPT_VERSION}",
            "",
            "Author one PlannerWorkerContractRequest from the supplied scenario brief.",
            f"The schema must be {PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA}.",
            "Output exactly one JSON object and no markdown or surrounding prose.",
            "Allowed top-level fields are schema, template_id, initial_params, "
            "routing_delta, and intent_slots.",
            "The template menu contains only the LM7A repair template.",
            'The create_script pins_out field must be ["A:double"].',
            "When the brief provides the desired output intent, it is not missing, "
            "and v1 has no legal field for that concrete value.",
            "When the brief omits the desired output intent, declare only the "
            "canonical unresolved desired_output_value slot and emit the matching "
            "missing_desired_output_value unresolved-intent route with required=false.",
            "Do not write repair code, acceptance prose, hidden bind params, or "
            "fields outside the request schema.",
        ]
    )


def _shape_guidance_planner_authoring_prompt() -> str:
    routing_delta_shape = json.dumps(
        {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [],
        },
        indent=2,
        sort_keys=True,
    )
    unresolved_slot_shape = json.dumps(
        {
            "intent_id": DESIRED_OUTPUT_VALUE_INTENT_ID,
            "status": "unresolved",
            "source_path": PLANNER_INTENT_SOURCE_PATH,
            "description": "Desired output value was not provided.",
        },
        indent=2,
        sort_keys=True,
    )
    unresolved_route_shape = json.dumps(
        {
            "route_id": MISSING_DESIRED_OUTPUT_ROUTE_ID,
            "source_class": "planner_user_intent",
            "source_path": PLANNER_INTENT_SOURCE_PATH,
            "purpose": "unresolved_intent",
            "required": False,
        },
        indent=2,
        sort_keys=True,
    )
    return "\n".join(
        [
            f"version: {SHAPE_GUIDANCE_PROMPT_VERSION}",
            "",
            "Author one PlannerWorkerContractRequest from the supplied scenario brief.",
            f"The schema must be {PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA}.",
            "Output exactly one JSON object and no markdown or surrounding prose.",
            "Required top-level fields are schema, template_id, initial_params, "
            "routing_delta, and intent_slots.",
            "Include required empty arrays and objects instead of omitting them.",
            "The template menu contains only the LM7A repair template.",
            'The create_script pins_out field must be ["A:double"].',
            "When the brief provides the desired output intent, it is not missing, "
            "and v1 has no legal field for that concrete value.",
            "When no intent is missing, intent_slots is [].",
            "When no unresolved-intent route is needed, "
            "routing_delta.add_unresolved_intent_routes is [].",
            "",
            "routing_delta container shape:",
            routing_delta_shape,
            "",
            "Canonical unresolved desired_output_value slot shape:",
            unresolved_slot_shape,
            "",
            "Canonical missing_desired_output_value unresolved-intent route shape:",
            unresolved_route_shape,
            "",
            "Use these only when desired_output_value is missing from the brief.",
            "Omit them when desired output intent is present.",
            "Do not write repair code, acceptance prose, hidden bind params, or "
            "fields outside the request schema.",
        ]
    )


def _template_menu() -> dict[str, Any]:
    return {
        "version": TEMPLATE_MENU_VERSION,
        "templates": [
            {
                "template_id": LM7A_TEMPLATE_ID,
                "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
                "purpose": "repair the same component after create failure",
                "allowed_top_level_fields": [
                    "schema",
                    "template_id",
                    "initial_params",
                    "routing_delta",
                    "intent_slots",
                ],
                "fixed_initial_params": {
                    "create_script.pins_out": ["A:double"],
                },
                "unresolved_intent_identity": {
                    "intent_id": DESIRED_OUTPUT_VALUE_INTENT_ID,
                    "route_id": MISSING_DESIRED_OUTPUT_ROUTE_ID,
                    "source_class": "planner_user_intent",
                    "source_path": PLANNER_INTENT_SOURCE_PATH,
                    "purpose": "unresolved_intent",
                    "required": False,
                },
            }
        ],
    }


def _scenario_brief(scenario: str) -> dict[str, str]:
    if scenario == "intent_complete":
        return {
            "version": INTENT_COMPLETE_BRIEF_VERSION,
            "text": (
                "Scenario intent_complete: create a script component with "
                'pins_out: ["A:double"]. The fallback output value is 7.5. '
                "That value means desired_output_value is present intent, but "
                "PlannerWorkerContractRequest v1 has no legal field for the "
                "concrete value."
            ),
        }
    if scenario == "intent_incomplete":
        return {
            "version": INTENT_INCOMPLETE_BRIEF_VERSION,
            "text": (
                "Scenario intent_incomplete: create a script component with "
                'pins_out: ["A:double"]. The desired output behavior/value is '
                "not supplied. Represent only the canonical unresolved "
                "desired_output_value identity."
            ),
        }
    raise ValueError(f"unknown_scenario:{scenario}")


def _prompt_call_payload(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    prompt_profile: str,
) -> dict[str, Any]:
    return {
        "schema": PROBE_SCHEMA,
        "scenario": scenario,
        "attempt_index": attempt_index,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "prompt": _planner_authoring_prompt(prompt_profile),
        "prompt_profile": prompt_profile,
        "prompt_version": _prompt_version(prompt_profile),
        "template_menu": _template_menu(),
        "brief": _scenario_brief(scenario),
    }


def _prompt_version(prompt_profile: str) -> str:
    if prompt_profile == PROMPT_PROFILE_SPARSE_V1:
        return SPARSE_PROMPT_VERSION
    if prompt_profile == PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return SHAPE_GUIDANCE_PROMPT_VERSION
    raise ValueError(f"unknown_prompt_profile:{prompt_profile}")


def _write_prompt_artifacts(run_dir: Path) -> None:
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "planner_authoring_prompt.txt").write_text(
        _planner_authoring_prompt() + "\n",
        encoding="utf-8",
    )
    (prompts_dir / "template_menu.json").write_text(
        json.dumps(_template_menu(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    for scenario in SCENARIOS:
        brief = _scenario_brief(scenario)
        (prompts_dir / f"{scenario}_brief.txt").write_text(
            f"version: {brief['version']}\n\n{brief['text']}\n",
            encoding="utf-8",
        )


def _strict_parse_model_output(raw_output: str) -> ParseResult:
    try:
        payload = json.loads(raw_output.strip())
    except json.JSONDecodeError:
        return ParseResult(PARSE_FAILED, None, "json_decode_failed")
    if not isinstance(payload, dict):
        return ParseResult(PARSE_FAILED, None, "json_not_object")
    if payload.get("schema") != PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA:
        return ParseResult(PARSE_FAILED, None, "invalid_schema")
    return ParseResult(PARSE_PARSED, payload, None)


def _canonical_unresolved_slot_present(payload: Mapping[str, Any]) -> bool:
    return any(
        isinstance(slot, Mapping)
        and slot.get("intent_id") == DESIRED_OUTPUT_VALUE_INTENT_ID
        and slot.get("status") == "unresolved"
        and slot.get("source_path") == PLANNER_INTENT_SOURCE_PATH
        for slot in _mapping_sequence(payload.get("intent_slots"))
    )


def _canonical_unresolved_route_present(payload: Mapping[str, Any]) -> bool:
    routing_delta = payload.get("routing_delta")
    if not isinstance(routing_delta, Mapping):
        return False
    return any(
        isinstance(route, Mapping)
        and route.get("route_id") == MISSING_DESIRED_OUTPUT_ROUTE_ID
        and route.get("source_class") == "planner_user_intent"
        and route.get("source_path") == PLANNER_INTENT_SOURCE_PATH
        and route.get("purpose") == "unresolved_intent"
        and route.get("required") is False
        for route in _mapping_sequence(routing_delta.get("add_unresolved_intent_routes"))
    )


def _mapping_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list) else ()


def _has_extra_unresolved_intent(payload: Mapping[str, Any]) -> bool:
    slots = _mapping_sequence(payload.get("intent_slots"))
    for slot in slots:
        if not isinstance(slot, Mapping):
            continue
        if slot.get("status") != "unresolved":
            continue
        if (
            slot.get("intent_id") != DESIRED_OUTPUT_VALUE_INTENT_ID
            or slot.get("source_path") != PLANNER_INTENT_SOURCE_PATH
        ):
            return True
    routing_delta = payload.get("routing_delta")
    routes = (
        _mapping_sequence(routing_delta.get("add_unresolved_intent_routes"))
        if isinstance(routing_delta, Mapping)
        else ()
    )
    for route in routes:
        if not isinstance(route, Mapping):
            continue
        if route.get("purpose") != "unresolved_intent":
            continue
        if (
            route.get("route_id") != MISSING_DESIRED_OUTPUT_ROUTE_ID
            or route.get("source_path") != PLANNER_INTENT_SOURCE_PATH
        ):
            return True
    return False


def _contains_invented_concrete_intent(payload: Mapping[str, Any]) -> bool:
    rendered = json.dumps(payload, sort_keys=True, default=str)
    markers = (
        "0.0",
        "1.0",
        "7.5",
        "42.0",
        "A = 0.0",
        "A = 1.0",
        "A = 42.0",
        "use a default",
        "set A to",
        "PROBE_REPAIR_CODE",
    )
    if any(marker in rendered for marker in markers):
        return True
    return _contains_repair_code_field(payload)


def _contains_repair_code_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key).lower()
            if key_text in {"code", "repair_code", "output_value"}:
                return True
            if _contains_repair_code_field(nested):
                return True
    if isinstance(value, list):
        return any(_contains_repair_code_field(item) for item in value)
    return False


def _classify_intent_decision(
    scenario: str,
    payload: Mapping[str, Any],
) -> IntentDecisionResult:
    if scenario not in SCENARIOS:
        return IntentDecisionResult(INTENT_NOT_CLASSIFIABLE, "unknown_scenario")
    if _contains_invented_concrete_intent(payload):
        return IntentDecisionResult(INTENT_INVENTED, "invented_concrete_intent")

    slot_present = _canonical_unresolved_slot_present(payload)
    route_present = _canonical_unresolved_route_present(payload)

    if scenario == "intent_complete":
        if slot_present or route_present:
            return IntentDecisionResult(
                INTENT_OVER_DECLARED,
                "desired_output_value_over_declared",
            )
        return IntentDecisionResult(INTENT_CORRECT, None)

    if _has_extra_unresolved_intent(payload):
        return IntentDecisionResult(INTENT_OVER_DECLARED, "extra_unresolved_intent")
    if slot_present and route_present:
        return IntentDecisionResult(INTENT_CORRECT, None)
    return IntentDecisionResult(
        INTENT_NOT_CLASSIFIABLE,
        "missing_unresolved_desired_output_value",
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint_json(value: Mapping[str, Any] | Sequence[Any] | str) -> str:
    if isinstance(value, str):
        rendered = value
    else:
        rendered = _canonical_json(value)
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _workflow_failure_reason(report: Mapping[str, Any]) -> str:
    codes: list[str] = []
    phases = report.get("phases")
    if isinstance(phases, Mapping):
        for phase in phases.values():
            if not isinstance(phase, Mapping):
                continue
            diagnostics = phase.get("diagnostics")
            if not isinstance(diagnostics, list):
                continue
            for diagnostic in diagnostics:
                if isinstance(diagnostic, Mapping) and isinstance(
                    diagnostic.get("code"),
                    str,
                ):
                    codes.append(diagnostic["code"])
    code_summary = ",".join(codes) if codes else "unknown"
    return f"workflow_validate_failed:{code_summary}"


def _base_row(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    raw_output: str,
    output_excerpt_chars: int,
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "attempt_index": attempt_index,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "prompt_version": PLANNER_AUTHORING_PROMPT_VERSION,
        "template_menu_version": TEMPLATE_MENU_VERSION,
        "brief_version": _scenario_brief(scenario)["version"],
        "parse_status": PARSE_FAILED,
        "validation_status": VALIDATION_NOT_EVALUATED,
        "intent_decision": INTENT_NOT_CLASSIFIABLE,
        "canonical_success": False,
        "request_fingerprint": None,
        "workflow_validate_report_fingerprint": None,
        "failure_reason": None,
        "output_excerpt": raw_output[:output_excerpt_chars],
        "output_sha256": _fingerprint_json(raw_output),
    }


def _score_model_output(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    raw_output: str,
    output_excerpt_chars: int,
) -> dict[str, Any]:
    row = _base_row(
        scenario=scenario,
        attempt_index=attempt_index,
        provider=provider,
        model=model,
        temperature=temperature,
        raw_output=raw_output,
        output_excerpt_chars=output_excerpt_chars,
    )

    parsed = _strict_parse_model_output(raw_output)
    row["parse_status"] = parsed.parse_status
    if parsed.parse_status != PARSE_PARSED or parsed.payload is None:
        row["failure_reason"] = parsed.failure_reason
        return row

    payload = parsed.payload
    report = validate_planner_worker_contract_request(payload)
    valid = report.get("valid") is True
    row["validation_status"] = VALIDATION_VALID if valid else VALIDATION_FAILED
    row["request_fingerprint"] = report.get("request_fingerprint") or _fingerprint_json(
        payload
    )
    row["workflow_validate_report_fingerprint"] = (
        report.get("report_fingerprint") or _fingerprint_json(report)
    )

    intent = _classify_intent_decision(scenario, payload)
    row["intent_decision"] = intent.intent_decision
    row["canonical_success"] = (
        row["parse_status"] == PARSE_PARSED
        and row["validation_status"] == VALIDATION_VALID
        and row["intent_decision"] == INTENT_CORRECT
    )

    if not valid and intent.intent_decision == INTENT_CORRECT:
        row["failure_reason"] = _workflow_failure_reason(report)
    elif intent.intent_decision != INTENT_CORRECT:
        row["failure_reason"] = intent.failure_reason
    else:
        row["failure_reason"] = None
    return row


def _git_short_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _new_run_dir(root: Path, sha: str | None = None) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = sha if sha is not None else _git_short_sha()
    run_dir = root / f"lm7c-{timestamp}-{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), sort_keys=True, default=str) + "\n")


def _scenario_count(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "total_rows": len(rows),
        "parse_success_count": sum(
            1 for row in rows if row.get("parse_status") == PARSE_PARSED
        ),
        "workflow_validate_valid_count": sum(
            1 for row in rows if row.get("validation_status") == VALIDATION_VALID
        ),
        "correct_intent_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_CORRECT
        ),
        "canonical_success_count": sum(
            1 for row in rows if row.get("canonical_success") is True
        ),
        "over_declared_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_OVER_DECLARED
        ),
        "invented_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_INVENTED
        ),
        "not_classifiable_count": sum(
            1 for row in rows if row.get("intent_decision") == INTENT_NOT_CLASSIFIABLE
        ),
    }


def _summarize_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    attempts: int,
    provider: str,
    model: str,
    temperature: float,
    canonical_evidence: bool,
) -> dict[str, Any]:
    counts = _scenario_count(rows)
    return {
        "schema": PROBE_SCHEMA,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "scheduled_attempts_per_scenario": attempts,
        **counts,
        "scenario_counts": {
            scenario: _scenario_count(
                [row for row in rows if row.get("scenario") == scenario]
            )
            for scenario in SCENARIOS
        },
        "canonical_evidence": canonical_evidence,
    }


def _manifest(
    *,
    provider: str,
    model: str,
    temperature: float,
    attempts: int,
    canonical_evidence: bool,
) -> dict[str, Any]:
    return {
        "schema": PROBE_SCHEMA,
        "git_commit": _git_short_sha(),
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "scheduled_attempts_per_scenario": attempts,
        "scenarios": list(SCENARIOS),
        "prompt_version": PLANNER_AUTHORING_PROMPT_VERSION,
        "template_menu_version": TEMPLATE_MENU_VERSION,
        "brief_versions": {
            scenario: _scenario_brief(scenario)["version"] for scenario in SCENARIOS
        },
        "canonical_evidence": canonical_evidence,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }


def _provider_error_row(
    *,
    scenario: str,
    attempt_index: int,
    provider: str,
    model: str,
    temperature: float,
    output_excerpt_chars: int,
    exc: Exception,
) -> dict[str, Any]:
    row = _base_row(
        scenario=scenario,
        attempt_index=attempt_index,
        provider=provider,
        model=model,
        temperature=temperature,
        raw_output="",
        output_excerpt_chars=output_excerpt_chars,
    )
    row["failure_reason"] = f"provider_error:{type(exc).__name__}"
    return row


def _run_probe(
    *,
    run_root: Path,
    provider: str,
    model: str,
    temperature: float,
    attempts: int,
    canonical_evidence: bool,
    output_excerpt_chars: int,
    prompt_profile: str,
    call_provider: Callable[[Mapping[str, Any]], str],
) -> Path:
    run_dir = _new_run_dir(Path(run_root))
    _write_prompt_artifacts(run_dir)
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            provider=provider,
            model=model,
            temperature=temperature,
            attempts=attempts,
            canonical_evidence=canonical_evidence,
        ),
    )

    rows: list[dict[str, Any]] = []
    rows_path = run_dir / "rows.jsonl"
    for scenario in SCENARIOS:
        for attempt_index in range(attempts):
            payload = _prompt_call_payload(
                scenario=scenario,
                attempt_index=attempt_index,
                provider=provider,
                model=model,
                temperature=temperature,
                prompt_profile=prompt_profile,
            )
            try:
                raw_output = call_provider(payload)
            except Exception as exc:
                row = _provider_error_row(
                    scenario=scenario,
                    attempt_index=attempt_index,
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    output_excerpt_chars=output_excerpt_chars,
                    exc=exc,
                )
            else:
                row = _score_model_output(
                    scenario=scenario,
                    attempt_index=attempt_index,
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    raw_output=raw_output,
                    output_excerpt_chars=output_excerpt_chars,
                )
            rows.append(row)
            _append_jsonl(rows_path, row)

    _write_json(
        run_dir / "summary.json",
        _summarize_rows(
            rows,
            attempts=attempts,
            provider=provider,
            model=model,
            temperature=temperature,
            canonical_evidence=canonical_evidence,
        ),
    )
    return run_dir


def _call_provider_command(
    command: str,
    call_payload: Mapping[str, Any],
    timeout_s: float,
) -> str:
    result = subprocess.run(
        command,
        input=json.dumps(dict(call_payload), sort_keys=True),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        shell=True,
        check=False,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout


def _canonical_evidence_is_valid(args: argparse.Namespace) -> bool:
    if not args.canonical_evidence:
        return True
    if args.attempts != 5:
        return False
    if args.prompt_profile != PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return False
    if args.provider in _PLACEHOLDER_PROVIDERS:
        return False
    if args.model in _PLACEHOLDER_MODELS:
        return False
    if (args.provider, args.model) == _REJECTED_LOCAL_MODEL_PAIR:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if args.provider_command is None:
        print("provider_command_required", file=sys.stderr)
        raise SystemExit(2)
    if not _canonical_evidence_is_valid(args):
        print("invalid_canonical_evidence", file=sys.stderr)
        raise SystemExit(2)

    run_dir = _run_probe(
        run_root=Path(args.run_dir),
        provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        attempts=args.attempts,
        canonical_evidence=args.canonical_evidence,
        output_excerpt_chars=args.output_excerpt_chars,
        prompt_profile=args.prompt_profile,
        call_provider=lambda call_payload: _call_provider_command(
            args.provider_command,
            call_payload,
            args.provider_timeout_s,
        ),
    )
    print(f"LM7C planner authoring probe complete run_dir={run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
