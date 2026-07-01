# Capability Index + Progressive Tool Disclosure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax
> for tracking.

**Goal:** Give any MCP client (Codex etc.) a way to discover and invoke Rook's full tool surface from a
small `lean` floor — browse → search → read-schema → call — without a restart and without breaking the
`readonly` safety wall.

**Architecture:** A new pure `capability_index.py` builds a public-MCP facet (`McpCapabilityRecord`) over
the unprofiled tool surface, enriched with metadata and linked **by tool name** to the existing LM2A
`CapabilityRecord` (read-only). Four `rook_tools_*` meta-tools are intercepted in `call_tool` *before*
`_call_tool_dispatch`; `rook_tools_call` re-enters the normal policy path for its target so the readonly
wall applies unchanged.

**Tech Stack:** Python 3.12, `pytest` + `pytest-asyncio`, MCP `Tool` objects, frozen dataclasses,
stdlib `ast` (dispatchable-name scan + import-boundary test), `contextvars`.

## Global Constraints

- **Base is `origin/main`** (contains PR #382 profile campaign + LM2A capability modules). Work in this
  worktree/branch; **nothing is committed on `main`**.
- **No new Python dependency** — the arg validator is in-house; do not add `jsonschema`.
- **LM2A is read-only.** Do **not** modify or extend `rook.agent.capability_record` or
  `rook.agent.capability_inventory`. Consume them only.
- **`capability_index.py` import boundary:** may import the `CapabilityRecord` *type* and leaf data
  modules (`rook.mcp_tool_profiles`, `rook.agent.tool_groups`, `rook.context`). Must **not** import
  `rook.server`, `rook.agent.capability_inventory`, or agent runtime (`tool_dispatcher`, `tool_registry`,
  `chat.*`). It reads no `os.environ`.
- **Counts (origin/main base):** full `429 → 433`, lean `18 → 22`, readonly `145 → 149`.
- **Enforcement authority unchanged:** `readonly` blocking stays `tool_blocked()` against the audited
  `PUBLIC_READONLY_TOOL_NAMES`. Facet fields (`readonly_safe`, `mcp_dispatchable`) never gate calls.
- **`mcp_only` (LM2A) ≠ `mcp_dispatchable` (facet).** Never derive one from the other.
- **All pytest runs use the worktree venv:** `.venv/Scripts/python.exe -m pytest ...` (Task 0 creates it).
- **Every commit** ends with the **executing agent's** attribution trailer. For Claude execution (this
  inline run): `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. If a different agent (e.g.
  Codex) executes, use its own trailer or none — **never attach a false Claude co-author trailer** to a
  commit Claude did not author. (The per-task commit examples below show the Claude-execution form.)
- **`META_TOOL_NAMES = {"rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"}`** —
  the single source of truth for the meta-tool set (defined in `server.py`, Task 6).

---

## File Structure

- **Create** `mcp_server/src/rook/capability_index.py` — `McpCapabilityRecord`, `CapabilityIndex`,
  `build_index()`, the `ls`/`search`/`read` query methods, `validate_arguments()`. Pure; no `server.py`,
  no `capability_inventory`, no env.
- **Modify** `mcp_server/src/rook/server.py` — `_all_live_tools()`; `list_tools()` becomes a projection;
  the four `rook_tools_*` `Tool()` defs; `META_TOOL_NAMES`; `_dispatchable_tool_names()`;
  `_get_capability_index()` (memoized, LM2A-failure-tolerant); `_dispatch_origin` ContextVar +
  `_record_observation` reads it; `call_tool` meta-interception + `_handle_meta_tool()`.
- **Modify** `mcp_server/src/rook/mcp_tool_profiles.py` — add the four `rook_tools_*` to
  `PUBLIC_LEAN_TOOL_NAMES` and `PUBLIC_READONLY_TOOL_NAMES`.
- **Create** `mcp_server/tests/test_capability_index.py` — pure facet unit tests + import-boundary test.
- **Create** `mcp_server/tests/test_rook_tools_meta.py` — meta-tool behavior, dispatch safety, recording.
- **Modify** `mcp_server/tests/test_server_tool_profiles.py`, `mcp_server/tests/test_mcp_tool_profiles.py`
  — update pinned counts (429→433, 18→22, 145→149) and add `rook_tools_*` membership assertions.

---

## Task 0: Worktree venv preflight & clean baseline

**Files:** none (environment only).

- [ ] **Step 1: Create the worktree-local venv**

Run (from the worktree root):
```
uv venv .venv --python 3.12
.venv/Scripts/python.exe -m pip install -e "mcp_server[test]"
```

- [ ] **Step 2: Verify `rook` resolves to THIS worktree, not the main checkout**

Run:
```
.venv/Scripts/python.exe -c "import rook, pathlib; print(pathlib.Path(rook.__file__).resolve())"
```
Expected: a path under `...\.claude\worktrees\capability-index-progressive-disclosure\mcp_server\src\rook\__init__.py`.

- [ ] **Step 3: Baseline the tests we will touch (must pass before we change them)**

Run:
```
.venv/Scripts/python.exe -m pytest mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py -q
```
Expected: PASS (0 failures). If any fail on a clean base, STOP and report — do not build on a red baseline.

- [ ] **Step 4: Commit** (records the baseline decision; no code yet)

No commit for Task 0 (environment only). Proceed to Task 1.

---

## Task 1: `_all_live_tools()` unprofiled source (P1a)

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`list_tools()` around :13365–:13373)
- Test: `mcp_server/tests/test_server_tool_profiles.py`

**Interfaces:**
- Produces: `async def _all_live_tools() -> list[Tool]` — the deprecated-gated, **unprofiled** surface
  (429 today). `list_tools()` returns `filter_tools(_all_live_tools(), resolve_profile(os.environ))`.

- [ ] **Step 1: Write the failing test**

Add to `test_server_tool_profiles.py`:
```python
def test_all_live_tools_is_unprofiled_429(monkeypatch):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    # Even with a restrictive profile set, the unprofiled source is the full 429.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    names = {t.name for t in asyncio.run(server._all_live_tools())}
    assert len(names) == 429
    assert _GATED.isdisjoint(names)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_server_tool_profiles.py::test_all_live_tools_is_unprofiled_428 -v`
Expected: FAIL with `AttributeError: module 'rook.server' has no attribute '_all_live_tools'`.

- [ ] **Step 3: Implement the refactor**

In `server.py`, extract the body of `list_tools()` from the `all_tools = [ ... ]` construction through the
deprecated-interactive gate into a new function, leaving `list_tools()` as a thin profile projection:
```python
async def _all_live_tools() -> list[Tool]:
    all_tools = [ ... ]  # the existing large static Tool(...) list, unchanged
    if not _interactive_command_learning_enabled():
        return [t for t in all_tools if t.name not in _DEPRECATED_INTERACTIVE_COMMAND_TOOLS]
    return all_tools

