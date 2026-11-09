using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Fal;
using Rook.Services.Vision.Fal.Models;

namespace Rook.Services.Vision.Generation
{
    public interface IConfiguredGenerationBinding
    {
        FalOperationBinding GetBinding(string operationId);
        bool RequiresConfirmedSubmission { get; }
    }

    /// <summary>Managers supply confirmed controls, owned media and the durable admission observer.
    /// Keep media alive until submit settles; polling uses only the pinned binding and handle.</summary>
    public interface IConfiguredGenerationProvider : IConfiguredGenerationBinding
    {
        Task<ProviderSubmitOutcome> SubmitConfiguredAsync(FalNormalizedRequest request, FalMediaSnapshot media, IFalExecutionObserver observer, CancellationToken ct);
        Task<ProviderStatusOutcome> GetStatusConfiguredAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct);
        Task<ProviderCancelOutcome> CancelConfiguredAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct);
        Task<ProviderResultOutcome> FetchResultConfiguredAsync(FalOperationBinding binding, ProviderJobHandle handle, CancellationToken ct);
    }

    // Shared by the two modality codecs and wrappers. This stores catalog state only, never job state.
    internal sealed class ConfiguredGenerationBinding
    {
        internal FalModelDefinition Model { get; }
        internal ConfiguredGenerationBinding(FalModelDefinition model, FalAdapterRegistry adapters, string modality)
        {
            Model = model ?? throw new ArgumentNullException(nameof(model));
            if (adapters == null) throw new ArgumentNullException(nameof(adapters));
            if (model.Operations.Count == 0 || model.Operations.Any(o => o.Result.MimeFamily != modality))
                throw new ArgumentException("Configured model does not belong to this modality.", nameof(model));
            foreach (var operation in model.Operations) adapters.Resolve(operation.AdapterId, operation.AdapterVersion);
        }
        internal FalOperationBinding GetBinding(string operationId) => Model.Operations.FirstOrDefault(o => o.OperationId == operationId)
            ?? throw new KeyNotFoundException("Unknown configured operation.");
        internal GenerationError? ValidateBinding(FalOperationBinding binding) =>
            binding != null && binding.ModelId == Model.ModelId && binding.DefinitionId == Model.DefinitionId
            && binding.Revision == Model.Revision && binding.DefinitionHash == Model.DefinitionHash
            && Model.Operations.Any(o => o.OperationId == binding.OperationId)
                ? null : Error("configured_binding_mismatch", "The binding does not belong to this configured model revision.", "operation");

        internal FalNormalizationResult Normalize(FalModelInput input, string? selectedOperation = null)
        {
            if (input == null) throw new ArgumentNullException(nameof(input));
            if (selectedOperation != null && input.OperationId != null && selectedOperation != input.OperationId)
                return Invalid("The selected operation conflicts with the supplied operation.");
            string? operation = selectedOperation ?? input.OperationId;
            FalOperationBinding? binding;
            if (operation != null) binding = Model.Operations.FirstOrDefault(o => o.OperationId == operation);
            else if (Model.Operations.Count == 1) binding = Model.Operations[0];
            else
            {
                // Inference uses semantic media only. Controls/defaults never choose a route.
                var candidates = Model.Operations.Where(o => input.Media.All(m => o.Media.Any(d => d.Role == m.Role))
                    && o.Media.All(d => input.Media.Count(m => m.Role == d.Role) >= d.MinCount
                        && input.Media.Count(m => m.Role == d.Role) <= d.MaxCount)).ToArray();
                binding = candidates.Length == 1 ? candidates[0] : null;
            }
            if (binding == null) return Invalid("Select an explicit, supported operation; media does not identify one unambiguous operation.");
            return new FalModelNormalizer().Normalize(binding, input);
        }
        private FalNormalizationResult Invalid(string message) => new(Model.Operations[0], null,
            new[] { new FalFieldError("operation", message) }, Array.Empty<string>());

        internal ValidationResult Validate(GenerationRequest request, ProviderOptions options, IModelCapability capability)
        {
            if (request == null) return ValidationResult.Fail("Request is null.", "request");
            if (request.Model != Model.ModelId || capability?.Id != Model.ModelId)
                return ValidationResult.Fail("Request and capability must belong to the configured model.", "model");
            if (options is not FalModelOptions configured)
                return ValidationResult.Fail("Configured fal models require raw FalModelOptions.", "options");
            var result = Normalize(configured.Input, configured.SelectedOperation);
            return result.Success ? ValidationResult.Ok() : ValidationResult.Fail(result.Errors[0].Message, result.Errors[0].Field);
        }
        internal JsonObject Serialize(ProviderOptions options) => options is FalModelOptions configured
            ? configured.Input.Options : throw new ArgumentException("Expected FalModelOptions.", nameof(options));

        // Compatibility codec JSON is options-only. Production ingress must create FalModelOptions
        // from raw FalModelInput before legacy request constructors; durable snapshots store the full input.
        internal ProviderOptionsDecodeResult Deserialize(JsonObject json) => json == null
            ? ProviderOptionsDecodeResult.Fail(Error("invalid_options", "Configured fal options JSON is null.", "options"))
            : ProviderOptionsDecodeResult.Ok(new FalModelOptions(new FalModelInput(options: json)));

        internal string[] Choices(string key) => Model.Operations.SelectMany(o => o.Fields)
            .Where(f => f.QualifiedKey == "request." + key && f.Type == "enum").SelectMany(f => f.Values).Distinct(StringComparer.Ordinal).ToArray();
        internal int MaxReferences => Model.Operations.SelectMany(o => o.Media).Where(m => m.Role == "reference_image").Select(m => m.MaxCount).DefaultIfEmpty(0).Max();
        internal static GenerationError Error(string code, string message, string? field = null) => new(GenerationErrorCode.InvalidRequest, message, false, field, code);
        internal static GenerationError ConfirmationRequired() => Error("confirmation_required", "Configured generation requires confirmed submission.");
        internal static GenerationError BindingRequired() => Error("configured_binding_required", "Configured lifecycle operations require a pinned operation binding.", "operation");
    }
}
