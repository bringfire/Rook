using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Artifacts;
using Rook.Services.Vision.Director;
using Xunit;

namespace Rook.Tests.Services.Vision.Director
{
    public sealed class DirectorVideoPublisherTests : IDisposable
    {
        private readonly string _root;
        private readonly string _directorRoot;
        private readonly ArtifactStore _store;

        public DirectorVideoPublisherTests()
        {
            _root = Path.Combine(Path.GetTempPath(), "rook-director-publish-" + Guid.NewGuid().ToString("N"));
            _directorRoot = Path.Combine(_root, "director");
            Directory.CreateDirectory(_directorRoot);
            _store = new ArtifactStore(Path.Combine(_root, "artifacts"));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                try
                {
                    Directory.Delete(_root, recursive: true);
                }
                catch
                {
                }
            }
        }

        [Fact]
        public void Publish_CreatesGeneratedVideoWithOnlyVideoBlob()
        {
            var runRoot = WriteStandardRun();
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(BuildRequest(runRoot));

            Assert.True(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            var artifactId = Guid.Parse(data["artifact_id"]!.GetValue<string>());
            var artifact = _store.Get(artifactId);
            Assert.NotNull(artifact);
            Assert.Equal("generated_video", artifact!.Kind);
            Assert.Single(artifact.Files);
            Assert.Equal("video", artifact.Files[0].Role);
            Assert.Equal("video.mp4", artifact.Files[0].Path);
            Assert.True(File.Exists(_store.GetBlobAbsolutePath(artifactId, "video")));
            Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(artifactId, "poster"));
            Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(artifactId, "start_frame"));
            Assert.Throws<KeyNotFoundException>(() => _store.GetBlobAbsolutePath(artifactId, "end_frame"));
            Assert.Equal("director_publish_standard_v1", artifact.Metadata["director"]!["profile"]!.GetValue<string>());
            Assert.Equal("hd_720", artifact.Metadata["director"]!["preset"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsSourceOutsideDirectorRoot()
        {
            var outside = Path.Combine(_root, "outside", "run-a");
            Directory.CreateDirectory(Path.Combine(outside, "videos"));
            File.WriteAllBytes(Path.Combine(outside, "videos", "preview.mp4"), Encoding.ASCII.GetBytes("fake-mp4"));
            var request = BuildRequest(WriteStandardRun());
            request["source"]!["run_root"] = outside;
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("artifact_boundary_mismatch", data["code"]!.GetValue<string>());
            Assert.Equal("source_path_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsNonPreviewRelativePath()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["source"]!["relative_path"] = "videos/other.mp4";
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("source_path_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsAdvisoryAbsolutePathMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["source"]!["absolute_path"] = Path.Combine(_root, "not-preview.mp4");
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("source_path_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsSourceHashMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["source"]!["sha256"] = new string('0', 64);
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("source_hash_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsSourceSizeMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["source"]!["byte_size"] = 999;
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("source_size_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsVideoManifestHashMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["hashes"]!["video_manifest_sha256"] = new string('0', 64);
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsFrameManifestHashMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["hashes"]!["frame_manifest_sha256"] = new string('0', 64);
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsDirectorMetadataResolutionMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["metadata"]!["director"]!["resolution"]!["width"] = 1920;
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsManifestFactMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["facts"]!["width"] = 1920;
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_RejectsRunIdMismatch()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            request["run_id"] = "other-run";
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("manifest_fact_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_ConfirmsPriorArtifactAndAllowsExtraMetadataFields()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot);
            var requestMetadata = Assert.IsType<JsonObject>(request["metadata"]);
            var sourcePath = Path.Combine(runRoot, "videos", "preview.mp4");
            var priorMetadata = new Dictionary<string, JsonNode?>
            {
                ["director"] = requestMetadata["director"]!.DeepClone(),
                ["extra_future_field"] = JsonValue.Create("allowed"),
            };
            var prior = _store.CreateFromFiles(
                "generated_video",
                new[]
                {
                    new BlobFileInput(
                        "video",
                        sourcePath,
                        "mp4",
                        ExpectedBytes: new FileInfo(sourcePath).Length),
                },
                metadata: priorMetadata);
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(BuildRequest(runRoot, prior.Id));

            Assert.True(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal(prior.Id.ToString("D"), data["artifact_id"]!.GetValue<string>());
            Assert.True(data["confirmed_prior_artifact"]!.GetValue<bool>());
        }

        [Fact]
        public void Publish_MissingPriorArtifactReturnsPublishedArtifactMissing()
        {
            var runRoot = WriteStandardRun();
            var request = BuildRequest(runRoot, Guid.NewGuid());
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("published_artifact_missing", data["code"]!.GetValue<string>());
        }

        [Fact]
        public void Publish_WrongPriorArtifactBlobHashReturnsMismatch()
        {
            var runRoot = WriteStandardRun();
            var wrong = _store.Create(
                "generated_video",
                new[] { new BlobInput("video", Encoding.ASCII.GetBytes("different"), "mp4") });
            var request = BuildRequest(runRoot, wrong.Id);
            var publisher = new DirectorVideoPublisher(_store, _directorRoot);

            var response = publisher.Publish(request);

            Assert.False(response.Success);
            var data = Assert.IsType<JsonObject>(response.Data);
            Assert.Equal("prior_artifact_mismatch", data["managed_subcode"]!.GetValue<string>());
        }

        private string WriteStandardRun(
            string runId = "run-a",
            int width = 1280,
            int height = 720,
            int fps = 24,
            int frameCount = 96,
            byte[]? bytes = null)
        {
            var runRoot = Path.Combine(_directorRoot, runId);
            Directory.CreateDirectory(Path.Combine(runRoot, "videos"));
            File.WriteAllBytes(Path.Combine(runRoot, "videos", "preview.mp4"), bytes ?? Encoding.ASCII.GetBytes("fake-mp4"));
            File.WriteAllText(
                Path.Combine(runRoot, "manifest.json"),
                JsonSerializer.Serialize(new
                {
                    schema_version = 1,
                    director_version = "slice1",
                    run_id = runId,
                    frame_count = frameCount,
                    resolution = new { width, height },
                    timeline = new { fps, duration_seconds = (double)frameCount / fps, frame_count = frameCount },
                }));
            File.WriteAllText(
                Path.Combine(runRoot, "video_manifest.json"),
                JsonSerializer.Serialize(new
                {
                    schema_version = 1,
                    state = "complete",
                    run_id = runId,
                    format = "mp4",
                    container = "mp4",
                    codec = "h264",
                    fps,
                    frame_count = frameCount,
                    width,
                    height,
                    output_path = "videos/preview.mp4",
                    output_current = true,
                }));
            return runRoot;
        }

        private static string Sha256(string path)
        {
            using var stream = File.OpenRead(path);
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        private JsonObject BuildRequest(string runRoot, Guid? priorArtifactId = null)
        {
            var sourcePath = Path.Combine(runRoot, "videos", "preview.mp4");
            var videoManifestPath = Path.Combine(runRoot, "video_manifest.json");
            var frameManifestPath = Path.Combine(runRoot, "manifest.json");
            var request = new JsonObject
            {
                ["run_id"] = Path.GetFileName(runRoot),
                ["profile"] = "director_publish_standard_v1",
                ["preset"] = "hd_720",
                ["source"] = new JsonObject
                {
                    ["run_root"] = runRoot,
                    ["relative_path"] = "videos/preview.mp4",
                    ["absolute_path"] = sourcePath,
                    ["byte_size"] = new FileInfo(sourcePath).Length,
                    ["sha256"] = Sha256(sourcePath),
                },
                ["facts"] = new JsonObject
                {
                    ["container"] = "mp4",
                    ["format"] = "mp4",
                    ["codec"] = "h264",
                    ["width"] = 1280,
                    ["height"] = 720,
                    ["fps"] = 24,
                    ["frame_count"] = 96,
                },
                ["hashes"] = new JsonObject
                {
                    ["video_manifest_sha256"] = Sha256(videoManifestPath),
                    ["frame_manifest_sha256"] = Sha256(frameManifestPath),
                },
                ["metadata"] = new JsonObject
                {
                    ["director"] = new JsonObject
                    {
                        ["schema_version"] = 1,
                        ["run_id"] = Path.GetFileName(runRoot),
                        ["profile"] = "director_publish_standard_v1",
                        ["preset"] = "hd_720",
                        ["source_video"] = "videos/preview.mp4",
                        ["video_manifest_hash"] = Sha256(videoManifestPath),
                        ["frame_manifest_hash"] = Sha256(frameManifestPath),
                        ["camera_strategy"] = "curve_follow_target",
                        ["camera"] = new JsonObject
                        {
                            ["strategy"] = "curve_follow_target",
                            ["curve_id"] = "00000000-0000-0000-0000-000000000001",
                            ["target"] = new JsonArray(0.0, 0.0, 0.0),
                            ["up"] = new JsonArray(0.0, 0.0, 1.0),
                            ["sampling"] = new JsonObject
                            {
                                ["mode"] = "normalized_parameter",
                                ["start"] = 0.0,
                                ["end"] = 1.0,
                            },
                        },
                        ["timeline"] = new JsonObject
                        {
                            ["fps"] = 24,
                            ["duration_seconds"] = 4.0,
                            ["frame_count"] = 96,
                        },
                        ["resolution"] = new JsonObject
                        {
                            ["width"] = 1280,
                            ["height"] = 720,
                        },
                    },
                },
            };
            if (priorArtifactId.HasValue)
                request["prior_artifact_id"] = priorArtifactId.Value.ToString("D");
            return request;
        }
    }
}
