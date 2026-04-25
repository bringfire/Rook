using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Translates a domain <see cref="VideoGenerationRequest"/> + the
    /// resolved model + an already-computed <see cref="VideoCostEstimate"/>
    /// into the provider-neutral durable shape used by the ledger
    /// (<see cref="VideoJobRecord"/>).
    ///
    /// V1c invariants:
    /// <list type="bullet">
    ///   <item><description>Provider name comes from
    ///     <see cref="ResolvedVideoModel.ProviderName"/> — no string
    ///     defaulting.</description></item>
    ///   <item><description>Provider options blob comes from
    ///     <see cref="IProviderOptionsCodec.Serialize"/> — no factory-side
    ///     `if (provider == "veo")` branches.</description></item>
    ///   <item><description><see cref="VideoJobRecord.Pricing"/> is copied
    ///     verbatim from <see cref="VideoCostEstimate.Pricing"/>; the
    ///     factory does NOT call any pricing function. Pricing is computed
    ///     once by the estimator at submit time and persisted exactly as
    ///     accepted.</description></item>
    /// </list>
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
            ResolvedVideoModel model,
            VideoCostEstimate estimate,
            VideoJobState initialState,
            DateTimeOffset now)
        {
            if (request is null) throw new ArgumentNullException(nameof(request));
            if (model is null) throw new ArgumentNullException(nameof(model));
            if (estimate is null) throw new ArgumentNullException(nameof(estimate));
            if (jobId == Guid.Empty)
                throw new ArgumentException("JobId must be non-empty.", nameof(jobId));

            return new VideoJobRecord(
                SchemaVersion: CurrentSchemaVersion,
                JobId: jobId,
                Provider: model.ProviderName,
                Model: request.Model,
                ProviderJobId: null,
                ProviderResultToken: null,
                State: initialState,
                NormalizedRequest: BuildNormalized(request),
                ProviderOptions: model.OptionsCodec.Serialize(request.Options),
                Pricing: estimate.Pricing,
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
    }
}
