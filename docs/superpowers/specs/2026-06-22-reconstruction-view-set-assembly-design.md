# Reconstruction View-Set Assembly — Design Spec

**Date:** 2026-06-22
**Status:** Approved for planning
**Base:** `origin/main` @ `0123f80a` (post PR #327)
**Worktree:** `.worktrees/reconstruction-view-set` on branch `feature/reconstruction-view-set-assembly`

---

## 1. Purpose

Lay the **first live foundation toward multi-view 2D→3D reconstruction**: a single,
synchronous, off-UI, full-stack operation that assembles a lineage-preserving
`reconstruction_view_set` artifact from existing image artifacts (captured viewports,
imported/generated images, or background-removed images).

This is the substrate that two *future* slices will stand on:
- a **view-generation / capture** slice (produces view sets via AI novel-view synthesis
  or Rhino camera capture), and
- a **multi-view provider submit** slice (consumes a view set, mapping `view_*` files to a
  provider's labeled fields or image array).

Neither of those is in scope here. This slice deliberately ships the *container and its
assembly capability* before any producer or consumer exists, because the artifact store
already supports it with zero schema change, and a real assembly op is exercisable
end-to-end **today** (captured viewports / bg-removed images are real image artifacts),
satisfying the project's "no dead controls / must be smokeable" discipline.

### Explicitly out of scope (deferred to later slices)
- Multi-source reconstruction **submit** contract (DTO/parser/provider payload for
  labeled or array image fields). It would be a dead, unexercised contract until a
  verified multi-view provider entry exists — and provider schemas are not to be guessed.
- AI **novel-view generation** and Rhino **camera-capture** producers.
- Provider entries for multi-view models; populating catalog `input.view_slots` / `input.array`.
- Auto background-removal chaining.
- Any UI.

---

## 2. Architecture

A **synchronous artifact transform**, not a reconstruction job. There is **no provider
call, no polling, no job lifecycle, and no job-ledger record**. The operation reads N
existing image artifacts, validates them, writes **one** new linked
`reconstruction_view_set` artifact, and returns a summary.

It uses the **same plumbing pattern** as background removal (MCP → native route → P/Invoke
bridge → `ReconstructionOpHandler`) but the **opposite dispatch arm**: the synchronous
`DispatchOffUi` branch (like `models` / `prepare_import` / `job_result`), **not** the async
job branch. Lineage and provenance live entirely in the artifact's `parent_ids` +
`metadata`.

```
rhino_2d_to_3d_assemble_view_set   (MCP tool, mutating reconstruction group)
        │  POST /reconstruction/2d-to-3d/view-sets
        ▼
RookServer.cpp  →  GrasshopperProxyHandler::HandleReconstructionAssembleViewSet
        │  P/Invoke (synchronous / off-UI path — NOT the async branch)
        ▼
NativeGhBridgeRegistrar  (off-UI dispatch; op string "assemble_view_set")
        ▼
ReconstructionOpHandler.DispatchOffUi  →  AssembleViewSet(args)
        ▼
ReconstructionViewSetAssembler  (validate → ArtifactStore.Create → summary)
        ▼
ArtifactStore  (one reconstruction_view_set artifact; sources untouched)
```

### Dispatch invariants (enforced as Task-1 tests, before assembler logic)
1. `assemble_view_set` is **absent from the async dispatch branch** of
   `HandleReconstructionDispatch` / `DispatchAsync` (it is an off-UI op).
2. The native route maps to the op string `"assemble_view_set"`.
3. A handler test proves `DispatchOffUi` reaches `ReconstructionViewSetAssembler`.
4. **Zero job-ledger writes** occur during assembly (assert the ledger is untouched).

---

## 3. Request contract

MCP tool: `rhino_2d_to_3d_assemble_view_set`. Native body / op args:

```jsonc
{
  "slots_expected": ["front", "left", "right", "back"],   // OPTIONAL; omitted ⇒ canonical four
  "views": [
    {
      "slot": "front",
      "artifact_id": "<source artifact guid>",
      "role": "image",                 // OPTIONAL per view; default "image"
      "provenance": { /* free-form JSON object */ }   // OPTIONAL; object-only
    },
    { "slot": "left", "artifact_id": "<source artifact guid>" }
  ],
  "method": "manual_assembly",         // OPTIONAL string; default "manual_assembly"
  "note": "optional free-form string"  // OPTIONAL
}
```

### Slot vocabulary (closed-but-extensible)
Allowed slots this slice: `front`, `left`, `right`, `back`, `top`, `three_quarter`
(underscore — never hyphen). Each maps deterministically to output file role
`view_<slot>` (`view_front`, `view_left`, `view_right`, `view_back`, `view_top`,
`view_three_quarter`). Unknown slot names are a hard reject; the set is one-line
extensible when a real provider requires more.

### Allowed source artifact kinds (assembler is more permissive than submit)
`generated_image`, `imported_image`, `captured_viewport`, `preprocessed_image`.
This intentionally includes `preprocessed_image` (the background-removal output), which
the provider-facing *submit* allowlist does **not** include. Assembly is a pure artifact
transform, not a 3D-gated provider submit, so bg-removed images are exactly the input we
want to support.

### Provenance
`provenance`, if present, **must be a JSON object** (reject arrays/scalars). Its internal
keys are **not interpreted or validated** this slice — it is stored verbatim under the
matching `views[]` metadata entry. This reserves a place for the future generator/capture
slice to write `{camera, prompt, generator, confidence, ...}` **without changing the
assembly request shape**, while avoiding fake typed schema before those producers exist.
No bespoke metadata-size quota is introduced (none exists in `ArtifactStore` today); rely
on normal artifact storage limits.

---

## 4. Validation rules

### Hard reject (no artifact is written)
- `views` is empty.
- Duplicate **slot** across `views` (duplicate detection is on slot, **not** source — the
  same source image may legitimately feed two slots).
- Unknown slot name in `views`.
- `slots_expected` present but **empty** (`[]`) — omitted means canonical four; an explicit
  empty list must not produce a trivially "complete" view set.
- Unknown slot name, or duplicate, in `slots_expected`.
- A view's `role` string is **malformed/unsafe** (fails `^[a-z0-9][a-z0-9_-]*$`) — validated
  **before** any artifact lookup.
- Source `artifact_id` not found in the store.
- Source artifact `kind` not in the allowed source-kind set.
- The named `role` is **absent** on the resolved source artifact.
- `provenance` present but not a JSON object.

### Allowed — artifact still written, `complete: false`
- A slot listed in `slots_expected` but absent from `views`. (This is the partial-set case;
  it is the completeness signal, not a failure.)

### Derivation pins
- `slots_present` is computed from **accepted views only**, never trusted from the request.
- `complete = slots_expected ⊆ slots_present`.
- `view_<slot>` role names are generated **only** from validated slots.
- `parent_ids` = the **distinct** set of source artifact ids used.

---

## 5. Output artifact

```jsonc
// kind: reconstruction_view_set
{
  "kind": "reconstruction_view_set",
  "files": [
    { "role": "view_front", "path": "view_front.<ext>" },   // copied bytes from source
    { "role": "view_left",  "path": "view_left.<ext>" }
  ],
  "parent_ids": ["<distinct source guid A>", "<distinct source guid B>"],
  "metadata": {
    "method": "manual_assembly",
    "note": "optional, omitted if absent",
    "slots_expected": ["front", "left", "right", "back"],
    "slots_present":  ["front", "left"],          // derived from accepted views
    "complete": false,                            // slots_expected ⊆ slots_present
    "views": [
      { "slot": "front", "source_artifact_id": "<A>", "source_role": "image",
        "view_role": "view_front", "provenance": { /* verbatim, only if supplied */ } },
      { "slot": "left",  "source_artifact_id": "<B>", "source_role": "image",
        "view_role": "view_left" }
    ]
  }
}
```

- The view set is **self-contained**: a future provider submit reads its `view_*` files
  directly; lineage remains intact via `parent_ids`.
- Source artifacts are **never mutated**. The only write is the new artifact.
- `provenance` is omitted (never serialized as `null`) when not supplied.

---

## 6. Response contract

### Success
Mirrors the established off-UI envelope (`Ok(Dictionary<string,object?>)` → `Success=true`,
`HttpStatus=200`), GUIDs as `.ToString("D")`, a `warnings` array for convention
consistency. The returned `views[]` uses the **same metadata shape**, including
`provenance` when supplied:

```jsonc
{
  "view_set_artifact_id": "<guid>",
  "kind": "reconstruction_view_set",
  "slots_expected": ["front", "left", "right", "back"],
  "slots_present":  ["front", "left"],
  "complete": false,
  "parent_ids": ["<A>", "<B>"],
  "views": [
    { "slot": "front", "source_artifact_id": "<A>", "source_role": "image",
      "view_role": "view_front", "provenance": { /* if supplied */ } },
    { "slot": "left",  "source_artifact_id": "<B>", "source_role": "image",
      "view_role": "view_left" }
  ],
  "warnings": []
}
```

The assembled view set is inspectable through existing artifact tooling
(`rhino_vision_artifacts` / `rhino_vision_get_artifact`); **no bespoke inspect surface** is
added.

### Error
Uses the existing `Fail(Failure(code, message, field, retryable), StatusFor(failure))`
envelope. `ReconstructionFailure` = `{ Code, Message, Retryable, Field, Details }`;
serialized as `{ code, message, retryable, field, details }`. The grouped-code approach
(confirmed): reuse the `invalid_source_*` family, add two new codes, all → **400** via
`StatusFor`, with `details.reason` discriminating the structural sub-cases.

| Reason | `code` | `field` | `details.reason` |
|---|---|---|---|
| empty `views` | `invalid_view_set` (new) | `views` | `empty_views` |
| duplicate slot in `views` | `invalid_view_set` | `views` | `duplicate_slot` |
| unknown slot in `views` | `invalid_view_set` | `views` | `unknown_slot` |
| `slots_expected` empty `[]` | `invalid_view_set` | `slots_expected` | `empty_slots_expected` |
| unknown / duplicate slot in `slots_expected` | `invalid_view_set` | `slots_expected` | `unknown_slot` / `duplicate_slot` |
| source artifact not found | `invalid_source_artifact` (existing) | the slot | `source_not_found` |
| source kind not image-capable | `invalid_source_artifact` | the slot | `source_kind_not_image` |
| role string malformed/unsafe | `invalid_source_role` (existing) | the slot | `invalid_role_format` |
| role absent on artifact | `invalid_source_role` | the slot | `role_not_present` |
| provenance not an object | `invalid_provenance` (new) | the slot | `provenance_not_object` |

`StatusFor` is extended so `invalid_view_set` and `invalid_provenance` map to 400 (joining
the existing `invalid_source_artifact` / `invalid_source_role` → 400 entries).

---

## 7. Components / files

### C# companion (`src/Rook/`)
- `Services/Reconstruction/ReconstructionContracts.cs` — add
  `ReconstructionArtifactKinds.ViewSet = "reconstruction_view_set"`; add view file-role
  constants (`view_front`/`left`/`right`/`back`/`top`/`three_quarter`); add the closed slot
  vocabulary + slot→view-role mapping + allowed source-kind set for assembly.
- `Services/Reconstruction/ReconstructionViewSetAssembler.cs` **(new)** — the validation +
  assembly service: parse-validated request → image-kind/role/lookup validation →
  read source bytes per accepted view → `ArtifactStore.Create(kind, blobs, parentIds,
  metadata)` → summary result.
- Request parse — a small DTO + parser (style of `ReconstructionSubmitRequestParser`):
  `ReconstructionViewSetRequest` { `SlotsExpected` (nullable list — distinguishes
  omitted vs explicit-empty), `Views` (list of `{Slot, ArtifactId, Role?, Provenance?}`),
  `Method?`, `Note?` }.
- `Handlers/ReconstructionOpHandler.cs` — add `OpAssembleViewSet = "assemble_view_set"`;
  route it in the `DispatchOffUi` switch to `AssembleViewSet(args)`; build the success
  envelope; map failures; extend `StatusFor` with the two new codes; serialization helpers
  consistent with `ModelToObj`/`InputToObj` style.
- `InternalBridge/NativeGhBridgeRegistrar.cs` — register `assemble_view_set` on the
  **off-UI / synchronous** dispatch path (explicitly **not** the async branch).

### C++ native (`src/RookNative/`)
- `RookServer.cpp` — `POST /reconstruction/2d-to-3d/view-sets`.
- `Handlers/GrasshopperProxyHandler.{h,cpp}` — `HandleReconstructionAssembleViewSet`
  dispatching via the synchronous off-UI path with op string `"assemble_view_set"`.

### Python MCP (`mcp_server/`)
- `src/rook/server.py` — `rhino_2d_to_3d_assemble_view_set` tool (params: `slots_expected?`,
  `views`, `method?`, `note?`).
- `src/rook/agent/tool_groups.py` — place the tool in the **mutating** reconstruction tool
  group (it writes a new artifact; not readonly).
- `src/rook/agent/tool_dispatcher.py` — dispatch wiring.

---

## 8. Testing

### C# (`src/Rook.Tests/`)
- `ReconstructionViewSetAssemblerTests.cs` **(new)** — validation matrix:
  - happy path: full four-slot set → `complete:true`; partial set → `complete:false`.
  - hard rejects: empty views; duplicate slot; unknown slot (views + `slots_expected`);
    explicit empty `slots_expected`; malformed role string; source not found; source kind
    not image-capable; role absent on artifact; provenance scalar; provenance array.
  - lineage: `parent_ids` = distinct sources; sources unmutated (kinds/roles intact after).
  - metadata: `slots_present` derived from accepted views; `complete` formula; `method`
    default `manual_assembly`; `note` omitted when absent.
  - provenance: object round-trips verbatim into `views[]`; omitted provenance is **omitted,
    not null**.
  - all six slots → six `view_<slot>` file roles with copied bytes.
- `ReconstructionOpHandlerTests.cs` — `DispatchOffUi` reaches the assembler; op **absent
  from the async branch**; success envelope keys/shape; each error code + `details.reason` +
  `StatusFor` status; `views[]` echoes provenance.
- Dispatch/bridge invariant tests mirroring the bg-removal pins — native route → op string;
  off-UI registration; **no job-ledger writes** during assembly.
- Contracts/role-constant test — view-role generation only from validated slots;
  `three_quarter` underscore.

### Python MCP (`mcp_server/tests/test_reconstruction_mcp_tools.py`)
- Tool present and wired; **tool-group membership pin** — `rhino_2d_to_3d_assemble_view_set`
  is in the mutating reconstruction group (mirror the existing video/reconstruction
  tool-group pins), not any readonly group.

---

## 9. Verification

- **Full local deploy required** before smoke: this slice crosses Python MCP + native route
  + managed bridge, even though there is no provider/job. Build native
  (`build-native.bat Release 14.44.35207`) + managed (`dotnet build src/Rook/Rook.csproj
  -c Release` → DeployToRhino) + `deploy-local-testing.ps1 -PayloadOnly -AllowRunning`
  (mirror mcp_server src → release venv site-packages). The new MCP tool is only callable
  after a fresh MCP connection (Claude Code restart).
- **Live smoke (merge gate):** create/obtain ≥2 image artifacts (e.g. a captured viewport
  and a bg-removed `preprocessed_image`), call `rhino_2d_to_3d_assemble_view_set` with
  front+left, omitting `slots_expected`. Assert: a `reconstruction_view_set` artifact is
  created; `parent_ids` link both sources; **sources unchanged**; `view_front`/`view_left`
  file roles present; `slots_expected` defaulted to canonical four; `complete:false`;
  `views[]` shape correct. Then assemble a full four-slot set and assert `complete:true`.
  Verify via `rhino_vision_artifacts` / `rhino_vision_get_artifact`.
- **No panel-dark gate** — no UI is touched this slice.

---

## 10. Roadmap context

This is step 1 of the longer multi-view pipeline:
1. **(this slice)** `reconstruction_view_set` artifact + assembly op — the container, live today.
2. **next:** view-generation / capture op (AI novel-view synthesis for flat photos; Rhino
   camera capture for existing 3D scenes) — *produces* view sets; provider schemas verified
   before any catalog entry.
3. **then:** multi-view provider submit — *consumes* a view set, mapping `view_*` files to a
   provider's labeled fields (`front_image_url`, …) or array (`image_urls`); catalog
   `input.view_slots` / `input.array` go live; ledger gains multi-source binding.
4. **later:** segmentation / part-aware outputs; topology / texture control metadata.
