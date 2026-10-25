# Task 1 implementation report

Status: DONE. Base: `bfc773b27f1b7e20f8c5139d4fdaa05986fe8ec3`. Workspace: `C:/Users/bring/.codex/worktrees/fal-model-definitions/Rook`; branch: `codex/fal-model-definitions`.

## Delivered

- Added the six requested managed catalog files and an empty production `catalog.json` under `src/Rook/Services/Vision/Fal/Models/`.
- Added the three requested test files under `src/Rook.Tests/Services/Vision/Fal/`.
- Added `docs/vision/fal-model-definition-v1.md`, documenting every admitted object member, enum, identity, numeric/pointer rule, finite mapping, condition, media profile, pricing shape and evidence field. Its two complete synthetic definition examples are parsed by a production-compiler test. The production manifest has no reference fixtures or configured endpoint registrations.
- Immutable sealed definitions, snapshots and bindings retain model/definition identity, revision, whole-definition canonical SHA-256, source file, exact operation/endpoint/lifecycle binding, adapter ID/version, typed metadata, and defensive JSON/list copies. `GetOperation` never derives suffixes; `TryGetOperation` validates exact pairs.
- Closed validation includes duplicate JSON member detection before node conversion, unknown members/enum/adapters, field references/types/defaults, exact safe-number policy, positive steps, nested metadata, media/operation cardinality, one-writer destination conflicts including parent/child overlap, result mappings and pricing/evidence provenance.
- Atomic catalog failure produces no partial snapshot and actionable file/pointer diagnostics. Windows path containment, rooted/UNC/parent/ADS rejection, case-insensitive duplicate filenames and reparse-point rejection include the manifest path and ancestors. The loader uses the supplied loaded-assembly directory plus `vision-models/fal/`, independently of current working directory.

## Pinned decisions applied

- Adapter IDs: `fal.image.declarative`, `fal.video.declarative`, version `1`; image sync/queue, video queue. Queue lifecycle roots are explicit complete segment ancestors or the exact endpoint.
- Semantic image roles: `primary_image`, `reference_image`, `start_frame`, `end_frame`. Only `validated_original` preparation and `fal_upload` transport are admitted. Optional `max_bytes` is at most 30 MiB, explicitly a conservative Rook catalog guard, to be intersected with runtime/provider limits by later preparation.
- Common request fields are exactly `prompt`, `resolution`, `aspect_ratio`, `duration_seconds`, `seed`. `negative_prompt` remains an option.
- Constraints use nonempty AND predicate arrays, qualified field references, `eq`/`in`, or role-presence predicates. Structural/reference/type errors, internally contradictory predicates, identical-guard empty allowed-value intersections and determinable default-state contradictions fail admission. There is no representative-state enumeration/SAT solver or new state-space bound. Contradictions for particular supplied combinations belong to Task 2 request validation.
- Pricing strategy names are `fixed_per_output`, `per_output_second`, `per_output_megapixel`. Finite enum/boolean selector tables have consistent keys and no duplicate combinations. **Absent `pricing` is valid and yields `binding.Pricing == null`, meaning unavailable for paid admission**. Explicit null or malformed pricing is invalid. Partial selector tables are valid; missing combinations mean unavailable at quotation, never zero. Pricing rates preserve exact decimal precision independently of editable control limits. No quotation/pricing arithmetic is implemented here.
- Output cardinality is fixed at one. Array results require a collection pointer and `cardinality: 1`; scalar-object results do not declare these members. Fixed provider-count constants remain available.

## TDD and command evidence

All commands ran in the explicit workspace above, on Windows. Logs listed below remain in this ignored task-evidence directory; this report is committed.

