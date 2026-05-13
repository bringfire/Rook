using Rook.Artifacts;

namespace Rook.Services.Vision.MediaImport
{
    internal static class MediaImportSubsystemFactory
    {
        public static MediaImportJobManager Build(ArtifactStore artifactStore) =>
            new MediaImportJobManager(new MediaImportProcessor(artifactStore));
    }
}
