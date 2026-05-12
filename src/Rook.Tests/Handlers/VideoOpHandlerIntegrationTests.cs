using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision.Video;
using Rook.Tests.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Handlers
{
    /// <summary>
    /// Step 8 — cross-handler integration smoke. Wires the production
    /// <see cref="VideoOpHandler"/> against a production
    /// <see cref="VideoJobManager"/>, real registry + estimator,
    /// <see cref="FakeVideoProvider"/>, <see cref="FakeVideoJobLedger"/>,
    /// and a real <see cref="ArtifactStore"/> on a temp root. Verifies
    /// the handler's JSON wire format flows correctly all the way
    /// through to the manager and back. Catches:
    /// <list type="bullet">
    ///   <item>JSON shape mismatches between handler and manager.</item>
    ///   <item>Ledger record schema regressions (the V1c bit-identity
    ///         fixtures pin the format byte-for-byte; this catches
    ///         drift that would corrupt the schema before the bytes).</item>
    ///   <item>Provider boundary correctness — the manager's translation
    ///         from <c>VideoGenerationRequest</c> + resolved media to
    ///         <c>ProviderSubmitOutcome</c> works end-to-end with a real
    ///         provider implementation (fake but the same contract).</item>
    /// </list>
    ///
    /// Production-state isolation: every test uses a fresh
    /// <see cref="FakeVideoJobLedger"/> (in-memory) and a fresh
    /// temp-rooted <see cref="ArtifactStore"/>. The default
    /// <c>%APPDATA%\Rook\video\job-ledger.jsonl</c> is NEVER touched.
    ///
    /// Native path note: the trampoline's C++
    /// <c>DispatchVisionOpWithPathId</c> injects <c>body["job_id"]</c>
    /// from the matched URL segment. These tests start from "the
    /// trampoline did its job correctly" and exercise downstream
    /// behavior; <see cref="NativeVisionDispatchSourceTests"/> pins the
    /// native source wiring for artifact-id versus job-id path routes.
    /// </summary>
    public class VideoOpHandlerIntegrationTests : IDisposable
    {
        private readonly string _artifactsRoot;
        private readonly ArtifactStore _store;
        private readonly FakeVideoJobLedger _ledger;
        private readonly FakeVideoProvider _provider;
        private readonly VideoJobManager _manager;
        private readonly VideoOpHandler _handler;

        public VideoOpHandlerIntegrationTests()
        {
            _artifactsRoot = Path.Combine(
                Path.GetTempPath(),
                $"rook-vid-int-{Guid.NewGuid():N}");
            Directory.CreateDirectory(_artifactsRoot);
            _store = new ArtifactStore(_artifactsRoot);

            _ledger = new FakeVideoJobLedger();
            _provider = new FakeVideoProvider();

            // Real registry + estimator. The fake provider is wired in
            // via VeoProviderRegistration so the registry resolves real
            // Veo model ids to the fake's behaviour.
            var registry = new DefaultVideoProviderRegistry(new[]
            {
                new VeoProviderRegistration(_provider),
            });
            var estimator = new VideoCostEstimator();
            var resolver = new ArtifactOnlyVideoMediaResolver(_store);

            _manager = new VideoJobManager(
                registry: registry,
                mediaResolver: resolver,
                ledger: _ledger,
                estimator: estimator,
                artifactStore: _store,
                clock: null,
                idGenerator: null,
                pollInterval: TimeSpan.FromMilliseconds(20),
                maxConcurrentJobs: VideoJobManager.DefaultMaxConcurrentJobs,
                materializer: null,
                posterProducer: new FakePosterProducer(_store),
                frameProducer: new FakeFrameProducer(_store));

            _handler = new VideoOpHandler(_manager, registry, estimator);
        }

        public void Dispose()
        {
            try { _manager.Dispose(); } catch { /* idempotent test cleanup */ }
            try { Directory.Delete(_artifactsRoot, recursive: true); }
            catch { /* test cleanup, ignore */ }
        }

        // ─── Submit → Status → Cancel cycle ──────────────────────────────

        [Fact]
        public async Task Submit_T2V_PersistsQueuedRecord_AndReturnsJobIdGuid()
        {
            // The handler should land a Queued record in the ledger
            // synchronously and return a parseable GUID job_id. The
            // background task may or may not have started; we don't
            // race on it here — just verify the synchronous contract.
            var resp = await _handler.DispatchAsync(BuildT2vBody());

            Assert.True(resp.Success, FormatFailure(resp));
            Assert.Equal(200, resp.HttpStatus);
            var data = AssertDataDict(resp);
            Assert.NotNull(data["job_id"]);
            var jobIdString = (string)data["job_id"]!;
            Assert.True(Guid.TryParseExact(jobIdString, "D", out var jobId));
            Assert.NotEqual(Guid.Empty, jobId);

            // Ledger has at least one record for this job, and the
            // first record is Queued (per VideoJobManager.SubmitAsync).
            var records = _ledger.AllRecords.Where(r => r.JobId == jobId).ToArray();
            Assert.NotEmpty(records);
            Assert.Equal(VideoJobState.Queued, records[0].State);
        }

        [Fact]
        public async Task Submit_Then_Status_ReadsLedger_AgainstSameJobId()
        {
            var submitResp = await _handler.DispatchAsync(BuildT2vBody());
            var submitData = AssertDataDict(submitResp);
            var jobId = (string)submitData["job_id"]!;

            // Status read should succeed and report a coherent state.
            // The exact in-flight state (Queued / Submitting / Polling)
            // depends on timing of the BG task; we don't pin it.
            var statusResp = _handler.DispatchOffUi($$"""
                {"op":"get_video_job","job_id":"{{jobId}}"}
                """);

            Assert.True(statusResp.Success, FormatFailure(statusResp));
            Assert.Equal(200, statusResp.HttpStatus);
            var statusData = AssertDataDict(statusResp);
            Assert.Equal(jobId, statusData["job_id"]);
            Assert.NotNull(statusData["state"]);
        }

        [Fact]
        public async Task Status_UnknownJobId_ReturnsInvalidRequest400()
        {
            var resp = _handler.DispatchOffUi("""
                {"op":"get_video_job","job_id":"99999999-9999-9999-9999-999999999999"}
                """);

            Assert.False(resp.Success);
            Assert.Equal(400, resp.HttpStatus);
            await Task.CompletedTask;
        }

        [Fact]
        public async Task Submit_Then_Cancel_TransitionsToCancelled()
        {
            // Provider.Cancel returns Cancelled by default. The manager
            // should transition the job to Cancelled in the ledger.
            var submitResp = await _handler.DispatchAsync(BuildT2vBody());
            var jobId = (string)AssertDataDict(submitResp)["job_id"]!;

            // Wait for the BG task to register a provider_job_id so
            // CancelAsync hits the in-flight branch (provider cancel
            // call). The fake provider's default GetStatus returns
            // Polling, so the BG task progresses through Submitting →
            // Polling and stalls there.
            await WaitForLedgerStateAsync(Guid.Parse(jobId), VideoJobState.Polling);

            var cancelResp = await _handler.DispatchAsync($$"""
                {"op":"cancel_video_job","job_id":"{{jobId}}"}
                """);

            Assert.True(cancelResp.Success, FormatFailure(cancelResp));
            Assert.Equal(200, cancelResp.HttpStatus);
            var data = AssertDataDict(cancelResp);
            Assert.Equal("cancelled", data["state"]);

            // Active cancel uses the model-aware provider lifecycle and
            // passes the provider_job_id the fake assigned at submit
            // ("fake-job-1" by default).
            var cancelCall = Assert.Single(_provider.RecordedCalls,
                c => c.Method == "CancelForModel");
            var payload = Assert.IsType<FakeVideoProvider.ModelAwareCall>(
                cancelCall.Payload);
            Assert.Equal(TestVideoFixtures.DefaultModelId, payload.ModelId);
            Assert.Equal("fake-job-1", payload.ProviderJobId);
        }

        // ─── Estimate against real registry + estimator ──────────────────

        [Fact]
        public void Estimate_LiteModel_ReturnsRealPricing()
        {
            // Pure-CPU dictionary lookup + arithmetic; no provider call.
            // Pin the price-shape to match VeoCapabilities lite pricing
            // (720p × 8s × $0.05/s = $0.40).
            var resp = _handler.DispatchOffUi("""
                {
                  "op": "estimate_video_job",
                  "model": "veo-3.1-lite-generate-preview",
                  "mode": "t2v",
                  "duration_seconds": 8,
                  "resolution": "720p",
                  "aspect_ratio": "16:9",
                  "prompt": "x",
                  "options": { "person_generation": "allow_all" },
                  "number_of_videos": 1
                }
                """);

            Assert.True(resp.Success, FormatFailure(resp));
            var data = AssertDataDict(resp);
            Assert.Equal(0.40m, (decimal)data["dollars_usd"]!);
            var pricing = (Dictionary<string, object?>)data["pricing"]!;
            Assert.Equal("per_second", pricing["kind"]);
            Assert.Equal(8, pricing["quantity"]);
            Assert.Equal(0.05m, (decimal)pricing["unit_price_usd"]!);
        }

        // ─── Result fetch (full happy-path through manager) ──────────────

        [Fact]
        public async Task Submit_PollComplete_FetchResult_RoundTrips()
        {
            // Configure the fake provider to advance through Polling →
            // Complete with a videoUri token, then return non-empty
            // bytes on fetch. The manager creates a real ArtifactStore
            // entry and the handler returns the artifact id + files.
            var pollCount = 0;
            _provider.OnGetStatus = handle =>
            {
                pollCount++;
                // First poll: still polling. Second poll: complete with
                // a result token. Avoids racing the BG task.
                return pollCount < 2
                    ? FakeVideoProvider.StatusInFlight(50)
                    : FakeVideoProvider.StatusComplete(handle, "fake-video-uri");
            };
            _provider.OnFetchResult = _ =>
                FakeVideoProvider.ResultOk(
                    bytes: System.Text.Encoding.UTF8.GetBytes("fake-mp4-bytes"),
                    mimeType: "video/mp4");

            var submitResp = await _handler.DispatchAsync(BuildT2vBody());
            var jobId = Guid.Parse((string)AssertDataDict(submitResp)["job_id"]!);

            await WaitForLedgerStateAsync(jobId, VideoJobState.Complete,
                timeoutMs: 2000);

            var resultResp = _handler.DispatchOffUi($$"""
                {"op":"get_video_job_result","job_id":"{{jobId:D}}"}
                """);

            Assert.True(resultResp.Success, FormatFailure(resultResp));
            Assert.Equal(200, resultResp.HttpStatus);
            var data = AssertDataDict(resultResp);
            Assert.Equal("complete", data["state"]);
            Assert.NotNull(data["result_artifact_id"]);
            Assert.True(Guid.TryParseExact(
                (string)data["result_artifact_id"]!, "D", out var artId));

            // Real artifact landed in the store with the bytes the fake
            // provider returned.
            var artifact = _store.Get(artId);
            Assert.NotNull(artifact);
            Assert.Equal("generated_video", artifact!.Kind);
        }

        // ─── Helpers ─────────────────────────────────────────────────────

        private static string BuildT2vBody() => """
            {
              "op": "submit_video_job",
              "model": "veo-3.1-lite-generate-preview",
              "mode": "t2v",
              "duration_seconds": 8,
              "resolution": "720p",
              "aspect_ratio": "16:9",
              "prompt": "a clip",
              "options": { "person_generation": "allow_all" },
              "number_of_videos": 1
            }
            """;

        private async Task WaitForLedgerStateAsync(
            Guid jobId, VideoJobState target, int timeoutMs = 1000)
        {
            var deadline = DateTime.UtcNow.AddMilliseconds(timeoutMs);
            while (DateTime.UtcNow < deadline)
            {
                var record = _ledger.AllRecords
                    .Where(r => r.JobId == jobId)
                    .LastOrDefault();
                if (record is not null && record.State == target) return;
                await Task.Delay(10);
            }
            throw new TimeoutException(
                $"Ledger did not reach state {target} for job {jobId:D} within {timeoutMs}ms.");
        }

        private static Dictionary<string, object?> AssertDataDict(ApiResponse resp)
        {
            Assert.NotNull(resp.Data);
            var dict = resp.Data as Dictionary<string, object?>;
            Assert.NotNull(dict);
            return dict!;
        }

        private static string FormatFailure(ApiResponse resp) =>
            "expected success=true; data: " + JsonSerializer.Serialize(resp.Data);
    }
}
