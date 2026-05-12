using System;
using System.IO;
using System.Text;
using Xunit;

namespace Rook.Tests.Plugin
{
    public class RookPluginLifecycleSourceTests
    {
        [Fact]
        public void StartupVideoReconcileFailure_IsCaughtAndLoggedAsNonFatal()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");
            var tryInitializeRuntime = ExtractMethod(source, "private void TryInitializeRuntime()");

            Assert.Contains("BeginStartupRetries();", onLoad);
            Assert.Contains("RhinoApp.InvokeOnUiThread(new Action(TryInitializeRuntime));", onLoad);
            Assert.Contains("return LoadReturnCode.Success;", onLoad);

            var reconcileBlock = ExtractTryCatchContaining(
                tryInitializeRuntime,
                "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();");

            Assert.Contains(
                "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();",
                reconcileBlock.TryBody);
            Assert.Contains(
                "TraceStartup(\"Video subsystem reconciled",
                reconcileBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video reconcile failed (non-fatal):",
                reconcileBlock.CatchBody);
            Assert.Contains(
                "continuing without reconcile",
                reconcileBlock.CatchBody);
            Assert.DoesNotContain("throw", reconcileBlock.CatchBody);
        }

        [Fact]
        public void ShutdownExternalTeardownSteps_HaveIndependentTryCatchWrappers()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onShutdown = ExtractMethod(source, "protected override void OnShutdown()");
            var steps = new[]
            {
                new TeardownStep(
                    "NativeGhBridgeRegistrar.ClearRegistration();",
                    "Native GH bridge clear failed"),
                new TeardownStep(
                    "ChatServiceManager.Instance.Shutdown();",
                    "Chat service shutdown failed"),
                new TeardownStep(
                    "RookSubsystemRoot.Instance.DisposeVideoSubsystemIfCreated();",
                    "Video subsystem dispose failed"),
            };

