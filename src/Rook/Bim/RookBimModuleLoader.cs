using System;
using System.IO;
using System.Reflection;

namespace Rook.Bim
{
    public static class RookBimModuleLoader
    {
        private static readonly object SyncRoot = new object();
        private static bool attempted;

        public static bool TryActivate()
        {
            lock (SyncRoot)
            {
                if (attempted)
                {
                    return false;
                }

                attempted = true;
            }

            var modulePath = Path.Combine(AppContext.BaseDirectory, "RookBim.dll");
            if (!File.Exists(modulePath))
            {
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
            catch
            {
                RookBimRuntimeRegistry.Install(
                    new RookBimUnavailableRuntime(
                        "rookbim_unavailable",
                        "RookBIM module failed to activate."),
                    "module-load-failed");
                return false;
            }
        }
    }
}
