# PR-15 Image Job Durability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an image-safe durable JSONL ledger and startup interrupted reconciliation for managed image jobs.

**Architecture:** Mirror video job lifecycle durability, but use a narrower image-specific record that persists only operational fields and a sanitized durable error. `ImageJobManager` becomes ledger-backed while keeping `_runningJobs` as current-process runtime state; restart recovery marks prior non-terminal jobs `Interrupted` and supports cancel-after-restart through persisted `provider_job_id` only.

**Tech Stack:** C# `net7.0;net48`, xUnit, `System.Text.Json.Nodes`, append-only JSONL, existing managed Vision image job/provider abstractions, fake providers/fake HTTP only.

---

## Scope Guard

Do:

- Add image job JSONL durability under `src/Rook/Services/Vision/Image/Jobs`.
- Persist only `schema_version`, `job_id`, `state`, `provider`, `model`, `provider_job_id`, `result_artifact_id`, sanitized `error`, `created_at`, and `updated_at`.
- Redact durable error messages before writing them to the ledger.
- Make `ImageJobManager` append durable snapshots for successful state transitions.
- Fail closed when the initial ledger append fails before provider submit.
- Stop polling and best-effort cancel if persisting the first `provider_job_id` fails.
- Reconcile prior non-terminal durable jobs to `Interrupted` at startup.
- Keep existing bridge op names and response shapes stable.
- Keep normal tests fake-provider/fake-HTTP only.

Do not:

- Persist prompt, resolution, aspect ratio, provider options, or parent artifact ids.
- Persist provider metadata, provider result tokens, provider URLs, output URLs, signed/auth requests, or token-looking values.
- Add Vision UI resurfacing.
- Add Replicate auto-resume.
- Modify `src/RookNative/**`.
- Modify `mcp_server/**`.
- Add public HTTP or `NativeGhBridgeRegistrar` exposure.
- Change synchronous `generate`.

---

## File Structure

Create:

- `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecord.cs`
  - Durable image-safe snapshot type.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactory.cs`
  - Builds initial and transitioned durable records, sanitizes errors, carries forward safe fields.
- `src/Rook/Services/Vision/Image/Jobs/IImageJobLedger.cs`
  - Append/read seam.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerReadResult.cs`
  - Compacted records + read errors.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerReadError.cs`
  - Line-scoped read error projection.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerReadErrorReason.cs`
  - Malformed/unsupported/missing-field reasons.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerWarning.cs`
  - Internal sanitized warning projection if manager needs one.
- `src/Rook/Services/Vision/Image/Jobs/JsonlImageJobLedger.cs`
  - Append-only JSONL production ledger.
- `src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobLedger.cs`
  - In-memory fake with append-failure hooks.
- `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs`
  - Durable record and redaction tests.
- `src/Rook.Tests/Services/Vision/Image/Jobs/JsonlImageJobLedgerTests.cs`
  - JSONL serialization/read tests.

Modify:

- `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
  - Accept ledger, append transitions, merge live/durable records, reconcile, cancel-after-restart.
- `src/Rook/Services/Vision/Image/Jobs/IImageJobManager.cs`
  - Add `ReconcileInterruptedJobs()`.
- `src/Rook/Services/Vision/Image/Jobs/ImageJobSubsystemBundle.cs`
  - No planned shape change.
- `src/Rook/RookSubsystemRoot.cs`
  - Construct `JsonlImageJobLedger`, add `ReconcileImageJobsOnce()`.
- `src/Rook/RookPlugin.cs`
  - Call image reconcile at startup, non-fatal.
- `src/Rook/Handlers/ImageJobOpHandler.cs`
  - Mostly unchanged; ensure durable records are projected without leaking internals.
- `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`
  - Add durability, reconcile, race, append-failure tests.
- `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`
  - Add durable bridge response/leakage tests.
- `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`
  - Add image reconcile root lifecycle tests alongside existing root lifecycle tests.
- `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`
  - No planned change; existing boundary/resource tests should continue passing.

---

## Task 1: Add Durable Image Job Record And Error Sanitizer

**Files:**
- Create: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecord.cs`
- Create: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactory.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs`

- [ ] **Step 1: Write failing durable-record tests**

Create `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactoryTests.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobLedgerRecordFactoryTests
    {
        [Fact]
        public void FromInitial_builds_operational_record_without_provider_job_id()
        {
            var now = DateTimeOffset.Parse("2026-05-04T12:00:00Z");
            var record = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("11111111-1111-1111-1111-111111111111"),
                GeminiImageCapabilities.ProviderName,
                GeminiImageCapabilities.DefaultModel,
                ImageJobState.Queued,
                now);

            Assert.Equal(ImageJobLedgerRecordFactory.CurrentSchemaVersion, record.SchemaVersion);
            Assert.Equal(ImageJobState.Queued, record.State);
            Assert.Equal("gemini", record.Provider);
            Assert.Equal(GeminiImageCapabilities.DefaultModel, record.Model);
            Assert.Null(record.ProviderJobId);
            Assert.Null(record.ResultArtifactId);
            Assert.Null(record.Error);
            Assert.Equal(now, record.CreatedAt);
            Assert.Equal(now, record.UpdatedAt);
        }

        [Fact]
        public void WithState_carries_forward_safe_fields_only()
        {
            var now = DateTimeOffset.Parse("2026-05-04T12:00:00Z");
            var later = now.AddSeconds(2);
            var initial = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("22222222-2222-2222-2222-222222222222"),
                "replicate",
                "black-forest-labs/flux-schnell",
                ImageJobState.Queued,
                now);

            var next = ImageJobLedgerRecordFactory.WithState(
                initial,
                ImageJobState.Polling,
                later,
                providerJobId: "prediction-123");

            Assert.Equal(initial.JobId, next.JobId);
            Assert.Equal(initial.CreatedAt, next.CreatedAt);
            Assert.Equal(later, next.UpdatedAt);
            Assert.Equal("prediction-123", next.ProviderJobId);
            Assert.Null(next.ResultArtifactId);
        }

        [Fact]
        public void WithState_redacts_unsafe_error_message_and_drops_provider_detail()
        {
            var initial = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("33333333-3333-3333-3333-333333333333"),
                "replicate",
                "black-forest-labs/flux-schnell",
                ImageJobState.Polling,
                DateTimeOffset.Parse("2026-05-04T12:00:00Z"));
            var error = new GenerationError(
                GenerationErrorCode.DependencyUnavailable,
                "Provider returned urls.get=https://api.replicate.com/v1/predictions/x and https://replicate.delivery/out.png",
                Retryable: false,
                Field: "provider",
                ProviderErrorCode: "E123",
                ProviderDetail: new System.Collections.Generic.Dictionary<string, JsonNode>
                {
                    ["raw"] = JsonValue.Create("secret-detail")!,
                });

            var next = ImageJobLedgerRecordFactory.WithState(
                initial,
                ImageJobState.Error,
                initial.UpdatedAt.AddSeconds(1),
                error: error);

            Assert.NotNull(next.Error);
            Assert.Equal(GenerationErrorCode.DependencyUnavailable, next.Error!.Code);
            Assert.Equal("Image job failed; provider details were redacted.", next.Error.Message);
            Assert.Equal("provider", next.Error.Field);
            Assert.Equal("E123", next.Error.ProviderErrorCode);
            Assert.Null(next.Error.ProviderDetail);
            Assert.DoesNotContain("urls.get", next.Error.Message);
            Assert.DoesNotContain("replicate.delivery", next.Error.Message);
            Assert.DoesNotContain("api.replicate.com", next.Error.Message);
        }

        [Fact]
        public void WithState_drops_long_provider_error_code()
        {
            var initial = ImageJobLedgerRecordFactory.FromInitial(
                Guid.Parse("44444444-4444-4444-4444-444444444444"),
                "replicate",
                "black-forest-labs/flux-schnell",
                ImageJobState.Polling,
                DateTimeOffset.Parse("2026-05-04T12:00:00Z"));
            var error = new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "plain failure",
                Retryable: false,
                ProviderErrorCode: new string('x', 128));

            var next = ImageJobLedgerRecordFactory.WithState(
                initial,
                ImageJobState.Error,
                initial.UpdatedAt.AddSeconds(1),
                error: error);

            Assert.Null(next.Error!.ProviderErrorCode);
            Assert.Equal("plain failure", next.Error.Message);
        }
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobLedgerRecordFactoryTests
```

