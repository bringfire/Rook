"""Measure context growth and retained result volume in a sealed Qwen cohort."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "rook.analysis.qwen38_varied_product_efficiency:v1"

CATEGORY_BY_TARGET = {
    "rook_tools_search": "component_discovery",
    "gh_library": "component_discovery",
    "rook_tools_read": "schema_metadata",
    "gh_batch_component_info": "schema_metadata",
    "gh_snapshot": "structural_observation",
    "gh_inspect_output": "output_inspection",
    "gh_status": "status_readiness",
    "gh_wait_for_solve_readiness": "status_readiness",
    "gh_errors": "diagnostics",
    "gh_edit": "mutation",
    "gh_execute_intent": "mutation",
    "gh_set_value": "mutation",
    "gh_create_script": "mutation",
    "gh_update_script": "mutation",
    "gh_set_script_pins": "mutation",
    "chirp_create": "mutation",
    "gh_bake_output": "export_visual",
    "gh_canvas_image": "export_visual",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if type(value) is not dict:
                raise ValueError(f"jsonl_object_required:{path.name}")
            values.append(value)
    return values


def analyze_context_growth(prime_events: list[dict[str, Any]]) -> dict[str, Any]:
    per_turn = []
    previous_input = None
    for event in prime_events:
        if type(event) is not dict or event.get("type") != "message_end":
            continue
        message = event.get("message")
        usage = message.get("usage") if type(message) is dict else None
        if type(usage) is not dict:
            continue
        input_tokens = usage.get("input", usage.get("inputTokens"))
        output_tokens = usage.get("output", usage.get("outputTokens"))
        if (
            type(input_tokens) is not int
            or input_tokens < 0
            or type(output_tokens) is not int
            or output_tokens < 0
        ):
            raise ValueError("provider_usage_invalid")
        growth = 0 if previous_input is None else input_tokens - previous_input
        per_turn.append(
            {
                "turn": len(per_turn) + 1,
                "inputTokens": input_tokens,
                "inputGrowthTokens": growth,
                "outputTokens": output_tokens,
            }
        )
        previous_input = input_tokens
    if not per_turn:
        raise ValueError("provider_usage_missing")
    inter_turn = [item["inputGrowthTokens"] for item in per_turn[1:]]
    largest = (
        max(per_turn[1:], key=lambda item: item["inputGrowthTokens"])
        if inter_turn
        else per_turn[0]
    )
    return {
        "turnCount": len(per_turn),
        "initialInputTokens": per_turn[0]["inputTokens"],
        "finalInputTokens": per_turn[-1]["inputTokens"],
        "netContextGrowthTokens": (
            per_turn[-1]["inputTokens"] - per_turn[0]["inputTokens"]
        ),
        "cumulativeInputTokens": sum(item["inputTokens"] for item in per_turn),
        "cumulativeOutputTokens": sum(item["outputTokens"] for item in per_turn),
        "averageInterTurnGrowthTokens": (
            round(sum(inter_turn) / len(inter_turn), 3) if inter_turn else 0.0
        ),
        "largestInterTurnGrowth": {
            "turn": largest["turn"],
            "tokens": largest["inputGrowthTokens"],
        },
        "perTurn": per_turn,
        "causalLimits": [
            "provider_input_tokens_are_reported_context_size_per_turn",
            "byte_counts_are_not_provider_token_attribution",
        ],
    }


def _category(target: str) -> str:
    return CATEGORY_BY_TARGET.get(target, "other")


def _normalized_text(value: Any) -> str | None:
    if type(value) is not str:
        return None
    return " ".join(value.casefold().split())


def _selector_atoms(arguments: dict[str, Any]) -> set[str]:
    atoms = set()
    for field, prefix in (("names", "name"), ("guids", "guid")):
        values = arguments.get(field, [])
        if type(values) is list:
            for value in values:
                normalized = _normalized_text(value)
                if normalized:
                    atoms.add(f"{prefix}:{normalized}")
    return atoms


def _exact_request_repeats(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, bytes], list[dict[str, Any]]] = {}
    for event in events:
        target = event["target"]
        arguments = event.get("arguments", {})
        groups.setdefault((target, _canonical_bytes(arguments)), []).append(event)
    repeats = []
    for (target, _), group in groups.items():
        if len(group) < 2:
            continue
        result_bytes = [_canonical_bytes(event.get("result")) for event in group]
        repeats.append(
            {
                "target": target,
                "sequences": [event["sequence"] for event in group],
                "calls": len(group),
                "repeatCalls": len(group) - 1,
                "repeatCanonicalResultBytes": sum(
                    len(value) for value in result_bytes[1:]
                ),
                "allResultsIdentical": len(set(result_bytes)) == 1,
            }
        )
    return sorted(repeats, key=lambda item: (item["sequences"][0], item["target"]))


def _near_request_repeats(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    near = []
    grouped: dict[tuple[str, bytes], list[dict[str, Any]]] = {}
    for event in events:
        target = event["target"]
        arguments = event.get("arguments", {})
        key = None
        kind = None
        if target == "gh_snapshot":
            projection = {
                name: value
                for name, value in arguments.items()
                if name not in {"max_preview_items", "readiness_receipt_id"}
            }
            key = _canonical_bytes(projection)
            kind = "same_projection_shape"
        elif target in {"gh_library", "rook_tools_search"}:
            field = "search" if target == "gh_library" else "query"
            normalized = _normalized_text(arguments.get(field))
            if normalized:
                key = normalized.encode("utf-8")
                kind = "same_normalized_search"
        if key is not None and kind is not None:
            grouped.setdefault((f"{target}:{kind}", key), []).append(event)
    for (group_name, _), group in grouped.items():
        exact_shapes = {_canonical_bytes(event.get("arguments", {})) for event in group}
        if len(group) < 2 or len(exact_shapes) < 2:
            continue
        target, kind = group_name.split(":", 1)
        near.append(
            {
                "target": target,
                "kind": kind,
                "sequences": [event["sequence"] for event in group],
                "calls": len(group),
            }
        )
    metadata = [event for event in events if event["target"] == "gh_batch_component_info"]
    for index, left in enumerate(metadata):
        left_args = left.get("arguments", {})
        left_exact = _canonical_bytes(left_args)
        left_atoms = _selector_atoms(left_args)
        for right in metadata[index + 1 :]:
            if left_exact == _canonical_bytes(right.get("arguments", {})):
                continue
            shared = sorted(left_atoms & _selector_atoms(right.get("arguments", {})))
            if shared:
                near.append(
                    {
                        "target": "gh_batch_component_info",
                        "kind": "overlapping_selectors",
                        "sequences": [left["sequence"], right["sequence"]],
                        "sharedSelectors": shared,
                    }
                )
    return sorted(near, key=lambda item: (item["sequences"][0], item["sequences"][-1]))


def analyze_gateway_results(source_events: list[dict[str, Any]]) -> dict[str, Any]:
    events = sorted(
        (
            event
            for event in source_events
            if type(event) is dict
            and type(event.get("sequence")) is int
            and type(event.get("target")) is str
        ),
        key=lambda event: event["sequence"],
    )
    by_tool: dict[str, dict[str, Any]] = {}
    by_category: dict[str, dict[str, int]] = {}
    total_bytes = 0
    for event in events:
        target = event["target"]
        category = _category(target)
        result_bytes = len(_canonical_bytes(event.get("result")))
        total_bytes += result_bytes
        tool = by_tool.setdefault(
            target,
            {"category": category, "calls": 0, "canonicalResultBytes": 0},
        )
        tool["calls"] += 1
        tool["canonicalResultBytes"] += result_bytes
        category_total = by_category.setdefault(
            category, {"calls": 0, "canonicalResultBytes": 0}
        )
        category_total["calls"] += 1
        category_total["canonicalResultBytes"] += result_bytes
    return {
        "callCount": len(events),
        "canonicalResultBytes": total_bytes,
        "byTool": dict(sorted(by_tool.items())),
        "byCategory": dict(sorted(by_category.items())),
        "exactRequestRepeats": _exact_request_repeats(events),
        "nearRequestRepeats": _near_request_repeats(events),
        "causalLimits": [
            "canonical_result_bytes_measure_retained_source_payloads_not_prompt_tokens",
            "repeated_request_shape_does_not_prove_the_call_was_unnecessary",
        ],
    }


def _static_gateway_attribution(code: Any) -> str:
    if type(code) is not str:
        return "unattributed"
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "unattributed"
    targets = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if not isinstance(owner, ast.Name) or owner.id != "rook_full":
            continue
        if node.func.attr == "search":
            targets.append("rook_tools_search")
        elif node.func.attr == "read":
            targets.append("rook_tools_read")
        elif node.func.attr == "call":
            if node.args and isinstance(node.args[0], ast.Constant) and type(node.args[0].value) is str:
                targets.append(node.args[0].value)
            else:
                targets.append("unknown_gateway")
    unique = sorted(set(targets))
    if not unique:
        return "non_gateway"
    if len(unique) == 1:
        return unique[0]
    return "mixed_gateway"


def analyze_prime_tool_results(session_events: list[dict[str, Any]]) -> dict[str, Any]:
    attribution_by_call: dict[str, str] = {}
    for event in session_events:
        if type(event) is not dict or event.get("type") != "message":
            continue
        message = event.get("message")
        if type(message) is not dict or message.get("role") != "assistant":
            continue
        content = message.get("content", [])
        if type(content) is not list:
            continue
        for item in content:
            if type(item) is not dict or item.get("type") != "toolCall":
                continue
            call_id = item.get("id")
            arguments = item.get("arguments")
            if type(call_id) is str and type(arguments) is dict:
                attribution_by_call[call_id] = _static_gateway_attribution(
                    arguments.get("code")
                )
    by_attribution: dict[str, dict[str, Any]] = {}
    count = 0
    total_bytes = 0
    for event in session_events:
        if type(event) is not dict or event.get("type") != "message":
            continue
        message = event.get("message")
        if type(message) is not dict or message.get("role") != "toolResult":
            continue
        content = message.get("content", [])
        if type(content) is not list:
            content = []
        text = "".join(
            item.get("text", "")
            for item in content
            if type(item) is dict
            and item.get("type") == "text"
            and type(item.get("text")) is str
        )
        text_bytes = len(text.encode("utf-8"))
        attribution = attribution_by_call.get(message.get("toolCallId"), "unattributed")
        category = (
            attribution
            if attribution in {"non_gateway", "mixed_gateway", "unattributed"}
            else _category(attribution)
        )
        bucket = by_attribution.setdefault(
            attribution,
            {"category": category, "cells": 0, "retainedTextBytes": 0},
        )
        bucket["cells"] += 1
        bucket["retainedTextBytes"] += text_bytes
        count += 1
        total_bytes += text_bytes
    return {
        "toolResultCount": count,
        "retainedTextBytes": total_bytes,
        "byAttribution": dict(sorted(by_attribution.items())),
        "causalLimits": [
            "counts_only_text_retained_in_prime_tool_result_content",
            "cell_attribution_is_static_and_may_be_mixed_or_unattributed",
            "retained_text_bytes_are_not_provider_token_attribution",
        ],
    }


def analyze_session_content(session_events: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, dict[str, int]] = {}

    def retain(kind: str, value: str | bytes) -> None:
        size = len(value if type(value) is bytes else value.encode("utf-8"))
        bucket = by_kind.setdefault(kind, {"items": 0, "contentBytes": 0})
        bucket["items"] += 1
        bucket["contentBytes"] += size

    for event in session_events:
        if type(event) is not dict:
            continue
        if event.get("type") == "custom_message" and type(event.get("content")) is str:
            retain("custom_message_text", event["content"])
            continue
        if event.get("type") != "message":
            continue
        message = event.get("message")
        if type(message) is not dict or type(message.get("content")) is not list:
            continue
        role = message.get("role")
        for item in message["content"]:
            if type(item) is not dict:
                continue
            item_type = item.get("type")
            if role == "assistant" and item_type == "thinking" and type(item.get("thinking")) is str:
                retain("assistant_thinking", item["thinking"])
            elif role == "assistant" and item_type == "text" and type(item.get("text")) is str:
                retain("assistant_text", item["text"])
            elif role == "assistant" and item_type == "toolCall" and type(item.get("arguments")) is dict:
                retain("assistant_tool_arguments", _canonical_bytes(item["arguments"]))
            elif role == "toolResult" and item_type == "text" and type(item.get("text")) is str:
                retain("tool_result_text", item["text"])
            elif role == "user" and item_type == "text" and type(item.get("text")) is str:
                retain("user_text", item["text"])
    ordered = dict(sorted(by_kind.items()))
    return {
        "measuredContentBytes": sum(item["contentBytes"] for item in ordered.values()),
        "byKind": ordered,
        "causalLimits": [
            "counts_selected_native_session_content_not_serialized_provider_prompt_bytes",
            "does_not_include_provider_system_material_or_protocol_overhead",
        ],
    }


def analyze_row(row_root: Path) -> dict[str, Any]:
    operator = row_root / "operator"
    prime_path = operator / "prime.jsonl"
    source_path = operator / "source.jsonl"
    sessions = sorted((row_root / "agent" / "sessions").glob("*.jsonl"))
    if len(sessions) != 1:
        raise ValueError(f"one_session_required:{row_root.name}")
    session_path = sessions[0]
    session_events = _jsonl(session_path)
    return {
        "contextGrowth": analyze_context_growth(_jsonl(prime_path)),
        "gatewayResults": analyze_gateway_results(_jsonl(source_path)),
        "primeToolResults": analyze_prime_tool_results(session_events),
        "sessionContent": analyze_session_content(session_events),
        "inputCustody": {
            "primeJsonlSha256": _sha_file(prime_path),
            "sourceJsonlSha256": _sha_file(source_path),
            "sessionJsonlSha256": _sha_file(session_path),
        },
    }


def analyze_cohort(evidence_root: Path) -> dict[str, Any]:
    rows = {row: analyze_row(evidence_root / row) for row in ("VP1", "VP2", "VP3")}
    manifest = evidence_root / "evidence-manifest.json"
    if not manifest.is_file():
        raise ValueError("campaign_manifest_missing")
    return {
        "schema": SCHEMA,
        "evidenceRoot": evidence_root.as_posix(),
        "campaignManifestSha256": _sha_file(manifest),
        "rows": rows,
        "interpretationBoundary": {
            "measured": [
                "provider_reported_per_turn_input_and_output_tokens",
                "canonical_source_result_bytes",
                "prime_session_tool_result_text_bytes",
                "exact_request_and_narrow_near_request_repetition",
            ],
            "notEstablished": [
                "provider_token_cost_caused_by_any_specific_tool_or_byte",
                "semantic_necessity_or_avoidability_of_a_repeated_call",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = analyze_cohort(arguments.evidence_root.resolve())
    serialized = json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    if arguments.output is None:
        print(serialized, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
