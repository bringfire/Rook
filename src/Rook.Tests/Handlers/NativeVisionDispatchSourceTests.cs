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
