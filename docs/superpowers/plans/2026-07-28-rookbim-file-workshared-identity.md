# RookBIM File-Workshared Document Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace RookBIM's Revit Server-only GUID assumption and fail-open document matching with the approved class-limited, operation-scoped document identity resolver.

**Architecture:** A Revit-free key codec in `src/Rook` implements the approved Windows canonicalization and versioned SHA-256 byte contract. One `RevitDocumentIdentityResolver` in `src/RookBim` captures immutable evidence once per Revit operation, projects every document/element identity from that snapshot, and performs closed fail-safe comparison before lookup or side effects. Same-operation selector and preset exports carry trusted live `Element` references internally instead of serializing and re-resolving them.

**Tech Stack:** C# with `net48` compatibility; SDK-style `net8.0;net7.0;net48` `Rook`; Autodesk Revit 2024 API isolated to `src/RookBim`; xUnit 2.9.2; `System.Security.Cryptography.SHA256`; strict `UTF8Encoding(false, true)`; existing gated RookBIM diagnostics; Windows PowerShell for verification and deployment.

## Execution model and prerequisites

- Execute Tasks 1 and 2 sequentially with a fresh implementation subagent for each task and a primary-agent review gate after each commit. Task 2 is one atomic production cutover and must not be split across agents or commits.
- Execute Tasks 3 and 4 inline with the primary agent/operator. No subagent may deploy, close hosts, manipulate disposable Revit fixtures, or make the acceptance decision.
- Do not execute from this documentation branch. The execution authorization must name one immutable full commit SHA from `main` that contains:
  - active-view merge `0ab4647132ec5fe53dd2191a13328dce051a7886`;
  - the final merged gated-diagnostics implementation and its live evidence report;
  - the approved probe report, identity specification, and this plan.
- Create `codex/rookbim-file-workshared-identity` in `.worktrees/rookbim-file-workshared-identity` from that reviewed `main` SHA. Verify the SHA with `git cat-file -e`, verify the listed ancestors with `git merge-base --is-ancestor`, and require a clean worktree before Task 1.
- Do not derive the execution base from whichever checkout happens to be current. If the review verdict does not supply the immutable `main` SHA, execution is not authorized.
- The two pre-existing FFmpeg modifications remain only in the original checkout and must never enter the identity worktree or a commit.

## Global Constraints

- Treat `docs/superpowers/specs/2026-07-26-rookbim-file-workshared-identity-design.md` as authoritative. Stop for review before deviating.
- Initial versioned sources are exactly `revit_creation_guid_central_path_v1`, `revit_creation_guid_document_path_v1`, and `unavailable`. Add no server, cloud, family, detached, or unsaved versioned source.
- A v1 key identifies document lineage at one canonical authoritative location. It does not identify a physical copy, immutable revision, or content version.
- Path-only evidence never authorizes durable resolution. Raw `Path`, `DocumentPath`, `Title`, and `DocumentTitle` remain compatibility/provenance fields and are never compared.
- File-workshared central/local use `CreationGUID + canonical central ModelPath`. Saved non-workshared projects use `CreationGUID + canonical Document.PathName`.
- Saved families, unsaved projects/families, detached documents, cloud documents, and otherwise unavailable evidence fail closed for caller-supplied identities.
- Revit Server emits no new versioned key. Retain only actual legacy `WorksharingCentralGUID` behavior for a qualifying server document when no incoming `documentKey` exists.
- Never call `WorksharingCentralGUID` for a file-based or cloud model. Never call `WorksharingProjectGUID` or `CloudModelGUID` in this initial identity release.
- A supplied versioned key is authoritative. Malformed, unknown, mismatched, conflicting, or unverifiable strong evidence never downgrades to a legacy GUID, path, title, `UniqueId`, or `ElementId`.
- Capture one immutable `RevitDocumentIdentityEvidence` per Revit operation. Do not cache by `Document`, correlation, thread, request, or static state.
- Capture all required Revit values inside the same Revit API operation. Never retain lazy getters, delegates, raw exceptions, `ModelPath`, or `BasicFileInfo` beyond capture.
- Project 1,000 element identities from one snapshot with zero additional document classification, GUID, ModelPath, normalization, or hashing reads.
- Validate all identities in a batch before the first `Document.GetElement`, selection change, export conversion, or file output.
- Live `Autodesk.Revit.DB.Element` references remain inside `src/RookBim`, the captured `Document`, and one Revit operation. They never enter shared DTOs, serialized output, caches, deferred work, or a later request.
- Every live element must pass `ReferenceEquals(element.Document, evidence.Owner)` before internal use.
- Expected identity-read failures, including Revit `InternalException`, produce unavailable evidence. Producer routes continue; identity consumers fail closed. Unexpected/programming and process-fatal exceptions remain loud.
- Diagnostics enabled/disabled paths choose identical classes, keys, comparison results, statuses, and route outcomes. Diagnostics never persist GUID values, keys, paths, titles, filenames, or request identities.
- Keep Autodesk/Revit references out of `src/Rook`. Add no external dependencies and do not modify project files unless a demonstrated compile failure requires an existing-file include correction.
- Do not change the active-view policy, dispatcher timeout, `not_rhino_inside` taxonomy, category-degradation policy, native callback, Grasshopper/RiR code, MCP code, or FFmpeg files.
- Build `src/Rook/Rook.csproj` before `src/RookBim/RookBim.csproj`. Use a verified nonexistent `RhinoPluginDir` for all pre-deployment Release builds.
- Commit the complete production cutover before deployment. `/bim/status` must expose the exact deployed commit.

