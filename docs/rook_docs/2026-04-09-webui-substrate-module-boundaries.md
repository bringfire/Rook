# WebUI Substrate, Shared Capabilities, and Module Boundaries

**Date:** 2026-04-09  
**Status:** Working architecture contract / Phase 2 guidance  
**Authors:** Codex + Bringfire (based on locked Phase 1 decisions)  
**Related:**
- `<repo>\src\Rook\UI\Chat\ChatTab.cs`
- `<repo>\src\Rook\UI\Chat\RookChatPanel.cs`
- `<repo>\mcp_server\src\rook\agent\chat\server.py`
- `<repos>\rook_docs\2026-04-08-sa-banana-integration.md`
- `<repos>\rook_docs\2026-04-09-grasshopper-video-nle.md`

---

## TL;DR

Rook should treat WebUI as a **shared platform** with **independent feature modules** on top of it.

- The **substrate** owns the hard common infrastructure: host, trust model, transport, panel/tab registration, shared styling, artifact roots, and cross-module navigation.
- A **shared capability** is a reusable building block that multiple modules consume: artifact browser, graph canvas, image preview, job-status feed, viewport capture service.
- A **module** is a feature-facing unit such as Knowledge Graph, Vision, 2D→3D review, Scene Graph explorer, or a future dashboard.

Near-term default: **separate panels/tabs that share infrastructure**.  
Do **not** start with a giant shared workspace. Evolve toward a more compositional model only when multiple real modules justify it.

---

## Locked Decisions

These decisions are already made and should be treated as constraints for any new WebUI work:

- Virtual-host origin: `https://app.rook.invalid`
- Session nonce is passed via env var or equivalent startup channel
- Discovery files remain metadata-only
- CORS is hygiene; the nonce is the real gate
- Phase 1 hardening is a narrow PR targeting `v1.4.6`
- Use system fonts first; vendor WOFF2 later only if it does not slow the patch
- Product model for now is **(a)**: separate surfaces sharing infrastructure
- Only move toward **(c)**, mixed shared workspace + standalone surfaces, when real modules prove the need

---

## Definitions

### 1. WebUI substrate

The substrate is the shared platform every WebUI surface runs on. It is responsible for:

- WebView hosting
- origin and nonce enforcement
- route and bridge plumbing
- panel/tab registration
- embedded-resource loading
- CSP and network policy
- shared design tokens and common UI primitives
- artifact root discovery
- lightweight cross-module navigation

The substrate is **not** a feature. It should not contain feature-specific business logic.

### 2. Shared capability

A shared capability is a reusable building block used by more than one module, or clearly likely to be used by more than one module soon.

Examples:

- artifact store and artifact browser
- image preview/lightbox
- graph canvas renderer
- async job/progress feed
- note-detail inspector
- viewport capture service

Shared capabilities sit above the substrate and below modules.

### 3. Module

A module is a feature-facing slice of the product with its own user purpose and domain logic.

Examples:

- Knowledge Graph
- Vision
- 2D→3D review
- Scene Graph explorer
- NLE/profiler dashboard

A module may consume multiple shared capabilities, but it should not reinvent them.

### 4. Artifact

An artifact is the shared currency between humans, agents, and modules. It is a stable, addressable unit of output or state, typically stored on disk with metadata.

Examples:

- generated image
- viewport capture
- depth map
- graph snapshot
- review state
- pipeline result

Modules should prefer exchanging artifacts or typed navigation intents over calling directly into each other.

---

## Boundary Rules

## 1. What belongs in the substrate

Something belongs in the substrate if it is required to make multiple WebUI surfaces possible or safe.

That includes:

- virtual-host and nonce model
- WebView bootstrapping
- resource loading and vendoring policy
- CSP defaults
- JS bridge or HTTP transport primitives
- panel/tab hosting and lifecycle hooks
- common styling tokens
- module registration and discovery
- cross-module deep links or intent dispatch

It does **not** include feature-specific routes, UI workflows, or domain terms.

If a proposed addition names a specific feature in its API, it probably does not belong in the substrate.

---

## 2. What belongs in a shared capability

Something belongs in a shared capability when it solves a reusable product problem, but is not universal enough to be substrate.

Promote something to a shared capability when at least one of these is true:

- two modules already need it
- one module needs it now and a second near-term module clearly will
- the implementation is non-trivial enough that duplication would be expensive

Good candidates:

- `ArtifactStore`
- `ArtifactGallery`
- `GraphCanvas`
- `JobStatusFeed`
- `ImageCompareView`

Bad candidates:

