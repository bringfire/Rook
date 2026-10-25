using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    internal sealed class FalDurableExecutionObserver : IFalExecutionObserver
    {
        private readonly Action<ProviderJobHandle?, CancellationToken> _commit;
        private readonly Func<CancellationTokenSource> _durabilityBudgetFactory;
        internal ProviderJobHandle? KnownHandle { get; private set; }
        internal FalDurableExecutionObserver(Action<ProviderJobHandle?, CancellationToken> commit, Func<CancellationTokenSource>? durabilityBudgetFactory = null)
        { _commit = commit; _durabilityBudgetFactory = durabilityBudgetFactory ?? NewDurabilityBudget; }
        internal static CancellationTokenSource NewDurabilityBudget() => new(TimeSpan.FromSeconds(10));
        public Task<GenerationError?> BeforeUploadAsync(CancellationToken ct)
        { ct.ThrowIfCancellationRequested(); return Task.FromResult<GenerationError?>(null); }
        public Task<GenerationError?> BeforeDispatchAsync(CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            _commit(null, ct);
            return Task.FromResult<GenerationError?>(null);
        }
        public Task AcceptedAsync(ProviderJobHandle handle, CancellationToken ct)
        {
            // Acceptance belongs to the job, even if the caller stopped while POST settled.
            // Ledgers are synchronous; the token bounds admission to the write, not filesystem I/O.
            using var durability = _durabilityBudgetFactory();
            KnownHandle = handle;
            _commit(handle, durability.Token);
            return Task.CompletedTask;
        }
        internal FalExecutionSnapshot Settled(FalExecutionSnapshot snapshot, ProviderSubmitOutcome outcome)
        {
            var settled = snapshot.WithOutcome(outcome);
            return settled.DispatchState == "unknown" && KnownHandle != null ? settled.WithDispatchState("unknown", KnownHandle) : settled;
        }
        internal static IDisposable EnterGate(object gate, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            if (!Monitor.TryEnter(gate, TimeSpan.FromSeconds(10))) throw new TimeoutException("Configured durability admission timed out.");
            return new GateLease(gate);
        }
        private sealed class GateLease : IDisposable
        {
            private readonly object _gate;
            internal GateLease(object gate) => _gate = gate;
            public void Dispose() => Monitor.Exit(_gate);
        }
    }
}