async def list_tools() -> list[Tool]:
    return filter_tools(await _all_live_tools(), resolve_profile(os.environ))
```
(Only move code; do not change any `Tool(...)` definition.)

- [ ] **Step 4: Run the Task-1 test + the existing profile snapshots (behavior-preserving)**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_server_tool_profiles.py -v`
Expected: the new test PASSES and `test_full_surface_is_428`, `test_lean_surface_is_exactly_18`,
`test_readonly_surface_is_exactly_145` still PASS (projection is behavior-identical).

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/server.py mcp_server/tests/test_server_tool_profiles.py
git commit -m "feat(capability-index): factor unprofiled _all_live_tools() source

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `McpCapabilityRecord` + `CapabilityIndex` types (import-boundary enforced)

**Files:**
- Create: `mcp_server/src/rook/capability_index.py`
- Test: `mcp_server/tests/test_capability_index.py`

**Interfaces:**
- Produces: frozen `McpCapabilityRecord` (fields per spec §4.2); frozen `CapabilityIndex` holding
  `records: tuple[McpCapabilityRecord, ...]` and `by_name: Mapping[str, McpCapabilityRecord]`.

- [ ] **Step 1: Write the failing tests** (fields + frozen + import boundary)

Create `test_capability_index.py`:
```python
from __future__ import annotations
import ast, os, subprocess, sys
from pathlib import Path
import pytest
from rook.agent.capability_record import CapabilityRecord
from rook.capability_index import McpCapabilityRecord, CapabilityIndex


def test_record_is_frozen_and_has_fields():
    rec = McpCapabilityRecord(
        name="t", path="/x/t", domain="x", groups=(), summary="s", description="d",
        readonly_safe=True, mcp_dispatchable=True, input_schema={}, agent_record=None,
    )
    assert rec.name == "t" and rec.agent_record is None
    with pytest.raises(Exception):
        rec.name = "other"  # frozen


def test_index_indexes_by_name():
    rec = McpCapabilityRecord(
        name="t", path="/x/t", domain="x", groups=(), summary="s", description="d",
        readonly_safe=False, mcp_dispatchable=True, input_schema={}, agent_record=None,
    )
    idx = CapabilityIndex(records=(rec,), by_name={"t": rec})
    assert idx.by_name["t"] is rec


def _direct_imports(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mods.add(f'{"." * node.level}{node.module or ""}')
        elif isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
    return mods


def test_capability_index_import_boundary():
    # Allowed: CapabilityRecord type + leaf data modules. Forbidden: server,
    # capability_inventory, agent runtime.
    imports = _direct_imports("mcp_server/src/rook/capability_index.py")
    forbidden = {
        "rook.server", "rook.agent.capability_inventory",
        "rook.agent.tool_dispatcher", "rook.agent.tool_registry",
    }
    assert imports.isdisjoint(forbidden), f"forbidden imports present: {imports & forbidden}"


def test_importing_capability_index_does_not_load_server_or_inventory():
    env = os.environ.copy()
    src = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    probe = (
        "import sys, rook.capability_index\n"
        "bad = {'rook.server','rook.agent.capability_inventory'} & set(sys.modules)\n"
        "raise SystemExit('loaded: ' + ','.join(sorted(bad)) if bad else 0)\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, env=env)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_capability_index.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rook.capability_index'`.

- [ ] **Step 3: Implement the types**

Create `capability_index.py`:
```python
"""Public-MCP capability facet (read-only link to the LM2A agent facet)."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from rook.agent.capability_record import CapabilityRecord  # type only; stdlib-only module


@dataclass(frozen=True)
class McpCapabilityRecord:
    name: str
    path: str
    domain: str
    groups: tuple[str, ...]
    summary: str
    description: str
    readonly_safe: bool
    mcp_dispatchable: bool
    input_schema: Mapping[str, Any]
    agent_record: CapabilityRecord | None


@dataclass(frozen=True)
class CapabilityIndex:
    records: tuple[McpCapabilityRecord, ...]
    by_name: Mapping[str, McpCapabilityRecord]
```

