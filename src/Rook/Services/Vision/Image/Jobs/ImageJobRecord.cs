using System;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobRecord
    {
        public ImageJobRecord(
            Guid jobId,
            ImageJobState state,
            string? model,
            string? provider,
            DateTimeOffset updatedAt,
            ProviderJobHandle? providerHandle,
            Guid? resultArtifactId,
            GenerationError? error)
        {
            if (jobId == Guid.Empty)
                throw new ArgumentException(
                    "JobId must be non-empty.", nameof(jobId));

            JobId = jobId;
            State = state;
            Model = model ?? string.Empty;
            Provider = provider ?? string.Empty;
            UpdatedAt = updatedAt;
            ProviderHandle = providerHandle;
            ResultArtifactId = resultArtifactId;
            Error = error;
        }

        public Guid JobId { get; }
        public ImageJobState State { get; }
        public string Model { get; }
        public string Provider { get; }
        public DateTimeOffset UpdatedAt { get; }
        public ProviderJobHandle? ProviderHandle { get; }
        public Guid? ResultArtifactId { get; }
        public GenerationError? Error { get; }
    }
}
