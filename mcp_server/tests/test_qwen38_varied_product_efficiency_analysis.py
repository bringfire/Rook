"""Causal tests for the sealed varied-product efficiency analyzer."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = ROOT / "scripts" / "qwen38_varied_product_efficiency_analysis.py"


def _analyzer():
    spec = importlib.util.spec_from_file_location("varied_efficiency", ANALYZER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_context_growth_uses_provider_reported_turn_inputs_without_inventing_cost():
    analyzer = _analyzer()
    events = [
        {
            "type": "message_end",
            "message": {
                "usage": {"input": 100, "output": 10, "totalTokens": 110}
            },
        },
        {
            "type": "message_end",
            "message": {
                "usage": {"input": 140, "output": 20, "totalTokens": 160}
            },
        },
        {
            "type": "message_end",
            "message": {
                "usage": {"input": 230, "output": 30, "totalTokens": 260}
            },
        },
    ]

    result = analyzer.analyze_context_growth(events)

    assert result == {
        "turnCount": 3,
        "initialInputTokens": 100,
        "finalInputTokens": 230,
        "netContextGrowthTokens": 130,
        "cumulativeInputTokens": 470,
        "cumulativeOutputTokens": 60,
        "averageInterTurnGrowthTokens": 65.0,
        "largestInterTurnGrowth": {"turn": 3, "tokens": 90},
        "perTurn": [
            {"turn": 1, "inputTokens": 100, "inputGrowthTokens": 0, "outputTokens": 10},
            {"turn": 2, "inputTokens": 140, "inputGrowthTokens": 40, "outputTokens": 20},
            {"turn": 3, "inputTokens": 230, "inputGrowthTokens": 90, "outputTokens": 30},
        ],
        "causalLimits": [
            "provider_input_tokens_are_reported_context_size_per_turn",
            "byte_counts_are_not_provider_token_attribution",
        ],
    }


def test_gateway_result_bytes_are_attributed_and_repetition_is_fail_closed():
    analyzer = _analyzer()
    events = [
        {"schema": "row_emitter"},
        {
            "sequence": 0,
            "target": "gh_status",
            "arguments": {},
            "result": {"success": True},
        },
        {
            "sequence": 1,
            "target": "gh_status",
            "arguments": {},
            "result": {"success": True},
        },
        {
            "sequence": 2,
            "target": "gh_snapshot",
            "arguments": {"include_data": True, "max_preview_items": 3},
            "result": {"success": True, "data": {"epoch": 1}},
        },
        {
            "sequence": 3,
            "target": "gh_snapshot",
            "arguments": {"include_data": True, "max_preview_items": 5},
            "result": {"success": True, "data": {"epoch": 2}},
        },
        {
            "sequence": 4,
            "target": "gh_library",
            "arguments": {"search": "Circle", "limit": 5},
            "result": {"success": True, "data": ["circle"]},
        },
        {
            "sequence": 5,
            "target": "gh_library",
            "arguments": {"search": "circle", "limit": 10},
            "result": {"success": True, "data": ["circle", "arc"]},
        },
        {
            "sequence": 6,
            "target": "gh_batch_component_info",
            "arguments": {"names": ["Circle", "Line"]},
            "result": {"success": True, "data": ["circle", "line"]},
        },
        {
            "sequence": 7,
            "target": "gh_batch_component_info",
            "arguments": {"names": ["Line", "Loft"]},
            "result": {"success": True, "data": ["line", "loft"]},
        },
    ]

    result = analyzer.analyze_gateway_results(events)

    assert result["callCount"] == 8
    assert result["byTool"]["gh_status"] == {
        "category": "status_readiness",
        "calls": 2,
        "canonicalResultBytes": 32,
    }
    assert result["byCategory"]["structural_observation"]["calls"] == 2
    assert result["byCategory"]["component_discovery"]["calls"] == 2
    assert result["byCategory"]["schema_metadata"]["calls"] == 2
    assert result["exactRequestRepeats"] == [
        {
            "target": "gh_status",
            "sequences": [0, 1],
            "calls": 2,
            "repeatCalls": 1,
            "repeatCanonicalResultBytes": 16,
            "allResultsIdentical": True,
        }
    ]
    assert result["nearRequestRepeats"] == [
        {
            "target": "gh_snapshot",
            "kind": "same_projection_shape",
            "sequences": [2, 3],
            "calls": 2,
        },
        {
            "target": "gh_library",
            "kind": "same_normalized_search",
            "sequences": [4, 5],
            "calls": 2,
        },
        {
            "target": "gh_batch_component_info",
            "kind": "overlapping_selectors",
            "sequences": [6, 7],
            "sharedSelectors": ["name:line"],
        },
    ]
    assert result["causalLimits"] == [
        "canonical_result_bytes_measure_retained_source_payloads_not_prompt_tokens",
        "repeated_request_shape_does_not_prove_the_call_was_unnecessary",
    ]


def test_prime_visible_tool_result_text_is_separate_from_gateway_source_bytes():
    analyzer = _analyzer()
    events = [
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolCall",
                        "id": "call-1",
                        "name": "ipython",
                        "arguments": {
                            "code": 'x = await rook_full.call("gh_snapshot", {})'
                        },
                    }
                ],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "toolResult",
                "toolCallId": "call-1",
                "content": [{"type": "text", "text": "snapshot payload"}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolCall",
                        "id": "call-2",
                        "name": "ipython",
                        "arguments": {"code": 'await rook_full.search("gh")'},
                    }
                ],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "toolResult",
                "toolCallId": "call-2",
                "content": [{"type": "text", "text": "search payload"}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolCall",
                        "id": "call-3",
                        "name": "ipython",
                        "arguments": {"code": "print('local')"},
                    }
                ],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "toolResult",
                "toolCallId": "call-3",
                "content": [{"type": "text", "text": "local"}],
            },
        },
    ]

    result = analyzer.analyze_prime_tool_results(events)

    assert result == {
        "toolResultCount": 3,
        "retainedTextBytes": 35,
        "byAttribution": {
            "gh_snapshot": {
                "category": "structural_observation",
                "cells": 1,
                "retainedTextBytes": 16,
            },
            "non_gateway": {
                "category": "non_gateway",
                "cells": 1,
                "retainedTextBytes": 5,
            },
            "rook_tools_search": {
                "category": "component_discovery",
                "cells": 1,
                "retainedTextBytes": 14,
            },
        },
        "causalLimits": [
            "counts_only_text_retained_in_prime_tool_result_content",
            "cell_attribution_is_static_and_may_be_mixed_or_unattributed",
            "retained_text_bytes_are_not_provider_token_attribution",
        ],
    }


def test_session_content_footprint_keeps_roles_and_content_kinds_distinct():
    analyzer = _analyzer()
    events = [
        {"type": "custom_message", "content": "goal"},
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "begin"}],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "think"},
                    {"type": "text", "text": "say"},
                    {
                        "type": "toolCall",
                        "id": "call-1",
                        "name": "ipython",
                        "arguments": {"code": "print(1)"},
                    },
                ],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "toolResult",
                "content": [{"type": "text", "text": "done"}],
            },
        },
    ]

    assert analyzer.analyze_session_content(events) == {
        "measuredContentBytes": 40,
        "byKind": {
            "assistant_text": {"items": 1, "contentBytes": 3},
            "assistant_thinking": {"items": 1, "contentBytes": 5},
            "assistant_tool_arguments": {"items": 1, "contentBytes": 19},
            "custom_message_text": {"items": 1, "contentBytes": 4},
            "tool_result_text": {"items": 1, "contentBytes": 4},
            "user_text": {"items": 1, "contentBytes": 5},
        },
        "causalLimits": [
            "counts_selected_native_session_content_not_serialized_provider_prompt_bytes",
            "does_not_include_provider_system_material_or_protocol_overhead",
        ],
    }