Expected: compile failure because `ImageJobLedgerRecordFactory` does not exist.

- [ ] **Step 3: Add durable record**

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecord.cs`:

```csharp
using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobLedgerRecord(
        int SchemaVersion,
        Guid JobId,
        string Provider,
        string Model,
        string? ProviderJobId,
        ImageJobState State,
        Guid? ResultArtifactId,
        GenerationError? Error,
        DateTimeOffset CreatedAt,
        DateTimeOffset UpdatedAt);
}
```

- [ ] **Step 4: Add durable record factory and sanitizer**

Create `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerRecordFactory.cs`:

```csharp
using System;
using System.Text.RegularExpressions;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public static class ImageJobLedgerRecordFactory
    {
        public const int CurrentSchemaVersion = 1;
        private const int MaxMessageLength = 300;
        private const int MaxProviderErrorCodeLength = 64;
        private const string RedactedMessage =
            "Image job failed; provider details were redacted.";

        private static readonly Regex ControlChars =
            new("[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F]", RegexOptions.Compiled);

        private static readonly string[] BannedSubstrings =
        {
            "http://",
            "https://",
            "replicate.delivery",
            "api.replicate.com",
            "urls.get",
            "urls.cancel",
            "status_url",
            "cancel_url",
            "response_url",
            "provider_result_token",
            "Bearer ",
            "api_token",
            "r8_",
        };

        public static ImageJobLedgerRecord FromInitial(
            Guid jobId,
            string provider,
            string model,
            ImageJobState initialState,
            DateTimeOffset now)
        {
            if (jobId == Guid.Empty)
                throw new ArgumentException("JobId must be non-empty.", nameof(jobId));
            if (string.IsNullOrWhiteSpace(provider))
                throw new ArgumentException("Provider must be non-empty.", nameof(provider));
            if (string.IsNullOrWhiteSpace(model))
                throw new ArgumentException("Model must be non-empty.", nameof(model));

            return new ImageJobLedgerRecord(
                CurrentSchemaVersion,
                jobId,
                provider,
                model,
                ProviderJobId: null,
                initialState,
                ResultArtifactId: null,
                Error: null,
                CreatedAt: now,
                UpdatedAt: now);
        }

        public static ImageJobLedgerRecord WithState(
            ImageJobLedgerRecord prior,
            ImageJobState state,
            DateTimeOffset now,
            string? providerJobId = null,
            Guid? resultArtifactId = null,
            GenerationError? error = null)
        {
            if (prior is null) throw new ArgumentNullException(nameof(prior));

            return prior with
            {
                State = state,
                ProviderJobId = string.IsNullOrWhiteSpace(providerJobId)
                    ? prior.ProviderJobId
                    : providerJobId,
                ResultArtifactId = resultArtifactId ?? prior.ResultArtifactId,
                Error = SanitizeError(error) ?? prior.Error,
                UpdatedAt = now,
            };
        }

        internal static GenerationError? SanitizeError(GenerationError? error)
        {
            if (error is null) return null;
            var message = SanitizeMessage(error.Message);
            var providerCode = SanitizeProviderErrorCode(error.ProviderErrorCode);
            return new GenerationError(
                error.Code,
                message,
                error.Retryable,
                error.Field,
                providerCode,
                ProviderDetail: null);
        }

        internal static string SanitizeMessage(string? message)
        {
            if (string.IsNullOrWhiteSpace(message))
                return RedactedMessage;

            var normalized = ControlChars.Replace(message, " ").Trim();
            foreach (var banned in BannedSubstrings)
            {
                if (normalized.IndexOf(banned, StringComparison.OrdinalIgnoreCase) >= 0)
                    return RedactedMessage;
            }

            return normalized.Length <= MaxMessageLength
                ? normalized
                : normalized.Substring(0, MaxMessageLength);
        }

        private static string? SanitizeProviderErrorCode(string? providerErrorCode)
        {
            if (string.IsNullOrWhiteSpace(providerErrorCode)) return null;
            var trimmed = providerErrorCode.Trim();
            if (trimmed.Length > MaxProviderErrorCodeLength) return null;
            foreach (var ch in trimmed)
            {
                if (!(char.IsLetterOrDigit(ch) || ch == '_' || ch == '-' || ch == '.'))
                    return null;
            }
            return trimmed;
        }
    }
}
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobLedgerRecordFactoryTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerRecord.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerRecordFactory.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobLedgerRecordFactoryTests.cs
git commit -m "feat(vision): add image job ledger record"
```

---

## Task 2: Add JSONL Image Job Ledger

**Files:**
- Create: `src/Rook/Services/Vision/Image/Jobs/IImageJobLedger.cs`
- Create: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerReadResult.cs`
- Create: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerReadError.cs`
- Create: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerReadErrorReason.cs`
- Create: `src/Rook/Services/Vision/Image/Jobs/ImageJobLedgerWarning.cs`
- Create: `src/Rook/Services/Vision/Image/Jobs/JsonlImageJobLedger.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/JsonlImageJobLedgerTests.cs`

- [ ] **Step 1: Write failing JSONL ledger tests**

Create `src/Rook.Tests/Services/Vision/Image/Jobs/JsonlImageJobLedgerTests.cs`:

