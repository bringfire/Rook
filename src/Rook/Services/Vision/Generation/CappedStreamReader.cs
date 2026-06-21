using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Reads a stream fully into memory while enforcing a byte cap during the
    /// read. Returns <c>null</c> when the cumulative byte count exceeds
    /// <paramref name="cap"/> (checked before the overflowing chunk is
    /// committed, so exactly-at-cap is allowed); otherwise returns the full
    /// body, which may be an empty array. Callers map the <c>null</c> overflow
    /// signal and an empty body to their own modality-specific errors.
    ///
    /// This is the single shared kernel behind the image, video, and
    /// reconstruction remote-download paths; everything above the read loop
    /// (HTTP dispatch, retry, status/error mapping, cancellation contract,
    /// MIME, Content-Length precheck) stays caller-local. net48: uses the
    /// array-based <see cref="Stream.ReadAsync(byte[],int,int,CancellationToken)"/>
    /// overload (no <c>Memory&lt;byte&gt;</c> overload available).
    /// </summary>
    internal static class CappedStreamReader
    {
        internal static async Task<byte[]?> ReadCappedAsync(
            Stream stream, long cap, CancellationToken ct)
        {
            using var ms = new MemoryStream();
            var buf = new byte[81920];
            int n;
            long total = 0;
            while ((n = await stream.ReadAsync(buf, 0, buf.Length, ct).ConfigureAwait(false)) > 0)
            {
                total += n;
                if (total > cap) return null;
                ms.Write(buf, 0, n);
            }
            return ms.ToArray();
        }
    }
}
