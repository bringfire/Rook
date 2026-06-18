# RookChat Tool-Schema Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic RookChat tool-schema contract harness so model-visible schemas are closed, consistent across fallback/local/MCP/cache/active registry paths, and aligned with dispatcher behavior before further model tuning.

**Architecture:** Add a small `tool_contracts.py` policy module that normalizes and audits LiteLLM function schemas without executing tools. Wire that policy into `ToolRegistry` and `ChatRunner` schema exposure boundaries, then lock the behavior with focused Python tests over policy helpers, catalogs, dispatcher parity, model-visible active schemas, and non-live transcript flows.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, LiteLLM function schema dictionaries, existing RookChat `ChatRunner`, `ToolRegistry`, and `ToolDispatcher`.

---

## Pre-Execution Branch Gate

This branch is currently allowed to be a planning branch, but implementation must not begin while its base is ambiguous.

- [ ] **Step 1: Fetch and inspect branch shape before implementation**

Run:

```powershell
cd C:\UDEV\Rook
git fetch origin
git status --short --branch
git rev-list --left-right --count origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected before executing Task 1:

- If the one-box autonomy work has merged: rebase this branch onto `origin/main` first so `origin/main...HEAD` contains only the tool-schema contract spec/plan plus new implementation commits.
- If the one-box autonomy work has not merged: explicitly declare this branch stacked on `codex/rookchat-gh-one-box-autonomy`, verify that dependency branch is the intended base, and do not present this branch as independently mergeable.
- In either case, working-tree dirt must still be limited to:

```text
 M knowledge/contextual_mab.pkl
 M knowledge/substrate_observations.jsonl
```

Do not continue into implementation if `origin/main...HEAD` unexpectedly includes unrelated workstreams.

---

## File Structure

Implementation should touch only the Python chat/tool contract surface and deterministic tests.

- Create `mcp_server/src/rook/agent/chat/tool_contracts.py`
  - Owns schema contract policy helpers.
  - No Rhino calls, no tool execution, no global cache writes.
  - Provides normalization/audit helpers used by `ChatRunner`, `ToolRegistry`, and tests.

- Modify `mcp_server/src/rook/agent/tool_registry.py`
  - Normalizes MCP-converted schemas, cache-loaded schemas, meta-tool schemas, and active schemas through the policy.
  - Keeps `request_tools` / `search_tools` behavior unchanged apart from closed parameter schemas.

- Modify `mcp_server/src/rook/agent/chat/chat_runner.py`
  - Reuses policy helpers for fallback schemas, local tool schemas, and zero-argument tools.
  - Keeps the existing typed GH script schemas and C# guidance; moves shared contract details into the policy where appropriate.

- Modify `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
  - Keep existing GH script parity tests.
  - Add or adjust assertions where the new policy changes schema closure/audit behavior.

- Create `mcp_server/tests/test_rookchat_tool_contracts.py`
  - Unit tests for schema policy helpers.
  - Tests are pure, fast, and do not require Rhino.

- Create `mcp_server/tests/test_rookchat_tool_schema_golden.py`
  - Model-visible schema invariants for fallback/local/MCP/cache/active registry paths.
  - Assertion-based golden checks, not brittle full-catalog snapshots.

- Create `mcp_server/tests/test_rookchat_tool_transcripts.py`
  - Non-live transcript-style ChatRunner tests for one-box and bad-call flows.
  - Mocks LiteLLM and tool dispatch; no Rhino.

- Create `docs/rookchat-tool-contract-smoke.md`
  - Optional manual/provider smoke instructions for qwen/cloud/Gemma-style exploration.
  - Not a CI gate and not metaharness integration.

Do not modify C# panel files, Workbench files, Rhino launcher/deploy scripts, or `knowledge/*` runtime artifacts in this slice.

---

## Task 1: Contract Policy Red Tests

**Files:**
- Create: `mcp_server/tests/test_rookchat_tool_contracts.py`
- Later implementation target: `mcp_server/src/rook/agent/chat/tool_contracts.py`

- [ ] **Step 1: Write failing policy-helper tests**

Create `mcp_server/tests/test_rookchat_tool_contracts.py` with these tests:

