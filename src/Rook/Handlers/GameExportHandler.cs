using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Rhino;
using Rhino.DocObjects;
using Rhino.FileIO;
using Rhino.Geometry;
using Rook.Models;

namespace Rook.Handlers
{
    /// <summary>
    /// Handles game export operations: semantic tagging, validation, and .3dm + manifest export
    /// for the Rhino-to-Games pipeline (consumed by Engram/UE5).
    /// </summary>
    public class GameExportHandler
    {
        // Built-in layer keyword → semantic tag defaults
        private static readonly List<(string Keyword, string SemanticType, string Collision, bool Nanite)> DefaultLayerMappings = new()
        {
            ("Walls", "wall", "complex_as_simple", true),
            ("Floors", "floor", "complex_as_simple", true),
            ("Glazing", "glass", "box", true),
            ("Glass", "glass", "box", true),
            ("Columns", "column", "complex_as_simple", true),
            ("Furniture", "furniture", "convex_decomposition", true),
            ("Seating", "furniture", "convex_decomposition", true),
            ("Landscape", "landscape", "complex_as_simple", true),
            ("Terrain", "landscape", "complex_as_simple", true),
            ("Doors", "door", "box", true),
            ("Stairs", "stair", "complex_as_simple", true),
            ("Railing", "railing", "box", false),
        };

        private static readonly JsonSerializerOptions ManifestJsonOptions = new()
        {
            WriteIndented = true,
            DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull
        };

        /// <summary>
        /// POST /game-export/tag - Tag objects with game export metadata via user strings.
        /// </summary>
        public ApiResponse TagObjectSemantic(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body required with 'ids' field" };

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
                return new ApiResponse { Success = false, Data = "Invalid request body" };

            if (!request.TryGetValue("ids", out var idsEl))
                return new ApiResponse { Success = false, Data = "Missing 'ids' field" };

            var ids = idsEl.EnumerateArray()
                .Select(e => e.GetString())
                .Where(s => s != null)
                .ToList();

            if (ids.Count == 0)
                return new ApiResponse { Success = false, Data = "No valid IDs provided" };

            // Extract optional tag values
            string? semanticType = request.TryGetValue("semantic_type", out var stEl) ? stEl.GetString() : null;
            string? collision = request.TryGetValue("collision", out var colEl) ? colEl.GetString() : null;
            bool? nanite = request.TryGetValue("nanite", out var nanEl) ? nanEl.GetBoolean() : null;
            string? materialIntentJson = null;
            if (request.TryGetValue("material_intent", out var miEl))
                materialIntentJson = miEl.GetRawText();
            List<string>? tags = null;
            if (request.TryGetValue("tags", out var tagsEl))
                tags = tagsEl.EnumerateArray().Select(e => e.GetString()!).Where(s => s != null).ToList();

            int taggedCount = 0;
            var results = new List<Dictionary<string, object>>();

            foreach (var idStr in ids)
            {
                if (!Guid.TryParse(idStr, out var guid))
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr!, ["error"] = "invalid GUID" });
                    continue;
                }

                var obj = doc.Objects.FindId(guid);
                if (obj == null)
                {
                    results.Add(new Dictionary<string, object> { ["id"] = idStr!, ["error"] = "not found" });
                    continue;
                }

                var keysSet = new List<string>();

                if (semanticType != null)
                {
                    obj.Attributes.SetUserString("semantic_type", semanticType);
                    keysSet.Add("semantic_type");
                }
                if (collision != null)
                {
                    obj.Attributes.SetUserString("collision", collision);
                    keysSet.Add("collision");
                }
                if (nanite.HasValue)
                {
                    obj.Attributes.SetUserString("nanite", nanite.Value ? "true" : "false");
                    keysSet.Add("nanite");
                }
                if (materialIntentJson != null)
                {
                    obj.Attributes.SetUserString("material_intent", materialIntentJson);
                    keysSet.Add("material_intent");
                }
                if (tags != null && tags.Count > 0)
                {
                    obj.Attributes.SetUserString("tags", string.Join(",", tags));
                    keysSet.Add("tags");
                }

