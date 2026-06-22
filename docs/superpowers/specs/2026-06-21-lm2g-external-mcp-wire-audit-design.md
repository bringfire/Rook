# LM2G — `external_mcp` Catalog-vs-Wire-Dispatch Audit

**Date:** 2026-06-21
**Status:** Approved (design)
**Campaign:** Local/Internal Models roadmap (LM2 — capability/surface evidence)
**Branch:** `codex/lm2g-external-mcp-wire-audit`

---

## Summary

The north-star LM2 deliverable names execution-profile membership for
`external_mcp`, `rookchat_cloud`, `rookchat_local`, `readonly`, and `planner`.
LM2A–F delivered `rookchat_local`, `readonly`, and `planner` as tier/group
execution profiles that reconcile against **internal local dispatchability**.
`external_mcp` is deliberately different and was deferred until it could be
modeled honestly.

`external_mcp` is **not an execution profile**. It is a read-only audit of the
**public MCP wire surface**: the set of tools advertised to MCP clients
(`server.list_tools()`) reconciled against the set of tools that the wire router
(`server._call_tool_dispatch`) can actually handle. Its visibility model is
catalog-all, and its notion of "dispatchable" is **MCP-wire reachability**
(a real `case` branch in the router), not the internal `ToolDispatcher`
local-handler path that LM2A–F audit.

LM2G adds a standalone report type, `ExternalMcpResolution`, plus a read-only,
no-execution evidence collector that extracts wire-handler names by **static AST
parsing** of `_call_tool_dispatch`. The load-bearing gate is a single error:
**a publicly advertised MCP tool with no wire handler** (`advertised_not_dispatchable`).
Diagnostic / read-only only — it mutates no `ToolRegistry`, schema, visibility,
or wire behavior, adds nothing to `ProfileDefinition` or `CapabilityRecord`, and
executes no tool.

## Why standalone (not a `ProfileDefinition`)

- `resolve_profile` inverts an inventory by **tiers + groups + pins**.
  `external_mcp`'s intended set is "every advertised tool," which is none of
  those. Forcing catalog-all into `ProfileDefinition` would require a special
  branch through every profile consumer (`resolve_profile`,
  `reconcile_profile`, the default seeds) and contaminate the tier/group model
  that LM2F just hardened (the `TIER_FIELDS` single-source-of-truth work).
- `external_mcp`'s dispatch axis is **MCP-wire reachability**, a different
  question from the inventory's `dispatch_path` (internal
  dispatcher/bridge/local). Putting a second dispatchability meaning on
  `CapabilityRecord` (e.g. an `mcp_dispatchable` field) would reintroduce the
  dual-meaning conflation LM2F removed. We keep the axis separate until a
  consumer demonstrably needs it merged.

So `external_mcp` lives in its own module with its own report type, a sibling to
`execution_profile.py` and `profile_reconciliation.py`, not a member of them.

## Design

### New module: `mcp_server/src/rook/agent/external_mcp.py`