- `KnowledgeGraphPanelState`
- `VisionPromptComposer`
- `SceneGraphSelectionRules`

Those are module-owned.

---

## 3. What belongs in a module

A module owns the parts of the system that are specific to its feature:

- domain logic
- module-specific routes or bridge methods
- module-specific UI
- module-specific persistence schema on top of shared roots
- module-specific commands or entry points
- module-specific review workflow

If removing the module would leave the rest of the WebUI platform coherent, the code is probably module-owned.

---

## 4. What modules must not own

Modules must not own:

- their own trust model
- their own ad hoc HTTP server
- their own static-file serving stack
- their own panel host abstraction
- their own copy of shared vendor libraries unless justified
- their own hidden artifact root outside the shared path contract

In practical terms: a module should never quietly reintroduce the SA_Banana pattern of “standalone localhost server + static files + permissive CORS”.

---

## Transport Rules

## 5. Two transport patterns only

There are only two allowed transport patterns for human-facing WebUI surfaces:

### Pattern A: in-process bridge

Use when the work is naturally C# / RhinoCommon / short-running.

- WebView surface lives in Rhino
- JS talks to typed C# bridge methods
- no browser-facing HTTP surface for the human path

Expected users:

- Vision
- Scene Graph explorer
- possibly local artifact browsing

### Pattern B: chat-server HTTP

Use when the work is naturally Python-bound or genuinely async/streaming.

- WebView surface uses `fetch()` to the chat server
- every request carries the session nonce
- route namespace is explicit and module-owned

Expected users:

- Knowledge Graph
- future 2D→3D workflows
- long-running review/pipeline surfaces

Do not invent a third pattern unless the existing two are demonstrably insufficient.

---

## 6. Validation rule

Validation happens in the programmatic adapter layer, not in the substrate and not only in the UI.

That means:

- substrate enforces origin / nonce / transport policy
- module adapter validates arguments and permissions
- domain layer assumes validated inputs

If the same validation logic appears in both the UI and the backend adapter, the UI copy is advisory only. The adapter remains authoritative.

---

## Composition Rules

## 7. Cross-module interaction happens by artifact or intent

Modules should interact in one of two ways:

- by reading and writing shared artifacts
- by dispatching typed navigation intents

Examples:

- Vision emits an image artifact, 2D→3D review consumes it
- Knowledge Graph emits “open scene graph for object X”, substrate routes to Scene Graph explorer
- NLE dashboard opens a specific artifact or job state

Modules should **not** depend directly on each other’s internal classes or page instances.

---

## 8. Default UI composition model

For now, the default is:

- one module = one panel or tab
- shared infrastructure beneath
- lightweight cross-links between modules

This is intentionally conservative. It avoids overcommitting to a universal workspace before real usage proves one is needed.

Move toward a richer shared workspace only when:

- at least two modules need to appear together often
- users need persistent multi-view coordination
- duplicated layout/state management becomes a real maintenance cost

Until then, separate surfaces are a feature, not a limitation.

---

## 9. Shared workspace is an earned abstraction

Do not build a giant compositional dashboard framework up front.

A shared workspace becomes justified only when real modules prove the need for:

- docked subviews within one larger surface
- synchronized selection or focus across views
- shared command palette or local workspace state
- module-contributed widgets inside a common shell

If that day comes, the substrate can grow toward model **(c)**. It should not start there.

---

## Ownership Shape

## 10. Recommended layering

Each feature should be easy to map into three layers:

### Domain

Owns business logic and persistent data semantics.

Examples:

- graph export
- artifact metadata updates
- review pipeline steps
- viewport capture logic

### Programmatic adapter

Owns transport-facing APIs.

Examples:

- chat-server routes
- typed JS bridge methods
- MCP-facing wrapper methods

### Human adapter

Owns panel/tab UI and rendering.

Examples:

- HTML/JS/CSS
- Eto panel or tab glue
- user input collection
- visual state rendering

The substrate should help modules fit this shape. It should not collapse the layers together.

---

## Review Checklist

Use this checklist when adding a new WebUI feature.

### Substrate questions

- Does this feature rely on existing origin/nonce/CSP policy without modification?
- Is it using one of the two approved transport patterns?
- Does it load only local/vendored assets?
- Does it reuse panel/tab hosting instead of creating a new one-off host?

### Shared-capability questions

- Is this solving a problem another module already has?
- If copied into a second module, would that be obvious duplication?
- Should this become a shared capability instead of staying module-local?

### Module questions

