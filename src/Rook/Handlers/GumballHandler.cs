using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Rhino;
using Rhino.Geometry;
using Rook.Commands;
using Rook.Models;

namespace Rook.Handlers
{
    /// <summary>
    /// Handles HTTP endpoints for AI Gumball mode: activate, deactivate, status, and history.
    /// </summary>
    public class GumballHandler
    {
        /// <summary>
        /// POST /gumball/activate - Enable AI Gumball mode.
        /// Optionally selects specified objects first. If mode is already on,
        /// selecting new objects will auto-update the gumball.
        /// Body: { "ids": ["guid1", "guid2"] }
        /// </summary>
        public ApiResponse Activate(string? body)
        {
            var doc = RhinoDoc.ActiveDoc;
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            // Parse and select objects if provided
            List<string>? ids = null;
            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    if (args != null && args.TryGetValue("ids", out var idsEl) && idsEl.ValueKind == JsonValueKind.Array)
                    {
                        ids = new List<string>();
                        foreach (var item in idsEl.EnumerateArray())
                        {
                            var id = item.GetString();
                            if (!string.IsNullOrEmpty(id))
                                ids.Add(id);
                        }
                    }
                }
                catch { /* Use defaults */ }
            }

            if (ids != null && ids.Count > 0)
            {
                doc.Objects.UnselectAll();
                int selected = 0;
                foreach (var idStr in ids)
                {
                    if (Guid.TryParse(idStr, out var guid))
                    {
                        var rhinoObj = doc.Objects.FindId(guid);
                        if (rhinoObj != null)
                        {
                            rhinoObj.Select(true);
                            selected++;
                        }
                    }
                }

                if (selected == 0)
                    return new ApiResponse { Success = false, Data = "None of the specified objects were found" };

                doc.Views.Redraw();
            }

