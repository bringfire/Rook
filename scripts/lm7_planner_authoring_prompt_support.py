#!/usr/bin/env python
"""Shared LM7 Planner authoring prompt/parser support."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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

INTENT_CORRECT = "correct_declared"
INTENT_OVER_DECLARED = "over_declared"
INTENT_INVENTED = "invented"
INTENT_NOT_CLASSIFIABLE = "not_classifiable"


@dataclass(frozen=True)
class ParseResult:
    parse_status: str
    payload: dict[str, Any] | None
    failure_reason: str | None


@dataclass(frozen=True)
class IntentDecisionResult:
    intent_decision: str
    failure_reason: str | None


def planner_authoring_prompt(
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


def template_menu() -> dict[str, Any]:
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


def scenario_brief(scenario: str) -> dict[str, str]:
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


def prompt_call_payload(
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
        "prompt": planner_authoring_prompt(prompt_profile),
        "prompt_profile": prompt_profile,
        "prompt_version": prompt_version(prompt_profile),
        "template_menu": template_menu(),
        "brief": scenario_brief(scenario),
    }


def prompt_version(prompt_profile: str) -> str:
    if prompt_profile == PROMPT_PROFILE_SPARSE_V1:
        return SPARSE_PROMPT_VERSION
    if prompt_profile == PROMPT_PROFILE_SHAPE_GUIDANCE_V2:
        return SHAPE_GUIDANCE_PROMPT_VERSION
    raise ValueError(f"unknown_prompt_profile:{prompt_profile}")


def write_prompt_artifacts(
    run_dir: Path,
    prompt_profile: str,
    scenarios: Sequence[str] = SCENARIOS,
) -> None:
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "planner_authoring_prompt.txt").write_text(
        planner_authoring_prompt(prompt_profile) + "\n",
        encoding="utf-8",
    )
    (prompts_dir / "template_menu.json").write_text(
        json.dumps(template_menu(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    for scenario in scenarios:
        brief = scenario_brief(scenario)
        (prompts_dir / f"{scenario}_brief.txt").write_text(
            f"version: {brief['version']}\n\n{brief['text']}\n",
            encoding="utf-8",
        )


def strict_parse_model_output(raw_output: str) -> ParseResult:
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


def classify_intent_decision(
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


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_json(value: Mapping[str, Any] | Sequence[Any] | str) -> str:
    if isinstance(value, str):
        rendered = value
    else:
        rendered = canonical_json(value)
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()
