# Extract shared `CappedStreamReader.ReadCappedAsync`

**Date:** 2026-06-20
**Type:** Behavior-preserving extraction (rule-of-three cleanup)
**Branch:** `codex/capped-stream-reader-extraction` (off `origin/main` `f3bd9848`)

## Problem

Three remote-asset download paths each contain a near-identical capped streaming
read loop:

- `src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs` (inline loop, ~lines 130–148)
- `src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs` (inline loop, ~lines 114–130)
- `src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs` (`ReadCappedAsync`, ~lines 88–102)

The reconstruction convergence audit deliberately built the reconstruction
downloader local, deferring a shared abstraction until the rule of three was
real. It now is (image, video, reconstruction).

## Critical finding — only the read loop is shared

A behavior comparison (not code shape) shows the three paths **diverge
materially** above the read loop, and these divergences are intentional:

| Dimension | Image | Video | Reconstruction |
|---|---|---|---|
| Input | `ResultArtifact` + inline dispatch | `ResultArtifact` + inline dispatch | raw `Uri` + `role` |
| Retry | none (1 attempt) | 3× on 5xx + timeout + `HttpRequestException` + `IOException` | 3× on transient status + transport, **excludes** `IOException` |
| Retryable status | 5xx only | 5xx only | 5xx + 408 + 429 |
| Cap-exceeded code | `ExecutionFailed` | `ExecutionFailed` | `UnsupportedMedia` |
| HTTP-fail retryable | per-status | per-status | always true |
| Cancellation | caught → `Interrupted` result | caught → `Interrupted` result | rethrows |
| Cap model | fixed 25 MB const | configurable scalar (250 MB) | `Func<string,long>` role-aware |
| Request build | injectable `requestFactory` | plain GET | `GetAsync`, absolute-HTTPS validation |
| MIME default | `image/png` | `video/mp4` | passthrough (nullable) |
| Result type | `ImageArtifactMaterializationResult` | `VideoArtifactMaterializationResult` | `ReconstructionDownloadResult` |

A single shared *downloader* would have to accept all of this as policy — three
behaviors encoded as config, high blast radius, near-zero real sharing. Rejected.

The **only byte-for-byte-identical** part is the capped streaming read loop:

- 81920-byte buffer.
- net48 array-based `ReadAsync(buf, 0, len, ct)` (no `Memory<byte>` overload).
- Overflow when cumulative-bytes-including-the-current-chunk `>` cap, checked
  **before** writing the chunk → exactly-at-cap is allowed (pinned by video's
  `Remote_exactly_cap_is_allowed`).
- Empty-body decision stays caller-side (the loop just returns the bytes).
- `ct` flows to `ReadAsync`; cancellation throws `OperationCanceledException`
  **out** of the loop into each caller's existing catch — so all three
  cancellation contracts are preserved unchanged.

## Decision

Extract **only** that kernel into one small shared helper. Keep retry,
error-code mapping, cancellation handling, request construction, inline
dispatch, Content-Length precheck, and cap source **modality-local**.

### The helper

File: `src/Rook/Services/Vision/Generation/CappedStreamReader.cs`
(Reconstruction already depends on `Rook.Services.Vision.Generation` for
`GenerationError` after the convergence work, so this namespace introduces no
new dependency.)

```csharp
namespace Rook.Services.Vision.Generation;

internal static class CappedStreamReader
{
    // Returns null when the cap is exceeded mid-stream (cumulative bytes > cap),
    // so the caller maps overflow to its own modality-specific error code.
    // Returns the full body otherwise (possibly empty — the caller decides how
    // to treat an empty body).
    internal static async Task<byte[]?> ReadCappedAsync(
        Stream stream, long cap, CancellationToken ct);
}
```

This is reconstruction's existing `ReadCappedAsync` promoted verbatim
(81920 buffer, accumulate into `MemoryStream`, `total > cap → null`, otherwise
`ms.ToArray()`).