```python
import pytest


def test_closed_no_arg_schema_shape():
    from rook.agent.chat.tool_contracts import closed_no_arg_parameters

    schema = closed_no_arg_parameters()

    assert schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_normalize_function_schema_closes_missing_parameters():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "gh_errors",
            "description": "Get errors and warnings from Grasshopper",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    assert normalized["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert schema["function"]["parameters"].get("additionalProperties") is None


def test_zero_argument_tool_override_rejects_open_schema():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "gh_errors",
            "description": "Get errors and warnings from Grasshopper",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "additionalProperties": True,
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    params = normalized["function"]["parameters"]
    assert params["properties"] == {}
    assert params["additionalProperties"] is False
    assert "Takes no arguments" in normalized["function"]["description"]


def test_explicit_dynamic_allowlist_preserves_open_map():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "ui_block",
            "description": "Present UI",
            "parameters": {
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "Shape varies by block_type",
                        "additionalProperties": True,
                    }
                },
                "required": ["config"],
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    params = normalized["function"]["parameters"]
    assert params["additionalProperties"] is False
    assert params["properties"]["config"]["additionalProperties"] is True


def test_normalize_closes_unallowlisted_nested_objects_recursively():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_nested_tool",
            "description": "Nested object sample",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "object",
                        "properties": {
                            "inner": {
                                "type": "object",
                                "properties": {},
                            }
                        },
                    }
                },
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    payload = normalized["function"]["parameters"]["properties"]["payload"]
    inner = payload["properties"]["inner"]
    assert normalized["function"]["parameters"]["additionalProperties"] is False
    assert payload["additionalProperties"] is False
    assert inner["additionalProperties"] is False


def test_normalize_closes_array_item_object_schemas():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_array_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                            },
                        },
                    }
                },
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)
    item_schema = (
        normalized["function"]["parameters"]
        ["properties"]["rows"]["items"]
    )

    assert item_schema["additionalProperties"] is False


def test_normalize_closes_composition_object_schemas():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_union_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {"id": {"type": "string"}},
                            },
                        ],
                    },
                    "scope": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {"layer": {"type": "string"}},
                                "additionalProperties": True,
                            }
                        ],
                    },
                    "options": {
                        "allOf": [
                            {
                                "type": "object",
                                "properties": {"hidden": {"type": "boolean"}},
                            }
                        ],
                    },
                },
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)
    target_object = (
        normalized["function"]["parameters"]
        ["properties"]["target"]["oneOf"][1]
    )
    scope_object = (
        normalized["function"]["parameters"]
        ["properties"]["scope"]["anyOf"][0]
    )
    options_object = (
        normalized["function"]["parameters"]
        ["properties"]["options"]["allOf"][0]
    )

    assert target_object["additionalProperties"] is False
    assert scope_object["additionalProperties"] is False
    assert options_object["additionalProperties"] is False


def test_zero_argument_policy_matches_dispatcher_strict_set():
    from rook.agent.chat.tool_contracts import ZERO_ARGUMENT_TOOLS
    from rook.agent.tool_dispatcher import STRICT_NO_ARGUMENT_BRIDGE_TOOLS

    assert ZERO_ARGUMENT_TOOLS == STRICT_NO_ARGUMENT_BRIDGE_TOOLS


def test_audit_reports_open_root_parameter_objects():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "legacy_open_tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_root_parameters",
            "tool": "legacy_open_tool",
            "path": "function.parameters.additionalProperties",
            "message": "Root tool parameters allow arbitrary keys.",
        }
    ]


def test_audit_reports_omitted_root_additional_properties_as_open():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "legacy_implicit_open_tool",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_root_parameters",
            "tool": "legacy_implicit_open_tool",
            "path": "function.parameters.additionalProperties",
            "message": "Root tool parameters allow arbitrary keys.",
        }
    ]


def test_audit_reports_unallowlisted_nested_open_objects():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_nested_open_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_nested_object",
            "tool": "sample_nested_open_tool",
            "path": "function.parameters.properties.payload.additionalProperties",
            "message": "Nested object allows arbitrary keys without an explicit allowlist entry.",
        }
    ]


def test_audit_reports_open_array_item_object_schemas():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_array_open_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {},
                        },
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_nested_object",
            "tool": "sample_array_open_tool",
            "path": "function.parameters.properties.rows.items.additionalProperties",
            "message": "Nested object allows arbitrary keys without an explicit allowlist entry.",
        }
    ]


def test_audit_reports_open_composition_object_schemas():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_union_open_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "oneOf": [
                            {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": True,
                            }
                        ],
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_nested_object",
            "tool": "sample_union_open_tool",
            "path": "function.parameters.properties.target.oneOf.0.additionalProperties",
            "message": "Nested object allows arbitrary keys without an explicit allowlist entry.",
        }
    ]


def test_audit_allows_named_dynamic_nested_object_maps():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "ui_block",
            "parameters": {
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    assert audit_litellm_tool_schema(schema) == []


def test_audit_accepts_closed_script_creation_schema():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = _build_local_tool_catalog({"gh_create_csharp_script": object()})[
        "gh_create_csharp_script"
    ]

    assert audit_litellm_tool_schema(schema) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_contracts.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'rook.agent.chat.tool_contracts'
```

- [ ] **Step 3: Stop at red**

Do not implement in this task. The failure proves the plan has a real policy-module floor.

---

## Task 2: Contract Policy Module

**Files:**
- Create: `mcp_server/src/rook/agent/chat/tool_contracts.py`
- Test: `mcp_server/tests/test_rookchat_tool_contracts.py`

- [ ] **Step 1: Implement the minimal policy helpers**

Create `mcp_server/src/rook/agent/chat/tool_contracts.py`:

