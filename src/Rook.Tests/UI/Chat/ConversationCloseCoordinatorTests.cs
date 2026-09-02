using System;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class ConversationCloseCoordinatorTests
    {
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
