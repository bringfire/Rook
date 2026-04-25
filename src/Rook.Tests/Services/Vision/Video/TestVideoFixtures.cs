using System.Collections.Generic;
using Rook.Services.Vision.Video;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Shared fixture helpers for V1c tests. Builds
    /// <see cref="ResolvedVideoModel"/> instances and registries for the
    /// production Veo data table without forcing every test to repeat
    /// the per-model wiring. Tests that need a different shape (custom
    /// pricing, fake codec, etc.) construct
    /// <see cref="ResolvedVideoModel"/> inline.
    /// </summary>
    internal static class TestVideoFixtures
    {
        public const string VeoProviderName = "veo";
        public const string DefaultModelId = "veo-3.1-lite-generate-preview";

        /// <summary>
        /// A V1c-shaped <see cref="VideoGenerationRequest"/> matching V1b
        /// defaults: T2V on the lite model, 720p × 8s, AllowAll. Tests
        /// override fields with <c>with</c>-expressions as needed.
        /// </summary>
        public static VideoGenerationRequest DefaultT2vRequest(
            string model = DefaultModelId,
            VideoMode mode = VideoMode.T2V,
            int duration = 8,
            string resolution = "720p",
            string aspect = "16:9",
            string? prompt = "a clip",
            int numberOfVideos = 1,
            VideoMediaRef? startFrame = null,
            VideoMediaRef? endFrame = null,
            IReadOnlyList<VideoMediaRef>? referenceFrames = null,
            int? seed = null,
            PersonGenerationPolicy personGeneration = PersonGenerationPolicy.AllowAll) =>
            new(
                Model: model,
                Mode: mode,
                DurationSeconds: duration,
                Resolution: resolution,
                AspectRatio: aspect,
                Prompt: prompt,
                StartFrame: startFrame,
                EndFrame: endFrame,
                ReferenceFrames: referenceFrames,
                Seed: seed,
                Options: new VeoOptions(personGeneration),
                NumberOfVideos: numberOfVideos);

        /// <summary>
        /// Resolves the production Veo lite model with a caller-supplied
        /// provider (defaults to a fresh <see cref="FakeVideoProvider"/>).
        /// </summary>
        public static ResolvedVideoModel VeoLiteResolved(
            IVideoProvider? provider = null,
            string modelId = DefaultModelId)
        {
            var p = provider ?? new FakeVideoProvider();
            var (cap, pricing) = VeoCapabilities.Models[modelId];
            return new ResolvedVideoModel(
                ModelId: modelId,
                ProviderName: VeoProviderName,
                Provider: p,
                Capability: cap,
                PricingModel: pricing,
                OptionsCodec: new VeoOptionsCodec());
        }

        /// <summary>
        /// Production-shaped registry holding all real Veo models against
        /// the supplied provider (default fake). Use this when the test
        /// needs registry-resolved models for several Veo IDs.
        /// </summary>
        public static IVideoProviderRegistry RegistryWithVeo(
            IVideoProvider? provider = null) =>
            new DefaultVideoProviderRegistry(new[]
            {
                new VeoProviderRegistration(provider ?? new FakeVideoProvider()),
            });
    }
}
