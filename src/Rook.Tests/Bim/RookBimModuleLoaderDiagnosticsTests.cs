using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Rook.Bim;
using Rook.Handlers;
using Rook.Tests.Bim.Diagnostics;
using Xunit;

namespace Rook.Tests.Bim
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class RookBimModuleLoaderDiagnosticsTests
    {
        private const string HostilePath =
            @"C:\private\Hostile Model.rvt\RookBim.dll";
        private const string HostileMessage =
            "Hostile Model.rvt at C:\\private\\Hostile Model.rvt";

        [Fact]
        public void TryActivateCore_NotFoundInitializesBeforeResolutionAndPreservesRegistryOutcome()
        {
            using var scope = BeginScope();
            var resolverSawActiveSession = false;

            var activated = RookBimModuleLoader.TryActivateCore(
                scope.Context,
                () =>
                {
                    resolverSawActiveSession = BimDiagnostics.SnapshotStatus().Enabled;
                    return new[] { HostilePath };
                },
                _ => false,
                _ => throw new InvalidOperationException("load must not run"),
                _ => throw new InvalidOperationException("activation must not run"));

            Assert.False(activated);
            Assert.True(resolverSawActiveSession);
            Assert.Equal("module-not-found", RookBimRuntimeRegistry.Source);
            Assert.IsType<RookBimUnavailableRuntime>(RookBimRuntimeRegistry.Current);
            AssertObservations(scope, new[]
            {
                Expected(BimDiagnosticStage.ModuleResolve, BimDiagnosticOutcome.Start),
                Expected(
                    BimDiagnosticStage.ModuleResolve,
                    BimDiagnosticOutcome.Failure,
                    BimDiagnosticDetailCode.None,
                    BimDiagnosticFailureImpact.Production),
            });
            AssertPrivateEvidenceAbsent(scope, HostilePath);
        }

        [Fact]
        public void TryActivateCore_LoadFailureIsDistinctAndPreservesRegistryOutcome()
        {
            using var scope = BeginScope();
            var exception = new BadImageFormatException(HostileMessage);

            var activated = RookBimModuleLoader.TryActivateCore(
                scope.Context,
                () => new[] { HostilePath },
                _ => true,
                _ => throw exception,
                _ => throw new InvalidOperationException("activation must not run"));

            Assert.False(activated);
            Assert.Equal("module-load-failed", RookBimRuntimeRegistry.Source);
            Assert.IsType<RookBimUnavailableRuntime>(RookBimRuntimeRegistry.Current);
            AssertObservations(scope, new[]
            {
                Expected(BimDiagnosticStage.ModuleResolve, BimDiagnosticOutcome.Start),
                Expected(BimDiagnosticStage.ModuleResolve, BimDiagnosticOutcome.Success),
                Expected(BimDiagnosticStage.ModuleLoad, BimDiagnosticOutcome.Start),
                Expected(
                    BimDiagnosticStage.ModuleLoad,
                    BimDiagnosticOutcome.Failure,
                    BimDiagnosticDetailCode.None,
                    BimDiagnosticFailureImpact.Production,
                    typeof(BadImageFormatException)),
            });
            AssertPrivateEvidenceAbsent(scope, HostilePath, HostileMessage);
        }

        [Fact]
        public void TryActivateCore_ActivationFailureIsDistinctAndPreservesRegistryOutcome()
        {
            using var scope = BeginScope();
            var exception = new TargetInvocationException(
                new InvalidOperationException(HostileMessage));

            var activated = RookBimModuleLoader.TryActivateCore(
                scope.Context,
                () => new[] { HostilePath },
                _ => true,
                _ => typeof(RookBimModuleLoader).Assembly,
                _ => throw exception);

            Assert.False(activated);
            Assert.Equal("module-load-failed", RookBimRuntimeRegistry.Source);
            Assert.IsType<RookBimUnavailableRuntime>(RookBimRuntimeRegistry.Current);
            AssertObservations(scope, new[]
            {
                Expected(BimDiagnosticStage.ModuleResolve, BimDiagnosticOutcome.Start),
                Expected(BimDiagnosticStage.ModuleResolve, BimDiagnosticOutcome.Success),
                Expected(BimDiagnosticStage.ModuleLoad, BimDiagnosticOutcome.Start),
                Expected(BimDiagnosticStage.ModuleLoad, BimDiagnosticOutcome.Success),
                Expected(BimDiagnosticStage.ModuleActivate, BimDiagnosticOutcome.Start),
                Expected(
                    BimDiagnosticStage.ModuleActivate,
                    BimDiagnosticOutcome.Failure,
                    BimDiagnosticDetailCode.None,
                    BimDiagnosticFailureImpact.Production,
                    typeof(InvalidOperationException)),
            });
            AssertPrivateEvidenceAbsent(scope, HostilePath, HostileMessage);
        }

        [Fact]
        public void TryActivateCore_SuccessRecordsEveryStageAndKeepsActivationInstall()
        {
            using var scope = BeginScope();
            var installed = new RookBimUnavailableRuntime(
                "test", "installed by reflected activation", "test");

            var activated = RookBimModuleLoader.TryActivateCore(
                scope.Context,
                () => new[] { HostilePath },
                _ => true,
                _ => typeof(RookBimModuleLoader).Assembly,
                _ => RookBimRuntimeRegistry.Install(installed, "activated-test"));

            Assert.True(activated);
            Assert.Equal("activated-test", RookBimRuntimeRegistry.Source);
            Assert.Same(installed, RookBimRuntimeRegistry.Current);
            AssertObservations(scope, new[]
            {
                Expected(BimDiagnosticStage.ModuleResolve, BimDiagnosticOutcome.Start),
                Expected(BimDiagnosticStage.ModuleResolve, BimDiagnosticOutcome.Success),
                Expected(BimDiagnosticStage.ModuleLoad, BimDiagnosticOutcome.Start),
                Expected(BimDiagnosticStage.ModuleLoad, BimDiagnosticOutcome.Success),
                Expected(BimDiagnosticStage.ModuleActivate, BimDiagnosticOutcome.Start),
                Expected(BimDiagnosticStage.ModuleActivate, BimDiagnosticOutcome.Success),
            });
            AssertPrivateEvidenceAbsent(scope, HostilePath);
        }

        [Fact]
        public void TryActivateCore_AlreadyInstalledObservesClosedDetailWithoutResolution()
        {
            using var scope = BeginScope();
            var installed = new RookBimUnavailableRuntime(
                "test", "already installed", "test");
            RookBimRuntimeRegistry.Install(installed, "already-installed-test");
            var resolverCalls = 0;

            var activated = RookBimModuleLoader.TryActivateCore(
                scope.Context,
                () =>
                {
                    resolverCalls++;
                    return new[] { HostilePath };
                },
                _ => true,
                _ => typeof(RookBimModuleLoader).Assembly,
                _ => throw new InvalidOperationException("activation must not run"));

            Assert.False(activated);
            Assert.Equal(0, resolverCalls);
            Assert.Equal("already-installed-test", RookBimRuntimeRegistry.Source);
            Assert.Same(installed, RookBimRuntimeRegistry.Current);
            AssertObservations(scope, new[]
            {
                Expected(
                    BimDiagnosticStage.ModuleActivate,
                    BimDiagnosticOutcome.Success,
                    BimDiagnosticDetailCode.AlreadyInitialized),
            });
        }

        [Fact]
        public void TryActivateCore_AlreadyAttemptedObservesClosedDetailWithoutRerunningActivation()
        {
            using var scope = BeginScope();
            var activationCalls = 0;
            var dependencies = new ActivationDependencies(
                () => new[] { HostilePath },
                _ => true,
                _ => typeof(RookBimModuleLoader).Assembly,
                _ => activationCalls++);

            Assert.True(Invoke(scope.Context, dependencies));
            RookBimRuntimeRegistry.ResetForTests();
            var envelopeCount = scope.Sink.Envelopes.Count;

            Assert.False(Invoke(scope.Context, dependencies));

            Assert.Equal(1, activationCalls);
            Assert.Equal("core-fallback", RookBimRuntimeRegistry.Source);
            var observation = Assert.Single(scope.Sink.Envelopes.Skip(envelopeCount));
            AssertExpected(
                observation,
                Expected(
                    BimDiagnosticStage.ModuleActivate,
                    BimDiagnosticOutcome.Success,
                    BimDiagnosticDetailCode.AlreadyInitialized));
        }

        [Fact]
        public void Dispatch_PassesTheAcceptedContextToModuleActivation()
        {
            using var scope = BeginScope();
            RookBimRuntimeRegistry.Install(
                new RookBimUnavailableRuntime(
                    "test", "already installed", "test"),
                "already-installed-test");

            var response = new BimHandler(() => true)
                .Dispatch("{\"op\":\"active_document\"}");

            var responseDiagnostics = JsonSerializer.SerializeToElement(
                response.Diagnostic);
            var correlationId = responseDiagnostics
                .GetProperty("correlationId")
                .GetString();
            var activation = Assert.Single(scope.Sink.Envelopes, envelope =>
                envelope.Stage == BimDiagnosticStage.ModuleActivate);
            var terminal = Assert.Single(scope.Sink.Envelopes, envelope =>
                envelope.Kind == BimDiagnosticRecordKind.Terminal);

            Assert.False(string.IsNullOrWhiteSpace(correlationId));
            Assert.Equal(correlationId, activation.CorrelationId);
            Assert.Equal(correlationId, terminal.CorrelationId);
            Assert.Equal(BimDiagnosticOutcome.Success, activation.Outcome);
            Assert.Equal(BimDiagnosticDetailCode.AlreadyInitialized,
                activation.Fields.DetailCode);
        }

        private static LoaderTestScope BeginScope()
        {
            RookBimRuntimeRegistry.ResetForTests();
            RookBimModuleLoader.ResetForTests();
            return new LoaderTestScope(TestDiagnostics.EnabledScope("status"));
        }

        private static bool Invoke(
            BimDiagnosticContext context,
            ActivationDependencies dependencies)
        {
            return RookBimModuleLoader.TryActivateCore(
                context,
                dependencies.ResolveCandidates,
                dependencies.FileExists,
                dependencies.LoadAssembly,
                dependencies.Activate);
        }

        private static void AssertObservations(
            LoaderTestScope scope,
            IReadOnlyList<ExpectedObservation> expected)
        {
            Assert.Equal(expected.Count, scope.Sink.Envelopes.Count);
            for (var index = 0; index < expected.Count; index++)
            {
                AssertExpected(scope.Sink.Envelopes[index], expected[index]);
            }
        }

        private static void AssertExpected(
            BimDiagnosticEnvelope actual,
            ExpectedObservation expected)
        {
            Assert.Equal(expected.Stage, actual.Stage);
            Assert.Equal(expected.Outcome, actual.Outcome);
            Assert.Equal(expected.DetailCode, actual.Fields.DetailCode);
            Assert.Equal(expected.FailureImpact, actual.Fields.FailureImpact);
            Assert.Equal(expected.ExceptionType?.FullName, actual.ExceptionTypeName);
        }

        private static void AssertPrivateEvidenceAbsent(
            LoaderTestScope scope,
            params string[] forbidden)
        {
            foreach (var envelope in scope.Sink.Envelopes)
            {
                var record = new BimDiagnosticRecord(
                    envelope,
                    TestDiagnostics.Snapshot(scope.Context),
                    "core-version",
                    "core-commit",
                    "module-version",
                    "module-commit");
                var encoded = Assert.IsType<string>(
                    BimDiagnosticJsonEncoder.Encode(record));
                foreach (var value in forbidden)
                {
                    Assert.DoesNotContain(value, encoded, StringComparison.Ordinal);
                }
            }
        }

        private static ExpectedObservation Expected(
            BimDiagnosticStage stage,
            BimDiagnosticOutcome outcome,
            BimDiagnosticDetailCode detailCode = BimDiagnosticDetailCode.None,
            BimDiagnosticFailureImpact failureImpact =
                BimDiagnosticFailureImpact.None,
            Type? exceptionType = null)
        {
            return new ExpectedObservation(
                stage, outcome, detailCode, failureImpact, exceptionType);
        }

        private sealed class ActivationDependencies
        {
            internal ActivationDependencies(
                Func<IReadOnlyList<string>> resolveCandidates,
                Func<string, bool> fileExists,
                Func<string, Assembly> loadAssembly,
                Action<Assembly> activate)
            {
                ResolveCandidates = resolveCandidates;
                FileExists = fileExists;
                LoadAssembly = loadAssembly;
                Activate = activate;
            }

            internal Func<IReadOnlyList<string>> ResolveCandidates { get; }
            internal Func<string, bool> FileExists { get; }
            internal Func<string, Assembly> LoadAssembly { get; }
            internal Action<Assembly> Activate { get; }
        }

        private sealed class LoaderTestScope : IDisposable
        {
            private readonly TestDiagnosticScope diagnostics;

            internal LoaderTestScope(TestDiagnosticScope diagnostics)
            {
                this.diagnostics = diagnostics;
            }

            internal BimDiagnosticContext Context
            {
                get { return diagnostics.Context; }
            }

            internal InMemoryBimDiagnosticEnvelopeSink Sink
            {
                get { return diagnostics.Sink; }
            }

            public void Dispose()
            {
                diagnostics.Dispose();
                RookBimModuleLoader.ResetForTests();
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        private sealed class ExpectedObservation
        {
            internal ExpectedObservation(
                BimDiagnosticStage stage,
                BimDiagnosticOutcome outcome,
                BimDiagnosticDetailCode detailCode,
                BimDiagnosticFailureImpact failureImpact,
                Type? exceptionType)
            {
                Stage = stage;
                Outcome = outcome;
                DetailCode = detailCode;
                FailureImpact = failureImpact;
                ExceptionType = exceptionType;
            }

            internal BimDiagnosticStage Stage { get; }
            internal BimDiagnosticOutcome Outcome { get; }
            internal BimDiagnosticDetailCode DetailCode { get; }
            internal BimDiagnosticFailureImpact FailureImpact { get; }
            internal Type? ExceptionType { get; }
        }
    }
}
