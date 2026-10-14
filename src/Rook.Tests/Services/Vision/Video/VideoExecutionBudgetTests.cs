using System;
using System.Threading;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoExecutionBudgetTests
    {
        internal sealed class Timer : IVideoDeadlineTimer
        {
            internal Action Fire = () => { };
            internal int Schedules;
            public IDisposable Schedule(DateTimeOffset when, Action callback) { Schedules++; Fire = callback; return new CancellationTokenSource(); }
        }
        [Fact]
        public void StopSignalsBeforePersistenceCanRun()
        {
            var clock = new FakeVideoJobClock();
            var timer = new Timer();
            using var budget = new VideoExecutionBudget(clock.Now.AddMinutes(20), clock, timer);
            timer.Fire();
            Assert.True(budget.Token.IsCancellationRequested);
            Assert.Equal(VideoStopReason.Deadline, budget.FirstStopReason);
            Assert.False(budget.TryStop(VideoStopReason.User));
            Assert.False(budget.TryAdmitCompletion());
        }
        [Fact]
        public void FirstStopAndCompletionAdmissionHaveOneWinner()
        {
            var clock = new FakeVideoJobClock();
            using var budget = new VideoExecutionBudget(clock.Now.AddMinutes(20), clock, new Timer());
            Assert.True(budget.TryAdmitCompletion());
            Assert.False(budget.TryStop(VideoStopReason.Shutdown));
            Assert.False(budget.Token.IsCancellationRequested);
        }
        [Fact]
        public void DeadlineIsNotResetByFallback()
        {
            var clock = new FakeVideoJobClock();
            var timer = new Timer();
            using var budget = new VideoExecutionBudget(clock.Now.AddMinutes(20), clock, timer);
            clock.Advance(TimeSpan.FromMinutes(19));
            Assert.Equal(TimeSpan.FromMinutes(1), budget.Remaining);
            Assert.Equal(1, timer.Schedules);
            Assert.True(budget.TryStop(VideoStopReason.User));
            timer.Fire();
            Assert.Equal(VideoStopReason.User, budget.FirstStopReason);
        }
    }
}
