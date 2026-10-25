using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Fal
{
    public class FalConfiguredExecutorTests
    {
        [Fact]
        public async Task Encoded_ownership_survives_preparation_until_dispatch_settles()
        {
            using var run = new ConfiguredRun();
            run.Observer.DispatchWrite = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var submit = run.Submit();
            try { Assert.Equal(1, run.Resources.ActiveBundles); }
            finally { run.Observer.DispatchWrite.TrySetResult(true); await submit; }
            Assert.Equal(0, run.Resources.ActiveBundles);
        }
        [Theory]
        [InlineData("success")]
        [InlineData("network")]
        [InlineData("cancel")]
        public async Task Payload_admission_stays_held_until_HTTP_settles_even_after_snapshot_disposal(string finish)
        {
            using var run = new ConfiguredRun();
            using var files = FalMediaPreparationTests.MediaFiles("data_uri");
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = FalMediaPreparationTests.Request(files, new[] { new FalMediaInput("reference_image", 0, source) });
            using var snapshot = FalMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(FalMediaPreparationTests.Png, "image/png") }, run.Resources);
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using var stop = new CancellationTokenSource();
            run.OnHttp = async (http, ct) =>
            {
                Assert.Contains("data:image/png;base64,", await http.Content!.ReadAsStringAsync());
                entered.TrySetResult(true); await release.Task;
                if (finish == "network") throw new HttpRequestException();
                if (finish == "cancel") throw new OperationCanceledException(ct);
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"images\":[{\"url\":\"https://fal.media/result.png\"}]}") };
            };
            var submit = run.Executor.SubmitAsync(request, snapshot, run.Observer, stop.Token);
            try
            {
                Assert.Same(entered.Task, await Task.WhenAny(entered.Task, Task.Delay(5000)));
                snapshot.Dispose(); if (finish == "cancel") stop.Cancel();
                Assert.False(submit.IsCompleted); Assert.Equal(1, run.Resources.ActiveBundles);
                using var second = FalMediaSnapshot.Capture(run.Request, new Dictionary<MediaRef, ResolvedMedia>(), run.Resources);
                using var denied = FalMediaSnapshot.Capture(run.Request, new Dictionary<MediaRef, ResolvedMedia>(), run.Resources);
                Assert.Null(second.ValidationError); Assert.Equal("media_preparation_busy", denied.ValidationError!.ProviderErrorCode);
            }
            finally { release.TrySetResult(true); }
            var outcome = await submit;
            if (finish == "success") Assert.IsType<SyncSubmitOutcome>(outcome);
            else Assert.Equal(SubmissionDisposition.Unknown, Assert.IsType<FailedSubmitOutcome>(outcome).Disposition);
            Assert.Equal(0, run.Resources.ActiveBundles);
        }
        [Theory]
        [InlineData("beforeUpload")]
        [InlineData("beforeDispatch")]
        [InlineData("accepted_write")]
        public async Task Admission_and_persistence_failures_release_payload_reservations(string failure)
        {
            using var run = new ConfiguredRun();
            if (failure == "accepted_write") run.Failure = failure; else run.Observer.DeniedPhase = failure;
            using var snapshot = FalMediaSnapshot.Capture(run.Request, new Dictionary<MediaRef, ResolvedMedia>(), run.Resources);
            var outcome = Assert.IsType<FailedSubmitOutcome>(await run.Executor.SubmitAsync(run.Request, snapshot, run.Observer, CancellationToken.None));
            Assert.Equal(failure == "accepted_write" ? SubmissionDisposition.Unknown : SubmissionDisposition.NotAccepted, outcome.Disposition);
            Assert.Equal(0, snapshot.Phase.Buffers.ReservedBytes); Assert.Equal(1, run.Resources.ActiveBundles);
            snapshot.Dispose(); Assert.Equal(0, run.Resources.ActiveBundles);
        }
        [Theory]
        [InlineData("sync", false)]
        [InlineData("queue", false)]
        [InlineData("queue", true)]
        public async Task Dispatch_intent_precedes_exactly_one_submit(string invocation, bool video)
        {
            using var run = new ConfiguredRun(invocation, video);
            var outcome = await run.Submit();
            Assert.Equal(invocation == "queue" ? new[] { "beforeUpload", "beforeDispatch", "submit", "accepted" } : new[] { "beforeUpload", "beforeDispatch", "submit" }, run.Events);
            if (invocation == "queue") Assert.IsType<QueuedSubmitOutcome>(outcome);
            else Assert.IsType<SuccessResultOutcome>(Assert.IsType<SyncSubmitOutcome>(outcome).Result);
        }

        [Theory]
        [InlineData("beforeUpload")]
        [InlineData("beforeDispatch")]
        public async Task Unconfirmed_input_never_submits(string deniedPhase)
        {
            using var run = new ConfiguredRun(); run.Observer.DeniedPhase = deniedPhase;
            var failure = Assert.IsType<FailedSubmitOutcome>(await run.Submit());
            Assert.Equal(SubmissionDisposition.NotAccepted, failure.Disposition);
            Assert.DoesNotContain("submit", run.Events);
        }

        [Theory]
        [InlineData(401)]
        [InlineData(422)]
        public async Task Authentication_and_provider_validation_are_not_accepted(int status)
        {
            using var run = new ConfiguredRun(); run.Status = status;
            var failure = Assert.IsType<FailedSubmitOutcome>(await run.Submit());
            Assert.Equal(SubmissionDisposition.NotAccepted, failure.Disposition);
            Assert.False(failure.Error.Retryable);
        }

        [Theory]
        [InlineData("timeout")]
        [InlineData("network")]
        [InlineData("cancel")]
        [InlineData("missing_handle")]
        [InlineData("bad_handle")]
        [InlineData("accepted_write")]
        [InlineData("server_error")]
        public async Task Uncertain_dispatch_is_unknown_and_never_replayed(string failure)
        {
            using var run = new ConfiguredRun();
            run.Failure = failure;
            var failed = Assert.IsType<FailedSubmitOutcome>(await run.Submit());
            Assert.Equal(SubmissionDisposition.Unknown, failed.Disposition); Assert.False(failed.Error.Retryable);
            await run.Executor.GetStatusAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None);
            await run.Executor.CancelAsync(run.Request.Binding, ConfiguredRun.Handle(), CancellationToken.None);
            Assert.Single(run.Events, e => e == "submit");
        }

        [Fact]
        public async Task Dispatch_and_acceptance_wait_for_observer_writes()
        {
            using var run = new ConfiguredRun();
            run.Observer.DispatchWrite = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            run.Observer.AcceptedWrite = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var submit = run.Submit();
            Assert.Equal(new[] { "beforeUpload", "beforeDispatch" }, run.Events); Assert.False(submit.IsCompleted);
            run.Observer.DispatchWrite.SetResult(true);
            Assert.Same(run.Observer.AcceptedEntered.Task, await Task.WhenAny(run.Observer.AcceptedEntered.Task, Task.Delay(5000)));
            Assert.False(submit.IsCompleted);
            run.Observer.AcceptedWrite.SetResult(true);
            Assert.IsType<QueuedSubmitOutcome>(await submit);
            Assert.Equal(new[] { "beforeUpload", "beforeDispatch", "submit", "accepted" }, run.Events);
        }

        [Fact]
        public async Task Cancellation_and_timeout_before_dispatch_are_not_accepted()
        {
            using var run = new ConfiguredRun(); run.Observer.ThrowBeforeDispatch = true;
            var failure = Assert.IsType<FailedSubmitOutcome>(await run.Submit());
            Assert.Equal(SubmissionDisposition.NotAccepted, failure.Disposition); Assert.DoesNotContain("submit", run.Events);
        }

        [Fact]
        public async Task Missing_credentials_never_dispatch()
        {
            using var run = new ConfiguredRun(); run.Key = null;
            Assert.IsType<FailedSubmitOutcome>(await run.Submit()); Assert.Empty(run.Events);
        }

        [Fact]
        public async Task Result_validation_precedes_sync_success()
        {
            using var run = new ConfiguredRun("sync"); run.Body = "{\"images\":[]}";
            Assert.IsType<FailedResultOutcome>(Assert.IsType<SyncSubmitOutcome>(await run.Submit()).Result);
        }

        [Fact]
        public void Old_failed_constructor_remains_known_not_accepted()
            => Assert.Equal(SubmissionDisposition.NotAccepted, new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.InvalidRequest, "invalid", false)).Disposition);
    }

    internal sealed class ConfiguredRun : IDisposable
    {
        internal readonly CatalogFiles Files;
        internal readonly List<string> Events = new();
        internal readonly RecordingObserver Observer;
        internal readonly FalNormalizedRequest Request;
        internal readonly FalConfiguredExecutor Executor;
        internal readonly HttpClient Http;
        internal readonly VideoPreparationResources Resources = new();
        internal int Status = 200;
        internal string? Body, Failure, Key = "test-key";
        internal string? LastUrl;
        internal Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>? OnHttp;
        internal const string Root = "https://queue.fal.run/fal-ai/synthetic/requests/job-1";
        internal ConfiguredRun(string invocation = "queue", bool video = false)
        {
            Files = new CatalogFiles(video ? CatalogFiles.VideoJson : CatalogFiles.ImageJson);
            Files.Operation["invocation"] = invocation;
            if (invocation == "queue") Files.Operation["lifecycle_root"] = "fal-ai/synthetic";
            if (video) { Files.Operation["operation_id"] = "text_to_video"; Files.Operation["media"] = new JsonArray(); }
            Files.Save();
            var binding = FalModelNormalizerTests.Binding(Files);
            var normalized = new FalModelNormalizer().Normalize(binding, video ? new FalModelInput(new JsonObject()) : FalModelNormalizerTests.Prompt());
            Assert.True(normalized.Success); Request = normalized.Request!;
            Observer = new RecordingObserver(Events, () => Failure);
            Http = new HttpClient(new Handler(this));
            Executor = new FalConfiguredExecutor(new FalApiClient(Http), () => Key);
        }
        internal async Task<ProviderSubmitOutcome> Submit()
        {
            using var snapshot = FalMediaSnapshot.Capture(Request, new Dictionary<MediaRef, ResolvedMedia>(), Resources);
            return await Executor.SubmitAsync(Request, snapshot, Observer, CancellationToken.None);
        }
        internal static ProviderJobHandle Handle(string? status = null, string? result = null, string? cancel = null) => new("job-1", new Uri(status ?? Root + "/status"), new Uri(result ?? Root), new Uri(cancel ?? Root + "/cancel"), "PUT");
        public void Dispose() { Http.Dispose(); Files.Dispose(); }
        private sealed class Handler : HttpMessageHandler
        {
            private readonly ConfiguredRun _run;
            internal Handler(ConfiguredRun run) { _run = run; }
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            {
                _run.LastUrl = request.RequestUri!.AbsoluteUri;
                if (_run.Failure == "lifecycle_timeout" && request.Method != HttpMethod.Post) throw new TaskCanceledException();
                if (_run.Failure == "lifecycle_network" && request.Method != HttpMethod.Post) throw new HttpRequestException();
                if (request.Method == HttpMethod.Post)
                {
                    _run.Events.Add("submit");
                    if (_run.Failure == "timeout") throw new TaskCanceledException();
                    if (_run.Failure == "network") throw new HttpRequestException();
                    if (_run.Failure == "cancel") throw new OperationCanceledException();
                }
                if (_run.OnHttp != null) return _run.OnHttp(request, ct);
                var body = _run.Body ?? (_run.Request.Binding.Invocation == "sync" ? "{\"images\":[{\"url\":\"https://fal.media/result.png\"}]}" : QueueBody());
                if (_run.Failure == "missing_handle") body = "{}";
                if (_run.Failure == "bad_handle") body = QueueBody().Replace("queue.fal.run", "evil.example");
                return Task.FromResult(new HttpResponseMessage((HttpStatusCode)(_run.Failure == "server_error" ? 503 : _run.Status)) { Content = new StringContent(body) });
            }
        }
        internal static string QueueBody() => new JsonObject { ["request_id"] = "job-1", ["status_url"] = Root + "/status", ["response_url"] = Root, ["cancel_url"] = Root + "/cancel" }.ToJsonString();
    }
    internal sealed class RecordingObserver : IFalExecutionObserver
    {
        private readonly List<string> _events; private readonly Func<string?> _failure;
        internal string? DeniedPhase; internal bool ThrowBeforeDispatch;
        internal TaskCompletionSource<bool>? DispatchWrite, AcceptedWrite;
        internal readonly TaskCompletionSource<bool> AcceptedEntered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal RecordingObserver(List<string> events, Func<string?> failure) { _events = events; _failure = failure; }
        public Task<GenerationError?> BeforeUploadAsync(CancellationToken ct) => Before("beforeUpload");
        public async Task<GenerationError?> BeforeDispatchAsync(CancellationToken ct)
        { if (ThrowBeforeDispatch) throw new TaskCanceledException(); var error = await Before("beforeDispatch"); if (DispatchWrite != null) await DispatchWrite.Task; return error; }
        private Task<GenerationError?> Before(string phase) { _events.Add(phase); return Task.FromResult(phase == DeniedPhase ? new GenerationError(GenerationErrorCode.InvalidRequest, "denied", false) : null); }
        public async Task AcceptedAsync(ProviderJobHandle handle, CancellationToken ct)
        { _events.Add("accepted"); AcceptedEntered.TrySetResult(true); if (_failure() == "accepted_write") throw new InvalidOperationException("write failed"); if (AcceptedWrite != null) await AcceptedWrite.Task; }
    }
}
