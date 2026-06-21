using System;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionDownloadResult(bool Success, byte[]? Bytes, string? MimeType, GenerationError? Error);

public interface IReconstructionRemoteAssetDownloader
{
    Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct);
}

/// <summary>
/// Disciplined async downloader for reconstruction package assets: absolute-https only,
/// header-read streaming, role-aware byte cap (enforced from Content-Length AND while streaming),
/// transient-transport-only retry. User cancellation rethrows and never retries; programmer/validation
/// errors propagate; every observed failure becomes a typed <see cref="GenerationError"/>.
///
/// Reconstruction-owned for now, with a deliberately small interface so a later shared media downloader
/// across image/video/reconstruction is a lift, not a rewrite (see substrate-trajectory in the spec).
/// </summary>
public sealed class ReconstructionRemoteAssetDownloader : IReconstructionRemoteAssetDownloader
{
    private readonly HttpClient _http;
    private readonly Func<string, long> _maxBytesByRole;
    private const int MaxAttempts = 3;

    public ReconstructionRemoteAssetDownloader(HttpClient http, Func<string, long> maxBytesByRole)
    {
        _http = http ?? throw new ArgumentNullException(nameof(http));
        _maxBytesByRole = maxBytesByRole ?? throw new ArgumentNullException(nameof(maxBytesByRole));
    }

    public async Task<ReconstructionDownloadResult> DownloadAsync(Uri url, string role, CancellationToken ct)
    {
        if (url is null || !url.IsAbsoluteUri || url.Scheme != Uri.UriSchemeHttps)
            return Fail(GenerationErrorCode.InvalidRequest, "Asset URL must be absolute HTTPS.");

        var cap = _maxBytesByRole(role);
        for (var attempt = 1; ; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                using var resp = await _http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false);
                if (!resp.IsSuccessStatusCode)
                {
                    if (IsTransientStatus((int)resp.StatusCode) && attempt < MaxAttempts) continue;
                    return Fail(GenerationErrorCode.DependencyUnavailable, $"Asset download failed: HTTP {(int)resp.StatusCode}.");
                }

                if (resp.Content.Headers.ContentLength is { } len && len > cap)
                    return Fail(GenerationErrorCode.UnsupportedMedia, $"Asset exceeds {cap} bytes (declared {len}).");

                var mime = resp.Content.Headers.ContentType?.MediaType;
                // net48: HttpContent.ReadAsStreamAsync has no CancellationToken overload.
                using var stream = await resp.Content.ReadAsStreamAsync().ConfigureAwait(false);
                var bytes = await CappedStreamReader.ReadCappedAsync(stream, cap, ct).ConfigureAwait(false);
                if (bytes is null) return Fail(GenerationErrorCode.UnsupportedMedia, $"Asset exceeds {cap} bytes while streaming.");
                if (bytes.Length == 0) return Fail(GenerationErrorCode.ExecutionFailed, "Asset body was empty.");
                return new ReconstructionDownloadResult(true, bytes, mime, null);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                throw; // user cancellation: never retry, never swallow
            }
            catch (Exception ex) when (IsTransientTransport(ex) && attempt < MaxAttempts)
            {
                // transient transport error or HTTP client timeout: retry
            }
            catch (Exception ex) when (IsTransientTransport(ex))
            {
                return Fail(GenerationErrorCode.DependencyUnavailable, $"Asset download error: {ex.Message}");
            }
            // Any other exception type (programmer/validation error) is intentionally NOT caught here -> propagates.
        }
    }

    // TaskCanceledException here is the HttpClient-timeout case; user cancellation is handled by the
    // filtered OperationCanceledException catch above, which rethrows before reaching this.
    private static bool IsTransientTransport(Exception ex) => ex is HttpRequestException || ex is TaskCanceledException;
    private static bool IsTransientStatus(int s) => s >= 500 || s == 408 || s == 429;

    private static ReconstructionDownloadResult Fail(GenerationErrorCode c, string m) =>
        new(false, null, null, new GenerationError(c, m, Retryable: c == GenerationErrorCode.DependencyUnavailable));
}
