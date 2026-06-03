# Rook North-Star Topology — Multi-File Work Allocation & Recomposition

- **Date:** 2026-06-03
- **Status:** Foundational architecture. Converged through a Rook ⇄ Codex ⇄ user deliberation. Guides the unified P1–P7 push (P6–P7 are the fan-in segment). **P1 implementation is unchanged by this document** — it only fixes the language and extensibility contract P1 must not violate.
- **Author:** Claude (synthesis of the Rook ⇄ Codex deliberation; refinements folded in)
- **Area:** `mcp_server/src/rook/{bridge,targeting,server}.py`, the agent/coordinator runtime (`mcp_server/src/rook/agent/`, incl. `conductor.py`), router/connector surface; reference clone: `C:\Users\aryan\source\repos\RhinoMCP`
- **Relationship to other docs:**
  - Extends `docs/superpowers/specs/2026-06-02-rook-rhinomcp-architecture-assessment.md` (the fourth plane, the two operating modes, the amended invariant). The assessment answered *how should Rook respond to McNeel's RhinoMCP*; **this document answers what the external/local-orchestration plane is actually for.**
  - Sets the contract that `docs/superpowers/plans/2026-06-02-router-p1-read-only-sessions.md` (the P1 implementation plan) must remain compatible with. P1 stays read-only, session-only, single-runtime.

---

## 1. Why this document exists

The assessment doc answered a defensive question. This one answers the generative question it exposed: **what is the orchestration plane for?**

The answer reframes the entire plane. It is **not** "multi-instance targeting" — the job is not "send this tool call to Rhino #2." It is **multi-file work allocation plus recomposition**:

> A cloud-grade coordinator decomposes a large design workflow across many Rhino files. Each file is worked by its own swarm of cheaper/local agents — in the optimum case running locally at ~$0. Their outputs are then recombined into a master deliverable through Rhino's native composition mechanisms: worksessions, imports, linked models, references, blocks/assets, reports.

P1 (read-only named sessions + liveness) is the first brick. This document is the building it belongs to. **Every choice in the P1–P7 push should be checked against the topology and the contracts defined here** — not so P1 over-builds, but so P1 never becomes a dead-end the fan-in future has to demolish.

---

## 2. The North-Star

### 2.1 Two tiers, one cost/intelligence gradient

The architecture is a **two-tier coordinator** with an explicit economic gradient:

- **Top tier — one expensive brain (cloud).** A single intelligent UI/model — Claude Desktop, Codex, or equivalent — owns the *macro* workflow: decomposition across files, disciplines, options and deliverables; cross-file planning; conflict resolution; recomposition strategy; "what does *done* look like." Low-frequency, high-stakes, judgment-heavy work that needs world-knowledge.
- **Bottom tier — many cheap brains (local, ideally $0).** Each Rhino file is worked by its own orchestrated swarm of cheaper/local-model agents doing the *micro* work: in-file modeling, mostly-deterministic tool sequences, retry loops. High-frequency, low-stakes-per-step, needs Rhino-domain competence but not world-knowledge.

Scarce intelligence sits at the top and is shared; abundant intelligence sits at the bottom and is replicated per file. Work is broken into smaller pieces, each piece costs little to attempt, and the pieces are reconciled at the top.

### 2.2 Topology

```
Cloud-grade coordinator (one, expensive)        ← Claude Desktop / Codex = macro coordinator
  plans workflow across files, disciplines, options, deliverables
        │  router-plane surface: enumerate · dispatch · lifecycle · RECOMBINE
        │  (stdio / MCPB — transport stays LOCAL; "cloud" = model weights only)
        ▼
Rook orchestration plane  (the local runtime on the workstation)
  session registry · liveness · ownership · work allocation · merge strategy
        ├──▶ Rhino file / session A — local orchestrator + cheap/local agents ┐
        ├──▶ Rhino file / session B — local orchestrator + cheap/local agents │ in-file:
        ├──▶ Rhino file / session C — local orchestrator + cheap/local agents │ one process,
        └──▶ …                       (each: RookNative + document context)   ┘ many async
                                                                                workers,
        │  fan-in: worksession · import · linked model · reference refresh      contextvars,
        ▼                            (a dependency DAG with ordering)           intent + KG
   master / anchor document  (Attached)        ← recomposed deliverable
```

