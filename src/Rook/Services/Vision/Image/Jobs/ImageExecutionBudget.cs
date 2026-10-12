using System;
using System.Threading;
namespace Rook.Services.Vision.Image.Jobs
{
    public enum ImageStopReason { None, UserCancellation, Shutdown, Deadline }
    public sealed class ImageExecutionBudget : IDisposable
    {
        private readonly CancellationTokenSource _linked = new();
        private readonly CancellationTokenSource? _deadline;
        private readonly CancellationTokenRegistration _userRegistration, _shutdownRegistration, _deadlineRegistration;
        private int _reason;
        public ImageExecutionBudget(CancellationToken userCancellation, CancellationToken shutdown,
            CancellationTokenSource? deadline)
        {
            _deadline = deadline;
            _userRegistration = userCancellation.Register(() => Stop(ImageStopReason.UserCancellation));
            _shutdownRegistration = shutdown.Register(() => Stop(ImageStopReason.Shutdown));
            _deadlineRegistration = deadline?.Token.Register(() => Stop(ImageStopReason.Deadline)) ?? default;
        }
        public CancellationToken Token => _linked.Token;
        public ImageStopReason StopReason => (ImageStopReason)Volatile.Read(ref _reason);
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