```csharp
using System;
using System.IO;
using System.Linq;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class JsonlImageJobLedgerTests : IDisposable
    {
        private readonly string _root = Path.Combine(
            Path.GetTempPath(),
            $"rook-image-ledger-{Guid.NewGuid():N}");

        public void Dispose()
        {
            if (Directory.Exists(_root))
                Directory.Delete(_root, recursive: true);
        }

        [Fact]
        public void Append_and_read_compacts_last_record_per_job()
        {
            var ledger = Ledger();
            var jobId = Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
            var first = Initial(jobId, ImageJobState.Queued);
            var second = ImageJobLedgerRecordFactory.WithState(
                first,
                ImageJobState.Polling,
                first.UpdatedAt.AddSeconds(1),
                providerJobId: "prediction-123");

            ledger.Append(first);
            ledger.Append(second);

            var read = ledger.ReadAll();

            Assert.Empty(read.Errors);
            var record = Assert.Single(read.Records);
            Assert.Equal(ImageJobState.Polling, record.State);
            Assert.Equal("prediction-123", record.ProviderJobId);
        }

        [Fact]
        public void ReadAll_line_scopes_malformed_json()
        {
            var path = LedgerPath();
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, "{bad-json\r\n");
            var ledger = new JsonlImageJobLedger(path);

            var read = ledger.ReadAll();

            Assert.Empty(read.Records);
            var error = Assert.Single(read.Errors);
            Assert.Equal(ImageJobLedgerReadErrorReason.MalformedJson, error.Reason);
            Assert.DoesNotContain("{bad-json", error.Message);
        }

        [Fact]
        public void ReadAll_rejects_complete_without_result_artifact_id()
        {
            var path = LedgerPath();
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path,
                "{\"schema_version\":1,\"job_id\":\"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb\",\"provider\":\"replicate\",\"model\":\"black-forest-labs/flux-schnell\",\"provider_job_id\":null,\"state\":\"Complete\",\"result_artifact_id\":null,\"error\":null,\"created_at\":\"2026-05-04T12:00:00.0000000+00:00\",\"updated_at\":\"2026-05-04T12:00:00.0000000+00:00\"}\r\n");
            var ledger = new JsonlImageJobLedger(path);

            var read = ledger.ReadAll();

            Assert.Empty(read.Records);
            var error = Assert.Single(read.Errors);
            Assert.Equal(ImageJobLedgerReadErrorReason.MissingRequiredField, error.Reason);
            Assert.Equal("result_artifact_id", error.FieldPath);
        }

        [Fact]
        public void Serialize_uses_provider_not_provider_name_and_omits_unsafe_fields()
        {
            var ledger = Ledger();
            var record = ImageJobLedgerRecordFactory.WithState(
                Initial(Guid.Parse("cccccccc-cccc-cccc-cccc-cccccccccccc"), ImageJobState.Error),
                ImageJobState.Error,
                DateTimeOffset.Parse("2026-05-04T12:00:01Z"),
                providerJobId: "prediction-456",
                error: new GenerationError(
                    GenerationErrorCode.ExecutionFailed,
                    "Provider returned urls.cancel=https://api.replicate.com/x",
                    Retryable: false,
                    ProviderErrorCode: "E456"));

            ledger.Append(record);
            var text = File.ReadAllText(LedgerPath());

            Assert.Contains("\"provider\":\"replicate\"", text);
            Assert.DoesNotContain("provider_name", text);
            Assert.DoesNotContain("urls.cancel", text);
            Assert.DoesNotContain("api.replicate.com", text);
            Assert.DoesNotContain("replicate.delivery", text);
            Assert.DoesNotContain("provider_detail", text);
            Assert.Contains("Image job failed; provider details were redacted.", text);
        }

        private JsonlImageJobLedger Ledger() => new(LedgerPath());
        private string LedgerPath() => Path.Combine(_root, "image", "job-ledger.jsonl");

        private static ImageJobLedgerRecord Initial(Guid jobId, ImageJobState state) =>
            ImageJobLedgerRecordFactory.FromInitial(
                jobId,
                "replicate",
                "black-forest-labs/flux-schnell",
                state,
                DateTimeOffset.Parse("2026-05-04T12:00:00Z"));
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter JsonlImageJobLedgerTests
```

Expected: compile failure because ledger types do not exist.

- [ ] **Step 3: Add ledger seam and read types**

Create `IImageJobLedger.cs`, `ImageJobLedgerReadResult.cs`, `ImageJobLedgerReadErrorReason.cs`, `ImageJobLedgerReadError.cs`, and `ImageJobLedgerWarning.cs`:

```csharp
namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobLedger
    {
        void Append(ImageJobLedgerRecord record);
        ImageJobLedgerReadResult ReadAll();
    }
}
```

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobLedgerReadResult
    {
        public ImageJobLedgerReadResult(
            IReadOnlyList<ImageJobLedgerRecord> records,
            IReadOnlyList<ImageJobLedgerReadError> errors)
        {
            Records = records ?? throw new ArgumentNullException(nameof(records));
            Errors = errors ?? throw new ArgumentNullException(nameof(errors));
        }

        public IReadOnlyList<ImageJobLedgerRecord> Records { get; }
        public IReadOnlyList<ImageJobLedgerReadError> Errors { get; }
    }
}
```

```csharp
namespace Rook.Services.Vision.Image.Jobs
{
    public enum ImageJobLedgerReadErrorReason
    {
        MalformedJson = 0,
        UnsupportedSchemaVersion = 1,
        MissingRequiredField = 2,
    }
}
```

```csharp
namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobLedgerReadError(
        int LineNumber,
        ImageJobLedgerReadErrorReason Reason,
        string Message,
        string? FieldPath);
}
```

```csharp
namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobLedgerWarning(
        int LineNumber,
        ImageJobLedgerReadErrorReason Reason,
        string Message,
        string? FieldPath);
}
```

- [ ] **Step 4: Add JSONL ledger**

Create `src/Rook/Services/Vision/Image/Jobs/JsonlImageJobLedger.cs` by following `JsonlVideoJobLedger` structure, but use the narrower image schema. The implementation must include these members exactly:

```csharp
public sealed class JsonlImageJobLedger : IImageJobLedger
{
    private readonly string _filePath;
    private readonly object _lock = new();