**No configurability beyond `Stream`, `cap`, `CancellationToken`.** No
buffer-size parameter — no current caller needs one.

### Adoption (each behavior-identical)

- **Reconstruction:** delete its private `ReadCappedAsync`; call the shared one.
  Pure move of its own code — zero behavior change. `null → UnsupportedMedia`,
  empty → `ExecutionFailed`, absolute-HTTPS check, role cap, retry set, and
  rethrow-on-cancel all stay.
- **Image:** replace the inline `while` loop with
  `var bytes = await CappedStreamReader.ReadCappedAsync(stream, MaxGeneratedImageBytes, cancellationToken);`
  then `bytes is null → ExecutionFailed("Remote image artifact exceeded the
  maximum allowed size.")`, `bytes.Length == 0 → ExecutionFailed("Remote image
  artifact response was empty.")`, else `Ok(bytes, mimeType)`. Same messages,
  same codes. Content-Length precheck, no-retry, `requestFactory` seam, png
  default, and `Interrupted`-on-cancel are untouched.
- **Video:** same swap inside its retry loop, using `_maxGeneratedVideoBytes`.
  Same overflow/empty messages and codes. 3× retry, mp4 default, configurable
  cap, and `Interrupted`-on-cancel are untouched.

## Out of scope (explicit)

- No `MediaDownloader` service. No shared result/error vocabulary. No
  centralized HTTP, retry, status handling, MIME, or result mapping.
- The Content-Length precheck stays caller-side (each maps to its own error
  code: `ExecutionFailed` vs `UnsupportedMedia`).
- MediaImport importers (`ImageMediaImporter`, `VideoMediaImporter`) are
  untouched — they validate *local file* size, not remote streaming, so they
  are not part of this rule-of-three.
- No fal/provider semantic changes. No reconstruction package behavior changes.
  No image/video result-contract changes. No new dependencies.

## Stop-and-report trigger

If adopting the kernel in any modality would change an observable — an error
message, error code, cap boundary, or retry interaction — stop and report
rather than force it into the helper.

## Testing

The existing **42 tests** are the regression net; any behavior drift fails one
of them:

- Image: 22 (`ImageArtifactMaterializerTests`) — incl. no-retry transport
  mapping, cancellation→`Interrupted`, content-length precheck, stream-cap,
  mime fallbacks, requestFactory seam.
- Video: 13 (`VideoArtifactMaterializerTests`) — incl.
  `Remote_transport_error_is_retried_before_success`,
  `Remote_exactly_cap_is_allowed`, mp4 fallback.
- Reconstruction: 7 (`ReconstructionRemoteAssetDownloaderTests`) — incl.
  `Download_500_RetriesThenFails`, `Download_Cancellation_NoRetry`, header-cap,
  stream-cap.

Add **one focused unit test class** `CappedStreamReaderTests` for the primitive:

1. Under-cap stream → returns all bytes.
2. Exactly-at-cap stream → returns the bytes (boundary; `>` not `>=`).
3. One-byte-over-cap stream → returns `null`.
4. Multi-chunk stream crossing the cap → returns `null` (overflow detected
   before the overflowing chunk is committed; the observable is the `null`
   return, since the helper exposes only the final bytes).
5. Empty stream → returns an empty array (not null).
6. Cancellation requested mid-read → throws `OperationCanceledException`.

Use a fake `Stream` overriding `ReadAsync` (the existing materializer test files
already contain such fakes to mirror).

## Verification

- Focused: `CappedStreamReaderTests` + the three materializer/downloader test
  classes.
- Full Debug C# suite: `dotnet test src\Rook.Tests\Rook.Tests.csproj -c Debug`
  → expect the same green baseline (current: 2836) plus the new primitive tests.
- Tripwire: `"Deployed Rook.rhp"` must NOT appear in Debug test output.
- MCP parity not required (no Python touched).
