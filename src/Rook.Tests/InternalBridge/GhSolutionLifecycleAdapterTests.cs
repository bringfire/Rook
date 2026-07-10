using System;
using System.Collections.Generic;
using System.Linq;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public sealed class GhSolutionLifecycleAdapterTests
    {
        public delegate void SolutionLifecycleHandler(object sender, SolutionLifecycleEventArgs args);
        public delegate void IncompatibleLifecycleHandler(object sender, IncompatibleLifecycleEventArgs args);

        public sealed class SolutionLifecycleEventArgs : EventArgs
        {
            public SolutionLifecycleEventArgs(object document)
            {
                Document = document;
            }

            public object Document { get; }
        }

        public sealed class IncompatibleLifecycleEventArgs : EventArgs
        {
        }

        public sealed class FakeDocument
        {
            public event SolutionLifecycleHandler? SolutionStart;
            public event SolutionLifecycleHandler? SolutionEnd;

            public void RaiseStart() => SolutionStart?.Invoke(this, new SolutionLifecycleEventArgs(this));
            public void RaiseEnd() => SolutionEnd?.Invoke(this, new SolutionLifecycleEventArgs(this));
        }

        public sealed class MissingEndDocument
        {
            public event SolutionLifecycleHandler? SolutionStart;

            public void RaiseStart() => SolutionStart?.Invoke(this, new SolutionLifecycleEventArgs(this));
        }

        public sealed class IncompatibleDocument
        {
            public event IncompatibleLifecycleHandler? SolutionStart;
            public event IncompatibleLifecycleHandler? SolutionEnd;

            public void RaiseStart() => SolutionStart?.Invoke(this, new IncompatibleLifecycleEventArgs());
            public void RaiseEnd() => SolutionEnd?.Invoke(this, new IncompatibleLifecycleEventArgs());
        }

        [Fact]
        public void Attach_CompatibleEvents_ForwardsStartThenEnd()
        {
            var document = new FakeDocument();
            var observed = new List<(string Phase, object Document)>();

            using var subscription = new GhSolutionLifecycleAdapter().Attach(
                document,
                callbackDocument => observed.Add(("start", callbackDocument)),
                callbackDocument => observed.Add(("end", callbackDocument)));

            Assert.True(subscription.IsAvailable);
            document.RaiseStart();
            document.RaiseEnd();

            Assert.Equal(new[] { "start", "end" }, observed.Select(item => item.Phase));
            Assert.All(observed, item => Assert.Same(document, item.Document));
        }

        [Fact]
        public void Attach_MissingSolutionEnd_FailsClosed()
        {
            using var subscription = new GhSolutionLifecycleAdapter().Attach(
                new MissingEndDocument(),
                _ => { },
                _ => { });

            Assert.False(subscription.IsAvailable);
            Assert.Equal("solution_end_event_missing", subscription.Reason);
        }

        [Fact]
        public void Attach_IncompatibleDelegate_FailsClosed()
        {
            using var subscription = new GhSolutionLifecycleAdapter().Attach(
                new IncompatibleDocument(),
                _ => { },
                _ => { });

            Assert.False(subscription.IsAvailable);
            Assert.Equal("solution_lifecycle_delegate_incompatible", subscription.Reason);
        }

        [Fact]
        public void Dispose_CompatibleSubscription_RemovesBothHandlersExactlyOnce()
        {
            var document = new FakeDocument();
            var callbackCount = 0;
            var subscription = new GhSolutionLifecycleAdapter().Attach(document, _ => callbackCount++, _ => callbackCount++);

            subscription.Dispose();
            subscription.Dispose();
            document.RaiseStart();
            document.RaiseEnd();

            Assert.Equal(0, callbackCount);
        }
    }
}
