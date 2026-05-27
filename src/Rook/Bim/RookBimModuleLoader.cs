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

        public static bool TryActivate()
        {
            lock (SyncRoot)
            {
                if (!string.Equals(RookBimRuntimeRegistry.Source, "core-fallback", StringComparison.Ordinal))
                {
                    return false;
                }

                if (attempted)
                {
                    return false;
                }

                attempted = true;
            }

            var candidates = ResolveCandidateModulePaths();
            var modulePath = candidates.FirstOrDefault(File.Exists);
            if (modulePath == null)
            {
                RookBimRuntimeRegistry.Install(
                    new RookBimUnavailableRuntime(
                        "rookbim_unavailable",
                        "RookBIM module was not found. Searched: " + string.Join("; ", candidates),
                        "module-loader"),
                    "module-not-found");
                return false;
            }

            try
            {
                var assembly = Assembly.LoadFrom(modulePath);
                var moduleType = assembly.GetType("RookBim.RookBimModule", throwOnError: true);
                var activate = moduleType.GetMethod(
                    "Activate",
                    BindingFlags.Public | BindingFlags.Static,
                    binder: null,
                    types: Type.EmptyTypes,
                    modifiers: null);

                if (activate == null)
                {
                    throw new MissingMethodException("RookBim.RookBimModule", "Activate");
                }

                activate.Invoke(null, null);
                return true;
            }
            catch (Exception ex)
            {
                var root = ex is TargetInvocationException target && target.InnerException != null
                    ? target.InnerException
                    : ex;
                RookBimRuntimeRegistry.Install(
                    new RookBimUnavailableRuntime(
                        "rookbim_unavailable",
                        $"RookBIM module failed to activate from '{modulePath}': {root.GetType().Name}: {root.Message}",
                        "module-loader"),
                    "module-load-failed");
                return false;
            }
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
