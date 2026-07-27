using System;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GhPostMutationSchedulePolicyTests
    {
        public static TheoryData<object, object, bool, bool, bool, bool> PolicyRows => new()
        {
            { Input(false, false, true, true, true, true), GhScheduleClassification.SolveNotRequested, false, false, false, true },
            { Input(true, true, true, false, true, true), GhScheduleClassification.RirDocumentUnregistered, false, false, false, true },
            { Input(true, true, false, false, true, true), GhScheduleClassification.RirRegistrationUnknown, false, true, false, true },
            { Input(true, true, true, true, false, true), GhScheduleClassification.GlobalSolverUnavailable, false, true, false, true },
            { Input(true, true, true, true, true, false), GhScheduleClassification.RirMediatedScheduleRequested, true, true, false, true },
            { Input(true, true, true, true, true, true), GhScheduleClassification.AsyncScheduleRequested, true, true, false, true },
            { Input(true, true, true, true, true, null), GhScheduleClassification.RirInstanceSolverStateUnknown, true, true, false, false },
            { Input(true, true, true, true, null, false), GhScheduleClassification.GlobalSolverStateUnknown, true, true, false, false },
            { Input(true, false, true, true, false, true), GhScheduleClassification.GlobalSolverUnavailable, false, false, false, true },
            { Input(true, false, true, true, true, false), GhScheduleClassification.DocumentSolverDisabled, false, true, true, true },
            { Input(true, false, true, true, true, true), GhScheduleClassification.AsyncScheduleRequested, true, false, false, true },
            { Input(true, false, true, true, null, false), GhScheduleClassification.DocumentSolverDisabled, false, true, true, true },
            { Input(true, false, true, true, null, true), GhScheduleClassification.SolverStateUnknown, true, true, false, false },
            { Input(true, false, true, true, null, null), GhScheduleClassification.SolverStateUnknown, true, true, false, false },
            { Input(true, false, true, true, true, null), GhScheduleClassification.SolverStateUnknown, true, true, false, false },
        };

        [Theory]
        [MemberData(nameof(PolicyRows))]
        public void Decide_MapsEveryPolicyRow(
            object input,
            object expectedClassification,
            bool attemptSchedule,
            bool verificationDeferred,
            bool solverLocked,
            bool solverStateKnown)
        {
            var decision = GhPostMutationSchedulePolicy.Decide((GhScheduleInputs)input);

            Assert.Equal((GhScheduleClassification)expectedClassification, decision.ScheduleClassification);
            Assert.Equal(attemptSchedule, decision.AttemptSchedule);
            Assert.Equal(verificationDeferred, decision.VerificationDeferred);
            Assert.Equal(solverLocked, decision.SolverLocked);
            Assert.Equal(solverStateKnown, decision.SolverStateKnown);
        }

        [Fact]
        public void Decide_RirTemporaryGlobalFalseThenTrue_DoesNotMutateInputFlags()
        {
            var temporarilyDisabled = Input(true, true, true, true, false, false);
            var restored = Input(true, true, true, true, true, false);

            var unavailable = GhPostMutationSchedulePolicy.Decide(temporarilyDisabled);
            var mediated = GhPostMutationSchedulePolicy.Decide(restored);

            Assert.Equal(GhScheduleClassification.GlobalSolverUnavailable, unavailable.ScheduleClassification);
            Assert.Equal(GhScheduleClassification.RirMediatedScheduleRequested, mediated.ScheduleClassification);
            Assert.False(temporarilyDisabled.GlobalEnableSolutions!.Value);
            Assert.False(temporarilyDisabled.DocumentEnabled!.Value);
            Assert.True(restored.GlobalEnableSolutions!.Value);
            Assert.False(restored.DocumentEnabled!.Value);
        }

        private static GhScheduleInputs Input(bool solveRequested, bool rir, bool registrationKnown, bool registered, bool? global, bool? document) =>
            new GhScheduleInputs
            {
                SolveRequested = solveRequested,
                RunningAsRhinoInside = rir,
                RegistrationKnown = registrationKnown,
                DocumentRegistered = registered,
                GlobalEnableSolutions = global,
                DocumentEnabled = document,
            };
    }
}
