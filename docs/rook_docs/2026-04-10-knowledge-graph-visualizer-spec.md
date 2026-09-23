# Knowledge Graph Visualizer Implementation Spec

**Date:** 2026-04-10  
**Status:** Phase 2 implementation spec  
**Authors:** Codex + Bringfire  
**Depends on:** `94d88cf fix(chat): harden WebUI trust model (#4)`  
**Related:**
- `<repos>\rook_docs\2026-04-09-webui-substrate-module-boundaries.md`
- `<repo>\src\Rook\UI\Chat\ChatTab.cs`
- `<repo>\src\Rook\UI\Chat\RookChatPanel.cs`
- `<repo>\src\Rook\RookPlugin.cs`
- `<repo>\mcp_server\src\rook\agent\chat\server.py`
- `<repo>\mcp_server\src\rook\learning\unified_store.py`
- `<repo>\mcp_server\src\rook\learning\knowledge_note.py`

---

## 1. Purpose

Build the first non-chat WebUI module on top of the hardened WebUI foundation: a dockable **Knowledge Graph** panel that renders the GH `UnifiedStore` as an interactive graph.

This module is intentionally important for two reasons:

1. it delivers a useful feature on its own
2. it proves the Phase 2 substrate works for a real panel that is not the chat surface

This is not just a visualization task. It is the first implementation of the substrate + module architecture described in the WebUI boundary document.

---

## 2. Locked Decisions

These decisions are fixed for this spec:

- **Substrate first.** Extract a reusable WebUI host from the current chat surface before building the graph panel.
- **Separate panel now.** The graph visualizer is its own Rhino dockable panel, not a chat tab.
- **Existing chat server only.** No new HTTP service.
- **Data source is `UnifiedStore`.** The exporter reads notes from `mcp_server/src/rook/learning/unified_store.py`.
- **Renderer is Cytoscape, not Three.js.** This is a topology view, not a 3D scene.
- **Frontend never touches files.** The UI only consumes normalized JSON over the hardened chat-server transport.

---

## 3. v1 Scope

Version 1 of the knowledge graph panel includes:

- dockable Rhino panel named `Knowledge Graph`
- graph fetch from the existing Python chat server
- Cytoscape rendering with `fcose` layout
- node coloring by `note_type`
- search by note id, name, tags, components, category
- client-side filtering by `note_type` and category
- click node -> open note detail sidebar
- 1-hop neighborhood focus mode
- fit / reset layout controls

Version 1 explicitly excludes:

- graph editing
- graph writes back into `UnifiedStore`
- multi-panel synchronization bus
- live push updates while notes are changing
- generic shared graph capability extracted for other modules
- Three.js / 3D spatial rendering

The first release should solve one problem well: inspect the current knowledge graph safely and interactively.

---

## 4. Canonical Data Source

The canonical data source is `UnifiedStore`.

Implementation rule:

- instantiate or reuse `UnifiedStore`
- read notes through `store.all()` and `store.get(note_id, track_access=False)` style APIs
- compute backlinks from `UnifiedIndex` via `store.get_related(note_id)`
- do not read `knowledge/gh/notes/*.json` directly from the UI route

Normalization belongs in the exporter, not in the frontend.

### 4.1 Directionality mapping rule

`UnifiedStore.get_related(note_id)` returns:

- `links_to`: note ids that link **to** this note, meaning backlinks / incoming edges
- `links_from`: note ids this note links **to**, meaning forward links / outgoing edges

The exporter must preserve that meaning explicitly.

For the note-detail route:

- `related.linksTo` = backlinks / incoming edges
- `related.linksFrom` = forward links / outgoing edges

This is easy to invert by accident and must be treated as a contract, not an implementation detail.

### 4.2 Export inclusion rules

For v1, the exporter should:

- include only notes where `deprecated == false`
- omit edges whose source or target is missing after filtering
- preserve the directed edge as stored in `KnowledgeNote.links`
- compute reverse-link counts for display metadata

Rationale: the first graph should represent the active working knowledge set, not archive noise.

---

## 5. HTTP Contract

All routes live on the existing chat server and inherit:

- virtual-host origin rules
- `X-Rook-Session` nonce enforcement
- current CORS middleware

### 5.1 `GET /knowledge/graph`

Returns the normalized graph payload used by the Cytoscape panel.

#### Response schema

