using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Fal;

namespace Rook.Services.Vision.Image
{
    public sealed record ImageSubmissionResult(ProviderSubmitOutcome Outcome, ImageExecutionSnapshot Execution);

    public sealed class ImageSubmissionExecutor
    {
        private readonly IImageProviderRegistry _registry;
        public ImageSubmissionExecutor(IImageProviderRegistry registry) =>
            _registry = registry ?? throw new ArgumentNullException(nameof(registry));
        public static bool UsesExecutionDeadline(ResolvedImageModel model) =>
            ImageRoutingCodec.IsAffected(model.ProviderName, model.ModelId);
        public async Task<ImageSubmissionResult> SubmitAsync(ImageGenerationRequest request, ResolvedImageModel model,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> media, ImageExecutionContext context, CancellationToken ct,
            Func<ImageExecutionSnapshot, CancellationToken, Task<GenerationError?>>? prepareEffectiveRouteAsync = null,
            Func<ImageExecutionContext, CancellationToken, Task<GenerationError?>>? prepareGenerationDispatchAsync = null)
        {
            context.Initialize(request, model);
            ImageSubmissionResult Result(ProviderSubmitOutcome outcome) => new(outcome, context.Snapshot());
            ProviderSubmitOutcome Fail(string message, GenerationErrorCode code = GenerationErrorCode.ExecutionFailed, string? field = null) =>
                new FailedSubmitOutcome(new(code, message, false, field));
            try
            {
                ct.ThrowIfCancellationRequested();
                var validation = model.OptionsCodec.Validate(request, request.Options, model.Capability);
                if (!validation.Success) return Result(Fail(validation.Message!, GenerationErrorCode.InvalidRequest, validation.Field));
                var directFal = model.ProviderName == "fal" && ImageRoutingCodec.IsFalModel(model.ModelId);
                if (!directFal)
                {
                    var primary = await AwaitAsync(model.Provider.SubmitAsync(request, media, ct), ct).ConfigureAwait(false);
                    ct.ThrowIfCancellationRequested();
                    var error = Error(primary);
                    var credential = error == null ? null : ImageCredentialErrors.FromError(model.ProviderName, error);
                    var target = model.ProviderName == "gemini" ? ImageRoutingCodec.FalModel(model.ModelId) : null;
                    if (target == null || credential == null) return Result(primary);
                    var route = new ImageRouteReceipt("gemini", model.ModelId, "fal", target,
                        FalNanoBananaPayload.EndpointId(target, media.Count != 0),
                        credential.Kind == ImageCredentialFailureKind.Missing
                            ? ImageFallbackReason.GeminiKeyMissing : ImageFallbackReason.GeminiKeyRejected,
                        ImageExecutionPhase.Validation, false);
                    context.SelectFallbackTarget(route);
                    if (!_registry.TryResolve(target, out var fallback) || fallback.ProviderName != "fal")
                        return Result(Fail("The mapped fal image model is unavailable.", GenerationErrorCode.DependencyUnavailable, "model"));
                    var decoded = fallback.OptionsCodec.Deserialize(new System.Text.Json.Nodes.JsonObject());
                    if (!decoded.Success) return Result(new FailedSubmitOutcome(decoded.Error!));
                    request = request.With(model: target, options: decoded.Options!,
                        resolution: model.ModelId == "gemini-3.1-flash-image-preview" && request.Resolution == "512" ? "0.5K" : request.Resolution);
                    model = fallback;
                    context.SelectFallback(request, model, route);
                    validation = model.OptionsCodec.Validate(request, request.Options, model.Capability);
                    if (!validation.Success) return Result(Fail(validation.Message!, GenerationErrorCode.InvalidRequest, validation.Field));
                    ct.ThrowIfCancellationRequested();
                    if (prepareEffectiveRouteAsync != null)
                    {
                        var denied = await prepareEffectiveRouteAsync(context.Snapshot(), ct).ConfigureAwait(false);
                        if (denied != null) return Result(new FailedSubmitOutcome(denied));
                    }
                }
                ct.ThrowIfCancellationRequested();
                if (model.Provider is not IImageDispatchAwareProvider provider)
                    return Result(Fail("The fal image model cannot fence generation dispatch.", GenerationErrorCode.DependencyUnavailable));
                var outcome = await AwaitAsync(provider.SubmitAsync(request, media,
                    token => prepareGenerationDispatchAsync == null ? Task.FromResult<GenerationError?>(null)
                        : prepareGenerationDispatchAsync(context, token),
                    context.MarkGenerationDispatchAttempted, ct), ct).ConfigureAwait(false);
                ct.ThrowIfCancellationRequested();
                var failure = Error(outcome);
                context.SetCredentialFailure(failure == null ? null : ImageCredentialErrors.FromError("fal", failure));
                return Result(outcome);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                context.SetCredentialFailure(null);
                context.SetPhase(ImageExecutionPhase.Interruption);
                return Result(Fail("Image execution stopped.", GenerationErrorCode.Interrupted));
            }
            catch (Exception)
            {
                // Includes secret-store read failure. Never reinterpret it as an absent key.
                context.SetCredentialFailure(null);
                return Result(Fail("Image provider execution failed.", GenerationErrorCode.DependencyUnavailable));
            }
        }
        private static GenerationError? Error(ProviderSubmitOutcome outcome) => outcome switch
        {
            FailedSubmitOutcome f => f.Error,
            SyncSubmitOutcome { Result: FailedResultOutcome f } => f.Error,
            _ => null
        };
        internal static async Task<T> AwaitAsync<T>(Task<T> task, CancellationToken ct)
        {
            if (!ct.CanBeCanceled) return await task.ConfigureAwait(false);
            var stopped = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using var registration = ct.Register(() => stopped.TrySetResult(true));
            if (await Task.WhenAny(task, stopped.Task).ConfigureAwait(false) != task)
            {
                _ = task.ContinueWith(t => { _ = t.Exception; }, CancellationToken.None,
                    TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                ct.ThrowIfCancellationRequested();
            }
            return await task.ConfigureAwait(false);
        }
    }
}