### 2.3 The reframe (load-bearing)

Three consequences of reading the plane this way:

1. **The unit of decomposition is a Rhino *file*, not a Rhino *window*.** Work is split into files and recombined through file-composition primitives. This is why session identity alone is not enough (see §5).
2. **The router plane is a *work-allocation layer*, not a port router.** Its job is "this subtask belongs to file/session B, with these local agents, these constraints, and this merge contract" — not "forward bytes to a second Rhino."
3. **Fan-in is the payoff, and it is the under-built half.** The roadmap is strong on fan-*out* (address, route, lifecycle). The deliverable is the recomposition. Fan-in gets its own track (§8, §9).

---

## 3. Macro and micro: two surfaces, not two products

The router plane and Rook's existing intent/knowledge runtime are **the macro and micro halves of the same two-tier coordinator** — not competing investments.

| | Macro surface | Micro surface |
|---|---|---|
| **Consumer** | the cloud brain | each file's local swarm |
| **Vocabulary** | sessions, work units, liveness, lifecycle, merge contracts | `rhino_execute_intent`, typed routes, KG queries |
| **Implemented by** | the router/orchestration plane (P1–P7) | the intent runtime + knowledge graph (already built) |
| **Shape** | *enumerate → decompose → dispatch → monitor → recombine* | *model competently while cheap* |

**The knowledge graph is the intelligence subsidy that makes the cheap tier viable.** A weak local model does not need world-knowledge if `rhino_execute_intent` + KG routing + typed routes + structured diagnostics carry the competence. This is the precise reason Rook's stated center of gravity (local-first + persistent KG + coordinated agents) is **not adjacent** to the router plane — it is *what lets the bottom tier be dumb-and-free without the work being bad.*

A corollary: the "fewer, intent-shaped tools, not 300 raw" principle from the assessment applies **doubly** to the local swarm. A cheap local model drowns in 300 tools faster than any cloud model. The cloud brain sees the *session/work* surface; the local swarm sees the *intent* surface; the 300 typed routes remain implementation substrate beneath both.

---

## 4. The two operating modes map onto the two tiers

The assessment defined two modes as the substrate realization of earned autonomy. They map cleanly onto the tiers — with one refinement that matters for fan-in:

- **Attached (adopted, never killed) = the human's master / anchor document.** Low autonomy (Assist). The coordinator may read and propose, never kill or replace. This is the recomposition target.
- **Workbench (owned, disposable, may reap + respawn) = the per-piece execution environment.** High autonomy (Explore/Build). This is where the free-local-compute swarm lives.

**The refinement — separate compute lifecycle from artifact lifecycle.** The Workbench *compute* is disposable; the `.3dm` *piece it produces* is durable and becomes a linked/referenced artifact in the composition. Free local inference inverts the economics: you can afford many disposable attempts and variations per piece, keep the winner, discard the rest. The session is throwaway; the artifact is currency handed from the disposable swarm to the durable composition. **Never conflate "kill the session" with "discard the output."**

---

## 5. The entity model (the load-bearing detail)

This is the part most easily gotten wrong, and the part that — if conflated now — we will regret during fan-in. The temptation is to make `session` mean "the file." It must not. **In fan-in, most artifacts are not live sessions:** a linked `.3dm` referenced by the master, sitting on disk, is a durable artifact with *no* live session at all. If `session` is overloaded to mean the file, there is no vocabulary for the majority of the fan-in graph.

### 5.1 Three identities and one relation

Model **three distinct identities (graph nodes)** and **one relation type (graph edge)**:

