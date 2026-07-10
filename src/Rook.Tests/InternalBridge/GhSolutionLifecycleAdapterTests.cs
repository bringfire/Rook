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

            public void RaiseStart(object eventDocument) => SolutionStart?.Invoke(this, new SolutionLifecycleEventArgs(eventDocument));
            public void RaiseEnd(object eventDocument) => SolutionEnd?.Invoke(this, new SolutionLifecycleEventArgs(eventDocument));
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

        public sealed class ThrowingRemoveDocument
        {
            private SolutionLifecycleHandler? _solutionStart;
            private SolutionLifecycleHandler? _solutionEnd;

            public int StartRemoveAttempts { get; private set; }
            public int EndRemoveAttempts { get; private set; }

            public event SolutionLifecycleHandler? SolutionStart
            {
                add => _solutionStart += value;
                remove
                {
                    StartRemoveAttempts++;
                    throw new InvalidOperationException("solution_start_remove_failed");
                }
            }

            public event SolutionLifecycleHandler? SolutionEnd
            {
                add => _solutionEnd += value;
                remove
                {
                    EndRemoveAttempts++;
                    throw new InvalidOperationException("solution_end_remove_failed");
                }
            }

            public void RaiseStart(object eventDocument) => _solutionStart?.Invoke(this, new SolutionLifecycleEventArgs(eventDocument));
            public void RaiseEnd(object eventDocument) => _solutionEnd?.Invoke(this, new SolutionLifecycleEventArgs(eventDocument));
        }

        [Fact]
        public void Attach_CompatibleEvents_ForwardsStartThenEnd()
        {
            var document = new FakeDocument();
            var eventDocument = new object();
            var observed = new List<(string Phase, object Document)>();

            using var subscription = new GhSolutionLifecycleAdapter().Attach(
                document,
                callbackDocument => observed.Add(("start", callbackDocument)),
                callbackDocument => observed.Add(("end", callbackDocument)));

            Assert.True(subscription.IsAvailable);
            document.RaiseStart(eventDocument);
            document.RaiseEnd(eventDocument);

            Assert.Equal(new[] { "start", "end" }, observed.Select(item => item.Phase));
            Assert.NotSame(document, eventDocument);
            Assert.All(observed, item => Assert.Same(eventDocument, item.Document));
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
            document.RaiseStart(new object());
            document.RaiseEnd(new object());

            Assert.Equal(0, callbackCount);
        }

        [Fact]
        public void Dispose_ThrowingSolutionRemovals_AttemptsBothAndLeavesOldCallbacksInert()
        {
            var adapter = new GhSolutionLifecycleAdapter();
            var oldDocument = new ThrowingRemoveDocument();
            var replacementDocument = new FakeDocument();
            var oldCallbackCount = 0;
            var replacementPhases = new List<string>();
            var oldSubscription = adapter.Attach(oldDocument, _ => oldCallbackCount++, _ => oldCallbackCount++);
            GhSolutionLifecycleSubscription? replacementSubscription = null;

            var exception = Record.Exception(() =>
            {
                oldSubscription.Dispose();
                oldSubscription.Dispose();
                replacementSubscription = adapter.Attach(
                    replacementDocument,
                    _ => replacementPhases.Add("start"),
                    _ => replacementPhases.Add("end"));
            });

            Assert.Null(exception);
            Assert.NotNull(replacementSubscription);
            Assert.True(replacementSubscription!.IsAvailable);
            Assert.Equal(1, oldDocument.StartRemoveAttempts);
            Assert.Equal(1, oldDocument.EndRemoveAttempts);
            oldDocument.RaiseStart(new object());
            oldDocument.RaiseEnd(new object());
            replacementDocument.RaiseStart(new object());
            replacementDocument.RaiseEnd(new object());
            Assert.Equal(0, oldCallbackCount);
            Assert.Equal(new[] { "start", "end" }, replacementPhases);
            replacementSubscription.Dispose();
        }
    }
}
