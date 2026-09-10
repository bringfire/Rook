using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Xunit;
using Xunit.Abstractions;

namespace Rook.Tests.UI.Chat
{
    public sealed class ConversationCloseCoordinatorTests
    {
        private readonly ITestOutputHelper _output;

        public ConversationCloseCoordinatorTests(ITestOutputHelper output) => _output = output;

        [Theory]
        [InlineData("completed-close", true)]
        [InlineData("deadline-expired", false)]
        [InlineData("empty-queue", true)]
        public void Shutdown_style_synchronous_drain_completes_without_context_pumping(
            string scenario, bool expectedResult)
        {
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            bool completedWithoutPump = false;
            bool? result = null;
            int queuedBeforeCleanup = 0;
            int pumpedDuringCleanup = 0;
            bool closeWorkSettled = false;
            Exception? failure = null;
            var thread = new Thread(() =>
            {
                var context = new QueuedSingleThreadContext();
                using var coordinator = ConversationCloseCoordinator.ForTests((_, _, _, _) => release.Task);
                Task<bool>? drain = null;
                try
                {
                    SynchronizationContext.SetSynchronizationContext(context);
                    if (scenario != "empty-queue")
                        coordinator.Enqueue(new ConversationCloseRequest(
                            new Uri("http://127.0.0.1:8765"), "shutdown-control", null));

                    drain = coordinator.DrainAsync(TimeSpan.FromMilliseconds(100));
                    if (scenario == "completed-close") release.TrySetResult(true);

                    // Match shutdown's blocking, non-pumping caller, but put a safety
                    // deadline on the wait before calling GetResult. Never strand a thread.
                    completedWithoutPump = drain.Wait(TimeSpan.FromSeconds(2));
                    queuedBeforeCleanup = context.PendingCount;
                    if (completedWithoutPump) result = drain.GetAwaiter().GetResult();
                }
                catch (Exception ex)
                {
                    failure = ex;
                }
                finally
                {
                    release.TrySetResult(true);
                    try
                    {
                        // Evidence above is frozen before cleanup pumps this same thread.
                        var cleanup = Stopwatch.StartNew();
                        while (drain != null && !drain.IsCompleted && cleanup.Elapsed < TimeSpan.FromSeconds(2))
                        {
                            if (context.RunOne()) pumpedDuringCleanup++;
                            else Thread.Sleep(1);
                        }
                        if (drain != null && drain.IsCompleted) result = drain.GetAwaiter().GetResult();
                        else if (drain != null) throw new TimeoutException("Drain did not settle during bounded cleanup.");
                    }
                    catch (Exception ex)
                    {
                        failure = failure ?? ex;
                    }
                    finally
                    {
                        SynchronizationContext.SetSynchronizationContext(null);
                        try
                        {
                            var finalDrain = coordinator.DrainAsync(TimeSpan.FromSeconds(1));
                            closeWorkSettled = finalDrain.Wait(TimeSpan.FromSeconds(2)) && finalDrain.GetAwaiter().GetResult();
                        }
                        catch (Exception ex)
                        {
                            failure = failure ?? ex;
                        }
                    }
                }
            }) { IsBackground = true, Name = "Rook shutdown drain regression" };

            thread.Start();
            var joined = thread.Join(TimeSpan.FromSeconds(10));
            _output.WriteLine($"scenario={scenario}; completedWithoutPump={completedWithoutPump}; " +
                $"queuedBeforeCleanup={queuedBeforeCleanup}; pumpedDuringCleanup={pumpedDuringCleanup}; " +
                $"result={result}; closeWorkSettled={closeWorkSettled}; threadJoined={joined}");
            Assert.True(joined, "Bounded fixture thread did not exit.");
            Assert.Null(failure);
            Assert.True(closeWorkSettled, "Synthetic close work was not settled during cleanup.");
            Assert.Equal(expectedResult, result);
            Assert.True(completedWithoutPump,
                $"Production DrainAsync blocked under synchronous wait ({scenario}); " +
                $"queued={queuedBeforeCleanup}, same-thread cleanup callbacks={pumpedDuringCleanup}, " +
                $"result after cleanup={result}. The close/deadline completed but its continuation required context pumping.");
        }

        private sealed class QueuedSingleThreadContext : SynchronizationContext
        {
            private readonly int _threadId = Thread.CurrentThread.ManagedThreadId;
            private readonly ConcurrentQueue<(SendOrPostCallback Callback, object? State)> _queue = new();

            public int PendingCount => _queue.Count;

            public override void Post(SendOrPostCallback callback, object? state) => _queue.Enqueue((callback, state));

            public bool RunOne()
            {
                if (Thread.CurrentThread.ManagedThreadId != _threadId)
                    throw new InvalidOperationException("Only the context's owning thread may pump callbacks.");
                if (!_queue.TryDequeue(out var item)) return false;
                item.Callback(item.State);
                return true;
            }
        }

        [Fact]
        public async Task Queued_close_survives_the_tab_client_lifetime_and_runs_once()
        {
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var calls = 0;
            using var coordinator = ConversationCloseCoordinator.ForTests(async (_, _, _, _) =>
            {
                Interlocked.Increment(ref calls);
                entered.TrySetResult(true);
                await release.Task;
            });

            coordinator.Enqueue(new ConversationCloseRequest(
                new Uri("http://127.0.0.1:8765"), "c1", "nonce"));
            await entered.Task;

            release.TrySetResult(true);
            Assert.True(await coordinator.DrainAsync(TimeSpan.FromSeconds(2)));
            Assert.Equal(1, calls);
        }

        [Fact]
        public async Task Duplicate_close_is_coalesced_by_conversation()
        {
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var calls = 0;
            using var coordinator = ConversationCloseCoordinator.ForTests(async (_, _, _, _) =>
            {
                Interlocked.Increment(ref calls);
                await release.Task;
            });
            var request = new ConversationCloseRequest(new Uri("http://127.0.0.1:8765"), "c1", null);

            coordinator.Enqueue(request);
            coordinator.Enqueue(request);
            release.TrySetResult(true);

            Assert.True(await coordinator.DrainAsync(TimeSpan.FromSeconds(2)));
            Assert.Equal(1, calls);
        }

        [Fact]
        public async Task Synchronously_completed_close_does_not_leave_a_pending_entry()
        {
            var calls = 0;
            using var coordinator = ConversationCloseCoordinator.ForTests((_, _, _, _) =>
            {
                Interlocked.Increment(ref calls);
                return Task.CompletedTask;
            });

            coordinator.Enqueue(new ConversationCloseRequest(
                new Uri("http://127.0.0.1:8765"), "c1", null));

            Assert.True(await coordinator.DrainAsync(TimeSpan.FromSeconds(2)));
            Assert.True(await coordinator.DrainAsync(TimeSpan.FromMilliseconds(20)));
            Assert.Equal(1, calls);
        }

        [Fact]
        public async Task Drain_is_bounded_without_cancelling_the_close()
        {
            var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using var coordinator = ConversationCloseCoordinator.ForTests((_, _, _, _) => release.Task);
            coordinator.Enqueue(new ConversationCloseRequest(
                new Uri("http://127.0.0.1:8765"), "c1", null));

            Assert.False(await coordinator.DrainAsync(TimeSpan.FromMilliseconds(20)));
            release.TrySetResult(true);
            Assert.True(await coordinator.DrainAsync(TimeSpan.FromSeconds(2)));
        }
    }
}
