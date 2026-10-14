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
        DateTimeOffset VerifiedOnUtc, bool ContinuityVerified, DateTimeOffset? NewSubmissionCutoffUtc,
        bool SupportsSeed, bool ReferenceFramingVerified);

    internal sealed class FalVeoBindingCatalog
    {
        public FalVeoBindingCatalog(IEnumerable<FalVeoBinding>? bindings = null) => All = Array.AsReadOnly((bindings ?? Candidates()).ToArray());
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
            if (!b.ContinuityVerified || b.NewSubmissionCutoffUtc is { } cutoff && now >= cutoff || (request.ReferenceFrames?.Count ?? 0) > 0 && !b.ReferenceFramingVerified)
                return (null, Error("fal Veo binding unavailable: continued support and source policy must be verified before submission.", "model"));
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
                    yield return new FalVeoBinding(id, id + suffix, "fal-ai/veo3.1", cap, "fal-veo-candidate-v1", suffix == "/reference-to-video" ? "reference-unverified-v1" : "exact-selected-ratio-v1", "fal-veo-candidate-rates-2026-10-14", "2026-10-14", new ReadOnlyDictionary<string, decimal>(rates), new Uri("https://fal.ai/models/" + id + suffix + "/api"), new DateTimeOffset(2026, 10, 14, 0, 0, 0, TimeSpan.Zero), false, new DateTimeOffset(2026, 11, 17, 0, 0, 0, TimeSpan.Zero), suffix != "/reference-to-video", false);
                }
            }
        }
    }
}
