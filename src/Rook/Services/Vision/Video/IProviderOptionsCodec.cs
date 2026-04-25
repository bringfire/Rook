using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Per-provider serialization, validation, and round-trip for
    /// <see cref="ProviderOptions"/>. Bound to a
    /// <see cref="ResolvedVideoModel"/> at registry construction; one
    /// codec per provider (a Veo model resolves to
    /// <see cref="VeoOptionsCodec"/>).
    ///
    /// <para><see cref="Validate"/> houses provider-specific rules that
    /// V1b kept inside <c>VideoCapabilities.Validate</c> (e.g. Veo's
    /// model-family × image-based PersonGeneration matrix).
    /// Provider-neutral request-shape validation lives separately in
    /// <see cref="CapabilityValidator"/>.</para>
    ///
    /// <para><see cref="Serialize"/> output is the inner blob persisted
    /// verbatim into <see cref="VideoJobRecord.ProviderOptions"/>; for
    /// Veo it is <c>{ "person_generation": "..." }</c>, byte-identical to
    /// V1b's <c>VideoJobRecordFactory.BuildProviderOptions</c> output.
    /// The bit-identity fixture test guards this.</para>
    ///
    /// <para><see cref="Deserialize"/> exists for replay, diagnostics,
    /// and future content-hash cache keys (per
    /// <c>feedback_capability_extension_prep_timing.md</c>) — every
    /// persisted options blob must round-trip back to typed
    /// <see cref="ProviderOptions"/>.</para>
    /// </summary>
    public interface IProviderOptionsCodec
    {
        ValidationResult Validate(
            VideoGenerationRequest request,
            ProviderOptions options,
            ModelCapability cap);

        JsonObject Serialize(ProviderOptions options);

        ProviderOptionsDecodeResult Deserialize(JsonObject json);
    }
}
