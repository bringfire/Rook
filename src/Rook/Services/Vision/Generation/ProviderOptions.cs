namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Discriminated base for provider-specific request options. Each
    /// provider declares its own sealed subtype and ships a matching
    /// <see cref="IProviderOptionsCodec{TRequest, TCapability}"/> for
    /// serialization, validation, and round-trip from the persisted
    /// ledger shape.
    ///
    /// The base is intentionally empty: nothing about request options
    /// is universal across providers (Veo's PersonGeneration, fal's
    /// per-route input field names, Replicate's version hash, Gemini's
    /// generationConfig — none of these share a contract).
    /// </summary>
    public abstract class ProviderOptions
    {
    }
}
