# Rook 2.0 Minimal Base — Living Roadmap

- **Status:** ACTIVE — update as research/slices land. Created 2026-07-04 (session: two-pole reframe + v0.1 plugin validation).
- **Governing docs:** `docs/superpowers/specs/2026-07-03-rook-2.0-minimal-iteration-design.md` (topology §11), memory `rook-as-agentic-plugin-thesis`.
- **Thesis:** "human collaboration is mediated by tools; the future of human collaboration will not be subscription based." Baseline = open-weight models (local + open-weight cloud). Subscription frontier models are guests, never the bar.

## Method (locked)

**Subtraction by addition to a minimal working base.** New trunk `mcp_server/src/rook2/` inside `bringfire/Rook` (strangler fig; old server untouched, env-selectable entry swap). Radicalism fences:
1. Import allowlist from `rook.*` starts **EMPTY** — nothing grandfathered; entry requires open-weight-tier ablation evidence (LM5K harness is the instrument).
2. Own dependency manifest: stdlib + MCP SDK at birth; every dep earns entry.
3. Black-box tests only (over the wire); no shared fixtures with legacy.
4. Metrics in every PR: trunk LOC, dep count, tool count.

**Architecture:** two-pole broker. Registry entry = `{name, schema, floor, route, receipt_contract}`; floors pluggable: `rooknative` (birth) | `mcneel-core` (reserved) | `python-local` (earned). `list_tools()` = query over registry, never a literal (anti-server.py).

**McNeel relationship:** patterns for the trunk · their **live released surface** as a runtime-peer floor (conformance snapshot per release; rebind-and-retire our overlapping tools) · their **source** only in the fork lab (≤2-file ACP AgentDefinition divergence, ff-mirror main).

**Hermes relationship:** never forked; harness + curator territory (flat skills tree is theirs — seed, diff, harvest; never blind-overwrite).

## Phases

### P0 — Demon hunt (IN PROGRESS, this session)
Fan-out recon over Rook + McNeel + hermes code for hidden couplings before the first stone.
- [ ] Rook-side demons: lean-22 tool classification (pure-proxy vs Python-local machinery), gh_edit epoch statefulness, bridge contract details, startup side effects → **findings below, §Demons**
- [ ] McNeel/hermes-side demons: floor callability, tool advertisement mechanism, ACP custom-agent feasibility, hermes acp launch shape → **findings below, §Demons**
- Exit: demons ranked; any plan-changing demon folded into P1 spec.

### P1 — Minimal-base spec + skeleton
- Spec slice: registry schema (floor field day one), dep budget, boundary test design, safe-22 list (per P0 verdict — may be <22 initially).
- Skeleton: `python -m rook2` = registry + stdio MCP adapter + fresh ~50-line RookNative floor client (discovery read + POST; zero rook.* imports).
- Exit: serves ping + snapshot black-box.

### P2 — MFE: lean surface green through a foreign harness
- Bind safe-22 (or safe-N) to `rooknative` floor; hermes config swapped to `-m rook2`.
- Exit: **tonight's proof ladder passes end-to-end on rook2** (discovery, ping, lean count, sphere, GH snapshot/epoch, /rook setup unaffected). Metrics recorded (target ≈2k LOC, ≈2 deps).

### P3 — Evidence-gated additions begin
- First allowlist candidates (each with ablation on open-weight tier): receipts/contracts modules, knowledge pull-path (vs hermes-memory substitution test — KG is NOT sacred), workflow_validate export when PH lands.
- McNeel conformance snapshot script + first tracked JSON.

