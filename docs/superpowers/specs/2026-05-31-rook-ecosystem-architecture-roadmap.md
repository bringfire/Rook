# Rook Ecosystem Architecture Roadmap

Date: 2026-05-31

Status: Draft foundational roadmap/spec. This is not an implementation plan.

Related context:

- `docs/CURRENT_ARCHITECTURE.md`
- `docs/AGENT_ARCHITECTURE.md`
- `docs/TROUBLESHOOTING.md`
- `docs/superpowers/specs/2026-05-26-managed-companion-startup-quiescence-design.md`
- `docs/superpowers/specs/2026-05-24-rhino-inside-revit-discovery-design.md`
- `docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md`
- `docs/superpowers/specs/2026-05-28-rookbim-runtime-category-resolution-design.md`
- `docs/superpowers/specs/2026-05-14-gh-legacy-route-readiness-boundary-design.md`
- `docs/superpowers/specs/2026-05-08-rhino-runtime-harness-design.md`
- `docs/superpowers/specs/2026-05-17-local-testing-live-proof-design.md`
- `docs/superpowers/specs/2026-05-18-rookvision-provider-media-policy-design.md`
- `docs/superpowers/specs/2026-05-12-ffmpeg-bundling-policy-design.md`
- `installer/RookSetup.iss`
- `installer/post_install.py`
- `scripts/deploy-local-testing.ps1`
- `scripts/register-rooknative-suite.ps1`
- `scripts/validate-release-artifacts.ps1`
- `scripts/tests/release-installer-guards.tests.ps1`
- `C:/Users/aryan/Desktop/Rhino_Plugin_Guide_Bundle/Rhino_Plugin_Deployment_and_Licensing_Guide.md`

No separate earlier "installer vision" document was found in the current tree
during review. This roadmap therefore treats the active installer source,
post-install validation, release artifact validation, release guards, and local
testing proof documents as the current installer/productization record. The
local desktop deployment/licensing guide was reviewed as commercial product
context, especially for installer technology, code signing, licensing,
entitlements, and multi-client MCP configuration.

## Purpose

Rook is moving from a working Rhino plugin into a product ecosystem. The next
architecture milestone is not to split everything apart immediately. The
milestone is to make the system explicit enough that it can grow safely.

The core product question is:

> How does Rook add more capability domains without making startup, discovery,
> routing, diagnostics, release packaging, or external LLM behavior fragile?

The answer in this roadmap is:

- Use a runtime capability model as the architecture spine.
- Treat installer/release structure as a first-class parallel productization
  track.
- Keep current deferred/eager companion loading as the early-phase
  compatibility baseline.
- Defer on-demand loading until clients can discover and handle domain states.
- Preserve all existing working behavior while migrating through explicit,
  validated phases.

## Current Architecture Summary

RookNative is the only public Rhino plugin surface. It owns:

- the public HTTP server;
- route registration;
- native discovery files;
- the main-thread dispatcher;
- scene graph/session subsystems;
- native command-control behavior;
- the public `/gh/*`, `/bim/*`, `/vision/*`, native Rhino, block, viewport,
  command, and utility route surface.

The managed companion is internal. It does not own a public HTTP server. It
currently provides important capability domains behind native routes and Rhino
UI commands:

- Grasshopper callback bridge;
- Rook Chat, Rook Vision, and Knowledge Graph panels;
- chat service launch/configuration;
- vision/media providers and image/video job management;
- Tier 3 viewport capture;
- BIM contracts and optional RookBIM module loading;
- companion-backed block-definition mutation exceptions;
- managed Rhino UI commands such as `ShowRookChat`, `ShowRookVision`,
  `ShowRookKnowledgeGraph`, and `RestartRookChatService`.

RookBIM is a first-class optional domain. It lives in `src/RookBim`, references
Revit APIs there only, loads through the managed companion, and activates a
Revit-backed runtime only when Rhino.Inside/Revit and Revit API assemblies are
present.

The Python MCP runtime and RookChat agent runtime are external to Rhino but
route through RookNative. Agent and chat paths converge on the HTTP bridge.
External clients discover Rhino targets through native discovery records under
the Rook discovery root.

The current installer is already broader than one Rhino plugin. It installs:

