using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public sealed class ImageCapability : IModelCapability
    {
        public ImageCapability(
            string Id,
            string Name,
            string Status,
            IReadOnlyList<string> Resolutions,
            IReadOnlyList<string> AspectRatios,
            int MaxReferenceImages,
            bool SupportsImageToImage,
            bool SupportsTextToImage,
            IReadOnlyList<string>? SubCapabilities = null)
        {
            if (string.IsNullOrWhiteSpace(Id))
                throw new ArgumentException("Id must be non-empty.", nameof(Id));
            if (string.IsNullOrWhiteSpace(Name))
                throw new ArgumentException("Name must be non-empty.", nameof(Name));
            if (string.IsNullOrWhiteSpace(Status))
                throw new ArgumentException("Status must be non-empty.", nameof(Status));
            if (Resolutions is null) throw new ArgumentNullException(nameof(Resolutions));
            if (AspectRatios is null) throw new ArgumentNullException(nameof(AspectRatios));
            if (MaxReferenceImages < 0)
                throw new ArgumentOutOfRangeException(
                    nameof(MaxReferenceImages), MaxReferenceImages,
                    "MaxReferenceImages must be non-negative.");

            this.Id = Id;
            this.Name = Name;
            this.Status = Status;
            this.Resolutions = CopyReadOnly(Resolutions);
            this.AspectRatios = CopyReadOnly(AspectRatios);
            this.MaxReferenceImages = MaxReferenceImages;
            this.SupportsImageToImage = SupportsImageToImage;
            this.SupportsTextToImage = SupportsTextToImage;
            this.SubCapabilities = CopyReadOnly(SubCapabilities ?? BuildSubCapabilities(
                SupportsTextToImage,
                SupportsImageToImage));
        }

        public string Id { get; }
        public string Name { get; }
        public string Status { get; }
        public string Modality => "image";
        public IReadOnlyList<string> SubCapabilities { get; }
        public IReadOnlyList<string> Resolutions { get; }
        public IReadOnlyList<string> AspectRatios { get; }
        public int MaxReferenceImages { get; }
        public bool SupportsImageToImage { get; }
        public bool SupportsTextToImage { get; }

        private static IReadOnlyList<string> BuildSubCapabilities(
            bool supportsTextToImage,
            bool supportsImageToImage)
        {
            var list = new List<string>();
            if (supportsTextToImage) list.Add("text_to_image");
            if (supportsImageToImage) list.Add("image_to_image");
            return list;
        }

        private static IReadOnlyList<T> CopyReadOnly<T>(IReadOnlyList<T> source)
        {
            var copy = new T[source.Count];
            for (int i = 0; i < source.Count; i++) copy[i] = source[i];
            return Array.AsReadOnly(copy);
        }
    }
}
