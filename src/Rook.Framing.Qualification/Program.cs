using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Versioning;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Framing;

namespace Rook.Framing.Qualification
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            try
            {
                if (args.Any(a => a.StartsWith("--probe-", StringComparison.Ordinal))) return ProcessProbe.Run(args);
                return RunAsync(args).GetAwaiter().GetResult();
            }
            catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
        }
        private static async Task<int> RunAsync(string[] args)
        {
            if (args.Contains("--installed-layout")) return await RendererQualification.RunAsync(
                Rook.Services.Vision.Video.Extraction.FfmpegBundledBinaryLocator.GetInstalledFfmpegPath() ?? throw new InvalidOperationException("Installed-layout renderer is missing."),
                Value(args, "--fixtures") ?? throw new ArgumentException("--fixtures required"), Value(args, "--report") ?? throw new ArgumentException("--report required"));
            if (Value(args, "--ffmpeg") is string ffmpeg) return await RendererQualification.RunAsync(ffmpeg, Value(args, "--fixtures") ?? throw new ArgumentException("--fixtures required"), Value(args, "--report") ?? throw new ArgumentException("--report required"));
            if (!args.Contains("--process-probes") && !args.Contains("--kernel-denial-characterization")) throw new ArgumentException("Specify --process-probes.");
            string report = Value(args, "--report") ?? throw new ArgumentException("--report is required.");
            var root = Path.Combine(Path.GetTempPath(), "rook-framing-qualification-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            var results = new System.Collections.Generic.List<object>();
            try
            {
                var kernelDenial = await KernelMemoryCharacterization.RunAsync(root);
                if (args.Contains("--kernel-denial-characterization"))
                {
                    File.WriteAllText(Path.GetFullPath(report), JsonSerializer.Serialize(kernelDenial));
                    Console.WriteLine(JsonSerializer.Serialize(kernelDenial)); return 0;
                }
                foreach (string mode in new[] { "marker", "incremental", "single", "child", "notification" })
                {
                    var marker = Path.Combine(root, mode + ".json");
                    var parameters = new System.Collections.Generic.List<string> { "--probe-marker", marker };
                    if (mode != "marker" && mode != "notification") parameters.AddRange(new[] { "--probe-commit-mib", "768" });
                    if (mode == "notification") parameters.Add("--probe-soft");
                    if (mode == "single") parameters.Add("--probe-single");
                    if (mode == "child") parameters.Add("--probe-child");
                    using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
                    var result = await new WindowsFramingProcessRunner().RunAsync(
                        new FramingProcessRequest(ProcessProbe.ExecutablePath, parameters, root, Path.Combine(root, "output.png")), deadline.Token);
                    Require(result.EnforcementEstablished, "Job Object enforcement was not established.");
                    Require(result.PeakJobChargeBytes > 0, "Missing raw job memory-charge accounting.");
                    if (mode == "marker")
                    {
                        Require(result.Success, "Contained marker failed: " + result.Diagnostics);
                        using var data = JsonDocument.Parse(File.ReadAllText(marker));
                        Require(data.RootElement.GetProperty("job_memory_limit").GetInt64() == 536_870_912, "Child executed without the 512 MiB limit.");
                    }
                    else Require(!result.Success && result.FailureDetail == "render_limits_exceeded", "Memory probe did not fail closed: " + result.Diagnostics);
                    if (mode == "notification") Require(result.PeakJobChargeBytes <= 536_870_912 &&
                        !result.Diagnostics.Contains("Unexpected hard allocation denial"), "Soft notification did not stop the probe below the hard cap.");
                    results.Add(new { mode, result.Success, result.FailureDetail, result.PeakJobChargeBytes, result.EnforcementEstablished, result.ExitCode });
                }
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(report))!);
                File.WriteAllText(report, JsonSerializer.Serialize(new {
                    framework = Assembly.GetExecutingAssembly().GetCustomAttribute<TargetFrameworkAttribute>()!.FrameworkName,
                    os = Environment.OSVersion.ToString(), x64 = Environment.Is64BitProcess, kernelDenial, results
                }, new JsonSerializerOptions { WriteIndented = true }));
                Console.WriteLine("PASS: contained marker, hard allocation denial, incremental limit, descendant group; " + report);
                return 0;
            }
            finally { Directory.Delete(root, true); }
        }
        internal static string? Value(string[] args, string name)
        { int index = Array.IndexOf(args, name); return index >= 0 && index + 1 < args.Length ? args[index + 1] : null; }
        internal static void Require(bool condition, string message)
        { if (!condition) throw new InvalidOperationException(message); }
    }
}
