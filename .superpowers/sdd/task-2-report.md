# Task 2 Report: View-Set Assembler — Contracts, Parser, Validation Matrix

## Status: DONE

## Files Changed

### `src/Rook/Services/Reconstruction/ReconstructionContracts.cs`
- Added `using System;`
- Added `ReconstructionArtifactKinds.ViewSet = "reconstruction_view_set"`
- Added six `ReconstructionFileRoles` constants: `ViewFront`, `ViewLeft`, `ViewRight`, `ViewBack`, `ViewTop`, `ViewThreeQuarter`
- Added new `ReconstructionViewSlots` static class with: `Canonical` (front/left/right/back), `Allowed` (HashSet, net48-compatible), `FileRole(slot)`, `AssemblySourceKinds` (HashSet, net48-compatible)
- Note: Used `HashSet<string>` (not `IReadOnlySet<T>`) because test project targets net48 and `IReadOnlySet<T>` is net5+.

### `src/Rook/Services/Reconstruction/ReconstructionViewSetRequest.cs`
- Added `TryParse(string? body, out ReconstructionFailure? failure)` static method to existing record
- Parser owns structural/shape rejects: empty views, explicit empty `slots_expected`, non-string `method`/`note`, non-object provenance, malformed/missing `artifact_id`, missing `slot`
- All failures set `Details["reason"]` per spec

### `src/Rook/Services/Reconstruction/ReconstructionViewSetAssembler.cs`
- Deleted `DefaultReconstructionViewSetAssembler`
- Added `public sealed class ReconstructionViewSetAssembler : IReconstructionViewSetAssembler` taking `ArtifactStore store`
- `Assemble()` follows the 10-step algorithm from the brief exactly
- All semantic/store rejects return before `store.Create` — no artifact on failure
- Private `Fail()` helper sets `Details["reason"]`

### `src/Rook/RookSubsystemRoot.cs`
- Changed `new DefaultReconstructionViewSetAssembler()` → `new ReconstructionViewSetAssembler(SharedArtifactStore)`

### `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`
- Changed `BuildHandler` default fallback: `new DefaultReconstructionViewSetAssembler()` → `new ReconstructionViewSetAssembler(store)`
- Changed `CreateFixture`: `new DefaultReconstructionViewSetAssembler()` → `new ReconstructionViewSetAssembler(store)`

### `src/Rook.Tests/Services/Reconstruction/ReconstructionViewSetRequestTests.cs` (new)
- 16 parser tests covering: valid full body, omitted `slots_expected` (null), explicit empty (reject), non-string method/note, provenance scalar/array (reject), missing views, empty views, non-GUID `artifact_id`, missing `slot`, null body, invalid JSON

### `src/Rook.Tests/Services/Reconstruction/ReconstructionViewSetAssemblerTests.cs` (new)
- 24 assembler tests covering: 4-view happy path, partial views (incomplete), explicit `slots_expected` subset/superset, provenance round-trip, no provenance (key absent), method default/override, note absent/present, six-slot set, source lineage unchanged, all semantic rejects (duplicate slot, unknown slot, unknown/dup in `slots_expected`, malformed role, source not found, source kind not image, role not present, blob deleted), `preprocessed_image` allowed, same source twice gives distinct parent ID, views/metadata cannot drift

## Validation → Code Mapping

| Reject | Owner | Code | `Details["reason"]` |
|--------|-------|------|---------------------|
| empty `views` | Parser + Assembler (guard) | `invalid_view_set` | `empty_views` |
| explicit empty `slots_expected` | Parser | `invalid_view_set` | `empty_slots_expected` |
| non-string `method` | Parser | `invalid_view_set` | `non_string_method` |
| non-string `note` | Parser | `invalid_view_set` | `non_string_note` |
| provenance not object | Parser | `invalid_provenance` | `provenance_not_object` |
| malformed `artifact_id` | Parser | `invalid_view_set` | `invalid_artifact_id` |
| missing `slot` | Parser | `invalid_view_set` | `missing_slot` |
| unknown slot in views | Assembler | `invalid_view_set` | `unknown_slot` |
| duplicate slot in views | Assembler | `invalid_view_set` | `duplicate_slot` |
| unknown slot in `slots_expected` | Assembler | `invalid_view_set` | `unknown_slot_expected` |
| duplicate slot in `slots_expected` | Assembler | `invalid_view_set` | `duplicate_slot_expected` |
| malformed role string | Assembler | `invalid_source_role` | `invalid_role_format` |
| source artifact not found | Assembler | `invalid_source_artifact` | `source_not_found` |
| source kind not image | Assembler | `invalid_source_artifact` | `source_kind_not_image` |
| role absent on artifact | Assembler | `invalid_source_role` | `role_not_present` |
| blob unreadable | Assembler | `invalid_source_artifact` | `source_blob_unreadable` |

## Red → Green Evidence

### Step 2 (parser tests fail): `CS0117: 'ReconstructionViewSetRequest' does not contain a definition for 'TryParse'`
All 16 parser tests failed to compile before `TryParse` was added.

### Step 4 (parser tests pass):
```
Passed! - Failed: 0, Passed: 16, Skipped: 0, Total: 16, Duration: 709 ms - Rook.Tests.dll (net48)
```

### Step 6 (assembler tests fail): `CS0246: The type or namespace name 'ReconstructionViewSetAssembler' could not be found`
All 24 assembler tests failed to compile before the real class was added.

### Step 8 (assembler tests pass):
```
Passed! - Failed: 0, Passed: 24, Skipped: 0, Total: 24, Duration: 1 s - Rook.Tests.dll (net48)
```

### Combined view-set filter:
```
Passed! - Failed: 0, Passed: 40, Skipped: 0, Total: 40, Duration: 1 s - Rook.Tests.dll (net48)
```

### Full test suite (no regressions):
```
Passed! - Failed: 0, Passed: 2963, Skipped: 0, Total: 2963, Duration: 5 s - Rook.Tests.dll (net48)
```

## git grep DefaultReconstructionViewSetAssembler (code files)
Returns nothing in `.cs` files. Only references are in documentation `.md` files which describe historical context. Verified with:
```
git grep DefaultReconstructionViewSetAssembler
```
→ 0 `.cs` matches; only `.md` plan document references (expected — those describe the design decision to delete the default).

## Concerns
None. The implementation is complete and all tests pass.
