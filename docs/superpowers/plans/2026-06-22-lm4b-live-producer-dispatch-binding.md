# LM4B Live Producer Dispatch Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the LM4B named live-dispatch seam and prove a real `ToolDispatcher.dispatch` callable can drive one `artifact_producer` PlanGraph node without reaching Rhino.

**Architecture:** Add one tiny agent-layer module, `rook.agent.plan_graph_live_dispatch`, whose only public function forwards to the existing LM4A adapter with an injected dispatch callable. Add a Rhino-free contract test that instantiates a real `ToolDispatcher`, registers a synthetic local tool, patches `rook.agent.tool_dispatcher.call_rhino` as a sentinel, and proves both happy and returned-failure producer paths.

**Tech Stack:** Python 3.10+, pytest, existing `rook.agent.plan_graph_live`, existing `rook.agent.tool_dispatcher.ToolDispatcher`, existing pure PlanGraph seams.

## Global Constraints

- Work on branch `codex/lm4b-live-producer-dispatch-binding`; do not move commits back to `main`.
- Branch remains local until the PR gate; do not push or create a PR during implementation unless explicitly requested.
- Production module must be tiny: `run_live_producer_node(graph, node_id, dispatch)` forwards to `apply_live_producer_node(graph, node_id, dispatch)`.
- Production module must not import `ToolDispatcher`, `rook.agent.tool_dispatcher`, `rook.server`, `chat`, or `ChatRunner`.
- Only tests may import `ToolDispatcher`.
- Contract tests must instantiate `ToolDispatcher()` with no port, register synthetic local tool name `lm4b_live_producer_probe`, and pass `dispatcher.dispatch` into `run_live_producer_node`.
- Contract tests must patch the sentinel at the bound name `rook.agent.tool_dispatcher.call_rhino`, and the sentinel must raise if invoked.
- Both happy-path and error-path real-dispatcher contract tests must run with the sentinel installed.
- Error-path raw payload must include mutation evidence (`mutation.status == "created"` and/or component guid/repair anchor) so the producer role promotes to graph `succeeded` while preserving `tool_status == "failed"` and `verified is False`.
- Assert the synthetic local handler receives exactly the declared params and no accidental `port` key.
- Do not edit `learning/plan_graph*.py`, `agent/plan_graph_live.py`, `agent/tool_dispatcher.py`, `base_agent.py`, `spawn.py`, `chat_runner.py`, `targeting.py`, or `plan_graph_templates.py`.
- No scheduler, no production call-site wiring, no port/targeting policy, no template `execution_params` mutation, no real Rhino dispatch, no HTTP.
- Do not call or introduce `apply_tool_result` on this producer path.

---

## File Structure

- Create `mcp_server/src/rook/agent/plan_graph_live_dispatch.py`
  - Responsibility: named LM4B live-dispatch composition root.
  - Interface: `async run_live_producer_node(graph, node_id, dispatch) -> LiveProducerResult`.
  - Imports: runtime import only from `rook.agent.plan_graph_live`; optional type-only imports from `rook.agent.plan_graph_live` and `rook.learning.plan_graph`.
  - Forbidden: `ToolDispatcher`, `tool_dispatcher`, `rook.server`, `chat`, `ChatRunner`, `_producer_*`, wildcard imports.

- Create `mcp_server/tests/test_plan_graph_live_dispatch.py`
  - Responsibility: prove the production seam works with a real `ToolDispatcher.dispatch` callable, while remaining Rhino-free.
  - Contains: local raw-result builders, local producer graph fixture, `_Probe` synthetic local tool, no-Rhino sentinel, happy/error contract tests, AST import-boundary guard.
  - This file may import `ToolDispatcher`.

---

