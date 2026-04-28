using System;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Consumer-side exhaustiveness check for the
    /// <see cref="ProviderSubmitOutcome"/> closed union (abstract class
    /// + sealed class hierarchy). C# does not natively enforce
    /// exhaustive switch matching on these unions; the structural
    /// closure is enforced by <c>UnionClosureTests</c> while these
    /// tests cover the consumer-side switch pattern. If a future
    /// change adds a new outcome subtype, the <c>switch</c> below
    /// will hit the <c>throw</c> arm and fail the test, surfacing
    /// the missing consumer-update.
    /// </summary>
    public class SubmitOutcomeExhaustivenessTests
    {
        private static string ClassifySubmit(ProviderSubmitOutcome outcome) => outcome switch
        {
            SyncSubmitOutcome => "sync",
            QueuedSubmitOutcome => "queued",
            FailedSubmitOutcome => "failed",
            _ => throw new InvalidOperationException(
                $"Unhandled ProviderSubmitOutcome subtype: {outcome.GetType().FullName}. " +
                "Update every consumer's switch statement when adding a new subtype."),
        };

        [Fact]
        public void Switch_handles_sync_subtype()
        {
            var inlineEnvelope = new ProviderResultEnvelope(
                Artifacts: new[]
                {
                    new ResultArtifact(
                        Role: "image",
                        Body: new InlineArtifactBody(new byte[] { 0x01 }),
                        DeclaredMimeType: "image/png",
                        ProviderMetadata: new System.Collections.Generic.Dictionary<string, System.Text.Json.Nodes.JsonNode>()),
                },
                EnvelopeMetadata: new System.Collections.Generic.Dictionary<string, System.Text.Json.Nodes.JsonNode>());

            var outcome = new SyncSubmitOutcome(new SuccessResultOutcome(inlineEnvelope));
            Assert.Equal("sync", ClassifySubmit(outcome));
        }

        [Fact]
        public void Switch_handles_queued_subtype()
        {
            var outcome = new QueuedSubmitOutcome(new ProviderJobHandle("job-123"));
            Assert.Equal("queued", ClassifySubmit(outcome));
        }

        [Fact]
        public void Switch_handles_failed_subtype()
        {
            var error = new GenerationError(
                Code: GenerationErrorCode.DependencyUnavailable,
                Message: "API key not configured.",
                Retryable: false);
            var outcome = new FailedSubmitOutcome(error);
            Assert.Equal("failed", ClassifySubmit(outcome));
        }

        // Result outcome union exhaustiveness — same enforcement.
        private static string ClassifyResult(ProviderResultOutcome outcome) => outcome switch
        {
            SuccessResultOutcome => "success",
            FailedResultOutcome => "failed",
            _ => throw new InvalidOperationException(
                $"Unhandled ProviderResultOutcome subtype: {outcome.GetType().FullName}."),
        };

        [Fact]
        public void Result_outcome_switch_is_exhaustive_over_known_subtypes()
        {
            var envelope = new ProviderResultEnvelope(
                Artifacts: new[]
                {
                    new ResultArtifact(
                        Role: "image",
                        Body: new InlineArtifactBody(new byte[] { 0x01 }),
                        DeclaredMimeType: "image/png",
                        ProviderMetadata: new System.Collections.Generic.Dictionary<string, System.Text.Json.Nodes.JsonNode>()),
                },
                EnvelopeMetadata: new System.Collections.Generic.Dictionary<string, System.Text.Json.Nodes.JsonNode>());

            Assert.Equal("success", ClassifyResult(new SuccessResultOutcome(envelope)));
            Assert.Equal("failed", ClassifyResult(new FailedResultOutcome(
                new GenerationError(GenerationErrorCode.ExecutionFailed, "NSFW", false))));
        }

        // Status outcome union exhaustiveness.
        private static string ClassifyStatus(ProviderStatusOutcome outcome) => outcome switch
        {
            InFlightStatusOutcome => "in_flight",
            ProviderCompleteStatusOutcome => "complete",
            FailedStatusOutcome => "failed",
            _ => throw new InvalidOperationException(
                $"Unhandled ProviderStatusOutcome subtype: {outcome.GetType().FullName}."),
        };

        [Fact]
        public void Status_outcome_switch_is_exhaustive_over_known_subtypes()
        {
            Assert.Equal("in_flight", ClassifyStatus(new InFlightStatusOutcome(
                GenerationLifecycleState.Pending, null)));
            Assert.Equal("complete", ClassifyStatus(new ProviderCompleteStatusOutcome(
                new ProviderJobHandle("job-1"))));
            Assert.Equal("failed", ClassifyStatus(new FailedStatusOutcome(
                new GenerationError(GenerationErrorCode.ExecutionFailed, "boom", false))));
        }

        // Cancel outcome union exhaustiveness.
        private static string ClassifyCancel(ProviderCancelOutcome outcome) => outcome switch
        {
            CanceledOutcome => "canceled",
            AlreadyTerminalOutcome => "already_terminal",
            FailedCancelOutcome => "failed",
            _ => throw new InvalidOperationException(
                $"Unhandled ProviderCancelOutcome subtype: {outcome.GetType().FullName}."),
        };

        [Fact]
        public void Cancel_outcome_switch_is_exhaustive_over_known_subtypes()
        {
            Assert.Equal("canceled", ClassifyCancel(new CanceledOutcome()));
            Assert.Equal("already_terminal", ClassifyCancel(new AlreadyTerminalOutcome(
                GenerationLifecycleState.Completed)));
            Assert.Equal("failed", ClassifyCancel(new FailedCancelOutcome(
                new GenerationError(GenerationErrorCode.DependencyUnavailable, "503", true))));
        }
    }
}
