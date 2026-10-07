using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal static class VeoInputCodec
    {
        internal static Dictionary<string, object?> BuildInstance(VideoGenerationRequest request,
            IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia)
        {
            var instance = new Dictionary<string, object?>
            {
                ["prompt"] = request.Prompt ?? string.Empty,
            };

            // Image payload shape (Vertex prediction shape — NOT inlineData):
            //   { "bytesBase64Encoded": "<b64>", "mimeType": "image/png" }
            // Lifted from SA_Banana's verified-correct shape after the
            // initial "inlineData isn't supported by this model" 400.
            if (request.StartFrame is not null
                && resolvedMedia.TryGetValue(request.StartFrame, out var startBytes))
            {
                instance["image"] = new
                {
                    bytesBase64Encoded = Convert.ToBase64String(startBytes.Bytes),
                    mimeType = startBytes.MimeType,
                };
            }

            if (request.EndFrame is not null
                && resolvedMedia.TryGetValue(request.EndFrame, out var endBytes))
            {
                instance["lastFrame"] = new
                {
                    bytesBase64Encoded = Convert.ToBase64String(endBytes.Bytes),
                    mimeType = endBytes.MimeType,
                };
            }

            if (request.ReferenceFrames is { Count: > 0 } refs)
            {
                var refList = new List<object>(refs.Count);
                foreach (var r in refs)
                {
                    if (!resolvedMedia.TryGetValue(r, out var refBytes)) continue;
                    refList.Add(new
                    {
                        image = new
                        {
                            bytesBase64Encoded = Convert.ToBase64String(refBytes.Bytes),
                            mimeType = refBytes.MimeType,
                        },
                        referenceType = "asset",
                    });
                }
                if (refList.Count > 0) instance["referenceImages"] = refList;
            }

            return instance;
        }
    }
}
