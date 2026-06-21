# CappedStreamReader Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the byte-for-byte-identical capped streaming read loop shared by the image, video, and reconstruction remote-download paths into one `internal static` helper, and adopt it in all three with zero observable behavior change.

**Architecture:** A single helper `CappedStreamReader.ReadCappedAsync(Stream, long cap, CancellationToken)` in `Rook.Services.Vision.Generation` returns the full body bytes, or `null` when the cumulative byte count exceeds `cap` mid-stream. Each caller maps `null` to its own modality-specific error code and keeps its own retry, HTTP dispatch, cancellation, MIME, Content-Length precheck, and empty-body handling. Nothing above the read loop is centralized.

**Tech Stack:** C# / .NET Framework 4.8 (`net48`), xUnit. `<Nullable>enable</Nullable>`, `<LangVersion>latest</LangVersion>`. Block-scoped namespaces in `Rook.Services.Vision.Generation`.

## Global Constraints

- Behavior-preserving extraction only. No change to retry policy, retryable-status sets, error codes, error messages, cancellation contracts, cap values/sources, request construction, MIME defaults, or result types.
- Helper signature is exactly `(Stream stream, long cap, CancellationToken ct)`. **No buffer-size parameter, no other configurability.**
- Helper is a verbatim move of reconstruction's existing private `ReadCappedAsync` (81920-byte buffer, net48 array-based `ReadAsync(buf, 0, len, ct)`, `total > cap → null`, otherwise `ms.ToArray()`).
- Overflow rule: cumulative bytes including the current chunk `> cap`, checked **before** writing the chunk → exactly-at-cap is allowed (`>`, not `>=`).
- Empty-body decision stays caller-side. Content-Length precheck stays caller-side.
- `VeoClient` and `ReconstructionJobManager`'s local-file read are OUT OF SCOPE — do not route them through the helper.
- No new dependencies. No fal/provider, package, or result-contract changes.
- **Stop-and-report trigger:** if adopting the helper in any modality would change an observable (message, code, cap boundary, retry interaction), stop and report instead of forcing it.
- Watch the deploy tripwire: `"Deployed Rook.rhp"` must NOT appear in Debug test output.

**Reference:** spec at `docs/superpowers/specs/2026-06-20-capped-stream-reader-extraction-design.md`.

---

## File Structure

- **Create** `src/Rook/Services/Vision/Generation/CappedStreamReader.cs` — the shared kernel (one responsibility: bounded read-to-memory).
- **Create** `src/Rook.Tests/Services/Vision/Generation/CappedStreamReaderTests.cs` — focused unit tests for the kernel.
- **Modify** `src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs` — delete private `ReadCappedAsync`, call the shared one.
- **Modify** `src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs` — replace inline loop with helper call.
- **Modify** `src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs` — replace inline loop with helper call.

The test assembly already sees `internal` types (existing tests cover the `internal` materializers), so no `InternalsVisibleTo` change is needed.

---

### Task 1: Create the shared `CappedStreamReader` kernel (TDD)

**Files:**
- Create: `src/Rook/Services/Vision/Generation/CappedStreamReader.cs`
- Test: `src/Rook.Tests/Services/Vision/Generation/CappedStreamReaderTests.cs`

**Interfaces:**
- Consumes: nothing.
- Produces: `internal static class CappedStreamReader` in namespace `Rook.Services.Vision.Generation`, with `internal static Task<byte[]?> ReadCappedAsync(Stream stream, long cap, CancellationToken ct)`. Returns `null` iff cumulative bytes `> cap`; otherwise the full body (possibly empty array).

- [ ] **Step 1: Write the failing tests**

Create `src/Rook.Tests/Services/Vision/Generation/CappedStreamReaderTests.cs`:

