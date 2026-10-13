using System;
using System.Threading;
namespace Rook.Services.Vision.Image.Jobs
{
    public enum ImageStopReason { None, UserCancellation, Shutdown, Deadline }
    public sealed class ImageExecutionBudget : IDisposable
    {
        private readonly CancellationTokenSource _linked = new();
        private CancellationTokenSource? _deadline;
        private readonly CancellationTokenRegistration _userRegistration, _shutdownRegistration;
        private CancellationTokenRegistration _deadlineRegistration;
        private int _reason;
        public ImageExecutionBudget(CancellationToken userCancellation, CancellationToken shutdown,
            CancellationTokenSource? deadline)
        {
            _userRegistration = userCancellation.Register(() => Stop(ImageStopReason.UserCancellation));
            _shutdownRegistration = shutdown.Register(() => Stop(ImageStopReason.Shutdown));
            if (deadline != null) StartDeadline(deadline);
        }
        public CancellationToken Token => _linked.Token;
        public ImageStopReason StopReason => (ImageStopReason)Volatile.Read(ref _reason);
        // The execution worker attaches the timer after queue admission and owns disposal.
        internal void StartDeadline(CancellationTokenSource deadline)
        {
            if (_deadline != null) throw new InvalidOperationException("Image execution deadline already started.");
            _deadline = deadline;
            _deadlineRegistration = deadline.Token.Register(() => Stop(ImageStopReason.Deadline));
        }
        private void Stop(ImageStopReason reason)
        {
            if (Interlocked.CompareExchange(ref _reason, (int)reason, 0) == 0)
                _linked.Cancel();
        }
        public void Dispose()
        {
            _userRegistration.Dispose(); _shutdownRegistration.Dispose(); _deadlineRegistration.Dispose();
            _linked.Dispose(); _deadline?.Dispose();
        }
    }
}
