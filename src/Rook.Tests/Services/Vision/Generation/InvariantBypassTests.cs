using System;
using System.Linq;
using System.Reflection;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Reflection-based proofs that invariant-bearing types in the
    /// Generation namespace cannot have their invariants bypassed via
    /// <c>with</c> expressions or object initializers.
    ///
    /// <para>The mechanism is: every public instance property on these
    /// types must be read-only (no <c>set</c> and no <c>init</c>). If
    /// a future change adds an <c>init</c> setter, this test fails —
    /// <c>with</c> would let callers create instances that bypass
    /// constructor validation (e.g. a valid <see cref="CostEstimate"/>
    /// cloned with <c>Min = -1m</c>).</para>
    ///
    /// <para>The list of types covers everything that performs
    /// constructor-time validation. Pure-data types without invariants
    /// (e.g. <c>GenerationError</c>, <c>MediaRefKind</c>) are
    /// intentionally excluded — they have nothing to bypass.</para>
    /// </summary>
    public class InvariantBypassTests
    {
        public static System.Collections.Generic.IEnumerable<object[]> InvariantTypes() =>
            new[]
            {
                new object[] { typeof(CostEstimate) },
                new object[] { typeof(JobPricing) },
                new object[] { typeof(ProviderJobHandle) },
                new object[] { typeof(ResultArtifact) },
                new object[] { typeof(ProviderResultEnvelope) },
                new object[] { typeof(ResolvedMedia) },
                new object[] { typeof(GenerationProgress) },
                new object[] { typeof(RemoteArtifactBody) },
                new object[] { typeof(InlineArtifactBody) },
                new object[] { typeof(SyncSubmitOutcome) },
                new object[] { typeof(QueuedSubmitOutcome) },
                new object[] { typeof(FailedSubmitOutcome) },
                new object[] { typeof(SuccessResultOutcome) },
                new object[] { typeof(FailedResultOutcome) },
                new object[] { typeof(InFlightStatusOutcome) },
                new object[] { typeof(ProviderCompleteStatusOutcome) },
                new object[] { typeof(FailedStatusOutcome) },
                new object[] { typeof(AlreadyTerminalOutcome) },
                new object[] { typeof(FailedCancelOutcome) },
            };

        [Theory]
        [MemberData(nameof(InvariantTypes))]
        public void Type_has_no_init_setters_on_public_instance_properties(Type type)
        {
            var properties = type.GetProperties(
                BindingFlags.Public | BindingFlags.Instance);

            foreach (var prop in properties)
            {
                var setter = prop.SetMethod;
                if (setter is null) continue;     // read-only, fine

                // An init setter shows up as a regular setter whose
                // return parameter has IsExternalInit modifier.
                var isInit = setter.ReturnParameter.GetRequiredCustomModifiers()
                    .Any(t => t.FullName == "System.Runtime.CompilerServices.IsExternalInit");

                Assert.False(
                    isInit,
                    $"{type.Name}.{prop.Name} has an init setter. " +
                    "Invariant-bearing types must use read-only properties so " +
                    "`with` expressions and object initializers cannot bypass " +
                    "constructor validation.");

                Assert.False(
                    setter.IsPublic,
                    $"{type.Name}.{prop.Name} has a public setter. " +
                    "Invariant-bearing types must be construction-only.");
            }
        }

        [Theory]
        [MemberData(nameof(InvariantTypes))]
        public void Type_is_not_a_record(Type type)
        {
            // Records compile to classes that have:
            //   - a public Clone method named "<Clone>$"
            //   - a property called EqualityContract
            // Either is a sufficient signal. We check for EqualityContract
            // because Clone uses an angle-bracket name not directly
            // expressible as a string literal in some build chains.
            var equalityContract = type.GetProperty(
                "EqualityContract",
                BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

            Assert.True(
                equalityContract is null,
                $"{type.Name} appears to be a record (has EqualityContract). " +
                "Invariant-bearing types must be non-record sealed classes — " +
                "records expose init setters and a protected copy constructor " +
                "that defeat construction-only validation.");
        }
    }
}
