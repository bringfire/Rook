using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Veo-specific provider options. <see cref="PersonGeneration"/>
    /// migrates from V1b's <c>VideoGenerationRequest.PersonGeneration</c>;
    /// the persisted JSON shape (<c>person_generation</c> string) is owned
    /// by <see cref="VeoOptionsCodec"/> and remains byte-identical.
    ///
    /// <para>PR-2 retargets the base from the deleted
    /// <c>Rook.Services.Vision.Video.ProviderOptions</c> to the
    /// modality-neutral
    /// <see cref="Rook.Services.Vision.Generation.ProviderOptions"/> so a
    /// single options hierarchy spans video and image providers.</para>
    /// </summary>
    public sealed record VeoOptions(
        PersonGenerationPolicy PersonGeneration) : ProviderOptions;
}
