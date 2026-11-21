using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Image.Fal
{
    public sealed class ConfiguredFalImageProvider : IImageProvider, IConfiguredGenerationProvider
    {
        private readonly ConfiguredGenerationBinding _binding;
        private readonly FalConfiguredExecutor _executor;
        public ConfiguredFalImageProvider(FalModelDefinition model, FalConfiguredExecutor executor, FalAdapterRegistry adapters)
        { _binding = new(model, adapters, "image"); _executor = executor ?? throw new ArgumentNullException(nameof(executor)); }
        public string ProviderName => "fal";
        public bool RequiresConfirmedSubmission => true;
        public FalOperationBinding GetBinding(string operationId) => _binding.GetBinding(operationId);
        public Task<ProviderSubmitOutcome> SubmitConfiguredAsync(FalNormalizedRequest request, FalMediaSnapshot media, IFalExecutionObserver observer, CancellationToken ct) =>
            _binding.ValidateBinding(request?.Binding!) is GenerationError error ? Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(error)) : _executor.SubmitAsync(request!, media, observer, ct);
        public Task<ProviderStatusOutcome> GetStatusConfiguredAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct) =>
            _binding.ValidateBinding(binding) is GenerationError error ? Task.FromResult<ProviderStatusOutcome>(new FailedStatusOutcome(error)) : _executor.GetStatusAsync(binding, handle, ct);
        public Task<ProviderCancelOutcome> CancelConfiguredAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct) =>
            _binding.ValidateBinding(binding) is GenerationError error ? Task.FromResult<ProviderCancelOutcome>(new FailedCancelOutcome(error)) : _executor.CancelAsync(binding, handle, ct);
        public Task<ProviderResultOutcome> FetchResultConfiguredAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct) =>
            _binding.ValidateBinding(binding) is GenerationError error ? Task.FromResult<ProviderResultOutcome>(new FailedResultOutcome(error)) : _executor.FetchResultAsync(binding, handle, ct);
        public Task<ProviderSubmitOutcome> SubmitAsync(ImageGenerationRequest request, IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia, CancellationToken ct) =>
            Task.FromResult<ProviderSubmitOutcome>(new FailedSubmitOutcome(ConfiguredGenerationBinding.ConfirmationRequired()));
        public Task<ProviderStatusOutcome> GetStatusAsync(ProviderJobHandle handle, CancellationToken ct) =>
            Task.FromResult<ProviderStatusOutcome>(new FailedStatusOutcome(ConfiguredGenerationBinding.BindingRequired()));
        public Task<ProviderCancelOutcome> CancelAsync(ProviderJobHandle handle, CancellationToken ct) =>
            Task.FromResult<ProviderCancelOutcome>(new FailedCancelOutcome(ConfiguredGenerationBinding.BindingRequired()));
        public Task<ProviderResultOutcome> FetchResultAsync(ProviderJobHandle handle, CancellationToken ct) =>
            Task.FromResult<ProviderResultOutcome>(new FailedResultOutcome(ConfiguredGenerationBinding.BindingRequired()));
    }
}
