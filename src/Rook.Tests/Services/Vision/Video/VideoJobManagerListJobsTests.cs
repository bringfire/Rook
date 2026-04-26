using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// PR-V3 tests for <see cref="VideoJobManager.ListJobsAsync"/> and the
    /// extracted <see cref="VideoJobManager.MergeByFreshness"/> helper.
    /// The merge rule is the load-bearing correctness piece — Codex flagged
    /// in v2 sign-off that a stale running snapshot must not regress a
    /// just-written terminal ledger record.
    /// </summary>
    public class VideoJobManagerListJobsTests : IDisposable
    {
        private readonly string _artifactRoot;
        private readonly ArtifactStore _artifactStore;
        private readonly FakeVideoJobLedger _ledger = new();
        private readonly FakeVideoJobClock _clock = new();
        private readonly FakeVideoJobIdGenerator _idGen = new();
        private readonly FakeVideoProvider _provider = new();
        private readonly FakeVideoMediaResolver _resolver = new();
        private readonly IVideoProviderRegistry _registry;
        private readonly VideoCostEstimator _estimator = new();
        private readonly ResolvedVideoModel _resolvedModel;

        public VideoJobManagerListJobsTests()
        {
            _artifactRoot = Path.Combine(
                Path.GetTempPath(),
                $"rook-listjobs-test-{Guid.NewGuid():N}");
            _artifactStore = new ArtifactStore(_artifactRoot);
            _registry = TestVideoFixtures.RegistryWithVeo(_provider);
            _resolvedModel = TestVideoFixtures.VeoLiteResolved(_provider);
        }

        public void Dispose()
        {
            if (Directory.Exists(_artifactRoot))
                try { Directory.Delete(_artifactRoot, recursive: true); }
                catch { /* best-effort */ }
        }

        private VideoJobManager Manager() =>
            new(
                registry: _registry,
                mediaResolver: _resolver,
                ledger: _ledger,
                estimator: _estimator,
                artifactStore: _artifactStore,
                clock: _clock,
                idGenerator: _idGen,
                pollInterval: TimeSpan.FromMilliseconds(5));

        // ─── ListJobsAsync end-to-end ────────────────────────────────────

        [Fact]
        public async Task ListJobsAsync_EmptyLedger_ReturnsEmpty()
        {
            var mgr = Manager();
            var result = await mgr.ListJobsAsync(50, CancellationToken.None);

            Assert.Empty(result.Jobs);
            Assert.Empty(result.Warnings);
            Assert.Equal(50, result.AppliedLimit);
        }

        [Fact]
        public async Task ListJobsAsync_NonPositiveLimit_Throws()
        {
            var mgr = Manager();
            await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
                () => mgr.ListJobsAsync(0, CancellationToken.None));
            await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
                () => mgr.ListJobsAsync(-5, CancellationToken.None));
        }

        [Fact]
        public async Task ListJobsAsync_LimitClampedToMax_ExposedViaAppliedLimit()
        {
            var mgr = Manager();
            var result = await mgr.ListJobsAsync(500, CancellationToken.None);

            Assert.Equal(VideoJobManager.MaxListLimit, result.AppliedLimit);
        }

        [Fact]
        public async Task ListJobsAsync_LimitInRange_PassesThrough()
        {
            var mgr = Manager();
            var result = await mgr.ListJobsAsync(7, CancellationToken.None);
            Assert.Equal(7, result.AppliedLimit);
        }

        [Fact]
        public async Task ListJobsAsync_SortsNewestFirst_TieBreakOnJobIdDescending()
        {
            // Three records: A (oldest), B and C (same updated_at, B's
            // GUID < C's GUID), D (newest). Expected order: D, C, B, A.
            var t0 = new DateTimeOffset(2026, 4, 25, 8, 0, 0, TimeSpan.Zero);
            var idA = Guid.Parse("aaaa1111-0000-0000-0000-000000000000");
            var idB = Guid.Parse("bbbb2222-0000-0000-0000-000000000000");
            var idC = Guid.Parse("cccc3333-0000-0000-0000-000000000000");
            var idD = Guid.Parse("dddd4444-0000-0000-0000-000000000000");

            _ledger.Append(BuildRecord(idA, VideoJobState.Complete, t0));
            _ledger.Append(BuildRecord(idB, VideoJobState.Polling, t0.AddMinutes(5)));
            _ledger.Append(BuildRecord(idC, VideoJobState.Polling, t0.AddMinutes(5))); // tie
            _ledger.Append(BuildRecord(idD, VideoJobState.Queued, t0.AddMinutes(10)));

            var mgr = Manager();
            var result = await mgr.ListJobsAsync(50, CancellationToken.None);

            var order = result.Jobs.Select(j => j.JobId).ToArray();
            Assert.Equal(new[] { idD, idC, idB, idA }, order);
        }

        [Fact]
        public async Task ListJobsAsync_LimitTrimsAfterSort_KeepsNewest()
        {
            var t0 = new DateTimeOffset(2026, 4, 25, 8, 0, 0, TimeSpan.Zero);
            var ids = Enumerable.Range(1, 5)
                .Select(i => Guid.Parse($"00000000-0000-0000-0000-{i:D12}"))
                .ToArray();
            for (int i = 0; i < 5; i++)
                _ledger.Append(BuildRecord(ids[i], VideoJobState.Complete, t0.AddMinutes(i)));

            var mgr = Manager();
            var result = await mgr.ListJobsAsync(2, CancellationToken.None);

            // limit=2 → newest two (highest i first).
            Assert.Equal(2, result.Jobs.Count);
            Assert.Equal(ids[4], result.Jobs[0].JobId);
            Assert.Equal(ids[3], result.Jobs[1].JobId);
        }

        [Fact]
        public async Task ListJobsAsync_Summary_ModelComesFromRecordTopLevel()
        {
            // User-flagged sign-off note: JobRequestSummary.Model MUST be
            // sourced from VideoJobRecord.Model, not NormalizedRequest
            // (which by contract does not carry the model id). Pin: a
            // record whose top-level Model differs from the resolver's
            // assumed default still surfaces correctly.
            var jobId = Guid.NewGuid();
            var t0 = new DateTimeOffset(2026, 4, 25, 8, 0, 0, TimeSpan.Zero);
            var record = BuildRecord(jobId, VideoJobState.Queued, t0)
                with { Model = "veo-3.0-fast-generate-001" };
            _ledger.Append(record);

            var mgr = Manager();
            var result = await mgr.ListJobsAsync(50, CancellationToken.None);

            var entry = Assert.Single(result.Jobs);
            Assert.Equal("veo-3.0-fast-generate-001", entry.Summary.Model);
        }

        [Fact]
        public async Task ListJobsAsync_UpdatedAt_IsDateTimeOffset_PreservesOffset()
        {
            // Pin the explicit-offset invariant. DateTimeOffset round-trip
            // through the projection must not collapse to UTC or drop
            // the offset.
            var jobId = Guid.NewGuid();
            var withOffset = new DateTimeOffset(2026, 4, 25, 12, 0, 0, TimeSpan.FromHours(-7));
            _ledger.Append(BuildRecord(jobId, VideoJobState.Polling, withOffset));

            var mgr = Manager();
            var result = await mgr.ListJobsAsync(50, CancellationToken.None);

            var entry = Assert.Single(result.Jobs);
            Assert.Equal(withOffset, entry.UpdatedAt);
            Assert.Equal(TimeSpan.FromHours(-7), entry.UpdatedAt.Offset);
        }

        // ─── MergeByFreshness (the load-bearing rule) ────────────────────

        [Fact]
        public void MergeByFreshness_OnlyLedger_LedgerWins()
        {
            var id = Guid.NewGuid();
            var t0 = DateTimeOffset.UtcNow;
            var ledger = BuildRecord(id, VideoJobState.Polling, t0);

            var merged = VideoJobManager.MergeByFreshness(
                new[] { ledger },
                Array.Empty<VideoJobRecord>());

            Assert.Single(merged);
            Assert.Same(ledger, merged[id]);
        }

        [Fact]
        public void MergeByFreshness_OnlyRunning_RunningWins()
        {
            // Defensive case — current submit path appends ledger BEFORE
            // adding to _runningJobs, so this should not happen. The
            // merge tolerates it rather than dropping the record.
            var id = Guid.NewGuid();
            var live = BuildRecord(id, VideoJobState.Submitting, DateTimeOffset.UtcNow);

            var merged = VideoJobManager.MergeByFreshness(
                Array.Empty<VideoJobRecord>(),
                new[] { live });

            Assert.Single(merged);
            Assert.Same(live, merged[id]);
        }

        [Fact]
        public void MergeByFreshness_LedgerNewer_LedgerWins()
        {
            var id = Guid.NewGuid();
            var t0 = DateTimeOffset.UtcNow;
            var live = BuildRecord(id, VideoJobState.Submitting, t0);
            var ledger = BuildRecord(id, VideoJobState.Polling, t0.AddSeconds(1));

            var merged = VideoJobManager.MergeByFreshness(
                new[] { ledger }, new[] { live });

            Assert.Same(ledger, merged[id]);
        }

        [Fact]
        public void MergeByFreshness_RunningNewer_RunningWins()
        {
            // Defensive: future ordering change.
            var id = Guid.NewGuid();
            var t0 = DateTimeOffset.UtcNow;
            var ledger = BuildRecord(id, VideoJobState.Submitting, t0);
            var live = BuildRecord(id, VideoJobState.Polling, t0.AddSeconds(1));

            var merged = VideoJobManager.MergeByFreshness(
                new[] { ledger }, new[] { live });

            Assert.Same(live, merged[id]);
        }

        [Fact]
        public void MergeByFreshness_Tied_TerminalLedger_NotRegressedByStaleRunning()
        {
            // THE critical Codex sign-off correction: a terminal record
            // already in the ledger must not be regressed to an earlier
            // in-flight running snapshot. With the rule "newer wins; tie
            // breaks to terminal", a tie with running=non-terminal and
            // ledger=terminal lets ledger keep its terminal state.
            var id = Guid.NewGuid();
            var t0 = DateTimeOffset.UtcNow;
            var ledgerComplete = BuildRecord(id, VideoJobState.Complete, t0);
            var stalePolling = BuildRecord(id, VideoJobState.Polling, t0); // tie

            var merged = VideoJobManager.MergeByFreshness(
                new[] { ledgerComplete }, new[] { stalePolling });

            Assert.Equal(VideoJobState.Complete, merged[id].State);
            Assert.Same(ledgerComplete, merged[id]);
        }

        [Fact]
        public void MergeByFreshness_Tied_TerminalRunning_BeatsNonTerminalLedger()
        {
            // Symmetric mid-write race: terminal running snapshot at the
            // same instant as the prior non-terminal ledger snapshot —
            // running wins so the queue panel reflects the just-completed
            // state without waiting for a re-read.
            var id = Guid.NewGuid();
            var t0 = DateTimeOffset.UtcNow;
            var inflightLedger = BuildRecord(id, VideoJobState.Polling, t0);
            var liveTerminal = BuildRecord(id, VideoJobState.Complete, t0); // tie

            var merged = VideoJobManager.MergeByFreshness(
                new[] { inflightLedger }, new[] { liveTerminal });

            Assert.Equal(VideoJobState.Complete, merged[id].State);
            Assert.Same(liveTerminal, merged[id]);
        }

        [Fact]
        public void MergeByFreshness_TiedBothNonTerminal_RunningWins()
        {
            // Codex v3-implementation review: tie + ledger non-terminal
            // → running wins, regardless of running's state. This is the
            // stricter rule that protects against a future code-ordering
            // inversion in RunJobAsync where LatestRecord could be
            // assigned BEFORE ledger.Append. Today both branches share
            // the same record reference at any tied instant, so
            // observable behavior doesn't change in the happy path; the
            // protection only kicks in if ordering ever flips.
            var id = Guid.NewGuid();
            var t0 = DateTimeOffset.UtcNow;
            var ledger = BuildRecord(id, VideoJobState.Polling, t0);
            var running = BuildRecord(id, VideoJobState.Polling, t0);

            var merged = VideoJobManager.MergeByFreshness(
                new[] { ledger }, new[] { running });

            Assert.Same(running, merged[id]);
        }

        // ─── End-to-end warning sanitization ─────────────────────────────

        [Fact]
        public async Task ListJobsAsync_LedgerHasUnknownPricingKind_WarningOmitsOffendingValue()
        {
            // Codex review of v3 implementation: LedgerReadError.Message
            // can interpolate user-supplied content
            // (e.g. "Unknown pricing.kind: '{kindStr}'."). The manager
            // must redact the message before surfacing it through
            // ListJobsAsync, OR a malicious / corrupted ledger line
            // would leak prompt text or provider-options content
            // through the unauthenticated read path.
            //
            // This test writes a real JSONL file with a known sensitive
            // string in `pricing.kind`, then asserts the warning surface
            // contains the line number + reason but NOT the sensitive
            // value.
            var sensitive = "SECRET_OFFENDING_PROMPT_VALUE_xyz";

            // Use a real JsonlVideoJobLedger over a temp file. One valid
            // record, one malformed line.
            var tempPath = Path.Combine(
                Path.GetTempPath(),
                $"rook-listjobs-warn-{Guid.NewGuid():N}.jsonl");
            try
            {
                var realLedger = new JsonlVideoJobLedger(tempPath);
                var goodId = Guid.NewGuid();
                // Polling — non-terminal, so no result_artifact_id
                // requirement. The schema lets a polling record round-
                // trip cleanly through write+read.
                realLedger.Append(VideoJobRecordFactory.From(
                    goodId,
                    TestVideoFixtures.DefaultT2vRequest(),
                    _resolvedModel,
                    _estimator.Estimate(_resolvedModel, TestVideoFixtures.DefaultT2vRequest()).Estimate!,
                    initialState: VideoJobState.Polling,
                    now: new DateTimeOffset(2026, 4, 25, 12, 0, 0, TimeSpan.Zero)));

                // Append a second line that mirrors the on-disk schema
                // but fails at pricing.kind — the JsonNode mutation
                // approach preserves the producer's exact field set so
                // we don't drift away from schema additions in V1c.
                var goodLine = File.ReadAllLines(tempPath)
                    .Single(l => l.Length > 0);
                var node = JsonNode.Parse(goodLine)!.AsObject();
                node["job_id"] = Guid.NewGuid().ToString("D");
                node["pricing"]!.AsObject()["kind"] = sensitive;
                // JsonlVideoJobLedger reads file with File.ReadAllLines,
                // which splits on any line ending, so writing with "\n"
                // alone is fine. Append to the existing file content.
                using (var sw = new StreamWriter(tempPath, append: true))
                {
                    sw.Write(node.ToJsonString());
                    sw.Write("\n");
                }

                var mgr = new VideoJobManager(
                    registry: _registry,
                    mediaResolver: _resolver,
                    ledger: realLedger,
                    estimator: _estimator,
                    artifactStore: _artifactStore,
                    clock: _clock,
                    idGenerator: _idGen,
                    pollInterval: TimeSpan.FromMilliseconds(5));

                var result = await mgr.ListJobsAsync(50, CancellationToken.None);

                // Valid record still surfaces (a single bad line does
                // not block the rest of the ledger).
                Assert.Contains(result.Jobs, j => j.JobId == goodId);

                // Warning surfaces, but with NO sensitive content.
                var warning = Assert.Single(result.Warnings);
                Assert.Equal(LedgerReadErrorReason.UnknownPricingKind, warning.Reason);
                Assert.DoesNotContain(sensitive, warning.Message);
                if (warning.FieldPath is not null)
                    Assert.DoesNotContain(sensitive, warning.FieldPath);
            }
            finally
            {
                if (File.Exists(tempPath)) File.Delete(tempPath);
            }
        }

        // ─── Helpers ─────────────────────────────────────────────────────

        private VideoJobRecord BuildRecord(
            Guid jobId,
            VideoJobState state,
            DateTimeOffset updatedAt)
        {
            // Build a real record using the production factory + estimator
            // so the bit-identity and serialization invariants stay valid.
            var request = TestVideoFixtures.DefaultT2vRequest();
            var estimate = _estimator.Estimate(_resolvedModel, request).Estimate!;
            var record = VideoJobRecordFactory.From(
                jobId, request, _resolvedModel, estimate,
                initialState: state, now: updatedAt);
            // VideoJobRecordFactory.From sets CreatedAt = UpdatedAt = now;
            // freshness tests only care about UpdatedAt so that's already
            // correct. Return as-is.
            return record;
        }
    }
}
