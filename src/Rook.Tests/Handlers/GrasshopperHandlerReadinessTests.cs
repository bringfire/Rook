using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json;
using System.Threading;
using Rook.Handlers;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.Handlers
{
    [CollectionDefinition(CollectionName, DisableParallelization = true)]
    public sealed class GrasshopperHandlerReadinessCollection
    {
        public const string CollectionName = "GrasshopperHandler readiness";
    }

    [Collection(GrasshopperHandlerReadinessCollection.CollectionName)]
    public sealed class GrasshopperHandlerReadinessTests
    {
        private static readonly PropertyInfo ActiveCanvasProperty = CreateActiveCanvasProperty();

        [Fact]
        public void MutationReceipt_ProjectsTheCapturedGhDocumentIdentity()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);
            var source = new FixedDispatchSource(canvas, document);

            var response = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Mutation,
                document.DocumentID.ToString("D"),
                () =>
                {
                    var issue = handler.BeginMutationReceipt(document, canvas);
                    return handler.GetSolveReadiness(issue.Receipt!.ReceiptId);
                });

            Assert.True(response.Success);
            var receipt = Element(response.Data).GetProperty("receipt");
            Assert.Equal(document.DocumentID.ToString("D"), receipt.GetProperty("gh_document_id").GetString());
        }

        [Fact]
        public void MutationReceipt_WithoutPanelDispatchPreservesLegacyProjection()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);

            var issue = handler.BeginMutationReceipt(document, canvas);
            var response = handler.GetSolveReadiness(issue.Receipt!.ReceiptId);

            Assert.True(response.Success);
            var receipt = Element(response.Data).GetProperty("receipt");
            Assert.False(receipt.TryGetProperty("gh_document_id", out _));
        }

        [Fact]
        public void ReadinessLookupAndWait_RejectAChangedCapturedGhDocument()
        {
            var intended = new FakeDocument();
            var handler = CreateHandler(intended, out var canvas);
            GhSolveReadinessReceipt? receipt = null;
            GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(canvas, intended),
                GhManagedDispatchScope.Mutation,
                intended.DocumentID.ToString("D"),
                () =>
                {
                    receipt = handler.BeginMutationReceipt(intended, canvas).Receipt!;
                    handler.FinalizeMutationReceipt(receipt.ReceiptId, ScheduledOutcome());
                    intended.RaiseSolutionStart();
                    intended.RaiseSolutionEnd();
                    return new ApiResponse { Success = true, Data = new { } };
                });
            var decoy = new FakeDocument();

            var lookup = GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(new FakeCanvas(decoy), decoy),
                GhManagedDispatchScope.Observation,
                null,
                () => handler.GetSolveReadiness(receipt!.ReceiptId));
            var wait = GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(new FakeCanvas(decoy), decoy),
                GhManagedDispatchScope.Observation,
                null,
                () => handler.WaitForSolveReadiness(receipt!.ReceiptId, 1));

            Assert.False(lookup.Success);
            Assert.False(wait.Success);
            Assert.Equal("gh_target_changed", Error(lookup));
            Assert.Equal("gh_target_changed", Error(wait));
        }

        [Fact]
        public void SuccessfulSliderMutation_NestsPendingReceiptWithoutChangingSuccess()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document, out _);

            var response = handler.SetValue(Body(slider.InstanceGuid, 7.5m));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal("slider", data.GetProperty("Type").GetString());
            Assert.Equal(7.5m, data.GetProperty("NewValue").GetDecimal());
            Assert.Equal("pending", MutationReceipt(data).GetProperty("status").GetString());
            Assert.Equal(1, document.ScheduleCount);
            Assert.Equal(1, slider.ExpireCount);
            Assert.False(slider.LastExpireRecompute);
            Assert.Equal(1, document.UndoUtil.RecordCount);
        }

        [Fact]
        public void LifecycleUnavailable_SuccessfulMutationReturnsTerminalUnknownReceipt()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new MissingLifecycleDocument(slider);
            var handler = CreateHandler(document, out _);

            var response = handler.SetValue(Body(slider.InstanceGuid, 3m));

            Assert.True(response.Success);
            var receipt = MutationReceipt(Element(response.Data));
            Assert.Equal("unknown", receipt.GetProperty("status").GetString());
            Assert.Equal("solution_start_event_missing", receipt.GetProperty("reason").GetString());
            Assert.Equal(3m, slider.Slider.Value);
            Assert.Equal(1, document.ScheduleCount);
        }

        [Fact]
        public void SolverLocked_SuccessfulMutationReturnsTerminalSolverLockedReceipt()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider) { Enabled = false };
            var handler = CreateHandler(document, out _);

            var response = handler.SetValue(Body(slider.InstanceGuid, 4m));

            Assert.True(response.Success);
            var receipt = MutationReceipt(Element(response.Data));
            Assert.Equal("solver_locked", receipt.GetProperty("status").GetString());
            Assert.Equal("solver_locked", receipt.GetProperty("reason").GetString());
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void ActiveRegistryCapacity_SetValueFailsBeforeTouchingSlider()
        {
            var slider = new GH_NumberSlider(Guid.NewGuid());
            var document = new FakeDocument(slider);
            var registry = new GhSolveReceiptRegistry();
            var handler = CreateHandler(document, out var canvas, registry);
            handler.EnsureReadinessSession(document, canvas);
            for (var i = 0; i < 64; i++)
            {
                Assert.True(registry.IssueMutation(new object()).Issued);
            }

            var response = handler.SetValue(Body(slider.InstanceGuid, 9m));

            Assert.False(response.Success);
            Assert.Equal("readiness_registry_capacity_exceeded", Error(response));
            Assert.Equal(0, slider.Slider.ValueSetCount);
            Assert.Equal(0, slider.ExpireCount);
            Assert.Equal(0, document.ScheduleCount);
            Assert.Equal(0, document.UndoUtil.RecordCount);
        }

        [Fact]
        public void ExternallyReplacedDocument_NextSetValueStartsNewSessionAndTombstonesOldReceipt()
        {
            var firstSlider = new GH_NumberSlider(Guid.NewGuid());
            var firstDocument = new FakeDocument(firstSlider);
            var registry = new GhSolveReceiptRegistry();
            var handler = CreateHandler(firstDocument, out var canvas, registry);
            var firstResponse = handler.SetValue(Body(firstSlider.InstanceGuid, 1m));
            var firstReceipt = MutationReceipt(Element(firstResponse.Data));

            var secondSlider = new GH_NumberSlider(Guid.NewGuid());
            var secondDocument = new FakeDocument(secondSlider);
            canvas.SetDocumentWithoutEvent(secondDocument);
            var secondResponse = handler.SetValue(Body(secondSlider.InstanceGuid, 2m));

            Assert.True(secondResponse.Success);
            var secondReceipt = MutationReceipt(Element(secondResponse.Data));
            Assert.NotEqual(
                firstReceipt.GetProperty("document_session_id").GetString(),
                secondReceipt.GetProperty("document_session_id").GetString());
            Assert.Equal(
                "document_replaced",
                Receipt(Element(handler.GetSolveReadiness(firstReceipt.GetProperty("receipt_id").GetString()).Data))
                    .GetProperty("status").GetString());
        }

        [Fact]
        public void CanvasDocumentChanged_EagerlyTombstonesAndSignalsPriorSession()
        {
            var document = new FakeDocument();
            var registry = new GhSolveReceiptRegistry();
            var handler = CreateHandler(document, out var canvas, registry);
            var issue = handler.BeginSetValueReceipt(document, canvas);
            var wait = new Thread(() => handler.WaitForSolveReadiness(issue.Receipt!.ReceiptId, 5000));
            wait.Start();
            Assert.True(SpinWait.SpinUntil(
                () => !registry.CanAcquireWaiterForTests(issue.Receipt!.ReceiptId),
                TimeSpan.FromSeconds(1)));

            var replacement = new FakeDocument();
            canvas.ReplaceDocument(replacement);

            Assert.True(wait.Join(TimeSpan.FromSeconds(1)));
            var status = handler.GetSolveReadiness(issue.Receipt!.ReceiptId);
            Assert.Equal("document_replaced", Receipt(Element(status.Data)).GetProperty("status").GetString());
            var replacementIssue = handler.BeginSetValueReceipt(replacement, canvas);
            Assert.NotEqual(issue.Receipt.DocumentSessionId, replacementIssue.Receipt!.DocumentSessionId);
            handler.FinalizeSetValueReceipt(replacementIssue.Receipt.ReceiptId, ScheduledOutcome());

            document.RaiseSolutionStart();
            document.RaiseSolutionEnd();

            Assert.Equal(
                "pending",
                Receipt(Element(handler.GetSolveReadiness(replacementIssue.Receipt.ReceiptId).Data))
                    .GetProperty("status").GetString());
            replacement.RaiseSolutionStart();
            replacement.RaiseSolutionEnd();
            Assert.Equal(
                "ready",
                Receipt(Element(handler.GetSolveReadiness(replacementIssue.Receipt.ReceiptId).Data))
                    .GetProperty("status").GetString());
        }

        [Fact]
        public void CanvasDocumentClosed_NullDocumentDoesNotReusePriorSession()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);
            var first = handler.BeginSetValueReceipt(document, canvas).Receipt!;

            canvas.ReplaceDocument(null);
            canvas.SetDocumentWithoutEvent(document);
            var reopened = handler.BeginSetValueReceipt(document, canvas).Receipt!;

            Assert.Equal(
                "document_replaced",
                Receipt(Element(handler.GetSolveReadiness(first.ReceiptId).Data)).GetProperty("status").GetString());
            Assert.NotEqual(first.DocumentSessionId, reopened.DocumentSessionId);
        }

        [Fact]
        public void KnownTerminalReceipt_StatusIsOuterSuccessWithSnapshot()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);
            var issue = handler.BeginSetValueReceipt(document, canvas);
            handler.FinalizeSetValueReceipt(issue.Receipt!.ReceiptId, LockedOutcome());

            var response = handler.GetSolveReadiness(issue.Receipt.ReceiptId);

            Assert.True(response.Success);
            Assert.Equal("solver_locked", Receipt(Element(response.Data)).GetProperty("status").GetString());
        }

        [Fact]
        public void FinalizeReceipt_UsesSolverLockedOnlyForTheTwoUnavailableClassifications()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);
            var global = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            handler.FinalizeSetValueReceipt(global.ReceiptId, new GhScheduleResult
            {
                ScheduleClassification = GhScheduleClassification.GlobalSolverUnavailable,
                ScheduleAcceptance = GhScheduleAcceptance.NotAttempted,
                Warnings = Array.Empty<GhScheduleWarning>(),
            });

            var other = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            handler.FinalizeSetValueReceipt(other.ReceiptId, new GhScheduleResult
            {
                ScheduleClassification = GhScheduleClassification.AsyncScheduleRequested,
                ScheduleAcceptance = GhScheduleAcceptance.Unknown,
                ScheduleFailureCode = GhScheduleFailureCode.ScheduleAcceptanceUnknown,
                SolverLocked = true,
                Warnings = Array.Empty<GhScheduleWarning>(),
            });

            var globalReceipt = Receipt(Element(handler.GetSolveReadiness(global.ReceiptId).Data));
            var otherReceipt = Receipt(Element(handler.GetSolveReadiness(other.ReceiptId).Data));
            Assert.Equal("solver_locked", globalReceipt.GetProperty("status").GetString());
            Assert.Equal("unknown", otherReceipt.GetProperty("status").GetString());
            Assert.Equal("schedule_acceptance_unknown", otherReceipt.GetProperty("reason").GetString());
        }

        [Fact]
        public void SharedMutationHelpers_IssueAndFinalizeTheExistingReceiptSchema()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);

            var issue = handler.BeginMutationReceipt(document, canvas);
            var finalized = handler.FinalizeMutationReceipt(issue.Receipt!.ReceiptId, ScheduledOutcome());

            Assert.True(issue.Issued);
            Assert.Equal(issue.Receipt.ReceiptId, finalized.ReceiptId);
            Assert.Equal(issue.Receipt.DocumentSessionId, finalized.DocumentSessionId);
            Assert.Equal(issue.Receipt.MutationEpoch, finalized.MutationEpoch);
            Assert.Equal(GhSolveReadinessStatus.Pending, finalized.Status);
        }

        [Fact]
        public void SharedMutationHelpers_FinalizeKnownZeroAndUnknownCommitWithoutScheduling()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);

            var noCommit = handler.BeginMutationReceipt(document, canvas).Receipt!;
            var noCommitTerminal = handler.FinalizeNoCommitReceipt(noCommit.ReceiptId);
            var unknown = handler.BeginMutationReceipt(document, canvas).Receipt!;
            var unknownTerminal = handler.FinalizeUnknownCommitReceipt(unknown.ReceiptId);

            Assert.Equal(GhSolveReadinessStatus.Unknown, noCommitTerminal.Status);
            Assert.Equal("no_solve_relevant_mutation_committed", noCommitTerminal.Reason);
            Assert.Equal(GhSolveReadinessStatus.Unknown, unknownTerminal.Status);
            Assert.Equal("mutation_commit_unknown", unknownTerminal.Reason);
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void PostReservationFailure_WithPriorScheduleFinalizesWithoutSchedulingAgain()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);
            var receipt = handler.BeginMutationReceipt(document, canvas).Receipt!;
            var fallbackScheduleCalls = 0;

            var terminal = handler.FinalizePostReservationFailureReceipt(
                receipt.ReceiptId,
                solveRelevantMutationCommitted: true,
                priorScheduleResult: ScheduledOutcome(),
                scheduleCommittedMutation: () =>
                {
                    fallbackScheduleCalls++;
                    return ScheduledOutcome();
                });

            Assert.NotNull(terminal);
            Assert.Equal(GhSolveReadinessStatus.Pending, terminal!.Status);
            Assert.Equal(0, fallbackScheduleCalls);
            Assert.Equal(0, document.ScheduleCount);
        }

        [Fact]
        public void DirectMutationFailureData_PreservesExactEmptyMessageAndClosedShape()
        {
            var data = Element(GrasshopperHandler.DirectMutationFailureData(
                "set_script_failed",
                string.Empty,
                solveRelevantMutationCommitted: null,
                receipt: null));

            Assert.Equal(
                new[] { "error", "message", "solve_relevant_mutation_committed", "solve_readiness_receipt" },
                data.EnumerateObject().Select(item => item.Name).ToArray());
            Assert.Equal("set_script_failed", data.GetProperty("error").GetString());
            Assert.Equal(string.Empty, data.GetProperty("message").GetString());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("solve_relevant_mutation_committed").ValueKind);
            Assert.Equal(JsonValueKind.Null, data.GetProperty("solve_readiness_receipt").ValueKind);
        }

        [Fact]
        public void DirectMutationFailureData_ProjectionFailureRetainsCommittedFactsWithNullReceipt()
        {
            var receipt = new GhSolveReadinessReceipt(
                "receipt-projection",
                "session-projection",
                1,
                null,
                0,
                GhSolveReadinessStatus.Pending,
                null,
                null,
                DateTimeOffset.UtcNow,
                null);

            var data = Element(GrasshopperHandler.DirectMutationFailureData(
                "set_script_failed",
                "after commit",
                true,
                receipt,
                receiptProjector: _ => throw new InvalidOperationException("projection failed")));

            Assert.Equal("set_script_failed", data.GetProperty("error").GetString());
            Assert.True(data.GetProperty("solve_relevant_mutation_committed").GetBoolean());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("solve_readiness_receipt").ValueKind);
        }

        [Fact]
        public void WaitResponses_UseOnlyReadyTimeoutOrTerminalAndIncludeReceipt()
        {
            var document = new FakeDocument();
            var handler = CreateHandler(document, out var canvas);

            var ready = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            handler.FinalizeSetValueReceipt(ready.ReceiptId, ScheduledOutcome());
            document.RaiseSolutionStart();
            document.RaiseSolutionEnd();
            AssertWait(handler.WaitForSolveReadiness(ready.ReceiptId, 1), "ready", "ready");

            var pending = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            handler.FinalizeSetValueReceipt(pending.ReceiptId, ScheduledOutcome());
            AssertWait(handler.WaitForSolveReadiness(pending.ReceiptId, 1), "timeout", "pending");

            var terminal = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            handler.FinalizeSetValueReceipt(terminal.ReceiptId, LockedOutcome());
            AssertWait(handler.WaitForSolveReadiness(terminal.ReceiptId, 300000), "terminal", "solver_locked");
        }

        [Fact]
        public void AbsentReceipt_StatusAndWaitUseStableOuterFailure()
        {
            var handler = CreateHandler(new FakeDocument(), out _);

            AssertUnknownReceiptFailure(handler, "absent-id");
        }

        [Fact]
        public void EvictedReceipt_StatusAndWaitUseStableOuterFailure()
        {
            var registry = new GhSolveReceiptRegistry();
            var document = new object();
            var first = registry.IssueMutation(document).Receipt!;
            registry.MarkSolverLocked(first.ReceiptId);
            for (var i = 0; i < 256; i++)
            {
                var receipt = registry.IssueMutation(document).Receipt!;
                registry.MarkSolverLocked(receipt.ReceiptId);
            }

            var handler = CreateHandler(new FakeDocument(), out _, registry);

            AssertUnknownReceiptFailure(handler, first.ReceiptId);
        }

        [Fact]
        public void PostRestartReceipt_StatusAndWaitUseStableOuterFailure()
        {
            var priorRegistry = new GhSolveReceiptRegistry();
            var priorReceipt = priorRegistry.IssueMutation(new object()).Receipt!;
            var handler = CreateHandler(new FakeDocument(), out _, new GhSolveReceiptRegistry());

            AssertUnknownReceiptFailure(handler, priorReceipt.ReceiptId);
        }

        private static void AssertUnknownReceiptFailure(GrasshopperHandler handler, string receiptId)
        {
            var status = handler.GetSolveReadiness(receiptId);
            var wait = handler.WaitForSolveReadiness(receiptId, 1);

            Assert.False(status.Success);
            Assert.False(wait.Success);
            Assert.Equal("readiness_receipt_not_found_or_evicted_or_process_restarted", Error(status));
            Assert.Equal("readiness_receipt_not_found_or_evicted_or_process_restarted", Error(wait));
        }

        [Fact]
        public void FencedInspect_PendingUnknownAndSupersededFailBeforeExtraction()
        {
            var component = new FakeComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document, out var canvas);

            var pending = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            AssertFenceFailure(handler, document, component, pending.ReceiptId, "readiness_receipt_not_ready");

            handler.FinalizeSetValueReceipt(pending.ReceiptId, UnavailableOutcome());
            AssertFenceFailure(handler, document, component, pending.ReceiptId, "readiness_receipt_unknown");

            var older = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            handler.BeginSetValueReceipt(document, canvas);
            AssertFenceFailure(handler, document, component, older.ReceiptId, "readiness_receipt_superseded");
        }

        [Fact]
        public void FencedInspect_StaleReceiptFailsBeforeExtraction()
        {
            var component = new FakeComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document, out var canvas);
            var receipt = ReadyReceipt(handler, document, canvas);
            document.RaiseSolutionStart();
            document.RaiseSolutionEnd();

            AssertFenceFailure(
                handler,
                document,
                component,
                receipt.ReceiptId,
                "readiness_receipt_stale_solution_run");
        }

        [Fact]
        public void FencedInspect_ReadyReceiptAddsBoundedProvenance()
        {
            var component = new FakeComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document, out var canvas);
            var receipt = ReadyReceipt(handler, document, canvas);

            var response = handler.InspectOutput(component.InstanceGuid.ToString(), "R", receipt.ReceiptId);

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.True(data.GetProperty("readiness_fenced").GetBoolean());
            Assert.Equal(receipt.ReceiptId, data.GetProperty("readiness_receipt_id").GetString());
            Assert.Equal(receipt.DocumentSessionId, data.GetProperty("document_session_id").GetString());
            Assert.Equal(1, data.GetProperty("mutation_epoch").GetInt64());
            Assert.Equal(1, data.GetProperty("solution_run_epoch").GetInt64());
            Assert.Equal(1, data.GetProperty("completed_solution_run_epoch").GetInt64());
            Assert.Equal(1, document.ObjectsReadCount);
        }

        [Fact]
        public void FencedInspect_RejectsChangedCapturedGhDocumentBeforeExtraction()
        {
            var component = new FakeComponent(Guid.NewGuid());
            var intended = new FakeDocument(component);
            var handler = CreateHandler(intended, out var canvas);
            GhSolveReadinessReceipt? receipt = null;
            GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(canvas, intended),
                GhManagedDispatchScope.Mutation,
                intended.DocumentID.ToString("D"),
                () =>
                {
                    receipt = ReadyReceipt(handler, intended, canvas);
                    return new ApiResponse { Success = true, Data = new { } };
                });
            var decoy = new FakeDocument(component);

            var response = GrasshopperDispatchContext.Execute(
                new FixedDispatchSource(new FakeCanvas(decoy), decoy),
                GhManagedDispatchScope.Observation,
                null,
                () => handler.InspectOutput(
                    component.InstanceGuid.ToString(),
                    "R",
                    receipt!.ReceiptId));

            Assert.False(response.Success);
            Assert.Equal("gh_target_changed", Error(response));
            Assert.Equal(0, decoy.ObjectsReadCount);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void FencedInspect_ExplicitBlankReceiptFailsClosedBeforeExtraction(string receiptId)
        {
            var component = new FakeComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document, out _);

            var response = handler.InspectOutput(component.InstanceGuid.ToString(), "R", receiptId);

            Assert.False(response.Success);
            Assert.Equal("readiness_receipt_id_invalid", Error(response));
            Assert.Equal(0, document.ObjectsReadCount);
        }

        [Fact]
        public void InspectOutput_OmittedReceiptPreservesLegacyUnfencedRead()
        {
            var component = new FakeComponent(Guid.NewGuid());
            var document = new FakeDocument(component);
            var handler = CreateHandler(document, out _);

            var response = handler.InspectOutput(component.InstanceGuid.ToString(), "R");

            Assert.True(response.Success);
            Assert.False(Element(response.Data).TryGetProperty("readiness_fenced", out _));
            Assert.Equal(1, document.ObjectsReadCount);
        }

        [Theory]
        [InlineData(5)]
        [InlineData(6)]
        [InlineData(7)]
        public void InspectOutput_ExplicitIndexReturnsResolvedOutputMetadataWithoutReadingOutputZero(
            int outputIndex)
        {
            var component = new FakeComponent(Guid.NewGuid(), outputCount: 8);
            var document = new FakeDocument(component);
            var handler = CreateHandler(document, out _);

            var response = handler.InspectOutput(
                component.InstanceGuid.ToString(),
                new GhInspectOutputSelector(param: null, outputIndex));

            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal(outputIndex, data.GetProperty("index").GetInt32());
            Assert.Equal($"Output {outputIndex}", data.GetProperty("param_name").GetString());
            Assert.Equal(0, component.Params.Output[0].VolatileDataReadCount);
            Assert.Equal(1, component.Params.Output[outputIndex].VolatileDataReadCount);
        }

        [Fact]
        public void ThrowingMutationWithUnknownCommit_TerminatesReservedReceiptAsUnknown()
        {
            var nextId = 0;
            var registry = new GhSolveReceiptRegistry(idFactory: () => "id-" + ++nextId);
            var slider = new GH_NumberSlider(Guid.NewGuid());
            slider.Slider.ThrowOnValueSet = true;
            var document = new FakeDocument(slider);
            var handler = CreateHandler(document, out _, registry);

            var response = handler.SetValue(Body(slider.InstanceGuid, 5m));

            Assert.False(response.Success);
            var lookup = registry.Get("id-2");
            Assert.True(lookup.Found);
            Assert.Equal(GhSolveReadinessStatus.Unknown, lookup.Receipt!.Status);
            Assert.Equal("mutation_commit_unknown", lookup.Receipt.Reason);
        }

        private static void AssertFenceFailure(
            GrasshopperHandler handler,
            FakeDocument document,
            FakeComponent component,
            string receiptId,
            string expectedError)
        {
            var readsBefore = document.ObjectsReadCount;

            var response = handler.InspectOutput(component.InstanceGuid.ToString(), "R", receiptId);

            Assert.False(response.Success);
            Assert.Equal(expectedError, Error(response));
            Assert.True(Element(response.Data).TryGetProperty("receipt", out _));
            Assert.Equal(readsBefore, document.ObjectsReadCount);
        }

        private static void AssertWait(ApiResponse response, string waitStatus, string receiptStatus)
        {
            Assert.True(response.Success);
            var data = Element(response.Data);
            Assert.Equal("rook.gh_solve_readiness_wait_result:v1", data.GetProperty("schema").GetString());
            Assert.Equal(waitStatus, data.GetProperty("wait_status").GetString());
            Assert.Equal(receiptStatus, Receipt(data).GetProperty("status").GetString());
            Assert.Equal(3, data.EnumerateObject().Count());
        }

        private static GhSolveReadinessReceipt ReadyReceipt(
            GrasshopperHandler handler,
            FakeDocument document,
            FakeCanvas canvas)
        {
            var receipt = handler.BeginSetValueReceipt(document, canvas).Receipt!;
            handler.FinalizeSetValueReceipt(receipt.ReceiptId, ScheduledOutcome());
            document.RaiseSolutionStart();
            document.RaiseSolutionEnd();
            return receipt;
        }

        private static GhScheduleResult ScheduledOutcome() => new()
        {
            ScheduleClassification = GhScheduleClassification.AsyncScheduleRequested,
            ScheduleAcceptance = GhScheduleAcceptance.Accepted,
            SolverStateKnown = true,
            Warnings = Array.Empty<GhScheduleWarning>(),
        };

        private static GhScheduleResult LockedOutcome() => new()
        {
            ScheduleClassification = GhScheduleClassification.DocumentSolverDisabled,
            ScheduleAcceptance = GhScheduleAcceptance.NotAttempted,
            SolverLocked = true,
            SolverStateKnown = true,
            Warnings = Array.Empty<GhScheduleWarning>(),
        };

        private static GhScheduleResult UnavailableOutcome() => new()
        {
            ScheduleClassification = GhScheduleClassification.AsyncScheduleRequested,
            ScheduleAcceptance = GhScheduleAcceptance.Unavailable,
            ScheduleFailureCode = GhScheduleFailureCode.ScheduleApiUnavailable,
            SolverStateKnown = true,
            Warnings = Array.Empty<GhScheduleWarning>(),
        };

        private static GrasshopperHandler CreateHandler(
            object document,
            out FakeCanvas canvas,
            GhSolveReceiptRegistry? registry = null)
        {
            FakeDocument.EnableSolutions = true;
            MissingLifecycleDocument.EnableSolutions = true;
            canvas = new FakeCanvas(document);
            ActiveCanvasProperty.SetValue(null, canvas);
            return new GrasshopperHandler(
                bridgeCore: new ReadyCore(),
                runningAsRhinoInside: () => false,
                solveReceiptRegistry: registry ?? new GhSolveReceiptRegistry(),
                solutionLifecycleAdapter: new GhSolutionLifecycleAdapter(),
                canvasDocumentLifecycleAdapter: new GhCanvasDocumentLifecycleAdapter());
        }

        private static string Body(Guid guid, decimal value) =>
            JsonSerializer.Serialize(new { guid = guid.ToString(), value });

        private static JsonElement Element(object? data) => JsonSerializer.SerializeToElement(data);

        private static JsonElement Receipt(JsonElement data) => data.GetProperty("receipt");

        private static JsonElement MutationReceipt(JsonElement data) =>
            data.GetProperty("solve_readiness_receipt");

        private static string Error(ApiResponse response) =>
            Element(response.Data).GetProperty("error").GetString()!;

        private static PropertyInfo CreateActiveCanvasProperty()
        {
            var existing = AppDomain.CurrentDomain.GetAssemblies()
                .FirstOrDefault(assembly => assembly.GetName().Name == "Grasshopper")
                ?.GetType("Grasshopper.Instances")
                ?.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static);
            if (existing != null)
            {
                return existing;
            }

            var assemblyName = new AssemblyName("Grasshopper");
            var assembly = AppDomain.CurrentDomain.DefineDynamicAssembly(assemblyName, AssemblyBuilderAccess.Run);
            var module = assembly.DefineDynamicModule("Grasshopper");
            module.DefineType(
                "Grasshopper.Kernel.IGH_Param",
                TypeAttributes.Public | TypeAttributes.Interface | TypeAttributes.Abstract)
                .CreateType();
            DefineGrasshopperNumberSlider(module);
            var type = module.DefineType(
                "Grasshopper.Instances",
                TypeAttributes.Public | TypeAttributes.Abstract | TypeAttributes.Sealed);
            var field = type.DefineField("_activeCanvas", typeof(object), FieldAttributes.Private | FieldAttributes.Static);
            var property = type.DefineProperty("ActiveCanvas", PropertyAttributes.None, typeof(object), Type.EmptyTypes);
            var getter = type.DefineMethod(
                "get_ActiveCanvas",
                MethodAttributes.Public | MethodAttributes.Static | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                typeof(object),
                Type.EmptyTypes);
            var getterIl = getter.GetILGenerator();
            getterIl.Emit(OpCodes.Ldsfld, field);
            getterIl.Emit(OpCodes.Ret);
            var setter = type.DefineMethod(
                "set_ActiveCanvas",
                MethodAttributes.Public | MethodAttributes.Static | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                null,
                new[] { typeof(object) });
            var setterIl = setter.GetILGenerator();
            setterIl.Emit(OpCodes.Ldarg_0);
            setterIl.Emit(OpCodes.Stsfld, field);
            setterIl.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
            property.SetSetMethod(setter);
            return type.CreateType()!.GetProperty("ActiveCanvas", BindingFlags.Public | BindingFlags.Static)!;
        }

        private static void DefineGrasshopperNumberSlider(ModuleBuilder module)
        {
            var type = module.DefineType(
                "Grasshopper.Kernel.Special.GH_NumberSlider",
                TypeAttributes.Public | TypeAttributes.Class);
            var guidField = type.DefineField("_instanceGuid", typeof(Guid), FieldAttributes.Private);
            var nickField = type.DefineField("_nickName", typeof(string), FieldAttributes.Private);
            var constructor = type.DefineConstructor(
                MethodAttributes.Public,
                CallingConventions.Standard,
                Type.EmptyTypes);
            var constructorIl = constructor.GetILGenerator();
            constructorIl.Emit(OpCodes.Ldarg_0);
            constructorIl.Emit(OpCodes.Call, typeof(object).GetConstructor(Type.EmptyTypes)!);
            constructorIl.Emit(OpCodes.Ldarg_0);
            constructorIl.Emit(OpCodes.Call, typeof(Guid).GetMethod(nameof(Guid.NewGuid), BindingFlags.Public | BindingFlags.Static)!);
            constructorIl.Emit(OpCodes.Stfld, guidField);
            constructorIl.Emit(OpCodes.Ret);
            DefineReadOnlyProperty(type, "InstanceGuid", typeof(Guid), guidField);
            DefineReadWriteProperty(type, "NickName", typeof(string), nickField);
            DefineNullProperty(type, "Slider");
            var expire = type.DefineMethod("ExpireSolution", MethodAttributes.Public, typeof(void), new[] { typeof(bool) });
            expire.GetILGenerator().Emit(OpCodes.Ret);
            type.CreateType();
        }

        private static void DefineReadOnlyProperty(TypeBuilder type, string name, Type propertyType, FieldBuilder field)
        {
            var property = type.DefineProperty(name, PropertyAttributes.None, propertyType, Type.EmptyTypes);
            var getter = type.DefineMethod(
                $"get_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                propertyType,
                Type.EmptyTypes);
            var il = getter.GetILGenerator();
            il.Emit(OpCodes.Ldarg_0);
            il.Emit(OpCodes.Ldfld, field);
            il.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
        }

        private static void DefineReadWriteProperty(TypeBuilder type, string name, Type propertyType, FieldBuilder field)
        {
            var property = type.DefineProperty(name, PropertyAttributes.None, propertyType, Type.EmptyTypes);
            var getter = type.DefineMethod(
                $"get_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                propertyType,
                Type.EmptyTypes);
            var getterIl = getter.GetILGenerator();
            getterIl.Emit(OpCodes.Ldarg_0);
            getterIl.Emit(OpCodes.Ldfld, field);
            getterIl.Emit(OpCodes.Ret);
            var setter = type.DefineMethod(
                $"set_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                typeof(void),
                new[] { propertyType });
            var setterIl = setter.GetILGenerator();
            setterIl.Emit(OpCodes.Ldarg_0);
            setterIl.Emit(OpCodes.Ldarg_1);
            setterIl.Emit(OpCodes.Stfld, field);
            setterIl.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
            property.SetSetMethod(setter);
        }

        private static void DefineNullProperty(TypeBuilder type, string name)
        {
            var property = type.DefineProperty(name, PropertyAttributes.None, typeof(object), Type.EmptyTypes);
            var getter = type.DefineMethod(
                $"get_{name}",
                MethodAttributes.Public | MethodAttributes.SpecialName | MethodAttributes.HideBySig,
                typeof(object),
                Type.EmptyTypes);
            var il = getter.GetILGenerator();
            il.Emit(OpCodes.Ldnull);
            il.Emit(OpCodes.Ret);
            property.SetGetMethod(getter);
        }

        private sealed class ReadyCore : IGrasshopperCore
        {
            public BridgeResult<GrasshopperStatusDto> GetStatus() =>
                BridgeResult<GrasshopperStatusDto>.Ok(new GrasshopperStatusDto
                {
                    Available = true,
                    HasActiveCanvas = true,
                    HasActiveDocument = true,
                    CanvasVisible = true,
                    ReadyForEdit = true,
                });

            public BridgeResult<GrasshopperDocumentInfoDto> GetDocumentInfo() =>
                BridgeResult<GrasshopperDocumentInfoDto>.Ok(new GrasshopperDocumentInfoDto());

            public BridgeResult<GrasshopperQueryDto> QueryDocument() =>
                BridgeResult<GrasshopperQueryDto>.Ok(new GrasshopperQueryDto());

            public BridgeResult<GrasshopperSelectionDto> GetSelection() =>
                BridgeResult<GrasshopperSelectionDto>.Ok(new GrasshopperSelectionDto());
        }

        public sealed class FakeCanvasDocumentChangedEventArgs : EventArgs
        {
            public FakeCanvasDocumentChangedEventArgs(object? oldDocument, object? newDocument)
            {
                OldDocument = oldDocument;
                NewDocument = newDocument;
            }

            public object? OldDocument { get; }
            public object? NewDocument { get; }
        }

        public sealed class FakeCanvas
        {
            public FakeCanvas(object document)
            {
                Document = document;
            }

            public object? Document { get; private set; }
            public int RefreshCount { get; private set; }
            public event EventHandler<FakeCanvasDocumentChangedEventArgs>? DocumentChanged;

            public void Refresh() => RefreshCount++;

            public void SetDocumentWithoutEvent(object? document) => Document = document;

            public void ReplaceDocument(object? document)
            {
                var oldDocument = Document;
                Document = document;
                DocumentChanged?.Invoke(this, new FakeCanvasDocumentChangedEventArgs(oldDocument, document));
            }
        }

        public sealed class FakeSolutionEventArgs : EventArgs
        {
            public FakeSolutionEventArgs(object document)
            {
                Document = document;
            }

            public object Document { get; }
        }

        public sealed class FakeDocument
        {
            private readonly IReadOnlyList<object> _objects;

            public FakeDocument(params object[] objects)
            {
                _objects = objects;
            }

            public static bool EnableSolutions { get; set; } = true;
            public Guid DocumentID { get; } = Guid.NewGuid();
            public bool Enabled { get; set; } = true;
            public int ScheduleCount { get; private set; }
            public int ObjectsReadCount { get; private set; }
            public FakeUndoUtil UndoUtil { get; } = new();
            public IReadOnlyList<object> Objects
            {
                get
                {
                    ObjectsReadCount++;
                    return _objects;
                }
            }

            public event EventHandler<FakeSolutionEventArgs>? SolutionStart;
            public event EventHandler<FakeSolutionEventArgs>? SolutionEnd;

            public void ScheduleSolution(int delayMs) => ScheduleCount++;
            public void RaiseSolutionStart() => SolutionStart?.Invoke(this, new FakeSolutionEventArgs(this));
            public void RaiseSolutionEnd() => SolutionEnd?.Invoke(this, new FakeSolutionEventArgs(this));
        }

        private sealed class FixedDispatchSource : IGrasshopperDispatchSource
        {
            private readonly object _canvas;
            private readonly object _document;

            internal FixedDispatchSource(object canvas, object document)
            {
                _canvas = canvas;
                _document = document;
            }

            public GrasshopperDispatchCapture Capture() =>
                GrasshopperDispatchCapture.Available(
                    typeof(FixedDispatchSource).Assembly,
                    _canvas,
                    _document);
        }

        public sealed class FakeUndoUtil
        {
            public int RecordCount { get; private set; }

            public void RecordGenericObjectEvent(string name, object documentObject) => RecordCount++;
        }

        public sealed class MissingLifecycleDocument
        {
            public MissingLifecycleDocument(params object[] objects)
            {
                Objects = objects;
            }

            public static bool EnableSolutions { get; set; } = true;
            public bool Enabled { get; set; } = true;
            public IReadOnlyList<object> Objects { get; }
            public int ScheduleCount { get; private set; }

            public void ScheduleSolution(int delayMs) => ScheduleCount++;
        }

        public sealed class GH_NumberSlider
        {
            public GH_NumberSlider(Guid instanceGuid)
            {
                InstanceGuid = instanceGuid;
            }

            public Guid InstanceGuid { get; }
            public FakeSlider Slider { get; } = new();
            public int ExpireCount { get; private set; }
            public bool LastExpireRecompute { get; private set; }

            public void ExpireSolution(bool recompute)
            {
                ExpireCount++;
                LastExpireRecompute = recompute;
            }
        }

        public sealed class FakeSlider
        {
            private decimal _value;

            public decimal Minimum { get; set; }
            public decimal Maximum { get; set; } = 100m;
            public bool ThrowOnValueSet { get; set; }
            public int ValueSetCount { get; private set; }
            public decimal Value
            {
                get => _value;
                set
                {
                    ValueSetCount++;
                    if (ThrowOnValueSet)
                    {
                        throw new InvalidOperationException("value mutation failed");
                    }

                    _value = value;
                }
            }
        }

        public sealed class FakeComponent
        {
            public FakeComponent(Guid instanceGuid, int outputCount = 1)
            {
                InstanceGuid = instanceGuid;
                Params = new FakeParams(outputCount);
            }

            public Guid InstanceGuid { get; }
            public FakeParams Params { get; }
        }

        public sealed class FakeParams
        {
            public FakeParams(int outputCount)
            {
                Output = Enumerable.Range(0, outputCount)
                    .Select(index => new FakeOutput(index))
                    .ToList();
            }

            public IList<FakeOutput> Output { get; }
        }

        public sealed class FakeOutput
        {
            public FakeOutput(int index)
            {
                Name = index == 0 ? "Result" : $"Output {index}";
                NickName = index == 0 ? "R" : $"O{index}";
            }

            public string Name { get; }
            public string NickName { get; }
            public string TypeName { get; } = "Number";
            public int VolatileDataReadCount { get; private set; }
            public object? VolatileData
            {
                get
                {
                    VolatileDataReadCount++;
                    return null;
                }
            }
        }
    }
}