- Is the feature’s domain logic isolated from the substrate?
- Are routes or bridge methods namespaced cleanly?
- Is persistence using the shared root contract instead of an ad hoc path?
- Can the feature be removed without breaking unrelated surfaces?

### Coupling questions

- Does this module communicate via artifact or typed intent?
- Is it directly referencing another module’s internals?
- If so, can that dependency be replaced by substrate-mediated navigation or shared artifact lookup?

---

## Renderer Selection Rules

## 11. Renderers are module choices, not substrate requirements

The substrate does not standardize on a single visualization library.

Its job is to provide:

- a safe WebView host
- trusted transport
- shared roots and styling
- panel/tab lifecycle

The module chooses the renderer that best fits the problem.

Examples:

- plain DOM/CSS for forms, lists, galleries, status, approval UI
- `cytoscape.js` for graph topology
- `three.js` for 3D mesh or spatial preview
- no external renderer at all when ordinary HTML is enough

If a renderer is needed by only one or two modules, keep it module-local.

---

## 12. Prefer the simplest renderer that correctly matches the problem

Do not reach for `three.js` when plain DOM, SVG, or 2D canvas is enough.

Use the simplest option that preserves clarity and keeps the implementation easy to secure and maintain.

Default preference order:

1. DOM/CSS
2. SVG or light 2D canvas
3. specialized 2D library such as `cytoscape.js`
4. `three.js` only when the problem is genuinely spatial or geometric

The burden of proof increases as the renderer becomes heavier.

---

## 13. Good first uses of Three.js

`three.js` is appropriate when the user benefits from orbiting, inspecting, or comparing geometry in 3D.

Good early uses:

- 2D→3D review
- scene-graph spatial preview
- before/after block rebase comparison
- geometry artifact inspection
- lightweight spatial overlays such as bounds, adjacency lines, or containment shells

In these cases, the 3D view is part of the feature itself, not decorative chrome.

---

## 14. Bad first uses of Three.js

`three.js` is the wrong tool when the surface is mostly about structure, text, state, or controls.

Bad early uses:

- knowledge graph topology
- dashboards
- chat-adjacent control surfaces
- forms and settings
- approval flows for flat images
- any surface where 3D adds novelty but not understanding

If a user would still understand the surface equally well from a static 2D representation, start without `three.js`.

---

## 15. Three.js in Rook is preview-first

In Rook, `three.js` should begin life as a preview renderer, not as a second full Rhino viewport.

That means:

- decimated meshes where possible
- lightweight materials
- modest texture use
- simple orbit/pan/zoom interaction
- stable frame pacing
- no assumption of dense, real-time scene rendering

Rhino and WebView2 share GPU resources. Module authors must assume preview scenes compete with Rhino for the same budget.

Do not build a WebUI surface that behaves like a second general-purpose modeling viewport unless there is a very strong product reason.

---

## 16. Promotion rule for shared 3D preview capability

If multiple modules converge on the same 3D preview shell, promote that shell to a shared capability, not to the substrate.

Examples of a future shared capability:

- `MeshPreviewSurface`
- `GeometryInspector`
- `SpatialDiffView`

That shared capability may wrap `three.js`, camera controls, common lighting, and standard interaction behavior.

But the substrate still should not depend on `three.js` directly.

The promotion threshold is the same as other shared capabilities:

- at least two real consumers now, or
- one consumer now and a second near-term consumer with obvious overlap

Until then, keep the dependency local to the module.

---

## Initial Module Map

This is the current recommended shape, not a permanent taxonomy.

### Substrate

- WebView host
- security model
- transport primitives
- panel registration
- shared tokens/styles
- deep-link or intent dispatcher
- root path discovery

### Shared capabilities

- artifact store
- artifact browser/gallery
- graph canvas
- image preview and compare
- job/progress model

### Modules

- Knowledge Graph
- Vision
- 2D→3D review
- Scene Graph explorer
- NLE/profiler dashboard

---

## Immediate Implication for Phase 1 and Phase 2

### Phase 1

Phase 1 remains narrow:

- harden the current chat WebView
- establish the real trust model
- remove remote dependencies
- unify route gating around nonce + origin

This document is **not** a Phase 1 blocker.

### Phase 2

Phase 2 should build the substrate so that:

- the first new module is straightforward
- the second new module is cheaper than the first
- cross-module handoff uses artifacts or intents, not bespoke coupling

That is the standard to judge the substrate by.

---

## Final Rule

If a future feature makes the WebUI platform more powerful but also more feature-specific, it is probably moving in the wrong direction.

The substrate should get **more reusable** as modules are added, not more entangled.
