# WebUI Substrate Contract — Proven by Knowledge Graph (v1)

**Date:** 2026-04-10  
**Status:** Post-implementation contract (proven, not speculative)  
**Authors:** Claude + Bringfire + Codex  
**Proves:** `2026-04-09-webui-substrate-module-boundaries.md`  
**PRs:** `#4 fix(chat): harden WebUI trust model`, `#5 feat(knowledge): add Knowledge Graph visualizer panel`

---

## What This Document Is

The boundaries doc (`2026-04-09`) was the theory. This document captures what
the Knowledge Graph implementation actually proved, what changed during
implementation, and what the concrete substrate API looks like for the next
module author.

If the boundaries doc and this doc disagree, this doc wins — it reflects
shipped code.

---

## The Substrate API (RookWebSurface)

**File:** `src/Rook/UI/Web/RookWebSurface.cs`

A module creates a class that extends `RookWebSurface` and declares three
things:

```csharp
protected override string ResourceRoot => "Rook.UI.Knowledge.Resources";
protected override string EntryPage => "knowledge-graph.html";
protected override string MinimalFallbackHtml => "...self-contained HTML...";
```

The substrate provides:

| Capability | How |
|---|---|
| WebView2 virtual host | `https://app.rook.invalid` — all surfaces share one origin |
| In-memory resource serving | `WebResourceRequested` serves from embedded assembly streams |
| CSP | Injected on HTML responses: `connect-src http://127.0.0.1:*` |
| Session nonce | Injected via `AddScriptToExecuteOnDocumentCreated` before navigation |
| Script buffering | `ExecuteScript()` queues before `DocumentLoaded`, replays in order |
| Explicit 404s | Missing resources return 404 with `X-Rook-Missing-Resource` header |
| Dark background | `DefaultBackgroundColor` set on native control to prevent white flash |
| Fallback | `MinimalFallbackHtml` loaded via `LoadHtml` when WebView2 unavailable |
| Bootstrap hook | `GetBootstrapScript()` override for surface-specific pre-navigation JS |
| Ready callback | `OnWebViewReady()` fires after document loads and buffered scripts flush |

**What the substrate does NOT provide:**

- Feature-specific routes
- Feature-specific JS bridge methods
- Layout (buttons, sidebars, toolbars)
- Renderer libraries (cytoscape, three.js, etc.)
- Domain logic

---

## The Module Contract

To ship a new WebUI module, you need exactly these pieces:

### C# side

1. **Surface class** — extends `RookWebSurface`, declares `ResourceRoot`,
   `EntryPage`, `MinimalFallbackHtml`
2. **Panel class** — Eto `Panel` implementing `IPanel`, creates the surface
   via `CreateWebContent()`, bootstraps service connection in `PanelShown`
3. **Command class** — toggles panel visibility using `GetOpenPanelIds()`
   (not `GetPanels()` — instance existence != visibility)
4. **Panel registration** — `Panels.RegisterPanel(...)` in `RookPlugin.OnLoad`
5. **csproj entry** — `<EmbeddedResource Include="UI\{Module}\Resources\**\*" />`

### Python side (Pattern B modules only)

6. **Route handlers** — registered in `create_chat_app()`, automatically
   covered by CORS + nonce middleware
7. **Domain logic** — exporter, transformer, or whatever the module needs

### Frontend

8. **HTML entry page** — references vendored JS/CSS only (no CDN, no remote)
9. **JS** — fetches from `http://127.0.0.1:{port}` with `X-Rook-Session`
   header, uses `window.__rookServicePort` injected by the panel
10. **Vendored libraries** — in `Resources/vendor/`, included as embedded
    resources automatically

---

## What We Learned During Implementation

### Confirmed from the boundaries doc

- **Separate panels, not tabs in chat** — correct call. The knowledge graph
  has no relationship to chat conversation state.
- **Pattern B (chat server HTTP)** — correct for Python-owned data. The
  knowledge store lives in Python; routing through HTTP is natural.
- **Cytoscape, not Three.js** — correct. Graph topology is 2D. Adding a
  Z-axis would hurt, not help.
- **Module chooses its renderer** — the substrate doesn't care that the
  knowledge graph uses cytoscape. It just serves the vendored JS.
- **CORS is hygiene, nonce is the gate** — confirmed in every Codex review.

### Changed or refined during implementation

- **`LoadHtml` fallback uses minimal HTML, not full HTML.** The full
  `chat.html` / `knowledge-graph.html` has relative `vendor/` paths that
  can't resolve under `LoadHtml`. Fallback must be fully self-contained.
  This became a substrate-level rule, not a per-module decision.

- **Script buffering is required in the substrate.** `ExecuteScript` calls
  that arrive before `DocumentLoaded` must queue and replay. Without this,
  `setPersona` / `setConversation` / service bootstrap injections are
  silently lost on fast startup. This was a pre-existing race in the chat
  panel that the substrate extraction exposed and fixed.