---

## File map

### New files

- `src/Rook/Bim/BimDocumentKeyCodec.cs` — Windows canonicalization, strict payload encoding, SHA-256 construction, and syntax validation for the approved public key-source contract; no Revit types.
- `src/Rook.Tests/Bim/BimDocumentKeyCodecTests.cs` — canonical path, byte/hash, syntax, and rejection vectors.
- `src/RookBim/Revit/RevitDocumentIdentityResolver.cs` — Revit classification/evidence capture, DTO projection, comparison, and lookup authorization.
- `src/RookBim/Revit/RevitQueryExecutionResult.cs` — private-module pairing of public query projection with same-operation live elements.
- `src/RookBim/Revit/RevitViewIdentitySerializer.cs` — view-only projection retained after deleting document/element identity logic from the old serializer.
- `docs/superpowers/reports/2026-07-28-rookbim-file-workshared-identity-acceptance.md` — redacted live acceptance record created only after Task 4.

### Modified files

- `src/Rook/Bim/BimContracts.cs` — exact wire sources/fields and closed identity error codes.
- `src/Rook/Bim/Diagnostics/BimDiagnosticContracts.cs` — identity capture/selection/comparison stages and bounded detail codes.
- `src/Rook/Bim/Diagnostics/BimDiagnosticJsonEncoder.cs` — exhaustive wire mappings for those closed values.
- `src/Rook/Handlers/BimHandler.cs` — wire mappings for `document_identity_unavailable` and `document_identity_invalid`.
- `src/RookBim/Revit/RevitRookBimRuntime.cs` — capture one evidence snapshot at each operation boundary and pass it explicitly.
- `src/RookBim/Revit/RevitCategoryResolver.cs` — project category table/resolution document identity from supplied evidence.
- `src/RookBim/Revit/RevitQueryService.cs` — return DTO plus live elements and reuse supplied evidence for every projection.
- `src/RookBim/Revit/RevitSelectionService.cs` — batch preflight before lookup/selection and snapshot-based result projection.
- `src/RookBim/Revit/RevitExportService.cs` — distinguish untrusted identity-list resolution from trusted same-operation selector elements; snapshot-based sidecar/validation projection.
- `src/RookBim/Revit/RevitPresetResolver.cs` — consume live query elements and deduplicate by `ElementId.Value` within the captured document.
- `src/Rook.Tests/Bim/RookBimContractsTests.cs` — public shape/default/source tests.
- `src/Rook.Tests/Handlers/BimHandlerTests.cs` and `src/Rook.Tests/Handlers/BimHandlerDiagnosticsTests.cs` — exact error/wire/diagnostic behavior.
- `src/Rook.Tests/Bim/Diagnostics/BimDiagnosticJsonEncoderTests.cs` — exhaustive new stage/detail encoding.
- `src/RookBim.Tests/RookBimModuleSourceTests.cs` — optional-module isolation guards and operation-path structure.
- `src/RookBim.Tests/RookBimExportSourceTests.cs` and `src/RookBim.Tests/RookBimExportPresetSourceTests.cs` — trusted live-element and identity-list boundaries.
- `docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md` — narrow supersession notice for the old path-fallback/fail-open doctrine.

### Deleted file

- `src/RookBim/Revit/RevitIdentitySerializer.cs` — remove universal server-GUID reads, boolean `DocumentMatches`, fail-open matching, and scattered document/element projection.

### Explicitly unchanged

- `src/RookNative/**`
- `src/Rook/InternalBridge/**`
- `mcp_server/**`
- `third_party/ffmpeg/**`
- Grasshopper/RiR lifecycle files
- dispatcher timeout and error taxonomy

---

### Task 1: Add the approved pure key codec without production route use

**Files:**
- Modify: `src/Rook/Bim/BimContracts.cs`
- Create: `src/Rook/Bim/BimDocumentKeyCodec.cs`
- Create: `src/Rook.Tests/Bim/BimDocumentKeyCodecTests.cs`

