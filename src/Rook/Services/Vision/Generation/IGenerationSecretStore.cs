namespace Rook.Services.Vision.Generation
{
    public static class GenerationSecretKeys
    {
        public const string GeminiApiKey = "gemini.api_key";
    }

    public interface IGenerationSecretStore
    {
        string? GetSecret(string secretKey);
        void SetSecret(string secretKey, string value);
        void RemoveSecret(string secretKey);
        bool HasSecret(string secretKey);
        string? GetPreview(string secretKey);
    }
}