    public JsonlImageJobLedger() : this(DefaultPath()) { }
    public JsonlImageJobLedger(string filePath)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("filePath must be non-empty.", nameof(filePath));
        _filePath = filePath;
    }
    public string FilePath => _filePath;

    public static string DefaultPath()
    {
        return System.IO.Path.Combine(RookPaths.SettingsRoot, "image", "job-ledger.jsonl");
    }

    public void Append(ImageJobLedgerRecord record)
    {
        if (record is null) throw new ArgumentNullException(nameof(record));
        var line = SerializeRecord(record);
        lock (_lock)
        {
            var dir = System.IO.Path.GetDirectoryName(_filePath);
            if (!string.IsNullOrEmpty(dir) && !System.IO.Directory.Exists(dir))
                System.IO.Directory.CreateDirectory(dir);
            using var stream = new System.IO.FileStream(
                _filePath,
                System.IO.FileMode.Append,
                System.IO.FileAccess.Write,
                System.IO.FileShare.Read);
            using var writer = new System.IO.StreamWriter(
                stream,
                new System.Text.UTF8Encoding(false));
            writer.WriteLine(line);
        }
    }

    public ImageJobLedgerReadResult ReadAll()
    {
        if (!System.IO.File.Exists(_filePath))
            return new ImageJobLedgerReadResult(
                Array.Empty<ImageJobLedgerRecord>(),
                Array.Empty<ImageJobLedgerReadError>());

        string[] lines;
        lock (_lock)
        {
            lines = System.IO.File.ReadAllLines(_filePath, System.Text.Encoding.UTF8);
        }

        var byJobId = new Dictionary<Guid, ImageJobLedgerRecord>();
        var errors = new List<ImageJobLedgerReadError>();
        for (var i = 0; i < lines.Length; i++)
        {
            if (string.IsNullOrWhiteSpace(lines[i])) continue;
            var (record, error) = TryDeserialize(lines[i], i + 1);
            if (error is not null)
            {
                errors.Add(error);
                continue;
            }
            byJobId[record!.JobId] = record;
        }

        return new ImageJobLedgerReadResult(byJobId.Values.ToArray(), errors);
    }
}
```

Serialization keys must be:

```text
schema_version
job_id
provider
model
provider_job_id
state
result_artifact_id
error
created_at
updated_at
```

The `error` object keys must be:

```text
code
message
retryable
field
provider_error_code
```

Deserialization rules:

- `schema_version` must equal `ImageJobLedgerRecordFactory.CurrentSchemaVersion`.
- `job_id` must be a non-empty GUID.
- `provider`, `model`, `state`, `created_at`, and `updated_at` are required.
- `state` must parse to a defined `ImageJobState`.
- `result_artifact_id`, when present, must parse to a non-empty GUID.
- `Complete` requires `result_artifact_id`.
- errors parse to `GenerationError` with `ProviderDetail: null`.
- malformed lines return `ImageJobLedgerReadError` with sanitized message text, not raw line excerpts.

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter JsonlImageJobLedgerTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\IImageJobLedger.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerReadResult.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerReadError.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerReadErrorReason.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobLedgerWarning.cs `
        src\Rook\Services\Vision\Image\Jobs\JsonlImageJobLedger.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\JsonlImageJobLedgerTests.cs
git commit -m "feat(vision): add image job JSONL ledger"
```

---

## Task 3: Add Fake Ledger And Manager Submit Durability

**Files:**
- Create: `src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobLedger.cs`
- Modify: `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`

- [ ] **Step 1: Add fake ledger**

Create `src/Rook.Tests/Services/Vision/Image/Jobs/FakeImageJobLedger.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Image.Jobs;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public sealed class FakeImageJobLedger : IImageJobLedger
    {
        private readonly List<ImageJobLedgerRecord> _records = new();
        private readonly object _lock = new();

        public Action<ImageJobLedgerRecord>? BeforeAppend { get; set; }
        public IReadOnlyList<ImageJobLedgerRecord> AllRecords
        {
            get { lock (_lock) return _records.ToArray(); }
        }

        public void Append(ImageJobLedgerRecord record)
        {
            BeforeAppend?.Invoke(record);
            lock (_lock) _records.Add(record);
        }

        public ImageJobLedgerReadResult ReadAll()
        {
            lock (_lock)
            {
                var byId = new Dictionary<Guid, ImageJobLedgerRecord>();
                foreach (var record in _records)
                    byId[record.JobId] = record;
                return new ImageJobLedgerReadResult(
                    byId.Values.ToArray(),
                    Array.Empty<ImageJobLedgerReadError>());
            }
        }
    }
}
```

- [ ] **Step 2: Add failing submit durability tests**

In `ImageJobManagerTests`, add `_ledger` field initialized with the other test fields and update the `Manager(...)` helper in this task to accept/use it. Add tests:

```csharp
[Fact]
public async Task SubmitAsync_AppendsQueuedLedgerRecordBeforeBackgroundWork()
{
    using var manager = Manager();

    var submit = await manager.SubmitAsync(Start(), CancellationToken.None);

    Assert.Equal(ImageJobState.Queued, submit.State);
    var queued = Assert.Single(_ledger.AllRecords, r => r.JobId == submit.JobId);
    Assert.Equal(ImageJobState.Queued, queued.State);
    Assert.Equal(GeminiImageCapabilities.ProviderName, queued.Provider);
    Assert.Equal(GeminiImageCapabilities.DefaultModel, queued.Model);
    Assert.Null(queued.ProviderJobId);
}

[Fact]
public async Task SubmitAsync_WhenInitialLedgerAppendFails_DoesNotCallProviderOrTrackRunningJob()
{
    _ledger.BeforeAppend = _ => throw new IOException("ledger unavailable");
    using var manager = Manager();

    var submit = await manager.SubmitAsync(Start(), CancellationToken.None);

    Assert.Equal(ImageJobState.Error, submit.State);
    Assert.NotNull(submit.Error);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, submit.Error!.Code);
    Assert.DoesNotContain("Submit", _provider.Calls);
    await WaitForRunningJobCountAsync(manager, 0);
}
```

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "SubmitAsync_AppendsQueuedLedgerRecordBeforeBackgroundWork|SubmitAsync_WhenInitialLedgerAppendFails"
```

Expected: compile failure or test failure because manager does not accept/append ledger records.

- [ ] **Step 4: Add ledger constructor support and initial append**

Modify `ImageJobManager`:

- add field `private readonly IImageJobLedger _ledger;`
- extend `ImageJobRecord` with `CreatedAt` before `UpdatedAt`, update its constructor call sites, and preserve `CreatedAt` across `BuildTransition`;
- constructors default to `new JsonlImageJobLedger()`;
- internal constructor accepts `IImageJobLedger? ledger`;
- add helper:

```csharp
private bool TryAppendLedger(
    ImageJobLedgerRecord record,
    out GenerationError? error)
{
    try
    {
        _ledger.Append(record);
        error = null;
        return true;
    }
    catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
    {
        error = new GenerationError(
            GenerationErrorCode.DependencyUnavailable,
            $"Image job ledger is unavailable: {ex.Message}",
            Retryable: true);
        return false;
    }
}
```

In `SubmitAsync`, before adding `_records`/`_runningJobs`, build and append:

```csharp
var now = _clock.UtcNow();
var initial = new ImageJobRecord(
    jobId,
    ImageJobState.Queued,
    model.ModelId,
    model.ProviderName,
    createdAt: now,
    updatedAt: now);
var durable = ImageJobLedgerRecordFactory.FromInitial(
    jobId,
    model.ProviderName,
    model.ModelId,
    ImageJobState.Queued,
    now);
if (!TryAppendLedger(durable, out var appendError))
    return Task.FromResult(ImageJobSubmitResult.Fail(appendError!));
```

Only after append succeeds, write `_records[jobId]`, create the CTS, add `_runningJobs`, and start the task.

- [ ] **Step 5: Update test helper**

In `ImageJobManagerTests`, add:

```csharp
private readonly FakeImageJobLedger _ledger = new();
```

Pass it into the manager helper:

```csharp
ledger: _ledger,
```

Add the new constructor argument to the helper signature:

```csharp
private ImageJobManager Manager(
    TimeSpan? pollInterval = null,
    ImageArtifactMaterializer? materializer = null,
    ImageArtifactRequestFactorySelector? selector = null,
    IImageJobLedger? ledger = null) =>
    new(
        registry: _registry,
        artifactStore: _artifactStore,
        clock: _clock,
        idGenerator: _idGenerator,
        pollInterval: pollInterval ?? TimeSpan.FromMilliseconds(1),
        maxConcurrentJobs: ImageJobManager.DefaultMaxConcurrentJobs,
        materializer: materializer,
        requestFactorySelector: selector,
        ledger: ledger ?? _ledger);
```

