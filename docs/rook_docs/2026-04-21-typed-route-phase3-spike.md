# Typed-Route Phase 3 — Empirical Spike

**Date:** 2026-04-21
**Stage:** scope pass (pre-plan, pre-code) — **empirical probes complete 2026-04-21**

## TL;DR — Probe-Gated Outcome (revised 2026-04-21 post-PR-2 API audit)

**Phase 3 = 1 PR shipped. Campaign closed.**

Original 2026-04-21 plan was 2 PRs. PR-2 killed during implementation-time RhinoCommon audit (see §Post-Hoc Finding below).

- **PR-1 — `curve_intersects_axis` on `/surface/revolve` — SHIPPED as `0a72a0f` (PR #82).** Detection is the only signal the caller receives — factory accepts the input and produces invalid-but-successful geometry without the detection.
- **~~PR-2 — `AlignWithSurface` on `/surface/sweep1`~~ — KILLED before scope pass reached implementation.** RhinoCommon does not expose the Align mode via managed API. `SweepOneRail` supports only Freeform + Roadlike; `Brep.CreateFromSweep*` overloads take no Surface argument; assembly-wide grep for `AlignWithSurface` returns 0 matches. Re-parked with strict trigger.
- **`rails_disconnected` on `/surface/sweep2` — DROPPED from Phase 3, permanent deferral.** Sweep2 factory tolerates multi-unit profile-rail gaps (3-unit gap accepted, produced brep). Any pre-validation threshold would regress legal wide-gap cases. See §Probe Findings.

---

**Basis:**
- `rook_docs/2026-04-15-typed-route-gap-analysis.md` — Decision Record (7 rules, boundary policy)
- `rook_docs/2026-04-17-typed-route-phase1-plan.md` — Phase 1 sub-plans (source of the 3 deferred codes)
- `rook_docs/2026-04-20-phase2-surface-curve-spike.md` — spike-memo template (inherited format)
- `rook_docs/2026-04-17-typed-route-phase1-spike.md` — fallback-matrix rhythm (not used here — see §Purpose)
- `rook_docs/work-queue.md` — `Now` entry (resume_entry_point)
- `src/Rook/Handlers/CreateHandler.cs` + `src/RookNative/Handlers/SurfaceHandler.cpp` — deferral comments split across the native/managed boundary (see §Matrix for exact sites)

---

## Purpose of This Spike

Phase 1 (8 routes, PRs #54-60, April 17) and Phase 2 (19 routes, PRs #62-75, April 19-20) shipped the typed-route campaign's first two waves. **Phase 3 deliberately narrows**, not expands.

Three candidate themes surfaced during post-Phase-2 synthesis:
- **Theme A — Primitive migration** (13 `/create` ops → individual `/geometry/*` typed routes). Biggest-leverage, largest scope (4-6 PR campaign).
- **Theme B — Phase 1 error-code polish** (3 deliberately-deferred codes on existing Phase 1 surface routes). Smallest, bounded, within-family.
- **Theme C — Batch primitive creation** (speculative).

**Phase 3 is committed to Theme B.** Themes A and C are explicitly deferred per §Theme A Gate and §Theme C Park below. Rationale:

1. Theme B finishes explicitly-deferred typed-route work from Phase 1 rather than starting a new campaign family. Each code has a `DEFERRED PLAN-CODE` comment pointing at a future PR — those PRs are this campaign.
2. Theme B has real engineering value even if Theme A's ROI turns out weak. **Probe 1 revealed the value is stronger than the memo's initial framing assumed** — `curve_intersects_axis` is NOT a fallthrough replacement; the factory currently produces silent invalid geometry with no `operation_failed` signal at all. PR-1 is the first real diagnostic signal for that failure mode. `AlignWithSurface` is pure schema work (enable a rejected input). Together the two PRs improve agent-facing error-driven routing on silent-bad-output paths that knowledge_record can learn from.
3. Theme A is only compelling if the missing per-primitive MCP surface is causing actual planning/discoverability pain. Agent synthesis 2026-04-21 flagged that primitives already route directly via `/create` — no DSPy long-tail, no latency cost. Theme A is a discoverability/ergonomics play, not a correctness/routing play. Needs product-level signal before committing to a 4-6 PR campaign.
4. Theme C is a spike topic at best, not a campaign candidate.

**Unlike Phase 1/2 spikes**, this one did NOT need a live-Rhino fallback-matrix probe. The scope wasn't "which new verbs deserve typed routes" — it was "how do we detect three specific geometric conditions reliably?" That's detection-heuristic-feasibility probing, resolved in §Probe Findings below.

**Probe-gating decision:** the three probes were run before plan-doc work (after memo authoring, before code), specifically to resolve whether each row was feasible as scoped. Probe-2 results killed the `rails_disconnected` row; Probe-1 results re-framed `curve_intersects_axis` justification. See §Probe Findings below.

---

## 3-Row Candidate Matrix

All three rows are within-family enhancements to existing Phase 1 routes. Zero ABI bumps. No new MCP tools. No new route paths. **Deferrals split across the native/managed boundary** — note the "Boundary" column. Row numbering in this matrix is the original 3-row enumeration; post-probe the middle row drops and the two shipping rows become PR-1 / PR-2 (see §PR Sequence).

| # | Code | Route | Boundary | Current deferral site | Detection approach | Post-probe status |
|---|------|-------|----------|-----------------------|--------------------|-------------------|
| 1 | `curve_intersects_axis` | `/surface/revolve` | **Managed-only** | `src/Rook/Handlers/CreateHandler.cs:1893-1898` in `CreateRevolveStrict`. **Probe 1 revealed the comment's premise is wrong** — curve-crosses-axis does NOT fall through to `operation_failed`. The factory accepts the input and produces a (likely self-intersecting) brep with `success: true`. Native-side pointer comment at `SurfaceHandler.cpp:557-563` mirrors the deferral but holds no code. | Pre-factory geometric check inside `CreateRevolveStrict`, after `ResolveCurveStrict` resolves `curveId`: `Intersection.CurveLine(curve, axisLine, tol, tol)` — reject if any intersection point lies on the profile curve interior (endpoints on axis are permitted, e.g. vase profiles terminating on the axis). | **SHIP (PR-1).** Probe 1 strengthened the justification: detection is the only signal the caller gets today. Tolerance calibration still required but not spike-gating. |
| 2 | `rails_disconnected` | `/surface/sweep2` | **Managed-only** | `src/Rook/Handlers/CreateHandler.cs:1735-1738` in `CreateSweep2Plural`. **Probe 2 revealed the factory accepts multi-unit gaps** — profile ending at x=2 with rail2 at x=5 (3-unit gap) produced a brep with `success: true`. Same for 0.5-unit miss and 0.01-unit near-miss. | N/A — no principled threshold. Any pre-validation rule would either regress legal wide-gap cases (factory tolerates 3+ unit gaps) or be arbitrary. | **DROP (permanent deferral).** Probe 2 killed the detection premise. Re-park with user-workflow trigger: only revisit if a real workflow surfaces a case where factory-tolerated-gap produced geometry that was wrong enough to warrant blocking the operation. |
| 3 | `style="AlignWithSurface"` support | `/surface/sweep1` | **Cross-boundary** (native schema + managed implementation) | Native side rejects the enum value wholesale at `src/RookNative/Handlers/SurfaceHandler.cpp:404-421` before dispatch: `"AlignWithSurface deferred to Phase 2"`. Managed `CreateSweep1Strict` in `CreateHandler.cs` never sees this style today because the request never reaches the managed bridge. | **Native:** accept `"AlignWithSurface"` enum value + add `alignSurfaceId: uuid` schema field (required iff `style="AlignWithSurface"`, mutually-exclusive with `roadlikeUp`). Validate UUID format + presence. **Managed:** receive the new field, resolve to `Surface` via shared helper (candidate reuse: `ResolveSeedSurfaceStrict` from PR #73), invoke `SweepOneRail.SetStyleAlignWithSurface(surface)` before `PerformSweep`. | **SHIP (PR-2).** Structured by precedent (`/surface/patch` in PR #73). Probe 3 deferred to implementation-time RhinoCommon introspection — verify API signature when writing `CreateSweep1Strict`'s new branch. |

**Substrate (post-probe, final PR labels):**
- **PR-1 (`curve_intersects_axis`, matrix row 1):** managed-only enhancement inside `CreateRevolveStrict`. No native schema change, no ABI bump, no new resolver helpers.
- **PR-2 (`AlignWithSurface`, matrix row 3):** cross-boundary. Native schema expanded + managed implementation extended. No ABI bump (field addition is additive).
- **`rails_disconnected` (matrix row 2) — dropped.** Re-parked with user-workflow trigger; not a Phase 3 PR.

---

## Probe Findings (2026-04-21)

Empirical probes run against live Rhino via `.scratch/phase3_probes.py`. Full envelope dumps captured in probe output; summary below.

### Probe 1 — Revolve / `curve_intersects_axis`

| Case | Profile | Axis | Expected | Actual |
|------|---------|------|----------|--------|
| 1.1 | Line (0,0,0)→(5,0,5), endpoint on axis | Z axis 0→10 | Accepted (cone) | ✓ success, Brep bbox [-5,-5,0]→[5,5,5] |
| **1.2** | **Line (-2,0,3)→(2,0,7), crosses axis interior** | **Z axis 0→10** | **Expected: operation_failed** | **✗ success, Brep bbox [-2,-2,3]→[2,2,?]** |
| 1.3 | Horizontal line (0,0,5)→(3,0,5), endpoint on axis | Z axis 0→10 | Accepted (disk) | ✓ success, Brep bbox [-3,-3,5]→[3,3,5] |
| 1.4 | Line (3,0,0)→(3,0,10), parallel to axis | Z axis 0→10 | Accepted (cylinder) | ✓ success, Brep bbox [-3,-3,0]→[3,3,10] |

**Key finding:** Case 1.2 did NOT fall through to `operation_failed` as the memo premise assumed. The factory accepted the curve-crosses-axis input and produced geometry (likely self-intersecting but no signal exposed via the current envelope — `isValid` field returned null). The `DEFERRED PLAN-CODE` comment at `CreateHandler.cs:1893-1898` describes a fallthrough path that doesn't actually exist for this input class.

**Consequence for PR-1:** detection is not replacing a fallthrough — it's the **only** signal the caller will ever get that the input was geometrically invalid. Higher value than the memo's original framing, same implementation surface.

### Probe 2 — Sweep2 / `rails_disconnected`

| Case | Profile | Rails | Expected | Actual |
|------|---------|-------|----------|--------|
| 2.1 | (0,0,5)→(5,0,5), touches both | parallel at x=0, x=5 | Ribbon | ✓ success, `objects_count: 1` |
| **2.2** | **(0,0,5)→(2,0,5), 3-unit gap from rail2** | **parallel at x=0, x=5** | **Rejected or silent no-op** | **✗ success, `objects_count: 1`** |
| 2.3 | (0,0,5)→(4.99,0,5), 0.01-unit near-miss | parallel at x=0, x=5 | Factory decides | ✓ success, `objects_count: 1` |
| 2.4 | (0,0,5)→(4.5,0,5), 0.5-unit gap | parallel at x=0, x=5 | Factory decides | ✓ success, `objects_count: 1` |

**Key finding:** the Sweep2 factory is extremely permissive — accepts multi-unit profile-rail gaps and produces a brep. Case 2.2's **3-unit gap** (profile ends at x=2 with rail at x=5 on a 5-unit rail span — 60% of the rail-to-rail distance) still produced an object. No pre-validation rule can distinguish "disconnected" from "loose but legal" without being arbitrary.

**Phase 1 spike memo warning validated.** The "heuristic too eager" concern was correct — any threshold regresses legal cases.

**Consequence for PR-2:** drop from Phase 3. Re-park `rails_disconnected` as permanent deferral. Trigger to revisit: a user reports a case where a factory-tolerated-gap produced geometry wrong enough to warrant blocking.

### Probe 3 — Sweep1 / AlignWithSurface

Codebase-side grep: no existing `SetStyleAlignWithSurface` callsites in `src/`. Expected — we haven't shipped the feature. RhinoCommon API surface verification deferred to PR implementation time via empirical introspection (match the pattern PR #73 used for `startingSurfaceId` / `ResolveSeedSurfaceStrict`).

No live Rhino probe needed for a feasibility question that has a direct precedent in the codebase.

---

---

## Post-Hoc Finding — PR-2 Killed by Implementation-Time API Audit (2026-04-21)

Running the scope pass for PR-2 on 2026-04-21 — hours after PR-1 merged — began with an empirical audit of the RhinoCommon `SweepOneRail` API surface (the probe this memo explicitly deferred to implementation time). The audit killed PR-2.

**What the audit found:**

| Surface probed | Result |
|---|---|
| `SweepOneRail` instance methods (reflection over all public members, Rhino 8) | `SetToRoadlikeFront()`, `SetToRoadlikeRight()`, `SetToRoadlikeTop()`, `SetRoadlikeUpDirection(Vector3d)`. **No `SetStyleAlignWithSurface` method.** |
| `SweepOneRail` properties | `IsFreeform`, `IsRoadlike`, `IsRoadlikeFront/Top/Right`, `IsRoadlineRight` [sic]. **Binary mode flag — no Align state.** |
| `Brep.CreateFromSweep*` static overloads (11 total) | None take a `Surface` or `BrepFace` argument. Most advanced overload takes `SweepFrame frameType` (enum) + `Vector3d roadlikeNormal` — same Freeform/Roadlike binary. |
| `SweepFrame` enum | Only two values: `Freeform`, `Roadlike`. |
| Assembly-wide reflection scan for `AlignWithSurface` / `AlignWith` / `StyleAlign` across all RhinoCommon types | **0 matches.** |

**Interpretation:**

Rhino's `_Sweep1` command UI has an "AlignWithSurface" style option, but the underlying opennurbs implementation is a command-internal codepath — it never got a public managed wrapper. The feature exists in Rhino, not in RhinoCommon.

The spike memo's original premise — *"invoke `SweepOneRail.SetStyleAlignWithSurface(surface)` before `PerformSweep`"* — is unimplementable via the managed-bridge-reuse substrate that defined Phases 1-3. The fix would require either (a) a lower-level opennurbs/C++ implementation bypassing the managed bridge entirely (huge scope bump — abandons the substrate rhythm), or (b) a `RhinoApp.RunScript`-driven scripted fallback (violates Decision Record Rule 3).

**Decision:** PR-2 killed. Feature re-parked with strict trigger set (any of):
- RhinoCommon adds a managed wrapper for the Align mode.
- A new native/opennurbs design pass is explicitly opened (separate campaign, different risk shape).
- A real user workflow surfaces sufficient need to justify the native route cost.

**Phase 3 = 1 shipped PR.** Same posture as Probe 2 killing `rails_disconnected` — empirical evidence kills feasibility, we document and re-park rather than pivot to hacks.

**Methodology lesson:** the spike memo deferred the `SweepOneRail` API audit to "implementation time" — but a feasibility-gating audit should run at spike time, not at plan-doc time. Mid-campaign API surprises are exactly what the spike rhythm is supposed to prevent. Future spike memos should treat "RhinoCommon-API-signature-checked" as a hard spike gate, not a deferrable check.

---

## Probe Methodology Reference

The three probes defined in §Probe Findings above were run via `.scratch/phase3_probes.py` (ad-hoc script, not committed — consistent with Phase 1/2 spike convention). Probes used existing `/surface/revolve` and `/surface/sweep2` routes to characterize factory behavior without writing any new routes; decision gates evaluated against the resulting envelopes.

Probe 1 outcome drove PR-1's scope (tolerance `ModelAbsoluteTolerance * 10` starting point; empirically tuned via characterization tests when PR-1 is written). Probe 2 outcome killed the `rails_disconnected` row. Probe 3 was intentionally a codebase-only check — the live-Rhino API surface for `SetStyleAlignWithSurface` is resolvable at PR implementation time via RhinoCommon introspection, same rhythm PR #73 used for `startingSurfaceId`.

---

## Theme A Gate — Lightweight Verification After Phase 3 B Ships

**Do not commit to Theme A until one cheap verification has run.** The single question: *is the missing per-primitive MCP surface causing actual planning/discoverability pain, or are agents already reaching primitives fine via `rhino_create`?*

**Verification plan** (run after Phase 3 PR-1 lands, before re-triaging Theme A):
1. Grep `knowledge/` for recent observations on primitive-creation intents — are there correction/struggle signals that point at discoverability?
2. Look at the `phase_tracker` metrics in `mcp_server/src/rook/learning/metrics_store.py` for primitive-creation tool call rates and success rates.
3. Check `rhino_execute_intent` DSPy-routing logs for primitive-intent fallback frequency — is the catch-all path actually hitting the DSPy branch, or is the direct-route table already resolving these?

**Decision criteria after verification:**
- **High-signal discoverability pain** (many correction events, DSPy fallback on primitives, or explicit user request) → commit Theme A as a 4-6 PR campaign.
- **Low/no signal** → park Theme A long-term with a firm trigger ("user explicitly asks for per-primitive MCP tools" or "a new primitive type gets added and the catch-all `/create` can't represent it cleanly"). Not a follow-up; an explicit non-project.

This gate is lightweight (~1 hour of log-grepping + one triage decision) — it preserves optionality without letting Theme A drift through as an implicit commitment.

---

## Theme C — Explicit Park

**Theme C (batch primitive creation) is not a Phase 3 candidate.** It's a product-level question, not a typed-route question:

- Are batch variants (`create_points_batch`, `create_circles_batch`) actually used enough to justify the API surface expansion?
- If yes, what's the right batch shape — parallel arrays of params, or uniform-type arrays?
- How does batching interact with attribute bundles (one layer per object, or one layer shared across a batch)?

None of these have signal today. Park with trigger: "a real workflow surfaces need for batch primitive creation specifically." If Theme A commits and ships, revisit whether batch variants should be added to the per-type surfaces at that time.

---

## PR Sequence (final, post-PR-2 kill)

- **PR-0** — spike memo landed (this doc). No code.
- **PR-1** — `curve_intersects_axis` on `/surface/revolve`. **SHIPPED 2026-04-21 as `0a72a0f` / PR #82.** Managed-only. Detection added in `CreateRevolveStrict` at `CreateHandler.cs:1900+`. Removed the `DEFERRED PLAN-CODE` comment; updated native pointer comment at `SurfaceHandler.cpp` in lockstep. 6/6 characterization probe + 19/19 live `test_revolve_live.py` + 45/45 intent_runtime regression. Single-round Codex review, no findings.
- **~~PR-2~~** — `AlignWithSurface` on `/surface/sweep1`. **KILLED pre-code, 2026-04-21.** RhinoCommon managed API does not expose the Align mode (`SweepOneRail` only supports Freeform + Roadlike; assembly-wide audit returned 0 hits for `AlignWithSurface` / `AlignWith` / `StyleAlign`). See §Post-Hoc Finding above for the full audit. Re-parked with strict trigger.

**Dropped from Phase 3:**
- **`rails_disconnected` on `/surface/sweep2`** — permanent deferral per Probe 2 (never got a PR number). Trigger to revisit: user workflow produces geometry wrong enough to warrant blocking despite factory tolerance.
- **`style="AlignWithSurface"` on `/surface/sweep1`** — killed by implementation-time RhinoCommon API audit. Trigger to revisit: RhinoCommon adds managed wrapper, OR new native/opennurbs design pass opened, OR real user workflow justifies native route cost.

**Final count:** 1 PR shipped. Meaningfully smaller than Phase 1 (7 PRs) or Phase 2 (11 PRs). Campaign closed.

---

## Campaign Exit Criterion

Phase 3 completes when:
1. ✅ `curve_intersects_axis` detection shipped (PR #82, 2026-04-21) — native pointer comment updated in lockstep.
2. ✅ `rails_disconnected` documented as permanent deferral with user-workflow trigger (see §Probe Findings, §PR Sequence).
3. ✅ `AlignWithSurface` documented as killed-by-API-audit with strict trigger set (see §Post-Hoc Finding, §PR Sequence).
4. 🟡 Phase 1 plan-doc's `Non-goals` section update — deferred; if the `DEFERRED PLAN-CODE` comments on the two re-parked rows need cross-referencing to the new trigger docs, that's a cheap follow-up commit.
5. 🟡 Theme A verification step — separate item on the work-queue, can fire any time post-Phase-3-close.

Phase 3 is effectively **closed 2026-04-21** with 1 shipped PR, 2 re-parked deferrals (1 from probe-matrix drop, 1 from implementation-time API-audit kill), and campaign-level empirical methodology validated.

After that, re-triage for the next architecture move. Theme C stays parked regardless.