### Task 1: Add LM4B seam and real-dispatcher contract proof

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_live_dispatch.py`
- Create: `mcp_server/tests/test_plan_graph_live_dispatch.py`

**Interfaces:**
- Consumes: `rook.agent.plan_graph_live.apply_live_producer_node(graph, node_id, dispatch) -> LiveProducerResult`.
- Consumes: `rook.agent.tool_dispatcher.ToolDispatcher.register_local(name, handler)` in tests only.
- Consumes: `rook.agent.tool_dispatcher.ToolDispatcher.dispatch(name: str, params: dict) -> dict` in tests only.
- Produces: `rook.agent.plan_graph_live_dispatch.run_live_producer_node(graph, node_id, dispatch)`.

- [ ] **Step 1: Write the failing contract tests**

Create `mcp_server/tests/test_plan_graph_live_dispatch.py` with this full content:

```python
from __future__ import annotations

import asyncio
import ast
from pathlib import Path

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_dispatch import run_live_producer_node
import rook.agent.plan_graph_live_dispatch as _dispatch_mod
from rook.agent.tool_dispatcher import ToolDispatcher
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY


_DISPATCH_MODULE_PATH = Path(_dispatch_mod.__file__)
_ALLOWED_ROOK_IMPORTS = {
    "rook.agent.plan_graph_live",
    "rook.learning.plan_graph",
}
_FORBIDDEN_SOURCE_SUBSTRINGS = (
    "ToolDispatcher",
    "tool_dispatcher",
    "rook.server",
    "rook.agent.chat",
    "ChatRunner",
)

COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"
PROBE_TOOL_NAME = "lm4b_live_producer_probe"


def _usable_receipt() -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": "usable",
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "repair_anchor": {"component_guid": COMPONENT_GUID},
    }


def _errors_receipt() -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": "created_with_errors",
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "verification": {"status": "failed", "target_error_count": 1},
        "repair_anchor": {
            "component_guid": COMPONENT_GUID,
            "pins_out": [{"name": "A", "type": "double"}],
        },
    }


def _usable_raw() -> dict:
    return {
        "success": True,
        "data": {"verified": True, "script_receipt": _usable_receipt()},
    }


def _error_raw() -> dict:
    return {
        "success": False,
        "data": {"verified": False, "script_receipt": _errors_receipt()},
    }


def _producer_graph(declared_params: dict) -> PlanGraph:
    node = PlanGraphNode(
        id="create_script",
        intent="Create C# script component through real dispatcher contract proof",
        execution_ref=PROBE_TOOL_NAME,
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: declared_params,
        },
    )
    graph = PlanGraph(nodes={"create_script": node})
    node.status = "ready"
    return graph


class _Probe:
    def __init__(self, raw: dict):
        self.calls: list[dict] = []
        self._raw = raw

    async def __call__(self, **kwargs) -> dict:
        self.calls.append(dict(kwargs))
        return self._raw


async def _fail_call_rhino(*args, **kwargs):
    raise AssertionError("LM4B contract test must not call Rhino")


def _run_with_real_dispatcher(raw: dict, monkeypatch):
    monkeypatch.setattr("rook.agent.tool_dispatcher.call_rhino", _fail_call_rhino)

    declared_params = {
        "language": "csharp",
        "code": "// noop",
        "component_name": "C",
    }
    graph = _producer_graph(declared_params)
    probe = _Probe(raw)
    dispatcher = ToolDispatcher()
    dispatcher.register_local(PROBE_TOOL_NAME, probe)

    result = asyncio.run(
        run_live_producer_node(graph, "create_script", dispatcher.dispatch)
    )
    return result, probe, declared_params


def test_real_tool_dispatcher_dispatch_happy_path(monkeypatch):
    result, probe, declared_params = _run_with_real_dispatcher(_usable_raw(), monkeypatch)

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    assert probe.calls == [declared_params]
    assert "port" not in probe.calls[0]


def test_real_tool_dispatcher_dispatch_returned_failure_is_producer_success(monkeypatch):
    result, probe, declared_params = _run_with_real_dispatcher(_error_raw(), monkeypatch)

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    node = result.graph.nodes["create_script"]
    assert node.status == "succeeded"
    assert node.evidence is not None
    assert node.evidence.tool_status == "failed"
    assert node.evidence.verified is False
    assert node.evidence.receipt is not None
    assert node.evidence.receipt["mutation"]["status"] == "created"
    assert node.evidence.repair_anchor is not None
    assert node.evidence.repair_anchor["component_guid"] == COMPONENT_GUID
    assert probe.calls == [declared_params]
    assert "port" not in probe.calls[0]


