using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// V1c bit-identity tripwire: the JSONL line produced by V1c's
    /// (factory + codec + pricing-model) chain through
    /// <see cref="JsonlVideoJobLedger.Append"/> must remain byte-identical
    /// to V1b's output for the same logical request. Pinned fixtures here
    /// represent V1b output as documented; future drift in V1c's
    /// serialization fails this test loudly.
    ///
    /// Per Codex Finding 4: tests use only production ledger API
    /// (<see cref="JsonlVideoJobLedger.Append"/> + <see cref="JsonlVideoJobLedger.ReadAll"/>)
    /// + stock file IO; no test-only ledger parse/serialize public surface.
    ///
    /// Per Codex Finding 6: byte equality is scoped to the file output of
    /// <see cref="JsonlVideoJobLedger.Append"/>, NOT to codec
    /// <c>JsonObject.ToJsonString()</c> output (codec tests use semantic
    /// JSON assertions instead).
    /// </summary>
    public class VideoJobRecordFactoryByteIdentityTests : IDisposable
    {
        private static readonly DateTimeOffset T0 = new(2026, 4, 25, 12, 0, 0, TimeSpan.Zero);
        private static readonly Guid PinnedJobId = new("11111111-1111-1111-1111-111111111111");

        private readonly List<string> _tempFiles = new();

        public void Dispose()
        {
            foreach (var p in _tempFiles)
                if (File.Exists(p)) File.Delete(p);
        }

        private string NewLedgerPath()
        {
            var p = Path.Combine(Path.GetTempPath(),
                $"rook-bitident-{Guid.NewGuid():N}.jsonl");
            _tempFiles.Add(p);
            return p;
        }

        private static VideoCostEstimate EstimateFor(
            ResolvedVideoModel model, VideoGenerationRequest req)
        {
            var result = new VideoCostEstimator().Estimate(model, req);
            Assert.True(result.Success, $"Estimator failed: {result.Error?.Message}");
            return result.Estimate!;
        }

        private string AppendAndReadLine(VideoJobRecord rec)
        {
            var path = NewLedgerPath();
            var ledger = new JsonlVideoJobLedger(path);
            ledger.Append(rec);
            var line = File.ReadAllText(path, Encoding.UTF8).TrimEnd('\n', '\r');
            return line;
        }

        // ─── Fixture: Veo lite T2V 720p 8s AllowAll, Queued ───────────

        // Hand-authored expected line. Format matches V1b's
        // JsonlVideoJobLedger.SerializeRecord field order:
        //   schema_version, job_id, provider, model, provider_job_id,
        //   provider_result_token, state, normalized_request,
        //   provider_options, pricing, result_artifact_id, error,
        //   created_at, updated_at
        private const string ExpectedVeoLiteT2v720p8sQueued =
            "{\"schema_version\":1,"
            + "\"job_id\":\"11111111-1111-1111-1111-111111111111\","
            + "\"provider\":\"veo\","
            + "\"model\":\"veo-3.1-lite-generate-preview\","
            + "\"provider_job_id\":null,"
            + "\"provider_result_token\":null,"
            + "\"state\":\"Queued\","
            + "\"normalized_request\":{"
                + "\"mode\":\"T2V\","
                + "\"duration_seconds\":8,"
                + "\"resolution\":\"720p\","
                + "\"aspect_ratio\":\"16:9\","
                + "\"prompt\":\"a clip\","
                + "\"start_frame\":null,"
                + "\"end_frame\":null,"
                + "\"reference_frames\":null,"
                + "\"seed\":null,"
                + "\"number_of_videos\":1"
            + "},"
            + "\"provider_options\":{\"person_generation\":\"allow_all\"},"
            + "\"pricing\":{"
                + "\"kind\":\"per_second\","
                + "\"currency\":\"USD\","
                + "\"quantity\":8,"
                + "\"unit_price_usd\":0.05,"
                + "\"total_usd\":0.40,"
                + "\"pricing_source\":\"veo-rate-card-v1\""
            + "},"
            + "\"result_artifact_id\":null,"
            + "\"error\":null,"
            + "\"created_at\":\"2026-04-25T12:00:00.0000000\\u002B00:00\","
            + "\"updated_at\":\"2026-04-25T12:00:00.0000000\\u002B00:00\"}";

        [Fact]
        public void V1c_factory_emits_byte_identical_jsonl_for_lite_t2v_720p_8s_AllowAll()
        {
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var rec = VideoJobRecordFactory.From(
                PinnedJobId, req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            var line = AppendAndReadLine(rec);

            Assert.Equal(ExpectedVeoLiteT2v720p8sQueued, line);
        }

        // ─── Fixture: Veo 3.1 full I2V 1080p 8s AllowAdult, Polling ──

        private const string ExpectedVeoFullI2v1080p8sAllowAdultPolling =
            "{\"schema_version\":1,"
            + "\"job_id\":\"22222222-2222-2222-2222-222222222222\","
            + "\"provider\":\"veo\","
            + "\"model\":\"veo-3.1-generate-preview\","
            + "\"provider_job_id\":\"operations/abc-123\","
            + "\"provider_result_token\":null,"
            + "\"state\":\"Polling\","
            + "\"normalized_request\":{"
                + "\"mode\":\"I2V\","
                + "\"duration_seconds\":8,"
                + "\"resolution\":\"1080p\","
                + "\"aspect_ratio\":\"16:9\","
                + "\"prompt\":null,"
                + "\"start_frame\":{"
                    + "\"kind\":\"Artifact\","
                    + "\"artifact_id\":\"33333333-3333-3333-3333-333333333333\","
                    + "\"path\":null,"
                    + "\"role\":\"image\""
                + "},"
                + "\"end_frame\":null,"
                + "\"reference_frames\":null,"
                + "\"seed\":null,"
                + "\"number_of_videos\":1"
            + "},"
            + "\"provider_options\":{\"person_generation\":\"allow_adult\"},"
            + "\"pricing\":{"
                + "\"kind\":\"per_second\","
                + "\"currency\":\"USD\","
                + "\"quantity\":8,"
                + "\"unit_price_usd\":0.40,"
                + "\"total_usd\":3.20,"
                + "\"pricing_source\":\"veo-rate-card-v1\""
            + "},"
            + "\"result_artifact_id\":null,"
            + "\"error\":null,"
            + "\"created_at\":\"2026-04-25T12:00:00.0000000\\u002B00:00\","
            + "\"updated_at\":\"2026-04-25T12:00:30.0000000\\u002B00:00\"}";

        [Fact]
        public void V1c_factory_emits_byte_identical_jsonl_for_full_i2v_1080p_8s_AllowAdult_polling()
        {
            var artId = new Guid("33333333-3333-3333-3333-333333333333");
            var startFrame = MediaRef.ForArtifact(artId, VideoMediaRoles.Image);
            var model = TestVideoFixtures.VeoLiteResolved(modelId: "veo-3.1-generate-preview");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.I2V,
                resolution: "1080p",
                duration: 8,
                prompt: null,
                startFrame: startFrame,
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var initial = VideoJobRecordFactory.From(
                new Guid("22222222-2222-2222-2222-222222222222"),
                req, model, EstimateFor(model, req),
                VideoJobState.Submitting, T0);

            var polling = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Polling, T0.AddSeconds(30),
                providerJobId: "operations/abc-123");

            var line = AppendAndReadLine(polling);

            Assert.Equal(ExpectedVeoFullI2v1080p8sAllowAdultPolling, line);
        }

        // ─── Fixture: Error state with full error block ───────────────

        private const string ExpectedVeoLiteT2vErrorWithFullErrorBlock =
            "{\"schema_version\":1,"
            + "\"job_id\":\"44444444-4444-4444-4444-444444444444\","
            + "\"provider\":\"veo\","
            + "\"model\":\"veo-3.1-lite-generate-preview\","
            + "\"provider_job_id\":\"operations/err-1\","
            + "\"provider_result_token\":null,"
            + "\"state\":\"Error\","
            + "\"normalized_request\":{"
                + "\"mode\":\"T2V\","
                + "\"duration_seconds\":8,"
                + "\"resolution\":\"720p\","
                + "\"aspect_ratio\":\"16:9\","
                + "\"prompt\":\"a clip\","
                + "\"start_frame\":null,"
                + "\"end_frame\":null,"
                + "\"reference_frames\":null,"
                + "\"seed\":null,"
                + "\"number_of_videos\":1"
            + "},"
            + "\"provider_options\":{\"person_generation\":\"allow_all\"},"
            + "\"pricing\":{"
                + "\"kind\":\"per_second\","
                + "\"currency\":\"USD\","
                + "\"quantity\":8,"
                + "\"unit_price_usd\":0.05,"
                + "\"total_usd\":0.40,"
                + "\"pricing_source\":\"veo-rate-card-v1\""
            + "},"
            + "\"result_artifact_id\":null,"
            + "\"error\":{"
                + "\"code\":\"ExecutionFailed\","
                + "\"message\":\"Veo API returned 500\","
                + "\"retryable\":true,"
                + "\"provider_message\":\"upstream rate-limited\","
                + "\"field\":null"
            + "},"
            + "\"created_at\":\"2026-04-25T12:00:00.0000000\\u002B00:00\","
            + "\"updated_at\":\"2026-04-25T12:00:30.0000000\\u002B00:00\"}";

        [Fact]
        public void V1c_factory_emits_byte_identical_jsonl_for_error_state_with_full_error_block()
        {
            var jobId = new Guid("44444444-4444-4444-4444-444444444444");
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var initial = VideoJobRecordFactory.From(
                jobId, req, model, EstimateFor(model, req),
                VideoJobState.Submitting, T0);

            var errored = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Error, T0.AddSeconds(30),
                providerJobId: "operations/err-1",
                error: new VideoJobError(
                    Code: VideoErrorCode.ExecutionFailed,
                    Message: "Veo API returned 500",
                    Retryable: true,
                    ProviderMessage: "upstream rate-limited",
                    Field: null));

            var line = AppendAndReadLine(errored);

            Assert.Equal(ExpectedVeoLiteT2vErrorWithFullErrorBlock, line);
        }

        // ─── Fixture: Complete state with result_artifact_id ──────────

        private const string ExpectedVeoLiteT2vCompleteWithArtifactId =
            "{\"schema_version\":1,"
            + "\"job_id\":\"55555555-5555-5555-5555-555555555555\","
            + "\"provider\":\"veo\","
            + "\"model\":\"veo-3.1-lite-generate-preview\","
            + "\"provider_job_id\":\"operations/ok-1\","
            + "\"provider_result_token\":\"https://veo/result/xyz\","
            + "\"state\":\"Complete\","
            + "\"normalized_request\":{"
                + "\"mode\":\"T2V\","
                + "\"duration_seconds\":8,"
                + "\"resolution\":\"720p\","
                + "\"aspect_ratio\":\"16:9\","
                + "\"prompt\":\"a clip\","
                + "\"start_frame\":null,"
                + "\"end_frame\":null,"
                + "\"reference_frames\":null,"
                + "\"seed\":null,"
                + "\"number_of_videos\":1"
            + "},"
            + "\"provider_options\":{\"person_generation\":\"allow_all\"},"
            + "\"pricing\":{"
                + "\"kind\":\"per_second\","
                + "\"currency\":\"USD\","
                + "\"quantity\":8,"
                + "\"unit_price_usd\":0.05,"
                + "\"total_usd\":0.40,"
                + "\"pricing_source\":\"veo-rate-card-v1\""
            + "},"
            + "\"result_artifact_id\":\"66666666-6666-6666-6666-666666666666\","
            + "\"error\":null,"
            + "\"created_at\":\"2026-04-25T12:00:00.0000000\\u002B00:00\","
            + "\"updated_at\":\"2026-04-25T12:02:00.0000000\\u002B00:00\"}";

        [Fact]
        public void V1c_factory_emits_byte_identical_jsonl_for_complete_state_with_result_artifact_id()
        {
            var jobId = new Guid("55555555-5555-5555-5555-555555555555");
            var artifactId = new Guid("66666666-6666-6666-6666-666666666666");
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var initial = VideoJobRecordFactory.From(
                jobId, req, model, EstimateFor(model, req),
                VideoJobState.Submitting, T0);

            var polling = VideoJobRecordFactory.WithState(
                initial, VideoJobState.Polling, T0.AddSeconds(30),
                providerJobId: "operations/ok-1");

            var downloading = VideoJobRecordFactory.WithState(
                polling, VideoJobState.Downloading, T0.AddSeconds(60),
                providerResultToken: "https://veo/result/xyz");

            var complete = VideoJobRecordFactory.WithState(
                downloading, VideoJobState.Complete, T0.AddSeconds(120),
                resultArtifactId: artifactId);

            var line = AppendAndReadLine(complete);

            Assert.Equal(ExpectedVeoLiteT2vCompleteWithArtifactId, line);
        }

        // ─── Fixture: multi-element reference_frames ──────────────────

        private const string ExpectedVeoFullT2vWithTwoReferenceFrames =
            "{\"schema_version\":1,"
            + "\"job_id\":\"77777777-7777-7777-7777-777777777777\","
            + "\"provider\":\"veo\","
            + "\"model\":\"veo-3.1-generate-preview\","
            + "\"provider_job_id\":null,"
            + "\"provider_result_token\":null,"
            + "\"state\":\"Queued\","
            + "\"normalized_request\":{"
                + "\"mode\":\"T2V\","
                + "\"duration_seconds\":8,"
                + "\"resolution\":\"1080p\","
                + "\"aspect_ratio\":\"16:9\","
                + "\"prompt\":\"a clip\","
                + "\"start_frame\":null,"
                + "\"end_frame\":null,"
                + "\"reference_frames\":["
                    + "{\"kind\":\"Artifact\",\"artifact_id\":\"88888888-8888-8888-8888-888888888888\",\"path\":null,\"role\":\"reference\"},"
                    + "{\"kind\":\"Artifact\",\"artifact_id\":\"99999999-9999-9999-9999-999999999999\",\"path\":null,\"role\":\"reference\"}"
                + "],"
                + "\"seed\":null,"
                + "\"number_of_videos\":1"
            + "},"
            + "\"provider_options\":{\"person_generation\":\"allow_adult\"},"
            + "\"pricing\":{"
                + "\"kind\":\"per_second\","
                + "\"currency\":\"USD\","
                + "\"quantity\":8,"
                + "\"unit_price_usd\":0.40,"
                + "\"total_usd\":3.20,"
                + "\"pricing_source\":\"veo-rate-card-v1\""
            + "},"
            + "\"result_artifact_id\":null,"
            + "\"error\":null,"
            + "\"created_at\":\"2026-04-25T12:00:00.0000000\\u002B00:00\","
            + "\"updated_at\":\"2026-04-25T12:00:00.0000000\\u002B00:00\"}";

        [Fact]
        public void V1c_factory_emits_byte_identical_jsonl_for_t2v_with_two_reference_frames()
        {
            var jobId = new Guid("77777777-7777-7777-7777-777777777777");
            var ref1 = new Guid("88888888-8888-8888-8888-888888888888");
            var ref2 = new Guid("99999999-9999-9999-9999-999999999999");
            var refs = new[]
            {
                MediaRef.ForArtifact(ref1, "reference"),
                MediaRef.ForArtifact(ref2, "reference"),
            };
            var model = TestVideoFixtures.VeoLiteResolved(modelId: "veo-3.1-generate-preview");
            // Reference frames trigger the "image-based" rule even on T2V,
            // so PersonGeneration must be AllowAdult.
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                resolution: "1080p",
                referenceFrames: refs,
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var rec = VideoJobRecordFactory.From(
                jobId, req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            var line = AppendAndReadLine(rec);

            Assert.Equal(ExpectedVeoFullT2vWithTwoReferenceFrames, line);
        }

        // ─── Round-trip: V1c output reads back identically ────────────

        [Fact]
        public void V1c_output_round_trips_through_ledger_to_equivalent_record()
        {
            // Build a V1c record, write to ledger, read back: parsed
            // record matches the original on all observable fields.
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var original = VideoJobRecordFactory.From(
                PinnedJobId, req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            var path = NewLedgerPath();
            var ledger = new JsonlVideoJobLedger(path);
            ledger.Append(original);

            var read = ledger.ReadAll();
            var parsed = Assert.Single(read.Records);

            Assert.Equal(original.JobId, parsed.JobId);
            Assert.Equal(original.Provider, parsed.Provider);
            Assert.Equal(original.Model, parsed.Model);
            Assert.Equal(original.State, parsed.State);
            Assert.Equal(original.Pricing.Kind, parsed.Pricing.Kind);
            Assert.Equal(original.Pricing.TotalUsd, parsed.Pricing.TotalUsd);
            Assert.Equal(original.Pricing.PricingSource, parsed.Pricing.PricingSource);
            Assert.Equal(
                original.ProviderOptions["person_generation"]!.GetValue<string>(),
                parsed.ProviderOptions["person_generation"]!.GetValue<string>());
            Assert.Equal(original.CreatedAt, parsed.CreatedAt);
            Assert.Equal(original.UpdatedAt, parsed.UpdatedAt);
        }

        // ─── Round-trip via codec.Deserialize (replay path) ───────────

        [Fact]
        public void V1c_provider_options_round_trip_through_codec_to_typed_VeoOptions()
        {
            // Replay path: read durable ProviderOptions JSON, deserialize
            // via codec, get typed VeoOptions back.
            var model = TestVideoFixtures.VeoLiteResolved();
            var req = TestVideoFixtures.DefaultT2vRequest(
                personGeneration: PersonGenerationPolicy.AllowAll);
            var rec = VideoJobRecordFactory.From(
                PinnedJobId, req, model, EstimateFor(model, req),
                VideoJobState.Queued, T0);

            var path = NewLedgerPath();
            new JsonlVideoJobLedger(path).Append(rec);

            var read = new JsonlVideoJobLedger(path).ReadAll();
            var parsed = Assert.Single(read.Records);
            var decoded = new VeoOptionsCodec().Deserialize(parsed.ProviderOptions);

            Assert.True(decoded.Success);
            var veo = Assert.IsType<VeoOptions>(decoded.Options);
            Assert.Equal(PersonGenerationPolicy.AllowAll, veo.PersonGeneration);
        }
    }
}
