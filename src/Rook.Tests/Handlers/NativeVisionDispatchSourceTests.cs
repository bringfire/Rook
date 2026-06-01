using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class NativeVisionDispatchSourceTests
    {
        [Fact]
        public void DispatchVisionOpWithPathId_InjectsPathIdUsingSuppliedFieldName()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var helper = ExtractFunction(source, "DispatchVisionOpWithPathId");

            Assert.Contains("const char* path_id_field", helper);
            Assert.Contains("body[path_id_field] = req.matches[1].str();", helper);
            Assert.DoesNotContain("body[\"artifact_id\"] =", helper);
            Assert.DoesNotContain("body[\"job_id\"] =", helper);
        }

        [Theory]
        [InlineData("HandleVisionGetArtifact", "get_artifact", "artifact_id")]
        [InlineData("HandleVisionApproveArtifact", "approve_artifact", "artifact_id")]
        [InlineData("HandleVisionDeleteArtifact", "delete_artifact", "artifact_id")]
        public void ArtifactPathRoutes_InjectArtifactId(
            string handlerName,
            string op,
            string fieldName)
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(source, handlerName);

            Assert.Contains(
                $"DispatchVisionOpWithPathId(req, res, \"{op}\", \"{fieldName}\");",
                handler);
        }

        [Theory]
        [InlineData("HandleVisionVideoStatus", "get_video_job", "job_id")]
        [InlineData("HandleVisionVideoCancel", "cancel_video_job", "job_id")]
        [InlineData("HandleVisionVideoResult", "get_video_job_result", "job_id")]
        public void VideoPathRoutes_InjectJobId(
            string handlerName,
            string op,
            string fieldName)
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(source, handlerName);

            Assert.Contains(
                $"DispatchVisionOpWithPathId(req, res, \"{op}\", \"{fieldName}\");",
                handler);
            Assert.DoesNotContain(
                $"DispatchVisionOpWithPathId(req, res, \"{op}\", \"artifact_id\");",
                handler);
        }

        [Fact]
        public void VisionVideoModelsRoute_IsSliceOneDiagnosticExample()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(source, "HandleVisionVideoModelsList");

            Assert.Contains("BuildVisionDispatchCallbackUnavailable", source);
            Assert.Contains("\"GET /vision/video/models\"", handler);
            Assert.Contains("\"list_video_models\"", handler);
            Assert.Contains("ForwardVisionDispatch", handler);
            Assert.DoesNotContain("CMainThreadDispatcher::Instance().Dispatch", handler);
            Assert.DoesNotContain("CRhinoDoc::", handler);
            Assert.DoesNotContain("RunScript", handler);
        }

        [Fact]
        public void VisionDispatchDiagnostic_IsOnlyEmittedForOptedInUnavailablePath()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var helper = ExtractFunction(source, "ForwardVisionDispatch");
            var generateHandler = ExtractFunction(source, "HandleVisionGenerate");
            var modelsHandler = ExtractFunction(source, "HandleVisionVideoModelsList");

            Assert.Single(FindAll(source, "BuildVisionDispatchCallbackUnavailable("));
            Assert.Contains("const nlohmann::json* unavailableDiagnostic", helper);
            Assert.Contains("if (unavailableDiagnostic != nullptr)", helper);
            Assert.Contains("CRookServer::SendErrorWithDiagnostic", helper);
            Assert.Contains("CRookServer::SendError(", helper);
            Assert.DoesNotContain("BuildVisionDispatchCallbackUnavailable", generateHandler);
            Assert.Contains("BuildVisionDispatchCallbackUnavailable", modelsHandler);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signature = "void " + functionName + "(";
            var signatureStart = source.IndexOf(signature, StringComparison.Ordinal);
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

        private static string[] FindAll(string source, string needle)
        {
            var matches = new System.Collections.Generic.List<string>();
            var index = 0;
            while (true)
            {
                index = source.IndexOf(needle, index, StringComparison.Ordinal);
                if (index < 0)
                    return matches.ToArray();
                matches.Add(needle);
                index += needle.Length;
            }
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
