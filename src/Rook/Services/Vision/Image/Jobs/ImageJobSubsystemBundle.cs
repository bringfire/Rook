using System;

namespace Rook.Services.Vision.Image.Jobs
{
    public sealed class ImageJobSubsystemBundle
    {
        public ImageJobSubsystemBundle(
            IImageJobManager manager, IImageProviderRegistry registry)
            : this(manager, registry, new ImageSubmissionExecutor(registry))
        {
        }
        public ImageJobSubsystemBundle(IImageJobManager manager, IImageProviderRegistry registry, ImageSubmissionExecutor executor)
        {
            Manager = manager ?? throw new ArgumentNullException(nameof(manager));
            Registry = registry ?? throw new ArgumentNullException(nameof(registry));
            Executor = executor ?? throw new ArgumentNullException(nameof(executor));
        }

        public IImageJobManager Manager { get; }
        public IImageProviderRegistry Registry { get; }
        public ImageSubmissionExecutor Executor { get; }
    }
}
