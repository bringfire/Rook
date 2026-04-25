using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Translates a domain <see cref="VideoGenerationRequest"/> into the
    /// provider-neutral durable shape used by the ledger
    /// (<see cref="VideoJobRecord"/>). Lifted out of
    /// <see cref="VideoJobManager"/> so the durable-schema mapping is
    /// independently testable, per Codex round 3 finding.
    ///
    /// V1c plan: when the registry lands, this factory becomes a thin
    /// shim that asks the registry for the per-provider normalization,
    /// or gets absorbed into the registry directly. Either way, the
    /// production callers won't change.
    /// </summary>
    public static class VideoJobRecordFactory
    {
        public const int CurrentSchemaVersion = 1;

        /// <summary>
        /// Build the initial record for a freshly-submitted job. The
        /// manager calls this once, then appends subsequent state
        /// transitions as new records via <see cref="WithState"/>.
        /// </summary>
        public static VideoJobRecord From(
            Guid jobId,
            VideoGenerationRequest request,
            string provider,
            VideoCostEstimate estimate,
            VideoJobState initialState,
            DateTimeOffset now)
        {
            if (request is null) throw new ArgumentNullException(nameof(request));
            if (estimate is null) throw new ArgumentNullException(nameof(estimate));
            if (string.IsNullOrWhiteSpace(provider))
                throw new ArgumentException("Provider must be non-empty.", nameof(provider));
            if (jobId == Guid.Empty)
                throw new ArgumentException("JobId must be non-empty.", nameof(jobId));

            return new VideoJobRecord(
                SchemaVersion: CurrentSchemaVersion,
                JobId: jobId,
                Provider: provider,
                Model: request.Model,
                ProviderJobId: null,
                ProviderResultToken: null,
                State: initialState,
                NormalizedRequest: BuildNormalized(request),
                ProviderOptions: BuildProviderOptions(provider, request),
                Pricing: BuildPricing(provider, request, estimate),
                ResultArtifactId: null,
                Error: null,
                CreatedAt: now,
                UpdatedAt: now,
                Extensions: null);
        }

        /// <summary>
        /// Produce a new record with a state transition applied. Caller
        /// passes the prior record (most-recent snapshot for this job)
        /// and the new fields; this preserves <c>CreatedAt</c> while
        /// updating <c>UpdatedAt</c>.
        /// </summary>
        public static VideoJobRecord WithState(
            VideoJobRecord prior,
            VideoJobState newState,
            DateTimeOffset now,
            string? providerJobId = null,
            string? providerResultToken = null,
            Guid? resultArtifactId = null,
            VideoJobError? error = null)
        {
            if (prior is null) throw new ArgumentNullException(nameof(prior));

            return prior with
            {
                State = newState,
                ProviderJobId = providerJobId ?? prior.ProviderJobId,
                ProviderResultToken = providerResultToken ?? prior.ProviderResultToken,
                ResultArtifactId = resultArtifactId ?? prior.ResultArtifactId,
                Error = error ?? prior.Error,
                UpdatedAt = now,
            };
        }

        private static NormalizedRequest BuildNormalized(VideoGenerationRequest req)
        {
            return new NormalizedRequest(
                Mode: req.Mode,
                DurationSeconds: req.DurationSeconds,
                Resolution: req.Resolution,
                AspectRatio: req.AspectRatio,
                Prompt: req.Prompt,
                StartFrame: ToNormalized(req.StartFrame),
                EndFrame: ToNormalized(req.EndFrame),
                ReferenceFrames: ToNormalizedList(req.ReferenceFrames),
                Seed: req.Seed,
                NumberOfVideos: req.NumberOfVideos);
        }

        private static NormalizedMediaRef? ToNormalized(VideoMediaRef? r) =>
            r is null ? null : new NormalizedMediaRef(r.Kind, r.ArtifactId, r.Path, r.Role);

        private static IReadOnlyList<NormalizedMediaRef>? ToNormalizedList(
            IReadOnlyList<VideoMediaRef>? refs)
        {
            if (refs is null) return null;
            var list = new List<NormalizedMediaRef>(refs.Count);
            foreach (var r in refs) list.Add(new NormalizedMediaRef(r.Kind, r.ArtifactId, r.Path, r.Role));
            return list;
        }

        private static JsonObject BuildProviderOptions(string provider, VideoGenerationRequest req)
        {
            var opts = new JsonObject();

            if (string.Equals(provider, "veo", StringComparison.OrdinalIgnoreCase))
            {
                opts["person_generation"] = MapVeoPersonGeneration(req.PersonGeneration);
            }

            return opts;
        }

        private static string MapVeoPersonGeneration(PersonGenerationPolicy p) => p switch
        {
            PersonGenerationPolicy.DontAllow => "dont_allow",
            PersonGenerationPolicy.AllowAdult => "allow_adult",
            PersonGenerationPolicy.AllowAll => "allow_all",
            _ => throw new ArgumentOutOfRangeException(
                nameof(p), p, "Unknown PersonGenerationPolicy."),
        };

        private static JobPricing BuildPricing(
            string provider, VideoGenerationRequest req, VideoCostEstimate estimate)
        {
            // V1b: Veo is per-second. V1c will introduce IPricingModel
            // and let each provider declare its own kind. For now we
            // hardcode the inference per provider.
            if (string.Equals(provider, "veo", StringComparison.OrdinalIgnoreCase))
            {
                var quantity = req.DurationSeconds * req.NumberOfVideos;
                var unit = quantity > 0
                    ? estimate.DollarsUsd / quantity
                    : (decimal?)null;

                return new JobPricing(
                    Kind: PricingKind.PerSecond,
                    Currency: "USD",
                    Quantity: quantity,
                    UnitPriceUsd: unit,
                    TotalUsd: estimate.DollarsUsd,
                    PricingSource: "veo-rate-card-v1");
            }

            // Unknown provider: degrade to External; V1c will replace
            // this with a per-provider IPricingModel.
            return new JobPricing(
                Kind: PricingKind.External,
                Currency: "USD",
                Quantity: req.NumberOfVideos,
                UnitPriceUsd: null,
                TotalUsd: estimate.DollarsUsd,
                PricingSource: $"{provider}-unknown");
        }
    }
}
