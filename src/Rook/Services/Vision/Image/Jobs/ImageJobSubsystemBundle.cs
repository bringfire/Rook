using System;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobSubsystemBundle
    {
        public ImageJobSubsystemBundle(
            IImageJobManager manager, IImageProviderRegistry registry)
        {
            Manager = manager ?? throw new ArgumentNullException(nameof(manager));
            Registry = registry ?? throw new ArgumentNullException(nameof(registry));
        }

        public IImageJobManager Manager { get; }
        public IImageProviderRegistry Registry { get; }
    }
}
