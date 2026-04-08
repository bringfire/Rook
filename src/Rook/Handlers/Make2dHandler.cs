using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace Rook.Handlers
{
    /// <summary>
    /// Handles /make2d endpoint - generates 2D drawings from 3D geometry.
    /// </summary>
    public class Make2dHandler
    {
        /// <summary>
        /// POST /make2d - Generates 2D drawing curves from 3D objects.
        /// Body: { "view": "Front", "ids": ["guid1",...], "showHiddenLines": false, "targetLayer": "Make2D" }
        /// </summary>
        public ApiResponse Make2d(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            string viewName = "Front";
            List<Guid>? objectIds = null;
            bool showHiddenLines = false;
            string targetLayer = "Make2D";

            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    if (request != null)
                    {
                        if (request.TryGetValue("view", out var v))
                            viewName = v.GetString() ?? "Front";
                        if (request.TryGetValue("showHiddenLines", out var shl))
                            showHiddenLines = shl.GetBoolean();
                        if (request.TryGetValue("targetLayer", out var tl))
                            targetLayer = tl.GetString() ?? "Make2D";
                        if (request.TryGetValue("ids", out var idsEl))
                        {
                            objectIds = idsEl.EnumerateArray()
                                .Select(e => Guid.TryParse(e.GetString(), out var g) ? g : Guid.Empty)
                                .Where(g => g != Guid.Empty)
                                .ToList();
                        }
                    }
                }
                catch { /* Use defaults */ }
            }

            try
            {
                // Get view direction based on view name
                var viewDirection = GetViewDirection(viewName);
                var upDirection = GetUpDirection(viewName);

                // Get objects to process
                List<GeometryBase> geometries = new();
                if (objectIds != null && objectIds.Count > 0)
                {
                    foreach (var id in objectIds)
                    {
                        var obj = doc.Objects.FindId(id);
                        if (obj?.Geometry != null)
                        {
                            geometries.Add(obj.Geometry);
                        }
                    }
                }
                else
                {
                    // Use all objects if no IDs specified
                    foreach (var obj in doc.Objects)
                    {
                        if (obj?.Geometry != null)
                        {
                            geometries.Add(obj.Geometry);
                        }
                    }
                }

                if (geometries.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "No objects to process" };
                }

                // Create or find target layer
                int layerIndex = doc.Layers.FindByFullPath(targetLayer, -1);
                if (layerIndex < 0)
                {
                    layerIndex = doc.Layers.Add(targetLayer, System.Drawing.Color.Black);
                }

                // Create hidden lines layer if needed
                int hiddenLayerIndex = -1;
                if (showHiddenLines)
                {
                    string hiddenLayerName = targetLayer + "::Hidden";
                    hiddenLayerIndex = doc.Layers.FindByFullPath(hiddenLayerName, -1);
                    if (hiddenLayerIndex < 0)
                    {
                        var hiddenLayer = new Layer();
                        hiddenLayer.Name = "Hidden";
                        hiddenLayer.ParentLayerId = doc.Layers[layerIndex].Id;
                        hiddenLayer.Color = System.Drawing.Color.Gray;
                        hiddenLayerIndex = doc.Layers.Add(hiddenLayer);
                    }
                }

                // Create projection plane
                var projectionPlane = new Plane(Point3d.Origin, viewDirection);

                var record = doc.BeginUndoRecord("Make2D");
                var createdIds = new List<string>();
                var visibleCurves = new List<Curve>();
                var hiddenCurves = new List<Curve>();

                // Project geometry silhouettes
                foreach (var geom in geometries)
                {
                    Curve[]? silhouettes = null;

                    if (geom is Brep brep)
                    {
                        // Get silhouette curves
                        var silhouette = Silhouette.Compute(brep, SilhouetteType.Projecting, viewDirection, 0.001, 0.001);
                        if (silhouette != null && silhouette.Length > 0)
                        {
                            silhouettes = silhouette.Select(s => s.Curve).Where(c => c != null).ToArray();
                        }

                        // Also get edges
                        var edges = brep.Edges.Select(e => e.EdgeCurve).Where(c => c != null).ToList();
                        if (edges.Count > 0)
                        {
                            silhouettes = silhouettes == null ? edges.ToArray()! : silhouettes.Concat(edges).ToArray()!;
                        }
                    }
                    else if (geom is Mesh mesh)
                    {
                        // Get mesh silhouette
                        var silhouette = Silhouette.Compute(mesh, SilhouetteType.Projecting, viewDirection, 0.001, 0.001);
                        if (silhouette != null && silhouette.Length > 0)
                        {
                            silhouettes = silhouette.Select(s => s.Curve).Where(c => c != null).ToArray();
                        }
                    }
                    else if (geom is Curve curve)
                    {
                        silhouettes = new[] { curve };
                    }

                    if (silhouettes != null)
                    {
                        foreach (var crv in silhouettes)
                        {
                            if (crv == null) continue;

                            // Project curve to plane
                            var projected = Curve.ProjectToPlane(crv, projectionPlane);
                            if (projected != null)
                            {
                                // Transform to XY plane for 2D output
                                var transform = Transform.PlaneToPlane(projectionPlane, Plane.WorldXY);
                                projected.Transform(transform);
                                visibleCurves.Add(projected);
                            }
                        }
                    }
                }

                // Add visible curves to document
                var attr = new ObjectAttributes();
                attr.LayerIndex = layerIndex;
                foreach (var crv in visibleCurves)
                {
                    var id = doc.Objects.AddCurve(crv, attr);
                    if (id != Guid.Empty)
                    {
                        createdIds.Add(id.ToString());
                    }
                }

                doc.EndUndoRecord(record);
                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["view"] = viewName,
                        ["visibleCurves"] = visibleCurves.Count,
                        ["hiddenCurves"] = hiddenCurves.Count,
                        ["createdIds"] = createdIds,
                        ["targetLayer"] = targetLayer
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Make2D failed: {ex.Message}" };
            }
        }

        private Vector3d GetViewDirection(string viewName)
        {
            return viewName.ToLowerInvariant() switch
            {
                "top" => -Vector3d.ZAxis,
                "bottom" => Vector3d.ZAxis,
                "front" => -Vector3d.YAxis,
                "back" => Vector3d.YAxis,
                "left" => Vector3d.XAxis,
                "right" => -Vector3d.XAxis,
                "perspective" => new Vector3d(-1, -1, -1),
                _ => -Vector3d.YAxis // Default to front
            };
        }

        private Vector3d GetUpDirection(string viewName)
        {
            return viewName.ToLowerInvariant() switch
            {
                "top" => Vector3d.YAxis,
                "bottom" => -Vector3d.YAxis,
                _ => Vector3d.ZAxis
            };
        }
    }
}
