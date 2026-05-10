# Critical Review And Scope Notes

## Review position

The merged Prompt Memory suite is a useful capture of the taxi-cab brainstorming session, but it is not yet rigorous enough to serve as an implementation plan.

The main risk is scope collapse: the original request was a small, crisp UX need in RookVision, while the current docs jump quickly to a cross-surface prompt memory graph for humans, local agents, and cloud agents.

The graph direction is valid, but it should be separated from the first implementation slice.

## Codebase facts that should constrain the spec

### Vision has multiple prompt surfaces

RookVision currently has at least three separate prompt inputs:

- Generate image: `src/Rook/UI/Vision/Resources/index.html`
- Studio: `src/Rook/UI/Vision/Resources/index.html`
- Video: `src/Rook/UI/Vision/Resources/index.html`

Any Vision prompt reuse spec must say whether image, studio, and video prompts share one memory pool or use mode-specific filters.

### Vision prompts are already captured in artifacts

Generated image artifacts already store prompt text in artifact metadata in `src/Rook/Handlers/VisionHandler.cs`.

This creates a possible low-risk source for recent Vision prompts, but it is not a complete prompt memory store:

- It captures generated artifacts, not necessarily prompt drafts.
- It may not capture enhancement attempts that were not used.
- It does not provide an indexed frequent/recent service.
- It is scan-based through the artifact store.

### The artifact store is persistent but not an indexed ranking backend

`ArtifactStore` is deliberately v1/no-index and scan-based. That may be acceptable for a narrow recent list, but it is not a strong foundation for fast fuzzy search, cross-surface ranking, or agent write traffic.

### Chat is architecturally different from Vision

Chat input is an Eto `TextArea`, not the same HTML prompt composer model as Vision. Agent chat conversation history is currently in-memory in the Python chat service.

That means "shared Vision + Chat prompt memory" is not just a UI extension. It requires persistence and capture hooks across managed UI and Python agent chat paths.

### Vision is hosted inside the Rook chat panel, but it is not a ChatTab

The Vision tab lives inside `RookChatPanel`, but `VisionTab` is explicitly not a `ChatTab`. It owns a `VisionWebSurface` and does not share chat send/stop/clear lifecycle.

Docs should avoid saying "Vision and chat share the same composer" or implying a common input implementation.

## Issues in the current docs

### Executive summary

The strategic direction is good, but it should distinguish:

- immediate user problem,
- Option B shared memory foundation,
- Option C palette shell,
- graph/agent north star.

Right now those are compressed into one short roadmap.

### Product UX spec

The UX spec is too generic. It should define:

- exact entry point near Vision prompt fields,
- whether selection inserts only or can run,
- how Recent and Frequent are displayed before search exists,
- empty states for each surface,
- whether video prompts participate,
- whether enhanced prompts are stored separately or as variants.

### Graph contract

The graph contract captures useful entity ideas but lacks implementation boundaries:

- local store vs artifact store vs knowledge graph,
- record identity and dedupe rules,
- event sourcing vs mutable counters,
- how agent writes are rate-limited and reviewed,
- what is v1 vs future.

### OpenAPI draft

The OpenAPI file is placeholder-level. Most schemas are `{ type: object }`. It should not be treated as a contract until fields, envelopes, error shapes, and pagination are specified.

### Playwright plan

The Playwright plan is valuable but orthogonal. It should remain a test-enablement plan, not be mixed into the product spec until the UI shape is chosen.

## Recommended scope split

### Track 1: Immediate product spec

Name: Vision Prompt Reuse MRU/Frequent

Purpose:

- Satisfy the original user quote.
- Deliver recent and frequent prompt reuse in RookVision first.
- Keep default action as insert/edit, not auto-run.

Likely v1 shape:

- Prompt history button near Vision prompt fields.
- Recent and Frequent segments.
- Click inserts prompt into the active prompt field.
- Secondary action may support Insert + Generate after confirmation or explicit command.
- Deduplicate normalized prompt text while preserving display text.
- Store source surface and basic timestamps.

Open questions:

- Include video prompts in v1?
- Capture prompt on generate only, enhance only, both, or input change?
- Global across Rhino documents or scoped by document/project?
- Use artifact metadata as seed data, or introduce a dedicated prompt memory store immediately?

### Track 2: Prompt Memory substrate

Purpose:

- Define the shared durable service for Vision, Chat, and agents.
- Provide typed records, provenance, dedupe, ranking, privacy, and scopes.
- Remain local-first for v1 unless cloud sync is explicitly designed.

This track should own:

- `PromptRecord`
- `PromptUseEvent`
- `PromptVariantEdge`
- source/provenance fields,
- pin/delete/privacy controls,
- ranking formula,
- future API shape.

### Track 3: Prompt Memory Graph and agent contract

Purpose:

- Preserve the moat-level architecture.
- Treat humans and agents as first-class authors and consumers.
- Connect prompts to artifacts, sessions, tool ops, outcomes, and project context.

This should be an architecture memo before it becomes an implementation plan.

### Track 4: Test and harness plan

Purpose:

- Define how the UI will be tested once v1 UI is chosen.
- Keep Playwright/Rhino harness work scoped and independently reviewable.

## Suggested next edits

1. Add a `00-origin-conversation-context.md` source note preserving how the idea evolved.
2. Rewrite `01-executive-summary.md` to explicitly separate immediate, substrate, and graph phases.
3. Rewrite `02-product-ux-spec.md` as a Vision-first MRU/frequent spec.
4. Move advanced palette, lineage, and agent capabilities into a separate future-state architecture doc.
5. Replace placeholder OpenAPI schemas only after the store/service boundary is chosen.