```python
"""Model-visible tool schema contract policy for RookChat.

This module normalizes and audits LiteLLM function schemas before they are
shown to chat models. It never executes tools and never calls Rhino.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..tool_dispatcher import STRICT_NO_ARGUMENT_BRIDGE_TOOLS

ZERO_ARGUMENT_TOOLS: frozenset[str] = STRICT_NO_ARGUMENT_BRIDGE_TOOLS

ROOT_OPEN_ALLOWLIST: frozenset[str] = frozenset()

DYNAMIC_NESTED_OBJECT_ALLOWLIST: dict[str, set[tuple[str, ...]]] = {
    "ui_block": {("config",)},
}


def _is_object_schema(schema: dict[str, Any]) -> bool:
    return schema.get("type") == "object" or isinstance(schema.get("properties"), dict)


def closed_no_arg_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def _tool_name(schema: dict[str, Any]) -> str:
    function = schema.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str):
            return name
    return ""


def _ensure_root_object(parameters: Any) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        return closed_no_arg_parameters()
    normalized = deepcopy(parameters)
    normalized["type"] = "object"
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized


def _normalize_nested_object_schemas(
    tool_name: str,
    schema: dict[str, Any],
    path: tuple[str, ...] = (),
) -> dict[str, Any]:
    normalized = deepcopy(schema)
    allowlist = DYNAMIC_NESTED_OBJECT_ALLOWLIST.get(tool_name, set())

    if _is_object_schema(normalized) and path and path not in allowlist:
        normalized["type"] = "object"
        normalized["additionalProperties"] = False

    properties = normalized.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop_schema in list(properties.items()):
            if isinstance(prop_schema, dict):
                properties[prop_name] = _normalize_nested_object_schemas(
                    tool_name,
                    prop_schema,
                    (*path, prop_name),
                )

    items = normalized.get("items")
    if isinstance(items, dict):
        normalized["items"] = _normalize_nested_object_schemas(
            tool_name,
            items,
            (*path, "items"),
        )
    elif isinstance(items, list):
        normalized["items"] = [
            _normalize_nested_object_schemas(tool_name, item, (*path, "items", str(index)))
            if isinstance(item, dict)
            else item
            for index, item in enumerate(items)
        ]

    for keyword in ("oneOf", "anyOf", "allOf"):
        entries = normalized.get(keyword)
        if isinstance(entries, list):
            normalized[keyword] = [
                _normalize_nested_object_schemas(tool_name, entry, (*path, keyword, str(index)))
                if isinstance(entry, dict)
                else entry
                for index, entry in enumerate(entries)
            ]

    return normalized


def _schema_path(path: tuple[str, ...]) -> str:
    schema_keywords = {"items", "oneOf", "anyOf", "allOf"}
    parts: list[str] = ["function", "parameters"]
    for part in path:
        if part in schema_keywords or part.isdigit():
            parts.append(part)
        else:
            parts.extend(["properties", part])
    return ".".join(parts)


def _audit_nested_object_schemas(
    tool_name: str,
    schema: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    allowlist = DYNAMIC_NESTED_OBJECT_ALLOWLIST.get(tool_name, set())

    if (
        _is_object_schema(schema)
        and path
        and path not in allowlist
        and schema.get("additionalProperties") is not False
    ):
        findings.append({
            "code": "open_nested_object",
            "tool": tool_name,
            "path": f"{_schema_path(path)}.additionalProperties",
            "message": (
                "Nested object allows arbitrary keys without an "
                "explicit allowlist entry."
            ),
        })

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            if isinstance(prop_schema, dict):
                findings.extend(
                    _audit_nested_object_schemas(
                        tool_name,
                        prop_schema,
                        (*path, prop_name),
                    )
                )

    items = schema.get("items")
    if isinstance(items, dict):
        findings.extend(_audit_nested_object_schemas(tool_name, items, (*path, "items")))
    elif isinstance(items, list):
        for index, item in enumerate(items):
            if isinstance(item, dict):
                findings.extend(
                    _audit_nested_object_schemas(tool_name, item, (*path, "items", str(index)))
                )

    for keyword in ("oneOf", "anyOf", "allOf"):
        entries = schema.get(keyword)
        if isinstance(entries, list):
            for index, entry in enumerate(entries):
                if isinstance(entry, dict):
                    findings.extend(
                        _audit_nested_object_schemas(
                            tool_name,
                            entry,
                            (*path, keyword, str(index)),
                        )
                    )

    return findings


def _append_no_arg_description(description: str) -> str:
    note = "Takes no arguments; call it with an empty argument object."
    if note in description:
        return description
    if description:
        return f"{description} {note}"
    return note


def normalize_litellm_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(schema)
    function = normalized.setdefault("function", {})
    if not isinstance(function, dict):
        normalized["function"] = function = {}

    name = _tool_name(normalized)
    function.setdefault("name", name)
    description = function.get("description")
    if not isinstance(description, str):
        description = name.replace("_", " ") if name else "tool"

    if name in ZERO_ARGUMENT_TOOLS:
        function["description"] = _append_no_arg_description(description)
        function["parameters"] = closed_no_arg_parameters()
        normalized["type"] = "function"
        return normalized

    parameters = _ensure_root_object(function.get("parameters"))
    if name not in ROOT_OPEN_ALLOWLIST:
        parameters["additionalProperties"] = False
    elif "additionalProperties" not in parameters:
        parameters["additionalProperties"] = True
    parameters = _normalize_nested_object_schemas(name, parameters)

    function["description"] = description
    function["parameters"] = parameters
    normalized["type"] = "function"
    return normalized


def normalize_catalog(catalog: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        name: normalize_litellm_tool_schema(schema)
        for name, schema in catalog.items()
    }


def audit_litellm_tool_schema(schema: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    name = _tool_name(schema)
    function = schema.get("function", {})
    parameters = function.get("parameters") if isinstance(function, dict) else None

    if not isinstance(parameters, dict):
        findings.append({
            "code": "missing_parameters",
            "tool": name,
            "path": "function.parameters",
            "message": "Tool schema has no parameter object.",
        })
        return findings

    if name in ZERO_ARGUMENT_TOOLS:
        if parameters != closed_no_arg_parameters():
            findings.append({
                "code": "zero_arg_schema_not_closed",
                "tool": name,
                "path": "function.parameters",
                "message": "Zero-argument tool schema must be exactly closed and empty.",
            })
        return findings

    if parameters.get("additionalProperties") is not False and name not in ROOT_OPEN_ALLOWLIST:
        findings.append({
            "code": "open_root_parameters",
            "tool": name,
            "path": "function.parameters.additionalProperties",
            "message": "Root tool parameters allow arbitrary keys.",
        })

    if parameters.get("type") != "object":
        findings.append({
            "code": "root_parameters_not_object",
            "tool": name,
            "path": "function.parameters.type",
            "message": "Root tool parameters must be a JSON object.",
        })

    findings.extend(_audit_nested_object_schemas(name, parameters))

    return findings


def audit_catalog(catalog: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for schema in catalog.values():
        findings.extend(audit_litellm_tool_schema(schema))
    return findings
```

