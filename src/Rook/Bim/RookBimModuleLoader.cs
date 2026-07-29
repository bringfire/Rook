using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;

namespace Rook.Bim
{
    public static class RookBimModuleLoader
    {
        private const string ModuleFileName = "RookBim.dll";
        private static readonly object SyncRoot = new object();
        private static bool attempted;

        public static bool TryActivate(BimDiagnosticContext diagnostics)
        {
            BimDiagnostics.InitializeFromEnvironment();
            return TryActivateCoreInitialized(
                diagnostics,
                ResolveCandidateModulePaths,
                File.Exists,
                Assembly.LoadFrom,
                ActivateAssembly);
        }

        internal static bool TryActivateCore(
            BimDiagnosticContext diagnostics,
            Func<IReadOnlyList<string>> candidateResolver,
            Func<string, bool> fileExists,
            Func<string, Assembly> assemblyLoader,
            Action<Assembly> reflectedActivation)
        {
            BimDiagnostics.InitializeFromEnvironment();
            return TryActivateCoreInitialized(
                diagnostics,
                candidateResolver,
                fileExists,
                assemblyLoader,
                reflectedActivation);
        }

        private static bool TryActivateCoreInitialized(
            BimDiagnosticContext diagnostics,
            Func<IReadOnlyList<string>> candidateResolver,
            Func<string, bool> fileExists,
            Func<string, Assembly> assemblyLoader,
            Action<Assembly> reflectedActivation)
        {
            var alreadyInitialized = false;
            lock (SyncRoot)
            {
                if (!string.Equals(RookBimRuntimeRegistry.Source, "core-fallback", StringComparison.Ordinal))
                {
                    alreadyInitialized = true;
                }
                else if (attempted)
                {
                    alreadyInitialized = true;
                }
                else
                {
                    attempted = true;
                }
            }

            if (alreadyInitialized)
            {
                BimDiagnostics.Observe(
                    diagnostics,
                    BimDiagnosticStage.ModuleActivate,
                    BimDiagnosticOutcome.Success,
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.AlreadyInitialized,
                        null,
                        BimDiagnosticFailureImpact.None));
                return false;
            }

            IReadOnlyList<string> candidates;
            string? modulePath;
            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.ModuleResolve,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            try
            {
                candidates = candidateResolver();
                modulePath = candidates.FirstOrDefault(fileExists);
            }
            catch (Exception ex)
            {
                BimDiagnostics.ObserveException(
                    diagnostics,
                    BimDiagnosticStage.ModuleResolve,
                    ex,
                    ProductionFailure());
                throw;
            }

            if (modulePath == null)
            {
                BimDiagnostics.Observe(
                    diagnostics,
                    BimDiagnosticStage.ModuleResolve,
                    BimDiagnosticOutcome.Failure,
                    ProductionFailure());
                RookBimRuntimeRegistry.Install(
                    new RookBimUnavailableRuntime(
                        "rookbim_unavailable",
                        "RookBIM module was not found. Searched: " + string.Join("; ", candidates),
                        "module-loader"),
                    "module-not-found");
                return false;
            }

            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.ModuleResolve,
                BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None);

            Assembly assembly;
            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.ModuleLoad,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            try
            {
                assembly = assemblyLoader(modulePath);
            }
            catch (Exception ex)
            {
                BimDiagnostics.ObserveException(
                    diagnostics,
                    BimDiagnosticStage.ModuleLoad,
                    ex,
                    ProductionFailure());
                InstallLoadFailure(modulePath, ex);
                return false;
            }

            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.ModuleLoad,
                BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None);

            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.ModuleActivate,
                BimDiagnosticOutcome.Start,
                BimDiagnosticFields.None);
            try
            {
                reflectedActivation(assembly);
            }
            catch (Exception ex)
            {
                var root = UnwrapInvocationException(ex);
                BimDiagnostics.ObserveException(
                    diagnostics,
                    BimDiagnosticStage.ModuleActivate,
                    root,
                    ProductionFailure());
                InstallLoadFailure(modulePath, ex);
                return false;
            }

            BimDiagnostics.Observe(
                diagnostics,
                BimDiagnosticStage.ModuleActivate,
                BimDiagnosticOutcome.Success,
                BimDiagnosticFields.None);
            return true;
        }

        internal static void ResetForTests()
        {
            lock (SyncRoot)
            {
                attempted = false;
            }
        }

        private static void ActivateAssembly(Assembly assembly)
        {
            var moduleType = assembly.GetType(
                "RookBim.RookBimModule", throwOnError: true);
            var activate = moduleType.GetMethod(
                "Activate",
                BindingFlags.Public | BindingFlags.Static,
                binder: null,
                types: Type.EmptyTypes,
                modifiers: null);

            if (activate == null)
            {
                throw new MissingMethodException(
                    "RookBim.RookBimModule", "Activate");
            }

            activate.Invoke(null, null);
        }

        private static void InstallLoadFailure(string modulePath, Exception exception)
        {
            var root = UnwrapInvocationException(exception);
            RookBimRuntimeRegistry.Install(
                new RookBimUnavailableRuntime(
                    "rookbim_unavailable",
                    $"RookBIM module failed to activate from '{modulePath}': {root.GetType().Name}: {root.Message}",
                    "module-loader"),
                "module-load-failed");
        }

        private static Exception UnwrapInvocationException(Exception exception)
        {
            return exception is TargetInvocationException target &&
                target.InnerException != null
                ? target.InnerException
                : exception;
        }

        private static BimDiagnosticFields ProductionFailure()
        {
            return new BimDiagnosticFields(
                BimDiagnosticDetailCode.None,
                null,
                BimDiagnosticFailureImpact.Production);
        }

        internal static IReadOnlyList<string> ResolveCandidateModulePathsForTests()
        {
            return ResolveCandidateModulePaths();
        }

        private static IReadOnlyList<string> ResolveCandidateModulePaths()
        {
            var paths = new List<string>();

            AddCandidateFromAssemblyLocation(paths, typeof(RookBimModuleLoader).Assembly.Location);
            AddCandidateFromDirectory(paths, AppContext.BaseDirectory);
            AddCandidateFromDirectory(paths, AppDomain.CurrentDomain.BaseDirectory);

            return paths;
        }

        private static void AddCandidateFromAssemblyLocation(List<string> paths, string? assemblyLocation)
        {
            if (string.IsNullOrWhiteSpace(assemblyLocation))
            {
                return;
            }

            AddCandidateFromDirectory(paths, Path.GetDirectoryName(assemblyLocation));
        }

        private static void AddCandidateFromDirectory(List<string> paths, string? directory)
        {
            if (string.IsNullOrWhiteSpace(directory))
            {
                return;
            }

            var path = Path.Combine(directory!, ModuleFileName);
            if (!paths.Any(existing => string.Equals(existing, path, StringComparison.OrdinalIgnoreCase)))
            {
                paths.Add(path);
            }
        }
    }
}
