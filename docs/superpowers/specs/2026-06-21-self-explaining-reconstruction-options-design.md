# Self-Explaining Reconstruction Options — Design

**Date:** 2026-06-21
**Status:** Approved. Slice 1 (D1) implements now; Slice 2 (D2+D3) deferred.
**Subsystem:** 2D→3D reconstruction (fal.ai Hunyuan-3D), C# companion plugin.

---

## Problem

The 2D→3D reconstruction submit path accepts `options` as an opaque JSON bag and
forwards every key verbatim into the fal request. Two fal flags interact in a way
the caller cannot see:

- `enable_pbr: true` → request textured / PBR output. **Produces a textured mesh.**
- `enable_pbr: true` **and** `enable_geometry: true` → `enable_geometry` wins;
  fal returns a **geometry-only white shell** and silently ignores `enable_pbr`.

This was hit live: a smoke prompt sent both flags and got back a textureless mesh.
The import path is verified texture-capable, so this is **not** an importer bug — it
is a request-construction trap. Rook spent a full fal job (~30–75s) producing a
result it could have predicted was wrong, and surfaced no explanation.

The catalog already advertises per-model `supports_pbr` and `output_roles`, but
those fields are inert: they are echoed in the models list and never consulted for
validation or warnings.

## Goal

Make the reconstruction request/result path **prevent or clearly explain**
textureless geometry caused by confusing fal options — without inventing hard
failures from metadata we have not empirically characterized.

## Doctrine (the spine)

Two tiers, separated by evidence strength:

1. **Reject known-impossible intent** — fail-closed, *before* submit, for the one
   contradiction we have empirically proven self-defeating
   (`enable_pbr:true` + `enable_geometry:true`).
2. **Warn on capability mismatch or degraded output** — fail-open, never blocking,
   for softer signals (model not PBR-capable; result missing texture/material).
3. **Never invent hard failures from metadata.** `output_roles` is capability
   *vocabulary*, not a guaranteed contract. A model advertising a role does not
   promise to deliver it on every run.

These three rules are the invariant. Everything below is their application.

---

## Slice 1 — D1: Fail-closed contradiction guard (IMPLEMENT NOW)

### Behavior

When a submit request carries both `enable_pbr:true` and `enable_geometry:true`,
reject it before spending anything:

- **Code:** `invalid_request` (the established submit-validation code).
- **Field:** `options`.
- **Retryable:** `false`.
- **Message (verbatim):**
  > `enable_geometry=true requests geometry-only output and cannot be combined with enable_pbr=true. Remove enable_geometry to request textured output, or remove enable_pbr to request geometry-only output.`

The message names **both** valid resolutions so the caller can pick the intent they
actually want.

### Placement

`ReconstructionJobManager.SubmitAsync` (`src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`).
Insert the guard **after** the `preprocessing_chain` check (the block ending at the
current line 113) and **before** the source lookup (`var source = _store.Get(...)`,
current line 115).

Consequences of this placement:
- No ledger record is created for an invalid request — consistent with the existing
  `model_id` / `preprocessing_chain` early-return validations above it.
- No source artifact read, no fal source-image publish, no provider submit.
- The request spends **nothing**.

### The check

```csharp
if (IsJsonTrue(request.Options, "enable_pbr") && IsJsonTrue(request.Options, "enable_geometry"))
    return SubmitFail(
        "invalid_request",
        "enable_geometry=true requests geometry-only output and cannot be combined with "
        + "enable_pbr=true. Remove enable_geometry to request textured output, or remove "
        + "enable_pbr to request geometry-only output.",
        "options");
```

`request.Options` is a `System.Text.Json.Nodes.JsonObject` (parsed and deep-cloned
by `ReconstructionSubmitRequestParser`). The guard reuses the existing `SubmitFail`
helper. **No DTO, contract, response-shape, or failure-code change.**

### `IsJsonTrue` — strict JSON-boolean typing

New private static helper on `ReconstructionJobManager`:

```csharp
private static bool IsJsonTrue(JsonObject options, string key)
{
    if (options is null) return false;
    if (!options.TryGetPropertyValue(key, out var node)) return false;
    if (node is not JsonValue value) return false;
    return value.TryGetValue<bool>(out var b) && b;
}
```

It returns `true` **only** when the named property is a JSON boolean literal `true`.
Deliberately **not** triggered by:
- a missing key,
- a JSON `null`,
- the string `"true"`,
- the number `1`,
- any non-boolean node.

Rationale: silently coercing loose caller input (`"true"`, `1`) into the guard would
itself be a hidden behavior — the exact failure class this feature exists to remove.
A contradiction must be expressed in the same typed form fal consumes.

### Out of scope for Slice 1 (explicitly)

- No typed DTO replacing the `JsonObject` options bag. The bag stays; the guard reads
  two keys from it.
