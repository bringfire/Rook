using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;

namespace Rook.Services.Vision.Video
{
    internal sealed record VideoSidecarBackfillOptions(
        int MaxArtifacts,
        TimeSpan MaxElapsed)
    {
        public static VideoSidecarBackfillOptions StartupDefault { get; } =
            new VideoSidecarBackfillOptions(10, TimeSpan.FromSeconds(10));
    }

    internal enum VideoSidecarBackfillArtifactResultCode
    {
        Attempted,
        SkippedNotGeneratedVideo,
        SkippedNoVideoRole,
        SkippedVideoBlobUnavailable,
        SkippedNoMissingRoles,
        SkippedCreatedAfterSweepStart,
        StoppedByBudget,
    }

    internal enum VideoSidecarBackfillRoleResultCode
    {
        Published,
        SkippedAlreadyExists,
        Failed,
        NotStartedBudgetExhausted,
    }

    internal sealed record VideoSidecarBackfillRoleResult(
        string Role,
        VideoSidecarBackfillRoleResultCode Code,
        string? Message = null,
        string? Diagnostic = null);

    internal sealed record VideoSidecarBackfillArtifactResult(
        Guid ArtifactId,
        VideoSidecarBackfillArtifactResultCode Code,
        IReadOnlyList<string> MissingRoles,
        IReadOnlyList<VideoSidecarBackfillRoleResult> RoleResults,
        string? Message = null);

    internal sealed record VideoSidecarBackfillResult(
        int ScannedArtifacts,
        int EligibleArtifacts,
        int ArtifactsSkipped,
        int ArtifactsAttempted,
        int RoleAttempts,
        int RolesPublished,
        int RolesSkippedAlreadyPresent,
        int RoleFailures,
        bool StoppedByCap,
        bool BudgetExhausted,
        IReadOnlyList<VideoSidecarBackfillArtifactResult> Artifacts)
    {
        public string ToTraceSummary()
            => $"scanned={ScannedArtifacts} eligible={EligibleArtifacts} "
               + $"attempted={ArtifactsAttempted} roles={RoleAttempts} "
               + $"published={RolesPublished} failed={RoleFailures} "
               + $"cap={StoppedByCap} budget={BudgetExhausted}";
    }

    internal interface IVideoSidecarBackfillClock
    {
        DateTimeOffset UtcNow { get; }
    }

    internal sealed class SystemVideoSidecarBackfillClock : IVideoSidecarBackfillClock
    {
        public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
    }

    internal interface IVideoSidecarBackfillService
    {
        Task<VideoSidecarBackfillResult> BackfillMissingSidecarsAsync(
            VideoSidecarBackfillOptions options,
            CancellationToken cancellationToken);
    }

    internal sealed class VideoSidecarBackfillService : IVideoSidecarBackfillService
    {
        private const string GeneratedVideoKind = "generated_video";
        private const int MaxDiagnosticLength = 2048;

        private readonly ArtifactStore _store;
        private readonly IVideoPosterSidecarProducer _posterProducer;
        private readonly IVideoFrameSidecarProducer _frameProducer;
        private readonly IVideoSidecarBackfillClock _clock;

        public VideoSidecarBackfillService(
            ArtifactStore store,
            IVideoPosterSidecarProducer posterProducer,
            IVideoFrameSidecarProducer frameProducer,
            IVideoSidecarBackfillClock? clock = null)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _posterProducer = posterProducer ?? throw new ArgumentNullException(nameof(posterProducer));
            _frameProducer = frameProducer ?? throw new ArgumentNullException(nameof(frameProducer));
            _clock = clock ?? new SystemVideoSidecarBackfillClock();
        }