- [ ] **Step 4: Run to confirm pass**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_capability_index.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/capability_index.py mcp_server/tests/test_capability_index.py
git commit -m "feat(capability-index): McpCapabilityRecord + CapabilityIndex types (import boundary)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `build_index()` — enrichment + LM2A link by name

**Files:**
- Modify: `mcp_server/src/rook/capability_index.py`
- Test: `mcp_server/tests/test_capability_index.py`

**Interfaces:**
- Consumes: `McpCapabilityRecord`, `CapabilityRecord` (type), `PUBLIC_READONLY_TOOL_NAMES`, `TOOL_GROUPS`.
- Produces: `def build_index(tools, agent_records, dispatchable_names) -> CapabilityIndex` where
  `tools: list[Tool]`, `agent_records: Mapping[str, CapabilityRecord]`, `dispatchable_names: frozenset[str]`.
- Produces: `def _domain_for(name) -> str`, `def _summary_of(description) -> str` (helpers).

- [ ] **Step 1: Write the failing tests**

Add to `test_capability_index.py`:
```python
from types import SimpleNamespace
from rook.capability_index import build_index
from rook.mcp_tool_profiles import PUBLIC_READONLY_TOOL_NAMES


def _tool(name, desc="Do a thing. Second sentence.", schema=None):
    return SimpleNamespace(name=name, description=desc, inputSchema=schema or {"type": "object"})


def _agent_rec(name, dispatch_path="bridge_route", mcp_only=False):
    return CapabilityRecord(name=name, visibility="local_visible", tiers=(), groups=(),
                            dispatch_path=dispatch_path, has_schema=True, risk=(),
                            no_argument=False, mcp_only=mcp_only)


def test_build_index_covers_all_tools_and_links_agent_records():
    tools = [_tool("rhino_director_preview_motion"), _tool("rhino_objects")]
    agent = {"rhino_objects": _agent_rec("rhino_objects")}
    idx = build_index(tools, agent, frozenset({"rhino_director_preview_motion", "rhino_objects"}))
    assert {r.name for r in idx.records} == {"rhino_director_preview_motion", "rhino_objects"}
    assert idx.by_name["rhino_objects"].agent_record.name == "rhino_objects"   # linked by name
    assert idx.by_name["rhino_director_preview_motion"].agent_record is None    # absent -> None


def test_readonly_safe_matches_audited_allowlist():
    name = next(iter(PUBLIC_READONLY_TOOL_NAMES))
    idx = build_index([_tool(name), _tool("rhino_create")], {}, frozenset({name, "rhino_create"}))
    assert idx.by_name[name].readonly_safe is True
    assert idx.by_name["rhino_create"].readonly_safe is False


def test_mcp_dispatchable_is_from_dispatchable_names_not_agent_mcp_only():
    # A tool with agent_mcp_only=True but NOT in dispatchable_names must be mcp_dispatchable=False,
    # and vice-versa — the two axes never derive from each other.
    tools = [_tool("a"), _tool("b")]
    agent = {"a": _agent_rec("a", mcp_only=True), "b": _agent_rec("b", mcp_only=False)}
    idx = build_index(tools, agent, frozenset({"b"}))  # only b is dispatchable
    assert idx.by_name["a"].mcp_dispatchable is False and idx.by_name["a"].agent_record.mcp_only is True
    assert idx.by_name["b"].mcp_dispatchable is True and idx.by_name["b"].agent_record.mcp_only is False


def test_build_index_tolerates_empty_agent_records():
    idx = build_index([_tool("x")], {}, frozenset({"x"}))
    assert idx.by_name["x"].agent_record is None  # LM2A "unavailable" still yields a working index


def test_summary_is_first_sentence():
    idx = build_index([_tool("x", desc="First. Second.")], {}, frozenset({"x"}))
    assert idx.by_name["x"].summary == "First."
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_capability_index.py -k build_index -v`
Expected: FAIL with `ImportError: cannot import name 'build_index'`.

- [ ] **Step 3: Implement `build_index` + helpers**

Append to `capability_index.py`:
```python
from rook.mcp_tool_profiles import PUBLIC_READONLY_TOOL_NAMES
from rook.agent.tool_groups import TOOL_GROUPS

_DOMAIN_PREFIXES = (  # longest-prefix wins
    ("rhino_director_", "director"), ("rhino_vision_", "vision"),
    ("rhino_video_", "video"), ("rhino_2d_to_3d_", "vision"),
    ("rookbim_", "bim"), ("scene_", "scene"), ("rc_", "rc"), ("road_", "rc"),
    ("gh_", "gh"), ("rhino_", "rhino"), ("knowledge_", "knowledge"),
    ("session_", "session"), ("rook_tools_", "meta"),
)

def _domain_for(name: str) -> str:
    for prefix, domain in _DOMAIN_PREFIXES:
        if name.startswith(prefix):
            return domain
    return "other"

def _summary_of(description: str) -> str:
    text = (description or "").strip()
    dot = text.find(". ")
    return (text[: dot + 1] if dot != -1 else text.split("\n", 1)[0]).strip()

def _groups_for(name: str) -> tuple[str, ...]:
    return tuple(sorted(g for g, tools in TOOL_GROUPS.items() if name in tools))

def build_index(tools, agent_records, dispatchable_names) -> CapabilityIndex:
    records = []
    for tool in tools:
        name = tool.name
        domain = _domain_for(name)
        groups = _groups_for(name)
        head = f"/{domain}" + (f"/{groups[0]}" if groups else "")
        records.append(McpCapabilityRecord(
            name=name, path=f"{head}/{name}", domain=domain, groups=groups,
            summary=_summary_of(tool.description), description=tool.description or "",
            readonly_safe=name in PUBLIC_READONLY_TOOL_NAMES,
            mcp_dispatchable=name in dispatchable_names,
            input_schema=tool.inputSchema, agent_record=agent_records.get(name),
        ))
    records = tuple(records)
    return CapabilityIndex(records=records, by_name={r.name: r for r in records})
```

