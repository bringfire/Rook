# SA_Banana → Rook Vision Integration Plan

**Date:** 2026-04-08
**Status:** Reopened / v3 — video addendum (v2.2 locked for image; v3 reopens for video integration)
**Authors:** Claude (Opus 4.6) + Codex review (rounds 1, 2, and 3)
**Related:**
- `C:\Users\aryan\source\repos\SA_Banana` — source plugin
- `C:\Users\aryan\source\repos\Rook\docs\CURRENT_ARCHITECTURE.md`
- `C:\Users\aryan\source\repos\Rook\docs\plans\2026-03-08-companion-boundary-audit.md`
- `C:\Users\aryan\source\repos\Rook\docs\plans\2026-03-21-rhinocommon-capability-audit.md`
- `C:\Users\aryan\source\repos\Rook\docs\2026-04-03-security-rollout-plan.md` — establishes the principle that the native Rhino server is not for browser JS
- `C:\Users\aryan\source\repos\Rook\src\Rook\UI\Chat\ChatTab.cs` — existing Eto.Forms WebView tab base class that Vision will extend
- `drafts/Competitive Teardown_ ArchSynth vs. Rook (Rhino MCP).md`
- `C:\Users\aryan\source\repos\rook_docs\2026-04-09-grasshopper-video-nle.md` — GH-as-NLE proposal (complements this plan; video services are shared)
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\VeoClient.cs` — Veo API client (long-running operation polling)
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\VideoJobManager.cs` — 2-concurrent async job queue
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\VideoCapabilities.cs` — per-model constraint matrix
- `C:\Users\aryan\source\repos\SA_Banana\src\SA_Banana\Services\MediaStorage.cs` — unified disk layout (images + videos + frames + sidecars)

---

## TL;DR

Bring SA_Banana into Rook as an **internal managed module** (`RookVision`), not a sidecar plugin and not a wholesale port. Keep ~1,000 LOC of genuinely new C# services, delete ~800 LOC of HTTP/UI shell that duplicates Rook infrastructure, and skip the parts (viewport route, named-view enumeration) that Rook already covers. The **public surface** stays a single Rhino plugin (`RookNative`) with a single HTTP server. The internal C# companion (`src/Rook/`) continues to exist as a managed `.rhp` loaded on demand by `RookNative` — Vision lands inside the companion, not as a third plugin. See [`docs/CURRENT_ARCHITECTURE.md:32-59`](../Rook/docs/CURRENT_ARCHITECTURE.md#L32-L59) for the existing public/internal boundary.

**Vision is not "MCP-only" or "WebUI-replaced-by-MCP."** It is *one Vision engine, two clients*: MCP tools for agents, plus a `VisionTab.cs` in Rook's existing chat panel for humans. Both clients consume the same `Services/Vision/*` domain code through a three-layer adapter pattern. Human and agent share **artifacts by ID**, not by re-deriving state. SA_Banana's WebUI is *rehoused* as the WebView resources backing the Vision tab — not deleted.

**Key framings:**
- *Codex:* "BYOK is a payment model. Standalone plugin is a product-boundary decision. You can be fully BYOK without creating a second plugin product."
- *Codex:* "Rook Vision is a shared vision subsystem with two front doors: MCP tools for agents and a Rhino-hosted panel for humans."

---

## Background

### What SA_Banana is

A standalone Rhino 7/8 plugin (`C:\Users\aryan\source\repos\SA_Banana`) built by the same team. ~2,700 LOC of C#. Production-tested. Implements direct-to-Google-Gemini image generation from Rhino viewports with BYOK.

| Layer | LOC | Notes |
|---|---|---|
| Services | ~1,370 | `ViewportCapture.cs` (469), `GeminiClient.cs` (284), `PromptEnhancer.cs` (284), `ImageStorage.cs` (218), `DepthMapGenerator.cs` (113) |
| HTTP server | ~830 | `WebServer.cs`, `ApiRouter.cs`, six `Handlers/*.cs` files. Hardcoded port 17172, own CORS, own auth surface. |
| Models | ~170 | 4 DTOs |
| WebUI | embedded | vanilla JS + HTML, served from DLL resources |
| Settings | — | `%APPDATA%\SA_Banana\settings.json`, separate from Rook |

**Plugin GUID:** `4C23EE05-6FF3-47F6-ACB4-475968E37CDE`
**Frameworks:** .NET 7-Windows (Rhino 8), .NET Framework 4.8 (Rhino 7)

### Why it matters strategically

The ArchSynth competitive strategy (`drafts/Competitive Teardown_ ArchSynth vs. Rook (Rhino MCP).md`) proposed building a Rhino-integrated AI rendering pipeline as Rook Phase 1. **It already exists** in SA_Banana — integration is adaptation, not greenfield.

The strategic claim is **BYOK + native Rhino integration to undercut ArchSynth's SaaS model**. Users pay wholesale to API providers (Google AI / fal.ai / Replicate) instead of subscribing. Software is MIT.

---

## Claude's first-pass analysis (corrected after Codex review)

### Initial framing — three options

**Option A — Sidecar plugin, MCP wraps SA_Banana's HTTP**
- Leave SA_Banana as a second `.rhp`, expose its `localhost:17172` endpoints as Rook MCP tools.
- **Rejected.** A second `.rhp` would still load into the same Rhino process (so this is *not* a process-boundary objection), but it would: (a) reintroduce a second HTTP server with hardcoded port and its own CORS surface — undoing the load-bearing fix from the April 2026 security audit; (b) split the public product surface across two installable plugins with independent lifecycles, settings stores, and discovery files; (c) duplicate routing/auth/config infrastructure; (d) force users to install and update two plugins; and (e) create a permanent "why isn't this in core Rook?" support burden. The objection is split public surface and duplicated infrastructure, not process isolation.

**Option B — Merge C# services into `src/Rook/`, expose via the existing C++ → bridge → C# pattern**
- Same shape as `GrasshopperProxyHandler.cpp` ↔ `GrasshopperHandler.cs` ↔ `NativeGhBridgeRegistrar.cs`.
- **Recommended structure**, but my first pass over-scoped what should move.

**Option C — Option B + push the Gemini call to Python/LiteLLM**
- Viewport capture / depth / storage stay in C# (RhinoCommon-bound).
- Gemini API call moves to Python MCP via LiteLLM.
- **Open question:** does LiteLLM cleanly handle Gemini's multimodal-chat-shaped image generation? See spike below.

### What I got wrong on the first pass

Codex flagged three stale claims, all of which I verified directly:

1. **Rook's viewport route already supports the parameter surface I described as a SA_Banana win.**
   `src/RookNative/Handlers/ViewportHandler.cpp:71-202` already accepts `view`, `displayMode`, `zoomExtents`, `transparentBackground`, `scale`, `drawGrid`, `drawWorldAxes`, `drawCPlaneAxes`. It handles standard view names *and* named views via SDK lookup (Tier 1, no `RunScript`), and restores `ON_Viewport` state after capture.

2. **Named-view enumeration and round-trip already exist.**
   `src/RookNative/Handlers/DocumentOpsHandler.cpp:430-521` covers `/views`, `/views/save`, `/views/restore`. SA_Banana's `ViewsHandler.cs` is fully redundant.

3. **The "GH" registrar isn't really GH-only anymore.**
   `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs:76-103` already carries Make2d, Gumball*, Block*, GameExport, BakeOutput, ScriptParams callbacks under a comment pointing at `docs/plans/2026-03-08-companion-boundary-audit.md`. Adding Vision callbacks is the established pattern, not a layering violation.

**Lesson reinforced:** observe before theorizing. The first pass's "we need a better viewport route" framing was overstated by ~80%.

---

## Codex's verdict (verbatim, lightly trimmed)

> The architecturally appropriate way to bring SA_Banana into Rook is not as a second Rhino plugin and not as a second localhost server. It should become a Rook-owned feature domain behind Rook's existing public boundary: `RookNative` remains the only public plugin and HTTP surface, while the managed companion implements the RhinoCommon-only pieces behind the native bridge. If you want a product name, use something like "RookVision" as an internal module or assembly, not as a separately installed `.rhp`.

### Codex on what to keep vs drop

**Keep from SA_Banana:**
- RhinoCommon capture logic where it is materially better than Rook's current Tier 2 `RunScript` capture, especially the `CaptureToBitmap()` path and raytraced stabilization in `Services/ViewportCapture.cs:303`.
- Depth-map generation for image-conditioned workflows, from `Services/DepthMapGenerator.cs:12`.
- Provider-facing generation logic (or at least its request/response shape), from `Services/GeminiClient.cs:16`.
- Prompt enhancement and gallery/storage concepts, but folded into Rook-owned settings/storage rather than `%APPDATA%\SA_Banana`.

**Do not keep:**
- The standalone plugin shell (`SA_BananaPlugin.cs`).
- The embedded HTTP server and `/api/*` routing (`WebServer.cs`, `ApiRouter.cs`).
- The WebUI — Rook already has a chat-panel surface; duplicating UI paradigms would be a regression.

### Codex on the BYOK-vs-standalone decision

> If the real choice is:
> 1. a BYOK standalone plugin, or
> 2. a managed module/assembly inside Rook,
>
> then I would recommend `2` decisively.
>
> A BYOK standalone plugin does avoid SaaS, but it still creates a second product surface: separate install, separate lifecycle, separate settings, separate UX, separate support burden, and eventually separate "why isn't this feature in core Rook?" questions. That is exactly how product sprawl starts, even if no cloud service is involved.
>
> A managed module or assembly inside Rook preserves the anti-SaaS ethos better because:
> - the user still brings their own key
> - the compute can still be direct-to-provider, with no Rook-hosted middle layer
> - the public surface remains one thing: Rook
> - the operational complexity stays inside one installer, one settings model, one tool surface, one architectural boundary
>
> So I would frame the principle like this:
> `BYOK` is a provider/payment model.
> `Standalone plugin` is a product-boundary decision.
> Those are separate questions. You can be fully BYOK without creating a second plugin product.

---

## Refined integration scope

### Per-asset disposition

| SA_Banana asset | Verdict | Why |
|---|---|---|
| `ViewportCapture.GetAllViews()` | **Drop** | `DocumentOpsHandler.cpp:430` covers it |
| `ViewportCapture.RestoreNamedView` / `RestoreViewportState` | **Drop** | `ViewportHandler.cpp:115-211` covers it |
| `ViewportCapture.CaptureView()` (file path) | **Drop** | Existing route covers it |
| `ViewportCapture.CaptureToBase64()` (in-memory) | **Keep — adds a Tier 3 capture path** | C++ Tier 2 path (`_-ViewCaptureToFile`) goes file → disk → re-read and is one of three audit-named Tier 2 hazards. The new path proxies through the bridge to `view.CaptureToBitmap()` (Tier 3, .NET-only, no command processor). Triggered by an `inMemory: true` flag on the viewport route — *adds* a safer alternative for the new use cases, doesn't *replace* the existing Tier 2 handler. See "The 2026-03-21 audit directly applies to this merge" below. |
| `ViewportCapture` raytraced/Cycles wait-for-convergence (`ViewportCapture.cs:303`) | **Keep — only reachable through the Tier 3 path** | Capturing a Raytraced viewport mid-sample gives the AI a noisy start image. Stabilization is .NET-only and rides on the same Tier 3 capture path above. |
| `DepthMapGenerator` | **Keep** | Arctic display mode + grayscale fallback. New capability. Useful for ControlNet-style depth conditioning later. |
| `GeminiClient` | **Keep** | Provider call. No analogue in Rook. |
| `PromptEnhancer` | **Keep** | Text-model prompt structuring. New capability. |
| `ImageStorage` (gallery, metadata sidecars) | **Keep, but reshape** | Concept stays. `%APPDATA%\SA_Banana\` path goes; storage moves under the *new* Rook persistent settings root that this merge introduces (see Settings section — Rook has no such root in trunk today). |
| `WebServer` / `ApiRouter` / `Server/Handlers/*` | **Delete** | Replaced by C++ routes + bridge callbacks. |
| `WebUI/*` (HTML / JS / CSS) | **Rehouse, don't delete** | The HTML/CSS/JS becomes the WebView resources backing a new `VisionTab.cs` in Rook's existing chat panel ([`src/Rook/UI/Chat/ChatTab.cs`](../Rook/src/Rook/UI/Chat/ChatTab.cs) is the Eto.Forms WebView base class). The transport changes: `fetch('/api/...')` calls into the SA_Banana HttpListener get replaced with narrow, typed JS bridge calls into `VisionHandler.cs`. The visual experience is preserved. ~30% of the JS needs reworking (transport layer); UI components, prompt input, gallery view, settings dialog carry over. See "Human visual surface" architectural section below. |
| `SA_BananaPlugin.cs` / `SA_BananaCommand.cs` | **Delete** | Feature lives inside Rook. |

**Net merge size:** ~1,000 LOC of services kept, ~800 LOC of HTTP shell + plugin scaffolding deleted, ~900 LOC redundant with existing Rook routes, plus the WebUI assets (~few hundred LOC of HTML/JS/CSS) rehoused into `src/Rook/UI/Chat/Resources/Vision/` with the transport layer rewritten.

### Target file layout

```
src/Rook/
├── Services/
│   └── Vision/                         # ─── DOMAIN LAYER ───
│       ├── ViewportCaptureBitmap.cs    # in-memory CaptureToBitmap path + raytraced stabilization
│       ├── DepthMapGenerator.cs         # Arctic + grayscale fallback (lifted from SA_Banana)
│       ├── GeminiClient.cs              # provider call, BYOK (lifted from SA_Banana)
│       ├── PromptEnhancer.cs            # text-model prompt structuring (lifted from SA_Banana)
│       ├── ArtifactStore.cs             # NEW: jobs and artifacts, on-disk JSON sidecars +
│       │                                #   index, shared between C# and Python via filesystem
│       └── ImageGallery.cs              # thin wrapper over ArtifactStore for the gallery view
├── Handlers/                           # ─── PROGRAMMATIC ADAPTER ───
│   └── VisionHandler.cs                # bridge-side methods + JS-bridge handlers (same code).
│                                       #   THIS IS THE VALIDATION BOUNDARY for both adapters —
│                                       #   treats every argument as untrusted regardless of
│                                       #   whether it came from the JS bridge or the C++ → bridge path.
├── UI/Chat/                            # ─── HUMAN ADAPTER ───
│   ├── VisionTab.cs                    # NEW: Eto.Forms ChatTab subclass hosting WebView
│   └── Resources/Vision/               # NEW: HTML / JS / CSS lifted from SA_Banana, transport-rewritten
│       ├── index.html                  #   no remote script loading, no CDN, all assets local
│       ├── app.js                      #   replaces fetch('/api/...') with JS bridge calls
│       └── styles.css
└── InternalBridge/
    └── NativeGhBridgeRegistrar.cs      # add // Vision section with the new callbacks

src/RookNative/Handlers/                # ─── PROGRAMMATIC ADAPTER (continued) ───
├── ViewportHandler.cpp                 # add inMemory + raytracedConverge flags,
│                                       #   proxy to bridge when set
└── VisionHandler.cpp                   # new: /vision/generate, /vision/enhance-prompt,
                                        #   /vision/artifacts/*, all proxied to bridge

mcp_server/src/rook/server.py           # ─── PROGRAMMATIC ADAPTER (MCP surface) ───
                                        # new MCP tools: rhino_render_view, rhino_enhance_prompt,
                                        #   rhino_vision_artifacts, rhino_vision_get_artifact,
                                        #   rhino_vision_approve, rhino_vision_consume_approved
```

**Naming note on `src/Rook/UI/Chat/`:** the directory is currently named `Chat/` but already hosts non-chat tabs in concept. Adding `VisionTab.cs` makes that misnomer concrete. The rename to `src/Rook/UI/Tabs/` is a mechanical refactor that should be a separate PR (same reasoning as `NativeGhBridgeRegistrar` rename — don't couple a rename to a feature merge).

### Settings

**Rook does not currently have a persistent settings root.** [`src/Rook/RookPaths.cs:9`](../Rook/src/Rook/RookPaths.cs#L9) only exposes `DiscoveryFolder` under `%TEMP%/rook` (ephemeral, instance discovery). There is no equivalent of `%APPDATA%\Rook\settings.json` in trunk today.

The Vision merge therefore needs to **introduce** a persistent settings abstraction — likely a sibling of `RookPaths.cs` that resolves to `%APPDATA%\Rook\` — to hold the BYOK key, default model, output folder, and gallery defaults. SA_Banana's `%APPDATA%\SA_Banana\settings.json` is dropped *in favor of* the new Rook-owned root, not into an existing store. This is a real piece of work, not a routing change, and the schema should be designed once for Vision but with room for future modules.

### Installer / migration

The next installer build needs an uninstall step for the standalone `4C23EE05-6FF3-47F6-ACB4-475968E37CDE` plugin so users with both don't end up with shadowed `SA_Banana` and `SA_BananaSettings` commands.

---

## Architectural decisions

### Bridge naming — reuse now, rename later

`NativeGhBridgeRegistrar.cs:76-103` already carries non-GH callbacks under an explicit "boundary audit" comment. Drop new Vision callbacks into the existing registrar under a clearly demarcated `// Vision` section, the same way "Canvas Graph Protocol" is marked at line 69.

The rename to a generalized `NativeBridgeRegistrar` (or split into per-domain registrars) is a purely mechanical refactor that touches every existing registration site. Doing it *now* would couple a high-churn rename to a feature merge and inflate the review surface; doing it *later* lets the rename be its own reviewable PR with no behavior change.

**The right reference for the broader question is [`docs/plans/2026-03-21-rhinocommon-capability-audit.md`](../Rook/docs/plans/2026-03-21-rhinocommon-capability-audit.md), not the 2026-03-08 doc.** The 2026-03-08 audit is explicitly scoped to the block-definition boundary only ([line 122-127](../Rook/docs/plans/2026-03-08-companion-boundary-audit.md#L122-L127)) and points downstream to the 2026-03-21 audit for full-surface RhinoCommon expansion. The 2026-03-21 audit is the document that will house any future `NativeGhBridgeRegistrar` → `NativeBridgeRegistrar` decision and is the source of truth for "which side owns capability X."

### The 2026-03-21 audit directly applies to this merge

The RhinoCommon capability audit is more relevant than I gave it credit for in the first draft. Two specific points:

1. **View capture is already on the audit's expansion list.** [`docs/plans/2026-03-21-rhinocommon-capability-audit.md`](../Rook/docs/plans/2026-03-21-rhinocommon-capability-audit.md) explicitly identifies "View capture / block preview bitmaps (.NET-only `ViewCaptureSettings`)" as a known companion-expansion candidate. The Vision merge is the natural moment to land that work — we already have production-tested .NET capture code (SA_Banana's `ViewportCapture.cs`) waiting to be lifted.

2. **The audit's safety-tier model specifically flags Rook's current capture path as Tier 2 (hazardous).** Per the audit, [`ViewportHandler.cpp:145`](../Rook/src/RookNative/Handlers/ViewportHandler.cpp#L145)'s `_-ViewCaptureToFile` path is one of three named Tier 2 handlers in the entire codebase. Tier 2 means: pre-scripted `RunScript` call, low but real modal-dialog risk, capable of blocking the dispatcher inside `RunScript()` itself with no recovery. The audit's Decision Framework (point 4) says companion routing is justified when "there is genuinely no safe SDK path." `view.CaptureToBitmap()` is exactly that: a .NET-only API with no C++ SDK equivalent and no command-processor involvement.

   This means the Vision merge isn't just adding an `inMemory: true` convenience flag — it's adding a **parallel Tier 3 capture path** that's safer than the existing Tier 2 handler and unlocks capabilities (in-memory output, raytraced sample stabilization) the Tier 2 path *cannot* provide. That reframes the architectural argument from "we want a nicer capture API" to "we're narrowing a known Tier 2 hazard's exposure by giving callers a safer alternative."

   **The audit's anti-convenience rule (point 3, "If a command covers 80%+, use the command path... Do not create a Tier 3 companion route for convenience") does *not* override this**, because the Tier 3 path isn't being added for parameter coverage parity — it's being added for capabilities (no disk round-trip, raytraced convergence) that the Tier 2 path provably can't provide. The existing Tier 2 handler stays in place for callers who want a file on disk; the Tier 3 path takes over when the caller wants in-memory bytes or stabilized raytraced output. View capture is also already on the audit's named companion-expansion list, so this isn't a unilateral expansion of the bridge surface.

   **Scope discipline:** this is *not* a wholesale "rip out `_-ViewCaptureToFile`" migration. The Tier 2 handler keeps its existing role; the Tier 3 path is additive. If a future PR wants to retire the Tier 2 handler entirely, that's a separate decision that should reference this doc but not be bundled into the Vision merge.

### Separate `.csproj` for `RookVision` — not yet

Codex left this as conditional: "if you want clean code ownership." I'd push back for now.

The bridge registrar lives in `src/Rook/InternalBridge/`, and any vision handlers it registers have to be reachable from there. A separate `RookVision.csproj` would either need:
- `Rook.csproj` to depend on it (means `Rook.csproj` knows about every feature module — bad), or
- `RookVision.csproj` to depend on `Rook.csproj` to consume the registrar API (no actual isolation benefit), or
- Splitting the registrar into a third assembly (real surgery for no concrete payoff).

Start with `src/Rook/Services/Vision/` and `src/Rook/Handlers/VisionHandler.cs` as folders. **Promote to a separate project if and when:**
- Vision grows past ~5k LOC, or
- It picks up its own NuGet dependencies the rest of Rook doesn't need, or
- Someone genuinely wants a "Rook without vision" build.

None of those conditions hold today.

### LiteLLM — keep C# in v1, revisit in v2 with a new spike question

**Key reframing:** Gemini's image generation isn't an image-generation-API shape; it's a **multimodal-chat shape**. You send a chat completion with text + image parts in the message, and Gemini returns text + image parts in the response. SA_Banana's `GeminiClient.cs` is structured this way, with viewport-as-last-image in the parts array.

This means LiteLLM's `chat.completions` route may handle this fine (it routes Gemini through Vertex/AI Studio with multimodal parts), whereas `litellm.image_generation` definitely won't. The spike question reframes:

- ~~Does LiteLLM support image gen?~~
- **Does LiteLLM's chat completion path correctly round-trip multipart image *responses* for Gemini's image-preview models?**

That's a 30-minute test against a real key.

**Decision for v1:** Keep the GeminiClient in C#. It's already written, BYOK already works, no extra hop. The architectural shape doesn't change either way — the C# `VisionHandler` either calls `GeminiClient` directly (v1) or HTTPs into the Python MCP layer (v2), both fully compatible with the "C# managed module" structure.

**Move to LiteLLM in v2 when:**
1. We want a second provider (fal.ai / Replicate / Imagen), and
2. The multipart-response spike comes back green.

### Human visual surface — Pattern A tab in the chat panel

The first draft of this plan said "drop the WebUI." That was wrong, or at least incomplete. The right call, after observing the existing chat panel, is **rehouse the WebUI as a tab in Rook's existing chat panel** — not delete it, not preserve it as a standalone localhost app.

#### What I observed

[`src/Rook/UI/Chat/ChatTab.cs:12-19`](../Rook/src/Rook/UI/Chat/ChatTab.cs#L12-L19) is already an abstract Eto.Forms base class providing "WebView-based rich text" with HTML/JS execution from C# on the UI thread (line 431). Concrete subclasses already exist: `AgentChatTab`, `ClaudeCodeTab`. `RookChatPanel.cs` is the host, and `ChatTab.cs:29` even includes a TextArea fallback when WebView is unavailable. **The tab is already the architectural unit for human visual surfaces in Rook.** Adding a `VisionTab.cs` is a known pattern, not new framework work.

#### Two transport patterns for tabs

| Pattern | Backend | Communication | Use when |
|---|---|---|---|
| **Pattern A — In-process tab** | C# in `src/Rook/Services/` | WebView JS bridge → C# methods directly. No network at all. | The work is C#-bound (RhinoCommon, .NET-only APIs) or short-running and synchronous. **Vision lands here.** |
| **Pattern B — HTTP tab** | Python in `mcp_server/src/rook/` | WebView `fetch()` → chat server (aiohttp) → Python module | The work is Python-bound *and* needs an async service boundary (long-running pipelines, streaming progress). **Image-to-CAD will land here when it ships.** |

The rule: **prefer Pattern A unless you genuinely need an async service boundary.** "Python is on the other side of a process" is *not* sufficient justification — `RhinoCommon` is also "on the other side of a process" from the MCP server, but Vision still uses Pattern A because the work itself happens in C#. Pattern B's justification is the *combination* of Python-bound logic plus genuine async needs (image-to-CAD's 30s+ pipeline runs are an example).

**Vision uses Pattern A.** The Vision tab's JavaScript talks to `VisionHandler.cs` directly via WebView's JS bridge. There is no HTTP layer for the human path. The same `VisionHandler.cs` is reachable from MCP through the existing C++ → bridge → C# path. One handler, two adapters, identical validation discipline (see "Three-layer architecture" below).

#### "No HTTP" is not "free security"

An in-process WebView tab removes the network attack surface, but it does not remove all attack surface. WebView2 has its own threat model — origin spoofing via custom URI handlers, JS bridge type confusion, CSP gaps, mixed-content if any remote asset slips in. The intuition that "it's in-process so it's safe" is exactly the kind of reasoning that puts `eval()`-equivalent code paths on a privileged surface.

**Vision tab security checklist (Codex's five controls + concrete mappings):**

1. **Ship only local/static UI assets.** All HTML/JS/CSS lives under `src/Rook/UI/Chat/Resources/Vision/` and is loaded from disk. No CDN scripts. No remote font loaders. No analytics. No `<iframe src>` to external origins. Verifiable by grep.
2. **No remote script loading.** Strict CSP header set on the WebView document: `default-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'none'`. The `connect-src 'none'` is deliberate — Vision tab JS has *no* network egress at all; everything goes through the JS bridge.
3. **Keep the JS bridge narrow and typed.** Each JS-callable C# method has a defined argument schema. No generic `invoke(method, args)` dispatcher. No JSON blob passthrough. The bridge surface is part of the security boundary and gets reviewed as such.
4. **Validate all arguments in `VisionHandler.cs`.** Treat every argument from the JS bridge as untrusted input, exactly the way arguments from the C++ → bridge → C# path are treated. Same handler, same validation, regardless of which adapter called it. This means `VisionHandler.cs` is the single validation boundary — adapters do transport, the handler does validation.
5. **Keep Rhino-affecting work on the established dispatch path.** Any operation that touches Rhino state (capture, set view, restore named view) goes through `CMainThreadDispatcher` or its companion equivalent. The JS bridge does not get a fast-path that bypasses thread serialization.

These are not nice-to-haves — they map onto known WebView2 hardening checklists and onto the same dispatcher discipline that protects every other part of Rook. They land in the merge, not as a follow-up.

#### Image-generation routes are high-value, not media

Codex flagged this and it deserves a concrete control. The intuition that "image generation is just a media endpoint" leads to laxer auth than appropriate. When bearer-token auth lands per [`docs/2026-04-03-security-rollout-plan.md`](../Rook/docs/2026-04-03-security-rollout-plan.md):

- `/vision/generate`, `/vision/enhance-prompt`, `/vision/approve`, `/vision/delete` → **auth required**. These spend money (BYOK API calls) and mutate user state. Treat them like write routes, not media routes.
- `/vision/artifacts` (list), `/vision/artifacts/{id}` (read) → **discovery file ownership check + planned auth**. Read-only but still privileged.
- The Vision tab holds its bearer token the same way the chat panel holds its existing chat-server credentials.

**Don't put `/vision/generate` in the "harmless media" auth bucket** when the tier classification work happens. This is the kind of thing that's easy to get wrong by default.

#### The parity rule

Every meaningful Vision capability ships **both** as an MCP tool *and* as a tab UI affordance. Both consume the same `Services/Vision/*` code through the three-layer adapter pattern. This prevents the surface from drifting where one consumer gets new capabilities the other doesn't. The corollary: when you add a new MCP tool, ask "what's the tab UX for this?" and when you add a new tab affordance, ask "what's the MCP tool signature?" If either answer is "doesn't apply," that's fine — but it should be a deliberate choice, not an oversight.

### Three-layer architecture: domain / programmatic adapter / human adapter

Codex's framing, lifted directly. The doc's file layout already implements this pattern; naming it makes the discipline enforceable.

| Layer | Lives in | Responsibilities | What it does NOT do |
|---|---|---|---|
| **Domain** | `src/Rook/Services/Vision/*` | Capture, prompt enhancement, generation, depth, artifact storage. Pure business logic. | Knows nothing about HTTP, JS bridges, MCP tools, WebView, or transport in general. Doesn't validate inputs (callers do). |
| **Programmatic adapter** | `VisionHandler.cs` (bridge methods + JS bridge handlers) + `VisionHandler.cpp` (HTTP routes) + new MCP tool registrations in `server.py` | Argument validation. Transport (HTTP, JS bridge, MCP). Marshalling between transport types and domain types. | Doesn't contain business logic. If you find yourself writing a `for` loop here that isn't iteration over arguments, you're in the wrong layer. |
| **Human adapter** | `VisionTab.cs` + `Resources/Vision/*` | Eto.Forms tab integration, WebView lifecycle, HTML/JS/CSS rendering, user input collection, calling into the JS bridge, displaying results. | Doesn't contain business logic. Doesn't talk to providers. Doesn't manage artifacts directly — calls into the programmatic adapter, which calls into the domain. |

**The load-bearing rule:** adapters are pure plumbing. If the same logic appears in both `VisionHandler.cs` (programmatic adapter) and `VisionTab.cs` (human adapter), it belongs in `Services/Vision/*` (domain). If validation logic appears in `Services/Vision/*`, it belongs in `VisionHandler.cs`. The layer boundaries are not aspirational — they're enforced by the file location.

This separation pays off most when 2D→3D lands. The 2D→3D pipeline has the same three layers (Python domain in `mcp_server/src/rook/image_to_cad.py`, programmatic adapter via MCP tool registrations, human adapter via a chat-server-backed tab). Same pattern, different transport for the human adapter. Future visual subsystems that follow this layering will be predictable to navigate; ones that don't will accumulate cross-layer leaks that are expensive to refactor later.

### Jobs and artifacts — the human↔agent shared currency

The hardest question for "one engine, two clients" is: **how do the human and the agent reference the same things?** The human creates an image in the Vision tab; the agent needs a handle to that image to use it in a 2D→3D workflow. The agent generates a depth map; the human needs to see it in the gallery. Without a shared addressing scheme, the two surfaces drift apart and "shared backend" becomes "two parallel galleries that happen to use the same provider."

The answer is **artifacts addressed by stable IDs, stored on disk, readable from both C# and Python.**

#### Artifact model

| Field | Type | Notes |
|---|---|---|
| `id` | UUID v4 | Stable across sessions and restarts. Generated at creation time. |
| `type` | enum | `viewport_capture` / `generated_image` / `depth_map` / `prompt_json` / `enhanced_prompt`. The "approved concept" is not a separate type — it's a flag on a `generated_image`. |
| `parent_ids` | UUID[] | A `generated_image`'s parents are the `viewport_capture` it was conditioned on plus any reference image artifacts. Forms a DAG, not a tree (one capture can spawn many generations; one generation can have multiple ref-image parents). |
| `created_at` | ISO timestamp | |
| `created_by` | enum | `human` / `agent` / `pipeline`. Useful for filtering and for the parity rule (audit who's using what). |
| `document_context` | object | Rhino doc path, view name, session ID, optional object selection IDs. Lets the agent reason about which document the artifact is anchored to. |
| `blob_path` | string | Relative path to the actual image/JSON file under the artifact root. |
| `metadata` | object | Open dictionary. Provider name, model name, prompt text, generation parameters, dimensions, etc. |
| `flags` | object | `approved: bool`, `archived: bool`, future flags. The `approve` / `consume_approved` MCP pair reads/writes this. |

#### Storage shape

```
%APPDATA%\Rook\artifacts\vision\
├── artifacts.index.json          # fast enumeration, append-only updates
├── 2026-04-08\
│   ├── {uuid}.png                # blob
│   ├── {uuid}.json               # sidecar with full artifact metadata
│   ├── {uuid}.png
│   └── {uuid}.json
└── 2026-04-09\
    └── ...
```

- **Day-bucketed directories** prevent any single directory from growing to tens of thousands of files.
- **JSON sidecars** mean the artifact metadata is on disk alongside the blob, not in a database. Both C# and Python can read them with no schema migration.
- **`artifacts.index.json`** is the fast-enumeration cache (it's a denormalized projection of the sidecars). If it gets out of sync, it can be rebuilt by walking the day directories. Rebuild on startup if a checksum mismatches.
- **File locking** for index updates (Windows file locks via `FileShare.None` during write). Both C# and Python honor it. Concurrent writes from agent + human is a real scenario and the file format has to support it.

This file-system contract is the load-bearing decision. A C# in-memory `Dictionary<Guid, Artifact>` would be simpler but wouldn't be reachable from Python — and the moment 2D→3D ships, the agent path is Python, the artifact path has to cross processes, and an in-memory store would force a refactor.

#### MCP tool surface for artifacts

| Tool | Returns | Purpose |
|---|---|---|
| `rhino_render_view(prompt, view?, refs?)` | `{artifact_id, ...}` | Capture + generate. Returns the artifact ID, NOT the inline base64. The agent fetches the blob via `rhino_vision_get_artifact` if it actually needs the bytes. Most agent code only needs the ID. |
| `rhino_vision_artifacts(filter?)` | `[{id, type, created_at, ...}, ...]` | List/query. Filter by type, document, session, approved status, created_by. |
| `rhino_vision_get_artifact(artifact_id, include_blob?)` | `{...full artifact..., blob_base64?}` | Fetch one. `include_blob: false` by default to keep agent context lean — only request the bytes when actually needed. |
| `rhino_vision_approve(artifact_id)` | `{success: true}` | Sets `flags.approved = true`. Closes the human→agent handoff: human approves an image in the panel, this tool flips the flag, the agent's next call to `consume_approved` finds it. |
| `rhino_vision_consume_approved(filter?)` | `{artifact_id, ...} \| null` | The agent's entry point for "give me the most recent approved concept." Optionally scoped by document/session. This is the mechanism that makes the seven-step 2D→3D handoff work without verbal/manual coordination. |

The Vision tab calls the same handlers via the JS bridge. When the user clicks "Approve" on an image in the gallery, the panel calls into `VisionHandler.SetApproved(artifact_id)`. When the agent calls `rhino_vision_consume_approved`, it sees the same flag flipped. There is no separate "panel state" or "agent state" — there is one artifact store, two readers/writers.

#### Why this matters for 2D→3D

The 2D→3D workflow's seven-step human↔agent flow (per Codex) only works if the two parties share artifact handles:

1. Human captures viewport / picks refs in Vision tab → creates `viewport_capture` artifact
2. Human and/or agent generates options → creates `generated_image` artifacts with `parent_ids = [viewport_capture_id]`
3. Human approves one → `flags.approved = true` on that `generated_image`
4. Agent calls `rhino_vision_consume_approved()` → gets the artifact ID
5. Agent runs 2D→3D pipeline against that ID → eventually creates new artifacts (depth map, mesh preview, NURBS surfaces)
6. Human reviews geometry in Rhino (via the existing `rhino_objects` surfaces, not Vision)
7. Repeat

Without artifact IDs as the lingua franca, step 4 doesn't work. The agent would have no addressable handle on what the human picked. The seven-step flow degenerates into "human screenshots the panel and pastes the image into a chat with the agent," which is exactly the disconnected ArchSynth-style workflow Rook is supposed to undercut. **The artifact model is the mechanism that earns the strategic claim.**

This sub-doc belongs more to image-to-CAD's plan than to Vision's, but the artifact infrastructure has to ship with Vision because it's the prerequisite. Cross-referenced from here for completeness.

---

## MCP tool surface (proposed)

New tools in `mcp_server/src/rook/server.py`. **All generation tools return `artifact_id` rather than inline base64**, per the artifact model above. Inline blobs are fetched on demand via `rhino_vision_get_artifact` so agent context stays lean.

| Tool | Returns | Purpose |
|---|---|---|
| `rhino_render_view(prompt, view?, refs?, model?)` | `{artifact_id, type: "generated_image", parent_ids: [capture_id], ...}` | Capture viewport (Tier 3 path, optionally with raytraced stabilization) → send to Gemini → store as artifact → return ID. |
| `rhino_enhance_prompt(prompt)` | `{artifact_id, type: "enhanced_prompt", ...}` | Text-only Gemini call to upgrade simple prompt → structured JSON. Stored as artifact so the agent can reference and re-use. |
| `rhino_capture_depth(view?)` | `{artifact_id, type: "depth_map", ...}` | Generate a depth pass for ControlNet-style conditioning. Stored as artifact. |
| `rhino_vision_artifacts(filter?)` | `[{id, type, created_at, created_by, flags, ...}, ...]` | List/query artifacts. Filter by type, document, session, approved status, created_by, time range. |
| `rhino_vision_get_artifact(artifact_id, include_blob?)` | `{...full artifact..., blob_base64?}` | Fetch one. `include_blob: false` by default. |
| `rhino_vision_approve(artifact_id)` | `{success: true}` | Sets `flags.approved = true`. Closes the human→agent handoff. |
| `rhino_vision_consume_approved(filter?)` | `{artifact_id, ...} \| null` | Agent entry point: "give me the most recent approved concept." Scoped by document/session if provided. The mechanism that makes the 2D→3D handoff work. |
| `rhino_vision_delete_artifact(artifact_id)` | `{success: true}` | Cleanup. Auth required when token auth lands. |

These compose with existing Rook tools: agents can `scene_graph` → identify objects → `rhino_select_by_type` → `rhino_render_view` → `rhino_vision_approve` → `rhino_vision_consume_approved` → 2D→3D pipeline → `rhino_import` in one session.

The Vision tab calls the same `VisionHandler.cs` methods via the JS bridge — same validation, same artifact store, same threading. Agent and human can hand off to each other through the artifact store without either side knowing the other exists.

---

## Open questions

### 1. Sequencing relative to public release

Per memory, Rook is at staging commit `99a0e9e5` with two Codex review rounds applied, not yet pushed. **The vision merge should land *after* the public push, not tangled with it.** It's non-trivial and would re-open review surface that's already cleared.

### 2. RhinoCommon capability audit (the right reference)

[`docs/plans/2026-03-21-rhinocommon-capability-audit.md`](../Rook/docs/plans/2026-03-21-rhinocommon-capability-audit.md) is the source of truth for "which side owns capability X" across the full RhinoCommon surface. The 2026-03-08 audit is block-only and explicitly delegates broader expansion to the 2026-03-21 doc. Read 2026-03-21 before the merge — it already names view capture as an expansion candidate, defines the safety-tier framework that justifies a Tier 2 → Tier 3 migration for `_-ViewCaptureToFile`, and is where any future bridge-registrar rename decision will land.

### 3. LiteLLM multipart-response spike

Cheap, decides v2 routing, doesn't block v1. Need to actually call `litellm.completion(model="gemini/gemini-2.5-flash-image", messages=[...with image parts...])` and inspect the response for image-part round-trip fidelity.

### 4. Human visual surface (settled in v2.2)

**Rehouse, not drop.** SA_Banana's WebUI assets become the WebView resources backing a new `VisionTab.cs` in Rook's existing chat panel. Pattern A transport (in-process JS bridge to `VisionHandler.cs`, no HTTP). MCP tools are the parallel surface for agents — both consume the same `Services/Vision/*` domain code through the three-layer adapter pattern. See "Human visual surface — Pattern A tab in the chat panel" architectural section above for the full design.

### 5. Settings root must be introduced, not reused

Confirmed: Rook has no persistent settings root in trunk. [`src/Rook/RookPaths.cs:9`](../Rook/src/Rook/RookPaths.cs#L9) only resolves `DiscoveryFolder` under `%TEMP%/rook` for instance discovery. The Vision merge needs to **introduce** a persistent abstraction (likely `%APPDATA%\Rook\settings.json` with a sibling helper in `RookPaths.cs` or a new `RookSettingsStore.cs`). The schema should be designed for Vision but with namespacing (`vision:`, `chat:`, future modules) so the next module that needs persistent state doesn't have to redo this work.

---

## Decision summary

| Question | Answer |
|---|---|
| Architecture shape | Managed module inside Rook + three-layer adapter pattern (domain / programmatic / human) |
| Public plugin surface | Single — `RookNative` only. The internal C# companion `.rhp` continues to exist and is where Vision lands. |
| HTTP surface | Single server (`RookNative`), no second server. Vision tab uses Pattern A (in-process JS bridge), no HTTP. |
| What to port | ~1,000 LOC of services + the WebUI assets, not the full plugin |
| What to delete | HTTP shell, plugin scaffolding (~800 LOC). **WebUI is rehoused, not deleted.** |
| What to skip | Viewport route, named-view routes (already exist) |
| Bridge | Existing `NativeGhBridgeRegistrar` + `// Vision` section, rename later |
| Code ownership | Folder (`src/Rook/Services/Vision/`), not separate `.csproj` |
| Provider layer (v1) | C# `GeminiClient`, BYOK, direct |
| Provider layer (v2) | LiteLLM via chat completion, pending multipart spike |
| Sequencing | After public release lands |
| **Human visual surface** | **`VisionTab.cs` in existing chat panel — Eto.Forms WebView, Pattern A (in-process JS bridge to `VisionHandler.cs`)** |
| **Human↔agent shared currency** | **Artifacts addressed by stable IDs, on-disk JSON sidecars under `%APPDATA%\Rook\artifacts\vision\`, readable from both C# and Python** |
| **Validation boundary** | **`VisionHandler.cs` — same handler, same validation, regardless of whether the call came from JS bridge or C++ → bridge** |
| **WebView security** | **Local-only assets, strict CSP `connect-src 'none'`, narrow typed JS bridge, dispatcher discipline preserved** |
| **Auth tier for `/vision/*`** | **Generation/approve/delete = auth required (write routes, BYOK money). Read = discovery file ownership + planned auth.** |
| **Parity rule** | **Every meaningful Vision capability ships as both an MCP tool AND a tab affordance, both consuming `Services/Vision/*`** |
| Settings | New persistent root must be introduced (none exists in trunk) |
| Installer | Add uninstall step for standalone `4C23EE05-…` plugin |

---

## Next steps

1. **Wait for public release to land** (commit `99a0e9e5` → push).
2. **Re-read [`docs/plans/2026-03-21-rhinocommon-capability-audit.md`](../Rook/docs/plans/2026-03-21-rhinocommon-capability-audit.md)** in full to position both (a) the Tier 2 → Tier 3 viewport-capture migration and (b) the eventual bridge-registrar rename. The 2026-03-08 doc is block-only and not the right anchor.
3. **Run the LiteLLM multipart-response spike** (30 min, cheap, informs v2).
4. **Investigate chat-server hardening status** in [`mcp_server/src/rook/agent/chat/server.py`](../Rook/mcp_server/src/rook/agent/chat/server.py). Compare against the native-server hardening pass from [`docs/2026-04-03-security-rollout-plan.md`](../Rook/docs/2026-04-03-security-rollout-plan.md). **This does not block Vision (Pattern A, no HTTP)** but it *does* block image-to-CAD shipping (Pattern B requires the chat server). Likely its own plan doc, not a paragraph here.
5. **Design the artifact store file format** — JSON sidecar schema, index file structure, day-bucketed directory layout, file-locking strategy for concurrent C# + Python writes, rebuild-from-sidecars recovery path. This is the prerequisite for both Vision and 2D→3D handoffs working as designed.
6. **Classify Vision routes into auth tiers** before the merge — `generate`, `approve`, `delete` go in the auth-required tier; `artifacts` list/read are discovery-file-ownership-checked. Document this in the route inventory so the next person setting up bearer tokens doesn't put image generation in the "harmless media" bucket by default.
7. **Design the WebView2 hardening for `VisionTab.cs`** — CSP header values, JS bridge method registration pattern, argument schema enforcement, asset loading strategy. The Vision security checklist above is the spec; this step turns it into concrete code.
8. **Draft the route inventory and exact MCP tool signatures** as a follow-up plan doc, ready to execute once the release ships.
9. **Design the persistent settings root** (new file under `src/Rook/`, likely `RookSettingsStore.cs` resolving to `%APPDATA%\Rook\settings.json`) with namespaced sections so future modules can reuse it. This is net-new infrastructure, not a configuration tweak. Ships alongside the artifact store since they share the `%APPDATA%\Rook\` root.
10. **Specify the installer uninstall mechanism** for the standalone `4C23EE05-6FF3-47F6-ACB4-475968E37CDE` plugin before that line graduates from planning to implementation. The plugin GUID is real, but the actual uninstall step (Inno Setup `[UninstallDelete]`? Detect-and-warn? Migrate settings then remove?) is unspecified.

---

## Addendum: Video Generation (v3 — 2026-04-13)

> **v3.1 — 2026-04-25:** The four open architectural questions raised in this addendum are now **locked**. See [`2026-04-22-v3-video-decisions.md`](2026-04-22-v3-video-decisions.md) for the binding pre-implementation contract (D1–D5, route paths, `VideoJobLedger` shape, submit-time payload constraints, sensitivities, and the PR-0 → PR-V1a/V1b → PR-V2 → PR-V3/V4 roadmap). The original question framing below is retained for historical context; do not code against the four "Pattern A/B options" or the "multi-blob vs linked artifacts" debate — both are resolved in v3.1.

### What changed since v2.2

SA_Banana now ships a complete **video generation pipeline** alongside its existing image generation. This was added in a focused sprint immediately after the v2.2 lock of this plan. The video pipeline is production-quality and tested end-to-end across five Veo model variants.

**New services in SA_Banana (not present when v2.2 was written):**

| Service | LOC | Responsibility |
|---|---|---|
| `VeoClient.cs` | ~220 | HTTP client for Google Veo API. Fundamentally different shape from GeminiClient: Vertex AI prediction endpoints, long-running operation names, poll-until-done semantics, multi-shape response parsing. |
| `VideoJobManager.cs` | ~280 | Async job queue. SemaphoreSlim(2) concurrency, per-job linked CancellationTokenSource (chained to plugin shutdown), state machine (Queued → Submitting → Polling → Downloading → Saving → Complete/Error), 10s poll interval. |
| `VideoCapabilities.cs` | ~350 | Per-model constraint matrix. 5 Veo models × (resolution, duration, mode, aspect ratio, personGeneration, reference image limits, cost/sec) with a `Validate()` method that pre-checks all constraints before any API call. |
| `MediaStorage.cs` | ~180 | Unified disk I/O replacing the old `ImageStorage`. Videos under `Videos/` subfolder with required JSON sidecars, frames under `Videos/frames/`, gallery scanner knows the difference. |
| `VideoHandler.cs` | ~200 | HTTP handler (6 endpoints). Will be deleted during integration (same as the image handlers), but the *logic* it wraps is the thing that needs a new home. |
| `VideoGenerationRequest.cs` / `VideoJob.cs` / updated `MediaMetadata.cs` | ~150 | DTOs for video jobs, request payloads, and unified media metadata (images + videos). |

**Net change to integration scope:** ~1,380 LOC of new video services on top of the ~1,370 LOC of image services already accounted for. The merge is now ~2,750 LOC of services, not ~1,000. The "delete" side stays the same (HTTP shell, plugin scaffolding), but there is significantly more domain logic to place.

### The integration problem video creates

The v2.2 plan was written for a world where Vision = synchronous image generation. Every architectural decision reflects that assumption:

1. **Pattern A was chosen because Vision work is "C#-bound and short-running."** Image generation via Gemini is a single HTTP call (~3–8s). Pattern A (in-process JS bridge → C# handler → domain service) is natural for this. Video generation via Veo is a 30s–6min async pipeline with polling, progress reporting, and concurrent job management. This is the *exact* scenario the plan reserved for Pattern B.

2. **The three-layer architecture assumed synchronous domain methods.** `GeminiClient.GenerateImageAsync()` returns a result. `VideoJobManager.Enqueue()` returns a job ID and then runs in the background for minutes. The domain layer needs to support fire-and-forget with progress callbacks, not just request/response.

3. **The artifact model assumed single-output artifacts.** A video generation produces: an MP4 (primary), a poster frame (thumbnail), optionally 1–2 input frames (start/end for i2v/interp), and a JSON sidecar. The `blob_path` field in the artifact schema needs to become a multi-file concept, or video artifacts need multiple linked artifact records.

4. **The LiteLLM deferral assumed the only provider API was Gemini's multimodal-chat shape.** Veo is a completely different API shape (Vertex AI predictions with long-running operations). A second provider for video (CogVideoX via Replicate, Wan2.1, Kling) would be a third shape. The "keep C# in v1, move to LiteLLM in v2" framing needs to account for whether LiteLLM handles async job APIs at all.

5. **The settings schema assumed image-only defaults.** Video adds: `VideoModel`, `VideoResolution`, `VideoDurationSeconds`, `VideoAspectRatio`, `VideoPersonGeneration`. Plus the capability matrix itself needs to be queryable (the tab UI uses it for client-side form gating).

6. **Cost was not a first-class concern for image generation.** Gemini image gen costs fractions of a cent. Veo 3.1 standard 4K costs $3.20 per 8s clip. A careless wire-wiggle in GH with five clips is $16+. Cost estimation, confirmation gates, and dry-run modes are load-bearing for video in a way they never were for images.

### Per-asset disposition: video additions

| SA_Banana asset | Verdict | Why |
|---|---|---|
| `VeoClient.cs` | **Keep — abstract for provider switching** | HTTP client for Veo. The API shape (start → poll → download) is different from Gemini but will be shared with future video providers (CogVideoX, Wan2.1). Design the interface for the common pattern (submit job → poll status → retrieve result), not the Veo-specific wire format. |
| `VideoJobManager.cs` | **Keep — redesign for Rook's threading model** | The 2-concurrent queue, linked cancellation, and shutdown coordination are correct. But the current implementation owns its own `SemaphoreSlim` and background tasks. Inside Rook, this must coordinate with the existing `CMainThreadDispatcher` for any Rhino-touching work and respect the companion plugin's lifecycle. The state machine shape is right; the hosting model needs rework. |
| `VideoCapabilities.cs` | **Keep as-is** | Pure data + validation, no dependencies. Lifts directly into `Services/Vision/`. The tab and MCP tools both need it for pre-submission validation and cost estimation. |
| `MediaStorage.cs` | **Keep — reshape into ArtifactStore** | The disk layout (Videos/, frames/, sidecars) is correct. But v2.2 already specified an `ArtifactStore.cs` with UUID-based addressing and day-bucketed directories. Video artifacts need to map into that scheme rather than maintaining a parallel storage layout. See "Artifact model extension" below. |
| `VideoHandler.cs` | **Delete** | Replaced by C++ routes + bridge callbacks, same as the image handlers. |
| `VideoGenerationRequest.cs` / `VideoJob.cs` | **Keep — fold into domain models** | The request/response DTOs and job state machine are domain concepts that belong in `Services/Vision/`. |

### Artifact model extension for video

The v2.2 artifact model needs video-specific fields. Two options:

**(a) Multi-blob artifacts.** Add a `blobs` array to the artifact record:

```json
{
  "id": "uuid",
  "type": "generated_video",
  "blobs": {
    "primary": "2026-04-13/uuid.mp4",
    "poster": "2026-04-13/uuid_poster.jpg",
    "start_frame": "2026-04-13/uuid_start.jpg",
    "end_frame": "2026-04-13/uuid_end.jpg"
  },
  "metadata": {
    "model": "veo-3.1-lite-generate-preview",
    "resolution": "720p",
    "duration_seconds": 8,
    "mode": "i2v",
    "cost_usd": 0.40,
    "video_capabilities_snapshot": { ... }
  }
}
```

**(b) Linked artifacts.** Keep `blob_path` singular. A video generation creates 2–4 artifacts linked by `parent_ids`:

```
generated_video (uuid-1)  →  blob: uuid-1.mp4
  ├── poster_frame (uuid-2)  →  blob: uuid-2.jpg, parent_ids: [uuid-1]
  ├── start_frame (uuid-3)   →  blob: uuid-3.jpg, parent_ids: [uuid-1]
  └── end_frame (uuid-4)     →  blob: uuid-4.jpg, parent_ids: [uuid-1]
```

**Trade-off:** (a) is simpler for the common case (fetch a video, get all its parts). (b) is more composable — a `start_frame` artifact that's also a `viewport_capture` can have two parents, which is the natural shape for the GH NLE workflow where frames are first-class tokens. **This is a design question for Codex review.**

### The Pattern A / B question — posed, not resolved

This is the central architectural decision the v3 addendum introduces. The v2.2 plan placed all of Vision into Pattern A. Video breaks that assumption. There are four credible options, each with real trade-offs.

#### Option 1: Vision stays Pattern A. Video is async-within-C#.

Keep the v2.2 architecture exactly as designed. Video's async nature is handled entirely within C# using background tasks + `ExpireSolution()` callbacks for GH and WebSocket-style push (or polling from JS) for the tab.

```
VisionTab.cs (WebView)
    │ JS bridge call: startVideoGeneration(request)
    ▼
VisionHandler.cs
    │ calls domain layer
    ▼
Services/Vision/VideoJobManager.cs
    │ background Task, SemaphoreSlim(2)
    │ polls Veo via VeoClient.cs
    ▼
VisionHandler.cs  ← callback when job completes
    │ pushes status update to WebView via JS bridge
    ▼
VisionTab.cs (WebView)  ← receives update, refreshes UI
```

**Arguments for:**
- Minimal architectural change from v2.2. The plan stays coherent.
- C# async/await is a perfectly good concurrency model for this workload.
- No Python involvement means no cross-process coordination for video.
- The GH NLE components already assume C# (they're a `.gha` assembly).
- SA_Banana's existing video code is already C# and already works.

**Arguments against:**
- The JS bridge in Eto.Forms WebView2 is fundamentally request/response. Pushing progress updates *from* C# *to* JS requires either (a) polling from JS on a timer, which is ugly but works, or (b) a mechanism to invoke JS from C# (`EvaluateJavaScriptAsync`), which Eto supports but which makes the bridge bidirectional — the plan's "narrow typed JS bridge" principle gets more complex.
- Adding a second provider (CogVideoX via Replicate) means a second C# HTTP client. The "keep C# in v1, move to LiteLLM in v2" deferral gets heavier — v2 would need to rip out two C# clients, not one.
- Video job state (queue, progress, errors) needs to survive across tab close/reopen. C# in-memory state is ephemeral; the artifact store on disk becomes the source of truth, but the job manager also needs to be a singleton that outlives any individual tab instance.

#### Option 2: Video is Pattern B. Image stays Pattern A. Hybrid tab.

Image generation stays Pattern A (in-process JS bridge → C# → Gemini). Video generation moves to Pattern B (WebView `fetch()` → chat server → Python module → Veo).

```
VisionTab.cs (WebView)
    │
    ├── [Image gen] JS bridge → VisionHandler.cs → GeminiClient.cs
    │
    └── [Video gen] fetch('https://app.rook.invalid/api/vision/video/...')
                        │
                        ▼
                   Chat server (aiohttp)
                        │
                        ▼
                   mcp_server/src/rook/vision/video.py
                        │ VeoClient (Python), JobManager (Python)
                        ▼
                   Artifact store on disk
```

**Arguments for:**
- Respects the plan's own rule: "prefer Pattern A unless you genuinely need an async service boundary." Video genuinely needs one.
- Python's async ecosystem (aiohttp, asyncio) is a natural fit for poll-until-done job management.
- Opens the door to LiteLLM routing for video providers from day one — no "rip out C# client later" migration.
- The chat server already exists and has its own port/discovery. Video endpoints are a natural addition.
- Progress streaming via SSE or WebSocket from the chat server is a solved problem.

**Arguments against:**
- Two transport paths in the same tab. The JS code has to know which backend to talk to for which operation. Complexity lands in the human adapter layer, which the plan says should be "pure plumbing."
- Requires porting VeoClient + VideoJobManager + VideoCapabilities from C# to Python. ~850 LOC of tested, working code gets rewritten. Risk of introducing bugs in the port.
- The GH NLE components (C# `.gha`) now need to talk to the Python chat server for video rendering. They can't use the JS bridge — they're not in a WebView. They'd need direct HTTP calls to the chat server, which means the `.gha` assembly has a runtime dependency on the chat server being up.
- Chat server hardening is still an open item (v2.2 next-step #4). Video would be blocked on that.

#### Option 3: Everything moves to Pattern B. Unified transport.

Both image and video generation go through the chat server. The C# domain layer keeps only RhinoCommon-bound work (viewport capture, depth map). All provider calls (Gemini, Veo, future providers) live in Python.

```
VisionTab.cs (WebView)
    │
    ├── [Viewport capture] JS bridge → VisionHandler.cs → ViewportCaptureBitmap.cs
    │                                                          (RhinoCommon, must stay C#)
    │
    └── [Everything else] fetch('https://app.rook.invalid/api/vision/...')
                              │
                              ▼
                         Chat server (aiohttp)
                              │
                              ▼
                         mcp_server/src/rook/vision/
                              ├── gemini_client.py
                              ├── veo_client.py
                              ├── job_manager.py
                              ├── capabilities.py
                              └── prompt_enhancer.py
```

**Arguments for:**
- Simplest mental model. One transport path for all generation work. Tab JS code doesn't need to know which backend handles what.
- All provider clients live in Python. LiteLLM routing is natural from day one for any provider.
- The GH NLE components talk to the same chat server endpoint as the tab. Uniform API surface.
- Future providers (CogVideoX, Wan2.1, fal.ai, Replicate) are Python packages. No C# wrapper needed.
- Progress streaming, job queuing, and cost estimation all live in one place.

**Arguments against:**
- Contradicts v2.2's explicit decision: "Vision uses Pattern A." This is a plan reversal, not an extension.
- Requires porting all of GeminiClient + PromptEnhancer + VeoClient + VideoJobManager to Python. ~1,600 LOC rewrite.
- Adds a network hop for image generation that v2.2 deliberately avoided. Synchronous Gemini calls go through `fetch()` → chat server → Python → Gemini API → back. Latency increases by the round-trip to the chat server (~2–5ms local, but still).
- Blocked on chat server hardening.
- Viewport capture and depth map generation *must* stay in C# (RhinoCommon). So even in "everything Pattern B," the tab still has two transport paths for capture vs. generation. The hybrid doesn't fully go away.

#### Option 4: Pattern A with a job-status sideband.

Vision stays Pattern A. Video job management stays in C#. But instead of pushing progress through the JS bridge, the job manager writes status to the artifact store on disk, and both the tab and GH components poll the artifact store for status updates.

```
VisionTab.cs (WebView)
    │ JS bridge: submitVideoJob(request)  → returns jobId immediately
    │ JS timer:  pollJobStatus(jobId)     → reads from artifact store via bridge
    ▼
VisionHandler.cs
    │
    ▼
Services/Vision/VideoJobManager.cs
    │ background Tasks
    │ writes progress to ArtifactStore on disk
    ▼
ArtifactStore.cs  ← source of truth for job state
    ▲
    │ also polled by:
    ├── GH Render sink component (C#, same process)
    └── MCP tools (Python, reads JSON sidecars)
```

**Arguments for:**
- No Python port needed. All video code stays in C# where it already works.
- The artifact store is already the "lingua franca" from v2.2. Making it the source of truth for in-flight job state is a natural extension.
- GH components can poll the same artifact store without needing the chat server.
- MCP tools (Python) can read job status from the same JSON sidecars without any new HTTP surface.
- Progress, cancellation, and cost tracking are all just fields on the artifact record.
- No chat server dependency. Not blocked on hardening.

**Arguments against:**
- File-system polling for real-time progress is coarse. 1s poll interval means 1s worst-case latency on status updates. Acceptable for video (jobs take 30s–6min), but feels wrong architecturally.
- The artifact store's file-locking strategy (already an open item from v2.2) becomes load-bearing for concurrent writes from the job manager + concurrent reads from the tab + concurrent reads from GH components + concurrent reads from MCP tools. Four concurrent accessors on the same JSON files is a real contention scenario.
- Job state on disk means job state survives plugin restart — which is either a feature (resume interrupted jobs) or a bug (stale "Submitting" records from a crash), depending on how recovery is designed.
- The `ArtifactStore` grows from a passive index into an active state machine. That's a scope expansion for what was supposed to be a "stable UUID, JSON sidecar, day-bucketed" storage layer.

### What Codex should weigh in on

This addendum deliberately does **not** resolve the Pattern A/B question. The four options represent genuinely different trade-offs, and converging prematurely would lose information. Specifically, Codex review should address:

1. **Which option best preserves the plan's existing architectural integrity while accommodating video's async nature?** The plan has been through three rounds of review and has earned trust. How much of it should be disturbed?

2. **Is the C#-to-Python port cost justified?** Options 2 and 3 require rewriting ~850–1,600 LOC of tested C# into Python. The code works. The risk is bugs in the port. Is "future provider flexibility via LiteLLM" worth the rewrite cost and risk, or is that a v2 concern?

3. **How should GH NLE components access video services?** The GH NLE proposal (`2026-04-09-grasshopper-video-nle.md`) assumes the `.gha` talks to SA_Banana's HTTP server on localhost. After integration, that server is gone. The GH components need *some* programmatic path to video generation. Options:
   - (a) C# in-process (Options 1, 4): GH `.gha` references `Rook.dll` directly, calls `VideoJobManager` in-process. Tight coupling but zero network.
   - (b) HTTP to native server (all options): C++ routes proxy to C# via bridge, GH `.gha` calls `localhost:{port}/vision/video/...`. Decoupled but adds the native server as a dependency.
   - (c) HTTP to chat server (Options 2, 3): GH `.gha` calls the Python chat server directly. Decoupled but adds the chat server as a dependency.

4. **Does the artifact model use multi-blob records (option a) or linked artifacts (option b)?** The GH NLE workflow strongly favors linked artifacts (frames are first-class tokens). The human tab workflow favors multi-blob (fetch one record, get the whole video package). Which consumer's ergonomics should win?

5. **Should video job state live in-memory, on-disk, or both?** In-memory is fast but ephemeral. On-disk survives restarts but introduces file-locking contention. A hybrid (in-memory primary, disk-persisted checkpoints) is the obvious answer but also the most complex.

6. **Is cost estimation and gating a domain concern or an adapter concern?** The v2.2 plan says domain = "pure business logic" and adapters = "transport + validation." Cost estimation feels like business logic (it depends on the capability matrix, the model, the resolution). But the confirmation gate ("this will cost $3.20, proceed?") is a UI concern. Where does the boundary fall?

7. **Does video change the LiteLLM timeline?** The v2.2 plan deferred LiteLLM to v2, contingent on (a) wanting a second provider and (b) the multipart-response spike. Video introduces a second API shape (Vertex AI predictions ≠ multimodal chat) and makes "wanting a second provider" concrete now rather than hypothetical. Does this pull the LiteLLM migration forward, or does it make the migration harder (LiteLLM may not handle Veo-style job APIs at all)?

### Updated decision summary (v3 additions only)

| Question | v2.2 Answer | v3 Status |
|---|---|---|
| Pattern A vs B for Vision | Pattern A (in-process JS bridge) | **Reopened.** Four options posed for Codex review. Video's async nature may require Pattern B for video endpoints, or an async-within-C# approach, or a disk-based sideband. |
| Services to port | ~1,000 LOC (image only) | **~2,750 LOC** (image + video). Six new service files. |
| Provider layer shape | Gemini multimodal-chat only | **Two shapes:** Gemini chat + Veo long-running operations. Future providers add more shapes. |
| Artifact model | Single blob_path per artifact | **Reopened.** Video needs multi-file artifacts. Two options posed. |
| Cost concern | Not first-class | **First-class for video.** Pre-cook estimation, confirmation gates, dry-run mode are load-bearing. |
| GH NLE integration | Not addressed (plan predates NLE proposal) | **New question.** How do GH components access video services after SA_Banana's HTTP server is gone? |
| Settings schema | Image defaults only | **Extended.** Five new video-specific settings fields + capability matrix queryability. |
| LiteLLM timeline | Deferred to v2 | **Reopened.** Video makes "second provider" concrete now, not hypothetical. |

### Updated next steps (v3 additions)

11. **Send this addendum to Codex** for review. The seven questions above are the review surface. Request explicit recommendation on the Pattern A/B question — that decision cascades into everything else.
12. **Inventory the GH NLE doc's assumptions** against each Pattern option. The NLE proposal (`2026-04-09-grasshopper-video-nle.md`) assumes `POST /api/video/generate` to a localhost HTTP server. After integration, that endpoint either lives on the C++ native server (Options 1, 2, 4) or the Python chat server (Option 3) — or the GH components call the C# domain layer directly (Option 1a, 4a). Map each NLE component to its post-integration API surface.
13. **Spike: LiteLLM + Veo-style job APIs.** Does LiteLLM (or any Python model-routing library) handle the submit → poll → download pattern for video generation? If yes, Options 2 and 3 become significantly more attractive. If no, video providers need custom clients regardless of language — weakening the "Python for provider flexibility" argument.
14. **Spike: Eto.Forms WebView2 bidirectional bridge.** Can `WebView2.CoreWebView2.ExecuteScriptAsync()` push progress updates from C# to JS reliably in the Eto.Forms wrapper? If yes, Option 1 becomes practical for real-time progress. If no, the tab needs polling or SSE, which points toward Options 2/3.
15. **Design the video artifact lifecycle.** Regardless of which Pattern option wins, video artifacts have a lifecycle that image artifacts don't: Queued → In-Progress → Complete/Error. Define how this maps to the artifact store — is it a separate `jobs` index alongside `artifacts.index.json`, or are in-flight jobs just artifacts with a `status` field?

---

## Changelog

- **2026-04-13 v3** — Video addendum. SA_Banana now ships a complete video generation pipeline (Veo 3.x, 5 models, async job queue, cost estimation). Reopened the Pattern A/B question with four credible options posed for Codex review. Added per-asset disposition for six new video services (~1,380 LOC). Posed the artifact model extension question (multi-blob vs. linked artifacts). Added seven questions for Codex and five new next steps. Status changed from "Locked" to "Reopened / v3." The v2.2 image integration plan is not invalidated — video is additive — but the transport and async architecture decisions need to be revisited before implementation begins.
- **2026-04-08 v2.2** — Human visual surface, three-layer architecture, and artifact model added (after Codex round 3 + observation of `src/Rook/UI/Chat/`):
  - **Reframed "drop the WebUI" as "rehouse as a Vision tab in the existing chat panel."** Observing [`ChatTab.cs`](../Rook/src/Rook/UI/Chat/ChatTab.cs) revealed the chat panel is already an Eto.Forms tabbed WebView surface — adding `VisionTab.cs` is a known pattern, not new framework work. SA_Banana's HTML/JS/CSS gets lifted into `src/Rook/UI/Chat/Resources/Vision/` with the transport layer rewritten from `fetch('/api/...')` to JS bridge calls. The visual experience is preserved.
  - **Added "Pattern A vs Pattern B" naming** for in-process tabs (JS bridge to C#) vs HTTP tabs (chat server to Python). Vision is Pattern A; image-to-CAD will be Pattern B when it ships. Rule: prefer Pattern A unless you genuinely need an async service boundary.
  - **Added the "no HTTP ≠ free security" sub-section** with five concrete WebView2 hardening controls (Codex round 3): local-only assets, strict CSP with `connect-src 'none'`, narrow typed JS bridge, all argument validation in `VisionHandler.cs`, dispatcher discipline preserved.
  - **Added "image-generation routes are high-value, not media"** — explicit auth tier classification so `/vision/generate` doesn't land in the harmless-media bucket by default when bearer-token auth ships.
  - **Added the parity rule** — every meaningful Vision capability ships as both an MCP tool *and* a tab affordance, both consuming `Services/Vision/*`.
  - **Named the three-layer architecture** (domain / programmatic adapter / human adapter) explicitly. The file layout already implemented this; naming it makes the discipline enforceable. Added the load-bearing rule: adapters are pure plumbing; if logic appears in two adapters, it belongs in the domain.
  - **Added the artifacts and jobs section.** Stable UUID artifact IDs, on-disk JSON sidecars under `%APPDATA%\Rook\artifacts\vision\`, day-bucketed directories, file-locking for concurrent C# + Python writes. This is the load-bearing mechanism that makes "one engine, two clients" actually work — without artifact IDs as a lingua franca, the human and agent surfaces drift apart and the seven-step 2D→3D handoff degenerates into screenshot-and-paste.
  - **Updated the MCP tool surface table** — generation tools now return `artifact_id` instead of inline base64. Added `rhino_vision_artifacts`, `rhino_vision_get_artifact`, `rhino_vision_approve`, `rhino_vision_consume_approved`, `rhino_vision_delete_artifact`. The `approve` / `consume_approved` pair is the human↔agent handoff mechanism.
  - **Updated the file layout** with `VisionTab.cs`, `Resources/Vision/`, `ArtifactStore.cs`. Added a naming note about renaming `src/Rook/UI/Chat/` → `src/Rook/UI/Tabs/` as a separate mechanical PR.
  - **Updated the per-asset table:** `WebUI/*` row flipped from "Delete" to "Rehouse, don't delete" with the transport-layer rewrite called out.
  - **Updated the decision summary** with seven new rows covering human visual surface, artifact model, validation boundary, WebView security, auth tiers, and the parity rule.
  - **Added four new next-steps items** — chat-server hardening investigation, artifact store file format design, Vision route auth tier classification, WebView2 hardening design.
  - **Added two new related-doc references** — `2026-04-03-security-rollout-plan.md` (security model context) and `ChatTab.cs` (the existing tab base class Vision will extend).
- **2026-04-08 v2.1** — Self-review coherence pass after the v2 edits:
  - Status field graduated from "Discussion" to "Locked / pre-implementation (v2)"; this is the canonical pre-implementation reference.
  - Per-asset table rows for `CaptureToBase64()` and raytraced stabilization rewritten to match the Tier 2 → Tier 3 prose framing added in v2 (the rows previously still said "small upgrade").
  - Two stale "Rook's settings root" references in the per-asset table and file-layout comments fixed to say "the *new* settings root introduced by this merge."
  - Tier 2 → Tier 3 prose sharpened: the Vision merge adds a *parallel* Tier 3 path for capabilities the Tier 2 handler can't provide (in-memory output, raytraced convergence). It does **not** retire the Tier 2 handler — that would be a separate PR. Added explicit scope-discipline paragraph so future readers don't over-interpret the migration framing.
  - Off-by-one fix: "Codex flagged two stale claims" → three (the list had three items).
  - Removed weasel word ("controversial rename") in favor of concrete rationale ("high-churn rename / inflated review surface").
- **2026-04-08 v2** — Codex review round 2 corrections:
  - Fixed "single `.rhp`" claim → "single public surface"; clarified that the internal C# companion `.rhp` continues to exist and is where Vision lands.
  - Repointed bridge-naming/companion-expansion references from `2026-03-08-companion-boundary-audit.md` (block-only) to `2026-03-21-rhinocommon-capability-audit.md` (full surface).
  - Added a new section explaining how the 2026-03-21 audit's safety-tier model directly justifies migrating viewport capture from Tier 2 (`_-ViewCaptureToFile`) to Tier 3 (`view.CaptureToBitmap()`), strengthening the architectural case beyond the first draft.
  - Weakened the sidecar rejection: removed the inaccurate "process boundaries the dispatcher can't see" claim. A second `.rhp` runs in the same Rhino process; the real objections are split public surface, duplicated infrastructure, and security-audit regression.
  - Corrected the settings claim: Rook has no persistent settings root in trunk (`RookPaths.cs` only resolves `DiscoveryFolder` under `%TEMP%`). Vision must introduce one, not consolidate into an existing store.
  - Added a step to specify the actual installer uninstall mechanism for the standalone SA_Banana plugin GUID.
