using System;
using System.Collections.Generic;
using System.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace Rook.Handlers
{
    #region DTOs

    internal sealed class BakeRequest
    {
        public List<BakeTargetDto> Targets { get; init; } = new();
        public string LayerName { get; init; } = "RookBake";
        public bool CreateSublayers { get; init; } = true;
        public bool ClearExisting { get; init; }
        public string? ClearMode { get; init; }
    }

    internal sealed class BakeTargetDto
    {
        public string InstanceGuid { get; init; } = "";
        public int OutputIndex { get; init; }
        public string? Nickname { get; init; }
        public List<BakeItem> Items { get; init; } = new();
    }

    internal sealed class BakeItem
    {
        public object? Value { get; init; }
        public string BranchPath { get; init; } = "{0}";
        public int ItemIndex { get; init; }
    }

    internal sealed class BakeResult
    {
        public bool Success { get; init; }
        public string? Error { get; init; }
        public int TotalBaked { get; init; }
        public int TotalSkipped { get; init; }
        public List<BakeTargetResult> PerTarget { get; init; } = new();
    }

    internal sealed class BakeTargetResult
    {
        public string InstanceGuid { get; init; } = "";
        public int OutputIndex { get; init; }
        public string? Sublayer { get; init; }
        public int BakedCount { get; init; }
        public List<string> BakedIds { get; init; } = new();
        public List<string> GeometryTypes { get; init; } = new();
        public int SkippedCount { get; init; }
        public List<string> SkippedReasons { get; init; } = new();
    }

    #endregion

    /// <summary>
    /// RhinoCommon-facing bake service. Accepts raw values and DTOs only —
    /// never sees Grasshopper objects. GrasshopperHandler owns the GH reflection;
    /// this class owns materialization into the Rhino document.
    /// </summary>
    internal static class BakeService
    {
        public static BakeResult Execute(BakeRequest request)
        {
            if (request.Targets.Count == 0)
                return new BakeResult { Success = false, Error = "No targets to bake" };

            // Validate clearing semantics
            if (request.ClearExisting && !request.CreateSublayers &&
                !string.Equals(request.ClearMode, "layer", StringComparison.OrdinalIgnoreCase))
            {
                return new BakeResult
                {
                    Success = false,
                    Error = "clearExisting with createSublayers=false requires clearMode=\"layer\". " +
                            "Whole-layer clearing must be explicitly opted into."
                };
            }

            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new BakeResult { Success = false, Error = "No active Rhino document" };

            var bakeTime = DateTime.UtcNow.ToString("o");
            var perTarget = new List<BakeTargetResult>();
            int totalBaked = 0;
            int totalSkipped = 0;

            // Ensure parent layer exists
            int parentLayerIndex = EnsureLayer(doc, request.LayerName);
            if (parentLayerIndex < 0)
                return new BakeResult { Success = false, Error = $"Failed to create layer '{request.LayerName}'" };

            foreach (var target in request.Targets)
            {
                var targetResult = BakeTarget(doc, request, target, parentLayerIndex, bakeTime);
                perTarget.Add(targetResult);
                totalBaked += targetResult.BakedCount;
                totalSkipped += targetResult.SkippedCount;
            }

            doc.Views.Redraw();

            return new BakeResult
            {
                Success = true,
                TotalBaked = totalBaked,
                TotalSkipped = totalSkipped,
                PerTarget = perTarget
            };
        }

        private static BakeTargetResult BakeTarget(
            RhinoDoc doc,
            BakeRequest request,
            BakeTargetDto target,
            int parentLayerIndex,
            string bakeTime)
        {
            var bakedIds = new List<string>();
            var geometryTypes = new List<string>();
            var skippedReasons = new List<string>();

            // Resolve target layer
            string? sublayerPath = null;
            int targetLayerIndex = parentLayerIndex;

            if (request.CreateSublayers)
            {
                sublayerPath = BuildSublayerPath(request.LayerName, target.Nickname, target.InstanceGuid, target.OutputIndex);
                targetLayerIndex = EnsureSublayerHierarchy(doc, parentLayerIndex, target.Nickname, target.InstanceGuid, target.OutputIndex);

                if (targetLayerIndex < 0)
                {
                    return new BakeTargetResult
                    {
                        InstanceGuid = target.InstanceGuid,
                        OutputIndex = target.OutputIndex,
                        Sublayer = sublayerPath,
                        SkippedCount = target.Items.Count,
                        SkippedReasons = new List<string> { $"Failed to create sublayer: {sublayerPath}" }
                    };
                }
            }

            // Clear if requested
            if (request.ClearExisting)
            {
                if (request.CreateSublayers)
                {
                    ClearObjectsOnLayer(doc, targetLayerIndex);
                }
                else if (string.Equals(request.ClearMode, "layer", StringComparison.OrdinalIgnoreCase))
                {
                    ClearObjectsOnLayer(doc, parentLayerIndex);
                }
            }

            // Bake each item
            string bakeSource = $"{target.InstanceGuid}:{target.OutputIndex}";

            foreach (var item in target.Items)
            {
                if (!TryNormalizeBakeGeometry(item.Value, out var geometry, out var sourceType, out var skipReason))
                {
                    skippedReasons.Add($"[{item.BranchPath}][{item.ItemIndex}] {skipReason} (type: {sourceType})");
                    continue;
                }

                var attrs = new ObjectAttributes();
                attrs.LayerIndex = targetLayerIndex;
                attrs.SetUserString("rook:bake_source", bakeSource);
                attrs.SetUserString("rook:bake_layer", sublayerPath ?? request.LayerName);
                attrs.SetUserString("rook:bake_time", bakeTime);
                attrs.SetUserString("rook:bake_branch", item.BranchPath);
                attrs.SetUserString("rook:bake_item_index", item.ItemIndex.ToString());

                var id = doc.Objects.Add(geometry!, attrs);
                if (id != Guid.Empty)
                {
                    bakedIds.Add(id.ToString());
                    geometryTypes.Add(sourceType);
                }
                else
                {
                    skippedReasons.Add($"[{item.BranchPath}][{item.ItemIndex}] doc.Objects.Add returned empty GUID (type: {sourceType})");
                }
            }

            return new BakeTargetResult
            {
                InstanceGuid = target.InstanceGuid,
                OutputIndex = target.OutputIndex,
                Sublayer = sublayerPath,
                BakedCount = bakedIds.Count,
                BakedIds = bakedIds,
                GeometryTypes = geometryTypes.Distinct().ToList(),
                SkippedCount = skippedReasons.Count,
                SkippedReasons = skippedReasons
            };
        }

        #region Geometry Normalization

        /// <summary>
        /// Normalize a raw value from GH VolatileData into a bakeable GeometryBase.
        /// Handles struct-to-class conversions (Line → LineCurve, etc.) and skips
        /// non-geometry data types with explicit reasons.
        /// </summary>
        internal static bool TryNormalizeBakeGeometry(
            object? value,
            out GeometryBase? geometry,
            out string sourceType,
            out string? skipReason)
        {
            geometry = null;
            skipReason = null;

            if (value == null)
            {
                sourceType = "null";
                skipReason = "Null value";
                return false;
            }

            sourceType = value.GetType().Name;

            // Pass through if already GeometryBase
            if (value is GeometryBase gb)
            {
                geometry = gb;
                return true;
            }

            // Struct-to-class conversions
            if (value is Line line)
            {
                if (!line.IsValid) { skipReason = "Invalid Line"; return false; }
                geometry = new LineCurve(line);
                return true;
            }

            if (value is Arc arc)
            {
                if (!arc.IsValid) { skipReason = "Invalid Arc"; return false; }
                geometry = new ArcCurve(arc);
                return true;
            }

            if (value is Circle circle)
            {
                if (!circle.IsValid) { skipReason = "Invalid Circle"; return false; }
                geometry = new ArcCurve(circle);
                return true;
            }

            if (value is Box box)
            {
                if (!box.IsValid) { skipReason = "Invalid Box"; return false; }
                geometry = box.ToBrep();
                return true;
            }

            if (value is Point3d pt)
            {
                geometry = new Point(pt);
                return true;
            }

            if (value is Polyline polyline)
            {
                if (!polyline.IsValid) { skipReason = "Invalid Polyline"; return false; }
                geometry = new PolylineCurve(polyline);
                return true;
            }

            if (value is Rectangle3d rect)
            {
                if (!rect.IsValid) { skipReason = "Invalid Rectangle3d"; return false; }
                geometry = rect.ToNurbsCurve();
                return true;
            }

            // Explicit skips with reasons
            if (value is Plane)
            {
                skipReason = "Infinite plane has no canonical bake representation";
                return false;
            }

            if (value is int or double or float or string or bool or decimal or long)
            {
                skipReason = $"Non-geometry data type: {sourceType}";
                return false;
            }

            skipReason = $"Unsupported type: {sourceType}";
            return false;
        }

        #endregion

        #region Layer Helpers

        /// <summary>
        /// Build the deterministic sublayer path. Always includes GUID suffix for stability.
        /// Format: {layerName}::{sanitizedNickname}_{guid8}::O{index}
        /// </summary>
        internal static string BuildSublayerPath(string layerName, string? nickname, string instanceGuid, int outputIndex)
        {
            var sanitized = SanitizeLayerName(nickname ?? "Output");
            var guid8 = instanceGuid.Replace("-", "").Substring(0, Math.Min(8, instanceGuid.Replace("-", "").Length));
            return $"{layerName}::{sanitized}_{guid8}::O{outputIndex}";
        }

        private static string SanitizeLayerName(string name)
        {
            if (string.IsNullOrWhiteSpace(name))
                return "Output";

            var chars = name.ToCharArray();
            for (int i = 0; i < chars.Length; i++)
            {
                if (!char.IsLetterOrDigit(chars[i]) && chars[i] != '_' && chars[i] != '-')
                    chars[i] = '_';
            }

            var result = new string(chars).Trim('_');
            return string.IsNullOrEmpty(result) ? "Output" : result;
        }

        private static int EnsureLayer(RhinoDoc doc, string layerName)
        {
            int idx = doc.Layers.FindByFullPath(layerName, -1);
            if (idx >= 0) return idx;

            var layer = new Layer { Name = layerName };
            return doc.Layers.Add(layer);
        }

        /// <summary>
        /// Ensure the full sublayer hierarchy: {layerName}::{mid}::O{index}
        /// where {mid} = {sanitizedNickname}_{guid8}
        /// </summary>
        private static int EnsureSublayerHierarchy(
            RhinoDoc doc,
            int parentLayerIndex,
            string? nickname,
            string instanceGuid,
            int outputIndex)
        {
            // Middle tier: {sanitizedNickname}_{guid8}
            var sanitized = SanitizeLayerName(nickname ?? "Output");
            var guid8 = instanceGuid.Replace("-", "").Substring(0, Math.Min(8, instanceGuid.Replace("-", "").Length));
            string midName = $"{sanitized}_{guid8}";

            int midIndex = FindChildLayer(doc, parentLayerIndex, midName);
            if (midIndex < 0)
            {
                var midLayer = new Layer
                {
                    Name = midName,
                    ParentLayerId = doc.Layers[parentLayerIndex].Id
                };
                midIndex = doc.Layers.Add(midLayer);
                if (midIndex < 0) return -1;
            }

            // Leaf tier: O{index}
            string leafName = $"O{outputIndex}";
            int leafIndex = FindChildLayer(doc, midIndex, leafName);
            if (leafIndex < 0)
            {
                var leafLayer = new Layer
                {
                    Name = leafName,
                    ParentLayerId = doc.Layers[midIndex].Id
                };
                leafIndex = doc.Layers.Add(leafLayer);
            }

            return leafIndex;
        }

        private static int FindChildLayer(RhinoDoc doc, int parentIndex, string childName)
        {
            var parentId = doc.Layers[parentIndex].Id;
            for (int i = 0; i < doc.Layers.Count; i++)
            {
                var layer = doc.Layers[i];
                if (!layer.IsDeleted && layer.ParentLayerId == parentId &&
                    string.Equals(layer.Name, childName, StringComparison.OrdinalIgnoreCase))
                {
                    return i;
                }
            }
            return -1;
        }

        private static void ClearObjectsOnLayer(RhinoDoc doc, int layerIndex)
        {
            var objects = doc.Objects.FindByLayer(doc.Layers[layerIndex]);
            if (objects != null)
            {
                foreach (var obj in objects)
                    doc.Objects.Delete(obj, true);
            }
        }

        #endregion
    }
}
