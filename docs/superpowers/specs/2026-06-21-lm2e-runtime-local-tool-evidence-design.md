# LM2E — Runtime-Faithful Local-Tool Dispatch Evidence

**Date:** 2026-06-21
**Status:** Approved (design)
**Campaign:** Local/Internal Models roadmap (LM2 — capability/surface evidence)
**Branch:** `codex/lm2e-runtime-local-tool-evidence`

---

## Summary

The LM2 visible-implies-dispatchable audit currently emits **false**
`not_dispatchable` findings for tools that dispatch through the dispatcher's
*local handler* path, because `collect_live_sources()` deliberately sets
`local_tool_names=frozenset()`. The live smoke surfaced this as
`registry_findings: not_dispatchable: 12` on the readonly profile.

LM2E adds an explicit **runtime-enriched** snapshot, `collect_runtime_sources()`,
that fills `local_tool_names` from the *actual* local tools dispatchable in this
runtime (`build_local_tools().keys()`), so the audit answers the real question —
"is this tool dispatchable *in this deployed runtime*" — without false positives.
The static `collect_live_sources()` is unchanged. This makes LM2D's audit
trustworthy (north-star LM2: "visible-implies-dispatchable audit over all
execution-profile groups"; exit criterion: "a new tool cannot become
local-model-visible without a dispatch path"). Read-only / diagnostic only — not
a registry or policy source.

## Why two collectors

- `collect_live_sources()` is the **static, import-light, deterministic**
  snapshot (module constants only; no `ToolDispatcher` instantiation). It is for
  stable inventory and unit tests. It stays exactly as-is.
- `build_local_tools()` (the only source of local-tool names) is **heavy and
  environment-dependent**: it imports the knowledge/learning/scene subsystems
  inside `try/except ImportError` and only includes a tool whose import
  succeeds. Calling it would violate `collect_live_sources()`'s purity.
- So the two truths are kept separate: a new `collect_runtime_sources()` returns
  the same snapshot **enriched** with runtime-dependent local-tool facts. Its
  result is per-runtime evidence, deliberately not deterministic across machines
  (a local tool whose import fails in a runtime genuinely *is* not dispatchable
  there — a true positive, not a false one).

## Design

### Unit 1 — `collect_runtime_sources()` (`capability_inventory.py`)

Add beside `collect_live_sources()`:

```python
def collect_runtime_sources() -> SurfaceSources:
    """Runtime-enriched surface snapshot.

    collect_live_sources() plus the ACTUAL local tools dispatchable in THIS
    runtime (build_local_tools().keys()). Diagnostic runtime evidence -- NOT a
    static registry or policy source, and intentionally environment-dependent.

    An unexpected build_local_tools() failure propagates (the caller treats a
    raise as a diagnostic failure); this never silently returns empty
    local_tool_names. Per-tool optional-import failures are handled inside
    build_local_tools() (the tool is faithfully absent).
    """
    from rook.agent import tool_dispatcher as td  # lazy, like collect_live_sources

    base = collect_live_sources()
    local_names = frozenset(td.build_local_tools().keys())
    return dataclasses.replace(base, local_tool_names=local_names)
```

- Requires adding `import dataclasses` to the module's stdlib imports.
- **Lazy** `tool_dispatcher` import inside the function only — no module-top
  dispatcher import. **No `ToolDispatcher` instantiation.**
- `dataclasses.replace` guarantees every field equals `collect_live_sources()`'s
  except `local_tool_names` — "same snapshot, enriched," not rebuilt.
- `collect_live_sources()` is **untouched** (still returns empty
  `local_tool_names`).

### Failure handling

`collect_runtime_sources()` does not swallow errors. `build_local_tools()`
already absorbs per-tool `ImportError` internally (faithful skips). Any
*unexpected* failure of `build_local_tools()` **propagates** out of
`collect_runtime_sources()`. Plain propagation — no custom exception type. The
collector never degrades to a silently-empty `local_tool_names` (that silent
empty is exactly what caused the false positives).

### Unit 2 — smoke `surface` uses the runtime collector

`scripts/lm_surface_smoke.py` `run_surface()` switches
`collect_live_sources()` → `collect_runtime_sources()`, wrapped so a raise emits
a `FAIL:` line (mirroring the catalog-build guard). It prints the enriched
local-tool count in the evidence block. `coherence` is unchanged. (This is the
one place runtime dispatch truth matters, so it opts into the enriched snapshot.)

## Data Flow

```
collect_runtime_sources()  =  collect_live_sources()  +  build_local_tools().keys()
        │                          (static snapshot)        (this runtime's locals)
        ▼
build_inventory / reconcile_profile  ->  dispatch_context_from_sources(sources)
        ->  classify_visible_tool(x) sees x in local_tool_names -> "dispatcher_local_tool"
        ->  no false not_dispatchable for local tools
```

No change to `classify_visible_tool` / the audit / `reconcile_profile` — they
already classify a `local_tool_names` member as `dispatcher_local_tool`. LM2E
only feeds them the truthful set.

## Testing

All deterministic. Unit tests **patch** `collect_live_sources` and
`build_local_tools` — the real heavy builder is never called in unit tests.

**`mcp_server/tests/test_capability_inventory.py`:**

1. **Enriches local_tool_names (not rebuilt):** monkeypatch
   `capability_inventory.collect_live_sources` → a fixed `base` `SurfaceSources`;
   monkeypatch `tool_dispatcher.build_local_tools` → `{"loc1": None, "loc2": None}`.
   Assert `collect_runtime_sources().local_tool_names == frozenset({"loc1","loc2"})`
   and `dataclasses.replace(out, local_tool_names=frozenset()) == base` (every
   other field identical).
2. **Propagates builder failure (not silent-empty):** monkeypatch
   `build_local_tools` to raise `RuntimeError`; assert `collect_runtime_sources()`
   raises (does not return empty).
3. **Back-compat:** the existing `collect_live_sources` test is unchanged —
   `local_tool_names` is still empty (proves no behavior change to the static
   collector).

**`mcp_server/tests/test_profile_reconciliation.py` — the load-bearing,
audit-path proof (paired):**

4. With `sources.local_tool_names={"x"}`, `x` in `agent_tier0`, `x` in the
   catalog, and a profile `initial_tier="agent_tier0"` intending `x`:
   `reconcile_profile(...).registry_findings` contains **no** `not_dispatchable`
   for `x`.
5. **Paired negative:** identical fixture but `local_tool_names=frozenset()` →
   `registry_findings` **does** contain `not_dispatchable` for `x`. Proves the
   enrichment is load-bearing on the exact LM2D audit path the smoke flagged
   (`reconcile_profile` → LM1A audit), not merely on `build_inventory`'s
   `dispatch_path`.

## Invariants

- `collect_live_sources()` behavior/output unchanged (static, import-light,
  empty `local_tool_names`).
- No `tool_dispatcher` import at module top; lazy import inside
  `collect_runtime_sources()` only. No `ToolDispatcher` instantiation.
- `classify_visible_tool`, the LM1A audit, `build_inventory`, `reconcile_profile`
  unchanged. LM2A–D modules otherwise untouched.
- Unexpected `build_local_tools()` failure propagates; never silent-empty.
- Diagnostic / read-only — no runtime, visibility, or policy change.

## File Touch List

- Modify: `mcp_server/src/rook/agent/capability_inventory.py` — add
  `import dataclasses`; add `collect_runtime_sources()`.
- Modify: `scripts/lm_surface_smoke.py` — `run_surface()` uses
  `collect_runtime_sources()` (FAIL on raise) + prints enriched local-tool count.
- Modify: `mcp_server/tests/test_capability_inventory.py` — tests 1–2.
- Modify: `mcp_server/tests/test_profile_reconciliation.py` — tests 4–5 (paired
  audit-path proof).
