# Phase 2 Typed Route Plan

**Date:** 2026-04-19
**Stage:** plan (campaign-level scope approved; PR-0 gate pending first-PR cut)
**Basis:** `rook_docs/2026-04-15-typed-route-gap-analysis.md` — `## Decision Record` (signed off 2026-04-17) + `rook_docs/2026-04-17-typed-route-phase1-plan.md` (Common Plan + Worked Example). This plan binds Phase 2 to the 7 rules and contract standards already in force. Common Plan is inherited verbatim from Phase 1 and only diffed where Phase 2 adds convention.

---

## Plan Inputs

### Empirical spike

Source: 2026-04-18 observation sequence against the Phase 1-closed codebase (session transcript).

Findings that drove substrate selection:

- **Managed annotations miss strict-attrs.** [CreateHandler.cs:93-121](src/Rook/Handlers/CreateHandler.cs#L93-L121) returns from the `annotationGuid` switch before the `_strictAttributes`-gated attribute block at [:181+](src/Rook/Handlers/CreateHandler.cs#L181). TEXT/dim/leader/dot/hatch do not apply `layer/color/visible/name`.
- **Managed TEXT regresses fidelity** vs. native. Native persists annotation-level overrides at [CreateHandler.cpp:558-563](src/RookNative/Handlers/CreateHandler.cpp#L558-L563) (`SetTextHeight`, `SetAnnotationFont`, `SetAnnotationBold`, `SetAnnotationItalic`, `SetAnnotationFacename` against parent dimstyle). Managed TextEntity only sets `TextHeight` + `DimensionStyleId` + `Font` at [CreateHandler.cs:963-975](src/Rook/Handlers/CreateHandler.cs#L963-L975).
- **Managed LINEAR/ALIGNED collapse.** Both dim factories pass `AnnotationType.Aligned` at [CreateHandler.cs:1009](src/Rook/Handlers/CreateHandler.cs#L1009) and [:1045](src/Rook/Handlers/CreateHandler.cs#L1045). They are not actually distinct today.
- **Native `/create?type=TEXT` and `=DIMENSION_LINEAR` are in-process** at [CreateHandler.cpp:514-615](src/RookNative/Handlers/CreateHandler.cpp#L514-L615). Bridge not required. Moving to managed would introduce a new `bridge_unavailable`/503 mode for routes that don't have one today.
- **User-string SDK is raw and already proven direct-native.** Block user strings use `pDoc->SetUserString` / `attrs.SetUserString` throughout [BlocksHandler.cpp](src/RookNative/Handlers/BlocksHandler.cpp) (:2551, :3068, :3090). Per-object user-text for arbitrary (non-block) objects has no typed route today.
- **`/select` contract drift.** [SelectionHandler.cpp:260-288](src/RookNative/Handlers/SelectionHandler.cpp#L260-L288) uses flat `namePattern` + `bboxMin`/`bboxMax`. [BlocksHandler.cpp:2910-2926](src/RookNative/Handlers/BlocksHandler.cpp#L2910-L2926) uses nested `bbox:{min,max}`. Router advertises `name` (exact) + nested `bbox`. Pure schema-contract fix, not substrate.

### Substrate decisions (locked 2026-04-19)

| Route family | Substrate | ABI bump | Rationale |
|---|---|---|---|
| `/annotation/*` | **direct-sdk native** | No | Keeps typed routes on `RookNative` (public HTTP surface per architecture); inherits native `ApplyCommonAttributes` at [CreateHandler.cpp:657](src/RookNative/Handlers/CreateHandler.cpp#L657); preserves existing TEXT override-persistence fidelity; avoids new 503 mode; does not bake the managed LINEAR/ALIGNED collapse into the new contract. |
| `/usertext/*` | **direct-sdk native** | No | `ON_3dmObjectAttributes::SetUserString` / `pDoc->SetUserString` are raw SDK; no RhinoCommon affordance needed; block-user-strings already proves native-only works. |
| `/select` drift | **schema hygiene (additive)** | No | Not a substrate decision. Accept new + old shapes simultaneously; deprecate flat form in a later post-soak PR. |

**Rejected option for annotation: managed-bridge reuse.** Would have required a prep PR to (i) fix strict-attrs bypass, (ii) lift native override-persistence into managed TEXT, (iii) split LINEAR vs ALIGNED. Substrate rhythm with PR-1-6 is symmetric but public HTTP belongs in native, and native already has the higher-fidelity TEXT path. Codex review 2026-04-18.

### Non-goals for Phase 2

- **Patch / NetworkSrf / EdgeSrf / BlendSrf / FilletSrf / OffsetSrf** (Category 5) — moved to Phase 2 surface-extension work-queue `Next` item; not bundled into this annotation/usertext/select campaign.
- **Curve blend / Curve boolean** (Category 4) — same `Next` bundle as surface extensions.
- **`/select` deprecation of flat `namePattern`/`bboxMin`/`bboxMax`** — post-soak; additive compatibility lands this campaign.
- **Hatch** (PR-8 in sequencing table) — deferred by default; promotable only if a targeted SDK spike on `CRhinoDoc::AddHatchObject` confirms single-PR envelope.
- **Dimension leaders nested inside leaders** / **TextObject 3D** / **3D Dot variants** — not in Phase 2.
- **Selection predicate additions** (`SelClosedCrv`, `SelDup`, `SelSmall`, `SelShortCrv`) — Phase 3 follow-up; PR-0 only fixes drift.
- **Migrating existing BlocksHandler user-string paths onto `UserTextHandler` substrate** — existing block metadata stays where it is. Phase 2 adds arbitrary-object and document user-text as new routes; does not rewrite block storage.

---

## Common Plan inheritance

Full Common Plan from `2026-04-17-typed-route-phase1-plan.md` §"Common Plan" applies unchanged:

- Native routing policy (§Native-routing vs native-implementation)
- Substrate decision test (Q1/Q2/Q3 + reuse-vs-add)
- Handler-level defaults (Rule 1 envelope, Rule 2 validation staging, error taxonomy base set, Rule 4 UndoScope, Rule 5 response shapes, Rule 6 substrate header, Rule 7 batch mode, optional attribute bundle)
- Shared patterns (worker-thread parse + dispatch template, managed-bridge pattern, live-Rhino characterization test shape)

Phase 2 adds two conventions on top:

### Reserved-prefix denylist (user-text routes only)

`/usertext/document-set` MUST reject writes whose keys start with any prefix in a reserved list maintained in the `UserTextHandler.cpp` source:

- `RookBlock::` — owned by block-definition metadata ([BlocksHandler.cpp:3028](src/RookNative/Handlers/BlocksHandler.cpp#L3028); rename-migration authoritative at [BlocksHandler.cs:578](src/Rook/Handlers/BlocksHandler.cs#L578))
- Future `Rook*::` reservations added to the same constant table as they appear

Violations surface `{errorCode: "reserved_namespace", errorMessage: "Key prefix 'X' is reserved for <subsystem>"}`. Read routes (`document-get`, `object-get`) are unrestricted — callers may inspect any key, including reserved ones, for diagnostics. Only writes are gated.

Object-level user-text (`/usertext/object-*`) is not subject to the denylist — object attributes are per-object storage and have no cross-subsystem namespace contract today.

### `/select` name-matching semantics (locked PR-0 contract)

- `name` = **exact-match** predicate
- `namePattern` = **wildcard** predicate (existing `MatchNamePattern` semantics, `*`/`?`)
- Both present in one request = **`invalid_input`**, not AND-composed, not silently precedence-ordered

Rationale: semantically overlapping predicates expressing different matching strategies on the same field. Mixed requests are caller confusion; strict rejection surfaces the bug. Callers that want "wildcard narrowed by type/layer" already have those composable filters.

---

## PR sequence

| PR | Scope | Gates |
|---|---|---|
| **PR-0** | `/select` additive compatibility: accept `name` (exact) + nested `bbox:{min,max}` alongside existing `namePattern` + `bboxMin`/`bboxMax`. Mixed `name` + `namePattern` = `invalid_input`. | **Gates the campaign.** Phase 2 does not open a second concurrent branch; PR-0 merges before PR-1 opens. |
| **PR-1** | `AnnotationHandler.cpp` scaffold + `/annotation/text` worked example. Extract native TEXT factory from `CreateHandler.cpp`; establish handler header substrate declaration, shared error-taxonomy helpers, route-registration pattern. | Worked-example acceptance gate (three questions below) before PR-2 opens. |
| **PR-2** | `/annotation/dim-linear`. Extract existing native DIMENSION_LINEAR factory. Contract semantics match a rotated/direction-aligned linear dimension (measures along a specified direction). Exact SDK construction verified empirically during implementation. | — |
| **PR-3** | `/annotation/dim-aligned`. New native factory. Contract semantics: dimension plane aligned with the start-end direction; measures direct Euclidean distance. Fixes the managed LINEAR/ALIGNED collapse by not replicating it. | — |
| **PR-4** | `/annotation/dim-radius` + `/annotation/dim-diameter` bundled. Same `CRhinoRadialDimension` family; differ only on the dimension variant enum. Two handlers sharing arc/circle-extraction helper. | — |
| **PR-5** | `/annotation/dim-angle`. Separate API family (`CRhinoAngularDimension`). Own PR per Rule 5 cardinality posture (different param shape: two lines or three points). | — |
| **PR-6** | `/annotation/leader`. Native factory; text + leader-point array. | — |
| **PR-7** | `/annotation/dot`. Simple text dot (always-camera-facing). | — |
| **PR-8** | `/annotation/hatch` — **deferred by default.** Promotable only after a scoped spike confirms `CRhinoDoc::AddHatchObject` + boundary-curve resolution fits a single-PR envelope. If the spike shows deeper work (pattern-library integration, multi-boundary-loop topology), item moves to Phase 3. | Spike gate. |
| **PR-9** | `UserTextHandler.cpp` scaffold + `/usertext/object-set` + `/usertext/object-get`. Worked-example for the usertext family. | Second worked-example gate (sub-family substrate declaration). |
| **PR-10** | `/usertext/document-set` + `/usertext/document-get` with reserved-prefix denylist active on the write route. | — |

**CapabilityRouter audit extension.** After PR-10 merges, extend the PR #61 four-surface audit (`tests/live_rhino/test_capability_router_phase*_coverage.py`) to cover every new Phase 2 intent + inventory reciprocity for the additive `/select` shape. Exit criterion for the campaign.

---

## Worked Example: `/annotation/text`

Template route. Text was chosen because (a) the existing native factory at [CreateHandler.cpp:514-576](src/RookNative/Handlers/CreateHandler.cpp#L514-L576) is already the canonical reference for annotation override fidelity, (b) every later annotation PR follows the same extraction-and-register pattern, (c) it exercises the font/dimstyle interaction that the managed path regresses — establishing that direct-sdk native is the right substrate for the whole family.

### Execution block

| Field | Value | Binding rule ref |
|---|---|---|
| **Substrate** | `direct-sdk` (native C++) — new `AnnotationHandler.cpp`; extracts the existing native TEXT factory; no bridge, no ABI bump. | Rule 6; §3 condition (b): native SDK path already mature |
| **Substrate rationale** | (a) `RookNative` is the public HTTP surface per architecture; managed is internal companion only. (b) Native already has higher-fidelity TEXT than managed (annotation-level override persistence). (c) Moving to managed would introduce new `bridge_unavailable`/503 mode for a route that has no bridge dependency today. (d) Avoids baking managed's strict-attrs bypass into the new contract. | Rule 6 Q3 forcing answer |
| **Native/managed owner** | Native owns: HTTP entry, JSON parse, schema validation, dimstyle override construction (`SetTextHeight`, `SetAnnotationFont`, `SetAnnotationBold`, `SetAnnotationItalic`, `SetAnnotationFacename`), `pDoc->CreateTextObject` + `pDoc->AddObject`, attribute application via `ApplyCommonAttributes`, response envelope. Managed owns: nothing on this route. | §3 |
| **Route path** | `POST /annotation/text` | Rule 3 |
| **Handler / file** | Native: `src/RookNative/Handlers/AnnotationHandler.cpp :: HandleText`. Handler header declares substrate per Rule 6. Factory body migrated near-verbatim from `CreateHandler.cpp:514-576`; `/create?type=TEXT` remains wired to the existing in-file factory for legacy-compat (not deleted in this PR). | Rule 3; §3 |
| **MCP tool impact** | New tool `rhino_annotation_text` in `server.py`. No existing tool conflict. | Decision Record §5 |
| **CapabilityRouter impact** | New entry `"create_text" → /annotation/text` in `intent_runtime.py`. Required: `text`. Optional: `point`, `height`, `font`, `bold`, `italic`, plus attribute bundle. | §5 |
| **Input schema** | `text: string REQUIRED non-empty`; `point: [x,y,z] OPTIONAL default [0,0,0]`; `height: number>0 OPTIONAL default 1.0` (matches native factory default; open to switching to a dimstyle-default policy if review flags it); `font: string OPTIONAL default "Arial"`; `bold: boolean OPTIONAL default false`; `italic: boolean OPTIONAL default false`; attribute bundle `{name?, layer?, color?, visible?}` per Common Plan. | Rule 2 |
| **Tolerance rule** | N/A (text has no tolerance parameter). | §4 |
| **Undo / batch mode** | Single-object route; one `UndoScope`. Not batch-capable. | Rule 4 |
| **Result cardinality policy** | Single-result (creator class). Returns full `ObjectSnapshot` per Rule 5. | Rule 5 |
| **Response shape** | `{id, type:"Text", layer, name, visible, color, bbox}` plus (new) `height`, `font`, `bold`, `italic` echoed back so agents can confirm applied overrides without a follow-up read. Field-level promotion decision deferred to review — if promotion is contentious, drop to bare `ObjectSnapshot` and add a separate `/annotation/text/describe` route. | Rule 5 |
| **Attribute handling** | Strict-attrs ON by default for this route (no `_strictAttributes` flag — Phase 2 typed routes enforce strict from day one). Unknown layer / unparseable color → `invalid_input`. Missing `visible` defaults to true. | Common Plan |
| **Error taxonomy** | Base set `{invalid_input, not_found, operation_failed}` only. No route-local codes for Phase 2. Font-characteristic failures fall back to the document default font (preserves existing native factory behavior at [CreateHandler.cpp:539-547](src/RookNative/Handlers/CreateHandler.cpp#L539-L547)); fallback is surfaced as success, not error. | — |
| **Tests** | `tests/live_rhino/test_annotation_text_characterization.py`: (a) happy path basic string, (b) custom font + bold + italic with override-persistence check (read back `SetAnnotationBold` state), (c) multi-line text, (d) height=0 → `invalid_input`, (e) empty `text` → `invalid_input`, (f) unknown layer → `invalid_input`, (g) non-existent font → success with default-font fallback (verify response payload echoes the effective font, not the requested one). | — |
| **PR slice** | **PR-1: AnnotationHandler + /annotation/text.** Includes scaffold (header, substrate declaration, route registration pattern in `RookServer.cpp`, shared structured-error helpers for the family), the text route itself, MCP tool, CapabilityRouter entry, characterization tests. **No ABI bump.** Existing `/create?type=TEXT` untouched for legacy-compat; migration of `/create` callers is deferred and not a Phase 2 goal. | — |

### Open Decision Record questions this example resolves

- **Per-operation substrate assignment for `/annotation/text`:** `direct-sdk` native — settled by public-HTTP-surface architecture + existing native factory fidelity.
- **Default text height:** 1.0 (matches existing native factory; open to review-time reopening if a dimstyle-default policy is preferred for Phase 2).
- **Response enrichment policy for annotation routes:** echo applied typography overrides back in the success payload so agents can verify without a follow-up read. Decision gated on PR-1 review.

### Acceptance gate

Before PR-2 opens, PR-1 must pass:

1. **Handler header substrate declaration is reusable as-is.** The comment block at the top of `AnnotationHandler.cpp` serves as the canonical rationale for every subsequent annotation route — no route-by-route substrate re-litigation.
2. **Extraction did not regress native TEXT behavior.** Live-Rhino test verifying override persistence matches pre-extraction output bit-for-bit (same dimstyle, same font characteristics, same bold/italic state).
3. **Shared structured-error helpers are general enough for dim/leader/dot reuse.** If PR-2 wants to duplicate the `invalidInput` lambda instead of calling into the shared helper, the shared helper is not yet general enough — PR-1 scope is incomplete.

---

## Worked Example: `/usertext/object-set` (PR-9)

Second worked example. Selected because the usertext family has different semantics from annotation (mutation class per Rule 5, not creator) and introduces the reserved-prefix denylist convention.

### Execution block (compressed — full fields in PR-9 sub-plan at implementation time)

- **Substrate:** `direct-sdk` native. `ON_3dmObjectAttributes::SetUserString` is raw SDK; the block-user-strings path at [BlocksHandler.cpp:2551](src/RookNative/Handlers/BlocksHandler.cpp#L2551) proves the pattern.
- **Route:** `POST /usertext/object-set` (mutation), `POST /usertext/object-get` (read).
- **Rule 5 class:** mutation; response **`{id, userStrings: {...}}`** — the FULL post-mutation user-string map, read back from the persisted attributes after `ModifyObjectAttributes`. Not `ObjectSnapshot`; no `type`/`layer`/`bbox`/attribute-bundle fields (this route mutates metadata, not geometry). Delete-related response fields are out of scope until a follow-up PR introduces `/usertext/object-delete`. **Rationale for full-echo over `{id, keysSet}`:** matches the annotation-route posture at [AnnotationHandler.cpp:41-47](src/RookNative/Handlers/AnnotationHandler.cpp#L41-L47) (echo EFFECTIVE applied values so callers verify persistence without a follow-up read); surfaces keys set by prior calls the current request did not touch; costs one extra `GetUserStringKeys` loop on the UI thread. Response shape updated 2026-04-19 during PR-9 scope pass per Codex review. The set RESPONSE itself is directly tested — not only via a follow-up `/usertext/object-get` — so the echo contract is pinned on the mutation surface.
- **Input (set):** `{id, userStrings: {k:v, k:v, ...}}` — object form inherits block-handler convention. Values must be **non-empty strings**: empty-string values are rejected with `invalid_input` at the handler. Empirical finding 2026-04-19 during PR-9 implementation: `ON_3dmObjectAttributes::SetUserString(key, "")` is the attribute-level delete sentinel (the SDK removes the key rather than storing an empty string). Accepting empty strings would silently deliver delete semantics through the set surface before the explicit `/usertext/object-delete` route is designed — rejection at validation preserves PR-9's scope containment. A dedicated test (`test_empty_string_value_does_not_sneak_delete_existing_key`) pins that the rejection path does not reach `ModifyObjectAttributes`, so a pre-existing key survives an attempted `{"key": ""}` set unchanged. Empty `userStrings` dict (`{}`) is accepted as an idempotent no-op: handler short-circuits before opening an `UndoScope` or calling `Redraw`, returning the object's current user-string map unchanged. Declared no-ops leave no fingerprint in the undo stack. The LookupObject + attribute read still dispatches through `CMainThreadDispatcher` per the Rhino UI-thread contract. PR-9 scope is set + get only.
- **Input (get):** `{id}` — returns `{id, userStrings: {...}}` with all keys; empty object `{}` if the object has no user strings.
- **Non-string value handling:** non-string values (number, null, nested object, array) are rejected with structured `invalid_input` whose message names the offending key exactly (`userStrings['foo'] must be a string`). Deliberate divergence from the lax legacy block-handler path at [BlocksHandler.cpp:2550-2551](src/RookNative/Handlers/BlocksHandler.cpp#L2550-L2551) which silently coerces non-strings to `""`; typed Phase 2 routes do not inherit that leniency. Block-specific routes remain on their legacy lax contract; this scope specifically excludes migrating them (per §"Non-goals for Phase 2").
- **Post-write readback:** response payload is built from `pDoc->LookupObject(id)` AFTER `ModifyObjectAttributes` returns, serializing from the freshly-looked-up object's attributes. Mirrors the native block-handler rhythm at [BlocksHandler.cpp:2565](src/RookNative/Handlers/BlocksHandler.cpp#L2565). Not synthesized from the request body; not assumed from the pre-write pointer.
- **Delete semantics:** deliberately out of scope for PR-9. Document-level delete is proven at [BlocksHandler.cpp:3090](src/RookNative/Handlers/BlocksHandler.cpp#L3090) via `pDoc->SetUserString(k, nullptr)`, but the equivalent object-attribute delete path (`attrs.SetUserString(k, nullptr)` or an `RemoveUserString` SDK affordance) is not exercised anywhere in-repo today. A separate follow-up PR introduces `/usertext/object-delete` after an empirical check confirms the SDK path; until then, callers cannot delete object user-text through the typed surface. This avoids baking unverified semantics into the public route.
- **Undo:** single `UndoScope` per non-empty set request; skipped entirely on the empty-map no-op path. Get is read-only, no undo.
- **Reserved-prefix:** **NOT applied** to object-level routes (per "reserved-prefix denylist" convention above).
- **CapabilityRouter:** `set_object_user_strings` → `/usertext/object-set` (required: `id`, `userStrings`); `get_object_user_strings` → `/usertext/object-get` (required: `id`). New `user_text` category in `CATEGORIES` contains both. Audit-extension test (`test_capability_router_phase2_coverage.py`) still deferred to post-PR-10 per §"Campaign exit criterion", but the route specs and category membership land in PR-9 — `/intent` traffic without a `RouteSpec` falls back to DSPy routing instead of the typed endpoint, so route specs must ship with the handler, not after.
- **Tests:** 16 live-Rhino tests. Happy path (round-trip, multi-key, set-response full-echo shape); overwrite same key; second-set-preserves-prior-keys IN SET RESPONSE (not only via follow-up get); empty-map no-op returns existing map unchanged; get of keyless object returns `{}`; strict validation — missing/malformed id, unknown id → `not_found`, **deleted-object id → `not_found`** (stronger than random UUID), missing/non-object userStrings, non-string value with key-specific error message, **empty-string value rejected with key-specific "delete" rationale**, and a **sneak-delete guard** that pins the persisted map is unchanged after a rejected `{"key": ""}` set on a pre-existing key.

### Acceptance gate

1. **Substrate declaration in `UserTextHandler.cpp` header is reusable for document routes.** PR-10 should extend the same handler without re-declaring substrate.
2. **Response shape discriminates object-level from doc-level.** Object routes echo `id`; doc routes do not. Plan field difference surfaced clearly.
3. **Reserved-prefix denylist wiring is in place even though PR-9 doesn't exercise it.** PR-9 introduces the constant table; PR-10 activates the check on `/usertext/document-set`.

---

## PR-10 Extension Block — `/usertext/document-*` + reserved-prefix denylist + `reserved_namespace`

Compressed extension of the PR-9 worked example. Not a full second worked example — PR-10 reuses the scaffold PR-9 established. This block exists because PR-10 introduces the first Phase 2 route-local error code (`reserved_namespace`) and the reserved-prefix denylist semantics, which future readers should not have to reconstruct from code.

### Execution block (compressed — full fields in handler header)

- **Substrate:** `direct-sdk` native, NOT re-declared (per acceptance gate #1). Extends `UserTextHandler.cpp`; reuses `StructuredError`, `EmitStructuredError`, and the `ValidateUserStringsObjectStrict` helper (now parametrized with `deleteRouteHint`).
- **Routes:** `POST /usertext/document-set` (mutation), `POST /usertext/document-get` (read). No `id` field on either (per acceptance gate #2).
- **Input (set):** `{userStrings: {k: non-empty-string, ...}}`. Empty `{}` is an idempotent no-op (short-circuit before `UndoScope`, mirrors object-set). Empty-string values rejected with `invalid_input` (empirical pre-flight 2026-04-19 confirmed `pDoc->SetUserString(k, "")` is the document-level delete sentinel — identical to the attribute-level behavior PR-9 probed). Non-string values rejected with key-specific `invalid_input`.
- **Input (get):** empty body OR `{}` both accepted. `ParseBodyAndDocSn` normalizes empty-body to `{}` natively, so the handler doesn't need branching logic.
- **Response (set):** `{userStrings: {...}}` — full post-mutation map read back via `pDoc->GetUserStringKeys` after mutation. No `id` field. Analog of PR-9's LookupObject-after-ModifyObjectAttributes rhythm.
- **Response (get):** `{userStrings: {...}}` — includes any reserved-prefix keys; reads are deliberately unrestricted so operators can inspect reserved namespaces for diagnostics.

### Reserved-prefix denylist (writes only)

Constant table `kReservedPrefixes[]` in `UserTextHandler.cpp` anon namespace:

```cpp
static constexpr ReservedPrefix kReservedPrefixes[] = {
    {"RookBlock::",
     "block-definition metadata (BlocksHandler)",
     "/block/user-strings"},
    // Future Rook*:: reservations append here as they appear.
};
```

Applied by `ValidateNoReservedPrefixes(body)` — worker-thread, runs AFTER base value validation and BEFORE `UndoScope` / UI-thread dispatch (per Codex scope-pass directive: reserved-prefix validation is pure JSON/key inspection and must fail before UI-thread dispatch). First-match short-circuit — consistent with PR-9's first-offender style on non-string/empty-string. Rejection is **WHOLESALE**: a mixed map like `{allowed: "v", "RookBlock::X": "v"}` fails with `reserved_namespace` AND does not write `allowed` either. No partial writes, no UndoScope opened.

Error message surface:
```
reserved_namespace: Key prefix 'RookBlock::' is reserved for
block-definition metadata (BlocksHandler); use /block/user-strings instead
```

Names the offending prefix, the owner, and the sanctioned redirect (when one exists in the table entry). Object-level routes are NOT gated — per-object attribute storage has no cross-subsystem namespace contract today. READS at both levels bypass the denylist.

### Error taxonomy extension: `reserved_namespace`

First Phase 2 route-local error code (prior Phase 2 PRs used only the base set `{invalid_input, not_found, operation_failed}`). Authorized by plan §"Reserved-prefix denylist". Gives callers a stable branch for "you used a forbidden namespace, use the sanctioned route instead" — collapsing this into `invalid_input` would erase the policy-violation-vs-shape-error distinction.

### CapabilityRouter four-surface audit (closes campaign exit criterion)

PR-10 lands `test_capability_router_phase2_coverage.py` mirroring PR #61's Phase 1 pattern:

- Per-intent parametrized checks across 4 surfaces (Tool registration, strict case-arm endpoint match, RouteSpec presence + endpoint match, category membership) for all 12 Phase 2 intents.
- Symmetric coverage-of-coverage — inventory derived from BOTH the route table AND the executor (neither side can drift silently).
- Additive `/select` shape reciprocity: BOTH legacy (`namePattern`, flat `bboxMin`/`bboxMax`) AND new (`name` exact, nested `bbox:{min,max}`) predicates must be documented in the `rhino_select` tool description — the PR-0 contract is additive by design.
- **Annotation-category backfill:** intents `create_text`, `create_dim_*`, `create_leader`, `create_dot` added to `CATEGORIES["creation"]` so the category surface check passes. Prior annotation PRs (PR-1..PR-7) shipped without category membership; PR-10 closes that gap as part of the Phase 2 audit landing.

### Acceptance gate (PR-10)

1. **Reserved-prefix rejection is wholesale, not partial.** `test_reserved_prefix_does_not_sneak_through_on_mixed_map` pre-seeds an allowed key via the typed route, attempts a mixed-map write that includes a reserved key + a new allowed key, and verifies (a) pre-existing allowed key is unchanged, (b) new allowed key was NOT added. Pins atomicity explicitly.
2. **`reserved_namespace` error message surfaces all three fields.** `test_reserved_prefix_error_message_names_prefix_and_owner` asserts the prefix, the owner description, AND the sanctioned-alternative redirect are all present in the message.
3. **Reads bypass the denylist.** `test_reserved_prefix_readable_via_get` seeds a reserved-prefix key directly via `rhino_execute` (deterministic, isolated — acceptable per Codex scope-pass caveat), then reads it back through the typed route and asserts it's visible.
4. **Four-surface audit green.** All 12 Phase 2 intents pass every surface check; `/select` additive reciprocity holds.

---

## Gap analysis refresh

Done. `rook_docs/2026-04-15-typed-route-gap-analysis.md` carries dated 2026-04-19 notes in-place under Categories 7, 8, and 9 — substrate decisions, extraction path, additive-then-deprecate posture, reserved-prefix rule, and scope containment for block-user-string migration. Decision trail stays in one canonical doc (not a separate addendum).

---

## Campaign exit criterion

Phase 2 is complete when:

1. All 11 PRs (PR-0 through PR-10) merged. If PR-8 is deferred per its spike gate, the merged count is 10 and hatch moves to Phase 3.
2. CapabilityRouter four-surface audit ([PR #61 pattern](tests/live_rhino/)) extended with Phase 2 intents; inventory reciprocity holds across additive `/select` shape.
3. Gap analysis Categories 7/8/9 each carry a dated 2026-04-19 "Phase 2 substrate decision" note reflecting direct-sdk native for annotation and usertext, additive-then-deprecate for `/select`. **(Done 2026-04-19.)**
4. Coverage delta measured against the Phase 1 baseline; target ~70% per gap analysis §Phase 2 (adjustable downward if PR-8 deferred).