- [ ] **Step 6: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "SubmitAsync_AppendsQueuedLedgerRecordBeforeBackgroundWork|SubmitAsync_WhenInitialLedgerAppendFails|SubmitAsync_SyncProvider_CompletesAndWritesArtifact"
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\FakeImageJobLedger.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobManagerTests.cs
git commit -m "feat(vision): append durable image job submits"
```

---

## Task 4: Append Durable State Transitions And Handle Append Failures

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`

- [ ] **Step 1: Add failing transition tests**

Add tests to `ImageJobManagerTests`:

```csharp
[Fact]
public async Task AsyncSubmit_PersistsOnlyProviderJobIdOnPolling()
{
    _provider.OnSubmit = (_, _) => new QueuedSubmitOutcome(new ProviderJobHandle(
        "prediction-789",
        statusUrl: new Uri("https://api.replicate.com/v1/predictions/prediction-789"),
        cancelUrl: new Uri("https://api.replicate.com/v1/predictions/prediction-789/cancel"),
        cancelHttpMethod: "POST",
        providerResultToken: "https://replicate.delivery/out.png"));
    _provider.OnGetStatus = _ => FakeImageProvider.Running();
    using var manager = Manager(pollInterval: TimeSpan.FromSeconds(5));

    var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
    await WaitForStateAsync(manager, submit.JobId!.Value, ImageJobState.Polling);

    var polling = _ledger.AllRecords.Last(r => r.JobId == submit.JobId.Value);
    Assert.Equal(ImageJobState.Polling, polling.State);
    Assert.Equal("prediction-789", polling.ProviderJobId);
    var serialized = System.Text.Json.JsonSerializer.Serialize(polling);
    Assert.DoesNotContain("api.replicate.com", serialized);
    Assert.DoesNotContain("replicate.delivery", serialized);
}

[Fact]
public async Task PollingLedgerAppendFailure_AttemptsProviderCancelAndStopsPolling()
{
    _provider.OnSubmit = (_, _) => FakeImageProvider.Queued("prediction-fail-ledger");
    var cancelCalls = 0;
    _provider.OnCancel = handle =>
    {
        cancelCalls++;
        Assert.Equal("prediction-fail-ledger", handle.ProviderJobId);
        return new CanceledOutcome();
    };
    _ledger.BeforeAppend = record =>
    {
        if (record.State == ImageJobState.Polling)
            throw new IOException("cannot persist provider id");
    };
    using var manager = Manager();

    var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
    var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

    Assert.Equal(ImageJobState.Error, status.State);
    Assert.Equal(1, cancelCalls);
    Assert.DoesNotContain(_ledger.AllRecords, r =>
        r.JobId == submit.JobId.Value && r.State == ImageJobState.Polling);
}

[Fact]
public async Task CompleteTransition_AppendsSingleDurableComplete()
{
    using var manager = Manager();

    var submit = await manager.SubmitAsync(Start(), CancellationToken.None);
    var status = await WaitForTerminalAsync(manager, submit.JobId!.Value);

    Assert.Equal(ImageJobState.Complete, status.State);
    var complete = Assert.Single(_ledger.AllRecords, r =>
        r.JobId == submit.JobId.Value && r.State == ImageJobState.Complete);
    Assert.Equal(status.ResultArtifactId, complete.ResultArtifactId);
}
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "AsyncSubmit_PersistsOnlyProviderJobIdOnPolling|PollingLedgerAppendFailure|CompleteTransition_AppendsSingleDurableComplete"
```

Expected: FAIL because transitions are not ledger-backed.

- [ ] **Step 3: Add transition helper**

In `ImageJobManager`, add a durable transition helper that updates `_records` and appends only when the transition wins:

```csharp
private bool TryTransitionWithLedger(
    ImageJobRecord prior,
    ImageJobState state,
    out ImageJobRecord next,
    out GenerationError? appendError,
    ProviderJobHandle? providerHandle = null,
    Guid? resultArtifactId = null,
    GenerationError? error = null)
{
    appendError = null;
    while (true)
    {
        var latest = LatestRecord(prior.JobId, prior);
        if (IsTerminal(latest.State))
        {
            next = latest;
            return false;
        }

        var candidate = BuildTransition(
            latest,
            state,
            providerHandle,
            resultArtifactId,
            error);
        var priorDurable = ToLedgerRecord(latest);
        var durable = ImageJobLedgerRecordFactory.WithState(
            priorDurable,
            state,
            candidate.UpdatedAt,
            providerJobId: providerHandle?.ProviderJobId,
            resultArtifactId: resultArtifactId,
            error: error);

        if (!_records.TryUpdate(latest.JobId, candidate, latest))
        {
            if (!_records.TryGetValue(latest.JobId, out var observed))
            {
                next = latest;
                return false;
            }
            if (IsTerminal(observed.State))
            {
                next = observed;
                return false;
            }
            prior = Freshest(observed, latest);
            continue;
        }

        if (!TryAppendLedger(durable, out appendError))
        {
            next = candidate;
            return false;
        }

        next = candidate;
        return true;
    }
}
```

Add `ToLedgerRecord(ImageJobRecord record)` that maps only safe fields:

```csharp
private ImageJobLedgerRecord ToLedgerRecord(ImageJobRecord record) =>
    new(
        ImageJobLedgerRecordFactory.CurrentSchemaVersion,
        record.JobId,
        record.Provider,
        record.Model,
        record.ProviderHandle?.ProviderJobId,
        record.State,
        record.ResultArtifactId,
        ImageJobLedgerRecordFactory.SanitizeError(record.Error),
        record.CreatedAt,
        record.UpdatedAt);
```

- [ ] **Step 4: Wire transitions**

Replace calls that currently use `Transition(...)` for durable lifecycle states with `TryTransitionWithLedger(...)`. For append failure:

- before provider id exists: mark local job `Error` and stop;
- when provider id append fails: call `TryRemoteCancelAsync(provider, handle, CancellationToken.None)` best-effort, mark local job `Error`, stop;
- after provider id exists: mark local job `Error`, stop, and avoid later terminal append.

Keep `BuildTransition` as the pure record builder.

- [ ] **Step 5: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobManagerTests"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobManagerTests.cs
git commit -m "feat(vision): persist image job transitions"
```

---

## Task 5: Durable Reads, Status/List/Result After Manager Restart

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`
- Test: `src/Rook.Tests/Handlers/ImageJobOpHandlerTests.cs`

- [ ] **Step 1: Add failing restart read tests**

Add to `ImageJobManagerTests`:

```csharp
[Fact]
public async Task StatusAndList_SurviveNewManagerOverSameLedger()
{
    using (var first = Manager())
    {
        var submit = await first.SubmitAsync(Start(), CancellationToken.None);
        _ = await WaitForTerminalAsync(first, submit.JobId!.Value);
    }
    using var second = Manager();

    var jobs = await second.ListJobsAsync(10, CancellationToken.None);
    var record = Assert.Single(jobs.Jobs);
    var status = await second.GetStatusAsync(record.JobId, CancellationToken.None);

    Assert.Equal(ImageJobState.Complete, record.State);
    Assert.Equal(ImageJobState.Complete, status.State);
    Assert.NotNull(status.ResultArtifactId);
}

[Fact]
public async Task FetchResultAsync_AfterRestart_VerifiesArtifactExists()
{
    Guid jobId;
    Guid artifactId;
    using (var first = Manager())
    {
        var submit = await first.SubmitAsync(Start(), CancellationToken.None);
        var complete = await WaitForTerminalAsync(first, submit.JobId!.Value);
        jobId = submit.JobId.Value;
        artifactId = complete.ResultArtifactId!.Value;
    }
    using var second = Manager();

    var fetch = await second.FetchResultAsync(jobId, CancellationToken.None);

    Assert.Equal(ImageJobState.Complete, fetch.State);
    Assert.Equal(artifactId, fetch.ResultArtifactId);
    Assert.Equal($"/blob/{artifactId:D}/image", Assert.Single(fetch.Files!).Path);
}

[Fact]
public async Task FetchResultAsync_AfterRestartMissingArtifact_ReturnsDependencyUnavailable()
{
    Guid jobId;
    Guid artifactId;
    using (var first = Manager())
    {
        var submit = await first.SubmitAsync(Start(), CancellationToken.None);
        var complete = await WaitForTerminalAsync(first, submit.JobId!.Value);
        jobId = submit.JobId.Value;
        artifactId = complete.ResultArtifactId!.Value;
    }
    Assert.True(_artifactStore.Delete(artifactId));
    using var second = Manager();

    var fetch = await second.FetchResultAsync(jobId, CancellationToken.None);

    Assert.Equal(ImageJobState.Error, fetch.State);
    Assert.Equal(GenerationErrorCode.DependencyUnavailable, fetch.Error!.Code);
    Assert.Equal("result_artifact_id", fetch.Error.Field);
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "StatusAndList_SurviveNewManager|FetchResultAsync_AfterRestart"
```

Expected: FAIL because reads still use in-memory `_records` only.

- [ ] **Step 3: Add live/durable freshness merge**

In `ImageJobManager`, add:

```csharp
private ImageJobRecord? FindLatestMergedRecord(Guid jobId)
{
    _runningJobs.TryGetValue(jobId, out var running);
    var live = running?.LatestRecord ?? (_records.TryGetValue(jobId, out var local) ? local : null);
    var durable = FindDurableRecord(jobId);
    return FreshestForRead(live, durable);
}

private ImageJobRecord? FindDurableRecord(Guid jobId)
{
    var read = _ledger.ReadAll();
    foreach (var record in read.Records)
        if (record.JobId == jobId)
            return FromLedgerRecord(record);
    return null;
}

private static ImageJobRecord? FreshestForRead(ImageJobRecord? live, ImageJobRecord? durable)
{
    if (live is null) return durable;
    if (durable is null) return live;
    if (durable.UpdatedAt > live.UpdatedAt) return durable;
    if (live.UpdatedAt > durable.UpdatedAt) return live;
    if (IsTerminal(durable.State)) return durable;
    return live;
}
```

Add `FromLedgerRecord(ImageJobLedgerRecord record)`:

```csharp
private static ImageJobRecord FromLedgerRecord(ImageJobLedgerRecord record) =>
    new(
        record.JobId,
        record.State,
        record.Model,
        record.Provider,
        createdAt: record.CreatedAt,
        updatedAt: record.UpdatedAt,
        providerHandle: string.IsNullOrWhiteSpace(record.ProviderJobId)
            ? null
            : new ProviderJobHandle(record.ProviderJobId),
        resultArtifactId: record.ResultArtifactId,
        error: record.Error);
```

Use `FindLatestMergedRecord` in `GetStatusAsync` and `FetchResultAsync`. Use `_ledger.ReadAll()` plus live merge in `ListJobsAsync`.

- [ ] **Step 4: Ensure bridge projections stay stable**

Leave `ImageJobOpHandler.JobToObj` projecting `provider_name`. Do not add `provider_job_id` or `warnings` to bridge response dictionaries in this task.

- [ ] **Step 5: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobManagerTests|ImageJobOpHandlerTests"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobManagerTests.cs `
        src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs
git commit -m "feat(vision): read durable image job state"
```

---

## Task 6: Add Interrupted Reconcile And Cancel After Restart

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Jobs/IImageJobManager.cs`
- Modify: `src/Rook/Services/Vision/Image/Jobs/ImageJobManager.cs`
- Test: `src/Rook.Tests/Services/Vision/Image/Jobs/ImageJobManagerTests.cs`

- [ ] **Step 1: Add failing reconcile and cancel-after-restart tests**

Add to `ImageJobManagerTests`:

