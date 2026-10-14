using System.Net;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>Closed Google authentication evidence shared by text and image routing.</summary>
    internal static class GoogleCredentialErrors
    {
        internal static bool IsRejectedKey(HttpStatusCode status, JsonObject? error)
        {
            if (error is null || status is not (HttpStatusCode.BadRequest or HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden))
                return false;
            if (status == HttpStatusCode.Unauthorized && IsString(error["status"], "UNAUTHENTICATED"))
                return true;
            if (error["details"] is not JsonArray details) return false;
            foreach (var node in details)
            {
                if (node is not JsonObject info ||
                    !IsString(info["@type"], "type.googleapis.com/google.rpc.ErrorInfo") ||
                    !IsString(info["domain"], "googleapis.com") ||
                    !IsString(info["reason"], "API_KEY_INVALID")) continue;
                if (info.TryGetPropertyValue("metadata", out var metadata))
                {
                    if (metadata is not JsonObject m) continue;
                    if (m.TryGetPropertyValue("service", out var service) &&
                        !IsString(service, "generativelanguage.googleapis.com")) continue;
                }
                return true;
            }
            return false;
        }

        private static bool IsString(JsonNode? node, string expected) =>
            node is JsonValue value && value.TryGetValue<string>(out var text) && text == expected;
    }
}