- RookNative;
- managed companion runtime payloads for `net8.0`, `net7.0`, and `net48`;
- optional RookBIM payload through the managed runtime layout;
- bundled FFmpeg;
- Python MCP server;
- Chirp source/runtime;
- knowledge stores;
- user-facing docs and instructions;
- Claude/Codex configuration;
- chat service manifest.

Current discovery is too narrow for the product Rook is becoming. The native
discovery file reports native host/port/process/version/Rhino.Inside state and
a Grasshopper callback route list only when the broad bridge registration is
ready. That bridge registration currently covers more than Grasshopper: it also
includes vision and BIM dispatch slots. The result is a single coarse readiness
boundary for several product domains that need separate state.

## Architectural Principles

1. RookNative remains the sole public Rhino HTTP and discovery surface.
2. The managed companion remains internal.
3. Native readiness is separate from managed readiness.
4. Managed readiness is separated by domain, not reported as one vague bridge
   bit.
5. A capability may be discoverable even when unavailable, degraded, missing
   dependencies, or not currently loaded.
6. External LLM/client discoverability is a product contract, not a diagnostic
   afterthought.
7. Current startup, GH, BIM, chat, vision, block, native route, and release
   behavior must not regress.
8. RookBIM/Rhino.Inside/Revit is a first-class domain, not a Grasshopper
   side note.
9. Runtime capability architecture and installer module architecture should
   eventually converge, but Phase 1 must not force that convergence.
10. Migration proceeds through measured phases with explicit validation gates.

## Recommended Architecture Stance

The roadmap uses three architecture options in a deliberate order.

### Option A: Runtime Capability Spine

Option A is the architecture spine.

Rook first introduces a versioned capability/domain model exposed by
RookNative. Native keeps serving the public route surface and continues
requesting companion load as it does today. The new work is that each product
domain gets its own state, route/tool inventory, dependency evidence,
diagnostics, and validation gates.

This is the lowest-risk path because it clarifies behavior before changing
load policy.

### Option B: Parallel Productization Track

Option B is a parallel installer/release track.

Rook needs a product module model for packaging, upgrades, diagnostics, and
support. That model should eventually align with runtime capabilities, but it
should not block Phase 1 runtime readiness work. The installer can begin
recording installed modules, versions, payload paths, and health probes while
the runtime continues using the current deployed layout.

This avoids letting an installer reorganization drive risky runtime changes.

### Option C: Later On-Demand Optimization

Option C is a later optimization.

On-demand companion/domain loading becomes eligible only after:

- clients can discover domain state before calling domain routes;
- unavailable/degraded/missing-dependency states are explicit and stable;
- diagnostics identify why a domain is not ready;
- tests and live harnesses prove the changed availability semantics;
- each affected domain has a rollback-compatible migration path.

Do not start by turning companion load into a lazy subsystem rewrite.

## Long-Term Target Architecture

The target architecture is a hub-and-domain model:

```text
External clients / LLM tools / chat agents
        |
        v
Rook MCP runtime and direct HTTP clients
        |
        v
RookNative public HTTP + discovery + capability contract
        |
        +-- native.core
        +-- native.command_control
        +-- native.scene_graph
        +-- gh.bridge / gh.canvas
        +-- bim.rhino_inside_revit
        +-- chat.ui
        +-- vision.media
        +-- viewport.capture
        +-- block.definition_mutation
        +-- mcp.runtime
        +-- knowledge.stores
        +-- future optional domains
```

RookNative is the public contract point for every Rhino-hosted domain. Managed
code may own implementation details, UI, or host-specific API calls, but
external clients should not need to know whether a route is native-only,
managed-backed, RookBIM-backed, chat-service-backed, or future-module-backed in
order to make safe decisions.

The runtime must report domains that exist even when they are not ready. For
example, an external LLM should be able to learn:

- Grasshopper exists but has no active editable canvas.
- RookBIM exists but is unavailable because the host is not Rhino.Inside/Revit.
- Vision exists but a provider credential is missing.
- Chat UI exists but the panel has not been opened.
- A block-definition mutation route exists but depends on the managed
  companion bridge.
- A future optional module is installed but not loaded.

## Capability And Domain Model

Capabilities are product domains, not just callback slots or files on disk.

Each domain should have a stable identifier. Initial identifiers should include:

