using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalConfiguredJobLifecycleTests
    {
        [Theory]
        [InlineData(false, false, "confirmed_cancelled")] [InlineData(true, false, "confirmed_cancelled")]
        [InlineData(false, false, "already_completed")] [InlineData(true, false, "already_completed")]
        [InlineData(false, false, "cancellation_requested")] [InlineData(true, false, "cancellation_requested")]
        [InlineData(false, true, "confirmed_cancelled")] [InlineData(true, true, "confirmed_cancelled")]
        [InlineData(false, true, "already_completed")] [InlineData(true, true, "already_completed")]
        [InlineData(false, true, "cancellation_requested")] [InlineData(true, true, "cancellation_requested")]
        [InlineData(false, false, "failed")] [InlineData(true, false, "failed")]
        [InlineData(false, true, "failed")] [InlineData(true, true, "failed")]
        public async Task Local_stop_and_remote_cancellation_outcomes_remain_distinct(bool video, bool late, string remote)
        {
            using var run = new Run(video); run.Transport.CancelDisposition = remote; run.Transport.HoldSubmit = late;
            await run.Submit();
            await Wait(late ? run.Transport.PostEntered.Task : run.Transport.PollEntered.Task);
            await run.Cancel();
            var localState = run.CancelState;
            if (late) run.Transport.PostRelease.TrySetResult(true);
            await Wait(run.CleanupPersisted.Task);
            var evidence = run.Snapshot()!.Cancellation!;
            Assert.True(evidence.LocalStopped); Assert.Equal(remote, evidence.RemoteDisposition); Assert.Equal(late, evidence.Automatic);
            Assert.Equal(remote == "already_completed" ? GenerationLifecycleState.Completed : (GenerationLifecycleState?)null, evidence.RemoteTerminalState);
            Assert.Equal(remote == "confirmed_cancelled", evidence.RemoteCancellationConfirmed);
            Assert.Equal(localState, video ? run.Videos.ReadAll().Records.Single().State.ToString() : run.Images.ReadAll().Records.Single().State.ToString());
            if (!late) { Assert.Equal(remote, run.LastCancellation!.RemoteDisposition); Assert.Equal(remote != "confirmed_cancelled", run.CancelHadError); }
            Assert.Empty(run.Store.List());
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Accepted_write_budget_expires_while_another_job_holds_ledger_admission(bool video)
        {
            using var run = new Run(video); run.Transport.HoldSubmit = true;
            await run.Submit(); await Wait(run.Transport.PostEntered.Task);
            using var held = await Rook.Tests.Services.Vision.Image.Jobs.LedgerAdmissionTest.Hold(video ? run.Videos.Inner : run.Images.Inner);
            run.Transport.PostRelease.TrySetResult(true);
            await Wait(run.BudgetCreated.Task); run.AcceptedBudget.Cancel();
            await Wait(run.AdmissionCancelled.Task);
            Assert.False(run.Accepted.Task.IsCompleted); Assert.Equal(0, run.Transport.Polls);
            held.Dispose();
            await Wait(run.Terminal.Task);
            Assert.False(run.Accepted.Task.IsCompleted);
            Assert.Equal("unknown", run.Snapshot()!.DispatchState);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Configured_completion_preserves_durable_sidecar_results(bool posterFails)
        {
            using var run = new Run(true); run.Transport.Complete = true; run.PosterFails = posterFails;
            run.Transport.FetchRelease.TrySetResult(true);
            await run.Submit(); await Wait(run.Finished.Task);
            var record = run.Videos.ReadAll().Records.Single();
            Assert.Equal(VideoJobState.Complete, record.State);
            Assert.Equal(posterFails ? "FinalizerFailed" : "Published", record.Extensions?["sidecars"]?["poster"]?["code"]?.GetValue<string>());
            Assert.NotNull(record.Extensions?["sidecars"]?["frames"]);
            Assert.NotNull(record.ConfiguredFalExecution!.Snapshot);
        }
        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Restarted_manager_cleans_up_removed_model_using_saved_binding(bool video)
        {
            using var run = new Run(video, recoverWithoutRegistration: true);
            var snapshot = run.AcceptedSnapshot(); run.Seed(snapshot);
            if (video) run.Video!.ReconcileInterruptedJobs(); else run.Image!.ReconcileInterruptedJobs();
            await run.Cancel();
            Assert.Equal(snapshot.Handle!.CancelUrl, run.Transport.CancelUrl);
            Assert.Equal(0, run.Transport.Posts); Assert.Equal(0, run.Transport.Polls);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Recovery_without_executor_persists_unavailable_remote_outcome(bool video)
        {
            using var run = new Run(video, recoverWithoutRegistration: true, recoveryAvailable: false);
            run.Seed(run.AcceptedSnapshot());
            if (video) run.Video!.ReconcileInterruptedJobs(); else run.Image!.ReconcileInterruptedJobs();
            await run.Cancel();
            Assert.Equal("unavailable", run.Snapshot()!.Cancellation!.RemoteDisposition);
            Assert.Equal("unavailable", run.LastCancellation!.RemoteDisposition);
            Assert.False(run.LastCancellation.RemoteCancellationConfirmed); Assert.True(run.CancelHadError);
            Assert.Null(run.Transport.CancelUrl);
        }

        [Fact]
        public async Task Synchronous_image_completes_as_a_durable_job_without_polling()
        {
            using var run = new Run(false, sync: true);
            await run.Submit(); await Wait(run.Terminal.Task);
            Assert.Single(run.Store.List()); Assert.Equal(1, run.Transport.Posts); Assert.Equal(0, run.Transport.Polls);
            Assert.Equal("accepted", run.Snapshot()!.DispatchState); Assert.Null(run.Snapshot()!.Handle);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Completed_artifact_uses_pinned_canonical_controls(bool video)
        {
            using var run = new Run(video); run.Transport.Complete = true; run.Transport.FetchRelease.TrySetResult(true);
            await run.Submit(); await Wait(run.Terminal.Task);
            var artifact = Assert.Single(run.Store.List());
            var read = FalExecutionSnapshotCodec.Deserialize(artifact.Metadata[FalExecutionSnapshot.ExtensionKey]!.AsObject());
            Assert.NotNull(read.Snapshot);
            if (video) Assert.Equal(5.5m, read.Snapshot!.Request.EffectiveRequestFields["duration_seconds"]!.GetValue<decimal>());
            else { Assert.Equal("canonical prompt", artifact.Metadata["prompt"]!.GetValue<string>()); Assert.Equal(9007199254740991L, read.Snapshot!.Request.EffectiveRequestFields["seed"]!.GetValue<long>()); }
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Admitted_media_is_retained_until_cancelled_transport_settles(bool video)
        {
            using var run = new Run(video); run.Transport.HoldSubmit = true;
            var resources = new Rook.Services.Vision.Video.Framing.VideoPreparationResources(maxBundles: 1);
            var normalized = run.Normalized();
            var media = FalMediaSnapshot.Capture(normalized, new Dictionary<MediaRef, ResolvedMedia>(), resources);
            await run.Submit(normalized, media); await Wait(run.Transport.PostEntered.Task);
            await run.Cancel(); Assert.Equal(1, resources.ActiveBundles);
            run.Transport.PostRelease.TrySetResult(true); await Wait(run.Accepted.Task);
            // Submit settlement, including durable acceptance, precedes lifecycle cleanup.
            await Wait(run.Transport.CancelEntered.Task);
            Assert.Equal(0, resources.ActiveBundles);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Restart_at_intent_is_interrupted_and_nonretryable_without_network(bool video)
        {
            using var run = new Run(video);
            var json = FalExecutionSnapshotCodec.Serialize(FalExecutionSnapshotTests.Snapshot());
            json["handle"] = null; json["dispatch_state"] = "dispatch_intent"; json["submission_outcome"] = null;
            var snapshot = FalExecutionSnapshotCodec.Deserialize(json).Snapshot!;
            run.Seed(snapshot);
            if (video) run.Video!.ReconcileInterruptedJobs(); else run.Image!.ReconcileInterruptedJobs();
            var error = video ? run.Videos.ReadAll().Records.Single().Error : run.Images.ReadAll().Records.Single().Error;
            Assert.False(error!.Retryable);
            Assert.Equal("fal_submission_unknown", error.ProviderErrorCode);
            await run.Cancel(); Assert.Equal(0, run.Transport.Posts); Assert.Equal(0, run.Transport.Polls);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Unsupported_snapshot_never_falls_through_to_registered_provider(bool video)
        {
            using var run = new Run(video); run.Seed(FalExecutionSnapshotTests.Snapshot(), unsupported: true);
            await run.Cancel();
            Assert.Null(run.Transport.CancelUrl); Assert.Equal(0, run.Transport.Posts); Assert.Equal(0, run.Transport.Polls);
            var read = video ? run.Videos.ReadAll().Records.Single().ConfiguredFalExecution : run.Images.ReadAll().Records.Single().ConfiguredFalExecution;
            Assert.NotNull(read!.Diagnostic); Assert.Null(read.Snapshot);
            Assert.Equal("unavailable", run.LastCancellation!.RemoteDisposition); Assert.True(run.CancelHadError);
        }

        [Fact]
        public void Video_record_defensively_copies_extensions()
        {
            using var run = new Run(true); run.Seed(FalExecutionSnapshotTests.Snapshot());
            var record = run.Videos.ReadAll().Records.Single();
            var source = record.Extensions!;
            var copy = record with { Extensions = source };
            source[FalExecutionSnapshot.ExtensionKey]!["version"] = 99;
            copy.Extensions![FalExecutionSnapshot.ExtensionKey]!["version"] = 99;
            Assert.NotNull(copy.ConfiguredFalExecution!.Snapshot);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Known_rejection_preserves_dispatch_evidence_without_unknown_acceptance(bool video)
        {
            using var run = new Run(video); run.Transport.RejectSubmit = true;
            await run.Submit(); await Wait(run.Terminal.Task);
            Assert.Equal("dispatch_intent", run.Snapshot()!.DispatchState);
            Assert.Equal("not_accepted", run.Snapshot()!.SubmissionOutcome); Assert.False(run.Snapshot()!.OutcomeUnknown);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Known_rejection_after_local_stop_clears_unknown_diagnostic(bool video)
        {
            using var run = new Run(video); run.Transport.HoldSubmit = true; run.Transport.RejectSubmit = true;
            await run.Submit(); await Wait(run.Transport.PostEntered.Task); await run.Cancel();
            run.Transport.PostRelease.TrySetResult(true); await Wait(run.Settled.Task);
            Assert.Equal("not_accepted", run.Snapshot()!.SubmissionOutcome);
            var error = video ? run.Videos.ReadAll().Records.Single().Error : run.Images.ReadAll().Records.Single().Error;
            Assert.NotEqual("fal_submission_unknown", error?.ProviderErrorCode);
        }

        [Theory]
        [InlineData(false, false)] [InlineData(true, false)]
        [InlineData(false, true)] [InlineData(true, true)]
        public async Task Stop_during_result_fetch_never_publishes(bool video, bool deadline)
        {
            using var run = new Run(video); run.Transport.Complete = true;
            await run.Submit(); await Wait(run.Transport.FetchEntered.Task);
            if (deadline) run.Expire(); else await run.Cancel();
            run.Transport.FetchRelease.TrySetResult(true); await Wait(run.Terminal.Task);
            Assert.Empty(run.Store.List());
            if (deadline) Assert.Equal("Interrupted", video ? run.Videos.ReadAll().Records.Single().State.ToString() : run.Images.ReadAll().Records.Single().State.ToString());
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Video_stop_at_publication_rolls_back_staged_artifact(bool deadline)
        {
            using var run = new Run(true); run.Transport.Complete = true; run.HoldPublication = true;
            run.Transport.FetchRelease.TrySetResult(true);
            await run.Submit(); await Wait(run.PublicationEntered.Task);
            Assert.Single(run.Store.List());
            if (deadline) run.Expire(); else await run.Cancel();
            run.PublicationRelease.TrySetResult(true); await Wait(run.Finished.Task);
            Assert.Empty(run.Store.List());
            Assert.Equal(deadline ? VideoJobState.Interrupted : VideoJobState.Cancelled, run.Videos.ReadAll().Records.Single().State);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Ledger_failure_before_dispatch_prevents_paid_call(bool video)
        {
            using var run = new Run(video, "dispatch_intent");
            await run.Submit(); await Wait(run.Terminal.Task);
            Assert.Equal(0, run.Transport.Posts);
            Assert.NotNull(run.Snapshot());
            Assert.Equal("prepared", run.Snapshot()!.DispatchState);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Accepted_handle_is_durable_before_poll_and_restart_never_resubmits(bool video)
        {
            using var run = new Run(video);
            await run.Submit(); await Wait(run.Transport.PollEntered.Task);
            Assert.Equal("accepted", run.Snapshot()!.DispatchState);
            Assert.Equal("https://queue.fal.run/fal-ai/synthetic/requests/id/cancel", run.Snapshot()!.Handle!.CancelUrl!.AbsoluteUri);
            if (video) Assert.Null(run.Videos.ReadAll().Records.Single().Extensions?["provider_handle"]);
            await run.Cancel(); run.Transport.PollRelease.TrySetResult(true); await Wait(run.Terminal.Task);
            Assert.Equal(1, run.Transport.Posts);
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Handle_write_failure_is_unknown_and_never_polls_or_publishes(bool video)
        {
            using var run = new Run(video, "accepted");
            await run.Submit(); await Wait(run.Terminal.Task);
            Assert.Equal(1, run.Transport.Posts);
            Assert.Equal(0, run.Transport.Polls);
            Assert.Equal("unknown", run.Snapshot()!.DispatchState);
            Assert.NotNull(run.Snapshot()!.Handle);
            Assert.Empty(run.Store.List());
        }

        [Theory]
        [InlineData(false)] [InlineData(true)]
        public async Task Cancel_during_transport_still_persists_late_acceptance_without_publication(bool video)
        {
            using var run = new Run(video); run.Transport.HoldSubmit = true;
            await run.Submit(); await Wait(run.Transport.PostEntered.Task);
            await run.Cancel(); run.Transport.PostRelease.TrySetResult(true);
            await Wait(run.Accepted.Task);
            Assert.Equal("accepted", run.Snapshot()!.DispatchState);
            Assert.NotNull(run.Snapshot()!.Handle);
            Assert.Empty(run.Store.List());
        }

        [Fact]
        public async Task Removed_catalog_cleanup_uses_only_saved_binding()
        {
            using var transport = new Transport(); using var client = new HttpClient(transport);
            var recovery = new FalExecutionRecovery(new FalConfiguredExecutor(new FalApiClient(client), () => "test-key"));
            var snapshot = FalExecutionSnapshotCodec.Deserialize(FalExecutionSnapshotCodec.Serialize(FalExecutionSnapshotTests.Snapshot())).Snapshot!;
            Assert.IsType<CanceledOutcome>(await recovery.CancelAsync(snapshot, CancellationToken.None));
            Assert.Equal(snapshot.Handle!.CancelUrl, transport.CancelUrl);
            Assert.Equal(0, transport.Posts); Assert.Equal(0, transport.Polls);
        }

        internal sealed class Run : IDisposable
        {
            internal readonly CatalogFiles Files;
            internal readonly string Root = Path.Combine(Path.GetTempPath(), "rook-configured-jobs-" + Guid.NewGuid().ToString("N"));
            internal readonly Transport Transport = new();
            internal readonly HttpClient Client;
            internal readonly ArtifactStore Store;
            internal readonly TaskCompletionSource<bool> Terminal = Signal(), Accepted = Signal(), Settled = Signal();
            internal readonly TaskCompletionSource<bool> BudgetCreated = Signal(), AdmissionCancelled = Signal();
            internal readonly TaskCompletionSource<bool> CleanupPersisted = Signal();
            internal FalCancellationSnapshot? LastCancellation;
            internal string? CancelState;
            internal bool CancelHadError;
            internal readonly CancellationTokenSource AcceptedBudget = new();
            private int _durabilityBudgets;
            private CancellationTokenSource NewDurabilityBudget()
            {
                if (Interlocked.Increment(ref _durabilityBudgets) == 1) { BudgetCreated.TrySetResult(true); return AcceptedBudget; }
                return new CancellationTokenSource(TimeSpan.FromSeconds(10));
            }
            internal readonly TaskCompletionSource<bool> PublicationEntered = Signal(), PublicationRelease = Signal(), Finished = Signal();
            internal bool HoldPublication, PosterFails;
            internal readonly CancellationTokenSource ImageDeadline = new();
            internal readonly ControlledTimer Timer = new();
            internal readonly ImageLedger Images;
            internal readonly VideoLedger Videos;
            internal readonly ImageJobManager? Image;
            internal readonly VideoJobManager? Video;
            internal Guid Id;
            private readonly FalModelDefinition _model;
            internal Run(bool video, string? fail = null, bool recoverWithoutRegistration = false, bool sync = false, bool recoveryAvailable = true)
            {
                Directory.CreateDirectory(Root); Store = new ArtifactStore(Path.Combine(Root, "artifacts"));
                Files = new CatalogFiles(video ? CatalogFiles.VideoJson : CatalogFiles.ImageJson);
                Files.Operation["invocation"] = "queue"; Files.Operation["lifecycle_root"] = "fal-ai/synthetic";
                if (sync) { Files.Operation["invocation"] = "sync"; Files.Operation.Remove("lifecycle_root"); Transport.Sync = true; }
                if (video) { Files.Operation["operation_id"] = "text_to_video"; Files.Operation["media"] = new JsonArray();
                    var duration = Files.Operation["fields"]![0]!; duration["type"] = "number"; duration["default"] = 5.5m; duration["payload"]!["conversion"] = "identity"; }
                Files.Save(); _model = Files.Compile().Catalog!.Definitions.Single();
                Images = new ImageLedger(new JsonlImageJobLedger(Path.Combine(Root, "image.jsonl")), this, fail);
                Videos = new VideoLedger(new JsonlVideoJobLedger(Path.Combine(Root, "video.jsonl")), this, fail);
                Client = new HttpClient(Transport); var executor = new FalConfiguredExecutor(new FalApiClient(Client), () => "test-key");
                if (video)
                {
                    var registry = new DefaultVideoProviderRegistry(recoverWithoutRegistration ? Array.Empty<IVideoProviderRegistration>() : new[] { new ConfiguredFalVideoRegistration(_model, executor, new FalAdapterRegistry(), new NoPricing<VideoGenerationRequest, VideoCapability>()) });
                    var poster = new Rook.Tests.Services.Vision.Video.FakePosterProducer(Store);
                    poster.OnPublishAsync = async (artifact, token) => { PublicationEntered.TrySetResult(true); if (HoldPublication) await PublicationRelease.Task; if (PosterFails) throw new InvalidOperationException("controlled poster failure"); return VideoPosterSidecarResult.From(VideoPosterSidecarResultCode.Published, artifact.Id); };
                    Video = new VideoJobManager(registry, new NoMedia(), Videos, new VideoCostEstimator(), Store, null, null, null, 2,
                        new VideoArtifactMaterializer(Transport), poster, new Rook.Tests.Services.Vision.Video.FakeFrameProducer(Store), deadlineTimer: Timer, configuredRecovery: recoveryAvailable ? new FalExecutionRecovery(executor) : null, configuredDurabilityBudgetFactory: NewDurabilityBudget);
                    Video.AfterRunForTests = _ => Finished.TrySetResult(true);
                }
                else
                {
                    var registry = new DefaultImageProviderRegistry(recoverWithoutRegistration ? Array.Empty<IImageProviderRegistration>() : new[] { new ConfiguredFalImageRegistration(_model, executor, new FalAdapterRegistry(), new NoPricing<ImageGenerationRequest, ImageCapability>()) });
                    Image = new ImageJobManager(registry, Store, null, null, null, 2, new ImageArtifactMaterializer(Transport), null, Images, deadlineFactory: _ => ImageDeadline, configuredRecovery: recoveryAvailable ? new FalExecutionRecovery(executor) : null, configuredDurabilityBudgetFactory: NewDurabilityBudget);
                }
            }
            internal FalNormalizedRequest Normalized()
                => new FalModelNormalizer().Normalize(_model.Operations.Single(), new FalModelInput(Video != null ? new JsonObject { ["duration_seconds"] = 5.5m } : new JsonObject { ["prompt"] = "canonical prompt", ["seed"] = 9007199254740991L }, operationId: _model.Operations.Single().OperationId)).Request!;
            internal FalExecutionSnapshot AcceptedSnapshot()
            {
                var request = Normalized();
                using var media = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>(), new Rook.Services.Vision.Video.Framing.VideoPreparationResources());
                return FalExecutionSnapshot.Create(request, media).WithDispatchState("accepted", FalExecutionSnapshotTests.Snapshot().Handle);
            }
            internal async Task Submit(FalNormalizedRequest? normalized = null, FalMediaSnapshot? media = null)
            {
                var input = new FalModelInput(Video != null ? new JsonObject { ["duration_seconds"] = 5.5m } : new JsonObject { ["prompt"] = "canonical prompt", ["seed"] = 9007199254740991L });
                var options = new FalModelOptions(input, Video != null ? "text_to_video" : "text_to_image");
                if (Video != null)
                {
                    var shell = new VideoGenerationRequest(_model.ModelId, VideoMode.T2V, 0, "placeholder", "placeholder", null, null, null, null, null, options, 1);
                    var result = normalized == null ? await Video.SubmitAsync(shell, CancellationToken.None) : await Video.SubmitConfiguredAsync(shell, normalized, media!, null, CancellationToken.None);
                    Assert.Null(result.Error); Id = result.JobId!.Value;
                }
                else
                {
                    var request = new ImageGenerationRequest(_model.ModelId, "placeholder", "placeholder", "placeholder", 1, null, options);
                    var result = await Image!.SubmitAsync(new ImageJobStartRequest(request, new Dictionary<MediaRef, ResolvedMedia>(), Array.Empty<Guid>(), configuredRequest: normalized, configuredMedia: media), CancellationToken.None);
                    Assert.Null(result.Error); Id = result.JobId!.Value;
                }
            }
            internal async Task Cancel()
            {
                if (Video != null) { var result = await Video.CancelAsync(Id, CancellationToken.None); LastCancellation = result.ConfiguredCancellation; CancelHadError = result.Error != null; CancelState = Videos.ReadAll().Records.Single().State.ToString(); }
                else { var result = await Image!.CancelAsync(Id, CancellationToken.None); LastCancellation = result.ConfiguredCancellation; CancelHadError = result.Error != null; CancelState = Images.ReadAll().Records.Single().State.ToString(); }
            }
            internal void Expire() { if (Video != null) Timer.Fire(); else ImageDeadline.Cancel(); }
            internal void Seed(FalExecutionSnapshot snapshot, bool unsupported = false)
            {
                Id = Guid.NewGuid(); var now = DateTimeOffset.UtcNow;
                var json = FalExecutionSnapshotCodec.Serialize(snapshot); if (unsupported) json["version"] = 99;
                if (Video != null)
                {
                    var request = new VideoGenerationRequest(_model.ModelId, VideoMode.T2V, 0, "placeholder", "placeholder", null, null, null, null, null, new FalModelOptions(new FalModelInput()), 1);
                    var pricing = new Rook.Services.Vision.Video.JobPricing(PricingKind.External, "USD", 1, null, null, "test");
                    Videos.Append(new VideoJobRecord(1, Id, "fal", _model.ModelId, snapshot.Handle?.ProviderJobId, null, VideoJobState.Submitting,
                        new NormalizedRequest(VideoMode.T2V, 0, "placeholder", "placeholder", null, null, null, null, null, 1), new JsonObject(), pricing, null, null, now, now,
                        new JsonObject { [FalExecutionSnapshot.ExtensionKey] = json }));
                }
                else Images.Append(ImageJobLedgerRecordFactory.FromInitial(Id, "fal", _model.ModelId, ImageJobState.Submitting, now) with
                    { ConfiguredFalExecution = FalExecutionSnapshotCodec.Deserialize(json) });
            }
            internal FalExecutionSnapshot? Snapshot() => Video != null ? Videos.ReadAll().Records.Last().ConfiguredFalExecution?.Snapshot : Images.ReadAll().Records.Last().ConfiguredFalExecution?.Snapshot;
            public void Dispose() { Image?.Dispose(); Video?.Dispose(); Transport.PostRelease.TrySetResult(true); Transport.PollRelease.TrySetResult(true); Transport.FetchRelease.TrySetResult(true); PublicationRelease.TrySetResult(true); Client.Dispose(); Files.Dispose(); }
        }
        internal sealed class ImageLedger : ICancellationAwareImageJobLedger
        {
            private readonly IImageJobLedger _inner; private readonly Run _run; private readonly string? _fail;
            internal ImageLedger(IImageJobLedger inner, Run run, string? fail) { _inner = inner; _run = run; _fail = fail; }
            internal object Inner => _inner;
            public void Append(ImageJobLedgerRecord r) => Append(r, CancellationToken.None);
            public void Append(ImageJobLedgerRecord r, CancellationToken ct)
            {
                if (r.ConfiguredFalExecution?.Snapshot?.DispatchState == _fail && _fail != null) throw new IOException("injected durability failure");
                ((ICancellationAwareImageJobLedger)_inner).Append(r, ct);
                if (r.ConfiguredFalExecution?.Snapshot?.Cancellation is { RemoteDisposition: not "unavailable" }) _run.CleanupPersisted.TrySetResult(true);
                if (r.ConfiguredFalExecution?.Snapshot?.SubmissionOutcome != null) _run.Settled.TrySetResult(true);
                if (r.ConfiguredFalExecution?.Snapshot?.DispatchState == "accepted") _run.Accepted.TrySetResult(true);
                if (r.State is ImageJobState.Error or ImageJobState.Cancelled or ImageJobState.Interrupted or ImageJobState.Complete) _run.Terminal.TrySetResult(true);
            }
            public ImageJobLedgerReadResult ReadAll() => _inner.ReadAll();
            public ImageJobLedgerReadResult ReadAll(CancellationToken ct)
            {
                try { return ((ICancellationAwareImageJobLedger)_inner).ReadAll(ct); }
                catch (OperationCanceledException) { _run.AdmissionCancelled.TrySetResult(true); throw; }
            }
        }
        internal sealed class VideoLedger : ICancellationAwareVideoJobLedger
        {
            private readonly IVideoJobLedger _inner; private readonly Run _run; private readonly string? _fail;
            internal VideoLedger(IVideoJobLedger inner, Run run, string? fail) { _inner = inner; _run = run; _fail = fail; }
            internal object Inner => _inner;
            public void Append(VideoJobRecord r) => Append(r, CancellationToken.None);
            public void Append(VideoJobRecord r, CancellationToken ct)
            {
                if (r.ConfiguredFalExecution?.Snapshot?.DispatchState == _fail && _fail != null) throw new IOException("injected durability failure");
                ((ICancellationAwareVideoJobLedger)_inner).Append(r, ct);
                if (r.ConfiguredFalExecution?.Snapshot?.Cancellation is { RemoteDisposition: not "unavailable" }) _run.CleanupPersisted.TrySetResult(true);
                if (r.ConfiguredFalExecution?.Snapshot?.SubmissionOutcome != null) _run.Settled.TrySetResult(true);
                if (r.ConfiguredFalExecution?.Snapshot?.DispatchState == "accepted") _run.Accepted.TrySetResult(true);
                if (r.State is VideoJobState.Error or VideoJobState.Cancelled or VideoJobState.Interrupted or VideoJobState.Complete) _run.Terminal.TrySetResult(true);
            }
            public VideoJobLedgerReadResult ReadAll() => _inner.ReadAll();
            public VideoJobLedgerReadResult ReadAll(CancellationToken ct)
            {
                try { return ((ICancellationAwareVideoJobLedger)_inner).ReadAll(ct); }
                catch (OperationCanceledException) { _run.AdmissionCancelled.TrySetResult(true); throw; }
            }
        }
        internal sealed class Transport : HttpMessageHandler
        {
            internal int Posts, Polls; internal bool HoldSubmit, RejectSubmit, Complete, Sync; internal Uri? CancelUrl;
            internal string CancelDisposition = "confirmed_cancelled";
            internal readonly TaskCompletionSource<bool> PostEntered = Signal(), PostRelease = Signal(), PollEntered = Signal(), PollRelease = Signal();
            internal readonly TaskCompletionSource<bool> FetchEntered = Signal(), FetchRelease = Signal();
            internal readonly TaskCompletionSource<bool> CancelEntered = Signal();
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                if (request.Method == HttpMethod.Post)
                {
                    Interlocked.Increment(ref Posts); PostEntered.TrySetResult(true);
                    if (HoldSubmit) await PostRelease.Task;
                    if (RejectSubmit) return new HttpResponseMessage(HttpStatusCode.BadRequest) { Content = new StringContent("{}") };
                    if (Sync) return Response("""{"images":[{"url":"https://fal.media/image.png","content_type":"image/png"}]}""");
                    return Response("""{"request_id":"id","status_url":"https://queue.fal.run/fal-ai/synthetic/requests/id/status","response_url":"https://queue.fal.run/fal-ai/synthetic/requests/id","cancel_url":"https://queue.fal.run/fal-ai/synthetic/requests/id/cancel"}""");
                }
                if (request.Method == HttpMethod.Put)
                {
                    CancelUrl = request.RequestUri; CancelEntered.TrySetResult(true);
                    return CancelDisposition == "already_completed" ? new HttpResponseMessage(HttpStatusCode.BadRequest) { Content = new StringContent("{\"status\":\"ALREADY_COMPLETED\"}") }
                        : CancelDisposition == "failed" ? new HttpResponseMessage(HttpStatusCode.NotFound) { Content = new StringContent("{\"status\":\"NOT_FOUND\"}") }
                        : CancelDisposition == "cancellation_requested" ? new HttpResponseMessage(HttpStatusCode.Accepted) { Content = new StringContent("{\"status\":\"CANCELLATION_REQUESTED\"}") }
                        : Response("{\"status\":\"OK\"}");
                }
                if (request.RequestUri!.Host == "fal.media") return new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[] { 1, 2, 3, 4 }) { Headers = { ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(request.RequestUri.AbsolutePath.EndsWith(".png") ? "image/png" : "video/mp4") } } };
                if (Complete && request.RequestUri.AbsolutePath.EndsWith("/status")) return Response("{\"status\":\"COMPLETED\"}");
                if (Complete)
                {
                    FetchEntered.TrySetResult(true); await FetchRelease.Task;
                    return Response("""{"video":{"url":"https://fal.media/video.mp4"},"images":[{"url":"https://fal.media/image.png","content_type":"image/png"}]}""");
                }
                Interlocked.Increment(ref Polls); PollEntered.TrySetResult(true); await PollRelease.Task;
                return Response("{\"status\":\"IN_QUEUE\"}");
            }
            private static HttpResponseMessage Response(string text) => new(HttpStatusCode.OK) { Content = new StringContent(text) };
        }
        private sealed class NoMedia : IMediaResolver
        { public Task<MediaResolutionResult> ResolveAllAsync(IReadOnlyList<MediaRef> refs, CancellationToken ct) => Task.FromResult(MediaResolutionResult.Ok(new Dictionary<MediaRef, ResolvedMedia>())); }
        private sealed class NoPricing<T, C> : IPricingModel<T, C> where T : GenerationRequest where C : IModelCapability
        {
            public string PricingSource => "test"; public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;
            public PricingResult Estimate(T request, C capability) => PricingResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest, "legacy pricing must not run", false));
            public Rook.Services.Vision.Generation.JobPricing? ExtractActualSpend(IReadOnlyDictionary<string, IReadOnlyList<string>> headers, JsonNode? body) => null;
        }
        private static TaskCompletionSource<bool> Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
        private static async Task Wait(Task task)
        { Assert.Same(task, await Task.WhenAny(task, Task.Delay(TimeSpan.FromSeconds(10)))); await task; }
        internal sealed class ControlledTimer : IVideoDeadlineTimer
        {
            private Action? _callback;
            public IDisposable Schedule(DateTimeOffset time, Action callback) { _callback = callback; return new Noop(); }
            internal void Fire() => _callback?.Invoke();
            private sealed class Noop : IDisposable { public void Dispose() { } }
        }
    }
}
