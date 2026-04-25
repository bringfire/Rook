namespace Rook.Services.Vision.Video
{
    public interface IVideoCapabilityCatalog
    {
        bool TryGetModel(string id, out ModelCapability model);

        ValidationResult Validate(VideoGenerationRequest request);
    }
}
