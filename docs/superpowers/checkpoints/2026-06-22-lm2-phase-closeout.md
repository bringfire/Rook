# LM2 Phase Closeout — Capability / Surface Evidence

**Date:** 2026-06-22
**Status:** CLOSED (complete except tracked residuals)
**Campaign:** Local/Internal Models roadmap — `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md` (phase LM2)

---

## What LM2 set out to do

LM2 is the **capability / surface-evidence** phase: make the surfaces a local model is
allowed to see *provably coherent* with the surfaces it can actually dispatch, as
**read-only diagnostic evidence** — no runtime, visibility, schema, or wire behavior is
changed by any LM2 module. The north-star deliverables were execution-profile membership
for `rookchat_local`, `readonly`, `planner`, `external_mcp` (and eventually
`rookchat_cloud`), plus a "visible-implies-dispatchable" audit whose exit criterion is:
**a tool cannot become local-model-visible without a dispatch path.**

## What LM2 now guarantees (on the deployed runtime)

Three independent surfaces are now provable from the deployed runtime, each clean today:

| Surface | Proof | Current signal |
|---|---|---|
| **Runtime import coherence** | smoke `coherence` | all LM2 modules import from deployed site-packages |
| **Internal / local execution surface** | smoke `surface` | readonly 64 intended == 64 active; `not_dispatchable: 4` (tracked, #303); catalog 416 |
| **Public MCP wire surface** | smoke `external` | 416 advertised / 431 wire handlers; **`advertised_not_dispatchable: 0`**; `handler_not_advertised: 15` (info) |

Key invariants established:
- **Visible-implies-dispatchable audit** exists and runs over the execution-profile groups
  (LM1A `audit_visible_tool_dispatchability`, consumed by LM2A `reconcile_active_schemas`
  and LM2D `reconcile_profile`).
- **Public MCP contract holds:** every advertised `list_tools` tool reaches a real
  `_call_tool_dispatch` handler (`advertised_not_dispatchable: 0`).
- **Tier-name contract is single-sourced** (`capability_record.TIER_FIELDS`), drift-pinned
  by tests across all five tier surfaces (LM2F yellow-alarm hardening).
- **`external_mcp` is modeled honestly** as a standalone wire audit, NOT forced into the
  tier/group `ProfileDefinition` shape — no `mcp_dispatchable` axis added to
  `CapabilityRecord` (LM2G).

## Execution-profile membership status

| Profile | Status | Notes |
|---|---|---|
| `rookchat_local` | ✓ | tier-only diagnostic seed (LM2B) |
| `readonly` | ✓ | evidence-backed group seed (LM2C) + reconciliation (LM2D) |
| `planner` | ✓ | evidence-backed planner seed + tier centralization (LM2F) |
| `external_mcp` | ✓ | catalog-vs-wire-dispatch audit, distinct visibility model (LM2G) |
| `rookchat_cloud` | deferred | needs a real runtime constant/policy before it can be modeled honestly |

## Slices (all merged to `main`)

| Slice | What | PR / merge |
|---|---|---|
| LM2A | capability record + inventory reconciliation | #293 / `e11abec` |
| LM2B | read-only `execution_profile` view | #294 / `9a69bb0` |
| LM2C | readonly group evidence + faithful local readonly seed | #295 / `42e07eb` |
| LM2D | profile reconciliation vs disposable active-schema evidence | #297 / `d2d3ecc` |
| live-smoke checkpoint | `scripts/lm_surface_smoke.py` (coherence/surface) | #299 / `10966e0` |
| LM2E | runtime-faithful local-tool dispatch evidence | #302 / `50e6e31` |
| LM2F | planner profile semantics + tier-name centralization | #304 / `b123ebf` |
| LM2G | external_mcp catalog-vs-wire-dispatch audit | #306 / `ba7b7f6` |

## Modules delivered (all read-only, import-light)

- `mcp_server/src/rook/agent/capability_record.py` — stdlib-only frozen types; `TIER_FIELDS`.
- `mcp_server/src/rook/agent/capability_inventory.py` — `build_inventory`,
  `reconcile_active_schemas`, `collect_live_sources`, `collect_runtime_sources`.
- `mcp_server/src/rook/agent/execution_profile.py` — `ProfileDefinition`/`resolve_profile`,
  `readonly_profile_from_sources`, `planner_profile_from_sources`, default seeds.
- `mcp_server/src/rook/agent/profile_reconciliation.py` — `reconcile_profile`.
- `mcp_server/src/rook/agent/external_mcp.py` — `extract_wire_dispatch_evidence_from_source`,
  `collect_wire_dispatch_evidence`, `reconcile_external_mcp`, `format_external_mcp_report`.
- `scripts/lm_surface_smoke.py` — `coherence` / `surface` / `external` subcommands.

## How to re-verify (deployed runtime)

Run under the **deployed venv interpreter** with an **empty `PYTHONPATH`** (the smoke
refuses otherwise, to avoid shadowing deployed site-packages with repo source). Because of
the deploy gap (#300), first re-mirror current `main` into deployed site-packages:

```
# 1. re-mirror (stopgap for #300)
robocopy C:\UDEV\Rook\mcp_server\src\rook ^
         C:\Users\bring\AppData\Local\Rook\venv\Lib\site-packages\rook /MIR

# 2. run the three surfaces (PowerShell)
$env:PYTHONPATH = ""
$py = "C:\Users\bring\AppData\Local\Rook\venv\Scripts\python.exe"
& $py C:\UDEV\Rook\scripts\lm_surface_smoke.py coherence   # expect PASS
& $py C:\UDEV\Rook\scripts\lm_surface_smoke.py surface     # expect PASS, not_dispatchable: 4 (#303)
& $py C:\UDEV\Rook\scripts\lm_surface_smoke.py external    # expect PASS, advertised_not_dispatchable: 0, handler_not_advertised: 15
```

Local (repo) regression: the LM2 suite (109 tests) under `mcp_server/.venv`:

```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ^
  mcp_server/tests/test_external_mcp.py ^
  mcp_server/tests/test_lm_surface_smoke.py ^
  mcp_server/tests/test_capability_record.py ^
  mcp_server/tests/test_capability_inventory.py ^
  mcp_server/tests/test_execution_profile.py ^
  mcp_server/tests/test_profile_reconciliation.py
```

Runbook: `docs/superpowers/runbooks/2026-06-21-lm-surface-smoke-checklist.md`.

## Open residuals (tracked, NOT blocking closeout)

- **#303** — 4 genuine readonly visible-but-not-dispatchable tools (`gh_canvas_image`,
  `scene_classify`, `scene_overlay`, `scene_query`): local-visible via a non-MCP
  readonly-allowed group but with no bridge route and no local handler. True positives.
  Remediation = add bridge routes OR drop them from the readonly-allowed groups.
- **#300** — deploy bundled-CPython gap: `deploy-local-testing.ps1` post_install aborts
  because the bundled private CPython runtime is absent, so the venv can't be recreated.
  Belongs to `chore/dev-infra`. The smoke uses a manual source-mirror stopgap until fixed.
- **`rookchat_cloud`** profile — deferred until a real runtime constant/policy exists.
- Deferred helper (from LM2C): a "readonly-allowed but missing group definition" drift check.
- NOT yet in scope: an audited surface *compiler* the registry actually consults at runtime
  (LM2 produces evidence; it does not yet gate runtime visibility).

## Recommended next move

Either **#303 remediation** (clean the local readonly surface before more planner
machinery — a clean readonly/local surface matters for Planner trust), **#300 infra fix**
(if deployment friction is costing time), or **LM3** (if the roadmap's next phase depends
more on PlanGraph/planner execution than surface cleanliness). Leaning #303.