            foreach (var step in steps)
            {
                var block = ExtractTryCatchContaining(onShutdown, step.Call);

                Assert.Contains(step.Call, block.TryBody);
                Assert.Contains(step.FailureLog, block.CatchBody);
                Assert.DoesNotContain("throw", block.CatchBody);

                foreach (var other in steps)
                {
                    if (ReferenceEquals(step, other))
                        continue;

                    Assert.DoesNotContain(other.Call, block.TryBody);
                }
            }
        }

        [Fact]
        public void StartupVideoSidecarBackfill_IsScheduledAsSeparateNonFatalAsyncStep()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var tryInitializeRuntime = ExtractMethod(source, "private void TryInitializeRuntime()");

            var reconcileBlock = ExtractTryCatchContaining(
                tryInitializeRuntime,
                "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();");
            Assert.DoesNotContain("BackfillVideoSidecarsOnce", reconcileBlock.TryBody);

            var backfillBlock = ExtractTryCatchContaining(
                tryInitializeRuntime,
                "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(");

            Assert.Contains(
                "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(",
                backfillBlock.TryBody);
            Assert.Contains(
                "VideoSidecarBackfillStartupOptions",
                backfillBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video sidecar backfill completed:",
                backfillBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video sidecar backfill failed (non-fatal):",
                backfillBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video sidecar backfill scheduling failed (non-fatal):",
                backfillBlock.CatchBody);
            Assert.DoesNotContain("throw", backfillBlock.CatchBody);
        }

        [Fact]
        public void ShutdownBaseCall_RemainsAfterAndOutsideTeardownTryCatchWrappers()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onShutdown = ExtractMethod(source, "protected override void OnShutdown()");

            var baseCallIndex = onShutdown.IndexOf("base.OnShutdown();", StringComparison.Ordinal);
            Assert.True(baseCallIndex >= 0, "base.OnShutdown() must remain in OnShutdown.");

            Assert.True(
                baseCallIndex > onShutdown.IndexOf(
                    "NativeGhBridgeRegistrar.ClearRegistration();",
                    StringComparison.Ordinal),
                "base.OnShutdown() must remain after bridge registration cleanup.");
            Assert.True(
                baseCallIndex > onShutdown.IndexOf(
                    "ChatServiceManager.Instance.Shutdown();",
                    StringComparison.Ordinal),
                "base.OnShutdown() must remain after chat service shutdown.");
            Assert.True(
                baseCallIndex > onShutdown.IndexOf(
                    "RookSubsystemRoot.Instance.DisposeVideoSubsystemIfCreated();",
                    StringComparison.Ordinal),
                "base.OnShutdown() must remain after video subsystem disposal.");

            Assert.Throws<InvalidOperationException>(
                () => ExtractTryCatchContaining(onShutdown, "base.OnShutdown();"));
        }

        private static TryCatchBlock ExtractTryCatchContaining(
            string source,
            string containedText)
        {
            var searchStart = 0;
            while (searchStart < source.Length)
            {
                var tryIndex = source.IndexOf("try", searchStart, StringComparison.Ordinal);
                if (tryIndex < 0)
                    break;

                if (!IsStandaloneWord(source, tryIndex, "try".Length))
                {
                    searchStart = tryIndex + "try".Length;
                    continue;
                }

                var bodyStart = source.IndexOf('{', tryIndex);
                if (bodyStart < 0)
                    break;

                var betweenKeywordAndBody = source.Substring(
                    tryIndex + "try".Length,
                    bodyStart - tryIndex - "try".Length);
                if (!string.IsNullOrWhiteSpace(betweenKeywordAndBody))
                {
                    searchStart = tryIndex + "try".Length;
                    continue;
                }

                var bodyEnd = FindMatchingBrace(source, bodyStart);
                var tryBody = source.Substring(bodyStart + 1, bodyEnd - bodyStart - 1);
                if (!tryBody.Contains(containedText))
                {
                    searchStart = bodyEnd + 1;
                    continue;
                }

                var catchIndex = NextNonWhitespaceIndex(source, bodyEnd + 1);
                if (!StartsWithAt(source, catchIndex, "catch"))
                {
                    searchStart = tryIndex + "try".Length;
                    continue;
                }

                var catchBodyStart = source.IndexOf('{', catchIndex);
                if (catchBodyStart < 0)
                    throw new InvalidOperationException(
                        "catch body not found for text: " + containedText);

                var catchBodyEnd = FindMatchingBrace(source, catchBodyStart);
                var catchBody = source.Substring(
                    catchBodyStart + 1,
                    catchBodyEnd - catchBodyStart - 1);
                return new TryCatchBlock(tryBody, catchBody);
            }

            throw new InvalidOperationException(
                "try/catch block not found for text: " + containedText);
        }

        private static string ExtractMethod(string source, string signatureStartText)
        {
            var signatureStart = source.IndexOf(
                signatureStartText,
                StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException(
                    "Method not found: " + signatureStartText);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException(
                    "Method body not found: " + signatureStartText);

            var bodyEnd = FindMatchingBrace(source, bodyStart);
            return source.Substring(signatureStart, bodyEnd - signatureStart + 1);
        }

        private static int FindMatchingBrace(string source, int openBraceIndex)
        {
            var depth = 0;
            for (var i = openBraceIndex; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return i;
                }
            }

            throw new InvalidOperationException(
                "Brace did not close at index " + openBraceIndex);
        }

        private static int NextNonWhitespaceIndex(string source, int start)
        {
            for (var i = start; i < source.Length; i++)
            {
                if (!char.IsWhiteSpace(source[i]))
                    return i;
            }

            return source.Length;
        }

        private static bool StartsWithAt(string source, int index, string value)
        {
            return index >= 0
                && index + value.Length <= source.Length
                && string.Compare(
                    source,
                    index,
                    value,
                    0,
                    value.Length,
                    StringComparison.Ordinal) == 0;
        }

        private static bool IsStandaloneWord(string source, int index, int length)
        {
            var before = index == 0 ? '\0' : source[index - 1];
            var afterIndex = index + length;
            var after = afterIndex >= source.Length ? '\0' : source[afterIndex];
            return !IsIdentifierChar(before) && !IsIdentifierChar(after);
        }

        private static bool IsIdentifierChar(char value)
        {
            return char.IsLetterOrDigit(value) || value == '_';
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return RemoveComments(File.ReadAllText(candidate));

                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private static string RemoveComments(string source)
        {
            var builder = new StringBuilder(source.Length);
            var inLineComment = false;
            var inBlockComment = false;
            var inString = false;
            var inVerbatimString = false;
            var inChar = false;

            for (var i = 0; i < source.Length; i++)
            {
                var current = source[i];
                var next = i + 1 < source.Length ? source[i + 1] : '\0';

                if (inLineComment)
                {
                    if (current == '\r' || current == '\n')
                    {
                        inLineComment = false;
                        builder.Append(current);
                    }
                    else
                    {
                        builder.Append(' ');
                    }

                    continue;
                }

                if (inBlockComment)
                {
                    if (current == '*' && next == '/')
                    {
                        builder.Append("  ");
                        i++;
                        inBlockComment = false;
                    }
                    else
                    {
                        builder.Append(current == '\r' || current == '\n' ? current : ' ');
                    }

                    continue;
                }

                if (inString)
                {
                    builder.Append(current);

                    if (inVerbatimString)
                    {
                        if (current == '"' && next == '"')
                        {
                            builder.Append(next);
                            i++;
                        }
                        else if (current == '"')
                        {
                            inString = false;
                            inVerbatimString = false;
                        }
                    }
                    else if (current == '\\' && next != '\0')
                    {
                        builder.Append(next);
                        i++;
                    }
                    else if (current == '"')
                    {
                        inString = false;
                    }

                    continue;
                }

                if (inChar)
                {
                    builder.Append(current);

                    if (current == '\\' && next != '\0')
                    {
                        builder.Append(next);
                        i++;
                    }
                    else if (current == '\'')
                    {
                        inChar = false;
                    }

                    continue;
                }

                if (current == '/' && next == '/')
                {
                    builder.Append("  ");
                    i++;
                    inLineComment = true;
                    continue;
                }

                if (current == '/' && next == '*')
                {
                    builder.Append("  ");
                    i++;
                    inBlockComment = true;
                    continue;
                }

                if (current == '"')
                {
                    inString = true;
                    inVerbatimString = IsVerbatimStringStart(source, i);
                    builder.Append(current);
                    continue;
                }

                if (current == '\'')
                {
                    inChar = true;
                    builder.Append(current);
                    continue;
                }

                builder.Append(current);
            }

            return builder.ToString();
        }

        private static bool IsVerbatimStringStart(string source, int quoteIndex)
        {
            return quoteIndex > 0 && source[quoteIndex - 1] == '@'
                || quoteIndex > 1
                && source[quoteIndex - 2] == '@'
                && source[quoteIndex - 1] == '$';
        }

        private sealed class TeardownStep
        {
            public TeardownStep(string call, string failureLog)
            {
                Call = call;
                FailureLog = failureLog;
            }

            public string Call { get; }

            public string FailureLog { get; }
        }

        private sealed class TryCatchBlock
        {
            public TryCatchBlock(string tryBody, string catchBody)
            {
                TryBody = tryBody;
                CatchBody = catchBody;
            }

            public string TryBody { get; }

            public string CatchBody { get; }
        }
    }
}