**Interfaces:**
- Produces public `BimDocumentKeySource` with exactly `Unavailable`, `RevitCreationGuidCentralPathV1`, and `RevitCreationGuidDocumentPathV1`.
- Produces `BimDocumentKeyCodec.TryCanonicalizeWindowsPath`, `TryCreate`, and `IsValid`.
- The enum and codec are a deliberately narrow cross-assembly contract from core to the optional Revit module; they are not routes, wire fields, or a general identity framework in Task 1.
- Uses only BCL/net48 APIs and remains unused by runtime routes until Task 2.

- [ ] **Step 1: Write failing canonicalization tests**

Add the normative vectors and exact UTF-8 assertions:

```csharp
[Theory]
[InlineData(@"C:\", @"C:\", "433a5c")]
[InlineData(@"c:/Models/../A.rvt", @"C:\A.RVT", "433a5c412e525654")]
[InlineData(@"\\server\share", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
[InlineData(@"\\server\share\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
[InlineData(@"\\server\share\folder\..\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
public void TryCanonicalizeWindowsPath_ProducesNormativeTextAndBytes(
    string input, string expected, string expectedHex)
{
    Assert.True(BimDocumentKeyCodec.TryCanonicalizeWindowsPath(input, out var actual));
    Assert.Equal(expected, actual);
    Assert.Equal(expectedHex, Hex(new UTF8Encoding(false, true).GetBytes(actual)));
}
```

Reject exactly: null, empty, whitespace, embedded NUL, relative, root-relative, drive-relative, URI, incomplete UNC, `\\?\`, `\\.\`, and `\??\`. Assert rejection returns `canonical == string.Empty`.

- [ ] **Step 2: Write failing key-byte and validation tests**

Use creation GUID `00112233-4455-6677-8899-aabbccddeeff` and assert:

```text
file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac
saved-document-v1:f8068f0ccb7e520b278de67a1b167f880ecbc7ec9ff4ddba603407643fc3e250
```

The file vector uses canonical `C:\MODELS\A.RVT` and payload `rookbim:file-workshared:v1`, NUL, lowercase D GUID, NUL, path. The saved-project vector uses canonical `\\SERVER\SHARE\A.RVT` and domain `rookbim:saved-project:v1`.

Also assert:

- the `BimDocumentKeySource` names and order are exactly `Unavailable`, `RevitCreationGuidCentralPathV1`, and `RevitCreationGuidDocumentPathV1`;
- `Guid.Empty` is rejected;
- `Unavailable` is rejected by both `TryCreate` and `IsValid`;
- source prefixes cannot be swapped;
- uppercase hex, 63/65 hex characters, non-hex characters, missing colon, and unknown prefixes are invalid;
- no server/cloud/family key kind or prefix exists;
- `TryCreate` does not expose the canonical path or GUID in the returned key.

- [ ] **Step 3: Run focused tests red**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter FullyQualifiedName~BimDocumentKeyCodecTests --verbosity minimal
```

Expected: FAIL because the codec/types do not exist.

- [ ] **Step 4: Implement the exact codec**

Add the closed public source enum to `BimContracts.cs` and use this public cross-assembly shape:

```csharp
public enum BimDocumentKeySource
{
    Unavailable,
    RevitCreationGuidCentralPathV1,
    RevitCreationGuidDocumentPathV1,
}

public static class BimDocumentKeyCodec
{
    public static bool TryCanonicalizeWindowsPath(string? input, out string canonical);
    public static bool TryCreate(
        BimDocumentKeySource source,
        Guid creationGuid,
        string path,
        out string key);
    public static bool IsValid(BimDocumentKeySource source, string? key);
}
```

Implement the seven canonicalization steps verbatim from the approved specification. Call `Path.GetFullPath` exactly once. Drive root remains `C:\`; UNC share root becomes `\\SERVER\SHARE` without a trailing separator. Apply `ToUpperInvariant`, no trim, no Unicode normalization, and no filesystem/network lookup.

Use `new UTF8Encoding(false, true)` and `SHA256.Create()`. Format the GUID with lowercase `creationGuid.ToString("D").ToLowerInvariant()`, separate the three payload fields with one `\0`, and emit exactly 64 lowercase hex characters.

Catch only `ArgumentException`, `NotSupportedException`, `PathTooLongException`, `SecurityException`, `EncoderFallbackException`, and `CryptographicException`; return `false` and empty output. Do not catch `Exception`.

- [ ] **Step 5: Run focused and full core tests green**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter FullyQualifiedName~BimDocumentKeyCodecTests --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: all pass.

- [ ] **Step 6: Prove the helper is unused and commit**

```powershell
$uses = @(rg -n "BimDocumentKeyCodec" src/Rook src/RookBim -g '*.cs' |
  Where-Object { $_ -notmatch 'BimDocumentKeyCodec.cs' })
