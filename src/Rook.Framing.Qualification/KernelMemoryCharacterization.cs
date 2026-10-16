using System;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Framing.Qualification
{
    internal static class KernelMemoryCharacterization
    {
        // Do not consume notifications here: observe the kernel refusing the
        // allocation, before the normal runner's notification handler kills it.
        // The same configured hard Job Object still contains the child.
        public static async Task<object> RunAsync(string directory)
        {
            using var job = WindowsFramingJobNative.CreateJob();
            using var port = WindowsFramingJobNative.CreateCompletionPort();
            var native = new WindowsFramingJobNative();
            native.ConfigureJob(job, port);
            var request = new FramingProcessRequest(ProcessProbe.ExecutablePath,
                new[] { "--probe-commit-mib", "768", "--probe-single" }, directory, Path.Combine(directory, "unused.png"));
            using var process = WindowsFramingJobNative.CreateSuspended(request);
            native.AssignProcess(job, process.Process);
            var diagnostics = Task.Run(() => {
                using var collected = new MemoryStream();
                var buffer = new byte[1024];
                while (true)
                {
                    int count = process.Stderr.Read(buffer, 0, buffer.Length);
                    if (count == 0) break;
                    if (collected.Length + count > 4096) throw new InvalidOperationException("Unexpected probe diagnostic volume.");
                    collected.Write(buffer, 0, count);
                }
                return Encoding.UTF8.GetString(collected.ToArray());
            });
            native.ResumeProcess(process.Thread);
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (WindowsFramingJobNative.WaitForSingleObject(process.Process, 100) == 258)
                if (DateTime.UtcNow >= deadline) { WindowsFramingJobNative.Terminate(job); throw new TimeoutException("Kernel denial probe timed out."); }
            WindowsFramingJobNative.GetExitCodeProcess(process.Process, out uint exit);
            string text = await diagnostics.ConfigureAwait(false);
            Program.Require(exit == 42, "Kernel did not refuse the oversized allocation: " + text);
            int start = text.IndexOf('{');
            Program.Require(start >= 0, "Missing allocation evidence.");
            using var data = JsonDocument.Parse(text.Substring(start));
            long successful = data.RootElement.GetProperty("successfullyAllocatedBytes").GetInt64();
            long current = data.RootElement.GetProperty("currentPrivateBytes").GetInt64();
            Program.Require(successful == 0 && current > 0 && current < 536_870_912,
                "An oversized allocation was admitted.");
            return new { allocationDenied = true, successfullyAllocatedBytes = successful,
                currentPrivateBytes = current, windowsPeakJobChargeBytes = WindowsFramingJobNative.PeakCommit(job),
                win32Error = data.RootElement.GetProperty("error").GetInt32() };
        }
    }
}
