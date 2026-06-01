using Xunit;

namespace Rook.Tests.Bim
{
    [CollectionDefinition(Name, DisableParallelization = true)]
    public sealed class RookBimRuntimeRegistryCollection
    {
        public const string Name = "RookBimRuntimeRegistry";
    }
}
