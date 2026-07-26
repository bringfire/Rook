using Rook.Bim;
using RookBim.Revit;
using System;
using System.Linq;

namespace RookBim
{
    public static class RookBimModule
    {
        public static void Activate()
        {
            BimDiagnostics.RegisterModuleMetadata(typeof(RookBimModule).Assembly);

            if (!IsLoaded("RevitAPIUI") || !IsLoaded("RhinoInside.Revit"))
            {
                RookBimRuntimeRegistry.Install(
                    new RookBimUnavailableRuntime(
                        "not_rhino_inside",
                        "RookBIM requires RhinoInside.Revit and RevitAPIUI to be loaded.",
                        "RookBim.dll"),
                    "RookBim.dll");
                return;
            }

            RookBimRuntimeRegistry.Install(new RevitRookBimRuntime(), "RookBim.dll");
        }

        private static bool IsLoaded(string assemblyName)
        {
            return AppDomain.CurrentDomain
                .GetAssemblies()
                .Any(assembly =>
                    string.Equals(
                        assembly.GetName().Name,
                        assemblyName,
                        StringComparison.OrdinalIgnoreCase));
        }
    }
}