```csharp
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public sealed class CappedStreamReaderTests
    {
        [Fact]
        public async Task Under_cap_returns_all_bytes()
        {
            using var stream = new ScriptedStream(total: 5, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.NotNull(bytes);
            Assert.Equal(5, bytes!.Length);
        }

        [Fact]
        public async Task Exactly_at_cap_returns_bytes()
        {
            using var stream = new ScriptedStream(total: 10, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.NotNull(bytes);
            Assert.Equal(10, bytes!.Length);
        }

        [Fact]
        public async Task One_over_cap_returns_null()
        {
            using var stream = new ScriptedStream(total: 11, chunk: 16);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.Null(bytes);
        }

        [Fact]
        public async Task Multi_chunk_crossing_cap_returns_null()
        {
            using var stream = new ScriptedStream(total: 12, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.Null(bytes);
        }

        [Fact]
        public async Task Empty_stream_returns_empty_array_not_null()
        {
            using var stream = new ScriptedStream(total: 0, chunk: 4);

            var bytes = await CappedStreamReader.ReadCappedAsync(
                stream, cap: 10, ct: CancellationToken.None);

            Assert.NotNull(bytes);
            Assert.Empty(bytes!);
        }

        [Fact]
        public async Task Cancellation_mid_read_throws_operation_cancelled()
        {
            using var stream = new ScriptedStream(total: 100, chunk: 4);
            using var cts = new CancellationTokenSource();
            cts.Cancel();

            await Assert.ThrowsAsync<OperationCanceledException>(
                () => CappedStreamReader.ReadCappedAsync(stream, cap: 1000, ct: cts.Token));
        }

        // Yields `total` bytes in reads of at most `chunk` bytes; honors cancellation.
        private sealed class ScriptedStream : Stream
        {
            private long _remaining;
            private readonly int _chunk;

            public ScriptedStream(long total, int chunk)
            {
                _remaining = total;
                _chunk = chunk;
            }

            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override long Length => throw new NotSupportedException();

            public override long Position
            {
                get => throw new NotSupportedException();
                set => throw new NotSupportedException();
            }

            public override void Flush() { }

            public override int Read(byte[] buffer, int offset, int count)
            {
                if (_remaining <= 0)
                    return 0;

                var toRead = (int)Math.Min(Math.Min(count, _chunk), _remaining);
                for (var i = 0; i < toRead; i++)
                    buffer[offset + i] = 7;
                _remaining -= toRead;
                return toRead;
            }

            public override Task<int> ReadAsync(
                byte[] buffer,
                int offset,
                int count,
                CancellationToken cancellationToken)
            {
                cancellationToken.ThrowIfCancellationRequested();
                return Task.FromResult(Read(buffer, offset, count));
            }

            public override long Seek(long offset, SeekOrigin origin) =>
                throw new NotSupportedException();

            public override void SetLength(long value) =>
                throw new NotSupportedException();

            public override void Write(byte[] buffer, int offset, int count) =>
                throw new NotSupportedException();
        }
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~CappedStreamReaderTests"`
Expected: BUILD FAILS — `CappedStreamReader` does not exist (`CS0103`/type-not-found). This confirms the test targets the not-yet-created helper.

