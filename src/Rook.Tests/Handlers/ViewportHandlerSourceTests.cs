using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class ViewportHandlerSourceTests
    {
        [Fact]
        public void ViewportTier3Unavailable_AddsDiagnosticAndPreservesTransportContract()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "ViewportHandler.cpp");
            var handleViewport = ExtractFunction(source, "HandleViewport");
            var unavailableBranch = ExtractBetween(
                handleViewport,
                "case ManagedCreateInvokeResult::Unavailable:",
                "case ManagedCreateInvokeResult::Failed:");

            Assert.Contains("BuildViewportCaptureCallbackUnavailable", unavailableBranch);
            Assert.Contains("CRookServer::SendErrorWithDiagnostic", unavailableBranch);
            Assert.Contains("res.status = 503;", unavailableBranch);
            Assert.Contains("res.set_header(\"X-Rook-Viewport-Backend\", \"tier3-unavailable\");", unavailableBranch);
        }

        [Fact]
        public void ViewportDiagnostics_DoNotMapUnknownBackendOrManagedFailedBranches()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "ViewportHandler.cpp");
            var handleViewport = ExtractFunction(source, "HandleViewport");

            var unknownBackendBranch = ExtractBetween(
                handleViewport,
                "if (!captureBackend.empty()",
                "if (captureBackend == \"tier3\")");
            Assert.Contains("Unknown captureBackend '", unknownBackendBranch);
            Assert.Contains("Expected 'legacy' or 'tier3' (or omit the field).", unknownBackendBranch);
            Assert.Contains("CRookServer::SendError(res,", unknownBackendBranch);
            Assert.Contains("res.status = 400;", unknownBackendBranch);
            Assert.DoesNotContain("SendErrorWithDiagnostic", unknownBackendBranch);

            var failedBranch = ExtractBetween(
                handleViewport,
                "case ManagedCreateInvokeResult::Failed:",
                "}");
            Assert.Contains("CRookServer::SendError(res,", failedBranch);
            Assert.Contains("Tier 3 viewport capture failed:", failedBranch);
            Assert.Contains("+ invokeError", failedBranch);
            Assert.Contains("res.status = 500;", failedBranch);
            Assert.Contains("res.set_header(\"X-Rook-Viewport-Backend\", \"tier3-failed\");", failedBranch);
            Assert.DoesNotContain("SendErrorWithDiagnostic", failedBranch);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName, StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Function body not found: " + functionName);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException("Function body did not close: " + functionName);
        }

        private static string ExtractBetween(string source, string start, string end)
        {
            var startIndex = source.IndexOf(start, StringComparison.Ordinal);
            Assert.True(startIndex >= 0, "Could not find start marker: " + start);

            var endIndex = source.IndexOf(end, startIndex + start.Length, StringComparison.Ordinal);
            Assert.True(endIndex >= 0, "Could not find end marker: " + end);

            return source.Substring(startIndex, endIndex - startIndex);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
