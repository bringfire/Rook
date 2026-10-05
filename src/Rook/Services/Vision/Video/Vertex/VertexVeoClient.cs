using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Generation.Vertex;
using Rook.Services.Vision.Image.Vertex;

namespace Rook.Services.Vision.Video.Vertex
{
    internal sealed record VertexVeoResponse(string? Operation = null, bool Done = false, byte[]? Video = null,
        GenerationError? Error = null, bool RetryableRead = false);

    // No retained operation state or output bodies. Status validates without decoding; fetch decodes once.
    internal sealed class VertexVeoClient
    {
        internal const int DecodedLimit = 250 * 1024 * 1024;
        internal const long WireLimit = 4L * ((DecodedLimit + 2L) / 3) + 1024 * 1024;
        private readonly VertexMediaTransport _transport;
        internal VertexVeoClient(HttpClient? http = null) => _transport = new VertexMediaTransport(http);
        internal static bool ValidOperation(VertexAuthorizationBinding binding, string operation)
        {
            if (!VertexMediaTransport.ValidBinding(binding) || binding.ModelId != VertexVeoProvider.ModelKey) return false;
            var prefix = VertexMediaTransport.ModelPath(binding) + "/operations/";
            return operation.StartsWith(prefix, StringComparison.Ordinal)
                && Regex.IsMatch(operation.Substring(prefix.Length), "^[A-Za-z0-9_-]{1,128}$");
        }
        internal async Task<VertexVeoResponse> SubmitAsync(VertexAuthorizationBinding binding, string token,
            VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolved, CancellationToken ct, Action? beforeDispatch = null)
        {
            var options = (VertexVeoOptions)request.Options;
            var parameters = new Dictionary<string, object>
            {
                ["sampleCount"] = 1, ["durationSeconds"] = request.DurationSeconds,
                ["aspectRatio"] = request.AspectRatio, ["resolution"] = request.Resolution,
                ["personGeneration"] = VertexVeoOptionsCodec.WireValue(options.PersonGeneration)!, ["generateAudio"] = true,
            };
            if (request.Seed.HasValue) parameters["seed"] = request.Seed.Value;
            var body = JsonSerializer.Serialize(new { instances = new[] { VeoInputCodec.BuildInstance(request, resolved) }, parameters });
            var response = await _transport.PostAsync(binding, token, "predictLongRunning", body,
                VertexMediaTransport.SmallResponseLimit, true, ct, beforeDispatch).ConfigureAwait(false);
            if (response.Error is not null) return new(Error: response.Error);
            try
            {
                using var doc = JsonDocument.Parse(response.Body!);
                var operation = doc.RootElement.GetProperty("name").GetString();
                if (operation is not null && ValidOperation(binding, operation)) return new(Operation: operation);
            }
            catch { }
            return new(Error: VertexMediaTransport.UnknownSubmission());
        }
        internal async Task<VertexVeoResponse> FetchOperationAsync(VertexAuthorizationBinding binding, string token,
            string operation, bool decodeVideo, CancellationToken ct)
        {
            if (!ValidOperation(binding, operation)) return new(Error: VertexMediaTransport.Interrupted());
            var response = await _transport.PostAsync(binding, token, "fetchPredictOperation",
                JsonSerializer.Serialize(new { operationName = operation }), WireLimit, false, ct).ConfigureAwait(false);
            if (response.Error is not null) return new(Error: response.Error, RetryableRead: response.RetryableRead);
            return ParseOperation(response.Body!, operation, decodeVideo);
        }
        internal static VertexVeoResponse ParseOperation(byte[] body, string operation, bool decodeVideo)
        {
            try
            {
                if (!VertexMediaTransport.ValidateEncodedFields(body, "bytesBase64Encoded", DecodedLimit))
                    return new(Error: VertexMediaTransport.InvalidOutput());
                using var doc = JsonDocument.Parse(body);
                var root = doc.RootElement;
                if (root.TryGetProperty("name", out var name) && name.GetString() != operation)
                    return new(Error: VertexMediaTransport.InvalidOutput());
                if (root.TryGetProperty("error", out _)) return new(Error: VertexMediaTransport.InvalidOutput());
                if (!root.TryGetProperty("done", out var done) || !done.GetBoolean()) return new(Done: false);
                var result = root.GetProperty("response");
                if (result.TryGetProperty("raiMediaFilteredCount", out var filtered) && filtered.GetInt32() > 0)
                    return new(Error: new GenerationError(GenerationErrorCode.ContentPolicy, "Google filtered this video request.", false));
                var videos = result.GetProperty("videos");
                if (videos.ValueKind != JsonValueKind.Array || videos.GetArrayLength() != 1)
                    return new(Error: VertexMediaTransport.InvalidOutput());
                var video = videos[0];
                if (video.GetProperty("mimeType").GetString() != "video/mp4"
                    || video.TryGetProperty("gcsUri", out _) || video.TryGetProperty("uri", out _)
                    || !video.TryGetProperty("bytesBase64Encoded", out var encoded))
                    return new(Error: VertexMediaTransport.InvalidOutput());
                // The raw UTF-8 validation above covers length, alphabet, and padding without a UTF-16 copy.
                return new(Done: true, Video: decodeVideo ? encoded.GetBytesFromBase64() : null);
            }
            catch { return new(Error: VertexMediaTransport.InvalidOutput()); }
        }
    }
}
