using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoProviderPayloadAuditDocsTests
    {
        [Fact]
        public void AuditProcedure_RequiresExplicitLiveCostApproval()
        {
            var doc = ReadRepoFile("docs", "rook_docs", "video-provider-payload-audit.md");

            Assert.Contains("does not authorize live provider generations", doc);
            Assert.Contains("explicit cost approval", doc);
            Assert.Contains("one Veo job and one fal job", doc);
            Assert.Contains("cost ceiling", doc);
        }

        [Fact]
        public void AuditProcedure_DefinesRedactionRules()
        {
            var doc = ReadRepoFile("docs", "rook_docs", "video-provider-payload-audit.md");

            Assert.Contains("No API keys.", doc);
            Assert.Contains("No signed URLs.", doc);
            Assert.Contains("No provider-private queue/status/result/cancel tokens.", doc);
            Assert.Contains("No local filesystem paths.", doc);
            Assert.Contains("No raw video bytes.", doc);
            Assert.Contains("No raw image bytes.", doc);
            Assert.Contains("No sensitive prompts.", doc);
            Assert.Contains("No account, project, bucket, tenant, or organization identifiers", doc);
        }

        [Fact]
        public void AuditProcedure_PinsUnknownFieldNonInferenceRule()
        {
            var doc = ReadRepoFile("docs", "rook_docs", "video-provider-payload-audit.md");

            Assert.Contains("Unknown provider fields are inert.", doc);
            Assert.Contains("posterUrl", doc);
            Assert.Contains("firstFrame", doc);
            Assert.Contains("lastFrame", doc);
            Assert.Contains("do not imply `poster`, `start_frame`, or `end_frame` support", doc);
        }

        [Theory]
        [InlineData("veo-completion.sanitized.example.json")]
        [InlineData("fal-result.sanitized.example.json")]
        public void SanitizedExampleFixtures_AreMarkedAsNonEvidenceAndInferNoRoles(string fileName)
        {
            var json = ReadRepoFile(
                "docs",
                "rook_docs",
                "fixtures",
                "video-provider-payload-audit",
                fileName);

            Assert.Contains("\"sanitized\": true", json);
            Assert.Contains("Not live provider evidence.", json);
            Assert.Contains("\"unknown_fields_are_inert\": true", json);
            Assert.Contains("\"inferred_roles\": []", json);
            Assert.DoesNotContain("AIza", json);
            Assert.DoesNotContain("queue.fal.run", json);
            Assert.DoesNotContain("v3b.fal.media", json);
            Assert.DoesNotContain("C:\\\\", json);
        }

        private static string ReadRepoFile(params string[] pathParts)
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
                "Could not locate repo file " + string.Join("/", pathParts));
        }
    }
}
