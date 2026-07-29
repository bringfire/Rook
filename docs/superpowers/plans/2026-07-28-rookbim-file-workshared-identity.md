# RookBIM File-Workshared Document Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace RookBIM's Revit Server-only GUID assumption and fail-open document matching with the approved class-limited, operation-scoped document identity resolver.

**Architecture:** A small Revit-free BIM policy in `src/Rook` owns key construction, ordered classification, evidence coherence, and comparison through closed reader results. A thin `src/RookBim` adapter owns Autodesk calls and diagnostics, while the Python MCP only admits and forwards the two optional strong-identity fields. One atomic cutover keeps managed contracts, Revit behavior, and the closed MCP schema version-aligned.

**Tech Stack:** C# with `net48` compatibility; SDK-style `net8.0;net7.0;net48` `Rook`; Autodesk Revit 2024 API isolated to `src/RookBim`; xUnit 2.9.2; Python 3.10+ with pytest; `System.Security.Cryptography.SHA256`; strict `UTF8Encoding(false, true)`; existing gated RookBIM diagnostics; Windows PowerShell for verification, deployment, and rollback artifacts.

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
- Diagnostics stay outside `BimDocumentIdentityPolicy`. The policy accepts only closed success/unavailable reader results and has no diagnostic context, observer, sink, or global flag.
- `Document.PathName` is read once per operation. Saved-project key derivation and compatibility display projection reuse that exact result.
- Read central `ModelPath` only after `IsDetached` and `IsWorkshared` succeed, the document is not detached, `IsWorkshared == true`, and cloud classification succeeds. Never read it for a non-workshared document.
- Legacy Revit Server GUID text is valid only when it is exactly 36 characters, `Guid.TryParseExact(value, "D", out var parsed)` succeeds without trimming, and `parsed != Guid.Empty`.
- MCP `documentKey` and `documentKeySource` are optional. Python admits only the three approved source strings, performs no key/regex/hash/coherence policy, and forwards identity dictionaries unchanged.
- Keep Autodesk/Revit references out of `src/Rook`. Add no external dependencies and do not modify project files unless a demonstrated compile failure requires an existing-file include correction.
- Keep the policy BIM-specific and closed. Add no generic reader framework, dependency-injection layer, cache, registry, or provider extension point.
- Do not change the active-view policy, dispatcher timeout, `not_rhino_inside` taxonomy, category-degradation policy, native callback, Grasshopper/RiR code, unrelated MCP code, or FFmpeg files.
- Build `src/Rook/Rook.csproj` before `src/RookBim/RookBim.csproj`. Use a verified nonexistent `RhinoPluginDir` for all pre-deployment Release builds.
- Commit the complete production cutover before deployment. `/bim/status` must expose the exact deployed commit.

---

## File map

### New files

- `src/Rook/Bim/BimDocumentKeyCodec.cs` — Windows canonicalization, strict payload encoding, SHA-256 construction, and syntax validation for the approved public key-source contract; no Revit types.
- `src/Rook/Bim/BimDocumentIdentityPolicy.cs` — closed BIM-specific reader results, ordered classification, strong/legacy coherence, comparison, and expected-exception read helper; no Revit or diagnostic observer types.
- `src/Rook.Tests/Bim/BimDocumentKeyCodecTests.cs` — canonical path, byte/hash, syntax, and rejection vectors.
- `src/Rook.Tests/Bim/BimDocumentIdentityPolicyTests.cs` — executable classifier/comparator/read-count, degradation, parity, and complete truth-table tests.
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
- `mcp_server/src/rook/server.py` — admit the two optional strong-identity properties and forward them unchanged; no identity policy.
- `mcp_server/tests/test_rookbim_mcp_tools.py` — exact optional schema, legacy-envelope compatibility, unknown-source rejection, and four-consumer dictionary forwarding.
- `docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md` — narrow supersession notice for the old path-fallback/fail-open doctrine.

### Deleted file

- `src/RookBim/Revit/RevitIdentitySerializer.cs` — remove universal server-GUID reads, boolean `DocumentMatches`, fail-open matching, and scattered document/element projection.

### Explicitly unchanged

- `src/RookNative/**`
- `src/Rook/InternalBridge/**`
- `mcp_server/**` except the two files listed above
- `third_party/ffmpeg/**`
- Grasshopper/RiR lifecycle files
- dispatcher timeout and error taxonomy

---

### Task 1: Add the approved Revit-free key and identity policy without production route use

**Files:**
- Modify: `src/Rook/Bim/BimContracts.cs`
- Create: `src/Rook/Bim/BimDocumentKeyCodec.cs`
- Create: `src/Rook/Bim/BimDocumentIdentityPolicy.cs`
- Create: `src/Rook.Tests/Bim/BimDocumentKeyCodecTests.cs`
- Create: `src/Rook.Tests/Bim/BimDocumentIdentityPolicyTests.cs`

**Interfaces:**
- Produces public `BimDocumentKeySource` with exactly `Unavailable`, `RevitCreationGuidCentralPathV1`, and `RevitCreationGuidDocumentPathV1`.
- Produces `BimDocumentKeyCodec.TryCanonicalizeWindowsPath`, `TryCreate`, and `IsValid`.
- Produces closed nested `BimDocumentIdentityPolicy` types for `ReadResult<T>`, `Readers`, `CentralPath`, `Evidence`, `Claim`, `Comparison`, and `PreflightResult`, plus `CaptureRead`, `Capture`, `Compare`, and `PreflightBatch`.
- The enum, codec, and policy are a deliberately narrow cross-assembly contract from core to the optional Revit module. They are not routes, serialized DTOs, generic readers, dependency injection, or provider extension points.
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

- [ ] **Step 6: Write failing policy classification/read tests**

In `BimDocumentIdentityPolicyTests.cs`, create counting fakes for every reader and prove these exact call sets:

- file-workshared: detached, workshared, cloud, central path, and creation GUID once each; family, saved path, and server GUID never;
- Revit Server: detached, workshared, cloud, central path, and server GUID once each; creation GUID never;
- saved project: detached, workshared, family, cached document path, and creation GUID once each; cloud, central path, and server GUID never;
- failure of detached/workshared/cloud/family/central-path classification stops identity/key readers and returns unavailable;
- non-workshared classification never invokes the central-ModelPath reader;
- a returned file central path selects only `RevitCreationGuidCentralPathV1`; a saved project selects only `RevitCreationGuidDocumentPathV1`.

Add `CaptureRead` tests using a synthetic expected exception. Require one invocation, unavailable result, bounded reason, and no retained `Exception`; require an unexpected exception to rethrow unchanged. Run each successful and expected-failure getter through these two exact effective-read shapes and require equal closed results:

