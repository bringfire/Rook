using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Common harness for PR-2 byte-identity goldens. Each PR-2 capture
    /// test routes its captured output through one of three checkers:
    /// <list type="bullet">
    ///   <item><see cref="AssertOrCapture"/> — semantic JSON equality
    ///         (canonicalized; tolerates whitespace / number-format drift).
    ///         Right for HTTP wire shapes and submit envelopes where the
    ///         JSON object structure is the contract.</item>
    ///   <item><see cref="AssertOrCaptureJsonl"/> — JSONL semantic equality
    ///         (per-line canonicalized).</item>
    ///   <item><see cref="AssertOrCaptureRawBytes"/> — literal byte-for-byte
    ///         equality. Right for ledger JSONL where the writer's exact
    ///         output (key order, no whitespace, line endings) is itself
    ///         the durability contract.</item>
    /// </list>
    ///
    /// <para>Default behavior: if the committed golden is absent, the
    /// assertion FAILS rather than silently writing a new file. This
    /// keeps an accidentally-deleted golden from being re-created during
    /// a routine test run and shipping in a drifted state. Set the env
    /// var <c>ROOK_UPDATE_GOLDENS=1</c> to switch to capture mode for an
    /// intentional regeneration session; the test still passes after
    /// writing.</para>
    ///
    /// <para>Goldens are committed to
    /// <c>src/Rook.Tests/Services/Vision/Video/Fixtures/Goldens/</c> and
    /// represent the V1c code path's output. Commits 2–5 must not change
    /// any captured byte; commit 6's parity tests assert the same goldens
    /// from the post-retrofit code paths and the assertion is the
    /// byte-identity proof.</para>
    /// </summary>
    internal static class VeoBehaviorParityFixture
    {
        // Set this env var to "1" / "true" to regenerate goldens
        // intentionally. Any other value (or unset) keeps the default
        // strict assert-only mode.
        private const string UpdateGoldensEnvVar = "ROOK_UPDATE_GOLDENS";

        private static bool UpdateMode()
        {
            var v = Environment.GetEnvironmentVariable(UpdateGoldensEnvVar);
            if (string.IsNullOrEmpty(v)) return false;
            return v == "1"
                || string.Equals(v, "true", StringComparison.OrdinalIgnoreCase);
        }
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
        /// Compare the captured JSON to the committed golden using
        /// semantic (canonical) equality. If the golden file is missing,
        /// the assertion FAILS by default to prevent silent recreation
        /// of an accidentally-deleted golden. Set
        /// <c>ROOK_UPDATE_GOLDENS=1</c> to regenerate intentionally.
        /// </summary>
        public static void AssertOrCapture(string filename, string capturedJson)
        {
            var path = GoldenPath(filename);
            var canonicalCaptured = Canonicalize(capturedJson);

            if (!File.Exists(path))
            {
                if (!UpdateMode())
                    throw new Xunit.Sdk.XunitException(
                        $"Golden missing: {filename}\n" +
                        $"Expected location: {path}\n" +
                        $"Set {UpdateGoldensEnvVar}=1 to capture intentionally.\n" +
                        $"--- captured ---\n{canonicalCaptured}\n");

                File.WriteAllText(path, canonicalCaptured);
                // Capture run still asserts so a second concurrent
                // assertion path (canonicalizer drift) would surface.
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
        /// JSONL variant of <see cref="AssertOrCapture"/>: per-line
        /// canonical equality. Use for cases where the JSONL is the
        /// semantic contract (line count + each line's JSON structure)
        /// but the writer's exact whitespace is not load-bearing.
        /// </summary>
        public static void AssertOrCaptureJsonl(string filename, string capturedJsonl)
        {
            var path = GoldenPath(filename);
            var canonicalCaptured = CanonicalizeJsonl(capturedJsonl);

            if (!File.Exists(path))
            {
                if (!UpdateMode())
                    throw new Xunit.Sdk.XunitException(
                        $"Golden missing (jsonl): {filename}\n" +
                        $"Expected location: {path}\n" +
                        $"Set {UpdateGoldensEnvVar}=1 to capture intentionally.\n" +
                        $"--- captured ---\n{canonicalCaptured}\n");

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

        /// <summary>
        /// Literal byte-for-byte comparison. Use this for the ledger
        /// JSONL goldens where the writer's exact output (key order, no
        /// whitespace, line endings) is the durability contract that
        /// PR-2 must preserve.
        ///
        /// <para>Line endings: the captured bytes are normalized to
        /// LF on the way in (file.Replace("\r\n","\n")) so a Windows
        /// vs. Linux runner does not flake the assertion. The committed
        /// golden also uses LF; the .gitattributes for the Goldens
        /// directory pins this if needed.</para>
        /// </summary>
        public static void AssertOrCaptureRawBytes(string filename, string capturedRaw)
        {
            var path = GoldenPath(filename);
            var captured = NormalizeLineEndings(capturedRaw);

            if (!File.Exists(path))
            {
                if (!UpdateMode())
                    throw new Xunit.Sdk.XunitException(
                        $"Golden missing (raw): {filename}\n" +
                        $"Expected location: {path}\n" +
                        $"Set {UpdateGoldensEnvVar}=1 to capture intentionally.\n" +
                        $"--- captured ---\n{captured}\n");

                File.WriteAllText(path, captured);
            }

            var golden = NormalizeLineEndings(File.ReadAllText(path));

            if (!string.Equals(golden, captured, StringComparison.Ordinal))
            {
                throw new Xunit.Sdk.XunitException(
                    $"Golden mismatch (raw bytes): {filename}\n" +
                    $"--- expected (golden) ---\n{golden}\n" +
                    $"--- actual (captured) ---\n{captured}\n");
            }
        }

        private static string NormalizeLineEndings(string s) =>
            s.Replace("\r\n", "\n");

        /// <summary>
        /// Replace the value of one or more JSON fields with a stable
        /// placeholder before asserting byte-identity. Used for
        /// ledger-transition goldens where a single field
        /// (<c>result_artifact_id</c>) is minted non-deterministically
        /// by <c>ArtifactStore</c>; the rest of the record is fully
        /// deterministic under the fake clock + id generator.
        ///
        /// <para>Match shape:
        /// <c>"&lt;fieldName&gt;": "&lt;guid&gt;"</c> (with optional
        /// whitespace), <c>guid</c> in any standard hex form. Only string
        /// values are matched, not numbers / nulls / objects.</para>
        /// </summary>
        public static string ReplaceGuidField(
            string source, string fieldName, string placeholder)
        {
            var pattern =
                "\"" + System.Text.RegularExpressions.Regex.Escape(fieldName) +
                "\"\\s*:\\s*\"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
                "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\"";
            var replacement = "\"" + fieldName + "\": \"" + placeholder + "\"";
            return System.Text.RegularExpressions.Regex.Replace(
                source, pattern, replacement);
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
