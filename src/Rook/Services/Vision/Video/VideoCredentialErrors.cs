using System.Net;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
namespace Rook.Services.Vision.Video
{
    internal sealed record VideoCredentialFailure(string Provider, string Kind);
    internal static class VideoCredentialErrors
    {
        public static VideoCredentialFailure? FromError(string provider, GenerationError error) => (provider, error.ProviderErrorCode) switch {
            ("veo", "rook.veo.key_missing") => new("gemini", "missing"), ("veo", "rook.veo.key_rejected") => new("gemini", "rejected"),
            ("fal", "rook.fal.key_missing") => new("fal", "missing"), ("fal", "rook.fal.key_rejected") => new("fal", "rejected"), _ => null };
        internal static JsonObject Project(VideoCredentialFailure evidence) => new() { ["provider"] = evidence.Provider, ["kind"] = evidence.Kind, ["secret_key"] = evidence.Provider == "gemini" ? GenerationSecretKeys.GeminiApiKey : GenerationSecretKeys.FalApiKey, ["source"] = evidence.Kind == "missing" ? "local_configuration" : "provider_response" };
        public static GenerationError Missing(string provider) => new(GenerationErrorCode.DependencyUnavailable, (provider == "veo" ? "Gemini" : "fal.ai") + " API key is not configured. Set it in Vision Settings.", false, "credentials", "rook." + provider + ".key_missing");
        public static GenerationError AccessFailed() => new(GenerationErrorCode.DependencyUnavailable, "Generation credential store could not be read.", false, "credentials", "secret_access_failed");
        public static GenerationError FromHttp(string provider, int status, string body)
        {
            JsonObject? error = null;
            try { var root = JsonNode.Parse(body) as JsonObject; error = root?["error"] as JsonObject; } catch { }
            var rejected = provider == "veo" ? GoogleCredentialErrors.IsRejectedKey((HttpStatusCode)status, error) : status == 401;
            if (rejected) return new(GenerationErrorCode.DependencyUnavailable, (provider == "veo" ? "Google" : "fal.ai") + " rejected its API credential.", false, "credentials", "rook." + provider + ".key_rejected");
            return new(status == 429 ? GenerationErrorCode.QuotaExceeded : GenerationErrorCode.ExecutionFailed, "Video provider request failed (HTTP " + status + ").", false);
        }
        public static GenerationError Unknown() => new(GenerationErrorCode.Interrupted, "Remote submission outcome is unknown. Review job history before deliberately starting another generation.", false, null, "submission_unknown");
    }
}
