using Eto.Forms;
using Xunit;

namespace Rook.Tests.UI
{
    /// <summary>
    /// Every test class that constructs Eto widgets joins this collection so xunit runs
    /// them serially. Eto's internal event lookup cache is a plain Dictionary; two
    /// classes constructing controls on parallel STA threads race on it
    /// ("An item with the same key has already been added").
    /// </summary>
    [CollectionDefinition(Name, DisableParallelization = true)]
    public sealed class EtoUiCollection
    {
        public const string Name = "Eto UI";
    }

    /// <summary>
    /// Process-wide, race-free Eto platform bootstrap for offline UI tests. xunit runs
    /// test classes in parallel; two classes constructing <see cref="Application"/> at
    /// once produce "The Eto.Forms Platform is already initialized" / "Cannot create
    /// more than one System.Windows.Application instance". Every UI test class must go
    /// through this gate instead of checking <c>Application.Instance == null</c> itself.
    /// </summary>
    internal static class EtoTestPlatform
    {
        private static readonly object Gate = new();

        public static void Ensure()
        {
            lock (Gate)
            {
                if (Application.Instance == null) _ = new Application(Eto.Platforms.Wpf);
            }
        }
    }
}