| Domain ID | Purpose | Expected Owner |
| --- | --- | --- |
| `native.core` | Native HTTP server, ping, discovery, dispatcher, core native routes | RookNative |
| `native.command_control` | Command prompt/send/cancel control during command-active states | RookNative |
| `native.scene_graph` | Native scene graph read/index behavior | RookNative |
| `gh.bridge` | Managed Grasshopper callback bridge and `/gh/*` route substrate | Managed companion via native |
| `gh.canvas` | Active canvas/document readiness for inspection and mutation | Managed companion |
| `bim.rhino_inside_revit` | RookBIM live Revit model interrogation | RookBIM via companion/native |
| `chat.ui` | Rook Chat panel and chat service launch/configuration | Managed companion + MCP runtime |
| `vision.media` | Vision providers, artifacts, image/video jobs, media policy | Managed companion via native |
| `viewport.capture` | Viewport capture tiers, including managed Tier 3 capture | Native + managed |
| `block.definition_mutation` | Companion-backed block-definition mutation exceptions | Managed companion via native |
| `mcp.runtime` | Installed Python MCP runtime and client configuration | Installer/post-install |
| `knowledge.stores` | Bundled and mutable knowledge stores | Installer + Python runtime |
| `chirp.runtime` | Chirp adapter/service and deterministic GH component support | Installer + Python runtime |
| `licensing.entitlement` | Product license, subscription, trial, and feature entitlement state | Future licensing service + companion/native summary |

Domains may be hierarchical, but clients must not be forced to infer one
domain's readiness from another unless the dependency is explicit. For example,
`gh.canvas` depends on `gh.bridge`, but `bim.rhino_inside_revit` should not be
treated as a Grasshopper subdomain.

## Readiness State Contract

Every domain should report a stable state. Initial states should be:

| State | Meaning |
| --- | --- |
| `ready` | Domain can serve its advertised ready operations now. |
| `degraded` | Domain can serve some operations, but with limitations or known warnings. |
| `unavailable` | Domain exists but cannot currently serve operations. |
| `not_loaded` | Domain exists but its runtime/module is not currently loaded. |
| `loading` | Domain load/initialization is in progress. |
| `blocked_by_host` | Host context makes the domain inapplicable, such as BIM outside Rhino.Inside/Revit. |
| `missing_dependency` | Required file, runtime, credential, service, or host dependency is absent. |
| `failed` | Domain attempted to initialize and failed. |
| `unknown` | State cannot be determined; this should be temporary and diagnostic-heavy. |

Each state record should include:

- `domainId`;
- `displayName`;
- `state`;
- `ready`;
- `installed`;
- `loaded`;
- `degraded`;
- `retriable`;
- `reasonCode`;
- `message`;
- `dependencies`;
- `routes`;
- `tools`;
- `operations`;
- `hostConstraints`;
- `version`;
- `schemaVersion`;
- `lastUpdatedUtc`;
- `diagnostics`.

The contract should distinguish execution readiness from discoverability:

```json
{
  "domainId": "bim.rhino_inside_revit",
  "displayName": "RookBIM Rhino.Inside/Revit",
  "state": "blocked_by_host",
  "ready": false,
  "installed": true,
  "loaded": false,
  "retriable": false,
  "reasonCode": "not_rhino_inside",
  "message": "RookBIM requires RhinoInside.Revit and RevitAPIUI to be loaded.",
  "routes": [
    "GET /bim/status",
    "GET /bim/active-document",
    "GET /bim/categories",
    "POST /bim/query-elements"
  ],
  "operations": [
    "status",
    "active_document",
    "list_categories",
    "query_elements"
  ],
  "hostConstraints": {
    "requiresRhinoInside": true,
    "requiresRevitApi": true
  }
}
```

## Native Readiness Versus Domain Readiness

Native readiness means:

- RookNative loaded;
- dispatcher started;
- HTTP server bound to loopback;
- native discovery file written;
- `/ping` responds;
- native core routes are registered;
- process identity and discovery cleanup are coherent.

Native readiness does not mean:

- Grasshopper is open;
- a Grasshopper canvas is editable;
- the managed companion has finished deferred startup;
- RookBIM is available;
- Revit API is available;
- chat service is running;
- provider credentials exist;
- vision media subsystems are initialized;
- companion-backed block routes are executable.

Domain readiness should be reported independently and should not suppress native
discovery. Native discovery must be available even when all managed-backed
domains are unavailable.

## External Client And LLM Discoverability Contract

