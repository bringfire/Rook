# LM Live-Smoke Checkpoint (pre-LM2E)

**Date:** 2026-06-21
**Status:** Approved (design)
**Campaign:** Local/Internal Models roadmap — coherence checkpoint after LM2A–D
**Branch:** `codex/lm-surface-smoke-checkpoint`

---

## Summary

LM2A–D now form a static profile/surface evidence chain
(`collect_live_sources → build_inventory → readonly_profile_from_sources →
resolve_profile → reconcile_profile`). Before LM2E, sanity-check that chain
against the **connected runtime** — not the repo source — and confirm the GH C#
create→error→repair workflow still produces `script_receipt` evidence.

This is **manual/diagnostic first**. No CI, no automated integration suite. The
deliverables are a runbook the user follows and a diagnostic script that proves
the deployed runtime and surface evidence. The script is a **diagnostic, not a
deploy orchestrator** — the user runs all deploy/Rhino/RookChat steps manually.

### Motivating machine-state finding (2026-06-21)

The session's `rook` MCP launches from
`C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe -m rook` with
`PYTHONPATH: ""`, importing `rook` from **deployed site-packages**. That deployed
runtime is **stale**: `…/Rook/venv/Lib/site-packages/rook/agent/profile_reconciliation.py`
is absent (LM2D not present), and no `agent_tool_catalog.json` cache exists. So
runtime coherence is the first gate; without a fresh release deploy the later
checks prove nothing. This is the split-brain the merged
`deploy-local-mcp-coherence` work hardened against, folded into this checkpoint.

## Goals / Non-goals

**Goals**
- Prove the deployed runtime (the product surface) contains and imports the
  merged LM2A–D modules.
- Run the LM2A→D chain against the deployed runtime's own advertised catalog and
  confirm the readonly profile evidence is sane (MCP-only exclusion holds;
  locally-reachable groups actually activate).
- Confirm the GH C# repair canary still yields `script_receipt` reaching
  `usable`.

**Non-goals**
- No CI / automated integration suite.
- The script does not deploy, start, or stop anything (no orchestration).
- No new runtime behavior, no MCP wire change, no changes to LM2A–D modules.

## Artifacts

1. **Runbook:** `docs/superpowers/runbooks/2026-06-21-lm-surface-smoke-checklist.md`
   — gate-0 deploy → coherence → surface evidence → canary. Each item carries the
   exact command/action, expected evidence, and a `PASS / FAIL / DEGRADED /
   WARNING` criterion.
2. **Diagnostic script:** `scripts/lm_surface_smoke.py` — two subcommands
   (`coherence`, `surface`). Always invoked with the **deployed venv interpreter**
   and empty `PYTHONPATH` so it imports the same `rook` the live surfaces use.
   Prints resolved `rook.__file__` / `rook.server.__file__` (self-verifying),
   emits explicit `PASS:` / `FAIL:` / `DEGRADED:` / `WARNING:` lines, exits 0 on
   pass and 1 on fail.
3. **Tests:** `mcp_server/tests/test_lm_surface_smoke.py` — unit tests for the
   script's **pure helpers only**. Because `scripts/` is not a package, the test
   imports the script via `importlib.util.spec_from_file_location`. The deployed
   runtime import path is **not** mocked into unit tests — that belongs to the
   live run.

## Invocation contract

Every script run uses the deployed venv, empty `PYTHONPATH`, from any cwd whose
`sys.path[0]` is not the repo `mcp_server/src` (so `import rook` resolves to
deployed site-packages):

```
C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe \
    C:/UDEV/Rook/scripts/lm_surface_smoke.py coherence
C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe \
    C:/UDEV/Rook/scripts/lm_surface_smoke.py surface
```

The script never adds repo `src` to `sys.path`. It prints the resolved import
origins so an accidental repo-source import is visible, not silent.

## Gate-0 — Deploy (manual, user)

Stop Rhino + rook MCP → run `scripts/deploy-local-testing.ps1` (release mode) →
restart Rhino. **Evidence:** the deploy completes and its own hardened release
verification passes (`rook.server.__file__` under site-packages; all seven
`rhino_2d_to_3d_*` tools advertised). **PASS** = deploy green. The script does
not perform or trigger this step.

## 1 — Coherence smoke (`lm_surface_smoke.py coherence`)

Under the deployed venv. Imports and resolves the origins of:
`rook`, `rook.server`, and the four LM2 modules
(`rook.agent.capability_record`, `rook.agent.capability_inventory`,
`rook.agent.execution_profile`, `rook.agent.profile_reconciliation`).

Prints each module's `__file__`. **PASS** when every one resolves **under**
`…/Rook/venv/Lib/site-packages/rook` (case-insensitive, normalized separators)
and all four LM2 modules import without error. **FAIL** if any LM2 module is
absent, errors on import, or resolves from the repo `src` tree (split-brain).

The script prints `rook.__file__` and `rook.server.__file__` explicitly (per the
import-origin guard), so the origin is always on the record.

*Chat-runtime currency* is a **manual** runbook item, not scripted (it needs the
chat server running): the user confirms the RookChat model dropdown populates —
the known stale-`RookChatService.json` canary.

## 2 — Surface-evidence smoke (`lm_surface_smoke.py surface`)

**Import-origin guard first.** `surface` runs the same module-origin checks as
`coherence` before any surface work and prints `rook.__file__` /
`rook.server.__file__`. If the origin guard fails (any LM2 module absent or
imported from repo source), `surface` exits **FAIL** immediately — it never
produces "comforting lies" against repo imports.

