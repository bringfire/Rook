using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Services.Vision.Video
{
    // Only prepared dispatch uses this streaming content. Image bytes never become
    // whole-image base64 strings or a second JSON payload buffer.
    internal sealed class VeoPreparedContent : HttpContent
    {
        private sealed record Part(byte[]? Text, VideoPreparedMediaSlot? Image);
        private readonly object _gate = new();
        private readonly List<Part> _parts = new();
        private readonly SemaphoreSlim _serial = new(1, 1);
        private readonly CancellationToken _ct;
        private readonly long _length;
        private VideoBufferReservation? _reservation;
        private byte[] _raw = Array.Empty<byte>(), _ascii = Array.Empty<byte>();
        private char[] _base64 = Array.Empty<char>();
        private int _active;
        private bool _disposed;
        public VeoPreparedContent(VideoGenerationRequest request, VideoPreparedMediaSnapshot media,
            object parameters, VideoPreparationLease phase, CancellationToken ct)
        {
            _ct = ct;
            // Conservative pre-allocation ceiling includes escaped text, serializer
            // growth/temporary strings, encoded fragments, and all fixed scratch arrays.
            long textUnits = (request.Prompt?.Length ?? 0) + request.AspectRatio.Length + request.Resolution.Length + media.Slots.Sum(s => (long)s.MimeType.Length);
            long capacity = 1_048_576 + textUnits * 64;
            if (capacity > VideoPreparationLimits.TransientBytes) throw new VideoPreparationBusyException();
            _reservation = phase.Buffers.Reserve((int)capacity);
            try
            {
                _raw = new byte[49_152]; _base64 = new char[65_536]; _ascii = new byte[65_536];
                Headers.ContentType = new MediaTypeHeaderValue("application/json") { CharSet = "utf-8" };
                Text("{\"instances\":[{\"prompt\":" + JsonSerializer.Serialize(request.Prompt ?? ""));
                foreach (var slot in media.Slots.Where(s => s.Role is "start_frame" or "end_frame"))
                { Text(slot.Role == "start_frame" ? ",\"image\":" : ",\"lastFrame\":"); Image(slot); }
                var references = media.Slots.Where(s => s.Role.StartsWith("reference_frames[", StringComparison.Ordinal)).ToArray();
                if (references.Length > 0)
                {
                    Text(",\"referenceImages\":[");
                    for (int i = 0; i < references.Length; i++) { Text(i == 0 ? "{\"image\":" : ",{\"image\":"); Image(references[i]); Text(",\"referenceType\":\"asset\"}"); }
                    Text("]");
                }
                Text("}],\"parameters\":" + JsonSerializer.Serialize(parameters) + "}");
                _length = _parts.Sum(p => p.Text?.LongLength ?? checked(((long)p.Image!.ByteLength + 2) / 3 * 4));
            }
            catch { Release(); throw; }
        }
        private void Text(string value) => _parts.Add(new(Encoding.UTF8.GetBytes(value), null));
        private void Image(VideoPreparedMediaSlot slot)
        { Text("{\"bytesBase64Encoded\":\""); _parts.Add(new(null, slot)); Text("\",\"mimeType\":" + JsonSerializer.Serialize(slot.MimeType) + "}"); }
        protected override bool TryComputeLength(out long length) { length = _length; return true; }
        protected override async Task SerializeToStreamAsync(Stream target, TransportContext? context)
        {
            lock (_gate) { if (_disposed) throw new ObjectDisposedException(nameof(VeoPreparedContent)); _active++; }
            bool entered = false;
            try
            {
                await _serial.WaitAsync(_ct).ConfigureAwait(false); entered = true;
                foreach (var part in _parts)
                {
                    CheckOpen();
                    if (part.Text != null) { await target.WriteAsync(part.Text, 0, part.Text.Length, _ct).ConfigureAwait(false); continue; }
                    using var source = part.Image!.OpenRead();
                    while (source.Position < source.Length)
                    {
                        CheckOpen();
                        // Keep all nonfinal chunks divisible by three: no interior padding.
                        int wanted = (int)Math.Min(_raw.Length, source.Length - source.Position), total = 0;
                        while (total < wanted) { int read = await source.ReadAsync(_raw, total, wanted - total, _ct).ConfigureAwait(false); if (read <= 0) throw new IOException("Prepared source ended early."); total += read; }
                        int chars = Convert.ToBase64CharArray(_raw, 0, total, _base64, 0);
                        int count = Encoding.ASCII.GetBytes(_base64, 0, chars, _ascii, 0);
                        await target.WriteAsync(_ascii, 0, count, _ct).ConfigureAwait(false);
                    }
                }
            }
            finally
            {
                if (entered) _serial.Release();
                lock (_gate) { _active--; if (_disposed && _active == 0) Release(); }
            }
        }
        private void CheckOpen() { _ct.ThrowIfCancellationRequested(); lock (_gate) if (_disposed) throw new ObjectDisposedException(nameof(VeoPreparedContent)); }
        private void Release()
        { _parts.Clear(); _raw = Array.Empty<byte>(); _ascii = Array.Empty<byte>(); _base64 = Array.Empty<char>(); Interlocked.Exchange(ref _reservation, null)?.Dispose(); }
        protected override void Dispose(bool disposing)
        { if (disposing) lock (_gate) { _disposed = true; if (_active == 0) Release(); } base.Dispose(disposing); }
    }
}
