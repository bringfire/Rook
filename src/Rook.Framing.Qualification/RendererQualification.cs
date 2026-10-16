using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Runtime.Versioning;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Video.Framing;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Generation;

namespace Rook.Framing.Qualification
{
    internal static class RendererQualification
    {
        public static async Task<int> RunAsync(string binary, string fixtures, string report)
        {
            binary = Path.GetFullPath(binary); fixtures = Path.GetFullPath(fixtures);
            using var golden = JsonDocument.Parse(File.ReadAllText(Path.Combine(fixtures, "qualified-profile.json")));
            Program.Require(golden.RootElement.GetProperty("renderer_sha256").GetString() == VideoFramingRendererProfile.Sha256, "Golden profile belongs to another binary.");
            using (var sha = SHA256.Create())
                Program.Require(BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(Path.Combine(fixtures, "manifest.json")))).Replace("-", "") == golden.RootElement.GetProperty("fixture_manifest_sha256").GetString(), "Fixture manifest changed without qualification.");
            var expectedHashes = golden.RootElement.GetProperty("outputs").EnumerateArray().ToDictionary(x => x.GetProperty("key").GetString()!, x => x.GetProperty("prepared_sha256").GetString()!);
            var runner = new DiagnosticRunner();
            var renderer = new FfmpegVideoSourceRenderer(runner, () => binary);
            var resources = new VideoPreparationResources();
            var cases = new List<(string File, string Resolution, string Aspect, SourceFramingMode Mode)>();
            string[] images = { "rgb-1166x912.png", "rgb-1166x912.jpg", "rgb-1166x912-lossless.webp", "rgb-1166x912-lossy.webp", "alpha.png", "alpha.webp", "depth16.png", "palette.png", "portrait.png", "square.png", "matching.png", "odd-119x73.png", "thin.png", "extreme-16384x720.png", "orientation-6.png", "orientation-6.webp" };
            foreach (var file in images.Concat(new[] { "rgb-icc-private.png" }).Concat(Enumerable.Range(1, 8).Select(n => $"orientation-{n}.jpg"))) cases.Add((file, "720p", "16:9", SourceFramingMode.Fit));
            foreach (var res in new[] { "720p", "1080p", "4k" }) foreach (var aspect in new[] { "16:9", "9:16" }) foreach (var mode in new[] { SourceFramingMode.Fit, SourceFramingMode.Fill }) cases.Add(("rgb-1166x912.png", res, aspect, mode));
            cases.Add(("extreme-16384x720.png", "4k", "9:16", SourceFramingMode.Fit));
            var records = new List<object>(); var hashes = new Dictionary<string, string>();
            foreach (var test in cases)
            {
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                using var phase = await resources.AcquireAsync(deadline.Token);
                using var original = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(Path.Combine(fixtures, test.File)), phase.Buffers);
                var inspected = VideoStillImageInspector.Inspect(original, "start_frame"); Program.Require(inspected.Error == null, "Inspection failed: " + test.File);
                var info = inspected.Info!;
                var geometry = VideoFramingGeometry.Create(info, test.Resolution, test.Aspect, test.Mode, "start_frame");
                Program.Require(geometry.Error == null, "Geometry failed: " + test);
                var recipe = new VideoFramingRecipe(test.Mode, info, geometry.Layout!, VideoFramingRendererProfile.Sha256);
                var result = await renderer.RenderAsync(original, info, recipe, phase, deadline.Token);
                Program.Require(result.Source != null, "Render failed: " + test + " " + JsonSerializer.Serialize(result.Error) + " output=" + runner.OutputInfo);
                using var output = result.Source!;
                var pixels = ReadRgb(output.Bytes);
                CheckPixels(test.File, recipe, pixels, fixtures);
                string key = $"{test.File}/{test.Resolution}/{test.Aspect}/{test.Mode}";
                Program.Require(expectedHashes.TryGetValue(key, out var expectedHash) && expectedHash == output.Bytes.Sha256, "Frozen content oracle changed: " + key);
                if (hashes.TryGetValue(key, out var previous)) Program.Require(previous == output.Bytes.Sha256, "Repeat render changed bytes: " + key);
                hashes[key] = output.Bytes.Sha256;
                records.Add(new { key, original = original.Sha256, prepared = output.Bytes.Sha256, bytes = output.Bytes.Length, recipe = output.Recipe.Canonical(), output.PeakJobChargeBytes, phase.Buffers.PeakReservedBytes });
                Console.WriteLine("PASS " + key);
            }
            // True encoded-limit fallback on deterministic, incompressible 4k pixels.
            string stress = Path.GetFullPath(Path.Combine(fixtures, "..", "..", "..", "..", "artifacts", "video-framing-fixtures", "generated-noise-4k.png"));
            Program.Require(File.Exists(stress), "Generate the manifest's --include-noise fixture before qualification.");
            using (var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15)))
            using (var phase = await resources.AcquireAsync(deadline.Token))
            using (var original = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(stress), phase.Buffers))
            {
                var info = VideoStillImageInspector.Inspect(original, "start_frame").Info!;
                var layout = VideoFramingGeometry.Create(info, "4k", "16:9", SourceFramingMode.Fit, "start_frame").Layout!;
                var result = await renderer.RenderAsync(original, info, new(SourceFramingMode.Fit, info, layout, VideoFramingRendererProfile.Sha256), phase, deadline.Token);
                Program.Require(result.Source != null, "Noise fallback failed: " + JsonSerializer.Serialize(result.Error) + " output=" + runner.OutputInfo);
                using var output = result.Source!; Program.Require(output.Recipe.Encoding == "mjpeg" && output.Bytes.Length <= 8_000_000, "Real PNG did not fall back to a bounded JPEG.");
                using (var jpeg = output.Bytes.OpenRead())
                using (var decoded = new System.Drawing.Bitmap(jpeg))
                {
                    Program.Require(decoded.Width == 3840 && decoded.Height == 2160, "Independent JPEG decoder disagrees with canvas.");
                    var expected = ReadRgb(original); int totalError = 0;
                    for (int n = 0; n < 64; n++)
                    {
                        int x = (n * 131 + 19) % 3840, y = (n * 79 + 41) % 2160; var pixel = decoded.GetPixel(x, y);
                        Program.Require(Math.Abs(pixel.R - pixel.G) <= 2 && Math.Abs(pixel.G - pixel.B) <= 2, "Grayscale JPEG acquired chroma.");
                        totalError += Math.Abs(pixel.R - expected[(y * 3840 + x) * 3]);
                    }
                    Program.Require(totalError <= 64 * 12, "Independent JPEG pixel oracle exceeded quantization tolerance.");
                }
                Program.Require(expectedHashes["noise-4k/fallback"] == output.Bytes.Sha256, "Frozen JPEG fallback content oracle changed.");
                records.Add(new { key = "noise-4k/fallback", original = original.Sha256, prepared = output.Bytes.Sha256, bytes = output.Bytes.Length, recipe = output.Recipe.Canonical(), output.PeakJobChargeBytes });
            }
            var legacy = new List<object>();
            var legacyDecoder = new FfmpegVideoSourceValidator(bundledPath: () => binary);
            foreach (var test in new[] {
                ("matching.png", true), ("rgb-1166x912.jpg", true), ("rgb-1166x912-lossless.webp", true), ("rgb-1166x912-lossy.webp", true),
                ("legacy-validation/legacy-single.apng.png", true), ("legacy-validation/empty-idat.png", false),
                ("legacy-validation/empty-scan.jpg", false), ("legacy-validation/empty-vp8l.webp", false),
                ("legacy-validation/short-rows-360.png", false), ("legacy-validation/short-rows-719.png", false) })
            {
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                using var phase = await resources.AcquireAsync(deadline.Token);
                var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
                var original = File.ReadAllBytes(Path.Combine(fixtures, test.Item1));
                string mime = test.Item1.EndsWith("jpg") ? "image/jpeg" : test.Item1.EndsWith("webp") ? "image/webp" : "image/png";
                var request = new VideoGenerationRequest("fal-ai/veo3.1", VideoMode.I2V, 8, "720p", "16:9", "synthetic", reference, null, null, null, new FalVeoOptions(), 1);
                using var snapshot = VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> { [reference] = new(original, mime) }, phase);
                string before = snapshot.Slots[0].Sha256;
                var error = await legacyDecoder.ValidateAsync(snapshot.Slots[0], phase, deadline.Token);
                Program.Require((error == null) == test.Item2, "Legacy pixel validation disagrees: " + test.Item1 + " " + JsonSerializer.Serialize(error));
                Program.Require(before == snapshot.Slots[0].Sha256, "Validation changed original bytes.");
                legacy.Add(new { file = test.Item1, original = before, accepted = error == null, detail = error?.ProviderErrorCode });
            }
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(report))!);
            File.WriteAllText(report, JsonSerializer.Serialize(new { framework = Assembly.GetExecutingAssembly().GetCustomAttribute<TargetFrameworkAttribute>()!.FrameworkName,
                os = Environment.OSVersion.ToString(), binary, renderer = VideoFramingRendererProfile.Sha256, records, legacy_validation = legacy }, new JsonSerializerOptions { WriteIndented = true }));
            Console.WriteLine("PASS renderer qualification: " + report); return 0;
        }
        private sealed class DiagnosticRunner : IFramingProcessRunner
        {
            public string? OutputInfo;
            public async Task<FramingProcessResult> RunAsync(FramingProcessRequest request, CancellationToken ct)
            {
                var run = await new WindowsFramingProcessRunner().RunAsync(request, ct);
                OutputInfo = run.Diagnostics;
                if (File.Exists(request.OutputPath) && new FileInfo(request.OutputPath).Length <= 8_000_000)
                {
                    using var bytes = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(request.OutputPath), new VideoBufferBudget());
                    OutputInfo += JsonSerializer.Serialize(VideoStillImageInspector.Inspect(bytes, "output"));
                }
                return run;
            }
        }
        private static void CheckPixels(string file, VideoFramingRecipe recipe, byte[] rgb, string fixtures)
        {
            var l = recipe.Layout;
            (int R, int G, int B) At(int x, int y) { int p = (y * l.CanvasWidth + x) * 3; return (rgb[p], rgb[p + 1], rgb[p + 2]); }
            void Near((int R, int G, int B) actual, (int R, int G, int B) expected, int tolerance)
            { Program.Require(Math.Abs(actual.R - expected.R) <= tolerance && Math.Abs(actual.G - expected.G) <= tolerance && Math.Abs(actual.B - expected.B) <= tolerance, $"Pixel mismatch {file} {actual} expected {expected}."); }
            if (recipe.Mode == SourceFramingMode.Fit)
            {
                if (l.OffsetX > 0 || l.OffsetY > 0) Near(At(0, 0), (0, 0, 0), 0);
                if (file is "alpha.png" or "alpha.webp")
                { Near(At(l.OffsetX + l.ScaledWidth / 10, l.OffsetY + l.ScaledHeight / 2), (0, 0, 0), 0); Near(At(l.OffsetX + l.ScaledWidth * 3 / 4, l.OffsetY + l.ScaledHeight / 2), (120, 20, 10), 2); }
                if (file == "depth16.png")
                { int gray = (40 * 511 + 36 * 73) / 257; Near(At(l.OffsetX + l.ScaledWidth * 40 / 128, l.OffsetY + l.ScaledHeight * 36 / 96), (gray, gray, gray), 4); }
                if (file == "palette.png")
                { Near(At(l.OffsetX + l.ScaledWidth * 68 / 128, l.OffsetY + l.ScaledHeight * 52 / 96), (14, 42, 98), 1); Near(At(l.OffsetX + l.ScaledWidth * 3 / 128, l.OffsetY + l.ScaledHeight * 3 / 96), (0, 0, 0), 0); }
                if (file.StartsWith("orientation-") && file.EndsWith(".jpg"))
                {
                    int n = int.Parse(file.Substring(12, 1));
                    using var oracle = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(Path.Combine(fixtures, $"orientation-{n}-oracle.png")), new VideoBufferBudget());
                    var oi = VideoStillImageInspector.Inspect(oracle, "oracle").Info!; var expected = ReadRgb(oracle);
                    foreach (var p in new[] { (1, 5), (9, 5), (5, 1), (5, 9), (5, 5) })
                    { int x = oi.Width * p.Item1 / 10, y = oi.Height * p.Item2 / 10, offset = (y * oi.Width + x) * 3;
                      Near(At(l.OffsetX + l.ScaledWidth * p.Item1 / 10, l.OffsetY + l.ScaledHeight * p.Item2 / 10), (expected[offset], expected[offset + 1], expected[offset + 2]), 5); }
                }
            }
            if (file == "rgb-1166x912.png" && l.CanvasWidth == 1920 && recipe.Mode == SourceFramingMode.Fit)
            { Near(At(960, 10), (240, 20, 20), 0); Near(At(960, 1070), (20, 240, 20), 0); Near(At(280, 540), (20, 20, 240), 0); Near(At(1640, 540), (240, 220, 20), 0); }
            if (file == "rgb-1166x912.png" && l.CanvasWidth == 1920 && recipe.Mode == SourceFramingMode.Fill) Near(At(960, 10), (180, 180, 180), 0);
        }
        // Independent qualification-only PNG scanline decoder, no product dependency.
        private static byte[] ReadRgb(VideoFrozenBuffer buffer)
        {
            using var source = buffer.OpenRead(); using var encoded = new BinaryReader(source); source.Position = 8;
            int width = 0, height = 0, components = 0; using var idat = new MemoryStream();
            int Big() { var b = encoded.ReadBytes(4); return checked((int)((uint)b[0] << 24 | (uint)b[1] << 16 | (uint)b[2] << 8 | b[3])); }
            while (source.Position < source.Length)
            {
                int size = Big(); string type = System.Text.Encoding.ASCII.GetString(encoded.ReadBytes(4));
                if (type == "IHDR") { width = Big(); height = Big(); int depth = encoded.ReadByte(), color = encoded.ReadByte(); Program.Require(depth == 8 && (color == 0 || color == 2 || color == 6), "Qualification expects gray/RGB/RGBA8 PNG."); components = color == 0 ? 1 : color == 2 ? 3 : 4; source.Position += size - 10; }
                else if (type == "IDAT") { var bytes = encoded.ReadBytes(size); idat.Write(bytes, 0, bytes.Length); }
                else source.Position += size;
                source.Position += 4;
            }
            idat.Position = 2; using var inflate = new DeflateStream(idat, CompressionMode.Decompress); int stride = width * components;
            var previous = new byte[stride]; var row = new byte[stride]; var result = new byte[width * height * 3];
            for (int y = 0; y < height; y++)
            {
                int filter = inflate.ReadByte(); int total = 0; while (total < stride) { int read = inflate.Read(row, total, stride - total); Program.Require(read > 0, "Truncated PNG pixels."); total += read; }
                for (int x = 0; x < stride; x++)
                {
                    int a = x >= components ? row[x - components] : 0, b = previous[x], c = x >= components ? previous[x - components] : 0;
                    int p = a + b - c, pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
                    int predictor = filter switch { 0 => 0, 1 => a, 2 => b, 3 => (a + b) / 2, 4 => pa <= pb && pa <= pc ? a : pb <= pc ? b : c, _ => throw new InvalidDataException("Bad PNG filter.") };
                    row[x] = unchecked((byte)(row[x] + predictor));
                }
                for (int x = 0; x < width; x++)
                { if (components == 1) { for (int c = 0; c < 3; c++) result[(y * width + x) * 3 + c] = row[x]; } else Buffer.BlockCopy(row, x * components, result, (y * width + x) * 3, 3); }
                var swap = previous; previous = row; row = swap;
            }
            return result;
        }
    }
}
