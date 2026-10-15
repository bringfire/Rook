using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class WindowsFramingProcessRunnerTests : IDisposable
    {
        private readonly string _temp = Path.Combine(Path.GetTempPath(), "rook-job-probe-" + Guid.NewGuid().ToString("N"));
        public WindowsFramingProcessRunnerTests() { Directory.CreateDirectory(_temp); }
        private static string ProbeExe
        {
            get
            {
                var current = new DirectoryInfo(AppContext.BaseDirectory);
                while (current != null)
                {
                    var path = Path.Combine(current.FullName, "src", "Rook.Framing.Qualification", "bin", "Release", "net48", "Rook.Framing.Qualification.exe");
                    if (File.Exists(path)) return path;
                    current = current.Parent;
                }
                throw new FileNotFoundException("Build the net48 qualification console before running process tests.");
            }
        }
        private FramingProcessRequest Request(params string[] extra) => new(ProbeExe,
            new[] { "--probe-marker", Path.Combine(_temp, "entered.json") }.Concat(extra).ToArray(),
            _temp, Path.Combine(_temp, "output.png"));

        [Fact]
        public async Task Runner_AssignsSuspendedChildBeforeResume()
        {
            var native = new TraceNative();
            var result = await new WindowsFramingProcessRunner(native).RunAsync(Request(), CancellationToken.None);
            Assert.True(result.Success, result.Diagnostics);
            Assert.True(result.EnforcementEstablished);
            Assert.Equal(new[] { "limits", "assign", "resume" }, native.Trace);
            using var marker = JsonDocument.Parse(File.ReadAllText(Path.Combine(_temp, "entered.json")));
            Assert.Equal(536_870_912L, marker.RootElement.GetProperty("job_memory_limit").GetInt64());
        }

        [Theory]
        [InlineData("limits")]
        [InlineData("assign")]
        public async Task Runner_LimitInstallOrAssignmentFailureNeverExecutesProbe(string failure)
        {
            var result = await new WindowsFramingProcessRunner(new TraceNative(failure)).RunAsync(Request(), CancellationToken.None);
            Assert.False(result.Success);
            Assert.Equal("enforcement_unavailable", result.FailureDetail);
            Assert.False(File.Exists(Path.Combine(_temp, "entered.json")));
            if (result.ProcessId.HasValue) Assert.False(IsAlive(result.ProcessId.Value));
        }

        [Theory]
        [InlineData(false, false)]
        [InlineData(true, false)]
        [InlineData(false, true)]
        public async Task Runner_CommitLimitIsHardAndGroupWide(bool child, bool singleAllocation)
        {
            var args = new List<string> { "--probe-commit-mib", "768" };
            if (child) args.Add("--probe-child");
            if (singleAllocation) args.Add("--probe-single");
            var result = await new WindowsFramingProcessRunner().RunAsync(Request(args.ToArray()), CancellationToken.None);
            Assert.False(result.Success);
            Assert.True(result.EnforcementEstablished);
            Assert.Equal("render_limits_exceeded", result.FailureDetail);
            // Windows' raw peak includes an attempted charge rejected by the
            // hard cap. Actual denial/private commit are qualified separately.
            Assert.True(result.PeakJobChargeBytes > 0, JsonSerializer.Serialize(result));
            Assert.False(IsAlive(result.ProcessId!.Value));
            var childMarker = Path.Combine(_temp, "child.json");
            if (File.Exists(childMarker))
            {
                using var childData = JsonDocument.Parse(File.ReadAllText(childMarker));
                Assert.False(IsAlive(childData.RootElement.GetProperty("pid").GetInt32()));
            }
        }

        [Fact]
        public async Task Runner_NotificationStopsBeforeHardCap()
        {
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            var result = await new WindowsFramingProcessRunner().RunAsync(Request("--probe-soft"), deadline.Token);
            Assert.False(result.Success);
            Assert.Equal("render_limits_exceeded", result.FailureDetail);
            Assert.InRange(result.PeakJobChargeBytes, 480L * 1024 * 1024, 536_870_912);
            Assert.DoesNotContain("Unexpected hard allocation denial", result.Diagnostics);
        }

        [Fact]
        public async Task Runner_CancelKillsOwnedTreeOnly()
        {
            using var sentinel = Process.Start(new ProcessStartInfo
            {
                FileName = ProbeExe, Arguments = "--probe-wait", WorkingDirectory = _temp,
                UseShellExecute = false, CreateNoWindow = true
            })!;
            using var stop = new CancellationTokenSource();
            var ready = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using var watcher = new FileSystemWatcher(_temp, "entered.json") { EnableRaisingEvents = true };
            watcher.Created += (_, _) => ready.TrySetResult(true);
            var running = new WindowsFramingProcessRunner().RunAsync(Request("--probe-wait"), stop.Token);
            try
            {
                Assert.Same(ready.Task, await Task.WhenAny(ready.Task, Task.Delay(TimeSpan.FromSeconds(10))));
                stop.Cancel();
                await Assert.ThrowsAnyAsync<OperationCanceledException>(() => running);
                Assert.False(sentinel.HasExited);
                Assert.False(File.Exists(Path.Combine(_temp, "output.png")));
            }
            finally { stop.Cancel(); if (!sentinel.HasExited) { sentinel.Kill(); sentinel.WaitForExit(); } }
        }

        [Fact]
        public async Task Runner_ParentJobAssignmentFailsClosed()
        {
            var native = new TraceNative("assign");
            var result = await new WindowsFramingProcessRunner(native).RunAsync(Request(), CancellationToken.None);
            Assert.False(result.Success);
            Assert.DoesNotContain("resume", native.Trace);
            Assert.False(File.Exists(Path.Combine(_temp, "entered.json")));
        }

        private static bool IsAlive(int pid)
        { try { using var process = Process.GetProcessById(pid); return !process.HasExited; } catch (ArgumentException) { return false; } }
        public void Dispose() { if (Directory.Exists(_temp)) Directory.Delete(_temp, true); }
        private sealed class TraceNative : WindowsFramingJobNative
        {
            private readonly string? _failure;
            public List<string> Trace { get; } = new();
            public TraceNative(string? failure = null) { _failure = failure; }
            internal override void ConfigureJob(FramingNativeHandle job, FramingNativeHandle completion)
            { Trace.Add("limits"); if (_failure == "limits") throw new Win32Exception(5); base.ConfigureJob(job, completion); }
            internal override void AssignProcess(FramingNativeHandle job, FramingNativeHandle process)
            { Trace.Add("assign"); if (_failure == "assign") throw new Win32Exception(5); base.AssignProcess(job, process); }
            internal override void ResumeProcess(FramingNativeHandle thread)
            { Trace.Add("resume"); base.ResumeProcess(thread); }
        }
    }
}
