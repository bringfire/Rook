using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal static class VideoProviderOutcomeAdapters
    {
        public static MediaRef ToGenerationMediaRef(VideoMediaRef mediaRef)
        {
            if (mediaRef is null) throw new ArgumentNullException(nameof(mediaRef));

            return mediaRef.Kind switch
            {
                VideoMediaRefKind.Artifact => MediaRef.ForArtifact(
                    mediaRef.ArtifactId ?? Guid.Empty,
                    mediaRef.Role),
                VideoMediaRefKind.Path => MediaRef.ForPath(
                    mediaRef.Path ?? string.Empty,
                    mediaRef.Role),
                _ => throw new ArgumentOutOfRangeException(
                    nameof(mediaRef), mediaRef.Kind, "Unknown video media ref kind."),
            };
        }

        public static VideoMediaRef ToVideoMediaRef(MediaRef mediaRef)
        {
            if (mediaRef is null) throw new ArgumentNullException(nameof(mediaRef));

            return mediaRef.Kind switch
            {
                MediaRefKind.Artifact => VideoMediaRef.ForArtifact(
                    mediaRef.ArtifactId ?? Guid.Empty,
                    mediaRef.Role),
                MediaRefKind.Path => VideoMediaRef.ForPath(
                    mediaRef.Path ?? string.Empty,
                    mediaRef.Role),
                _ => throw new ArgumentOutOfRangeException(
                    nameof(mediaRef), mediaRef.Kind, "Unknown generation media ref kind."),
            };
        }

        public static IReadOnlyDictionary<MediaRef, ResolvedMedia> ToGenerationMedia(
            IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia>? media)
        {
            if (media is null || media.Count == 0)
                return new Dictionary<MediaRef, ResolvedMedia>();

            var converted = new Dictionary<MediaRef, ResolvedMedia>(media.Count);
            foreach (var kvp in media)
            {
                converted[ToGenerationMediaRef(kvp.Key)] =
                    new ResolvedMedia(kvp.Value.Bytes, kvp.Value.MimeType);
            }

            return converted;
        }

        public static IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> ToVideoMedia(
            IReadOnlyDictionary<MediaRef, ResolvedMedia>? media)
        {
            if (media is null || media.Count == 0)
                return new Dictionary<VideoMediaRef, ResolvedVideoMedia>();

            var converted = new Dictionary<VideoMediaRef, ResolvedVideoMedia>(media.Count);
            foreach (var kvp in media)
            {
                var videoRef = ToVideoMediaRef(kvp.Key);
                converted[videoRef] = new ResolvedVideoMedia(
                    kvp.Value.Bytes,
                    kvp.Value.MimeType,
                    SourceDescription(videoRef));
            }

            return converted;
        }

        public static GenerationError ToGenerationError(VideoJobError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));

            var providerDetail = string.IsNullOrEmpty(error.ProviderMessage)
                ? null
                : new Dictionary<string, JsonNode>
                {
                    [VideoErrorDetailKeys.ProviderMessage] =
                        JsonValue.Create(error.ProviderMessage)!,
                };

            return new GenerationError(
                ToGenerationErrorCode(error.Code),
                error.Message,
                error.Retryable,
                error.Field,
                ProviderErrorCode: null,
                ProviderDetail: providerDetail);
        }

        public static VideoJobError ToVideoJobError(GenerationError error)
        {
            if (error is null) throw new ArgumentNullException(nameof(error));

            var providerMessage = TryGetProviderMessage(error.ProviderDetail);
            return new VideoJobError(
                Code: ToVideoErrorCode(error.Code),
                Message: error.Message,
                Retryable: error.Retryable,
                ProviderMessage: providerMessage,
                Field: error.Field);
        }

        public static ProviderSubmitResult ToProviderSubmitResult(
            ProviderSubmitOutcome outcome)
        {
            return outcome switch
            {
                QueuedSubmitOutcome queued =>
                    ProviderSubmitResult.Ok(queued.Handle.ProviderJobId),
                FailedSubmitOutcome failed =>
                    ProviderSubmitResult.Fail(ToVideoJobError(failed.Error)),
                SyncSubmitOutcome =>
                    ProviderSubmitResult.Fail(new VideoJobError(
                        VideoErrorCode.ExecutionFailed,
                        "Synchronous video submit outcomes are not supported by the V1c manager adapter.",
                        Retryable: false)),
                _ => ProviderSubmitResult.Fail(new VideoJobError(
                    VideoErrorCode.ExecutionFailed,
                    $"Unknown provider submit outcome: {outcome.GetType().Name}.",
                    Retryable: false)),
            };
        }

        public static ProviderSubmitOutcome ToProviderSubmitOutcome(
            ProviderSubmitResult result)
        {
            if (result.Error is not null)
                return new FailedSubmitOutcome(ToGenerationError(result.Error));

            return new QueuedSubmitOutcome(
                new ProviderJobHandle(result.ProviderJobId!));
        }

        public static ProviderStatusResult ToProviderStatusResult(
            ProviderStatusOutcome outcome)
        {
            return outcome switch
            {
                InFlightStatusOutcome inFlight => ProviderStatusResult.InFlight(
                    ToVideoInFlightState(inFlight.State),
                    ToVideoProgress(inFlight.Progress)),
                ProviderCompleteStatusOutcome complete
                    when !string.IsNullOrEmpty(complete.UpdatedHandle.ProviderResultToken) =>
                    ProviderStatusResult.Complete(complete.UpdatedHandle.ProviderResultToken!),
                ProviderCompleteStatusOutcome =>
                    ProviderStatusResult.Failed(
                        VideoJobState.Error,
                        new VideoJobError(
                            VideoErrorCode.ExecutionFailed,
                            "Provider completed without a result token.",
                            Retryable: false)),
                FailedStatusOutcome failed =>
                    ProviderStatusResult.Failed(
                        VideoJobState.Error,
                        ToVideoJobError(failed.Error)),
                _ => ProviderStatusResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        VideoErrorCode.ExecutionFailed,
                        $"Unknown provider status outcome: {outcome.GetType().Name}.",
                        Retryable: false)),
            };
        }

        public static ProviderCancelResult ToProviderCancelResult(
            ProviderCancelOutcome outcome)
        {
            return outcome switch
            {
                CanceledOutcome =>
                    ProviderCancelResult.Ok(VideoJobState.Cancelled),
                AlreadyTerminalOutcome terminal =>
                    ProviderCancelResult.Ok(ToVideoTerminalState(terminal.TerminalState)),
                FailedCancelOutcome failed =>
                    ProviderCancelResult.Fail(ToVideoJobError(failed.Error)),
                _ => ProviderCancelResult.Fail(new VideoJobError(
                    VideoErrorCode.ExecutionFailed,
                    $"Unknown provider cancel outcome: {outcome.GetType().Name}.",
                    Retryable: false)),
            };
        }

        public static ProviderCancelOutcome ToProviderCancelOutcome(
            ProviderCancelResult result)
        {
            if (result.Error is not null)
                return new FailedCancelOutcome(ToGenerationError(result.Error));

            return result.State switch
            {
                VideoJobState.Complete =>
                    new AlreadyTerminalOutcome(GenerationLifecycleState.Completed),
                VideoJobState.Error =>
                    new AlreadyTerminalOutcome(GenerationLifecycleState.Failed),
                VideoJobState.Cancelled => new CanceledOutcome(),
                _ => new CanceledOutcome(),
            };
        }

        public static ProviderFetchResult ToProviderFetchResult(
            ProviderResultOutcome outcome)
        {
            switch (outcome)
            {
                case FailedResultOutcome failed:
                    return ProviderFetchResult.Fail(ToVideoJobError(failed.Error));

                case SuccessResultOutcome success:
                    foreach (var artifact in success.Envelope.Artifacts)
                    {
                        if (artifact.Role == VideoMediaRoles.Video
                            && artifact.Body is InlineArtifactBody inline
                            && !string.IsNullOrWhiteSpace(artifact.DeclaredMimeType))
                        {
                            return ProviderFetchResult.Ok(
                                inline.Bytes,
                                artifact.DeclaredMimeType!);
                        }
                    }

                    return ProviderFetchResult.Fail(new VideoJobError(
                        VideoErrorCode.ExecutionFailed,
                        "Provider result envelope did not contain an inline video artifact.",
                        Retryable: false));

                default:
                    return ProviderFetchResult.Fail(new VideoJobError(
                        VideoErrorCode.ExecutionFailed,
                        $"Unknown provider result outcome: {outcome.GetType().Name}.",
                        Retryable: false));
            }
        }

        private static string SourceDescription(VideoMediaRef mediaRef)
        {
            return mediaRef.Kind switch
            {
                VideoMediaRefKind.Artifact =>
                    $"artifact:{mediaRef.ArtifactId} role:{mediaRef.Role}",
                VideoMediaRefKind.Path =>
                    $"path:{mediaRef.Path} role:{mediaRef.Role}",
                _ => $"unknown:{mediaRef.Role}",
            };
        }

        private static GenerationErrorCode ToGenerationErrorCode(VideoErrorCode code) =>
            code switch
            {
                VideoErrorCode.InvalidRequest => GenerationErrorCode.InvalidRequest,
                VideoErrorCode.UnsupportedMedia => GenerationErrorCode.UnsupportedMedia,
                VideoErrorCode.DependencyUnavailable => GenerationErrorCode.DependencyUnavailable,
                VideoErrorCode.ExecutionFailed => GenerationErrorCode.ExecutionFailed,
                VideoErrorCode.Cancelled => GenerationErrorCode.Cancelled,
                VideoErrorCode.Interrupted => GenerationErrorCode.Interrupted,
                _ => GenerationErrorCode.ExecutionFailed,
            };

        private static VideoErrorCode ToVideoErrorCode(GenerationErrorCode code) =>
            code switch
            {
                GenerationErrorCode.InvalidRequest => VideoErrorCode.InvalidRequest,
                GenerationErrorCode.UnsupportedMedia => VideoErrorCode.UnsupportedMedia,
                GenerationErrorCode.DependencyUnavailable => VideoErrorCode.DependencyUnavailable,
                GenerationErrorCode.ExecutionFailed => VideoErrorCode.ExecutionFailed,
                GenerationErrorCode.Cancelled => VideoErrorCode.Cancelled,
                GenerationErrorCode.Interrupted => VideoErrorCode.Interrupted,
                GenerationErrorCode.QuotaExceeded => VideoErrorCode.DependencyUnavailable,
                GenerationErrorCode.ContentPolicy => VideoErrorCode.ExecutionFailed,
                _ => VideoErrorCode.ExecutionFailed,
            };

        private static VideoJobState ToVideoInFlightState(GenerationLifecycleState state) =>
            state switch
            {
                GenerationLifecycleState.Pending => VideoJobState.Polling,
                GenerationLifecycleState.Running => VideoJobState.Polling,
                _ => VideoJobState.Polling,
            };

        private static VideoJobState ToVideoTerminalState(GenerationLifecycleState state) =>
            state switch
            {
                GenerationLifecycleState.Completed => VideoJobState.Complete,
                GenerationLifecycleState.Canceled => VideoJobState.Cancelled,
                GenerationLifecycleState.Failed => VideoJobState.Error,
                _ => VideoJobState.Error,
            };

        private static VideoJobProgress? ToVideoProgress(GenerationProgress? progress)
        {
            if (progress is null) return null;

            return new VideoJobProgress(
                Pct: progress.PercentComplete is null
                    ? null
                    : (int?)Math.Round(progress.PercentComplete.Value),
                Stage: progress.QueuePosition is null
                    ? "polling"
                    : $"queue:{progress.QueuePosition.Value}",
                Message: progress.Message);
        }

        private static string? TryGetProviderMessage(
            IReadOnlyDictionary<string, JsonNode>? detail)
        {
            if (detail is null) return null;
            return detail.TryGetValue(VideoErrorDetailKeys.ProviderMessage, out var node)
                ? node?.GetValue<string>()
                : null;
        }
    }

    internal static class VideoProviderV1cCompatibilityExtensions
    {
        public static async Task<ProviderSubmitResult> SubmitAsync(
            this IVideoProvider provider,
            VideoGenerationRequest request,
            IReadOnlyDictionary<VideoMediaRef, ResolvedVideoMedia> resolvedMedia,
            CancellationToken ct)
        {
            var outcome = await provider.SubmitAsync(
                request,
                VideoProviderOutcomeAdapters.ToGenerationMedia(resolvedMedia),
                ct).ConfigureAwait(false);
            return VideoProviderOutcomeAdapters.ToProviderSubmitResult(outcome);
        }

        public static async Task<ProviderStatusResult> GetStatusAsync(
            this IVideoProvider provider,
            string providerJobId,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                return ProviderStatusResult.Failed(
                    VideoJobState.Error,
                    new VideoJobError(
                        VideoErrorCode.InvalidRequest,
                        "ProviderJobId must be non-empty.",
                        Retryable: false,
                        Field: nameof(providerJobId)));

            var outcome = await provider.GetStatusAsync(
                new ProviderJobHandle(providerJobId),
                ct).ConfigureAwait(false);
            return VideoProviderOutcomeAdapters.ToProviderStatusResult(outcome);
        }

        public static async Task<ProviderCancelResult> CancelAsync(
            this IVideoProvider provider,
            string providerJobId,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                return ProviderCancelResult.Fail(new VideoJobError(
                    VideoErrorCode.InvalidRequest,
                    "ProviderJobId must be non-empty.",
                    Retryable: false,
                    Field: nameof(providerJobId)));

            var outcome = await provider.CancelAsync(
                new ProviderJobHandle(providerJobId),
                ct).ConfigureAwait(false);
            return VideoProviderOutcomeAdapters.ToProviderCancelResult(outcome);
        }

        public static async Task<ProviderFetchResult> FetchResultAsync(
            this IVideoProvider provider,
            string providerJobId,
            string? providerResultToken,
            CancellationToken ct)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                return ProviderFetchResult.Fail(new VideoJobError(
                    VideoErrorCode.InvalidRequest,
                    "ProviderJobId must be non-empty.",
                    Retryable: false,
                    Field: nameof(providerJobId)));

            var outcome = await provider.FetchResultAsync(
                new ProviderJobHandle(
                    providerJobId,
                    providerResultToken: providerResultToken),
                ct).ConfigureAwait(false);
            return VideoProviderOutcomeAdapters.ToProviderFetchResult(outcome);
        }
    }
}
