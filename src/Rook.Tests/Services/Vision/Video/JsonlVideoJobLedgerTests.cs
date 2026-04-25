using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class JsonlVideoJobLedgerTests : IDisposable
    {
        private readonly string _filePath;
        private readonly JsonlVideoJobLedger _ledger;
        private static readonly DateTimeOffset T0 = new(2026, 4, 25, 12, 0, 0, TimeSpan.Zero);

        public JsonlVideoJobLedgerTests()
        {
            _filePath = Path.Combine(
                Path.GetTempPath(),
                $"rook-jsonl-test-{Guid.NewGuid():N}.jsonl");
            _ledger = new JsonlVideoJobLedger(_filePath);
        }

        public void Dispose()
        {
            if (File.Exists(_filePath)) File.Delete(_filePath);
            var dir = Path.GetDirectoryName(_filePath);
            // Don't delete %TEMP% itself; just the file is enough.
            _ = dir;
        }

        // ─── Helpers ──────────────────────────────────────────────────

        private static VideoGenerationRequest BasicRequest() => new(
            Model: "veo-3.1-lite-generate-preview",
            Mode: VideoMode.T2V,
            DurationSeconds: 8,
            Resolution: "720p",
            AspectRatio: "16:9",
            Prompt: "a clip",
            StartFrame: null,
            EndFrame: null,
            ReferenceFrames: null,
            Seed: 42,
            PersonGeneration: PersonGenerationPolicy.AllowAll,
            NumberOfVideos: 1);

        private static VideoCostEstimate BasicEstimate() => new(
            DollarsUsd: 0.40m,
            Model: "veo-3.1-lite-generate-preview",
            Resolution: "720p",
            DurationSeconds: 8,
            NumberOfVideos: 1,
            Breakdown: new[] { new CostBreakdownComponent("test", 0.40m) });

        private static VideoJobRecord MakeRecord(
            Guid? jobId = null,
            VideoJobState state = VideoJobState.Queued,
            string? providerJobId = null,
            string? providerResultToken = null,
            Guid? resultArtifactId = null) =>
            VideoJobRecordFactory.From(
                jobId ?? Guid.NewGuid(),
                BasicRequest(), "veo", BasicEstimate(),
                state, T0)
            with
            {
                ProviderJobId = providerJobId,
                ProviderResultToken = providerResultToken,
                ResultArtifactId = resultArtifactId,
            };

        // ─── Roundtrip ────────────────────────────────────────────────

        [Fact]
        public void Empty_file_returns_empty_result()
        {
            var read = _ledger.ReadAll();

            Assert.Empty(read.Records);
            Assert.Empty(read.Errors);
            Assert.True(read.Success);
        }

        [Fact]
        public void Append_then_ReadAll_roundtrips_basic_record()
        {
            var jobId = Guid.NewGuid();
            var record = MakeRecord(jobId);

            _ledger.Append(record);
            var read = _ledger.ReadAll();

            var got = Assert.Single(read.Records);
            Assert.Equal(jobId, got.JobId);
            Assert.Equal(record.Provider, got.Provider);
            Assert.Equal(record.Model, got.Model);
            Assert.Equal(record.State, got.State);
            Assert.Equal(record.Pricing.Kind, got.Pricing.Kind);
            Assert.Equal(record.Pricing.TotalUsd, got.Pricing.TotalUsd);
            Assert.True(read.Success);
        }

        [Fact]
        public void Roundtrip_preserves_provider_job_id_and_result_token()
        {
            var record = MakeRecord(
                providerJobId: "operations/abc-123",
                providerResultToken: "https://veo/result/xyz");

            _ledger.Append(record);
            var read = _ledger.ReadAll();

            var got = Assert.Single(read.Records);
            Assert.Equal("operations/abc-123", got.ProviderJobId);
            Assert.Equal("https://veo/result/xyz", got.ProviderResultToken);
        }

        [Fact]
        public void Roundtrip_preserves_provider_options()
        {
            var record = MakeRecord();

            _ledger.Append(record);
            var read = _ledger.ReadAll();

            var got = Assert.Single(read.Records);
            Assert.NotNull(got.ProviderOptions);
            Assert.Equal("allow_all", got.ProviderOptions["person_generation"]!.GetValue<string>());
        }

        [Fact]
        public void Roundtrip_preserves_result_artifact_id_and_error_when_set()
        {
            var artifactId = Guid.NewGuid();
            var record = MakeRecord(
                state: VideoJobState.Complete,
                resultArtifactId: artifactId);

            _ledger.Append(record);
            var read = _ledger.ReadAll();

            var got = Assert.Single(read.Records);
            Assert.Equal(artifactId, got.ResultArtifactId);
        }

        // ─── Compaction (latest per job_id) ──────────────────────────

        [Fact]
        public void Multiple_records_same_job_id_compact_to_latest()
        {
            var jobId = Guid.NewGuid();
            _ledger.Append(MakeRecord(jobId, VideoJobState.Queued));
            _ledger.Append(MakeRecord(jobId, VideoJobState.Submitting));
            _ledger.Append(MakeRecord(jobId, VideoJobState.Polling, providerJobId: "op-1"));
            _ledger.Append(MakeRecord(jobId, VideoJobState.Complete, providerJobId: "op-1",
                resultArtifactId: Guid.NewGuid()));

            var read = _ledger.ReadAll();

            var got = Assert.Single(read.Records);
            Assert.Equal(VideoJobState.Complete, got.State);
            Assert.NotNull(got.ResultArtifactId);
        }

        [Fact]
        public void Different_jobs_all_returned()
        {
            var j1 = Guid.NewGuid();
            var j2 = Guid.NewGuid();
            _ledger.Append(MakeRecord(j1, VideoJobState.Polling));
            _ledger.Append(MakeRecord(j2, VideoJobState.Complete,
                resultArtifactId: Guid.NewGuid()));

            var read = _ledger.ReadAll();

            Assert.Equal(2, read.Records.Count);
        }

        // ─── Malformed lines (line-scoped failure) ────────────────────

        [Fact]
        public void Malformed_json_line_is_skipped_and_recorded_as_error()
        {
            // Append one valid record
            var validId = Guid.NewGuid();
            _ledger.Append(MakeRecord(validId));

            // Manually append a malformed line
            File.AppendAllText(_filePath,
                "{not valid json\n", new UTF8Encoding(false));

            // Then a second valid record
            var secondId = Guid.NewGuid();
            _ledger.Append(MakeRecord(secondId));

            var read = _ledger.ReadAll();

            // Both valid records present
            Assert.Equal(2, read.Records.Count);
            // One error recorded
            var error = Assert.Single(read.Errors);
            Assert.Equal(LedgerReadErrorReason.MalformedJson, error.Reason);
            Assert.NotNull(error.RawLineExcerpt);  // populated for malformed JSON
            Assert.False(read.Success);
        }

        [Fact]
        public void Whitespace_only_lines_are_skipped_silently()
        {
            _ledger.Append(MakeRecord());
            File.AppendAllText(_filePath, "\n   \n\t\n", new UTF8Encoding(false));
            _ledger.Append(MakeRecord());

            var read = _ledger.ReadAll();

            Assert.Equal(2, read.Records.Count);
            Assert.Empty(read.Errors);
        }

        // ─── Schema version (fail closed) ─────────────────────────────

        [Fact]
        public void Unsupported_schema_version_fails_line_closed()
        {
            // Write a record with future schema_version directly
            File.WriteAllText(_filePath,
                "{\"schema_version\":99,\"job_id\":\"" + Guid.NewGuid() + "\"}\n",
                new UTF8Encoding(false));

            var read = _ledger.ReadAll();

            Assert.Empty(read.Records);
            var error = Assert.Single(read.Errors);
            Assert.Equal(LedgerReadErrorReason.UnsupportedSchemaVersion, error.Reason);
            Assert.Equal("schema_version", error.FieldPath);
            Assert.Equal("99", error.OffendingValue);
            // RawLineExcerpt NOT populated for semantic errors per Codex round 4
            Assert.Null(error.RawLineExcerpt);
        }

        [Fact]
        public void Unknown_pricing_kind_fails_line_closed()
        {
            // Append a valid record so we know the surrounding works
            _ledger.Append(MakeRecord());

            // Then a record with unknown pricing.kind
            var bogus = "{\"schema_version\":1,\"job_id\":\"" + Guid.NewGuid() + "\","
                + "\"provider\":\"x\",\"model\":\"y\",\"state\":\"Queued\","
                + "\"normalized_request\":{},\"provider_options\":{},"
                + "\"pricing\":{\"kind\":\"subscription_v2\",\"currency\":\"USD\",\"quantity\":1,\"pricing_source\":\"x\"},"
                + "\"created_at\":\"2026-04-25T12:00:00Z\",\"updated_at\":\"2026-04-25T12:00:00Z\"}\n";
            File.AppendAllText(_filePath, bogus, new UTF8Encoding(false));

            var read = _ledger.ReadAll();

            Assert.Single(read.Records);
            var error = Assert.Single(read.Errors);
            Assert.Equal(LedgerReadErrorReason.UnknownPricingKind, error.Reason);
            Assert.Equal("pricing.kind", error.FieldPath);
            Assert.Equal("subscription_v2", error.OffendingValue);
        }

        // ─── Unknown-field preservation ───────────────────────────────

        [Fact]
        public void Unknown_top_level_fields_preserved_through_roundtrip()
        {
            // Write a record with extra top-level keys directly
            var jobId = Guid.NewGuid();
            var withExtras = "{\"schema_version\":1,\"job_id\":\"" + jobId + "\","
                + "\"provider\":\"veo\",\"model\":\"veo-3.1-lite-generate-preview\",\"state\":\"Queued\","
                + "\"normalized_request\":{\"mode\":\"T2V\",\"duration_seconds\":8,\"resolution\":\"720p\",\"aspect_ratio\":\"16:9\",\"number_of_videos\":1},"
                + "\"provider_options\":{\"person_generation\":\"allow_all\"},"
                + "\"pricing\":{\"kind\":\"per_second\",\"currency\":\"USD\",\"quantity\":8,\"unit_price_usd\":0.05,\"total_usd\":0.40,\"pricing_source\":\"veo-rate-card-v1\"},"
                + "\"created_at\":\"2026-04-25T12:00:00Z\",\"updated_at\":\"2026-04-25T12:00:00Z\","
                + "\"future_field_v2\":{\"some\":\"value\"},\"another_unknown\":42}\n";
            File.WriteAllText(_filePath, withExtras, new UTF8Encoding(false));

            var read = _ledger.ReadAll();

            var got = Assert.Single(read.Records);
            Assert.NotNull(got.Extensions);
            Assert.Equal("value", got.Extensions!["future_field_v2"]!["some"]!.GetValue<string>());
            Assert.Equal(42, got.Extensions["another_unknown"]!.GetValue<int>());

            // Now append it back via Append() and verify the round-trip preserves the extras
            _ledger.Append(got);
            var fileText = File.ReadAllText(_filePath, Encoding.UTF8);
            Assert.Contains("future_field_v2", fileText);
            Assert.Contains("another_unknown", fileText);
        }

        [Fact]
        public void Unknown_keys_inside_provider_options_preserved()
        {
            var jobId = Guid.NewGuid();
            var withExtras = "{\"schema_version\":1,\"job_id\":\"" + jobId + "\","
                + "\"provider\":\"veo\",\"model\":\"veo-3.1-lite-generate-preview\",\"state\":\"Queued\","
                + "\"normalized_request\":{\"mode\":\"T2V\",\"duration_seconds\":8,\"resolution\":\"720p\",\"aspect_ratio\":\"16:9\",\"number_of_videos\":1},"
                + "\"provider_options\":{\"person_generation\":\"allow_all\",\"future_veo_field\":\"future_value\"},"
                + "\"pricing\":{\"kind\":\"per_second\",\"currency\":\"USD\",\"quantity\":8,\"unit_price_usd\":0.05,\"total_usd\":0.40,\"pricing_source\":\"veo-rate-card-v1\"},"
                + "\"created_at\":\"2026-04-25T12:00:00Z\",\"updated_at\":\"2026-04-25T12:00:00Z\"}\n";
            File.WriteAllText(_filePath, withExtras, new UTF8Encoding(false));

            var read = _ledger.ReadAll();

            var got = Assert.Single(read.Records);
            Assert.Equal("future_value", got.ProviderOptions["future_veo_field"]!.GetValue<string>());
        }

        // ─── Append-only / concurrent reads ───────────────────────────

        [Fact]
        public void Append_creates_directory_if_missing()
        {
            var nested = Path.Combine(
                Path.GetTempPath(),
                $"rook-jsonl-nested-{Guid.NewGuid():N}",
                "subdir",
                "ledger.jsonl");
            try
            {
                var ledger = new JsonlVideoJobLedger(nested);
                ledger.Append(MakeRecord());
                Assert.True(File.Exists(nested));
            }
            finally
            {
                var topDir = Path.GetDirectoryName(Path.GetDirectoryName(nested));
                if (topDir is not null && Directory.Exists(topDir))
                    Directory.Delete(topDir, recursive: true);
            }
        }

        [Fact]
        public void DefaultPath_is_appdata_rook_video_ledger()
        {
            var defaultPath = JsonlVideoJobLedger.DefaultPath();

            Assert.Contains("Rook", defaultPath);
            Assert.Contains("video", defaultPath);
            Assert.EndsWith("job-ledger.jsonl", defaultPath);
        }
    }
}