- **`DefaultBackgroundColor` must be set on the native control.** Without
  it, every panel flashes white when losing focus. This is a WebView2
  platform behavior, not a CSS issue. Fixed in the substrate.

- **Health nonce exemption must be exact path, not suffix.** The original
  `endswith("/health")` would accidentally exempt future `/knowledge/health`
  or similar routes. Tightened to `request.path == "/agent/chat/health"`.

- **Reconnect lifecycle matters.** If the C# companion reloads but the
  Python chat server is still running, `SessionNonce` is null. The old
  server rejects everything. Fix: detect nonce-less reconnect and force
  restart to generate a fresh nonce.

- **fcose has a two-deep transitive dependency chain.** `cytoscape-fcose`
  requires `cose-base` which requires `layout-base`. All three must be
  vendored and loaded in order. The UMD side-effect registration is not
  reliable in WebView2 — explicit `cytoscape.use(cytoscapeFcose)` is
  required.

- **CSP `connect-src` and JS `serviceUrl()` must agree on the host literal.**
  CSP allows `http://127.0.0.1:*`. If JS constructs URLs with `localhost`
  (from discovery), CSP blocks them. Fix: JS always uses `127.0.0.1`
  regardless of what discovery returns.

- **Deprecated notes must be excluded from detail endpoints too.** The graph
  excludes deprecated notes, but the original detail endpoint returned them.
  This creates a contract mismatch — the graph says "this node doesn't
  exist" but the detail says "here it is." Fix: detail returns 404 for
  deprecated notes.

- **Graph payload must be deterministic.** `store.all()` returns notes in
  insertion order, which varies. Sort nodes by `id`, edges by `(source,
  target)` for caching, snapshots, and diff-based debugging.

### Not yet needed (correctly deferred)

- Cross-module navigation bus
- Artifact store (`%APPDATA%\Rook\artifacts\`)
- Shared capabilities (e.g., `GraphCanvas`, `MeshPreviewSurface`)
- Live graph updates during learning runs
- Saved layouts / pinning / workspaces
- Three.js for any surface

---

## Next Module Recommendations

The substrate is proven for Pattern B (chat server HTTP) modules with
vendored JS renderers. The next module should ideally exercise a different
axis to prove the substrate's generality:

### Option 1: Vision tab (Pattern A — in-process bridge)

Proves the substrate works for C#-owned surfaces with no HTTP. Rehouses
SA_Banana as a managed module. This is the locked v2 plan from
`2026-04-08-sa-banana-integration.md`.

**Why it's good next:** exercises Pattern A (the untested transport), and
the SA_Banana integration is already designed.

**Why it might wait:** Pattern A requires a JS↔C# bridge layer that doesn't
exist in `RookWebSurface` yet. That's new substrate work, not just a new
module.

### Option 2: Scene Graph explorer (Pattern A or B)

Proves the substrate works for a visualization that needs both graph topology
AND spatial preview. Could start as cytoscape (like KG) and add Three.js
later for spatial overlay.

**Why it's good next:** it's the second differentiator in POSITIONING.md
and it reuses the graph-rendering pattern we just proved.

### Option 3: 2D→3D review surface (Pattern B)

Proves the substrate works for a multi-step workflow with image + geometry
preview. This is where Three.js first enters.

**Why it might wait:** depends on HAWPv3 spike completing first, and
introduces Three.js which is a new renderer.

**My recommendation:** Vision tab (Option 1) if the goal is proving Pattern
A. Scene Graph explorer (Option 2) if the goal is building on what we just
proved and shipping another visible feature quickly.

---

## Review Checklist for New Modules

Before opening a PR for a new WebUI module, verify:

- [ ] Surface class extends `RookWebSurface` with correct `ResourceRoot`
- [ ] Panel class implements `IPanel` with `PanelShown` / `PanelHidden`
- [ ] Command uses `GetOpenPanelIds()` for toggle (not `GetPanels()`)
- [ ] Panel registered in `RookPlugin.OnLoad`
- [ ] csproj has explicit `<EmbeddedResource>` entry for the module
- [ ] All JS/CSS/vendor assets are embedded resources (no CDN, no remote)
- [ ] JS fetches use `http://127.0.0.1:{port}` (matches CSP)
- [ ] JS includes `X-Rook-Session` header on all fetch calls
- [ ] Python routes registered in `create_chat_app()` (middleware covers them)
- [ ] Deprecated / filtered data is excluded from both list and detail endpoints
- [ ] Fallback HTML is fully self-contained (no relative URLs)
- [ ] C# builds clean for both net7.0 and net48
- [ ] Existing tests still pass
- [ ] New routes have test coverage for schema, auth, and edge cases
