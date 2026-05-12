using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Captures byte-identity goldens for the on-disk JSONL produced by
    /// <see cref="JsonlVideoJobLedger"/> across four representative
    /// state-transition sequences:
    /// <list type="bullet">
    ///   <item>#06 — Happy path: Queued → Submitting → Polling →
    ///         Downloading → Saving → Complete (6 lines)</item>
    ///   <item>#07 — Submit auth fail: Queued → Submitting → Error
    ///         (3 lines)</item>
    ///   <item>#08 — Mid-poll provider error: Queued → Submitting →
    ///         Polling → Error (4 lines)</item>
    ///   <item>#09 — Cancel mid-flight: Queued → Submitting → Polling
    ///         → Cancelled (4 lines, with the Cancelled error
    ///         persisted)</item>
    /// </list>
    ///
    /// <para>Compared as raw bytes (LF-normalized) — the on-disk shape
    /// is the durability contract that PR-2's ledger-mapping retrofit
    /// must preserve. Determinism comes from
    /// <see cref="FakeVideoJobClock"/> (fixed timestamps) +
    /// <see cref="FakeVideoJobIdGenerator"/> (pre-set jobId) + scripted
    /// <see cref="FakeVideoProvider"/> (fixed provider_job_id /
    /// provider_result_token / canned bytes). The single
    /// non-deterministic field — <c>result_artifact_id</c>, minted by
    /// <see cref="ArtifactStore"/> — is replaced with a stable
    /// placeholder via
    /// <see cref="VeoBehaviorParityFixture.ReplaceGuidField"/> before
    /// assertion.</para>
    /// </summary>
    public class VeoLedgerTransitionCaptureTests : IDisposable
    {
        private readonly string _testRoot;
        private readonly string _ledgerPath;
        private readonly string _artifactRoot;
        private readonly ArtifactStore _artifactStore;

        public VeoLedgerTransitionCaptureTests()
        {
            _testRoot = Path.Combine(
                Path.GetTempPath(),
                $"rook-pr2-capture-{Guid.NewGuid():N}");
            Directory.CreateDirectory(_testRoot);
            _ledgerPath = Path.Combine(_testRoot, "ledger.jsonl");
            _artifactRoot = Path.Combine(_testRoot, "artifacts");
            _artifactStore = new ArtifactStore(_artifactRoot);
        }

        public void Dispose()
        {
            if (Directory.Exists(_testRoot))
                Directory.Delete(_testRoot, recursive: true);
        }

        // ─── #06 — Happy path ─────────────────────────────────────────

        [Fact]
        public async Task Golden_06_ledger_happy_path()
        {
            var jobId = Guid.Parse("12345678-aaaa-bbbb-cccc-1234567890ab");
            var idGen = new FakeVideoJobIdGenerator();
            idGen.Sequence.Enqueue(jobId);

            var provider = new FakeVideoProvider
            {
                OnSubmit = (_, _) =>
                    FakeVideoProvider.SubmitQueued("operations/op-fake-123"),
                OnGetStatus = handle => FakeVideoProvider.StatusComplete(
                    handle,
                    "https://veo/result/fake-video.mp4"),
                OnFetchResult = _ => FakeVideoProvider.ResultOk(
                    FakeMp4Bytes(), "video/mp4"),
            };

            var mgr = BuildManager(provider, idGen);
            await mgr.SubmitAsync(
                TestVideoFixtures.DefaultT2vRequest(),
                CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId, VideoJobState.Complete);

            AssertLedgerGolden("06_ledger_happy_path.jsonl");
        }

        // ─── #07 — Submit auth fail ──────────────────────────────────

        [Fact]
        public async Task Golden_07_ledger_submit_auth_fail()
        {
            var jobId = Guid.Parse("22222222-aaaa-bbbb-cccc-222222222222");
            var idGen = new FakeVideoJobIdGenerator();
            idGen.Sequence.Enqueue(jobId);

            var provider = new FakeVideoProvider
            {
                OnSubmit = (_, _) => FakeVideoProvider.SubmitFailed(new VideoJobError(
                    Code: VideoErrorCode.DependencyUnavailable,
                    Message: "Veo submit rejected: authentication failed (401). " +
                             "{\"error\":\"unauthenticated\"}",
                    Retryable: false,
                    ProviderMessage: "{\"error\":\"unauthenticated\"}")),
            };

            var mgr = BuildManager(provider, idGen);
            await mgr.SubmitAsync(
                TestVideoFixtures.DefaultT2vRequest(),
                CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId, VideoJobState.Error);

            AssertLedgerGolden("07_ledger_submit_auth_fail.jsonl");
        }

        // ─── #08 — Mid-poll provider error ──────────────────────────

        [Fact]
        public async Task Golden_08_ledger_mid_poll_error()
        {
            var jobId = Guid.Parse("33333333-aaaa-bbbb-cccc-333333333333");
            var idGen = new FakeVideoJobIdGenerator();
            idGen.Sequence.Enqueue(jobId);

            var provider = new FakeVideoProvider
            {
                OnSubmit = (_, _) =>
                    FakeVideoProvider.SubmitQueued("operations/op-fake-456"),
                OnGetStatus = _ => FakeVideoProvider.StatusFailed(
                    new VideoJobError(
                        Code: VideoErrorCode.ExecutionFailed,
                        Message: "Veo poll backend error (503). " +
                                 "{\"error\":\"unavailable\"}",
                        Retryable: true,
                        ProviderMessage: "{\"error\":\"unavailable\"}")),
            };

            var mgr = BuildManager(provider, idGen);
            await mgr.SubmitAsync(
                TestVideoFixtures.DefaultT2vRequest(),
                CancellationToken.None);
            await WaitForTerminalAsync(mgr, jobId, VideoJobState.Error);

            AssertLedgerGolden("08_ledger_mid_poll_error.jsonl");
        }

        // ─── #09 — Cancel mid-flight ────────────────────────────────

        [Fact]
        public async Task Golden_09_ledger_cancel_midflight()
        {
            var jobId = Guid.Parse("44444444-aaaa-bbbb-cccc-444444444444");
            var idGen = new FakeVideoJobIdGenerator();
            idGen.Sequence.Enqueue(jobId);

            // Hold polling so the cancel request lands while the job is
            // mid-poll. An in-flight provider status is the manager's
            // cue to keep waiting; the test cancels through the manager
            // path which fires the per-job CTS, the polling Task.Delay
            // throws OperationCanceledException, and the manager's catch
            // arm appends the Cancelled record.
            var provider = new FakeVideoProvider
            {
                OnSubmit = (_, _) =>
                    FakeVideoProvider.SubmitQueued("operations/op-fake-789"),
                OnGetStatus = _ => FakeVideoProvider.StatusInFlight(),
                OnCancel = _ => FakeVideoProvider.CancelOk(),
            };

            var mgr = BuildManager(provider, idGen);
            await mgr.SubmitAsync(
                TestVideoFixtures.DefaultT2vRequest(),
                CancellationToken.None);

            await WaitForStateAsync(mgr, jobId, VideoJobState.Polling);

            var cancel = await mgr.CancelAsync(jobId, CancellationToken.None);
            Assert.Null(cancel.Error);
            await WaitForTerminalAsync(mgr, jobId, VideoJobState.Cancelled);

            AssertLedgerGolden("09_ledger_cancel_midflight.jsonl");
        }

        // ─── Helpers ──────────────────────────────────────────────────

        private VideoJobManager BuildManager(
            FakeVideoProvider provider, FakeVideoJobIdGenerator idGen)
        {
            var registry = TestVideoFixtures.RegistryWithVeo(provider);
            var mediaResolver = new ArtifactOnlyVideoMediaResolver(_artifactStore);
            var ledger = new JsonlVideoJobLedger(_ledgerPath);
            var estimator = new VideoCostEstimator();
            var clock = new FakeVideoJobClock
            {
                Now = new DateTimeOffset(2026, 4, 25, 0, 0, 0, TimeSpan.Zero),
            };

            return new VideoJobManager(
                registry: registry,
                mediaResolver: mediaResolver,
                ledger: ledger,
                estimator: estimator,
                artifactStore: _artifactStore,
                clock: clock,
                idGenerator: idGen,
                pollInterval: TimeSpan.FromMilliseconds(5),
                maxConcurrentJobs: VideoJobManager.DefaultMaxConcurrentJobs,
                materializer: null,
                posterProducer: new FakePosterProducer(_artifactStore),
                frameProducer: new FakeFrameProducer(_artifactStore));
        }

        private static async Task WaitForStateAsync(
            VideoJobManager mgr, Guid jobId, VideoJobState expected)
        {
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(5);
            while (DateTime.UtcNow < deadline)
            {
                var s = await mgr.GetStatusAsync(jobId, CancellationToken.None);
                if (s.State == expected)
                    return;

                await Task.Delay(5);
            }

            throw new TimeoutException(
                $"Job {jobId:D} did not reach state {expected}.");
        }

        private static async Task WaitForTerminalAsync(
            VideoJobManager mgr, Guid jobId, VideoJobState expected)
        {
            var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(5);
            while (DateTime.UtcNow < deadline)
            {
                var s = await mgr.GetStatusAsync(jobId, CancellationToken.None);
                if (IsTerminal(s.State))
                {
                    Assert.Equal(expected, s.State);
                    // Give the manager a beat to flush the final ledger
                    // append + remove from _runningJobs. WaitForTerminal
                    // can race the ledger-append-then-RunningJobs-remove
                    // ordering on the BG task; an extra small wait here
                    // ensures the captured file reflects the terminal
                    // line.
                    await Task.Delay(30);
                    return;
                }
                await Task.Delay(5);
            }
            throw new TimeoutException(
                $"Job {jobId:D} did not reach a terminal state.");
        }

        private static bool IsTerminal(VideoJobState s) =>
            s is VideoJobState.Complete
              or VideoJobState.Error
              or VideoJobState.Cancelled
              or VideoJobState.Interrupted;

        // 16 deterministic bytes serving as the "downloaded video."
        // ArtifactStore writes this verbatim; the resulting artifact id
        // is non-deterministic but the rest of the ledger record is.
        private static byte[] FakeMp4Bytes() => new byte[]
        {
            0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70,
            0x69, 0x73, 0x6F, 0x6D, 0x00, 0x00, 0x00, 0x00,
        };

        private void AssertLedgerGolden(string filename)
        {
            var raw = File.ReadAllText(_ledgerPath);
            // result_artifact_id is the only non-deterministic field
            // (ArtifactStore mints Guid.NewGuid()). Replace before
            // assertion with a stable placeholder; everything else in
            // the ledger record is deterministic under the fake clock,
            // fake id generator, and scripted fake provider.
            var stabilized = VeoBehaviorParityFixture.ReplaceGuidField(
                raw, "result_artifact_id", "<RESULT_ARTIFACT_ID>");
            VeoBehaviorParityFixture.AssertOrCaptureRawBytes(filename, stabilized);
        }
    }
}
