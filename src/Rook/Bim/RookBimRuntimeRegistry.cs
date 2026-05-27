using System;

namespace Rook.Bim
{
    public static class RookBimRuntimeRegistry
    {
        private static readonly object SyncRoot = new object();
        private static IRookBimRuntime current = CreateFallback();
        private static string source = "core-fallback";

        public static IRookBimRuntime Current
        {
            get
            {
                lock (SyncRoot)
                {
                    return current;
                }
            }
        }

        public static string Source
        {
            get
            {
                lock (SyncRoot)
                {
                    return source;
                }
            }
        }

        public static void Install(IRookBimRuntime runtime, string source)
        {
            if (runtime == null)
            {
                throw new ArgumentNullException(nameof(runtime));
            }

            if (string.IsNullOrWhiteSpace(source))
            {
                throw new ArgumentException("Runtime source is required.", nameof(source));
            }

            lock (SyncRoot)
            {
                current = runtime;
                RookBimRuntimeRegistry.source = source;
            }
        }

        internal static void ResetForTests()
        {
            lock (SyncRoot)
            {
                current = CreateFallback();
                source = "core-fallback";
            }
        }

        private static IRookBimRuntime CreateFallback()
        {
            return new RookBimUnavailableRuntime(
                "rookbim_unavailable",
                "RookBIM runtime is unavailable.");
        }
    }
}
