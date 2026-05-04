using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed record ImageJobLedgerRecord(
        int SchemaVersion,
        Guid JobId,
        string Provider,
        string Model,
        string? ProviderJobId,
        ImageJobState State,
        Guid? ResultArtifactId,
        GenerationError? Error,
        DateTimeOffset CreatedAt,
        DateTimeOffset UpdatedAt);
}
