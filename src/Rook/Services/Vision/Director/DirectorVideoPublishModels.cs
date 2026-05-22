using System;
using System.Text.Json.Nodes;
using Rook;

namespace Rook.Services.Vision.Director
{
    internal static class DirectorVideoPublishResponses
    {
        public static ApiResponse BoundaryMismatch(string subcode, string message)
            => new ApiResponse
            {
                Success = false,
                Data = new JsonObject
                {
                    ["code"] = "artifact_boundary_mismatch",
                    ["managed_subcode"] = subcode,
                    ["message"] = message,
                },
            };

        public static ApiResponse PublishedArtifactMissing(Guid id)
            => new ApiResponse
            {
                Success = false,
                Data = new JsonObject
                {
                    ["code"] = "published_artifact_missing",
                    ["message"] = $"Previously published artifact '{id:D}' no longer exists.",
                },
            };
    }
}
