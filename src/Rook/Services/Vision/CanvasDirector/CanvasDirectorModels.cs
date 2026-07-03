using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorExtractRequest
    {
        public string? Op { get; init; }
        public string? ExportId { get; init; }
        public string? DocumentId { get; init; }
        public string? ProposalId { get; init; }
        public string? SolveMode { get; init; } = "require_fresh_solve";
        public string? ExpectedSolutionToken { get; init; }

        public static CanvasDirectorExtractRequest Parse(string? requestJson)
        {
            if (string.IsNullOrWhiteSpace(requestJson))
            {
                requestJson = "{}";
            }

            using var document = JsonDocument.Parse(requestJson!);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new CanvasDirectorException(
                    "invalid_input",
                    "CanvasDirector request body must be a JSON object.",
                    400);
            }

            var root = document.RootElement;
            return new CanvasDirectorExtractRequest
            {
                Op = GetString(root, "op"),
                ExportId = GetString(root, "export_id"),
                DocumentId = GetString(root, "document_id"),
                ProposalId = GetString(root, "proposal_id"),
                SolveMode = GetString(root, "solve_mode") ?? "require_fresh_solve",
                ExpectedSolutionToken = GetString(root, "expected_solution_token"),
            };
        }

        private static string? GetString(JsonElement root, string name)
        {
            if (!root.TryGetProperty(name, out var value) ||
                value.ValueKind != JsonValueKind.String)
            {
                return null;
            }

            return value.GetString();
        }
    }

    internal sealed class CanvasDirectorException : Exception
    {
        public CanvasDirectorException(string code, string message, int httpStatus)
            : base(message)
        {
            Code = code;
            HttpStatus = httpStatus;
        }

        public string Code { get; }
        public int HttpStatus { get; }
    }

    internal sealed class CanvasDirectorExtractionEnvelope
    {
        [JsonPropertyName("canvas_export_state")]
        public JsonElement CanvasExportState { get; init; }

        [JsonPropertyName("canvas_export_state_sha256")]
        public string CanvasExportStateSha256 { get; init; } = string.Empty;

        [JsonPropertyName("diagnostics")]
        public object[] Diagnostics { get; init; } = Array.Empty<object>();

        [JsonPropertyName("suggested_spec_id")]
        public string? SuggestedSpecId { get; init; }

        [JsonPropertyName("read_only")]
        public bool ReadOnly { get; init; } = true;

        public static CanvasDirectorExtractionEnvelope FromState(object state)
        {
            using var document = JsonDocument.Parse(JsonSerializer.Serialize(state));
            var element = document.RootElement.Clone();
            return new CanvasDirectorExtractionEnvelope
            {
                CanvasExportState = element,
                CanvasExportStateSha256 = CanvasDirectorCanonicalJson.Sha256Hex(element),
            };
        }
    }

    internal interface ICanvasDirectorExtractor
    {
        CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request);
    }
}