External LLMs and direct clients need to make safe choices without guessing from
timeouts or failed mutations. Rook should provide a versioned discoverability
surface through RookNative.

Recommended surfaces:

- native discovery file includes a compact capability summary;
- `GET /capabilities` returns the full domain contract;
- `GET /capabilities/{domainId}` returns one domain;
- existing domain status routes remain domain-specific diagnostics;
- MCP tool metadata consumes the same domain model where practical.

Discovery should answer these questions:

- What domains exist in this installation?
- Which domains are usable now?
- Which domains are unavailable but expected in this product?
- Which dependencies are missing?
- Is the problem host state, credentials, module load, route readiness, or
  runtime failure?
- Which routes/tools are valid for this domain?
- Is retry appropriate?
- Is a lifecycle action available to make the domain ready?
- What should an LLM do next without inventing a route or blind retry?

LLM-facing tool surfaces should progressively disclose tools based on domain
state. A domain can remain discoverable while its tools are hidden, limited, or
annotated as unavailable.

Do not require clients to call GH, BIM, vision, or chat routes to learn that
those domains exist.

## Companion Loading Policy

Current deferred/eager companion loading is the early-phase compatibility
baseline.

Phase 0/1 rules:

- Native continues requesting companion load as it does today.
- Managed companion `OnLoad` remains minimal and startup-gated.
- Deferred companion startup continues after Rhino reaches quiescent idle.
- Native readiness is decoupled from companion/domain readiness.
- No domain loses existing availability semantics until its readiness state,
  diagnostics, and validation gates exist.

Near-term goal:

- Split readiness state and diagnostics by domain.
- Stop treating broad bridge registration as the product-level readiness model.
- Keep route behavior compatible while improving error and status reporting.

Later option:

- On-demand loading may be considered per domain after readiness and
  discoverability are mature.
- On-demand loading must be domain-specific, not a global "load companion if
  anything managed is called" rule.
- On-demand loading must be validated against startup `_Open`, GH, BIM,
  chat/panel, vision/media, block exceptions, and release install behavior.

Do not use on-demand loading as a shortcut for capability modeling.

## Grasshopper Readiness Model

Grasshopper needs multiple states, not one bridge bit.

Minimum split:

- `gh.bridge`: callback registration exists and can dispatch GH operations.
- `gh.runtime`: Grasshopper assemblies/runtime are available.
- `gh.canvas`: an active canvas/document exists and can be inspected or
  mutated safely.
- `gh.canvas_graph`: Canvas Graph Protocol/navigation callbacks are available.
- `chirp.runtime`: deterministic Chirp component support is installed and
  callable.

`/gh/status` should remain the domain status authority for GH details. The
capability model should summarize the important state and link callers to
`/gh/status` for deeper diagnostics.

Public `/gh/*` routes should retain the readiness categories from the GH legacy
route boundary:

- status/library routes may execute without active canvas readiness;
- canvas inspection routes fail closed when no real active editable canvas
  exists;
- mutation routes fail closed when `ready_for_edit` is false;
- lifecycle routes are explicitly classified and may intentionally change
  readiness only by reviewed behavior.

The capability model must not imply that GH is ready merely because the managed
companion is loaded.

## BIM / Rhino.Inside / Revit Readiness Model

RookBIM is a first-class domain:

```text
bim.rhino_inside_revit
```

It should report separately:

- RookBIM module installed;
- RookBIM module loaded;
- Rhino.Inside/Revit host detected;
- `RevitAPIUI` loaded;
- `RhinoInside.Revit` loaded;
- Revit API dispatcher available;
- active Revit document present;
- active document identity quality;
- active view/scope support;
- category resolution support;
- selection side-effect support.

Outside Rhino.Inside/Revit, RookBIM should be discoverable but
`blocked_by_host`. That is a normal state, not an installation failure.

If the RookBIM DLL is missing, report `missing_dependency` with the searched
paths. If the DLL fails to load, report `failed` with a concise error and log
location. If Revit has no active document, report `unavailable` or `degraded`
depending on which status operations can still run.

RookBIM readiness must not be inferred from GH readiness.

## Chat / UI Readiness Model

Chat/UI has several layers:

- managed companion loaded;
- panel registration complete;
- Rook Chat panel available;
- chat service manifest present;
- Python runtime present;
- chat service process launchable;
- chat service healthy;
- MCP/runtime paths resolve to installed AppData payloads;
- provider credentials/model configuration sufficient for chat.

