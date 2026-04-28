using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Common harness for PR-2 byte-identity goldens. Each PR-2 capture
    /// test routes its captured JSON through <see cref="AssertOrCapture"/>:
    /// on first run (golden absent on disk) the bytes are written and the
    /// test passes; on subsequent runs the bytes are compared to the
    /// committed golden and the test asserts equality.
    ///
    /// <para>Goldens are committed to
    /// <c>src/Rook.Tests/Services/Vision/Video/Fixtures/Goldens/</c> and
    /// represent the V1c code path's output. Commits 2–5 must not change
    /// any captured byte; commit 6's parity tests assert the same goldens
    /// from the post-retrofit code paths and the assertion is the
    /// byte-identity proof.</para>
    ///
    /// <para>Comparison is content-based via canonical
    /// <see cref="JsonNode"/> serialization; this avoids trailing-newline
    /// or whitespace drift across editors but still catches every
    /// semantic JSON difference. JSONL multi-line goldens are compared
    /// line-by-line through the same canonicalizer.</para>
    /// </summary>
    internal static class VeoBehaviorParityFixture
    {
        // Walk up from the test binary to find the repo root, then anchor
        // goldens at the source-tree path so they are committed alongside
        // the fixture class. Mirrors SymbolScanGuardTests's lookup pattern.
        private static string GoldensDir()
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                var candidate = Path.Combine(
                    dir.FullName,
                    "src", "Rook.Tests", "Services", "Vision", "Video",
                    "Fixtures", "Goldens");
                if (Directory.Exists(candidate)) return candidate;
                dir = dir.Parent;
            }
            throw new DirectoryNotFoundException(
                "Could not locate Goldens directory by walking up from " +
                AppContext.BaseDirectory);
        }

        public static string GoldenPath(string filename) =>
            Path.Combine(GoldensDir(), filename);

        /// <summary>
        /// Compare the captured JSON to the committed golden. If the
        /// golden file does not exist, write it (capture mode for first
        /// run / regeneration). Always asserts equality after the file
        /// is on disk. Canonicalization drops insignificant whitespace
        /// so editor settings cannot bit-rot a golden.
        /// </summary>
        public static void AssertOrCapture(string filename, string capturedJson)
        {
            var path = GoldenPath(filename);
            var canonicalCaptured = Canonicalize(capturedJson);

            if (!File.Exists(path))
            {
                // First run / regeneration: write the canonical form so
                // committed goldens are stable across editors.
                File.WriteAllText(path, canonicalCaptured);
                // Fall through and assert; this run's "expected" is the
                // file we just wrote, so the assertion trivially passes.
            }

            var goldenText = File.ReadAllText(path);
            var canonicalGolden = Canonicalize(goldenText);

            if (!string.Equals(canonicalGolden, canonicalCaptured, StringComparison.Ordinal))
            {
                throw new Xunit.Sdk.XunitException(
                    $"Golden mismatch: {filename}\n" +
                    $"--- expected (golden) ---\n{canonicalGolden}\n" +
                    $"--- actual (captured) ---\n{canonicalCaptured}\n");
            }
        }

        /// <summary>
        /// JSONL variant: each line is a separate JSON object. Compares
        /// line count and each line through the canonicalizer.
        /// </summary>
        public static void AssertOrCaptureJsonl(string filename, string capturedJsonl)
        {
            var path = GoldenPath(filename);
            var canonicalCaptured = CanonicalizeJsonl(capturedJsonl);

            if (!File.Exists(path))
            {
                File.WriteAllText(path, canonicalCaptured);
            }

            var goldenText = File.ReadAllText(path);
            var canonicalGolden = CanonicalizeJsonl(goldenText);

            if (!string.Equals(canonicalGolden, canonicalCaptured, StringComparison.Ordinal))
            {
                throw new Xunit.Sdk.XunitException(
                    $"Golden mismatch (jsonl): {filename}\n" +
                    $"--- expected (golden) ---\n{canonicalGolden}\n" +
                    $"--- actual (captured) ---\n{canonicalCaptured}\n");
            }
        }

        // Reformat through JsonNode + a deterministic indented writer.
        // Property order is preserved (System.Text.Json keeps insertion
        // order on JsonObject), so the canonicalizer normalizes only
        // whitespace and number formatting — semantic differences still
        // surface as mismatches.
        private static string Canonicalize(string json)
        {
            if (string.IsNullOrWhiteSpace(json)) return string.Empty;
            var node = JsonNode.Parse(json);
            return node?.ToJsonString(IndentedOptions) ?? string.Empty;
        }

        private static string CanonicalizeJsonl(string jsonl)
        {
            var lines = jsonl.Replace("\r\n", "\n").Split('\n');
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < lines.Length; i++)
            {
                if (string.IsNullOrWhiteSpace(lines[i])) continue;
                if (sb.Length > 0) sb.Append('\n');
                sb.Append(Canonicalize(lines[i]));
            }
            // Trailing newline so editors that auto-add one don't break
            // the canonical form across edits.
            sb.Append('\n');
            return sb.ToString();
        }

        private static readonly JsonSerializerOptions IndentedOptions = new()
        {
            WriteIndented = true,
        };
    }
}
