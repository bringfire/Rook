using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportOrganizationPolicyTests
    {
        [Fact]
        public void Legacy_IsFlatNoNameMinimal()
        {
            var p = BimExportOrganizationPolicy.Legacy;
            Assert.Equal(BimLayerScheme.Flat, p.LayerScheme);
            Assert.Equal(BimNameScheme.None, p.NameScheme);
            Assert.Equal(BimMetadataProfile.Minimal, p.MetadataProfile);
        }

        [Theory]
        [InlineData("by_category", BimLayerScheme.ByCategory)]
        [InlineData("by_level_then_category", BimLayerScheme.ByLevelThenCategory)]
        [InlineData("flat", BimLayerScheme.Flat)]
        public void TryParseLayer_ParsesKnownSchemes(string raw, BimLayerScheme expected)
        {
            Assert.True(BimExportOrganizationPolicy.TryParseLayer(raw, out var scheme));
            Assert.Equal(expected, scheme);
        }

        [Fact]
        public void TryParseLayer_RejectsUnknown()
        {
            Assert.False(BimExportOrganizationPolicy.TryParseLayer("spiral", out _));
        }

        [Theory]
        [InlineData("readable_with_id", BimNameScheme.ReadableWithId)]
        [InlineData("type_only", BimNameScheme.TypeOnly)]
        [InlineData("revit_name", BimNameScheme.RevitName)]
        [InlineData("none", BimNameScheme.None)]
        public void TryParseName_ParsesKnownSchemes(string raw, BimNameScheme expected)
        {
            Assert.True(BimExportOrganizationPolicy.TryParseName(raw, out var scheme));
            Assert.Equal(expected, scheme);
        }

        [Theory]
        [InlineData("minimal", BimMetadataProfile.Minimal)]
        [InlineData("standard", BimMetadataProfile.Standard)]
        [InlineData("full", BimMetadataProfile.Full)]
        public void TryParseProfile_ParsesKnownProfiles(string raw, BimMetadataProfile expected)
        {
            Assert.True(BimExportOrganizationPolicy.TryParseProfile(raw, out var profile));
            Assert.Equal(expected, profile);
        }

        [Fact]
        public void WireHelpers_EmitWireFormatNotEnumNames()
        {
            Assert.Equal("flat", BimExportOrganizationPolicy.LayerToWire(BimLayerScheme.Flat));
            Assert.Equal("by_category", BimExportOrganizationPolicy.LayerToWire(BimLayerScheme.ByCategory));
            Assert.Equal("by_level_then_category", BimExportOrganizationPolicy.LayerToWire(BimLayerScheme.ByLevelThenCategory));
            Assert.Equal("readable_with_id", BimExportOrganizationPolicy.NameToWire(BimNameScheme.ReadableWithId));
            Assert.Equal("type_only", BimExportOrganizationPolicy.NameToWire(BimNameScheme.TypeOnly));
            Assert.Equal("none", BimExportOrganizationPolicy.NameToWire(BimNameScheme.None));
            Assert.Equal("standard", BimExportOrganizationPolicy.ProfileToWire(BimMetadataProfile.Standard));
            Assert.Equal("full", BimExportOrganizationPolicy.ProfileToWire(BimMetadataProfile.Full));
            Assert.Equal("both", BimExportOrganizationPolicy.RoomsToWire(BimRoomsMode.Both));
            Assert.Equal("labels_only", BimExportOrganizationPolicy.RoomsToWire(BimRoomsMode.LabelsOnly));
            Assert.Equal("exclude", BimExportOrganizationPolicy.RoomsToWire(BimRoomsMode.Exclude));
        }

        [Fact]
        public void Resolve_UsesPresetDefaultsWhenNoOverrides()
        {
            var def = new BimPresetDefinition
            {
                DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                DefaultNameScheme = BimNameScheme.ReadableWithId,
                DefaultMetadataProfile = BimMetadataProfile.Full,
            };
            var result = BimExportOrganizationPolicy.Resolve(def, null, null, null, out var policy);
            Assert.True(result.Success);
            Assert.Equal(BimLayerScheme.ByLevelThenCategory, policy.LayerScheme);
            Assert.Equal(BimNameScheme.ReadableWithId, policy.NameScheme);
            Assert.Equal(BimMetadataProfile.Full, policy.MetadataProfile);
        }

        [Fact]
        public void Resolve_AppliesOverrides()
        {
            var def = new BimPresetDefinition
            {
                DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                DefaultNameScheme = BimNameScheme.ReadableWithId,
                DefaultMetadataProfile = BimMetadataProfile.Standard,
            };
            var result = BimExportOrganizationPolicy.Resolve(def, "by_category", "type_only", "minimal", out var policy);
            Assert.True(result.Success);
            Assert.Equal(BimLayerScheme.ByCategory, policy.LayerScheme);
            Assert.Equal(BimNameScheme.TypeOnly, policy.NameScheme);
            Assert.Equal(BimMetadataProfile.Minimal, policy.MetadataProfile);
        }

        [Fact]
        public void Resolve_RejectsBadOverrideWithInvalidScope()
        {
            var def = new BimPresetDefinition();
            var result = BimExportOrganizationPolicy.Resolve(def, "spiral", null, null, out _);
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }
    }
}
