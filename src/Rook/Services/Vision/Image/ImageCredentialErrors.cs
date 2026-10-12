using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image
{
    public static class ImageCredentialErrors
    {
        public const string GeminiMissing = "rook.gemini.key_missing";
        public const string GeminiRejected = "rook.gemini.key_rejected";
        public const string FalMissing = "rook.fal.key_missing";
        public const string FalRejected = "rook.fal.key_rejected";
        public static bool IsReserved(string? value) => value is GeminiMissing or GeminiRejected or FalMissing or FalRejected;
        public static ImageCredentialFailure? FromError(string provider, GenerationError error) =>
            (provider, error.ProviderErrorCode) switch
            {
                ("gemini", GeminiMissing) or ("fal", FalMissing) => new(provider, ImageCredentialFailureKind.Missing),
                ("gemini", GeminiRejected) or ("fal", FalRejected) => new(provider, ImageCredentialFailureKind.Rejected),
                _ => null
            };
    }
}
