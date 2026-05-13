using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.MediaImport
{
    public enum MediaImportFailureCode
    {
        UnsupportedMediaType,
        FileNotFound,
        NotRegularFile,
        FileInaccessible,
        FileTooLarge,
        DecodeFailed,
        VideoProbeFailed,
        SidecarExtractionFailed,
        CopyFailed,
        PublishFailed,
    }

    public enum MediaImportStartFailureCode
    {
        EmptySelection,
        TooManyFiles,
    }

    public enum MediaImportItemState
    {
        Queued,
        Copying,
        Probing,
        ExtractingSidecars,
        Publishing,
        Imported,
        Failed,
    }

    public enum MediaImportJobState
    {
        Queued,
        Running,
        Complete,
    }

    public sealed record MediaImportItemSnapshot(
        Guid ImportItemId,
        string Basename,
        MediaImportItemState State,
        Guid? ArtifactId,
        string? ArtifactKind,
        MediaImportFailureCode? FailureCode,
        string? Message);

    public sealed record MediaImportJobSnapshot(
        Guid JobId,
        MediaImportJobState State,
        DateTimeOffset CreatedAt,
        DateTimeOffset UpdatedAt,
        IReadOnlyList<MediaImportItemSnapshot> Items);

    public sealed record MediaImportStartResult(
        bool Created,
        MediaImportJobSnapshot? Job,
        MediaImportStartFailureCode? FailureCode,
        string? Message);

    public sealed record MediaImportJobListResult(IReadOnlyList<MediaImportJobSnapshot> Jobs);

    public sealed record MediaImportProcessResult(
        bool IsSuccess,
        Guid? ArtifactId,
        string? ArtifactKind,
        MediaImportFailureCode? FailureCode,
        string? Message)
    {
        public static MediaImportProcessResult Success(Guid artifactId, string artifactKind) =>
            new(true, artifactId, artifactKind, null, null);

        public static MediaImportProcessResult Failed(MediaImportFailureCode code, string message) =>
            new(false, null, null, code, message);
    }
}
