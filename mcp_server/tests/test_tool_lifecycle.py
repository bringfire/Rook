from __future__ import annotations

import sys
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.tool_lifecycle import (  # noqa: E402
    CONTAINED_TOOLS,
    ToolDisposition,
    denial_payload,
    resolve_contained_tool,
)


EXPECTED = {
    "gh_execute_intent": ToolDisposition.RETIRED,
    "rhino_execute_intent": ToolDisposition.RETIRED,
    "plan_and_execute": ToolDisposition.SUSPENDED,
    "spawn_agent": ToolDisposition.SUSPENDED,
    "gh_explore_workflow": ToolDisposition.SUSPENDED,
    "gh_replay_recipe": ToolDisposition.SUSPENDED,
}


def test_lifecycle_contains_exactly_the_six_reviewed_identities() -> None:
    assert {entry.name: entry.disposition for entry in CONTAINED_TOOLS} == EXPECTED
    assert all(entry.recovery.startswith("Rediscover the current tool surface") for entry in CONTAINED_TOOLS)


def test_resolution_is_exact_case_sensitive_and_type_strict() -> None:
    assert resolve_contained_tool("gh_execute_intent").name == "gh_execute_intent"
    for near_match in (
        "GH_EXECUTE_INTENT",
        " gh_execute_intent",
        "gh_execute_intent ",
        "gh_execute_intent\n",
        "gh_execute_intent.extra",
        b"gh_execute_intent",
        None,
        7,
    ):
        assert resolve_contained_tool(near_match) is None


def test_denial_payload_is_stable_and_contains_no_caller_data() -> None:
    entry = resolve_contained_tool("spawn_agent")
    assert entry is not None
    assert denial_payload(entry) == {
        "code": "legacy_semantic_tool_contained",
        "tool": "spawn_agent",
        "verified": False,
        "retryable": False,
        "disposition": "suspended",
        "recovery": entry.recovery,
    }
