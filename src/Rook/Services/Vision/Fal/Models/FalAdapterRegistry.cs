using System;
namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalAdapterRegistry
    {
        public IFalModelAdapter Resolve(string adapterId, int adapterVersion)
        {
            if (adapterVersion == 1)
            {
                if (adapterId == "fal.image.declarative") return new FalDeclarativeImageAdapter();
                if (adapterId == "fal.video.declarative") return new FalDeclarativeVideoAdapter();
            }
            throw new NotSupportedException("Unsupported fal adapter and version: " + adapterId + "/" + adapterVersion);
        }
    }
}