The required focused filter was:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug -f net48 --filter 'FullyQualifiedName~FalCatalog|FullyQualifiedName~FalCanonicalJson' -p:RhinoPluginDir=
```

1. `task-1-red.log`: exit 1; the test-first API references failed to compile because the `Fal.Models` namespace and result/compiler types did not exist.
2. `task-1-red-behavior.log`: after minimal fail-closed contracts/stubs, exit 1; **54 selected, 10 failed, 44 passed, 0 skipped**. Positive admission/hash/loader tests failed because compiler/hash behavior was not implemented. A temporary missing test `using` was corrected before recording this executable red run.
3. `task-1-green.log`: exit 0; **54 passed, 0 failed/skipped** after initial compiler/canonicalization implementation.
4. `task-1-red-edges.log`: exit 1; **73 selected, 1 failed, 72 passed**. The regression test demonstrated adapter version `1.0` and media cardinality `1e0` passing admission but throwing `FormatException` during binding conversion. Conversion now uses the exact admitted decimal/integer value rather than lexeme-dependent `GetInt32`.
5. `task-1-green-edges.log`: exit 0; **73 passed** after that conversion fix.
6. `task-1-red-defaults.log`: exit 1; **76 selected, 2 failed, 74 passed**. The failures reproduced invalid default-filled restrictions being admitted and the initially too-wide common-field set admitting request `negative_prompt`.
7. `task-1-green-defaults.log`: exit 0; **76 passed** after default-state validation and common-field correction.
8. `task-1-green-final.log`: exit 0; **81 passed, 0 failed/skipped**, including complete documentation parsing, exactly-one-MiB files, 64 valid definitions, 128 valid fields, 256 valid constraints, above-bound failures, junctions and loader defensive copies.

Relevant existing registry/factory verification:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug -f net48 --filter 'FullyQualifiedName~VisionProviderRegistrationsTests|FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~DefaultVideoProviderRegistryTests|FullyQualifiedName~VideoSubsystemFactoryTests' -p:RhinoPluginDir=
```

`task-1-registry.log`: exit 0; **54 passed, 0 failed/skipped**. The new tests also compile an invalid catalog and prove the independent legacy image registry still resolves FLUX Schnell.

Final verification after the last production/test edits:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug -f net48 --filter 'FullyQualifiedName~FalCatalog|FullyQualifiedName~FalCanonicalJson|FullyQualifiedName~VisionProviderRegistrationsTests|FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~DefaultVideoProviderRegistryTests|FullyQualifiedName~VideoSubsystemFactoryTests' -p:RhinoPluginDir=
dotnet build src/Rook/Rook.csproj -c Debug -p:RhinoPluginDir=
```

`task-1-verified.log`: exit 0; **135 passed, 0 failed/skipped** (81 catalog + 54 existing registry/factory tests).

`task-1-managed-build-final.log`: exit 0; **net48, net7.0 and net8.0 build succeeded**, 0 errors, **280 warnings**. Debug was used; there was no deployment. No native source or native/managed ABI changed.

## Warnings and limits of verification

Existing compiler/analyzer warnings were emitted, rather than a clean zero-warning build. No emitted warning is attributed to the new catalog or new test files. The final test/build logs include warning codes `CA1416`, `CS0067`, `CS0612`, `CS0618`, `CS1066`, `CS7095`, `CS8600`, `CS8601`, `CS8602`, `CS8603`, `CS8604`, `CS8619`, `CS8622`, `CS8629`, `xUnit1012`, `xUnit1031`, `xUnit2013`, `xUnit2031`, on existing source/test files. `baseline-managed.log` records the earlier managed baseline; additional target builds expose existing platform warnings in unmodified files. This report does not claim warnings were fixed or that the entire unrelated suite ran.

Focused checks follow the controller's proportional-verification instruction; broad regression remains Task 11. No paid calls, external provider requests, installed-runtime checks, native build, new dependency, deployment, `.vcxproj`/filters change, provider/transport/normalizer or later-task integration occurred.

## Self-review and concerns

Self-review checked the revised task brief against the complete vocabulary, nested rejection rules, finite adapter versions, exact numeric conversion, immutable JSON boundaries, independent lifecycle root, queue/video requirements, Windows containment/reparse handling, atomic diagnostics, unpriced/disabled metadata, synthetic examples and unchanged legacy factories. No unresolved Task 1 concern is known. Later tasks must consume this closed vocabulary, enforce supplied-combination restrictions, intersect media ceilings, treat absent pricing/missing selectors as unavailable, and integrate loading at subsystem initialization; none of those later responsibilities is claimed here.
