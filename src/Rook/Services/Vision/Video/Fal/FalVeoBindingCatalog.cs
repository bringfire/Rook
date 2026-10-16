using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed record FalVeoBinding(string ModelId, string SubmitEndpoint, string LifecycleRoot,
        VideoCapability Capability, string ProfileRevision, string FramingRevision, string PricingSource,
        string PricingRevision, IReadOnlyDictionary<string, decimal> RatesUsdPerSecond, Uri DocumentationSource,
        DateTimeOffset VerifiedOnUtc, bool SubmissionVerified, DateTimeOffset? NewSubmissionCutoffUtc,
        bool SupportsSeed, bool ReferenceFramingVerified);

    internal sealed class FalVeoBindingCatalog
    {
        public FalVeoBindingCatalog(IEnumerable<FalVeoBinding>? bindings = null) => All = Array.AsReadOnly((bindings ?? Candidates()).Select(b => b with { RatesUsdPerSecond = new ReadOnlyDictionary<string, decimal>(b.RatesUsdPerSecond.ToDictionary(kv => kv.Key, kv => kv.Value, StringComparer.Ordinal)) }).ToArray());
        public IReadOnlyList<FalVeoBinding> All { get; }
        public (FalVeoBinding? Binding, GenerationError? Error) GetCandidate(VideoGenerationRequest request)
        {
            var model = VideoSubmissionCoordinator.FalModelFor(request.Model) ?? request.Model;
            var suffix = request.Mode == VideoMode.Interp ? "/first-last-frame-to-video" : request.Mode == VideoMode.I2V ? "/image-to-video" : (request.ReferenceFrames?.Count ?? 0) > 0 ? "/reference-to-video" : "";
            var binding = All.SingleOrDefault(b => b.SubmitEndpoint == model + suffix);
            return binding is null ? (null, Error("Unsupported fal Veo tier or mode.", "mode")) : (binding, null);
        }
        public (FalVeoBinding? Binding, GenerationError? Error) Resolve(VideoGenerationRequest request, DateTimeOffset now)
        {
            var result = GetCandidate(request);
            if (result.Binding is not { } b) return result;
            if ((request.ReferenceFrames?.Count ?? 0) > 0 && (!b.SubmissionVerified || !b.ReferenceFramingVerified))
                return (null, Error("fal Veo reference-image generation is not qualified. Use image-to-video/interpolation, or Google with a configured API key.", "reference_frames"));
            if (!b.SubmissionVerified || b.NewSubmissionCutoffUtc is { } cutoff && now >= cutoff || (request.ReferenceFrames?.Count ?? 0) > 0 && !b.ReferenceFramingVerified)
                return (null, Error("This fal Veo endpoint or its source policy has not been verified for submission.", "model"));
            return result;
        }
        internal static GenerationError Error(string message, string field) => new(GenerationErrorCode.InvalidRequest, message, false, field);
        private static IEnumerable<FalVeoBinding> Candidates()
        {
            foreach (var tier in new[] { "", "/fast", "/lite" })
            {
                var id = "fal-ai/veo3.1" + tier;
                var lite = tier == "/lite";
                var cap = new VideoCapability(id, "Veo 3.1" + (lite ? " Lite" : tier == "/fast" ? " Fast" : "") + " · fal.ai", "preview", lite ? new[] { "720p", "1080p" } : new[] { "720p", "1080p", "4k" }, new[] { 4, 6, 8 }, new[] { "16:9", "9:16" }, new[] { VideoMode.T2V, VideoMode.I2V, VideoMode.Interp }, !lite, lite ? 0 : 3, new[] { "1080p", "4k", "referenceImages" });
                var rates = new Dictionary<string, decimal> { ["720p"] = lite ? .05m : tier == "/fast" ? .15m : .40m, ["1080p"] = lite ? .08m : tier == "/fast" ? .15m : .40m };
                if (!lite) rates["4k"] = tier == "/fast" ? .35m : .60m;
                foreach (var suffix in new[] { "", "/image-to-video", "/first-last-frame-to-video", "/reference-to-video" })
                {
                    if (lite && suffix == "/reference-to-video") continue;
                    // Deprecation is maintenance evidence, not a provider-mandated
                    // shutdown. Do not disable a working endpoint by calendar.
                    // Reference framing still requires separate qualification.
                    yield return new FalVeoBinding(id, id + suffix, "fal-ai/veo3.1", cap, "fal-veo-audio-defaults-v1", suffix == "/reference-to-video" ? "reference-unverified-v1" : "exact-selected-ratio-v1", "fal-veo-endpoint-rates-2026-10-16", "2026-10-16", new ReadOnlyDictionary<string, decimal>(rates), new Uri("https://fal.ai/models/" + id + suffix + "/api"), new DateTimeOffset(2026, 10, 16, 0, 0, 0, TimeSpan.Zero), suffix != "/reference-to-video", null, suffix != "/reference-to-video", false);
                }
            }
        }
    }
}
