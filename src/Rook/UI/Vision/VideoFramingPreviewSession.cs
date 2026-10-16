using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.UI.Vision
{
    internal sealed class VideoFramingPreviewSession : IDisposable
    {
        private readonly object _gate = new();
        private long _latest;
        private bool _closed;
        private CancellationTokenSource? _active;
        public async Task<ApiResponse> RunAsync(long revision, Func<CancellationToken, Task<ApiResponse>> prepare, CancellationToken ct)
        {
            CancellationTokenSource own, previous;
            lock (_gate)
            {
                if (_closed || revision <= _latest) return Superseded();
                _latest = revision; previous = _active!;
                // The shared preparer owns the single 15s admission budget.
                own = CancellationTokenSource.CreateLinkedTokenSource(ct); _active = own;
            }
            Stop(previous);
            try
            {
                var result = await prepare(own.Token).ConfigureAwait(false);
                lock (_gate) return !_closed && _latest == revision && !own.IsCancellationRequested ? result : Superseded();
            }
            catch (OperationCanceledException) when (own.IsCancellationRequested) { return Superseded(); }
            finally { lock (_gate) if (ReferenceEquals(_active, own)) _active = null; own.Dispose(); }
        }
        public void Cancel(long revision)
        {
            CancellationTokenSource? previous;
            lock (_gate) { if (_closed || revision <= _latest) return; _latest = revision; previous = _active; _active = null; }
            Stop(previous);
        }
        public void Dispose()
        {
            CancellationTokenSource? previous;
            lock (_gate) { _closed = true; previous = _active; _active = null; }
            Stop(previous);
        }
        private static void Stop(CancellationTokenSource? source) { try { source?.Cancel(); } catch (ObjectDisposedException) { } }
        private static ApiResponse Superseded() => new() { Success = false, HttpStatus = 409,
            Data = new Dictionary<string, object?> { ["code"] = "cancelled", ["message"] = "Preview superseded.", ["retryable"] = false } };
    }
}
