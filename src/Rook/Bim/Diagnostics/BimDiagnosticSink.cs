using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

namespace Rook.Bim
{
    internal interface IBimDiagnosticFileSystem
    {
        void CreateDirectory(string path);

        Stream OpenWrite(string path);
    }

    internal sealed class BimDiagnosticSinkSnapshot
    {
        internal BimDiagnosticSinkSnapshot(
            BimDiagnosticSinkState state,
            BimDiagnosticSinkFailureCode failureCode,
            long droppedCount)
        {
            State = state;
            FailureCode = failureCode;
            DroppedCount = droppedCount;
        }

        internal BimDiagnosticSinkState State { get; }
        internal BimDiagnosticSinkFailureCode FailureCode { get; }
        internal long DroppedCount { get; }
    }

    internal sealed class BimDiagnosticSink :
        IBimDiagnosticEnvelopeSink, IDisposable
    {
        private const int ProductionCapacity = 1024;
        private const int MaximumRecordBytes = 16 * 1024;
        private const long ProductionMaximumFileBytes = 16L * 1024 * 1024;
        private const int ProcessExitJoinMilliseconds = 250;

        private static readonly Encoding Utf8WithoutBom = new UTF8Encoding(false);

        private readonly object sync = new object();
        private readonly Queue<BimDiagnosticEnvelope> queue =
            new Queue<BimDiagnosticEnvelope>();
        private readonly AutoResetEvent signal = new AutoResetEvent(false);
        private readonly string directoryPath;
        private readonly BimDiagnosticProvenance provenance;
        private readonly int capacity;
        private readonly long maximumFileBytes;
        private readonly Func<BimDiagnosticRecord, string?> encoder;
        private readonly IBimDiagnosticFileSystem fileSystem;
        private readonly DateTime startUtc;
        private readonly int processId;
        private Thread? writerThread;
        private int started;
        private int stopping;
        private int disposed;
        private int state = (int)BimDiagnosticSinkState.Starting;
        private int firstFailureCode = (int)BimDiagnosticSinkFailureCode.None;
        private long droppedCount;

        internal BimDiagnosticSink(
            string directoryPath,
            BimDiagnosticProvenance provenance,
            int capacity = ProductionCapacity,
            long maximumFileBytes = ProductionMaximumFileBytes,
            Func<BimDiagnosticRecord, string?>? encoder = null,
            IBimDiagnosticFileSystem? fileSystem = null)
        {
            if (string.IsNullOrEmpty(directoryPath))
            {
                throw new ArgumentException(
                    "A diagnostic directory is required.", nameof(directoryPath));
            }

            if (provenance == null)
            {
                throw new ArgumentNullException(nameof(provenance));
            }

            if (capacity <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(capacity));
            }

            if (maximumFileBytes <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(maximumFileBytes));
            }

