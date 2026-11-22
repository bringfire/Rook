using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public sealed class FalExecutionRecovery
    {
        private readonly FalConfiguredExecutor _executor;
        public FalExecutionRecovery(FalConfiguredExecutor executor) => _executor = executor ?? throw new ArgumentNullException(nameof(executor));
        public Task<ProviderCancelOutcome> CancelAsync(FalExecutionSnapshot snapshot, CancellationToken ct)
        {
            var validated = FalExecutionSnapshotCodec.Deserialize(FalExecutionSnapshotCodec.Serialize(snapshot));
            if (!validated.CleanupAvailable) return Task.FromResult<ProviderCancelOutcome>(new FailedCancelOutcome(Unavailable(validated.Diagnostic)));
            return _executor.CancelAsync(validated.Snapshot!.Binding, validated.Snapshot.Handle!, ct);
        }
        internal static GenerationError Unavailable(string? reason = null) => new(GenerationErrorCode.DependencyUnavailable,
            reason ?? "Configured fal remote cleanup is unavailable; no validated durable handle or recovery service exists.", false, ProviderErrorCode: "configured_cleanup_unavailable");
    }
}