### P4 — Fork-lab ACP spike (parallel track, independent)
- Hermes AgentDefinition in McNeel panel (per P0 Part-B verdict: config-only vs minimal C# change).
- Exit: panel-hosted user agent drives rook2 tools. The pole-fusion demo.

### P5 — Continuous subtraction
- Per McNeel release: conformance diff → rebind/retire overlapping tools.
- Harvest loop: diff hermes-evolved skills vs plugin canonical; approved improvements upstreamed.
- Legacy retirement criteria (TBD): rook2 covers daily-driver usage for N weeks.

## Demons Registry (ranked; update as found)

> P0 agent findings land here.

### Rook-side (P0 recon, 2026-07-04 — full report in session)
- **D-R1 CLEARED (was scariest):** `gh_edit` epoch is pure round-trip — server.py:15613 passes it to `/gh/edit` unvalidated/unstored; `apply_gh_edit_contract` post-processes only. **Stateless proxy fully safe for gh_snapshot/gh_edit.**
- **D-R2 (HIGH, MFE-scoping):** the lean-22 splits ~15 pure-native-HTTP (ping/objects/geometry/gh_snapshot/gh_edit/gh_errors/instances/sessions/intent-executes…) vs **7 needing Python machinery**: knowledge trio (`knowledge_query`/`rhino_knowledge_query`/`gh_knowledge_query` = LOCAL_TIER_0 handlers → UnifiedStore/CommandLearner lazy disk loads, tool_dispatcher.py:1206-1262) + `rook_tools_ls/search/read/call` (need capability index built from full list_tools() + LM2A records, server.py:21261). **Decision needed at P1:** MFE ships safe-15 first; knowledge trio = the FIRST allowlist/ablation case (doubles as the hermes-memory-substitution test — Q2 says KG not sacred); meta-tools need a build-time catalog-export JSON (~100 lines) or defer PD.
- **D-R3 (MEDIUM):** bridge contract to replicate: `{success,data}` envelope (bridge.py:1136), dual discovery folders %TEMP%/rook + %LOCALAPPDATA%/Rook/discovery merged w/ stale-PID cleanup (92-96, 515-550), pluginType filter `("native","roadcreator")` (570). PID-liveness failure diagnostics (844-866) NOT replicated in 50 lines — keep client dumb, report raw errors.
- **D-R4 (LOW):** legacy server startup runs DSPy config (~2-3s, non-blocking) + CommandLearner init — neither needed by lean; **no startup side effect Rhino depends on** → rook2 replacing rook breaks nothing in-Rhino.

### McNeel/hermes-side (P0 recon — CAVEAT: agent searched Rook's own native plugin, NOT D:\Rook-2; McNeel-specific claims re-verified/pending)
- **D-M1 RE-SCOPED (2026-07-04, user-prompted recon — binding ALREADY EXISTS both sides):** Rook v1 solves doc-binding at request level: `call_rhino` resolves the selected instance (bridge.py:974-1146), `_RHINO_CONTEXT_DOCUMENT_SN` → `_apply_document_context` injects `documentSerialNumber` into payloads (bridge.py:117-120, 900-913), PanelTargetLock binds doc+process (targeting.py:63-146, 963-976), and C++ handlers resolve via `CRhinoDoc::FromRuntimeSerialNumber` (DocumentHandler.cpp:16-42) — NOT ActiveDoc when serial present. McNeel solves it structurally: **one listener per document** (`Servers[doc.RuntimeSerialNumber]`, RhMcpHost.cs:13-98), agents pooled by (doc_serial, agent_name); slots carry no doc column — doc identity is implicit in the port. **Residual demon (the real one): the race exists only for clients that omit the serial** — ambient-ActiveDoc is the fallback. Therefore: rook2's floor client MUST carry `documentSerialNumber` from first slice (capture at snapshot/instance-select, inject on every mutating call, echo in receipts) — replicate v1's injection, not invent a guard header. Guard-header proposal WITHDRAWN as redundant. Also fold into P3: which lean tools' payloads accept the serial (verify per-route). Parallel v1+rook2 mutation testing is safe once both carry serials to different docs.
- **D-M2 (valid):** RookNative port is OS-assigned per process, no auth, PID-liveness is the client's job (RookServer.cpp:1571,1380) — rook2 floor client must re-discover on connection failure, verify PID, tolerate stale files. (~matches D-R3.)
- **D-M3 (MEDIUM, valid — hermes ACP):** `hermes acp` = **stdio ACP server spawned by the client** (acp_adapter/entry.py:262), no socket mode; `agent-client-protocol==0.9.0` hard-pinned, no version negotiation. P4 spike must check the fork's `rhino/acp/` codegen schema version against 0.9.0 FIRST — version skew is the likeliest P4 killer.
- **D-M4 ✅ RESOLVED (2026-07-04, corrected recon on D:\Rook-2): custom agent is CONFIG-ONLY, zero C# change.** `AgentDefinition` record (Name, Adapter{Claude,Codex,Gemini}, Command, SearchPaths, Model, ExtraArgs, SystemPrompt, Enabled, IsBuiltin) — AgentDefinition.cs:8-17; custom entries live in Rhino PersistentSettings, overlay built-ins by name at runtime (AISettings.cs:44-71, AgentRegistry.Overlay:44-56). The Gemini path is a GENERIC native-ACP spawner: any Command resolved via SearchPaths → ProcessStdioTransport → ClientSideConnection (GeminiConnection.cs:13-49). **Register hermes as Adapter=Gemini.** One nuance (D-M6): GeminiConnection appends `--experimental-acp` (line 28) — hermes must tolerate the flag or get a 2-line shim script (`hermes-acp.cmd` → `hermes acp`), still zero C# change.
- **D-M5 ✅ RESOLVED: conformance snapshot viable on BOTH channels.** Wire: their MCP endpoint serves `tools/list` with full JSON schemas + annotations (McpEndpoint.cs:153-182; 38 tools per PLAN.md:123). Source: one-file-per-tool `[McpServerTool]` attributes under rhino/plugin/Tools/ (ToolRegistry.cs:22-55, reflection scan, no source-gen) — grep-parseable per release. Snapshot script does wire-primary + source-fallback.
- **D-M3 UPDATED:** their ACP targets schema **version 1** (rhino/acp/schema/meta.json:22, codegen'd constant); MCP protocol `2024-11-05` (Protocol.cs:63). hermes's `agent-client-protocol==0.9.0` is a *lib* version implementing protocol v1 — likely compatible; **P4 spike step 1 = live handshake test**, not source archaeology.
- **D-M6 (LOW, new):** hardcoded `--experimental-acp` flag on the generic ACP spawn path (GeminiConnection.cs:28) — shim answer above; also a clean tiny upstream PR candidate ("make ACP flag part of AgentDefinition.ExtraArgs").
- **D-M7 (INFO):** their AgentDispatch turn-gate uses Wait(0)-under-lock (AgentDispatch.cs:170) — deliberate, safe today; noted as fragile-if-modified. Fork code health otherwise strong (their W0 sweep fixed 6 high-severity).

### Known from session evidence
- **D-S1 (design):** hermes curator absorbed/renamed/expanded our flat-tree skill (`software-development/rook-rhino-grasshopper`, 63→176 lines). `/rook setup` v0.2 must be seed-or-diff, never blind reinstall (duplicate risk). Harvest loop required.
- **D-S2 (proportionality):** discipline caused ~10-call ceremony on a 1-call task (GPT-5.5 sphere trace). Skill needs triage ladder; knowledge = pull-not-push. Ablate on open-weight tier before judging.
- **D-S3 (env):** hermes CLI hangs on interactive confirms in non-interactive shells — automation must edit config.yaml directly or use flags.
- **D-S4 ✅ RESOLVED (2026-07-04):** fork renamed `bringfire/rhinomcp-lab` (local: `D:\rhinomcp-lab`, origin updated, upstream=mcneel intact). New trunk repo created: `bringfire/rook2` (local: `C:\UDEV\rook2`, empty — first commit = P1 spec-driven scaffold). **TOPOLOGY UPDATE (floor-flip consequence): rook2 trunk is a STANDALONE repo**, consuming BOTH floors (mcneel-core + rooknative) as released wire surfaces — conformance snapshots apply to both symmetrically. §11 of the design spec and "where 2.0 lives" decisions are SUPERSEDED accordingly: bringfire/Rook = floors + legacy + LM/PH campaigns; rook2 = the broker trunk; five repos total (+plugin, +lab, +release).

- **D-M8 (WATCH):** upstream is effectively single-maintainer — 36/40 recent PRs by `clicky` (Callum), 3 by dcascaval, 1 external. Good: tiny well-formed PRs (D-M6 flag) get one person's direct attention; relationship > process. Risk: bus-factor + identity churn is LIVE — PR #73/78/79 renamed the plugin to 'ai', reverted, re-opened; an open PR adds a safety/permissions tab. Conformance snapshot + discovery assumptions must tolerate a plugin rename; recheck naming before P3 snapshot script.

## OPEN DECISION (2026-07-04, user-raised): FLOOR POSTURE FLIP
Evidence this session (wire-introspectable schemas, per-doc listeners, SlotStore lifecycle, GH2 focus, warm Callum channel) says McNeel's core beats RookNative on every COMMODITY axis. Proposal: invert the default — **`mcneel-core` = default floor for everything his surface covers; RookNative shrinks to the never-McNeel core** (vision, display conduit, video, receipts-bearing GH contract path, analysis hot paths, intent). Anchor invariant #2 ("RookNative sole in-Rhino surface") predates the radical-reduction reframe and should be consciously re-ratified or retired, not inherited. **Deciding artifact: floor-coverage matrix** — lean-15 (+ next tiers) × {mcneel-core 38 tools, rooknative}: what does his surface cover today, what semantics differ, Rhino 8 compat, receipts gap. Callum topics: receipts fields upstream, Rhino 8 support, schema stability. MFE may bind commodity tools to mcneel-core from birth.

## PULL-BACK AUDIT (2026-07-04, end of founding session — flags, not blown past)
- **F1 — The moat needs restating post-flip.** After KG-not-sacred + tools-track-McNeel + harness=hermes + commodity-floor=mcneel-core, Rook's irreducible value = receipts/contract discipline + RookVision/reach surfaces + open-weight reliability scaffold + (knowledge IF ablation proves it). Never re-stated as product identity since the flip. ACTION: deliberate anchor revision — the 2026-06-12 anchor is now contradicted on ≥4 points (Open-Q7 resolution, invariant #2, Layer-2 KG permanence, Part VIII MVP) and tonight's method violated its own no-drift doctrine, productively but unratified.
- **F2 — Two north stars coexist unreconciled.** Planner-harness (PR #395, frozen) builds Rook-owned worker/runner INTO v1; rook2 topology doesn't yet say where PH lives (future `floor: python-local` registry entries? separate service?). ACTION: PH↔rook2 convergence decision before PH's next major slice.
- **F3 — All live validation ran on a guest model (GPT-5.5), which the thesis says is NOT the bar.** Phase-0 open-weight panel results were never recorded. ACTION: P2 exit criterion amended → proof ladder must pass on a baseline-tier model (qwen3-class); record Phase-0 evidence retroactively.
- **F4 — Floor flip is DIRECTION, not day-one dependency.** mcneel-core targets Rhino9/GH2 BETA, 38 tools, single maintainer, naming in flux, less release-mature than rook-release. MFE must not hard-depend on it; rooknative stays the birth floor where the coverage matrix shows R8 gaps. Flip governs the *trajectory* of bindings.
- **F5 — Cross-repo oracle discipline:** differential tester pins v1 by release version (v1 = just another versioned wire surface).
- **F6 — Plugin repo carries v1-shaped claims** (lean env var, `-m rook`) that migrate when rook2 fronts it. Note for plugin v0.2.
- **F7 — PROCESS RULE (root cause of tonight's drift):** at every phase exit, run a pull-back audit — re-read the full decision stack for inherited-invariant contradictions BEFORE the next phase. Stones only after stepping back.

## R9 CORRECTION (2026-07-04, web-verified vs discourse/developer.rhino3d.com)
My "native plugins are version-locked, R9 needs its own SDK" claim was WRONG for Rhino 9: McNeel's stated goal (Steve Baer, Jun 2026) is **NOT to break the C++ SDK for 9 — V8-SDK-built plugins should load in Rhino 9** (pattern held 6→7→8; third-party confirmed in practice). No dedicated R9 C++ SDK exists yet (~1-2 months out, post SDK-freeze); WIP devs build against the Rhino 8 SDK (installed on this machine). CONFIRMED: WIP expires 45 days/weekly builds; RhinoCommon 9.0.x-wip on NuGet. NEW CHEAP EXPERIMENT (do before any port planning): load the EXISTING RookNative.rhp in Rhino 9 WIP → ping/objects smoke. If green, **rooknative serves BOTH R8 and R9 from one build** and the two-floor×two-version picture simplifies massively. WATCH: community reports Rhino 9 runs .NET 9 — Rook's C# companion (net48/net7 dual-target) + GH1 hosting in R9 need their own load smoke; no official C++ porting guide exists yet.

**R9 SMOKE RESULT (2026-07-04): RookNative 1.5.15 (R8-SDK build) LOADS AND SERVES in Rhino 9 WIP** — HTTP up on :57298, unmodified binary. McNeel V8-compat promise holds for Rook's C++ floor → one rooknative build plausibly serves R8+R9. Managed companion auto-load FAILED 3/3 under R9 (GH path unavailable) — the predicted .NET-9 seam; next: surface the real loader error (drag net8.0\Rook.rhp manually) + inspect RookNative's companion target-framework picker. Wire-level ping/objects verification pending. **UPDATE same-night: net8.0\Rook.rhp drag-drop loaded CLEAN in R9 — "native GH callback bridge registered" → FULL Rook 1 stack (C++ floor + C# companion + GH bridge) runs on Rhino 9 from existing binaries, zero code changes.** Root cause isolated: RookNative's companion auto-loader probes R8-era targets (net7.0/net48) — net8.0 works; since drag-drop REGISTERED the companion, Rhino auto-loads it henceforth and the auto-loader failure is moot on this machine. Residual fix = loader probes net8.0 first (one-liner, rook-release installer concern for R9 users). **R9 SMOKE COMPLETE: gh_snapshot returned clean over the wire on Rhino 9 (epoch 1, empty canvas, 0 errors)** — the deepest seam (HTTP → C++ → P/Invoke → C# companion → Grasshopper) verified end-to-end. VERDICT: rooknative serves R8 AND R9 from one existing build; mcneel-core = additive GH2/script layer, per matrix. The P1 spec is now written against a two-generation floor.

## CHAT PANEL DECISION (2026-07-04, user-raised: "can we just use theirs?")
**Direction: YES — retire RookChat; McNeel's AI Panel (hosting the user's agent via ACP, hermes seat = config-only per D-M4) becomes the in-Rhino view.** Deletes ~4.4k LOC agent/chat + C# panel + chat service process (Bucket A realized). Three qualifiers: (1) **R8 gap** — their panel is Rhino-9-only; R8 users use external harnesses (Claude Code/hermes terminal) in the interim → freeze RookChat NOW (no new investment), delete after P4 proves hermes-in-panel driving rook2 on R9; strangler not demolition. (2) **View-shape gap (partially resolves F2):** decision-3's "view" was planner-STATE-shaped (plan graph, receipts, gates); their panel is transcript-shaped → near-term: receipts narrated through agent chat; if state-view proves necessary, it ships as a thin read-only web mount (RookVision pattern), never a new panel. (3) Approval UX: their non-blocking ask_user + per-turn undo vs Rook receipts-gates — verify sufficiency during P4. Callum topic added: Rook intends to deprecate its panel in favor of theirs hosting arbitrary ACP agents.

## Update log
- 2026-07-04: Created. P0 launched (two Explore agents). v0.1 plugin validated same day (see probes/2026-07-04-rook20-v01-hermes-plugin-validation.md).
- 2026-07-05: **Pass-1 implementation plan committed in rook2** (`docs/plans/2026-07-05-pass1-implementation-plan.md`, rook2@6781b2d) — birth-12 registry (supersedes safe-15, erratum applied to the brief), two-track shape (floor ∥ broker → M3 hermes×baseline ladder), R9-primary posture, companion-GUID one-liner + 1.6.0.1 three-site version bump, truthful-discovery stubs, `{success,data,receipt}` contract, fence evolution (provenance manifest, companion allowlist, GUID coherence, BROKER_LOC_CEILING). Brief decisions D1/D2/D4/D5 resolved, D3 parked to rook-release. Founding docs (this roadmap, overnight spec, v0.1 probe) committed to the Rook repo via `codex/rook2-foundations` (PR pending user merge gate). Codex round 1 next.
