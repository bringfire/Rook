# Grasshopper skill cascade routing acceptance

Date: 2026-08-03

Decision: **PASS for the deterministic private acceptance boundary.** The unattended Codex CLI smoke is **incomplete environmental evidence**. It is neither a Rook product failure nor a live pass, and it is non-blocking under the amended plan.

## Provenance

- Base: `93fe02e58836934edf836c13a3a92439328616b8`
- Approved specification: `96f42a2b082f7c213c5071a746aa00c2454a88e9`
- Approved plan: `acb7edb773b0b7cb73316c4469b02b8ab077a21b`
- Design implementation: `f9427596`
- Planning implementation: `3553ea11`
- Execution implementation: `2814bacd`
- Consolidation retirement and installer migration: `ccdd280704b2db675917435615decb150ba13c27`
- Installer and installed-runtime acceptance head: `ccdd280704b2db675917435615decb150ba13c27`
- Final reviewed skill-contract head: `cbbee98f535217d1414ce5ae8439f0d045a3a519`
- Chirp release provenance: `2eedab6c9aaa19e458cbd939889e980f781445f3`

The installer hash, four installation cycles, installed-runtime checks, and installed mirror evidence were captured at `ccdd2807`. Commit `cbbee98f` subsequently corrected 10 skill-mirror and focused-test paths without changing runtime or installer code. Static mirror equality and the fresh 75-pass focused cascade gate cover `cbbee98f`; no rebuild, reinstall, or live-host rerun was required for that contract-only correction.

## Deterministic skill and test gates

- Integrated focused cascade gate at `cbbee98f`: **75 passed, 1 deselected**, with 11 warnings.
- The one deselected test is `test_gh_replay_recipe_strict_partial_failure_is_recorded_as_partial`. Its handler is lifecycle-contained at all reachable ingresses; the stale unreachable-handler test remains separate pre-existing debt.
- Lifecycle/containment proof: **195 passed**.
- Focused installer migration gate at `ccdd2807`: **8 passed, 36 deselected**.
- `uv lock --check`: passed.
- `git diff --check`: passed at the implementation checkpoint.
- Repository-wide suite: not run, as required by the approved plan and prior baseline comparison.

At `cbbee98f`, the retained `.agents`, `.claude`, and installer skill mirrors have identical recursive relative-file inventories and byte-identical contents for `design-grasshopper`, `plan-grasshopper`, and `execute-grasshopper`. The installed mirror evidence applies to `ccdd2807`. The retired `consolidate` skill is absent from active user-facing roots while `gh_consolidate`, DSPy implementation, and developer maintenance capability remain unchanged.

## Immutable scenario replay

Task 0 fixture SHA-256: `D8CCAD1AABF3F6D51065AEA7C290D26B973AA7772D428613220DBDFBFDDC1775`.

| Scenario | Baseline SHA-256 | Candidate SHA-256 | Candidate outcome |
|---|---|---|---|
| clear brief | `EF82DFCFF5B82D42D41BA2D39980F29AC2B941208BA7C4C4A2240D0D622E2FA1` | `944D831C09E99C1FA8D20088F7515AE512C36F272225A74F7420395DDB267EEF` | Routes directly to execute with current live admission, bounded ownership, and verification. |
| ambiguous brief | `0D920C39EABBCF406969FBE761EE6F58B5369ECF79DC11CBC2C167B8D2927EC9` | `997C0E41691BC1CA6BC31F71D03F7114113FAE1C90968511A7B52C9A0914BE20` | Routes to read-only design and a material user decision; no automatic next stage. |
| high-risk existing canvas | `57CD15AC72F84CD4C9C1E1C5F1BEA89F223BDF15E9219EA3153F21B2B238A392` | `06F5E566B6A769D2C36F270E92574AA304E21F693CD4F0C95568629E5CD91D8C` | Uses optional planning with a structural baseline and approval before topology or preservation changes. |
| missing Wasp | `6E259D2F8841A2FA7E5CE4AE1D397F0D0E3A35E4F3787558FCBA97EEA346B60F` | `10EFD193B57A7311916E716FC1D9994BC459D3740E198A633AB7115013355A42` | Fails live admission with zero mutation. |
| successful without consolidation | `EEB9D8BF1317806841F165BD5119505E14865DAB4C6372CCCAC35E212AE62CEF` | `7F19D1411382C6B780405EE2B2B89E108BA210AF637BC043B6428D6345E895F8` | Returns terminal success without consolidation or a knowledge write. |