| Concept | Kind | Definition | Example |
|---|---|---|---|
| **Session / Slot** | node (identity) | A live execution context: a Rhino process / window / listener. | `rhino-7101`, `workbench-a` |
| **Document / Artifact** | node (identity) | A document worked in a session (ephemeral) or a durable `.3dm` produced/consumed (durable). | in-session: serial `48201`; durable: `C:/proj/site-core.3dm` |
| **Work Unit** | node (identity) | A coordinator-level assignment: role, constraints, expected output. | `facade-study`, `context-cleanup`, `option-B-structure` |
| **Merge Contract** | **edge** (relation/strategy) | *How* a produced artifact recombines into a consumer. Lives on the dependency-DAG edge, not in a flat registry. | `facade-option-02 →[linked-block, refresh-after-save]→ site-master` |

The north-star sentence:

> The cloud coordinator **assigns Work Units → to Sessions/Slots → operating on Documents/Artifacts → producing outputs → reconciled by Merge Contracts** along a dependency DAG into the master/anchor document.

**Why Merge Contract is an edge, not a fourth peer entity:** a merge contract only has meaning *between* a produced artifact and a consuming master, with an ordering ("refresh M after A is saved"). Modeled as a flat registry it loses the ordering structure — and that ordering *is* the fan-in problem. It is an attribute of a dependency edge, not a standalone addressable thing.

### 5.2 Grounding — what already exists in code

Two of the three identities are not hypothetical; their seeds are in the current code:

- **Session** — `targeting.InstanceRef(port, process_id)` is the internal address; P1's `session_id_for_instance` (`rhino-<pid>`) is the external **live-session** handle (stable for the Rhino process lifetime; durable registry aliases arrive at P5 — see §7). *Exists.*
- **Document** — already latent and merely **subordinated to session binding**. `targeting.fetch_document_metadata` (`targeting.py:1180`) pulls `documentName`, `documentPath`, `objectCount`, `windowTitle`; `_matches_text` (`:1013`) already lets a caller bind a session by document name/path; `document_serial_number` is threaded through `rhino_request_context` and the panel lock. Promoting Document to first-class is **surfacing existing metadata, not inventing a new subsystem.**
- **Work Unit** and **Merge Contract** — **net-new.** No seed in the runtime today. They are coordinator concepts.

### 5.3 Altitude — these do not all live in the same place

| Entity | Plane | Home |
|---|---|---|
| Session, Document | **Orchestration plane** (the Rook runtime) | `bridge.py` / `targeting.py` — Rook already holds this data |
| Work Unit, Merge Contract | **Coordinator plane** (above the runtime) | the coordinator (`agent/conductor.py` territory) and the fan-in track |

Co-locating all four in one registry is a subtler version of the same overloading we are guarding against. Session/Document describe *what is live and addressable*; Work Unit/Merge Contract describe *what the coordinator intends*. Keep them in separate registries (`SessionRegistry`, `DocumentRegistry`, `WorkUnitRegistry`, and the `DependencyDAG` whose edges carry merge contracts).

### 5.4 Direction of reference — the disposability invariant

**Coordinator registries point *down* at sessions. Sessions never point *up* at work units.**

The coordinator maps `WorkUnit → Session`; a session does **not** carry a `workUnitId` or `mergeContract` back-reference. This is not pedantry — it is what makes Workbench sessions **disposable**: you can reap and respawn a session without orphaning campaign state, *because that state lives in the coordinator's `WorkUnitRegistry`, not in the session row.* A work cell must know nothing about the campaign it serves. (This supersedes the earlier suggestion to reserve `workUnitId`/`mergeContract` fields on the session payload — those fields belong to the coordinator's registries, not to the session.)

### 5.5 The Save membrane — the fragile seam

Document identity is **two-phase**:

```
in-session  (serial number; possibly unsaved, no path)
     │
     └── Save ──▶ durable  (path on disk; possibly no live session)
```