            this.directoryPath = directoryPath;
            this.provenance = provenance;
            this.capacity = capacity;
            this.maximumFileBytes = maximumFileBytes;
            this.encoder = encoder ?? BimDiagnosticJsonEncoder.Encode;
            this.fileSystem = fileSystem ?? new PhysicalFileSystem();
            startUtc = DateTime.UtcNow;
            processId = CurrentProcessId();
        }

        public bool TryEnqueue(BimDiagnosticEnvelope envelope)
        {
            if (envelope == null)
            {
                throw new ArgumentNullException(nameof(envelope));
            }

            var currentState = (BimDiagnosticSinkState)Volatile.Read(ref state);
            if (Volatile.Read(ref stopping) != 0 ||
                currentState == BimDiagnosticSinkState.Failed ||
                currentState == BimDiagnosticSinkState.FileLimitReached ||
                currentState == BimDiagnosticSinkState.Stopped)
            {
                var failure = currentState == BimDiagnosticSinkState.FileLimitReached
                    ? BimDiagnosticSinkFailureCode.FileLimitReached
                    : BimDiagnosticSinkFailureCode.QueueFull;
                Drop(envelope, failure);
                return false;
            }

            if (!Monitor.TryEnter(sync, 0))
            {
                Drop(envelope, BimDiagnosticSinkFailureCode.QueueContention);
                return false;
            }

            var admitted = false;
            try
            {
                if (queue.Count < capacity)
                {
                    queue.Enqueue(envelope);
                    admitted = true;
                }
                else if (envelope.Kind == BimDiagnosticRecordKind.Terminal &&
                         queue.Peek().Kind !=
                         BimDiagnosticRecordKind.Terminal)
                {
                    var evicted = queue.Dequeue();
                    Drop(evicted,
                        BimDiagnosticSinkFailureCode.PriorityEviction);
                    queue.Enqueue(envelope);
                    admitted = true;
                }
                else
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.QueueFull);
                }

                if (admitted)
                {
                    signal.Set();
                }
            }
            finally
            {
                Monitor.Exit(sync);
            }

            return admitted;
        }

        internal void Start()
        {
            if (Interlocked.CompareExchange(ref started, 1, 0) != 0 ||
                Volatile.Read(ref disposed) != 0)
            {
                return;
            }

            try
            {
                AppDomain.CurrentDomain.ProcessExit += OnProcessExit;
                var thread = new Thread(WriterMain)
                {
                    IsBackground = true,
                    Name = "RookBimDiagnosticWriter"
                };
                writerThread = thread;
                thread.Start();
            }
            catch (Exception)
            {
                FailWithoutWriter(BimDiagnosticSinkFailureCode.FileOpenFailure);
            }
        }

        internal BimDiagnosticSinkSnapshot Snapshot()
        {
            return new BimDiagnosticSinkSnapshot(
                (BimDiagnosticSinkState)Volatile.Read(ref state),
                (BimDiagnosticSinkFailureCode)Volatile.Read(
                    ref firstFailureCode),
                Volatile.Read(ref droppedCount));
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref disposed, 1) != 0)
            {
                return;
            }

            AppDomain.CurrentDomain.ProcessExit -= OnProcessExit;
            Stop(ProcessExitJoinMilliseconds);
            signal.Dispose();
        }

        private void OnProcessExit(object? sender, EventArgs eventArgs)
        {
            Stop(ProcessExitJoinMilliseconds);
        }

        private void Stop(int joinMilliseconds)
        {
            Interlocked.Exchange(ref stopping, 1);
            try
            {
                signal.Set();
            }
            catch (ObjectDisposedException)
            {
            }
            var thread = Volatile.Read(ref writerThread);
            if (thread == null)
            {
                DrainAsDropped(BimDiagnosticSinkFailureCode.QueueFull);
                Volatile.Write(ref state, (int)BimDiagnosticSinkState.Stopped);
                return;
            }

            if (thread != Thread.CurrentThread)
            {
                thread.Join(joinMilliseconds);
            }

            Volatile.Write(ref state, (int)BimDiagnosticSinkState.Stopped);
        }

        private void WriterMain()
        {
            Stream? output = null;
            try
            {
                try
                {
                    fileSystem.CreateDirectory(directoryPath);
                }
                catch (Exception)
                {
                    FailWithoutWriter(
                        BimDiagnosticSinkFailureCode.DirectoryCreateFailure);
                    return;
                }

                var fileName = string.Format(
                    System.Globalization.CultureInfo.InvariantCulture,
                    "rookbim-{0:yyyyMMddTHHmmssfffZ}-{1}.jsonl",
                    startUtc,
                    processId);
                try
                {
                    output = fileSystem.OpenWrite(
                        Path.Combine(directoryPath, fileName));
                }
                catch (Exception)
                {
                    FailWithoutWriter(BimDiagnosticSinkFailureCode.FileOpenFailure);
                    return;
                }

                Interlocked.CompareExchange(
                    ref state,
                    (int)BimDiagnosticSinkState.Ready,
                    (int)BimDiagnosticSinkState.Starting);

                var writtenBytes = 0L;
                while (TryTakeNext(out var envelope))
                {
                    if (!WriteEnvelope(output, envelope, ref writtenBytes))
                    {
                        var current = (BimDiagnosticSinkState)
                            Volatile.Read(ref state);
                        if (current == BimDiagnosticSinkState.Failed ||
                            current == BimDiagnosticSinkState.FileLimitReached)
                        {
                            return;
                        }
                    }
                }
            }
            finally
            {
                if (output != null)
                {
                    try
                    {
                        output.Dispose();
                    }
                    catch (Exception)
                    {
                    }
                }
            }
        }

        private bool TryTakeNext(out BimDiagnosticEnvelope envelope)
        {
            while (true)
            {
                lock (sync)
                {
                    if (queue.Count > 0)
                    {
                        envelope = queue.Dequeue();
                        return true;
                    }

                    if (Volatile.Read(ref stopping) != 0)
                    {
                        envelope = null!;
                        return false;
                    }
                }

                signal.WaitOne();
            }
        }

        private bool WriteEnvelope(
            Stream output,
            BimDiagnosticEnvelope envelope,
            ref long writtenBytes)
        {
            try
            {
                BimDiagnosticRecord record;
                try
                {
                    var request = envelope.Accumulator?.Snapshot() ??
                        new BimDiagnosticRequestSnapshot(
                            null, null, null, null, null, null, 0);
                    var metadata = provenance.Snapshot();
                    record = new BimDiagnosticRecord(
                        envelope,
                        request,
                        metadata.CoreVersion,
                        metadata.CoreCommit,
                        metadata.ModuleVersion,
                        metadata.ModuleCommit);
                }
                catch (Exception)
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.RecordInvalid);
                    return false;
                }

                string? encoded;
                try
                {
                    encoded = encoder(record);
                }
                catch (Exception)
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.EncoderFailure);
                    return false;
                }

                if (encoded == null)
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.RecordOversize);
                    return false;
                }

                if (!IsSingleJsonLine(encoded))
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.RecordInvalid);
                    return false;
                }

                byte[] bytes;
                try
                {
                    bytes = Utf8WithoutBom.GetBytes(encoded);
                }
                catch (Exception)
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.EncoderFailure);
                    return false;
                }

                if (bytes.Length > MaximumRecordBytes)
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.RecordOversize);
                    return false;
                }

                if (writtenBytes > maximumFileBytes - bytes.Length)
                {
                    Drop(envelope,
                        BimDiagnosticSinkFailureCode.FileLimitReached);
                    Volatile.Write(ref state,
                        (int)BimDiagnosticSinkState.FileLimitReached);
                    Interlocked.Exchange(ref stopping, 1);
                    DrainAsDropped(
                        BimDiagnosticSinkFailureCode.FileLimitReached);
                    return false;
                }

                try
                {
                    output.Write(bytes, 0, bytes.Length);
                }
                catch (Exception)
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.FileWriteFailure);
                    FailAndDrain(BimDiagnosticSinkFailureCode.FileWriteFailure);
                    return false;
                }

                try
                {
                    output.Flush();
                }
                catch (Exception)
                {
                    Drop(envelope, BimDiagnosticSinkFailureCode.FileFlushFailure);
                    FailAndDrain(BimDiagnosticSinkFailureCode.FileFlushFailure);
                    return false;
                }

                writtenBytes += bytes.Length;
                envelope.ReleaseAccumulator();
                return true;
            }
            catch (Exception)
            {
                Drop(envelope, BimDiagnosticSinkFailureCode.FileWriteFailure);
                FailAndDrain(BimDiagnosticSinkFailureCode.FileWriteFailure);
                return false;
            }
        }

        private void FailWithoutWriter(BimDiagnosticSinkFailureCode failureCode)
        {
            Volatile.Write(ref state, (int)BimDiagnosticSinkState.Failed);
            Interlocked.Exchange(ref stopping, 1);
            if (!DrainAsDropped(failureCode))
            {
                RecordGlobalDrop(failureCode);
            }
        }

        private void FailAndDrain(BimDiagnosticSinkFailureCode failureCode)
        {
            Volatile.Write(ref state, (int)BimDiagnosticSinkState.Failed);
            Interlocked.Exchange(ref stopping, 1);
            DrainAsDropped(failureCode);
        }

        private bool DrainAsDropped(BimDiagnosticSinkFailureCode failureCode)
        {
            var droppedAny = false;
            while (true)
            {
                BimDiagnosticEnvelope? envelope;
                lock (sync)
                {
                    envelope = queue.Count == 0 ? null : queue.Dequeue();
                }

                if (envelope == null)
                {
                    return droppedAny;
                }

                droppedAny = true;
                Drop(envelope, failureCode);
            }
        }

        private void Drop(
            BimDiagnosticEnvelope envelope,
            BimDiagnosticSinkFailureCode failureCode)
        {
            if (envelope.MarkDropped(failureCode))
            {
                RecordGlobalDrop(failureCode);
            }

            envelope.ReleaseAccumulator();
        }

        private void RecordGlobalDrop(BimDiagnosticSinkFailureCode failureCode)
        {
            Interlocked.CompareExchange(
                ref firstFailureCode,
                (int)failureCode,
                (int)BimDiagnosticSinkFailureCode.None);
            while (true)
            {
                var current = Volatile.Read(ref droppedCount);
                if (current == long.MaxValue)
                {
                    break;
                }

                if (Interlocked.CompareExchange(
                        ref droppedCount, current + 1, current) == current)
                {
                    break;
                }
            }

            if (failureCode == BimDiagnosticSinkFailureCode.FileLimitReached)
            {
                Volatile.Write(ref state,
                    (int)BimDiagnosticSinkState.FileLimitReached);
                return;
            }

            switch (failureCode)
            {
                case BimDiagnosticSinkFailureCode.DirectoryCreateFailure:
                case BimDiagnosticSinkFailureCode.FileOpenFailure:
                case BimDiagnosticSinkFailureCode.FileWriteFailure:
                case BimDiagnosticSinkFailureCode.FileFlushFailure:
                    Volatile.Write(ref state,
                        (int)BimDiagnosticSinkState.Failed);
                    return;
            }

            while (true)
            {
                var currentState = (BimDiagnosticSinkState)
                    Volatile.Read(ref state);
                if (currentState != BimDiagnosticSinkState.Starting &&
                    currentState != BimDiagnosticSinkState.Ready)
                {
                    return;
                }

                if (Interlocked.CompareExchange(
                        ref state,
                        (int)BimDiagnosticSinkState.Degraded,
                        (int)currentState) == (int)currentState)
                {
                    return;
                }
            }
        }

        private static bool IsSingleJsonLine(string value)
        {
            if (value.Length < 3 ||
                value[0] != '{' ||
                value[value.Length - 2] != '}' ||
                value[value.Length - 1] != '\n')
            {
                return false;
            }

            for (var index = 0; index < value.Length - 1; index++)
            {
                if (value[index] == '\r' || value[index] == '\n')
                {
                    return false;
                }
            }

            return true;
        }

        private static int CurrentProcessId()
        {
            using (var process = Process.GetCurrentProcess())
            {
                return process.Id;
            }
        }

        private sealed class PhysicalFileSystem : IBimDiagnosticFileSystem
        {
            public void CreateDirectory(string path)
            {
                Directory.CreateDirectory(path);
            }

            public Stream OpenWrite(string path)
            {
                return new FileStream(
                    path,
                    FileMode.Create,
                    FileAccess.Write,
                    FileShare.Read,
                    4096,
                    FileOptions.SequentialScan);
            }
        }
    }
}