- [ ] **Step 4: Run to confirm pass**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_capability_index.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/capability_index.py mcp_server/tests/test_capability_index.py
git commit -m "feat(capability-index): build_index with enrichment + read-only LM2A link by name

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `ls` / `search` / `read` query methods + arg validator

**Files:**
- Modify: `mcp_server/src/rook/capability_index.py`
- Test: `mcp_server/tests/test_capability_index.py`

**Interfaces (pure — `scope_readonly` is an argument; the module reads no env):**
- `CapabilityIndex.ls(self, path="/", depth=1, *, scope_readonly=False) -> dict`
- `CapabilityIndex.search(self, query, *, domain=None, scope_readonly=False, limit=10) -> list[dict]`
- `CapabilityIndex.read(self, name) -> dict | None`
- `def validate_arguments(schema: Mapping, arguments: Mapping) -> list[str]` (empty ⇒ valid)

- [ ] **Step 1: Write the failing tests**

Add to `test_capability_index.py`:
```python
from rook.capability_index import validate_arguments


def _idx():
    tools = [_tool("rhino_director_preview_motion", "Preview a camera move."),
             _tool("rhino_create", "Create geometry."),
             _tool("rhino_objects", "List objects.")]
    # NOTE: rhino_objects is readonly-safe on the real PUBLIC_READONLY_TOOL_NAMES allowlist;
    # rhino_create and rhino_director_preview_motion are not.
    return build_index(tools, {}, frozenset({t.name for t in tools}))


def test_search_finds_director_and_respects_readonly_scope():
    idx = _idx()
    assert any(r["name"] == "rhino_director_preview_motion"
               for r in idx.search("director preview", scope_readonly=False))
    # readonly scope hides non-readonly_safe tools:
    ro_names = {r["name"] for r in idx.search("director preview", scope_readonly=True)}
    assert "rhino_director_preview_motion" not in ro_names


def test_ls_returns_compact_entries_without_schema():
    idx = _idx()
    out = idx.ls("/rhino", depth=2)
    assert all("input_schema" not in e for e in out["entries"])


def test_read_returns_schema_none_for_unknown_and_scopes_readonly():
    idx = _idx()
    assert idx.read("rhino_create")["input_schema"] is not None
    assert idx.read("nope") is None
    # readonly scope hides a non-readonly_safe tool's schema, but keeps a safe one:
    assert idx.read("rhino_create", scope_readonly=True) is None
    assert idx.read("rhino_objects", scope_readonly=True) is not None


def test_validate_arguments_enforces_subset_and_passes_through_rest():
    schema = {"type": "object", "required": ["n"],
              "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 3},
                             "mode": {"type": "string", "enum": ["a", "b"]},
                             "tags": {"type": "array", "items": {"type": "string"}}}}
    assert validate_arguments(schema, {"n": 2, "mode": "a", "tags": ["x"]}) == []
    assert any("n" in e for e in validate_arguments(schema, {}))               # missing required
    assert any("n" in e for e in validate_arguments(schema, {"n": "x"}))        # wrong type
    assert any("n" in e for e in validate_arguments(schema, {"n": 9}))          # out of range
    assert any("mode" in e for e in validate_arguments(schema, {"n": 1, "mode": "z"}))  # enum
    # Unsupported keyword (minItems) is NOT enforced -> passes through:
    schema2 = {"type": "object", "properties": {"tags": {"type": "array", "minItems": 5}}}
    assert validate_arguments(schema2, {"tags": []}) == []
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_capability_index.py -k "search or ls or read or validate" -v`
Expected: FAIL (`AttributeError`/`ImportError`).

- [ ] **Step 3: Implement the query methods + validator**

