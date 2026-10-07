using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video.Vertex;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Vertex
{
    // Opt-in source probe. Launch a fresh testhost for each size/concurrency pair; ordinary runs do not claim memory acceptance.
    public sealed class VertexInlineVideoMemoryTests
    {
        [Fact]
        public async Task ActualStreamsEnforceCapAndCancellation()
        {
            using var overflow = new InlineFixtureStream(1024 * 1024);
            Assert.Null(await CappedStreamReader.ReadCappedAsync(overflow, 1024, CancellationToken.None));
            using var cancelled = new InlineFixtureStream(1024 * 1024);
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => CappedStreamReader.ReadCappedAsync(cancelled, VertexVeoClient.WireLimit, new CancellationToken(true)));
        }
        [Fact]
        public async Task StreamedInlineOutputProcessMemoryProbe()
        {
            var output = Environment.GetEnvironmentVariable("ROOK_VERTEX_MEMORY_OUTPUT");
            if (string.IsNullOrEmpty(output)) return;
            var mib = int.Parse(Environment.GetEnvironmentVariable("ROOK_VERTEX_MEMORY_MIB") ?? "1");
            var concurrent = int.Parse(Environment.GetEnvironmentVariable("ROOK_VERTEX_MEMORY_CONCURRENT") ?? "1");
            var decoded = checked(mib * 1024 * 1024);
            Assert.InRange(decoded, 1, VertexVeoClient.DecodedLimit);
            Assert.InRange(concurrent, 1, 2);
            var phases = new List<object>();
            using var process = Process.GetCurrentProcess();
            long Working() { process.Refresh(); return process.WorkingSet64; }
            long Private() { process.Refresh(); return process.PrivateMemorySize64; }
            var baselineWorking = Working(); var baselinePrivate = Private();
            var baselineManaged = GC.GetTotalMemory(true);
            var payloads = new ConcurrentBag<(string Kind, WeakReference Reference, int Length)>();
            async Task Measure(string phase, Func<Task> action)
            {
                var working = Working(); var priv = Private();
                using var stopped = new CancellationTokenSource();
                var watch = Stopwatch.StartNew();
                var sampler = Task.Run(async () =>
                {
                    while (!stopped.IsCancellationRequested)
                    {
                        working = Math.Max(working, Working()); priv = Math.Max(priv, Private());
                        await Task.Delay(10).ConfigureAwait(false);
                    }
                });
                try { await action().ConfigureAwait(false); }
                finally { working = Math.Max(working, Working()); priv = Math.Max(priv, Private()); stopped.Cancel(); await sampler; }
                process.Refresh();
                phases.Add(new { phase, elapsed_ms = watch.ElapsedMilliseconds, sampled_working_peak = working,
                    sampled_private_peak = priv, os_peak_working_set = process.PeakWorkingSet64 });
            }
            async Task<byte[]> Fetch(bool decode)
            {
                using var stream = new InlineFixtureStream(decoded);
                var bytes = await CappedStreamReader.ReadCappedAsync(stream, VertexVeoClient.WireLimit, CancellationToken.None);
                Assert.NotNull(bytes);
                payloads.Add(("encoded", new WeakReference(bytes), bytes!.Length));
                var parsed = VertexVeoClient.ParseOperation(bytes!, VertexVeoTests.Operation, decode);
                Assert.Null(parsed.Error); Assert.True(parsed.Done);
                if (!decode) { Assert.Null(parsed.Video); return Array.Empty<byte>(); }
                Assert.Equal(decoded, parsed.Video!.Length);
                payloads.Add(("decoded", new WeakReference(parsed.Video), parsed.Video.Length));
                Assert.Equal(0, parsed.Video[0]); Assert.Equal(0, parsed.Video[decoded - 1]);
                return parsed.Video;
            }
            await Measure("terminal_poll_no_decode", async () => await Task.WhenAll(Enumerable.Range(0, concurrent).Select(_ => Task.Run(() => Fetch(false)))));
            if (mib == 250 && concurrent == 1)
            {
                await Measure("one_byte_above_decoded_cap", async () =>
                {
                    using var oversized = new InlineFixtureStream(VertexVeoClient.DecodedLimit + 1);
                    var bytes = await CappedStreamReader.ReadCappedAsync(oversized, VertexVeoClient.WireLimit, CancellationToken.None);
                    Assert.NotNull(bytes);
                    Assert.NotNull(VertexVeoClient.ParseOperation(bytes!, VertexVeoTests.Operation, true).Error);
                });
            }
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            byte[][]? videos = null;
            await Measure("fetch_decode", async () => videos = await Task.WhenAll(Enumerable.Range(0, concurrent).Select(_ => Task.Run(() => Fetch(true)))));
            var root = Path.Combine(Path.GetTempPath(), "rook-vertex-memory-" + Guid.NewGuid().ToString("N"));
            try
            {
                var store = new ArtifactStore(root);
                var ids = new List<Guid>();
                await Measure("publish", () =>
                {
                    foreach (var video in videos!) ids.Add(store.Create("generated_video", new[] { new BlobInput("video", video, "mp4") }).Id);
                    return Task.CompletedTask;
                });
                await Measure("cleanup", () =>
                {
                    foreach (var id in ids) Assert.True(store.Delete(id));
                    videos = null;
                    GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
                    return Task.CompletedTask;
                });
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
            var retainedManaged = GC.GetTotalMemory(true);
            Assert.DoesNotContain(payloads, payload => payload.Reference.IsAlive);
            var report = new { status = "passed", decoded_mib = mib, concurrency = concurrent,
                process_id = process.Id, architecture = IntPtr.Size == 8 ? "x64" : "x86", baseline_working = baselineWorking,
                baseline_private = baselinePrivate, retained_working = Working(), retained_private = Private(),
                gc_collections = new[] { GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2) },
                baseline_managed = baselineManaged, retained_managed = retainedManaged,
                payload_references = payloads.Select(p => new { kind = p.Kind, length = p.Length, alive = p.Reference.IsAlive }).ToArray(),
                methodology = "fresh testhost; streaming constant Base64 fixture; 10ms process sampling; UTF8 JSON; no second expected payload", phases };
            File.WriteAllText(output!, JsonSerializer.Serialize(report));
        }

        // Emits JSON and Base64 directly into the reader's small buffer. Payload is decoded all-zero bytes.
        private sealed class InlineFixtureStream : Stream
        {
            private readonly byte[] _prefix = Encoding.ASCII.GetBytes("{\"done\":true,\"response\":{\"videos\":[{\"mimeType\":\"video/mp4\",\"bytesBase64Encoded\":\"");
            private readonly byte[] _suffix = Encoding.ASCII.GetBytes("\"}]}}");
            private readonly long _encoded;
            private readonly int _padding;
            private long _position;
            internal InlineFixtureStream(int decoded) { _encoded = 4L * ((decoded + 2L) / 3); _padding = (3 - decoded % 3) % 3; }
            public override int Read(byte[] buffer, int offset, int count)
            {
                var available = (int)Math.Min(count, Length - _position);
                for (var i = 0; i < available; i++, _position++)
                    buffer[offset + i] = _position < _prefix.Length ? _prefix[(int)_position]
                        : _position < _prefix.Length + _encoded ? (byte)(_position >= _prefix.Length + _encoded - _padding ? '=' : 'A')
                        : _suffix[(int)(_position - _prefix.Length - _encoded)];
                return available;
            }
            public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct)
            { ct.ThrowIfCancellationRequested(); return Task.FromResult(Read(buffer, offset, count)); }
            public override long Length => _prefix.Length + _encoded + _suffix.Length;
            public override long Position { get => _position; set => throw new NotSupportedException(); }
            public override bool CanRead => true;
            public override bool CanSeek => false;
            public override bool CanWrite => false;
            public override void Flush() { }
            public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
            public override void SetLength(long value) => throw new NotSupportedException();
            public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        }
    }
}
