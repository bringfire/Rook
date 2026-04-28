using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Per-provider serialization, validation, and round-trip for
    /// <see cref="ProviderOptions"/>. Bound to a
    /// <see cref="ResolvedVideoModel"/> at registry construction.
    ///
    /// V1c implementations (e.g. <see cref="VeoOptionsCodec"/>)
    /// fail-closed on unknown serialized values. V2+ replay consumers
    /// reading records written by a newer binary may encounter values
    /// added after this codec shipped; design those consumers to tolerate
    /// a fail-closed Deserialize (e.g. surface a typed
    /// <see cref="VideoErrorCode.UnsupportedMedia"/>) rather than crash.
    /// If forward-compat envelope semantics are needed, add a
    /// <c>RawProviderOptions</c> fallback subtype before V2 ships.
    /// </summary>
    public interface IProviderOptionsCodec
    {
        ValidationResult Validate(
            VideoGenerationRequest request,
            ProviderOptions options,
            VideoCapability cap);

        JsonObject Serialize(ProviderOptions options);

        ProviderOptionsDecodeResult Deserialize(JsonObject json);
    }
}