- [ ] **Step 2: Run policy tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_contracts.py -q
```

Expected:

```text
15 passed
```

- [ ] **Step 3: Commit Task 1-2**

Stage only:

```powershell
git add mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/tests/test_rookchat_tool_contracts.py
git commit -m "feat(chat): add tool schema contract policy"
```

Do not stage `knowledge/contextual_mab.pkl` or `knowledge/substrate_observations.jsonl`.

---

## Task 3: Normalize Registry and Cache Schema Boundaries

**Files:**
- Modify: `mcp_server/src/rook/agent/tool_registry.py`
- Modify: `mcp_server/tests/test_rookchat_tool_contracts.py`
- Create: `mcp_server/tests/test_rookchat_tool_schema_golden.py`

- [ ] **Step 1: Write failing registry-boundary tests**

Append to `mcp_server/tests/test_rookchat_tool_contracts.py`:

```python
def test_mcp_tool_to_litellm_closes_root_parameters_when_server_omits_flag():
    from types import SimpleNamespace

    from rook.agent.tool_registry import mcp_tool_to_litellm

    tool = SimpleNamespace(
        name="sample_tool",
        description="Sample tool",
        inputSchema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )

    schema = mcp_tool_to_litellm(tool)

    assert schema["function"]["parameters"]["additionalProperties"] is False


def test_load_catalog_from_cache_normalizes_zero_arg_schema(tmp_path):
    import json

    from rook.agent.tool_registry import load_catalog_from_cache

    cache = tmp_path / "agent_tool_catalog.json"
    cache.write_text(
        json.dumps({
            "gh_errors": {
                "type": "function",
                "function": {
                    "name": "gh_errors",
                    "description": "Get errors and warnings from Grasshopper",
                    "parameters": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "additionalProperties": True,
                    },
                },
            }
        }),
        encoding="utf-8",
    )

    catalog = load_catalog_from_cache(cache)

    assert catalog["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_meta_tool_schemas_are_closed():
    from rook.agent.tool_registry import ToolRegistry

    registry = ToolRegistry(catalog={})
    schemas = {
        schema["function"]["name"]: schema
        for schema in registry.get_active_schemas()
    }

    for name in ("request_tools", "search_tools"):
        params = schemas[name]["function"]["parameters"]
        assert params["additionalProperties"] is False
```

Create `mcp_server/tests/test_rookchat_tool_schema_golden.py` with this initial active-schema test:

```python
from rook.agent.chat.tool_contracts import audit_litellm_tool_schema
from rook.agent.tool_registry import ToolRegistry


def _schema_by_name(schemas):
    return {
        schema.get("function", {}).get("name"): schema
        for schema in schemas
    }


def test_active_registry_schemas_are_audited_closed_at_exposure_boundary():
    registry = ToolRegistry(
        catalog={
            "gh_errors": {
                "type": "function",
                "function": {
                    "name": "gh_errors",
                    "description": "Get errors",
                    "parameters": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "additionalProperties": True,
                    },
                },
            }
        },
        tier0={"gh_errors", "request_tools", "search_tools"},
        agent_mode=True,
    )

    schemas = _schema_by_name(registry.get_active_schemas())

    assert schemas["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert audit_litellm_tool_schema(schemas["gh_errors"]) == []
    assert schemas["request_tools"]["function"]["parameters"]["additionalProperties"] is False
    assert schemas["search_tools"]["function"]["parameters"]["additionalProperties"] is False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_contracts.py tests/test_rookchat_tool_schema_golden.py -q
```

Expected failures:

```text
assert None is False
```

or:

```text
assert True is False
```

from unclosed registry/cache/meta schemas.

- [ ] **Step 3: Wire policy into `tool_registry.py`**

Modify `mcp_server/src/rook/agent/tool_registry.py`:

1. Add import near existing imports:

```python
from .chat.tool_contracts import normalize_catalog, normalize_litellm_tool_schema
```

2. In `mcp_tool_to_litellm`, wrap the return value:

```python
    return normalize_litellm_tool_schema({
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or tool.name.replace("_", " "),
            "parameters": input_schema or {
                "type": "object",
                "properties": {},
            },
        },
    })
```

3. In `load_catalog_from_cache`, normalize after JSON load:

```python
        catalog = normalize_catalog(json.load(f))
```

4. In `ToolRegistry.__init__`, normalize the incoming catalog assignment:

```python
        self._catalog: Dict[str, dict] = normalize_catalog(catalog or {})
```

5. In `_build_meta_schemas`, add root closure for both meta tools:

```python
                            "required": ["group"],
                            "additionalProperties": False,
```

and:

```python
                            "required": ["query"],
                            "additionalProperties": False,
```

6. At the end of `_build_meta_schemas`, either return the literal through `normalize_catalog(...)` or normalize each schema before returning:

```python
        return normalize_catalog(schemas)
```

If using a local `schemas` variable, keep the schema bodies identical except for `additionalProperties: False`.

7. In `get_active_schemas`, normalize at the exposure boundary:

```python
                schemas.append(normalize_litellm_tool_schema(self._meta_schemas[name]))
```

and:

```python
                schemas.append(normalize_litellm_tool_schema(self._catalog[name]))
```

- [ ] **Step 4: Run registry-boundary tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_contracts.py tests/test_rookchat_tool_schema_golden.py -q
```

Expected:

```text
19 passed
```

- [ ] **Step 5: Commit Task 3**

Stage only:

```powershell
git add mcp_server/src/rook/agent/tool_registry.py mcp_server/tests/test_rookchat_tool_contracts.py mcp_server/tests/test_rookchat_tool_schema_golden.py
git commit -m "feat(chat): normalize model-visible tool registry schemas"
```

---

## Task 4: ChatRunner Fallback and Local Catalog Discipline

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`
- Modify: `mcp_server/tests/test_rookchat_tool_schema_golden.py`

- [ ] **Step 1: Write failing fallback/local catalog tests**

Append to `mcp_server/tests/test_rookchat_tool_schema_golden.py`:

```python
from rook.agent.chat.tool_contracts import audit_litellm_tool_schema


