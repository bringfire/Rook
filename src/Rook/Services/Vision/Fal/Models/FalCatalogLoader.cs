using System.Collections.Generic;
using System.IO;

namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalCatalogLoader
    {
        public FalCatalogLoadResult Load(string companionAssemblyDirectory, IReadOnlyCollection<string> reservedModelIds)
            => new FalCatalogCompiler().Compile(Path.Combine(companionAssemblyDirectory, "vision-models", "fal"), reservedModelIds);
    }
}
