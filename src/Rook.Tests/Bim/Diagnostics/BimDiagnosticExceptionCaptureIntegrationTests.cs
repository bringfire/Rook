using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Rook.Bim;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimDiagnosticExceptionCaptureIntegrationTests
    {
        [Fact]
        public void ObserveException_CapturesBeforeEnvelope_AndRetainsNoRawException()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var raw = CaptureNestedFailure();

            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                raw,
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    7,
                    BimDiagnosticFailureImpact.Production));

            var envelope = Assert.Single(scope.Sink.Envelopes);
            var captured = Assert.IsType<BimDiagnosticExceptionInfo>(
                envelope.ExceptionInfo);
            Assert.Equal(typeof(InvalidOperationException).FullName,
                captured.TypeName);
            Assert.Contains(nameof(CaptureNestedFailure), captured.Stack);
            Assert.Equal(typeof(ArgumentException).FullName,
                Assert.Single(captured.InnerExceptions).TypeName);

            AssertNoRawExceptionMembers(typeof(BimDiagnosticEnvelope));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticRecord));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticObservation));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticExceptionInfo));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticExceptionCaptureResult));
            AssertNoRawExceptionMembers(typeof(BimDiagnosticObservationAdmission));
            AssertNoRawExceptionMembers(
                typeof(BimDiagnosticDeferredCompletionState));
            AssertNoContextOrCallbackMembers(
                typeof(BimDiagnosticObservationAdmission));
            AssertNoContextOrCallbackMembers(
                typeof(BimDiagnosticDeferredCompletionState));
            Assert.False(typeof(IDisposable).IsAssignableFrom(
                typeof(BimDiagnosticObservationAdmission)));
            Assert.Null(typeof(BimDiagnosticObservationAdmission).GetMethod(
                "Dispose", BindingFlags.Instance | BindingFlags.Public |
                BindingFlags.NonPublic));
        }

        [Fact]
        public void ObserveException_CaptureFailureUsesClosedDetailAndStillEnqueuesRootEvidence()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");

            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                new ThrowingStackException(),
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    null,
                    BimDiagnosticFailureImpact.Production));

            var envelope = Assert.Single(scope.Sink.Envelopes);
            Assert.Equal(BimDiagnosticDetailCode.ExceptionCaptureFailed,
                envelope.Fields.DetailCode);
            Assert.Equal(typeof(ThrowingStackException).FullName,
                envelope.ExceptionInfo?.TypeName);
            Assert.Equal(typeof(ThrowingStackException).FullName,
                TestDiagnostics.Snapshot(scope.Context)
                    .FirstFailureExceptionType);
        }

        [Fact]
        public void ObserveException_AlreadySealedNeverTouchesStackTrace()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var exception = new CountingThrowingStackException();
            scope.Session.CompleteRequest(
                scope.Context, BimDiagnosticOutcome.Success);

            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                exception,
                BimDiagnosticFields.None);

            Assert.Equal(0, exception.StackTraceReads);
            Assert.Single(scope.Sink.Envelopes);
            Assert.Equal(BimDiagnosticRecordKind.Terminal,
                scope.Sink.Envelopes[0].Kind);
        }

        [Fact]
        public async Task ObserveException_AdmittedCaptureOffersFailureBeforeDeferredCompletion()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            using var captureEntered = new ManualResetEventSlim(false);
            using var releaseCapture = new ManualResetEventSlim(false);
            var exception = new BlockingStackException(
                captureEntered, releaseCapture);

            var observation = Task.Run(() => scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                exception,
                new BimDiagnosticFields(
                    BimDiagnosticDetailCode.None,
                    3,
                    BimDiagnosticFailureImpact.Production)));
            Task? completion = null;
            var completedBeforeRelease = false;
            var envelopeCountBeforeRelease = -1;
            try
            {
                Assert.True(captureEntered.Wait(TimeSpan.FromSeconds(5)));
                completion = Task.Run(() => scope.Session.CompleteRequest(
                    scope.Context, BimDiagnosticOutcome.Failure));
                completedBeforeRelease = await Task.WhenAny(
                    completion, Task.Delay(TimeSpan.FromSeconds(1))) ==
                    completion;
                Assert.True(completedBeforeRelease);
                var accumulator =
                    Assert.IsType<BimDiagnosticOutcomeAccumulator>(
                        scope.Context.Accumulator);
                Assert.Null(accumulator.TryBeginObservation());
                envelopeCountBeforeRelease = scope.Sink.Envelopes.Count;
            }
            finally
            {
                releaseCapture.Set();
                if (completion == null)
                {
                    await observation;
                }
                else
                {
                    await Task.WhenAll(observation, completion);
                }
            }

            Assert.True(completedBeforeRelease);
            Assert.Equal(0, envelopeCountBeforeRelease);
            Assert.Equal(1, exception.StackTraceReads);
            Assert.Collection(
                scope.Sink.Envelopes,
                envelope => Assert.Equal(
                    BimDiagnosticRecordKind.Failure, envelope.Kind),
                envelope => Assert.Equal(
                    BimDiagnosticRecordKind.Terminal, envelope.Kind));
            var snapshot = TestDiagnostics.Snapshot(scope.Context);
            Assert.Equal(BimDiagnosticStage.RevitCategoryName,
                snapshot.FirstFailureStage);
            Assert.Equal(BimDiagnosticStage.RevitCategoryName,
                snapshot.LastStage);
        }

        [Fact]
        public void ObserveException_ReentrantCompletionFromStackTraceDefersTerminal()
        {
            var sink = new InMemoryBimDiagnosticEnvelopeSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext("list_categories");
            var exception = new ReentrantCompletionStackException(
                session, context);
            using var finished = new ManualResetEventSlim(false);
            string? observedFailure = null;
            var thread = new Thread(() =>
            {
                try
                {
                    session.ObserveException(
                        context,
                        BimDiagnosticStage.RevitCategoryName,
                        exception,
                        new BimDiagnosticFields(
                            BimDiagnosticDetailCode.None,
                            null,
                            BimDiagnosticFailureImpact.Production));
                }
                catch (Exception caught)
                {
                    observedFailure = caught.GetType().FullName;
                }
                finally
                {
                    finished.Set();
                }
            })
            {
                IsBackground = true
            };

            thread.Start();
            try
            {
                Assert.True(finished.Wait(TimeSpan.FromSeconds(1)),
                    "same-thread completion deadlocked while capturing StackTrace");
                Assert.Null(observedFailure);
                Assert.Equal(1, exception.StackTraceReads);
                Assert.Collection(
                    sink.Envelopes,
                    envelope => Assert.Equal(
                        BimDiagnosticRecordKind.Failure, envelope.Kind),
                    envelope =>
                    {
                        Assert.Equal(
                            BimDiagnosticRecordKind.Terminal, envelope.Kind);
                        Assert.Equal(
                            BimDiagnosticOutcome.Failure, envelope.Outcome);
                    });
                var snapshot = TestDiagnostics.Snapshot(context);
                Assert.Equal(BimDiagnosticStage.RevitCategoryName,
                    snapshot.FirstFailureStage);

                session.CompleteRequest(context, BimDiagnosticOutcome.Success);
                Assert.Equal(2, sink.Envelopes.Count);
            }
            finally
            {
                JoinOrAbort(thread);
            }
        }

        [Fact]
        public void ObserveException_ReentrantCompletionFromSynchronousSinkDefersTerminal()
        {
            var sink = new ReentrantCompletionSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext("list_categories");
            sink.Configure(session, context);
            using var finished = new ManualResetEventSlim(false);
            string? observedFailure = null;
            var thread = new Thread(() =>
            {
                try
                {
                    session.ObserveException(
                        context,
                        BimDiagnosticStage.RevitCategoryName,
                        new InvalidOperationException("private failure"),
                        BimDiagnosticFields.None);
                }
                catch (Exception caught)
                {
                    observedFailure = caught.GetType().FullName;
                }
                finally
                {
                    finished.Set();
                }
            })
            {
                IsBackground = true
            };

            thread.Start();
            try
            {
                Assert.True(finished.Wait(TimeSpan.FromSeconds(1)),
                    "synchronous sink completion deadlocked the observation");
                Assert.Null(observedFailure);
                Assert.Collection(
                    sink.Envelopes,
                    envelope => Assert.Equal(
                        BimDiagnosticRecordKind.Failure, envelope.Kind),
                    envelope =>
                    {
                        Assert.Equal(
                            BimDiagnosticRecordKind.Terminal, envelope.Kind);
                        Assert.Equal(
                            BimDiagnosticOutcome.Failure, envelope.Outcome);
                    });
            }
            finally
            {
                JoinOrAbort(thread);
            }
        }

        [Fact]
        public void ObserveException_ReentrantThrowingSinkStillAttemptsTerminal()
        {
            var sink = new ReentrantThrowingFailureSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext("list_categories");
            sink.Configure(session, context);
            using var finished = new ManualResetEventSlim(false);
            string? observedFailure = null;
            var thread = new Thread(() =>
            {
                try
                {
                    session.ObserveException(
                        context,
                        BimDiagnosticStage.RevitCategoryName,
                        new InvalidOperationException("private failure"),
                        BimDiagnosticFields.None);
                }
                catch (Exception caught)
                {
                    observedFailure = caught.GetType().FullName;
                }
                finally
                {
                    finished.Set();
                }
            })
            {
                IsBackground = true
            };

            thread.Start();
            try
            {
                Assert.True(finished.Wait(TimeSpan.FromSeconds(1)),
                    "throwing synchronous sink deadlocked the observation");
                Assert.Null(observedFailure);
                Assert.Equal(
                    new[]
                    {
                        BimDiagnosticRecordKind.Failure,
                        BimDiagnosticRecordKind.Terminal
                    },
                    sink.Attempts);
                var terminal = Assert.Single(sink.Accepted);
                Assert.Equal(BimDiagnosticRecordKind.Terminal, terminal.Kind);
                var snapshot = TestDiagnostics.Snapshot(context);
                Assert.Equal(1, snapshot.RequestDroppedCount);
                Assert.Equal(
                    BimDiagnosticStage.RevitCategoryName,
                    snapshot.LastStage);
            }
            finally
            {
                JoinOrAbort(thread);
            }
        }

        [Fact]
        public void ObserveException_ValidationFailureStillAttemptsDeferredTerminal()
        {
            var sink = new ThrowingTerminalSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext("list_categories");
            var exception = new ReentrantCompletionStackException(
                session, context);

            var failure = Assert.Throws<ArgumentOutOfRangeException>(() =>
                session.ObserveException(
                    context,
                    (BimDiagnosticStage)999,
                    exception,
                    BimDiagnosticFields.None));

            Assert.Equal("value", failure.ParamName);
            Assert.Equal(
                BimDiagnosticRecordKind.Terminal,
                Assert.Single(sink.Attempts));
            var snapshot = TestDiagnostics.Snapshot(context);
            Assert.Null(snapshot.LastStage);
            Assert.Equal(1, snapshot.RequestDroppedCount);
            Assert.Null(context.Accumulator!.TryBeginObservation());
            session.CompleteRequest(context, BimDiagnosticOutcome.Success);
            Assert.Single(sink.Attempts);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void ObserveException_TwoAdmissionsEmitTerminalAfterBothFailures(
            bool reverseReleaseOrder)
        {
            var sink = new InMemoryBimDiagnosticEnvelopeSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext("list_categories");
            using var firstEntered = new ManualResetEventSlim(false);
            using var secondEntered = new ManualResetEventSlim(false);
            using var releaseFirst = new ManualResetEventSlim(false);
            using var releaseSecond = new ManualResetEventSlim(false);
            var firstException = new BlockingStackException(
                firstEntered, releaseFirst);
            var secondException = new BlockingStackException(
                secondEntered, releaseSecond);
            string? firstFailure = null;
            string? secondFailure = null;
            var firstThread = ObservationThread(
                session, context, firstException,
                value => firstFailure = value);
            var secondThread = ObservationThread(
                session, context, secondException,
                value => secondFailure = value);

            firstThread.Start();
            secondThread.Start();
            try
            {
                Assert.True(firstEntered.Wait(TimeSpan.FromSeconds(5)));
                Assert.True(secondEntered.Wait(TimeSpan.FromSeconds(5)));
                session.CompleteRequest(
                    context, BimDiagnosticOutcome.Failure);
                Assert.Empty(sink.Envelopes);

                var firstToRelease = reverseReleaseOrder
                    ? releaseSecond
                    : releaseFirst;
                var secondToRelease = reverseReleaseOrder
                    ? releaseFirst
                    : releaseSecond;
                var firstToJoin = reverseReleaseOrder
                    ? secondThread
                    : firstThread;
                var secondToJoin = reverseReleaseOrder
                    ? firstThread
                    : secondThread;

                firstToRelease.Set();
                Assert.True(firstToJoin.Join(TimeSpan.FromSeconds(5)));
                var firstEnvelope = Assert.Single(sink.Envelopes);
                Assert.Equal(
                    BimDiagnosticRecordKind.Failure, firstEnvelope.Kind);

                secondToRelease.Set();
                Assert.True(secondToJoin.Join(TimeSpan.FromSeconds(5)));
                Assert.Null(firstFailure);
                Assert.Null(secondFailure);
                Assert.Collection(
                    sink.Envelopes,
                    envelope => Assert.Equal(
                        BimDiagnosticRecordKind.Failure, envelope.Kind),
                    envelope => Assert.Equal(
                        BimDiagnosticRecordKind.Failure, envelope.Kind),
                    envelope => Assert.Equal(
                        BimDiagnosticRecordKind.Terminal, envelope.Kind));
            }
            finally
            {
                releaseFirst.Set();
                releaseSecond.Set();
                JoinOrAbort(firstThread);
                JoinOrAbort(secondThread);
            }
        }

        [Fact]
        public void CompleteRequest_AfterFinalAdmissionReleaseEmitsOneTerminal()
        {
            var sink = new InMemoryBimDiagnosticEnvelopeSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext("list_categories");

            session.ObserveException(
                context,
                BimDiagnosticStage.RevitCategoryName,
                new InvalidOperationException("private failure"),
                BimDiagnosticFields.None);
            session.CompleteRequest(context, BimDiagnosticOutcome.Success);
            session.CompleteRequest(context, BimDiagnosticOutcome.Failure);

            Assert.Collection(
                sink.Envelopes,
                envelope => Assert.Equal(
                    BimDiagnosticRecordKind.Failure, envelope.Kind),
                envelope =>
                {
                    Assert.Equal(BimDiagnosticRecordKind.Terminal, envelope.Kind);
                    Assert.Equal(BimDiagnosticOutcome.Success, envelope.Outcome);
                });
        }

        [Fact]
        public void CompleteRequest_InvalidStartDoesNotSealTheAccumulator()
        {
            var sink = new InMemoryBimDiagnosticEnvelopeSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext("list_categories");

            Assert.Throws<ArgumentOutOfRangeException>(() =>
                session.CompleteRequest(context, BimDiagnosticOutcome.Start));

            session.ObserveException(
                context,
                BimDiagnosticStage.RevitCategoryName,
                new InvalidOperationException("private failure"),
                BimDiagnosticFields.None);
            session.CompleteRequest(context, BimDiagnosticOutcome.Failure);

            Assert.Collection(
                sink.Envelopes,
                envelope => Assert.Equal(
                    BimDiagnosticRecordKind.Failure, envelope.Kind),
                envelope => Assert.Equal(
                    BimDiagnosticRecordKind.Terminal, envelope.Kind));
        }

        [Fact]
        public void RecordMaterialization_CopiesOnlyTheFixedExceptionNode()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            scope.Session.ObserveException(
                scope.Context,
                BimDiagnosticStage.RevitCategoryName,
                CaptureNestedFailure(),
                BimDiagnosticFields.None);

            var envelope = Assert.Single(scope.Sink.Envelopes);
            var record = new BimDiagnosticRecord(
                envelope,
                TestDiagnostics.Snapshot(scope.Context),
                "1.2.3",
                "abc123",
                "unavailable",
                "unavailable");

            Assert.Same(envelope.ExceptionInfo, record.ExceptionInfo);
            Assert.Equal(envelope.ExceptionInfo?.TypeName,
                record.ExceptionInfo?.TypeName);
            Assert.Equal(envelope.ExceptionInfo?.HResult,
                record.ExceptionInfo?.HResult);
        }

        [Fact]
        public void ObserveExceptionSource_CapturesExactlyOnceBeforeEnqueue()
        {
            var source = ReadSourceFile(
                "src", "Rook", "Bim", "Diagnostics", "BimDiagnosticSession.cs");
            var method = Extract(
                source,
                "internal void ObserveException(",
                "internal void CompleteRequest(");
            const string CaptureCall =
                "BimDiagnosticExceptionCapture.Capture(exception)";

            var captureIndex = method.IndexOf(CaptureCall,
                StringComparison.Ordinal);
            var rootIndex = method.IndexOf("var root = capture.Root",
                StringComparison.Ordinal);
            var enqueueIndex = method.IndexOf("Enqueue(",
                StringComparison.Ordinal);

            Assert.True(captureIndex >= 0);
            Assert.Equal(captureIndex, method.LastIndexOf(CaptureCall,
                StringComparison.Ordinal));
            Assert.True(rootIndex > captureIndex);
            Assert.True(enqueueIndex > rootIndex);
            Assert.Matches(
                @"var\s+capture\s*=\s*BimDiagnosticExceptionCapture\.Capture\(exception\)\s*;\s*var\s+root\s*=\s*capture\.Root\s*;",
                method);
            Assert.Single(Regex.Matches(method, @"\broot\s*=(?!=)")
                .Cast<Match>());
            Assert.DoesNotContain("new BimDiagnosticExceptionInfo", method);
            Assert.Contains("root?.TypeName", method);
            Assert.Contains("root == null ? (int?)null : root.HResult", method);
            Assert.Matches(
                @"Enqueue\s*\([\s\S]*?observation\s*,\s*timestampUtc\s*,\s*root\s*\)",
                method);

            var accumulatorSource = ReadSourceFile(
                "src", "Rook", "Bim", "Diagnostics",
                "BimDiagnosticOutcomeAccumulator.cs");
            Assert.DoesNotContain("Monitor.Wait", accumulatorSource);
            Assert.DoesNotContain("Action<", accumulatorSource);
            Assert.DoesNotContain("Func<", accumulatorSource);
            Assert.DoesNotContain("IDisposable", accumulatorSource);
            Assert.DoesNotContain("void Dispose", accumulatorSource);

            var enqueue = Extract(
                source,
                "private void Enqueue(",
                "private void Offer(");
            Assert.Contains("BimDiagnosticExceptionInfo? exceptionInfo", enqueue);
            Assert.Matches(
                @"new BimDiagnosticEnvelope\s*\([\s\S]*?observation\.Fields\s*,\s*exceptionInfo\s*,\s*accumulator\s*\)",
                enqueue);

            var envelopeConstructor = Extract(
                source,
                "internal BimDiagnosticEnvelope(",
                "internal BimDiagnosticRecordKind Kind");
            Assert.Contains("ExceptionInfo = exceptionInfo", envelopeConstructor);

            var constructor = Extract(
                source,
                "internal BimDiagnosticRecord(",
                "internal BimDiagnosticRecordKind Kind");
            Assert.Contains("ExceptionInfo = envelope.ExceptionInfo", constructor);
        }

        private static Exception CaptureNestedFailure()
        {
            try
            {
                throw new InvalidOperationException(
                    "private root message",
                    new ArgumentException("private inner message"));
            }
            catch (Exception exception)
            {
                return exception;
            }
        }

        private sealed class ThrowingStackException : Exception
        {
            public override string? StackTrace =>
                throw new InvalidOperationException("stack access failed");
        }

        private sealed class CountingThrowingStackException : Exception
        {
            private int stackTraceReads;

            internal int StackTraceReads => Volatile.Read(ref stackTraceReads);

            public override string? StackTrace
            {
                get
                {
                    Interlocked.Increment(ref stackTraceReads);
                    throw new InvalidOperationException(
                        "sealed observations must not capture");
                }
            }
        }

        private sealed class BlockingStackException : Exception
        {
            private readonly ManualResetEventSlim entered;
            private readonly ManualResetEventSlim release;
            private int stackTraceReads;

            internal BlockingStackException(
                ManualResetEventSlim entered,
                ManualResetEventSlim release)
            {
                this.entered = entered;
                this.release = release;
            }

            internal int StackTraceReads => Volatile.Read(ref stackTraceReads);

            public override string StackTrace
            {
                get
                {
                    Interlocked.Increment(ref stackTraceReads);
                    entered.Set();
                    if (!release.Wait(TimeSpan.FromSeconds(5)))
                    {
                        throw new TimeoutException("capture was not released");
                    }

                    return "at Example.Type.Read()";
                }
            }
        }

        private sealed class ReentrantCompletionStackException : Exception
        {
            private readonly BimDiagnosticSession session;
            private readonly BimDiagnosticContext context;
            private int stackTraceReads;

            internal ReentrantCompletionStackException(
                BimDiagnosticSession session,
                BimDiagnosticContext context)
            {
                this.session = session;
                this.context = context;
            }

            internal int StackTraceReads => Volatile.Read(ref stackTraceReads);

            public override string StackTrace
            {
                get
                {
                    Interlocked.Increment(ref stackTraceReads);
                    session.CompleteRequest(
                        context, BimDiagnosticOutcome.Failure);
                    session.CompleteRequest(
                        context, BimDiagnosticOutcome.Success);
                    return "at Example.Type.Read()";
                }
            }
        }

        private sealed class ReentrantCompletionSink : IBimDiagnosticEnvelopeSink
        {
            private readonly object sync = new object();
            private readonly List<BimDiagnosticEnvelope> envelopes =
                new List<BimDiagnosticEnvelope>();
            private BimDiagnosticSession? session;
            private BimDiagnosticContext? context;
            private int completionRequested;

            internal IReadOnlyList<BimDiagnosticEnvelope> Envelopes
            {
                get
                {
                    lock (sync)
                    {
                        return envelopes.ToArray();
                    }
                }
            }

            internal void Configure(
                BimDiagnosticSession session,
                BimDiagnosticContext context)
            {
                this.session = session;
                this.context = context;
            }

            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                lock (sync)
                {
                    envelopes.Add(envelope);
                }

                if (envelope.Kind == BimDiagnosticRecordKind.Failure &&
                    Interlocked.Exchange(ref completionRequested, 1) == 0)
                {
                    session!.CompleteRequest(
                        context!, BimDiagnosticOutcome.Failure);
                }

                return true;
            }
        }

        private sealed class ReentrantThrowingFailureSink :
            IBimDiagnosticEnvelopeSink
        {
            private readonly object sync = new object();
            private readonly List<BimDiagnosticRecordKind> attempts =
                new List<BimDiagnosticRecordKind>();
            private readonly List<BimDiagnosticEnvelope> accepted =
                new List<BimDiagnosticEnvelope>();
            private BimDiagnosticSession? session;
            private BimDiagnosticContext? context;

            internal IReadOnlyList<BimDiagnosticRecordKind> Attempts
            {
                get
                {
                    lock (sync)
                    {
                        return attempts.ToArray();
                    }
                }
            }

            internal IReadOnlyList<BimDiagnosticEnvelope> Accepted
            {
                get
                {
                    lock (sync)
                    {
                        return accepted.ToArray();
                    }
                }
            }

            internal void Configure(
                BimDiagnosticSession session,
                BimDiagnosticContext context)
            {
                this.session = session;
                this.context = context;
            }

            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                lock (sync)
                {
                    attempts.Add(envelope.Kind);
                }

                if (envelope.Kind == BimDiagnosticRecordKind.Failure)
                {
                    session!.CompleteRequest(
                        context!, BimDiagnosticOutcome.Failure);
                    throw new InvalidOperationException(
                        "diagnostic sink rejected the failure");
                }

                lock (sync)
                {
                    accepted.Add(envelope);
                }

                return true;
            }
        }

        private sealed class ThrowingTerminalSink : IBimDiagnosticEnvelopeSink
        {
            private readonly List<BimDiagnosticRecordKind> attempts =
                new List<BimDiagnosticRecordKind>();

            internal IReadOnlyList<BimDiagnosticRecordKind> Attempts =>
                attempts.ToArray();

            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                attempts.Add(envelope.Kind);
                throw new InvalidOperationException(
                    "diagnostic terminal sink failure");
            }
        }

        private static Thread ObservationThread(
            BimDiagnosticSession session,
            BimDiagnosticContext context,
            Exception exception,
            Action<string?> recordFailure)
        {
            return new Thread(() =>
            {
                try
                {
                    session.ObserveException(
                        context,
                        BimDiagnosticStage.RevitCategoryName,
                        exception,
                        BimDiagnosticFields.None);
                }
                catch (Exception caught)
                {
                    recordFailure(caught.GetType().FullName);
                }
            })
            {
                IsBackground = true
            };
        }

        private static void JoinOrAbort(Thread thread)
        {
            if (thread.Join(TimeSpan.FromSeconds(5)))
            {
                return;
            }

            try
            {
                thread.Abort();
            }
            catch (ThreadStateException)
            {
            }

            if (!thread.Join(TimeSpan.FromSeconds(5)))
            {
                throw new TimeoutException(
                    "The diagnostic test thread did not terminate after abort.");
            }
        }

        private static void AssertNoRawExceptionMembers(Type type)
        {
            const BindingFlags Flags = BindingFlags.Instance |
                BindingFlags.Public | BindingFlags.NonPublic;
            var unsafeMember = type.GetFields(Flags)
                .Select(field => new { field.Name, MemberType = field.FieldType })
                .Concat(type.GetProperties(Flags).Select(property =>
                    new { property.Name, MemberType = property.PropertyType }))
                .FirstOrDefault(member =>
                    member.MemberType == typeof(object) ||
                    typeof(Exception).IsAssignableFrom(member.MemberType));

            Assert.True(unsafeMember == null,
                type.FullName + " retains unsafe member " + unsafeMember?.Name);
        }

        private static void AssertNoContextOrCallbackMembers(Type type)
        {
            const BindingFlags Flags = BindingFlags.Instance |
                BindingFlags.Public | BindingFlags.NonPublic;
            var unsafeMember = type.GetFields(Flags)
                .Select(field => new { field.Name, MemberType = field.FieldType })
                .Concat(type.GetProperties(Flags).Select(property =>
                    new { property.Name, MemberType = property.PropertyType }))
                .FirstOrDefault(member =>
                    member.MemberType == typeof(BimDiagnosticContext) ||
                    member.MemberType == typeof(BimDiagnosticSession) ||
                    typeof(Delegate).IsAssignableFrom(member.MemberType));

            Assert.True(unsafeMember == null,
                type.FullName + " retains execution member " +
                unsafeMember?.Name);
        }

        private static string Extract(
            string source,
            string startMarker,
            string endMarker)
        {
            var start = source.IndexOf(startMarker, StringComparison.Ordinal);
            var end = source.IndexOf(
                endMarker, start + startMarker.Length, StringComparison.Ordinal);
            Assert.True(start >= 0 && end > start);
            return source.Substring(start, end - start);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                var candidate = Path.Combine(
                    new[] { directory.FullName }.Concat(pathParts).ToArray());
                if (File.Exists(candidate))
                {
                    return File.ReadAllText(candidate);
                }

                directory = directory.Parent;
            }

            throw new FileNotFoundException(string.Join("/", pathParts));
        }
    }
}
