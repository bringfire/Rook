using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    /// <summary>Immutable execution authority and history. Never contains transport media or keys.</summary>
    public sealed class FalExecutionSnapshot
    {
        public const int CurrentVersion = 1;
        public const string ExtensionKey = "configured_fal_execution";
        public FalNormalizedRequest Request { get; }
        public FalOperationBinding Binding => Request.Binding;
        public FalPricingSnapshot? Pricing { get; }
        public string DispatchState { get; }
        public ProviderJobHandle? Handle { get; }
        public string? SubmissionOutcome { get; }
        public FalCancellationSnapshot? Cancellation { get; }
        public bool OutcomeUnknown => SubmissionOutcome == "unknown" || SubmissionOutcome == null && DispatchState == "dispatch_intent";
        private readonly JsonArray _media;
        public JsonArray MediaProvenance => (JsonArray)_media.DeepClone();
        internal FalExecutionSnapshot(FalNormalizedRequest request, JsonArray media, FalPricingSnapshot? pricing, string state, ProviderJobHandle? handle, string? outcome = null, FalCancellationSnapshot? cancellation = null)
        {
            if (state is not ("prepared" or "dispatch_intent" or "accepted" or "unknown")) throw new ArgumentException("Invalid dispatch state.");
            if (handle != null && FalConfiguredLifecycle.Validate(request.Binding, handle) is { } error) throw new ArgumentException(error.Message);
            if (state == "accepted" && handle == null && request.Binding.Invocation == "queue") throw new ArgumentException("Accepted queue execution requires a handle.");
            if (handle != null && state is not ("accepted" or "unknown")) throw new ArgumentException("Unexpected handle before acceptance.");
            Request = request; _media = (JsonArray)media.DeepClone(); Pricing = pricing; DispatchState = state;
            if (outcome is not (null or "not_accepted" or "accepted" or "unknown")) throw new ArgumentException("Invalid submission outcome.");
            SubmissionOutcome = outcome;
            Cancellation = cancellation;
            Handle = handle == null ? null : new ProviderJobHandle(handle.ProviderJobId, handle.StatusUrl, handle.ResponseUrl, handle.CancelUrl, "PUT");
        }
        public static FalExecutionSnapshot Create(FalNormalizedRequest request, FalMediaSnapshot media, FalPricingSnapshot? pricing = null)
        {
            if (media.Validate(request) is { } error) throw new ArgumentException(error.Message);
            var provenance = new JsonArray();
            foreach (var slot in media.Slots)
                provenance.Add(new JsonObject { ["role"] = slot.Role, ["ordinal"] = slot.Ordinal,
                    ["artifact_id"] = slot.Source.ArtifactId?.ToString("D"), ["source_role"] = slot.Source.Role,
                    ["source_kind"] = slot.Source.Kind.ToString(), ["sha256"] = slot.Sha256,
                    ["mime_type"] = slot.MimeType, ["byte_length"] = slot.ByteLength });
            return new FalExecutionSnapshot(request, provenance, pricing, "prepared", null);
        }
        public FalExecutionSnapshot WithDispatchState(string state, ProviderJobHandle? handle = null)
            => new(Request, _media, Pricing, state, handle ?? Handle, state == "accepted" ? "accepted" : state == "unknown" ? "unknown" : SubmissionOutcome, Cancellation);
        public FalExecutionSnapshot WithOutcome(ProviderSubmitOutcome outcome) => outcome is FailedSubmitOutcome failed
            ? new(Request, _media, Pricing, failed.Disposition == SubmissionDisposition.Unknown ? "unknown" : DispatchState, Handle,
                failed.Disposition == SubmissionDisposition.Unknown ? "unknown" : "not_accepted", Cancellation)
            : WithDispatchState("accepted", (outcome as QueuedSubmitOutcome)?.Handle);
        public FalExecutionSnapshot WithCancellation(FalCancellationSnapshot cancellation)
            => new(Request, _media, Pricing, DispatchState, Handle, SubmissionOutcome, cancellation ?? throw new ArgumentNullException(nameof(cancellation)));
        // Called under the manager's commit gate for a cancellation that originally
        // saw no handle. Absence observed earlier cannot erase a later remote fact.
        internal (FalCancellationSnapshot Evidence, GenerationError? Error) ReconcileNoHandleCancellation(bool automatic)
        {
            if (Handle != null && Cancellation != null)
                return (Cancellation, Cancellation.RetainedOutcomeError());
            var error = Handle != null
                ? FalExecutionRecovery.Unavailable("Local monitoring stopped; a remote handle is now available, but remote cancellation is not yet confirmed.")
                : OutcomeUnknown ? FalExecutionRecovery.Unavailable("Local monitoring stopped; remote submission outcome is unknown.") : null;
            return (new FalCancellationSnapshot(true, error == null ? "not_requested" : "unavailable", automatic), error);
        }

        internal GenerationError? ReconcileStopError(GenerationError? error)
            => error?.ProviderErrorCode == "fal_submission_unknown" && SubmissionOutcome is "accepted" or "not_accepted"
                ? new GenerationError(error.Code, SubmissionOutcome == "accepted"
                    ? "Local monitoring stopped after provider acceptance; remote work may continue until cancellation is confirmed."
                    : "Local monitoring stopped; the provider subsequently confirmed submission was not accepted.", false)
                : error;
    }
}