**The Save operation is the membrane between the Session world and the Artifact world — it is literally the fan-out → fan-in boundary,** the instant a work cell's output becomes recomposable. And it sits exactly on Rook's known-fragile cross-process `.3dm` save/refresh substrate (the .NET-subprocess handle-inheritance save failure documented in project memory). So the single most failure-prone seam in the entire north-star is architecturally pinpointed here: **the Session→Document handoff at Save/refresh.** The fan-in track's rigor concentrates on this membrane (save atomicity, file locking, reference-refresh ordering), not on the easier addressing problem.

---

## 6. The resolution model — how a target is addressed

When `session` becomes a first-class selector (P3), it resolves to the existing internal address through one disciplined path.

### 6.1 The resolver is `(session, endpoint) → InstanceRef`, not `session → InstanceRef`

A session is a Rhino **window** = one pid — but that pid can expose multiple route-capable **discovery records** — e.g. the **native** listener and a separate **RoadCreator** adapter record — addressed on **different ports** (GH is *not* a separate listener; it is native-callback-backed through the companion via P/Invoke). `bridge.select_rhino_instance` is already endpoint-aware: a GH call to session `rhino-7101` routes to the native port; an `/rc/` call to the *same* session routes to the RoadCreator port (`bridge.py:391-419`, pid-scoped at `379-381`). So the **load-bearing identity is the pid; the port is endpoint-resolved.** The long-term resolver shape:

```
(session_id, document_serial_number?, document_path?, endpoint)
        │
        ▼  one internal resolver (the single funnel — §6.2)
InstanceRef(port, process_id)
        │
        ▼
existing targeting + bridge routing (rhino_request_context → select_rhino_instance → HTTP)
```

`document_serial_number` / `document_path` here are **in-session disambiguators** (which document within a session or worksession), not independent routables — a durable artifact with no live session is addressed through `DocumentRegistry`, never the targeting resolver. **Work Unit is deliberately absent from this tuple:** the coordinator resolves `WorkUnit → (session, document)` *upstream* and hands targeting a session/document selector only, so the targeting resolver never learns that work units exist (preserving the §5.3 altitude split and the §5.4 direction-of-reference invariant).

### 6.2 One resolver funnel (anti-rot invariant)

Every selection path — explicit session, default/active session, and the legacy explicit port — must resolve through **one** internal `resolve_target(selector, endpoint) → InstanceRef`. One place where session→pid→InstanceRef happens; one place where liveness/staleness is judged. Without a single funnel, "canonicalize on sessions, coexist operationally during migration" silently calcifies into two parallel resolvers with divergent staleness and lock semantics — the exact outcome to avoid.

### 6.3 Panel lock is a constraint, not a precedence rung

The Attached panel lock **filters the candidate set** and is evaluated before the precedence ladder. It is not one option among others. A request for a session outside the locked process/document **fails closed** — exactly as an explicit port outside the locked process already does today (`targeting.py:903-913`). When `session` becomes a selector, it inherits this rule unchanged: *a panel-locked MCP process cannot be redirected to another session by a coordinator plan.*

### 6.4 `_ACTIVE_TARGET` downgraded to "default selected session"

`_ACTIVE_TARGET` is a **UI/default convenience for a single MCP client**, not the architectural routing model. A cloud coordinator cannot reason in terms of "whatever this MCP process happens to have active" — it addresses explicit session handles. Note that `resolve_tool_route` reads `_ACTIVE_TARGET`/`_PANEL_TARGET_LOCK` as **process-global state at policy time** (`targeting.py:893,949`), *before* any per-task `contextvars` binding. Therefore the active-session default is safe only for single-active-client use; the coordinator fan-out path passes an explicit session on every call. The natural terminus — when the multi-worker coordinator wants per-worker defaults without threading session through every call — is to promote the active session from a module global to a **per-task contextvar**. (Beyond P3; named here so the line is visible.)

