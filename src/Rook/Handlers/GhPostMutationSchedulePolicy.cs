using System;

namespace Rook.Handlers
{
    internal enum GhScheduleClassification
    {
        SolveNotRequested, RirDocumentUnregistered, RirRegistrationUnknown,
        GlobalSolverUnavailable, RirMediatedScheduleRequested, AsyncScheduleRequested,
        RirInstanceSolverStateUnknown, GlobalSolverStateUnknown, DocumentSolverDisabled,
        SolverStateUnknown,
    }

    internal enum GhScheduleWarning
    {
        CompletionUnverified, RegistrationUnknown, GlobalSolverStateUnknown,
        InstanceSolverStateUnknown, ScheduleInvocationUnknown, StandaloneRestoreFailed,
    }

    internal enum GhScheduleAcceptance { NotAttempted, Unavailable, Accepted, Unknown }

    internal enum GhScheduleFailureCode
    {
        StandaloneSolverRestoreFailed,
        SchedulePreconditionRejected,
        ScheduleApiUnavailable,
        ScheduleAcceptanceUnknown,
    }

    internal readonly struct GhScheduleInputs
    {
        public bool SolveRequested { get; init; }
        public bool RunningAsRhinoInside { get; init; }
        public bool RegistrationKnown { get; init; }
        public bool DocumentRegistered { get; init; }
        public bool? GlobalEnableSolutions { get; init; }
        public bool? DocumentEnabled { get; init; }
    }

    internal readonly struct GhScheduleDecision
    {
        public GhScheduleClassification ScheduleClassification { get; init; }
        public bool AttemptSchedule { get; init; }
        public bool VerificationDeferred { get; init; }
        public bool SolverLocked { get; init; }
        public bool SolverStateKnown { get; init; }
        public GhScheduleWarning[] Warnings { get; init; }
    }

    internal readonly struct GhScheduleResult
    {
        public GhScheduleClassification ScheduleClassification { get; init; }
        public GhScheduleAcceptance ScheduleAcceptance { get; init; }
        public GhScheduleFailureCode? ScheduleFailureCode { get; init; }
        public bool VerificationDeferred { get; init; }
        public bool SolverLocked { get; init; }
        public bool SolverStateKnown { get; init; }
        public string? ExceptionType { get; init; }
        public GhScheduleWarning[] Warnings { get; init; }
        public bool SolveScheduled => ScheduleAcceptance == GhScheduleAcceptance.Accepted;
    }

    internal readonly struct GhSolverRestoreResult
    {
        public bool Attempted { get; init; }
        public bool Succeeded { get; init; }
        public GhScheduleFailureCode? FailureCode { get; init; }
        public bool? ObservedDocumentEnabled { get; init; }
    }

    internal static class GhPostMutationSchedulePolicy
    {
        public static GhScheduleDecision Decide(GhScheduleInputs inputs)
        {
            var solverStateKnown = IsSolverStateKnown(inputs.GlobalEnableSolutions, inputs.DocumentEnabled);
            if (!inputs.SolveRequested)
                return Decision(GhScheduleClassification.SolveNotRequested, false, false, false, solverStateKnown);

            if (inputs.RunningAsRhinoInside)
            {
                if (!inputs.RegistrationKnown)
                    return Decision(GhScheduleClassification.RirRegistrationUnknown, false, true, false, solverStateKnown, GhScheduleWarning.RegistrationUnknown);
                if (!inputs.DocumentRegistered)
                    return Decision(GhScheduleClassification.RirDocumentUnregistered, false, false, false, solverStateKnown);
                if (inputs.GlobalEnableSolutions == false)
                    return Decision(GhScheduleClassification.GlobalSolverUnavailable, false, true, false, true);
                if (!inputs.GlobalEnableSolutions.HasValue)
                    return Decision(GhScheduleClassification.GlobalSolverStateUnknown, true, true, false, false, GhScheduleWarning.GlobalSolverStateUnknown);
                if (inputs.DocumentEnabled == false)
                    return Decision(GhScheduleClassification.RirMediatedScheduleRequested, true, true, false, true);
                if (!inputs.DocumentEnabled.HasValue)
                    return Decision(GhScheduleClassification.RirInstanceSolverStateUnknown, true, true, false, false, GhScheduleWarning.InstanceSolverStateUnknown);
                return Decision(GhScheduleClassification.AsyncScheduleRequested, true, true, false, true);
            }

            if (inputs.GlobalEnableSolutions == false)
                return Decision(GhScheduleClassification.GlobalSolverUnavailable, false, false, false, true);
            if (inputs.DocumentEnabled == false)
                return Decision(GhScheduleClassification.DocumentSolverDisabled, false, true, true, true);
            if (inputs.GlobalEnableSolutions == true && inputs.DocumentEnabled == true)
                return Decision(GhScheduleClassification.AsyncScheduleRequested, true, false, false, true);
            return Decision(GhScheduleClassification.SolverStateUnknown, true, true, false, false, GhScheduleWarning.GlobalSolverStateUnknown);
        }