Two non-blocking evaluator observations were retained: the clear-brief prompt itself supplied the empty-document context, and real execution still requires `gh_status` admission even when a scenario stipulates successful operations.

## Release payload and installer

The detached release worktree remained clean at `ccdd280704b2db675917435615decb150ba13c27`; Chirp remained clean at `2eedab6c9aaa19e458cbd939889e980f781445f3`.

- Native Release build: passed with MSVC `14.44.35207`, zero warnings and zero errors.
- Companion Release build: passed with zero errors and existing analyzer warnings.
- RookBIM Release build after the companion: passed with zero warnings and zero errors.
- Python runtime: CPython `3.11.9`.
- Wheelhouse: 106 wheels; Rook `1.5.16`; MCP `1.28.1`; no MCP 2.x wheel.
- Rook and Chirp temporary-runtime imports, audits, and `pip check`: passed.
- Installer: `C:/Users/aryan/source/repos/Rook-cascade-acceptance/installer/output/Rook-Setup-1.5.16.exe`
- Installer size: `236,967,187` bytes.
- Installer SHA-256: `0C5F2D818DDE7DAE0493527D296607F58FD986C4D43C7AFF45702078B37469C5`.

The manifest records Rook `ccdd280704b2db675917435615decb150ba13c27`, Chirp `2eedab6c9aaa19e458cbd939889e980f781445f3`, release `1.5.16`, Python `3.11.9`, and MCP `1.28.1`.

## Installed migration and mirror acceptance

All four exact installer cycles exited `0`:

1. `selected-first`: `plugins,mcp,codex`
2. `selected-repair`: `plugins,mcp,codex`
3. `deselected`: `plugins,mcp`
4. `selected-final`: `plugins,mcp,codex`

The exact retired targets `design-road`, `masterplan-roads`, and `consolidate` were absent after cleanup. The Codex sibling sentinel and Claude sibling sentinel were preserved. Cleanup completed, and the installed `design-grasshopper`, `plan-grasshopper`, and `execute-grasshopper` roots were recursively byte-identical to the packaged roots.

## Advisory unattended Codex CLI evidence

The unattended live attempt is incomplete because the local Codex environment did not admit approval-requiring MCP calls. It is not part of the required acceptance decision.

Evidence progression:

1. Codex CLI `0.116.0` rejected the local `service_tier = "default"` value before MCP startup.
2. A test-only `service_tier="fast"` override exposed that CLI `0.116.0` was too old for the configured `gpt-5.6-sol` model.
3. After the user upgraded to Codex CLI `0.146.0`, unattended MCP calls were cancelled by the local approval boundary.
4. A final diagnostic attempt proved Grasshopper preparation itself: the harness-owned Rhino process loaded Grasshopper, obtained an active visible canvas and empty document, and reported `ready_for_edit=true` with `object_count=0`. The subsequent Codex MCP calls were still cancelled, so Codex returned `success=false` with no created or deleted IDs and no graph mutation.

`-a never` means never prompt; it does not approve MCP calls that independently require approval. No global Codex configuration or Rook MCP approval policy was changed. Although a per-invocation approval-mode override exists, it was deliberately not used.

The Rook MCP configuration for these attempts points to the installed runtime under `%LOCALAPPDATA%`. The implementation and detached release worktrees supplied provenance and orchestration only; they did not launch the MCP server used by Codex.

Preserved ignored evidence:

- `.scratch/grasshopper-skill-cascade-routing/live/artifacts/rhino-runtime-20260803-104523-d36e0494/manifest.json`
- `.scratch/grasshopper-skill-cascade-routing/live/artifacts/rhino-runtime-20260803-105716-072f385a/manifest.json`
- `.scratch/grasshopper-skill-cascade-routing/live/artifacts/rhino-runtime-20260803-110144-366e8494/manifest.json`
- `.scratch/grasshopper-skill-cascade-routing/live/artifacts/rhino-runtime-20260803-111304-c2a402fa/manifest.json`
- `.scratch/grasshopper-skill-cascade-routing/live/grasshopper-preparation.json`
- `.scratch/grasshopper-skill-cascade-routing/live/result.json`
- `.scratch/grasshopper-skill-cascade-routing/live/events.jsonl`
- `.scratch/grasshopper-skill-cascade-routing/live/codex.stderr.log`

All owned hosts exited through graceful harness cleanup, and no Rhino, Revit, Grasshopper, or Rook MCP process remained afterward.

The source-based Grasshopper preparation helper incremented usage counters in `knowledge/gh/operations_knowledge.json`. That tracked change was restored exactly before acceptance. Preventing acceptance helpers from writing tracked knowledge is separate test-hygiene debt; no knowledge-data change enters this candidate.

