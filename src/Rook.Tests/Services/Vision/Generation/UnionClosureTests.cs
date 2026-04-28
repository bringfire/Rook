using System;
using System.Linq;
using System.Reflection;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Closure enforcement for the discriminated unions. C# records
    /// auto-generate a <c>protected</c> copy constructor for non-sealed
    /// records, which is reachable from external derived records — that
    /// loophole defeats <c>private protected</c> on the parameterless
    /// ctor. Phase 1 PR-1 review pass 4 forced the conversion to
    /// <c>abstract class</c> + <c>sealed class</c> hierarchies, which
    /// have no compiler-generated copy constructor and a real
    /// <c>private protected</c> closure.
    ///
    /// <para>This test file enforces the closure structurally and the
    /// subtype set by reflection. Adding a leaf in this assembly fails
    /// the subtype-set test until the expected list is updated.
    /// External-assembly derivation is structurally blocked because:
    /// <list type="number">
    ///   <item>The bases are non-record classes — no compiler-generated
    ///         protected copy constructor exists.</item>
    ///   <item>The only base constructor is <c>private protected</c>,
    ///         requiring same-assembly + derived-class context.</item>
    /// </list></para>
    /// </summary>
    public class UnionClosureTests
    {
        private static string[] ConcreteSubtypeNames(Type baseType)
        {
            // Production assembly references types whose runtime
            // dependencies aren't loaded in the test context
            // (RhinoCommon, WebView2 on net7.0). GetTypes throws
            // ReflectionTypeLoadException; ex.Types contains the
            // loadable subset, sufficient for closure scanning since
            // every union subtype lives in a leaf namespace with no
            // Rhino/WebView2 dependencies.
            Type[] types;
            try
            {
                types = baseType.Assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException ex)
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

        // Each base must have exactly one constructor, declared
        // private protected. No compiler-generated protected copy
        // constructor (which a record would have for non-sealed bases).
        [Theory]
        [InlineData(typeof(ProviderSubmitOutcome))]
        [InlineData(typeof(ProviderResultOutcome))]
        [InlineData(typeof(ProviderStatusOutcome))]
        [InlineData(typeof(ProviderCancelOutcome))]
        [InlineData(typeof(ArtifactBody))]
        public void Union_base_has_only_a_private_protected_parameterless_ctor(Type baseType)
        {
            // None public:
            var publicCtors = baseType.GetConstructors(
                BindingFlags.Instance | BindingFlags.Public);
            Assert.Empty(publicCtors);

            // No purely-protected ctors either — that would be the
            // record copy-ctor leak this test exists to catch.
            var allCtors = baseType.GetConstructors(
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            foreach (var ctor in allCtors)
            {
                // private protected = IsFamilyAndAssembly. protected =
                // IsFamily. The latter is the leak vector.
                Assert.False(
                    ctor.IsFamily,
                    $"{baseType.Name} has a protected (not private protected) " +
                    $"constructor: {ctor}. This is the record copy-ctor leak " +
                    "that lets external assemblies derive. The base must be a " +
                    "non-record class, or the copy ctor must be private protected.");
            }

            // And exactly one private-protected parameterless ctor:
            var ppCtors = allCtors.Where(c => c.IsFamilyAndAssembly).ToArray();
            Assert.Single(ppCtors);
            Assert.Empty(ppCtors[0].GetParameters());
        }

        // Every leaf is sealed — pattern-matching consumers can rely on
        // exhaustive type discrimination and there is no further
        // hierarchy to consider.
        [Theory]
        [InlineData(typeof(ProviderSubmitOutcome))]
        [InlineData(typeof(ProviderResultOutcome))]
        [InlineData(typeof(ProviderStatusOutcome))]
        [InlineData(typeof(ProviderCancelOutcome))]
        [InlineData(typeof(ArtifactBody))]
        public void Union_leaves_are_sealed(Type baseType)
        {
            Type[] types;
            try { types = baseType.Assembly.GetTypes(); }
            catch (ReflectionTypeLoadException ex)
            {
                types = ex.Types.Where(t => t is not null).Cast<Type>().ToArray();
            }
            var leaves = types
                .Where(t => !t.IsAbstract && baseType.IsAssignableFrom(t) && t != baseType);
            foreach (var leaf in leaves)
            {
                Assert.True(leaf.IsSealed, $"{leaf.Name} must be sealed.");
            }
        }
    }
}