Add methods to `CapabilityIndex` and a module-level `validate_arguments`:
```python
    def _visible(self, *, scope_readonly: bool):
        for r in self.records:
            if not r.mcp_dispatchable:            # visible => mcp-dispatchable
                continue
            if scope_readonly and not r.readonly_safe:
                continue
            yield r

    def ls(self, path="/", depth=1, *, scope_readonly=False) -> dict:
        p = path if path.endswith("/") else path + "/"
        entries, children = [], set()
        for r in self._visible(scope_readonly=scope_readonly):
            if not (r.path + "").startswith(p if p != "/" else "/"):
                continue
            rest = r.path[len(p):] if p != "/" else r.path.lstrip("/")
            if rest.count("/") < depth:
                entries.append({"name": r.name, "path": r.path, "domain": r.domain,
                                "groups": list(r.groups), "readonly_safe": r.readonly_safe,
                                "summary": r.summary})
            else:
                children.add(p + "/".join(rest.split("/")[:depth]))
        return {"path": path, "entries": entries, "children": sorted(children)}

    def search(self, query, *, domain=None, scope_readonly=False, limit=10) -> list[dict]:
        terms = [t for t in query.lower().split() if t]
        scored = []
        for r in self._visible(scope_readonly=scope_readonly):
            if domain and r.domain != domain:
                continue
            hay = f"{r.name} {r.summary} {r.domain} {' '.join(r.groups)}".lower()
            score = sum(hay.count(t) for t in terms) + (2 if any(t in r.name.lower() for t in terms) else 0)
            if score:
                scored.append((score, r))
        scored.sort(key=lambda sr: (-sr[0], sr[1].name))
        return [{"name": r.name, "path": r.path, "domain": r.domain,
                 "readonly_safe": r.readonly_safe, "summary": r.summary} for _, r in scored[:limit]]

    def read(self, name, *, scope_readonly=False) -> dict | None:
        r = self.by_name.get(name)
        if r is None or not r.mcp_dispatchable:
            return None
        if scope_readonly and not r.readonly_safe:
            return None   # readonly clients must not read blocked-mutator schemas
        ar = r.agent_record
        return {"name": r.name, "path": r.path, "domain": r.domain, "groups": list(r.groups),
                "description": r.description, "readonly_safe": r.readonly_safe,
                "mcp_dispatchable": r.mcp_dispatchable, "input_schema": dict(r.input_schema),
                "agent_dispatchable": (ar is not None and ar.dispatch_path is not None),
                "agent_visibility": (ar.visibility if ar else None),
                "agent_mcp_only": (ar.mcp_only if ar else None)}


_JSON_TYPES = {"string": str, "integer": int, "number": (int, float),
               "boolean": bool, "array": list, "object": dict}

def validate_arguments(schema, arguments) -> list[str]:
    errors: list[str] = []
    props = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
    for req in schema.get("required", []) or []:
        if req not in arguments:
            errors.append(f"{req}: required field missing")
    for key, spec in props.items():
        if key not in arguments or not isinstance(spec, Mapping):
            continue
        val = arguments[key]
        t = spec.get("type")
        py = _JSON_TYPES.get(t)
        if py and not isinstance(val, py) or (t == "integer" and isinstance(val, bool)):
            errors.append(f"{key}: expected {t}")
            continue
        if "enum" in spec and val not in spec["enum"]:
            errors.append(f"{key}: must be one of {spec['enum']}")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if "minimum" in spec and val < spec["minimum"]:
                errors.append(f"{key}: below minimum {spec['minimum']}")
            if "maximum" in spec and val > spec["maximum"]:
                errors.append(f"{key}: above maximum {spec['maximum']}")
        if t == "array" and isinstance(val, list):
            item_t = (spec.get("items") or {}).get("type")
            ipy = _JSON_TYPES.get(item_t)
            if ipy and any(not isinstance(v, ipy) for v in val):
                errors.append(f"{key}: array items must be {item_t}")
    return errors
```

- [ ] **Step 4: Run to confirm pass**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_capability_index.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/capability_index.py mcp_server/tests/test_capability_index.py
git commit -m "feat(capability-index): ls/search/read (scope_readonly arg) + in-house arg validator

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Startup wiring — `dispatchable_names` (∪ meta-tools), read-only LM2A inventory, memoized index

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_rook_tools_meta.py` (new)

**Interfaces:**
- Produces: `META_TOOL_NAMES: frozenset[str]`; `def _dispatchable_tool_names() -> frozenset[str]`
  (AST scan of `_call_tool_dispatch` `case "<name>":` labels **∪ `META_TOOL_NAMES`**);
  `async def _get_capability_index() -> CapabilityIndex` (memoized; LM2A failure ⇒ `agent_records={}`).

- [ ] **Step 1: Write the failing tests**

Create `test_rook_tools_meta.py`:
```python
import asyncio
from rook import server

def test_dispatchable_names_include_meta_and_a_known_native():
    names = server._dispatchable_tool_names()
    assert server.META_TOOL_NAMES <= names            # meta-tools unioned in (P1b)
    assert "rhino_objects" in names                    # a known dispatcher case label

def test_dispatchable_names_include_or_case_arms():
    # server.py has: case "rhino_command_knowledge" | "rhino_knowledge_query":
    names = server._dispatchable_tool_names()
    assert "rhino_command_knowledge" in names and "rhino_knowledge_query" in names

