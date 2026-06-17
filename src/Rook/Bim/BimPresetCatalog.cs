using System;
using System.Collections.Generic;

namespace Rook.Bim
{
    public static class BimPresetCatalog
    {
        private static readonly Dictionary<string, BimPresetDefinition> Presets =
            new Dictionary<string, BimPresetDefinition>(StringComparer.OrdinalIgnoreCase)
            {
                ["architectural_shell"] = new BimPresetDefinition
                {
                    Name = "architectural_shell",
                    Categories = new[]
                    {
                        "Walls", "Floors", "Roofs", "Ceilings",
                        "Curtain Walls", "Curtain Panels", "Curtain Wall Mullions", "Columns",
                    },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                },
                ["interiors"] = new BimPresetDefinition
                {
                    Name = "interiors",
                    Categories = new[]
                    {
                        "Furniture", "Furniture Systems", "Casework", "Specialty Equipment",
                        "Plumbing Fixtures", "Lighting Fixtures", "Generic Models",
                    },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                },
                ["openings_and_hosts"] = new BimPresetDefinition
                {
                    Name = "openings_and_hosts",
                    Categories = new[] { "Doors", "Windows" },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                },
                ["structural"] = new BimPresetDefinition
                {
                    Name = "structural",
                    // Revit commonly represents structural slabs as the Floors category; Floors are
                    // intentionally left to architectural_shell to avoid double-owning the category.
                    Categories = new[] { "Structural Columns", "Structural Framing", "Structural Foundations" },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Exclude,
                },
                ["rooms_and_spaces"] = new BimPresetDefinition
                {
                    Name = "rooms_and_spaces",
                    Categories = Array.Empty<string>(),
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                    RoomsDriven = true,
                },
                ["calibration_fixture"] = new BimPresetDefinition
                {
                    Name = "calibration_fixture",
                    Categories = new[]
                    {
                        "Walls", "Floors", "Roofs", "Ceilings", "Columns",
                        "Doors", "Windows",
                        "Structural Columns", "Structural Framing",
                        "Furniture", "Casework",
                    },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Full,
                    DefaultRooms = BimRoomsMode.Both,
                },
            };

        public static IReadOnlyList<string> Names
        {
            get { return new List<string>(Presets.Keys); }
        }

        public static bool TryGet(string? preset, out BimPresetDefinition definition)
        {
            if (!string.IsNullOrWhiteSpace(preset) && Presets.TryGetValue(preset!, out var found))
            {
                definition = found;
                return true;
            }

            definition = new BimPresetDefinition();
            return false;
        }
    }
}
