using System;
using System.Threading;

namespace Rook.Services.Vision.Video
{
    internal enum VideoStopReason { User, Deadline, Shutdown }
    internal enum VideoStopPersistence { None, Pending, Durable, Failed }
    internal interface IVideoDeadlineTimer { IDisposable Schedule(DateTimeOffset deadlineUtc, Action callback); }
    internal sealed class SystemVideoDeadlineTimer : IVideoDeadlineTimer
    {
        private readonly IVideoJobClock _clock;
        public SystemVideoDeadlineTimer(IVideoJobClock clock) { _clock = clock; }
        public IDisposable Schedule(DateTimeOffset deadlineUtc, Action callback) => new Timer(_ => callback(), null, deadlineUtc <= _clock.UtcNow() ? TimeSpan.Zero : deadlineUtc - _clock.UtcNow(), Timeout.InfiniteTimeSpan);
    }
    internal sealed class VideoExecutionBudget : IDisposable
    {
        private readonly object _gate = new();
        private readonly CancellationTokenSource _cts = new();
        private readonly IVideoJobClock _clock;
        private readonly DateTimeOffset _deadline;
        private readonly IDisposable _timer;
        private int _decision;
        private VideoStopReason? _stop;
        public VideoExecutionBudget(DateTimeOffset deadlineUtc, IVideoJobClock clock, IVideoDeadlineTimer timer)
        {
            _deadline = deadlineUtc; _clock = clock; Token = _cts.Token;
            _timer = timer.Schedule(deadlineUtc, () => TryStop(VideoStopReason.Deadline));
        }
        public CancellationToken Token { get; }
        public VideoStopReason? FirstStopReason { get { lock (_gate) return _stop; } }
        public TimeSpan Remaining => _deadline > _clock.UtcNow() ? _deadline - _clock.UtcNow() : TimeSpan.Zero;
        public bool TryStop(VideoStopReason reason)
        {
            lock (_gate) { if (_decision != 0) return false; _decision = 1; _stop = reason; }
            try { _cts.Cancel(); } catch (AggregateException) { /* A transport callback cannot undo the selected stop. */ }
            return true;
        }
        public bool TryAdmitCompletion()
        {
            if (Remaining <= TimeSpan.Zero) TryStop(VideoStopReason.Deadline);
            lock (_gate) { if (_decision != 0) return false; _decision = 2; return true; }
        }
        public void Dispose() { _timer.Dispose(); lock (_gate) { if (_decision == 0) _decision = 3; } _cts.Dispose(); }
    }
}
