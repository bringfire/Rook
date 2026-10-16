using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Tests
{
    // A synchronous WaitHandle/bridge operation must not depend on a free pool
    // worker while the test itself blocks waiting for its handshake.
    internal sealed class BlockingTestWorker<T> : IDisposable
    {
        private readonly CancellationTokenSource _stop = new();
        internal Task<T> Task { get; }

        internal BlockingTestWorker(Func<CancellationToken, T> operation)
        {
            Task = System.Threading.Tasks.Task.Factory.StartNew(() => operation(_stop.Token),
                CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        }

        public void Dispose()
        {
            _stop.Cancel();
            try
            {
                if (!Task.Wait(TimeSpan.FromSeconds(10)))
                    throw new TimeoutException("The owned blocking test worker did not stop after cancellation.");
            }
            catch (AggregateException ex) when (ex.InnerExceptions.All(e => e is OperationCanceledException)) { }
            finally { if (Task.IsCompleted) _stop.Dispose(); }
        }
    }
}