A later manual advisory smoke may be run through the normal Codex app against an owned empty Rhino/Grasshopper session, where MCP approvals can be handled normally. It is not required for this private PR.

## Exact changed-path inventory

The accepted product contains the following 74 implementation paths relative to the approved plan, followed by this plan amendment and report. No native, managed Rhino/RookBIM, dependency, lock, bridge, DSPy, knowledge-data, or unrelated-skill path changed.

```text
D .agents/skills/consolidate/SKILL.md
D .agents/skills/consolidate/references/consolidation-paths.md
M .agents/skills/design-grasshopper/SKILL.md
M .agents/skills/design-grasshopper/references/explore-checklist.md
A .agents/skills/design-grasshopper/references/wasp-admission.md
D .agents/skills/design-grasshopper/references/wasp-domain-context.md
D .agents/skills/design-grasshopper/references/wasp-rhino-scaffold.md
M .agents/skills/execute-grasshopper/SKILL.md
M .agents/skills/execute-grasshopper/references/checkpoint-protocol.md
M .agents/skills/plan-grasshopper/SKILL.md
M .agents/skills/plan-grasshopper/references/tool-call-patterns.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-aggregate.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-catalog.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-constraints.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-disco-export.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-field.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-grammar-aggregate.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-hierarchy.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-learn.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-parts.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-rules.md
D .agents/skills/plan-grasshopper/references/wasp/wasp-save-load.md
D .claude/skills/consolidate/SKILL.md
D .claude/skills/consolidate/references/consolidation-paths.md
M .claude/skills/design-grasshopper/SKILL.md
M .claude/skills/design-grasshopper/references/explore-checklist.md
A .claude/skills/design-grasshopper/references/wasp-admission.md
D .claude/skills/design-grasshopper/references/wasp-domain-context.md
D .claude/skills/design-grasshopper/references/wasp-rhino-scaffold.md
M .claude/skills/execute-grasshopper/SKILL.md
M .claude/skills/execute-grasshopper/references/checkpoint-protocol.md
M .claude/skills/plan-grasshopper/SKILL.md
M .claude/skills/plan-grasshopper/references/tool-call-patterns.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-aggregate.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-catalog.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-constraints.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-disco-export.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-field.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-grammar-aggregate.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-hierarchy.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-learn.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-parts.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-rules.md
D .claude/skills/plan-grasshopper/references/wasp/wasp-save-load.md
M AGENT_SETUP.md
M QUICK_START.md
M README.md
M installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md
M installer/agent-assets/ROOK_CODEX_POST_INSTALL.md
M installer/agent-assets/codex-skills/design-grasshopper/SKILL.md
M installer/agent-assets/codex-skills/design-grasshopper/references/explore-checklist.md
A installer/agent-assets/codex-skills/design-grasshopper/references/wasp-admission.md
D installer/agent-assets/codex-skills/design-grasshopper/references/wasp-domain-context.md
D installer/agent-assets/codex-skills/design-grasshopper/references/wasp-rhino-scaffold.md
M installer/agent-assets/codex-skills/execute-grasshopper/SKILL.md
M installer/agent-assets/codex-skills/execute-grasshopper/references/checkpoint-protocol.md
M installer/agent-assets/codex-skills/plan-grasshopper/SKILL.md
M installer/agent-assets/codex-skills/plan-grasshopper/references/tool-call-patterns.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-aggregate.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-catalog.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-constraints.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-disco-export.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-field.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-grammar-aggregate.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-hierarchy.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-learn.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-parts.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-rules.md
D installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-save-load.md
M installer/post_install.py
M mcp_server/src/rook/server.py
A mcp_server/tests/test_grasshopper_skill_cascade_contract.py
M mcp_server/tests/test_python_runtime_install.py
M scripts/session-start.sh
M docs/superpowers/plans/2026-08-03-grasshopper-skill-cascade-routing.md
A docs/superpowers/reports/2026-08-03-grasshopper-skill-cascade-routing-acceptance.md
```

## Final disposition

The deterministic private acceptance boundary is complete. Installer, installed-runtime, migration, sibling-preservation, and installed-mirror evidence is accepted at `ccdd280704b2db675917435615decb150ba13c27`. The final routed three-skill contract and byte-identical repository mirrors are accepted at `cbbee98f535217d1414ce5ae8439f0d045a3a519` through the fresh focused cascade gate.

Public `rook-release` promotion remains a separate, non-blocking Gate 2 based on the accepted private SHA as provenance. No public promotion work has started.