        public async Task<VideoSidecarBackfillResult> BackfillMissingSidecarsAsync(
            VideoSidecarBackfillOptions options,
            CancellationToken cancellationToken)
        {
            if (options.MaxArtifacts <= 0)
                return EmptyResult();

            var startedAt = _clock.UtcNow;
            var artifactResults = new List<VideoSidecarBackfillArtifactResult>();
            var scanned = 0;
            var eligible = 0;
            var consideredForBackfill = 0;
            var attempted = 0;
            var stoppedByCap = false;
            var budgetExhausted = false;

            foreach (var artifact in _store.Enumerate())
            {
                scanned++;
                if (!string.Equals(artifact.Kind, GeneratedVideoKind, StringComparison.Ordinal))
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedNotGeneratedVideo,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    continue;
                }

                if (artifact.CreatedAt > startedAt)
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedCreatedAfterSweepStart,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>(),
                        "Artifact was created after this backfill sweep started."));
                    continue;
                }

                if (!artifact.Files.Any(f => f.Role == VideoMediaRoles.Video))
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedNoVideoRole,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    continue;
                }

                try
                {
                    _ = _store.GetBlobAbsolutePath(artifact.Id, VideoMediaRoles.Video);
                }
                catch (Exception ex)
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedVideoBlobUnavailable,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>(),
                        Truncate(ex.Message)));
                    continue;
                }

                eligible++;
                if (IsBudgetExhausted(startedAt, options))
                {
                    budgetExhausted = true;
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.StoppedByBudget,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    break;
                }

                var missingRoles = MissingRoles(artifact);
                if (missingRoles.Count == 0)
                {
                    artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                        artifact.Id,
                        VideoSidecarBackfillArtifactResultCode.SkippedNoMissingRoles,
                        Array.Empty<string>(),
                        Array.Empty<VideoSidecarBackfillRoleResult>()));
                    continue;
                }

                if (consideredForBackfill >= options.MaxArtifacts)
                {
                    stoppedByCap = true;
                    break;
                }

                consideredForBackfill++;
                attempted++;
                var roleResults = new List<VideoSidecarBackfillRoleResult>();
                for (var i = 0; i < missingRoles.Count; i++)
                {
                    var role = missingRoles[i];
                    if (IsBudgetExhausted(startedAt, options))
                    {
                        budgetExhausted = true;
                        roleResults.AddRange(
                            missingRoles
                                .Skip(i)
                                .Select(NotStartedBudgetExhausted));
                        break;
                    }

                    roleResults.Add(await TryBackfillRoleAsync(
                            artifact.Id,
                            role,
                            cancellationToken)
                        .ConfigureAwait(false));
                }

                artifactResults.Add(new VideoSidecarBackfillArtifactResult(
                    artifact.Id,
                    VideoSidecarBackfillArtifactResultCode.Attempted,
                    missingRoles,
                    roleResults));

                if (budgetExhausted)
                    break;
            }

            return BuildResult(
                scanned,
                eligible,
                attempted,
                stoppedByCap,
                budgetExhausted,
                artifactResults);
        }

        private async Task<VideoSidecarBackfillRoleResult> TryBackfillRoleAsync(
            Guid artifactId,
            string role,
            CancellationToken cancellationToken)
        {
            try
            {
                if (role == VideoMediaRoles.Poster)
                {
                    var result = await _posterProducer.TryPublishPosterAsync(
                            artifactId,
                            cancellationToken)
                        .ConfigureAwait(false);
                    return FromPoster(result);
                }

                var frameResult = await _frameProducer.TryPublishFrameSidecarsAsync(
                        artifactId,
                        new[] { role },
                        cancellationToken)
                    .ConfigureAwait(false);
                var roleResult = frameResult.RoleResults.FirstOrDefault();
                return roleResult is null
                    ? Failed(role, "Frame sidecar producer returned no role result.", null)
                    : FromFrame(roleResult);
            }
            catch (Exception ex)
            {
                return Failed(role, ex.Message, ex.ToString());
            }
        }

        private static List<string> MissingRoles(Artifact artifact)
        {
            var existing = new HashSet<string>(
                artifact.Files.Select(f => f.Role),
                StringComparer.Ordinal);
            var missing = new List<string>(3);
            if (!existing.Contains(VideoMediaRoles.Poster))
                missing.Add(VideoMediaRoles.Poster);
            if (!existing.Contains(VideoMediaRoles.StartFrame))
                missing.Add(VideoMediaRoles.StartFrame);
            if (!existing.Contains(VideoMediaRoles.EndFrame))
                missing.Add(VideoMediaRoles.EndFrame);
            return missing;
        }

        private bool IsBudgetExhausted(
            DateTimeOffset startedAt,
            VideoSidecarBackfillOptions options)
            => options.MaxElapsed > TimeSpan.Zero
               && _clock.UtcNow - startedAt >= options.MaxElapsed;

        private static VideoSidecarBackfillRoleResult FromPoster(
            VideoPosterSidecarResult result)
            => result.Code switch
            {
                VideoPosterSidecarResultCode.Published =>
                    new VideoSidecarBackfillRoleResult(
                        VideoMediaRoles.Poster,
                        VideoSidecarBackfillRoleResultCode.Published,
                        result.Message),
                VideoPosterSidecarResultCode.SkippedAlreadyExists =>
                    new VideoSidecarBackfillRoleResult(
                        VideoMediaRoles.Poster,
                        VideoSidecarBackfillRoleResultCode.SkippedAlreadyExists,
                        result.Message),
                _ => Failed(VideoMediaRoles.Poster, result.Message, result.Diagnostic),
            };

        private static VideoSidecarBackfillRoleResult FromFrame(
            VideoFrameSidecarRoleResult result)
            => result.Code switch
            {
                VideoFrameSidecarRoleResultCode.Published =>
                    new VideoSidecarBackfillRoleResult(
                        result.Role,
                        VideoSidecarBackfillRoleResultCode.Published,
                        result.Message),
                VideoFrameSidecarRoleResultCode.SkippedAlreadyExists =>
                    new VideoSidecarBackfillRoleResult(
                        result.Role,
                        VideoSidecarBackfillRoleResultCode.SkippedAlreadyExists,
                        result.Message),
                _ => Failed(result.Role, result.Message, result.Diagnostic),
            };

        private static VideoSidecarBackfillRoleResult Failed(
            string role,
            string? message,
            string? diagnostic)
            => new VideoSidecarBackfillRoleResult(
                role,
                VideoSidecarBackfillRoleResultCode.Failed,
                Truncate(message),
                Truncate(diagnostic));

        private static string? Truncate(string? value)
            => value is null || value.Length <= MaxDiagnosticLength
                ? value
                : value.Substring(0, MaxDiagnosticLength);

        private static VideoSidecarBackfillResult EmptyResult()
            => new VideoSidecarBackfillResult(
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                StoppedByCap: true,
                BudgetExhausted: false,
                Artifacts: Array.Empty<VideoSidecarBackfillArtifactResult>());

        private static VideoSidecarBackfillResult BuildResult(
            int scanned,
            int eligible,
            int attempted,
            bool stoppedByCap,
            bool budgetExhausted,
            IReadOnlyList<VideoSidecarBackfillArtifactResult> artifacts)
        {
            var roleResults = artifacts.SelectMany(a => a.RoleResults).ToList();
            return new VideoSidecarBackfillResult(
                scanned,
                eligible,
                artifacts.Count(a => a.Code != VideoSidecarBackfillArtifactResultCode.Attempted),
                attempted,
                roleResults.Count(r =>
                    r.Code != VideoSidecarBackfillRoleResultCode.NotStartedBudgetExhausted),
                roleResults.Count(r => r.Code == VideoSidecarBackfillRoleResultCode.Published),
                roleResults.Count(r => r.Code == VideoSidecarBackfillRoleResultCode.SkippedAlreadyExists),
                roleResults.Count(r => r.Code == VideoSidecarBackfillRoleResultCode.Failed),
                stoppedByCap,
                budgetExhausted,
                artifacts);
        }

        private static VideoSidecarBackfillRoleResult NotStartedBudgetExhausted(
            string role)
            => new VideoSidecarBackfillRoleResult(
                role,
                VideoSidecarBackfillRoleResultCode.NotStartedBudgetExhausted,
                "Backfill budget was exhausted before this role started.");
    }
}
