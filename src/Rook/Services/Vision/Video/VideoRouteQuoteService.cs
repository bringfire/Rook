using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoRouteQuoteService
    {
        private readonly VideoSubmissionCoordinator _coordinator;
        private readonly IVideoJobClock _clock;
        internal VideoFramingPreparationService Preparation { get; }
        public VideoRouteQuoteService(VideoSubmissionCoordinator coordinator, IMediaResolver mediaResolver, IVideoJobClock clock,
            VideoFramingPreparationService? preparation = null)
        { _coordinator = coordinator; _clock = clock; Preparation = preparation ?? new(mediaResolver, new VideoFramingCache()); }
        public async Task<VideoRouteQuoteResult> QuoteAsync(VideoRequestIntent intent, CancellationToken ct)
        {
            var prepared = await PrepareSubmissionAsync(intent, ct).ConfigureAwait(false);
            using var bundle = prepared.Bundle;
            return new(prepared.Quote, prepared.Error);
        }
        internal async Task<(VideoPreparedBundleLease? Bundle, VideoRouteQuote? Quote, GenerationError? Error)> PrepareSubmissionAsync(VideoRequestIntent intent, CancellationToken ct)
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(15));
            if (VideoFramingPreparationService.ValidateUse(intent.Request) is { } invalid) return (null, null, invalid);
            var available = _coordinator.Availability(intent, _clock.UtcNow());
            if (available.Error != null) return (null, null, available.Error);
            VideoPreparedBundleLease? pin = null;
            try
            {
                using var phase = await Preparation.Resources.AcquireAsync(deadline.Token).ConfigureAwait(false);
                var prepared = await Preparation.PrepareSelectedAsync(intent, phase, deadline.Token).ConfigureAwait(false);
                if (prepared.Bundle == null) return (null, null, prepared.Error);
                pin = prepared.Bundle;
                var quoted = await QuotePreparedAsync(intent, pin, deadline.Token).ConfigureAwait(false);
                if (quoted.Error != null) return (null, null, quoted.Error);
                var transferred = pin; pin = null; return (transferred, quoted.Quote, null);
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested) { return (null, null, VideoSourcePreparationErrors.Busy("source_framing")); }
            catch (VideoPreparationBusyException) { return (null, null, VideoSourcePreparationErrors.Busy("source_framing")); }
            finally { pin?.Dispose(); }
        }
        public Task<VideoRouteQuoteResult> QuotePreparedAsync(VideoRequestIntent intent, VideoPreparedBundleLease held, CancellationToken ct)
        {
            if (Preparation.ValidateProfile(intent) is { } profile) return Task.FromResult(new VideoRouteQuoteResult(null, profile));
            return QuoteCoreAsync(intent, held.Prepared, held.SourcePreparation, held.Originals, ct);
        }
        public async Task<VideoRouteQuoteResult> RevalidateForDispatchAsync(VideoRequestIntent intent, VideoPreparedBundleLease held,
            VideoRouteQuote accepted, VideoSubmitConfirmation confirmation, VideoRouteCandidate selected, VideoPreparationLease phase, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var fresh = await Preparation.ReadOriginalsAsync(intent.Request, phase, ct).ConfigureAwait(false);
            if (fresh.Snapshot == null) return new(null, fresh.Error);
            using var originals = fresh.Snapshot;
            if (!JsonNode.DeepEquals(ProjectMedia(originals), ProjectMedia(held.Originals)) || ValidatePreparedMedia(held.Prepared, accepted) != null ||
                !JsonNode.DeepEquals(held.SourcePreparation, accepted.SourcePreparation))
                return new(null, Error("Source or prepared media changed; obtain a fresh estimate and confirm a new job.", "media", "estimate_stale"));
            var current = await QuotePreparedAsync(intent, held, ct).ConfigureAwait(false);
            if (current.Error != null) return current;
            var invalid = ValidateConfirmation(current.Quote!, confirmation, selected);
            return invalid == null ? current : new(null, invalid);
        }
        internal static MediaRef[] VideoMediaReferences(VideoGenerationRequest request) => new[] { request.StartFrame, request.EndFrame }.Where(r => r != null).Cast<MediaRef>().Concat(request.ReferenceFrames ?? Array.Empty<MediaRef>()).ToArray();

        public Task<VideoRouteQuoteResult> QuotePreparedAsync(VideoRequestIntent intent, VideoPreparedMediaSnapshot preparedMedia, CancellationToken ct)
            => QuoteCoreAsync(intent, preparedMedia, null, preparedMedia, ct);
        private Task<VideoRouteQuoteResult> QuoteCoreAsync(VideoRequestIntent intent, VideoPreparedMediaSnapshot preparedMedia, JsonObject? sourcePreparation, VideoPreparedMediaSnapshot originals, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var availability = _coordinator.Availability(intent, _clock.UtcNow());
            if (availability.Error != null) return Task.FromResult(new VideoRouteQuoteResult(null, availability.Error));
            bool googleConfigured = availability.Google, falConfigured = availability.Fal;
            var candidates = _coordinator.ResolveCandidates(intent, preparedMedia, _clock.UtcNow());
            var primary = candidates.FirstOrDefault(c => c.Model.ProviderName == (googleConfigured ? "veo" : "fal"));
            if (primary is null) return Task.FromResult(new VideoRouteQuoteResult(null, Error("No compatible video binding is registered.", "model")));
            if (primary.EligibilityError != null || primary.Estimate?.Pricing.TotalUsd is null) return Task.FromResult(new VideoRouteQuoteResult(null, primary.EligibilityError ?? Error("Pricing is unavailable.", "pricing")));
            // Configuration presence is metadata, not credential validation. Missing fal can still be quoted,
            // but cannot be submitted. This preserves a price-only quote without decrypting unused secrets.
            var eligible = candidates.Where(c => c.EligibilityError is null && c.Estimate?.Pricing.TotalUsd != null && (googleConfigured || c.Model.ProviderName == "fal")).ToArray();
            var maximum = eligible.Max(c => c.Estimate!.DollarsUsd);
            var request = intent.Request;
            var normalizedOptions = _coordinator.Registry.TryResolve(request.Model, out var requested) ? requested.OptionsCodec.Serialize(request.Options) : new JsonObject();
            var candidateJson = new JsonArray();
            foreach (var candidate in candidates)
            {
                var binding = candidate.Binding;
                candidateJson.Add(new JsonObject {
                    ["provider"] = candidate.Model.ProviderName, ["model"] = candidate.Model.ModelId,
                    ["endpoint"] = binding?.SubmitEndpoint, ["lifecycle_root"] = binding?.LifecycleRoot,
                    ["capability"] = ProjectCapability(candidate.Model.Capability), ["supports_seed"] = binding?.SupportsSeed,
                    ["effective_options"] = candidate.Model.OptionsCodec.Serialize(candidate.Request.Options),
                    ["profile"] = binding?.ProfileRevision, ["framing"] = binding?.FramingRevision,
                    ["submission_verified"] = binding?.SubmissionVerified, ["cutoff"] = binding?.NewSubmissionCutoffUtc?.ToString("O"),
                    ["documentation"] = binding?.DocumentationSource.AbsoluteUri, ["verified_on"] = binding?.VerifiedOnUtc.ToString("O"), ["reference_framing_verified"] = binding?.ReferenceFramingVerified,
                    ["pricing_source"] = candidate.Estimate?.Pricing.PricingSource, ["pricing_revision"] = binding?.PricingRevision ?? candidate.Estimate?.Pricing.PricingSource,
                    ["currency"] = candidate.Estimate?.Pricing.Currency, ["unit_rate"] = candidate.Estimate?.Pricing.UnitPriceUsd, ["total"] = candidate.Estimate?.Pricing.TotalUsd,
                    ["eligible"] = candidate.EligibilityError is null, ["incompatible_field"] = candidate.EligibilityError?.Field
                });
            }
            var canonical = new JsonObject {
                ["version"] = 1, ["policy"] = "google-first-veo-v2",
                ["request"] = new JsonObject { ["model"] = request.Model, ["mode"] = request.Mode.ToString(), ["prompt"] = request.Prompt, ["duration"] = request.DurationSeconds, ["resolution"] = request.Resolution, ["aspect"] = request.AspectRatio, ["seed"] = request.Seed, ["outputs"] = request.NumberOfVideos, ["supplied_options"] = intent.SuppliedOptions, ["normalized_options"] = normalizedOptions, ["person_generation_supplied"] = intent.PersonGenerationSupplied },
                ["media"] = ProjectMedia(preparedMedia), ["google_configured"] = googleConfigured, ["fal_configured"] = falConfigured,
                ["candidates"] = candidateJson, ["maximum_estimated_cost_usd"] = maximum
            };
            if (request.SourceFraming != null)
            {
                if (sourcePreparation == null) return Task.FromResult(new VideoRouteQuoteResult(null, Error("Prepared framing evidence is required.", "source_framing", "estimate_stale")));
                canonical["request"]!["source_framing"] = request.SourceFraming.Value.Wire();
                canonical["original_media"] = ProjectMedia(originals);
                canonical["source_preparation"] = sourcePreparation.DeepClone();
            }
            return Task.FromResult(new VideoRouteQuoteResult(new VideoRouteQuote(canonical, candidates, primary.Estimate, maximum, VideoEstimateFingerprint.Compute(canonical)), null));
        }
        internal static JsonArray ProjectMedia(VideoPreparedMediaSnapshot preparedMedia) => new(preparedMedia.Slots.Select(s => (JsonNode?)new JsonObject { ["role"] = s.Role, ["artifact_id"] = s.Ref.ArtifactId?.ToString("D"), ["source_role"] = s.Ref.Role, ["mime_type"] = s.MimeType, ["sha256"] = s.Sha256, ["byte_length"] = s.ByteLength }).ToArray());
        private static JsonObject ProjectCapability(VideoCapability capability) => new() {
            ["id"] = capability.Id, ["status"] = capability.Status,
            ["resolutions"] = new JsonArray(capability.Resolutions.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()),
            ["durations"] = new JsonArray(capability.Durations.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()),
            ["aspects"] = new JsonArray(capability.AspectRatios.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()),
            ["modes"] = new JsonArray(capability.Modes.Select(s => (JsonNode?)JsonValue.Create(s.ToString())).ToArray()),
            ["supports_references"] = capability.SupportsReferenceImages, ["references"] = capability.MaxReferenceImages,
            ["must_8s_with"] = new JsonArray(capability.Must8sWith.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()) };
        public GenerationError? ValidatePreparedMedia(VideoPreparedMediaSnapshot preparedMedia, VideoRouteQuote quote) => JsonNode.DeepEquals(ProjectMedia(preparedMedia), quote.CanonicalSnapshot["media"]) ? null : Error("Source media changed; obtain a fresh estimate and confirm a new job.", "media", "estimate_stale");
        public GenerationError? ValidateConfirmation(VideoRouteQuote current, VideoSubmitConfirmation confirmation, VideoRouteCandidate? selected)
        {
            if (confirmation.EstimateFingerprint != null && (!confirmation.MaxEstimatedCostUsd.HasValue || confirmation.EstimateFingerprint.Length != 67 || !confirmation.EstimateFingerprint.StartsWith("v1:", StringComparison.Ordinal) || confirmation.EstimateFingerprint.Skip(3).Any(c => !Uri.IsHexDigit(c)))) return Error("A valid estimate fingerprint requires a numeric cost cap.", "estimate_fingerprint");
            if (confirmation.MaxEstimatedCostUsd < 0) return Error("Cost cap cannot be negative.", "max_estimated_cost_usd");
            if (confirmation.EstimateFingerprint != null && confirmation.EstimateFingerprint != current.EstimateFingerprint) return Error("Estimate changed; obtain a fresh estimate and confirm a new job.", "estimate_fingerprint", "estimate_stale");
            var fresh = selected == null ? null : current.Candidates.FirstOrDefault(c => c.Model.ProviderName == selected.Model.ProviderName && c.Model.ModelId == selected.Model.ModelId && c.Binding?.SubmitEndpoint == selected.Binding?.SubmitEndpoint);
            if (selected != null && (fresh == null || fresh.EligibilityError != null || fresh.Estimate?.Pricing.TotalUsd == null)) return Error("Selected route is no longer compatible; obtain a fresh estimate.", "model", "estimate_stale");
            var cost = fresh?.Estimate?.DollarsUsd ?? current.MaximumEstimatedCostUsd;
            if (confirmation.MaxEstimatedCostUsd is { } cap && cost > cap) return Error("Estimated video cost exceeds the confirmed bound.", "max_estimated_cost_usd", "cost_cap_exceeded");
            return null;
        }
        private static GenerationError Error(string message, string field, string? code = null) => new(GenerationErrorCode.InvalidRequest, message, false, field, code);
    }
}
