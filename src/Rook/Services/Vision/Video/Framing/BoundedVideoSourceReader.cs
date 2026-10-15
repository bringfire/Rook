using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed record VideoSourceReadResult(VideoFrozenBuffer? Buffer, GenerationError? Error);
    internal static class BoundedVideoSourceReader
    {
        public static Task<VideoSourceReadResult> ReadAsync(Stream opened, long initialLength, string field,
            VideoPreparationLease lease, CancellationToken ct)
            => ReadCoreAsync(opened, initialLength, field, lease, true, VideoPreparationLimits.OriginalBytes, ct);

        internal static Task<VideoSourceReadResult> ReadOutputAsync(Stream opened, long initialLength, string field,
            VideoPreparationLease lease, CancellationToken ct)
            => ReadCoreAsync(opened, initialLength, field, lease, false, VideoPreparationLimits.UploadBytes, ct);

        private static async Task<VideoSourceReadResult> ReadCoreAsync(Stream opened, long initialLength, string field,
            VideoPreparationLease lease, bool original, long maxBytes, CancellationToken ct)
        {
            VideoBufferReservation? payloadReservation = null;
            try
            {
                ct.ThrowIfCancellationRequested();
                if (initialLength <= 0) return Changed(field);
                if (initialLength > maxBytes || original && !lease.AdmitOriginal(initialLength))
                    return new(null, VideoSourcePreparationErrors.Create("source_input_too_large", field));
                if (opened.Length != initialLength) return Changed(field);
                payloadReservation = lease.Buffers.Reserve(checked((int)initialLength));
                using var scratchReservation = lease.Buffers.Reserve(VideoPreparationLimits.ChunkBytes);
                using var probeReservation = lease.Buffers.Reserve(1);
                var bytes = new byte[(int)initialLength];
                int total = 0;
                while (total < bytes.Length)
                {
                    ct.ThrowIfCancellationRequested();
                    int count = Math.Min(VideoPreparationLimits.ChunkBytes, bytes.Length - total);
                    int read = await opened.ReadAsync(bytes, total, count, ct).ConfigureAwait(false);
                    if (read <= 0 || read > count) return Changed(field);
                    total = checked(total + read);
                }
                var probe = new byte[1];
                if (await opened.ReadAsync(probe, 0, 1, ct).ConfigureAwait(false) != 0 || opened.Length != initialLength)
                    return Changed(field);
                ct.ThrowIfCancellationRequested();
                var frozen = VideoFrozenBuffer.Adopt(bytes, payloadReservation, VideoFrozenBuffer.Hash(bytes));
                payloadReservation = null;
                return new(frozen, null);
            }
            catch (OperationCanceledException) { throw; }
            catch (VideoPreparationBusyException) { return new(null, VideoSourcePreparationErrors.Busy(field)); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException or OverflowException)
            { return Changed(field); }
            finally { payloadReservation?.Dispose(); }
        }
        private static VideoSourceReadResult Changed(string field) => new(null, VideoSourcePreparationErrors.Create("source_changed", field));
    }
}