def test_fallback_catalog_gh_canvas_critical_tools_are_closed():
    from rook.agent.chat.chat_runner import _build_fallback_catalog
    from rook.agent.tool_groups import TOOL_GROUPS

    catalog = _build_fallback_catalog()

    critical = {
        "gh_errors",
        "gh_update_script",
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
    }
    for tool_name in critical & set(TOOL_GROUPS["gh_canvas"]):
        params = catalog[tool_name]["function"]["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        assert audit_litellm_tool_schema(catalog[tool_name]) == []


def test_local_catalog_unknown_tools_are_closed_by_default():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"local_experimental": object()})

    params = catalog["local_experimental"]["function"]["parameters"]
    assert params == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
```

Append to `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`:

```python
def test_gh_create_pin_objects_match_server_pin_contract_without_arbitrary_keys():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"gh_create_csharp_script": object()})
    pin_item = (
        catalog["gh_create_csharp_script"]["function"]["parameters"]
        ["properties"]["pins_out"]["items"]["oneOf"][1]
    )

    assert pin_item["additionalProperties"] is False
    assert set(pin_item["properties"]) == {
        "name",
        "type",
        "nick",
        "access",
        "optional",
        "description",
        "hidden",
    }
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected failures:

```text
assert True is False
```

for fallback/local unknown schemas or pin item arbitrary-key allowance.

- [ ] **Step 3: Update `chat_runner.py` to use policy helpers**

Modify imports in `mcp_server/src/rook/agent/chat/chat_runner.py`:

```python
from .tool_contracts import (
    closed_no_arg_parameters,
    normalize_catalog,
    normalize_litellm_tool_schema,
)
```

In `_build_fallback_catalog()`, replace generic fallback parameters:

```python
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
```

Then return `normalize_catalog(catalog)` at the end:

```python
    return normalize_catalog(catalog)
```

In `_GH_ERRORS_SCHEMA`, use the helper:

```python
        "parameters": closed_no_arg_parameters(),
```

In `_GH_UPDATE_SCRIPT_SCHEMA`, add:

```python
            "additionalProperties": False,
```

next to `required`.

In `_GH_SCRIPT_PIN_ARRAY_SCHEMA`, change the pin-object branch from:

```python
                "additionalProperties": True,
```

to:

```python
                "additionalProperties": False,
```

and ensure its `properties` include the same create-script pin fields exposed by `server.py`:

```python
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "nick": {"type": "string"},
                    "access": {
                        "type": "string",
                        "enum": ["item", "list", "tree"],
                    },
                    "optional": {"type": "boolean"},
                    "description": {"type": "string"},
                    "hidden": {"type": "boolean"},
```

In `_build_local_tool_catalog`, change the generic local-tool fallback to:

```python
        catalog[name] = normalize_litellm_tool_schema({
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        })
```

At the end of `_build_local_tool_catalog`, return:

```python
    return normalize_catalog(catalog)
```

- [ ] **Step 4: Run fallback/local catalog tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 5: Commit Task 4**

Stage only:

```powershell
git add mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/tests/test_rookchat_gh_script_creation_parity.py mcp_server/tests/test_rookchat_tool_schema_golden.py
git commit -m "feat(chat): close fallback and local tool schemas"
```

---

## Task 5: Dispatcher and Schema Parity Audits

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/tool_contracts.py`
- Create or modify: `mcp_server/tests/test_rookchat_tool_schema_golden.py`
- Modify: `mcp_server/tests/test_rookchat_gh_script_creation_parity.py`

- [ ] **Step 1: Write failing dispatcher/schema parity tests**

Append to `mcp_server/tests/test_rookchat_tool_schema_golden.py`:

```python
import pytest


CRITICAL_PARITY_TOOLS = (
    "gh_create_script",
    "gh_create_python_script",
    "gh_create_csharp_script",
    "gh_errors",
    "request_tools",
    "search_tools",
    "gh_update_script",
)


@pytest.mark.parametrize("tool_name", CRITICAL_PARITY_TOOLS)
def test_critical_active_tool_schemas_are_closed_and_named(tool_name):
    from rook.agent.chat.chat_runner import _build_local_tool_catalog
    from rook.agent.tool_registry import ToolRegistry

    local_catalog = _build_local_tool_catalog({
        "gh_create_script": object(),
        "gh_create_python_script": object(),
        "gh_create_csharp_script": object(),
        "gh_update_script": object(),
    })
    if tool_name == "gh_errors":
        from rook.agent.chat.chat_runner import _build_fallback_catalog
        local_catalog.update({"gh_errors": _build_fallback_catalog()["gh_errors"]})

    registry = ToolRegistry(
        catalog=local_catalog,
        tier0=set(CRITICAL_PARITY_TOOLS),
        agent_mode=True,
    )
    schemas = _schema_by_name(registry.get_active_schemas())

    schema = schemas[tool_name]
    assert schema["function"]["name"] == tool_name
    assert schema["function"]["parameters"]["type"] == "object"
    assert schema["function"]["parameters"]["additionalProperties"] is False


def test_strict_no_argument_dispatcher_tools_have_zero_argument_schemas():
    from rook.agent.chat.chat_runner import _build_fallback_catalog
    from rook.agent.tool_dispatcher import STRICT_NO_ARGUMENT_BRIDGE_TOOLS

    catalog = _build_fallback_catalog()

    for tool_name in STRICT_NO_ARGUMENT_BRIDGE_TOOLS:
        assert catalog[tool_name]["function"]["parameters"] == {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }


