using System.Threading;
using Rook.Services.Vision.Image.Jobs;
using Xunit;
namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageExecutionBudgetTests
    {
        [Theory]
        [InlineData(ImageStopReason.UserCancellation)]
        [InlineData(ImageStopReason.Shutdown)]
        [InlineData(ImageStopReason.Deadline)]
        public void FirstObservedStopReasonWins(ImageStopReason first)
        {
            using var user = new CancellationTokenSource();
            using var shutdown = new CancellationTokenSource();
            var deadline = new CancellationTokenSource();
            using var budget = new ImageExecutionBudget(user.Token, shutdown.Token, deadline);
            var firstSource = first == ImageStopReason.UserCancellation ? user :
                first == ImageStopReason.Shutdown ? shutdown : deadline;
            firstSource.Cancel();
            Assert.True(budget.Token.IsCancellationRequested);
            user.Cancel(); shutdown.Cancel(); deadline.Cancel();
            Assert.Equal(first, budget.StopReason);
        }
    }
}