if ($uses.Count -ne 0) { throw "Task 1 codec entered a production route" }
git diff --check
git add -- src/Rook/Bim/BimContracts.cs src/Rook/Bim/BimDocumentKeyCodec.cs `
  src/Rook.Tests/Bim/BimDocumentKeyCodecTests.cs
git commit -m "feat(rookbim): add approved document key codec"
```

Expected: one behavior-neutral preparatory commit.

---

### Task 2: Atomically cut every production identity path to one resolver

**Files:**
- Create/modify/delete every Task 2 file listed in the file map.

**Interfaces:**
- Consumes `BimDocumentKeyCodec` from Task 1 and the merged gated-diagnostic probe/session API.
- Produces exact wire fields `documentKey`, `documentKeySource`, `document_identity_unavailable`, and `document_identity_invalid`.
- Produces one `RevitDocumentIdentityEvidence` capture per operation and one closed `RevitDocumentIdentityComparison` result.
- Produces `RevitQueryExecutionResult` with a wire DTO plus same-operation live elements.

- [ ] **Step 1: Write failing core contract and wire tests**

Add these exact contracts in tests before production code:

```csharp
Assert.Equal(new[]
{
    "Unavailable",
    "RevitCreationGuidCentralPathV1",
    "RevitCreationGuidDocumentPathV1",
}, Enum.GetNames(typeof(BimDocumentKeySource)));

var document = new BimDocumentIdentity();
Assert.Null(document.DocumentKey);
Assert.Equal(BimDocumentKeySource.Unavailable, document.DocumentKeySource);

var element = new BimElementIdentity();
Assert.Null(element.DocumentKey);
Assert.Equal(BimDocumentKeySource.Unavailable, element.DocumentKeySource);
```

Serialize representative document/element identities through the existing handler serializer and assert exact wire names/values:

```json
"documentKey":"file-document-v1:<64 lowercase hex>",
"documentKeySource":"revit_creation_guid_central_path_v1"
```

Add handler tests mapping `DocumentIdentityUnavailable` to `document_identity_unavailable`/409 and `DocumentIdentityInvalid` to `document_identity_invalid`/400.

- [ ] **Step 2: Write failing optional-module source contracts**

Keep source tests to isolation/structure that managed tests cannot exercise. Use the existing lexer/member-extraction helpers, not whitespace matching. Require:

- only `RevitDocumentIdentityResolver.cs` contains `WorksharingCentralGUID`;
- no production file contains `WorksharingProjectGUID` or `CloudModelGUID`;
- the server GUID read is dominated by `ModelPath.ServerPath == true` and cannot execute for file/cloud branches;
- file-workshared and saved-project branches independently read `CreationGUID` and their approved path source;
- each Revit property read has its own availability boundary;
- `InternalException` is in the expected-exception allowlist;
- `DocumentMatches`, `GetWorksharingCentralGUID`, and every old `RevitIdentitySerializer.DocumentIdentity/ElementIdentity/Resolve` invocation are absent;
- each runtime operation captures evidence once and passes that same local to consumers/projections;
- identity batches complete every comparison before the first `GetElement`, `SetElementIds`, export conversion, or file write;
- selector and preset paths consume `RevitQueryExecutionResult.Elements` directly;
- preset dedup uses `ElementId.Value` after the owner-reference check;
- no `Element`, `Document`, `ModelPath`, or evidence type appears in `src/Rook/Bim` DTOs;
- old serializer file is deleted and the view-only serializer has no document GUID/path logic.

Do not use source text to assert runtime equality, hashing, exception behavior, or path semantics; those belong to delegate/core tests and live Revit.

- [ ] **Step 3: Run the focused tests red**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter "FullyQualifiedName~RookBimContractsTests|FullyQualifiedName~BimHandlerTests|FullyQualifiedName~BimDiagnosticJsonEncoderTests" `
  --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore `
  --filter FullyQualifiedName~Identity --verbosity minimal
```

Expected: FAIL on missing contracts/resolver/cutover.

- [ ] **Step 4: Add exact wire/error and diagnostic contracts**

Use the exact `BimDocumentKeySource` enum introduced by Task 1. Add to `BimContracts.cs`:

```csharp
// BimDocumentIdentity
public string? DocumentKey { get; set; }
public BimDocumentKeySource DocumentKeySource { get; set; } = BimDocumentKeySource.Unavailable;

