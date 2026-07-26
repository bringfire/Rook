using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;
using System.Threading;
using Rook.Bim;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Bim.Diagnostics
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimDiagnosticsConfigurationTests
    {
        public static IEnumerable<object[]> DisabledValues()
        {
            yield return new object[] { null! };
            yield return new object[] { string.Empty };
            yield return new object[] { "true" };
            yield return new object[] { "TRUE" };
            yield return new object[] { "01" };
            yield return new object[] { "1 " };
            yield return new object[] { " 1" };
        }

        [Theory]
        [MemberData(nameof(DisabledValues))]
        public void Initialize_OnlyExactOrdinalOneEnablesAndReadsOnce(
            string? initialValue)
        {
            var reads = 0;
            var sinkCreations = 0;
            var suppliedValue = initialValue;
            var bootstrap = new BimDiagnosticBootstrap(
                name =>
                {
                    Assert.Equal("ROOK_BIM_DIAGNOSTICS", name);
                    reads++;
                    return suppliedValue;
                },
                provenance =>
                {
                    sinkCreations++;
                    return new RecordingSink();
                },
                CreateAssembly("CoreDisabled", new Version(1, 2, 3, 4),
                    "1.2.3+abc123"));

            var first = bootstrap.Initialize();
            suppliedValue = "1";
            var second = bootstrap.Initialize();

            Assert.Same(first, second);
            Assert.Equal(1, reads);
            Assert.Equal(0, sinkCreations);
            Assert.False(first.CreateContext("status").Enabled);
            var status = bootstrap.SnapshotStatus();
            Assert.False(status.Enabled);
            Assert.Equal(BimDiagnosticSinkState.Disabled, status.SinkState);
        }

        [Fact]
        public void Initialize_ExactOneCreatesOneEnabledSessionAndNeverRereads()
        {
            var reads = 0;
            var sinkCreations = 0;
            var suppliedValue = "1";
            var sink = new RecordingSink();
            var bootstrap = new BimDiagnosticBootstrap(
                _ =>
                {
                    reads++;
                    return suppliedValue;
                },
                _ =>
                {
                    sinkCreations++;
                    return sink;
                },
                CreateAssembly("CoreEnabled", new Version(2, 3, 4, 5),
                    "2.3.4+ABCDEF09"));

            var first = bootstrap.Initialize();
            suppliedValue = null!;
            var second = bootstrap.Initialize();

            Assert.Same(first, second);
            Assert.Equal(1, reads);
            Assert.Equal(1, sinkCreations);
            var context = first.CreateContext("status");
            Assert.True(context.Enabled);
            Assert.NotNull(context.CorrelationId);
            Assert.Collection(
                sink.Envelopes,
                envelope =>
                {
                    Assert.Equal(BimDiagnosticStage.CoreInitialize,
                        envelope.Stage);
                    Assert.Equal(BimDiagnosticOutcome.Start, envelope.Outcome);
                },
                envelope =>
                {
                    Assert.Equal(BimDiagnosticStage.CoreInitialize,
                        envelope.Stage);
                    Assert.Equal(BimDiagnosticOutcome.Success, envelope.Outcome);
                });
        }

        [Fact]
        public void Provenance_IsImmediateBoundedAndModuleRegistrationIsAtomic()
        {
            var reads = 0;
            var sinkCreations = 0;
            var bootstrap = new BimDiagnosticBootstrap(
                _ =>
                {
                    reads++;
                    return "1";
                },
                _ =>
                {
                    sinkCreations++;
                    return new RecordingSink();
                },
                CreateAssembly("KnownCore", new Version(5, 6, 7, 8),
                    "5.6.7+deadBEEF"));

            var beforeInitialize = bootstrap.SnapshotStatus();
            Assert.Equal("5.6.7.8", beforeInitialize.CoreVersion);
            Assert.Equal("deadBEEF", beforeInitialize.CoreCommit);
            Assert.Equal("unavailable", beforeInitialize.ModuleVersion);
            Assert.Equal("unavailable", beforeInitialize.ModuleCommit);

            bootstrap.Initialize();
            bootstrap.RegisterModuleMetadata(CreateAssembly(
                "KnownModule", new Version(9, 10, 11, 12),
                "9.10.11+c0ffee"));
            var registered = bootstrap.SnapshotStatus();

            Assert.Equal("9.10.11.12", registered.ModuleVersion);
            Assert.Equal("c0ffee", registered.ModuleCommit);
            Assert.Equal(1, reads);
            Assert.Equal(1, sinkCreations);

            bootstrap.RegisterModuleMetadata(CreateAssembly(
                "BoundedModule", new Version(10, 0, 0, 0),
                "10.0.0+" + new string('a', 256)));
            Assert.Equal(128,
                bootstrap.SnapshotStatus().ModuleCommit.Length);
            Assert.Equal(1, reads);
            Assert.Equal(1, sinkCreations);
        }

        [Fact]
        public void ModuleProvenance_ConcurrentRegistrationNeverPublishesMixedFields()
        {
            var bootstrap = new BimDiagnosticBootstrap(
                _ => null,
                _ => throw new InvalidOperationException("disabled factory"),
                CreateAssembly("AtomicCore", new Version(1, 0, 0, 0),
                    "1.0.0+abc123"));
            bootstrap.Initialize();
            var first = CreateAssembly(
                "AtomicModuleA", new Version(2, 0, 0, 0), "2.0.0+aaaa");
            var second = CreateAssembly(
                "AtomicModuleB", new Version(3, 0, 0, 0), "3.0.0+bbbb");
            using var start = new ManualResetEventSlim(false);
            var remaining = 2;
            var firstWriter = new Thread(() =>
            {
                start.Wait();
                for (var index = 0; index < 1000; index++)
                {
                    bootstrap.RegisterModuleMetadata(first);
                }

                Interlocked.Decrement(ref remaining);
            }) { IsBackground = true };
            var secondWriter = new Thread(() =>
            {
                start.Wait();
                for (var index = 0; index < 1000; index++)
                {
                    bootstrap.RegisterModuleMetadata(second);
                }

                Interlocked.Decrement(ref remaining);
            }) { IsBackground = true };
            firstWriter.Start();
            secondWriter.Start();
            start.Set();

            while (Volatile.Read(ref remaining) != 0)
            {
                var status = bootstrap.SnapshotStatus();
                var unavailable = status.ModuleVersion == "unavailable" &&
                    status.ModuleCommit == "unavailable";
                var firstPair = status.ModuleVersion == "2.0.0.0" &&
                    status.ModuleCommit == "aaaa";
                var secondPair = status.ModuleVersion == "3.0.0.0" &&
                    status.ModuleCommit == "bbbb";
                Assert.True(unavailable || firstPair || secondPair,
                    "module provenance exposed fields from different registrations");
            }

            Assert.True(firstWriter.Join(TimeSpan.FromSeconds(5)));
            Assert.True(secondWriter.Join(TimeSpan.FromSeconds(5)));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("1.2.3")]
        [InlineData("1.2.3+not-hex")]
        [InlineData("1.2.3+abc_123")]
        public void Provenance_NonHexOrAbsentInformationalSuffixIsUnavailable(
            string? informationalVersion)
        {
            var core = CreateAssembly("CoreNonHex", new Version(3, 2, 1, 0),
                informationalVersion);
            var bootstrap = new BimDiagnosticBootstrap(
                _ => null,
                _ => throw new InvalidOperationException("must not create sink"),
                core);

            var status = bootstrap.SnapshotStatus();

            Assert.Equal("3.2.1.0", status.CoreVersion);
            Assert.Equal("unavailable", status.CoreCommit);
        }

        [Fact]
        public void CreateUncorrelatedContext_IsEnabledIndependentAndNeverTerminal()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);

            var first = session.CreateUncorrelatedContext("pre_parse");
            var second = session.CreateUncorrelatedContext("pre_parse");
            session.Observe(first, BimDiagnosticStage.HandlerDeserialize,
                BimDiagnosticOutcome.Start, BimDiagnosticFields.None);
            session.CompleteRequest(first, BimDiagnosticOutcome.Failure);

            Assert.True(first.Enabled);
            Assert.Null(first.CorrelationId);
            Assert.NotNull(first.Accumulator);
            Assert.NotSame(first.Accumulator, second.Accumulator);
            var envelope = Assert.Single(sink.Envelopes);
            Assert.Equal(BimDiagnosticRecordKind.Milestone, envelope.Kind);
            Assert.DoesNotContain(sink.Envelopes,
                item => item.Kind == BimDiagnosticRecordKind.Terminal);
        }

        [Fact]
        public void Facade_ContainsInvalidInputsAndPublishesPublicSnapshots()
        {
            var replacement = new BimDiagnosticSession(
                true, new ThrowingDisposableSink());
            using (BimDiagnostics.PushSessionForTests(replacement))
            {
                var context = BimDiagnostics.CreateContext("status");

                BimDiagnostics.Observe(context,
                    (BimDiagnosticStage)int.MaxValue,
                    BimDiagnosticOutcome.Start,
                    BimDiagnosticFields.None);
                BimDiagnostics.ObserveException(context,
                    BimDiagnosticStage.HandlerRuntime,
                    new InvalidOperationException("private"),
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.None,
                        null,
                        BimDiagnosticFailureImpact.Production));
                BimDiagnostics.CompleteRequest(context,
                    (BimDiagnosticOutcome)int.MaxValue);
                BimDiagnostics.RegisterModuleMetadata(null!);

                BimDiagnosticRequestSnapshot request =
                    BimDiagnostics.SnapshotRequest(context);
                BimDiagnosticStatusSnapshot status =
                    BimDiagnostics.SnapshotStatus();
                Assert.NotNull(request);
                Assert.NotNull(status);
                Assert.True(status.Enabled);
                Assert.Equal(1, request.RequestDroppedCount);
                Assert.Equal(BimDiagnosticStage.HandlerRuntime,
                    request.FirstFailureStage);
                Assert.False(BimDiagnostics.CreateContext(string.Empty).Enabled);
            }
        }

        [Fact]
        public void PushSessionForTests_RestoresPreviousAndStopsReplacement()
        {
            var outerSink = new DisposableSink();
            var innerSink = new DisposableSink();
            var outer = new BimDiagnosticSession(true, outerSink);
            var inner = new BimDiagnosticSession(false, innerSink);

            using (BimDiagnostics.PushSessionForTests(outer))
            {
                Assert.True(BimDiagnostics.CreateContext("outer").Enabled);
                using (BimDiagnostics.PushSessionForTests(inner))
                {
                    Assert.False(BimDiagnostics.CreateContext("inner").Enabled);
                }

                Assert.True(innerSink.Disposed);
                Assert.True(BimDiagnostics.CreateContext("outer_again").Enabled);
            }

            Assert.True(outerSink.Disposed);
        }

        private static Assembly CreateAssembly(
            string prefix,
            Version version,
            string? informationalVersion)
        {
            var name = new AssemblyName(prefix + Guid.NewGuid().ToString("N"))
            {
                Version = version
            };
            var assembly = AssemblyBuilder.DefineDynamicAssembly(
                name, AssemblyBuilderAccess.Run);
            if (informationalVersion != null)
            {
                var constructor = typeof(AssemblyInformationalVersionAttribute)
                    .GetConstructor(new[] { typeof(string) })!;
                assembly.SetCustomAttribute(new CustomAttributeBuilder(
                    constructor, new object[] { informationalVersion }));
            }

            return assembly;
        }

        private sealed class RecordingSink : IBimDiagnosticEnvelopeSink
        {
            private readonly List<BimDiagnosticEnvelope> envelopes =
                new List<BimDiagnosticEnvelope>();

            internal IReadOnlyList<BimDiagnosticEnvelope> Envelopes =>
                envelopes.ToArray();

            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                envelopes.Add(envelope);
                return true;
            }
        }

        private sealed class DisposableSink :
            IBimDiagnosticEnvelopeSink, IDisposable
        {
            internal bool Disposed { get; private set; }

            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                return true;
            }

            public void Dispose()
            {
                Disposed = true;
            }
        }

        private sealed class ThrowingDisposableSink :
            IBimDiagnosticEnvelopeSink, IDisposable
        {
            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                throw new InvalidOperationException("diagnostic-only failure");
            }

            public void Dispose()
            {
            }
        }
    }
}
