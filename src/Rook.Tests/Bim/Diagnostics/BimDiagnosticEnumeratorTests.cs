using System;
using System.Collections;
using System.Collections.Generic;
using Rook.Bim;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimDiagnosticEnumeratorTests
    {
        [Fact]
        public void ForEach_VisitsInOrderIncludingFinalFalseMoveNextAndDisposesOnce()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var iterator = new ControlledEnumerator("A", "B");
            var visited = new List<string>();
            var indexes = new List<long>();

            BimDiagnosticEnumerator.ForEach<string>(
                scope.Context,
                new ControlledEnumerable(iterator),
                (value, index) =>
                {
                    visited.Add(value);
                    indexes.Add(index);
                });

            Assert.Equal(new[] { "A", "B" }, visited);
            Assert.Equal(new long[] { 0, 1 }, indexes);
            Assert.Equal(3, iterator.MoveNextCalls);
            Assert.Equal(2, iterator.CurrentCalls);
            Assert.Equal(1, iterator.DisposeCalls);
        }

        [Theory]
        [InlineData(TraversalFailure.MoveNext)]
        [InlineData(TraversalFailure.Current)]
        [InlineData(TraversalFailure.Visitor)]
        public void ForEach_DisposesOnceAndPreservesTraversalFailure(
            TraversalFailure failure)
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var expected = new TraversalException(failure.ToString());
            var iterator = new ControlledEnumerator("A")
            {
                MoveNextException = failure == TraversalFailure.MoveNext ? expected : null,
                CurrentException = failure == TraversalFailure.Current ? expected : null
            };

            var actual = Assert.Throws<TraversalException>(() =>
                BimDiagnosticEnumerator.ForEach<string>(
                    scope.Context,
                    new ControlledEnumerable(iterator),
                    (_, __) =>
                    {
                        if (failure == TraversalFailure.Visitor)
                        {
                            throw expected;
                        }
                    }));

            Assert.Same(expected, actual);
            Assert.Equal(1, iterator.DisposeCalls);
        }

        [Fact]
        public void ForEach_DisposeFailureReplacesInFlightFailure()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var traversal = new TraversalException("visitor");
            var disposal = new DisposeException();
            var iterator = new ControlledEnumerator("A")
            {
                DisposeException = disposal
            };

            var actual = Assert.Throws<DisposeException>(() =>
                BimDiagnosticEnumerator.ForEach<string>(
                    scope.Context,
                    new ControlledEnumerable(iterator),
                    (_, __) => throw traversal));

            Assert.Same(disposal, actual);
            Assert.Equal(1, iterator.DisposeCalls);
            var disposalFailure = Assert.Single(scope.Sink.Envelopes);
            Assert.Equal(BimDiagnosticStage.RevitCategoriesIteratorDispose,
                disposalFailure.Stage);
        }

        [Fact]
        public void ForEach_NonDisposableIteratorCompletesWithNotDisposableDetail()
        {
            using var scope = TestDiagnostics.EnabledScope("list_categories");
            var iterator = new NonDisposableEnumerator("A");
            var visited = 0;

            BimDiagnosticEnumerator.ForEach<string>(
                scope.Context,
                new ControlledEnumerable(iterator),
                (_, __) => visited++);

            Assert.Equal(1, visited);
            var snapshot = TestDiagnostics.Snapshot(scope.Context);
            Assert.Equal(BimDiagnosticStage.RevitCategoriesIteratorDispose,
                snapshot.LastStage);
            Assert.Equal(BimDiagnosticOutcome.Success, snapshot.LastOutcome);
            Assert.Empty(scope.Sink.Envelopes);
        }

        [Fact]
        public void ForEach_DisabledTraversalUsesOriginalOperationsAndStillDisposes()
        {
            var iterator = new ControlledEnumerator("A");
            var enumerable = new ControlledEnumerable(iterator);
            var visited = 0;

            BimDiagnosticEnumerator.ForEach<string>(
                BimDiagnosticContext.Disabled,
                enumerable,
                (_, __) => visited++);

            Assert.Equal(1, enumerable.GetEnumeratorCalls);
            Assert.Equal(2, iterator.MoveNextCalls);
            Assert.Equal(1, iterator.CurrentCalls);
            Assert.Equal(1, iterator.DisposeCalls);
            Assert.Equal(1, visited);
        }

        public enum TraversalFailure
        {
            MoveNext,
            Current,
            Visitor
        }

        private sealed class TraversalException : Exception
        {
            internal TraversalException(string message) : base(message) { }
        }

        private sealed class DisposeException : Exception { }

        private sealed class ControlledEnumerable : IEnumerable
        {
            private readonly IEnumerator iterator;

            internal ControlledEnumerable(IEnumerator iterator)
            {
                this.iterator = iterator;
            }

            internal int GetEnumeratorCalls { get; private set; }

            public IEnumerator GetEnumerator()
            {
                GetEnumeratorCalls++;
                return iterator;
            }
        }

        private sealed class ControlledEnumerator : IEnumerator, IDisposable
        {
            private readonly object[] values;
            private int index = -1;

            internal ControlledEnumerator(params object[] values)
            {
                this.values = values;
            }

            internal Exception? MoveNextException { get; set; }

            internal Exception? CurrentException { get; set; }

            internal Exception? DisposeException { get; set; }

            internal int MoveNextCalls { get; private set; }

            internal int CurrentCalls { get; private set; }

            internal int DisposeCalls { get; private set; }

            public object Current
            {
                get
                {
                    CurrentCalls++;
                    if (CurrentException != null)
                    {
                        throw CurrentException;
                    }

                    return values[index];
                }
            }

            public bool MoveNext()
            {
                MoveNextCalls++;
                if (MoveNextException != null)
                {
                    throw MoveNextException;
                }

                index++;
                return index < values.Length;
            }

            public void Reset()
            {
                throw new NotSupportedException();
            }

            public void Dispose()
            {
                DisposeCalls++;
                if (DisposeException != null)
                {
                    throw DisposeException;
                }
            }
        }

        private sealed class NonDisposableEnumerator : IEnumerator
        {
            private readonly object[] values;
            private int index = -1;

            internal NonDisposableEnumerator(params object[] values)
            {
                this.values = values;
            }

            public object Current
            {
                get { return values[index]; }
            }

            public bool MoveNext()
            {
                index++;
                return index < values.Length;
            }

            public void Reset()
            {
                throw new NotSupportedException();
            }
        }
    }
}