// BimElementIdentity
public string? DocumentKey { get; set; }
public BimDocumentKeySource DocumentKeySource { get; set; } = BimDocumentKeySource.Unavailable;
```

Add `DocumentIdentityUnavailable` and `DocumentIdentityInvalid` to `BimErrorCode`; map them exactly in `BimHandler.MapErrorCode`.

Add diagnostic stages for classification, `CreationGUID`, ModelPath conversion, path canonicalization, key-source selection, and identity comparison. Reuse `revit.document.central_guid` only for the qualifying legacy Revit Server getter. Add only bounded class/result details needed to distinguish file-workshared, saved-project, server, cloud, family, unsaved, detached, match, mismatch, unavailable, and invalid evidence. Update the dependency-free encoder and exhaustive tests. Do not encode values.

- [ ] **Step 5: Implement operation-scoped evidence capture**

Create these internal shapes in `RevitDocumentIdentityResolver.cs`:

```csharp
internal enum RevitDocumentClass
{
    FileWorkshared,
    RevitServer,
    CloudWorkshared,
    SavedProject,
    SavedFamily,
    UnsavedProject,
    UnsavedFamily,
    Detached,
    Unknown,
}

internal enum RevitDocumentIdentityComparison
{
    Match,
    Mismatch,
    Unavailable,
    InvalidEvidence,
}

internal sealed class RevitDocumentIdentityEvidence
{
    internal Document Owner { get; }
    internal RevitDocumentClass DocumentClass { get; }
    internal string? DocumentKey { get; }
    internal BimDocumentKeySource DocumentKeySource { get; }
    internal string? LegacyGuid { get; }
    internal BimDocumentGuidSource LegacyGuidSource { get; }
    internal string? Title { get; }
    internal string? Path { get; }
    internal bool IsFamilyDocument { get; }
    internal bool IsWorkshared { get; }
    internal string UnavailableReason { get; }
}
```

The evidence constructor copies scalar/string values and the owning `Document` reference only. It stores no `ModelPath`, delegate, exception, diagnostic context, or mutable collection.

`RevitDocumentIdentityResolver.Capture(Document, BimDiagnosticContext)` performs this exact decision order:

1. Read `IsDetached`, `IsWorkshared`, `IsModelInCloud`, `IsFamilyDocument`, `Title`, and `PathName` independently.
2. If detached is true, return unavailable/detached without reading key material.
3. If workshared is true, obtain central `ModelPath` independently. Cloud classification wins when `IsModelInCloud` or `ModelPath.CloudPath` is true and returns unavailable without any GUID getter.
4. If `ModelPath.ServerPath` is true, classify Revit Server, read actual `WorksharingCentralGUID` once for legacy projection, emit no document key, and retain no failure object.
5. Otherwise require a nonempty file central ModelPath, convert it once with `ModelPathUtils.ConvertModelPathToUserVisiblePath`, read `CreationGUID` once, and invoke `BimDocumentKeyCodec.TryCreate(BimDocumentKeySource.RevitCreationGuidCentralPathV1, ...)` once.
6. If non-workshared and family, return saved/unsaved family unavailable according to `PathName` without key derivation.
7. If non-workshared project with empty `PathName`, return unsaved project unavailable.
8. Otherwise read `CreationGUID` once and invoke `TryCreate(BimDocumentKeySource.RevitCreationGuidDocumentPathV1, creationGuid, PathName, ...)` once.
9. Any unknown/failed required input returns an unavailable evidence snapshot while preserving independently read display fields.

Use a generic read result containing only success/value, bounded unavailable reason, exception type, and HResult. Do not retain `Exception`.

Expected Revit exceptions are exactly `InapplicableDataException`, Revit `InvalidOperationException`, `InternalException`, `InvalidObjectException`, Revit `ArgumentException`, and Revit `ArgumentNullException`. Expected BCL key/path exceptions are exactly the Task 1 codec allowlist. A diagnostic-enabled read goes through `BimDiagnosticProbe.Production`, which records and rethrows; the resolver catches the same expected exception and degrades. A disabled read invokes the Revit getter directly and applies the identical catch/result policy.

- [ ] **Step 6: Implement projection, comparison, and lookup authorization**

Add resolver methods with these responsibilities:

```csharp
internal BimDocumentIdentity ProjectDocument(RevitDocumentIdentityEvidence evidence);
internal BimElementIdentity ProjectElement(
    RevitDocumentIdentityEvidence evidence, Element element);
internal RevitDocumentIdentityComparison Compare(
    RevitDocumentIdentityEvidence evidence, BimElementIdentity identity);
internal BimElementResolveResult ResolveAfterComparison(
    RevitDocumentIdentityEvidence evidence, BimElementIdentity identity);