```csharp
using var scope = TestDiagnostics.EnabledScope("identity_policy");
Func<int> raw = () => 42;
var direct = BimDocumentIdentityPolicy.CaptureRead(
    raw, _ => false, BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
Func<int> observed = () => BimDiagnosticProbe.Production(
    scope.Context,
    BimDiagnosticStage.RevitDocumentAcquire,
    raw,
    BimDiagnosticFields.None);
var enabled = BimDocumentIdentityPolicy.CaptureRead(
    observed, _ => false, BimDocumentIdentityPolicy.UnavailableReason.KeyMaterialUnavailable);
Assert.Equal(direct.Available, enabled.Available);
Assert.Equal(direct.Value, enabled.Value);
Assert.Equal(direct.Reason, enabled.Reason);
```

Repeat with `raw` throwing the synthetic expected exception and the predicate recognizing only that type. The policy API itself must contain no diagnostic type.

- [ ] **Step 7: Write the failing comparison/preflight truth-table tests**

Use table-driven tests for every normative row in the specification. Include at minimum:

```csharp
private const string ValidFileKey =
    "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac";

private static BimDocumentIdentityPolicy.Evidence ActiveFileEvidence()
{
    return BimDocumentIdentityPolicy.Capture(
        new BimDocumentIdentityPolicy.Readers(
            () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
            () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(true),
            () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
            () => BimDocumentIdentityPolicy.ReadResult<bool>.Success(false),
            () => BimDocumentIdentityPolicy.ReadResult<string?>.Success(@"C:\LOCAL.RVT"),
            () => BimDocumentIdentityPolicy.ReadResult<BimDocumentIdentityPolicy.CentralPath>.Success(
                new BimDocumentIdentityPolicy.CentralPath(
                    BimDocumentIdentityPolicy.CentralPathKind.File,
                    @"C:\MODELS\A.RVT")),
            () => BimDocumentIdentityPolicy.ReadResult<Guid>.Success(
                Guid.ParseExact("00112233-4455-6677-8899-aabbccddeeff", "D")),
            () => BimDocumentIdentityPolicy.ReadResult<Guid>.Unavailable(
                BimDocumentIdentityPolicy.UnavailableReason.UnsupportedClass)));
}

private static BimDocumentIdentityPolicy.Claim Claim(
    string? key,
    BimDocumentKeySource source)
{
    return new BimDocumentIdentityPolicy.Claim(
        "revit", key, source, null, BimDocumentGuidSource.Unavailable,
        false, null, null, null, null, null, "element-1", 1);
}

[Theory]
[InlineData(null, BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
[InlineData("", BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
[InlineData("   ", BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
[InlineData("file-document-v1:bad", BimDocumentKeySource.RevitCreationGuidCentralPathV1)]
[InlineData(ValidFileKey, BimDocumentKeySource.Unavailable)]
public void Compare_IncoherentStrongEvidence_IsInvalid(
    string? key, BimDocumentKeySource source)
{
    Assert.Equal(
        BimDocumentIdentityPolicy.Comparison.InvalidEvidence,
        BimDocumentIdentityPolicy.Compare(ActiveFileEvidence(), Claim(key, source)));
}
```

Legacy GUID tests require exact non-empty `D` form: length 36, `Guid.TryParseExact(value, "D", out var parsed)`, `parsed != Guid.Empty`, and no trimming. Prove uppercase/lowercase `D` text is accepted, while braces, 32-character `N` form, leading/trailing whitespace, malformed text, and `00000000-0000-0000-0000-000000000000` are invalid. Prove coherent nonblank `path_fallback` returns unavailable, not match.

Add `PreflightBatch` tests for the exact order: null entry, linked evidence (including an empty/whitespace linked string), coherence, document comparison, then locator validation. Put a valid first entry and invalid second entry in a batch; require the second index and failure outcome. `PreflightBatch` performs no lookup and exposes no lookup callback.

- [ ] **Step 8: Run policy tests red**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter FullyQualifiedName~BimDocumentIdentityPolicyTests --verbosity minimal
```

Expected: FAIL because `BimDocumentIdentityPolicy` does not exist.

- [ ] **Step 9: Implement the closed BIM-specific policy**

Create one public static class with only these nested BIM-specific types and methods:

```csharp
public static class BimDocumentIdentityPolicy
{
    public enum DocumentClass
    {
        FileWorkshared, RevitServer, CloudWorkshared, SavedProject,
        SavedFamily, UnsavedProject, UnsavedFamily, Detached, Unknown
    }

    public enum UnavailableReason
    {
        None, DiscriminatorUnavailable, KeyMaterialUnavailable, UnsupportedClass
    }

    public enum CentralPathKind { File, Server, Cloud }
    public enum Comparison { Match, Mismatch, Unavailable, InvalidEvidence }
    public enum PreflightOutcome
    {
        Valid, InvalidEvidence, LinkedElementUnsupported,
        Mismatch, Unavailable, ElementLocatorInvalid
    }

    public readonly struct ReadResult<T>
    {
        public bool Available { get; }
        public T Value { get; }
        public UnavailableReason Reason { get; }
        public static ReadResult<T> Success(T value);
        public static ReadResult<T> Unavailable(UnavailableReason reason);
    }

    public readonly struct CentralPath
    {
        public CentralPath(CentralPathKind kind, string? filePath);
        public CentralPathKind Kind { get; }
        public string? FilePath { get; }
    }

    public sealed class Readers
    {
        public Readers(
            Func<ReadResult<bool>> readIsDetached,
            Func<ReadResult<bool>> readIsWorkshared,
            Func<ReadResult<bool>> readIsModelInCloud,
            Func<ReadResult<bool>> readIsFamilyDocument,
            Func<ReadResult<string?>> readDocumentPath,
            Func<ReadResult<CentralPath>> readCentralModelPath,
            Func<ReadResult<Guid>> readCreationGuid,
            Func<ReadResult<Guid>> readServerCentralGuid);
        public Func<ReadResult<bool>> ReadIsDetached { get; }
        public Func<ReadResult<bool>> ReadIsWorkshared { get; }
        public Func<ReadResult<bool>> ReadIsModelInCloud { get; }
        public Func<ReadResult<bool>> ReadIsFamilyDocument { get; }
        public Func<ReadResult<string?>> ReadDocumentPath { get; }
        public Func<ReadResult<CentralPath>> ReadCentralModelPath { get; }
        public Func<ReadResult<Guid>> ReadCreationGuid { get; }
        public Func<ReadResult<Guid>> ReadServerCentralGuid { get; }
    }

    public sealed class Evidence
    {
        public DocumentClass Class { get; }
        public string? DocumentKey { get; }
        public BimDocumentKeySource DocumentKeySource { get; }
        public Guid? LegacyGuid { get; }
        public BimDocumentGuidSource LegacyGuidSource { get; }
        public UnavailableReason Reason { get; }
    }

