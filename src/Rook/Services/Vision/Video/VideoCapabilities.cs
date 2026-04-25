using System;
using System.Collections.Generic;
using System.Linq;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Single source of truth for Veo model capabilities, pricing, and
    /// mode/resolution/duration constraints. Lifted from SA_Banana's
    /// VideoCapabilities (April 2026). Conservative policy: features are
    /// marked supported only where primary Google documentation confirms
    /// them for the exact model ID.
    ///
    /// Sources:
    ///   - https://ai.google.dev/gemini-api/docs/video
    ///   - https://ai.google.dev/gemini-api/docs/pricing
    /// </summary>
    public sealed class VideoCapabilities : IVideoCapabilityCatalog
    {
        public const string DefaultModelId = "veo-3.1-lite-generate-preview";

        public static readonly IReadOnlyDictionary<string, ModelCapability> Models =
            BuildDefaultModels();

        public static readonly VideoCapabilities Default = new(Models);

        private readonly IReadOnlyDictionary<string, ModelCapability> _models;

        public VideoCapabilities(IReadOnlyDictionary<string, ModelCapability> models)
        {
            _models = models ?? throw new ArgumentNullException(nameof(models));
        }

        public bool TryGetModel(string id, out ModelCapability model)
        {
            if (!string.IsNullOrWhiteSpace(id) && _models.TryGetValue(id, out var found))
            {
                model = found;
                return true;
            }

            model = null!;
            return false;
        }

        public ValidationResult Validate(VideoGenerationRequest request)
        {
            if (request is null)
                return ValidationResult.Fail(nameof(request), "Request is null.");

            if (string.IsNullOrWhiteSpace(request.Model))
                return ValidationResult.Fail(nameof(request.Model), "Model is required.");

            if (!_models.TryGetValue(request.Model, out var cap))
                return ValidationResult.Fail(
                    nameof(request.Model),
                    $"Unknown model '{request.Model}'.");

            if (request.NumberOfVideos != 1)
                return ValidationResult.Fail(
                    nameof(request.NumberOfVideos),
                    $"NumberOfVideos must be 1 for v1; got {request.NumberOfVideos}.");

            if (!cap.Modes.Contains(request.Mode))
                return ValidationResult.Fail(
                    nameof(request.Mode),
                    $"{cap.Name} does not support mode {request.Mode}.");

            // Required inputs per mode
            if (request.Mode == VideoMode.T2V && string.IsNullOrWhiteSpace(request.Prompt))
                return ValidationResult.Fail(
                    nameof(request.Prompt),
                    "Text-to-video requires a prompt.");

            if (request.Mode == VideoMode.I2V && request.StartFrame is null)
                return ValidationResult.Fail(
                    nameof(request.StartFrame),
                    "Image-to-video requires a start frame.");

            if (request.Mode == VideoMode.Interp)
            {
                if (request.StartFrame is null)
                    return ValidationResult.Fail(
                        nameof(request.StartFrame),
                        "Interpolation requires a start frame.");
                if (request.EndFrame is null)
                    return ValidationResult.Fail(
                        nameof(request.EndFrame),
                        "Interpolation requires an end frame.");
            }

            if (!cap.Resolutions.Contains(request.Resolution))
                return ValidationResult.Fail(
                    nameof(request.Resolution),
                    $"{cap.Name} does not support resolution '{request.Resolution}'. " +
                    $"Supported: {string.Join(", ", cap.Resolutions)}.");

            if (!cap.Durations.Contains(request.DurationSeconds))
                return ValidationResult.Fail(
                    nameof(request.DurationSeconds),
                    $"{cap.Name} does not support duration {request.DurationSeconds}s. " +
                    $"Supported: {string.Join(", ", cap.Durations)}s.");

            if (!cap.AspectRatios.Contains(request.AspectRatio))
                return ValidationResult.Fail(
                    nameof(request.AspectRatio),
                    $"{cap.Name} does not support aspect ratio '{request.AspectRatio}'. " +
                    $"Supported: {string.Join(", ", cap.AspectRatios)}.");

            // Reference image gating
            var refCount = request.ReferenceFrames?.Count ?? 0;
            if (refCount > 0)
            {
                if (!cap.SupportsReferenceImages)
                    return ValidationResult.Fail(
                        nameof(request.ReferenceFrames),
                        $"{cap.Name} does not support reference images.");
                if (refCount > cap.MaxReferenceImages)
                    return ValidationResult.Fail(
                        nameof(request.ReferenceFrames),
                        $"{cap.Name} supports at most {cap.MaxReferenceImages} reference images; got {refCount}.");
            }

            // Must-8s coupling
            var triggers = new List<string>();
            if (cap.Must8sWith.Contains(request.Resolution))
                triggers.Add(request.Resolution);
            if (refCount > 0 && cap.Must8sWith.Contains("referenceImages"))
                triggers.Add("reference images");

            if (triggers.Count > 0 && request.DurationSeconds != 8)
                return ValidationResult.Fail(
                    nameof(request.DurationSeconds),
                    $"{cap.Name} requires 8s duration when using {string.Join(", ", triggers)}.");

            // PersonGeneration is a Veo API requirement, not a UI nicety.
            // Per Google's docs, only specific values are allowed per
            // (model-family × mode) combination; Veo rejects submissions
            // that violate the table. Lifted from SA_Banana's
            // ValidatePersonGeneration. Regional EU/UK/CH/MENA overrides
            // are looser on the server side and deferred to Veo.
            var personErr = ValidatePersonGeneration(
                request.Model, request.Mode, request.PersonGeneration, cap);
            if (personErr is not null)
                return ValidationResult.Fail(
                    nameof(request.PersonGeneration), personErr);

            return ValidationResult.Ok();
        }

        private static string? ValidatePersonGeneration(
            string modelId,
            VideoMode mode,
            PersonGenerationPolicy personGen,
            ModelCapability cap)
        {
            // Fail-closed on undefined enum values. C# enums are coercible
            // — (PersonGenerationPolicy)999 can reach this method via a
            // cast, reflection, or a loose adapter. Reject before
            // applying the model/mode table so the branches below only
            // ever see the three defined values. SA_Banana's string-based
            // validator did the equivalent check before the model/mode
            // rules; preserving that posture under enum typing.
            if (!Enum.IsDefined(typeof(PersonGenerationPolicy), personGen))
                return $"Unknown PersonGeneration value: {(int)personGen}.";

            var isVeo2 = modelId.StartsWith(
                "veo-2", StringComparison.OrdinalIgnoreCase);
            var imageBased = mode == VideoMode.I2V || mode == VideoMode.Interp;

            if (isVeo2)
            {
                // Veo 2: T2V allows all three; image-based modes reject AllowAll.
                if (imageBased && personGen == PersonGenerationPolicy.AllowAll)
                    return $"{cap.Name} requires PersonGeneration=AllowAdult or DontAllow " +
                           "for image-based modes (image-to-video, interpolation).";
                return null;
            }

            // Veo 3.x family: docs list exactly one value per mode shape.
            if (imageBased)
            {
                if (personGen != PersonGenerationPolicy.AllowAdult)
                    return $"{cap.Name} requires PersonGeneration=AllowAdult for " +
                           "image-based modes (image-to-video, interpolation, " +
                           "reference images).";
            }
            else // T2V
            {
                if (personGen != PersonGenerationPolicy.AllowAll)
                    return $"{cap.Name} requires PersonGeneration=AllowAll for text-to-video.";
            }

            return null;
        }

        private static IReadOnlyDictionary<string, ModelCapability> BuildDefaultModels()
        {
            var t2vI2vInterp = new[] { VideoMode.T2V, VideoMode.I2V, VideoMode.Interp };

            return new Dictionary<string, ModelCapability>
            {
                ["veo-3.1-generate-preview"] = new ModelCapability(
                    Id: "veo-3.1-generate-preview",
                    Name: "Veo 3.1",
                    Status: "preview",
                    Resolutions: new[] { "720p", "1080p", "4k" },
                    Durations: new[] { 4, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: true,
                    MaxReferenceImages: 3,
                    Must8sWith: new[] { "1080p", "4k", "referenceImages" },
                    PricePerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.40m,
                        ["1080p"] = 0.40m,
                        ["4k"] = 0.60m,
                    }),

                ["veo-3.1-fast-generate-preview"] = new ModelCapability(
                    Id: "veo-3.1-fast-generate-preview",
                    Name: "Veo 3.1 Fast",
                    Status: "preview",
                    Resolutions: new[] { "720p", "1080p", "4k" },
                    Durations: new[] { 4, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: true,
                    MaxReferenceImages: 3,
                    Must8sWith: new[] { "1080p", "4k", "referenceImages" },
                    PricePerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.10m,
                        ["1080p"] = 0.12m,
                        ["4k"] = 0.30m,
                    }),

                ["veo-3.1-lite-generate-preview"] = new ModelCapability(
                    Id: "veo-3.1-lite-generate-preview",
                    Name: "Veo 3.1 Lite",
                    Status: "preview",
                    Resolutions: new[] { "720p", "1080p" },
                    Durations: new[] { 4, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: new[] { "1080p" },
                    PricePerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.05m,
                        ["1080p"] = 0.08m,
                    }),

                ["veo-3.0-generate-001"] = new ModelCapability(
                    Id: "veo-3.0-generate-001",
                    Name: "Veo 3",
                    Status: "stable",
                    Resolutions: new[] { "720p", "1080p" },
                    Durations: new[] { 8 },
                    AspectRatios: new[] { "16:9" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>(),
                    PricePerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.40m,
                        ["1080p"] = 0.40m,
                    }),

                ["veo-3.0-fast-generate-001"] = new ModelCapability(
                    Id: "veo-3.0-fast-generate-001",
                    Name: "Veo 3 Fast",
                    Status: "stable",
                    Resolutions: new[] { "720p", "1080p" },
                    Durations: new[] { 8 },
                    AspectRatios: new[] { "16:9" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>(),
                    PricePerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.10m,
                        ["1080p"] = 0.12m,
                    }),

                ["veo-2.0-generate-001"] = new ModelCapability(
                    Id: "veo-2.0-generate-001",
                    Name: "Veo 2",
                    Status: "stable",
                    Resolutions: new[] { "720p" },
                    Durations: new[] { 5, 6, 8 },
                    AspectRatios: new[] { "16:9", "9:16" },
                    Modes: t2vI2vInterp,
                    SupportsReferenceImages: false,
                    MaxReferenceImages: 0,
                    Must8sWith: Array.Empty<string>(),
                    PricePerSecondUsd: new Dictionary<string, decimal>
                    {
                        ["720p"] = 0.35m,
                    }),
            };
        }
    }
}