@pytest.mark.asyncio
async def test_local_gh_create_required_fields_match_server_mcp_contract():
    from rook import server
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    local_catalog = _build_local_tool_catalog({
        "gh_create_script": object(),
        "gh_create_python_script": object(),
        "gh_create_csharp_script": object(),
    })
    server_tools = {tool.name: tool for tool in await server.list_tools()}

    assert (
        local_catalog["gh_create_script"]["function"]["parameters"]["required"]
        == server_tools["gh_create_script"].inputSchema["required"]
        == ["language", "code"]
    )
    for tool_name in ("gh_create_python_script", "gh_create_csharp_script"):
        assert (
            local_catalog[tool_name]["function"]["parameters"]["required"]
            == server_tools[tool_name].inputSchema["required"]
            == ["code", "pins_in", "pins_out"]
        )
```

- [ ] **Step 2: Run parity tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected before implementation may already be partly green from prior tasks. Any failing assertion should point to missing schema closure or missing fallback entries.

- [ ] **Step 3: Add policy helper only if tests need it**

If repeated parity setup becomes noisy, add this helper to `mcp_server/src/rook/agent/chat/tool_contracts.py`:

```python
def parameter_required_fields(schema: dict[str, Any]) -> list[str]:
    function = schema.get("function", {})
    parameters = function.get("parameters", {}) if isinstance(function, dict) else {}
    required = parameters.get("required", []) if isinstance(parameters, dict) else []
    return list(required) if isinstance(required, list) else []
```

Use it in tests only if it reduces duplication. Do not add broader abstractions.

- [ ] **Step 4: Run parity tests again**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 5: Commit Task 5**

Stage only the files actually changed:

```powershell
git add mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/tests/test_rookchat_tool_schema_golden.py mcp_server/tests/test_rookchat_gh_script_creation_parity.py
git commit -m "test(chat): lock dispatcher and schema parity"
```

If `tool_contracts.py` was not changed in this task, omit it from `git add`.

---

## Task 6: Model-Visible Golden Schema Invariants

**Files:**
- Modify: `mcp_server/tests/test_rookchat_tool_schema_golden.py`
- Potentially modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Potentially modify: `mcp_server/src/rook/agent/tool_registry.py`

- [ ] **Step 1: Add active `gh_canvas` invariant tests**

Append to `mcp_server/tests/test_rookchat_tool_schema_golden.py`:

```python
def _active_schemas_after_requesting_gh_canvas():
    from rook.agent.chat.chat_runner import _build_fallback_catalog, _build_local_tool_catalog
    from rook.agent.tool_dispatcher import build_local_tools
    from rook.agent.tool_registry import ToolRegistry

    catalog = _build_fallback_catalog()
    catalog.update(_build_local_tool_catalog(build_local_tools()))
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    result = registry.request_group("gh_canvas", turn=1)
    assert result["success"] is True
    return _schema_by_name(registry.get_active_schemas())


def test_model_visible_gh_canvas_schema_has_distinct_script_tools():
    schemas = _active_schemas_after_requesting_gh_canvas()

    for name in ("gh_create_script", "gh_create_python_script", "gh_create_csharp_script"):
        assert schemas[name]["function"]["name"] == name

    assert (
        schemas["gh_create_script"]["function"]["parameters"]["required"]
        == ["language", "code"]
    )
    assert (
        schemas["gh_create_csharp_script"]["function"]["parameters"]["required"]
        == ["code", "pins_in", "pins_out"]
    )


def test_model_visible_gh_canvas_schema_has_no_unallowlisted_open_roots():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schemas = _active_schemas_after_requesting_gh_canvas()
    findings = []
    for schema in schemas.values():
        findings.extend(audit_litellm_tool_schema(schema))

    assert findings == []