            // Enable mode if not already on
            var manager = AIGumballManager.Instance;
            if (!manager.IsEnabled)
            {
                RhinoApp.RunScript("_AIGumball", false);
            }

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    Message = "AI Gumball mode enabled. Gumball appears on selected objects — drag handles to transform, Esc to pause, select new objects to continue.",
                    Enabled = true,
                    ObjectCount = ids?.Count ?? 0
                }
            };
        }

        /// <summary>
        /// POST /gumball/deactivate - Disable AI Gumball mode.
        /// </summary>
        public ApiResponse Deactivate()
        {
            var manager = AIGumballManager.Instance;
            if (manager.IsEnabled)
            {
                RhinoApp.RunScript("_AIGumball", false); // Toggle off
            }

            return new ApiResponse
            {
                Success = true,
                Data = new { Message = "AI Gumball mode disabled.", Enabled = false }
            };
        }

        /// <summary>
        /// GET /gumball/status - Get current AI Gumball status.
        /// Returns mode state, drag activity, count, last handle mode, and cumulative transform.
        /// </summary>
        public ApiResponse GetStatus()
        {
            var manager = AIGumballManager.Instance;

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    Enabled = manager.IsEnabled,
                    DragActive = manager.IsDragActive,
                    DragCount = manager.CurrentDragCount,
                    LastMode = manager.LastMode.ToString(),
                    CumulativeTransform = AIGumballManager.TransformToArray(manager.CurrentCumulativeTransform)
                }
            };
        }

        /// <summary>
        /// GET /gumball/history - Get AI Gumball drag history from the current session.
        /// Returns all AIGumball command records with full drag detail.
        /// Body: { "limit": 20 }
        /// </summary>
        public ApiResponse GetHistory(string? body)
        {
            int limit = 20;

            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    if (args != null && args.TryGetValue("limit", out var limitEl))
                        limit = limitEl.GetInt32();
                }
                catch { /* Use defaults */ }
            }

            var history = SessionRecorder.Instance.GetHistory(limit: 1000, offset: 0);
            var allGumball = history.Where(c => c.CommandName == "AIGumball").ToList();
            var gumballCommands = allGumball
                .Skip(Math.Max(0, allGumball.Count - limit))
                .Select(c => new
                {
                    c.Id,
                    c.SequenceNumber,
                    c.Timestamp,
                    c.DurationMs,
                    c.GumballDragCount,
                    c.GumballMode,
                    c.InputObjectIds,
                    c.InputSubObjects,
                    c.TransformMatrix,
                    c.ObjectIdsCreated,
                    Drags = c.GumballDrags?.Select(d => new
                    {
                        d.DragIndex,
                        HandleMode = d.HandleMode.ToString(),
                        d.DeltaTransformMatrix,
                        d.CumulativeTransformMatrix,
                        d.IsCopy,
                        d.IsRelocate,
                        d.Timestamp,
                        d.DragDurationMs
                    })
                })
                .ToList();

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    Count = gumballCommands.Count,
                    Commands = gumballCommands
                }
            };
        }

        /// <summary>
        /// POST /gumball/align - Set gumball alignment mode.
        /// Body: { "mode": "world" | "cplane" | "object" }
        /// </summary>
        public ApiResponse Align(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body required with 'mode' field" };

            string mode = "object";
            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args != null && args.TryGetValue("mode", out var modeEl))
                    mode = modeEl.GetString() ?? "object";
            }
            catch
            {
                return new ApiResponse { Success = false, Data = "Invalid JSON body" };
            }

            var manager = AIGumballManager.Instance;
            if (!manager.SetAlignment(mode))
                return new ApiResponse { Success = false, Data = $"Unknown alignment mode: '{mode}'. Use 'world', 'cplane', or 'object'." };

            return new ApiResponse
            {
                Success = true,
                Data = new
                {
                    Message = $"Gumball alignment set to '{mode}'.",
                    Alignment = manager.Alignment.ToString()
                }
            };
        }

        /// <summary>
        /// POST /gumball/extrude - Programmatic extrude via gumball (without mouse interaction).
        /// Body: { "ids": ["guid"], "direction": [0,0,1], "distance": 5.0, "cap": true, "faceIndex": 0 }
        /// </summary>
        public ApiResponse Extrude(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body required" };

            var doc = RhinoDoc.ActiveDoc;
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args == null)
                    return new ApiResponse { Success = false, Data = "Invalid JSON" };

                // Parse IDs
                var ids = new List<Guid>();
                if (args.TryGetValue("ids", out var idsEl) && idsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in idsEl.EnumerateArray())
                    {
                        if (Guid.TryParse(item.GetString(), out var id))
                            ids.Add(id);
                    }
                }
                if (ids.Count == 0)
                    return new ApiResponse { Success = false, Data = "No valid object IDs provided" };

                // Parse direction
                var dir = Vector3d.ZAxis;
                if (args.TryGetValue("direction", out var dirEl) && dirEl.ValueKind == JsonValueKind.Array)
                {
                    var coords = dirEl.EnumerateArray().Select(d => d.GetDouble()).ToArray();
                    if (coords.Length >= 3)
                        dir = new Vector3d(coords[0], coords[1], coords[2]);
                }

                var distance = args.TryGetValue("distance", out var distEl) ? distEl.GetDouble() : 1.0;
                var cap = !args.TryGetValue("cap", out var capEl) || capEl.GetBoolean();
                var faceIndex = args.TryGetValue("faceIndex", out var fiEl) ? fiEl.GetInt32() : -1;

                var results = new List<object>();
                using var undo = new UndoScope(doc, "AIGumball Extrude");

                foreach (var objId in ids)
                {
                    ExtrudeResult extResult;
                    var rhinoObj = doc.Objects.FindId(objId);

                    if (faceIndex >= 0 && rhinoObj?.Geometry is Brep)
                        extResult = GumballExtrudeHandler.ExtrudeFace(doc, objId, faceIndex, dir, distance, cap);
                    else if (rhinoObj?.Geometry is Curve)
                        extResult = GumballExtrudeHandler.ExtrudeCurve(doc, objId, dir, distance, cap);
                    else if (rhinoObj?.Geometry is Brep singleFace && singleFace.Faces.Count == 1)
                        extResult = GumballExtrudeHandler.ExtrudeFace(doc, objId, 0, dir, distance, cap);
                    else
                        extResult = GumballExtrudeHandler.ExtrudeFace(doc, objId, faceIndex >= 0 ? faceIndex : 0, dir, distance, cap);

                    results.Add(new
                    {
                        ObjectId = objId.ToString(),
                        extResult.Success,
                        extResult.Error,
                        extResult.GeometryType,
                        extResult.BooleanOperation,
                        Created = extResult.CreatedIds.Select(g => g.ToString()).ToList(),
                        Deleted = extResult.DeletedIds.Select(g => g.ToString()).ToList()
                    });
                }

                doc.Views.Redraw();
                return new ApiResponse { Success = true, Data = results };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Extrude failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /gumball/cut - Programmatic cut/boss via gumball (without mouse interaction).
        /// Body: { "ids": ["guid"], "direction": [0,0,1], "distance": -3.0, "faceIndex": 2 }
        /// Positive distance = boss (boolean union), negative = cut (boolean difference).
        /// </summary>
        public ApiResponse Cut(string? body)
        {
            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body required" };

            var doc = RhinoDoc.ActiveDoc;
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                if (args == null)
                    return new ApiResponse { Success = false, Data = "Invalid JSON" };

                var ids = new List<Guid>();
                if (args.TryGetValue("ids", out var idsEl) && idsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in idsEl.EnumerateArray())
                    {
                        if (Guid.TryParse(item.GetString(), out var id))
                            ids.Add(id);
                    }
                }
                if (ids.Count == 0)
                    return new ApiResponse { Success = false, Data = "No valid object IDs provided" };

                var dir = Vector3d.ZAxis;
                if (args.TryGetValue("direction", out var dirEl) && dirEl.ValueKind == JsonValueKind.Array)
                {
                    var coords = dirEl.EnumerateArray().Select(d => d.GetDouble()).ToArray();
                    if (coords.Length >= 3)
                        dir = new Vector3d(coords[0], coords[1], coords[2]);
                }

                var distance = args.TryGetValue("distance", out var distEl) ? distEl.GetDouble() : -1.0;
                var faceIndex = args.TryGetValue("faceIndex", out var fiEl) ? fiEl.GetInt32() : 0;

                var results = new List<object>();
                using var undo = new UndoScope(doc, "AIGumball Cut");

                foreach (var objId in ids)
                {
                    var extResult = GumballExtrudeHandler.CutOrBoss(doc, objId, faceIndex, dir, distance);
                    results.Add(new
                    {
                        ObjectId = objId.ToString(),
                        extResult.Success,
                        extResult.Error,
                        extResult.GeometryType,
                        extResult.BooleanOperation,
                        Created = extResult.CreatedIds.Select(g => g.ToString()).ToList(),
                        Deleted = extResult.DeletedIds.Select(g => g.ToString()).ToList()
                    });
                }

                doc.Views.Redraw();
                return new ApiResponse { Success = true, Data = results };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Cut failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /gumball/settings - Get or set gumball behavior settings.
        /// Body: { "dragStrength": 0.5, "autoReset": true, "snapEnabled": false, ... }
        /// Any fields omitted are left unchanged. Returns current settings.
        /// </summary>
        public ApiResponse Settings(string? body)
        {
            var manager = AIGumballManager.Instance;

            if (!string.IsNullOrEmpty(body))
            {
                try
                {
                    var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
                    if (args != null)
                    {
                        if (args.TryGetValue("dragStrength", out var dsEl))
                            manager.DragStrength = Math.Max(0.01, Math.Min(dsEl.GetDouble(), 10.0));
                        if (args.TryGetValue("autoReset", out var arEl))
                            manager.AutoReset = arEl.GetBoolean();
                        if (args.TryGetValue("snapEnabled", out var seEl))
                            manager.SnapEnabled = seEl.GetBoolean();
                        if (args.TryGetValue("snapTranslate", out var stEl))
                            manager.SnapTranslate = Math.Max(0.001, stEl.GetDouble());
                        if (args.TryGetValue("snapRotateDeg", out var srEl))
                            manager.SnapRotateDeg = Math.Max(0.1, srEl.GetDouble());
                        if (args.TryGetValue("snapScale", out var ssEl))
                            manager.SnapScale = Math.Max(0.001, ssEl.GetDouble());
                        if (args.TryGetValue("alignment", out var alEl))
                        {
                            var mode = alEl.GetString() ?? "";
                            manager.SetAlignment(mode);
                        }
                    }
                }
                catch (Exception ex)
                {
                    return new ApiResponse { Success = false, Data = $"Invalid settings: {ex.Message}" };
                }
            }

            return new ApiResponse
            {
                Success = true,
                Data = manager.GetSettings()
            };
        }
    }
}