```json
{
  "meta": {
    "generatedAt": "2026-04-10T16:20:00Z",
    "source": "UnifiedStore",
    "noteCount": 1230,
    "edgeCount": 2410,
    "excludedDeprecatedCount": 12,
    "excludedDanglingEdgeCount": 7
  },
  "nodes": [
    {
      "id": "comp_ab12cd34",
      "label": "Sphere",
      "noteType": "component",
      "category": "Primitives",
      "tags": ["surface", "primitive"],
      "components": ["Sphere"],
      "brief": "Creates a sphere from center and radius.",
      "deprecated": false,
      "componentGuid": "dabc854d-f50e-408a-b001-d043c7de151d",
      "created": "2026-03-14T19:22:11Z",
      "outDegree": 4,
      "inDegree": 9,
      "degree": 13
    }
  ],
  "edges": [
    {
      "id": "comp_ab12cd34->recipe_ef56gh78",
      "source": "comp_ab12cd34",
      "target": "recipe_ef56gh78",
      "linkType": "related"
    }
  ]
}
```

#### Required node fields

- `id: string`
- `label: string`
- `noteType: "component" | "recipe" | "struggle" | "teaching"`
- `category: string`
- `tags: string[]`
- `components: string[]`
- `brief: string`
- `deprecated: boolean`
- `created: string`
- `outDegree: number`
- `inDegree: number`
- `degree: number`

#### Optional node fields

- `componentGuid: string | null`

Rules:

- `label` maps to `KnowledgeNote.name`
- `componentGuid` is populated from `note.type_data.guid` when `noteType == "component"`
- `degree = inDegree + outDegree`
- payload must be deterministic for a fixed store snapshot

#### Required edge fields

- `id: string`
- `source: string`
- `target: string`
- `linkType: "related"`

Rules:

- `linkType` is fixed to `"related"` in v1 because `KnowledgeNote.links` is untyped
- no duplicate edges for the same `source -> target`

### 5.2 `GET /knowledge/note/{note_id}`

Returns the full note payload for the right-hand inspector.

There is no standalone `body` field on `KnowledgeNote`. For v1, the inspector should treat:

- `brief` as the short summary
- `context` as the primary readable long-form content
- `note` from `to_dict()` as the full structured payload

#### Response schema

```json
{
  "note": {
    "note_id": "comp_ab12cd34",
    "note_type": "component",
    "name": "Sphere",
    "brief": "Creates a sphere from center and radius.",
    "version": "1.0",
    "created": "2026-03-14T19:22:11Z",
    "context": "...",
    "keywords": ["sphere", "surface"],
    "category": "Primitives",
    "tags": ["surface", "primitive"],
    "trigger_intents": ["create sphere"],
    "trigger_symptoms": [],
    "components": ["Sphere"],
    "solution_principle": "...",
    "anti_patterns": [],
    "preconditions": [],
    "postconditions": [],
    "links": ["recipe_ef56gh78"],
    "times_used": 3,
    "times_succeeded": 3,
    "retrieval_count": 10,
    "last_accessed": "2026-04-10T12:00:00Z",
    "last_verified": "2026-04-09T18:00:00Z",
    "citations": [],
    "created_from": "manual",
    "last_evolved": null,
    "evolved_by": [],
    "evolution_history": [],
    "type_data": {
      "guid": "dabc854d-f50e-408a-b001-d043c7de151d"
    },
    "deprecated": false,
    "deprecated_reason": null,
    "deprecated_by": null,
    "deprecated_replacement_name": null
  },
  "related": {
    "linksFrom": ["recipe_ef56gh78"],
    "linksTo": ["teaching_99887766"]
  }
}
```

Rules:

- `note` is `KnowledgeNote.to_dict()`
- `related.linksFrom` means forward links from this note
- `related.linksTo` means backlinks into this note
- return `404` if the note id is unknown

---

## 6. Substrate Extraction: `RookWebSurface`

The current `ChatTab` contains both chat behavior and generic hardened WebView hosting. That hosting code should move into a reusable base class first.

### 6.1 New base class

Create:

- `src/Rook/UI/Web/RookWebSurface.cs`

Namespace:

- `Rook.UI.Web`

Class shape:

```csharp
public abstract class RookWebSurface : Panel
{
    protected abstract string ResourceRoot { get; }
    protected abstract string StartPage { get; }
    protected abstract string MinimalFallbackHtml { get; }
    protected virtual string? SessionNonce => ChatServiceManager.Instance.SessionNonce;
    protected virtual string ContentSecurityPolicy => DefaultContentSecurityPolicy;

    protected Control CreateWebContent();
    protected void ExecuteScript(string script);
    protected virtual Task BeforeFirstNavigationAsync(CoreWebView2 coreWebView2);
    protected virtual void OnWebViewReady();
}
```

### 6.2 Code that moves from `ChatTab.cs`

Move these generic concerns into `RookWebSurface`:

- `VirtualHostName`
- `VirtualHostOrigin`
- `_webView`
- `_webViewReady`
- fallback `TextArea` host for non-WebView cases
- WebView creation
- WebView2 init hookup
- `TrySetupVirtualHost(...)`
- `ConfigureVirtualHost(...)`
- `OnWebResourceRequested(...)`
- CSP / content-type header helpers
- `FallbackToMinimalHtml()`
- `OnDocumentLoaded(...)`
- `ExecuteScript(...)`
- `EscapeForJavaScript(...)`

Critical implementation detail:

- the current resource lookup in `ChatTab.OnWebResourceRequested(...)` hardcodes `Rook.UI.Chat.Resources.{path}`
- this must be rewritten to use the new `ResourceRoot` abstraction, for example `var resourceName = $"{ResourceRoot}.{path}";`

Without this change, any non-chat surface will 404 all embedded resources even if the rest of the extraction is correct.

### 6.3 Code that stays in `ChatTab.cs`

`ChatTab` remains chat-owned and keeps:

- send / stop / clear buttons
- status bar
- input area
- chat-specific fallback formatting
- `AddMessageToChat(...)`
- `UpdateStreamingChat(...)`
- `ShowTypingIndicator(...)`
- `FinalizeStreaming(...)`
- `AddImageToChat(...)`
- conversation / persona JS shims

### 6.4 Constructor and layout refactor scope

The extraction is not a simple method move.

Today `ChatTab` constructor flow is:

1. `InitializeComponents()`
2. `LayoutControls()`
3. `AttachEvents()`

and that flow is tightly coupled to chat-specific controls:

- send button
- stop button
- clear button
- input area
- status label
- WebView host

Phase 2 must therefore split the current class into:

- a generic `RookWebSurface` that owns only the hardened WebView host and fallback content area
- a chat-specific `ChatTab` layout that composes that host together with the chat controls

`RookWebSurface` should not inherit the current `ChatTab` constructor shape. It should expose a `CreateWebContent()`-style surface host that higher-level panels or tabs place inside their own layout.

### 6.5 Startup configuration injection

`RookWebSurface.BeforeFirstNavigationAsync(...)` is the hook for per-surface bootstrap data.

`KnowledgeGraphPanel` should use it to inject:

```js
window.__rookSessionNonce = "...";
window.__rookChatService = { host: "127.0.0.1", port: 54321 };
```

This keeps host/port discovery out of the frontend code and makes the graph panel independent of any chat tab being open.

The host and port come from `ChatServiceManager.Instance.EnsureStartedAsync()`, specifically from the returned `ChatServiceHealth.BaseUri`. The panel should extract:

- `host` from `BaseUri.Host`
- `port` from `BaseUri.Port`

and inject those exact values into the page bootstrap object.

---

## 7. Rhino UI Shape

The graph visualizer is its own Rhino panel.

### New files

- `src/Rook/UI/Knowledge/KnowledgeGraphPanel.cs`
- `src/Rook/Commands/ShowRookKnowledgeGraphCommand.cs`

### Modified files

- `src/Rook/RookPlugin.cs`
- `src/Rook/Rook.csproj`

### Panel behavior

`KnowledgeGraphPanel` should:

- derive from `RookWebSurface`
- implement `IPanel`
- be registered in `RookPlugin.OnLoad(...)`
- open via Rhino command `ShowRookKnowledgeGraph`
- call `ChatServiceManager.Instance.EnsureStartedAsync()` in `PanelShown(...)`
- bootstrap the page with host, port, and nonce before navigation

### Panel type

Use `PanelType.PerDoc` for consistency with current panel registration, even though the graph data itself is global rather than document-scoped.

---

## 8. Frontend Module Shape

### New files

