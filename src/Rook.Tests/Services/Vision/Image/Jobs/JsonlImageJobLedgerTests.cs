using System;
using System.IO;
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
