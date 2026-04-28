using System;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Modality-neutral base for generation requests. Modality-specific
    /// subclasses (<c>VideoGenerationRequest</c>,
    /// <c>ImageGenerationRequest</c>) inherit and add their own typed
    /// fields. The <see cref="Options"/> field carries the
    /// provider-specific bag; the provider casts to its concrete
    /// <see cref="ProviderOptions"/> subtype internally.
    /// </summary>
    public abstract record GenerationRequest
    {
        protected GenerationRequest(string model, ProviderOptions options)
        {
            if (string.IsNullOrWhiteSpace(model))
                throw new ArgumentException(
                    "Model id must be non-empty.", nameof(model));
            if (options is null)
                throw new ArgumentNullException(nameof(options));

            Model = model;
            Options = options;
        }

        public string Model { get; init; }
        public ProviderOptions Options { get; init; }
    }
}
