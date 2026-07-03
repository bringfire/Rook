namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorExtractor : ICanvasDirectorExtractor
    {
        public CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request)
        {
            throw new CanvasDirectorException(
                "grasshopper_not_ready",
                "CanvasDirector extraction requires an active Grasshopper document.",
                503);
        }
    }
}
