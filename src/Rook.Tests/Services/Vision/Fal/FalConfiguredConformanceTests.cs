using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Collections.Generic;
using System.Threading;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Tests.Services.Vision.Video;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.Vision.Qualification;
using Xunit;
namespace Rook.Tests.Services.Vision.Fal
{
    public class FalConfiguredConformanceTests
    {
        internal static string Repo
        {
            get { var d = new DirectoryInfo(AppContext.BaseDirectory); while (d != null && !File.Exists(Path.Combine(d.FullName, "scripts/verify-vision-merge.ps1"))) d = d.Parent; return d!.FullName; }
        }
        [Fact]
        public async Task Legacy_Kling_wire_matches_declarative_reference_and_keeps_its_public_registration()
        {
            JsonObject? wire = null;
            using var http = new HttpClient(new TestHttpMessageHandler { OnSend = message => {
                wire = JsonNode.Parse(message.Content!.ReadAsStringAsync().GetAwaiter().GetResult())!.AsObject();
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"request_id\":\"fixture-job\",\"status\":\"IN_QUEUE\"}") };
            }});
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "start_frame");
            var provider = new FalVideoProvider(() => "fixture-key", new FalApiClient(http), new ReferenceSourceTransport());
            var request = new VideoGenerationRequest(FalVideoCapabilities.KlingV3StandardI2v, VideoMode.I2V, 5, "720p", "16:9", "animate this source", source, null, null, null, new FalVideoOptions(), 1);
            Assert.IsType<QueuedSubmitOutcome>(await provider.SubmitAsync(request, new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None));
            var cases = JsonNode.Parse(File.ReadAllText(Path.Combine(Repo,"src/Rook.Tests/Services/Vision/Fal/Fixtures/configured-cases.json")))!;
            var expected = cases["cases"]!.AsArray().Single(c => c!["id"]!.GetValue<string>() == "legacy-video-wire")!["expected"]!["provider_payload"];
            Assert.True(ConfiguredEndpointQualification.Equal(expected, ConfiguredEndpointQualification.Sanitize(wire)));
            Assert.Single(VisionProviderRegistrations.CreateVideoRegistrations(() => null, () => null), r => r.Models.ContainsKey(FalVideoCapabilities.KlingV3StandardI2v));
        }
        private sealed class ReferenceSourceTransport : IFalSourceFrameTransport
        {
            public Task<(FalSourceFrameUrls? Urls, GenerationError? Error)> ResolveAndUploadAsync(FalSourceFramePolicy policy, VideoGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> media, string apiKey, CancellationToken ct)
                => Task.FromResult<(FalSourceFrameUrls?, GenerationError?)>((new FalSourceFrameUrls("https://v3.fal.media/files/fixture-source.png", null), null));
        }
        [Fact]
        public async Task Reference_wire_contracts_match_without_public_registration_changes()
        {
            var ids = VisionProviderRegistrations.GetLegacyModelIds().OrderBy(x => x).ToArray();
            JsonObject? wire = null;
            var handler = new TestHttpMessageHandler { OnSend = message => {
                wire = JsonNode.Parse(message.Content!.ReadAsStringAsync().GetAwaiter().GetResult())!.AsObject();
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"images\":[{\"url\":\"https://fal.media/result.png\",\"content_type\":\"image/png\"}]}") };
            }};
            using var http = new HttpClient(handler);
            var provider = new FalImageProvider(() => "fixture-key", new FalApiClient(http));
            var result = await provider.SubmitAsync(new ImageGenerationRequest(FalImageCapabilities.FluxSchnell, "sunlit massing study", "1K", "16:9", 1, Array.Empty<MediaRef>(), new FalImageOptions()), new Dictionary<MediaRef, ResolvedMedia>(), CancellationToken.None);
            Assert.IsType<SuccessResultOutcome>(Assert.IsType<SyncSubmitOutcome>(result).Result);
            var fixtures = Path.Combine(Repo, "src/Rook.Tests/Services/Vision/Fal/Fixtures");
            var cases = JsonNode.Parse(File.ReadAllText(Path.Combine(fixtures,"configured-cases.json")))!;
            var reference = cases["cases"]!.AsArray().Single(c => c!["id"]!.GetValue<string>() == "legacy-image-wire")!;
            Assert.True(ConfiguredEndpointQualification.Equal(reference["expected"]!["provider_payload"], wire));
            var catalog = new FalCatalogCompiler().Compile(fixtures, ids).Catalog!;
            var registrations = VisionProviderRegistrations.CreateImageRegistrations(() => null, () => null, () => null, catalog:catalog, configuredExecutor:new FalConfiguredExecutor(new FalApiClient(http), () => null));
            Assert.All(ids.Where(id => id == FalImageCapabilities.FluxSchnell), id => Assert.Single(registrations, r => r.Models.ContainsKey(id)));
            Assert.Equal(ids, VisionProviderRegistrations.GetLegacyModelIds().OrderBy(x => x).ToArray());
        }
        [Fact]
        public async Task Generic_cases_cover_real_surface_values_media_queued_image_and_lifecycle_failures()
        {
            var fixtures = Path.Combine(Repo, "src/Rook.Tests/Services/Vision/Fal/Fixtures");
            var report = Path.Combine(Path.GetTempPath(), "rook-fal-cases-" + Guid.NewGuid().ToString("N") + ".json");
            try
            {
                int exit = await ConfiguredEndpointQualification.VerifyAsync(fixtures, Path.Combine(fixtures, "configured-cases.json"), report);
                var result = JsonNode.Parse(File.ReadAllText(report))!;
                Assert.True(exit == 0, string.Join("; ", result["cases"]!.AsArray().Where(c => c!["passed"]!.GetValue<bool>() == false).Select(c => c!.ToJsonString())));
                Assert.True(result["cases"]!.AsArray().Count >= 30);
                var json = File.ReadAllText(report); Assert.DoesNotContain("offline-fixture-credential", json); Assert.DoesNotContain("data:image", json); Assert.DoesNotContain("https://v3.fal.media/files/fixture-source", json);
            }
            finally { File.Delete(report); }
        }
        [Fact]
        public async Task Arbitrary_new_model_ids_and_provider_fields_work_without_test_code_changes()
        {
            var fixtures = Path.Combine(Repo, "src/Rook.Tests/Services/Vision/Fal/Fixtures");
            var root = Path.Combine(Path.GetTempPath(), "rook-fal-arbitrary-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
            try
            {
                foreach (var file in Directory.GetFiles(fixtures, "*.json")) File.Copy(file, Path.Combine(root, Path.GetFileName(file)));
                var cases = JsonNode.Parse(File.ReadAllText(Path.Combine(root, "configured-cases.json")))!.AsObject();
                var selected = cases["cases"]!.AsArray().First(c => c!["id"]!.GetValue<string>() == "sync-image-managed-controls")!.DeepClone();
                var arbitrary = "synthetic/" + Guid.NewGuid().ToString("N"); selected["request"]!["model"] = arbitrary;
                selected["expected"]!["provider_payload"]!["new_control"] = .123456m; selected["expected"]!["provider_payload"]!.AsObject().Remove("strength");
                cases["cases"] = new JsonArray(selected);
                File.WriteAllText(Path.Combine(root, "configured-cases.json"), cases.ToJsonString());
                var definition = JsonNode.Parse(File.ReadAllText(Path.Combine(root, "configured-sync-image.json")))!; definition["model_id"] = arbitrary;
                foreach (var op in definition["operations"]!.AsArray()) op!["fields"]![4]!["payload"]!["pointer"] = "/new_control";
                File.WriteAllText(Path.Combine(root, "configured-sync-image.json"), definition.ToJsonString());
                var report = Path.Combine(root, "report.json");
                Assert.Equal(0, await ConfiguredEndpointQualification.VerifyAsync(root, Path.Combine(root, "configured-cases.json"), report));
                selected["expected"]!["provider_payload"]!["new_control"] = .5m; cases["cases"] = new JsonArray(selected.DeepClone());
                File.WriteAllText(Path.Combine(root, "configured-cases.json"), cases.ToJsonString());
                Assert.Equal(1, await ConfiguredEndpointQualification.VerifyAsync(root, Path.Combine(root, "configured-cases.json"), report));
            }
            finally { Directory.Delete(root, true); }
        }
    }
}
