using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Generation.Vertex;
using Rook.Services.Vision.Image.Gemini;

namespace Rook.Services.Vision.Image.Vertex
{
    internal sealed class VertexImageProviderRegistration : IImageProviderRegistration
    {
        internal static readonly ImageCapability Capability = new(VertexImageProvider.ModelKey,"Google Enterprise - Nano Banana 2","stable",
            new[]{"512","1K","2K","4K"},GeminiImageCapabilities.Models[GeminiImageCapabilities.NanoBanana2].AspectRatios,8,true,true);
        internal VertexImageProviderRegistration(IImageProvider provider) {Provider=provider;}
        public string ProviderName => "vertex_ai";
        public ImageSubmissionMode SubmissionMode => ImageSubmissionMode.Sync;
        public IImageProvider Provider {get;}
        public IProviderOptionsCodec<ImageGenerationRequest,ImageCapability> OptionsCodec {get;} = new GeminiImageOptionsCodec();
        public IReadOnlyList<ProviderSecretRequirement> SecretRequirements => Array.Empty<ProviderSecretRequirement>();
        public IReadOnlyDictionary<string,(ImageCapability Capability,IPricingModel<ImageGenerationRequest,ImageCapability> PricingModel)> Models {get;} =
            new Dictionary<string,(ImageCapability,IPricingModel<ImageGenerationRequest,ImageCapability>)>
            { [VertexImageProvider.ModelKey] = (Capability,new VertexUnpricedModel<ImageGenerationRequest,ImageCapability>()) };
    }
}
