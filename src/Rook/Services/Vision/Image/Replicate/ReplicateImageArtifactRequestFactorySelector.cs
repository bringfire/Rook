using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Rook.Services.Vision.Replicate;

namespace Rook.Services.Vision.Image.Replicate
{
    internal sealed class ReplicateImageArtifactRequestFactorySelector
    {
        private readonly Func<string?> _apiTokenProvider;

        public ReplicateImageArtifactRequestFactorySelector(
            Func<string?> apiTokenProvider)
        {
            _apiTokenProvider = apiTokenProvider
                ?? throw new ArgumentNullException(nameof(apiTokenProvider));
        }

        public ImageArtifactRequestFactory? Select(
            ResolvedImageModel model,
            ResultArtifact artifact)
        {
            if (model is null)
                return null;
            if (!string.Equals(
                    model.ProviderName,
                    ReplicateImageCapabilities.ProviderName,
                    StringComparison.Ordinal))
            {
                return null;
            }

            return _ =>
            {
                if (artifact.Body is not RemoteArtifactBody remote)
                {
                    return ImageArtifactFetchRequest.Failed(new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        "Replicate image artifact required authenticated fetch but was not remote.",
                        Retryable: false));
                }

                var apiToken = _apiTokenProvider();
                if (string.IsNullOrWhiteSpace(apiToken))
                    return ImageArtifactFetchRequest.Failed(
                        ReplicateErrorMapper.MissingToken());

                try
                {
                    return ImageArtifactFetchRequest.Created(
                        ReplicateApiClient.BuildAuthenticatedOutputRequest(
                            apiToken!,
                            remote.Url));
                }
                catch (ArgumentException ex)
                {
                    return ImageArtifactFetchRequest.Failed(new GenerationError(
                        GenerationErrorCode.ExecutionFailed,
                        ex.Message,
                        Retryable: false));
                }
            };
        }
    }
}
