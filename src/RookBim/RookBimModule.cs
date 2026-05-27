using Rook.Bim;
using RookBim.Revit;

namespace RookBim
{
    public static class RookBimModule
    {
        public static void Activate()
        {
            RookBimRuntimeRegistry.Install(new RevitRookBimRuntime(), "RookBim.dll");
        }
    }
}