    public sealed class Claim
    {
        public Claim(
            string? source,
            string? documentKey,
            BimDocumentKeySource documentKeySource,
            string? documentGuid,
            BimDocumentGuidSource documentGuidSource,
            bool linked,
            int? linkInstanceId,
            string? linkInstanceUniqueId,
            string? linkedDocumentGuid,
            int? linkedElementId,
            string? linkedElementUniqueId,
            string? uniqueId,
            int? elementId);
        public string? Source { get; }
        public string? DocumentKey { get; }
        public BimDocumentKeySource DocumentKeySource { get; }
        public string? DocumentGuid { get; }
        public BimDocumentGuidSource DocumentGuidSource { get; }
        public bool Linked { get; }
        public int? LinkInstanceId { get; }
        public string? LinkInstanceUniqueId { get; }
        public string? LinkedDocumentGuid { get; }
        public int? LinkedElementId { get; }
        public string? LinkedElementUniqueId { get; }
        public string? UniqueId { get; }
        public int? ElementId { get; }
    }

    public readonly struct PreflightResult
    {
        public PreflightOutcome Outcome { get; }
        public int? ItemIndex { get; }
    }

    public static ReadResult<T> CaptureRead<T>(
        Func<T> read,
        Func<Exception, bool> isExpected,
        UnavailableReason failureReason);
    public static Evidence Capture(Readers readers);
    public static Comparison Compare(Evidence active, Claim incoming);
    public static PreflightResult PreflightBatch(
        Evidence active,
        IReadOnlyList<Claim?> claims);
}
```

`Readers` contains exactly `ReadIsDetached`, `ReadIsWorkshared`, `ReadIsModelInCloud`, `ReadIsFamilyDocument`, `ReadDocumentPath`, `ReadCentralModelPath`, `ReadCreationGuid`, and `ReadServerCentralGuid`. It is a closed constructor-initialized bundle, not an interface or service locator. `CentralPath` contains only kind plus the converted file path when kind is file; it never contains `ModelPath` or a host delegate.

Implement the specification's branch order literally. `CaptureRead` catches only when `isExpected(exception)` is true, returns unavailable without retaining the exception, and otherwise uses `throw;`. `Compare` implements the complete coherence and active-evidence tables. `PreflightBatch` validates all claims without lookup and returns the first failure by input index. Do not reference diagnostics from this file.

- [ ] **Step 10: Run focused and full core tests green**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter "FullyQualifiedName~BimDocumentKeyCodecTests|FullyQualifiedName~BimDocumentIdentityPolicyTests" `
  --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
```

Expected: all pass.

- [ ] **Step 11: Prove the preparatory surface is unused and commit**

```powershell
$uses = @(rg -n "BimDocumentKeyCodec|BimDocumentIdentityPolicy" src/Rook src/RookBim -g '*.cs' |
  Where-Object { $_ -notmatch 'BimDocumentKeyCodec.cs|BimDocumentIdentityPolicy.cs' })