```csharp
[Theory]
[InlineData(ImageJobState.Queued)]
[InlineData(ImageJobState.Submitting)]
[InlineData(ImageJobState.Polling)]
[InlineData(ImageJobState.Materializing)]
public void ReconcileInterruptedJobs_MarksPriorNonTerminalRecordsInterrupted(ImageJobState state)
{
    var jobId = Guid.NewGuid();
    var initial = ImageJobLedgerRecordFactory.FromInitial(
        jobId,
        GeminiImageCapabilities.ProviderName,
        GeminiImageCapabilities.DefaultModel,
        state,
        _clock.UtcNow());
    var stale = state == ImageJobState.Polling
        ? ImageJobLedgerRecordFactory.WithState(
            initial,
            state,
            initial.UpdatedAt.AddSeconds(1),
            providerJobId: "provider-job-1")
        : initial;
    _ledger.Append(stale);
    using var manager = Manager();

    manager.ReconcileInterruptedJobs();

    var latest = _ledger.AllRecords.Last(r => r.JobId == jobId);
    Assert.Equal(ImageJobState.Interrupted, latest.State);
    Assert.Equal(stale.ProviderJobId, latest.ProviderJobId);
    Assert.Equal(GenerationErrorCode.Interrupted, latest.Error!.Code);
    Assert.DoesNotContain("Submit", _provider.Calls);
    Assert.DoesNotContain("GetStatus", _provider.Calls);
}

[Fact]
public void ReconcileInterruptedJobs_DoesNotTouchTerminalRecords()
{
    var jobId = Guid.NewGuid();
    var complete = ImageJobLedgerRecordFactory.WithState(
        ImageJobLedgerRecordFactory.FromInitial(
            jobId,
            GeminiImageCapabilities.ProviderName,
            GeminiImageCapabilities.DefaultModel,
            ImageJobState.Queued,
            _clock.UtcNow()),
        ImageJobState.Complete,
        _clock.UtcNow().AddSeconds(1),
        resultArtifactId: Guid.NewGuid());
    _ledger.Append(complete);
    using var manager = Manager();

    manager.ReconcileInterruptedJobs();

    Assert.Single(_ledger.AllRecords, r => r.JobId == jobId);
}

[Fact]
public async Task CancelAsync_AfterRestartInterruptedWithProviderJobId_CallsProviderCancelAndAppendsCancelled()
{
    var jobId = Guid.NewGuid();
    var interrupted = ImageJobLedgerRecordFactory.WithState(
        ImageJobLedgerRecordFactory.FromInitial(
            jobId,
            GeminiImageCapabilities.ProviderName,
            GeminiImageCapabilities.DefaultModel,
            ImageJobState.Polling,
            _clock.UtcNow()),
        ImageJobState.Interrupted,
        _clock.UtcNow().AddSeconds(1),
        providerJobId: "provider-job-cancel",
        error: new GenerationError(GenerationErrorCode.Interrupted, "interrupted", Retryable: true));
    _ledger.Append(interrupted);
    var cancelCalls = 0;
    _provider.OnCancel = handle =>
    {
        cancelCalls++;
        Assert.Equal("provider-job-cancel", handle.ProviderJobId);
        Assert.Null(handle.CancelUrl);
        Assert.Null(handle.StatusUrl);
        Assert.Null(handle.ProviderResultToken);
        return new CanceledOutcome();
    };
    using var manager = Manager();

    var result = await manager.CancelAsync(jobId, CancellationToken.None);

    Assert.Equal(ImageJobState.Cancelled, result.State);
    Assert.Equal(1, cancelCalls);
    Assert.Equal(ImageJobState.Cancelled, _ledger.AllRecords.Last(r => r.JobId == jobId).State);
}

[Fact]
public async Task CancelAsync_AfterRestartInterruptedWithoutProviderJobId_ReturnsInterruptedUnchanged()
{
    var jobId = Guid.NewGuid();
    var interrupted = ImageJobLedgerRecordFactory.WithState(
        ImageJobLedgerRecordFactory.FromInitial(
            jobId,
            GeminiImageCapabilities.ProviderName,
            GeminiImageCapabilities.DefaultModel,
            ImageJobState.Polling,
            _clock.UtcNow()),
        ImageJobState.Interrupted,
        _clock.UtcNow().AddSeconds(1),
        error: new GenerationError(GenerationErrorCode.Interrupted, "interrupted", Retryable: true));
    _ledger.Append(interrupted);
    using var manager = Manager();

    var result = await manager.CancelAsync(jobId, CancellationToken.None);

    Assert.Equal(ImageJobState.Interrupted, result.State);
    Assert.DoesNotContain("Cancel", _provider.Calls);
    Assert.Single(_ledger.AllRecords, r => r.JobId == jobId);
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReconcileInterruptedJobs|CancelAsync_AfterRestartInterrupted"
```

Expected: compile failure because `ReconcileInterruptedJobs` does not exist.

- [ ] **Step 3: Add interface method**

Modify `IImageJobManager.cs`:

```csharp
void ReconcileInterruptedJobs();
```

Update test stubs in `ImageJobOpHandlerTests`:

```csharp
public void ReconcileInterruptedJobs() { }
```

- [ ] **Step 4: Implement reconcile**

In `ImageJobManager`, add:

```csharp
public void ReconcileInterruptedJobs()
{
    var read = _ledger.ReadAll();
    var now = _clock.UtcNow();
    foreach (var record in read.Records)
    {
        if (IsTerminal(record.State)) continue;
        var interrupted = ImageJobLedgerRecordFactory.WithState(
            record,
            ImageJobState.Interrupted,
            now,
            error: new GenerationError(
                GenerationErrorCode.Interrupted,
                "Image job interrupted by plugin reload.",
                Retryable: true));
        _ledger.Append(interrupted);
    }
}
```

- [ ] **Step 5: Implement cancel-after-restart**

In `CancelAsync`, keep the live `_runningJobs` branch but re-check the freshest terminal record before remote cancel:

```csharp
var freshest = FindLatestMergedRecord(jobId);
if (freshest is not null && IsTerminal(freshest.State) && freshest.State != ImageJobState.Interrupted)
    return ImageJobCancelResult.Ok(freshest.State);
```

In the not-running branch:

- read `FindLatestMergedRecord(jobId)`;
- terminal `Complete`, `Error`, `Cancelled` return unchanged;
- `Interrupted` without provider handle returns `Interrupted`;
- `Interrupted` with `ProviderHandle.ProviderJobId` resolves provider by `record.Provider`;
- calls `TryRemoteCancelAsync(provider, new ProviderJobHandle(providerJobId), ct)`;
- appends durable `Cancelled` only after provider cancel succeeds.

- [ ] **Step 6: Run focused tests and verify pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReconcileInterruptedJobs|CancelAsync_AfterRestartInterrupted|CancelAsync"
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src\Rook\Services\Vision\Image\Jobs\IImageJobManager.cs `
        src\Rook\Services\Vision\Image\Jobs\ImageJobManager.cs `
        src\Rook.Tests\Services\Vision\Image\Jobs\ImageJobManagerTests.cs `
        src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs
git commit -m "feat(vision): reconcile interrupted image jobs"
```

---

## Task 7: Wire Root Lifecycle Reconcile

**Files:**
- Modify: `src/Rook/RookSubsystemRoot.cs`
- Modify: `src/Rook/RookPlugin.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/VideoSubsystemFactoryTests.cs`
- Test: `src/Rook.Tests/RookSubsystemRootTests.cs` if existing source-scan tests need updates

- [ ] **Step 1: Add failing root lifecycle tests**

In `VideoSubsystemFactoryTests.cs`, add tests near existing `ReconcileVideoJobsOnce` tests:

```csharp
[Fact]
public void ReconcileImageJobsOnce_RepeatedCalls_OnlyFireOnce()
{
    var root = FreshRoot();
    try
    {
        var jobId = Guid.NewGuid();
        var bundle = root.ImageJobs;
        var ledgerField = typeof(ImageJobManager).GetField(
            "_ledger",
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        var ledger = Assert.IsAssignableFrom<IImageJobLedger>(
            ledgerField!.GetValue(bundle.Manager));
        ledger.Append(ImageJobLedgerRecordFactory.FromInitial(
            jobId,
            "gemini",
            "gemini-2.5-flash-image-preview",
            ImageJobState.Polling,
            DateTimeOffset.UtcNow));

        root.ReconcileImageJobsOnce();
        root.ReconcileImageJobsOnce();
        root.ReconcileImageJobsOnce();

        var read = ledger.ReadAll();
        Assert.Equal(ImageJobState.Interrupted, Assert.Single(read.Records).State);
    }
    finally { root.DisposeVideoSubsystemIfCreated(); }
}

[Fact]
public void ReconcileImageJobsOnce_AfterDispose_ThrowsObjectDisposed()
{
    var root = FreshRoot();
    root.DisposeVideoSubsystemIfCreated();

    Assert.Throws<ObjectDisposedException>(() => root.ReconcileImageJobsOnce());
}
```

