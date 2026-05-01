using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobFetchResult
    {
        public ImageJobState State { get; }
        public Guid? ResultArtifactId { get; }
        public IReadOnlyList<ImageJobResultFile>? Files { get; }
        public GenerationError? Error { get; }

        private ImageJobFetchResult(
            ImageJobState state,
            Guid? resultArtifactId,
            IReadOnlyList<ImageJobResultFile>? files,
            GenerationError? error)
        {
            State = state;
            ResultArtifactId = resultArtifactId;
            Files = files;
            Error = error;
        }

        public static ImageJobFetchResult Complete(
            Guid resultArtifactId, IReadOnlyList<ImageJobResultFile> files)
        {
            if (resultArtifactId == Guid.Empty)
                throw new ArgumentException(
                    "ResultArtifactId must be non-empty for Complete.",
                    nameof(resultArtifactId));
            if (files is null)
                throw new ArgumentNullException(nameof(files));
            if (files.Count == 0)
                throw new ArgumentException(
                    "Files must be non-empty for Complete.",
                    nameof(files));

            return new ImageJobFetchResult(
                ImageJobState.Complete,
                resultArtifactId,
                files,
                error: null);
        }

        public static ImageJobFetchResult Failed(
            ImageJobState state, GenerationError error)
        {
            if (state == ImageJobState.Complete)
                throw new ArgumentException(
                    "Failed requires a non-Complete state.",
                    nameof(state));
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new ImageJobFetchResult(
                state,
                resultArtifactId: null,
                files: null,
                error);
        }
    }
}
