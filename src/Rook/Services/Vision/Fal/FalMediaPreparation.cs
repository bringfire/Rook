using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Fal
{
    public sealed class FalMediaPreparation
    {
        internal const int MaxCdnUrlCharacters = 4096;
        private readonly FalApiClient _client;
        private readonly Func<string?> _apiKeyProvider;
        public FalMediaPreparation(FalApiClient client, Func<string?> apiKeyProvider)
        { _client = client ?? throw new ArgumentNullException(nameof(client)); _apiKeyProvider = apiKeyProvider ?? throw new ArgumentNullException(nameof(apiKeyProvider)); }
        public async Task<IReadOnlyList<FalPreparedMedia>> PrepareAsync(FalNormalizedRequest request, FalMediaSnapshot media, CancellationToken ct)
        {
            var batch = await PrepareOwnedAsync(request, media, ct).ConfigureAwait(false);
            // This compatibility seam transfers its reservation to the snapshot. Values may be
            // used only while that snapshot remains alive. Executor uses the explicit batch seam.
            media.OwnValues(batch);
            return batch.Values;
        }

        internal async Task<FalPreparedMediaBatch> PrepareOwnedAsync(FalNormalizedRequest request, FalMediaSnapshot media, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            var error = media.Validate(request);
            if (error != null) throw new FalMediaPreparationException(error);
            var prepared = new List<FalPreparedMedia>();
            var envelope = ReserveEnvelope(request, media);
            var batch = new FalPreparedMediaBatch(prepared, envelope.Reservation, envelope.MaxSerializedBytes);
            try
            {
                var uploaded = new Dictionary<string, string>(StringComparer.Ordinal);
                foreach (var slot in media.Slots)
                {
                    ct.ThrowIfCancellationRequested();
                    var bytes = slot.CopyForPreparedBatch();
                    try
                    {
                        string value;
                        if (slot.Transport == "data_uri") value = "data:" + slot.MimeType + ";base64," + Convert.ToBase64String(bytes);
                        else if (!uploaded.TryGetValue(slot.MimeType + ":" + slot.Sha256, out value))
                        {
                            value = await _client.UploadFileToCdnAsync(_apiKeyProvider() ?? "", "rook-configured-source." + Extension(slot.MimeType), bytes, slot.MimeType,
                                FalUploadPlatformHeaders.ForSourceUpload(3600), ct).ConfigureAwait(false);
                            if (value.Length > MaxCdnUrlCharacters) throw PayloadLimit();
                            uploaded.Add(slot.MimeType + ":" + slot.Sha256, value);
                        }
                        prepared.Add(new FalPreparedMedia(slot.Role, slot.Ordinal, value));
                    }
                    finally { Array.Clear(bytes, 0, bytes.Length); }
                }
                return batch;
            }
            catch { batch.Dispose(); throw; }
        }

        private static (VideoBufferReservation Reservation, long MaxSerializedBytes) ReserveEnvelope(FalNormalizedRequest request, FalMediaSnapshot media)
        {
            // Unlike an original-byte ceiling, this covers retained UTF-16 data URIs, their
            // conversion/concatenation temporaries, escaped JSON writer growth and final text,
            // and UTF-8 StringContent bytes throughout the awaited HTTP call. Existing originals
            // and compatibility copies are already charged to this same admitted owner.
            long units = request.EffectiveInputCharacterUnits;
            if (units > VideoPreparationLimits.TransientBytes / 128) throw PayloadLimit();
            // Catalog files have a compiled 1 MiB ceiling. Reserve conservative DOM/string
            // scratch before inspecting their cloned lookup/constant getters. Scalar controls
            // use the cached bound above, so even their getter clones wait for final admission.
            VideoBufferReservation scratch;
            try { scratch = media.Phase.Buffers.Reserve(32 * 1024 * 1024); }
            catch (VideoPreparationBusyException) { throw PayloadLimit(); }
            long capacity, wire;
            using (scratch)
            {
                foreach (var field in request.Binding.Fields) units += field.Payload.Pointer.Length + field.Key.Length + 64 + JsonUnits(field.Payload.Lookup);
                foreach (var constant in request.Binding.Constants) units += constant.Pointer.Length + 64 + JsonUnits(constant.Value);
                capacity = 1_048_576 + units * 128;
                wire = 1_048_576 + units * 6;
                long largestCopy = media.Slots.Count == 0 ? 0 : media.Slots.Max(s => s.ByteLength);
                capacity += largestCopy;
                // Reject obvious aggregate expansion before scanning immutable base64 sextets.
                long minimum = capacity;
                foreach (var slot in media.Slots)
                    minimum += slot.Transport == "data_uri" ? DataUriCharacters(slot) * 12 : MaxCdnUrlCharacters * 52L;
                if (minimum > VideoPreparationLimits.TransientBytes) throw PayloadLimit();
                foreach (var slot in media.Slots)
                {
                    if (slot.Transport == "data_uri")
                    {
                        long raw = DataUriCharacters(slot);
                        long encoded = slot.Read(bytes => DataUriJsonCharacters(bytes, slot.MimeType));
                        capacity += raw * 4 + encoded * 8;
                        wire += encoded + 2;
                    }
                    else
                    {
                        capacity += MaxCdnUrlCharacters * 52L;
                        wire += MaxCdnUrlCharacters * 6L + 2;
                    }
                }
                if (capacity > VideoPreparationLimits.TransientBytes) throw PayloadLimit();
            }
            try { return (media.Phase.Buffers.Reserve((int)capacity), wire); }
            catch (VideoPreparationBusyException) { throw PayloadLimit(); }
        }

        private static long JsonUnits(JsonNode? node)
        {
            if (node == null) return 4;
            if (node is JsonObject obj) return 2 + obj.Sum(p => (long)p.Key.Length + 4 + JsonUnits(p.Value));
            if (node is JsonArray array) return 2 + array.Sum(n => 1 + JsonUnits(n));
            return node.GetValueKind() == JsonValueKind.String ? node.GetValue<string>().Length + 2L : node.ToJsonString().Length;
        }
        private static long DataUriCharacters(FalMediaSnapshotSlot slot) => 13 + slot.MimeType.Length + (slot.ByteLength + 2) / 3 * 4;
        private static long DataUriJsonCharacters(ReadOnlySpan<byte> bytes, string mime)
        {
            const string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
            long length = 0;
            foreach (var c in "data:" + mime + ";base64,") length += JsonAsciiCharacters(c);
            for (int i = 0; i < bytes.Length; i += 3)
            {
                int a = bytes[i], b = i + 1 < bytes.Length ? bytes[i + 1] : 0, c = i + 2 < bytes.Length ? bytes[i + 2] : 0;
                length += JsonAsciiCharacters(alphabet[a >> 2]);
                length += JsonAsciiCharacters(alphabet[((a & 3) << 4) | (b >> 4)]);
                length += JsonAsciiCharacters(i + 1 < bytes.Length ? alphabet[((b & 15) << 2) | (c >> 6)] : '=');
                length += JsonAsciiCharacters(i + 2 < bytes.Length ? alphabet[c & 63] : '=');
            }
            return length;
        }
        private static int JsonAsciiCharacters(char c) => JavaScriptEncoder.Default.WillEncode(c) ? 6 : 1;
        private static FalMediaPreparationException PayloadLimit() => new(new GenerationError(GenerationErrorCode.InvalidRequest,
            "Configured fal source encoding and request payload exceed the shared runtime memory ceiling; use smaller sources or controls.", false, "media", "media_payload_limit"));
        private static string Extension(string mime) => mime == "image/png" ? "png" : mime == "image/jpeg" ? "jpg" : "webp";
    }

    /// <summary>Owns the conservative payload envelope until serialization and paid HTTP settle.
    /// It remains charged even if the original snapshot is disposed during an in-flight call.</summary>
    internal sealed class FalPreparedMediaBatch : IDisposable
    {
        private readonly List<FalPreparedMedia> _values;
        private VideoBufferReservation? _reservation;
        internal IReadOnlyList<FalPreparedMedia> Values { get; }
        internal long MaxSerializedBytes { get; }
        internal FalPreparedMediaBatch(List<FalPreparedMedia> values, VideoBufferReservation reservation, long maxSerializedBytes)
        { _values = values; Values = values.AsReadOnly(); _reservation = reservation; MaxSerializedBytes = maxSerializedBytes; }
        public void Dispose() { _values.Clear(); Interlocked.Exchange(ref _reservation, null)?.Dispose(); }
    }
    public sealed class FalMediaPreparationException : Exception
    {
        public GenerationError Error { get; }
        internal FalMediaPreparationException(GenerationError error) : base(error.Message) { Error = error; }
    }
}