**Catalog build (deployed runtime, in-process).** The authoritative catalog is
the deployed server's own advertised tools:

```python
import asyncio
from rook.server import list_tools
from rook.agent.tool_registry import build_catalog_from_mcp_tools

tools = asyncio.run(list_tools())
catalog = build_catalog_from_mcp_tools(tools)
```

Not the cache, not RookChat side effects, not repo source. If the build raises or
yields an empty catalog → **FAIL**.

**Run the chain and print evidence.**

```python
from rook.agent.capability_inventory import collect_live_sources, build_inventory
from rook.agent.execution_profile import (
    readonly_profile_from_sources, readonly_excluded_mcp_only_groups, resolve_profile,
)
from rook.agent.profile_reconciliation import reconcile_profile

sources = collect_live_sources()
inventory = build_inventory(sources, catalog)
profile = readonly_profile_from_sources(sources)
resolution = resolve_profile(profile, inventory)
rec = reconcile_profile(resolution, sources, catalog)
```

Print: catalog tool count; profile name; `len(intended_names)`; `len(active_names)`;
`registry_findings` counts grouped by `code`; `len(profile_findings)`.

**Assertions (FAIL on violation):**
- `readonly_excluded_mcp_only_groups(sources) == ("gh_exploration", "gh_knowledge", "gh_validation")`.
- None of those three appear in `profile.groups`.
- **Non-degenerate activation:** every readonly-profile group that is present in
  the built catalog activates — i.e. no `group_activation_failed` finding whose
  `tool` is a group present in the catalog's group membership. (Catches the
  "empty-catalog, everything fails" degenerate case; a group genuinely absent
  from the catalog is allowed to fail and is reported, not asserted against.)

**Cache comparison — explicitly secondary.** If
`agent_tool_catalog.json` (via `get_catalog_cache_path()` /
`load_catalog_from_cache()`) is:
- **absent** → `DEGRADED:` info line only (never FAIL);
- **present and identical** → `PASS:` cache-current line;
- **present and drifts** → `WARNING:` by default, listing the delta; escalates to
  `FAIL:` only if the drift touches the **required set**:
  - any of the four LM2 modules (importable/current — already gated by coherence),
  - `request_tools`, `search_tools`,
  - `gh_snapshot`, `gh_create_csharp_script`, `gh_update_script`, `gh_errors`,
  - any tool that appears in the resolved local readonly profile
    (`resolution.tool_names`).

The smoke never depends on the cache existing or on RookChat writing it first.

## 3 — Workflow canary (manual RookChat, user)

Through RookChat (natural language → agent → GH tools):
1. Ask it to create a C# GH script with a deliberate compile error (e.g. an
   undefined symbol assigned to an output pin).
2. Confirm the create result carries `data.script_receipt` with `mutation`,
   `verification`, `artifact_status`, and `repair_anchor`.
3. Ask it to repair (assign a valid value).
4. Confirm the receipt's `artifact_status` reaches `usable` and `gh_errors` is
   clean.

Documented in the runbook with exact prompts and the expected receipt fields.
**PASS** = receipt present on create and repair reaches `usable` with clean
errors. **FAIL** = receipt absent or repair does not reach `usable`.

**Optional complement (assistant-run, once Rhino is up):** the same
create→error→repair at the MCP-tool level (`gh_create_csharp_script` →
`gh_update_script` → `gh_errors`) as a deterministic cross-check of the deployed
GH C# path. This complements — does not replace — the manual RookChat run.

## Pure helpers (testable)

Factor the script's judgment into pure functions, unit-tested without importing
the deployed runtime:
- `module_origin_ok(path, site_packages_root) -> bool` — case-insensitive,
  normalized-separator "under site-packages" check.
- `classify_cache(cache, built, required_names) -> Literal["absent","current","warning","fail"]`
  — the cache tri-state + required-set escalation (operates on plain dicts/sets).
- `degenerate_activation_failures(rec, catalog_group_members) -> tuple[str, ...]`
  — group-activation failures whose group is present in the catalog (the
  assertion target), as sorted plain data.
- `format_surface_evidence(...) -> str` — deterministic evidence block from plain
  inputs (counts, code histogram).

## Testing

`mcp_server/tests/test_lm_surface_smoke.py`:
- Import the script via `importlib.util.spec_from_file_location` (scripts/ is not
  a package).
- Test the pure helpers above with plain fixtures: `module_origin_ok` (under vs.
  repo-src vs. case/sep variants); `classify_cache` (absent→absent,
  identical→current, benign drift→warning, required-set drift→fail);
  `degenerate_activation_failures` (catalog-present group failing → flagged;
  catalog-absent group failing → not flagged); `format_surface_evidence`
  (stable, deterministic).
- **Do not** mock the deployed-runtime import (`rook.server.list_tools`,
  `collect_live_sources`, etc.) into unit tests — those are exercised by the live
  run only.

## Invariants

- Script is diagnostic only: no deploy, no process start/stop, no writes to the
  deployed runtime, no repo-`src` injection into `sys.path`.
- Surface work is gated behind the import-origin guard.
- Catalog is built from the deployed `rook.server.list_tools()`; cache is
  secondary and never a hard prerequisite.
- LM2A–D modules and all runtime behavior are untouched.

## File Touch List

- Create: `docs/superpowers/runbooks/2026-06-21-lm-surface-smoke-checklist.md`
- Create: `scripts/lm_surface_smoke.py`
- Create: `mcp_server/tests/test_lm_surface_smoke.py`