Add an internal test-only constructor seam to `RookSubsystemRoot` for `IImageJobLedger? imageLedger`, matching video's existing ledger seam. Use that seam in these tests instead of reflection when constructing `FreshRoot()`.

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReconcileImageJobsOnce"
```

Expected: compile failure because root method does not exist.

- [ ] **Step 3: Add root image reconcile**

In `RookSubsystemRoot`, add a second once flag:

```csharp
private int _imageReconcileFired = 0;
```

Add method:

```csharp
public void ReconcileImageJobsOnce()
{
    if (Interlocked.CompareExchange(ref _imageReconcileFired, 1, 0) != 0)
        return;

    try
    {
        ImageJobs.Manager.ReconcileInterruptedJobs();
    }
    catch
    {
        Volatile.Write(ref _imageReconcileFired, 0);
        throw;
    }
}
```

Construct production `ImageJobManager` with `new JsonlImageJobLedger()` explicitly in `RookSubsystemRoot`.

- [ ] **Step 4: Call reconcile from plugin startup**

In `RookPlugin.OnLoad` where video reconcile is called, add a separate non-fatal image reconcile block:

```csharp
try
{
    RookSubsystemRoot.Instance.ReconcileImageJobsOnce();
    TraceStartup("Image job subsystem reconciled (or no-op)");
}
catch (Exception ex)
{
    TraceStartup($"Image job reconcile failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
    RhinoApp.WriteLine(
        "Rook: image job reconcile failed at startup; continuing without reconcile. " +
        $"Reason: {ex.GetType().Name}.");
}
```

- [ ] **Step 5: Run root lifecycle tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReconcileImageJobsOnce|RookSubsystemRoot"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src\Rook\RookSubsystemRoot.cs `
        src\Rook\RookPlugin.cs `
        src\Rook.Tests\Services\Vision\Video\VideoSubsystemFactoryTests.cs `
        src\Rook.Tests\RookSubsystemRootTests.cs
git commit -m "feat(vision): reconcile image jobs at startup"
```

---

## Task 8: Bridge Leakage And Boundary Verification

**Files:**
- Modify tests only if verification exposes a gap.
- No production native/MCP files.

- [ ] **Step 1: Add focused bridge leakage tests if missing**

In `ImageJobOpHandlerTests`, add or update tests to assert durable response shape:

```csharp
[Fact]
public void List_DoesNotExposeProviderJobIdOrWarnings()
{
    var manager = new StubImageJobManager
    {
        ListImpl = _ => new ImageJobListResult(
            new[]
            {
                new ImageJobRecord(
                    SampleJobId,
                    ImageJobState.Interrupted,
                    "black-forest-labs/flux-schnell",
                    "replicate",
                    createdAt: DateTimeOffset.Parse("2026-05-04T12:00:00Z"),
                    updatedAt: DateTimeOffset.Parse("2026-05-04T12:00:00Z"),
                    providerHandle: new ProviderJobHandle("prediction-hidden"),
                    error: new GenerationError(
                        GenerationErrorCode.Interrupted,
                        "Image job interrupted by plugin reload.",
                        Retryable: true)),
            },
            50),
    };
    var handler = new ImageJobOpHandler(manager, NewVisionHandler());

    var response = handler.DispatchOffUi("""{"op":"image_jobs"}""");
    var json = System.Text.Json.JsonSerializer.Serialize(response.Data);

    Assert.Contains("provider_name", json);
    Assert.DoesNotContain("provider_job_id", json);
    Assert.DoesNotContain("prediction-hidden", json);
    Assert.DoesNotContain("warnings", json);
}
```

- [ ] **Step 2: Run handler tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter ImageJobOpHandlerTests
```

Expected: PASS.

- [ ] **Step 3: Run boundary scans**

Run:

```powershell
rg -n "image_generate_start|image_job_status|image_job_cancel|image_job_result|image_jobs" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected:

- no hits under `src\RookNative`;
- no hits under `mcp_server`;
- no hits in `src\Rook\InternalBridge\NativeGhBridgeRegistrar.cs`.

Run:

```powershell
rg -n "JsonlImageJobLedger|ImageJobLedgerRecord|job-ledger.jsonl|provider_job_id" src\RookNative mcp_server src\Rook\InternalBridge
```

Expected: no hits.

- [ ] **Step 4: Run leakage scan over production image job code**

Run:

```powershell
rg -n "replicate.delivery|api.replicate.com|status_url|cancel_url|response_url|provider_result_token|ProviderDetail|Bearer|api_token" src\Rook\Services\Vision\Image\Jobs src\Rook\Handlers\ImageJobOpHandler.cs
```

Expected:

- hits are allowed only in sanitizer banned-substring constants or test/source comments;
- no serializer writes these values into ledger records or bridge response data.

- [ ] **Step 5: Commit if tests changed**

If this task changed tests:

```powershell
git add src\Rook.Tests\Handlers\ImageJobOpHandlerTests.cs
git commit -m "test(vision): pin image job durability bridge boundary"
```

If no files changed, no commit is needed.

---

## Task 9: Focused And Full Verification

**Files:**
- No planned production file changes.

- [ ] **Step 1: Run image job focused tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ImageJobLedger|ImageJobManagerTests|ImageJobOpHandlerTests"
```

Expected: PASS.

- [ ] **Step 2: Run Replicate image job tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "ReplicateImageJobManagerTests|ReplicateImageProvider"
```

Expected: PASS.

- [ ] **Step 3: Run Vision surface tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "VisionWebSurfaceTests|VisionHandlerTests"
```

Expected: PASS.

- [ ] **Step 4: Run broad managed Vision suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "Vision|Image|Generation|Fal|Replicate"
```

Expected: PASS.

- [ ] **Step 5: Run full managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj
```

Expected: PASS. If the full suite cannot complete for local prerequisite reasons, record the exact command, failure, and all focused passing evidence. Do not claim full verification unless this command passes.

- [ ] **Step 6: Diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected:

- `git diff --check` clean;
- changed files limited to managed Vision image-job code/tests, root/plugin composition, and docs;
- no files under `src/RookNative/**`;
- no files under `mcp_server/**`;
- no Vision UI resource edits.

---

## Self-Review Checklist

- [ ] Image jobs write an append-only JSONL ledger.
- [ ] Image ledger record is image-specific and narrower than video.
- [ ] On-disk field is `provider`; bridge field remains `provider_name`.
- [ ] Durable error messages are sanitized before ledger write.
- [ ] `GenerationError.ProviderDetail` is never persisted.
- [ ] Initial ledger append failure fails before provider submit.
- [ ] First `provider_job_id` append failure attempts best-effort provider cancel and stops polling.
- [ ] Reads merge live and durable records by `updated_at`, with durable terminal tie-break.
- [ ] Prior non-terminal records reconcile to `Interrupted`.
- [ ] Reconcile makes no provider calls.
- [ ] Completed durable jobs fetch result only when local artifact exists.
- [ ] Cancel-after-restart uses only `provider_job_id` and provider-name resolution.
- [ ] Provider cancel failure leaves durable state unchanged.
- [ ] No request summaries are persisted.
- [ ] No Vision UI resurfacing is added.
- [ ] No native/MCP/public HTTP/`NativeGhBridgeRegistrar` exposure is added.
- [ ] Existing sync `generate` behavior remains source-image based.