- `src/Rook/UI/Knowledge/Resources/knowledge-graph.html`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.css`
- `src/Rook/UI/Knowledge/Resources/knowledge-graph.js`
- `src/Rook/UI/Knowledge/Resources/vendor/cytoscape.min.js`
- `src/Rook/UI/Knowledge/Resources/vendor/cytoscape-fcose.min.js`

### Required UI regions

1. **Top toolbar**
   - search box
   - note-type filter
   - category filter
   - reset view
   - focus neighborhood toggle

2. **Main graph canvas**
   - Cytoscape container
   - draggable / zoomable
   - responsive resize handling

3. **Right sidebar**
   - note title
   - note id
   - note type / category / tags
   - brief
   - context as the primary readable long-form content
   - solution principle
   - backlinks / forward links summary

### Rendering rules

- layout: `fcose`
- node color by `noteType`
- node label from `label`
- edge arrows visible
- no custom animation loop beyond Cytoscape's own layout behavior

### Required client behavior

- initial fetch: `GET /knowledge/graph`
- click node: `GET /knowledge/note/{id}`
- client-side filtering on the already-fetched graph payload
- search should match at least:
  - `id`
  - `label`
  - `category`
  - `tags`
  - `components`

---

## 9. Python Backend Shape

### New files

- `mcp_server/src/rook/agent/chat/knowledge_graph_export.py`

### Modified files

- `mcp_server/src/rook/agent/chat/server.py`
- `mcp_server/tests/test_chat_server.py`

### Exporter API

`knowledge_graph_export.py` should expose a small, explicit API:

```python
def build_knowledge_graph_payload(store: UnifiedStore) -> dict: ...
def build_note_detail_payload(store: UnifiedStore, note_id: str) -> dict | None: ...
```

Rules:

- exporter owns all normalization
- exporter is pure relative to `UnifiedStore` input
- routes stay thin and only handle HTTP concerns

### Route responsibilities

`server.py` should add:

- `handle_knowledge_graph(request)`
- `handle_knowledge_note(request)`

and register:

- `GET /knowledge/graph`
- `GET /knowledge/note/{note_id}`

Do not add a second aiohttp app or a second route-registration abstraction.

---

## 10. Resource Embedding

### New embedded-resource root

The current csproj embeds only chat resources:

- `UI\Chat\Resources\**\*`

For the knowledge graph panel, use explicit resource entries rather than a broad wildcard:

```xml
<EmbeddedResource Include="UI\Chat\Resources\**\*" />
<EmbeddedResource Include="UI\Knowledge\Resources\**\*" />
```

This keeps the first Phase 2 change narrow and avoids accidentally embedding unrelated `Resources` trees. A broader wildcard can be reconsidered once a third WebUI module exists.

---

## 11. Tests

### Python tests

Extend `mcp_server/tests/test_chat_server.py` to cover:

- `GET /knowledge/graph` requires nonce
- `GET /knowledge/note/{note_id}` requires nonce
- allowed origin accepted
- bad origin rejected
- graph payload shape
- note payload shape
- missing note returns `404`
- deprecated notes excluded from graph export
- dangling links omitted from edge export
- only `/agent/chat/health` is nonce-exempt

### C# verification

Minimum manual verification for the panel:

- `ShowRookKnowledgeGraph` opens the panel
- panel starts the chat server if needed
- graph loads under `https://app.rook.invalid`
- browser devtools show no CSP violations
- no remote asset requests occur
- search and click interactions work

No new native/C++ work is required for this feature.

### 11.1 Middleware follow-up included in this spec

The current nonce exemption check is suffix-based. Before or during the knowledge-graph route work, tighten:

- from: `request.path.endswith("/health")`
- to: `request.path == "/agent/chat/health"`

This prevents unrelated future routes such as `/knowledge/health` from accidentally bypassing nonce enforcement.

---

## 12. Acceptance Criteria

The implementation is done when all of the following are true:

1. `RookWebSurface` exists and `ChatTab` has been reduced to chat-specific behavior.
2. The knowledge graph panel is a separate Rhino panel and opens via `ShowRookKnowledgeGraph`.
3. The panel loads entirely from embedded resources under the hardened virtual-host model.
4. The panel fetches graph data from the existing chat server using the session nonce.
5. `/knowledge/graph` returns a deterministic, normalized payload sourced from `UnifiedStore`.
6. `/knowledge/note/{note_id}` returns full note details plus backlinks/forward links.
7. Cytoscape renders the current knowledge graph interactively with acceptable responsiveness on the current dataset.
8. Search, filtering, node inspection, and 1-hop neighborhood focus all work.
9. No remote assets, no CSP violations, no second localhost service, and no direct file reads from the frontend exist.
10. Python route and exporter tests cover the new API surface.

---

## 13. Implementation Order

Recommended order:

1. extract `RookWebSurface`
2. widen embedded-resource inclusion in `Rook.csproj`
3. vendor Cytoscape assets
4. implement Python exporter
5. add `/knowledge/graph` and `/knowledge/note/{id}` routes
6. build `KnowledgeGraphPanel`
7. register panel + command
8. wire frontend interactions
9. add tests and do manual panel verification

This order keeps the substrate work explicit and makes the graph panel the first real consumer of it.

---

## 14. Parallel Zero-Risk Prep

The following work can happen in parallel with no architecture risk:

- vendor `cytoscape.min.js`
- vendor `cytoscape-fcose.min.js`
- inspect current `UnifiedStore` note distribution by `note_type` and category
- collect one or two representative note payloads to validate the frontend schema

Do **not** start writing the panel UI before the HTTP contract and `RookWebSurface` extraction are accepted.
