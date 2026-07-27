using System;
using System.Collections.Generic;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GhScheduleInvokerTests
    {
        [Fact]
        public void Invoke_MissingScheduleMethod_IsUnavailableWithoutInvocation()
        {
            var result = GhScheduleInvoker.Invoke(new NoScheduleDocument(), PermittedDecision(), 1);

            Assert.Equal(GhScheduleAcceptance.Unavailable, result.ScheduleAcceptance);
            Assert.Equal(GhScheduleFailureCode.ScheduleApiUnavailable, result.ScheduleFailureCode);
            Assert.False(result.SolveScheduled);
        }

        [Fact]
        public void Invoke_ZeroDelay_IsRejectedBeforeInvocation()
        {
            var document = new ReturningDocument();

            var result = GhScheduleInvoker.Invoke(document, PermittedDecision(), 0);

            Assert.Equal(GhScheduleAcceptance.NotAttempted, result.ScheduleAcceptance);
            Assert.Equal(GhScheduleFailureCode.SchedulePreconditionRejected, result.ScheduleFailureCode);
            Assert.Equal(0, document.CallCount);
        }

        [Fact]
        public void Invoke_ReturningMethod_InvokesExactlyOnceWithPositiveDelay()
        {
            var document = new ReturningDocument();

            var result = GhScheduleInvoker.Invoke(document, PermittedDecision(), 25);

            Assert.Equal(1, document.CallCount);
            Assert.Equal(25, document.Delay);
            Assert.Equal(GhScheduleAcceptance.Accepted, result.ScheduleAcceptance);
            Assert.Null(result.ScheduleFailureCode);
            Assert.True(result.SolveScheduled);
            Assert.True(result.VerificationDeferred);
        }

        [Fact]
        public void Invoke_ThrowingTarget_IsUnknownWithoutRetry()
        {
            var document = new ThrowingDocument();

            var result = GhScheduleInvoker.Invoke(document, PermittedDecision(), 9);

            Assert.Equal(1, document.CallCount);
            Assert.Equal(9, document.Delay);
            Assert.True(document.ScheduleArmed);
            Assert.Equal(GhScheduleAcceptance.Unknown, result.ScheduleAcceptance);
            Assert.Equal(GhScheduleFailureCode.ScheduleAcceptanceUnknown, result.ScheduleFailureCode);
            Assert.False(result.SolveScheduled);
            Assert.True(result.VerificationDeferred);
            Assert.Equal(nameof(InvalidOperationException), result.ExceptionType);
        }

        [Fact]
        public void Invoke_AmbiguousReflectionBeforeInvocation_IsNotAttemptedOnlyWhenNoTargetCanBeEntered()
        {
            var result = GhScheduleInvoker.Invoke(new AmbiguousDocument(), PermittedDecision(), 1);

            Assert.Equal(GhScheduleAcceptance.NotAttempted, result.ScheduleAcceptance);
            Assert.Equal(GhScheduleFailureCode.SchedulePreconditionRejected, result.ScheduleFailureCode);
        }

        [Fact]
        public void Wire_MapsEveryEnumValueAndRejectsUndefinedValues()
        {
            var classifications = new Dictionary<GhScheduleClassification, string>
            {
                [GhScheduleClassification.SolveNotRequested] = "solve_not_requested",
                [GhScheduleClassification.RirDocumentUnregistered] = "rir_document_unregistered",
                [GhScheduleClassification.RirRegistrationUnknown] = "rir_registration_unknown",
                [GhScheduleClassification.GlobalSolverUnavailable] = "global_solver_unavailable",
                [GhScheduleClassification.RirMediatedScheduleRequested] = "rir_mediated_schedule_requested",
                [GhScheduleClassification.AsyncScheduleRequested] = "async_schedule_requested",
                [GhScheduleClassification.RirInstanceSolverStateUnknown] = "rir_instance_solver_state_unknown",
                [GhScheduleClassification.GlobalSolverStateUnknown] = "global_solver_state_unknown",
                [GhScheduleClassification.DocumentSolverDisabled] = "document_solver_disabled",
                [GhScheduleClassification.SolverStateUnknown] = "solver_state_unknown",
            };
            var acceptances = new Dictionary<GhScheduleAcceptance, string>
            {
                [GhScheduleAcceptance.NotAttempted] = "not_attempted",
                [GhScheduleAcceptance.Unavailable] = "unavailable",
                [GhScheduleAcceptance.Accepted] = "accepted",
                [GhScheduleAcceptance.Unknown] = "unknown",
            };
            var failures = new Dictionary<GhScheduleFailureCode, string>
            {
                [GhScheduleFailureCode.StandaloneSolverRestoreFailed] = "standalone_solver_restore_failed",
                [GhScheduleFailureCode.SchedulePreconditionRejected] = "schedule_precondition_rejected",
                [GhScheduleFailureCode.ScheduleApiUnavailable] = "schedule_api_unavailable",
                [GhScheduleFailureCode.ScheduleAcceptanceUnknown] = "schedule_acceptance_unknown",
            };
            var warnings = new Dictionary<GhScheduleWarning, string>
            {
                [GhScheduleWarning.CompletionUnverified] = "completion_unverified",
                [GhScheduleWarning.RegistrationUnknown] = "registration_unknown",
                [GhScheduleWarning.GlobalSolverStateUnknown] = "global_solver_state_unknown",
                [GhScheduleWarning.InstanceSolverStateUnknown] = "instance_solver_state_unknown",
                [GhScheduleWarning.ScheduleInvocationUnknown] = "schedule_invocation_unknown",
                [GhScheduleWarning.StandaloneRestoreFailed] = "standalone_restore_failed",
            };

            foreach (var pair in classifications) Assert.Equal(pair.Value, GhScheduleWire.ToWire(pair.Key));
            foreach (var pair in acceptances) Assert.Equal(pair.Value, GhScheduleWire.ToWire(pair.Key));
            foreach (var pair in failures) Assert.Equal(pair.Value, GhScheduleWire.ToWire(pair.Key));
            foreach (var pair in warnings) Assert.Equal(pair.Value, GhScheduleWire.ToWire(pair.Key));

            Assert.Equal("rir_mediated_schedule_requested", GhScheduleWire.ToWire(GhScheduleClassification.RirMediatedScheduleRequested));
            Assert.Equal("accepted", GhScheduleWire.ToWire(GhScheduleAcceptance.Accepted));
            Assert.Equal("schedule_acceptance_unknown", GhScheduleWire.ToWire(GhScheduleFailureCode.ScheduleAcceptanceUnknown));
            Assert.Throws<ArgumentOutOfRangeException>(() => GhScheduleWire.ToWire((GhScheduleClassification)999));
            Assert.Throws<ArgumentOutOfRangeException>(() => GhScheduleWire.ToWire((GhScheduleAcceptance)999));
            Assert.Throws<ArgumentOutOfRangeException>(() => GhScheduleWire.ToWire((GhScheduleFailureCode)999));
            Assert.Throws<ArgumentOutOfRangeException>(() => GhScheduleWire.ToWire((GhScheduleWarning)999));
        }

        private static GhScheduleDecision PermittedDecision() => new GhScheduleDecision
        {
            ScheduleClassification = GhScheduleClassification.AsyncScheduleRequested,
            AttemptSchedule = true,
            SolverStateKnown = true,
            Warnings = Array.Empty<GhScheduleWarning>(),
        };

        private sealed class NoScheduleDocument { }
        private sealed class ReturningDocument
        {
            public int CallCount { get; private set; }
            public int Delay { get; private set; }
            public void ScheduleSolution(int delayMs) { CallCount++; Delay = delayMs; }
        }
        private sealed class ThrowingDocument
        {
            public int CallCount { get; private set; }
            public int Delay { get; private set; }
            public bool ScheduleArmed { get; private set; }
            public void ScheduleSolution(int delayMs)
            {
                CallCount++;
                Delay = delayMs;
                ScheduleArmed = true;
                throw new InvalidOperationException("target entered");
            }
        }
        private class AmbiguousBaseDocument
        {
            public void ScheduleSolution(int delayMs) { }
        }
        private sealed class AmbiguousDocument : AmbiguousBaseDocument
        {
            public new void ScheduleSolution(int delayMs) { }
        }
    }
}
