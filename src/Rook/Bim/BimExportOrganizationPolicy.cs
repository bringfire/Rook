using System;

namespace Rook.Bim
{
    public sealed class BimExportOrganizationPolicy
    {
        public BimLayerScheme LayerScheme { get; set; } = BimLayerScheme.Flat;

        public BimNameScheme NameScheme { get; set; } = BimNameScheme.None;

        public BimMetadataProfile MetadataProfile { get; set; } = BimMetadataProfile.Minimal;

        // The raw rookbim_export_elements path uses Legacy so its output stays semantically identical:
        // flat RookBim::Model layer, the four user strings, no object names.
        public static BimExportOrganizationPolicy Legacy
        {
            get
            {
                return new BimExportOrganizationPolicy
                {
                    LayerScheme = BimLayerScheme.Flat,
                    NameScheme = BimNameScheme.None,
                    MetadataProfile = BimMetadataProfile.Minimal,
                };
            }
        }

        public static bool TryParseLayer(string? raw, out BimLayerScheme scheme)
        {
            switch ((raw ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "flat": scheme = BimLayerScheme.Flat; return true;
                case "by_category": scheme = BimLayerScheme.ByCategory; return true;
                case "by_level_then_category": scheme = BimLayerScheme.ByLevelThenCategory; return true;
                default: scheme = BimLayerScheme.Flat; return false;
            }
        }

        public static bool TryParseName(string? raw, out BimNameScheme scheme)
        {
            switch ((raw ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "none": scheme = BimNameScheme.None; return true;
                case "revit_name": scheme = BimNameScheme.RevitName; return true;
                case "type_only": scheme = BimNameScheme.TypeOnly; return true;
                case "readable": scheme = BimNameScheme.Readable; return true;
                case "readable_with_id": scheme = BimNameScheme.ReadableWithId; return true;
                default: scheme = BimNameScheme.None; return false;
            }
        }

        public static bool TryParseProfile(string? raw, out BimMetadataProfile profile)
        {
            switch ((raw ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "minimal": profile = BimMetadataProfile.Minimal; return true;
                case "standard": profile = BimMetadataProfile.Standard; return true;
                case "full": profile = BimMetadataProfile.Full; return true;
                default: profile = BimMetadataProfile.Standard; return false;
            }
        }

        // Wire-format serializers — the SINGLE source for every policy echo (summary/sidecar/
        // validation). Emits the request's wire vocabulary, never the C# enum name.
        public static string LayerToWire(BimLayerScheme scheme)
        {
            switch (scheme)
            {
                case BimLayerScheme.ByCategory: return "by_category";
                case BimLayerScheme.ByLevelThenCategory: return "by_level_then_category";
                default: return "flat";
            }
        }

        public static string NameToWire(BimNameScheme scheme)
        {
            switch (scheme)
            {
                case BimNameScheme.RevitName: return "revit_name";
                case BimNameScheme.TypeOnly: return "type_only";
                case BimNameScheme.Readable: return "readable";
                case BimNameScheme.ReadableWithId: return "readable_with_id";
                default: return "none";
            }
        }

        public static string ProfileToWire(BimMetadataProfile profile)
        {
            switch (profile)
            {
                case BimMetadataProfile.Standard: return "standard";
                case BimMetadataProfile.Full: return "full";
                default: return "minimal";
            }
        }

        public static string RoomsToWire(BimRoomsMode rooms)
        {
            switch (rooms)
            {
                case BimRoomsMode.LabelsOnly: return "labels_only";
                case BimRoomsMode.Exclude: return "exclude";
                default: return "both";
            }
        }

        public static BimValidationResult Resolve(
            BimPresetDefinition definition,
            string? layerOverride,
            string? nameOverride,
            string? profileOverride,
            out BimExportOrganizationPolicy policy)
        {
            var layer = definition.DefaultLayerScheme;
            var name = definition.DefaultNameScheme;
            var profile = definition.DefaultMetadataProfile;

            if (!string.IsNullOrWhiteSpace(layerOverride))
            {
                if (!TryParseLayer(layerOverride, out layer))
                {
                    return Bad("layerPolicy", layerOverride!, out policy);
                }
            }

            if (!string.IsNullOrWhiteSpace(nameOverride))
            {
                if (!TryParseName(nameOverride, out name))
                {
                    return Bad("namePolicy", nameOverride!, out policy);
                }
            }

            if (!string.IsNullOrWhiteSpace(profileOverride))
            {
                if (!TryParseProfile(profileOverride, out profile))
                {
                    return Bad("metadataProfile", profileOverride!, out policy);
                }
            }

            policy = new BimExportOrganizationPolicy
            {
                LayerScheme = layer,
                NameScheme = name,
                MetadataProfile = profile,
            };
            return BimValidationResult.Ok;
        }

        private static BimValidationResult Bad(string field, string value, out BimExportOrganizationPolicy policy)
        {
            policy = Legacy;
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = BimErrorCode.InvalidScope,
                Message = $"Invalid {field} override '{value}'.",
            };
        }
    }
}