### 6.5 The precedence ladder (destination)

```
panel lock / Attached lock     — a CONSTRAINT; filters candidates; fails closed; overrides all below
explicit session / slot        — the canonical selector
explicit port                  — lower-layer addressing + diagnostic escape hatch (NOT "legacy/deprecated")
default selected session       — single-client convenience (the downgraded _ACTIVE_TARGET)
auto                           — only if unambiguous; existing read/mutate safety (read warns, mutate refuses)
```

Explicit port is retained deliberately: it is the substrate coordinate a session *resolves to*, and the last-resort manual override when naming breaks (malformed discovery, pid collision). It is demoted in preference, not deprecated.

---

## 7. The process model and where SQLite lands

The earlier "do we need a cross-process registry / SQLite" question resolves cleanly once the topology is two-tiered. **It is both — at different altitudes:**

- **Inside one file/session:** one local runtime, many async workers, `contextvars` routing. **No SQLite.** Per-task context isolation gives correct concurrent routing for free (asyncio copies context per task). This is the P1–P3 substrate.
- **Across files/sessions:** multiple owned Workbench slots, possibly multiple local orchestrator processes, that can concurrently claim / spawn / close files. **A persistent cross-process registry is required** — as a **cross-file claim & lifecycle ledger**, never as an in-file worker scheduler.

When that ledger is built (P5), adopt RhinoMCP's proven patterns directly (verified in `RhinoMCP/rhino/router/SlotStore.cs`): `BEGIN IMMEDIATE` write transactions + WAL + `busy_timeout`; **"the row is the lock"** (a `launching` placeholder a peer observes and waits on); **persist intent, never asserted health** (liveness is always probed, dead rows are `DELETE`d, never marked dead); **ephemeral** (drop & rebuild on version change); and the **`adopted` flag** as the Workbench-vs-Attached enforcement primitive (an adopted **live** session is never killed/closed by the router; a dead adopted session's registry row is still reaped like any other once its PID is gone — **adoption guards active close, not dead-row cleanup**). The "persist intent, probe truth" philosophy is already Rook's own diagnostic-truth discipline, one layer up.

**The shaping requirement for P1:** even though P1 uses a read-through projection over `discover_instances()` (no registry), its coordinator-facing **vocabulary** must be shaped so SQLite can replace the projection later *without changing the coordinator's language*. P1 exposes sessions as stable **live-session** handles (`rhino-<pid>` — stable only for the lifetime of that Rhino process; a respawn yields a new pid and thus a new handle, so these are **not** durable workflow handles). P5 makes the handle vocabulary registry-backed and can introduce **durable aliases** that survive respawn (e.g. `workbench-a`). The handle vocabulary is the invariant; the storage is swappable.

### 7.1 The bounding simplification (do not over-scope)

