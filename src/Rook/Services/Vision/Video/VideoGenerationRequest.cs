using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Domain request shape for video generation. D2.1-clean: NO base64
    /// fields exist anywhere in the domain. Inputs are referenced by
    /// <see cref="MediaRef"/> (artifact_id + role, or validated path).
    /// The adapter (PR-V2) is the rejection boundary for any
    /// legacy/base64-shaped wire payloads; the type system enforces the
    /// invariant from V1a on.
    ///
    /// V1c: provider-specific fields (e.g. PersonGeneration for Veo)
    /// migrated off this generic shape into per-provider
    /// <see cref="ProviderOptions"/> subtypes (e.g. <see cref="VeoOptions"/>).
    /// <see cref="GenerationRequest.Options"/> is non-nullable; manager +
    /// estimator fail typed <see cref="VideoErrorCode.InvalidRequest"/> at
    /// the boundary if a caller hands them a request with null options.
    ///
    /// <para>PR-2: inherits the modality-neutral
    /// <see cref="Rook.Services.Vision.Generation.GenerationRequest"/> so
    /// the generic seam can typecheck a request without knowing it is
    /// video-shaped. The base owns <c>Model</c> and <c>Options</c> via
    /// init-only properties; the derived's positional <c>Model</c> and
    /// <c>Options</c> parameters pass through to the base initializer.</para>
    /// </summary>
    public sealed class VideoGenerationRequest : GenerationRequest
    {
        public VideoGenerationRequest(
            string Model,
            VideoMode Mode,
            int DurationSeconds,
            string Resolution,
            string AspectRatio,
            string? Prompt,
            MediaRef? StartFrame,
            MediaRef? EndFrame,
            IReadOnlyList<MediaRef>? ReferenceFrames,
            int? Seed,
            ProviderOptions Options,
            int NumberOfVideos)
            : base(Model, Options)
        {
            this.Mode = Mode;
            this.DurationSeconds = DurationSeconds;
            this.Resolution = Resolution;
            this.AspectRatio = AspectRatio;
            this.Prompt = Prompt;
            this.StartFrame = StartFrame;
            this.EndFrame = EndFrame;
            this.ReferenceFrames = ReferenceFrames;
            this.Seed = Seed;
            this.NumberOfVideos = NumberOfVideos;
        }

        public VideoMode Mode { get; }
        public int DurationSeconds { get; }
        public string Resolution { get; }
        public string AspectRatio { get; }
        public string? Prompt { get; }
        public MediaRef? StartFrame { get; }
        public MediaRef? EndFrame { get; }
        public IReadOnlyList<MediaRef>? ReferenceFrames { get; }
        public int? Seed { get; }
        public int NumberOfVideos { get; }

        public VideoGenerationRequest With(
            string? model = null,
            VideoMode? mode = null,
            int? durationSeconds = null,
            string? resolution = null,
            string? aspectRatio = null,
            string? prompt = null,
            MediaRef? startFrame = null,
            MediaRef? endFrame = null,
            IReadOnlyList<MediaRef>? referenceFrames = null,
            int? seed = null,
            ProviderOptions? options = null,
            int? numberOfVideos = null) =>
            new VideoGenerationRequest(
                model ?? Model,
                mode ?? Mode,
                durationSeconds ?? DurationSeconds,
                resolution ?? Resolution,
                aspectRatio ?? AspectRatio,
                prompt ?? Prompt,
                startFrame ?? StartFrame,
                endFrame ?? EndFrame,
                referenceFrames ?? ReferenceFrames,
                seed ?? Seed,
                options ?? Options,
                numberOfVideos ?? NumberOfVideos);

        public VideoGenerationRequest WithPrompt(string? prompt) =>
            new VideoGenerationRequest(
                Model,
                Mode,
                DurationSeconds,
                Resolution,
                AspectRatio,
                prompt,
                StartFrame,
                EndFrame,
                ReferenceFrames,
                Seed,
                Options,
                NumberOfVideos);
    }
}