if ($uses.Count -ne 0) { throw "Task 1 policy entered a production route" }
if (rg -n "BimDiagnostic|IServiceProvider|ServiceCollection|Dictionary<.*Document|Json(Property|Converter)|DataContract" `
    src/Rook/Bim/BimDocumentIdentityPolicy.cs) {
    throw "Policy acquired diagnostics, DI, cache, or serialization state"
}
git diff --check
git add -- src/Rook/Bim/BimContracts.cs src/Rook/Bim/BimDocumentKeyCodec.cs `
  src/Rook/Bim/BimDocumentIdentityPolicy.cs `
  src/Rook.Tests/Bim/BimDocumentKeyCodecTests.cs `
  src/Rook.Tests/Bim/BimDocumentIdentityPolicyTests.cs
git commit -m "feat(rookbim): add closed document identity policy"
```

Expected: one behavior-neutral preparatory commit with no DTO field or route change.

---

### Task 2: Atomically cut every production identity path to one resolver

**Files:**
- Create/modify/delete every Task 2 file listed in the file map.

**Interfaces:**
- Consumes `BimDocumentKeyCodec`, `BimDocumentIdentityPolicy`, and the merged gated-diagnostic probe/session API from Task 1 and the execution base.
- Produces exact wire fields `documentKey`, `documentKeySource`, `document_identity_unavailable`, and `document_identity_invalid`.
- Produces one `RevitDocumentIdentityEvidence` capture per operation and uses the policy's closed comparison/preflight outcomes.
- Produces `RevitQueryExecutionResult` with a wire DTO plus same-operation live elements.
- Produces optional MCP `documentKey`/`documentKeySource` schema fields and unchanged dictionary forwarding through all four identity consumers.

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
"documentKey":"file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac",
"documentKeySource":"revit_creation_guid_central_path_v1"
```

Add handler tests mapping `DocumentIdentityUnavailable` to `document_identity_unavailable`/409 and `DocumentIdentityInvalid` to `document_identity_invalid`/400.

- [ ] **Step 2: Write failing MCP schema and forwarding tests**

In `test_rookbim_mcp_tools.py`, add `import json`, add `documentKey` and `documentKeySource` to `IDENTITY_FIELDS`, and assert:

```python
identity = schema["properties"]["identity"]
assert identity["properties"]["documentKey"] == {"type": ["string", "null"]}
assert identity["properties"]["documentKeySource"] == {
    "type": "string",
    "enum": [
        "revit_creation_guid_central_path_v1",
        "revit_creation_guid_document_path_v1",
        "unavailable",
    ],
}
assert "documentKey" not in identity["required"]
assert "documentKeySource" not in identity["required"]
assert identity["required"] == ["documentGuidSource"]
assert "pattern" not in identity["properties"]["documentKey"]
assert identity["additionalProperties"] is False
```

Retain a legacy fixture containing only `documentGuidSource: unavailable` and prove it still dispatches. Add one representative strong identity dictionary and parameterize exact forwarding through `rookbim_element_info`, `rookbim_element_parameters`, `rookbim_select_elements`, and `rookbim_export_elements` with `identities`. Mock `call_rhino`, extract the nested forwarded identity, and require both dictionary equality and equal compact UTF-8 JSON bytes:

```python
before = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
after = json.dumps(forwarded_identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
assert forwarded_identity == identity
assert after == before
```

Do not add Python key regex, prefix/source pairing, GUID parsing, normalization, or downgrade tests; those are managed policy tests.

- [ ] **Step 3: Write failing optional-module source contracts**

Keep source tests to isolation/structure that managed tests cannot exercise. Use the existing lexer/member-extraction helpers, not whitespace matching. Require:

- only `RevitDocumentIdentityResolver.cs` contains `WorksharingCentralGUID`;
- no production file contains `WorksharingProjectGUID` or `CloudModelGUID`;
- the server GUID read is dominated by `ModelPath.ServerPath == true` and cannot execute for file/cloud branches;
- file-workshared and saved-project branches independently read `CreationGUID` and their approved path source;
- `PathName` is read once into one local closed result, and that local supplies both saved-project policy input and display projection;
- each invoked discriminator stores one closed local result reused by display projection; no display property triggers a second host read;
- the central-ModelPath callback is invoked only by the policy and cannot run on the non-workshared branch;
- each Revit property read has its own availability boundary;
- `InternalException` is in the expected-exception allowlist;
- diagnostics appear only in the Revit adapter/read wrapper and never in `BimDocumentIdentityPolicy.cs`;
- `DocumentMatches`, `GetWorksharingCentralGUID`, and every old `RevitIdentitySerializer.DocumentIdentity/ElementIdentity/Resolve` invocation are absent;
- each runtime operation captures evidence once and passes that same local to consumers/projections;
- identity batches complete every comparison before the first `GetElement`, `SetElementIds`, export conversion, or file write;
- selector and preset paths consume `RevitQueryExecutionResult.Elements` directly;
- preset dedup uses `ElementId.Value` after the owner-reference check;
- no Autodesk `Element`, `Document`, or `ModelPath` type appears anywhere in `src/Rook`; policy `Evidence`/`Claim` types do not appear as properties of serialized DTOs in `BimContracts.cs`;
- old serializer file is deleted and the view-only serializer has no document GUID/path logic.

Do not use source text to assert runtime equality, hashing, exception behavior, or path semantics; those belong to delegate/core tests and live Revit.

- [ ] **Step 4: Run the focused tests red**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter "FullyQualifiedName~RookBimContractsTests|FullyQualifiedName~BimHandlerTests|FullyQualifiedName~BimDiagnosticJsonEncoderTests" `
  --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore `
  --filter FullyQualifiedName~Identity --verbosity minimal
python -m pytest mcp_server/tests/test_rookbim_mcp_tools.py -q
```

Expected: FAIL on missing contracts, resolver cutover, and MCP fields.

- [ ] **Step 5: Add exact wire/error and diagnostic contracts**

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

- [ ] **Step 6: Implement the minimal MCP schema cutover**

In `_rookbim_identity_schema`, add exactly:

```python
"documentKey": {"type": ["string", "null"]},
"documentKeySource": {
    "type": "string",
    "enum": [
        "revit_creation_guid_central_path_v1",
        "revit_creation_guid_document_path_v1",
        "unavailable",
    ],
},
```

Do not add either field to `required`; retain `required: ["documentGuidSource"]` and `additionalProperties: false`. Do not modify tool dispatch: its existing dictionary forwarding is the desired implementation. Do not add `pattern`, `minLength`, parsing, normalization, or helper policy in Python.

Run the focused MCP file immediately:

```powershell
python -m pytest mcp_server/tests/test_rookbim_mcp_tools.py -q
```

Expected: all focused MCP tests pass, including legacy envelopes and all four exact forwarding cases.

- [ ] **Step 7: Implement the thin operation-scoped Revit adapter**

Create these internal shapes in `RevitDocumentIdentityResolver.cs`:

```csharp
internal sealed class RevitDocumentIdentityEvidence
{
    internal Document Owner { get; }
    internal BimDocumentIdentityPolicy.Evidence Identity { get; }
    internal string? Title { get; }
    internal string? Path { get; }
    internal bool IsFamilyDocument { get; }
    internal bool IsWorkshared { get; }
}
```

The evidence constructor copies scalar/string values and the owning `Document` reference only. It stores no `ModelPath`, delegate, exception, diagnostic context, or mutable collection.

`RevitDocumentIdentityResolver.Capture(Document, BimDiagnosticContext)` first reads `Title` and `PathName` independently into closed adapter results. `PathName` is called exactly once. Its one result supplies both compatibility `Path` projection and the policy's `ReadDocumentPath` callback; do not call the host property again. Each discriminator callback likewise stores its one closed result in an operation-local variable so `IsWorkshared`/`IsFamilyDocument` display projection never rereads the host. These locals are not a cache and do not outlive `Capture`.

Build the exact eight-callback `BimDocumentIdentityPolicy.Readers` bundle. Each callback selects one effective getter:

```csharp
Func<T> effectiveRead = diagnostics.Enabled
    ? () => BimDiagnosticProbe.Production(
        diagnostics, stage, getter, BimDiagnosticFields.None)
    : getter;
return BimDocumentIdentityPolicy.CaptureRead(
    effectiveRead,
    IsExpectedIdentityException,
    failureReason);
```

Diagnostics and Revit exception typing stay entirely in this adapter. `IsExpectedIdentityException` recognizes exactly `InapplicableDataException`, Revit `InvalidOperationException`, `InternalException`, `InvalidObjectException`, Revit `ArgumentException`, and Revit `ArgumentNullException`. Unexpected exceptions rethrow unchanged. The core policy never receives `BimDiagnosticContext`, a diagnostic observer, an Autodesk type, or an exception.

The central-path callback is the only code that calls `GetWorksharingCentralModelPath()`. It runs only when the policy reaches the successfully classified workshared branch. It classifies the returned `ModelPath` once; cloud returns `CentralPathKind.Cloud`, server returns `CentralPathKind.Server`, and file converts once with `ModelPathUtils.ConvertModelPathToUserVisiblePath` and returns `CentralPathKind.File` plus the converted string. It never returns or retains `ModelPath`.

The policy owns this exact identity branch order: detached/workshared; cloud only for workshared; central path only for workshared/non-cloud; family only for non-workshared; cached `PathName` only for saved-project identity; then class-specific GUID/key material. Any unavailable discriminator stops identity classification/key reads without falling into another class. Independent title/path display results remain available for producer projection.

- [ ] **Step 8: Implement projection, policy mapping, and lookup authorization**

Add resolver methods with these responsibilities:

```csharp
internal BimDocumentIdentity ProjectDocument(RevitDocumentIdentityEvidence evidence);
internal BimElementIdentity ProjectElement(
    RevitDocumentIdentityEvidence evidence, Element element);
internal BimDocumentIdentityPolicy.Claim CreateClaim(BimElementIdentity identity);
internal BimElementResolveResult ResolveAfterPreflight(
    RevitDocumentIdentityEvidence evidence, BimElementIdentity identity);
```

`ProjectDocument` copies the versioned key/source, compatibility title/path, class booleans, and actual legacy Revit Server GUID only. File/saved-project `CreationGUID` never enters `Guid`.

`ProjectElement` first requires `ReferenceEquals(element.Document, evidence.Owner)`, then copies the snapshot's document key/source and approved legacy projection. It never recaptures document evidence.

`CreateClaim` copies the raw DTO fields needed by the policy, including every linked-evidence and locator field. It performs no normalization and does not turn whitespace into absence. Unknown `documentKeySource` strings remain ordinary serializer/binding HTTP 400 failures; add no converter.

Use `BimDocumentIdentityPolicy.PreflightBatch` as the only document-evidence decision. Map `Mismatch` to `document_mismatch`/409, `Unavailable` to `document_identity_unavailable`/409, `InvalidEvidence` and a null entry to `document_identity_invalid`/400, `LinkedElementUnsupported` to the existing linked error, and `ElementLocatorInvalid` to the existing element-not-found contract.

Preflight order is exact: null entry, any linked evidence, key/source/legacy coherence, active-document comparison, then locator validation. Legacy persistent GUID validity is the policy's exact non-empty `D`-format rule; no adapter uses `Guid.TryParse` or trims the value.

`ResolveAfterPreflight` is callable only after the entire batch returns valid. It performs no document comparison or evidence reread. It preserves UniqueId-first and ElementId-only-when-UniqueId-absent lookup semantics and never turns unavailable evidence into a match.

Delete `RevitIdentitySerializer.cs`. Move only `ViewIdentity` and its view-specific helpers to `RevitViewIdentitySerializer.cs`.

- [ ] **Step 9: Cut producer and consumer operations over atomically**

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

For selection and identity-list export, first map the entire input—including null entries—to policy claims, then call `PreflightBatch` once. If it fails, return the first indexed failure before any `GetElement`, selection change, geometry conversion, or output creation. Only after the whole batch passes may the second pass resolve every element; only after all resolutions succeed may selection/export side effects begin. Do not recompare or reread document evidence during resolution.

For producing routes, an unavailable snapshot still projects `documentKey=null`, `documentKeySource=unavailable` and returns the route's otherwise normal status.

- [ ] **Step 10: Replace selector/preset identity round-trips with trusted live elements**

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

- [ ] **Step 11: Update doctrine and delete obsolete tests/code**

Add a notice to the Phase 1 design stating that the approved July 28 identity design supersedes path-fallback/non-stable and fail-open matching language. Link to the approved spec.

Delete tests that require unavailable document evidence to match, forbid executable versioned fallback identity, or require universal `WorksharingCentralGUID`. Replace them with the exact initial source set, downgrade prevention, server-only legacy rule, cloud no-call rule, snapshot reuse, batch-preflight, and trusted-live-element source contracts.

Do not retain deprecated code behind a fallback switch.

- [ ] **Step 12: Run focused and complete tests/builds**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter "FullyQualifiedName~BimDocumentKey|FullyQualifiedName~BimDocumentIdentityPolicy|FullyQualifiedName~RookBimContracts|FullyQualifiedName~BimHandler|FullyQualifiedName~BimDiagnostic" `
  --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
python -m pytest mcp_server/tests/test_rookbim_mcp_tools.py -q

$guard = Join-Path $env:TEMP ("rook-identity-no-deploy-" + [guid]::NewGuid().ToString("N"))
if (Test-Path $guard) { throw "Guard path already exists" }
dotnet build src\Rook\Rook.csproj --configuration Release --no-restore --verbosity minimal `
  -p:RhinoPluginDir=$guard
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal `
  -p:RhinoPluginDir=$guard
if (Test-Path $guard) { throw "Guarded build attempted deployment" }
```

Expected: all managed and focused MCP tests pass; both builds exit zero; installed plugin and AppData MCP runtime are untouched.

- [ ] **Step 13: Run production/source/privacy scans**

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
if (rg -n "BimDiagnostic|IServiceProvider|ServiceCollection|static.*Dictionary|Json(Property|Converter)|DataContract" `
    src/Rook/Bim/BimDocumentIdentityPolicy.cs) {
    throw "Policy acquired diagnostics, DI, cache, or serialization state"
}
if (rg -n '\["(documentKey|documentPath|documentGuid|title|path|guid)"\]|\.DocumentKey\b|\.DocumentPath\b|\.DocumentGuid\b|\.CreationGUID\b|rawPath|normalizedPath' `
    src/Rook/Bim/Diagnostics -g '*.cs') {
    throw "Sensitive identity value entered diagnostic persistence"
}
$mcpChanged = @(git diff --name-only -- mcp_server)
if (@($mcpChanged | Where-Object {
    $_ -notin @('mcp_server/src/rook/server.py','mcp_server/tests/test_rookbim_mcp_tools.py')
}).Count -ne 0) { throw "Unrelated MCP file changed" }
git diff --check
```

Review `git diff --stat` and `git diff --name-only` against the Task 2 file map. Require exactly the two approved MCP files when MCP is filtered. Reject native, Grasshopper, FFmpeg, dispatcher-timeout, taxonomy, unrelated MCP, or unrelated export changes.

- [ ] **Step 14: Commit one atomic behavior change**

Stage explicit Task 2 paths only and commit:

```powershell
git add -- `
  src/Rook/Bim/BimContracts.cs `
  src/Rook/Bim/Diagnostics/BimDiagnosticContracts.cs `
  src/Rook/Bim/Diagnostics/BimDiagnosticJsonEncoder.cs `
  src/Rook/Handlers/BimHandler.cs `
  src/RookBim/Revit/RevitDocumentIdentityResolver.cs `
  src/RookBim/Revit/RevitQueryExecutionResult.cs `
  src/RookBim/Revit/RevitViewIdentitySerializer.cs `
  src/RookBim/Revit/RevitIdentitySerializer.cs `
  src/RookBim/Revit/RevitRookBimRuntime.cs `
  src/RookBim/Revit/RevitCategoryResolver.cs `
  src/RookBim/Revit/RevitQueryService.cs `
  src/RookBim/Revit/RevitSelectionService.cs `
  src/RookBim/Revit/RevitExportService.cs `
  src/RookBim/Revit/RevitPresetResolver.cs `
  src/Rook.Tests/Bim/RookBimContractsTests.cs `
  src/Rook.Tests/Handlers/BimHandlerTests.cs `
  src/Rook.Tests/Handlers/BimHandlerDiagnosticsTests.cs `
  src/Rook.Tests/Bim/Diagnostics/BimDiagnosticJsonEncoderTests.cs `
  src/RookBim.Tests/RookBimModuleSourceTests.cs `
  src/RookBim.Tests/RookBimExportSourceTests.cs `
  src/RookBim.Tests/RookBimExportPresetSourceTests.cs `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_rookbim_mcp_tools.py `
  docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md
git commit -m "fix(rookbim): enforce document identity"
```

The managed cutover, MCP schema/tests, Revit adapter, removal of old writers/matcher, live-element trust path, tests, and doctrine must land together. Do not deploy an intermediate subset.

---

### Task 3: Whole-branch review and committed deployment

**Files:**
- Review: all Task 1-2 files.
- Do not modify production code in this task.

**Interfaces:**
- Consumes the two reviewed commits.
- Produces one verified pre-deploy rollback ZIP/SHA sidecar and installed managed/MCP artifacts whose inventories and hashes match committed source.

- [ ] **Step 1: Run a whole-branch review**

Compare the implementation base through Task 2 head. Per-task reviews do not replace this gate. Verify:

```powershell
$task2Head = (git rev-parse HEAD).Trim()
$task1Commit = (git rev-parse HEAD^).Trim()
$implementationBase = (git rev-parse HEAD^^).Trim()
git log --oneline --decorate $implementationBase..$task2Head
git diff --check $implementationBase..$task2Head
git diff --stat $implementationBase..$task2Head
git diff --name-status $implementationBase..$task2Head
```

Require exactly one behavior-neutral Task 1 commit and one atomic Task 2 commit above the authorized base. Stop if ancestry or commit count differs from the reviewed execution ledger.

- the approved class/source matrix is exhaustive;
- file/cloud paths cannot reach the server getter;
- no strong-key downgrade exists;
- all batches preflight before lookup/side effects;
- one snapshot flows through each operation;
- selector/preset live elements cannot cross an API/request boundary;
- expected failure degradation is identical with diagnostics disabled/enabled;
- the policy has no diagnostic, DI, generic-provider, cache, or Revit dependency;
- the closed MCP schema admits both optional strong fields, preserves legacy envelopes, and forwards dictionaries unchanged through all four consumers;
- every obsolete identity branch/test is removed;
- no unrelated subsystem changed.

If review finds a defect, return to Task 2 under an explicitly authorized safety wave, commit the complete correction, and repeat the whole-branch review. Do not patch after deployment.

- [ ] **Step 2: Repeat final tests and guarded Release builds**

At reviewed head, run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore `
  --filter "FullyQualifiedName~BimDocumentKey|FullyQualifiedName~BimDocumentIdentityPolicy|FullyQualifiedName~RookBimContracts|FullyQualifiedName~BimHandler|FullyQualifiedName~BimDiagnostic" `
  --verbosity minimal
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --configuration Release --no-restore --verbosity minimal
dotnet test src\Rook.Tests\Rook.Tests.csproj --configuration Release --no-restore --verbosity minimal
python -m pytest mcp_server/tests/test_rookbim_mcp_tools.py -q

$guard = Join-Path $env:TEMP ("rook-identity-final-no-deploy-" + [guid]::NewGuid().ToString('N'))
if (Test-Path $guard) { throw 'Guard path already exists' }
dotnet build src\Rook\Rook.csproj --configuration Release --no-restore --verbosity minimal `
  -p:RhinoPluginDir=$guard
dotnet build src\RookBim\RookBim.csproj --configuration Release --no-restore --verbosity minimal `
  -p:RhinoPluginDir=$guard
if (Test-Path $guard) { throw 'Guarded build attempted deployment' }
if (git status --short) { throw 'Reviewed implementation worktree is not clean' }
```

Record exact managed/MCP counts, build warnings/errors, and `$task2Head` in the execution ledger.

- [ ] **Step 3: Close hosts and create the exact rollback artifact**

Close Revit, Rhino, Grasshopper, and every `python -m rook` process. Confirm all counts are zero. Then snapshot the current installed plugin plus both installed MCP package copies before deployment:

```powershell
$implementationCommit = (git rev-parse HEAD).Trim()
$local = [Environment]::GetFolderPath('LocalApplicationData')
$roaming = [Environment]::GetFolderPath('ApplicationData')
$rollbackRoot = Join-Path $local 'Rook\rollback\rookbim-file-workshared-identity'
$stage = Join-Path $rollbackRoot ("stage-" + $implementationCommit)
$rollbackZip = Join-Path $rollbackRoot ("rookbim-identity-predeploy-" + $implementationCommit + ".zip")
$rollbackShaFile = $rollbackZip + '.sha256'
$pluginDir = Join-Path $roaming 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
$appRook = Join-Path $local 'Rook\app\mcp_server\src\rook'
$venvRook = Join-Path $local 'Rook\venv\Lib\site-packages\rook'

foreach ($path in @($pluginDir, $appRook, $venvRook)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Rollback source missing: $path"
    }
}
if ((Test-Path -LiteralPath $stage) -or (Test-Path -LiteralPath $rollbackZip) -or
    (Test-Path -LiteralPath $rollbackShaFile)) {
    throw 'Refusing to overwrite an existing rollback artifact'
}

$rollbackRootFull = [IO.Path]::GetFullPath($rollbackRoot).TrimEnd('\')
$stageFull = [IO.Path]::GetFullPath($stage)
if (-not $stageFull.StartsWith($rollbackRootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Rollback stage escaped the dedicated rollback root'
}

New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath $pluginDir -Destination (Join-Path $stage 'plugin') -Recurse
Copy-Item -LiteralPath $appRook -Destination (Join-Path $stage 'app-rook') -Recurse
Copy-Item -LiteralPath $venvRook -Destination (Join-Path $stage 'venv-rook') -Recurse

$payload = @(Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object {
    [pscustomobject]@{
        path = $_.FullName.Substring($stageFull.TrimEnd('\').Length + 1).Replace('\','/')
        length = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
})
$metadata = [ordered]@{
    artifactType = 'rookbim-file-workshared-identity-predeploy-v1'
    implementationCommit = $implementationCommit
    capturedUtc = [DateTime]::UtcNow.ToString('O')
    pluginProductVersion = (Get-Item (Join-Path $pluginDir 'net8.0\Rook.rhp')).VersionInfo.ProductVersion
    bimProductVersion = (Get-Item (Join-Path $pluginDir 'net48\RookBim.dll')).VersionInfo.ProductVersion
    payload = $payload
}
$metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stage 'manifest.json') -Encoding UTF8
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $rollbackZip -CompressionLevel Optimal
$rollbackSha = (Get-FileHash -LiteralPath $rollbackZip -Algorithm SHA256).Hash
Set-Content -LiteralPath $rollbackShaFile -Value ($rollbackSha + '  ' + (Split-Path -Leaf $rollbackZip)) -Encoding ASCII
Remove-Item -LiteralPath $stage -Recurse -Force

if ((Get-FileHash -LiteralPath $rollbackZip -Algorithm SHA256).Hash -ne
    ((Get-Content -LiteralPath $rollbackShaFile -Raw).Trim().Split(' ')[0])) {
    throw 'Rollback ZIP SHA verification failed'
}
Write-Host "RollbackArtifact=$rollbackZip"
Write-Host "RollbackSHA256=$rollbackSha"
```

Record the exact ZIP path and SHA-256 in the execution ledger. This is a byte-exact recovery artifact, not a claim that the pre-deploy fail-open identity behavior is safe.

- [ ] **Step 4: Deploy only reviewed head**

With Revit, Rhino, Grasshopper, and exact `python -m rook` processes closed, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\deploy-local-testing.ps1 -Configuration Release
```

Do not use `setx`. Do not start live acceptance until deploy completes.

- [ ] **Step 5: Verify installed provenance and inventories**

Compare source/deploy inventories and SHA-256 for runtime-bearing files in `net8.0`, `net7.0`, and `net48`, including `Rook.rhp`, managed dependencies, runtime subtrees, and `RookBim.dll`. Detect missing, mismatched, and stale extra files.

Also compare the repository `mcp_server/src/rook` tree against both `%LOCALAPPDATA%\Rook\app\mcp_server\src\rook` and `%LOCALAPPDATA%\Rook\venv\Lib\site-packages\rook`. Exclude only `__pycache__`, `.pyc`, and `.pyo`; require identical relative paths, lengths, and SHA-256 for every other file. Require `server.py` to match in all three locations and run:

```powershell
function Get-HashInventory([string]$root, [scriptblock]$include) {
    $fullRoot = [IO.Path]::GetFullPath($root).TrimEnd('\')
    if (-not (Test-Path -LiteralPath $fullRoot -PathType Container)) {
        throw "Inventory root missing: $fullRoot"
    }
    return @(Get-ChildItem -LiteralPath $fullRoot -Recurse -File |
        Where-Object { & $include $_ $fullRoot } |
        ForEach-Object {
            [pscustomobject]@{
                path = $_.FullName.Substring($fullRoot.Length + 1).Replace('\','/').ToLowerInvariant()
                length = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            }
        } | Sort-Object path)
}

function Assert-SameInventory([object[]]$expected, [object[]]$actual, [string]$label) {
    $difference = @(Compare-Object $expected $actual -Property path,length,sha256)
    if ($difference.Count -ne 0) {
        $difference | Format-Table | Out-String | Write-Host
        throw "Inventory mismatch: $label"
    }
}

$pluginDir = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
$managedInclude = {
    param($file, $root)
    $relative = $file.FullName.Substring($root.Length + 1).Replace('\','/')
    return $relative -match '^(Rook\.rhp|Rook\.rui|Rook\.deps\.json|Rook\.runtimeconfig\.json|[^/]+\.dll|runtimes/.+)$'
}
foreach ($runtime in @('net8.0','net7.0','net48')) {
    $source = Join-Path (Get-Location) "src\Rook\bin\Release\$runtime"
    $installed = Join-Path $pluginDir $runtime
    Assert-SameInventory `
        (Get-HashInventory $source $managedInclude) `
        (Get-HashInventory $installed $managedInclude) `
        "managed-$runtime"
}

$pythonInclude = {
    param($file, $root)
    $relative = $file.FullName.Substring($root.Length + 1).Replace('\','/')
    return $relative -notmatch '(^|/)__pycache__/|\.(pyc|pyo)$'
}
$sourceRook = Join-Path (Get-Location) 'mcp_server\src\rook'
$appRook = Join-Path $env:LOCALAPPDATA 'Rook\app\mcp_server\src\rook'
$venvRook = Join-Path $env:LOCALAPPDATA 'Rook\venv\Lib\site-packages\rook'
$sourceInventory = Get-HashInventory $sourceRook $pythonInclude
Assert-SameInventory $sourceInventory (Get-HashInventory $appRook $pythonInclude) 'mcp-app-source'
Assert-SameInventory $sourceInventory (Get-HashInventory $venvRook $pythonInclude) 'mcp-site-packages'

& "$env:LOCALAPPDATA\Rook\venv\Scripts\python.exe" -c `
  "import pathlib, rook.server; print(pathlib.Path(rook.server.__file__).resolve())"
```

Require the printed path to be under `%LOCALAPPDATA%\Rook\venv\Lib\site-packages\rook`. After the next launch, confirm `/bim/status` reports the Task 2 head for core and module. Record the rollback ZIP path/SHA and every installed inventory result before beginning Task 4.

---

### Task 4: Operator-assisted Revit identity acceptance and redacted report

**Files:**
- Create after the matrix reaches a pass or a bounded blocker/rollback decision: `docs/superpowers/reports/2026-07-28-rookbim-file-workshared-identity-acceptance.md`
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

On a disposable file-workshared local with a graphical 3D view, call status, active document, categories, and active-view query. Run the query through the public MCP tool and retain its returned identity dictionary only in memory.

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

For each simultaneous-document mismatch, produce an identity in A through MCP, activate B, and pass that exact dictionary without reconstruction through MCP element info, parameters, selection, and identity-list export. Require HTTP 409 before `GetElement`, selection change, geometry conversion, or output creation. Switch back to the matching document and require all four consumers to succeed.

For the same-path cases, perform this exact sequence:

1. Open the original at disposable canonical path P and capture one MCP query identity.
2. Close the document and verify its Revit file handle is released.
3. Place a same-lineage copy at P, reopen P, and require the original dictionary to succeed through all four MCP consumers.
4. Close the document and verify the file handle is released again.
5. Replace P with a different-lineage document, reopen P, and require the original dictionary to fail through all four consumers before lookup or side effects.

- [ ] **Step 4: Run saved-project and unavailable-class cases**

Require:

- saved non-workshared project and its reopen use stable `revit_creation_guid_document_path_v1`;
- a different project replacing that path uses a different key;
- saved family, fresh unsaved project, fresh unsaved family, detached document, and cloud document (when infrastructure exists) emit `documentKey=null`, source `unavailable`;
- caller-supplied identity operations on unavailable classes return HTTP 409 `document_identity_unavailable` before lookup/side effects;
- valid enum values with whitespace/malformed/source-conflicting keys return HTTP 400 `document_identity_invalid` without downgrade;
- unknown `documentKeySource` text is allowed to fail at ordinary MCP/HTTP schema or enum binding with HTTP 400; no special error-name claim is required;
- legacy persistent GUID text accepts only exact non-empty 36-character `D` format without trimming; braces, `N` format, whitespace, malformed text, and empty GUID are invalid;
- raw matching title/path never changes those results.

If Revit Server infrastructure is available, verify only the no-key legacy persistent GUID flow and confirm no versioned server key is emitted. If unavailable, record the fixture limitation; do not simulate approval.

- [ ] **Step 5: Prove trusted selector/preset paths remain available**

For every unavailable class that supports ordinary query/export preconditions, require selector and preset export to consume same-operation live elements without identity re-resolution. Verify each element belongs by reference to the captured document, no live reference survives the operation, and no output is produced from another document.

Identity-list export remains fail closed on the same fixture. Use a disposable output directory and verify missing output on every rejected request.

- [ ] **Step 6: Repeat parity with diagnostics disabled**

Close Revit. Launch a fresh process without `ROOK_BIM_DIAGNOSTICS`, reload the same controlled cases, and repeat representative producer, MCP round-trip match/mismatch, unavailable, invalid, selector-export, and identity-list-export calls.

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
- rollback ZIP path normalized under `%LOCALAPPDATA%\Rook\rollback\rookbim-file-workshared-identity`, exact filename/implementation commit, SHA-256, and successful pre-deploy artifact verification;
- repository/AppData/site-packages MCP inventory equality and all four public round-trip outcomes;
- aliases and equality/mismatch outcomes only;
- every document class attempted and any infrastructure limitation;
- route/status/error/side-effect outcomes;
- diagnostics enabled/disabled parity;
- JSONL validity, bounds, drop/completeness, and privacy scan;
- Revit-journal absence of the prior native getter warning;
- final pass/block decision and rollback state.

On a blocker, execute the exact Rollback section below with hosts closed before finalizing the report. Record the restored ZIP SHA, inventory verification, and smoke outcome; do not convert a rollback into a pass.

```powershell
git diff --check
git add -- docs/superpowers/reports/2026-07-28-rookbim-file-workshared-identity-acceptance.md
git commit -m "docs: record RookBIM identity acceptance"
```

## Rollback

Do not partially roll back the managed contract, policy, Revit adapter, MCP package, or comparator. This repository has no tested runtime switch that disables only identity-based routes, so this plan makes no such claim.

If Task 4 blocks the release, keep Revit, Rhino, Grasshopper, and every `python -m rook` process closed. Restore only the verified Task 3 artifact; do not rebuild an assumed baseline or run the deploy script from a different checkout.

```powershell
$implementationCommit = (git log -1 --format=%H -- src/RookBim/Revit/RevitDocumentIdentityResolver.cs).Trim()
$local = [Environment]::GetFolderPath('LocalApplicationData')
$roaming = [Environment]::GetFolderPath('ApplicationData')
$rollbackRoot = Join-Path $local 'Rook\rollback\rookbim-file-workshared-identity'
$rollbackZip = Join-Path $rollbackRoot ("rookbim-identity-predeploy-" + $implementationCommit + ".zip")
$rollbackShaFile = $rollbackZip + '.sha256'
$restoreStage = Join-Path $rollbackRoot ("restore-" + [guid]::NewGuid().ToString('N'))
$pluginDir = Join-Path $roaming 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
$appRook = Join-Path $local 'Rook\app\mcp_server\src\rook'
$venvRook = Join-Path $local 'Rook\venv\Lib\site-packages\rook'

if (-not (Test-Path -LiteralPath $rollbackZip -PathType Leaf) -or
    -not (Test-Path -LiteralPath $rollbackShaFile -PathType Leaf)) {
    throw 'Verified rollback ZIP or SHA sidecar is missing'
}
$expectedZipSha = ((Get-Content -LiteralPath $rollbackShaFile -Raw).Trim().Split(' ')[0])
$actualZipSha = (Get-FileHash -LiteralPath $rollbackZip -Algorithm SHA256).Hash
if ($actualZipSha -ne $expectedZipSha) { throw 'Rollback ZIP SHA mismatch' }

$rollbackRootFull = [IO.Path]::GetFullPath($rollbackRoot).TrimEnd('\')
$restoreStageFull = [IO.Path]::GetFullPath($restoreStage)
if (-not $restoreStageFull.StartsWith($rollbackRootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Restore stage escaped the dedicated rollback root'
}
Expand-Archive -LiteralPath $rollbackZip -DestinationPath $restoreStage
$manifest = Get-Content -LiteralPath (Join-Path $restoreStage 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.artifactType -ne 'rookbim-file-workshared-identity-predeploy-v1' -or
    $manifest.implementationCommit -ne $implementationCommit) {
    throw 'Rollback manifest does not match this deployment'
}

$targets = [ordered]@{
    'plugin' = [IO.Path]::GetFullPath($pluginDir)
    'app-rook' = [IO.Path]::GetFullPath($appRook)
    'venv-rook' = [IO.Path]::GetFullPath($venvRook)
}
$expectedTargets = [ordered]@{
    'plugin' = [IO.Path]::GetFullPath((Join-Path $roaming 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'))
    'app-rook' = [IO.Path]::GetFullPath((Join-Path $local 'Rook\app\mcp_server\src\rook'))
    'venv-rook' = [IO.Path]::GetFullPath((Join-Path $local 'Rook\venv\Lib\site-packages\rook'))
}
foreach ($name in $targets.Keys) {
    if (-not [string]::Equals($targets[$name], $expectedTargets[$name], [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unexpected destructive restore target: $($targets[$name])"
    }
    $source = Join-Path $restoreStage $name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Rollback payload missing: $name"
    }
    & robocopy $source $targets[$name] /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Rollback mirror failed for ${name}: $LASTEXITCODE" }
}

foreach ($entry in $manifest.payload) {
    $entryPath = [string]$entry.path
    $separator = $entryPath.IndexOf('/')
    if ($separator -le 0) { throw "Invalid rollback manifest path: $entryPath" }
    $rootName = $entryPath.Substring(0, $separator)
    $relativeName = $entryPath.Substring($separator + 1)
    $restored = Join-Path $targets[$rootName] $relativeName.Replace('/','\')
    if (-not (Test-Path -LiteralPath $restored -PathType Leaf)) {
        throw "Restored file missing: $($entry.path)"
    }
    if ((Get-Item -LiteralPath $restored).Length -ne [long]$entry.length -or
        (Get-FileHash -LiteralPath $restored -Algorithm SHA256).Hash -ne [string]$entry.sha256) {
        throw "Restored file mismatch: $($entry.path)"
    }
}

$expectedCount = @($manifest.payload).Count
$actualCount = @(
    Get-ChildItem -LiteralPath $pluginDir -Recurse -File
    Get-ChildItem -LiteralPath $appRook -Recurse -File
    Get-ChildItem -LiteralPath $venvRook -Recurse -File
).Count
if ($actualCount -ne $expectedCount) { throw 'Restored inventory contains missing or extra files' }

if ((Get-Item (Join-Path $pluginDir 'net8.0\Rook.rhp')).VersionInfo.ProductVersion -ne
        [string]$manifest.pluginProductVersion -or
    (Get-Item (Join-Path $pluginDir 'net48\RookBim.dll')).VersionInfo.ProductVersion -ne
        [string]$manifest.bimProductVersion) {
    throw 'Restored managed provenance does not match the rollback manifest'
}
Remove-Item -LiteralPath $restoreStage -Recurse -Force
Write-Host "RestoredArtifact=$rollbackZip"
Write-Host "RestoredSHA256=$actualZipSha"
```

Only after every hash and inventory check passes may Revit be restarted for a rollback smoke. Require `/bim/status` core/module provenance to match the restored product versions and require Python to import from the restored `%LOCALAPPDATA%\Rook\venv\Lib\site-packages\rook` path. Record the restore result in the execution ledger.

The artifact restores the exact pre-deploy installation, which still contains the diagnosed fail-open identity behavior. It is support containment, not a safe identity release. Do not claim identity resolution, selection, or identity-list export is approved after rollback; prepare and deploy a corrected reviewed build instead.

## Plan self-review checklist

- [ ] Initial source set contains exactly the two approved composites plus unavailable.
- [ ] No path-only authorization, speculative source, or physical-copy claim exists.
- [ ] Strong evidence cannot downgrade.
- [ ] Every document class has an explicit disposition.
- [ ] File/cloud models cannot call the server getter.
- [ ] Expected `InternalException` produces unavailable producer evidence and fail-closed consumer behavior.
- [ ] Required discriminator failure stops classification/key reads; non-workshared documents never read central ModelPath.
- [ ] One `PathName` result supplies both saved-project identity and display projection.
- [ ] Legacy persistent GUID validation is exact non-empty `D` format without trimming.
- [ ] One operation captures once; projections and 1,000-element batches do not reread.
- [ ] All batch comparisons precede lookup and side effects.
- [ ] Selector/preset live elements never cross `src/RookBim` or the operation boundary.
- [ ] Task 1 is behavior-neutral; Task 2 is one atomic deployable cutover.
- [ ] MCP changes are limited to the closed schema and focused tests; both new fields stay optional and all four consumers forward exact dictionaries.
- [ ] The policy contains no diagnostics, Autodesk types, generic reader framework, DI, cache, or provider extension point.
- [ ] Diagnostics parity/privacy and exact wire names are tested.
- [ ] Whole-branch review precedes deployment.
- [ ] Pre-deploy rollback ZIP, SHA sidecar, and manifest are verified; restore commands target only the three exact installation roots.
- [ ] Live two-document Revit acceptance remains the release gate.