def test_model_visible_gh_canvas_schema_keeps_zero_arg_tools_empty():
    schemas = _active_schemas_after_requesting_gh_canvas()

    assert schemas["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_model_visible_gh_canvas_csharp_creation_guidance_survives_registry_path():
    schemas = _active_schemas_after_requesting_gh_canvas()
    text = str(schemas["gh_create_csharp_script"])

    assert "RhinoCode C# Script" in text
    assert "GH_Component" in text
    assert "body" in text and "RunScript" in text
```

- [ ] **Step 2: Run golden schema tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_schema_golden.py -q
```

Expected:

```text
all tests passed
```

If this fails because a valid dynamic tool in `gh_canvas` needs an open nested object, add a narrow allowlist entry in `tool_contracts.py` and a test naming the reason. Do not make root schemas open.

- [ ] **Step 3: Commit Task 6**

Stage only:

```powershell
git add mcp_server/tests/test_rookchat_tool_schema_golden.py mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/src/rook/agent/tool_registry.py
git commit -m "test(chat): add model-visible schema golden invariants"
```

Omit any implementation file that did not change.

---

## Task 7: Non-Live Golden Transcript Tests

**Files:**
- Create: `mcp_server/tests/test_rookchat_tool_transcripts.py`
- Potentially modify: `mcp_server/src/rook/agent/chat/chat_runner.py`

- [ ] **Step 1: Add transcript test helpers**

Create `mcp_server/tests/test_rookchat_tool_transcripts.py`:

```python
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat.conversation_store import Conversation


class _ToolCall:
    def __init__(self, tool_id, name, arguments):
        self.id = tool_id
        self.name = name
        self.arguments = arguments

    def to_delta(self, index):
        return SimpleNamespace(
            index=index,
            id=self.id,
            function=SimpleNamespace(
                name=self.name,
                arguments=json.dumps(self.arguments),
            ),
        )


async def _stream_chunks(*chunks):
    for chunk in chunks:
        yield chunk


def _chunk(delta):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta)],
        usage=None,
    )


def _usage_chunk():
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def _tool_stream(*calls):
    delta = SimpleNamespace(
        content=None,
        tool_calls=[call.to_delta(index) for index, call in enumerate(calls)],
    )
    return _stream_chunks(_chunk(delta), _usage_chunk())


def _text_stream(text):
    delta = SimpleNamespace(content=text, tool_calls=None)
    return _stream_chunks(_chunk(delta), _usage_chunk())


def _runtime_facts_patch():
    return patch(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        AsyncMock(return_value={"verified_runtime_facts": []}),
    )


async def _collect_events(runner, completion_side_effects, user_message="make a box"):
    conv = Conversation(
        id="conv_tool_contract",
        persona="architect",
        model="ollama_chat/qwen3:14b",
        api_base="http://localhost:11434",
    )
    events = []
    with (
        patch(
            "rook.agent.chat.chat_runner.litellm.acompletion",
            AsyncMock(side_effect=completion_side_effects),
        ),
        _runtime_facts_patch(),
    ):
        async for event in runner.run_turn(conv, user_message, "system"):
            events.append(event)
    return events, conv
```

- [ ] **Step 2: Add clean one-box sequence test**

Append:

```python
@pytest.mark.asyncio
async def test_clean_one_box_tool_sequence_is_reported_without_live_rhino():
    tool_results = {
        "gh_create_csharp_script": {
            "success": True,
            "data": {
                "component_guid": "script-guid",
                "name": "Box Maker",
                "pins_out": ["B:Brep"],
            },
        },
        "gh_errors": {
            "success": True,
            "data": {"errorCount": 0, "warningCount": 0},
        },
    }

    async def executor(name, params):
        if name == "request_tools":
            raise AssertionError("request_tools is handled internally")
        return tool_results[name]

    runner = ChatRunner(tool_executor=executor)
    responses = [
        _tool_stream(_ToolCall("call_request", "request_tools", {"group": "gh_canvas"})),
        _tool_stream(
            _ToolCall(
                "call_create",
                "gh_create_csharp_script",
                {
                    "code": "var box = new Rhino.Geometry.Box(Rhino.Geometry.Plane.WorldXY, new Rhino.Geometry.Interval(0, 10), new Rhino.Geometry.Interval(0, 10), new Rhino.Geometry.Interval(0, 10)); B = box.ToBrep();",
                    "pins_in": [],
                    "pins_out": ["B:Brep"],
                    "name": "Box Maker",
                },
            )
        ),
        _tool_stream(_ToolCall("call_errors", "gh_errors", {})),
        _text_stream("Created Box Maker. gh_errors returned 0 errors and 0 warnings."),
    ]

    events, conv = await _collect_events(runner, responses)

    tool_results_events = [
        event for event in events
        if event.type == "tool_result"
    ]
    assert [event.name for event in tool_results_events] == [
        "request_tools",
        "gh_create_csharp_script",
        "gh_errors",
    ]
    assert tool_results_events[0].tool_status == "success"
    assert tool_results_events[1].tool_status == "success"
    assert tool_results_events[2].tool_status == "success"
    assert conv.messages[-1]["role"] == "assistant"
    assert "0 errors" in conv.messages[-1]["content"]
```

- [ ] **Step 3: Add bad-call transcript tests**

Append:

```python
@pytest.mark.asyncio
async def test_bad_gh_errors_arguments_surface_actionable_failure_without_rhino(monkeypatch):
    from rook.agent import tool_dispatcher

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        raise AssertionError("gh_errors with unexpected args must fail before call_rhino")

    monkeypatch.setattr(tool_dispatcher, "call_rhino", fake_call_rhino)

    runner = ChatRunner()
    responses = [
        _tool_stream(_ToolCall("call_request", "request_tools", {"group": "gh_canvas"})),
        _tool_stream(
            _ToolCall(
                "call_bad_errors",
                "gh_errors",
                {"code": "B = box.ToBrep();", "pins_out": ["B:Brep"]},
            )
        ),
        _text_stream("I need to call gh_create_csharp_script instead."),
    ]

    events, conv = await _collect_events(runner, responses)

    bad_result = [
        event for event in events
        if event.type == "tool_result" and event.name == "gh_errors"
    ][0]
    assert bad_result.tool_status == "failed"
    assert "unexpected_arguments" in bad_result.result
    assert "gh_create_csharp_script" in bad_result.result
    assert any(
        message["role"] == "tool" and "unexpected_arguments" in message["content"]
        for message in conv.messages
    )


@pytest.mark.asyncio
async def test_missing_code_create_call_surfaces_failed_tool_status():
    async def executor(name, params):
        if name == "gh_create_csharp_script":
            return {"success": False, "data": "Missing required parameter: code"}
        raise AssertionError(f"unexpected executor call: {name}")

    runner = ChatRunner(tool_executor=executor)
    responses = [
        _tool_stream(_ToolCall("call_request", "request_tools", {"group": "gh_canvas"})),
        _tool_stream(
            _ToolCall(
                "call_create",
                "gh_create_csharp_script",
                {"pins_out": ["B:Brep"], "name": "Box Maker"},
            )
        ),
        _text_stream("I need to retry with code."),
    ]

    events, _conv = await _collect_events(runner, responses)

    create_result = [
        event for event in events
        if event.type == "tool_result" and event.name == "gh_create_csharp_script"
    ][0]
    assert create_result.tool_status == "failed"
    assert "Missing required parameter: code" in create_result.result
```

- [ ] **Step 4: Run transcript tests to verify behavior**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_transcripts.py -q
```

Expected:

```text
3 passed
```

If the `gh_errors` bad-call test fails, do not weaken the expected failed `tool_status`; inspect whether `STRICT_NO_ARGUMENT_BRIDGE_TOOLS` is still applied before `call_rhino`.

- [ ] **Step 5: Commit Task 7**

Stage only:

```powershell
git add mcp_server/tests/test_rookchat_tool_transcripts.py mcp_server/src/rook/agent/chat/chat_runner.py
git commit -m "test(chat): add non-live tool transcript regressions"
```

Omit `chat_runner.py` if no production changes were needed.

---

## Task 8: Optional Provider Smoke Documentation

**Files:**
- Create: `docs/rookchat-tool-contract-smoke.md`

- [ ] **Step 1: Write the manual smoke doc**

Create `docs/rookchat-tool-contract-smoke.md`:

````markdown
# RookChat Tool Contract Smoke Checks

These checks are manual/provider probes, not CI gates. They are for comparing
model behavior after deterministic schema/dispatcher contract tests pass.

## Required local setup

From `C:\UDEV\Rook`:

```powershell
scripts\deploy-local-testing.ps1 -UseRepoVenv
```

Open Rhino, open Grasshopper, open the Rook Chat panel, and select the target
model in the panel.

## Required one-box prompt

```text
Create a Grasshopper C# script component that outputs one box. After creating it, check the canvas for errors and fix the existing component if needed. Report what you created and the exact error-check result.
```

## Expected successful sequence

- The model calls `request_tools` with `group: gh_canvas` at most once.
- The model calls `gh_create_csharp_script`, or `gh_create_script` with `language: csharp`.
- The script creation call includes `code`.
- For the alias tools, the call includes `pins_in` and `pins_out`.
- The C# code is RhinoCode C# Script body-style code, not a `GH_Component` subclass.
- The model calls `gh_errors`.
- Final response reports the created component and the exact error/warning result.

## Provider notes

- `ollama_chat/qwen3:14b`: current local smoke baseline.
- One cloud model: sanity comparison for tool contract regressions.
- Experimental local models such as Gemma variants are exploratory only and are not merge gates.

## Failure classification

- Schema/contract bug: model-visible schema permits arguments the dispatcher rejects.
- Dispatcher bug: model-visible schema requires or permits a valid field, but dispatch rejects it unexpectedly.
- Model behavior: schema is correct and dispatcher feedback is actionable, but the model ignores it.
- UI feedback bug: tool result succeeds/fails but the panel card misrepresents status.

Do not tune prompts or weaken schemas to make a single weak model pass. Fix
contract bugs first, then compare model behavior.
````

- [ ] **Step 2: Commit Task 8**

Stage only:

```powershell
git add docs/rookchat-tool-contract-smoke.md
git commit -m "docs(chat): add tool contract smoke checklist"
```

---

## Task 9: Full Verification and Review Handoff

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused Python contract suites**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_rookchat_tool_contracts.py tests/test_rookchat_tool_schema_golden.py tests/test_rookchat_tool_transcripts.py tests/test_rookchat_gh_script_creation_parity.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 2: Run prompt and existing RookChat focused suites**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_chat_prompt_builder.py tests/test_chat_runner_model_tools.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: Run server contract subset for GH script creation**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests/test_server_contract_hardening.py -k "gh_create_script or gh_create_python_script or gh_create_csharp_script" -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 4: Run diff whitespace check**

Run:

```powershell
cd C:\UDEV\Rook
git diff --check origin/main...HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 5: Check branch movement before PR**

Run:

```powershell
cd C:\UDEV\Rook
git fetch origin
git rev-list --left-right --count origin/main...HEAD
git status --short --branch
```

Expected:

- left count may be `0`; if nonzero, stop and rebase before PR.
- right count includes the plan/spec plus implementation commits.
- working tree dirt is only:

```text
 M knowledge/contextual_mab.pkl
 M knowledge/substrate_observations.jsonl
```

- [ ] **Step 6: Request code review before PR**

Summarize:

- contract policy module;
- registry/cache normalization;
- fallback/local schema closure;
- dispatcher/schema parity tests;
- model-visible golden schema invariants;
- non-live transcript tests;
- optional provider smoke doc;
- tests run and results;
- no live Rhino/deploy claim.

Do not merge locally. Do not create a PR until review approves.

---

## Self-Review

### Spec Coverage

- Schema source-of-truth strategy: Task 2 introduces policy helpers; Tasks 3-6 enforce staged MCP/local/fallback rules and parity.
- Fallback/local/MCP/catalog parity: Tasks 3, 4, 5, and 6 cover cache, MCP conversion, fallback catalog, local catalog, and active registry exposure.
- Zero-argument tools: Tasks 1, 2, 3, 4, 5, and 6 require `gh_errors` and `STRICT_NO_ARGUMENT_BRIDGE_TOOLS` to be closed no-argument schemas.
- `additionalProperties` discipline: Tasks 1, 2, 3, 4, 5, and 6 close root schemas by default and avoid unallowlisted open roots.
- Dispatcher/schema parity: Task 5 locks critical GH script and verification tools.
- Model-visible golden transcript/schema tests: Task 6 covers active schema invariants; Task 7 covers transcript-style event boundaries.
- No broad prompt tuning: no task modifies persona prompts except existing tests may be run for regression.
- No metaharness integration: Task 8 documents future provider smoke only; no metaharness dependency is introduced.

### Placeholder Scan

No placeholder markers are intentionally present. Conditional instructions name exact fallback behavior and exact files.

### Type Consistency

The plan consistently uses:

- `normalize_litellm_tool_schema(schema: dict[str, Any]) -> dict[str, Any]`
- `normalize_catalog(catalog: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]`
- `audit_litellm_tool_schema(schema: dict[str, Any]) -> list[dict[str, str]]`
- `closed_no_arg_parameters() -> dict[str, Any]`
- `ZERO_ARGUMENT_TOOLS`
- existing `ChatRunner`, `ToolRegistry`, `_build_fallback_catalog`, and `_build_local_tool_catalog` anchors.

### Execution Boundary

This plan does not require live Rhino, local deploy, C# UI changes, Workbench changes, or production implementation before review. Implementation should begin only after this plan is approved and an execution skill is invoked.