- [ ] **Step 3: Create the helper (verbatim move of reconstruction's loop)**

Create `src/Rook/Services/Vision/Generation/CappedStreamReader.cs`:

```csharp
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Reads a stream fully into memory while enforcing a byte cap during the
    /// read. Returns <c>null</c> when the cumulative byte count exceeds
    /// <paramref name="cap"/> (checked before the overflowing chunk is
    /// committed, so exactly-at-cap is allowed); otherwise returns the full
    /// body, which may be an empty array. Callers map the <c>null</c> overflow
    /// signal and an empty body to their own modality-specific errors.
    ///
    /// This is the single shared kernel behind the image, video, and
    /// reconstruction remote-download paths; everything above the read loop
    /// (HTTP dispatch, retry, status/error mapping, cancellation contract,
    /// MIME, Content-Length precheck) stays caller-local. net48: uses the
    /// array-based <see cref="System.IO.Stream.ReadAsync(byte[],int,int,CancellationToken)"/>
    /// overload (no <c>Memory&lt;byte&gt;</c> overload available).
    /// </summary>
    internal static class CappedStreamReader
    {
        internal static async Task<byte[]?> ReadCappedAsync(
            Stream stream, long cap, CancellationToken ct)
        {
            using var ms = new MemoryStream();
            var buf = new byte[81920];
            int n;
            long total = 0;
            while ((n = await stream.ReadAsync(buf, 0, buf.Length, ct).ConfigureAwait(false)) > 0)
            {
                total += n;
                if (total > cap) return null;
                ms.Write(buf, 0, n);
            }
            return ms.ToArray();
        }
    }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~CappedStreamReaderTests"`
Expected: PASS — `Failed: 0, Passed: 6`.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Vision/Generation/CappedStreamReader.cs \
        src/Rook.Tests/Services/Vision/Generation/CappedStreamReaderTests.cs
git commit -m "feat(vision): add shared CappedStreamReader.ReadCappedAsync kernel"
```

---

### Task 2: Adopt the kernel in reconstruction (zero-behavior move)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs`

**Interfaces:**
- Consumes: `CappedStreamReader.ReadCappedAsync(Stream, long, CancellationToken)` from Task 1.
- Produces: no API change. `IReconstructionRemoteAssetDownloader.DownloadAsync` is unchanged.

This is the safest adoption: the downloader's existing private `ReadCappedAsync` is identical to the shared one, so this just deletes the private copy and calls the shared one. The file already has `using Rook.Services.Vision.Generation;`.

- [ ] **Step 1: Confirm the reconstruction tests are green before the change**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionRemoteAssetDownloaderTests"`
Expected: PASS — `Failed: 0, Passed: 7`.

- [ ] **Step 2: Replace the call site to use the shared helper**

In `DownloadAsync`, the current call is:

```csharp
                var bytes = await ReadCappedAsync(stream, cap, ct).ConfigureAwait(false);
```

Change it to:

```csharp
                var bytes = await CappedStreamReader.ReadCappedAsync(stream, cap, ct).ConfigureAwait(false);
```

- [ ] **Step 3: Delete the private `ReadCappedAsync` method**

Remove the entire private method (the `net48: use the array-based ReadAsync overload` block):

```csharp
    private static async Task<byte[]?> ReadCappedAsync(Stream s, long cap, CancellationToken ct)
    {
        using var ms = new MemoryStream();
        var buf = new byte[81920];
        int n;
        long total = 0;
        // net48: use the array-based ReadAsync overload (no Memory<byte> overload).
        while ((n = await s.ReadAsync(buf, 0, buf.Length, ct).ConfigureAwait(false)) > 0)
        {
            total += n;
            if (total > cap) return null;
            ms.Write(buf, 0, n);
        }
        return ms.ToArray();
    }
```

Leave all `using` directives unchanged. After deletion the file no longer names a `System.IO` type explicitly (the remaining `using var stream = await resp.Content.ReadAsStreamAsync()` is `var`), so `using System.IO;` becomes technically unnecessary — but the project does not treat warnings as errors (no `TreatWarningsAsErrors` in `Rook.csproj` or `Directory.Build.props`), so leaving it is harmless and keeps the diff minimal. Do not remove it.

- [ ] **Step 4: Run the reconstruction tests to verify they still pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Reconstruction"`
Expected: PASS — all `ReconstructionRemoteAssetDownloaderTests` (7) and `ReconstructionPackageMaterializerTests` (3) green, no behavior change.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs
git commit -m "refactor(reconstruction): use shared CappedStreamReader kernel"
```

---

### Task 3: Adopt the kernel in `ImageArtifactMaterializer`

**Files:**
- Modify: `src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs`

**Interfaces:**
- Consumes: `CappedStreamReader.ReadCappedAsync(Stream, long, CancellationToken)` from Task 1.
- Produces: no API change. `MaterializeAsync` result type, codes, and messages are unchanged.

The file already has `using Rook.Services.Vision.Generation;`. Image has **no retry**, so the read happens once; overflow maps to the same `ExecutionFailed` message as today.

- [ ] **Step 1: Confirm the image tests are green before the change**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageArtifactMaterializerTests"`
Expected: PASS — `Failed: 0, Passed: 22`.

- [ ] **Step 2: Replace the inline read loop with a helper call**

Find this block (the stream read through the final `Ok`):

```csharp
                using var stream = await response.Content.ReadAsStreamAsync()
                    .ConfigureAwait(false);
                using var buffer = new MemoryStream();
                var readBuffer = new byte[81920];

                while (true)
                {
                    var read = await stream.ReadAsync(
                            readBuffer,
                            0,
                            readBuffer.Length,
                            cancellationToken)
                        .ConfigureAwait(false);
                    if (read == 0)
                        break;

                    if (buffer.Length + read > MaxGeneratedImageBytes)
                    {
                        return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote image artifact exceeded the maximum allowed size."));
                    }

                    buffer.Write(readBuffer, 0, read);
                }

                if (buffer.Length == 0)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact response was empty."));

                return ImageArtifactMaterializationResult.Ok(buffer.ToArray(), mimeType);
```

Replace it with:

```csharp
                using var stream = await response.Content.ReadAsStreamAsync()
                    .ConfigureAwait(false);

                var bytes = await CappedStreamReader.ReadCappedAsync(
                        stream, MaxGeneratedImageBytes, cancellationToken)
                    .ConfigureAwait(false);
                if (bytes is null)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact exceeded the maximum allowed size."));

                if (bytes.Length == 0)
                    return ImageArtifactMaterializationResult.Fail(ExecutionFailed(
                        "Remote image artifact response was empty."));

                return ImageArtifactMaterializationResult.Ok(bytes, mimeType);
```

- [ ] **Step 3: Run the image tests to verify they still pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ImageArtifactMaterializerTests"`
Expected: PASS — `Failed: 0, Passed: 22`. In particular the cap tests (`Remote_artifact_rejects_content_length_greater_than_max_before_reading`, `Remote_artifact_rejects_read_bytes_greater_than_max_when_content_length_is_missing`) and `Caller_cancellation_maps_interrupted_non_retryable` stay green.

- [ ] **Step 4: Commit**

```bash
git add src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs
git commit -m "refactor(vision): ImageArtifactMaterializer uses shared CappedStreamReader"
```

---

### Task 4: Adopt the kernel in `VideoArtifactMaterializer`

**Files:**
- Modify: `src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs`

**Interfaces:**
- Consumes: `CappedStreamReader.ReadCappedAsync(Stream, long, CancellationToken)` from Task 1.
- Produces: no API change. Result type, codes, messages, and 3× retry behavior unchanged.

The read loop sits inside the `for (attempt...)` retry loop. A cap-exceed returns from the method immediately today (it is not retried); mapping the helper's `null` to the same `return ...Fail(...)` preserves that exactly. The file already has `using Rook.Services.Vision.Generation;`. The cap field is `_maxGeneratedVideoBytes`.

- [ ] **Step 1: Confirm the video tests are green before the change**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~VideoArtifactMaterializerTests"`
Expected: PASS — `Failed: 0, Passed: 13`.

- [ ] **Step 2: Replace the inline read loop with a helper call**

Find this block inside the retry loop (stream read through the final `Ok`):

```csharp
                    using var stream = await response.Content.ReadAsStreamAsync()
                        .ConfigureAwait(false);
                    using var buffer = new MemoryStream();
                    var readBuffer = new byte[81920];

                    while (true)
                    {
                        var read = await stream.ReadAsync(
                                readBuffer,
                                0,
                                readBuffer.Length,
                                cancellationToken)
                            .ConfigureAwait(false);
                        if (read == 0)
                            break;

                        if (buffer.Length + read > _maxGeneratedVideoBytes)
                            return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                                "Remote video artifact exceeded the maximum allowed size."));

                        buffer.Write(readBuffer, 0, read);
                    }

                    if (buffer.Length == 0)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote video artifact response was empty."));

                    return VideoArtifactMaterializationResult.Ok(buffer.ToArray(), mimeType);
```

Replace it with:

```csharp
                    using var stream = await response.Content.ReadAsStreamAsync()
                        .ConfigureAwait(false);

                    var bytes = await CappedStreamReader.ReadCappedAsync(
                            stream, _maxGeneratedVideoBytes, cancellationToken)
                        .ConfigureAwait(false);
                    if (bytes is null)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote video artifact exceeded the maximum allowed size."));

                    if (bytes.Length == 0)
                        return VideoArtifactMaterializationResult.Fail(ExecutionFailed(
                            "Remote video artifact response was empty."));

                    return VideoArtifactMaterializationResult.Ok(bytes, mimeType);
```

- [ ] **Step 3: Run the video tests to verify they still pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~VideoArtifactMaterializerTests"`
Expected: PASS — `Failed: 0, Passed: 13`. In particular `Remote_exactly_cap_is_allowed`, `Remote_missing_content_length_fails_when_stream_crosses_cap`, and `Remote_transport_error_is_retried_before_success` stay green.

- [ ] **Step 4: Commit**

```bash
git add src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs
git commit -m "refactor(vision): VideoArtifactMaterializer uses shared CappedStreamReader"
```

---

### Task 5: Final verification (dead-wood greps + full suite)

**Files:** none modified — verification only.

- [ ] **Step 1: Dead-wood greps — duplicated kernel is gone**

Run:
```bash
rg -n "private static async Task<byte\[\]\?> ReadCappedAsync" src/Rook/Services/Reconstruction/ReconstructionRemoteAssetDownloader.cs
```
Expected: no output (the private method is gone; only the `CappedStreamReader.ReadCappedAsync` call remains).

Run:
```bash
rg -n "81920" src/Rook/Services/Vision/Image/ImageArtifactMaterializer.cs src/Rook/Services/Vision/Video/VideoArtifactMaterializer.cs
```
Expected: no output (no inline capped loop remains in either materializer).

- [ ] **Step 2: Intentionally-different stream sites remain untouched**

Run:
```bash
rg -n "CopyToAsync|81920" src/Rook/Services/Vision/Video/VeoClient.cs src/Rook/Services/Reconstruction/ReconstructionJobManager.cs
```
Expected: the uncapped `VeoClient` download (`CopyToAsync(ms, 81920, ct)`) and the `ReconstructionJobManager` local-file read (`FileStream` + `CopyToAsync`) are both still present and unchanged.

Run:
```bash
rg -n "CappedStreamReader" src/Rook
```
Expected: exactly four hits — the helper definition plus three call sites (reconstruction, image, video).

- [ ] **Step 3: Run the full Debug C# suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`
Expected: PASS — `Failed: 0`, total = previous baseline (2836) + 6 new `CappedStreamReaderTests` = **2842**.

- [ ] **Step 4: Confirm the deploy tripwire did not fire**

Inspect the Step 3 output: the string `"Deployed Rook.rhp"` must NOT appear. (The normal compile artifact line `Rook -> ...bin\Debug\net48\Rook.rhp` is expected and is NOT the tripwire.)

- [ ] **Step 5: No commit**

Task 5 is verification only; there is nothing to commit. The branch is ready for PR after this task.

---

## Notes for the PR

- Open a ready (non-draft) PR into `main`, preserve commit history (no squash unless approved), do not merge locally without review.
- MCP parity is not required — no Python is touched.
- Expected commit sequence on the branch: spec (2 commits already present) → Task 1 (helper+tests) → Task 2 (reconstruction) → Task 3 (image) → Task 4 (video).
