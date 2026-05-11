using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Extraction
{
    public class VideoExtractionSpikeManualTests
    {
        [Fact]
        public async Task Ffmpeg_extracts_poster_from_local_mp4_when_enabled()
        {
            if (!string.Equals(Environment.GetEnvironmentVariable("ROOK_RUN_VIDEO_EXTRACTION_SPIKE"), "1", StringComparison.Ordinal))
                return;

            var input = RequiredEnv("ROOK_VIDEO_SPIKE_MP4");
            var findingsPath = RequiredEnv("ROOK_VIDEO_SPIKE_FINDINGS_PATH");
            var configuredFfmpeg = Environment.GetEnvironmentVariable("ROOK_VIDEO_SPIKE_FFMPEG");
            var outputRoot = Environment.GetEnvironmentVariable("ROOK_VIDEO_SPIKE_OUTPUT_DIR");
            if (string.IsNullOrWhiteSpace(outputRoot))
                outputRoot = Path.Combine(Path.GetTempPath(), "rook-video-extraction-spike");

            Directory.CreateDirectory(outputRoot);
            var output = Path.Combine(outputRoot, "poster-candidate.jpg");

            var resolution = FfmpegBinaryResolver.Resolve(configuredFfmpeg);
            var result = resolution.Success
                ? await new FfmpegPosterFrameExtractor().ExtractPosterAsync(
                    resolution.Path!,
                    input,
                    output,
                    TimeSpan.FromSeconds(30),
                    CancellationToken.None)
                : FfmpegPosterExtractionResult.Failed(
                    "ffmpeg discovery",
                    null,
                    resolution.Message,
                    output,
                    TimeSpan.Zero,
                    FfmpegPosterExtractionError.BinaryMissing,
                    resolution.Message);

            WriteFindings(findingsPath, input, configuredFfmpeg, resolution, result);

            Assert.True(resolution.Success, resolution.Message);
            Assert.True(result.Success, result.Message + Environment.NewLine + result.Stderr);
        }

        [Fact]
        public void WriteFindings_RedactsLocalPathsFromMessagesAndDiagnostics()
        {
            var root = Path.Combine(Path.GetTempPath(), "rook-video-findings-redaction-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                var input = Path.Combine(root, "client", "input.mp4");
                var ffmpeg = Path.Combine(root, "tools", "ffmpeg.exe");
                var output = Path.Combine(root, "out", "poster.jpg");
                var findings = Path.Combine(root, "findings.md");
                Directory.CreateDirectory(Path.GetDirectoryName(input)!);
                Directory.CreateDirectory(Path.GetDirectoryName(ffmpeg)!);
                File.WriteAllText(input, "fake mp4");
                File.WriteAllText(ffmpeg, "fake ffmpeg");

                var inputWithForwardSlashes = input.Replace('\\', '/');
                var resolution = FfmpegBinaryResolution.Failed(
                    FfmpegBinaryResolutionError.ConfiguredPathMissing,
                    $"Configured ffmpeg path does not exist: {ffmpeg}");
                var result = FfmpegPosterExtractionResult.Failed(
                    $"{ffmpeg} -i {input} {output}",
                    null,
                    $"ffmpeg failed while reading {inputWithForwardSlashes}, writing {output}, and using {ffmpeg}",
                    output,
                    TimeSpan.Zero,
                    FfmpegPosterExtractionError.ProcessStartFailed,
                    "ffmpeg process could not be started.");

                WriteFindings(findings, input, ffmpeg, resolution, result);

                var text = File.ReadAllText(findings);
                Assert.Contains("<INPUT_MP4>", text);
                Assert.Contains("<OUTPUT_IMAGE>", text);
                Assert.Contains("<FFMPEG_EXE>", text);
                Assert.DoesNotContain(input, text);
                Assert.DoesNotContain(inputWithForwardSlashes, text);
                Assert.DoesNotContain(output, text);
                Assert.DoesNotContain(ffmpeg, text);
            }
            finally
            {
                if (Directory.Exists(root))
                    Directory.Delete(root, recursive: true);
            }
        }

        private static string RequiredEnv(string name)
        {
            var value = Environment.GetEnvironmentVariable(name);
            if (string.IsNullOrWhiteSpace(value))
                throw new InvalidOperationException($"{name} must be set when ROOK_RUN_VIDEO_EXTRACTION_SPIKE=1.");
            return value;
        }

        private static void WriteFindings(
            string findingsPath,
            string input,
            string? configuredFfmpeg,
            FfmpegBinaryResolution resolution,
            FfmpegPosterExtractionResult result)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(findingsPath)!);
            var now = DateTimeOffset.Now;
            var sb = new StringBuilder();
            sb.AppendLine("# Local MP4 Extraction Spike Findings");
            sb.AppendLine();
            sb.AppendLine($"Date: {now:yyyy-MM-dd}");
            sb.AppendLine();
            sb.AppendLine("## Fixture Policy");
            sb.AppendLine();
            sb.AppendLine("No MP4 fixture or ffmpeg binary is committed. The spike used a local MP4 path supplied by the runner or discovered from the local Rook artifact store.");
            sb.AppendLine();
            sb.AppendLine("## Environment");
            sb.AppendLine();
            sb.AppendLine($"- OS: {Environment.OSVersion}");
            sb.AppendLine($"- .NET runtime: {Environment.Version}");
            sb.AppendLine();
            sb.AppendLine("## Input");
            sb.AppendLine();
            sb.AppendLine($"- Input path shape: `{Sanitize(input)}`");
            sb.AppendLine($"- Input exists: `{File.Exists(input)}`");
            if (File.Exists(input))
                sb.AppendLine($"- Input bytes: `{new FileInfo(input).Length}`");
            sb.AppendLine();
            sb.AppendLine("## ffmpeg Discovery");
            sb.AppendLine();
            sb.AppendLine($"- Success: `{resolution.Success}`");
            sb.AppendLine($"- Source: `{resolution.Source}`");
            sb.AppendLine($"- Error code: `{resolution.ErrorCode}`");
            sb.AppendLine($"- Resolved path shape: `{Sanitize(resolution.Path)}`");
            sb.AppendLine($"- Message: {EscapeMarkdown(RedactPaths(resolution.Message, input, configuredFfmpeg, resolution.Path, result.OutputPath))}");
            sb.AppendLine();
            sb.AppendLine("## Extraction Result");
            sb.AppendLine();
            sb.AppendLine($"- Success: `{result.Success}`");
            sb.AppendLine($"- Command/API shape: `{RedactPaths(result.CommandLine, input, configuredFfmpeg, resolution.Path, result.OutputPath)}`");
            sb.AppendLine($"- Exit code: `{result.ExitCode}`");
            sb.AppendLine($"- Error code: `{result.ErrorCode}`");
            sb.AppendLine($"- Output path shape: `{Sanitize(result.OutputPath)}`");
            sb.AppendLine($"- Output exists: `{File.Exists(result.OutputPath)}`");
            sb.AppendLine($"- Output dimensions: `{result.Width}x{result.Height}`");
            sb.AppendLine($"- Elapsed ms: `{result.Elapsed.TotalMilliseconds:0}`");
            sb.AppendLine($"- Diagnostic summary: {EscapeMarkdown(Trim(RedactPaths(result.Stderr, input, configuredFfmpeg, resolution.Path, result.OutputPath), 600))}");
            sb.AppendLine();
            sb.AppendLine("## WMF Feasibility");
            sb.AppendLine();
            sb.AppendLine("WMF was not implemented as code in this spike. The feasibility review remains documentation-level: using WMF from the managed companion would require new interop or package work and careful COM/threading design, while the ffmpeg external-process path keeps decoding out of the Rhino UI process and is directly testable from managed code.");
            sb.AppendLine();
            sb.AppendLine("## Failure Observations");
            sb.AppendLine();
            sb.AppendLine("- Missing ffmpeg is represented as a structured binary-discovery failure.");
            sb.AppendLine("- Missing input fails before process start.");
            sb.AppendLine("- Process-start failure is represented as a structured extraction failure for invalid or non-executable configured paths.");
            sb.AppendLine("- Nonzero exit, timeout, missing output, and invalid image output are covered by unit tests.");
            sb.AppendLine();
            sb.AppendLine("## Recommendation");
            sb.AppendLine();
            sb.AppendLine(result.Success
                ? "Use ffmpeg as the production extraction path candidate, invoked as a replaceable external process. Keep packaging, LGPL-build selection, notices, and source-compliance work in a later slice."
                : "Do not proceed to production extraction until the local ffmpeg failure above is resolved and rerun.");
            File.WriteAllText(findingsPath, sb.ToString(), Encoding.UTF8);
        }

        private static string Sanitize(string? path)
        {
            if (string.IsNullOrWhiteSpace(path))
                return "";

            var file = Path.GetFileName(path);
            var parent = Path.GetFileName(Path.GetDirectoryName(path) ?? "");
            return string.IsNullOrWhiteSpace(parent)
                ? file
                : Path.Combine("...", parent, file);
        }

        private static string RedactPaths(
            string value,
            string inputPath,
            string? configuredFfmpegPath,
            string? resolvedFfmpegPath,
            string outputPath)
        {
            var sanitized = value;
            sanitized = ReplacePathVariants(sanitized, inputPath, "<INPUT_MP4>");
            sanitized = ReplacePathVariants(sanitized, SafeFullPath(inputPath), "<INPUT_MP4>");
            sanitized = ReplacePathVariants(sanitized, configuredFfmpegPath, "<FFMPEG_EXE>");
            sanitized = ReplacePathVariants(sanitized, SafeFullPath(configuredFfmpegPath), "<FFMPEG_EXE>");
            sanitized = ReplacePathVariants(sanitized, resolvedFfmpegPath, "<FFMPEG_EXE>");
            sanitized = ReplacePathVariants(sanitized, SafeFullPath(resolvedFfmpegPath), "<FFMPEG_EXE>");
            sanitized = ReplacePathVariants(sanitized, outputPath, "<OUTPUT_IMAGE>");
            sanitized = ReplacePathVariants(sanitized, SafeFullPath(outputPath), "<OUTPUT_IMAGE>");

            var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if (!string.IsNullOrWhiteSpace(userProfile))
                sanitized = ReplacePathVariants(sanitized, userProfile, "<USERPROFILE>");

            var userName = Environment.UserName;
            if (!string.IsNullOrWhiteSpace(userName))
                sanitized = sanitized.Replace(userName, "<USER>");

            return sanitized;
        }

        private static string SafeFullPath(string? path)
        {
            if (string.IsNullOrWhiteSpace(path))
                return "";

            var pathValue = path!;
            try
            {
                return Path.GetFullPath(pathValue);
            }
            catch
            {
                return pathValue;
            }
        }

        private static string ReplacePathVariants(string value, string? search, string replacement)
        {
            if (string.IsNullOrWhiteSpace(search))
                return value;

            var searchValue = search!;
            var updated = value.Replace(searchValue, replacement);
            updated = updated.Replace(searchValue.Replace('\\', '/'), replacement);
            updated = updated.Replace(searchValue.Replace('/', '\\'), replacement);
            return updated;
        }

        private static string Trim(string value, int max) =>
            string.IsNullOrEmpty(value) || value.Length <= max
                ? value
                : value.Substring(0, max) + "...";

        private static string EscapeMarkdown(string value) =>
            string.IsNullOrEmpty(value)
                ? ""
                : value.Replace("|", "\\|").Replace("\r", " ").Replace("\n", " ");
    }
}
