using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Fal
{
    public sealed class FalMediaPreparation
    {
        private readonly FalApiClient _client;
        private readonly Func<string?> _apiKeyProvider;
        public FalMediaPreparation(FalApiClient client, Func<string?> apiKeyProvider)
        { _client = client ?? throw new ArgumentNullException(nameof(client)); _apiKeyProvider = apiKeyProvider ?? throw new ArgumentNullException(nameof(apiKeyProvider)); }
        public async Task<IReadOnlyList<FalPreparedMedia>> PrepareAsync(FalNormalizedRequest request, FalMediaSnapshot media, CancellationToken ct)
        {
            var error = media.Validate(request);
            if (error != null) throw new FalMediaPreparationException(error);
            using var phase = media.Slots.Count == 0 ? null : await VideoPreparationResources.Shared.AcquireAsync(ct).ConfigureAwait(false);
            var prepared = new List<FalPreparedMedia>();
            var uploaded = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var slot in media.Slots)
            {
                ct.ThrowIfCancellationRequested();
                using var owned = slot.CopyOwned(phase!.Buffers);
                var bytes = owned.Bytes;
                try
                {
                    string value;
                    if (slot.Transport == "data_uri") value = "data:" + slot.MimeType + ";base64," + Convert.ToBase64String(bytes);
                    else if (!uploaded.TryGetValue(slot.MimeType + ":" + slot.Sha256, out value))
                    {
                        value = await _client.UploadFileToCdnAsync(_apiKeyProvider() ?? "", "rook-configured-source." + Extension(slot.MimeType), bytes, slot.MimeType,
                            FalUploadPlatformHeaders.ForSourceUpload(3600), ct).ConfigureAwait(false);
                        uploaded.Add(slot.MimeType + ":" + slot.Sha256, value);
                    }
                    prepared.Add(new FalPreparedMedia(slot.Role, slot.Ordinal, value));
                }
                finally { Array.Clear(bytes, 0, bytes.Length); }
            }
            return prepared.AsReadOnly();
        }
        private static string Extension(string mime) => mime == "image/png" ? "png" : mime == "image/jpeg" ? "jpg" : "webp";
    }
    public sealed class FalMediaPreparationException : Exception
    {
        public GenerationError Error { get; }
        internal FalMediaPreparationException(GenerationError error) : base(error.Message) { Error = error; }
    }
}
