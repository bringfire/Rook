# LM Live-Smoke Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a diagnostic script + runbook that prove the DEPLOYED rook runtime contains the merged LM2A–D modules and that the LM2A→D surface chain is sane against the deployed runtime's own catalog, plus document the manual deploy/coherence/canary steps.

**Architecture:** One stdlib-top diagnostic script `scripts/lm_surface_smoke.py` with two subcommands (`coherence`, `surface`). All `rook` imports are **lazy** (inside the subcommand functions), so `main` can enforce an empty `PYTHONPATH` and the pure helpers are unit-testable without a deployed runtime. A separate runbook documents the manual gate-0 deploy, the script invocation, and the RookChat repair canary.

**Tech Stack:** Python 3.12 stdlib (argparse, os, sys, asyncio, importlib), pytest. Script under `scripts/`, tests under `mcp_server/tests/`, runbook under `docs/superpowers/runbooks/`.

**Spec:** `docs/superpowers/specs/2026-06-21-lm-surface-smoke-checkpoint-design.md`

## Global Constraints

- Diagnostic only: the script deploys nothing, starts/stops no process, writes nothing to the deployed runtime, and never adds repo `src` to `sys.path`.
- All `rook` imports are lazy (inside `run_coherence`/`run_surface`), never at module top — so the module imports under the repo dev venv for unit tests, and the PYTHONPATH gate runs before any `rook` import.
- `PYTHONPATH` enforced both ways: runbook command clears it; `main` prints it and returns FAIL (exit 1) if non-empty, before dispatching.
- `surface` runs the PYTHONPATH gate then the module-origin guard FIRST; if either fails it exits FAIL before any surface work. Both subcommands print `rook.__file__` and `rook.server.__file__`.
- Catalog is built in-process from `asyncio.run(rook.server.list_tools())` → `build_catalog_from_mcp_tools(...)` — not the cache, not RookChat, not repo source.
- Module-origin PASS = every checked module's `__file__` resolves under `{sys.prefix}/Lib/site-packages` (the deployed venv's site-packages), case-insensitive, normalized separators.
- Readonly assertions: `readonly_excluded_mcp_only_groups(sources) == ("gh_exploration","gh_knowledge","gh_validation")`; none of those three in `profile.groups`; no `group_activation_failed` for a group that has ≥1 member in the catalog.
- Cache comparison secondary: absent → DEGRADED (never FAIL); drift → WARNING by default; FAIL only if drift touches the required set, which is **tool names only**: `request_tools`, `search_tools`, `gh_snapshot`, `gh_create_csharp_script`, `gh_update_script`, `gh_errors`, and every name in `resolution.tool_names`.
- Unit tests cover the pure helpers + the runtime-free gate/parser behavior only. The deployed-runtime import (`rook.server.list_tools`, `collect_live_sources`, …) is **not** mocked into unit tests — it is exercised by the live run.
- Unit tests run under the repo dev venv from repo root: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider …`. The live smoke runs the script under the **deployed** venv (documented in the runbook), never in tests.

---

### Task 1: Pure helpers + tests

**Files:**
- Create: `scripts/lm_surface_smoke.py` (module docstring, stdlib imports, the five pure helpers only)
- Test: `mcp_server/tests/test_lm_surface_smoke.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces (Task 2 reuses these):
  - `pythonpath_clean(env_value: str) -> bool`
  - `module_origin_ok(module_file: str, site_packages_root: str) -> bool`
  - `classify_cache(cache_keys, built_keys, required) -> str` (returns `"absent"|"current"|"warning"|"fail"`; `cache_keys` may be `None`)
  - `degenerate_activation_failures(group_failed_tools, catalog_group_names) -> tuple[str, ...]`
  - `format_surface_evidence(*, catalog_count, profile_name, intended_count, active_count, finding_histogram, profile_findings_count) -> str`

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_lm_surface_smoke.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "lm_surface_smoke.py"
    spec = importlib.util.spec_from_file_location("lm_surface_smoke", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SMOKE = _load_script()


def test_pythonpath_clean():
    assert SMOKE.pythonpath_clean("") is True
    assert SMOKE.pythonpath_clean("   ") is True
    assert SMOKE.pythonpath_clean("C:/repo/src") is False
    assert SMOKE.pythonpath_clean(" C:/x ") is False


def test_module_origin_ok_under_site_packages():
    root = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages"
    under = r"C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages\rook\__init__.py"
    repo = r"C:\UDEV\Rook\mcp_server\src\rook\__init__.py"
    assert SMOKE.module_origin_ok(under, root) is True
    # case + separator insensitivity
    assert SMOKE.module_origin_ok(under.lower().replace("\\", "/"), root) is True
    assert SMOKE.module_origin_ok(repo, root) is False


def test_classify_cache():
    required = {"gh_snapshot", "gh_errors"}
    assert SMOKE.classify_cache(None, {"a"}, required) == "absent"
    assert SMOKE.classify_cache({"a", "b"}, {"a", "b"}, required) == "current"
    # benign drift (not in required) -> warning
    assert SMOKE.classify_cache({"a", "b"}, {"a"}, required) == "warning"
    # required-touching drift -> fail
    assert SMOKE.classify_cache({"a"}, {"a", "gh_snapshot"}, required) == "fail"


def test_degenerate_activation_failures():
    catalog_groups = {"gh_canvas", "rhino_geometry"}
    # gh_canvas present in catalog but failed -> degenerate
    assert SMOKE.degenerate_activation_failures(
        {"gh_canvas", "absent_group"}, catalog_groups
    ) == ("gh_canvas",)
    # a group absent from the catalog failing is allowed (not flagged)
    assert SMOKE.degenerate_activation_failures({"absent_group"}, catalog_groups) == ()


def test_format_surface_evidence_is_deterministic():
    out = SMOKE.format_surface_evidence(
        catalog_count=300,
        profile_name="readonly",
        intended_count=64,
        active_count=12,
        finding_histogram={"active_not_intended": 3, "group_activation_failed": 1},
        profile_findings_count=76,
    )
    assert "catalog tools: 300" in out
    assert "profile: readonly" in out
    # histogram rendered in sorted code order
    assert out.index("active_not_intended") < out.index("group_activation_failed")
    assert out == SMOKE.format_surface_evidence(
        catalog_count=300,
        profile_name="readonly",
        intended_count=64,
        active_count=12,
        finding_histogram={"group_activation_failed": 1, "active_not_intended": 3},
        profile_findings_count=76,
    )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm_surface_smoke.py -q`
Expected: FAIL — `FileNotFoundError` / `spec_from_file_location` cannot load (the script does not exist yet), or `AttributeError` on the helpers.

- [ ] **Step 3: Create the script with the pure helpers**

Create `scripts/lm_surface_smoke.py`:

```python
#!/usr/bin/env python3
"""LM live-smoke diagnostic (pre-LM2E).

Proves the DEPLOYED rook runtime (site-packages, empty PYTHONPATH) contains the
merged LM2A-D modules, and that the LM2A->D surface chain is sane against the
deployed runtime's own advertised catalog. Diagnostic only: it deploys nothing,
starts/stops nothing, writes nothing to the deployed runtime, and never adds
repo src to sys.path.

Run with the DEPLOYED venv interpreter and an empty PYTHONPATH, e.g. (PowerShell):
  $env:PYTHONPATH=""; & "<...>/Rook/venv/Scripts/python.exe" scripts/lm_surface_smoke.py coherence
"""
from __future__ import annotations

import argparse
import os
import sys


def pythonpath_clean(env_value: str) -> bool:
    """True iff PYTHONPATH is empty/whitespace-only."""
    return not env_value.strip()


def module_origin_ok(module_file: str, site_packages_root: str) -> bool:
    """True iff module_file resolves under site_packages_root.

    Case-insensitive with normalized separators (Windows casing/slashes).
    """
    def _norm(p: str) -> str:
        return os.path.normpath(p).replace("\\", "/").lower()

    return _norm(module_file).startswith(_norm(site_packages_root))


def classify_cache(cache_keys, built_keys, required) -> str:
    """Cache tri-state vs. the in-process built catalog.

    - cache_keys is None        -> "absent"
    - no symmetric difference   -> "current"
    - difference touches required -> "fail"
    - otherwise                 -> "warning"
    """
    if cache_keys is None:
        return "absent"
    delta = set(cache_keys) ^ set(built_keys)
    if not delta:
        return "current"
    if delta & set(required):
        return "fail"
    return "warning"


def degenerate_activation_failures(group_failed_tools, catalog_group_names) -> tuple[str, ...]:
    """Groups that failed to activate despite being present in the catalog.

    A group genuinely absent from the catalog is allowed to fail; only a group
    with >=1 catalog member that still failed is the degenerate signal.
    """
    return tuple(sorted(set(group_failed_tools) & set(catalog_group_names)))


def format_surface_evidence(
    *,
    catalog_count: int,
    profile_name: str,
    intended_count: int,
    active_count: int,
    finding_histogram: dict,
    profile_findings_count: int,
) -> str:
    """Deterministic evidence block (histogram rendered in sorted code order)."""
    lines = [
        f"  catalog tools: {catalog_count}",
        f"  profile: {profile_name}",
        f"  intended: {intended_count}",
        f"  active: {active_count}",
        f"  profile_findings: {profile_findings_count}",
        "  registry_findings by code:",
    ]
    for code in sorted(finding_histogram):
        lines.append(f"    {code}: {finding_histogram[code]}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm_surface_smoke.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/lm_surface_smoke.py mcp_server/tests/test_lm_surface_smoke.py
git commit -m "feat(lm-smoke): pure helpers for the live-smoke diagnostic"
```

---

### Task 2: CLI shell (coherence + surface + main)

**Files:**
- Modify: `scripts/lm_surface_smoke.py` (append print helpers, `_site_packages_root`, `_check_origins`, `run_coherence`, `run_surface`, `build_parser`, `main`, and the `__main__` guard — below the pure helpers)
- Test: `mcp_server/tests/test_lm_surface_smoke.py` (append the gate + parser tests)

**Interfaces:**
- Consumes: the Task 1 pure helpers (`pythonpath_clean`, `module_origin_ok`, `classify_cache`, `degenerate_activation_failures`, `format_surface_evidence`); lazily, the deployed `rook` runtime (`rook`, `rook.server.list_tools`, `rook.agent.tool_registry`, `rook.agent.tool_groups.TOOL_GROUPS`, `rook.agent.capability_inventory`, `rook.agent.execution_profile`, `rook.agent.profile_reconciliation`).
- Produces: `build_parser() -> argparse.ArgumentParser`; `main(argv) -> int` (0 pass / 1 fail); `run_coherence() -> int`; `run_surface() -> int`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_lm_surface_smoke.py`:

```python
def test_build_parser_accepts_two_subcommands():
    parser = SMOKE.build_parser()
    assert parser.parse_args(["coherence"]).command == "coherence"
    assert parser.parse_args(["surface"]).command == "surface"


def test_build_parser_rejects_unknown_subcommand():
    import pytest

    parser = SMOKE.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["nonsense"])


def test_main_fails_fast_on_nonempty_pythonpath(monkeypatch, capsys):
    # The PYTHONPATH gate runs in main() BEFORE any rook import, so this test
    # needs no deployed runtime: a dirty PYTHONPATH must return 1 immediately.
    monkeypatch.setenv("PYTHONPATH", "C:/repo/src")
    rc = SMOKE.main(["coherence"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "PYTHONPATH" in out
    assert "FAIL" in out
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm_surface_smoke.py -k "parser or pythonpath" -q`
Expected: FAIL — `AttributeError: module 'lm_surface_smoke' has no attribute 'build_parser'` / `main`.

- [ ] **Step 3: Append the CLI shell to the script**

Append to `scripts/lm_surface_smoke.py` (after the pure helpers):

```python
# --- output helpers ---

def _p(prefix: str, msg: str) -> None:
    print(f"{prefix}: {msg}")


# --- coherence / origin guard (lazy rook import) ---

_LM2_MODULES = (
    "rook.agent.capability_record",
    "rook.agent.capability_inventory",
    "rook.agent.execution_profile",
    "rook.agent.profile_reconciliation",
)


def _site_packages_root() -> str:
    return os.path.join(sys.prefix, "Lib", "site-packages")


def _check_origins() -> int:
    """Import rook + LM2 modules and assert their origin is the deployed
    site-packages. 0 = PASS, 1 = FAIL. Prints rook/server/LM2 origins."""
    import importlib

    spr = _site_packages_root()
    print(f"  sys.prefix: {sys.prefix}")
    print(f"  site-packages root: {spr}")
    try:
        import rook
        import rook.server
    except Exception as exc:  # an import failure is a coherence FAIL
        _p("FAIL", f"could not import rook/rook.server: {exc!r}")
        return 1

    print(f"  rook.__file__: {rook.__file__}")
    print(f"  rook.server.__file__: {rook.server.__file__}")
    failed = False
    for mod_file, name in ((rook.__file__, "rook"), (rook.server.__file__, "rook.server")):
        if not module_origin_ok(mod_file, spr):
            _p("FAIL", f"{name} not under deployed site-packages ({mod_file})")
            failed = True

    for name in _LM2_MODULES:
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            _p("FAIL", f"LM2 module {name} did not import: {exc!r}")
            failed = True
            continue
        mod_file = getattr(mod, "__file__", "")
        print(f"  {name}.__file__: {mod_file}")
        if not module_origin_ok(mod_file, spr):
            _p("FAIL", f"{name} not under deployed site-packages ({mod_file})")
            failed = True

    return 1 if failed else 0


def run_coherence() -> int:
    print("== coherence ==")
    rc = _check_origins()
    if rc == 0:
        _p("PASS", "all LM2 modules import from deployed site-packages")
    return rc


# --- surface evidence (lazy rook import; gated behind _check_origins) ---

_REQUIRED_BASE = frozenset(
    {
        "request_tools",
        "search_tools",
        "gh_snapshot",
        "gh_create_csharp_script",
        "gh_update_script",
        "gh_errors",
    }
)
_EXPECTED_EXCLUDED = ("gh_exploration", "gh_knowledge", "gh_validation")


def run_surface() -> int:
    print("== surface ==")
    rc = _check_origins()
    if rc != 0:
        _p("FAIL", "origin guard failed; refusing surface work")
        return rc

    import asyncio

    from rook.server import list_tools
    from rook.agent.tool_registry import (
        build_catalog_from_mcp_tools,
        get_catalog_cache_path,
        load_catalog_from_cache,
    )
    from rook.agent.tool_groups import TOOL_GROUPS
    from rook.agent.capability_inventory import build_inventory, collect_live_sources
    from rook.agent.execution_profile import (
        readonly_excluded_mcp_only_groups,
        readonly_profile_from_sources,
        resolve_profile,
    )
    from rook.agent.profile_reconciliation import reconcile_profile

    try:
        tools = asyncio.run(list_tools())
        catalog = build_catalog_from_mcp_tools(tools)
    except Exception as exc:
        _p("FAIL", f"catalog build from deployed list_tools() failed: {exc!r}")
        return 1
    if not catalog:
        _p("FAIL", "deployed list_tools() produced an empty catalog")
        return 1

    sources = collect_live_sources()
    inventory = build_inventory(sources, catalog)
    profile = readonly_profile_from_sources(sources)
    resolution = resolve_profile(profile, inventory)
    rec = reconcile_profile(resolution, sources, catalog)

    histogram: dict = {}
    for finding in rec.registry_findings:
        histogram[finding.code] = histogram.get(finding.code, 0) + 1
    print(
        format_surface_evidence(
            catalog_count=len(catalog),
            profile_name=rec.profile_name,
            intended_count=len(rec.intended_names),
            active_count=len(rec.active_names),
            finding_histogram=histogram,
            profile_findings_count=len(rec.profile_findings),
        )
    )

    failed = False

    excluded = readonly_excluded_mcp_only_groups(sources)
    if excluded != _EXPECTED_EXCLUDED:
        _p("FAIL", f"readonly_excluded_mcp_only_groups != {_EXPECTED_EXCLUDED}: {excluded}")
        failed = True
    overlap = set(profile.groups) & set(_EXPECTED_EXCLUDED)
    if overlap:
        _p("FAIL", f"readonly profile includes MCP-only groups: {sorted(overlap)}")
        failed = True

    catalog_group_names = {
        g for g, members in TOOL_GROUPS.items() if any(m in catalog for m in members)
    }
    group_failed = {
        f.tool for f in rec.registry_findings if f.code == "group_activation_failed"
    }
    degenerate = degenerate_activation_failures(group_failed, catalog_group_names)
    if degenerate:
        _p("FAIL", f"groups present in catalog failed to activate: {list(degenerate)}")
        failed = True

    required = set(_REQUIRED_BASE) | set(resolution.tool_names)
    cache_path = get_catalog_cache_path()
    cached = load_catalog_from_cache(cache_path)
    cache_keys = None if cached is None else set(cached.keys())
    verdict = classify_cache(cache_keys, set(catalog.keys()), required)
    if verdict == "absent":
        _p("DEGRADED", f"no catalog cache at {cache_path}; built from live list_tools()")
    elif verdict == "current":
        _p("PASS", "catalog cache matches deployed runtime")
    elif verdict == "warning":
        delta = sorted(cache_keys ^ set(catalog.keys()))
        shown = delta[:20]
        suffix = " ..." if len(delta) > 20 else ""
        _p("WARNING", f"catalog cache drifts (non-required): {shown}{suffix}")
    else:  # "fail"
        delta = sorted((cache_keys ^ set(catalog.keys())) & required)
        _p("FAIL", f"catalog cache drift touches required tools: {delta}")
        failed = True

    if failed:
        _p("FAIL", "surface evidence smoke failed")
        return 1
    _p("PASS", "surface evidence smoke passed")
    return 0


# --- CLI ---

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lm_surface_smoke",
        description="LM live-smoke diagnostic (deployed-runtime coherence + surface evidence).",
    )
    parser.add_argument("command", choices=("coherence", "surface"))
    return parser


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    pythonpath = os.environ.get("PYTHONPATH", "")
    print(f"PYTHONPATH={pythonpath!r}")
    if not pythonpath_clean(pythonpath):
        _p(
            "FAIL",
            "PYTHONPATH is non-empty; refusing to run (it can shadow deployed "
            "site-packages with repo source)",
        )
        return 1
    if args.command == "coherence":
        return run_coherence()
    return run_surface()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the gate + parser tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_lm_surface_smoke.py -q`
Expected: PASS (8 tests — the 5 helper tests + 3 new). The `test_main_fails_fast_on_nonempty_pythonpath` test confirms the gate returns 1 without importing `rook`.

- [ ] **Step 5: Verify the script compiles and the parser help works**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile scripts/lm_surface_smoke.py && mcp_server/.venv/Scripts/python.exe scripts/lm_surface_smoke.py --help`
Expected: `py_compile` silent; `--help` prints usage listing the `{coherence,surface}` choices and exits 0. (This runs under the repo dev venv and only reaches argparse — it does not import `rook` because `--help` exits before dispatch.)

- [ ] **Step 6: Commit**

```bash
git add scripts/lm_surface_smoke.py mcp_server/tests/test_lm_surface_smoke.py
git commit -m "feat(lm-smoke): coherence + surface subcommands with PYTHONPATH/origin gates"
```

---

### Task 3: Runbook

**Files:**
- Create: `docs/superpowers/runbooks/2026-06-21-lm-surface-smoke-checklist.md`

**Interfaces:**
- Consumes: the `scripts/lm_surface_smoke.py` subcommands and their PASS/FAIL/DEGRADED/WARNING output (Task 2).
- Produces: nothing (documentation).

- [ ] **Step 1: Create the runbook**

Create `docs/superpowers/runbooks/2026-06-21-lm-surface-smoke-checklist.md`:

````markdown
# LM Live-Smoke Checklist (pre-LM2E)

Manual/diagnostic checkpoint after LM2A–D. Run the steps in order; each gate
must pass before the next is meaningful. The script is a diagnostic only — it
deploys nothing and starts/stops nothing. You run the deploy, Rhino, and
RookChat steps.

Deployed venv interpreter (used for every script command below):
`C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe`

---

## Gate 0 — Fresh release deploy (manual)

The deployed runtime must contain LM2A–D before anything else.

1. Close Rhino and stop the rook MCP (so the deploy can recreate the venv).
2. From the repo, run the release deploy:
   `pwsh -File scripts/deploy-local-testing.ps1` (release mode).
3. Restart Rhino.

**PASS:** the deploy completes and its own release verification passes
(`rook.server.__file__` under site-packages; all seven `rhino_2d_to_3d_*`
tools advertised). **FAIL:** the deploy errors or its verification fails — fix
the deploy before continuing.

---

## Gate 1 — Coherence

```powershell
$env:PYTHONPATH=""; & "C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe" "C:/UDEV/Rook/scripts/lm_surface_smoke.py" coherence
```

**Expected evidence:** prints `PYTHONPATH=''`, `sys.prefix` under
`…/Rook/venv`, and a `…__file__` line for `rook`, `rook.server`, and each of the
four LM2 modules — every path under `…/Rook/venv/Lib/site-packages/rook`.

**PASS:** final line `PASS: all LM2 modules import from deployed site-packages`
(exit 0). **FAIL:** any `FAIL:` line — a module is absent, failed to import, or
resolved from repo source (split-brain) — or a non-empty `PYTHONPATH`. Re-run
Gate 0.

### Gate 1b — Chat runtime currency (manual)

Open RookChat and confirm the model dropdown populates (cloud + local models).
An empty dropdown means a stale AppData chat runtime (no `/agent/chat/models`)
— redeploy / clear the shadowing `RookChatService.json`. **PASS:** dropdown
populates. **FAIL:** empty dropdown.

---

## Gate 2 — Surface evidence

```powershell
$env:PYTHONPATH=""; & "C:/Users/bring/AppData/Local/Rook/venv/Scripts/python.exe" "C:/UDEV/Rook/scripts/lm_surface_smoke.py" surface
```

**Expected evidence:** the origin guard lines (as Gate 1), then a catalog tool
count, the readonly profile name/intended/active counts, a `registry_findings
by code` histogram, and the profile-findings count.

**PASS:** final line `PASS: surface evidence smoke passed` (exit 0) — the
readonly MCP-only exclusion holds (`gh_exploration`, `gh_knowledge`,
`gh_validation` excluded), no catalog-present group failed to activate, and the
cache (if present) does not drift on a required tool.
**DEGRADED:** a `DEGRADED:` cache-absent line is informational, not a failure —
the surface was still built from the live `list_tools()`.
**WARNING:** a `WARNING:` cache-drift line on non-required tools — note it, not a
failure.
**FAIL:** any `FAIL:` line (empty catalog, broken exclusion, a catalog-present
group failing to activate, or cache drift on a required tool).

---

## Gate 3 — GH C# repair canary (manual, RookChat)

Through RookChat:

1. Ask it to create a C# Grasshopper script with a deliberate compile error —
   e.g. an output pin `A` (double) set from an undefined symbol:
   "Create a C# script component with output A (double) where `A = nope + 1;`."
2. Inspect the create result: confirm `data.script_receipt` is present with
   `mutation`, `verification`, `artifact_status`, and `repair_anchor`.
3. Ask it to repair: "Set `A = 42.0;` instead."
4. Confirm the receipt's `artifact_status` reaches `usable` and `gh_errors` is
   clean.

**PASS:** receipt present on create, repair reaches `usable`, errors clean.
**FAIL:** receipt absent or repair does not reach `usable`.

### Optional complement (assistant-run, once Rhino is up)

The assistant can cross-check the deployed GH C# path at the MCP-tool level
(`gh_create_csharp_script` → `gh_update_script` → `gh_errors`) for a
deterministic second data point. This complements — does not replace — the
manual RookChat run above.

---

## Outcome summary

Record per gate: `PASS` / `FAIL` / `DEGRADED` / `WARNING`. Gate 0 and Gate 1
are hard gates (must pass). Gate 2 `DEGRADED`/`WARNING` are acceptable to
proceed with a note. Any `FAIL` blocks the LM2E start until resolved.
````

- [ ] **Step 2: Verify the runbook renders and references match the script**

Run: `mcp_server/.venv/Scripts/python.exe scripts/lm_surface_smoke.py --help`
Confirm the subcommand names in the runbook (`coherence`, `surface`) match the `--help` output. (No automated test for prose; this is a manual consistency check.)

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/runbooks/2026-06-21-lm-surface-smoke-checklist.md
git commit -m "docs(lm-smoke): live-smoke runbook (deploy/coherence/surface/canary)"
```

---

## Self-Review

**1. Spec coverage:**
- Diagnostic script, two subcommands, deployed-venv invocation → Tasks 1–2. ✓
- PYTHONPATH enforced (print + FAIL if non-empty, before rook import) → Task 2 `main` + `test_main_fails_fast_on_nonempty_pythonpath`. ✓
- Coherence: import-origin check under site-packages, prints rook/server/LM2 origins → Task 2 `_check_origins`/`run_coherence`. ✓
- Surface: origin guard first, catalog from `asyncio.run(list_tools())`, chain, readonly-exclusion + non-degenerate-activation assertions, cache tri-state with tool-names-only required set → Task 2 `run_surface`. ✓
- Pure helpers (`pythonpath_clean`, `module_origin_ok`, `classify_cache`, `degenerate_activation_failures`, `format_surface_evidence`) + tests via `spec_from_file_location`, no deployed-import mocking → Task 1. ✓
- Gate-0 deploy (manual), chat-runtime currency (manual), canary (manual) + optional MCP complement → Task 3 runbook. ✓
- Script is diagnostic only (no deploy/start/stop/sys.path injection) → no step adds any; Global Constraints restate. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code; every run step shows the exact command and expected outcome. ✓

**3. Type consistency:** Helper names and signatures identical across Task 1 (definition), Task 2 (use in `run_surface`/`main`), and the tests. `classify_cache` returns the four string literals used by `run_surface`'s branch. `degenerate_activation_failures` takes `(group_failed_tools, catalog_group_names)` in both definition and caller. `format_surface_evidence` keyword args match between definition, caller, and test. The required set in `run_surface` (`_REQUIRED_BASE | resolution.tool_names`) matches the spec's tool-names-only set. ✓