`chat.ui` can be discoverable when no panel has been opened. It may be
`not_loaded` or `unavailable` while still advertising the route/command surface
and explaining what would make it usable.

The roadmap should keep chat UI panel behavior eager after companion quiescence
for now. Later work may make panel-specific services lazy, but only after
manifest health, service diagnostics, and client-visible state are stable.

## Vision / Media / Viewport Readiness Model

Vision/media readiness should be split from GH and from generic companion
readiness.

Suggested domains:

- `vision.media`: provider policy, credentials, artifacts, image jobs, video
  jobs, media validation, provider dispatch;
- `viewport.capture`: native viewport capture plus managed Tier 3 capture;
- `vision.ui`: Vision panel registration and WebView surface state, if UI
  state needs client-visible diagnostics later.

`vision.media` should distinguish:

- route dispatch callback present;
- artifact store available;
- provider catalog available;
- credentials present/missing per provider;
- local media dependencies such as FFmpeg present;
- video sidecar/backfill service state;
- active jobs/reconcile state.

Provider credentials should not block discoverability of the domain. They
should affect operation-level readiness and explain which operations need which
credentials.

Viewport capture readiness should not be hidden behind a general vision bit.
Native capture and managed Tier 3 capture may have different readiness and
failure modes.

## Companion-Backed Block Routes

The companion-backed block-definition mutation routes are intentional
exceptions, not accidental leftovers. They should become an explicit domain:

```text
block.definition_mutation
```

The roadmap should preserve the current exception list unless a future
companion-boundary audit proves a route can move safely:

- `/block/set-layers`
- `/block/set-materials`
- `/block/set-object-colors`
- `/block/set-object-names`
- `/block/set-object-user-strings`
- `/block/replace-object-geometry`
- `/block/transform-object`

Clients should be able to discover that these routes exist and are managed
backed. If the companion bridge is not registered, these routes should fail with
domain-specific unavailable diagnostics, not with a vague GH bridge failure.

Do not broaden this exception set without an explicit architecture review.

## Installer And Release Structure: Parallel Productization Track

Installer and release structure is a first-class track, parallel to runtime
capabilities. It should eventually converge with the domain model, but Phase 1
should not force that convergence.

Current installer reality:

- Rhino plugin payload lives under the per-user Rhino plugin folder
  `RookNative`.
- Native plugin lives at the plugin root.
- Managed companion payloads are packaged under `net8.0`, `net7.0`, and
  `net48`.
- Registry currently points the companion to `net7.0\Rook.rhp`.
- RookBIM is built into the managed output layout and copied where the
  companion can load it.
- FFmpeg is bundled under the plugin directory.
- MCP server, Chirp, knowledge, docs, and support files live under
  `%LOCALAPPDATA%\Rook\app`.
- Mutable data, logs, and discovery live under `%LOCALAPPDATA%\Rook`.
- Chat service manifest is written into the Rhino plugin directory.

Target productization model:

```text
%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\
  RookNative.rhp
  RookNative.pdb
  managed\
    net7.0\
    net8.0\
    net48\
  modules\
    rookbim\
      net48\
  ffmpeg\
  manifests\
    installed-modules.json
    chat-service.json

%LOCALAPPDATA%\Rook\
  app\
    mcp_server\
    chirp\
    knowledge\
    scripts\
    docs\
  data\
  logs\
  discovery\
  diagnostics\
```

This target layout is directional, not a Phase 1 mandate. Phase 1 may introduce
module manifests while preserving current physical paths.

Installer module records should eventually include:

- module ID;
- display name;
- installed version;
- payload path;
- runtime/framework;
- host compatibility;
- dependencies;
- domain IDs served;
- health probe command or status file;
- upgrade policy;
- uninstall policy;
- support log locations.

Initial module IDs should align with product components, not necessarily
one-to-one with runtime domains:

- `rook.native`;
- `rook.companion`;
- `rook.bim`;
- `rook.mcp`;
- `rook.chirp`;
- `rook.knowledge`;
- `rook.chat_service`;
- `rook.ffmpeg`;
- `rook.licensing`;
- future optional modules.

The runtime domain model and installer module model should reference each
other, but neither should pretend they are the same thing. One installed module
may provide several runtime domains; one runtime domain may depend on several
installed modules.

### Commercial Deployment Considerations