"Cloud" here means *where the top model's weights live*, **not** where orchestration runs. Claude Desktop / Codex run **on the workstation**; the MCP transport stays **local** (stdio / MCPB / loopback); all Rhino files + the local swarm share one machine's `%LOCALAPPDATA%\Rook\discovery\` folder. **The folder-based, single-machine substrate is therefore sufficient for the entire north-star.** Truly distributed Rhinos across machines is a separate, XL, PX-class future (the same class as Mac cross-platform) — explicitly **not** a blocker for P1–P7. The hard new problem is recomposition, not transport.

---

## 8. Fan-out and fan-in

| | Fan-out | Fan-in |
|---|---|---|
| Question | "Which session does this work go to?" | "How do these outputs become one deliverable?" |
| Substrate | addressing, routing, lifecycle (P1–P5) | dependency DAG + reference-refresh ordering (P6–P7) |
| Concurrency | parallel across independent sessions | **serialized on dependencies** |
| Maturity in roadmap | strong | **under-named — this document's main addition** |

Fan-in is a **build-system-over-Rhino-files** problem. If file A is a linked reference in master M, then A's swarm must finish and save before M refreshes its reference; two files with no dependency may proceed in parallel; a file and its dependents serialize at the recompose step. This needs: a cross-file dependency model; reference/worksession refresh orchestration; **file-granular (not just window-granular) addressing** (seeded by `document_serial_number` / `documentPath`); and disciplined handling of the Save membrane (§5.5). The choice of merge mechanism (worksession vs linked-block vs import-merge vs reference) is itself a design axis with different locking/consistency properties — it determines the fan-in concurrency model and must be pinned per dependency edge, not assumed globally.

---

## 9. Roadmap

The external/local-orchestration plane, extended with the fan-in track. Discipline unchanged: **name & observe → report truth → route safely → own lifecycle → recompose.**

```
P0  (done)  Phase 2C standalone smoke PASSED (PR #207).
P1  Observe + name live sessions          read-only; rhino_sessions / rhino_session_capabilities; liveness envelope
P2  Truthful liveness / failure envelopes  crash / dead-session wrapper for adopted sessions
P3  Explicit session-targeted mutation     session becomes the canonical selector; Attached-mode guards
P4  Owned Workbench session launch         port env + runscript spawn; wait-for-bind; license-dialog detection
P5  Persistent session/document registry   sessions + documents, ownership/claims (SQLite, adopt SlotStore patterns)
P6  Document / artifact graph + merge       artifact identity, dependency DAG, merge contracts
P7  Per-file local orchestrators + fan-in   coordinator work allocation + recomposition into the master/anchor

—— parallel, independent ——
PC  MCPB connector packaging (pull forward; small). In the north-star this is the cloud brain's ENTRY POINT, so it
    is more load-bearing than "peripheral adapter" — but still packages the adapter, not the product.
PX  (XL) Cross-platform / Mac AND multi-machine distribution. Separate go/no-go. Never bundled with P1–P7.
```

### 9.1 The two-speed spec discipline (decided)

Pull schema design forward **selectively**, not wholesale:

- **Freeze now (P3 depends on it):** the **Session + Document identity contract** — the external handle vocabulary, the `(session, endpoint)` resolver shape, the reserved document fields (`document`, `documentSerialNumber`, `documentPath`). P3 makes `session` canonical; redesigning the handle vocabulary mid-flight is the expensive failure.
- **Defer to fan-in kickoff (~P6), designed against *observed* fan-out:** the **Work Unit + Merge Contract schema**. Speccing the coordinator's work-allocation and merge ontology before session-targeted mutation has even shipped is premature theorizing — it must meet real fan-out behavior first (the project's observe-before-theorizing rule).

Freeze what the next phase structurally depends on; let the rest hit reality before it is frozen.

---

## 10. What P1 grounds — and what it deliberately does not

**P1 is the coordinator's perception layer: naming, and truth. Its eyes, not its hands.** You cannot orchestrate a fleet you cannot truthfully see. `rhino_sessions` + `rhino_session_capabilities` is literally "enumerate the pieces and read what each can do" — the first move of macro-decomposition — and the live/unreachable/dead envelope is the fleet's truth surface, without which a coordinator over a flaky, multi-process, local-model fleet cannot recover.

The one seam that is real forward-prep: the centralized `session_id_for_instance` helper. It is the single point where pid-derived identity later becomes a slot/stable **session** identity without touching callers — file identity is a separate concern that flows through `DocumentRegistry`, never this session helper. P1 already does the right thing by funneling identity through one function — keep it that way.

**P1 explicitly does not, and should not, ground:** mutation routing (P3), spawn/kill (P4/P5), the persistent registry (P5), the document/artifact graph or merge contracts (P6/P7), cross-process coordination, or multi-machine transport (PX). P1 stays **read-only, session-only, single-runtime**. It *may* expose cheap document metadata on a session payload (name/path/serial — data Rook already has via `fetch_document_metadata`) to seed §5.2, but it carries **no** `workUnitId`/`mergeContract` (§5.4) and changes **no** routing or reaping behavior.

---

## 11. Invariants

Carried from the assessment, plus the new ones this document fixes:

1. **(Amended, from the assessment)** RookNative remains the sole **in-Rhino** Rook HTTP / capability / control / discovery surface. A Rook router/connector may become the **public LLM/MCP** surface.
2. **Session ≠ Document ≠ Work Unit.** Three distinct identities; Merge Contract is a dependency-edge attribute, not a fourth entity. Never conflate the live execution context with the durable artifact it produces (§5).
3. **Disposability / reference direction.** Coordinator registries point down at sessions; a session never back-references a work unit. Reaping a session must never orphan campaign state (§5.4).
4. **Single resolver funnel.** All selection paths resolve through one `resolve_target(selector, endpoint) → InstanceRef`; never two parallel resolvers (§6.2).
5. **Panel lock is a fail-closed constraint,** not a precedence rung; it overrides all explicit session selection (§6.3).
6. **Session is the canonical external handle; `InstanceRef(port,pid)` is the internal address; `_ACTIVE_TARGET` is a single-client default,** not the routing model (§6).
7. **Two-speed spec.** Freeze the Session+Document contract before P3; design Work Unit + Merge Contract against observed reality at ~P6 (§9.1).
8. **Single-workstation bound.** Local transport, shared discovery folder; multi-machine distribution is PX-class and never bundled (§7.1).

---

## 12. The load-bearing empirical bet

The whole economic case rests on a single premise: **cheap/local model + knowledge-graph subsidy ≈ competent-enough in-file.** That is an *empirical* bet, not an architectural guarantee. If it holds, the gradient works and multi-file decomposition has a reason to exist. If it fails, the gradient collapses back to "expensive everywhere" and the decomposition loses its point.

Therefore: **de-risk the KG-subsidy-closes-the-competence-gap hypothesis early** (the local-model exploration / Gemma probe is the right instrument), in parallel with — not after — the P1–P5 substrate work. The substrate is sound regardless; the *premise* is the thing to validate against reality before betting the roadmap's later phases on it. (Consistent with the project's observe-before-theorizing discipline.)

---

## 13. Decision log

- **The plane is a work-allocation + recomposition layer, not a port router** (§2.3). The unit of decomposition is a file.
- **Two-tier coordinator** (cloud macro / local micro); router plane = macro surface, intent+KG = micro surface; **KG is the competence subsidy for the cheap tier** (§3).
- **Modes map to tiers:** Attached = master/anchor; Workbench = disposable compute. **Compute lifecycle ≠ artifact lifecycle** (§4).
- **Three identities + one edge:** Session, Document, Work Unit (nodes); Merge Contract (DAG edge). Session and Document have code seeds today; Work Unit and Merge Contract are net-new coordinator concepts at a higher altitude (§5).
- **Save is the fan-out→fan-in membrane** and the most fragile seam (cross-process `.3dm` substrate) (§5.5).
- **Resolver is `(session, endpoint) → InstanceRef`** through a single funnel; **panel lock is a fail-closed constraint**; **`_ACTIVE_TARGET` downgraded** to a single-client default (§6).
- **SQLite lands at the cross-file boundary (P5)**, adopting SlotStore's patterns (adoption guards active close, not dead-row reaping); in-file fan-out needs none. **Single-workstation substrate is sufficient** for the whole north-star (§7).
- **Fan-in is a first-class track** (P6–P7): dependency DAG, reference-refresh ordering, file-granular addressing (§8).
- **Two-speed spec:** freeze Session+Document before P3; defer Work Unit + Merge to ~P6 against observed reality (§9.1).
- **P1 is unchanged** — perception/naming/truth only; read-only, session-only, single-runtime (§10).
- **The roadmap's premise (cheap+KG ≈ competent) is an empirical bet to de-risk early** (§12).
