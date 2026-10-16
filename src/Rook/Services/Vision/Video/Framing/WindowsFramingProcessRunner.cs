using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed record FramingProcessRequest(string ExecutablePath, IReadOnlyList<string> Arguments, string WorkingDirectory, string OutputPath);
    internal sealed record FramingProcessResult(bool Success, string? FailureDetail, long PeakJobChargeBytes,
        bool EnforcementEstablished, string Diagnostics, int? ExitCode, int? ProcessId);
    internal interface IFramingProcessRunner
    { Task<FramingProcessResult> RunAsync(FramingProcessRequest request, CancellationToken ct); }

    internal sealed class WindowsFramingProcessRunner : IFramingProcessRunner
    {
        private readonly WindowsFramingJobNative _native;
        private readonly VideoPreparationResources _resources;
        public WindowsFramingProcessRunner(WindowsFramingJobNative? native = null, VideoPreparationResources? resources = null)
        { _native = native ?? new WindowsFramingJobNative(); _resources = resources ?? VideoPreparationResources.Shared; }

        public async Task<FramingProcessResult> RunAsync(FramingProcessRequest request, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            using var permit = await _resources.AcquireRendererAsync(ct).ConfigureAwait(false);
            // No cancellation argument: cleanup must run even when cancellation
            // occurs before the thread pool starts the launch.
            return await Task.Run(() => RunOwnedAsync(request, ct)).ConfigureAwait(false);
        }

        private async Task<FramingProcessResult> RunOwnedAsync(FramingProcessRequest request, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            bool enforce = false;
            int? pid = null, exit = null;
            long peak = 0;
            string diagnostics = "";
            SuspendedFramingProcess? process = null;
            FramingNativeHandle? job = null, completion = null;
            Task<string>? stderr = null, stdout = null;
            Task? monitor = null;
            int monitorStop = 0, memoryExceeded = 0, monitorFailed = 0;
            CancellationTokenRegistration stop = default;
            try
            {
                if (!Environment.Is64BitProcess) throw new PlatformNotSupportedException("The framing renderer requires a 64-bit host.");
                ValidatePaths(request);
                job = WindowsFramingJobNative.CreateJob();
                completion = WindowsFramingJobNative.CreateCompletionPort();
                _native.ConfigureJob(job, completion);
                var ownedJob = job; var port = completion;
                monitor = Task.Run(() =>
                {
                    while (Volatile.Read(ref monitorStop) == 0)
                    {
                        bool received = WindowsFramingJobNative.GetQueuedCompletionStatus(port, out var message, out _, out _, 100);
                        if (!received)
                        {
                            int error = Marshal.GetLastWin32Error();
                            if (error == 258 || Volatile.Read(ref monitorStop) != 0) continue;
                            Interlocked.Exchange(ref monitorFailed, 1);
                            WindowsFramingJobNative.Terminate(ownedJob); return;
                        }
                        if (message is 9 or 10 or 11)
                        {
                            // Only a memory notification limit is registered.
                            Interlocked.Exchange(ref memoryExceeded, 1);
                            try { if (message == 11) WindowsFramingJobNative.ReadViolation(ownedJob); }
                            catch { Interlocked.Exchange(ref monitorFailed, 1); }
                            WindowsFramingJobNative.Terminate(ownedJob); return;
                        }
                    }
                });
                process = WindowsFramingJobNative.CreateSuspended(request);
                pid = checked((int)WindowsFramingJobNative.GetProcessId(process.Process));
                _native.AssignProcess(job, process.Process);
                enforce = true;
                stop = ct.Register(() => WindowsFramingJobNative.Terminate(ownedJob));
                ct.ThrowIfCancellationRequested();
                stderr = DrainAsync(process.Stderr, 65_536);
                stdout = DrainAsync(process.Stdout, 4096);
                _native.ResumeProcess(process.Thread);
                while (true)
                {
                    uint waited = WindowsFramingJobNative.WaitForSingleObject(process.Process, 100);
                    if (waited == 0) break;
                    if (waited != 258) throw new Win32Exception(Marshal.GetLastWin32Error());
                    ct.ThrowIfCancellationRequested();
                }
                if (!WindowsFramingJobNative.GetExitCodeProcess(process.Process, out var code))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                exit = unchecked((int)code);
                peak = WindowsFramingJobNative.PeakCommit(job);
                WindowsFramingJobNative.Terminate(job); // also stop surviving descendants
                diagnostics = await stderr.ConfigureAwait(false);
                await stdout.ConfigureAwait(false);
                ct.ThrowIfCancellationRequested();
                bool oom = Volatile.Read(ref memoryExceeded) != 0 ||
                    diagnostics.IndexOf("Cannot allocate memory", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    diagnostics.IndexOf("Out of memory", StringComparison.OrdinalIgnoreCase) >= 0;
                string? detail = oom ? "render_limits_exceeded" :
                    Volatile.Read(ref monitorFailed) != 0 ? "enforcement_unavailable" :
                    exit == 0 ? null : "renderer_failed";
                if (detail != null) RemoveOutput(request);
                return new(detail == null, detail, peak, enforce, diagnostics, exit, pid);
            }
            catch (OperationCanceledException) { RemoveOutput(request); throw; }
            catch (Exception ex) when (ex is Win32Exception or IOException or UnauthorizedAccessException or
                PlatformNotSupportedException or ArgumentException)
            {
                RemoveOutput(request);
                return new(false, enforce ? "renderer_failed" : "enforcement_unavailable", peak,
                    enforce, ex.GetType().Name, exit, pid);
            }
            finally
            {
                stop.Dispose();
                if (job != null) WindowsFramingJobNative.Terminate(job);
                process?.Dispose();
                Interlocked.Exchange(ref monitorStop, 1);
                if (monitor != null) await monitor.ConfigureAwait(false);
                // Reads have no inheritable parent writer. Terminating owned
                // children closes the last writers; finish draining before release.
                if (stderr != null) try { await stderr.ConfigureAwait(false); } catch (IOException) { }
                if (stdout != null) try { await stdout.ConfigureAwait(false); } catch (IOException) { }
                completion?.Dispose(); job?.Dispose();
            }
        }

        private static async Task<string> DrainAsync(Stream stream, int capacity)
        {
            var saved = new byte[capacity]; var scratch = new byte[4096]; int used = 0;
            try
            {
                while (true)
                {
                    int n = await stream.ReadAsync(scratch, 0, scratch.Length).ConfigureAwait(false);
                    if (n == 0) break;
                    int retain = Math.Min(n, saved.Length - used);
                    if (retain > 0) { Buffer.BlockCopy(scratch, 0, saved, used, retain); used += retain; }
                }
            }
            catch (ObjectDisposedException) { }
            return Encoding.UTF8.GetString(saved, 0, used);
        }
        private static void ValidatePaths(FramingProcessRequest request)
        {
            if (!Path.IsPathRooted(request.ExecutablePath) || !File.Exists(request.ExecutablePath))
                throw new IOException("Renderer unavailable.");
            var root = Path.GetFullPath(request.WorkingDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                + Path.DirectorySeparatorChar;
            var output = Path.GetFullPath(request.OutputPath);
            if (!Directory.Exists(root) || !output.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Renderer output must belong to the preparation directory.");
        }
        private static void RemoveOutput(FramingProcessRequest request)
        {
            try
            {
                var root = Path.GetFullPath(request.WorkingDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    + Path.DirectorySeparatorChar;
                var output = Path.GetFullPath(request.OutputPath);
                if (output.StartsWith(root, StringComparison.OrdinalIgnoreCase) && File.Exists(output)) File.Delete(output);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException) { }
        }
    }
}