The current Inno Setup installer remains the pragmatic near-term packaging
choice. It already handles the product's custom needs: Rhino plugin registry
registration, multi-runtime managed payloads, post-install Python setup, MCP
client configuration, Chirp setup, knowledge payloads, and validation. A future
MSI/WiX or commercial installer track may become useful for enterprise
deployment, rollback, Group Policy/SCCM, or silent install requirements, but it
should be treated as a packaging milestone, not as a runtime architecture
precondition.

Rook should continue to be explicit about its registration model. The generic
Rhino deployment guide discusses `HKLM` plugin registration, but Rook's current
installer is per-user and writes `HKCU` registration with lowest privileges.
Changing that would affect install permissions, upgrades, uninstall behavior,
and support expectations. Any move to machine-wide registration must be a
separate product decision with installer, local deploy, and release smoke
coverage.

Yak/Rhino Package Manager is not a sufficient primary distribution mechanism
for the current Rook ecosystem. Rook needs custom install logic for Python MCP
runtime setup, client configuration merging, Chirp, knowledge stores, bundled
media tooling, chat service manifests, validation, and eventual licensing.
Yak-style packaging may be reconsidered only for a narrower optional module
that does not need those side effects.

Code signing becomes a commercial release requirement:

- sign the installer and uninstaller;
- sign native and managed plugin payloads where applicable;
- record signing status in release validation;
- keep unsigned dev/local builds possible but clearly labeled;
- treat SmartScreen reputation and certificate renewal as release operations.

MCP/client configuration must remain merge-safe. Installer and post-install
flows should update Claude, Codex, Cursor, VS Code, and future client configs
without overwriting unrelated user servers. The module manifest should record
which clients were configured, skipped, or failed, and `rook doctor` should
report the same state.

### Licensing And Entitlements

Licensing is a future first-class product domain, not a reason to change the
public HTTP architecture now.

The roadmap should reserve:

```text
licensing.entitlement
```

as a discoverable domain that can report license state without hiding product
capabilities. Capability discovery should still reveal domains that are
unlicensed, trial-expired, subscription-limited, offline-grace-limited, or
enterprise-floating-license unavailable.

Potential licensing models include:

- trial;
- subscription;
- perpetual;
- node-locked activation;
- floating/concurrent license;
- offline grace period;
- enterprise entitlement policy.

The licensing domain should eventually report:

- license state;
- entitlement tier;
- feature/domain entitlements;
- expiration or renewal state;
- offline grace state;
- activation machine/user evidence;
- support-safe reason codes;
- remediation hints.

Licensing must not become a vague global readiness bit. A domain can be
installed and technically ready but not entitled. Another domain can be
entitled but blocked by host state or missing dependencies. External clients
need to distinguish those cases.

Zoo/Cloud Zoo, Keygen, Cryptolens, LicenseSpring, or a custom licensing service
are product/business decisions outside this roadmap. Any integration must
preserve the architecture invariants:

- RookNative remains the public discovery surface.
- Managed companion remains internal.
- licensing state is exposed as capability/domain state, not as hidden route
  failure.
- offline/floating/subscription failures use stable reason codes.
- licensing checks do not make startup or native discovery brittle.

## Versioning And Upgrade Policy

Rook needs explicit version surfaces:

- product version;
- native plugin version;
- managed companion version;
- bridge ABI version;
- RookBIM module version;
- MCP runtime version;
- Chirp runtime version;
- knowledge bundle version;
- installer schema version;
- capability schema version.

Upgrade rules:

- Existing install paths remain supported until a migration PR proves
  compatibility.
- Registry path changes require install, upgrade, uninstall, and local deploy
  validation.
- AppData mutable data must not be overwritten by seed knowledge updates.
- Discovery/log directories may be cleaned by explicit stale-file policy only.
- Module manifests must tolerate older installs that do not have every field.
- Clients must handle unknown domains and unknown fields.

## Diagnostics, Logs, Discovery Files, And Supportability

Diagnostics should be designed for support, not just developer debugging.

Required diagnostic surfaces:

- native discovery files;
- native discovery diagnostic logs;
- companion runtime status file;
- companion startup log;
- capability/domain status route;
- installer module manifest;
- post-install validation output;
- release smoke manifest;
- owned-Rhino harness artifacts;
- chat service manifest and health;
- MCP doctor output;
- domain-specific status routes such as `/gh/status` and `/bim/status`.

