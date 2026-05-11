using System;
using Rook.Artifacts;

namespace Rook.Services.Vision.Video
{
    public enum VideoSidecarPublishResultCode
    {
        Succeeded,
        SkippedAlreadyExists,
        RejectedUnsupportedRole,
        RejectedWrongArtifactKind,
        ArtifactNotFound,
        StorageFailed,
    }

    public sealed record VideoSidecarPublishResult(
        VideoSidecarPublishResultCode Code,
        Guid ArtifactId,
        string Role,
        AppendBlobResultCode? StorageCode = null,
        string? Message = null)
    {
        public bool Success =>
            Code == VideoSidecarPublishResultCode.Succeeded
            || Code == VideoSidecarPublishResultCode.SkippedAlreadyExists;
    }

    public sealed class VideoSidecarPublisher
    {
        private const string GeneratedVideoKind = "generated_video";

        private readonly ArtifactStore _store;

        public VideoSidecarPublisher(ArtifactStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        public VideoSidecarPublishResult Publish(
            Guid artifactId,
            string role,
            byte[] content,
            string fileExtension)
        {
            if (!IsSupportedSidecarRole(role))
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.RejectedUnsupportedRole,
                    artifactId,
                    role,
                    Message: $"Role '{role ?? "<null>"}' is not a generated-video sidecar role.");
            }

            Artifact? artifact;
            try
            {
                artifact = _store.Get(artifactId);
            }
            catch (Exception ex)
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.StorageFailed,
                    artifactId,
                    role,
                    Message: ex.Message);
            }

            if (artifact is null)
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.ArtifactNotFound,
                    artifactId,
                    role,
                    Message: $"Artifact '{artifactId:D}' not found.");
            }

            if (!string.Equals(artifact.Kind, GeneratedVideoKind, StringComparison.Ordinal))
            {
                return new VideoSidecarPublishResult(
                    VideoSidecarPublishResultCode.RejectedWrongArtifactKind,
                    artifactId,
                    role,
                    Message: $"Artifact '{artifactId:D}' has kind '{artifact.Kind}', not '{GeneratedVideoKind}'.");
            }

            var storage = _store.AppendBlob(artifactId, role, content, fileExtension);
            return storage.Code switch
            {
                AppendBlobResultCode.Succeeded =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.Succeeded,
                        artifactId,
                        role,
                        StorageCode: storage.Code),

                AppendBlobResultCode.DuplicateRole =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.SkippedAlreadyExists,
                        artifactId,
                        role,
                        StorageCode: storage.Code,
                        Message: storage.Message),

                AppendBlobResultCode.ArtifactNotFound =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.ArtifactNotFound,
                        artifactId,
                        role,
                        StorageCode: storage.Code,
                        Message: storage.Message),

                _ =>
                    new VideoSidecarPublishResult(
                        VideoSidecarPublishResultCode.StorageFailed,
                        artifactId,
                        role,
                        StorageCode: storage.Code,
                        Message: storage.Message),
            };
        }

        private static bool IsSupportedSidecarRole(string role) =>
            string.Equals(role, VideoMediaRoles.Poster, StringComparison.Ordinal)
            || string.Equals(role, VideoMediaRoles.StartFrame, StringComparison.Ordinal)
            || string.Equals(role, VideoMediaRoles.EndFrame, StringComparison.Ordinal);
    }
}
