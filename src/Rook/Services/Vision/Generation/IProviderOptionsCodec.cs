using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Per-provider serialization, validation, and round-trip for
    /// <see cref="ProviderOptions"/>. Generic over the modality's
    /// request and capability types so a video codec can validate
    /// against video-specific fields and an image codec can validate
    /// against image-specific fields.
    ///
    /// <para>Bound to a resolved-model record at registry construction.
    /// Phase 0 evidence: codec contracts vary not only across providers
    /// but per-route within a provider (Replicate community vs official;
    /// fal per-route input field naming). The codec encapsulates the
    /// per-route shape; Phase 2 will introduce per-route registration
    /// records to make this explicit.</para>
    /// </summary>
    public interface IProviderOptionsCodec<TRequest, TCapability>
        where TRequest : GenerationRequest
        where TCapability : IModelCapability
    {
        ValidationResult Validate(
            TRequest request,
            ProviderOptions options,
            TCapability capability);

        JsonObject Serialize(ProviderOptions options);

        ProviderOptionsDecodeResult Deserialize(JsonObject json);
    }
}