```

`ProjectDocument` copies the versioned key/source, compatibility title/path, class booleans, and actual legacy Revit Server GUID only. File/saved-project `CreationGUID` never enters `Guid`.

`ProjectElement` first requires `ReferenceEquals(element.Document, evidence.Owner)`, then copies the snapshot's document key/source and approved legacy projection. It never recaptures document evidence.

`Compare` implements the specification's normative precedence:

- incoming key present: validate exact source/prefix/version; require the active snapshot's same source; compare ordinal key bytes; reject any non-null legacy GUID as conflicting; never downgrade;
- no incoming key: allow actual legacy GUID comparison only when both sides are qualifying Revit Server persistent-GUID evidence;
- `path_fallback`, raw path/title, missing evidence, and unsupported classes never match;
- return one of the four closed results and emit only bounded diagnostic outcome/detail.

Map `Mismatch` to `document_mismatch`/409, `Unavailable` to `document_identity_unavailable`/409, and `InvalidEvidence` to `document_identity_invalid`/400.

`ResolveAfterComparison` requires `Compare == Match` before `GetElement`. It preserves UniqueId-first and ElementId-only-when-UniqueId-absent lookup semantics. It never turns unavailable evidence into a match.

Delete `RevitIdentitySerializer.cs`. Move only `ViewIdentity` and its view-specific helpers to `RevitViewIdentitySerializer.cs`.

- [ ] **Step 7: Cut producer and consumer operations over atomically**

In every `RevitRookBimRuntime` operation, capture evidence once after acquiring the active `Document`. Pass it explicitly through:

- active document and active view projection;
- category list/resolution;
- query execution and result projection;
- element info/parameters;
- selection/clear selection;
- explicit identity-list export;
- selector export;
- preset resolution/export;
- sidecar and validation projection.

No downstream method may call `Capture`.

For selection and identity-list export, use two passes: compare every input first; return the first deterministic failure before lookup or side effects; then resolve elements. Rechecking the pure comparison during resolution is allowed, but document evidence may not be reread.

For producing routes, an unavailable snapshot still projects `documentKey=null`, `documentKeySource=unavailable` and returns the route's otherwise normal status.

- [ ] **Step 8: Replace selector/preset identity round-trips with trusted live elements**

Create:

```csharp
internal sealed class RevitQueryExecutionResult
{
    internal BimApiResponse Response { get; }
    internal IReadOnlyList<Element> Elements { get; }
}
```

`RevitQueryService.Execute` builds the existing public `BimQueryElementsResult` with snapshot-based projections and returns the matching ordered live-element list separately. Failure results carry an empty live list. Validate `ReferenceEquals` before constructing success.

Ordinary query routes return only `execution.Response`. Selector export consumes `execution.Elements` directly after truncation policy. Preset resolution consumes each category execution's live list and deduplicates with `HashSet<long>` over `element.Id.Value` after owner verification. Remove document-GUID/UniqueId dedup and every serialize/resolve round-trip.

Pass evidence through export record, failed-record, sidecar, and validation builders. No export helper recaptures identity.

- [ ] **Step 9: Update doctrine and delete obsolete tests/code**

Add a notice to the Phase 1 design stating that the approved July 28 identity design supersedes path-fallback/non-stable and fail-open matching language. Link to the approved spec.

Delete tests that require unavailable document evidence to match, forbid executable versioned fallback identity, or require universal `WorksharingCentralGUID`. Replace them with the exact initial source set, downgrade prevention, server-only legacy rule, cloud no-call rule, snapshot reuse, batch-preflight, and trusted-live-element source contracts.

Do not retain deprecated code behind a fallback switch.

- [ ] **Step 10: Run focused and complete tests/builds**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter "FullyQualifiedName~BimDocumentKey|FullyQualifiedName~RookBimContracts|FullyQualifiedName~BimHandler|FullyQualifiedName~BimDiagnostic" `
  --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal

$guard = Join-Path $env:TEMP ("rook-identity-no-deploy-" + [guid]::NewGuid().ToString("N"))
if (Test-Path $guard) { throw "Guard path already exists" }
dotnet build src\Rook\Rook.csproj --configuration Release --no-restore --verbosity minimal `
  -p:RhinoPluginDir=$guard
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal `
  -p:RhinoPluginDir=$guard
