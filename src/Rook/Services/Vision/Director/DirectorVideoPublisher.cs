using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook;
using Rook.Artifacts;

namespace Rook.Services.Vision.Director
{
    internal sealed class DirectorVideoPublisher
    {
        private const string ProfileName = "director_publish_standard_v1";
        private const string SourceRelativePath = "videos/preview.mp4";
        private static readonly IReadOnlyDictionary<string, (int Width, int Height)> PresetDimensions =
            new Dictionary<string, (int Width, int Height)>(StringComparer.Ordinal)
            {
                ["hd_720"] = (1280, 720),
                ["full_hd_1080"] = (1920, 1080),
                ["uhd_4k"] = (3840, 2160),
                ["uhd_8k"] = (7680, 4320),
            };
        private static readonly ISet<int> AllowedFps = new HashSet<int> { 24, 30 };

        private readonly ArtifactStore _artifactStore;
        private readonly string _directorRoot;
        private readonly Action<string>? _beforeCreateFromFilesForTests;

        public DirectorVideoPublisher(
            ArtifactStore artifactStore,
            string? directorRoot = null,
            Action<string>? beforeCreateFromFilesForTests = null)
        {
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));
            _directorRoot = Canonicalize(directorRoot ?? ResolveDirectorOutputRoot());
            _beforeCreateFromFilesForTests = beforeCreateFromFilesForTests;
        }

        public ApiResponse Publish(JsonObject request)
        {
            try
            {
                return PublishCore(request);
            }
            catch (ArgumentException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", ex.Message);
            }
            catch (InvalidDataException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", ex.Message);
            }
            catch (JsonException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", ex.Message);
            }
            catch (InvalidOperationException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", ex.Message);
            }
            catch (FormatException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", ex.Message);
            }
            catch (IOException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", ex.Message);
            }
        }

        private ApiResponse PublishCore(JsonObject request)
        {
            var runId = RequireString(request, "run_id");
            var profile = RequireString(request, "profile");
            if (!string.Equals(profile, ProfileName, StringComparison.Ordinal))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "profile mismatch.");

            var source = RequireObject(request, "source");
            var runRoot = Canonicalize(RequireString(source, "run_root"));
            var relativePath = RequireString(source, "relative_path");
            if (!string.Equals(relativePath, SourceRelativePath, StringComparison.Ordinal))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "source relative_path must be videos/preview.mp4.");
            if (!IsRelativeToOrSame(runRoot, _directorRoot))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "run_root must resolve under the configured Director output root.");

            var sourcePath = Canonicalize(Path.Combine(runRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
            var expectedSourcePath = Canonicalize(Path.Combine(runRoot, "videos", "preview.mp4"));
            if (!IsRelativeToOrSame(sourcePath, runRoot)
                || !string.Equals(sourcePath, expectedSourcePath, StringComparison.OrdinalIgnoreCase))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "source path must resolve to run_root/videos/preview.mp4.");
            }
            if (HasReparsePointBetween(_directorRoot, runRoot)
                || HasReparsePointBetween(runRoot, sourcePath))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "Director source path must not traverse reparse points.");
            }

            if (source.TryGetPropertyValue("absolute_path", out var advisoryNode) && advisoryNode is not null)
            {
                var advisory = Canonicalize(advisoryNode.GetValue<string>());
                if (!string.Equals(advisory, sourcePath, StringComparison.OrdinalIgnoreCase))
                    return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "advisory absolute_path does not match recomputed source path.");
            }

            if (!File.Exists(sourcePath))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_path_mismatch", "source video is missing.");

            var expectedSize = RequireLong(source, "byte_size");
            var actualSize = new FileInfo(sourcePath).Length;
            if (actualSize != expectedSize)
                return DirectorVideoPublishResponses.BoundaryMismatch("source_size_mismatch", "source video byte size mismatch.");

            var expectedHash = RequireString(source, "sha256");
            var actualHash = Sha256(sourcePath);
            if (!string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_hash_mismatch", "source video hash mismatch.");

            var manifestCheck = ValidateManifests(runRoot, request, runId);
            if (!manifestCheck.Success) return manifestCheck;

            var profileCheck = ValidateProfile(request);
            if (!profileCheck.Success) return profileCheck;

            var requestContractCheck = ValidateRequestHashesAndMetadata(runRoot, request, runId, expectedHash);
            if (!requestContractCheck.Success) return requestContractCheck;

            if (request.TryGetPropertyValue("prior_artifact_id", out var priorNode) && priorNode is not null)
            {
                if (!Guid.TryParse(priorNode.GetValue<string>(), out var priorId))
                    return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior_artifact_id must be a GUID.");
                return ConfirmPriorArtifact(priorId, request, expectedHash, expectedSize);
            }

            var metadata = RequireObject(request, "metadata").DeepClone().AsObject();
            _beforeCreateFromFilesForTests?.Invoke(sourcePath);

            Artifact artifact;
            try
            {
                artifact = _artifactStore.CreateFromFiles(
                    "generated_video",
                    new[] { new BlobFileInput("video", sourcePath, "mp4", ExpectedBytes: expectedSize) },
                    metadata: JsonObjectToDictionary(metadata));
            }
            catch (ArtifactBlobSizeException ex)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("source_size_mismatch", ex.Message);
            }

            var copiedCheck = ValidateCopiedArtifactBlob(artifact.Id, expectedHash, expectedSize);
            if (!copiedCheck.Success)
            {
                _artifactStore.Delete(artifact.Id);
                return copiedCheck;
            }

            return PublishedArtifactResponse(artifact, confirmedPriorArtifact: false);
        }

        private ApiResponse ValidateManifests(string runRoot, JsonObject request, string runId)
        {
            var manifestPath = Path.Combine(runRoot, "manifest.json");
            var videoManifestPath = Path.Combine(runRoot, "video_manifest.json");
            var manifest = ParseJsonObject(manifestPath);
            var videoManifest = ParseJsonObject(videoManifestPath);

            if (!string.Equals(manifest["run_id"]?.GetValue<string>(), runId, StringComparison.Ordinal)
                || !string.Equals(videoManifest["run_id"]?.GetValue<string>(), runId, StringComparison.Ordinal))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "run_id does not match manifests.");
            }

            if (!string.Equals(videoManifest["state"]?.GetValue<string>(), "complete", StringComparison.Ordinal)
                || videoManifest["output_current"]?.GetValue<bool>() != true)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "video_manifest is not current and complete.");
            }
            if (!string.Equals(videoManifest["output_path"]?.GetValue<string>(), SourceRelativePath, StringComparison.Ordinal))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "video_manifest output_path must be videos/preview.mp4.");

            var facts = RequireObject(request, "facts");
            var resolution = RequireObject(manifest, "resolution");
            var timeline = RequireObject(manifest, "timeline");
            if (RequireInt(resolution, "width") != RequireInt(facts, "width")
                || RequireInt(resolution, "height") != RequireInt(facts, "height")
                || RequireInt(timeline, "fps") != RequireInt(facts, "fps")
                || RequireInt(timeline, "frame_count") != RequireInt(facts, "frame_count")
                || RequireInt(manifest, "frame_count") != RequireInt(facts, "frame_count"))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "request facts do not match manifest.json.");
            }

            if (RequireInt(videoManifest, "width") != RequireInt(facts, "width")
                || RequireInt(videoManifest, "height") != RequireInt(facts, "height")
                || RequireInt(videoManifest, "frame_count") != RequireInt(facts, "frame_count")
                || RequireInt(videoManifest, "fps") != RequireInt(facts, "fps")
                || !string.Equals(videoManifest["format"]?.GetValue<string>(), RequireString(facts, "format"), StringComparison.Ordinal)
                || !string.Equals(videoManifest["container"]?.GetValue<string>(), RequireString(facts, "container"), StringComparison.Ordinal)
                || !string.Equals(videoManifest["codec"]?.GetValue<string>(), RequireString(facts, "codec"), StringComparison.Ordinal))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "request facts do not match video_manifest.json.");
            }

            return SuccessResponse();
        }

        private ApiResponse ValidateProfile(JsonObject request)
        {
            var facts = RequireObject(request, "facts");
            if (!string.Equals(RequireString(facts, "format"), "mp4", StringComparison.Ordinal)
                || !string.Equals(RequireString(facts, "container"), "mp4", StringComparison.Ordinal)
                || !string.Equals(RequireString(facts, "codec"), "h264", StringComparison.Ordinal))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "unsupported director_publish_standard_v1 format/container/codec.");
            }

            var width = RequireInt(facts, "width");
            var height = RequireInt(facts, "height");
            var fps = RequireInt(facts, "fps");
            if (!AllowedFps.Contains(fps))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "unsupported director_publish_standard_v1 fps.");

            var preset = RequireString(request, "preset");
            if (!PresetDimensions.TryGetValue(preset, out var dimensions)
                || dimensions.Width != width
                || dimensions.Height != height)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "preset does not match director_publish_standard_v1 dimensions.");
            }

            return SuccessResponse();
        }

        private ApiResponse ValidateRequestHashesAndMetadata(string runRoot, JsonObject request, string runId, string expectedSourceHash)
        {
            var hashes = RequireObject(request, "hashes");
            if (!string.Equals(expectedSourceHash, RequireString(hashes, "source_video_sha256"), StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_hash_mismatch", "source video hash does not match request hashes.");
            var videoManifestHash = Sha256(Path.Combine(runRoot, "video_manifest.json"));
            var frameManifestHash = Sha256(Path.Combine(runRoot, "manifest.json"));
            if (!string.Equals(videoManifestHash, RequireString(hashes, "video_manifest_sha256"), StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "video_manifest hash does not match request.");
            if (!string.Equals(frameManifestHash, RequireString(hashes, "frame_manifest_sha256"), StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "frame manifest hash does not match request.");

            var facts = RequireObject(request, "facts");
            var director = RequireObject(RequireObject(request, "metadata"), "director");
            if (!string.Equals(director["run_id"]?.GetValue<string>(), runId, StringComparison.Ordinal)
                || !string.Equals(director["profile"]?.GetValue<string>(), ProfileName, StringComparison.Ordinal)
                || !string.Equals(director["preset"]?.GetValue<string>(), RequireString(request, "preset"), StringComparison.Ordinal)
                || !string.Equals(director["source_video"]?.GetValue<string>(), SourceRelativePath, StringComparison.Ordinal)
                || !string.Equals(director["video_manifest_hash"]?.GetValue<string>(), videoManifestHash, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(director["frame_manifest_hash"]?.GetValue<string>(), frameManifestHash, StringComparison.OrdinalIgnoreCase))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "metadata.director identity fields do not match request facts.");
            }

            var resolution = RequireObject(director, "resolution");
            if (RequireInt(resolution, "width") != RequireInt(facts, "width")
                || RequireInt(resolution, "height") != RequireInt(facts, "height"))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "metadata.director resolution does not match request facts.");
            }

            var timeline = RequireObject(director, "timeline");
            if (RequireInt(timeline, "fps") != RequireInt(facts, "fps")
                || RequireInt(timeline, "frame_count") != RequireInt(facts, "frame_count"))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("manifest_fact_mismatch", "metadata.director timeline does not match request facts.");
            }

            return SuccessResponse();
        }

        private ApiResponse ConfirmPriorArtifact(Guid artifactId, JsonObject request, string expectedHash, long expectedSize)
        {
            var artifact = _artifactStore.Get(artifactId);
            if (artifact is null)
                return DirectorVideoPublishResponses.PublishedArtifactMissing(artifactId);
            if (!string.Equals(artifact.Kind, "generated_video", StringComparison.Ordinal)
                || artifact.Files.Count != 1
                || !string.Equals(artifact.Files[0].Role, "video", StringComparison.Ordinal))
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact is not generated_video/video.");
            }

            string blobPath;
            try
            {
                blobPath = _artifactStore.GetBlobAbsolutePath(artifactId, "video");
            }
            catch (Exception ex) when (
                ex is IOException ||
                ex is KeyNotFoundException ||
                ex is InvalidDataException)
            {
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", ex.Message);
            }

            if (new FileInfo(blobPath).Length != expectedSize)
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact video size mismatch.");
            if (!string.Equals(Sha256(blobPath), expectedHash, StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact video hash mismatch.");

            var requestDirector = RequireObject(RequireObject(request, "metadata"), "director");
            var artifactDirectorNode = artifact.Metadata.TryGetValue("director", out var node) ? node : null;
            if (artifactDirectorNode is not JsonObject artifactDirector)
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact lacks director metadata.");

            if (!ContainsAllRequestFields(requestDirector, artifactDirector))
                return DirectorVideoPublishResponses.BoundaryMismatch("prior_artifact_mismatch", "prior artifact director metadata mismatch.");

            return PublishedArtifactResponse(artifact, confirmedPriorArtifact: true);
        }

        private ApiResponse ValidateCopiedArtifactBlob(Guid artifactId, string expectedHash, long expectedSize)
        {
            var copiedPath = _artifactStore.GetBlobAbsolutePath(artifactId, "video");
            if (new FileInfo(copiedPath).Length != expectedSize)
                return DirectorVideoPublishResponses.BoundaryMismatch("source_size_mismatch", "copied artifact video byte size mismatch.");
            if (!string.Equals(Sha256(copiedPath), expectedHash, StringComparison.OrdinalIgnoreCase))
                return DirectorVideoPublishResponses.BoundaryMismatch("source_hash_mismatch", "copied artifact video hash mismatch.");

            return SuccessResponse();
        }

        private static ApiResponse PublishedArtifactResponse(Artifact artifact, bool confirmedPriorArtifact)
            => new ApiResponse
            {
                Success = true,
                Data = new JsonObject
                {
                    ["artifact_id"] = artifact.Id.ToString("D"),
                    ["kind"] = artifact.Kind,
                    ["confirmed_prior_artifact"] = confirmedPriorArtifact,
                    ["files"] = new JsonArray(
                        artifact.Files.Select(f => new JsonObject
                        {
                            ["role"] = f.Role,
                            ["path"] = f.Path,
                        }).ToArray<JsonNode?>()),
                },
            };

        private static ApiResponse SuccessResponse()
            => new ApiResponse { Success = true, Data = new JsonObject() };

        private static string ResolveDirectorOutputRoot()
        {
            var configured = Environment.GetEnvironmentVariable("ROOK_DIRECTOR_OUTPUT_ROOT");
            if (!string.IsNullOrWhiteSpace(configured))
                return configured;

            var localAppData = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            if (string.IsNullOrWhiteSpace(localAppData))
                throw new InvalidOperationException("LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set.");

            return Path.Combine(localAppData, "Rook", "rookvision_director");
        }

        private static string Canonicalize(string path)
            => Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        private static bool IsRelativeToOrSame(string path, string root)
        {
            var canonicalPath = Canonicalize(path);
            var canonicalRoot = Canonicalize(root);
            if (string.Equals(canonicalPath, canonicalRoot, StringComparison.OrdinalIgnoreCase))
                return true;

            return canonicalPath.StartsWith(
                canonicalRoot + Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase);
        }

        private static bool HasReparsePointBetween(string root, string path)
        {
            var canonicalRoot = Canonicalize(root);
            var canonicalPath = Canonicalize(path);
            if (!IsRelativeToOrSame(canonicalPath, canonicalRoot))
                return true;

            var current = canonicalRoot;
            if (HasReparsePoint(current))
                return true;

            var relative = canonicalPath.Length == canonicalRoot.Length
                ? string.Empty
                : canonicalPath.Substring(canonicalRoot.Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            foreach (var segment in relative.Split(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar }, StringSplitOptions.RemoveEmptyEntries))
            {
                current = Path.Combine(current, segment);
                if (HasReparsePoint(current))
                    return true;
            }

            return false;
        }

        private static bool HasReparsePoint(string path)
        {
            if (!File.Exists(path) && !Directory.Exists(path))
                return false;

            return (File.GetAttributes(path) & FileAttributes.ReparsePoint) == FileAttributes.ReparsePoint;
        }

        private static JsonObject ParseJsonObject(string path)
        {
            var node = JsonNode.Parse(File.ReadAllText(path));
            if (node is not JsonObject obj)
                throw new InvalidDataException($"{Path.GetFileName(path)} must be a JSON object.");

            return obj;
        }

        private static JsonObject RequireObject(JsonObject obj, string name)
            => obj[name] as JsonObject ?? throw new ArgumentException($"{name} must be an object.");

        private static string RequireString(JsonObject obj, string name)
            => obj[name]?.GetValue<string>() ?? throw new ArgumentException($"{name} must be a string.");

        private static int RequireInt(JsonObject obj, string name)
            => RequireIntegralInt(obj[name], name);

        private static int RequireIntegralInt(JsonNode? node, string name)
        {
            if (node is null)
                throw new ArgumentException($"{name} must be an integer.");

            if (TryGetIntegralInt(node, out var value))
                return value;

            throw new ArgumentException($"{name} must be an integer.");
        }

        private static bool TryGetIntegralInt(JsonNode node, out int value)
        {
            try
            {
                value = node.GetValue<int>();
                return true;
            }
            catch (Exception ex) when (ex is InvalidOperationException || ex is FormatException)
            {
            }

            try
            {
                var longValue = node.GetValue<long>();
                if (longValue >= int.MinValue && longValue <= int.MaxValue)
                {
                    value = (int)longValue;
                    return true;
                }
            }
            catch (Exception ex) when (ex is InvalidOperationException || ex is FormatException)
            {
            }

            try
            {
                var doubleValue = node.GetValue<double>();
                if (!double.IsNaN(doubleValue)
                    && !double.IsInfinity(doubleValue)
                    && doubleValue >= int.MinValue
                    && doubleValue <= int.MaxValue
                    && Math.Truncate(doubleValue) == doubleValue)
                {
                    value = (int)doubleValue;
                    return true;
                }
            }
            catch (Exception ex) when (ex is InvalidOperationException || ex is FormatException)
            {
            }

            value = default;
            return false;
        }

        private static long RequireLong(JsonObject obj, string name)
        {
            var node = obj[name] ?? throw new ArgumentException($"{name} must be an integer.");
            try
            {
                return node.GetValue<long>();
            }
            catch (InvalidOperationException)
            {
                return node.GetValue<int>();
            }
        }

        private static Dictionary<string, JsonNode?> JsonObjectToDictionary(JsonObject obj)
        {
            var result = new Dictionary<string, JsonNode?>(StringComparer.Ordinal);
            foreach (var kvp in obj)
            {
                result[kvp.Key] = kvp.Value?.DeepClone();
            }

            return result;
        }

        private static bool ContainsAllRequestFields(JsonNode? requestNode, JsonNode? artifactNode)
        {
            if (requestNode is JsonObject requestObject)
            {
                if (artifactNode is not JsonObject artifactObject)
                    return false;

                foreach (var kvp in requestObject)
                {
                    if (!artifactObject.TryGetPropertyValue(kvp.Key, out var artifactChild))
                        return false;
                    if (!ContainsAllRequestFields(kvp.Value, artifactChild))
                        return false;
                }

                return true;
            }

            return JsonNode.DeepEquals(requestNode, artifactNode);
        }

        private static string Sha256(string path)
        {
            using var stream = File.OpenRead(path);
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
    }
}