Stdlib-only: `ast`, `dataclasses`, `importlib.util`. It reuses
`capability_record.Severity` for the severity literal. **It never imports
`rook.server`** (it reads that module's *source file*, it does not execute it),
and it instantiates no `ToolRegistry` and calls no tool.

### Types

```python
from rook.agent.capability_record import Severity  # "info" | "warning" | "error"

@dataclass(frozen=True)
class ExternalMcpFinding:
    code: str
    tool: str          # tool name; "" or a module name for structural findings
    severity: Severity
    message: str

@dataclass(frozen=True)
class WireDispatchEvidence:
    names: tuple[str, ...]                  # sorted, de-duplicated wire-handler names
    findings: tuple[ExternalMcpFinding, ...]  # extraction anomalies (sorted)

@dataclass(frozen=True)
class ExternalMcpResolution:
    advertised_names: tuple[str, ...]       # sorted
    wire_dispatch_names: tuple[str, ...]    # sorted
    findings: tuple[ExternalMcpFinding, ...]  # sorted; includes folded evidence findings
```

### Functions

```python
def extract_wire_dispatch_evidence_from_source(source: str) -> WireDispatchEvidence
def collect_wire_dispatch_evidence(module_name: str = "rook.server") -> WireDispatchEvidence
def reconcile_external_mcp(
    advertised_names: Iterable[str],
    wire_evidence: WireDispatchEvidence,
) -> ExternalMcpResolution
def format_external_mcp_report(resolution: ExternalMcpResolution) -> str
```

**`extract_wire_dispatch_evidence_from_source` (pure AST).**
1. `ast.parse(source)`; find the function (sync or async) named exactly
   `_call_tool_dispatch`. If none → return empty `names` plus one
   `ExternalMcpFinding(code="dispatch_function_missing", tool="_call_tool_dispatch",
   severity="error", ...)`. (The reconcile cascade then loudly flags every
   advertised tool, which is the correct alarm — the audit's substrate is gone.)
2. Within that function, consider only `ast.Match` statements whose subject
   unparses to exactly `name`. If more than one such match exists → emit one
   `multiple_dispatch_matches` (warning), but still harvest from all of them.
3. For each case pattern:
   - `MatchValue` wrapping a `str` `Constant` → collect the string.
   - `MatchOr` → collect every sub-pattern that is a `MatchValue` of a `str`
     `Constant`; if any sub-pattern is not → emit `unextractable_case` (warning,
     with line number) and skip that sub-pattern.
   - Bare wildcard `case _` (`MatchAs` with `pattern is None and name is None`)
     → skip silently (it is the `Unknown tool` fallback).
   - Anything else (a guard via `case.guard`, a named capture `MatchAs` with a
     `name`, a non-`str` constant, a class/sequence/mapping pattern) → emit
     `unextractable_case` (warning, with line number) and collect no name.
4. Return de-duplicated, sorted `names` and sorted `findings`.

**`collect_wire_dispatch_evidence` (no module execution).**
`importlib.util.find_spec(module_name)` → read `spec.origin` from disk →
`extract_wire_dispatch_evidence_from_source(text)`. Uses `find_spec` (not
`import rook.server`) so the heavy server module is never executed. If the spec
or its `origin` cannot be resolved, or the file cannot be read → return empty
`names` plus a `dispatch_function_missing`-class structural finding
(`code="wire_source_unresolved"`, severity `error`, `tool=module_name`).

**`reconcile_external_mcp` (pure two-set reconcile).**
- `advertised = frozenset(advertised_names)`, `wire = frozenset(wire_evidence.names)`.
- Start findings from `wire_evidence.findings` (folded through verbatim).
- If `advertised` is empty → add `empty_catalog` (error, `tool=""`).
- For each name in `sorted(advertised - wire)` → `advertised_not_dispatchable`
  (**error**): a publicly advertised MCP tool with no wire handler.
- For each name in `sorted(wire - advertised)` → `handler_not_advertised`
  (**info**): a wire handler that exists outside the public advertised surface.
- Return `ExternalMcpResolution` with sorted name tuples and sorted findings.

### Finding codes and severities

| code | meaning | severity |
|------|---------|----------|
| `advertised_not_dispatchable` | in `advertised` but not in `wire` — public MCP contract violation | **error** |
| `handler_not_advertised` | in `wire` but not in `advertised` — a handler outside the public advertised surface | **info** |
| `empty_catalog` | `advertised_names` is empty — the advertised evidence source is broken | **error** |
| `dispatch_function_missing` | `_call_tool_dispatch` not found in source | **error** |
| `wire_source_unresolved` | module spec/origin unreadable | **error** |
| `multiple_dispatch_matches` | more than one `match name:` in the function | **warning** |
| `unextractable_case` | a guarded / capture / non-constant / non-str case pattern | **warning** |

**`handler_not_advertised` is explicitly NOT a defect assertion.** It states
only that "a wire handler exists outside the public advertised MCP surface,"
which is frequently intentional (internal agent-facing GH creation tools;
deprecated interactive command-learning tools filtered from `list_tools()`).
It is informational context unless a future policy slice chooses to constrain
the orphan-handler set. Today the audit finds 0 `advertised_not_dispatchable`
and 15 `handler_not_advertised`, all intentional internals — so `info` keeps the
one loud channel (the error direction) uncontaminated.

**No allowlist.** LM2G introduces no maintained "expected unadvertised handlers"
set. A hand-curated allowlist is itself a drift surface and would invent a
parallel truth — the exact failure mode this slice exists to avoid.

## Provenance (caller context matters)

`collect_wire_dispatch_evidence` resolves its source via
`importlib.util.find_spec(module_name).origin`, so **which `rook.server` it reads
depends on import resolution / `PYTHONPATH` in the calling process**. This is by
design, and the two intended callers see two honest, different sources:

- **Repo unit tests** run with the worktree's `mcp_server/src` importable, so
  `find_spec("rook.server")` resolves the **worktree source** — the code under
  development is what gets audited.
- **Deployed smoke** (`scripts/lm_surface_smoke.py`) enforces an **empty
  `PYTHONPATH`** in `main()` and runs under the deployed venv interpreter, so
  `find_spec("rook.server")` resolves the **deployed site-packages** copy — the
  code actually serving MCP clients is what gets audited.

The collector does not hide this; the smoke subcommand prints the resolved
`rook.server.__file__` so the audited path is visible in the evidence block.

## Smoke integration — new `external` subcommand

`scripts/lm_surface_smoke.py` gains a third subcommand, `external`, that keeps
the public-wire audit a distinct concern from `surface`'s readonly checks while
reusing the same machinery and the same origin guarantees. `coherence` and
`surface` are unchanged.

`run_external()` ordering (mirrors `run_surface` exactly):
1. `rc = _check_origins()`; if `rc != 0`, print `FAIL` and refuse. This is the
   second tightening: the AST audit must not run against a `rook.server` whose
   origin has not been confirmed to be the deployed site-packages. `_check_origins`
   imports `rook.server` and asserts containment under
   `sys.prefix/Lib/site-packages`.
2. Build the advertised catalog the same way `surface` does:
   `tools = asyncio.run(list_tools())`, `catalog = build_catalog_from_mcp_tools(tools)`.
   `FAIL` on exception or empty catalog. `advertised_names = tuple(catalog.keys())`.
3. `evidence = collect_wire_dispatch_evidence("rook.server")`. Because `main()`
   enforces an empty `PYTHONPATH` and step 1 already proved `rook.server`
   resolves under deployed site-packages, `find_spec` resolves that same
   deployed file. Print `rook.server.__file__` as the audited wire-source path.
4. `resolution = reconcile_external_mcp(advertised_names, evidence)`.
5. Print a deterministic evidence block: advertised count, wire count, the
   audited wire-source path, and a finding histogram by code (sorted).
6. Exit contract:
   - any `advertised_not_dispatchable`, `empty_catalog`, `dispatch_function_missing`,
     or `wire_source_unresolved` → **FAIL** (exit 1).
   - any `multiple_dispatch_matches` or `unextractable_case` → **WARNING**
     (printed; does not by itself fail).
   - `handler_not_advertised` → printed as info lines only.
   - clean → **PASS** (exit 0).

`build_parser()` adds `external` to the `command` choices; `main()` dispatches
to `run_external()`.

## Data flow

```
list_tools()  ──build_catalog_from_mcp_tools──▶ advertised_names (catalog.keys())
                                                          │
find_spec("rook.server").origin ──read──▶ source ──AST──▶ WireDispatchEvidence.names
                                                          │
                          reconcile_external_mcp(advertised_names, evidence)
                                                          │
                                                          ▼
                                              ExternalMcpResolution
                            advertised − wire ▶ advertised_not_dispatchable (error)
                            wire − advertised ▶ handler_not_advertised (info)
```

## Testing

All deterministic. The pure functions are tested against synthetic source
strings and synthetic name sets; the collector is tested once against the real
`rook.server` origin to prove the `find_spec` path works without importing the
module.

**`mcp_server/tests/test_external_mcp.py`:**

*Extractor (synthetic source strings):*
1. **Plain cases:** source with `async def _call_tool_dispatch(...)` containing
   `match name:` with `case "tool_a":` and `case "tool_b":` →
   `names == ("tool_a", "tool_b")`, no findings.
2. **OR-pattern:** `case "tool_b" | "tool_c":` → both names collected.
3. **Wildcard ignored:** a `case _:` arm contributes no name and no finding.
4. **Guarded case:** `case "x" if cond:` → no name; one `unextractable_case`
   (warning) with the line number.
5. **Capture case:** `case other:` → no name; one `unextractable_case`.
6. **Non-constant / non-str:** `case SOME_CONST:` and `case 5:` → no name; one
   `unextractable_case` each.
7. **Missing function:** source with no `_call_tool_dispatch` → empty names; one
   `dispatch_function_missing` (error).
8. **Multiple `match name`:** two `match name:` blocks in the function → names
   from both; one `multiple_dispatch_matches` (warning).
9. **Subject not `name`:** a `match other:` block is ignored (no names from it).

*Collector (real origin, no import of server):*
10. `collect_wire_dispatch_evidence("rook.server")` returns a non-empty `names`
    of plausible size (e.g. `> 300`) and contains known handlers `rhino_ping`
    and `gh_edit`. A separate focused test monkeypatches `find_spec` to point at
    a temp file containing a tiny synthetic `_call_tool_dispatch` and asserts the
    collector reads that file's labels — proving it sources via `find_spec.origin`
    rather than importing/executing the module.
11. **Unresolved module:** `collect_wire_dispatch_evidence("rook.__nope__")` →
    empty names; one `wire_source_unresolved` (error).

*Reconcile (synthetic name sets):*
12. **Advertised-without-handler:** advertised `{"a","b"}`, wire `{"a"}` →
    one `advertised_not_dispatchable` (error) for `b`; no error for `a`.
13. **Handler-without-advertisement:** advertised `{"a"}`, wire `{"a","z"}` →
    one `handler_not_advertised` (info) for `z`; no error.
14. **Empty catalog:** advertised `()`, wire `{"a"}` → one `empty_catalog`
    (error).
15. **Clean overlap:** advertised `{"a","b"}`, wire `{"a","b"}` → no error and
    no info finding.
16. **Evidence findings folded:** pass a `WireDispatchEvidence` carrying an
    `unextractable_case` warning → it appears verbatim in
    `ExternalMcpResolution.findings`.
17. **Severity table pin:** assert the code→severity mapping for all seven codes
    (drift-pin, mirroring the other LM2 modules' static pins).

**`mcp_server/tests/test_lm_surface_smoke.py` (extend):**
18. `build_parser()` accepts `external`.
19. `run_external` returns non-zero when `reconcile_external_mcp` would yield an
    `advertised_not_dispatchable` (inject via monkeypatching the catalog and
    evidence collectors used inside `run_external`), and zero on a clean
    reconcile. (No deployed runtime required; patch the seams.)
20. `run_external` calls `_check_origins` before building the catalog (assert by
    monkeypatching `_check_origins` to return 1 and confirming the function
    refuses and returns 1 without building the catalog).

## Invariants

- No `import rook.server`; source is read via `find_spec(...).origin` only. No
  `ToolRegistry`, no `ToolDispatcher`, no tool execution, no schema/visibility/
  wire mutation.
- `external_mcp.py` is stdlib-only (`ast`, `dataclasses`, `importlib.util`) plus
  the `Severity` literal from `capability_record`. It imports nothing from
  `execution_profile`, `profile_reconciliation`, or `tool_*`.
- `ProfileDefinition`, `CapabilityRecord`, `CapabilityInventory`, the LM2A–F
  modules, and `_call_tool_dispatch` itself are untouched. No `mcp_dispatchable`
  field is added to `CapabilityRecord`.
- The real gate is exactly one thing: a publicly advertised MCP tool with no
  wire handler (`advertised_not_dispatchable`, error). `handler_not_advertised`
  is documented, non-defect, informational context.
- The smoke `external` subcommand runs `_check_origins()` before any AST audit,
  and audits the same deployed-resolved `rook.server` that the origin guard
  validated. `coherence` and `surface` behavior is unchanged.

## File Touch List

- Create: `mcp_server/src/rook/agent/external_mcp.py` — types, extractor,
  collector, reconciler, report formatter.
- Create: `mcp_server/tests/test_external_mcp.py` — tests 1–17.
- Modify: `scripts/lm_surface_smoke.py` — add `run_external()`, register
  `external` in `build_parser()` / `main()`. No change to `run_coherence` /
  `run_surface`.
- Modify: `mcp_server/tests/test_lm_surface_smoke.py` — tests 18–20.
