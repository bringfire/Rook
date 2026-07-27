using System;
using System.Threading.Tasks;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.CreationGuidProbe
{
    public sealed class BimCreationGuidProbeDispatchAwaiterTests
    {
        [Fact]
        public async Task Wait_WhenPendingAbandonmentSucceedsReturnsTimeoutWithoutWaitingForLateTask()
        {
            var completion = new TaskCompletionSource<string>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var abandonCalls = 0;

            var wait = Task.Run(() => Record.Exception(() =>
                BimCreationGuidProbeDispatchAwaiter.Wait(
                    completion.Task,
                    () =>
                    {
                        abandonCalls++;
                        return true;
                    },
                    TimeSpan.Zero)));

            var exception = await CompletesWithin(wait);

            Assert.IsType<TimeoutException>(exception);
            Assert.Equal(1, abandonCalls);
            Assert.False(completion.Task.IsCompleted);
            completion.TrySetResult("ignored late completion");
        }

        [Fact]
        public async Task Wait_WhenRunningAbandonmentFailsRemainsAttachedUntilLateCompletion()
        {
            var completion = new TaskCompletionSource<string>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var abandonAttempted = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var abandonCalls = 0;

            var wait = Task.Run(() => BimCreationGuidProbeDispatchAwaiter.Wait(
                completion.Task,
                () =>
                {
                    abandonCalls++;
                    abandonAttempted.TrySetResult(true);
                    return false;
                },
                TimeSpan.Zero));

            Assert.True(await CompletesWithin(abandonAttempted.Task));
            Assert.False(wait.IsCompleted);

            completion.TrySetResult("actual completion");

            Assert.Equal("actual completion", await CompletesWithin(wait));
            Assert.Equal(1, abandonCalls);
        }

        [Fact]
        public void Wait_WhenTaskCompletesBeforeTimeoutReturnsWithoutAbandonment()
        {
            var abandonCalls = 0;

            var result = BimCreationGuidProbeDispatchAwaiter.Wait(
                Task.FromResult("already complete"),
                () =>
                {
                    abandonCalls++;
                    return true;
                },
                TimeSpan.FromSeconds(1));

            Assert.Equal("already complete", result);
            Assert.Equal(0, abandonCalls);
        }

        private static async Task<T> CompletesWithin<T>(Task<T> task)
        {
            var winner = await Task.WhenAny(task, Task.Delay(TimeSpan.FromSeconds(2)));
            Assert.Same(task, winner);
            return await task;
        }
    }
}
