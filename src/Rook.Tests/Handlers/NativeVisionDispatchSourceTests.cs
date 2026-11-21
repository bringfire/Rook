using System;
using System.IO;
using System.Text.RegularExpressions;
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

        [Theory]
        [InlineData("HandleVisionImageModelsList", "GET /vision/image/models", "list_image_models")]
        [InlineData("HandleVisionImageEstimate", "POST /vision/image/estimate", "image_estimate")]
        [InlineData("HandleVisionImageSubmit", "POST /vision/image/jobs", "image_generate_start")]
        [InlineData("HandleVisionImageStatus", "GET /vision/image/jobs/{job_id}", "image_job_status")]
        [InlineData("HandleVisionImageResult", "GET /vision/image/jobs/{job_id}/result", "image_job_result")]
        [InlineData("HandleVisionImageCancel", "POST /vision/image/jobs/{job_id}/cancel", "image_job_cancel")]
        [InlineData("HandleVisionImageJobsList", "GET /vision/image/jobs", "image_jobs")]
        public void ImageRoutes_ForwardThroughExistingVisionBoundary(string handlerName, string route, string op)
        {
            var native = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(native, handlerName);
            Assert.Contains("\"" + route + "\"", handler);
            Assert.Contains("\"" + op + "\"", handler);
            Assert.DoesNotContain("CMainThreadDispatcher", handler);
            if (route.Contains("{job_id}"))
                Assert.Contains("\"job_id\"", handler);
        }

        [Fact]
        public void ImageBridgeAdmission_MatchesSharedHandlerDispatchAndPreservesResolver()
        {
            var source = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");
            var admissionStart = source.IndexOf("ExpectedVisionOps =", StringComparison.Ordinal);
            var admissionEnd = source.IndexOf("};", admissionStart, StringComparison.Ordinal);
            var admission = source.Substring(admissionStart, admissionEnd - admissionStart);
            Assert.Contains("\"list_image_models\"", admission);
            foreach (var name in new[] { "OpEstimate", "OpStart", "OpStatus", "OpResult", "OpCancel", "OpList" })
            {
                Assert.Contains("ImageJobOpHandler." + name, admission);
                Assert.Contains("case ImageJobOpHandler." + name + ":", source);
            }
            Assert.Contains("new ImageJobOpHandler(RookSubsystemRoot.Instance.ImageJobs.Manager, Vision)", source);
            Assert.Contains("_imageJobOpHandler.Value.DispatchAsync(reqJson, ct)", source);
            Assert.Contains("_imageJobOpHandler.Value.DispatchOffUi(reqJson)", source);
            Assert.Contains("bundle.Framing, bundle.MediaResolver", source);
            Assert.DoesNotContain("\"image_job_wait\"", admission);
        }

        [Theory]
        [InlineData("Get", "/vision/image/models", "HandleVisionImageModelsList")]
        [InlineData("Post", "/vision/image/estimate", "HandleVisionImageEstimate")]
        [InlineData("Post", "/vision/image/jobs", "HandleVisionImageSubmit")]
        [InlineData("Get", "/vision/image/jobs", "HandleVisionImageJobsList")]
        [InlineData("Get", "/vision/image/jobs/([^/]+)", "HandleVisionImageStatus")]
        [InlineData("Get", "/vision/image/jobs/([^/]+)/result", "HandleVisionImageResult")]
        [InlineData("Post", "/vision/image/jobs/([^/]+)/cancel", "HandleVisionImageCancel")]
        public void ImageRouteRegistrations_PreserveHttpMethodAndHandler(string method, string path, string handler)
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var literal = path.Contains("([^/]+)") ? "R\"(" + path + ")\"" : "\"" + path + "\"";
            var registration = Regex.Match(source,
                "m_server->" + method + @"\(" + Regex.Escape(literal) + @",[^}]+\}");
            Assert.True(registration.Success, "Missing route registration: " + method + " " + path);
            Assert.Contains(handler + "(req, res)", registration.Value);
        }

        [Fact]
        public void ImageCapabilities_UseExistingVisionCallbackReadiness()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var start = source.IndexOf("domains.push_back(Domain(\"vision.media\"", StringComparison.Ordinal);
            const string boundary = "CompanionEvidenceFor(companionStatus, \"vision.media\")));";
            var end = source.IndexOf(boundary, start, StringComparison.Ordinal) + boundary.Length;
            var capability = source.Substring(start, end - start);
            Assert.Contains("visionReady", capability);
            Assert.Contains("managed_bridge_callback_not_registered", capability);
            foreach (var route in new[] {
                "GET /vision/image/models", "POST /vision/image/estimate", "POST /vision/image/jobs",
                "GET /vision/image/jobs", "GET /vision/image/jobs/{job_id}",
                "GET /vision/image/jobs/{job_id}/result", "POST /vision/image/jobs/{job_id}/cancel" })
                Assert.Contains("\"" + route + "\"", capability);
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
