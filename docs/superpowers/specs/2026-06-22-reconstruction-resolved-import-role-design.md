# Reconstruction: Resolved Import Role Display — Design

**Date:** 2026-06-22
**Status:** Approved (Approach A)
**Lineage:** Follows PR #310 (first-class Reconstruct view) and PR #315 (one-click Import to Rhino). Base: origin/main `896ea949`.

## Problem

The Reconstruct result panel shows catalog preference, e.g. `Catalog preferred: model_glb`. But textured Hunyuan packages typically deliver `model_obj, material_mtl, texture, thumbnail` — the catalog-preferred role is often *absent* from the delivered package. The actual import resolves to `model_obj` via the importer's fallback chain. After import the UI correctly reports `Imported N object(s) as model_obj`, but **before** import the panel never states which role will actually be imported. The panel is honest about the catalog ideal and silent about the delivered reality.

## Goal

Make the result panel state, before import, the role the importer will actually use — without broadening into an import manager, without re-implementing resolution logic, and without any mutating preview call.

## Key insight: one resolver, no drift

The `import_package` path (PR #315) forwards to native `/reconstruction/2d-to-3d/import`, which calls **back into C# `prepare_import`** for its plan and imports `plan["asset_role"]` (`src/RookNative/Handlers/ImportExportHandler.cpp:90`, `:391`). That plan role is produced by C# `ResolveAssetRole`:

1. explicit `requestedRole` if present in the package, else
2. `manifest["preferred_asset"]` if present in the package, else
3. first role in `manifest["fallback_order"]` present in the package, else **fail** (no importable model asset).

Therefore the role native actually imports **equals** `ResolveAssetRole(package, manifest, requestedRole: null, …)`. Packages are immutable, so a value computed by that same function at display time cannot drift from the real import. **The resolution rule must stay in exactly one place (C#).** We surface its output to the UI; we do not copy the rule into JavaScript.

## Approach A (approved)

Backend computes the resolved role and exposes it; the UI displays it verbatim.

### Backend — `ReconstructionOpHandler.PackageSummary`

`PackageSummary(Guid packageId)` already loads the package and reads the same `import_manifest` (for `preferred_asset`). Add one field computed from the existing resolver:

```csharp
// inside PackageSummary, after `manifest` is read:
string? resolvedImportRole = null;
if (manifest is not null)
    resolvedImportRole = ResolveAssetRole(package, manifest, requestedRole: null, out _);

return new Dictionary<string, object?>
{
    ["artifact_id"]          = package.Id.ToString("D"),
    ["kind"]                 = package.Kind,
    ["asset_roles"]          = package.Files.Select(f => f.Role).Where(IsAssetRole).ToArray(),
    ["preferred_asset_role"] = preferred,            // unchanged — catalog/declared preference
    ["resolved_import_role"] = resolvedImportRole,   // NEW — the role the importer will choose, or null
};
```

Notes:
- **`resolved_import_role`**, not `import_role` — names it as the resolver's decision, not another catalog hint.
- `preferred_asset_role` is **unchanged** (still `manifest["preferred_asset"]`).
- The resolver's `out failure` is discarded (`out _`): on an unimportable package `ResolveAssetRole` returns `null`, which is exactly the value we want to surface. Passive display never throws on resolution failure.
- This is additive to the `package` summary dict — backward compatible with existing consumers.

### Purity precaution (already satisfied)

`ResolveAssetRole(Artifact package, JsonObject manifest, string? requestedRole, out ReconstructionFailure? failure) → string?` is already a pure role-resolution helper: it reads the in-memory `manifest` (`preferred_asset`, `fallback_order`) and calls `HasRole(package, …)` against `package.Files`. It allocates nothing, stages nothing, takes no import-id, and has no requested-role side effect. So `PackageSummary` calls it directly with `requestedRole: null` — **no extraction needed**. (If a future change ever gave `ResolveAssetRole` a side effect, the pure core would have to be extracted first; today it is already pure.)

### UI — `app.js` `renderResult`

The summary reaches the UI as `result.package` (`pkg`). Replace the current meta lines so the panel shows ideal vs. actual:

- `Available assets: model_obj, material_mtl, texture, thumbnail`  *(relabel of the current "Assets:" line)*
- `Catalog preferred: model_glb`  *(unchanged)*
- `Import will use: model_obj`  *(new, from `pkg.resolved_import_role`)*

Button + unresolvable handling:
- When `pkg.resolved_import_role` is a non-empty string → show `Import will use: <role>`; the Import button's enabled state is governed by `result_available` as today.
- When `pkg.resolved_import_role` is `null`/absent → show `Import unavailable: no importable model asset` (an actionable state, not a parenthetical), and **disable** the Import button regardless of `result_available`. This pre-empts a guaranteed `invalid_package` failure.

The resolved-role line is read from the field by code — never inferred from `asset_roles` in JS. No fallback resolution in JavaScript.

### Consistency with post-import copy (unchanged)

Post-import copy stays `Imported N object(s) as <role>`, read from the native import response. Because both the pre-import prediction and the native import derive from the same `ResolveAssetRole`, the two lines agree by construction.

## Out of scope

- Target-layer UI.
- assetRole override UI. Display is read-only; an override is not required, and MCP marks `assetRole` advanced/discouraged.
- Select/zoom-to-imported, duplicate-import confirmation, pre-import preview staging.
- Any `prepare_import` (mutating op) call for preview. We call only the pure `ResolveAssetRole` helper inside `PackageSummary`.
- Any native importer change. No second importer. No WebView direct HTTP (Pattern A preserved).

## Test strategy

**Backend unit tests** (`src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`), each building a package + manifest then reading `job_result`'s `package` summary:

1. **preferred present → resolved equals preferred.** Manifest `preferred_asset` is a role present in the package; assert `resolved_import_role == preferred_asset_role`.
2. **preferred missing, fallback present → resolved equals first available fallback.** Manifest `preferred_asset` is a role absent from the package (e.g. `model_glb`), `fallback_order` lists `model_obj` present; assert `resolved_import_role == "model_obj"` and that it differs from `preferred_asset_role`.
3. **no importable role → null.** The materializer guarantees every package carries `model_glb` or `model_obj`, and the static manifest's `fallback_order` lists both — so a *naturally materialized* package can never resolve to null. To exercise the defensive null path, build a real package, then overwrite its `import_manifest` blob with a degenerate manifest whose `preferred_asset`/`fallback_order` name no role present in the package (e.g. `{"preferred_asset":"model_glb","fallback_order":[]}` on an obj-only package). Assert `resolved_import_role == null` and that reading the summary does not throw (`job_result` still succeeds). This pins the UI's "Import unavailable" guard for the genuinely-unimportable case (which also makes `prepare_import` fail).
4. Extend the existing `DispatchOffUi_Result_ReturnsCompactPackageSummary` to assert the new `resolved_import_role` key is present (its model_glb package has the preferred present, so it equals `model_glb`).
5. **Parity regression (the load-bearing test).** For one package (preferred missing, fallback `model_obj` present): read `job_result`'s summary and assert `resolved_import_role == "model_obj"`; then call `prepare_import` with the *same* package and no `assetRole` and assert `prepare_import.data.asset_role == resolved_import_role`. This pins the exact promise of the slice — the panel's "Import will use" line equals the import plan's role — and guards against the two paths drifting if either resolver changes.

**UI:** the panel-dark gate is mandatory after any JS/HTML change — `node --check`, no duplicate IDs, every `$("id")` in the Reconstruct module exists in `index.html`, no stale symbols.

## Live-smoke requirement (merge gate)

Web assets are embedded resources, so a real test needs a managed Release build/deploy of `src/Rook/Rook.csproj` (Rhino closed during deploy). Drive a real Hunyuan **textured** reconstruction whose catalog preferred is `model_glb` and delivered roles are `model_obj, material_mtl, texture, thumbnail`. Confirm:
- result panel shows `Import will use: model_obj` **before** import, and
- post-import copy shows `Imported … as model_obj`,
- the two agree.

## Files touched

- `src/Rook/Handlers/ReconstructionOpHandler.cs` — one field in `PackageSummary`.
- `src/Rook/UI/Vision/Resources/app.js` — `renderResult` meta lines + unresolvable button state.
- `src/Rook/UI/Vision/Resources/index.html` / `styles.css` — only if a new line needs a hook/class; reuse existing meta containers where possible.
- `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs` — three new tests + one extension.