        private static bool IsSolverStateKnown(bool? global, bool? document) =>
            global == false || document == false || (global == true && document == true);

        private static GhScheduleDecision Decision(GhScheduleClassification classification, bool attemptSchedule, bool verificationDeferred, bool solverLocked, bool solverStateKnown, params GhScheduleWarning[] warnings) =>
            new GhScheduleDecision
            {
                ScheduleClassification = classification,
                AttemptSchedule = attemptSchedule,
                VerificationDeferred = verificationDeferred,
                SolverLocked = solverLocked,
                SolverStateKnown = solverStateKnown,
                Warnings = warnings ?? Array.Empty<GhScheduleWarning>(),
            };
    }

    internal static class GhScheduleWire
    {
        public static string ToWire(GhScheduleClassification value) => value switch
        {
            GhScheduleClassification.SolveNotRequested => "solve_not_requested", GhScheduleClassification.RirDocumentUnregistered => "rir_document_unregistered", GhScheduleClassification.RirRegistrationUnknown => "rir_registration_unknown", GhScheduleClassification.GlobalSolverUnavailable => "global_solver_unavailable", GhScheduleClassification.RirMediatedScheduleRequested => "rir_mediated_schedule_requested", GhScheduleClassification.AsyncScheduleRequested => "async_schedule_requested", GhScheduleClassification.RirInstanceSolverStateUnknown => "rir_instance_solver_state_unknown", GhScheduleClassification.GlobalSolverStateUnknown => "global_solver_state_unknown", GhScheduleClassification.DocumentSolverDisabled => "document_solver_disabled", GhScheduleClassification.SolverStateUnknown => "solver_state_unknown", _ => throw new ArgumentOutOfRangeException(nameof(value), value, null),
        };

        public static string ToWire(GhScheduleAcceptance value) => value switch
        {
            GhScheduleAcceptance.NotAttempted => "not_attempted", GhScheduleAcceptance.Unavailable => "unavailable", GhScheduleAcceptance.Accepted => "accepted", GhScheduleAcceptance.Unknown => "unknown", _ => throw new ArgumentOutOfRangeException(nameof(value), value, null),
        };

        public static string ToWire(GhScheduleFailureCode value) => value switch
        {
            GhScheduleFailureCode.StandaloneSolverRestoreFailed => "standalone_solver_restore_failed", GhScheduleFailureCode.SchedulePreconditionRejected => "schedule_precondition_rejected", GhScheduleFailureCode.ScheduleApiUnavailable => "schedule_api_unavailable", GhScheduleFailureCode.ScheduleAcceptanceUnknown => "schedule_acceptance_unknown", _ => throw new ArgumentOutOfRangeException(nameof(value), value, null),
        };

        public static string ToWire(GhScheduleWarning value) => value switch
        {
            GhScheduleWarning.CompletionUnverified => "completion_unverified", GhScheduleWarning.RegistrationUnknown => "registration_unknown", GhScheduleWarning.GlobalSolverStateUnknown => "global_solver_state_unknown", GhScheduleWarning.InstanceSolverStateUnknown => "instance_solver_state_unknown", GhScheduleWarning.ScheduleInvocationUnknown => "schedule_invocation_unknown", GhScheduleWarning.StandaloneRestoreFailed => "standalone_restore_failed", _ => throw new ArgumentOutOfRangeException(nameof(value), value, null),
        };
    }
}
