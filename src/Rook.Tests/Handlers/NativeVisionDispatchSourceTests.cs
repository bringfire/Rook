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

            Assert.Contains("const char* route", helper);
            Assert.Contains("const char* op", helper);
            Assert.Contains("const char* path_id_field", helper);
            Assert.Contains("body[path_id_field] = req.matches[1].str();", helper);
            Assert.DoesNotContain("body[\"artifact_id\"] =", helper);
            Assert.DoesNotContain("body[\"job_id\"] =", helper);
        }

        [Theory]
        [InlineData("HandleVisionGenerate", "\"POST /vision/generate\"", "\"generate\"")]
        [InlineData("HandleVisionEnhancePrompt", "\"POST /vision/enhance-prompt\"", "\"enhance_prompt\"")]
        [InlineData("HandleVisionCaptureDepth", "\"POST /vision/capture-depth\"", "\"capture_depth\"")]
        [InlineData("HandleVisionDirectorPublishVideo", "\"POST /vision/director/publish-video\"", "\"publish_director_video\"")]
        [InlineData("HandleVisionConsumeApproved", "\"POST /vision/artifacts/consume-approved\"", "\"consume_approved\"")]
        [InlineData("HandleVisionApproveArtifact", "\"POST /vision/artifacts/{artifact_id}/approve\"", "\"approve_artifact\"")]
        [InlineData("HandleVisionListArtifacts", "\"GET /vision/artifacts\"", "\"list_artifacts\"")]
        [InlineData("HandleVisionGetArtifact", "\"GET /vision/artifacts/{artifact_id}\"", "\"get_artifact\"")]
        [InlineData("HandleVisionDeleteArtifact", "\"DELETE /vision/artifacts/{artifact_id}\"", "\"delete_artifact\"")]
        [InlineData("HandleVisionVideoSubmit", "\"POST /vision/video/jobs\"", "\"submit_video_job\"")]
        [InlineData("HandleVisionVideoJobsList", "\"GET /vision/video/jobs\"", "\"list_video_jobs\"")]
        [InlineData("HandleVisionVideoModelsList", "\"GET /vision/video/models\"", "\"list_video_models\"")]
        [InlineData("HandleVisionVideoEstimate", "\"POST /vision/video/estimate\"", "\"estimate_video_job\"")]
        [InlineData("HandleVisionVideoCancel", "\"POST /vision/video/jobs/{job_id}/cancel\"", "\"cancel_video_job\"")]
        [InlineData("HandleVisionVideoResult", "\"GET /vision/video/jobs/{job_id}/result\"", "\"get_video_job_result\"")]
        [InlineData("HandleVisionVideoStatus", "\"GET /vision/video/jobs/{job_id}\"", "\"get_video_job\"")]
        public void VisionRoutes_ProvideDiagnosticRouteAndOperationContext(string handlerName, string route, string operation)
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(source, handlerName);

            Assert.Contains(route, handler);
            Assert.Contains(operation, handler);
        }

        [Theory]
        [InlineData("HandleVisionGetArtifact", "GET /vision/artifacts/{artifact_id}", "get_artifact", "artifact_id")]
        [InlineData("HandleVisionApproveArtifact", "POST /vision/artifacts/{artifact_id}/approve", "approve_artifact", "artifact_id")]
        [InlineData("HandleVisionDeleteArtifact", "DELETE /vision/artifacts/{artifact_id}", "delete_artifact", "artifact_id")]
        public void ArtifactPathRoutes_InjectArtifactId(
            string handlerName,
            string routeTemplate,
            string op,
            string fieldName)
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(source, handlerName);

            Assert.Contains(
                $"DispatchVisionOpWithPathId(req, res, \"{routeTemplate}\", \"{op}\", \"{fieldName}\");",
                handler);
        }

        [Theory]
        [InlineData("HandleVisionVideoStatus", "GET /vision/video/jobs/{job_id}", "get_video_job", "job_id")]
        [InlineData("HandleVisionVideoCancel", "POST /vision/video/jobs/{job_id}/cancel", "cancel_video_job", "job_id")]
        [InlineData("HandleVisionVideoResult", "GET /vision/video/jobs/{job_id}/result", "get_video_job_result", "job_id")]
        public void VideoPathRoutes_InjectJobId(
            string handlerName,
            string routeTemplate,
            string op,
            string fieldName)
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(source, handlerName);

            Assert.Contains(
                $"DispatchVisionOpWithPathId(req, res, \"{routeTemplate}\", \"{op}\", \"{fieldName}\");",
                handler);
            Assert.DoesNotContain(
                $"DispatchVisionOpWithPathId(req, res, \"{routeTemplate}\", \"{op}\", \"artifact_id\");",
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
        public void VisionDispatchDiagnostics_RemainUnavailableOnly()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var forward = ExtractFunction(source, "ForwardVisionDispatch");
            var parse = ExtractFunction(source, "ParseBodyAsObject");

            Assert.Contains("BuildVisionDispatchCallbackUnavailable", source);
            Assert.Contains("ManagedCreateInvokeResult::Unavailable", forward);
            Assert.Contains("SendErrorWithDiagnostic", forward);
            Assert.DoesNotContain("SendErrorWithDiagnostic", parse);
        }

        [Fact]
        public void VisionDispatchDiagnostic_PreservesUnavailableTransportContract()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var helper = ExtractFunction(source, "ForwardVisionDispatch");
            var unavailableStart = helper.IndexOf("case ManagedCreateInvokeResult::Unavailable:", StringComparison.Ordinal);
            var failedStart = helper.IndexOf("case ManagedCreateInvokeResult::Failed:", unavailableStart, StringComparison.Ordinal);
            var unavailableCase = helper.Substring(unavailableStart, failedStart - unavailableStart);

            Assert.Contains("CRookServer::SendErrorWithDiagnostic", unavailableCase);
            Assert.Contains("res.status = 503;", unavailableCase);
            Assert.Contains("res.set_header(\"X-Rook-Vision-Op\", op);", unavailableCase);

            var diagnosticIndex = unavailableCase.IndexOf("CRookServer::SendErrorWithDiagnostic", StringComparison.Ordinal);
            var statusIndex = unavailableCase.IndexOf("res.status = 503;", StringComparison.Ordinal);
            var headerIndex = unavailableCase.IndexOf("res.set_header(\"X-Rook-Vision-Op\", op);", StringComparison.Ordinal);

            Assert.True(diagnosticIndex >= 0, "Diagnostic response helper was not found.");
            Assert.True(statusIndex > diagnosticIndex, "Unavailable status must be restored after the diagnostic helper call.");
            Assert.True(headerIndex > statusIndex, "Vision operation header must be preserved after restoring 503 status.");
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

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