if (Test-Path $guard) { throw "Guarded build attempted deployment" }
```

Expected: all tests pass; both builds exit zero; installed plugin is untouched.

- [ ] **Step 11: Run production/source/privacy scans**

```powershell
if (rg -n "WorksharingProjectGUID|CloudModelGUID" src/RookBim/Revit -g '*.cs') {
    throw "Unapproved cloud identity property entered production"
}
$centralGuidFiles = @(rg -l "WorksharingCentralGUID" src/RookBim/Revit -g '*.cs')
if ($centralGuidFiles.Count -ne 1 -or
    $centralGuidFiles[0] -notlike '*RevitDocumentIdentityResolver.cs') {
    throw "WorksharingCentralGUID escaped the authoritative resolver"
}
if (rg -n "DocumentMatches|GetWorksharingCentralGUID|RevitIdentitySerializer" `
    src/RookBim/Revit -g '*.cs') {
    throw "Obsolete identity path remains"
}
if (rg -n '\["(documentKey|documentPath|documentGuid|title|path|guid)"\]|\.DocumentKey\b|\.DocumentPath\b|\.DocumentGuid\b|\.CreationGUID\b|rawPath|normalizedPath' `
    src/Rook/Bim/Diagnostics -g '*.cs') {
    throw "Sensitive identity value entered diagnostic persistence"
}
git diff --check
```

Review `git diff --stat` and `git diff --name-only` against the Task 2 file map. Reject native, Grasshopper, MCP, FFmpeg, dispatcher-timeout, taxonomy, or unrelated export changes.

- [ ] **Step 12: Commit one atomic behavior change**

Stage explicit Task 2 paths only and commit:

```powershell
git commit -m "fix(rookbim): enforce document identity"
```

The cutover, wire fields, resolver, removal of old writers/matcher, live-element trust path, tests, and doctrine must land together. Do not deploy an intermediate subset.

---

### Task 3: Whole-branch review and committed deployment

**Files:**
- Review: all Task 1-2 files.
- Do not modify production code in this task.

**Interfaces:**
- Consumes the two reviewed commits.
- Produces installed binaries whose inventories and hashes match committed source.

- [ ] **Step 1: Run a whole-branch review**

Compare the implementation base through Task 2 head. Per-task reviews do not replace this gate. Verify:

- the approved class/source matrix is exhaustive;
- file/cloud paths cannot reach the server getter;
- no strong-key downgrade exists;
- all batches preflight before lookup/side effects;
- one snapshot flows through each operation;
- selector/preset live elements cannot cross an API/request boundary;
- expected failure degradation is identical with diagnostics disabled/enabled;
- every obsolete identity branch/test is removed;
- no unrelated subsystem changed.

If review finds a defect, return to Task 2 under an explicitly authorized safety wave, commit the complete correction, and repeat the whole-branch review. Do not patch after deployment.

- [ ] **Step 2: Repeat final tests and guarded Release builds**

Run the complete commands from Task 2 Step 10 at reviewed head. Record exact counts, warnings, and commit. Require clean status.

- [ ] **Step 3: Close hosts and deploy only reviewed head**

With Revit, Rhino, Grasshopper, and exact `python -m rook` processes closed, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\deploy-local-testing.ps1 -Configuration Release
```

Do not use `setx`. Do not start live acceptance until deploy completes.

- [ ] **Step 4: Verify installed provenance and inventories**

Compare source/deploy inventories and SHA-256 for runtime-bearing files in `net8.0`, `net7.0`, and `net48`, including `Rook.rhp`, managed dependencies, runtime subtrees, and `RookBim.dll`. Detect missing, mismatched, and stale extra files. Confirm `/bim/status` reports the Task 2 head for core and module after the next launch.

---

### Task 4: Operator-assisted Revit identity acceptance and redacted report

**Files:**
- Create only after successful matrix: `docs/superpowers/reports/2026-07-28-rookbim-file-workshared-identity-acceptance.md`
- Keep raw HTTP, JSONL, model files, identities, paths, keys, and GUIDs outside Git.

**Interfaces:**
- Consumes the exact installed Task 2 commit.
- Produces a redacted approval/blocker report. Live Revit, not source tests, is authoritative.

- [ ] **Step 1: Start a diagnostics-enabled Revit process**

```powershell
$env:ROOK_BIM_DIAGNOSTICS = '1'
Start-Process 'C:\Program Files\Autodesk\Revit 2024\Revit.exe'
Remove-Item Env:ROOK_BIM_DIAGNOSTICS
```

Load Rhino.Inside.Revit and Rook. Verify status commit, version, diagnostics enabled, sink ready, and zero initial drops.

- [ ] **Step 2: Prove the producer-route regression is removed**

On a disposable file-workshared local with a graphical 3D view, call status, active document, categories, and active-view query.

Require:

- all four routes complete without `InternalException`, dispatch timeout, or `not_rhino_inside`;
- `active_document`, category result, query result, and every element identity use `revit_creation_guid_central_path_v1` with one consistent opaque key;
- legacy GUID fields are null;
- no `revit.document.central_guid` event occurs for the file model;
- categories complete beyond the prior item-380 boundary;
- the Revit journal contains no new `ADocument::getModelGUID_()` warning and no 12-second Rook Idling callback.

If any query still stalls after the invalid getter is gone, stop acceptance and add query-stage instrumentation in a separate reviewed diagnostic change. Do not call the residual stall fixed by assumption.

