using System.Collections.Generic;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// Produced by RevitPresetResolver, consumed by RevitExportService. Its presence is the single
    /// gate for preset-only decoration (summary + relationships); a null context = the raw path.
    /// </summary>
    internal sealed class RevitPresetContext
    {
        public string Preset { get; set; } = string.Empty;

        public BimExportOrganizationPolicy Policy { get; set; } = BimExportOrganizationPolicy.Legacy;

        public BimRoomsMode EffectiveRooms { get; set; } = BimRoomsMode.Both;

        public bool RoomsDriven { get; set; }

        public int LimitPerCategory { get; set; } = 1000;

        public List<string> EffectiveCategories { get; set; } = new List<string>();

        public List<RevitPresetCategoryCount> ResolvedCategories { get; set; } = new List<RevitPresetCategoryCount>();

        public List<RevitPresetWarning> Warnings { get; set; } = new List<RevitPresetWarning>();
    }

    internal sealed class RevitPresetCategoryCount
    {
        public string Category { get; set; } = string.Empty;

        public int Resolved { get; set; }

        public string Status { get; set; } = "resolved"; // resolved | unavailable
    }

    internal sealed class RevitPresetWarning
    {
        public string Code { get; set; } = string.Empty;

        public string Message { get; set; } = string.Empty;
    }
}
