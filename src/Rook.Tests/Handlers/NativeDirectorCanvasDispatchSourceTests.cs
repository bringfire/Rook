using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class NativeDirectorCanvasDispatchSourceTests
    {
        [Fact]
        public void DirectorCanvasExtractRoute_IsRegisteredUnderDirectorCanvas()
        {
            var server = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.Contains("\"/director/canvas/extract\"", server);
            Assert.Contains("HandleDirectorCanvasExtract(req, res);", server);
        }

        [Fact]
        public void DirectorCanvasExtractHandler_InjectsExtractOpAndUsesCanvasDirectorDispatch()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "DirectorHandler.cpp");
            var handler = ExtractFunction(source, "HandleDirectorCanvasExtract");

            Assert.Contains("body[\"op\"] = \"extract\";", handler);
            Assert.Contains("InvokeCanvasDirectorDispatchWithBody", handler);
            Assert.Contains("CRookServer::SendErrorData", handler);
            Assert.Contains("MakeErrorData(\"invalid_input\"", handler);
            Assert.Contains("canvas_director_unavailable", handler);
            Assert.Contains("canvas_director_dispatch_failed", handler);
            Assert.Contains("X-Rook-Director-Canvas-Op", handler);
            Assert.DoesNotContain("CMainThreadDispatcher::Instance().Dispatch", handler);
            Assert.DoesNotContain("CRhinoDoc::", handler);
            Assert.DoesNotContain("RunScript", handler);
        }

        [Fact]
        public void GrasshopperProxy_DeclaresCanvasDirectorDispatchCallback()
        {
            var header = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.h");
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

            Assert.Contains("bool HasCanvasDirectorDispatchRegistration();", header);
            Assert.Contains("InvokeCanvasDirectorDispatchWithBody", header);
            Assert.Contains("canvas_director_dispatch", source);
            Assert.Contains("HasCanvasDirectorDispatchRegistration", source);
            Assert.Contains("InvokeCanvasDirectorDispatchWithBody", source);
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
            throw new FileNotFoundException("Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
