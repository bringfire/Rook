namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Discriminated base for provider-specific request options. Each
    /// provider declares its own sealed subtype (e.g.
    /// <see cref="VeoOptions"/>) and ships a matching
    /// <see cref="IProviderOptionsCodec"/> for serialization, validation,
    /// and round-trip from the persisted ledger shape.
    ///
    /// V1c lifts <c>PersonGeneration</c> off
    /// <see cref="VideoGenerationRequest"/> into <see cref="VeoOptions"/>;
    /// future providers add their own subtypes alongside.
    /// </summary>
    public abstract record ProviderOptions;
}
