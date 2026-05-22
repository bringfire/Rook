using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public sealed class ImageGenerationRequest : GenerationRequest
    {
        public ImageGenerationRequest(
            string Model,
            string Prompt,
            string Resolution,
            string AspectRatio,
            int NumberOfImages,
            IReadOnlyList<MediaRef>? ReferenceImages,
            ProviderOptions Options)
            : base(Model, Options)
        {
            this.Prompt = Prompt;
            this.Resolution = Resolution;
            this.AspectRatio = AspectRatio;
            this.NumberOfImages = NumberOfImages;
            this.ReferenceImages = ReferenceImages;
        }

        public string Prompt { get; }
        public string Resolution { get; }
        public string AspectRatio { get; }
        public int NumberOfImages { get; }
        public IReadOnlyList<MediaRef>? ReferenceImages { get; }

        public ImageGenerationRequest With(
            string? model = null,
            string? prompt = null,
            string? resolution = null,
            string? aspectRatio = null,
            int? numberOfImages = null,
            IReadOnlyList<MediaRef>? referenceImages = null,
            ProviderOptions? options = null) =>
            new ImageGenerationRequest(
                model ?? Model,
                prompt ?? Prompt,
                resolution ?? Resolution,
                aspectRatio ?? AspectRatio,
                numberOfImages ?? NumberOfImages,
                referenceImages ?? ReferenceImages,
                options ?? Options);
    }
}
