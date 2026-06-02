# Rook ⇄ RhinoMCP — Architecture Assessment & External/Local-Orchestration Plane

- **Date:** 2026-06-02
- **Status:** Architecture stance approved (reviewer sign-off after wording/safety edits). Prototype 1 approved as the next step — implementation plan pending. Phase 2C standalone smoke: **passed** (PR #207).
- **Author:** Claude (synthesis of a Rook ⇄ Codex deliberation; senior-reviewer corrections folded in)
- **Area:** `mcp_server/src/rook/bridge.py`, `mcp_server/src/rook/server.py`, agent runtime (`mcp_server/src/rook/agent/`), install/connector; reference: `C:\Users\aryan\source\repos\RhinoMCP` (cloned `main`)
- **Prompted by:** McNeel's public release of RhinoMCP (mcneel/RhinoMCP) — a first-party Rhino MCP server with a stdio **router**, multi-instance slots, auto-launch, and crash recovery.

---

## 1. TL;DR

RhinoMCP is **not** a threat to Rook's center of gravity, but it exposes a **missing architectural layer** in Rook's roadmap. McNeel's plugin shares the **same broad substrate** as Rook's: an in-Rhino localhost HTTP listener plus a discovery/announcement record. (The *implementation shape* differs materially — RhinoMCP is C#/.NET per-document HTTP MCP tooling; RookNative is a C++ `cpp-httplib` REST/capability/control server fronting an internal managed companion. "Same substrate" must not be read as "easy port.") Their advantage is entirely in a **separate stdio MCP router process** that owns instance **launch, slot targeting, crash recovery, and client ergonomics** — capabilities Rook's Python MCP runtime does not yet have.

The correct response is **not a panic-pivot to "another Rhino MCP server."** McNeel will own the generic-Rhino-control lane as the platform vendor. Rook's durable bet is **local-first intelligence + persistent knowledge graph + coordinated multi-agent behavior**, with Rhino as *one* attached capability provider. The local-first lens *sharpens* this: it makes the slot/session layer **critical-path substrate for the coordinator**, not a peripheral access concern.

This document defines a **fourth plane** (external/local-orchestration), **amends one invariant**, maps the **two operating modes** (Workbench vs Attached) onto Rook's existing earned-autonomy model, and **recommends a lowest-risk Prototype 1** (read-only named sessions + liveness envelope) — no spawning, no killing, no mutation routing.

---

## 2. What RhinoMCP actually is (ground truth from source)

Read locally from the clone, not from docs. The system is three pieces, all C#/.NET (cross-platform):

### 2.1 In-Rhino plugin — *same broad substrate, different implementation shape*
`rhino/plugin/` runs an **HTTP MCP server** per document, on a private port (base `10500`, walks forward), with `Stateless = true` so each `tools/call` is a self-contained JSON-RPC POST (no initialize handshake). On start it drops a **one-shot announcement** JSON `{v, pid, port, version}` into `%LOCALAPPDATA%/McNeel/rhino-mcp/listeners/` (`RhMcpHost.WriteAnnouncement`).

> This is the **same broad substrate** as RookNative's HTTP server + discovery record. RookNative writes its record to `%LOCALAPPDATA%\Rook\discovery\instance-<pid>-native.json` (primary; `%TEMP%/rook` retained only as legacy fallback — `RookServer.cpp:160,165`), carrying `processId`, `pluginVersion`, `rhinoInside`, port, and a capability snapshot (`RookServer.cpp:2195-2214`). **The router→Rhino hop is still localhost HTTP** — McNeel did *not* invent a new transport. The substrate matches; the implementations (C# vs C++) do not.

Tools are plain C# classes with `[McpServerTool]`/`[McpServerToolType]`; `ToolRegistry.Scan()` reflects the assembly and `SchemaBuilder` auto-generates each tool's JSON schema. ~40 generic tools (`RunPython`, `RunCSharp`, `RunCommand`, list/select/camera/layer/viewport/doc) plus **parallel GH1 + GH2** toolsets. Also exposes MCP **Resources** (`CommandHelp`, `HostEnvironment`, `InstalledPlugins`).

### 2.2 The Router — *the part Rook is missing*
`rhino/router/` is a small stdio MCP server (NativeAOT on Mac, `.exe` on Win) with **zero Rhino dependencies**. It is the client-facing surface and adds, on top of the HTTP proxy:

- **Slots** — N Rhino instances, each its own process+port, tracked in **SQLite** (`SlotStore`). State is *intent only*; liveness is probed, never stored. `BEGIN IMMEDIATE` transactions + WAL make it safe across **concurrent router processes** (one per agent session).
- **Auto-launch** — `RhinoManager.LaunchAsLeaderAsync` spawns Rhino with `/runscript=_MCPSpawn` and a `RHINO_MCP_AUTOSTART_PORT` env var, then waits for the port to bind (distinguishing *process died* from *timeout* — license/EULA dialog).
- **Adopt + reap** — `ScanAnnouncements()` adopts user-started Rhinos from the drop directory; `TryReapDead` / `ReapAllDead` prune instances whose **pid is dead OR port stopped listening**.
- **Crash recovery** — `ProxyDispatcher` catches connection-level failures, confirms death via pid+port probe, and returns a **structured** `rhino_crashed` error carrying the crash-report path and a concrete next-action ("retry to auto-spawn" vs "call spawn_slot").
- **Auto-spawn-on-slotless-call** — a tool call with no `slot` arg resolves to an adopted/owned/fresh Rhino and tells the agent via `autoSpawnedSlot`.
- **Mac shared-process model** — leader/follower slots share one Rhino pid; followers ask the leader's listener to spawn a sibling doc+port.

### 2.3 Connector / install
`connector/manifest.json` is an **MCPB v0.3** package (`router-launcher.mjs` entry) with user-config (`rhino_version`, `startup_timeout`), a getting-started prompt, support/privacy metadata, and `platforms: [darwin, win32]`. One-click install in Claude Desktop; the plugin itself comes from Rhino's PackageManager. There is also a `cc-plugin/` Claude Code plugin with role agents (`rhino-modeller`, `grasshopper-scripter`, …).

---

## 3. The key finding: Rook already owns most of the substrate

**Rook's Python MCP runtime (`server.py`) plus `bridge.py` already form most of the router substrate.** `server.py` is the stdio MCP surface; `bridge.py` is the HTTP discovery/proxy/session-selection layer beneath it. Together they are structurally the router — `bridge.py` *already discovers and returns all live instances* (`discover_instances()`, `bridge.py:513`) and proxies tool calls over HTTP. What's missing is the layer above raw discovery: projecting instances as **named sessions**, **liveness**, **explicit targeting**, and **lifecycle** (spawn/recover). It never spawns, names, or recovers.

| Router capability | RhinoMCP | Rook today | Gap |
|---|---|---|---|
| In-Rhino HTTP server | ✅ | ✅ RookNative | none |
| Discovery/announcement file | ✅ `listeners/` | ✅ `%LOCALAPPDATA%\Rook\discovery\` | none |
| stdio MCP front | ✅ router | ✅ `server.py` | none |
| HTTP discovery/proxy | ✅ router | ✅ `bridge.py` (returns all instances) | none |
| **Named-session registry** | ✅ SQLite slots | ❌ raw records, unnamed | **build** |
| **Per-call slot targeting** | ✅ `slot` arg | ❌ | **build** |
| **Liveness probe + structured dead errors** | ✅ | ❌ vague "bridge unavailable" | **build** |
| **Auto-launch Rhino** | ✅ | ❌ | **later** |
| **Spawn/close lifecycle** | ✅ | ❌ | **later** |
| Cross-platform / Mac | ✅ (free from C#) | ❌ C++/Win-only | **separate XL track** |

Consequence: the slot/session manager can be **grown inside Rook's existing Python runtime**, *not* ported from McNeel's C#. That keeps the coordinator's home language and de-risks viability.

---

## 4. How local-first models change the read (the load-bearing reframe)

The user's thesis: *McNeel bets on cloud models driving Rhino; Rook's future is local models with coordinated behavior supported by the knowledge graph.* This does not soften the conclusion — it sharpens four things:

**4.1 The router is internal substrate, not the product face.** For McNeel the router *is* the public surface (Claude Desktop → router). For Rook the primary consumer is the **local coordinator** (Planner/Workers/Conductor); stdio-MCP is *one adapter* on top for external clients. The thing being built is a **slot/session manager that Rook's own agents call**, not "a Rhino MCP server." McNeel is inverted (router on top, no coordinator).

**4.2 Multi-slot is critical-path, not peripheral.** McNeel's slots mostly serve different humans/sessions. Rook's coordinated multi-agent bet *wants to fan work across slots* (parallel exploration, A/B variations, headless batch) — which is exactly the constraint memory calls *the* concurrency bottleneck (single Rhino UI thread). The slot layer is what makes coordinated local agents physically possible. **Elevate it above "access plane."**

**4.3 McNeel's crash recovery == Rook's diagnostic-truth work, one layer up.** Phase 1/2/2C is "don't let the runtime lie to the model." A local 26B coordinator cannot recover from `bridge unavailable`; it *can* recover from `rhino_crashed: pid 8123, report at X, retry to auto-spawn`. This is **Rook's own philosophy**, extended to the access layer — it validates finishing 2C, it does not compete with it.

**4.4 The local-first lesson is *fewer, intent-shaped* tools — not tool-count parity.** A small local model drowns in 300 tools. The coordinator should see an **intent/KG-shaped surface** (`rhino_execute_intent` already collapses many routes into one) while the 300 typed routes remain **implementation substrate** the router dispatches to. Rook already has the better answer; do **not** trade it for McNeel's flat tool list. "Expose more tools than McNeel" is a fragile bet; "know what to do, why, and how to recover" is the durable one.

---

## 5. Answers to the seven assessment questions

**Q1 — What should Rook adopt?**
The **access-layer lessons**: (a) multi-instance slot/session registry; (b) liveness probing + structured dead/stale errors; (c) auto-launch + spawn/close lifecycle (later phase); (d) crash-report surfacing with next-actions; (e) MCPB connector packaging for the external-client use case; (f) richer viewport returns (image **+** camera/scene diagnostics, not just a file path).

**Q2 — What should Rook avoid?**
Becoming "another Rhino MCP server." Avoid: flattening to ~40 generic tools; making `RunPython`/`RunCSharp` the primary path (it discards typed-route validation and KG routing); making the router the product's center of gravity; treating "kill the slot" as the universal recovery answer (unacceptable in Attached mode).

**Q3 — What remains uniquely Rook?**
Local-first intelligence; persistent knowledge graph + learned conventions; coordinated multi-agent behavior; intent runtime; Chirp; BIM/road/block/vision-media modules; live-session care; design memory across projects; productized install/runtime health; "why did this fail and what next" domain diagnostics.

**Q4 — Does Rook need a router/connector layer?**
**Yes — but as a local orchestration shell, not the product core.** It is the substrate that lets the coordinator address N Rhino sessions and recover from failure. The stdio-MCP/connector surface is a secondary adapter for external clients (Claude Code/Desktop), valuable but not central.

**Q5 — How does it affect Phase 2–5 sequencing?**
Finish 2C **iff** its standalone Rhino smoke passes. **Pause** broad route diagnostics after BIM. Insert the assessment (this doc) + the fourth plane. **Pull installer/connector strategy forward.** Resume diagnostics only where they feed the coordinator's decision-making (capability/liveness/failure truth), since a local coordinator needs truthful runtime state more than more raw routes.

**Q6 — Which invariants must be amended?**
One, and it is load-bearing (see §6).

**Q7 — What is the lowest-risk prototype?**
Read-only multi-session adoption + liveness envelope (see §8).

---

## 6. The invariant amendment

**Before:**
> RookNative remains the sole public discovery surface.

**After:**
> RookNative remains the sole **in-Rhino** Rook HTTP / capability / control / discovery surface.
> A **Rook router/connector** may become the **public LLM/MCP** surface.

This single edit preserves all native/managed/plugin stability work (the native plugin stays the only thing inside Rhino that owns routes and discovery) while permitting a better client architecture above it.

---

## 7. The fourth plane and the two operating modes

### 7.1 Planes
The existing three planes stay valid; add a fourth:

```
behavior plane         — what Rook does inside Rhino (routes, capabilities, safe-solve)
state plane            — document/session/scene truth
install plane          — how Rook gets onto the machine
external/local-        — how LLM clients AND Rook's own coordinator discover, launch,
  orchestration plane     target, recover, and talk to Rhino sessions   ← NEW
```

### 7.2 Two modes (substrate realization of earned autonomy)
The router must support two modes; they are **not** competing recovery philosophies — they are Rook's existing *Assist / Explore / Build* autonomy levels with a process boundary enforcing them:

```
Workbench / agent-slot mode      (high autonomy — Explore/Build)
  router MAY spawn, own, close, and recover disposable Rhino instances.
  Recovery = reap + respawn is acceptable. This is where coordinated local
  multi-agent fan-out and headless batch live.

Attached / live-user mode        (low autonomy — Assist)
  Rook is conservative and non-destructive. NEVER kill/replace the user's
  live document. Recovery = structured report + safe deferral (the 2C/safe-solve
  discipline). The user's Rhino is adopted, never owned.
```

The `adopted` flag in the slot model is the enforcement primitive: **adopted sessions are never killed by the router** (mirrors `RhinoManager.CloseAsync` refusing adopted slots). Workbench Rhinos are *owned*; user Rhinos are *adopted*.

---

## 8. Prototype 1 — Read-only session adoption + liveness envelope

**Thesis under test:** *Can Rook discover multiple RookNative sessions, name them, report their capability state, and route coordinator calls to a chosen session — without changing startup, spawning, killing, or live-document behavior?*

### 8.1 In scope
- **Project** the records `discover_instances()` already returns (`bridge.py:513`) as **named sessions** — stable, human/agent-legible ids over `processId`. (Discovery of multiple instances already works; this is naming + a session view over it, not new discovery.)
- A thin **session registry** (in-process dict first; SQLite only if/when concurrent routers are real).
- New read-only tools: `list_sessions`, `get_session_capabilities`.
- **Read-only session targeting only** — an optional `session` arg permitted **only** on an explicitly reviewed read-only allowlist (`/ping`, `/capabilities`, and other vetted read/status calls). Mutating-route targeting is **out of scope until P3.** Default preserves today's single-session behavior.
- **Liveness checks** — probe pid-alive and port-listening **independently**, and treat the two failure cases **differently**. RhinoMCP probes both, but Rook's Attached mode demands a more conservative deletion policy than "any probe fails ⇒ reap":
  - **PID dead** → the session is genuinely gone. Return `{code: rhino_session_dead, session, pid, next_action}` and **reap** the stale discovery record (safe — the process no longer exists).
  - **PID alive but port not listening** → do **NOT** reap. This can mean the plugin unloaded, the listener is restarting, a firewall/socket transient, or a startup/shutdown edge — and the live process may be the **user's document**. Return `{code: rook_native_listener_unreachable, session, pid, next_action}` and **leave the discovery record in place**.
- **Conservative stale-file deletion** — in P1 only dead-PID records are deleted; unreachable-but-alive records are reported, never removed. (Deletion policy for the alive-but-persistently-unreachable case is deferred — it needs a debounce/age threshold, out of scope here.)

### 8.2 Explicitly out of scope (this prototype)
- No spawning / auto-launch.
- No closing / killing.
- No mutation routing by default (route only read-only probes first: `/ping`, `/capabilities`, viewport/status-style reads).
- No change to RookNative route ownership.
- No replacement of the current single-session default.

### 8.3 Why this is the right first commitment
Validates the substrate before taking lifecycle ownership; protects attached user docs; begins dissolving the single-UI-thread bottleneck without making Rook responsible for launching Rhino; gives the coordinator a real mental model ("I have N sessions with different states"); is fully compatible with the Phase 1/2 capability work; and is the foundation every later phase requires.

---

## 9. Roadmap — the external/local-orchestration plane

Discipline (mirrors the rest of the Rook roadmap): **name and observe → report liveness → route safely → own lifecycle.**

```
P0 (done)  Phase 2C standalone smoke PASSED (PR #207). New route diagnostics paused.
P1         Read-only named sessions + liveness/stale-session errors (recommended)   (§8)
P2         Crash / dead-session wrapper for the adopted-session path
             (structured rhino_session_dead, crash-report surfacing, reaping)
P3         Mutating session targeting with explicit user/coordinator intent
             (Attached-mode guards; mutation requires a resolved, live session)
P4         Auto-launch a disposable Workbench session
             (port env + runscript spawn; wait-for-bind; license-dialog detection)
P5         Spawn / close / recover Workbench slots
             (owned vs adopted; reap + respawn; coordinator fan-out across slots)
—— parallel, independent ——
PC         MCPB connector packaging for the external-client adapter (pull forward; small)
PX (XL)    Cross-platform / Mac — strategic, separate track. C++ native is the blocker.
             Do NOT bundle with P1–P5. Decide as its own go/no-go.
```

### 9.1 Sequencing notes
- **PC (connector)** is independent and cheap; can land alongside P1–P2 to improve external-client onboarding. It packages the *adapter*, not the product.
- **PX (Mac)** is the one genuinely XL item — McNeel gets it free from C#/.NET; Rook's C++/Windows native plugin is the blocker. Treat as a strategic go/no-go, not a sprint.
- **Schema-from-reflection / fewer-tools** is folded into Q4's stance: the coordinator's surface is intent/KG-shaped; the 300 routes stay as substrate. No separate "expose cleaner tools" workstream.

---

## 10. Target architecture (hybrid)

```
Rook Local Runtime  (Python)
  ├─ local models + knowledge graph + learned conventions
  ├─ agent coordinator (Planner/Workers/Conductor, intent runtime)
  ├─ project / design memory
  ├─ module health
  ├─ Rhino slot/session adapter   ← the router capability (this plane)
  └─ MCP / external-client adapter (stdio; MCPB connector)   ← secondary surface

Rhino session  (one attached capability provider among several)
  └─ RookNative (sole in-Rhino HTTP / capability / control / discovery surface)
       └─ managed companion (RhinoCommon / GH / BIM / UI bridges)
```

McNeel = clean reference for **tool access**. Rook = the **local reasoning + product layer** above it. Adopt their access ergonomics; keep Rook's center of gravity.

---

## 11. Open questions / follow-ups

- Registry storage for P1: in-process dict is enough until **concurrent routers** (multiple simultaneous agent sessions) are real. SQLite (RhinoMCP's `SlotStore`) becomes necessary at P5 / multi-session coordinator fan-out — adopt its `BEGIN IMMEDIATE` + WAL + "row-is-the-lock" pattern then.
- Viewport return enrichment (image + camera/scene diagnostics) is a small, high-LLM-value adopt — slot it near P2.
- Discovery-record fields (verified): `processId`, `port`, `pluginVersion`, `rhinoInside`, plus a capability snapshot are present (`RookServer.cpp:2195-2214`). **`processId` is sufficient for P1 liveness** (pid-alive + port-listening). There is **no Rhino major-version field** (only `pluginVersion`, which is Rook's version, and `rhinoInside`). So: **drop `version` from the P1 prerequisite.** A small `rhinoMajorVersion`/`rhinoVersion` discovery field is only needed later (P4/P5, when version-pinned spawn matters) — add it then, not now.
- Decide whether `_RookSpawn` (P4) reuses the existing native autoload path or a dedicated hidden command.

---

## 12. Decision log

- **Do not panic-pivot.** RhinoMCP is a reference for the access layer, not Rook's destination.
- **Adopt access lessons, not center of gravity.** Local-first + KG + coordinated agents stays the bet.
- **Invariant amended** (§6): RookNative = sole *in-Rhino* surface; a Rook router may be the *public MCP* surface.
- **Fourth plane added** (§7): external/local-orchestration.
- **Two modes** (§7.2): Workbench (owned, may kill/respawn) vs Attached (adopted, never kill) = earned-autonomy substrate.
- **Prototype 1 approved as next step** (§8): read-only named sessions + liveness envelope; read-only targeting allowlist only; conservative deletion (reap dead-PID only, report alive-but-unreachable); no spawn/kill/mutation. Implementation plan pending.
- **Mac is a separate XL go/no-go**, never bundled with P1–P5.
