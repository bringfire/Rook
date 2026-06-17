using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimPresetCatalogTests
    {
        [Theory]
        [InlineData("architectural_shell")]
        [InlineData("interiors")]
        [InlineData("openings_and_hosts")]
        [InlineData("structural")]
        [InlineData("rooms_and_spaces")]
        [InlineData("calibration_fixture")]
        public void TryGet_ResolvesEveryDocumentedPreset(string preset)
        {
            Assert.True(BimPresetCatalog.TryGet(preset, out var def));
            Assert.Equal(preset, def.Name);
        }

        [Fact]
        public void TryGet_IsCaseInsensitive()
        {
            Assert.True(BimPresetCatalog.TryGet("Architectural_Shell", out _));
        }

        [Fact]
        public void TryGet_RejectsUnknownPreset()
        {
            Assert.False(BimPresetCatalog.TryGet("kitchen_sink", out _));
        }

        [Fact]
        public void ArchitecturalShell_HasCategoriesAndByLevelLayers()
        {
            BimPresetCatalog.TryGet("architectural_shell", out var def);
            Assert.Contains("Walls", def.Categories);
            Assert.Contains("Floors", def.Categories);
            Assert.Equal(BimLayerScheme.ByLevelThenCategory, def.DefaultLayerScheme);
            Assert.Equal(BimMetadataProfile.Standard, def.DefaultMetadataProfile);
            Assert.False(def.RoomsDriven);
        }

        [Fact]
        public void RoomsAndSpaces_IsRoomsDrivenWithNoCategories()
        {
            BimPresetCatalog.TryGet("rooms_and_spaces", out var def);
            Assert.Empty(def.Categories);
            Assert.True(def.RoomsDriven);
            Assert.Equal(BimRoomsMode.Both, def.DefaultRooms);
        }

        [Fact]
        public void Structural_ExcludesFloorsAndRooms()
        {
            BimPresetCatalog.TryGet("structural", out var def);
            Assert.DoesNotContain("Floors", def.Categories);
            Assert.Contains("Structural Framing", def.Categories);
            Assert.Equal(BimRoomsMode.Exclude, def.DefaultRooms);
        }

        [Fact]
        public void CalibrationFixture_IsBroadAndFullProfile()
        {
            BimPresetCatalog.TryGet("calibration_fixture", out var def);
            Assert.Contains("Doors", def.Categories);
            Assert.Contains("Windows", def.Categories);
            Assert.Contains("Furniture", def.Categories);
            Assert.Equal(BimMetadataProfile.Full, def.DefaultMetadataProfile);
            Assert.Equal(BimRoomsMode.Both, def.DefaultRooms);
        }

        [Fact]
        public void Names_ListsAllPresets()
        {
            Assert.Equal(6, BimPresetCatalog.Names.Count);
        }

        [Theory]
        [InlineData("architectural_shell")]
        [InlineData("interiors")]
        [InlineData("openings_and_hosts")]
        [InlineData("structural")]
        [InlineData("rooms_and_spaces")]
        [InlineData("calibration_fixture")]
        public void EveryPreset_DefaultsToReadableWithIdNames(string preset)
        {
            // Spec default namePolicy = readable_with_id; only the raw export path (Legacy policy)
            // opts back to None. A preset defaulting to None would emit unnamed Rhino objects.
            BimPresetCatalog.TryGet(preset, out var def);
            Assert.Equal(BimNameScheme.ReadableWithId, def.DefaultNameScheme);
        }
    }
}