Every unavailable/degraded domain state should include:

- stable `reasonCode`;
- human-readable message;
- dependency evidence;
- log or diagnostic path when available;
- retry/lifecycle hint;
- whether the state is expected for the current host.

Avoid diagnostics that only say "bridge unavailable." Name the domain and the
missing condition.

## Backward Compatibility And Migration Phases

### Phase 0: Document And Preserve

Goals:

- establish this roadmap;
- keep current loading and route behavior;
- keep native as sole public surface;
- identify current coarse readiness coupling;
- avoid code changes that alter startup behavior.

Validation:

- document review;
- no implementation plan in this PR;
- no behavior changes.

### Phase 1: Capability Contract Without Load Policy Changes

Goals:

- add versioned capability/domain schema;
- expose full capability state through RookNative;
- keep native discovery available regardless of managed readiness;
- keep native companion-load request behavior unchanged;
- report GH, BIM, chat, vision, viewport, and block exception domains
  separately;
- add source/contract tests for domain inventory and invariant preservation.

Validation:

- managed/source tests for capability schema;
- native source tests for discovery fields;
- MCP tests for capability parsing and LLM-facing tool availability behavior;
- existing GH/BIM/vision/chat tests remain green;
- recent-file `_Open` startup live gate remains green.

### Phase 2: Domain Diagnostics And Route Error Alignment

Goals:

- align route failures with domain readiness states;
- ensure companion-backed block exceptions report their own domain;
- ensure BIM outside Rhino.Inside is discoverable as `blocked_by_host`;
- ensure provider credential gaps are operation-level readiness, not hidden
  domains;
- feed capability state into MCP/chat progressive tool disclosure.

Validation:

- route contract tests for domain-specific unavailable responses;
- GH readiness live tests;
- RookBIM standalone and Rhino.Inside/Revit live tests;
- vision/media credential-missing and dependency-missing tests;
- chat service manifest/health tests.

### Phase 3: Installer Module Manifest And Productization

Goals:

- add installed module manifest generation;
- record installed payloads, versions, paths, domains served, and health probes;
- extend post-install validation to verify module manifest correctness;
- keep current physical layout unless path migration is explicitly approved;
- connect installer module data to runtime capability diagnostics where safe.

Validation:

- release installer guard tests;
- post-install validation;
- local deploy installed-runtime gate;
- release artifact validation;
- upgrade/uninstall smoke;
- no repo/worktree leakage into installed runtime.

### Phase 4: Runtime/Installer Convergence

Goals:

- map runtime domains to installer modules explicitly;
- use module manifests to improve missing-dependency diagnostics;
- support optional future domain modules without native route/discovery
  ambiguity;
- prepare for physical layout cleanup or `modules/` directory migration.

Validation:

- mixed-version install tests;
- missing-module tests;
- stale manifest tests;
- optional-module absent/present tests;
- support bundle includes enough evidence to diagnose install versus runtime
  failures.

### Phase 5: Selective On-Demand Loading

Goals:

- consider on-demand loading only for domains whose readiness/discoverability
  contracts are mature;
- preserve existing availability semantics unless explicitly changed;
- make each on-demand move reversible and domain-specific.

Validation:

- recent-file `_Open` startup repeated gate;
- GH readiness and mutation gates;
- RookBIM Rhino.Inside/Revit gates;
- chat/panel gates;
- vision/media gates;
- block exception gates;
- owned-Rhino harness startup and cleanup gates;
- release installer smoke.

## Validation Gates By Domain

### Native Core

- native MSVC build with working toolset;
- `/ping`;
- discovery file written to shared root;
- stale discovery cleanup;
- command-control saturation smoke;
- recent-file `_Open` startup validation.

### Grasshopper

- `gh_status`;
- no phantom canvas mutation;
- legacy route readiness boundaries;
- Chirp deterministic component smoke;
- GH undo/cleanup;
- direct HTTP and MCP route behavior.

### BIM / Rhino.Inside / Revit

- standalone Rhino reports BIM discoverable but blocked/unavailable as
  appropriate;
- Rhino.Inside/Revit publishes native discovery with Revit PID;
- RookBIM module load and unavailable fallback;
- active document status;
- category list/query/element info/parameters;
- selection and clear-selection live gates.

### Chat / UI

