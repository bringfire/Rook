using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public static class FalNanoBananaPayload
    {
        public static string EndpointId(string model, bool hasMedia)
        {
            if (!ImageRoutingCodec.IsFalModel(model)) throw new ArgumentException("Unsupported fal model.", nameof(model));
            return model + (hasMedia ? "/edit" : "");
        }
        public static string Encode(ImageGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media)
        {
            var sources = media.Keys.Where(k => k.Role == ImageMediaRoles.InputImage).ToArray();
            if (sources.Length > 1) throw new ArgumentException("Only one primary source is supported.", "input_image_path");
            var accounted = new HashSet<MediaRef>();
            var urls = new JsonArray();
            void Add(MediaRef reference)
            {
                if (!media.TryGetValue(reference, out var bytes))
                    throw new ArgumentException("Referenced image bytes are missing.", "reference_image_paths");
                if (bytes.MimeType is not ("image/png" or "image/jpeg" or "image/webp"))
                    throw new ArgumentException("Unsupported image MIME type.", "input_image_path");
                urls.Add("data:" + bytes.MimeType + ";base64," + Convert.ToBase64String(bytes.Bytes));
                accounted.Add(reference);
            }
            foreach (var source in sources) Add(source);
            foreach (var reference in request.ReferenceImages ?? Array.Empty<MediaRef>()) Add(reference);
            if (accounted.Count != media.Count)
                throw new ArgumentException("Unaccounted image input.", "reference_image_paths");
            var body = new JsonObject
            {
                ["prompt"] = request.Prompt,
                ["aspect_ratio"] = string.IsNullOrWhiteSpace(request.AspectRatio) ? "auto" : request.AspectRatio,
                ["resolution"] = string.IsNullOrWhiteSpace(request.Resolution) ? "1K" : request.Resolution.ToUpperInvariant(),
                ["num_images"] = 1, ["output_format"] = "png", ["limit_generations"] = true, ["sync_mode"] = false
            };
            if (urls.Count > 0) body["image_urls"] = urls;
            return body.ToJsonString();
        }
    }
}
