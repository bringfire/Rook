using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Reconstruction
{
    /// <summary>
    /// Managed adapter over the native reconstruction import route. The native
    /// importer stays authoritative; this only loops a request back to it so the
    /// in-process WebView tab (Pattern A, no network) can trigger an import.
    /// </summary>
    public interface IReconstructionImportClient
    {
        Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken cancellationToken);
    }

    /// <summary>
    /// Either the unwrapped native <c>data</c> object (success) or a structured failure.
    /// The native route returns its own <c>{success,data}</c> envelope; the client unwraps
    /// it once so callers see <c>asset_role</c>/<c>imported_ids</c> at the top level.
    /// </summary>
    public sealed record NativeImportOutcome(JsonObject? Data, ReconstructionFailure? Failure)
    {
        public bool Success => Failure is null;

        public static NativeImportOutcome Ok(JsonObject data) => new(data, null);
        public static NativeImportOutcome Fail(ReconstructionFailure failure) => new(null, failure);
    }

    /// <summary>
    /// Loopback adapter to the native <c>/reconstruction/2d-to-3d/import</c> route.
    /// (Endpoint discovery and the HTTP POST land in slice-2 Tasks 2–3; this skeleton
    /// exists so routing compiles and the deadlock-invariant tests can pin the wiring.)
    /// </summary>
    public sealed class NativeReconstructionImportClient : IReconstructionImportClient
    {
        public Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken cancellationToken)
            => Task.FromResult(NativeImportOutcome.Fail(new ReconstructionFailure(
                "native_unavailable",
                "Reconstruction import endpoint not yet available.",
                Retryable: true,
                Field: null,
                Details: new Dictionary<string, object?>())));
    }
}