- panel registration after quiescent companion startup;
- chat service manifest path and schema;
- service launch/health;
- installed Python runtime path;
- provider/model configuration diagnostics;
- shutdown cleanup.

### Vision / Media / Viewport

- provider catalog availability;
- credential missing diagnostics;
- artifact store availability;
- image/video job reconcile;
- FFmpeg presence/provenance;
- video sidecar behavior;
- viewport capture tier status;
- panel/WebView smoke where UI behavior is in scope.

### Installer / Release

- release installer guard tests;
- post-install validation;
- release artifact validation;
- installed-runtime gate;
- owned-process release smoke;
- no source/worktree leakage;
- upgrade and uninstall behavior;
- release notes and manifest consistency.

## Risks

1. Capability schema overreach: too much schema too early can slow delivery.
   Mitigation: start with domain inventory, state, reason codes, routes, and
   diagnostics; add richer fields incrementally.
2. False readiness: reporting `ready` without live proof can mislead agents.
   Mitigation: require validation gates before marking operation groups ready.
3. Installer/runtime conflation: forcing module manifests to match runtime
   domains exactly can create artificial architecture.
   Mitigation: keep tracks parallel until convergence is proven useful.
4. Load-policy churn: on-demand loading can reintroduce startup and route
   regressions.
   Mitigation: keep current loading baseline through early phases.
5. Bridge ABI coupling: broad callback registration currently couples GH, BIM,
   vision, and block exceptions.
   Mitigation: capability state should be domain-specific even before ABI
   slots are split.
6. External client drift: MCP, chat, and direct HTTP clients may interpret
   readiness differently.
   Mitigation: make RookNative capability state the source consumed by all
   clients where practical.

## Explicit Non-Goals

- Do not implement code in this roadmap PR.
- Do not remove or delay current companion loading in Phase 0/1.
- Do not make managed companion a public HTTP surface.
- Do not introduce a second Rhino/Revit public plugin surface for RookBIM.
- Do not classify RookBIM as a Grasshopper feature.
- Do not move Revit API references into `src/Rook`.
- Do not reorganize installer physical paths before manifests and validation
  exist.
- Do not remove legacy routes as part of capability modeling.
- Do not hide unavailable domains from discovery.
- Do not treat a larger thread pool, arbitrary retry, or blind route probing as
  an architecture substitute.

## Proposed PR Sequence

1. **Capability schema spec and source guards**
   - Define domain IDs, state values, required fields, and compatibility rules.
   - Add tests that prevent collapsing domain readiness into one bridge bit.

2. **Native capability endpoint and discovery summary**
   - Add `GET /capabilities`.
   - Add compact domain summary to native discovery.
   - Keep existing route behavior unchanged.

3. **Managed domain status aggregation**
   - Have companion provide per-domain status snapshots for GH, chat/UI,
     vision/media, viewport Tier 3, block exceptions, and BIM fallback/module
     state.
   - Preserve current deferred startup.

4. **MCP and chat discoverability consumption**
   - Teach MCP/chat runtime to consume capability state for tool disclosure,
     failure messaging, and retry/lifecycle hints.

5. **Route error alignment**
   - Align GH, BIM, vision, viewport, and block exception unavailable responses
     with domain state and reason codes.

6. **Installer module manifest v1**
   - Generate installed module records during post-install and local deploy.
   - Validate payload paths, versions, dependencies, and health probes.
   - Preserve current physical layout.

7. **Release validation expansion**
   - Extend release smoke manifests to include capability and module state.
   - Add standalone Rhino and Rhino.Inside/Revit capability assertions.

8. **Runtime/installer convergence**
   - Link runtime domains to installed module records.
   - Improve missing-dependency diagnostics using module data.

9. **Optional domain module path migration**
   - Only after manifests and validation are stable, consider moving payloads
     toward `managed/`, `modules/`, and `manifests/` directories.

10. **Selective on-demand loading review**
    - Evaluate one domain at a time.
    - Require existing availability semantics, diagnostics, and live gates
      before any load-policy change.

## Durable Decision

Rook should grow by making capabilities explicit before making loading clever.

The near-term architecture is not "load less companion." It is:

```text
native public surface stays reliable
  + companion loading stays compatible
  + domain readiness becomes explicit
  + installer modules become inspectable
  + clients learn before they act
```

That is the path from working plugin to mature plugin ecosystem.
