# Reconstruction Degraded-Output Warnings (D2/D3) — Design

**Date:** 2026-06-21
**Status:** Approved. One coherent vertical slice; build before UI.
**Subsystem:** 2D→3D reconstruction (fal.ai Hunyuan-3D), C# companion plugin.
**Predecessor:** D1 fail-closed options guard (PR #301, merged `fd65b8aa`). Doctrine doc: `docs/superpowers/specs/2026-06-21-self-explaining-reconstruction-options-design.md`.

---

## Problem

A reconstruction can complete *successfully* yet return geometry with no
material or texture — a confusing "successful but degraded" result. The caller
gets a bare mesh and no explanation. D1 closed the one *known-impossible* request
(`enable_pbr:true` + `enable_geometry:true`); it does nothing for the broader
case where a textured result was reasonably expected but the delivered package
came back bare.

The catalog advertises `supports_pbr` and `output_roles`, but neither is
load-bearing: they are echoed in the models list and never consulted to detect or
explain a degraded result.

A second, subtler trap: for Hunyuan rapid, **omitting** texture options still
means "textured expected" (textured is the model's default — confirmed in the
2026-06-21 live smoke). So "did the caller ask for texture?" cannot be reduced to
"did they send `enable_pbr:true`." Expectation must account for the model's
default behavior, not just explicit flags.

## Goal

When a reconstruction completes without the texture/material it was reasonably
expected to produce, surface a clear, high-signal **warning** on the result — so
the UI reads a labeled degraded state instead of inferring "white mesh" from raw
package roles, and so callers are not handed a silent confusing success.

This is the D2/D3 half of the "self-explaining reconstruction options" doctrine.
D1 (reject known-impossible intent) shipped. This slice adds **warn on capability
mismatch or degraded output**, with the catalog finally earning its keep.

## Doctrine (unchanged from the D1 pass)

1. **Reject known-impossible intent** — fail-closed, pre-submit. *(D1, shipped.)*
2. **Warn on capability mismatch or degraded output** — fail-open, never blocking. *(This slice.)*
3. **Never invent hard failures from metadata.** `output_roles` is capability
   *vocabulary*, not a guaranteed contract.

---

## Why one slice (not split)

The catalog default, the persisted expectation flag, and the result-time warnings
are inseparable: a persisted flag nobody reads, or warnings with no persisted
flag, are non-functional intermediate states that help neither the user nor the
UI. This is one bounded, single-subsystem, contract-*additive* vertical. One PR.

## Why before UI

- **Prevents UI rework:** the UI reads a populated `result.warnings[]` from day
  one instead of inferring texture degradation from raw `asset_roles` (the
  inference anti-pattern). When warnings later expand (e.g. a status echo), the UI
  already reads the channel.
- **Protects users:** a default-textured request that returns bare is *labeled*,
  not silently delivered as a confusing success.
- The cost is bounded (one catalog field + one persisted bool + result-time
  computation), not open-ended plumbing.

---

## The expectation model

### Catalog field (new) — `default_texture_expected`

Add to `ReconstructionModelEntry` and the catalog JSON, parallel to but distinct
from `supports_pbr`:

```json
"default_texture_expected": true
```

Meaning — a **Rook contract stance**, not a provider guarantee: *"Rook should
expect textured output for this model when the request gives no texture/geometry
signal, and should warn if the delivered package falls short."* Set `true` on
`fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d` (empirically confirmed: omitted
options → textured). Absent in JSON → `false` (System.Text.Json default for
`bool`).

`supports_pbr` answers a different question — *capability* ("can this model do
PBR at all"). The two are independent and both become load-bearing in this slice.

### `TextureExpected` — derived at submit, persisted on the job

Evaluated in `SubmitAsync` **after** D1's guard (so `enable_pbr:true` +
`enable_geometry:true` cannot reach here). All option reads use **strict JSON
booleans** — a non-boolean node (`"true"`, `1`, `null`) is treated as *absent*,
never coerced (consistent with D1's `IsJsonTrue`).

First match wins:

| # | Condition | `TextureExpected` | Rationale |
|---|-----------|-------------------|-----------|
| 1 | `enable_geometry === true` | **false** | explicit geometry-only mode |
| 2 | `enable_pbr === true` | **true** | explicit textured intent |
| 3 | `enable_pbr === false` | **false** | explicit opt-out of texture |
| 4 | otherwise (omitted / non-bool / null) | **`catalog.default_texture_expected`** | model's declared default — covers omitted-options |

The resulting `bool TextureExpected` is written onto the queued ledger record. The
submit `Options` bag itself is **not** persisted — only this one normalized,
typed flag.

This is the conservative resolution of the previously-deferred "effective PBR
requested" question: **effective texture expectation = normalized submit intent,
with the model's catalog default filling the omitted case** — a declared,
verifiable catalog fact, not a guess about fal internals.

### Ledger persistence + schema migration

- Add `bool TextureExpected` to `ReconstructionJobLedgerRecord`; serialize as
  `texture_expected`.
- Bump `CurrentSchemaVersion` 1 → 2.
- **Critical — relax the deserialize version gate.** Today
  `TryDeserialize` rejects any record whose `schema_version != CurrentSchemaVersion`
  as `unsupported_schema_version` (an exact-match gate). Bumping to 2 under that
  gate would drop **every** existing v1 record on read. Change the gate to accept
  any known version `1..CurrentSchemaVersion` (reject only `< 1` or `> current`).
- **v1 records read with `texture_expected` absent → `false`** (no retroactive
  warnings on historical jobs).
- New records are written at v2 with the field present.
- Forward note: an old (v1-only) reader encountering a v2 record will still drop
  it as unsupported — acceptable; downgrade is not a supported path.

---

## The warnings (result-time, Result-only)

Computed in `ReconstructionJobManager.Result(jobId)` at call time — the natural
point where all three inputs are present: persisted `TextureExpected`, catalog
capability (`_catalog.Find(job.ModelId)`), and the **delivered package's actual
roles** (`_store.Get(job.ResultArtifactId)` → enumerate `Files[].Role`). Surfaced
on the existing `ReconstructionJobResultEnvelope.Warnings` list, which the Result
HTTP response already serializes via `WarningToObj` (precedent:
`result_artifact_missing`). No new channel, no DTO surface added.

### Role-presence check (on the delivered package)

- **material present** = the package has a file with role `material_mtl`.
- **texture present** = the package has any file whose role starts with `texture`
  (covers `texture` and detailed `texture_base_color` / `texture_normal` / …;
  mirrors the existing `IsAssetRole` convention).
- **texture/material missing** = *neither* present.

Note: **material-only counts as NOT degraded.** An OBJ+MTL package can legitimately
reference materials even when texture-map assets are absent, so the presence of
`material_mtl` alone suppresses the degraded warning.

### The two warnings (mutually exclusive on `supports_pbr`)

Evaluated **only when the package is present** (see precedence). At most one fires.

| Code | Fires when | Message | Details |
|------|-----------|---------|---------|
| `pbr_unsupported_by_model` | `TextureExpected` ∧ `supports_pbr == false` | `Texture output was expected for this request, but model '{model_id}' is not catalogued as supporting textured/PBR output. The result may lack materials or textures.` | `model_id`, `supports_pbr: false` |
| `result_missing_texture` | `TextureExpected` ∧ `supports_pbr == true` ∧ texture/material missing | `Texture output was expected and this model supports it, but the delivered package contains no material or texture assets.` | `model_id`, `delivered_roles: [...]` |

### Precedence and co-occurrence

1. **Package missing** (the existing `result_artifact_missing` case —
   `ResultArtifactId` set but artifact gone): emit `result_artifact_missing`
   **only**. Do **not** evaluate texture warnings (roles are unreadable). No crash,
   no false "missing texture."
2. `TextureExpected == false` → neither texture warning fires, regardless of roles.
3. The `supports_pbr` split is exclusive → at most one texture warning per result.

---

## Explicitly out of scope (pinned)

- **No status warnings.** `Status` / `StatusAsync` and their HTTP response stay
  warning-free in this slice (the status branch keeps emitting `Array.Empty`). The
  UI polls status until complete, then calls `result` for warning state. Adding a
  status-level warning echo later is non-breaking *because* `TextureExpected` is
  persisted and warning computation is deterministic.
- **No package mutation.** Warnings are computed *interpretation* at Result time,
  never stamped into the package artifact or its metadata. Policy stays out of the
  materializer/artifact layer.
- **`output_roles` stays non-load-bearing.** The role-presence check uses the role
  *name* constants (`material_mtl`, `texture*`) directly — not an intersection with
  the model's advertised `output_roles`. `output_roles` keeps doing exactly what it
  does today (echoed in the models list). The only catalog fields that become
  load-bearing here are `default_texture_expected` (new) and `supports_pbr`
  (existing).
- **No MCP / Python / UI changes.** Warnings flow through the existing
  `WarningToObj` serializer and Result response shape. The MCP tool surface is
  unchanged.

## UI implication (for the next slice)

The UI must read `result.warnings[]` (after the job completes and it calls
`result`) to render degraded/expectation state. It must **not** infer texture
degradation from raw `package.asset_roles`. Warning codes the UI can rely on:
`pbr_unsupported_by_model`, `result_missing_texture` (and the pre-existing
`result_artifact_missing`).

---

## Components touched

| Component | File | Change |
|-----------|------|--------|
| Catalog data | `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json` | add `default_texture_expected` to Hunyuan rapid (and any other entries, defaulting `false`) |
| Catalog type | `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` | add `bool DefaultTextureExpected` (`[JsonPropertyName("default_texture_expected")]`) to `ReconstructionModelEntry` |
| Ledger record | `src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs` | add `bool TextureExpected`; `CurrentSchemaVersion`→2; serialize `texture_expected`; **relax** version gate to `1..current`; v1 read → `false` |
| Submit | `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` | derive `TextureExpected` (strict-bool reader + 4-rule table) after D1 guard; write onto the queued record |
| Result | `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` | in `Result()`, after the `result_artifact_missing` branch, when package present: resolve catalog entry, read package roles, append the two warnings |
| Warning codes | (constants, alongside existing reconstruction codes) | `pbr_unsupported_by_model`, `result_missing_texture` |

No changes to `ReconstructionOpHandler` response shape (warnings already serialized
on Result), no MCP server change, no UI change.

---

## Testing

**Submit-side derivation** (`ReconstructionJobManagerTests`):
- rule 1: `{enable_geometry:true}` → persisted `TextureExpected == false`.
- rule 2: `{enable_pbr:true}` → `true`.
- rule 3: `{enable_pbr:false}` → `false`.
- rule 4a: `{}` (omitted) on Hunyuan rapid (`default_texture_expected:true`) → `true`.
- rule 4b: non-bool (`{enable_pbr:"true"}`) → treated as omitted → catalog default.
- a model with `default_texture_expected:false`, omitted options → `false`.

**Ledger schema** (`ReconstructionJobLedgerTests`):
- v2 record round-trips `texture_expected` (true and false).
- a v1 record line (no `texture_expected`, `schema_version:1`) reads successfully
  (gate accepts it) with `TextureExpected == false` — **not** dropped as
  unsupported.
- a `schema_version` above current is still rejected as `unsupported_schema_version`.

**Result-side warnings** (`ReconstructionJobManagerTests`):
- `TextureExpected:true`, model `supports_pbr:false` → `pbr_unsupported_by_model`,
  no `result_missing_texture`.
- `TextureExpected:true`, `supports_pbr:true`, package has only `model_glb`/`model_obj`
  (no texture/material) → `result_missing_texture`.
- `TextureExpected:true`, `supports_pbr:true`, package has a `texture` role → no
  texture warning.
- `TextureExpected:true`, `supports_pbr:true`, package has `material_mtl` only (no
  texture) → no warning (material-only is not degraded).
- `TextureExpected:false`, bare package → no texture warning.
- package missing (`ResultArtifactId` set, artifact gone) → `result_artifact_missing`
  only, no texture warning.

**Catalog** (`ReconstructionModelCatalogTests`):
- `default_texture_expected` parses; Hunyuan rapid → `true`; an entry omitting the
  field → `false`.

All tests use existing fakes/fixtures; deterministic and offline. Full
`Rook.Tests` suite must stay green.
