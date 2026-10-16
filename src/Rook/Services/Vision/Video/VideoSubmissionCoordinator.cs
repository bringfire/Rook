using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video
{
    internal sealed record VideoRouteCandidate(ResolvedVideoModel Model, VideoGenerationRequest Request, FalVeoBinding? Binding, VideoCostEstimate? Estimate, GenerationError? EligibilityError);

    internal sealed class VideoSubmissionCoordinator
    {
        internal readonly IVideoProviderRegistry Registry;
        internal readonly FalVeoBindingCatalog Bindings;
        internal readonly IGenerationSecretStore Secrets;
        public VideoSubmissionCoordinator(IVideoProviderRegistry registry, FalVeoBindingCatalog catalog, IGenerationSecretStore secrets) { Registry = registry; Bindings = catalog; Secrets = secrets; }
        public static string? FalModelFor(string model) => model switch { "veo-3.1-generate-preview" => "fal-ai/veo3.1", "veo-3.1-fast-generate-preview" => "fal-ai/veo3.1/fast", "veo-3.1-lite-generate-preview" => "fal-ai/veo3.1/lite", _ => null };
        public static bool IsGoogleModel(string model) => FalModelFor(model) is not null;
        public static bool IsAffectedModel(string model) => IsGoogleModel(model) || model is "fal-ai/veo3.1" or "fal-ai/veo3.1/fast" or "fal-ai/veo3.1/lite";
        internal (bool Google, bool Fal, GenerationError? Error) Availability(VideoRequestIntent intent, DateTimeOffset now)
        {
            bool google = false, fal = false;
            try { google = IsGoogleModel(intent.Request.Model) && !string.IsNullOrWhiteSpace(Secrets.GetSecret(GenerationSecretKeys.GeminiApiKey)); }
            catch { return (false, false, VideoCredentialErrors.AccessFailed()); }
            try { fal = Secrets.HasSecret(GenerationSecretKeys.FalApiKey); }
            catch { if (!google) return (false, false, VideoCredentialErrors.AccessFailed()); }
            if (google) return (google, fal, null);
            if (Bindings.Resolve(intent.Request, now).Error != null)
                return (google, fal, Unavailable(IsGoogleModel(intent.Request.Model)
                    ? "Video generation needs a Google API key. Fal Veo fallback is currently disabled."
                    : "Fal Veo generation is currently disabled until endpoint continuity is verified.", IsGoogleModel(intent.Request.Model)));
            if (!fal) return (google, fal, Unavailable(IsGoogleModel(intent.Request.Model)
                ? "Video generation needs a Google or fal.ai API key. Open Vision Settings."
                : "Video generation needs a fal.ai API key. Open Vision Settings.", true));
            return (google, fal, null);
        }
        internal static GenerationError Unavailable(string message, bool settings) => new(GenerationErrorCode.DependencyUnavailable,
            message, false, "model", "video_route_unavailable", settings ? new Dictionary<string, System.Text.Json.Nodes.JsonNode> { ["action"] = System.Text.Json.Nodes.JsonValue.Create("open_settings")! } : null);
        public VideoRouteCandidate SelectInitial(VideoRouteQuote quote) => quote.Candidates.First(c => c.Model.ModelId == quote.PrimaryEstimate.Model);
        public VideoRouteCandidate? SelectFallback(VideoRouteQuote quote, GenerationError error) => VideoCredentialErrors.FromError("veo", error) != null ? quote.Candidates.FirstOrDefault(c => c.Model.ProviderName == "fal" && c.EligibilityError is null) : null;
        public Task<ProviderSubmitOutcome> SubmitAttemptAsync(VideoRouteCandidate candidate, VideoPreparedMediaSnapshot media, Action beforeDispatch, CancellationToken ct, VideoPreparationLease? phase = null) => candidate.Model.Provider is IPreparedMediaVideoProvider prepared
            ? prepared.SubmitPreparedAsync(candidate.Request, media, beforeDispatch, ct, phase)
            : Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(new GenerationError(GenerationErrorCode.DependencyUnavailable, "Video provider lacks durable prepared dispatch support.", false)));
        public IReadOnlyList<VideoRouteCandidate> ResolveCandidates(VideoRequestIntent intent, IReadOnlyDictionary<MediaRef, ResolvedMedia> media, DateTimeOffset now)
        { using var snapshot = VideoPreparedMediaSnapshot.Capture(intent.Request, media); return ResolveCandidates(intent, snapshot, now); }
        public IReadOnlyList<VideoRouteCandidate> ResolveCandidates(VideoRequestIntent intent, VideoPreparedMediaSnapshot media, DateTimeOffset now)
        {
            var list = new List<VideoRouteCandidate>();
            var estimator = new VideoCostEstimator();
            if (IsGoogleModel(intent.Request.Model) && Registry.TryResolve(intent.Request.Model, out var google))
            {
                var estimate = estimator.Estimate(google, intent.Request);
                list.Add(new VideoRouteCandidate(google, intent.Request, null, estimate.Estimate, estimate.Error));
            }
            var candidate = Bindings.GetCandidate(intent.Request);
            if (candidate.Binding is { } binding && Registry.TryResolve(binding.ModelId, out var fal))
            {
                var request = intent.Request.With(model: binding.ModelId, options: new FalVeoOptions());
                var estimate = estimator.Estimate(fal, request);
                var eligibility = Bindings.Resolve(intent.Request, now).Error ?? FalVeoCompatibility.Validate(intent, binding, media) ?? estimate.Error;
                if (estimate.Estimate?.Pricing.TotalUsd is null) eligibility ??= FalVeoBindingCatalog.Error("Binding pricing is unavailable.", "pricing");
                list.Add(new VideoRouteCandidate(fal, request, binding, estimate.Estimate, eligibility));
            }
            return list.AsReadOnly();
        }
    }
}