                obj.CommitChanges();
                taggedCount++;
                results.Add(new Dictionary<string, object> { ["id"] = idStr!, ["keys_set"] = keysSet });
            }

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["tagged_count"] = taggedCount,
                    ["objects"] = results
                }
            };
        }

        /// <summary>
        /// POST /game-export/tag-from-layers - Batch-tag objects based on layer naming convention.
        /// Tag-once semantics: skips objects that already have semantic_type set.
        /// </summary>
        public ApiResponse TagObjectsFromLayers(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            var request = !string.IsNullOrEmpty(body)
                ? JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body)
                : new Dictionary<string, JsonElement>();

            bool applyDefaults = true;
            if (request != null && request.TryGetValue("apply_defaults", out var adEl))
                applyDefaults = adEl.GetBoolean();

            // Build effective mapping: defaults + custom overrides
            var mappings = new List<(string Keyword, string SemanticType, string Collision, bool Nanite)>();
            if (applyDefaults)
                mappings.AddRange(DefaultLayerMappings);

            // Parse custom mapping if provided
            if (request != null && request.TryGetValue("mapping", out var mapEl))
            {
                foreach (var prop in mapEl.EnumerateObject())
                {
                    var keyword = prop.Name;
                    var val = prop.Value;
                    var st = val.TryGetProperty("semantic_type", out var stProp) ? stProp.GetString() ?? "other" : "other";
                    var col = val.TryGetProperty("collision", out var colProp) ? colProp.GetString() ?? "complex_as_simple" : "complex_as_simple";
                    var nan = val.TryGetProperty("nanite", out var nanProp) && nanProp.GetBoolean();
                    mappings.Add((keyword, st, col, nan));
                }
            }

            int taggedCount = 0;
            var layersMatched = new HashSet<string>();
            var allLayerPaths = new HashSet<string>();

            foreach (var rhinoObj in doc.Objects)
            {
                if (rhinoObj == null || rhinoObj.Attributes.IsInstanceDefinitionObject) continue;

                var layerIndex = rhinoObj.Attributes.LayerIndex;
                var layer = doc.Layers.FindIndex(layerIndex);
                if (layer == null) continue;

                var layerPath = layer.FullPath;
                allLayerPaths.Add(layerPath);

                // Tag-once: skip if already has semantic_type
                var existingSemantic = rhinoObj.Attributes.GetUserString("semantic_type");
                if (!string.IsNullOrEmpty(existingSemantic)) continue;

                // Check if layer path matches any keyword
                bool matched = false;
                foreach (var (keyword, semanticType, collision, nanite) in mappings)
                {
                    if (layerPath.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        rhinoObj.Attributes.SetUserString("semantic_type", semanticType);
                        rhinoObj.Attributes.SetUserString("collision", collision);
                        rhinoObj.Attributes.SetUserString("nanite", nanite ? "true" : "false");
                        rhinoObj.CommitChanges();
                        taggedCount++;
                        layersMatched.Add(layerPath);
                        matched = true;
                        break;
                    }
                }

                if (!matched)
                {
                    // Will appear in unmatched_layers
                }
            }

            var unmatchedLayers = allLayerPaths.Except(layersMatched).ToList();

            if (taggedCount > 0)
                doc.Views.Redraw();

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["tagged_count"] = taggedCount,
                    ["layers_matched"] = layersMatched.ToList(),
                    ["unmatched_layers"] = unmatchedLayers
                }
            };
        }

        /// <summary>
        /// POST /game-export/validate - Advisory pre-flight checks before export.
        /// Never blocks export; surfaces issues for the user to decide.
        /// </summary>
        public ApiResponse ValidateExport(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            var objects = ResolveObjects(doc, body);
            if (objects.Count == 0)
                return new ApiResponse { Success = false, Data = "No objects to validate" };

            var issues = new List<Dictionary<string, object>>();
            bool hasWarnings = false;

            foreach (var rhinoObj in objects)
            {
                var geometry = rhinoObj.Geometry;
                if (geometry == null) continue;

                var objId = rhinoObj.Id.ToString();
                var objName = rhinoObj.Attributes.Name ?? objId.Substring(0, 8);

                // Check Brep health
                if (geometry is Brep brep)
                {
                    if (!brep.IsManifold)
                    {
                        issues.Add(MakeIssue(objId, objName, "warning", "Non-manifold Brep — may cause tessellation artifacts"));
                        hasWarnings = true;
                    }

                    if (!brep.IsSolid)
                    {
                        int nakedCount = brep.Edges.Count(e => e.Valence == EdgeAdjacency.Naked);
                        if (nakedCount > 0)
                        {
                            issues.Add(MakeIssue(objId, objName, "warning", $"Has {nakedCount} naked edge(s) — geometry is not watertight"));
                            hasWarnings = true;
                        }
                    }
                }

                // Check Mesh health
                if (geometry is Mesh mesh)
                {
                    if (!mesh.IsValid)
                    {
                        issues.Add(MakeIssue(objId, objName, "warning", "Invalid mesh"));
                        hasWarnings = true;
                    }
                }

                // Check material assignment
                if (rhinoObj.Attributes.MaterialIndex < 0)
                {
                    issues.Add(MakeIssue(objId, objName, "info", "No material assigned"));
                }

                // Check user strings
                var semanticType = rhinoObj.Attributes.GetUserString("semantic_type");
                if (string.IsNullOrEmpty(semanticType))
                {
                    issues.Add(MakeIssue(objId, objName, "info", "No semantic_type set — consider running tag-from-layers first"));
                }
            }

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["valid"] = !hasWarnings,
                    ["object_count"] = objects.Count,
                    ["issues"] = issues
                }
            };
        }

        /// <summary>
        /// POST /game-export/export - Export .3dm and write companion manifest JSON.
        /// </summary>
        public ApiResponse ExportWithManifest(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body required with 'path' field" };

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
                return new ApiResponse { Success = false, Data = "Invalid request body" };

            if (!request.TryGetValue("path", out var pathEl))
                return new ApiResponse { Success = false, Data = "Missing 'path' field" };

            var filePath = pathEl.GetString();
            if (string.IsNullOrEmpty(filePath))
                return new ApiResponse { Success = false, Data = "Invalid path" };

            // Ensure .3dm extension
            if (!filePath.EndsWith(".3dm", StringComparison.OrdinalIgnoreCase))
                filePath += ".3dm";

            // Ensure directory exists
            var directory = Path.GetDirectoryName(filePath);
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
                Directory.CreateDirectory(directory);

            var objects = ResolveObjects(doc, body);
            if (objects.Count == 0)
                return new ApiResponse { Success = false, Data = "No objects to export" };

            try
            {
                // Build manifest
                var manifest = BuildManifest(doc, filePath, objects, request);

                // Export .3dm with layers, materials, and user strings preserved
                var file3dm = new File3dm();

                // Copy layer table from source document
                foreach (var layer in doc.Layers.Where(l => !l.IsDeleted))
                    file3dm.AllLayers.Add(layer);

                // Copy material table for materials used by exported objects
                var usedMaterialIndices = objects
                    .Select(o => o.Attributes.MaterialIndex)
                    .Where(idx => idx >= 0)
                    .Distinct();
                foreach (var matIdx in usedMaterialIndices)
                {
                    var material = doc.Materials[matIdx];
                    if (material != null)
                        file3dm.AllMaterials.Add(material);
                }

                foreach (var rhinoObj in objects)
                {
                    var geometry = rhinoObj.Geometry;
                    if (geometry == null) continue;

                    // Duplicate preserves LayerIndex, MaterialIndex, Name, and all other attributes
                    var attr = rhinoObj.Attributes.Duplicate();

                    // Also copy user strings (Duplicate may not copy these)
                    var userStrings = rhinoObj.Attributes.GetUserStrings();
                    if (userStrings != null)
                    {
                        foreach (string key in userStrings.AllKeys)
                            attr.SetUserString(key, userStrings[key]);
                    }

                    if (geometry is Curve curve)
                        file3dm.Objects.AddCurve(curve, attr);
                    else if (geometry is Brep brep)
                        file3dm.Objects.AddBrep(brep, attr);
                    else if (geometry is Mesh mesh)
                        file3dm.Objects.AddMesh(mesh, attr);
                    else if (geometry is Surface surface)
                        file3dm.Objects.AddSurface(surface, attr);
                    else if (geometry is Point point)
                        file3dm.Objects.AddPoint(point.Location, attr);
                    else if (geometry is Extrusion extrusion)
                        file3dm.Objects.AddExtrusion(extrusion, attr);
                }

                var writeOptions = new File3dmWriteOptions();
                bool success = file3dm.Write(filePath, writeOptions);
                file3dm.Dispose();

                if (!success || !File.Exists(filePath))
                {
                    return new ApiResponse { Success = false, Data = "Failed to write .3dm file" };
                }

                // Write manifest JSON
                var manifestPath = Path.Combine(
                    Path.GetDirectoryName(filePath) ?? ".",
                    Path.GetFileNameWithoutExtension(filePath) + "_manifest.json");

                var manifestJson = JsonSerializer.Serialize(manifest, ManifestJsonOptions);
                File.WriteAllText(manifestPath, manifestJson);

                var fileInfo = new FileInfo(filePath);

                // Count tagged objects for summary
                int taggedCount = objects.Count(o => !string.IsNullOrEmpty(o.Attributes.GetUserString("semantic_type")));

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["export_path"] = filePath,
                        ["manifest_path"] = manifestPath,
                        ["object_count"] = objects.Count,
                        ["file_size"] = fileInfo.Length,
                        ["manifest_summary"] = new Dictionary<string, object>
                        {
                            ["version"] = manifest.Version,
                            ["objects_with_semantic_type"] = taggedCount,
                            ["material_mappings"] = manifest.MaterialMap?.Count ?? 0
                        }
                    }
                };
            }
            catch (Exception ex)
            {
                // Clean up partial .3dm if manifest write failed
                if (File.Exists(filePath))
                {
                    try { File.Delete(filePath); } catch { }
                }
                return new ApiResponse { Success = false, Data = $"Export failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /game-export/prepare - One-command orchestrator: tag → validate → export.
        /// Always runs to completion. Reports all results.
        /// </summary>
        public ApiResponse PrepareForGameExport(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            if (string.IsNullOrEmpty(body))
                return new ApiResponse { Success = false, Data = "Request body required with 'path' field" };

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
                return new ApiResponse { Success = false, Data = "Invalid request body" };

            if (!request.TryGetValue("path", out _))
                return new ApiResponse { Success = false, Data = "Missing 'path' field" };

            bool skipTagging = request.TryGetValue("skip_tagging", out var stEl) && stEl.GetBoolean();
            bool skipValidation = request.TryGetValue("skip_validation", out var svEl) && svEl.GetBoolean();

            // Step 1: Tag from layers (unless skipped)
            ApiResponse? taggingResult = null;
            if (!skipTagging)
            {
                // Build tagging body — preserve custom mapping if provided
                var tagRequest = new Dictionary<string, object> { ["apply_defaults"] = true };
                if (request.TryGetValue("mapping", out var mappingEl))
                    tagRequest["mapping"] = JsonSerializer.Deserialize<object>(mappingEl.GetRawText())!;
                var tagBody = JsonSerializer.Serialize(tagRequest);
                taggingResult = TagObjectsFromLayers(tagBody);
            }

            // Step 2: Validate (unless skipped)
            ApiResponse? validationResult = null;
            if (!skipValidation)
            {
                validationResult = ValidateExport(body);
            }

            // Step 3: Export with manifest (always runs)
            var exportResult = ExportWithManifest(body);

            return new ApiResponse
            {
                Success = exportResult.Success,
                Data = new Dictionary<string, object?>
                {
                    ["tagging_result"] = taggingResult?.Data,
                    ["validation_result"] = validationResult?.Data,
                    ["export_result"] = exportResult.Data
                }
            };
        }

        // ── Helpers ──────────────────────────────────────────────────

        /// <summary>
        /// Resolve objects from body params: by ids, selection, or all.
        /// Matches the pattern used in ImportExportHandler.Export.
        /// </summary>
        private static List<RhinoObject> ResolveObjects(RhinoDoc doc, string? body)
        {
            if (string.IsNullOrEmpty(body))
                return doc.Objects.Where(o => o != null && !o.Attributes.IsInstanceDefinitionObject).ToList();

            Dictionary<string, JsonElement>? request;
            try
            {
                request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            }
            catch
            {
                return doc.Objects.Where(o => o != null && !o.Attributes.IsInstanceDefinitionObject).ToList();
            }

            if (request == null)
                return doc.Objects.Where(o => o != null && !o.Attributes.IsInstanceDefinitionObject).ToList();

            // By specific IDs
            if (request.TryGetValue("ids", out var idsEl))
            {
                return idsEl.EnumerateArray()
                    .Select(e => Guid.TryParse(e.GetString(), out var g) ? doc.Objects.FindId(g) : null)
                    .Where(obj => obj != null)
                    .Cast<RhinoObject>()
                    .ToList();
            }

            // By selection
            if (request.TryGetValue("selection", out var selEl) && selEl.ValueKind == JsonValueKind.True)
            {
                return doc.Objects.GetSelectedObjects(false, false).ToList();
            }

            // All objects (excluding instance definitions)
            return doc.Objects.Where(o => o != null && !o.Attributes.IsInstanceDefinitionObject).ToList();
        }

        /// <summary>
        /// Build the ExportManifest from objects and request parameters.
        /// </summary>
        private static ExportManifest BuildManifest(
            RhinoDoc doc, string filePath,
            List<RhinoObject> objects,
            Dictionary<string, JsonElement> request)
        {
            var manifest = new ExportManifest
            {
                Source = new ManifestSource
                {
                    RhinoVersion = RhinoApp.ExeVersion.ToString(),
                    File = Path.GetFileName(filePath),
                    ExportedAt = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
                }
            };

            // Parse settings if provided
            if (request.TryGetValue("settings", out var settingsEl))
            {
                manifest.Settings = JsonSerializer.Deserialize<ManifestSettings>(settingsEl.GetRawText());
            }

            // Parse material_map if provided
            if (request.TryGetValue("material_map", out var mmEl))
            {
                manifest.MaterialMap = JsonSerializer.Deserialize<Dictionary<string, MaterialMapping>>(mmEl.GetRawText());
            }

            // Parse level_placement if provided
            if (request.TryGetValue("level_placement", out var lpEl))
            {
                manifest.LevelPlacement = JsonSerializer.Deserialize<LevelPlacement>(lpEl.GetRawText());
            }

            // Build object entries
            foreach (var rhinoObj in objects)
            {
                var entry = new ManifestObject
                {
                    RhinoUuid = rhinoObj.Id.ToString(),
                    Name = !string.IsNullOrEmpty(rhinoObj.Attributes.Name)
                        ? rhinoObj.Attributes.Name
                        : rhinoObj.Id.ToString().Substring(0, 8),
                    Layer = doc.Layers.FindIndex(rhinoObj.Attributes.LayerIndex)?.FullPath ?? "Default"
                };

                // Read user strings
                var semanticType = rhinoObj.Attributes.GetUserString("semantic_type");
                if (!string.IsNullOrEmpty(semanticType))
                    entry.SemanticType = semanticType;

                var collisionStr = rhinoObj.Attributes.GetUserString("collision");
                if (!string.IsNullOrEmpty(collisionStr))
                    entry.Collision = collisionStr;

                var naniteStr = rhinoObj.Attributes.GetUserString("nanite");
                if (!string.IsNullOrEmpty(naniteStr))
                    entry.Nanite = naniteStr.Equals("true", StringComparison.OrdinalIgnoreCase);

                var materialIntentStr = rhinoObj.Attributes.GetUserString("material_intent");
                if (!string.IsNullOrEmpty(materialIntentStr))
                {
                    try
                    {
                        entry.MaterialIntent = JsonDocument.Parse(materialIntentStr).RootElement.Clone();
                    }
                    catch { /* ignore malformed JSON */ }
                }

                var tagsStr = rhinoObj.Attributes.GetUserString("tags");
                if (!string.IsNullOrEmpty(tagsStr))
                    entry.Tags = tagsStr.Split(',').Select(t => t.Trim()).Where(t => t.Length > 0).ToList();

                manifest.Objects.Add(entry);
            }

            return manifest;
        }

        private static Dictionary<string, object> MakeIssue(string id, string name, string severity, string message)
        {
            return new Dictionary<string, object>
            {
                ["id"] = id,
                ["name"] = name,
                ["severity"] = severity,
                ["message"] = message
            };
        }
    }
}
