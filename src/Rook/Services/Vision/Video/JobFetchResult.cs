using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Outcome of <see cref="IVideoProvider.FetchResultAsync"/>.
    /// Constructed only via <see cref="Complete"/> or <see cref="Failed"/>;
    /// the type system enforces v3.1 D3's invariant:
    /// <c>Error == null</c> ⇔
    /// <c>(State == VideoJobState.Complete &amp;&amp;
    ///    ResultArtifactId.HasValue &amp;&amp; Files != null)</c>.
    ///
    /// Premature fetches and terminal failures both surface here without
    /// fake GUIDs — Codex caught the original positional-record shape
    /// allowing invalid states; private ctor + factories make the
    /// invariant compiler-enforced.
    /// </summary>
    public sealed record JobFetchResult
    {
        public VideoJobState State { get; }
        public Guid? ResultArtifactId { get; }
        public IReadOnlyList<JobResultFile>? Files { get; }
        public VideoJobError? Error { get; }

        private JobFetchResult(
            VideoJobState state,
            Guid? resultArtifactId,
            IReadOnlyList<JobResultFile>? files,
            VideoJobError? error)
        {
            State = state;
            ResultArtifactId = resultArtifactId;
            Files = files;
            Error = error;
        }

        public static JobFetchResult Complete(
            Guid resultArtifactId, IReadOnlyList<JobResultFile> files)
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

            return new JobFetchResult(
                VideoJobState.Complete,
                resultArtifactId,
                files,
                error: null);
        }

        public static JobFetchResult Failed(
            VideoJobState state, VideoJobError error)
        {
            if (state == VideoJobState.Complete)
                throw new ArgumentException(
                    "Failed requires a non-Complete state.",
                    nameof(state));
            if (error is null)
                throw new ArgumentNullException(nameof(error));

            return new JobFetchResult(
                state,
                resultArtifactId: null,
                files: null,
                error);
        }
    }
}
