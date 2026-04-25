namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Veo-specific provider options. <see cref="PersonGeneration"/>
    /// migrates from V1b's <c>VideoGenerationRequest.PersonGeneration</c>;
    /// the persisted JSON shape (<c>person_generation</c> string) is owned
    /// by <see cref="VeoOptionsCodec"/> and remains byte-identical.
    /// </summary>
    public sealed record VeoOptions(
        PersonGenerationPolicy PersonGeneration) : ProviderOptions;
}
