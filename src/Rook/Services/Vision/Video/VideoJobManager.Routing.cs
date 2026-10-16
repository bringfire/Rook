using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video
{
    public sealed partial class VideoJobManager
    {
        private readonly VideoSubmissionCoordinator? _routeCoordinator;
        public bool ConfirmedRoutingAvailable => _routeCoordinator != null && _routeQuotes != null;
        public JsonObject ModelAvailability(string model)
        {
            if (_routeCoordinator == null || !VideoSubmissionCoordinator.IsAffectedModel(model)) return new JsonObject();
            bool googleModel = VideoSubmissionCoordinator.IsGoogleModel(model), configured = false, falConfigured = false, secretFailed = false;
            try {
                configured = _routeCoordinator.Secrets.HasSecret(googleModel ? GenerationSecretKeys.GeminiApiKey : GenerationSecretKeys.FalApiKey);
                if (!configured && googleModel) falConfigured = _routeCoordinator.Secrets.HasSecret(GenerationSecretKeys.FalApiKey);
            } catch { secretFailed = true; }
            string falModel = VideoSubmissionCoordinator.FalModelFor(model) ?? model;
            bool falAvailable = _routeCoordinator.Bindings.All.Any(b => b.ModelId == falModel && b.SubmissionVerified && (b.NewSubmissionCutoffUtc == null || b.NewSubmissionCutoffUtc > _clock.UtcNow()));
            bool available = googleModel || falAvailable;
            bool canGenerate = !secretFailed && (configured && available || googleModel && falConfigured && falAvailable);
            string? reason = canGenerate ? null : secretFailed ? "Generation credential store could not be read." : googleModel && !falAvailable
                ? "Video generation needs a Google API key. Fal Veo fallback is currently disabled." : !available
                ? "Fal Veo generation is currently disabled until endpoint continuity is verified." : "Configure a video provider API key in Vision Settings.";
            return new JsonObject { ["credential_configured"] = configured, ["new_submission_available"] = available,
                ["availability_reason"] = available ? null : "endpoint_continuity_unverified", ["can_generate"] = canGenerate,
                ["generation_unavailable_reason"] = reason, ["generation_unavailable_detail_code"] = canGenerate ? null : secretFailed ? "secret_access_failed" : "video_route_unavailable" };
        }
        private readonly VideoRouteQuoteService? _routeQuotes;
        private readonly IVideoDeadlineTimer _routeTimer;
        private readonly VideoPublicationService _publication;
        internal Action<Guid>? AfterRollbackForTests;
        private readonly ConcurrentDictionary<Guid, RoutedJob> _routedJobs = new();
        private readonly ConcurrentDictionary<Guid, VideoJobRecord> _routeRecordCache = new();
        private IReadOnlyList<LedgerReadError> _routeReadErrors = Array.Empty<LedgerReadError>();

        private sealed class RoutedJob
        {
            internal readonly object Gate = new();
            internal volatile VideoJobRecord Durable;
            internal readonly VideoRequestIntent Intent;
            internal readonly VideoRouteQuote Quote;
            internal readonly VideoSubmitConfirmation Confirmation;
            internal readonly VideoExecutionBudget Budget;
            internal VideoRouteCandidate Candidate;
            internal volatile ProviderJobHandle? KnownHandle;
            internal VideoPreparedBundleLease? Bundle;
            internal volatile VideoStopPersistence StopPersistence;
            internal volatile bool PersistenceFailed;
            internal int CleanupRunning;
            internal volatile string? CleanupOutcome;
            internal volatile string? CleanupPersistence;
            internal volatile string? PublicationWarning;
            internal bool CompletionCommitAttempted;
            internal readonly TaskCompletionSource<bool> Finished = new(TaskCreationOptions.RunContinuationsAsynchronously);
            internal RoutedJob(VideoJobRecord record, VideoRequestIntent intent, VideoRouteQuote quote, VideoSubmitConfirmation confirmation, VideoExecutionBudget budget, VideoRouteCandidate candidate)
            { Durable = record; Intent = intent; Quote = quote; Confirmation = confirmation; Budget = budget; Candidate = candidate; }
        }
        private sealed class RouteFailure : Exception
        {
            internal readonly GenerationError Error;
            internal RouteFailure(GenerationError error) { Error = error; }
        }
        Task<VideoRouteQuoteResult> IVideoConfirmedJobManager.QuoteAsync(VideoRequestIntent intent, CancellationToken ct) => _routeQuotes != null ? _routeQuotes.QuoteAsync(intent, ct) : Task.FromResult(new VideoRouteQuoteResult(null, RoutingError("Video route quotation is unavailable.")));
        Task<JobSubmitResult> IVideoConfirmedJobManager.SubmitConfirmedAsync(VideoRequestIntent intent, VideoSubmitConfirmation confirmation, CancellationToken ct) => SubmitRoutedAsync(intent, confirmation, ct);

        private async Task<JobSubmitResult> SubmitRoutedAsync(VideoRequestIntent intent, VideoSubmitConfirmation confirmation, CancellationToken ct)
        {
            if (_routeQuotes is null || _routeCoordinator is null) return JobSubmitResult.Fail(RoutingError("Video route orchestration is unavailable."));
            if (VideoFramingPreparationService.ValidateUse(intent.Request) is { } framingError) return JobSubmitResult.Fail(framingError);
            if (intent.Request.SourceFraming != null && (confirmation.EstimateFingerprint == null || confirmation.MaxEstimatedCostUsd == null))
                return JobSubmitResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest, "Framed video requires a fresh estimate fingerprint and numeric cost cap.", false, "estimate_fingerprint"));
            var prepared = await _routeQuotes.PrepareSubmissionAsync(intent, ct).ConfigureAwait(false);
            if (prepared.Error != null) return JobSubmitResult.Fail(prepared.Error);
            var bundle = prepared.Bundle!; bool transferred = false;
            try
            {
                var quote = prepared.Quote!;
                var candidate = _routeCoordinator.SelectInitial(quote);
                if (_routeQuotes.ValidateConfirmation(quote, confirmation, candidate) is { } confirmationError) return JobSubmitResult.Fail(confirmationError);
                var now = _clock.UtcNow();
                var record = VideoJobRecordFactory.From(_idGenerator.NewJobId(), candidate.Request, candidate.Model, candidate.Estimate!, VideoJobState.Queued, now);
                var data = new JsonObject { ["requested_provider"] = VideoSubmissionCoordinator.IsGoogleModel(intent.Request.Model) ? "veo" : "fal", ["requested_model"] = intent.Request.Model, ["supplied_options"] = intent.SuppliedOptions, ["normalized_google_options"] = intent.Request.Options is VeoOptions veo ? new VeoOptionsCodec().Serialize(veo) : null, ["accepted_quote"] = quote.CanonicalSnapshot, ["estimate_fingerprint"] = confirmation.EstimateFingerprint, ["max_estimated_cost_usd"] = confirmation.MaxEstimatedCostUsd, ["deadline_utc"] = now.AddMinutes(20).ToString("O"), ["phase"] = "queued", ["attempts"] = new JsonArray() };
                if (bundle.SourcePreparation != null) data["source_preparation"] = bundle.SourcePreparation;
                record = VideoExecutionSnapshot.Write(record, new VideoExecutionSnapshot(1, data));
                ct.ThrowIfCancellationRequested();
                try { _ledger.Append(record); _routeRecordCache[record.JobId] = record; }
                catch { return JobSubmitResult.Fail(PersistenceError()) with { Execution = new VideoExecutionProjection(new JsonObject { ["execution_stopped"] = true, ["stop_persistence"] = "failed", ["durability_unknown"] = true, ["job_id"] = record.JobId.ToString("D") }) }; }
                var job = new RoutedJob(record, intent, quote, confirmation, new VideoExecutionBudget(now.AddMinutes(20), _clock, _routeTimer), candidate) { Bundle = bundle };
                _routedJobs[record.JobId] = job; transferred = true;
                job.Budget.Token.Register(() => {
                    if (job.Budget.FirstStopReason is null) return;
                    job.StopPersistence = VideoStopPersistence.Pending;
                    _ = PersistObservedStopAsync(job);
                    if (job.KnownHandle is { } known) _ = Task.Run(() => CleanupRoutedHandleAsync(job, known));
                });
                if (_shutdownCts.IsCancellationRequested) ObserveStop(job, VideoStopReason.Shutdown);
                _ = Task.Run(() => RunRoutedAsync(job));
                return JobSubmitResult.Ok(record.JobId, VideoJobState.Queued) with { Execution = RouteProjection(record) };
            }
            finally { if (!transferred) bundle.Dispose(); }
        }

        private void CommitRouted(RoutedJob job, Func<VideoJobRecord, VideoJobRecord> update)
        {
            lock (job.Gate)
            {
                // Every worker transition, including failures selected before
                // this lock, must defer to the latest terminal state and stop.
                CheckRouted(job);
                AppendRouted(job, update(job.Durable));
            }
        }
        // Caller holds Gate. Stop persistence uses this after selecting the
        // winning stop under that gate; worker transitions use CommitRouted.
        private void AppendRouted(RoutedJob job, VideoJobRecord next)
        {
            try { _ledger.Append(next); }
            catch
            {
                job.PersistenceFailed = true; job.StopPersistence = VideoStopPersistence.Failed;
                job.Budget.AbortExecution();
                throw new RouteFailure(PersistenceError());
            }
            job.Durable = next; _routeRecordCache[next.JobId] = next;
        }
        private VideoJobRecord UpdateRouted(VideoJobRecord record, Action<JsonObject> update, VideoJobState? state = null, GenerationError? error = null)
        {
            var data = VideoExecutionSnapshot.Read(record).Snapshot?.Data ?? throw new RouteFailure(RoutingError("Invalid video execution evidence."));
            update(data);
            return VideoExecutionSnapshot.Write(record with { State = state ?? record.State, UpdatedAt = _clock.UtcNow(), Error = error ?? record.Error }, new VideoExecutionSnapshot(1, data));
        }
        private static void CheckRouted(RoutedJob job)
        {
            if (job.PersistenceFailed) throw new RouteFailure(PersistenceError());
            if (job.Budget.Remaining <= TimeSpan.Zero) job.Budget.TryStop(VideoStopReason.Deadline);
            if (job.Budget.FirstStopReason != null) throw new OperationCanceledException(job.Budget.Token);
            job.Budget.Token.ThrowIfCancellationRequested();
            if (IsTerminal(job.Durable.State)) throw new OperationCanceledException(job.Budget.Token);
        }
        private async Task<T> AwaitRouted<T>(RoutedJob job, Func<Task<T>> action)
        {
            CheckRouted(job);
            return await AwaitCancellation(Task.Run(() => { CheckRouted(job); return action(); }), job.Budget.Token).ConfigureAwait(false);
        }
        private static async Task<T> AwaitCancellation<T>(Task<T> work, CancellationToken ct)
        {
            var stopped = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using var registration = ct.Register(() => stopped.TrySetResult(true));
            if (await Task.WhenAny(work, stopped.Task).ConfigureAwait(false) != work)
            { _ = work.ContinueWith(t => { _ = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted); throw new OperationCanceledException(ct); }
            ct.ThrowIfCancellationRequested();
            return await work.ConfigureAwait(false);
        }
        private async Task<ProviderSubmitOutcome> SubmitOwnedRoutedAttemptAsync(RoutedJob job, VideoRouteCandidate candidate, VideoPreparedBundleLease pin)
        {
            using (pin)
            {
                VideoPreparationLease phase;
                try { phase = await _routeQuotes!.Preparation.Resources.AcquireAsync(job.Budget.Token).ConfigureAwait(false); }
                catch (VideoPreparationBusyException)
                {
                    // Admission failed locally, before a coordinator call or durable dispatch intent.
                    return new FailedSubmitOutcome(VideoSourcePreparationErrors.Busy("source_framing"));
                }
                using (phase)
                {
                    phase.OwnRetainedMedia(pin.Retain());
                    return await _routeCoordinator!.SubmitAttemptAsync(candidate, pin.Prepared,
                        () => AdmitGenerationDispatch(job, candidate, pin, phase), job.Budget.Token, phase).ConfigureAwait(false);
                }
            }
        }
        private async Task RunRoutedAsync(RoutedJob job)
        {
            bool acquired = false;
            try
            {
                await _concurrency.WaitAsync(job.Budget.Token).ConfigureAwait(false); acquired = true;
                CheckRouted(job);
                PrepareRoutedBinding(job, job.Candidate);
                if (_routeQuotes!.ValidatePreparedMedia(job.Bundle!.Prepared, job.Quote) is { } changed) throw new RouteFailure(changed);
                while (true)
                {
                    var prepared = await AwaitRouted(job, () => _routeQuotes.QuotePreparedAsync(job.Intent, job.Bundle!, job.Budget.Token)).ConfigureAwait(false);
                    if (prepared.Error != null) throw new RouteFailure(prepared.Error);
                    if (_routeQuotes.ValidateConfirmation(prepared.Quote!, job.Confirmation, job.Candidate) is { } stale) throw new RouteFailure(stale);
                    var attemptPin = job.Bundle!.Retain();
                    var attempt = job.Candidate;
                    var submit = Task.Run(() => SubmitOwnedRoutedAttemptAsync(job, attempt, attemptPin));
                    ProviderSubmitOutcome outcome;
                    try { outcome = await AwaitCancellation(submit, job.Budget.Token).ConfigureAwait(false); }
                    catch (OperationCanceledException) { _ = ObserveLateSubmitAsync(job, submit); throw; }
                    if (outcome is QueuedSubmitOutcome accepted)
                    {
                        job.KnownHandle = accepted.Handle;
                        CommitRouted(job, record => {
                            CheckRouted(job);
                            var next = VideoJobRecordFactory.WithState(record, VideoJobState.Polling, _clock.UtcNow(), providerHandle: accepted.Handle);
                            return UpdateRouted(next, data => { LastAttempt(data)["dispatch_state"] = "accepted"; LastAttempt(data)["generation_dispatch_attempted"] = true; data["phase"] = "polling"; });
                        });
                        break;
                    }
                    if (outcome is not FailedSubmitOutcome failure) throw new RouteFailure(VideoCredentialErrors.Unknown());
                    var credential = VideoCredentialErrors.FromError(job.Candidate.Model.ProviderName, failure.Error);
                    var uncertain = failure.Error.ProviderErrorCode == "submission_unknown";
                    CommitRouted(job, record => UpdateRouted(record, data => {
                        if (data["attempts"]!.AsArray().Count > 0) LastAttempt(data)["dispatch_state"] = uncertain ? "unknown" : "rejected";
                        if (credential != null) data["credential_failure"] = VideoCredentialErrors.Project(credential);
                    }));
                    if (uncertain) throw new RouteFailure(failure.Error);
                    var fallback = job.Candidate.Model.ProviderName == "veo" ? _routeCoordinator!.SelectFallback(job.Quote, failure.Error) : null;
                    if (fallback is null) throw new RouteFailure(VideoSubmissionCoordinator.FallbackReason(failure.Error) != null && job.Candidate.Model.ProviderName == "veo" ? job.Quote.Candidates.FirstOrDefault(c => c.Model.ProviderName == "fal")?.EligibilityError ?? failure.Error : failure.Error);
                    PrepareRoutedBinding(job, fallback, VideoSubmissionCoordinator.FallbackReason(failure.Error));
                }
                while (true)
                {
                    var status = await AwaitRouted(job, () => job.Candidate.Model.Provider is VeoProvider googleStatus ? googleStatus.GetStatusSafeAsync(job.KnownHandle!, job.Budget.Token) : GetProviderStatusAsync(job.Candidate.Model, job.KnownHandle!, job.Budget.Token)).ConfigureAwait(false);
                    if (status is FailedStatusOutcome failed) throw new RouteFailure(SafeLifecycleError(job.Candidate.Model.ProviderName, failed.Error, "status"));
                    if (status is ProviderCompleteStatusOutcome complete)
                    {
                        job.KnownHandle = complete.UpdatedHandle;
                        CommitRouted(job, r => { CheckRouted(job); return VideoJobRecordFactory.WithState(r, VideoJobState.Downloading, _clock.UtcNow(), providerHandle: complete.UpdatedHandle); });
                        break;
                    }
                    await Task.Delay(_pollInterval, job.Budget.Token).ConfigureAwait(false);
                }
                var result = await AwaitRouted(job, () => job.Candidate.Model.Provider is VeoProvider googleResult ? googleResult.FetchResultSafeAsync(job.KnownHandle!, job.Budget.Token) : FetchProviderResultAsync(job.Candidate.Model, job.KnownHandle!, job.Budget.Token)).ConfigureAwait(false);
                if (result is FailedResultOutcome resultFailure) throw new RouteFailure(SafeLifecycleError(job.Candidate.Model.ProviderName, resultFailure.Error, "result"));
                if (result is not SuccessResultOutcome success || success.Envelope.Artifacts.Count != 1 || success.Envelope.Artifacts[0].Role != "video") throw new RouteFailure(RoutingError("Provider did not return one video."));
                await PublishRoutedResultAsync(job, success.Envelope.Artifacts[0]).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                await PersistRoutedFailureAsync(job, VideoJobState.Error, new GenerationError(GenerationErrorCode.DependencyUnavailable, "Video provider operation stopped before completion.", false, null, "provider_timeout")).ConfigureAwait(false);
            }
            catch (RouteFailure failure)
            {
                await PersistRoutedFailureAsync(job, failure.Error.Code == GenerationErrorCode.Interrupted ? VideoJobState.Interrupted : VideoJobState.Error, failure.Error).ConfigureAwait(false);
            }
            catch
            {
                await PersistRoutedFailureAsync(job, job.KnownHandle == null ? VideoJobState.Interrupted : VideoJobState.Error,
                    job.KnownHandle == null ? VideoCredentialErrors.Unknown() : new GenerationError(GenerationErrorCode.ExecutionFailed, "The accepted video job could not produce a valid local video.", false)).ConfigureAwait(false);
            }
            finally
            {
                job.Bundle?.Dispose(); job.Bundle = null;
                if (job.KnownHandle != null && (job.PersistenceFailed || job.Budget.FirstStopReason != null)) await CleanupRoutedHandleAsync(job, job.KnownHandle).ConfigureAwait(false);
                job.Finished.TrySetResult(true);
                job.Budget.Dispose();
                if (acquired) try { _concurrency.Release(); } catch (ObjectDisposedException) { }
                AfterRunForTests?.Invoke(job.Durable.JobId);
            }
        }
        private async Task PersistRoutedFailureAsync(RoutedJob job, VideoJobState state, GenerationError error)
        {
            var preparationError = VideoSourcePreparationErrors.Project(error);
            var persistedError = preparationError == null ? error : error with { ProviderDetail = null };
            try
            {
                CommitRouted(job, record => UpdateRouted(record, data => {
                    data["phase"] = "failed";
                    if (VideoCredentialErrors.FromError(record.Provider, error) is { } credential) data["credential_failure"] = VideoCredentialErrors.Project(credential);
                    if (preparationError != null) data["source_preparation_error"] = preparationError.DeepClone();
                }, state, persistedError));
            }
            catch (OperationCanceledException)
            {
                if (job.Budget.FirstStopReason != null) await PersistObservedStopAsync(job).ConfigureAwait(false);
            }
            catch (RouteFailure) { /* Persistence failure already stopped execution. */ }
        }
        private static GenerationError SafeLifecycleError(string provider, GenerationError error, string phase)
        {
            if (error.ProviderErrorCode == "provider_timeout") return new GenerationError(GenerationErrorCode.DependencyUnavailable, "Video provider " + phase + " request timed out.", error.Retryable, null, "provider_timeout");
            if (VideoCredentialErrors.FromError(provider, error) is { } credential)
                return credential.Kind == "missing" ? VideoCredentialErrors.Missing(provider) : new GenerationError(GenerationErrorCode.DependencyUnavailable, "Video provider rejected its API credential.", false, "credentials", error.ProviderErrorCode);
            return new GenerationError(error.Code, "Video provider " + phase + " request failed.", error.Retryable);
        }
        private void PrepareRoutedBinding(RoutedJob job, VideoRouteCandidate candidate, string? fallbackReason = null)
        {
            CommitRouted(job, record => {
                CheckRouted(job);
                job.Candidate = candidate;
                var next = record with { Provider = candidate.Model.ProviderName, Model = candidate.Model.ModelId, ProviderOptions = candidate.Model.OptionsCodec.Serialize(candidate.Request.Options), Pricing = candidate.Estimate!.Pricing };
                if (fallbackReason != null || candidate.Model.ProviderName == "fal" && VideoSubmissionCoordinator.IsGoogleModel(job.Intent.Request.Model))
                {
                    var extensions = (JsonObject?)next.Extensions?.DeepClone() ?? new JsonObject();
                    extensions["video_route"] = new JsonObject { ["version"] = 1, ["requested_provider"] = "veo", ["requested_model"] = job.Intent.Request.Model, ["effective_provider"] = "fal", ["effective_model"] = candidate.Model.ModelId, ["provider_endpoint"] = candidate.Binding?.SubmitEndpoint, ["fallback_reason"] = fallbackReason ?? "gemini_key_missing" };
                    next = next with { Extensions = extensions };
                }
                return UpdateRouted(next, data => { data["phase"] = "preparation"; data["effective_binding"] = candidate.Binding?.SubmitEndpoint; data["profile_revision"] = candidate.Binding?.ProfileRevision; data["effective_provider"] = candidate.Model.ProviderName; data["effective_model"] = candidate.Model.ModelId; data["effective_options"] = candidate.Model.OptionsCodec.Serialize(candidate.Request.Options); data["effective_pricing"] = new JsonObject { ["estimated_cost_usd"] = candidate.Estimate!.DollarsUsd, ["currency"] = candidate.Estimate.Pricing.Currency, ["source"] = candidate.Estimate.Pricing.PricingSource }; data["route_receipt"] = next.Extensions?["video_route"]?.DeepClone(); }, VideoJobState.Submitting);
            });
        }
        private void AdmitGenerationDispatch(RoutedJob job, VideoRouteCandidate candidate, VideoPreparedBundleLease held, VideoPreparationLease phase)
        {
            CheckRouted(job);
            var current = _routeQuotes!.RevalidateForDispatchAsync(job.Intent, held, job.Quote, job.Confirmation, candidate, phase, job.Budget.Token).GetAwaiter().GetResult();
            if (current.Error != null) throw new RouteFailure(current.Error);
            var preparedMedia = held.Prepared;
            var fresh = current.Quote!.Candidates.First(c => c.Model.ProviderName == candidate.Model.ProviderName && c.Model.ModelId == candidate.Model.ModelId && c.Binding?.SubmitEndpoint == candidate.Binding?.SubmitEndpoint);
            CommitRouted(job, record => {
                CheckRouted(job);
                record = record with { Pricing = fresh.Estimate!.Pricing };
                if (candidate.Binding != null && _routeCoordinator!.Bindings.Resolve(candidate.Request, _clock.UtcNow()).Error is { } unavailable) throw new RouteFailure(unavailable);
                return UpdateRouted(record, data => { data["phase"] = "submission"; data["effective_pricing"] = new JsonObject { ["estimated_cost_usd"] = fresh.Estimate!.DollarsUsd, ["currency"] = fresh.Estimate.Pricing.Currency, ["source"] = fresh.Estimate.Pricing.PricingSource }; data["prepared_media"] = VideoRouteQuoteService.ProjectMedia(preparedMedia); data["attempts"]!.AsArray().Add(new JsonObject { ["provider"] = candidate.Model.ProviderName, ["model"] = candidate.Model.ModelId, ["endpoint"] = candidate.Binding?.SubmitEndpoint, ["dispatch_state"] = "intent_recorded", ["generation_dispatch_attempted"] = false }); });
            });
            CheckRouted(job);
        }
        private static JsonObject LastAttempt(JsonObject data) => data["attempts"]!.AsArray().Last()!.AsObject();
        private void ObserveStop(RoutedJob job, VideoStopReason reason) { job.Budget.TryStop(reason); }
        private Task<JobCancelResult> PersistObservedStopAsync(RoutedJob job) => Task.Run(() => {
            try
            {
                lock (job.Gate)
                {
                    if (job.Durable.State == VideoJobState.Complete || job.Budget.FirstStopReason == null) return JobCancelResult.Ok(job.Durable.State) with { Execution = RouteProjection(job.Durable) };
                    if (IsTerminal(job.Durable.State) && VideoExecutionSnapshot.Read(job.Durable).Snapshot?.Data["first_stop_reason"] != null) { job.StopPersistence = VideoStopPersistence.Durable; return JobCancelResult.Ok(job.Durable.State) with { Execution = RouteProjection(job.Durable) }; }
                    var reason = job.Budget.FirstStopReason.Value;
                    var data = VideoExecutionSnapshot.Read(job.Durable).Snapshot!.Data;
                    var hasIntent = data["attempts"]!.AsArray().Any(a => a?["dispatch_state"]?.GetValue<string>() is "intent_recorded" or "unknown" or "accepted");
                    var terminal = reason == VideoStopReason.User && (!hasIntent || job.KnownHandle != null) ? VideoJobState.Cancelled : VideoJobState.Interrupted;
                    var error = hasIntent && job.KnownHandle == null ? VideoCredentialErrors.Unknown() : new GenerationError(terminal == VideoJobState.Cancelled ? GenerationErrorCode.Cancelled : GenerationErrorCode.Interrupted, reason == VideoStopReason.User ? "Local video execution cancelled; remote work may continue." : "Local video execution stopped: " + reason.ToString().ToLowerInvariant() + ".", false);
                    AppendRouted(job, UpdateRouted(job.Durable, d => { d["first_stop_reason"] = reason.ToString().ToLowerInvariant(); d["stop_persistence"] = "durable"; d["phase"] = "interruption"; d["cleanup"] = job.KnownHandle != null ? "unknown" : hasIntent ? "unknown" : "not_dispatched"; }, terminal, error));
                    job.PersistenceFailed = false; job.StopPersistence = VideoStopPersistence.Durable;
                    return JobCancelResult.Ok(job.Durable.State) with { Execution = RouteProjection(job.Durable) };
                }
            }
            catch { job.PersistenceFailed = true; job.StopPersistence = VideoStopPersistence.Failed; return JobCancelResult.Fail(VideoProviderOutcomeAdapters.ToVideoJobError(PersistenceError())) with { Execution = RouteProjection(job.Durable) }; }
        });
        private async Task<JobCancelResult> CancelRoutedAsync(VideoJobRecord record, CancellationToken ct)
        {
            if (_routedJobs.TryGetValue(record.JobId, out var job))
            {
                if (record.State == VideoJobState.Complete) return JobCancelResult.Ok(record.State) with { Execution = RouteProjection(record) };
                if (job.PersistenceFailed && job.Budget.FirstStopReason == null) return JobCancelResult.Fail(VideoProviderOutcomeAdapters.ToVideoJobError(PersistenceError())) with { Execution = RouteProjection(record) };
                ObserveStop(job, VideoStopReason.User);
                if (job.Budget.FirstStopReason == null) { await AwaitCancellation(job.Finished.Task, ct).ConfigureAwait(false); return JobCancelResult.Ok(job.Durable.State) with { Execution = RouteProjection(job.Durable) }; }
                var result = await AwaitCancellation(PersistObservedStopAsync(job), ct).ConfigureAwait(false);
                if (job.KnownHandle != null) _ = Task.Run(() => CleanupRoutedHandleAsync(job, job.KnownHandle));
                return result;
            }
            if (VideoExecutionSnapshot.Read(record).Error is { } invalid) return JobCancelResult.Fail(VideoProviderOutcomeAdapters.ToVideoJobError(invalid));
            if (record.State != VideoJobState.Complete && record.ProviderHandle is { } handle && _registry.TryResolve(record.Model, out var model))
            {
                using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(30));
                var outcome = await AwaitCancellation(model.Provider is IModelAwareVideoProvider aware ? aware.CancelAsync(record.Model, handle, cleanup.Token) : model.Provider.CancelAsync(handle, cleanup.Token), cleanup.Token).ConfigureAwait(false);
                record = UpdateRouted(record, data => data["cleanup"] = FalVeoQueueAdapter.CleanupOutcome(outcome));
                try { _ledger.Append(record); _routeRecordCache[record.JobId] = record; } catch { return JobCancelResult.Fail(VideoProviderOutcomeAdapters.ToVideoJobError(PersistenceError())); }
            }
            return JobCancelResult.Ok(record.State) with { Execution = RouteProjection(record) };
        }
        private async Task ObserveLateSubmitAsync(RoutedJob job, Task<ProviderSubmitOutcome> submission)
        {
            try
            {
                if (await submission.ConfigureAwait(false) is not QueuedSubmitOutcome accepted) return;
                job.KnownHandle = accepted.Handle;
                var cleanup = Task.Run(() => CleanupRoutedHandleAsync(job, accepted.Handle));
                _ = Task.Run(() => CommitRoutedMetadata(job, record => VideoJobRecordFactory.WithState(record, record.State, _clock.UtcNow(), providerHandle: accepted.Handle)));
                await cleanup.ConfigureAwait(false);
            }
            catch { /* Original interruption remains authoritative. */ }
        }
        private async Task CleanupRoutedHandleAsync(RoutedJob job, ProviderJobHandle handle)
        {
            if (Interlocked.CompareExchange(ref job.CleanupRunning, 1, 0) != 0) return;
            string outcome = "unknown";
            try
            {
                using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(30));
                var provider = job.Candidate.Model.Provider;
                var result = await AwaitCancellation(Task.Run(() => provider is IModelAwareVideoProvider aware ? aware.CancelAsync(job.Candidate.Model.ModelId, handle, cleanup.Token) : provider.CancelAsync(handle, cleanup.Token)), cleanup.Token).ConfigureAwait(false);
                outcome = FalVeoQueueAdapter.CleanupOutcome(result);
            }
            catch { outcome = "failed"; }
            job.CleanupOutcome = outcome; job.CleanupPersistence = "pending";
            _ = Task.Run(() => CommitRoutedMetadata(job, r => VideoJobRecordFactory.WithState(UpdateRouted(r, data => data["cleanup"] = outcome), r.State, _clock.UtcNow(), providerHandle: handle)));
            Interlocked.Exchange(ref job.CleanupRunning, 0);
        }
        private void CommitRoutedMetadata(RoutedJob job, Func<VideoJobRecord, VideoJobRecord> update, bool cleanupMetadata = true)
        {
            lock (job.Gate)
            {
                try { var next = update(job.Durable); _ledger.Append(next); job.Durable = next; _routeRecordCache[next.JobId] = next; if (cleanupMetadata) job.CleanupPersistence = "durable"; }
                catch { if (cleanupMetadata) job.CleanupPersistence = "failed"; }
            }
        }
        private async Task PublishRoutedResultAsync(RoutedJob job, ResultArtifact result)
        {
            Artifact? artifact = null;
            try
            {
                CheckRouted(job);
                var preparation = Task.Run(() => _publication.PrepareAsync(job.Durable.JobId, result, VideoExecutionSnapshot.Read(job.Durable).Snapshot!, job.Budget.Token));
                try { artifact = await AwaitCancellation(preparation, job.Budget.Token).ConfigureAwait(false); }
                catch { _ = preparation.ContinueWith(t => { if (t.Status == TaskStatus.RanToCompletion) _publication.RemoveOwnedProvisional(t.Result, job.Durable); else _ = t.Exception; }); throw; }
                var warnings = new JsonArray();
                try { if (!(await AwaitRouted(job, () => _posterProducer.TryPublishPosterAsync(artifact.Id, job.Budget.Token)).ConfigureAwait(false)).Success) warnings.Add("poster_unavailable"); } catch (OperationCanceledException) when (job.Budget.Token.IsCancellationRequested) { throw; } catch { warnings.Add("poster_unavailable"); }
                try { if ((await AwaitRouted(job, () => _frameProducer.TryPublishFrameSidecarsAsync(artifact.Id, job.Budget.Token)).ConfigureAwait(false)).RoleResults.Any(r => !r.Success)) warnings.Add("frames_unavailable"); } catch (OperationCanceledException) when (job.Budget.Token.IsCancellationRequested) { throw; } catch { warnings.Add("frames_unavailable"); }
                CommitRouted(job, r => {
                    CheckRouted(job);
                    if (!job.Budget.TryAdmitCompletion()) throw new OperationCanceledException(job.Budget.Token);
                    job.CompletionCommitAttempted = true;
                    return UpdateRouted(r with { ResultArtifactId = artifact.Id, Error = null }, data => { data["phase"] = "complete"; data["warnings"] = warnings.DeepClone(); }, VideoJobState.Complete);
                });
                var finalize = Task.Run(() => _publication.FinalizeMarker(artifact));
                var remaining = job.Budget.Remaining;
                var warning = remaining <= TimeSpan.Zero || await Task.WhenAny(finalize, Task.Delay(remaining)).ConfigureAwait(false) != finalize ? true : await finalize.ConfigureAwait(false) != null;
                if (warning)
                {
                    job.PublicationWarning = "artifact_marker_pending";
                    _ = Task.Run(() => CommitRoutedMetadata(job, r => UpdateRouted(r, data => data["warnings"] = new JsonArray("artifact_marker_pending")), cleanupMetadata: false));
                }
            }
            catch
            {
                if (artifact != null && !(job.Durable.State == VideoJobState.Complete && job.Durable.ResultArtifactId == artifact.Id))
                {
                    if (job.CompletionCommitAttempted && job.PersistenceFailed)
                    {
                        // A failed write may have reached disk. Verify before deleting; unknown IO quarantines.
                        var owned = artifact;
                        _ = Task.Run(() => { try { var durable = _ledger.ReadAll().Records.FirstOrDefault(r => r.JobId == job.Durable.JobId); if (durable != null) _publication.RemoveOwnedProvisional(owned, durable); } catch { } finally { AfterRollbackForTests?.Invoke(job.Durable.JobId); } });
                    }
                    else try { _publication.RemoveOwnedProvisional(artifact, job.Durable); } catch { }
                }
                throw;
            }
        }
        private bool TryGetRoutedRecord(Guid id, out VideoJobRecord? record)
        {
            if (_routedJobs.TryGetValue(id, out var job)) { record = job.Durable; return true; }
            if (_routeRecordCache.TryGetValue(id, out record) && record.Extensions?.ContainsKey("video_execution") == true) return true;
            record = null; return false;
        }
        private VideoExecutionProjection RouteProjection(VideoJobRecord record)
        {
            if (_routedJobs.TryGetValue(record.JobId, out var job))
            {
                var fields = VideoExecutionSnapshot.Project(record, job.Budget.FirstStopReason, job.StopPersistence).Fields;
                if (job.CleanupOutcome != null) fields["cleanup"] = job.CleanupOutcome;
                if (job.CleanupPersistence != null) fields["cleanup_persistence"] = job.CleanupPersistence;
                if (job.PublicationWarning != null) fields["warnings"] = new JsonArray(job.PublicationWarning);
                AddMarkerWarning(record, fields);
                return new VideoExecutionProjection(fields);
            }
            var projection = VideoExecutionSnapshot.Project(record, null, VideoStopPersistence.None).Fields;
            AddMarkerWarning(record, projection);
            return new VideoExecutionProjection(projection);
        }
        private void AddMarkerWarning(VideoJobRecord record, JsonObject fields)
        {
            if (record.State != VideoJobState.Complete || record.ResultArtifactId is not { } id) return;
            try { if (_artifactStore.Get(id) is { } artifact && VideoPublicationService.MarkerPending(artifact)) fields["warnings"] = new JsonArray("artifact_marker_pending"); } catch { }
        }
        internal bool IsArtifactVisible(Artifact artifact)
        {
            if (!VideoPublicationService.IsAffectedArtifact(artifact)) return true;
            if (!artifact.Metadata.TryGetValue("video_job_id", out var owner) || owner is not JsonValue value || !value.TryGetValue<string>(out var text) || !Guid.TryParse(text, out var jobId)) return false;
            return _publication.IsVisible(artifact, _routeRecordCache.TryGetValue(jobId, out var record) ? record : null);
        }
        private void RepairRoutedArtifacts()
        {
            foreach (var artifact in _artifactStore.List())
            {
                if (!VideoPublicationService.IsAffectedArtifact(artifact)) continue;
                VideoJobRecord? record = null;
                if (artifact.Metadata.TryGetValue("video_job_id", out var owner) && owner is JsonValue value && value.TryGetValue<string>(out var text) && Guid.TryParse(text, out var id)) _routeRecordCache.TryGetValue(id, out record);
                var warning = _publication.RepairFromLedger(artifact, record);
                if (warning != null) System.Diagnostics.Trace.WriteLine("Rook video artifact " + artifact.Id.ToString("D") + ": " + warning.ProviderErrorCode);
            }
        }
        private JobStatusResult RoutedStatus(VideoJobRecord record) => TranslateToStatus(record) with { Execution = RouteProjection(record) };
        private JobFetchResult FetchRouted(VideoJobRecord record)
        {
            var projection = RouteProjection(record);
            if (record.State != VideoJobState.Complete || record.ResultArtifactId is not { } id) return JobFetchResult.Failed(record.State, VideoProviderOutcomeAdapters.ToVideoJobError(record.Error ?? RoutingError("Video job has no completed result."))) with { Execution = projection };
            var artifact = _artifactStore.Get(id);
            if (artifact == null || !IsArtifactVisible(artifact)) return JobFetchResult.Failed(VideoJobState.Error, VideoProviderOutcomeAdapters.ToVideoJobError(RoutingError("Completed video artifact is unavailable."))) with { Execution = projection };
            return JobFetchResult.Complete(id, artifact.Files.Select(f => new JobResultFile(f.Role, f.Path)).ToArray()) with { Execution = projection };
        }
        private VideoJobLedgerReadResult ReadConsumerLedger() => _routeCoordinator is null ? _ledger.ReadAll() : new VideoJobLedgerReadResult(_routeRecordCache.Values.ToArray(), _routeReadErrors);
        private void AppendCommittedSnapshot(VideoJobRecord record) { _ledger.Append(record); _routeRecordCache[record.JobId] = record; }
        private void ReconcileRoutedRecord(VideoJobRecord record)
        {
            if (IsTerminal(record.State)) return;
            var read = VideoExecutionSnapshot.Read(record);
            var uncertain = read.Snapshot?.Data["attempts"]?.AsArray().Any(a => a?["dispatch_state"]?.GetValue<string>() is "intent_recorded" or "unknown") == true;
            var interrupted = record with { State = VideoJobState.Interrupted, UpdatedAt = _clock.UtcNow(), Error = read.Error ?? (uncertain ? VideoCredentialErrors.Unknown() : new GenerationError(GenerationErrorCode.Interrupted, "Video interrupted by restart; no provider work was resumed.", false)) };
            if (read.Snapshot != null) interrupted = UpdateRouted(interrupted, data => { data["phase"] = "interruption"; data["reconciliation"] = "restart"; });
            AppendCommittedSnapshot(interrupted);
        }
        private static GenerationError PersistenceError() => new(GenerationErrorCode.DependencyUnavailable, "Video execution stopped because its durable transition could not be confirmed.", false, null, "persistence_failed");
        private static GenerationError RoutingError(string message) => new(GenerationErrorCode.ExecutionFailed, message, false);
    }
}