def test_live_dispatch_module_import_boundary():
    source = _DISPATCH_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: list[str] = []

    for forbidden in _FORBIDDEN_SOURCE_SUBSTRINGS:
        assert forbidden not in source, (
            f"plan_graph_live_dispatch.py must not mention {forbidden!r}"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.append(module)
            for alias in node.names:
                assert alias.name != "*", "no star imports in the live dispatch seam"
                assert not alias.name.startswith("_producer"), (
                    f"dispatch seam must not import private runner helper {alias.name!r}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.Attribute):
            assert not node.attr.startswith("_producer"), (
                f"dispatch seam must not reach a private runner helper: .{node.attr}"
            )
        elif isinstance(node, ast.Name):
            assert not node.id.startswith("_producer"), (
                f"dispatch seam must not reference a private runner helper: {node.id}"
            )

    for module in imported_modules:
        if module.startswith("rook."):
            assert module in _ALLOWED_ROOK_IMPORTS, (
                f"unexpected rook import in live dispatch seam: {module!r}"
            )
```

- [ ] **Step 2: Run the new test file and verify it fails for the right reason**

Run from `C:\UDEV\Rook`:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_plan_graph_live_dispatch.py `
  -p no:cacheprovider -q
```

Expected: collection fails because `rook.agent.plan_graph_live_dispatch` does not exist yet. Acceptable failure text includes:

```text
ModuleNotFoundError: No module named 'rook.agent.plan_graph_live_dispatch'
```

If the test reaches Rhino or fails for a different reason, stop and inspect before implementing.

- [ ] **Step 3: Add the tiny production seam**

Create `mcp_server/src/rook/agent/plan_graph_live_dispatch.py` with this full content:

```python
"""LM4B live-dispatch composition root for one PlanGraph producer node."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_live import apply_live_producer_node

if TYPE_CHECKING:
    from rook.agent.plan_graph_live import LiveProducerResult
    from rook.learning.plan_graph import PlanGraph


async def run_live_producer_node(
    graph: "PlanGraph",
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> "LiveProducerResult":
    """Drive one live producer node through an injected dispatch callable."""
    return await apply_live_producer_node(graph, node_id, dispatch)
```

Do not add this function to `mcp_server/src/rook/agent/__init__.py`.

- [ ] **Step 4: Run the LM4B test file and verify it passes**

Run from `C:\UDEV\Rook`:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_plan_graph_live_dispatch.py `
  -p no:cacheprovider -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Run LM4A + LM4B live-adapter tests together**

Run from `C:\UDEV\Rook`:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_plan_graph_live.py `
  mcp_server/tests/test_plan_graph_live_dispatch.py `
  -p no:cacheprovider -q
```

Expected: 40 tests pass (37 existing LM4A tests + 3 LM4B tests). Acceptable output includes:

```text
40 passed
```

- [ ] **Step 6: Run the full non-live PlanGraph suite**

Run from `C:\UDEV\Rook` (repo root is required; some import-boundary guards use repo-root-relative paths):

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_plan_graph.py `
  mcp_server/tests/test_plan_graph_runner.py `
  mcp_server/tests/test_plan_graph_projection.py `
  mcp_server/tests/test_plan_graph_outcomes.py `
  mcp_server/tests/test_plan_graph_live.py `
  mcp_server/tests/test_plan_graph_live_dispatch.py `
  mcp_server/tests/test_plan_graph_templates.py `
  mcp_server/tests/test_plan_graph_walker.py `
  mcp_server/tests/test_plan_graph_verifiers.py `
  mcp_server/tests/test_plan_graph_bridge.py `
  -p no:cacheprovider -q
```

Expected: 231 tests pass (228 existing PlanGraph tests + 3 LM4B tests). Acceptable output includes:

```text
231 passed
```

If any import-boundary test reports `FileNotFoundError` for `mcp_server\src\...`, verify the command was run from `C:\UDEV\Rook`, not `C:\UDEV\Rook\mcp_server`.

- [ ] **Step 7: Run explicit production-boundary grep**

Run from `C:\UDEV\Rook`:

```powershell
Select-String -Path "mcp_server/src/rook/agent/plan_graph_live_dispatch.py" `
  -Pattern "ToolDispatcher|tool_dispatcher|rook\.server|rook\.agent\.chat|ChatRunner"
```

Expected: no output. This command intentionally uses regex alternation; do not add `-SimpleMatch`. The pattern deliberately omits `_producer` as a raw substring: the public seam name `run_live_producer_node` (and the forwarder target `apply_live_producer_node`) legitimately contain `_producer`, so a substring grep would false-positive. The private-helper ban (`_producer_*`) is enforced precisely by the AST guard `test_live_dispatch_module_import_boundary`, which matches identifiers with `startswith("_producer")` rather than a substring — that test is the authoritative boundary check.

- [ ] **Step 8: Confirm branch state and that planning docs are already committed**

The planning docs (spec status flip to `Approved` and this plan document) are committed **before** implementation begins, in a dedicated docs commit, so the plan is never left untracked during the implementation step. That docs commit is made prior to Step 1.

Run from `C:\UDEV\Rook`:

```powershell
git branch --show-current
git status --short
git diff --name-only origin/main..HEAD
git diff --name-only
```

Expected — only the two new Python files are still untracked (the spec and plan are already committed, not pending):

```text
codex/lm4b-live-producer-dispatch-binding
?? mcp_server/src/rook/agent/plan_graph_live_dispatch.py
?? mcp_server/tests/test_plan_graph_live_dispatch.py
```

`git diff --name-only origin/main..HEAD` lists only committed markdown docs (the design spec and this plan) before the implementation is staged; after Step 9 it will additionally include the two new Python files. The plan document must NOT appear under `??` here — if it does, the pre-implementation docs commit was skipped; make it before continuing. Do not push the branch.

- [ ] **Step 9: Commit the implementation locally**

Run from `C:\UDEV\Rook` after all tests pass:

```powershell
git add `
  mcp_server/src/rook/agent/plan_graph_live_dispatch.py `
  mcp_server/tests/test_plan_graph_live_dispatch.py

git commit -m "feat(lm4b): prove live producer dispatch binding"
```

Expected commit summary:

```text
2 files changed
create mode 100644 mcp_server/src/rook/agent/plan_graph_live_dispatch.py
create mode 100644 mcp_server/tests/test_plan_graph_live_dispatch.py
```

- [ ] **Step 10: Final verification after commit**

Run from `C:\UDEV\Rook`:

```powershell
git status --short
git log --oneline origin/main..HEAD
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_plan_graph.py `
  mcp_server/tests/test_plan_graph_runner.py `
  mcp_server/tests/test_plan_graph_projection.py `
  mcp_server/tests/test_plan_graph_outcomes.py `
  mcp_server/tests/test_plan_graph_live.py `
  mcp_server/tests/test_plan_graph_live_dispatch.py `
  mcp_server/tests/test_plan_graph_templates.py `
  mcp_server/tests/test_plan_graph_walker.py `
  mcp_server/tests/test_plan_graph_verifiers.py `
  mcp_server/tests/test_plan_graph_bridge.py `
  -p no:cacheprovider -q
```

Expected:

```text
# git status --short has no output
# git log includes, newest first:
feat(lm4b): prove live producer dispatch binding
docs(lm4b): correct Step 7 boundary grep (avoid _producer false-positive)
docs(lm4b): approve spec and add implementation plan
docs(lm4b): mark spec status as draft pending user review
docs(lm4b): live producer dispatch-binding design (real ToolDispatcher contract proof)
231 passed
```

The `docs(lm4b): approve spec and add implementation plan` commit is the pre-implementation docs commit from Step 8 (spec `Draft → Approved` plus this plan). The `docs(lm4b): correct Step 7 boundary grep` commit is a follow-up doc fix made during inline execution (the original Step 7 grep listed `_producer`, which false-positives on the public seam name). Do not push. Stop at the review/PR gate.
