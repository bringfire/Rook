using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class FalImageProviderRegistration :
        IImageProviderRegistration,
        IImageModelSubmissionModeRegistration
    {
        public FalImageProviderRegistration(IImageProvider provider)
        {
            Provider = provider ?? throw new ArgumentNullException(nameof(provider));
        }

        public string ProviderName => FalImageCapabilities.ProviderName;
        public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
        public IImageProvider Provider { get; }
        public IProviderOptionsCodec<ImageGenerationRequest, ImageCapability> OptionsCodec { get; }
            = new FalImageOptionsCodec();

        public ImageSubmissionMode GetSubmissionMode(string modelId) =>
            string.Equals(
                modelId,
                FalImageCapabilities.GptImage2Edit,
                StringComparison.Ordinal)
                ? ImageSubmissionMode.AsyncImageJob
                : ImageSubmissionMode.Sync;

        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => _secretRequirements;

        private static readonly IReadOnlyList<ProviderSecretRequirement> _secretRequirements =
            Array.AsReadOnly(new[]
            {
                new ProviderSecretRequirement(
                    GenerationSecretKeys.FalApiKey,
                    "fal API key",
                    isRequired: true),
            });

        public IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> Models
            => _models;

        private static readonly IReadOnlyDictionary<string, (ImageCapability Capability, IPricingModel<ImageGenerationRequest, ImageCapability> PricingModel)> _models =
            new Dictionary<string, (ImageCapability, IPricingModel<ImageGenerationRequest, ImageCapability>)>(StringComparer.Ordinal)
            {
                [FalImageCapabilities.FluxSchnell] = (
                    FalImageCapabilities.Models[FalImageCapabilities.FluxSchnell],
                    new FalFluxSchnellPricingModel()),

                [FalImageCapabilities.GptImage2Edit] = (
                    FalImageCapabilities.Models[FalImageCapabilities.GptImage2Edit],
                    new FalGptImage2EditPricingModel()),
            };
    }

    internal sealed class FalGptImage2EditPricingModel
        : IPricingModel<ImageGenerationRequest, ImageCapability>
    {
        public const string Source =
            "fal-openai-gpt-image-2-edit-2026-05-05";
        public const string Provenance =
            "fal-openai-gpt-image-2-edit-pricing-placeholder-2026-05-05";

        public string PricingSource => Source;
        public PricingMetadataLocation MetadataLocation =>
            PricingMetadataLocation.NotApplicable;

        public PricingResult Estimate(
            ImageGenerationRequest request,
            ImageCapability capability)
        {
            if (request is null)
                return PricingResult.Fail(new GenerationError(
                    Code: GenerationErrorCode.InvalidRequest,
                    Message: "Image generation request is null.",
                    Retryable: false,
                    Field: "request"));

            return PricingResult.Ok(
                new JobPricing(
                    Currency: "USD",
                    UnitPrice: null,
                    Unit: "image",
                    Quantity: 1m,
                    TotalUsd: null,
                    PricingSource: Source),
                new CostEstimate(
                    Min: 0m,
                    Max: 0m,
                    IsExact: false,
                    Provenance: Provenance));
        }

        public JobPricing? ExtractActualSpend(
            IReadOnlyDictionary<string, IReadOnlyList<string>> responseHeaders,
            JsonNode? responseBody) => null;
    }
}
