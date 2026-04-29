namespace Rook.Services.Vision.Generation
{
    public static class GenerationSecretKeys
    {
        public const string GeminiApiKey = "gemini.api_key";
        public const string FalApiKey = "fal.api_key";
        public const string ReplicateApiToken = "replicate.api_token";
        public const string TencentSecretId = "tencent.secret_id";
        public const string TencentSecretKey = "tencent.secret_key";
        public const string TencentStsToken = "tencent.sts_token";
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