def test_capability_index_covers_full_unprofiled_surface(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")  # profile must NOT shrink the index
    idx = asyncio.run(server._get_capability_index())
    live = {t.name for t in asyncio.run(server._all_live_tools())}
    assert {r.name for r in idx.records} == live
    assert idx.by_name["rhino_director_preview_motion"].mcp_dispatchable is True

def test_index_survives_lm2a_failure(monkeypatch):
    server._reset_capability_index_cache()  # test hook (Step 3)
    import rook.agent.capability_inventory as inv
    monkeypatch.setattr(inv, "collect_live_sources", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    idx = asyncio.run(server._get_capability_index())
    assert all(r.agent_record is None for r in idx.records)  # tolerated -> agent_records = {}
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rook_tools_meta.py -v`
Expected: FAIL (`AttributeError: ... has no attribute '_dispatchable_tool_names'`).

- [ ] **Step 3: Implement wiring in `server.py`**

```python
import ast as _ast, inspect as _inspect, textwrap as _textwrap
from rook.capability_index import build_index
from rook.agent.tool_registry import build_catalog_from_mcp_tools

META_TOOL_NAMES = frozenset({"rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"})
_CAPABILITY_INDEX = None

def _reset_capability_index_cache() -> None:  # test hook
    global _CAPABILITY_INDEX
    _CAPABILITY_INDEX = None

def _dispatchable_tool_names() -> frozenset[str]:
    src = _textwrap.dedent(_inspect.getsource(_call_tool_dispatch))
    tree = _ast.parse(src)
    labels: set[str] = set()
    # ast.walk recurses into MatchOr.patterns, so `case "a" | "b":` OR-arms are captured too.
    for node in _ast.walk(tree):
        if isinstance(node, _ast.MatchValue) and isinstance(node.value, _ast.Constant) \
                and isinstance(node.value.value, str):
            labels.add(node.value.value)
    return frozenset(labels) | META_TOOL_NAMES

def _collect_agent_records(tools) -> dict:
    # Read-only LM2A. Freshly built catalog from the UNPROFILED surface — no cache, no profile filter.
    try:
        from rook.agent.capability_inventory import build_inventory, collect_live_sources
        catalog = build_catalog_from_mcp_tools(tools)
        inv = build_inventory(collect_live_sources(), catalog)
        return {r.name: r for r in inv.records}
    except Exception:
        logger.exception("LM2A inventory unavailable; capability index will omit agent_record links")
        return {}

async def _get_capability_index():
    global _CAPABILITY_INDEX
    if _CAPABILITY_INDEX is None:
        tools = await _all_live_tools()
        _CAPABILITY_INDEX = build_index(tools, _collect_agent_records(tools), _dispatchable_tool_names())
    return _CAPABILITY_INDEX
```

- [ ] **Step 4: Run to confirm pass**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rook_tools_meta.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/server.py mcp_server/tests/test_rook_tools_meta.py
git commit -m "feat(capability-index): startup wiring (dispatchable_names union meta, read-only LM2A)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Four `rook_tools_*` Tool() defs + profile membership + count updates

**Files:**
- Modify: `mcp_server/src/rook/server.py` (add four `Tool(...)` defs inside the `_all_live_tools()` list)
- Modify: `mcp_server/src/rook/mcp_tool_profiles.py` (`PUBLIC_LEAN_TOOL_NAMES`, `PUBLIC_READONLY_TOOL_NAMES`)
- Test: `mcp_server/tests/test_server_tool_profiles.py`, `mcp_server/tests/test_mcp_tool_profiles.py`

- [ ] **Step 1: Update the pinned-count tests to the new truth (fail first)**

In `test_server_tool_profiles.py`: `429 → 433` (in `test_full_surface_is_429_and_gates_deprecated` and
`test_readonly_partition_over_live_surface`), `18 → 22` (`test_lean_surface_is_exactly_18`),
`145 → 149` (`test_readonly_surface_is_exactly_145`); rename the count-bearing functions to the new
numbers (e.g. `_is_429` → `_is_433`). Add:
```python
def test_meta_tools_present_in_all_profiles(monkeypatch):
    for prof in (None, "full", "lean", "readonly"):
        names = _list_names(monkeypatch, prof)
        assert {"rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"} <= names
```
In `test_mcp_tool_profiles.py::test_set_sizes_are_pinned`: `18 → 22`, `145 → 149`.

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py -v`
Expected: FAIL (counts mismatch / meta tools absent).

- [ ] **Step 3: Add the four `Tool(...)` defs and profile membership**

In `server.py` `_all_live_tools()` static list, add four `Tool(...)` entries (see schemas below). In
`mcp_tool_profiles.py`, add the four names to both `PUBLIC_LEAN_TOOL_NAMES` and
`PUBLIC_READONLY_TOOL_NAMES`.

`rook_tools_ls`: `{path?: string, depth?: integer}`. `rook_tools_search`:
`{query: string(required), domain?: string, readonly_safe?: boolean, limit?: integer}`.
`rook_tools_read`: `{name: string(required)}`. `rook_tools_call`:
`{name: string(required), arguments?: object}`. Descriptions state "browse/search/read-schema/invoke the
Rook tool catalog" so `search` matches domain keywords.

- [ ] **Step 4: Run to confirm pass**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/server.py mcp_server/src/rook/mcp_tool_profiles.py mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py
git commit -m "feat(capability-index): add rook_tools_* defs + profile membership (18->22,145->149,429->433)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: `_dispatch_origin` ContextVar + `_record_observation` reads it

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Test: `mcp_server/tests/test_rook_tools_meta.py`

**Interfaces:**
- Produces: `_dispatch_origin: ContextVar[str]` (default `"native"`); `_record_observation` records the
  current origin (its recorded Observation carries an `origin` field / metric tag).

- [ ] **Step 1: Write the failing test**
```python
def test_dispatch_origin_defaults_native_and_is_readable():
    from rook.server import _dispatch_origin
    assert _dispatch_origin.get() == "native"
    tok = _dispatch_origin.set("meta")
    try:
        assert _dispatch_origin.get() == "meta"
    finally:
        _dispatch_origin.reset(tok)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rook_tools_meta.py -k dispatch_origin -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**
```python
from contextvars import ContextVar
_dispatch_origin: ContextVar[str] = ContextVar("_dispatch_origin", default="native")
```
In `_record_observation`, read `origin = _dispatch_origin.get()` and include it on the recorded
Observation (add an `origin` field / metric attribute; default `"native"` preserves existing behavior).

- [ ] **Step 4: Run to confirm pass**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rook_tools_meta.py -k dispatch_origin -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/server.py mcp_server/tests/test_rook_tools_meta.py
git commit -m "feat(capability-index): _dispatch_origin ContextVar recorded by _record_observation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: `call_tool` meta-interception + `rook_tools_call` guards & re-entry (load-bearing)

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`call_tool` at :20925, after the wall at :20929)
- Test: `mcp_server/tests/test_rook_tools_meta.py`

**Interfaces:**
- Consumes: `_get_capability_index`, `validate_arguments`, `tool_blocked`, `profile_blocked_envelope`,
  `resolve_profile`, `Profile`, `_dispatch_origin`, `META_TOOL_NAMES`, `_format_tool_result`, `call_tool`.
- Produces: `async def _handle_meta_tool(name, arguments, profile) -> list[TextContent]`.

- [ ] **Step 1: Write the failing tests** (mirror `_call_text` from `test_server_tool_profiles.py`)
```python
import json
from rook import server

def _text(name, args=None):
    return asyncio.run(server.call_tool(name, args or {}))[0].text

def _stub_dispatch(monkeypatch):
    # requires_rhino=False routes call_tool straight to _call_tool_dispatch (no Rhino/route
    # resolution needed), so the meta re-entry actually reaches the stub.
    from types import SimpleNamespace
    monkeypatch.setattr(server.targeting, "policy_for_tool",
                        lambda name: SimpleNamespace(requires_rhino=False))
    async def ok(name, arguments):
        return {"success": True, "data": {"dispatched": name, "origin": server._dispatch_origin.get()}}
    monkeypatch.setattr(server, "_call_tool_dispatch", ok)

def test_lean_reach_search_read_call(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    _stub_dispatch(monkeypatch)
    found = json.loads(_text("rook_tools_search", {"query": "director preview"}))
    assert any(e["name"] == "rhino_director_preview_motion" for e in found)
    schema = json.loads(_text("rook_tools_read", {"name": "rhino_director_preview_motion"}))
    assert "input_schema" in schema
    called = json.loads(_text("rook_tools_call",
                              {"name": "rhino_director_preview_motion",
                               "arguments": {"timeline": {}, "motion": []}}))  # satisfies required timeline+motion
    assert called["dispatched"] == "rhino_director_preview_motion" and called["origin"] == "meta"

def test_readonly_block_wall_before_validation(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    _stub_dispatch(monkeypatch)
    # invalid args, but the blocked target must still return tool_profile_blocked (wall first):
    text = _text("rook_tools_call",
                 {"name": "rhino_director_preview_motion", "arguments": {"bogus": 1}})
    assert "tool_profile_blocked" in text

def test_recursion_guard(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    assert "error" in _text("rook_tools_call", {"name": "rook_tools_ls"}).lower()

def test_non_dispatchable_refused(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    _stub_dispatch(monkeypatch)
    assert "error" in _text("rook_tools_call", {"name": "definitely_not_a_tool"}).lower()

def test_meta_layer_never_self_records(monkeypatch):
    # Meta tools are intercepted BEFORE _call_tool_dispatch's recording tail, so they must never
    # appear as observations. (Target-under-real-name + origin=meta is covered by test_lean_reach:
    # the stub reads _dispatch_origin at dispatch time; the real recording tail is exercised by a
    # requires_rhino integration run, out of scope for this unit suite.)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    _stub_dispatch(monkeypatch)
    recorded = []
    monkeypatch.setattr(server, "_record_observation", lambda name, *a, **k: recorded.append(name))
    _text("rook_tools_search", {"query": "objects"})
    _text("rook_tools_read", {"name": "rhino_objects"})
    _text("rook_tools_call", {"name": "rhino_objects", "arguments": {}})
    assert "rook_tools_call" not in recorded
    assert "rook_tools_search" not in recorded and "rook_tools_read" not in recorded


def test_meta_dispatch_records_target_once_with_origin_meta(monkeypatch):
    # Real non-Rhino target: rhino_instances -> targeting.instances_result() needs no live Rhino, so the
    # REAL _call_tool_dispatch recording tail runs. Do NOT stub dispatch.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    recorded = []
    monkeypatch.setattr(server, "_record_observation",
                        lambda name, *a, **k: recorded.append((name, server._dispatch_origin.get())))
    _text("rook_tools_call", {"name": "rhino_instances", "arguments": {}})
    assert recorded == [("rhino_instances", "meta")]   # one record, target name, tagged meta

def test_readonly_blocked_meta_call_has_no_side_effects(monkeypatch):
    # Mirror test_blocked_readonly_call_has_no_side_effects for the meta path.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    flags = {"observed": False, "dispatched": False}
    monkeypatch.setattr(server, "_record_observation", lambda *a, **k: flags.__setitem__("observed", True))
    async def _spy(*a, **k): flags["dispatched"] = True; return {"success": True, "data": {}}
    monkeypatch.setattr(server, "_call_tool_dispatch", _spy)
    assert "tool_profile_blocked" in _text("rook_tools_call",
                                           {"name": "rhino_create", "arguments": {}})
    assert flags == {"observed": False, "dispatched": False}
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rook_tools_meta.py -v`
Expected: FAIL (meta tools currently fall through to `_call_tool_dispatch`'s `case _` → "Unknown tool").

- [ ] **Step 3: Implement interception in `call_tool` + `_handle_meta_tool`**

In `call_tool`, immediately **after** the wall block (`if tool_blocked(name, _active_profile): ...` at
:20929) and **before** the deprecated-interactive branch:
```python
    if name in META_TOOL_NAMES:
        return await _handle_meta_tool(name, arguments, _active_profile)
```
Add:
```python
async def _handle_meta_tool(name, arguments, profile):
    index = await _get_capability_index()
    scope_readonly = (profile == Profile.READONLY)
    if name == "rook_tools_ls":
        return _format_tool_result({"success": True, "data": index.ls(
            arguments.get("path", "/"), int(arguments.get("depth", 1) or 1), scope_readonly=scope_readonly)})
    if name == "rook_tools_search":
        # readonly profile ALWAYS forces safe-only discovery; the readonly_safe arg may only NARROW
        # further (True), never widen a readonly client past the wall.
        want_safe = scope_readonly or bool(arguments.get("readonly_safe"))
        return _format_tool_result({"success": True, "data": index.search(
            arguments.get("query", ""), domain=arguments.get("domain"),
            scope_readonly=want_safe, limit=int(arguments.get("limit", 10) or 10))})
    if name == "rook_tools_read":
        rec = index.read(arguments.get("name", ""), scope_readonly=scope_readonly)
        if rec is None:
            return _format_tool_result({"success": False, "data": {"error": "unknown_or_non_dispatchable",
                                                                   "name": arguments.get("name")}})
        return _format_tool_result({"success": True, "data": rec})
    # rook_tools_call — guards in order: recursion -> wall(target) -> mcp_dispatchable -> validation
    target = arguments.get("name", "")
    targs = arguments.get("arguments", {}) or {}
    if target in META_TOOL_NAMES:
        return _format_tool_result({"success": False, "data": {"error": "meta_recursion_forbidden",
                                                               "name": target}})
    if tool_blocked(target, profile):                              # WALL BEFORE VALIDATION (P1)
        return _format_tool_result(profile_blocked_envelope(target, profile))
    rec = index.read(target)
    if rec is None:                                                # covers unknown + non-dispatchable
        return _format_tool_result({"success": False, "data": {"error": "not_mcp_dispatchable",
                                                               "name": target}})
    verrs = validate_arguments(rec["input_schema"], targs)
    if verrs:
        return _format_tool_result({"success": False, "data": {"error": "invalid_arguments",
                                                               "name": target, "fields": verrs}})
    token = _dispatch_origin.set("meta")                           # tag target obs as meta-originated
    try:
        return await call_tool(target, targs)                      # re-enter full policy path
    finally:
        _dispatch_origin.reset(token)
```

- [ ] **Step 4: Run the full new suite + the profile suite (no regressions)**

Run:
```
.venv/Scripts/python.exe -m pytest mcp_server/tests/test_rook_tools_meta.py mcp_server/tests/test_capability_index.py mcp_server/tests/test_server_tool_profiles.py mcp_server/tests/test_mcp_tool_profiles.py mcp_server/tests/test_capability_record.py mcp_server/tests/test_capability_inventory.py mcp_server/tests/test_dispatcher_safety.py -v
```
Expected: PASS (all), including the LM2A tests (unchanged) and dispatcher-safety (no regression).

- [ ] **Step 5: Commit**
```
git add mcp_server/src/rook/server.py mcp_server/tests/test_rook_tools_meta.py
git commit -m "feat(capability-index): call_tool meta-interception + rook_tools_call (wall-before-validation)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (run after Task 8)

- [ ] Run the whole suite touched by this change plus a broad import smoke:
```
.venv/Scripts/python.exe -m pytest mcp_server/tests/ -q -k "capability or profile or meta or dispatcher"
.venv/Scripts/python.exe -c "import rook.server, rook.capability_index; print('import ok')"
```
Expected: PASS; `import ok`. The acceptance criterion is proven by
`test_lean_reach_search_read_call` (lean), `test_readonly_block_wall_before_validation` (readonly), and
the unchanged `test_full_*` profile snapshots (full).

---

## Self-Review (completed against the spec)

- **Spec coverage:** §4.1 unprofiled source → T1; §4.2 record + `mcp_only≠mcp_dispatchable` + agent link →
  T2/T3; §5 ls/search/read + readonly scoping → T4; §6.1 validator → T4; §4.1 wiring + `dispatchable_names`
  ∪ meta (P1b) → T5; §7.2 counts + membership → T6; §6 origin tagging → T7; §6 interception, wall-before-
  validation (P1), guards, no-side-effect-on-block, no meta self/double-record → T8. Invariants 1–9 each
  map to a test (readonly-safe oracle T3; import boundary T2; LM2A-untouched T2/T3/T5 + rerun of
  `test_capability_record.py`).
- **Placeholder scan:** none — every code step carries real code; every run step carries the exact
  command + expected result.
- **Type consistency:** `build_index(tools, agent_records, dispatchable_names)`, `McpCapabilityRecord`
  field names, `CapabilityIndex.ls/search/read(..., scope_readonly=...)`, `validate_arguments(schema,
  arguments) -> list[str]`, `META_TOOL_NAMES`, `_dispatch_origin`, `_all_live_tools`,
  `_get_capability_index` are used identically across tasks.
- **Reviewer's three edits baked in:** T2 is an **import-boundary** test (not stdlib-only); T5 builds the
  LM2A catalog via `build_catalog_from_mcp_tools(_all_live_tools())` → `build_inventory(collect_live_sources(),
  catalog)` (no cache, unprofiled); T4 takes `scope_readonly` as an explicit argument (`server.py` owns
  env/profile resolution in `_handle_meta_tool`).
