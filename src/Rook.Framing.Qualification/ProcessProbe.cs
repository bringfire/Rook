using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;

namespace Rook.Framing.Qualification
{
    // Synthetic allocations use commit without touching every page. No Rook
    // instance/provider is involved; these modes are only spawned by the runner.
    internal static class ProcessProbe
    {
        public static string ExecutablePath => Process.GetCurrentProcess().MainModule!.FileName;
        public static int Run(string[] args)
        {
            var marker = Program.Value(args, "--probe-marker");
            if (marker != null)
                File.WriteAllText(marker, JsonSerializer.Serialize(new { pid = Process.GetCurrentProcess().Id, job_memory_limit = CurrentLimit() }));
            if (args.Contains("--probe-child"))
            {
                var childMarker = Path.Combine(Environment.CurrentDirectory, "child.json");
                using var child = Process.Start(new ProcessStartInfo {
                    FileName = ExecutablePath, Arguments = "--probe-commit-mib 768 --probe-marker \"" + childMarker + "\"",
                    UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Environment.CurrentDirectory
                })!;
                Thread.Sleep(Timeout.Infinite);
            }
            if (args.Contains("--probe-wait")) Thread.Sleep(Timeout.Infinite);
            if (args.Contains("--probe-soft"))
            {
                using var self = Process.GetCurrentProcess();
                while (true)
                {
                    self.Refresh();
                    if (self.PrivateMemorySize64 >= 490L * 1024 * 1024) break;
                    if (VirtualAlloc(IntPtr.Zero, new UIntPtr(1024 * 1024), 0x3000, 4) == IntPtr.Zero)
                    { Console.Error.WriteLine("Unexpected hard allocation denial before soft notification."); return 43; }
                }
                // Below the hard cap: only the guaranteed soft notification
                // (or the enclosing test deadline) can end this wait.
                Thread.Sleep(Timeout.Infinite);
            }
            var count = Program.Value(args, "--probe-commit-mib");
            if (count == null) return 0;
            long total = checked(long.Parse(count) * 1024 * 1024);
            long step = args.Contains("--probe-single") ? total : 16 * 1024 * 1024;
            var allocations = new List<IntPtr>();
            try
            {
                for (long allocated = 0; allocated < total; allocated += step)
                {
                    var block = VirtualAlloc(IntPtr.Zero, new UIntPtr((ulong)Math.Min(step, total - allocated)), 0x3000, 4);
                    if (block == IntPtr.Zero)
                    {
                        int error = Marshal.GetLastWin32Error();
                        using var self = Process.GetCurrentProcess();
                        Console.Error.WriteLine("Cannot allocate memory; " + JsonSerializer.Serialize(new {
                            error, successfullyAllocatedBytes = allocated, currentPrivateBytes = self.PrivateMemorySize64
                        }));
                        return 42;
                    }
                    allocations.Add(block);
                }
                return 0;
            }
            finally { foreach (var block in allocations) VirtualFree(block, UIntPtr.Zero, 0x8000); }
        }
        private static long CurrentLimit()
        {
            // Windows SDK x64 JOBOBJECT_EXTENDED_LIMIT_INFORMATION: JobMemoryLimit
            // follows Basic(64), IO_COUNTERS(48), ProcessMemoryLimit(8).
            var data = new byte[144];
            return QueryInformationJobObject(IntPtr.Zero, 9, data, data.Length, IntPtr.Zero)
                ? checked((long)BitConverter.ToUInt64(data, 120)) : 0;
        }
        [DllImport("kernel32", SetLastError = true)] private static extern bool QueryInformationJobObject(IntPtr job, int type, [Out] byte[] data, int size, IntPtr returned);
        [DllImport("kernel32", SetLastError = true)] private static extern IntPtr VirtualAlloc(IntPtr address, UIntPtr size, uint allocation, uint protection);
        [DllImport("kernel32", SetLastError = true)] private static extern bool VirtualFree(IntPtr address, UIntPtr size, uint freeType);
    }
}
