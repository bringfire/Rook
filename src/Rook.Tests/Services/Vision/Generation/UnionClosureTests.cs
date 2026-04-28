using System;
using System.Linq;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Reflection-based subtype-closure enforcement. Sealed-record
    /// unions in C# are not language-enforced; the closed-set property
    /// is enforced by:
    /// <list type="number">
    ///   <item>Each abstract base record has a
    ///         <c>private protected</c> constructor, so external
    ///         assemblies cannot derive (only same-assembly +
    ///         derived-class can call the base ctor).</item>
    ///   <item>This test enumerates the actual concrete subtypes of
    ///         each union via reflection over the production assembly
    ///         and asserts the exact expected name set. If a future
    ///         change adds a subtype to the production assembly, this
    ///         test fails until the expected set is updated, forcing
    ///         a deliberate choice + downstream consumer review.</item>
    /// </list>
    /// </summary>
    public class UnionClosureTests
    {
        private static string[] ConcreteSubtypeNames(Type baseType)
        {
            // The production assembly references types whose runtime
            // dependencies aren't loaded in the test context (RhinoCommon,
            // WebView2 on net7.0). Assembly.GetTypes() throws
            // ReflectionTypeLoadException listing those; the loadable
            // types that DO resolve come back via ex.Types (with nulls
            // for the failures). Either path gives us the full set of
            // loadable types — which is sufficient for closure scanning
            // because every union subtype lives in a leaf namespace
            // with no Rhino/WebView2 dependencies of its own.
            Type[] types;
            try
            {
                types = baseType.Assembly.GetTypes();
            }
            catch (System.Reflection.ReflectionTypeLoadException ex)
            {
                types = ex.Types.Where(t => t is not null).Cast<Type>().ToArray();
            }

            return types
                .Where(t => !t.IsAbstract && baseType.IsAssignableFrom(t) && t != baseType)
                .Select(t => t.Name)
                .OrderBy(n => n, StringComparer.Ordinal)
                .ToArray();
        }

        [Fact]
        public void ProviderSubmitOutcome_subtypes_are_closed_to_known_set()
        {
            var actual = ConcreteSubtypeNames(typeof(ProviderSubmitOutcome));
            var expected = new[]
            {
                nameof(FailedSubmitOutcome),
                nameof(QueuedSubmitOutcome),
                nameof(SyncSubmitOutcome),
            };
            Assert.Equal(expected, actual);
        }

        [Fact]
        public void ProviderResultOutcome_subtypes_are_closed_to_known_set()
        {
            var actual = ConcreteSubtypeNames(typeof(ProviderResultOutcome));
            var expected = new[]
            {
                nameof(FailedResultOutcome),
                nameof(SuccessResultOutcome),
            };
            Assert.Equal(expected, actual);
        }

        [Fact]
        public void ProviderStatusOutcome_subtypes_are_closed_to_known_set()
        {
            var actual = ConcreteSubtypeNames(typeof(ProviderStatusOutcome));
            var expected = new[]
            {
                nameof(FailedStatusOutcome),
                nameof(InFlightStatusOutcome),
                nameof(ProviderCompleteStatusOutcome),
            };
            Assert.Equal(expected, actual);
        }

        [Fact]
        public void ProviderCancelOutcome_subtypes_are_closed_to_known_set()
        {
            var actual = ConcreteSubtypeNames(typeof(ProviderCancelOutcome));
            var expected = new[]
            {
                nameof(AlreadyTerminalOutcome),
                nameof(CanceledOutcome),
                nameof(FailedCancelOutcome),
            };
            Assert.Equal(expected, actual);
        }

        [Fact]
        public void ArtifactBody_subtypes_are_closed_to_known_set()
        {
            var actual = ConcreteSubtypeNames(typeof(ArtifactBody));
            var expected = new[]
            {
                nameof(InlineArtifactBody),
                nameof(RemoteArtifactBody),
            };
            Assert.Equal(expected, actual);
        }

        // The ctor-accessibility check below documents that external
        // derivation is structurally blocked. private protected is
        // only accessible to derived classes in the SAME assembly,
        // which is what closes the union from external code without
        // preventing same-assembly subtypes from existing.
        [Theory]
        [InlineData(typeof(ProviderSubmitOutcome))]
        [InlineData(typeof(ProviderResultOutcome))]
        [InlineData(typeof(ProviderStatusOutcome))]
        [InlineData(typeof(ProviderCancelOutcome))]
        [InlineData(typeof(ArtifactBody))]
        public void Union_base_has_no_publicly_accessible_constructor(Type baseType)
        {
            var publicCtors = baseType.GetConstructors(
                System.Reflection.BindingFlags.Instance |
                System.Reflection.BindingFlags.Public);
            Assert.Empty(publicCtors);
        }
    }
}
