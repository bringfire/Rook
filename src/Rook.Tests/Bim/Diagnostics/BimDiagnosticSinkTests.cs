using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    public sealed class BimDiagnosticSinkTests
    {
        [Fact]
        public void TerminalAdmission_EvictsOnlyTheOldestNonTerminalAtomically()
        {
            using var sink = CreateSink(capacity: 2);
            var evicted = Envelope(BimDiagnosticRecordKind.Milestone);
            var retained = Envelope(BimDiagnosticRecordKind.Failure);
            var terminal = Envelope(BimDiagnosticRecordKind.Terminal);

            Assert.True(sink.TryEnqueue(evicted.Envelope));
            Assert.True(sink.TryEnqueue(retained.Envelope));
            Assert.True(sink.TryEnqueue(terminal.Envelope));

            var status = sink.Snapshot();
            Assert.Equal(1, status.DroppedCount);
            Assert.Equal(BimDiagnosticSinkFailureCode.PriorityEviction,
                status.FailureCode);
            Assert.Equal(1,
                evicted.OriginalAccumulator.Snapshot().RequestDroppedCount);
            Assert.Null(evicted.Envelope.Accumulator);
            Assert.NotNull(retained.Envelope.Accumulator);
            Assert.NotNull(terminal.Envelope.Accumulator);
            sink.Dispose();
        }

        [Fact]
        public void TerminalAdmission_NeverEvictsAnotherTerminal()
        {
            using var sink = CreateSink(capacity: 2);
            var firstTerminal = Envelope(BimDiagnosticRecordKind.Terminal);
            var milestone = Envelope(BimDiagnosticRecordKind.Milestone);
            var rejectedTerminal = Envelope(BimDiagnosticRecordKind.Terminal);

            Assert.True(sink.TryEnqueue(firstTerminal.Envelope));
            Assert.True(sink.TryEnqueue(milestone.Envelope));
            Assert.False(sink.TryEnqueue(rejectedTerminal.Envelope));

            var status = sink.Snapshot();
            Assert.Equal(BimDiagnosticSinkFailureCode.QueueFull,
                status.FailureCode);
            Assert.Equal(1, status.DroppedCount);
            Assert.Equal(1, rejectedTerminal.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.Null(rejectedTerminal.Envelope.Accumulator);
            Assert.NotNull(firstTerminal.Envelope.Accumulator);
            sink.Dispose();
        }

        [Fact]
        public void ProducerContention_RejectsImmediatelyWithExactDropEvidence()
        {
            using var sink = CreateSink(capacity: 2);
            var sync = typeof(BimDiagnosticSink).GetField("sync",
                BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(sink)!;
            var entered = new ManualResetEventSlim(false);
            var release = new ManualResetEventSlim(false);
            var holder = new Thread(() =>
            {
                lock (sync)
                {
                    entered.Set();
                    release.Wait();
                }
            }) { IsBackground = true };
            holder.Start();
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
            var envelope = Envelope(BimDiagnosticRecordKind.Failure);

            var stopwatch = Stopwatch.StartNew();
            var admitted = sink.TryEnqueue(envelope.Envelope);
            stopwatch.Stop();
            release.Set();
            Assert.True(holder.Join(TimeSpan.FromSeconds(5)));

            Assert.False(admitted);
            Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(1));
            Assert.Equal(BimDiagnosticSinkFailureCode.QueueContention,
                sink.Snapshot().FailureCode);
            Assert.Equal(1,
                envelope.OriginalAccumulator.Snapshot().RequestDroppedCount);
            Assert.Null(envelope.Envelope.Accumulator);
            sink.Dispose();
        }

        [Fact]
        public void Stop_ClosesAdmissionAndWriterDrainsEveryAcceptedEnvelope()
        {
            var fileSystem = new BlockingWriteFileSystem();
            var sink = CreateSink(capacity: 4, fileSystem: fileSystem);
            var writing = Envelope(BimDiagnosticRecordKind.Failure);
            var queued = Envelope(BimDiagnosticRecordKind.Failure);
            var late = Envelope(BimDiagnosticRecordKind.Failure);
            try
            {
                Assert.True(sink.TryEnqueue(writing.Envelope));
                sink.Start();
                Assert.True(fileSystem.WriteEntered.Wait(TimeSpan.FromSeconds(5)));
                Assert.True(sink.TryEnqueue(queued.Envelope));

                sink.Dispose();
                Assert.False(sink.TryEnqueue(late.Envelope));
                Assert.Null(late.Envelope.Accumulator);
                Assert.Equal(1, late.OriginalAccumulator.Snapshot()
                    .RequestDroppedCount);

                fileSystem.ReleaseWrite.Set();
                Assert.True(fileSystem.WriterExited.Wait(TimeSpan.FromSeconds(5)));
                Assert.Null(writing.Envelope.Accumulator);
                Assert.Null(queued.Envelope.Accumulator);
                Assert.Equal(1, sink.Snapshot().DroppedCount);
            }
            finally
            {
                fileSystem.ReleaseWrite.Set();
                sink.Dispose();
                fileSystem.WriterExited.Wait(TimeSpan.FromSeconds(5));
            }
        }

        [Fact]
        public void Dispose_WriterBeyondJoinKeepsSignalAliveUntilWriterExits()
        {
            var fileSystem = new BlockingWriteFileSystem();
            var sink = CreateSink(fileSystem: fileSystem);
            var envelope = Envelope(BimDiagnosticRecordKind.Failure);
            try
            {
                Assert.True(sink.TryEnqueue(envelope.Envelope));
                sink.Start();
                Assert.True(fileSystem.WriteEntered.Wait(TimeSpan.FromSeconds(5)));

                var stopwatch = Stopwatch.StartNew();
                sink.Dispose();
                stopwatch.Stop();

                Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(1));
                Assert.False(GetSignal(sink).SafeWaitHandle.IsClosed);
                fileSystem.ReleaseWrite.Set();
                Assert.True(fileSystem.WriterExited.Wait(TimeSpan.FromSeconds(5)));
                Assert.True(SpinWait.SpinUntil(
                    () => GetSignal(sink).SafeWaitHandle.IsClosed,
                    TimeSpan.FromSeconds(5)));
                Assert.Null(envelope.Envelope.Accumulator);
            }
            finally
            {
                fileSystem.ReleaseWrite.Set();
                sink.Dispose();
                fileSystem.WriterExited.Wait(TimeSpan.FromSeconds(5));
            }
        }

        [Fact]
        public void ConcurrentStartAndDispose_NeverPublishesAWriterAfterStop()
        {
            for (var iteration = 0; iteration < 32; iteration++)
            {
                var fileSystem = new MemoryFileSystem();
                var sink = CreateSink(fileSystem: fileSystem);
                using var barrier = new Barrier(3);
                Exception? startFailure = null;
                Exception? disposeFailure = null;
                var starter = new Thread(() =>
                {
                    try
                    {
                        barrier.SignalAndWait();
                        sink.Start();
                    }
                    catch (Exception exception)
                    {
                        startFailure = exception;
                    }
                }) { IsBackground = true };
                var disposer = new Thread(() =>
                {
                    try
                    {
                        barrier.SignalAndWait();
                        sink.Dispose();
                    }
                    catch (Exception exception)
                    {
                        disposeFailure = exception;
                    }
                }) { IsBackground = true };
                starter.Start();
                disposer.Start();
                barrier.SignalAndWait();
                Assert.True(starter.Join(TimeSpan.FromSeconds(5)));
                Assert.True(disposer.Join(TimeSpan.FromSeconds(5)));
                try
                {
                    Assert.Null(startFailure);
                    Assert.Null(disposeFailure);
                    var writer = GetWriterThread(sink);
                    Assert.True(writer == null ||
                        SpinWait.SpinUntil(() => !writer.IsAlive,
                            TimeSpan.FromSeconds(5)));
                    Assert.Equal(BimDiagnosticSinkState.Stopped,
                        sink.Snapshot().State);
                    Assert.True(GetSignal(sink).SafeWaitHandle.IsClosed);
                }
                finally
                {
                    sink.Dispose();
                }
            }
        }

        [Fact]
        public void QueueRejection_DropAccountingDoesNotWaitForAccumulatorGate()
        {
            using var sink = CreateSink(capacity: 1);
            Assert.True(sink.TryEnqueue(
                Envelope(BimDiagnosticRecordKind.Failure).Envelope));
            var rejected = Envelope(BimDiagnosticRecordKind.Failure);
            var gate = typeof(BimDiagnosticOutcomeAccumulator).GetField(
                "gate", BindingFlags.Instance | BindingFlags.NonPublic)!
                .GetValue(rejected.OriginalAccumulator)!;
            using var entered = new ManualResetEventSlim(false);
            using var release = new ManualResetEventSlim(false);
            using var cancelDelayedRelease = new ManualResetEventSlim(false);
            var holder = new Thread(() =>
            {
                lock (gate)
                {
                    entered.Set();
                    release.Wait();
                }
            }) { IsBackground = true };
            holder.Start();
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
            var releaser = new Thread(() =>
            {
                cancelDelayedRelease.Wait(TimeSpan.FromMilliseconds(750));
                release.Set();
            }) { IsBackground = true };
            releaser.Start();

            var stopwatch = Stopwatch.StartNew();
            var admitted = sink.TryEnqueue(rejected.Envelope);
            stopwatch.Stop();
            cancelDelayedRelease.Set();
            release.Set();
            Assert.True(holder.Join(TimeSpan.FromSeconds(5)));
            Assert.True(releaser.Join(TimeSpan.FromSeconds(5)));

            Assert.False(admitted);
            Assert.True(stopwatch.Elapsed < TimeSpan.FromMilliseconds(250),
                "drop accounting blocked behind the request accumulator gate");
            Assert.Equal(1, rejected.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
        }

        [Fact]
        public void DropAccounting_ConcurrentSnapshotsAreCoherentAndSaturate()
        {
            const int WorkerCount = 4;
            var accumulator = new BimDiagnosticOutcomeAccumulator();
            accumulator.RecordDrop(long.MaxValue - 1000);
            using var start = new ManualResetEventSlim(false);
            var remaining = WorkerCount;
            var workers = new Thread[WorkerCount];
            for (var worker = 0; worker < WorkerCount; worker++)
            {
                workers[worker] = new Thread(() =>
                {
                    start.Wait();
                    for (var index = 0; index < 1000; index++)
                    {
                        accumulator.RecordDrop();
                    }

                    Interlocked.Decrement(ref remaining);
                }) { IsBackground = true };
                workers[worker].Start();
            }

            start.Set();
            var previous = long.MaxValue - 1000;
            while (Volatile.Read(ref remaining) != 0)
            {
                var current = accumulator.Snapshot().RequestDroppedCount;
                Assert.InRange(current, previous, long.MaxValue);
                previous = current;
            }

            Assert.All(workers,
                worker => Assert.True(worker.Join(TimeSpan.FromSeconds(5))));
            Assert.Equal(long.MaxValue,
                accumulator.Snapshot().RequestDroppedCount);
        }

        [Fact]
        public void WriterTimeTerminalSnapshot_IncludesEarlierFifoDrop()
        {
            var records = new List<BimDiagnosticRecord>();
            var recordsSync = new object();
            var calls = 0;
            var fileSystem = new MemoryFileSystem();
            using var sink = CreateSink(
                capacity: 2,
                fileSystem: fileSystem,
                encoder: record =>
                {
                    lock (recordsSync)
                    {
                        records.Add(record);
                        calls++;
                        return calls == 1 ? null : "{}\n";
                    }
                });
            var accumulator = new BimDiagnosticOutcomeAccumulator();
            var failure = Envelope(BimDiagnosticRecordKind.Failure, accumulator);
            var terminal = Envelope(BimDiagnosticRecordKind.Terminal, accumulator);
            Assert.True(sink.TryEnqueue(failure.Envelope));
            Assert.True(sink.TryEnqueue(terminal.Envelope));

            sink.Start();
            WaitUntil(() =>
            {
                lock (recordsSync)
                {
                    return records.Count == 2;
                }
            });
            sink.Dispose();

            Assert.Equal(BimDiagnosticSinkFailureCode.RecordOversize,
                sink.Snapshot().FailureCode);
            Assert.Equal(1, accumulator.Snapshot().RequestDroppedCount);
            lock (recordsSync)
            {
                Assert.Equal(1, records[1].RequestDroppedCount);
                Assert.False(records[1].TraceComplete);
            }
            Assert.Null(failure.Envelope.Accumulator);
            Assert.Null(terminal.Envelope.Accumulator);
        }

        [Theory]
        [InlineData("encoder", BimDiagnosticSinkFailureCode.EncoderFailure,
            BimDiagnosticSinkState.Degraded)]
        [InlineData("invalid", BimDiagnosticSinkFailureCode.RecordInvalid,
            BimDiagnosticSinkState.Degraded)]
        [InlineData("oversize", BimDiagnosticSinkFailureCode.RecordOversize,
            BimDiagnosticSinkState.Degraded)]
        [InlineData("limit", BimDiagnosticSinkFailureCode.FileLimitReached,
            BimDiagnosticSinkState.FileLimitReached)]
        public void RecordFailures_MapExactCodeAndReleaseAccumulator(
            string mode,
            BimDiagnosticSinkFailureCode expected,
            BimDiagnosticSinkState expectedState)
        {
            Func<BimDiagnosticRecord, string?> encoder = mode switch
            {
                "encoder" => _ => throw new InvalidOperationException("private"),
                "invalid" => _ => "not-json\n",
                "oversize" => _ => "{\"x\":\"" +
                    new string('x', 16 * 1024) + "\"}\n",
                _ => _ => "{}\n"
            };
            using var sink = CreateSink(
                fileSystem: new MemoryFileSystem(),
                maximumFileBytes: mode == "limit" ? 2 : 16 * 1024 * 1024,
                encoder: encoder);
            var envelope = Envelope(BimDiagnosticRecordKind.Failure);
            Assert.True(sink.TryEnqueue(envelope.Envelope));

            sink.Start();
            WaitUntil(() =>
            {
                var current = sink.Snapshot();
                return current.DroppedCount == 1 &&
                    current.State == expectedState;
            });
            var status = sink.Snapshot();
            sink.Dispose();

            Assert.Equal(expected, status.FailureCode);
            Assert.Equal(expectedState, status.State);
            Assert.Equal(1, status.DroppedCount);
            Assert.Equal(1, envelope.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.Null(envelope.Envelope.Accumulator);
        }

        [Theory]
        [InlineData("{not-json}\n")]
        [InlineData("{\"x\":}\n")]
        public void Writer_RejectsBraceDelimitedMalformedJson(string encoded)
        {
            Assert.ThrowsAny<JsonException>(() =>
                JsonDocument.Parse(encoded.TrimEnd('\n')));
            var fileSystem = new MemoryFileSystem();
            using var sink = CreateSink(
                fileSystem: fileSystem,
                encoder: _ => encoded);
            var envelope = Envelope(BimDiagnosticRecordKind.Failure);
            Assert.True(sink.TryEnqueue(envelope.Envelope));

            sink.Start();
            WaitUntil(() => sink.Snapshot().DroppedCount == 1);
            var status = sink.Snapshot();
            sink.Dispose();

            Assert.Equal(BimDiagnosticSinkState.Degraded, status.State);
            Assert.Equal(BimDiagnosticSinkFailureCode.RecordInvalid,
                status.FailureCode);
            Assert.Equal(1, status.DroppedCount);
            Assert.Equal(1, envelope.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.Empty(fileSystem.Bytes);
            Assert.Null(envelope.Envelope.Accumulator);
        }

        [Fact]
        public void Writer_AcceptsNestedJsonWithEscapedContent()
        {
            const string encoded =
                "{\"x\":[1,true,null,{\"y\":\"escaped\\\\n\"}]}\n";
            using (JsonDocument.Parse(encoded.TrimEnd('\n')))
            {
            }
            var fileSystem = new MemoryFileSystem();
            using var sink = CreateSink(
                fileSystem: fileSystem,
                encoder: _ => encoded);
            var envelope = Envelope(BimDiagnosticRecordKind.Failure);
            Assert.True(sink.TryEnqueue(envelope.Envelope));

            sink.Start();
            WaitUntil(() => fileSystem.Bytes.Length ==
                Encoding.UTF8.GetByteCount(encoded));
            var status = sink.Snapshot();
            sink.Dispose();

            Assert.Equal(BimDiagnosticSinkFailureCode.None,
                status.FailureCode);
            Assert.Equal(0, status.DroppedCount);
            Assert.Equal(encoded, Encoding.UTF8.GetString(fileSystem.Bytes));
            Assert.Equal(0, envelope.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.Null(envelope.Envelope.Accumulator);
        }

        [Theory]
        [InlineData("directory", BimDiagnosticSinkFailureCode.DirectoryCreateFailure)]
        [InlineData("open", BimDiagnosticSinkFailureCode.FileOpenFailure)]
        [InlineData("write", BimDiagnosticSinkFailureCode.FileWriteFailure)]
        [InlineData("flush", BimDiagnosticSinkFailureCode.FileFlushFailure)]
        public void FileFailures_MapExactCodeAndDropOwningRequest(
            string mode,
            BimDiagnosticSinkFailureCode expected)
        {
            var fileSystem = new MemoryFileSystem { FailureMode = mode };
            using var sink = CreateSink(fileSystem: fileSystem);
            var envelope = Envelope(BimDiagnosticRecordKind.Failure);
            Assert.True(sink.TryEnqueue(envelope.Envelope));

            sink.Start();
            WaitUntil(() =>
            {
                var current = sink.Snapshot();
                return current.DroppedCount == 1 &&
                    current.State == BimDiagnosticSinkState.Failed;
            });
            var status = sink.Snapshot();
            sink.Dispose();

            Assert.Equal(expected, status.FailureCode);
            Assert.Equal(BimDiagnosticSinkState.Failed, status.State);
            Assert.Equal(1, status.DroppedCount);
            Assert.Equal(1, envelope.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.Null(envelope.Envelope.Accumulator);
        }

        [Fact]
        public void Writer_UsesUtf8WithoutBomAndBoundsPhysicalRecords()
        {
            var directory = Path.Combine(Path.GetTempPath(),
                "rookbim-sink-" + Guid.NewGuid().ToString("N"));
            try
            {
                using var sink = new BimDiagnosticSink(
                    directory,
                    Provenance(),
                    capacity: 2,
                    maximumFileBytes: 16 * 1024 * 1024);
                var envelope = Envelope(BimDiagnosticRecordKind.Failure);
                Assert.True(sink.TryEnqueue(envelope.Envelope));
                Assert.False(Directory.Exists(directory));

                sink.Start();
                WaitUntil(() => Directory.Exists(directory) &&
                    Directory.GetFiles(directory, "*.jsonl").Length == 1 &&
                    new FileInfo(Directory.GetFiles(directory, "*.jsonl")[0]).Length > 0);
                sink.Dispose();

                var path = Assert.Single(Directory.GetFiles(directory, "*.jsonl"));
                var bytes = File.ReadAllBytes(path);
                Assert.True(bytes.Length <= 16 * 1024);
                Assert.False(bytes.Length >= 3 && bytes[0] == 0xEF &&
                    bytes[1] == 0xBB && bytes[2] == 0xBF);
                Assert.EndsWith("\n", Encoding.UTF8.GetString(bytes));
                Assert.Null(envelope.Envelope.Accumulator);
            }
            finally
            {
                if (Directory.Exists(directory))
                {
                    Directory.Delete(directory, true);
                }
            }
        }

        [Fact]
        public void FileLimit_StopsWithoutOpeningARotationFile()
        {
            var fileSystem = new MemoryFileSystem();
            using var sink = CreateSink(
                capacity: 2,
                maximumFileBytes: 4,
                fileSystem: fileSystem,
                encoder: _ => "{}\n");
            var first = Envelope(BimDiagnosticRecordKind.Failure);
            var second = Envelope(BimDiagnosticRecordKind.Failure);
            Assert.True(sink.TryEnqueue(first.Envelope));
            Assert.True(sink.TryEnqueue(second.Envelope));

            sink.Start();
            WaitUntil(() => sink.Snapshot().State ==
                BimDiagnosticSinkState.FileLimitReached);
            sink.Dispose();

            Assert.Equal(1, fileSystem.OpenCount);
            Assert.Equal(3, fileSystem.Bytes.Length);
            Assert.Equal(0, first.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.Equal(1, second.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.Null(first.Envelope.Accumulator);
            Assert.Null(second.Envelope.Accumulator);
        }

        [Fact]
        public void EverySuccessfulWrite_ReleasesEnvelopeAccumulator()
        {
            var fileSystem = new MemoryFileSystem();
            using var sink = CreateSink(fileSystem: fileSystem);
            var envelope = Envelope(BimDiagnosticRecordKind.Failure);
            var producerThread = Thread.CurrentThread.ManagedThreadId;
            Assert.True(sink.TryEnqueue(envelope.Envelope));
            Assert.Empty(fileSystem.OperationThreadIds);

            sink.Start();
            WaitUntil(() => fileSystem.OperationThreadIds.Count >= 4);
            sink.Dispose();

            Assert.Null(envelope.Envelope.Accumulator);
            Assert.Equal(0, envelope.OriginalAccumulator.Snapshot()
                .RequestDroppedCount);
            Assert.NotEmpty(fileSystem.OperationThreadIds);
            Assert.All(fileSystem.OperationThreadIds,
                threadId => Assert.NotEqual(producerThread, threadId));
        }

        private static BimDiagnosticSink CreateSink(
            int capacity = 2,
            long maximumFileBytes = 16 * 1024 * 1024,
            Func<BimDiagnosticRecord, string?>? encoder = null,
            IBimDiagnosticFileSystem? fileSystem = null)
        {
            return new BimDiagnosticSink(
                "C:\\bounded-test-path",
                Provenance(),
                capacity,
                maximumFileBytes,
                encoder,
                fileSystem ?? new MemoryFileSystem());
        }

        private static BimDiagnosticProvenance Provenance()
        {
            return new BimDiagnosticProvenance(
                typeof(BimDiagnosticSinkTests).Assembly);
        }

        private static EnvelopeCase Envelope(
            BimDiagnosticRecordKind kind,
            BimDiagnosticOutcomeAccumulator? accumulator = null)
        {
            accumulator = accumulator ?? new BimDiagnosticOutcomeAccumulator();
            return new EnvelopeCase(
                new BimDiagnosticEnvelope(
                    kind,
                    DateTime.UtcNow.Ticks,
                    DateTime.UtcNow,
                    123,
                    Thread.CurrentThread.ManagedThreadId,
                    "11111111-2222-3333-4444-555555555555",
                    "status",
                    kind == BimDiagnosticRecordKind.Terminal
                        ? BimDiagnosticStage.HandlerTerminal
                        : BimDiagnosticStage.HandlerRuntime,
                    kind == BimDiagnosticRecordKind.Terminal
                        ? BimDiagnosticOutcome.Success
                        : BimDiagnosticOutcome.Failure,
                    BimDiagnosticFields.None,
                    null,
                    accumulator),
                accumulator);
        }

        private static void WaitUntil(Func<bool> condition)
        {
            Assert.True(SpinWait.SpinUntil(condition, TimeSpan.FromSeconds(5)),
                "Timed out waiting for the diagnostic writer.");
        }

        private static AutoResetEvent GetSignal(BimDiagnosticSink sink)
        {
            return (AutoResetEvent)typeof(BimDiagnosticSink).GetField(
                "signal", BindingFlags.Instance | BindingFlags.NonPublic)!
                .GetValue(sink)!;
        }

        private static Thread? GetWriterThread(BimDiagnosticSink sink)
        {
            return (Thread?)typeof(BimDiagnosticSink).GetField(
                "writerThread", BindingFlags.Instance | BindingFlags.NonPublic)!
                .GetValue(sink);
        }

        private sealed class EnvelopeCase
        {
            internal EnvelopeCase(BimDiagnosticEnvelope envelope,
                BimDiagnosticOutcomeAccumulator originalAccumulator)
            {
                Envelope = envelope;
                OriginalAccumulator = originalAccumulator;
            }

            internal BimDiagnosticEnvelope Envelope { get; }
            internal BimDiagnosticOutcomeAccumulator OriginalAccumulator { get; }
        }

        private sealed class MemoryFileSystem : IBimDiagnosticFileSystem
        {
            private readonly object sync = new object();
            private readonly List<int> operationThreadIds = new List<int>();
            private readonly RecordingStream stream;

            internal MemoryFileSystem()
            {
                stream = new RecordingStream(RecordThread);
            }

            internal string? FailureMode { get; set; }
            internal int OpenCount { get; private set; }
            internal byte[] Bytes => stream.ToArray();
            internal IReadOnlyList<int> OperationThreadIds
            {
                get
                {
                    lock (sync)
                    {
                        return operationThreadIds.ToArray();
                    }
                }
            }

            public void CreateDirectory(string path)
            {
                RecordThread();
                if (FailureMode == "directory")
                {
                    throw new IOException("private directory failure");
                }
            }

            public Stream OpenWrite(string path)
            {
                RecordThread();
                OpenCount++;
                if (FailureMode == "open")
                {
                    throw new IOException("private open failure");
                }

                stream.FailureMode = FailureMode;
                return stream;
            }

            private void RecordThread()
            {
                lock (sync)
                {
                    operationThreadIds.Add(
                        Thread.CurrentThread.ManagedThreadId);
                }
            }
        }

        private sealed class RecordingStream : MemoryStream
        {
            private readonly Action recordThread;

            internal RecordingStream(Action recordThread)
            {
                this.recordThread = recordThread;
            }

            internal string? FailureMode { get; set; }

            public override void Write(byte[] buffer, int offset, int count)
            {
                recordThread();
                if (FailureMode == "write")
                {
                    throw new IOException("private write failure");
                }

                base.Write(buffer, offset, count);
            }

            public override void Flush()
            {
                recordThread();
                if (FailureMode == "flush")
                {
                    throw new IOException("private flush failure");
                }

                base.Flush();
            }

            protected override void Dispose(bool disposing)
            {
                // The fake remains readable after the writer closes it.
            }
        }

        private sealed class BlockingWriteFileSystem : IBimDiagnosticFileSystem
        {
            private readonly BlockingWriteStream stream;

            internal BlockingWriteFileSystem()
            {
                stream = new BlockingWriteStream(
                    WriteEntered, ReleaseWrite, WriterExited);
            }

            internal ManualResetEventSlim WriteEntered { get; } =
                new ManualResetEventSlim(false);
            internal ManualResetEventSlim ReleaseWrite { get; } =
                new ManualResetEventSlim(false);
            internal ManualResetEventSlim WriterExited { get; } =
                new ManualResetEventSlim(false);

            public void CreateDirectory(string path)
            {
            }

            public Stream OpenWrite(string path)
            {
                return stream;
            }
        }

        private sealed class BlockingWriteStream : MemoryStream
        {
            private readonly ManualResetEventSlim writeEntered;
            private readonly ManualResetEventSlim releaseWrite;
            private readonly ManualResetEventSlim writerExited;

            internal BlockingWriteStream(
                ManualResetEventSlim writeEntered,
                ManualResetEventSlim releaseWrite,
                ManualResetEventSlim writerExited)
            {
                this.writeEntered = writeEntered;
                this.releaseWrite = releaseWrite;
                this.writerExited = writerExited;
            }

            public override void Write(byte[] buffer, int offset, int count)
            {
                writeEntered.Set();
                releaseWrite.Wait();
                base.Write(buffer, offset, count);
            }

            protected override void Dispose(bool disposing)
            {
                writerExited.Set();
                base.Dispose(disposing);
            }
        }
    }
}