- [ ] **Step 3: Run the approved file-workshared lineage/location matrix**

Using disposable files only, record aliases rather than values and prove:

1. central and standard local compare equal;
2. the same local after reopen compares equal;
3. same-lineage copied central at a different canonical location compares unequal;
4. same-lineage copy later occupying the original canonical location compares equal by design;
5. different-lineage model later occupying that canonical location compares unequal.

For each mismatch, produce an identity in A, activate B, and call element info, parameters, selection, and identity-list export. Require HTTP 409 before `GetElement`, selection change, geometry conversion, or output creation. Switch back to the matching document and require success.

- [ ] **Step 4: Run saved-project and unavailable-class cases**

Require:

- saved non-workshared project and its reopen use stable `revit_creation_guid_document_path_v1`;
- a different project replacing that path uses a different key;
- saved family, fresh unsaved project, fresh unsaved family, detached document, and cloud document (when infrastructure exists) emit `documentKey=null`, source `unavailable`;
- caller-supplied identity operations on unavailable classes return HTTP 409 `document_identity_unavailable` before lookup/side effects;
- malformed/unknown/source-conflicting keys return HTTP 400 `document_identity_invalid` without downgrade;
- raw matching title/path never changes those results.

If Revit Server infrastructure is available, verify only the no-key legacy persistent GUID flow and confirm no versioned server key is emitted. If unavailable, record the fixture limitation; do not simulate approval.

- [ ] **Step 5: Prove trusted selector/preset paths remain available**

For every unavailable class that supports ordinary query/export preconditions, require selector and preset export to consume same-operation live elements without identity re-resolution. Verify each element belongs by reference to the captured document, no live reference survives the operation, and no output is produced from another document.

Identity-list export remains fail closed on the same fixture. Use a disposable output directory and verify missing output on every rejected request.

- [ ] **Step 6: Repeat parity with diagnostics disabled**

Close Revit. Launch a fresh process without `ROOK_BIM_DIAGNOSTICS`, reload the same controlled cases, and repeat representative producer, match, mismatch, unavailable, invalid, selector-export, and identity-list-export calls.

Require identical keys, statuses, error codes, and side effects. Only diagnostic fields/JSONL presence may differ.

- [ ] **Step 7: Validate enabled JSONL privacy and completeness**

For the enabled run, parse every line and verify:

- valid JSONL, increasing sequence, one terminal per accepted request;
- exact deployed core/module commit in every record;
- zero drops or explicit bounded loss evidence;
- one identity evidence capture/key selection per operation, not per element;
- exact expected failure stage/type/HResult when evidence degrades;
- zero raw/normalized path, model title, filename, GUID value, document key, category/element name, request identity, or exception message.

Do not commit JSONL or HTTP captures.

- [ ] **Step 8: Write and commit the redacted acceptance report**

The report records:

- exact commit, Revit/Rhino/RiR/Rook versions, test/build counts, deploy/inventory result;
- aliases and equality/mismatch outcomes only;
- every document class attempted and any infrastructure limitation;
- route/status/error/side-effect outcomes;
- diagnostics enabled/disabled parity;
- JSONL validity, bounds, drop/completeness, and privacy scan;
- Revit-journal absence of the prior native getter warning;
- final pass/block decision and rollback state.

Run `git diff --check`, stage only the report, and commit `docs: record RookBIM identity acceptance`.

## Rollback

Do not partially roll back wire fields, resolver, or comparator. If live acceptance fails before release, keep hosts closed and redeploy the last known installed build only for diagnostics/support use; do not expose identity-based mutation/export as safe. If a released identity build must roll back, either deploy a corrected known-safe identity build or disable identity-based resolution, selection, and export until corrected. Restoring fail-open matching while those routes remain available is not an acceptable rollback.

## Plan self-review checklist

- [ ] Initial source set contains exactly the two approved composites plus unavailable.
- [ ] No path-only authorization, speculative source, or physical-copy claim exists.
- [ ] Strong evidence cannot downgrade.
- [ ] Every document class has an explicit disposition.
- [ ] File/cloud models cannot call the server getter.
- [ ] Expected `InternalException` produces unavailable producer evidence and fail-closed consumer behavior.
- [ ] One operation captures once; projections and 1,000-element batches do not reread.
- [ ] All batch comparisons precede lookup and side effects.
- [ ] Selector/preset live elements never cross `src/RookBim` or the operation boundary.
- [ ] Task 1 is behavior-neutral; Task 2 is one atomic deployable cutover.
- [ ] Diagnostics parity/privacy and exact wire names are tested.
- [ ] Whole-branch review precedes deployment.
- [ ] Live two-document Revit acceptance remains the release gate.