- No `supports_pbr` / `output_roles` consultation. D1 depends on no catalog metadata.
- No warnings. D1 is reject-or-pass only.
- No change to `enable_geometry:true` *alone* (still passes — it is a legitimate
  geometry-only request) or `enable_pbr:true` *alone* (still passes — the textured
  happy path).

### Tests (Slice 1)

Unit tests on `ReconstructionJobManager.SubmitAsync` with a spy/fake provider and a
spy/fake source publisher that record invocation:

1. **Contradiction rejected:** `enable_pbr:true` + `enable_geometry:true` →
   `ReconstructionSubmitResult` failure, `Code == "invalid_request"`,
   `Field == "options"`, `Retryable == false`, message equals the verbatim string.
2. **Provider/publisher not invoked:** in case 1, the spy provider's `SubmitAsync`
   and the spy publisher's `PublishAsync` are **never called**. *(This is the
   load-bearing assertion — it proves no fal job is spent.)*
3. **`enable_pbr:true` alone passes the guard** — execution proceeds past the guard
   (reaches source lookup / provider submit).
4. **`enable_geometry:true` alone passes the guard** — no contradiction; proceeds.
5. **Strict typing — string:** `enable_pbr:"true"` + `enable_geometry:"true"` does
   **not** trigger the guard.
6. **Strict typing — numeric:** `enable_pbr:1` + `enable_geometry:1` does **not**
   trigger the guard.
7. **Missing / empty options** does **not** trigger the guard.

Tests must not require a live fal endpoint — the spy provider/publisher make the
guard path fully deterministic and offline.

---

## Slice 2 — D2+D3: Capability & degraded-output warnings (DESIGN ONLY — DEFERRED)

Captured here so the doctrine is whole. **Not implemented in this PR.** Slice 2 gets
its own brainstorm, spec refinement, plan, and review.

### Warning model (approved shape)

Two warnings, both anchored on **request intent × catalog capability** — never on
raw advertised-vs-delivered role diffing.

1. **`pbr_unsupported_by_model`**
   - **Trigger:** request has `enable_pbr:true` and the resolved catalog entry has
     `supports_pbr:false`.
   - **Meaning:** "You asked for PBR, but this model is not cataloged as
     PBR-capable."
   - **Timing:** knowable at submit. Because we chose *not* to fail-closed on this
     case, it must be carried as a warning associated with the job and surfaced at
     status/result. This implies warning **persistence on the job** (likely through
     `ReconstructionJobLedger` / job state) — the principal reason Slice 2 is a
     larger surface than Slice 1.

2. **`result_missing_texture`**
   - **Trigger:** effective PBR requested **and** model supports PBR **and** the
     delivered package has neither a `material_mtl` role nor any `texture` role.
   - **Meaning:** "You asked for textured/PBR output, the selected model supports it,
     but the provider result did not include material/texture assets."
   - **Suppressed when:** `enable_geometry:true` was requested (geometry-only intent);
     PBR was not requested; or the model does not support PBR (that path gets
     `pbr_unsupported_by_model` instead).

### "Missing texture/material" — narrow definition

- **Texture present** if any delivered role is `texture` (or a detailed texture role,
  if such roles exist in the result mapping at implementation time).
- **Material present** if a `material_mtl` role is delivered.
- Warn only if **neither** a useful material **nor** texture signal exists for a mesh
  result.

Do **not** warn merely because `output_roles` advertises a role the package omitted.
That treats the catalog as a strict contract and produces noise. `output_roles` is
capability vocabulary feeding the definition above, not a trigger of its own.

### Metadata that becomes load-bearing in Slice 2

- `supports_pbr` — drives `pbr_unsupported_by_model` and gates `result_missing_texture`.
- `output_roles` — supplies the role vocabulary for the "missing texture/material"
  definition. Not a standalone warning trigger.
- `fallback_order` — already load-bearing today (asset selection); unchanged.

### Open question deferred to Slice 2

**The exact meaning of "effective PBR requested."** Candidates:
- strictly explicit `enable_pbr:true` in options; or
- inferring fal's default-on behavior when `enable_pbr` is absent (asserts a fal
  default we have not characterized).

This ambiguity is precisely why D2/D3 must not be bundled into D1 — resolving it
requires verifying fal default semantics, which is Slice 2 work.

---

## Why slice here

D1 is the exact failure mode we tripped: known-bad, cheap to detect, cheap to reject
before a fal job. It depends on no catalog metadata, changes no contract, and ships
a safety wall with a narrow blast radius. D2+D3 introduce new warning semantics,
job-state persistence, result/status response-shape considerations, package-role
inspection, and catalog-capability interpretation — a different kind and size of
work that deserves its own PR and review. Shipping D1 first removes the proven trap
immediately without gating it on the larger warning plumbing.
