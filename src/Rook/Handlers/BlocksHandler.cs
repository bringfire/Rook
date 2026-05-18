using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Rhino;
using Rhino.DocObjects;
using Rhino.FileIO;
using Rhino.Geometry;
using Rook;

namespace Rook.Handlers
{
    /// <summary>
    /// Handles /block and /blocks endpoints for block/instance operations.
    /// </summary>
    public class BlocksHandler
    {
        /// <summary>
        /// GET /blocks - Lists all block definitions in the document.
        /// </summary>
        public ApiResponse GetBlocks()
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            var blocks = new List<Dictionary<string, object>>();

            foreach (var idef in doc.InstanceDefinitions)
            {
                if (idef.IsDeleted) continue;

                var refs = idef.GetReferences(0);
                blocks.Add(new Dictionary<string, object>
                {
                    ["index"] = idef.Index,
                    ["id"] = idef.Id.ToString(),
                    ["name"] = idef.Name,
                    ["description"] = idef.Description ?? "",
                    ["objectCount"] = idef.ObjectCount,
                    ["instanceCount"] = refs?.Length ?? 0
                });
            }

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["count"] = blocks.Count,
                    ["blocks"] = blocks
                }
            };
        }

        /// <summary>
        /// POST /block/insert - Inserts a block instance.
        /// Body: { "name": "MyBlock", "point": [10,10,0], "scale": 1, "rotation": 0 }
        /// </summary>
        public ApiResponse InsertBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            Point3d insertPoint = Point3d.Origin;
            double scale = 1.0;
            double rotation = 0.0; // degrees

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("point", out var ptEl))
            {
                var coords = ptEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                if (coords.Length >= 3)
                {
                    insertPoint = new Point3d(coords[0], coords[1], coords[2]);
                }
            }

            if (request.TryGetValue("scale", out var scaleEl))
            {
                scale = scaleEl.GetDouble();
            }

            if (request.TryGetValue("rotation", out var rotEl))
            {
                rotation = rotEl.GetDouble();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Insert Block");

                // Build transformation
                var xform = Transform.Identity;

                // Scale
                if (Math.Abs(scale - 1.0) > 0.0001)
                {
                    xform = Transform.Scale(Point3d.Origin, scale);
                }

                // Rotation (around Z axis)
                if (Math.Abs(rotation) > 0.0001)
                {
                    var rotXform = Transform.Rotation(rotation * Math.PI / 180.0, Vector3d.ZAxis, Point3d.Origin);
                    xform = rotXform * xform;
                }

                // Translation
                var translateXform = Transform.Translation(insertPoint - Point3d.Origin);
                xform = translateXform * xform;

                var instanceId = doc.Objects.AddInstanceObject(idef.Index, xform);

                doc.Views.Redraw();

                if (instanceId == Guid.Empty)
                {
                    return new ApiResponse { Success = false, Data = "Failed to insert block instance" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["instanceId"] = instanceId.ToString(),
                        ["blockName"] = blockName,
                        ["point"] = new[] { insertPoint.X, insertPoint.Y, insertPoint.Z },
                        ["scale"] = scale,
                        ["rotation"] = rotation
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Insert block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/explode - Explodes a block instance into individual objects.
        /// Body: { "id": "instanceGuid" }
        /// </summary>
        public ApiResponse ExplodeBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            Guid instanceId = Guid.Empty;
            if (request.TryGetValue("id", out var idEl))
            {
                Guid.TryParse(idEl.GetString(), out instanceId);
            }

            if (instanceId == Guid.Empty)
            {
                return new ApiResponse { Success = false, Data = "Valid instance ID required" };
            }

            var rhinoObj = doc.Objects.FindId(instanceId);
            if (rhinoObj == null || !(rhinoObj is InstanceObject instanceObj))
            {
                return new ApiResponse { Success = false, Data = "Object is not a block instance" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Explode Block");

                var xform = instanceObj.InstanceXform;
                var idef = instanceObj.InstanceDefinition;

                var createdIds = new List<string>();

                // Get the geometry from the instance definition and transform it
                foreach (var defObj in idef.GetObjects())
                {
                    var geom = defObj.Geometry.Duplicate();
                    geom.Transform(xform);

                    var attr = defObj.Attributes.Duplicate();
                    Guid newId = Guid.Empty;

                    if (geom is Curve curve)
                        newId = doc.Objects.AddCurve(curve, attr);
                    else if (geom is Brep brep)
                        newId = doc.Objects.AddBrep(brep, attr);
                    else if (geom is Mesh mesh)
                        newId = doc.Objects.AddMesh(mesh, attr);
                    else if (geom is Surface surface)
                        newId = doc.Objects.AddSurface(surface, attr);
                    else if (geom is Point point)
                        newId = doc.Objects.AddPoint(point.Location, attr);
                    else if (geom is Extrusion extrusion)
                        newId = doc.Objects.AddExtrusion(extrusion, attr);

                    if (newId != Guid.Empty)
                    {
                        createdIds.Add(newId.ToString());
                    }
                }

                // Delete the original instance
                doc.Objects.Delete(instanceId, true);

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["explodedInstanceId"] = instanceId.ToString(),
                        ["createdCount"] = createdIds.Count,
                        ["createdIds"] = createdIds
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Explode block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// DELETE /block - Deletes a block definition and optionally all its instances.
        /// Body: { "name": "MyBlock", "deleteInstances": true }
        /// </summary>
        public ApiResponse DeleteBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            bool deleteInstances = true;

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("deleteInstances", out var delEl))
            {
                deleteInstances = delEl.GetBoolean();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Delete Block");

                // Get instance count before deletion
                var instances = idef.GetReferences(0);
                int instanceCount = instances?.Length ?? 0;

                // Delete the block definition (and optionally all instances)
                bool deleted = doc.InstanceDefinitions.Delete(idef.Index, deleteInstances, false);

                doc.Views.Redraw();

                if (!deleted)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to delete block definition '{blockName}'" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["deletedBlock"] = blockName,
                        ["instancesDeleted"] = deleteInstances ? instanceCount : 0,
                        ["instancesExisted"] = instanceCount
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Delete block failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 1: Block Modification Operations
        // =====================================================================

        /// <summary>
        /// POST /block/rename - Renames a block definition.
        /// Body: { "name": "OldName", "newName": "NewName" }
        /// </summary>
        public ApiResponse RenameBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? oldName = null;
            string? newName = null;

            if (request.TryGetValue("name", out var nameEl))
            {
                oldName = nameEl.GetString();
            }

            if (request.TryGetValue("newName", out var newNameEl))
            {
                newName = newNameEl.GetString();
            }

            if (string.IsNullOrEmpty(oldName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            if (string.IsNullOrEmpty(newName))
            {
                return new ApiResponse { Success = false, Data = "New name required" };
            }

            var idef = doc.InstanceDefinitions.Find(oldName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{oldName}' not found" };
            }

            // Check if new name already exists
            var existingDef = doc.InstanceDefinitions.Find(newName);
            if (existingDef != null && existingDef.Index != idef.Index)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{newName}' already exists" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Rename Block");

                bool modified = doc.InstanceDefinitions.Modify(idef.Index, newName, idef.Description, true);

                if (modified)
                {
                    // Migrate user strings stored under "RookBlock::{oldName}" to "RookBlock::{newName}"
                    string oldSection = $"RookBlock::{oldName}";
                    string newSection = $"RookBlock::{newName}";
                    var entries = doc.Strings.GetEntryNames(oldSection);
                    if (entries != null && entries.Length > 0)
                    {
                        foreach (var key in entries)
                        {
                            var val = doc.Strings.GetValue(oldSection, key);
                            doc.Strings.SetString(newSection, key, val);
                            doc.Strings.Delete(oldSection, key);
                        }
                    }
                }

                doc.Views.Redraw();

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to rename block '{oldName}'" };
                }

                var refs = idef.GetReferences(0);

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["oldName"] = oldName,
                        ["newName"] = newName,
                        ["instanceCount"] = refs?.Length ?? 0
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Rename block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/description - Sets or gets block description and URL.
        /// Body: { "name": "BlockName", "description": "...", "url": "...", "urlDescription": "..." }
        /// </summary>
        public ApiResponse SetBlockDescription(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            string? description = null;
            string? url = null;
            string? urlDescription = null;

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("description", out var descEl))
            {
                description = descEl.GetString();
            }

            if (request.TryGetValue("url", out var urlEl))
            {
                url = urlEl.GetString();
            }

            if (request.TryGetValue("urlDescription", out var urlDescEl))
            {
                urlDescription = urlDescEl.GetString();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Set Block Description");

                // Use existing values if not provided
                var newDescription = description ?? idef.Description;
                var newUrl = url ?? idef.Url;
                var newUrlDescription = urlDescription ?? idef.UrlDescription;

                bool modified = doc.InstanceDefinitions.Modify(
                    idef.Index,
                    idef.Name,
                    newDescription,
                    newUrl,
                    newUrlDescription,
                    true
                );

                doc.Views.Redraw();

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                // Re-fetch to get updated values
                idef = doc.InstanceDefinitions[idef.Index];

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["name"] = blockName,
                        ["description"] = idef.Description ?? "",
                        ["url"] = idef.Url ?? "",
                        ["urlDescription"] = idef.UrlDescription ?? ""
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set block description failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// GET /block/info - Gets detailed information about a block definition.
        /// Query: ?name=BlockName
        /// </summary>
        public ApiResponse GetBlockInfo(string? blockName)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            var refs = idef.GetReferences(0);
            var objects = idef.GetObjects();

            var objectInfos = objects.Select(obj => new Dictionary<string, object>
            {
                ["id"] = obj.Id.ToString(),
                ["type"] = obj.ObjectType.ToString(),
                ["layer"] = doc.Layers[obj.Attributes.LayerIndex].FullPath
            }).ToList();

            // Determine block type
            string blockType = "Embedded";
            if (!string.IsNullOrEmpty(idef.SourceArchive))
            {
                // Check update type to determine if it's linked or embedded-and-linked
                blockType = idef.UpdateType == InstanceDefinitionUpdateType.Linked ? "Linked" : "EmbeddedAndLinked";
            }

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["index"] = idef.Index,
                    ["id"] = idef.Id.ToString(),
                    ["name"] = idef.Name,
                    ["description"] = idef.Description ?? "",
                    ["url"] = idef.Url ?? "",
                    ["urlDescription"] = idef.UrlDescription ?? "",
                    ["blockType"] = blockType,
                    ["sourceArchive"] = idef.SourceArchive ?? "",
                    ["objectCount"] = idef.ObjectCount,
                    ["instanceCount"] = refs?.Length ?? 0,
                    ["objects"] = objectInfos
                }
            };
        }

        // =====================================================================
        // Phase 2: Block Geometry Operations
        // =====================================================================

        /// <summary>
        /// POST /block/add-objects - Adds objects to an existing block definition.
        /// Body: { "name": "BlockName", "ids": ["guid1", "guid2"], "deleteOriginals": true }
        /// </summary>
        public ApiResponse AddObjectsToBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            List<Guid> objectIds = new();
            bool deleteOriginals = true;

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("ids", out var idsEl))
            {
                objectIds = idsEl.EnumerateArray()
                    .Select(e => Guid.TryParse(e.GetString(), out var g) ? g : Guid.Empty)
                    .Where(g => g != Guid.Empty)
                    .ToList();
            }

            if (request.TryGetValue("deleteOriginals", out var delEl))
            {
                deleteOriginals = delEl.GetBoolean();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            if (objectIds.Count == 0)
            {
                return new ApiResponse { Success = false, Data = "No valid object IDs provided" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            try
            {
                // Get existing geometry and attributes from block
                var existingObjects = idef.GetObjects();
                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                foreach (var obj in existingObjects)
                {
                    allGeometry.Add(obj.Geometry.Duplicate());
                    allAttributes.Add(obj.Attributes.Duplicate());
                }

                // Get new objects to add
                var newObjects = objectIds
                    .Select(id => doc.Objects.FindId(id))
                    .Where(obj => obj != null)
                    .ToList();

                if (newObjects.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "No valid objects found to add" };
                }

                foreach (var obj in newObjects)
                {
                    allGeometry.Add(obj!.Geometry.Duplicate());
                    allAttributes.Add(obj.Attributes.Duplicate());
                }

                // Modify the block geometry
                using var undo = new UndoScope(doc, "Add Objects to Block");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (modified && deleteOriginals)
                {
                    foreach (var id in objectIds)
                    {
                        doc.Objects.Delete(id, true);
                    }
                }

                doc.Views.Redraw();

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to add objects to block '{blockName}'" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["addedCount"] = newObjects.Count,
                        ["newObjectCount"] = allGeometry.Count,
                        ["originalsDeleted"] = deleteOriginals
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Add objects to block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/remove-objects - Removes objects from a block definition by index.
        /// Body: { "name": "BlockName", "indices": [0, 2] }
        /// </summary>
        public ApiResponse RemoveObjectsFromBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            List<int> indices = new();

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("indices", out var indicesEl))
            {
                indices = indicesEl.EnumerateArray()
                    .Select(e => e.GetInt32())
                    .ToList();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            if (indices.Count == 0)
            {
                return new ApiResponse { Success = false, Data = "No indices provided" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            var existingObjects = idef.GetObjects().ToArray();

            // Validate indices
            foreach (var idx in indices)
            {
                if (idx < 0 || idx >= existingObjects.Length)
                {
                    return new ApiResponse { Success = false, Data = $"Invalid index: {idx}. Block has {existingObjects.Length} objects." };
                }
            }

            // Must keep at least one object
            if (indices.Count >= existingObjects.Length)
            {
                return new ApiResponse { Success = false, Data = "Cannot remove all objects from block. At least one must remain." };
            }

            try
            {
                using var undo = new UndoScope(doc, "Remove Objects from Block");

                // Build new geometry list excluding specified indices
                var indicesToRemove = new HashSet<int>(indices);
                var remainingGeometry = new List<GeometryBase>();
                var remainingAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    if (!indicesToRemove.Contains(i))
                    {
                        remainingGeometry.Add(existingObjects[i].Geometry.Duplicate());
                        remainingAttributes.Add(existingObjects[i].Attributes.Duplicate());
                    }
                }

                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, remainingGeometry, remainingAttributes);

                doc.Views.Redraw();

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to remove objects from block '{blockName}'" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["removedCount"] = indices.Count,
                        ["remainingCount"] = remainingGeometry.Count
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Remove objects from block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/replace-geometry - Replaces all geometry in a block definition.
        /// Body: { "name": "BlockName", "ids": ["guid1", "guid2"], "deleteOriginals": true }
        /// </summary>
        public ApiResponse ReplaceBlockGeometry(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            List<Guid> objectIds = new();
            bool deleteOriginals = true;

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("ids", out var idsEl))
            {
                objectIds = idsEl.EnumerateArray()
                    .Select(e => Guid.TryParse(e.GetString(), out var g) ? g : Guid.Empty)
                    .Where(g => g != Guid.Empty)
                    .ToList();
            }

            if (request.TryGetValue("deleteOriginals", out var delEl))
            {
                deleteOriginals = delEl.GetBoolean();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            if (objectIds.Count == 0)
            {
                return new ApiResponse { Success = false, Data = "No valid object IDs provided" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            try
            {
                // Get new objects
                var newObjects = objectIds
                    .Select(id => doc.Objects.FindId(id))
                    .Where(obj => obj != null)
                    .ToList();

                if (newObjects.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "No valid objects found for replacement" };
                }

                var newGeometry = new List<GeometryBase>();
                var newAttributes = new List<ObjectAttributes>();

                foreach (var obj in newObjects)
                {
                    newGeometry.Add(obj!.Geometry.Duplicate());
                    newAttributes.Add(obj.Attributes.Duplicate());
                }

                using var undo = new UndoScope(doc, "Replace Block Geometry");
                int oldCount = idef.ObjectCount;
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, newGeometry, newAttributes);

                if (modified && deleteOriginals)
                {
                    foreach (var id in objectIds)
                    {
                        doc.Objects.Delete(id, true);
                    }
                }

                doc.Views.Redraw();

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to replace geometry in block '{blockName}'" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["previousObjectCount"] = oldCount,
                        ["newObjectCount"] = newGeometry.Count,
                        ["originalsDeleted"] = deleteOriginals
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Replace block geometry failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-layers - Set layer assignments of objects within a block definition.
        /// Body: { "name": "BlockName", "layer": "LayerName", "mappings": [{ "index": 0, "layer": "OtherLayer" }] }
        /// </summary>
        public ApiResponse SetBlockObjectLayers(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                var blockName = request.GetProperty("name").GetString();
                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                // Resolve bulk layer (applies to all objects)
                int bulkLayerIndex = -1;
                if (request.TryGetProperty("layer", out var layerEl))
                {
                    var layerName = layerEl.GetString();
                    if (!string.IsNullOrEmpty(layerName))
                    {
                        bulkLayerIndex = doc.Layers.FindByFullPath(layerName, -1);
                        if (bulkLayerIndex < 0)
                        {
                            return new ApiResponse { Success = false, Data = $"Layer '{layerName}' not found" };
                        }
                    }
                }

                // Resolve per-object mappings
                var perObjectLayers = new Dictionary<int, int>(); // index → layerIndex
                if (request.TryGetProperty("mappings", out var mappingsEl) && mappingsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var mapping in mappingsEl.EnumerateArray())
                    {
                        int objIndex = mapping.GetProperty("index").GetInt32();
                        var layerName = mapping.GetProperty("layer").GetString();
                        if (string.IsNullOrEmpty(layerName))
                        {
                            return new ApiResponse { Success = false, Data = $"Layer name required in mapping for index {objIndex}" };
                        }
                        int layerIndex = doc.Layers.FindByFullPath(layerName, -1);
                        if (layerIndex < 0)
                        {
                            return new ApiResponse { Success = false, Data = $"Layer '{layerName}' not found (mapping index {objIndex})" };
                        }
                        perObjectLayers[objIndex] = layerIndex;
                    }
                }

                if (bulkLayerIndex < 0 && perObjectLayers.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "Either 'layer' or 'mappings' must be provided" };
                }

                var existingObjects = idef.GetObjects();

                // Validate mapping indices before modifying anything
                foreach (var idx in perObjectLayers.Keys)
                {
                    if (idx < 0 || idx >= existingObjects.Length)
                    {
                        return new ApiResponse { Success = false, Data = $"Object index {idx} out of range (block has {existingObjects.Length} objects)" };
                    }
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                    var attrs = existingObjects[i].Attributes.Duplicate();

                    // Apply bulk layer first, then per-object override
                    if (bulkLayerIndex >= 0)
                    {
                        attrs.LayerIndex = bulkLayerIndex;
                    }
                    if (perObjectLayers.TryGetValue(i, out int mappedLayer))
                    {
                        attrs.LayerIndex = mappedLayer;
                    }

                    allAttributes.Add(attrs);
                }

                using var undo = new UndoScope(doc, "Set Block Object Layers");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                // Return updated object info
                var updatedObjects = idef.GetObjects();
                var objectInfos = updatedObjects.Select((obj, idx) => new Dictionary<string, object>
                {
                    ["index"] = idx,
                    ["id"] = obj.Id.ToString(),
                    ["type"] = obj.ObjectType.ToString(),
                    ["layer"] = doc.Layers[obj.Attributes.LayerIndex].FullPath
                }).ToList();

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["objectCount"] = objectInfos.Count,
                        ["objects"] = objectInfos
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set block object layers failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-layers-batch - Batch set layer assignments for multiple block definitions.
        /// Body: { "items": [{ "name": "BlockName", "layer": "LayerPath" }, ...], "redraw": false }
        /// Single undo scope, deferred redraw, compact summary response.
        /// </summary>
        public ApiResponse SetBlockObjectLayersBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Envelope guard (inherited from PR #21): JsonElement.TryGetProperty
                // throws InvalidOperationException on non-object kinds (array / string /
                // number / bool / null). Without this check, a malformed body falls into
                // the outer try/catch and surfaces as a generic wrapper message rather
                // than the intended shape-error contract.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl) &&
                    (redrawEl.ValueKind == JsonValueKind.True || redrawEl.ValueKind == JsonValueKind.False))
                    redraw = redrawEl.GetBoolean();

                // Pre-resolve unique layer names. Skip malformed items silently here —
                // the main loop records them as skipped so callers still get a summary
                // instead of the whole batch aborting on a single bad entry.
                var layerCache = new Dictionary<string, int>();
                var badLayers = new HashSet<string>();
                foreach (var item in itemsEl.EnumerateArray())
                {
                    if (item.ValueKind != JsonValueKind.Object) continue;
                    if (!item.TryGetProperty("layer", out var lEl) || lEl.ValueKind != JsonValueKind.String) continue;
                    var layerName = lEl.GetString();
                    if (string.IsNullOrEmpty(layerName) || layerCache.ContainsKey(layerName) || badLayers.Contains(layerName))
                        continue;
                    int idx = doc.Layers.FindByFullPath(layerName, -1);
                    if (idx >= 0)
                        layerCache[layerName] = idx;
                    else
                        badLayers.Add(layerName);
                }

                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object>>();

                using var undo = new UndoScope(doc, "Batch Set Block Object Layers");

                foreach (var item in itemsEl.EnumerateArray())
                {
                    string? blockName = null;
                    string? layerName = null;
                    try
                    {
                        if (item.ValueKind != JsonValueKind.Object ||
                            !item.TryGetProperty("name", out var nEl) || !item.TryGetProperty("layer", out var lEl))
                        { skipped++; continue; }
                        blockName = nEl.GetString();
                        layerName = lEl.GetString();
                        if (string.IsNullOrEmpty(blockName) || string.IsNullOrEmpty(layerName))
                        { skipped++; continue; }

                        var idef = doc.InstanceDefinitions.Find(blockName);
                        if (idef == null)
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "not_found" });
                            skipped++; continue;
                        }

                        if (!layerCache.TryGetValue(layerName, out int targetLayerIndex))
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "layer_not_resolved", ["layer"] = layerName });
                            skipped++; continue;
                        }

                        var existingObjects = idef.GetObjects();
                        var allGeometry = new List<GeometryBase>();
                        var allAttributes = new List<ObjectAttributes>();

                        for (int i = 0; i < existingObjects.Length; i++)
                        {
                            allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                            var attrs = existingObjects[i].Attributes.Duplicate();
                            attrs.LayerIndex = targetLayerIndex;
                            allAttributes.Add(attrs);
                        }

                        bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);
                        if (modified)
                            routed++;
                        else
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "modify_failed" });
                            skipped++;
                        }
                    }
                    catch (Exception ex)
                    {
                        errors.Add(new Dictionary<string, object>
                        {
                            ["name"] = blockName ?? "unknown",
                            ["error"] = "exception",
                            ["message"] = ex.Message
                        });
                        skipped++;
                    }
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = itemsEl.GetArrayLength()
                };
                if (badLayers.Count > 0)
                    result["unresolvableLayers"] = badLayers.ToList();
                if (errors.Count > 0)
                    result["errors"] = errors;

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch set block object layers failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-materials-batch - Batch set bulk material for multiple block definitions.
        /// Each item assigns one material to ALL objects within that block definition.
        /// Body: { "items": [{ "name": "BlockName", "material": "MatName" }, ...], "redraw": false }
        /// Single undo scope, deferred redraw, compact summary response.
        /// </summary>
        public ApiResponse SetBlockObjectMaterialsBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Envelope guard (inherited from PR #21): JsonElement.TryGetProperty
                // throws InvalidOperationException on non-object kinds (array / string /
                // number / bool / null). Without this check, a malformed body falls into
                // the outer try/catch and surfaces as a generic wrapper message rather
                // than the intended shape-error contract.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl) &&
                    (redrawEl.ValueKind == JsonValueKind.True || redrawEl.ValueKind == JsonValueKind.False))
                    redraw = redrawEl.GetBoolean();

                // Pre-resolve unique material names. Skip malformed items silently here —
                // the main loop records them as skipped so callers still get a summary
                // instead of the whole batch aborting on a single bad entry.
                var matCache = new Dictionary<string, int>();
                var badMaterials = new HashSet<string>();
                foreach (var item in itemsEl.EnumerateArray())
                {
                    if (item.ValueKind != JsonValueKind.Object) continue;
                    if (!item.TryGetProperty("material", out var mEl) || mEl.ValueKind != JsonValueKind.String) continue;
                    var matName = mEl.GetString();
                    if (string.IsNullOrEmpty(matName) || matCache.ContainsKey(matName) || badMaterials.Contains(matName))
                        continue;
                    int idx = doc.Materials.Find(matName, true);
                    if (idx >= 0)
                        matCache[matName] = idx;
                    else
                        badMaterials.Add(matName);
                }

                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object>>();

                using var undo = new UndoScope(doc, "Batch Set Block Object Materials");

                foreach (var item in itemsEl.EnumerateArray())
                {
                    string? blockName = null;
                    string? matName = null;
                    try
                    {
                        if (item.ValueKind != JsonValueKind.Object ||
                            !item.TryGetProperty("name", out var nEl) || !item.TryGetProperty("material", out var mEl))
                        { skipped++; continue; }
                        blockName = nEl.GetString();
                        matName = mEl.GetString();
                        if (string.IsNullOrEmpty(blockName) || string.IsNullOrEmpty(matName))
                        { skipped++; continue; }

                        var idef = doc.InstanceDefinitions.Find(blockName);
                        if (idef == null)
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "not_found" });
                            skipped++; continue;
                        }

                        if (!matCache.TryGetValue(matName, out int targetMatIndex))
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "material_not_resolved", ["material"] = matName });
                            skipped++; continue;
                        }

                        var existingObjects = idef.GetObjects();
                        var allGeometry = new List<GeometryBase>();
                        var allAttributes = new List<ObjectAttributes>();

                        for (int i = 0; i < existingObjects.Length; i++)
                        {
                            allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                            var attrs = existingObjects[i].Attributes.Duplicate();
                            attrs.MaterialSource = ObjectMaterialSource.MaterialFromObject;
                            attrs.MaterialIndex = targetMatIndex;
                            allAttributes.Add(attrs);
                        }

                        bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);
                        if (modified)
                            routed++;
                        else
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "modify_failed" });
                            skipped++;
                        }
                    }
                    catch (Exception ex)
                    {
                        errors.Add(new Dictionary<string, object>
                        {
                            ["name"] = blockName ?? "unknown",
                            ["error"] = "exception",
                            ["message"] = ex.Message
                        });
                        skipped++;
                    }
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = itemsEl.GetArrayLength()
                };
                if (badMaterials.Count > 0)
                    result["unresolvableMaterials"] = badMaterials.ToList();
                if (errors.Count > 0)
                    result["errors"] = errors;

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch set block object materials failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-object-colors-batch - Batch set bulk object color for multiple block definitions.
        /// Each item assigns one RGB color to ALL objects within that block definition.
        /// Body: { "items": [{ "name": "BlockName", "color": [r, g, b] }, ...], "redraw": false }
        /// </summary>
        public ApiResponse SetBlockObjectColorsBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Envelope guard (inherited from PR #21): JsonElement.TryGetProperty
                // throws InvalidOperationException on non-object kinds (array / string /
                // number / bool / null). Without this check, a malformed body falls into
                // the outer try/catch and surfaces as a generic wrapper message rather
                // than the intended shape-error contract.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl) &&
                    (redrawEl.ValueKind == JsonValueKind.True || redrawEl.ValueKind == JsonValueKind.False))
                    redraw = redrawEl.GetBoolean();

                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object>>();

                using var undo = new UndoScope(doc, "Batch Set Block Object Colors");

                foreach (var item in itemsEl.EnumerateArray())
                {
                    string? blockName = null;
                    try
                    {
                        if (item.ValueKind != JsonValueKind.Object ||
                            !item.TryGetProperty("name", out var nEl) || !item.TryGetProperty("color", out var cEl) ||
                            cEl.ValueKind != JsonValueKind.Array)
                        { skipped++; continue; }
                        blockName = nEl.GetString();
                        if (string.IsNullOrEmpty(blockName))
                        { skipped++; continue; }

                        var rgb = cEl.EnumerateArray().Select(e => Math.Min(Math.Max(e.GetInt32(), 0), 255)).ToArray();
                        if (rgb.Length < 3)
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "color_needs_3_channels" });
                            skipped++; continue;
                        }
                        var color = System.Drawing.Color.FromArgb(rgb[0], rgb[1], rgb[2]);

                        var idef = doc.InstanceDefinitions.Find(blockName);
                        if (idef == null)
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "not_found" });
                            skipped++; continue;
                        }

                        var existingObjects = idef.GetObjects();
                        var allGeometry = new List<GeometryBase>();
                        var allAttributes = new List<ObjectAttributes>();

                        for (int i = 0; i < existingObjects.Length; i++)
                        {
                            allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                            var attrs = existingObjects[i].Attributes.Duplicate();
                            attrs.ColorSource = ObjectColorSource.ColorFromObject;
                            attrs.ObjectColor = color;
                            allAttributes.Add(attrs);
                        }

                        bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);
                        if (modified) routed++;
                        else
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "modify_failed" });
                            skipped++;
                        }
                    }
                    catch (Exception ex)
                    {
                        errors.Add(new Dictionary<string, object>
                        {
                            ["name"] = blockName ?? "unknown",
                            ["error"] = "exception",
                            ["message"] = ex.Message
                        });
                        skipped++;
                    }
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = itemsEl.GetArrayLength()
                };
                if (errors.Count > 0)
                    result["errors"] = errors;

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch set block object colors failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-object-user-strings-batch - Batch stamp user strings on all objects within multiple block definitions.
        /// Each item applies the given key/value map to every object in that block definition.
        /// Body: { "items": [{ "name": "BlockName", "userStrings": {"k": "v"} }, ...], "redraw": false }
        /// </summary>
        public ApiResponse SetBlockObjectUserStringsBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Envelope guard (inherited from PR #21): JsonElement.TryGetProperty
                // throws InvalidOperationException on non-object kinds (array / string /
                // number / bool / null). Without this check, a malformed body falls into
                // the outer try/catch and surfaces as a generic wrapper message rather
                // than the intended shape-error contract.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl) &&
                    (redrawEl.ValueKind == JsonValueKind.True || redrawEl.ValueKind == JsonValueKind.False))
                    redraw = redrawEl.GetBoolean();

                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object>>();

                using var undo = new UndoScope(doc, "Batch Set Block Object User Strings");

                foreach (var item in itemsEl.EnumerateArray())
                {
                    string? blockName = null;
                    try
                    {
                        if (item.ValueKind != JsonValueKind.Object ||
                            !item.TryGetProperty("name", out var nEl) || !item.TryGetProperty("userStrings", out var usEl) ||
                            usEl.ValueKind != JsonValueKind.Object)
                        { skipped++; continue; }
                        blockName = nEl.GetString();
                        if (string.IsNullOrEmpty(blockName))
                        { skipped++; continue; }

                        var kvs = new Dictionary<string, string>();
                        foreach (var prop in usEl.EnumerateObject())
                            kvs[prop.Name] = prop.Value.GetString() ?? "";

                        if (kvs.Count == 0)
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "userStrings_empty" });
                            skipped++; continue;
                        }

                        var idef = doc.InstanceDefinitions.Find(blockName);
                        if (idef == null)
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "not_found" });
                            skipped++; continue;
                        }

                        var existingObjects = idef.GetObjects();
                        var allGeometry = new List<GeometryBase>();
                        var allAttributes = new List<ObjectAttributes>();

                        for (int i = 0; i < existingObjects.Length; i++)
                        {
                            allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                            var attrs = existingObjects[i].Attributes.Duplicate();
                            foreach (var kvp in kvs)
                                attrs.SetUserString(kvp.Key, kvp.Value);
                            allAttributes.Add(attrs);
                        }

                        bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);
                        if (modified) routed++;
                        else
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "modify_failed" });
                            skipped++;
                        }
                    }
                    catch (Exception ex)
                    {
                        errors.Add(new Dictionary<string, object>
                        {
                            ["name"] = blockName ?? "unknown",
                            ["error"] = "exception",
                            ["message"] = ex.Message
                        });
                        skipped++;
                    }
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = itemsEl.GetArrayLength()
                };
                if (errors.Count > 0)
                    result["errors"] = errors;

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch set block object user strings failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-object-names-batch - Batch set object name on all objects within multiple block definitions.
        /// Each item assigns one name to ALL objects within that block definition (useful for tagging Revit family/type).
        /// Body: { "items": [{ "name": "BlockName", "objectName": "W-BEAM-01" }, ...], "redraw": false }
        /// </summary>
        public ApiResponse SetBlockObjectNamesBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Envelope guard (inherited from PR #21): JsonElement.TryGetProperty
                // throws InvalidOperationException on non-object kinds (array / string /
                // number / bool / null). Without this check, a malformed body falls into
                // the outer try/catch and surfaces as a generic wrapper message rather
                // than the intended shape-error contract.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl) &&
                    (redrawEl.ValueKind == JsonValueKind.True || redrawEl.ValueKind == JsonValueKind.False))
                    redraw = redrawEl.GetBoolean();

                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object>>();

                using var undo = new UndoScope(doc, "Batch Set Block Object Names");

                foreach (var item in itemsEl.EnumerateArray())
                {
                    string? blockName = null;
                    string? objName = null;
                    try
                    {
                        if (item.ValueKind != JsonValueKind.Object ||
                            !item.TryGetProperty("name", out var nEl) || !item.TryGetProperty("objectName", out var oEl))
                        { skipped++; continue; }
                        blockName = nEl.GetString();
                        objName = oEl.GetString() ?? "";
                        if (string.IsNullOrEmpty(blockName))
                        { skipped++; continue; }

                        var idef = doc.InstanceDefinitions.Find(blockName);
                        if (idef == null)
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "not_found" });
                            skipped++; continue;
                        }

                        var existingObjects = idef.GetObjects();
                        var allGeometry = new List<GeometryBase>();
                        var allAttributes = new List<ObjectAttributes>();

                        for (int i = 0; i < existingObjects.Length; i++)
                        {
                            allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                            var attrs = existingObjects[i].Attributes.Duplicate();
                            attrs.Name = objName;
                            allAttributes.Add(attrs);
                        }

                        bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);
                        if (modified) routed++;
                        else
                        {
                            errors.Add(new Dictionary<string, object> { ["name"] = blockName, ["error"] = "modify_failed" });
                            skipped++;
                        }
                    }
                    catch (Exception ex)
                    {
                        errors.Add(new Dictionary<string, object>
                        {
                            ["name"] = blockName ?? "unknown",
                            ["error"] = "exception",
                            ["message"] = ex.Message
                        });
                        skipped++;
                    }
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = itemsEl.GetArrayLength()
                };
                if (errors.Count > 0)
                    result["errors"] = errors;

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch set block object names failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-materials - Set material assignments of objects within a block definition.
        /// Body: { "name": "BlockName", "material": "MatName", "mappings": [{ "index": 0, "material": "OtherMat" }] }
        /// </summary>
        public ApiResponse SetBlockObjectMaterials(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                var blockName = request.GetProperty("name").GetString();
                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                // Resolve bulk material (applies to all objects)
                int bulkMatIndex = -1;
                if (request.TryGetProperty("material", out var matEl))
                {
                    var matName = matEl.GetString();
                    if (!string.IsNullOrEmpty(matName))
                    {
                        bulkMatIndex = doc.Materials.Find(matName, true);
                        if (bulkMatIndex < 0)
                        {
                            return new ApiResponse { Success = false, Data = $"Material '{matName}' not found" };
                        }
                    }
                }

                // Resolve per-object mappings
                var perObjectMats = new Dictionary<int, int>(); // index → materialIndex
                if (request.TryGetProperty("mappings", out var mappingsEl) && mappingsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var mapping in mappingsEl.EnumerateArray())
                    {
                        int objIndex = mapping.GetProperty("index").GetInt32();
                        var matName = mapping.GetProperty("material").GetString();
                        if (string.IsNullOrEmpty(matName))
                        {
                            return new ApiResponse { Success = false, Data = $"Material name required in mapping for index {objIndex}" };
                        }
                        int matIndex = doc.Materials.Find(matName, true);
                        if (matIndex < 0)
                        {
                            return new ApiResponse { Success = false, Data = $"Material '{matName}' not found (mapping index {objIndex})" };
                        }
                        perObjectMats[objIndex] = matIndex;
                    }
                }

                if (bulkMatIndex < 0 && perObjectMats.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "Either 'material' or 'mappings' must be provided" };
                }

                var existingObjects = idef.GetObjects();

                // Validate mapping indices before modifying anything
                foreach (var idx in perObjectMats.Keys)
                {
                    if (idx < 0 || idx >= existingObjects.Length)
                    {
                        return new ApiResponse { Success = false, Data = $"Object index {idx} out of range (block has {existingObjects.Length} objects)" };
                    }
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                    var attrs = existingObjects[i].Attributes.Duplicate();

                    // Apply bulk material first, then per-object override
                    if (bulkMatIndex >= 0)
                    {
                        attrs.MaterialSource = ObjectMaterialSource.MaterialFromObject;
                        attrs.MaterialIndex = bulkMatIndex;
                    }
                    if (perObjectMats.TryGetValue(i, out int mappedMat))
                    {
                        attrs.MaterialSource = ObjectMaterialSource.MaterialFromObject;
                        attrs.MaterialIndex = mappedMat;
                    }

                    allAttributes.Add(attrs);
                }

                using var undo = new UndoScope(doc, "Set Block Object Materials");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                // Return updated object info with material details
                var updatedObjects = idef.GetObjects();
                var objectInfos = updatedObjects.Select((obj, idx) =>
                {
                    var info = new Dictionary<string, object>
                    {
                        ["index"] = idx,
                        ["id"] = obj.Id.ToString(),
                        ["type"] = obj.ObjectType.ToString(),
                        ["layer"] = doc.Layers[obj.Attributes.LayerIndex].FullPath,
                        ["materialSource"] = obj.Attributes.MaterialSource.ToString()
                    };

                    if (obj.Attributes.MaterialSource == ObjectMaterialSource.MaterialFromObject &&
                        obj.Attributes.MaterialIndex >= 0 &&
                        obj.Attributes.MaterialIndex < doc.Materials.Count)
                    {
                        info["material"] = doc.Materials[obj.Attributes.MaterialIndex].Name;
                    }

                    return info;
                }).ToList();

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["objectCount"] = objectInfos.Count,
                        ["objects"] = objectInfos
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set block object materials failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 3: Block Instance Operations
        // =====================================================================

        /// <summary>
        /// GET /block/instances - Gets all instances of a block definition.
        /// Query: ?name=BlockName&depth=0
        /// </summary>
        public ApiResponse GetBlockInstances(string? blockName, int depth = 0)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            var refs = idef.GetReferences(depth);
            var instances = new List<Dictionary<string, object>>();

            if (refs != null)
            {
                foreach (var inst in refs)
                {
                    var xform = inst.InstanceXform;

                    // Extract transform components
                    var insertionPoint = new Point3d(xform.M03, xform.M13, xform.M23);

                    // Approximate scale (assuming uniform or near-uniform scaling)
                    double scaleX = Math.Sqrt(xform.M00 * xform.M00 + xform.M10 * xform.M10 + xform.M20 * xform.M20);
                    double scaleY = Math.Sqrt(xform.M01 * xform.M01 + xform.M11 * xform.M11 + xform.M21 * xform.M21);
                    double scaleZ = Math.Sqrt(xform.M02 * xform.M02 + xform.M12 * xform.M12 + xform.M22 * xform.M22);

                    // Extract rotation around Z axis (degrees) by removing scale from the matrix columns
                    double rotationDeg = 0;
                    if (scaleX > 1e-10)
                    {
                        double rotationRad = Math.Atan2(xform.M10 / scaleX, xform.M00 / scaleX);
                        rotationDeg = Math.Round(rotationRad * (180.0 / Math.PI), 2);
                    }

                    instances.Add(new Dictionary<string, object>
                    {
                        ["id"] = inst.Id.ToString(),
                        ["insertionPoint"] = new[] { insertionPoint.X, insertionPoint.Y, insertionPoint.Z },
                        ["scale"] = new[] { scaleX, scaleY, scaleZ },
                        ["rotation"] = rotationDeg,
                        ["layer"] = doc.Layers[inst.Attributes.LayerIndex].FullPath,
                        ["name"] = inst.Name ?? ""
                    });
                }
            }

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["blockName"] = blockName,
                    ["depth"] = depth,
                    ["instanceCount"] = instances.Count,
                    ["instances"] = instances
                }
            };
        }

        /// <summary>
        /// POST /block/replace-instance - Replaces an instance's block definition with another.
        /// Body: { "instanceId": "guid", "newBlockName": "OtherBlock" }
        /// </summary>
        public ApiResponse ReplaceBlockInstance(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            Guid instanceId = Guid.Empty;
            string? newBlockName = null;

            if (request.TryGetValue("instanceId", out var idEl))
            {
                Guid.TryParse(idEl.GetString(), out instanceId);
            }

            if (request.TryGetValue("newBlockName", out var nameEl))
            {
                newBlockName = nameEl.GetString();
            }

            if (instanceId == Guid.Empty)
            {
                return new ApiResponse { Success = false, Data = "Valid instance ID required" };
            }

            if (string.IsNullOrEmpty(newBlockName))
            {
                return new ApiResponse { Success = false, Data = "New block name required" };
            }

            var rhinoObj = doc.Objects.FindId(instanceId);
            if (rhinoObj == null || !(rhinoObj is InstanceObject instanceObj))
            {
                return new ApiResponse { Success = false, Data = "Object is not a block instance" };
            }

            var newIdef = doc.InstanceDefinitions.Find(newBlockName);
            if (newIdef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{newBlockName}' not found" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Replace Block Instance");

                string oldBlockName = instanceObj.InstanceDefinition.Name;
                bool replaced = doc.Objects.ReplaceInstanceObject(instanceId, newIdef.Index);

                doc.Views.Redraw();

                if (!replaced)
                {
                    return new ApiResponse { Success = false, Data = "Failed to replace block instance" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["instanceId"] = instanceId.ToString(),
                        ["oldBlockName"] = oldBlockName,
                        ["newBlockName"] = newBlockName
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Replace block instance failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/reset-scale - Resets an instance's scale to 1,1,1.
        /// Body: { "id": "instance-guid" }
        /// </summary>
        public ApiResponse ResetBlockScale(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            Guid instanceId = Guid.Empty;
            if (request.TryGetValue("id", out var idEl))
            {
                Guid.TryParse(idEl.GetString(), out instanceId);
            }

            if (instanceId == Guid.Empty)
            {
                return new ApiResponse { Success = false, Data = "Valid instance ID required" };
            }

            var rhinoObj = doc.Objects.FindId(instanceId);
            if (rhinoObj == null || !(rhinoObj is InstanceObject instanceObj))
            {
                return new ApiResponse { Success = false, Data = "Object is not a block instance" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Reset Block Scale");

                var oldXform = instanceObj.InstanceXform;

                // Extract translation (position)
                var translation = new Vector3d(oldXform.M03, oldXform.M13, oldXform.M23);

                // Create new transform with just translation (no scale/rotation)
                // Actually, we want to preserve rotation but reset scale
                // For simplicity, we'll just use identity scale with same position
                var newXform = Transform.Translation(translation);

                // Delete old instance and create new one
                var idefIndex = instanceObj.InstanceDefinition.Index;
                var attrs = instanceObj.Attributes.Duplicate();

                doc.Objects.Delete(instanceId, true);
                var newId = doc.Objects.AddInstanceObject(idefIndex, newXform, attrs);

                doc.Views.Redraw();

                if (newId == Guid.Empty)
                {
                    return new ApiResponse { Success = false, Data = "Failed to reset block scale" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["oldInstanceId"] = instanceId.ToString(),
                        ["newInstanceId"] = newId.ToString(),
                        ["scale"] = new[] { 1.0, 1.0, 1.0 }
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Reset block scale failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 4: Linked Block Operations
        // =====================================================================

        /// <summary>
        /// POST /block/link - Creates a linked block from an external file.
        /// Body: { "path": "C:/path/to/file.3dm", "name": "LinkedBlock" }
        /// </summary>
        public ApiResponse LinkBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? path = null;
            string? blockName = null;
            string updateTypeStr = "linked";
            double[]? insertionPoint = null;

            if (request.TryGetValue("path", out var pathEl))
            {
                path = pathEl.GetString();
            }

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("updateType", out var updateTypeEl))
            {
                updateTypeStr = updateTypeEl.GetString() ?? "linked";
            }

            if (request.TryGetValue("insertionPoint", out var insertionEl) && insertionEl.ValueKind == JsonValueKind.Array)
            {
                var arr = insertionEl.EnumerateArray().ToArray();
                if (arr.Length >= 3)
                {
                    insertionPoint = new double[] { arr[0].GetDouble(), arr[1].GetDouble(), arr[2].GetDouble() };
                }
            }

            if (string.IsNullOrEmpty(path))
            {
                return new ApiResponse { Success = false, Data = "File path required" };
            }

            if (!System.IO.File.Exists(path))
            {
                return new ApiResponse { Success = false, Data = $"File not found: {path}" };
            }

            if (string.IsNullOrEmpty(blockName))
            {
                blockName = System.IO.Path.GetFileNameWithoutExtension(path);
            }

            // Check if block name already exists
            var existingDef = doc.InstanceDefinitions.Find(blockName);
            if (existingDef != null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' already exists" };
            }

            // Determine update type
            InstanceDefinitionUpdateType updateType;
            switch (updateTypeStr.ToLowerInvariant())
            {
                case "static":
                    updateType = InstanceDefinitionUpdateType.Static;
                    break;
                case "linkedandembedded":
                case "linked_and_embedded":
                    updateType = InstanceDefinitionUpdateType.LinkedAndEmbedded;
                    break;
                case "linked":
                default:
                    updateType = InstanceDefinitionUpdateType.Linked;
                    break;
            }

            try
            {
                using var undo = new UndoScope(doc, "Link Block");

                // Read the external .3dm file using RhinoCommon
                var file3dm = File3dm.Read(path);
                if (file3dm == null)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to read file: {path}" };
                }

                // Extract geometry and attributes from the file
                var geometries = new List<GeometryBase>();
                var attributes = new List<ObjectAttributes>();

                foreach (var obj in file3dm.Objects)
                {
                    if (obj.Geometry != null)
                    {
                        geometries.Add(obj.Geometry.Duplicate());
                        attributes.Add(obj.Attributes.Duplicate());
                    }
                }

                if (geometries.Count == 0)
                {
                    file3dm.Dispose();
                    return new ApiResponse { Success = false, Data = "No geometry found in file" };
                }

                // Calculate base point (use bounding box center or origin)
                var allBbox = BoundingBox.Empty;
                foreach (var geom in geometries)
                {
                    allBbox.Union(geom.GetBoundingBox(true));
                }
                var basePoint = allBbox.IsValid ? allBbox.Min : Point3d.Origin;

                // Create the block definition with geometry from the file
                int idefIndex = doc.InstanceDefinitions.Add(
                    blockName,
                    $"Linked from: {path}",
                    basePoint,
                    geometries,
                    attributes
                );

                if (idefIndex < 0)
                {
                    file3dm.Dispose();
                    return new ApiResponse { Success = false, Data = "Failed to create block definition" };
                }

                // Convert to linked block by setting the source archive
                var fileRef = FileReference.CreateFromFullPath(path);
                bool linkSuccess = doc.InstanceDefinitions.ModifySourceArchive(
                    idefIndex,
                    fileRef,
                    updateType,
                    true  // quiet - suppress dialogs
                );

                // Optionally insert an instance
                Guid? instanceId = null;
                if (insertionPoint != null)
                {
                    var insertPt = new Point3d(insertionPoint[0], insertionPoint[1], insertionPoint[2]);
                    var xform = Transform.Translation(insertPt - basePoint);
                    instanceId = doc.Objects.AddInstanceObject(idefIndex, xform);
                }

                file3dm.Dispose();
                doc.Views.Redraw();

                var newDef = doc.InstanceDefinitions[idefIndex];
                var result = new Dictionary<string, object>
                {
                    ["name"] = newDef.Name,
                    ["index"] = idefIndex,
                    ["sourcePath"] = path,
                    ["updateType"] = updateType.ToString(),
                    ["objectCount"] = geometries.Count,
                    ["isLinked"] = linkSuccess
                };

                if (instanceId.HasValue && instanceId.Value != Guid.Empty)
                {
                    result["instanceId"] = instanceId.Value.ToString();
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = result
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Link block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/refresh - Refreshes a linked block from its source file.
        /// Body: { "name": "LinkedBlock" }
        /// </summary>
        public ApiResponse RefreshLinkedBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            if (string.IsNullOrEmpty(idef.SourceArchive))
            {
                return new ApiResponse { Success = false, Data = $"Block '{blockName}' is not a linked block" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Refresh Linked Block");

                bool refreshed = doc.InstanceDefinitions.RefreshLinkedBlock(idef);

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = refreshed,
                    Data = new Dictionary<string, object>
                    {
                        ["name"] = blockName,
                        ["sourcePath"] = idef.SourceArchive,
                        ["refreshed"] = refreshed
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Refresh linked block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/unlink - Converts a linked block to embedded.
        /// Body: { "name": "LinkedBlock" }
        /// </summary>
        public ApiResponse UnlinkBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? blockName = null;
            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            string oldSourcePath = idef.SourceArchive ?? "";
            if (string.IsNullOrEmpty(oldSourcePath))
            {
                return new ApiResponse { Success = false, Data = $"Block '{blockName}' is not a linked block" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Unlink Block");

                bool unlinked = doc.InstanceDefinitions.DestroySourceArchive(idef, true);

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = unlinked,
                    Data = new Dictionary<string, object>
                    {
                        ["name"] = blockName,
                        ["previousSourcePath"] = oldSourcePath,
                        ["unlinked"] = unlinked
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Unlink block failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 5: Block Utility Operations
        // =====================================================================

        /// <summary>
        /// POST /block/purge - Removes unused or deleted block definitions.
        /// Body: { "unused": true, "deleted": true }
        /// </summary>
        public ApiResponse PurgeBlocks(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            var request = string.IsNullOrEmpty(body)
                ? new Dictionary<string, JsonElement>()
                : JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body) ?? new();

            bool purgeUnused = true;
            bool purgeDeleted = true;

            if (request.TryGetValue("unused", out var unusedEl))
            {
                purgeUnused = unusedEl.GetBoolean();
            }

            if (request.TryGetValue("deleted", out var deletedEl))
            {
                purgeDeleted = deletedEl.GetBoolean();
            }

            try
            {
                using var undo = new UndoScope(doc, "Purge Blocks");

                var purgedNames = new List<string>();
                var indicesToPurge = new List<int>();

                // Count active definitions BEFORE purging (enumeration is stale immediately after Purge/Compact)
                int countBefore = 0;
                foreach (var idef in doc.InstanceDefinitions)
                {
                    if (!idef.IsDeleted) countBefore++;
                }

                // Collect blocks to purge (don't modify collection during iteration)
                if (purgeUnused)
                {
                    foreach (var idef in doc.InstanceDefinitions)
                    {
                        if (idef.IsDeleted) continue;

                        var refs = idef.GetReferences(0);
                        if (refs == null || refs.Length == 0)
                        {
                            purgedNames.Add(idef.Name);
                            indicesToPurge.Add(idef.Index);
                        }
                    }

                    // Purge collected indices (reverse order to avoid index shifting)
                    for (int i = indicesToPurge.Count - 1; i >= 0; i--)
                    {
                        doc.InstanceDefinitions.Purge(indicesToPurge[i]);
                    }
                }

                if (purgeDeleted)
                {
                    doc.InstanceDefinitions.Compact(true);
                }

                // Derive remaining from pre-purge count (enumeration is stale immediately after Purge/Compact)
                int remainingCount = countBefore - purgedNames.Count;

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["purgedCount"] = purgedNames.Count,
                        ["purgedNames"] = purgedNames,
                        ["remainingCount"] = remainingCount
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Purge blocks failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/duplicate - Duplicates a block definition with a new name.
        /// Body: { "name": "SourceBlock", "newName": "CopiedBlock" }
        /// </summary>
        public ApiResponse DuplicateBlock(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(body))
            {
                return new ApiResponse { Success = false, Data = "Request body required" };
            }

            var request = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);
            if (request == null)
            {
                return new ApiResponse { Success = false, Data = "Invalid request body" };
            }

            string? sourceName = null;
            string? newName = null;

            if (request.TryGetValue("name", out var nameEl))
            {
                sourceName = nameEl.GetString();
            }

            if (request.TryGetValue("newName", out var newNameEl))
            {
                newName = newNameEl.GetString();
            }

            if (string.IsNullOrEmpty(sourceName))
            {
                return new ApiResponse { Success = false, Data = "Source block name required" };
            }

            if (string.IsNullOrEmpty(newName))
            {
                return new ApiResponse { Success = false, Data = "New block name required" };
            }

            var sourceIdef = doc.InstanceDefinitions.Find(sourceName);
            if (sourceIdef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{sourceName}' not found" };
            }

            // Check if new name already exists
            var existingDef = doc.InstanceDefinitions.Find(newName);
            if (existingDef != null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{newName}' already exists" };
            }

            try
            {
                using var undo = new UndoScope(doc, "Duplicate Block");

                // Copy geometry and attributes from source
                var sourceObjects = sourceIdef.GetObjects();
                var geometries = sourceObjects.Select(o => o.Geometry.Duplicate()).ToArray();
                var attributes = sourceObjects.Select(o => o.Attributes.Duplicate()).ToArray();

                // Get the base point from an instance if one exists, otherwise use origin
                Point3d basePoint = Point3d.Origin;
                var refs = sourceIdef.GetReferences(0);
                if (refs != null && refs.Length > 0)
                {
                    var xform = refs[0].InstanceXform;
                    basePoint = new Point3d(xform.M03, xform.M13, xform.M23);
                }

                // Create new block definition
                var newIndex = doc.InstanceDefinitions.Add(
                    newName,
                    sourceIdef.Description,
                    basePoint,
                    geometries!,
                    attributes
                );

                doc.Views.Redraw();

                if (newIndex < 0)
                {
                    return new ApiResponse { Success = false, Data = "Failed to create duplicate block" };
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["sourceName"] = sourceName,
                        ["newName"] = newName,
                        ["newIndex"] = newIndex,
                        ["objectCount"] = geometries.Length
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Duplicate block failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// GET /block/nested - Gets the nested block hierarchy.
        /// Query: ?name=ParentBlock
        /// </summary>
        public ApiResponse GetNestedBlocks(string? blockName)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            var hierarchy = BuildNestedHierarchy(doc, idef, new HashSet<int>());

            return new ApiResponse
            {
                Success = true,
                Data = hierarchy
            };
        }

        private Dictionary<string, object> BuildNestedHierarchy(RhinoDoc doc, InstanceDefinition idef, HashSet<int> visited)
        {
            var result = new Dictionary<string, object>
            {
                ["name"] = idef.Name,
                ["objectCount"] = idef.ObjectCount
            };

            // Prevent infinite recursion for circular references
            if (visited.Contains(idef.Index))
            {
                result["circular"] = true;
                result["children"] = new List<Dictionary<string, object>>();
                return result;
            }

            visited.Add(idef.Index);

            var children = new List<Dictionary<string, object>>();

            // Find nested blocks (instance objects within this block)
            foreach (var obj in idef.GetObjects())
            {
                if (obj is InstanceObject nestedInstance)
                {
                    var nestedDef = nestedInstance.InstanceDefinition;
                    children.Add(BuildNestedHierarchy(doc, nestedDef, new HashSet<int>(visited)));
                }
            }

            result["children"] = children;
            return result;
        }

        // =====================================================================
        // Phase 6: Instance Property Operations
        // =====================================================================

        /// <summary>
        /// POST /block/set-instance-properties - Set properties on specific block instances.
        /// Body: { "ids": ["guid1", "guid2"], "name": "Chair_01", "layer": "Furniture", "color": [255,0,0], "material": "Leather" }
        /// All property fields are optional — only provided ones are changed.
        /// </summary>
        public ApiResponse SetInstanceProperties(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);

                // Parse instance IDs (required)
                var instanceIds = new List<Guid>();
                if (request.TryGetProperty("ids", out var idsEl) && idsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var el in idsEl.EnumerateArray())
                    {
                        if (Guid.TryParse(el.GetString(), out var guid))
                        {
                            instanceIds.Add(guid);
                        }
                    }
                }
                else if (request.TryGetProperty("id", out var idEl))
                {
                    if (Guid.TryParse(idEl.GetString(), out var guid))
                    {
                        instanceIds.Add(guid);
                    }
                }

                if (instanceIds.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "At least one instance ID required ('id' or 'ids')" };
                }

                // Pre-resolve optional properties
                int? layerIndex = null;
                if (request.TryGetProperty("layer", out var layerEl))
                {
                    var layerName = layerEl.GetString();
                    if (!string.IsNullOrEmpty(layerName))
                    {
                        int idx = doc.Layers.FindByFullPath(layerName, -1);
                        if (idx < 0)
                        {
                            return new ApiResponse { Success = false, Data = $"Layer '{layerName}' not found" };
                        }
                        layerIndex = idx;
                    }
                }

                int? matIndex = null;
                if (request.TryGetProperty("material", out var matEl))
                {
                    var matName = matEl.GetString();
                    if (!string.IsNullOrEmpty(matName))
                    {
                        int idx = doc.Materials.Find(matName, true);
                        if (idx < 0)
                        {
                            return new ApiResponse { Success = false, Data = $"Material '{matName}' not found" };
                        }
                        matIndex = idx;
                    }
                }

                System.Drawing.Color? color = null;
                if (request.TryGetProperty("color", out var colorEl) && colorEl.ValueKind == JsonValueKind.Array)
                {
                    var rgb = colorEl.EnumerateArray().Select(e => Math.Min(Math.Max(e.GetInt32(), 0), 255)).ToArray();
                    if (rgb.Length >= 3)
                    {
                        color = System.Drawing.Color.FromArgb(rgb[0], rgb[1], rgb[2]);
                    }
                }

                string? newName = null;
                if (request.TryGetProperty("name", out var nameEl))
                {
                    newName = nameEl.GetString();
                }

                // Apply to each instance
                using var undo = new UndoScope(doc, "Set Instance Properties");
                var results = new List<Dictionary<string, object>>();

                foreach (var guid in instanceIds)
                {
                    var rhinoObj = doc.Objects.FindId(guid);
                    if (rhinoObj == null || !(rhinoObj is InstanceObject inst))
                    {
                        results.Add(new Dictionary<string, object>
                        {
                            ["id"] = guid.ToString(),
                            ["success"] = false,
                            ["error"] = "Not found or not a block instance"
                        });
                        continue;
                    }

                    var attrs = inst.Attributes.Duplicate();

                    if (newName != null)
                    {
                        attrs.Name = newName;
                    }
                    if (layerIndex.HasValue)
                    {
                        attrs.LayerIndex = layerIndex.Value;
                    }
                    if (color.HasValue)
                    {
                        attrs.ColorSource = ObjectColorSource.ColorFromObject;
                        attrs.ObjectColor = color.Value;
                    }
                    if (matIndex.HasValue)
                    {
                        attrs.MaterialSource = ObjectMaterialSource.MaterialFromObject;
                        attrs.MaterialIndex = matIndex.Value;
                    }

                    // Apply user strings if provided
                    if (request.TryGetProperty("userStrings", out var usEl) && usEl.ValueKind == JsonValueKind.Object)
                    {
                        foreach (var prop in usEl.EnumerateObject())
                        {
                            attrs.SetUserString(prop.Name, prop.Value.GetString() ?? "");
                        }
                    }

                    doc.Objects.ModifyAttributes(inst, attrs, true);

                    var info = new Dictionary<string, object>
                    {
                        ["id"] = guid.ToString(),
                        ["success"] = true,
                        ["name"] = attrs.Name ?? "",
                        ["layer"] = doc.Layers[attrs.LayerIndex].FullPath
                    };

                    if (attrs.ColorSource == ObjectColorSource.ColorFromObject)
                    {
                        info["color"] = new[] { attrs.ObjectColor.R, attrs.ObjectColor.G, attrs.ObjectColor.B };
                    }
                    if (attrs.MaterialSource == ObjectMaterialSource.MaterialFromObject && attrs.MaterialIndex >= 0 && attrs.MaterialIndex < doc.Materials.Count)
                    {
                        info["material"] = doc.Materials[attrs.MaterialIndex].Name;
                    }

                    results.Add(info);
                }

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["modifiedCount"] = results.Count(r => r.ContainsKey("success") && (bool)r["success"]),
                        ["instances"] = results
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set instance properties failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-instance-visibility - Hide or show block instances.
        /// Body: { "ids": ["guid1", "guid2"], "visible": true }
        /// </summary>
        public ApiResponse SetInstanceVisibility(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);

                var instanceIds = new List<Guid>();
                if (request.TryGetProperty("ids", out var idsEl) && idsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var el in idsEl.EnumerateArray())
                    {
                        if (Guid.TryParse(el.GetString(), out var guid))
                        {
                            instanceIds.Add(guid);
                        }
                    }
                }
                else if (request.TryGetProperty("id", out var idEl))
                {
                    if (Guid.TryParse(idEl.GetString(), out var guid))
                    {
                        instanceIds.Add(guid);
                    }
                }

                if (instanceIds.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "At least one instance ID required" };
                }

                if (!request.TryGetProperty("visible", out var visEl))
                {
                    return new ApiResponse { Success = false, Data = "'visible' parameter required (true/false)" };
                }

                bool visible = visEl.GetBoolean();

                using var undo = new UndoScope(doc, "Set Instance Visibility");
                int modifiedCount = 0;

                foreach (var guid in instanceIds)
                {
                    var rhinoObj = doc.Objects.FindId(guid);
                    if (rhinoObj == null || !(rhinoObj is InstanceObject)) continue;

                    if (visible)
                        doc.Objects.Show(guid, true);
                    else
                        doc.Objects.Hide(guid, true);

                    modifiedCount++;
                }

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["visible"] = visible,
                        ["modifiedCount"] = modifiedCount,
                        ["requestedCount"] = instanceIds.Count
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set instance visibility failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 7: Instance Transform Operations
        // =====================================================================

        /// <summary>
        /// POST /block/transform-instance - Apply incremental transforms to an existing block instance.
        /// Transforms are RELATIVE/INCREMENTAL — they compound on the instance's existing transform.
        /// Body: { "id": "guid", "move": [dx, dy, dz], "rotate": 45, "scale": [sx, sy, sz], "mirror": {"normal": [1,0,0], "origin": [0,0,0]} }
        /// All transform fields are optional — applied in order: scale, rotate, move, mirror.
        /// </summary>
        public ApiResponse TransformInstance(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);

                if (!request.TryGetProperty("id", out var idEl) || !Guid.TryParse(idEl.GetString(), out var instanceGuid))
                {
                    return new ApiResponse { Success = false, Data = "Valid instance 'id' required" };
                }

                var rhinoObj = doc.Objects.FindId(instanceGuid);
                if (rhinoObj == null || !(rhinoObj is InstanceObject inst))
                {
                    return new ApiResponse { Success = false, Data = "Object is not a block instance" };
                }

                // Get the current instance center for rotation/scale pivot
                var currentXform = inst.InstanceXform;
                var pivot = new Point3d(currentXform.M03, currentXform.M13, currentXform.M23);

                var combinedXform = Transform.Identity;
                var appliedOps = new List<string>();

                // Scale (around instance pivot)
                if (request.TryGetProperty("scale", out var scaleEl))
                {
                    if (!TryParseScaleOp(scaleEl, pivot, out var scaleXform, out var scaleDesc, out var scaleErr))
                    {
                        return new ApiResponse { Success = false, Data = $"scale: {scaleErr}" };
                    }
                    combinedXform = scaleXform * combinedXform;
                    appliedOps.Add(scaleDesc!);
                }

                // Rotate (around Z axis at instance pivot, degrees)
                if (request.TryGetProperty("rotate", out var rotEl))
                {
                    double angleDeg = rotEl.GetDouble();
                    var rotXform = Transform.Rotation(angleDeg * Math.PI / 180.0, Vector3d.ZAxis, pivot);
                    combinedXform = rotXform * combinedXform;
                    appliedOps.Add($"rotate {angleDeg}°");
                }

                // Move (translation vector)
                if (request.TryGetProperty("move", out var moveEl) && moveEl.ValueKind == JsonValueKind.Array)
                {
                    var delta = moveEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                    if (delta.Length >= 3)
                    {
                        combinedXform = Transform.Translation(delta[0], delta[1], delta[2]) * combinedXform;
                        appliedOps.Add($"move [{delta[0]}, {delta[1]}, {delta[2]}]");
                    }
                }

                // Mirror (across a plane defined by normal + origin)
                if (request.TryGetProperty("mirror", out var mirrorEl) && mirrorEl.ValueKind == JsonValueKind.Object)
                {
                    var normal = new Vector3d(0, 1, 0);
                    var origin = Point3d.Origin;

                    if (mirrorEl.TryGetProperty("normal", out var normalEl))
                    {
                        var n = normalEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                        if (n.Length >= 3) normal = new Vector3d(n[0], n[1], n[2]);
                    }
                    if (mirrorEl.TryGetProperty("origin", out var originEl))
                    {
                        var o = originEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                        if (o.Length >= 3) origin = new Point3d(o[0], o[1], o[2]);
                    }

                    var mirrorPlane = new Plane(origin, normal);
                    combinedXform = Transform.Mirror(mirrorPlane) * combinedXform;
                    appliedOps.Add($"mirror");
                }

                if (appliedOps.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "At least one transform required: 'move', 'rotate', 'scale', or 'mirror'" };
                }

                using var undo = new UndoScope(doc, "Transform Block Instance");
                doc.Objects.Transform(instanceGuid, combinedXform, true);
                doc.Views.Redraw();

                // Read back new position
                var updatedObj = doc.Objects.FindId(instanceGuid) as InstanceObject;
                var newXform = updatedObj?.InstanceXform ?? Transform.Identity;
                var newPos = new Point3d(newXform.M03, newXform.M13, newXform.M23);

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["id"] = instanceGuid.ToString(),
                        ["operations"] = appliedOps,
                        ["newPosition"] = new[] { newPos.X, newPos.Y, newPos.Z }
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Transform instance failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/transform-instance-batch - Apply incremental transforms to many
        /// block instances in one call. Each item specifies an instance GUID and any
        /// subset of {move, rotate, scale, mirror}. Composition order per item matches
        /// the single-target tool: scale -> rotate -> move -> mirror, pivoted at the
        /// current instance translation. Best-effort: a malformed item is skipped with
        /// a structured error record, batch continues.
        ///
        /// Duplicate-GUID behavior: GUIDs are preserved across instance transforms
        /// (empirically verified against both the companion batch path and the native
        /// single-target path, which explicitly copies the original ObjectAttributes
        /// including m_uuid when recreating the instance). Consequently, if the same
        /// GUID appears twice in items[], both iterations apply and transforms
        /// accumulate against the current state. The pivot is re-read between items,
        /// so e.g. the same GUID with move [10,0,0] twice produces a net +20 on X.
        ///
        /// Body: { "items": [{ "id": "guid", "move": [...], ... }, ...], "redraw": false }
        /// </summary>
        public ApiResponse TransformInstanceBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Envelope guard (inherited from PR #21): JsonElement.TryGetProperty
                // throws InvalidOperationException on non-object kinds (array / string /
                // number / bool / null). Without this check, a malformed body falls into
                // the outer try/catch and surfaces as a generic wrapper message rather
                // than the intended shape-error contract.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl))
                {
                    if (redrawEl.ValueKind != JsonValueKind.True && redrawEl.ValueKind != JsonValueKind.False)
                        return new ApiResponse { Success = false, Data = "'redraw' must be a boolean" };
                    redraw = redrawEl.GetBoolean();
                }

                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object>>();

                using var undo = new UndoScope(doc, "Batch Transform Instances");

                foreach (var item in itemsEl.EnumerateArray())
                {
                    string? recordedId = null;
                    try
                    {
                        if (item.ValueKind != JsonValueKind.Object)
                        {
                            errors.Add(new Dictionary<string, object> { ["id"] = "", ["error"] = "invalid_id" });
                            skipped++;
                            continue;
                        }

                        // ---- id validation
                        if (!item.TryGetProperty("id", out var idEl) ||
                            idEl.ValueKind != JsonValueKind.String ||
                            !Guid.TryParse(idEl.GetString(), out var instanceGuid))
                        {
                            errors.Add(new Dictionary<string, object>
                            {
                                ["id"] = (item.TryGetProperty("id", out var rawId) && rawId.ValueKind == JsonValueKind.String)
                                    ? (rawId.GetString() ?? "") : "",
                                ["error"] = "invalid_id"
                            });
                            skipped++;
                            continue;
                        }
                        recordedId = instanceGuid.ToString();

                        // ---- lookup
                        var rhinoObj = doc.Objects.FindId(instanceGuid);
                        if (rhinoObj == null)
                        {
                            errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "not_found" });
                            skipped++;
                            continue;
                        }
                        if (!(rhinoObj is InstanceObject inst))
                        {
                            errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "not_instance" });
                            skipped++;
                            continue;
                        }

                        // ---- pivot re-read per item
                        var currentXform = inst.InstanceXform;
                        var pivot = new Point3d(currentXform.M03, currentXform.M13, currentXform.M23);

                        var combinedXform = Transform.Identity;
                        bool anyOp = false;

                        // ---- scale (shared helper)
                        if (item.TryGetProperty("scale", out var scaleEl))
                        {
                            if (!TryParseScaleOp(scaleEl, pivot, out var scaleXform, out _, out var scaleErr))
                            {
                                errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = scaleErr ?? "invalid_scale" });
                                skipped++;
                                continue;
                            }
                            combinedXform = scaleXform * combinedXform;
                            anyOp = true;
                        }

                        // ---- rotate
                        if (item.TryGetProperty("rotate", out var rotEl))
                        {
                            if (rotEl.ValueKind != JsonValueKind.Number)
                            {
                                errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "invalid_rotate" });
                                skipped++;
                                continue;
                            }
                            double angleDeg = rotEl.GetDouble();
                            var rotXform = Transform.Rotation(angleDeg * Math.PI / 180.0, Vector3d.ZAxis, pivot);
                            combinedXform = rotXform * combinedXform;
                            anyOp = true;
                        }

                        // ---- move
                        if (item.TryGetProperty("move", out var moveEl))
                        {
                            if (moveEl.ValueKind != JsonValueKind.Array)
                            {
                                errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "invalid_move" });
                                skipped++;
                                continue;
                            }
                            var delta = new List<double>();
                            bool moveBad = false;
                            foreach (var e in moveEl.EnumerateArray())
                            {
                                if (e.ValueKind != JsonValueKind.Number) { moveBad = true; break; }
                                delta.Add(e.GetDouble());
                            }
                            if (moveBad || delta.Count != 3)
                            {
                                errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "invalid_move" });
                                skipped++;
                                continue;
                            }
                            combinedXform = Transform.Translation(delta[0], delta[1], delta[2]) * combinedXform;
                            anyOp = true;
                        }

                        // ---- mirror
                        if (item.TryGetProperty("mirror", out var mirrorEl))
                        {
                            if (mirrorEl.ValueKind != JsonValueKind.Object ||
                                !mirrorEl.TryGetProperty("normal", out var normalEl) ||
                                !mirrorEl.TryGetProperty("origin", out var originEl) ||
                                normalEl.ValueKind != JsonValueKind.Array ||
                                originEl.ValueKind != JsonValueKind.Array)
                            {
                                errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "invalid_mirror" });
                                skipped++;
                                continue;
                            }
                            var normalVals = new List<double>();
                            bool mirrorBad = false;
                            foreach (var e in normalEl.EnumerateArray())
                            {
                                if (e.ValueKind != JsonValueKind.Number) { mirrorBad = true; break; }
                                normalVals.Add(e.GetDouble());
                            }
                            var originVals = new List<double>();
                            if (!mirrorBad)
                            {
                                foreach (var e in originEl.EnumerateArray())
                                {
                                    if (e.ValueKind != JsonValueKind.Number) { mirrorBad = true; break; }
                                    originVals.Add(e.GetDouble());
                                }
                            }
                            if (mirrorBad || normalVals.Count != 3 || originVals.Count != 3)
                            {
                                errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "invalid_mirror" });
                                skipped++;
                                continue;
                            }
                            if (normalVals[0] == 0.0 && normalVals[1] == 0.0 && normalVals[2] == 0.0)
                            {
                                errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "invalid_mirror" });
                                skipped++;
                                continue;
                            }
                            var mirrorPlane = new Plane(
                                new Point3d(originVals[0], originVals[1], originVals[2]),
                                new Vector3d(normalVals[0], normalVals[1], normalVals[2]));
                            combinedXform = Transform.Mirror(mirrorPlane) * combinedXform;
                            anyOp = true;
                        }

                        if (!anyOp)
                        {
                            errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "no_ops" });
                            skipped++;
                            continue;
                        }

                        // ---- apply
                        if (doc.Objects.Transform(instanceGuid, combinedXform, true) == Guid.Empty)
                        {
                            errors.Add(new Dictionary<string, object> { ["id"] = recordedId, ["error"] = "transform_failed" });
                            skipped++;
                            continue;
                        }
                        routed++;
                    }
                    catch (Exception ex)
                    {
                        errors.Add(new Dictionary<string, object>
                        {
                            ["id"] = recordedId ?? "",
                            ["error"] = "exception",
                            ["message"] = ex.Message
                        });
                        skipped++;
                    }
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = itemsEl.GetArrayLength()
                };
                if (errors.Count > 0)
                    result["errors"] = errors;

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch transform instances failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/array-instances - Create a linear or circular array of block instances.
        /// Linear: { "name": "BlockName", "count": 5, "direction": [10, 0, 0] }
        /// Circular: { "name": "BlockName", "count": 8, "center": [0, 0, 0], "radius": 10, "startAngle": 0, "endAngle": 360 }
        /// </summary>
        public ApiResponse ArrayInstances(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);

                if (!request.TryGetProperty("name", out var nameEl) || string.IsNullOrEmpty(nameEl.GetString()))
                {
                    return new ApiResponse { Success = false, Data = "Block 'name' required" };
                }
                var blockName = nameEl.GetString()!;

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                if (!request.TryGetProperty("count", out var countEl))
                {
                    return new ApiResponse { Success = false, Data = "'count' is required" };
                }
                int count = (int)countEl.GetDouble();
                if (count < 1)
                {
                    return new ApiResponse { Success = false, Data = "'count' must be >= 1" };
                }

                double scale = 1.0;
                if (request.TryGetProperty("scale", out var scaleEl))
                {
                    scale = scaleEl.GetDouble();
                }

                using var undo = new UndoScope(doc, "Array Block Instances");
                var createdIds = new List<string>();

                // Detect mode: circular if 'center' is provided, linear if 'direction' is provided
                bool isCircular = request.TryGetProperty("center", out var centerEl);

                if (isCircular)
                {
                    // Circular array
                    var center = Point3d.Origin;
                    var coords = centerEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                    if (coords.Length >= 3) center = new Point3d(coords[0], coords[1], coords[2]);

                    double radius = 10.0;
                    if (request.TryGetProperty("radius", out var radEl)) radius = radEl.GetDouble();

                    double startAngle = 0;
                    if (request.TryGetProperty("startAngle", out var saEl)) startAngle = saEl.GetDouble();

                    double endAngle = 360;
                    if (request.TryGetProperty("endAngle", out var eaEl)) endAngle = eaEl.GetDouble();

                    double angleSpan = endAngle - startAngle;
                    // If full circle, divide evenly; otherwise divide into count-1 gaps
                    double angleStep = Math.Abs(angleSpan - 360) < 0.001 ? angleSpan / count : angleSpan / Math.Max(count - 1, 1);

                    for (int i = 0; i < count; i++)
                    {
                        double angle = startAngle + i * angleStep;
                        double rad = angle * Math.PI / 180.0;

                        var point = new Point3d(
                            center.X + radius * Math.Cos(rad),
                            center.Y + radius * Math.Sin(rad),
                            center.Z
                        );

                        // Build transform: scale → rotate to face outward → translate
                        var xform = Transform.Identity;
                        if (Math.Abs(scale - 1.0) > 0.0001) xform = Transform.Scale(Point3d.Origin, scale);
                        var rotXform = Transform.Rotation(rad, Vector3d.ZAxis, Point3d.Origin);
                        xform = rotXform * xform;
                        xform = Transform.Translation(point - Point3d.Origin) * xform;

                        var instanceId = doc.Objects.AddInstanceObject(idef.Index, xform);
                        if (instanceId != Guid.Empty) createdIds.Add(instanceId.ToString());
                    }
                }
                else
                {
                    // Linear array
                    if (!request.TryGetProperty("direction", out var dirEl))
                    {
                        return new ApiResponse { Success = false, Data = "Either 'direction' (linear) or 'center' (circular) required" };
                    }

                    var dir = dirEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                    if (dir.Length < 3)
                    {
                        return new ApiResponse { Success = false, Data = "'direction' must be [dx, dy, dz]" };
                    }

                    var basePoint = Point3d.Origin;
                    if (request.TryGetProperty("basePoint", out var bpEl))
                    {
                        var bp = bpEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                        if (bp.Length >= 3) basePoint = new Point3d(bp[0], bp[1], bp[2]);
                    }

                    for (int i = 0; i < count; i++)
                    {
                        var point = new Point3d(
                            basePoint.X + i * dir[0],
                            basePoint.Y + i * dir[1],
                            basePoint.Z + i * dir[2]
                        );

                        var xform = Transform.Identity;
                        if (Math.Abs(scale - 1.0) > 0.0001) xform = Transform.Scale(Point3d.Origin, scale);
                        xform = Transform.Translation(point - Point3d.Origin) * xform;

                        var instanceId = doc.Objects.AddInstanceObject(idef.Index, xform);
                        if (instanceId != Guid.Empty) createdIds.Add(instanceId.ToString());
                    }
                }

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["mode"] = isCircular ? "circular" : "linear",
                        ["createdCount"] = createdIds.Count,
                        ["instanceIds"] = createdIds
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Array instances failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 8: Object Properties Within Blocks
        // =====================================================================

        /// <summary>
        /// POST /block/set-object-colors - Set colors of objects within a block definition.
        /// Body: { "name": "BlockName", "color": [255,0,0], "mappings": [{ "index": 0, "color": [0,255,0] }] }
        /// </summary>
        public ApiResponse SetBlockObjectColors(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                var blockName = request.GetProperty("name").GetString();
                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                // Parse bulk color
                System.Drawing.Color? bulkColor = null;
                if (request.TryGetProperty("color", out var colorEl) && colorEl.ValueKind == JsonValueKind.Array)
                {
                    var rgb = colorEl.EnumerateArray().Select(e => Math.Min(Math.Max(e.GetInt32(), 0), 255)).ToArray();
                    if (rgb.Length >= 3) bulkColor = System.Drawing.Color.FromArgb(rgb[0], rgb[1], rgb[2]);
                }

                // Parse per-object mappings
                var perObjectColors = new Dictionary<int, System.Drawing.Color>();
                if (request.TryGetProperty("mappings", out var mappingsEl) && mappingsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var mapping in mappingsEl.EnumerateArray())
                    {
                        int objIndex = mapping.GetProperty("index").GetInt32();
                        var rgb = mapping.GetProperty("color").EnumerateArray().Select(e => Math.Min(Math.Max(e.GetInt32(), 0), 255)).ToArray();
                        if (rgb.Length >= 3)
                        {
                            perObjectColors[objIndex] = System.Drawing.Color.FromArgb(rgb[0], rgb[1], rgb[2]);
                        }
                    }
                }

                if (!bulkColor.HasValue && perObjectColors.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "Either 'color' or 'mappings' must be provided" };
                }

                var existingObjects = idef.GetObjects();

                // Validate indices
                foreach (var idx in perObjectColors.Keys)
                {
                    if (idx < 0 || idx >= existingObjects.Length)
                    {
                        return new ApiResponse { Success = false, Data = $"Object index {idx} out of range (block has {existingObjects.Length} objects)" };
                    }
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                    var attrs = existingObjects[i].Attributes.Duplicate();

                    if (bulkColor.HasValue)
                    {
                        attrs.ColorSource = ObjectColorSource.ColorFromObject;
                        attrs.ObjectColor = bulkColor.Value;
                    }
                    if (perObjectColors.TryGetValue(i, out var mappedColor))
                    {
                        attrs.ColorSource = ObjectColorSource.ColorFromObject;
                        attrs.ObjectColor = mappedColor;
                    }

                    allAttributes.Add(attrs);
                }

                using var undo = new UndoScope(doc, "Set Block Object Colors");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                var updatedObjects = idef.GetObjects();
                var objectInfos = updatedObjects.Select((obj, idx) => new Dictionary<string, object>
                {
                    ["index"] = idx,
                    ["type"] = obj.ObjectType.ToString(),
                    ["color"] = new[] { obj.Attributes.ObjectColor.R, obj.Attributes.ObjectColor.G, obj.Attributes.ObjectColor.B },
                    ["colorSource"] = obj.Attributes.ColorSource.ToString()
                }).ToList();

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["objectCount"] = objectInfos.Count,
                        ["objects"] = objectInfos
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set block object colors failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-object-names - Set names of objects within a block definition.
        /// Body: { "name": "BlockName", "mappings": [{ "index": 0, "objectName": "Floor" }, { "index": 1, "objectName": "Wall" }] }
        /// </summary>
        public ApiResponse SetBlockObjectNames(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                var blockName = request.GetProperty("name").GetString();
                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                if (!request.TryGetProperty("mappings", out var mappingsEl) || mappingsEl.ValueKind != JsonValueKind.Array)
                {
                    return new ApiResponse { Success = false, Data = "'mappings' array required with {index, objectName} entries" };
                }

                var perObjectNames = new Dictionary<int, string>();
                foreach (var mapping in mappingsEl.EnumerateArray())
                {
                    int objIndex = mapping.GetProperty("index").GetInt32();
                    var objName = mapping.GetProperty("objectName").GetString() ?? "";
                    perObjectNames[objIndex] = objName;
                }

                var existingObjects = idef.GetObjects();

                foreach (var idx in perObjectNames.Keys)
                {
                    if (idx < 0 || idx >= existingObjects.Length)
                    {
                        return new ApiResponse { Success = false, Data = $"Object index {idx} out of range (block has {existingObjects.Length} objects)" };
                    }
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                    var attrs = existingObjects[i].Attributes.Duplicate();

                    if (perObjectNames.TryGetValue(i, out var newName))
                    {
                        attrs.Name = newName;
                    }

                    allAttributes.Add(attrs);
                }

                using var undo = new UndoScope(doc, "Set Block Object Names");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                var updatedObjects = idef.GetObjects();
                var objectInfos = updatedObjects.Select((obj, idx) => new Dictionary<string, object>
                {
                    ["index"] = idx,
                    ["type"] = obj.ObjectType.ToString(),
                    ["name"] = obj.Attributes.Name ?? "",
                    ["layer"] = doc.Layers[obj.Attributes.LayerIndex].FullPath
                }).ToList();

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["objectCount"] = objectInfos.Count,
                        ["objects"] = objectInfos
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set block object names failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/set-object-user-strings - Set user strings on objects within a block definition.
        /// Body: { "name": "BlockName", "userStrings": {"key": "value"}, "mappings": [{ "index": 0, "userStrings": {"key": "value"} }] }
        /// </summary>
        public ApiResponse SetBlockObjectUserStrings(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                var blockName = request.GetProperty("name").GetString();
                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                // Parse bulk user strings (applied to all objects)
                var bulkStrings = new Dictionary<string, string>();
                if (request.TryGetProperty("userStrings", out var usEl) && usEl.ValueKind == JsonValueKind.Object)
                {
                    foreach (var prop in usEl.EnumerateObject())
                    {
                        bulkStrings[prop.Name] = prop.Value.GetString() ?? "";
                    }
                }

                // Parse per-object user strings
                var perObjectStrings = new Dictionary<int, Dictionary<string, string>>();
                if (request.TryGetProperty("mappings", out var mappingsEl) && mappingsEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var mapping in mappingsEl.EnumerateArray())
                    {
                        int objIndex = mapping.GetProperty("index").GetInt32();
                        var strings = new Dictionary<string, string>();
                        if (mapping.TryGetProperty("userStrings", out var mUsEl) && mUsEl.ValueKind == JsonValueKind.Object)
                        {
                            foreach (var prop in mUsEl.EnumerateObject())
                            {
                                strings[prop.Name] = prop.Value.GetString() ?? "";
                            }
                        }
                        perObjectStrings[objIndex] = strings;
                    }
                }

                if (bulkStrings.Count == 0 && perObjectStrings.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "Either 'userStrings' or 'mappings' with userStrings must be provided" };
                }

                var existingObjects = idef.GetObjects();

                foreach (var idx in perObjectStrings.Keys)
                {
                    if (idx < 0 || idx >= existingObjects.Length)
                    {
                        return new ApiResponse { Success = false, Data = $"Object index {idx} out of range (block has {existingObjects.Length} objects)" };
                    }
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                    var attrs = existingObjects[i].Attributes.Duplicate();

                    // Apply bulk strings
                    foreach (var kvp in bulkStrings)
                    {
                        attrs.SetUserString(kvp.Key, kvp.Value);
                    }

                    // Apply per-object overrides
                    if (perObjectStrings.TryGetValue(i, out var objStrings))
                    {
                        foreach (var kvp in objStrings)
                        {
                            attrs.SetUserString(kvp.Key, kvp.Value);
                        }
                    }

                    allAttributes.Add(attrs);
                }

                using var undo = new UndoScope(doc, "Set Block Object User Strings");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                // Return user strings per object
                var updatedObjects = idef.GetObjects();
                var objectInfos = updatedObjects.Select((obj, idx) =>
                {
                    var us = new Dictionary<string, string>();
                    var keys = obj.Attributes.GetUserStrings();
                    if (keys != null)
                    {
                        foreach (string key in keys.AllKeys)
                        {
                            us[key] = keys[key] ?? "";
                        }
                    }
                    return new Dictionary<string, object>
                    {
                        ["index"] = idx,
                        ["type"] = obj.ObjectType.ToString(),
                        ["userStrings"] = us
                    };
                }).ToList();

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["objectCount"] = objectInfos.Count,
                        ["objects"] = objectInfos
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Set block object user strings failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 9: Block Definition Metadata
        // =====================================================================

        /// <summary>
        /// POST /block/user-strings - Get or set user strings on a block definition.
        /// GET: /block/user-strings?name=BlockName
        /// POST set: { "name": "BlockName", "action": "set", "userStrings": { "version": "2.0", "author": "Rook" } }
        /// POST get: { "name": "BlockName", "action": "get" }
        /// POST delete: { "name": "BlockName", "action": "delete", "keys": ["version"] }
        /// </summary>
        public ApiResponse BlockUserStrings(string? body, string? queryName = null)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                string? blockName = queryName;
                string action = "get";
                JsonElement request = default;

                if (!string.IsNullOrEmpty(body))
                {
                    request = JsonSerializer.Deserialize<JsonElement>(body);
                    if (request.TryGetProperty("name", out var nameEl))
                        blockName = nameEl.GetString();
                    if (request.TryGetProperty("action", out var actionEl))
                        action = actionEl.GetString() ?? "get";
                }

                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                // Use doc.Strings with section "RookBlock::{blockName}" since InstanceDefinition
                // doesn't expose SetUserString/GetUserStrings in the available RhinoCommon version.
                string section = $"RookBlock::{blockName}";

                switch (action.ToLower())
                {
                    case "get":
                    {
                        var strings = new Dictionary<string, string>();
                        var entries = doc.Strings.GetEntryNames(section);
                        if (entries != null)
                        {
                            foreach (var key in entries)
                            {
                                strings[key] = doc.Strings.GetValue(section, key) ?? "";
                            }
                        }
                        return new ApiResponse
                        {
                            Success = true,
                            Data = new Dictionary<string, object>
                            {
                                ["blockName"] = blockName,
                                ["userStrings"] = strings,
                                ["count"] = strings.Count
                            }
                        };
                    }

                    case "set":
                    {
                        if (!request.TryGetProperty("userStrings", out var usEl) || usEl.ValueKind != JsonValueKind.Object)
                        {
                            return new ApiResponse { Success = false, Data = "'userStrings' object required for 'set' action" };
                        }

                        using var undoSet = new UndoScope(doc, "Set Block User Strings");
                        int setCount = 0;
                        foreach (var prop in usEl.EnumerateObject())
                        {
                            doc.Strings.SetString(section, prop.Name, prop.Value.GetString() ?? "");
                            setCount++;
                        }

                        return new ApiResponse
                        {
                            Success = true,
                            Data = new Dictionary<string, object>
                            {
                                ["blockName"] = blockName,
                                ["action"] = "set",
                                ["keysSet"] = setCount
                            }
                        };
                    }

                    case "delete":
                    {
                        if (!request.TryGetProperty("keys", out var keysEl) || keysEl.ValueKind != JsonValueKind.Array)
                        {
                            return new ApiResponse { Success = false, Data = "'keys' array required for 'delete' action" };
                        }

                        using var undoDel = new UndoScope(doc, "Delete Block User Strings");
                        int deletedCount = 0;
                        foreach (var keyEl in keysEl.EnumerateArray())
                        {
                            var key = keyEl.GetString();
                            if (!string.IsNullOrEmpty(key))
                            {
                                doc.Strings.Delete(section, key);
                                deletedCount++;
                            }
                        }

                        return new ApiResponse
                        {
                            Success = true,
                            Data = new Dictionary<string, object>
                            {
                                ["blockName"] = blockName,
                                ["action"] = "delete",
                                ["keysDeleted"] = deletedCount
                            }
                        };
                    }

                    default:
                        return new ApiResponse { Success = false, Data = $"Unknown action '{action}'. Use 'get', 'set', or 'delete'" };
                }
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Block user strings failed: {ex.Message}" };
            }
        }

        // =====================================================================
        // Phase 10: Enhanced Block Queries
        // =====================================================================

        /// <summary>
        /// POST /block/find-instances - Find block instances matching criteria.
        /// Body: { "name": "BlockName", "layer": "Furniture", "namePattern": "Chair*", "bbox": {"min": [0,0,0], "max": [100,100,100]} }
        /// All filter fields are optional. If 'name' is omitted, searches all block definitions.
        /// </summary>
        public ApiResponse FindInstances(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                var request = string.IsNullOrEmpty(body)
                    ? default
                    : JsonSerializer.Deserialize<JsonElement>(body);

                // Optional block name filter
                string? blockName = null;
                if (request.ValueKind == JsonValueKind.Object && request.TryGetProperty("name", out var nameEl))
                {
                    blockName = nameEl.GetString();
                }

                // Optional layer filter
                string? layerFilter = null;
                if (request.ValueKind == JsonValueKind.Object && request.TryGetProperty("layer", out var layerEl))
                {
                    layerFilter = layerEl.GetString();
                }

                // Optional name pattern filter
                string? namePattern = null;
                if (request.ValueKind == JsonValueKind.Object && request.TryGetProperty("namePattern", out var patEl))
                {
                    namePattern = patEl.GetString();
                }

                // Optional bounding box filter
                BoundingBox? bboxFilter = null;
                if (request.ValueKind == JsonValueKind.Object && request.TryGetProperty("bbox", out var bboxEl))
                {
                    if (bboxEl.TryGetProperty("min", out var minEl) && bboxEl.TryGetProperty("max", out var maxEl))
                    {
                        var min = minEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                        var max = maxEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                        if (min.Length >= 3 && max.Length >= 3)
                        {
                            bboxFilter = new BoundingBox(
                                new Point3d(min[0], min[1], min[2]),
                                new Point3d(max[0], max[1], max[2]));
                        }
                    }
                }

                var results = new List<Dictionary<string, object>>();

                // Iterate all block definitions or a specific one
                var definitions = new List<InstanceDefinition>();
                if (!string.IsNullOrEmpty(blockName))
                {
                    var idef = doc.InstanceDefinitions.Find(blockName);
                    if (idef != null) definitions.Add(idef);
                }
                else
                {
                    foreach (var idef in doc.InstanceDefinitions)
                    {
                        if (!idef.IsDeleted) definitions.Add(idef);
                    }
                }

                foreach (var idef in definitions)
                {
                    var refs = idef.GetReferences(0);
                    if (refs == null) continue;

                    foreach (var inst in refs)
                    {
                        // Layer filter
                        if (layerFilter != null)
                        {
                            var instLayer = doc.Layers[inst.Attributes.LayerIndex].FullPath;
                            if (!instLayer.Equals(layerFilter, StringComparison.OrdinalIgnoreCase))
                                continue;
                        }

                        // Name pattern filter (simple wildcard: * at start/end)
                        if (namePattern != null)
                        {
                            var instName = inst.Name ?? "";
                            bool match = false;
                            if (namePattern.StartsWith("*") && namePattern.EndsWith("*"))
                                match = instName.IndexOf(namePattern.Trim('*'), StringComparison.OrdinalIgnoreCase) >= 0;
                            else if (namePattern.EndsWith("*"))
                                match = instName.StartsWith(namePattern.TrimEnd('*'), StringComparison.OrdinalIgnoreCase);
                            else if (namePattern.StartsWith("*"))
                                match = instName.EndsWith(namePattern.TrimStart('*'), StringComparison.OrdinalIgnoreCase);
                            else
                                match = instName.Equals(namePattern, StringComparison.OrdinalIgnoreCase);

                            if (!match) continue;
                        }

                        // BBox filter — test instance geometry bounds, not just insertion point
                        if (bboxFilter.HasValue)
                        {
                            var instBbox = inst.Geometry.GetBoundingBox(true);
                            if (!instBbox.IsValid) continue;
                            var intersection = BoundingBox.Intersection(instBbox, bboxFilter.Value);
                            if (!intersection.IsValid) continue;
                        }

                        var xf = inst.InstanceXform;
                        results.Add(new Dictionary<string, object>
                        {
                            ["id"] = inst.Id.ToString(),
                            ["blockName"] = idef.Name,
                            ["insertionPoint"] = new[] { xf.M03, xf.M13, xf.M23 },
                            ["layer"] = doc.Layers[inst.Attributes.LayerIndex].FullPath,
                            ["name"] = inst.Name ?? ""
                        });
                    }
                }

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["matchCount"] = results.Count,
                        ["instances"] = results
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Find instances failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// GET/POST /block/objects-detailed - Get full attribute details for all objects in a block definition.
        /// </summary>
        public ApiResponse GetBlockObjectsDetailed(string? blockName)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            if (string.IsNullOrEmpty(blockName))
            {
                return new ApiResponse { Success = false, Data = "Block name required" };
            }

            var idef = doc.InstanceDefinitions.Find(blockName);
            if (idef == null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
            }

            var objects = idef.GetObjects();
            var objectInfos = objects.Select((obj, idx) =>
            {
                var info = new Dictionary<string, object>
                {
                    ["index"] = idx,
                    ["id"] = obj.Id.ToString(),
                    ["type"] = obj.ObjectType.ToString(),
                    ["name"] = obj.Attributes.Name ?? "",
                    ["layer"] = doc.Layers[obj.Attributes.LayerIndex].FullPath,
                    ["color"] = new[] { obj.Attributes.ObjectColor.R, obj.Attributes.ObjectColor.G, obj.Attributes.ObjectColor.B },
                    ["colorSource"] = obj.Attributes.ColorSource.ToString(),
                    ["materialSource"] = obj.Attributes.MaterialSource.ToString(),
                    ["visible"] = obj.Attributes.Visible
                };

                // Material name if set
                if (obj.Attributes.MaterialSource == ObjectMaterialSource.MaterialFromObject &&
                    obj.Attributes.MaterialIndex >= 0 && obj.Attributes.MaterialIndex < doc.Materials.Count)
                {
                    info["material"] = doc.Materials[obj.Attributes.MaterialIndex].Name;
                }

                // User strings
                var us = new Dictionary<string, string>();
                var keys = obj.Attributes.GetUserStrings();
                if (keys != null)
                {
                    foreach (string key in keys.AllKeys)
                    {
                        us[key] = keys[key] ?? "";
                    }
                }
                if (us.Count > 0) info["userStrings"] = us;

                // Bounding box
                var bbox = obj.Geometry.GetBoundingBox(true);
                if (bbox.IsValid)
                {
                    info["bbox"] = new Dictionary<string, object>
                    {
                        ["min"] = new[] { bbox.Min.X, bbox.Min.Y, bbox.Min.Z },
                        ["max"] = new[] { bbox.Max.X, bbox.Max.Y, bbox.Max.Z }
                    };
                }

                return info;
            }).ToList();

            // Definition-level bounding box (computed from objects)
            var defBbox = BoundingBox.Empty;
            foreach (var obj in objects)
            {
                defBbox.Union(obj.Geometry.GetBoundingBox(true));
            }

            return new ApiResponse
            {
                Success = true,
                Data = new Dictionary<string, object>
                {
                    ["blockName"] = idef.Name,
                    ["objectCount"] = objectInfos.Count,
                    ["bbox"] = defBbox.IsValid ? new Dictionary<string, object>
                    {
                        ["min"] = new[] { defBbox.Min.X, defBbox.Min.Y, defBbox.Min.Z },
                        ["max"] = new[] { defBbox.Max.X, defBbox.Max.Y, defBbox.Max.Z }
                    } : null,
                    ["objects"] = objectInfos
                }
            };
        }

        // ---- Replace-object-geometry shared helpers (used by single-target and batch) ----

        private enum ReplaceItemShapeError
        {
            None,
            InvalidName,
            InvalidIndex,
            InvalidSourceId,
            InvalidDeleteFlag,
        }

        private enum ReplaceItemResolutionError
        {
            None,
            SourceNotFound,
            SourceHasNoGeometry,
            IndexOutOfRange,
        }

        private readonly struct ReplaceItemShape
        {
            public readonly string Name;
            public readonly int Index;
            public readonly Guid SourceGuid;
            public readonly string SourceIdRaw;    // raw user-supplied sourceId for echo/error preservation
            public readonly bool DeleteOriginal;

            public ReplaceItemShape(string name, int index, Guid sourceGuid, string sourceIdRaw, bool deleteOriginal)
            {
                Name = name;
                Index = index;
                SourceGuid = sourceGuid;
                SourceIdRaw = sourceIdRaw;
                DeleteOriginal = deleteOriginal;
            }
        }

        private readonly struct ReplaceItemResolution
        {
            public readonly RhinoObject SourceObject;
            public readonly int TargetIndex;

            public ReplaceItemResolution(RhinoObject sourceObject, int targetIndex)
            {
                SourceObject = sourceObject;
                TargetIndex = targetIndex;
            }
        }

        // Reserved user-string key mirroring the native side (see
        // src/RookNative/Handlers/BlocksHandler.cpp kRookBlockBasePointKey).
        // Value format: "x,y,z" written by native with %.17g — culture-invariant,
        // parses cleanly with InvariantCulture. Missing or malformed → treat as
        // origin (no normalization needed, matches native fallback).
        private const string RookBlockBasePointKey = "rook_block_base_point";

        // Interim compatibility bridge to native PR #25 storage.
        //
        // Native writes rook_block_base_point via ON_Object::SetUserString on
        // the ON_InstanceDefinition. RhinoCommon 8.0.23304 does NOT publicly
        // surface GetUserString/SetUserString on managed InstanceDefinition
        // (Layer exposes them; InstanceDefinition intentionally does not —
        // verified via reflection and across the ModelComponent hierarchy).
        // The non-public P/Invoke bridge `_GetUserString` does exist and is
        // the same bridge Layer.GetUserString wraps.
        //
        // Resolved once at type-init. Null here = the non-public bridge is
        // absent in this RhinoCommon version → callers MUST fail loud
        // (silent origin fallback would invisibly reproduce #24/#27).
        //
        // Follow-up: the real fix is to migrate the storage slot so both
        // native and managed can read via stable public APIs (proposed:
        // InstanceDefinition.UserDictionary with a dual-read/dual-write
        // transition window). That's tracked as a separate issue.
        private static readonly MethodInfo? _idefGetUserStringReflected =
            typeof(InstanceDefinition).GetMethod(
                "_GetUserString",
                BindingFlags.Instance | BindingFlags.NonPublic,
                binder: null,
                types: new[] { typeof(string) },
                modifiers: null);

        // Three-state result from reading the native-written basePoint metadata.
        // Found: key present and parsed — normalization needed.
        // Origin: key genuinely absent or malformed → treat as origin (matches
        //   native LookupDefinitionBasePoint's swscanf_s fallback).
        // BridgeFailure: reflection bridge missing OR invocation threw — callers
        //   MUST fail the route so the drift never reappears silently.
        private enum BasePointReadState { Origin, Found, BridgeFailure }

        // Read the stored basePoint. New-first: once a valid Rook-owned
        // UserData payload is present, the reflection bridge to the legacy
        // user-string is NEVER consulted. This is the load-bearing invariant
        // that lets follow-up #34 retire the reflection bridge entirely.
        //
        // Order (matches native LookupDefinitionBasePoint):
        //   1. New slot — RookBlockBasePointUserData.TryRead
        //   2. Legacy user-string via reflection bridge (pre-migration .3dm
        //      compat + fallback for unknown-major / malformed new-slot reads)
        //   3. Origin
        //
        // BasePointReadState.BridgeFailure is returnable ONLY from the
        // legacy-fallback branch. Once the new slot is present, bridge
        // status is irrelevant.
        private static BasePointReadState TryReadDefinitionBasePoint(
            InstanceDefinition idef,
            out Vector3d basePoint,
            out string? bridgeError)
        {
            basePoint = Vector3d.Zero;
            bridgeError = null;
            if (idef == null) return BasePointReadState.Origin;

            // New slot first. Uses the public RhinoCommon UserData API —
            // no reflection, no bridge failure mode possible here.
            if (Rook.UserData.RookBlockBasePointUserData.TryRead(idef, out Point3d fromUserData))
            {
                basePoint = new Vector3d(fromUserData.X, fromUserData.Y, fromUserData.Z);
                return BasePointReadState.Found;
            }

            // Legacy fallback via reflection bridge. Reachable for:
            //   - pre-migration .3dm files (no UserData ever written)
            //   - unknown-major new-slot payloads (forward-compat, §4.1)
            //   - malformed new-slot payloads (treated as missing, §4.1)
            if (_idefGetUserStringReflected == null)
            {
                bridgeError = "RhinoCommon does not expose InstanceDefinition._GetUserString "
                    + "in this build; cannot read native-written rook_block_base_point metadata "
                    + "and no Rook-owned UserData is attached (new-slot read returned false)";
                return BasePointReadState.BridgeFailure;
            }

            string? value;
            try
            {
                value = (string?)_idefGetUserStringReflected.Invoke(idef, new object[] { RookBlockBasePointKey });
            }
            catch (Exception ex)
            {
                bridgeError = "InstanceDefinition._GetUserString reflection invocation failed: "
                    + ex.GetBaseException().Message;
                return BasePointReadState.BridgeFailure;
            }

            // Key absent → native's LookupDefinitionBasePoint returns origin; match.
            if (string.IsNullOrEmpty(value))
                return BasePointReadState.Origin;

            // Malformed → native's swscanf_s returns != 3 → origin; match.
            var parts = value.Split(',');
            if (parts.Length != 3
                || !double.TryParse(parts[0], NumberStyles.Float, CultureInfo.InvariantCulture, out double x)
                || !double.TryParse(parts[1], NumberStyles.Float, CultureInfo.InvariantCulture, out double y)
                || !double.TryParse(parts[2], NumberStyles.Float, CultureInfo.InvariantCulture, out double z))
            {
                return BasePointReadState.Origin;
            }

            basePoint = new Vector3d(x, y, z);
            return BasePointReadState.Found;
        }

        // Duplicate a source object's geometry and, if the target definition
        // has a non-origin basePoint stored, transform it from world coords
        // into definition-local coords. Returns null and sets errorMessage on
        // any failure (null Duplicate result OR failed Transform) — callers
        // fail loud rather than silently inserting untransformed world-coord
        // geometry into the definition (which would reproduce the Issue #24 /
        // #27 drift).
        //
        // Guards Duplicate() returning null: matches the native reference
        // MaterializeTransformedSource which explicitly checks
        // `if (!dupGeom) return nullptr;` before Transform. Without this guard,
        // an unduplicatable source type would crash the whole route (single)
        // or abort the batch (batch) instead of emitting a per-item error.
        private static GeometryBase? DuplicateAndNormalizeSourceGeometry(
            RhinoObject sourceObj,
            Transform worldToLocal,
            bool needsTransform,
            out string? errorMessage)
        {
            errorMessage = null;
            var dup = sourceObj.Geometry?.Duplicate();
            if (dup == null)
            {
                errorMessage = "Source geometry could not be duplicated";
                return null;
            }
            if (needsTransform && !dup.Transform(worldToLocal))
            {
                errorMessage = "Failed to transform source geometry to definition-local coords";
                return null;
            }
            return dup;
        }

        // Shape validation for one replace-object-geometry item.
        // strictDeleteFlag=false matches single-target behavior: any non-boolean deleteOriginal silently defaults to true.
        // strictDeleteFlag=true is the batch semantic: non-boolean deleteOriginal is InvalidDeleteFlag.
        private static ReplaceItemShapeError TryParseReplaceItemShape(
            JsonElement itemEl,
            bool strictDeleteFlag,
            out ReplaceItemShape shape,
            out string? errorMessage)
        {
            shape = default;
            errorMessage = null;

            if (itemEl.ValueKind != JsonValueKind.Object)
            {
                errorMessage = "Item must be a JSON object";
                return ReplaceItemShapeError.InvalidName;
            }

            string? blockName = null;
            if (itemEl.TryGetProperty("name", out var nameEl))
            {
                if (nameEl.ValueKind == JsonValueKind.String)
                {
                    blockName = nameEl.GetString();
                }
            }
            if (string.IsNullOrEmpty(blockName))
            {
                errorMessage = "Block name required";
                return ReplaceItemShapeError.InvalidName;
            }

            if (!itemEl.TryGetProperty("index", out var indexEl) || indexEl.ValueKind != JsonValueKind.Number || !indexEl.TryGetInt32(out int targetIndex))
            {
                errorMessage = "Object index required (integer)";
                return ReplaceItemShapeError.InvalidIndex;
            }

            string? sourceIdStr = null;
            if (itemEl.TryGetProperty("sourceId", out var sourceIdEl) && sourceIdEl.ValueKind == JsonValueKind.String)
            {
                sourceIdStr = sourceIdEl.GetString();
            }
            if (string.IsNullOrEmpty(sourceIdStr) || !Guid.TryParse(sourceIdStr, out Guid sourceGuid))
            {
                errorMessage = "Valid sourceId (GUID) required";
                return ReplaceItemShapeError.InvalidSourceId;
            }

            bool deleteOriginal = true;
            if (itemEl.TryGetProperty("deleteOriginal", out var delEl))
            {
                if (delEl.ValueKind == JsonValueKind.True)
                {
                    deleteOriginal = true;
                }
                else if (delEl.ValueKind == JsonValueKind.False)
                {
                    deleteOriginal = false;
                }
                else if (strictDeleteFlag)
                {
                    errorMessage = "deleteOriginal must be a boolean";
                    return ReplaceItemShapeError.InvalidDeleteFlag;
                }
                // else: loose mode preserves single-target behavior (treat non-boolean as default true)
            }

            shape = new ReplaceItemShape(blockName!, targetIndex, sourceGuid, sourceIdStr!, deleteOriginal);
            return ReplaceItemShapeError.None;
        }

        // Resolution against a FIXED idef snapshot. The caller supplies existingObjects read once at group entry;
        // this helper never re-reads idef.GetObjects() to preserve the design's fixed-snapshot invariant.
        private static ReplaceItemResolutionError TryResolveReplaceItem(
            RhinoDoc doc,
            RhinoObject[] existingObjects,
            ReplaceItemShape shape,
            out ReplaceItemResolution resolution,
            out string? errorMessage)
        {
            resolution = default;
            errorMessage = null;

            if (shape.Index < 0 || shape.Index >= existingObjects.Length)
            {
                errorMessage = $"Object index {shape.Index} out of range (block has {existingObjects.Length} objects)";
                return ReplaceItemResolutionError.IndexOutOfRange;
            }

            var sourceObj = doc.Objects.FindId(shape.SourceGuid);
            if (sourceObj == null)
            {
                errorMessage = $"Source object '{shape.SourceIdRaw}' not found in document";
                return ReplaceItemResolutionError.SourceNotFound;
            }
            if (sourceObj.Geometry == null)
            {
                errorMessage = $"Source object '{shape.SourceIdRaw}' has no geometry";
                return ReplaceItemResolutionError.SourceHasNoGeometry;
            }

            resolution = new ReplaceItemResolution(sourceObj, shape.Index);
            return ReplaceItemResolutionError.None;
        }

        /// <summary>
        /// POST /block/replace-object-geometry - Replace the geometry of a single object within
        /// a block definition by index. The replacement comes from a document-resident object.
        /// Body: { "name": "BlockA", "index": 2, "sourceId": "guid", "deleteOriginal": true }
        /// </summary>
        public ApiResponse ReplaceObjectGeometry(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);

                // Loose mode preserves existing behavior: non-boolean deleteOriginal silently defaults to true.
                var shapeErr = TryParseReplaceItemShape(request, strictDeleteFlag: false, out var shape, out var shapeMsg);
                if (shapeErr != ReplaceItemShapeError.None)
                {
                    return new ApiResponse { Success = false, Data = shapeMsg ?? "Invalid request" };
                }

                var idef = doc.InstanceDefinitions.Find(shape.Name);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{shape.Name}' not found" };
                }

                var existingObjects = idef.GetObjects();
                var resErr = TryResolveReplaceItem(doc, existingObjects, shape, out var resolution, out var resMsg);
                if (resErr != ReplaceItemResolutionError.None)
                {
                    // Preserve legacy single-target wire message: SourceHasNoGeometry uses the same "not found in document" text
                    // that previous builds emitted (the old inline check conflated null-object with null-geometry).
                    string legacyMsg = resErr == ReplaceItemResolutionError.SourceHasNoGeometry
                        ? $"Source object '{shape.SourceIdRaw}' not found in document"
                        : resMsg ?? "Invalid request";
                    return new ApiResponse { Success = false, Data = legacyMsg };
                }

                var sourceObj = resolution.SourceObject;
                int targetIndex = resolution.TargetIndex;

                // Normalize world-coord source into definition-local coords
                // when the definition has a non-origin basePoint stored (see
                // Issue #27 / PR #25 native equivalent). Missing/origin key →
                // identity transform → existing behavior preserved. Bridge
                // failure → fail loud (policy: never silently fall back to
                // origin, which would invisibly reproduce the drift).
                Transform worldToLocal = Transform.Identity;
                bool needsTransform = false;
                var bpState = TryReadDefinitionBasePoint(idef, out Vector3d basePoint, out string? bridgeErr);
                if (bpState == BasePointReadState.BridgeFailure)
                {
                    return new ApiResponse
                    {
                        Success = false,
                        Data = $"Cannot replace object in block '{shape.Name}': {bridgeErr ?? "basePoint metadata unreadable"}"
                    };
                }
                if (bpState == BasePointReadState.Found)
                {
                    worldToLocal = Transform.Translation(-basePoint);
                    needsTransform = !basePoint.IsTiny(1e-12);
                }

                var normalizedReplacement = DuplicateAndNormalizeSourceGeometry(
                    sourceObj, worldToLocal, needsTransform, out string? transformErr);
                if (normalizedReplacement == null)
                {
                    return new ApiResponse { Success = false, Data = transformErr ?? "Failed to transform source geometry" };
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    if (i == targetIndex)
                    {
                        allGeometry.Add(normalizedReplacement);
                    }
                    else
                    {
                        allGeometry.Add(existingObjects[i].Geometry.Duplicate());
                    }
                    allAttributes.Add(existingObjects[i].Attributes.Duplicate());
                }

                using var undo = new UndoScope(doc, "Replace Block Object Geometry");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{shape.Name}'" };
                }

                bool sourceDeleted = false;
                if (shape.DeleteOriginal)
                {
                    sourceDeleted = doc.Objects.Delete(sourceObj, true);
                }

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = shape.Name,
                        ["objectCount"] = existingObjects.Length,
                        ["replacedIndex"] = targetIndex,
                        ["newGeometryType"] = sourceObj.Geometry.ObjectType.ToString(),
                        ["sourceDeleted"] = sourceDeleted
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Replace object geometry failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/replace-object-geometry-batch - Batch variant. Replace geometry of objects
        /// across one or more block definitions in one call, coalescing same-block items into a
        /// single ModifyGeometry call per definition. Best-effort per-item semantics under one UndoScope.
        /// Body: { "items": [{ "name": "BlockA", "index": 0, "sourceId": "guid", "deleteOriginal": true }], "redraw": false }
        /// </summary>
        public ApiResponse ReplaceObjectGeometryBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Top-level envelope must be an object. JsonElement.TryGetProperty throws InvalidOperationException
                // on non-object kinds (array / string / number / bool / null), which would otherwise fall into the
                // generic exception wrapper instead of the intended contract-error response.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl))
                {
                    if (redrawEl.ValueKind != JsonValueKind.True && redrawEl.ValueKind != JsonValueKind.False)
                        return new ApiResponse { Success = false, Data = "'redraw' must be a boolean" };
                    redraw = redrawEl.GetBoolean();
                }

                int total = itemsEl.GetArrayLength();
                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object?>>();

                // Per-item state carried through the pipeline after shape passes
                var slots = new List<Slot>();

                using var undo = new UndoScope(doc, "Batch Replace Block Object Geometry");

                // ==== Phase 1: Shape validation (per item, independent) ====
                int requestIdx = -1;
                foreach (var itemEl in itemsEl.EnumerateArray())
                {
                    requestIdx++;

                    // Capture raw name element for verbatim echo on shape errors (non-string / null / missing).
                    JsonElement? rawName = null;
                    if (itemEl.ValueKind == JsonValueKind.Object && itemEl.TryGetProperty("name", out var nEl))
                        rawName = nEl.Clone();

                    // Pre-parse the index so it can be echoed on non-invalid_index shape errors
                    // (design rule: errors[].index echoes when the shape allowed it to parse; omitted on invalid_index).
                    int? parseableIndex = null;
                    if (itemEl.ValueKind == JsonValueKind.Object
                        && itemEl.TryGetProperty("index", out var rawIdxEl)
                        && rawIdxEl.ValueKind == JsonValueKind.Number
                        && rawIdxEl.TryGetInt32(out int parsedIdx))
                    {
                        parseableIndex = parsedIdx;
                    }

                    var shapeErr = TryParseReplaceItemShape(itemEl, strictDeleteFlag: true, out var shape, out var shapeMsg);
                    if (shapeErr != ReplaceItemShapeError.None)
                    {
                        // Omit index for invalid_index (the offending field itself); echo it on other shape errors
                        // (invalid_name, invalid_source_id, invalid_delete_flag) when the raw value was parseable.
                        int? echoIndex = (shapeErr == ReplaceItemShapeError.InvalidIndex) ? null : parseableIndex;
                        errors.Add(BuildBatchError(rawName, echoIndex, ShapeErrorCode(shapeErr), shapeMsg));
                        skipped++;
                        continue;
                    }

                    slots.Add(new Slot { RequestIndex = requestIdx, RawName = rawName, Shape = shape });
                }

                // ==== Phase 2: Relational validation (first-occurrence-wins, duplicate_target before conflicting_delete_flag) ====
                var seenTargets = new HashSet<(string, int)>();
                var sourcePolicies = new Dictionary<Guid, bool>();
                var survivors = new List<Slot>();
                foreach (var slot in slots)
                {
                    var targetKey = (slot.Shape.Name, slot.Shape.Index);
                    if (!seenTargets.Add(targetKey))
                    {
                        errors.Add(BuildBatchError(slot.RawName, slot.Shape.Index, "duplicate_target",
                            $"Block '{slot.Shape.Name}' index {slot.Shape.Index} already targeted by an earlier item"));
                        skipped++;
                        continue;
                    }
                    if (sourcePolicies.TryGetValue(slot.Shape.SourceGuid, out bool existingPolicy))
                    {
                        if (existingPolicy != slot.Shape.DeleteOriginal)
                        {
                            errors.Add(BuildBatchError(slot.RawName, slot.Shape.Index, "conflicting_delete_flag",
                                $"sourceId '{slot.Shape.SourceIdRaw}' referenced with conflicting deleteOriginal values"));
                            skipped++;
                            continue;
                        }
                    }
                    else
                    {
                        sourcePolicies[slot.Shape.SourceGuid] = slot.Shape.DeleteOriginal;
                    }
                    survivors.Add(slot);
                }

                // ==== Phase 3: Group + resolution against fixed per-group snapshot ====
                // Preserve in-group order from survivors by iterating in order and appending to groups.
                var groupOrder = new List<string>();
                var groupItems = new Dictionary<string, List<Slot>>();
                foreach (var slot in survivors)
                {
                    if (!groupItems.ContainsKey(slot.Shape.Name))
                    {
                        groupOrder.Add(slot.Shape.Name);
                        groupItems[slot.Shape.Name] = new List<Slot>();
                    }
                    groupItems[slot.Shape.Name].Add(slot);
                }

                var resolvedGroups = new List<(InstanceDefinition idef, RhinoObject[] snapshot, List<(Slot slot, ReplaceItemResolution res)> resolved)>();
                foreach (var name in groupOrder)
                {
                    var idef = doc.InstanceDefinitions.Find(name);
                    if (idef == null)
                    {
                        foreach (var slot in groupItems[name])
                        {
                            errors.Add(BuildBatchError(slot.RawName, slot.Shape.Index, "block_not_found",
                                $"Block definition '{name}' not found"));
                            skipped++;
                        }
                        continue;
                    }

                    // Fixed snapshot for the whole group — read once, never re-read mid-group.
                    var existingObjects = idef.GetObjects();
                    var resolvedList = new List<(Slot slot, ReplaceItemResolution res)>();
                    foreach (var slot in groupItems[name])
                    {
                        var resErr = TryResolveReplaceItem(doc, existingObjects, slot.Shape, out var resolution, out var resMsg);
                        if (resErr != ReplaceItemResolutionError.None)
                        {
                            errors.Add(BuildBatchError(slot.RawName, slot.Shape.Index, ResolutionErrorCode(resErr), resMsg));
                            skipped++;
                            continue;
                        }
                        resolvedList.Add((slot, resolution));
                    }

                    if (resolvedList.Count > 0)
                        resolvedGroups.Add((idef, existingObjects, resolvedList));
                }

                // ==== Phase 4: Per-group rebuild + queue deletions ====
                var deletionOrder = new List<Guid>();
                var deletionSet = new HashSet<Guid>();

                foreach (var (idef, snapshot, resolvedList) in resolvedGroups)
                {
                    // Per-group basePoint lookup (Issue #27). Missing/origin key
                    // → identity transform → origin fast path, matches existing
                    // behavior pre-fix. Bridge failure → every slot in THIS
                    // group gets basepoint_bridge_unavailable; sibling groups
                    // still proceed. Never silently fall back to origin — that
                    // would invisibly reproduce the #24/#27 drift.
                    Transform worldToLocal = Transform.Identity;
                    bool needsTransform = false;
                    var bpState = TryReadDefinitionBasePoint(idef, out Vector3d basePoint, out string? bridgeErr);
                    if (bpState == BasePointReadState.BridgeFailure)
                    {
                        foreach (var (slot, _) in resolvedList)
                        {
                            errors.Add(BuildBatchError(slot.RawName, slot.Shape.Index, "basepoint_bridge_unavailable",
                                $"Cannot read basePoint metadata for block '{idef.Name}': {bridgeErr ?? "reflection bridge unavailable"}"));
                            skipped++;
                        }
                        continue;
                    }
                    if (bpState == BasePointReadState.Found)
                    {
                        worldToLocal = Transform.Translation(-basePoint);
                        needsTransform = !basePoint.IsTiny(1e-12);
                    }

                    // Pre-transform replacements eagerly so a failed transform
                    // becomes a per-item error instead of silently injecting
                    // world-coord geometry (the #24/#27 drift). Each target
                    // index is unique within a group (relational validation
                    // Phase 2), so one duplicate per replacement, same as before.
                    var replacementByIndex = new Dictionary<int, GeometryBase>();
                    var successfulSlots = new List<(Slot slot, ReplaceItemResolution res)>();
                    foreach (var (slot, res) in resolvedList)
                    {
                        // Batch has richer context than the helper's generic
                        // message (knows the idef and the raw sourceId), so the
                        // helper's errorMessage is discarded — the batch message
                        // is always the same rich form.
                        var normalized = DuplicateAndNormalizeSourceGeometry(
                            res.SourceObject, worldToLocal, needsTransform, out _);
                        if (normalized == null)
                        {
                            errors.Add(BuildBatchError(slot.RawName, slot.Shape.Index, "transform_failed",
                                $"Failed to transform source '{slot.Shape.SourceIdRaw}' to definition-local coords for block '{idef.Name}'"));
                            skipped++;
                            continue;
                        }
                        replacementByIndex[res.TargetIndex] = normalized;
                        successfulSlots.Add((slot, res));
                    }

                    // If every item in the group transform-failed, skip the SDK
                    // call entirely — no replacements to make, no group error.
                    if (successfulSlots.Count == 0)
                        continue;

                    // Build allGeometry / allAttributes from the fixed snapshot.
                    var allGeometry = new List<GeometryBase>(snapshot.Length);
                    var allAttributes = new List<ObjectAttributes>(snapshot.Length);

                    for (int i = 0; i < snapshot.Length; i++)
                    {
                        // Attributes preserved unchanged across all slots — the key parity invariant.
                        allAttributes.Add(snapshot[i].Attributes.Duplicate());

                        if (replacementByIndex.TryGetValue(i, out var replGeom))
                            allGeometry.Add(replGeom);
                        else
                            allGeometry.Add(snapshot[i].Geometry.Duplicate());
                    }

                    bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);
                    if (!modified)
                    {
                        // SDK-level group failure cements group_modify_failed for
                        // the successful-so-far slots; transform-failed slots are
                        // already in the errors list above.
                        foreach (var (slot, _) in successfulSlots)
                        {
                            errors.Add(BuildBatchError(slot.RawName, slot.Shape.Index, "group_modify_failed",
                                $"Failed to modify block '{idef.Name}'"));
                            skipped++;
                        }
                        continue;
                    }

                    // Group succeeded — cement routed status and queue deletions
                    // for effective-true sources (only for slots whose transform
                    // actually succeeded; transform-failed slots stay skipped).
                    foreach (var (slot, _) in successfulSlots)
                    {
                        routed++;
                        if (slot.Shape.DeleteOriginal && deletionSet.Add(slot.Shape.SourceGuid))
                            deletionOrder.Add(slot.Shape.SourceGuid);
                    }
                }

                // ==== Deferred deletions ====
                // Failed Delete calls are silent — routed already cemented; deletedSources is the authoritative audit.
                var deletedSources = new List<string>();
                foreach (var guid in deletionOrder)
                {
                    var sourceObj = doc.Objects.FindId(guid);
                    if (sourceObj != null && doc.Objects.Delete(sourceObj, true))
                        deletedSources.Add(guid.ToString());
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = total,
                    ["deletedSources"] = deletedSources,
                    ["errors"] = errors,
                };

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch replace object geometry failed: {ex.Message}" };
            }
        }

        // ---- Batch-local helpers for error construction and slot state ----

        private sealed class Slot
        {
            public int RequestIndex;
            public JsonElement? RawName;  // raw JsonElement for verbatim name echo in error rows
            public ReplaceItemShape Shape;
        }

        private static string ShapeErrorCode(ReplaceItemShapeError err) => err switch
        {
            ReplaceItemShapeError.InvalidName => "invalid_name",
            ReplaceItemShapeError.InvalidIndex => "invalid_index",
            ReplaceItemShapeError.InvalidSourceId => "invalid_source_id",
            ReplaceItemShapeError.InvalidDeleteFlag => "invalid_delete_flag",
            _ => "exception",
        };

        private static string ResolutionErrorCode(ReplaceItemResolutionError err) => err switch
        {
            ReplaceItemResolutionError.SourceNotFound => "source_not_found",
            ReplaceItemResolutionError.SourceHasNoGeometry => "source_has_no_geometry",
            ReplaceItemResolutionError.IndexOutOfRange => "index_out_of_range",
            _ => "exception",
        };

        private static Dictionary<string, object?> BuildBatchError(
            JsonElement? rawName,
            int? index,
            string errorCode,
            string? message)
        {
            var entry = new Dictionary<string, object?>();
            // rawName echoes verbatim including non-string / null / missing ("" sentinel).
            // STJ serializes boxed JsonElement in an object? value by emitting its raw JSON.
            entry["name"] = rawName.HasValue ? (object)rawName.Value : (object)"";
            if (index.HasValue)
                entry["index"] = index.Value;
            entry["error"] = errorCode;
            if (!string.IsNullOrEmpty(message))
                entry["message"] = message;
            return entry;
        }

        // ---- Transform-object shared helpers (used by single-target and batch) ----
        //
        // IMPORTANT: TryParseTransformSpec is LOOSE on zero-scale (factor: 0 and scale3d
        // components of 0 are accepted at parse phase) to preserve single-target wire
        // parity. Do NOT reuse TryParseScaleOp here — it serves the TransformInstance
        // family, operates on a different scale shape (scalar-or-3-array), and rejects
        // zero as invalid_scale. Swapping helpers would silently tighten the public
        // contract for rhino_block_transform_object. Any future tightening here must be
        // opt-in (pattern: strictDeleteFlag in PR #21), never a silent change.

        private enum TransformItemShapeError
        {
            None,
            InvalidName,
            InvalidIndices,
            InvalidTransform,
            InvalidTransformType,
            InvalidMove,
            InvalidRotate,
            InvalidScale,
            InvalidScale3d,
        }

        private readonly struct TransformItemShape
        {
            public readonly string Name;
            public readonly HashSet<int> Indices;   // deduped; serialize ascending for API stability
            public readonly Transform Xform;
            public readonly string XformType;       // lower-invariant; echoed in single-target response

            public TransformItemShape(string name, HashSet<int> indices, Transform xform, string xformType)
            {
                Name = name;
                Indices = indices;
                Xform = xform;
                XformType = xformType;
            }
        }

        // Parse transform spec into a Transform. Loose on zero-scale by design.
        private static TransformItemShapeError TryParseTransformSpec(
            JsonElement xformEl,
            out Transform xform,
            out string xformType,
            out string? errorMessage)
        {
            xform = Transform.Identity;
            xformType = "";
            errorMessage = null;

            if (xformEl.ValueKind != JsonValueKind.Object)
            {
                errorMessage = "transform object required";
                return TransformItemShapeError.InvalidTransform;
            }

            if (!xformEl.TryGetProperty("type", out var typeEl) || typeEl.ValueKind != JsonValueKind.String)
            {
                errorMessage = "transform.type required (string)";
                return TransformItemShapeError.InvalidTransformType;
            }
            xformType = typeEl.GetString()?.ToLowerInvariant() ?? "";

            switch (xformType)
            {
                case "move":
                {
                    if (!TryReadOptionalNumber(xformEl, "x", out double x, out errorMessage)
                        || !TryReadOptionalNumber(xformEl, "y", out double y, out errorMessage)
                        || !TryReadOptionalNumber(xformEl, "z", out double z, out errorMessage))
                    {
                        return TransformItemShapeError.InvalidMove;
                    }
                    xform = Transform.Translation(x, y, z);
                    return TransformItemShapeError.None;
                }
                case "rotate":
                {
                    if (!xformEl.TryGetProperty("angle", out var angleEl) || angleEl.ValueKind != JsonValueKind.Number)
                    {
                        errorMessage = "rotate.angle required (number, degrees)";
                        return TransformItemShapeError.InvalidRotate;
                    }
                    double angleRad = angleEl.GetDouble() * Math.PI / 180.0;

                    if (!TryReadVector3d(xformEl, "axis", Vector3d.ZAxis, out Vector3d axis, out errorMessage))
                        return TransformItemShapeError.InvalidRotate;
                    if (!TryReadPoint3d(xformEl, "center", Point3d.Origin, out Point3d center, out errorMessage))
                        return TransformItemShapeError.InvalidRotate;

                    xform = Transform.Rotation(angleRad, axis, center);
                    return TransformItemShapeError.None;
                }
                case "scale":
                {
                    if (!xformEl.TryGetProperty("factor", out var factorEl) || factorEl.ValueKind != JsonValueKind.Number)
                    {
                        errorMessage = "scale.factor required (number)";
                        return TransformItemShapeError.InvalidScale;
                    }
                    double factor = factorEl.GetDouble();
                    // Zero factor is accepted (loose parity with single-target). Runtime outcome
                    // depends on geom.Transform for the chosen geometry.

                    if (!TryReadPoint3d(xformEl, "center", Point3d.Origin, out Point3d center, out errorMessage))
                        return TransformItemShapeError.InvalidScale;

                    xform = Transform.Scale(center, factor);
                    return TransformItemShapeError.None;
                }
                case "scale3d":
                {
                    if (!TryReadOptionalNumber(xformEl, "x", out double sx, out errorMessage, defaultValue: 1.0))
                        return TransformItemShapeError.InvalidScale3d;
                    if (!TryReadOptionalNumber(xformEl, "y", out double sy, out errorMessage, defaultValue: 1.0))
                        return TransformItemShapeError.InvalidScale3d;
                    if (!TryReadOptionalNumber(xformEl, "z", out double sz, out errorMessage, defaultValue: 1.0))
                        return TransformItemShapeError.InvalidScale3d;
                    // Zero components accepted (loose parity with single-target).

                    if (!TryReadPoint3d(xformEl, "center", Point3d.Origin, out Point3d center, out errorMessage))
                        return TransformItemShapeError.InvalidScale3d;

                    var plane = new Plane(center, Vector3d.XAxis, Vector3d.YAxis);
                    xform = Transform.Scale(plane, sx, sy, sz);
                    return TransformItemShapeError.None;
                }
                default:
                    errorMessage = $"Unknown transform type '{xformType}'. Supported: move, rotate, scale, scale3d";
                    return TransformItemShapeError.InvalidTransformType;
            }
        }

        // Returns true if absent or numeric. On non-numeric present, sets errorMessage and returns false.
        private static bool TryReadOptionalNumber(JsonElement parent, string name, out double value, out string? errorMessage, double defaultValue = 0.0)
        {
            value = defaultValue;
            errorMessage = null;
            if (!parent.TryGetProperty(name, out var el)) return true;
            if (el.ValueKind != JsonValueKind.Number)
            {
                errorMessage = $"{name} must be a number";
                return false;
            }
            value = el.GetDouble();
            return true;
        }

        // Match pre-refactor loose behavior for axis/center overrides exactly:
        //   absent         -> silent default
        //   non-array      -> silent default (old inline code only entered the branch on ValueKind == Array)
        //   short array    -> silent default (old inline code only applied override when arr.Length >= 3)
        //   long-enough array with non-numeric element(s) -> error. Pre-refactor the .GetDouble()
        //     would have thrown and been caught by the outer try/catch as "Transform block object
        //     failed: ...". Surfacing as invalid_rotate / invalid_scale / invalid_scale3d is the
        //     same class of exception-path cleanup PR #21 established.
        private static bool TryReadPoint3d(JsonElement parent, string name, Point3d defaultValue, out Point3d value, out string? errorMessage)
        {
            value = defaultValue;
            errorMessage = null;
            if (!parent.TryGetProperty(name, out var el)) return true;
            if (el.ValueKind != JsonValueKind.Array) return true;
            var arr = el.EnumerateArray().ToArray();
            if (arr.Length < 3) return true;
            if (arr[0].ValueKind != JsonValueKind.Number
                || arr[1].ValueKind != JsonValueKind.Number
                || arr[2].ValueKind != JsonValueKind.Number)
            {
                errorMessage = $"{name} elements must be numeric";
                return false;
            }
            value = new Point3d(arr[0].GetDouble(), arr[1].GetDouble(), arr[2].GetDouble());
            return true;
        }

        private static bool TryReadVector3d(JsonElement parent, string name, Vector3d defaultValue, out Vector3d value, out string? errorMessage)
        {
            value = defaultValue;
            errorMessage = null;
            if (!parent.TryGetProperty(name, out var el)) return true;
            if (el.ValueKind != JsonValueKind.Array) return true;
            var arr = el.EnumerateArray().ToArray();
            if (arr.Length < 3) return true;
            if (arr[0].ValueKind != JsonValueKind.Number
                || arr[1].ValueKind != JsonValueKind.Number
                || arr[2].ValueKind != JsonValueKind.Number)
            {
                errorMessage = $"{name} elements must be numeric";
                return false;
            }
            value = new Vector3d(arr[0].GetDouble(), arr[1].GetDouble(), arr[2].GetDouble());
            return true;
        }

        // Parse one item's {name, indices[], transform} into shape record.
        // Dedupes indices via HashSet<int>. Caller serializes ascending for wire stability.
        private static TransformItemShapeError TryParseTransformItemShape(
            JsonElement itemEl,
            out TransformItemShape shape,
            out string? errorMessage)
        {
            shape = default;
            errorMessage = null;

            if (itemEl.ValueKind != JsonValueKind.Object)
            {
                errorMessage = "Item must be a JSON object";
                return TransformItemShapeError.InvalidName;
            }

            string? blockName = null;
            if (itemEl.TryGetProperty("name", out var nameEl) && nameEl.ValueKind == JsonValueKind.String)
                blockName = nameEl.GetString();
            if (string.IsNullOrEmpty(blockName))
            {
                errorMessage = "Block name required";
                return TransformItemShapeError.InvalidName;
            }

            if (!itemEl.TryGetProperty("indices", out var indicesEl) || indicesEl.ValueKind != JsonValueKind.Array)
            {
                errorMessage = "indices array required";
                return TransformItemShapeError.InvalidIndices;
            }
            var deduped = new HashSet<int>();
            foreach (var idx in indicesEl.EnumerateArray())
            {
                if (idx.ValueKind != JsonValueKind.Number || !idx.TryGetInt32(out int iv))
                {
                    errorMessage = "indices must be integers";
                    return TransformItemShapeError.InvalidIndices;
                }
                deduped.Add(iv);
            }
            if (deduped.Count == 0)
            {
                errorMessage = "At least one index required";
                return TransformItemShapeError.InvalidIndices;
            }

            if (!itemEl.TryGetProperty("transform", out var xformEl))
            {
                errorMessage = "transform object required";
                return TransformItemShapeError.InvalidTransform;
            }

            var specErr = TryParseTransformSpec(xformEl, out Transform xform, out string xformType, out errorMessage);
            if (specErr != TransformItemShapeError.None)
                return specErr;

            shape = new TransformItemShape(blockName!, deduped, xform, xformType);
            return TransformItemShapeError.None;
        }

        // Validate deduped index set against a fixed snapshot. Returns the first out-of-range
        // index in ASCENDING order for deterministic error messages (HashSet<int> iteration order
        // is undefined). The batch handler needs stable error output across runs; the single-target
        // call site prior to this refactor was also effectively undefined, so switching to
        // ascending is strictly better here.
        private static bool TryValidateItemIndicesAgainstSnapshot(
            RhinoObject[] existingObjects,
            HashSet<int> indices,
            out int offendingIndex,
            out string? errorMessage)
        {
            errorMessage = null;
            offendingIndex = 0;
            foreach (int idx in indices.OrderBy(i => i))
            {
                if (idx < 0 || idx >= existingObjects.Length)
                {
                    offendingIndex = idx;
                    errorMessage = $"Object index {idx} out of range (block has {existingObjects.Length} objects)";
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// POST /block/transform-object - Transform objects within a block definition by index.
        /// Body: { "name": "BlockA", "indices": [0, 2], "transform": { "type": "move", "x": 5, "y": 0, "z": 0 } }
        /// Supported transforms: move, rotate, scale, scale3d
        /// </summary>
        public ApiResponse TransformBlockObject(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
            {
                return new ApiResponse { Success = false, Data = "No active document" };
            }

            try
            {
                if (string.IsNullOrEmpty(body))
                {
                    return new ApiResponse { Success = false, Data = "Request body required" };
                }

                var request = JsonSerializer.Deserialize<JsonElement>(body);

                var shapeErr = TryParseTransformItemShape(request, out var shape, out var shapeMsg);
                if (shapeErr != TransformItemShapeError.None)
                {
                    return new ApiResponse { Success = false, Data = shapeMsg ?? "Invalid request" };
                }

                var idef = doc.InstanceDefinitions.Find(shape.Name);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{shape.Name}' not found" };
                }

                var existingObjects = idef.GetObjects();
                if (!TryValidateItemIndicesAgainstSnapshot(existingObjects, shape.Indices, out int _, out string? resMsg))
                {
                    return new ApiResponse { Success = false, Data = resMsg ?? "Invalid request" };
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();
                var failedIndices = new List<int>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    var geom = existingObjects[i].Geometry.Duplicate();
                    if (shape.Indices.Contains(i))
                    {
                        if (!geom.Transform(shape.Xform))
                        {
                            failedIndices.Add(i);
                        }
                    }
                    allGeometry.Add(geom);
                    allAttributes.Add(existingObjects[i].Attributes.Duplicate());
                }

                if (failedIndices.Count > 0)
                {
                    return new ApiResponse
                    {
                        Success = false,
                        Data = $"Transform failed for object(s) at index {string.Join(", ", failedIndices.OrderBy(i => i))}. No changes applied."
                    };
                }

                using var undo = new UndoScope(doc, "Transform Block Objects");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{shape.Name}'" };
                }

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = shape.Name,
                        ["objectCount"] = existingObjects.Length,
                        ["transformedIndices"] = shape.Indices.OrderBy(i => i).ToArray(),
                        ["transformType"] = shape.XformType
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Transform block object failed: {ex.Message}" };
            }
        }

        /// <summary>
        /// POST /block/transform-object-batch - Batch variant. Apply move/rotate/scale/scale3d
        /// transforms to objects inside one or more block definitions in a single call. Items
        /// targeting the same block are coalesced into a single ModifyGeometry call per definition.
        /// Best-effort per-item semantics under one UndoScope; item is the atomic unit.
        /// Body: { "items": [{ "name": "BlockA", "indices": [0, 1], "transform": {...} }], "redraw": false }
        /// </summary>
        public ApiResponse TransformBlockObjectBatch(string? body)
        {
            var doc = DocumentContext.GetDocument();
            if (doc == null)
                return new ApiResponse { Success = false, Data = "No active document" };

            try
            {
                if (string.IsNullOrEmpty(body))
                    return new ApiResponse { Success = false, Data = "Request body required" };

                var request = JsonSerializer.Deserialize<JsonElement>(body);
                // Envelope guard inherited from PR #21: JsonElement.TryGetProperty throws
                // InvalidOperationException on non-object kinds.
                if (request.ValueKind != JsonValueKind.Object)
                    return new ApiResponse { Success = false, Data = "Request body must be a JSON object" };
                if (!request.TryGetProperty("items", out var itemsEl) || itemsEl.ValueKind != JsonValueKind.Array)
                    return new ApiResponse { Success = false, Data = "'items' array required" };

                bool redraw = true;
                if (request.TryGetProperty("redraw", out var redrawEl))
                {
                    if (redrawEl.ValueKind != JsonValueKind.True && redrawEl.ValueKind != JsonValueKind.False)
                        return new ApiResponse { Success = false, Data = "'redraw' must be a boolean" };
                    redraw = redrawEl.GetBoolean();
                }

                int total = itemsEl.GetArrayLength();
                int routed = 0, skipped = 0;
                var errors = new List<Dictionary<string, object?>>();

                var slots = new List<TransformSlot>();

                using var undo = new UndoScope(doc, "Batch Transform Block Objects");

                // ==== Phase 1: Shape validation (per item, independent) ====
                int requestIdx = -1;
                foreach (var itemEl in itemsEl.EnumerateArray())
                {
                    requestIdx++;

                    // Capture raw name JsonElement for verbatim echo in errors, including
                    // non-string / null / missing (per PR #21 convention).
                    JsonElement? rawName = null;
                    if (itemEl.ValueKind == JsonValueKind.Object && itemEl.TryGetProperty("name", out var nEl))
                        rawName = nEl.Clone();

                    // Pre-parse indices for error echo independently of the full-shape helper
                    // (PR #21 pre-parse pattern). The design rule is: errors[].indices echoes
                    // in ascending order whenever indices[] parsed successfully; omitted only
                    // on invalid_indices. If the item has valid indices but a bad name or
                    // transform, we still want the parseable set in diagnostics.
                    int[]? parseableIndicesAsc = null;
                    if (itemEl.ValueKind == JsonValueKind.Object
                        && itemEl.TryGetProperty("indices", out var rawIdxEl)
                        && rawIdxEl.ValueKind == JsonValueKind.Array)
                    {
                        var echoSet = new HashSet<int>();
                        bool allIntegers = true;
                        foreach (var ix in rawIdxEl.EnumerateArray())
                        {
                            if (ix.ValueKind != JsonValueKind.Number || !ix.TryGetInt32(out int iv))
                            {
                                allIntegers = false;
                                break;
                            }
                            echoSet.Add(iv);
                        }
                        if (allIntegers && echoSet.Count > 0)
                            parseableIndicesAsc = echoSet.OrderBy(i => i).ToArray();
                    }

                    var shapeErr = TryParseTransformItemShape(itemEl, out var shape, out var shapeMsg);
                    if (shapeErr != TransformItemShapeError.None)
                    {
                        // Omit indices on invalid_indices (the offending field itself); echo
                        // the parseable set on other shape errors (invalid_name, invalid_transform,
                        // invalid_transform_type, invalid_move/rotate/scale/scale3d).
                        int[]? indicesToEcho = (shapeErr == TransformItemShapeError.InvalidIndices) ? null : parseableIndicesAsc;
                        errors.Add(BuildBatchTransformError(rawName, indicesAsc: indicesToEcho, TransformShapeErrorCode(shapeErr), shapeMsg));
                        skipped++;
                        continue;
                    }

                    slots.Add(new TransformSlot { RequestIndex = requestIdx, RawName = rawName, Shape = shape });
                }

                // ==== Phase 2: Relational validation (cross-item, first-occurrence-wins) ====
                // Per-block claim set of already-taken indices. Overlap of ANY of an item's indices
                // with an earlier item's claim set for the same block -> whole item skipped.
                var claims = new Dictionary<string, HashSet<int>>(StringComparer.Ordinal);
                var survivors = new List<TransformSlot>();
                foreach (var slot in slots)
                {
                    if (!claims.TryGetValue(slot.Shape.Name, out var claimed))
                    {
                        claimed = new HashSet<int>();
                        claims[slot.Shape.Name] = claimed;
                    }

                    // Find the overlap subset (ascending for deterministic message).
                    var overlap = slot.Shape.Indices.Where(i => claimed.Contains(i)).OrderBy(i => i).ToArray();
                    if (overlap.Length > 0)
                    {
                        errors.Add(BuildBatchTransformError(
                            slot.RawName,
                            slot.Shape.Indices.OrderBy(i => i).ToArray(),
                            "overlapping_indices",
                            $"Indices {string.Join(", ", overlap)} already claimed by an earlier item for block '{slot.Shape.Name}'"));
                        skipped++;
                        continue;
                    }
                    // Claim the item's indices for future overlap detection.
                    foreach (int i in slot.Shape.Indices) claimed.Add(i);
                    survivors.Add(slot);
                }

                // ==== Phase 3: Grouping and resolution (per-group fixed snapshot) ====
                // Preserve in-group order from survivors.
                var groupOrder = new List<string>();
                var groupItems = new Dictionary<string, List<TransformSlot>>(StringComparer.Ordinal);
                foreach (var slot in survivors)
                {
                    if (!groupItems.ContainsKey(slot.Shape.Name))
                    {
                        groupOrder.Add(slot.Shape.Name);
                        groupItems[slot.Shape.Name] = new List<TransformSlot>();
                    }
                    groupItems[slot.Shape.Name].Add(slot);
                }

                var resolvedGroups = new List<(InstanceDefinition idef, RhinoObject[] snapshot, List<TransformSlot> items)>();
                foreach (var name in groupOrder)
                {
                    var idef = doc.InstanceDefinitions.Find(name);
                    if (idef == null)
                    {
                        foreach (var slot in groupItems[name])
                        {
                            errors.Add(BuildBatchTransformError(
                                slot.RawName,
                                slot.Shape.Indices.OrderBy(i => i).ToArray(),
                                "block_not_found",
                                $"Block definition '{name}' not found"));
                            skipped++;
                        }
                        continue;
                    }

                    // Fixed snapshot read once per group.
                    var existingObjects = idef.GetObjects();
                    var resolvedItems = new List<TransformSlot>();
                    foreach (var slot in groupItems[name])
                    {
                        if (!TryValidateItemIndicesAgainstSnapshot(existingObjects, slot.Shape.Indices, out int _, out string? resMsg))
                        {
                            errors.Add(BuildBatchTransformError(
                                slot.RawName,
                                slot.Shape.Indices.OrderBy(i => i).ToArray(),
                                "index_out_of_range",
                                resMsg));
                            skipped++;
                            continue;
                        }
                        resolvedItems.Add(slot);
                    }

                    if (resolvedItems.Count > 0)
                        resolvedGroups.Add((idef, existingObjects, resolvedItems));
                }

                // ==== Phase 4: Per-group rebuild (try-then-commit per item) ====
                foreach (var (idef, snapshot, items) in resolvedGroups)
                {
                    // Attribute preservation invariant (inherited from PR #21): allAttributes
                    // is untouched across ALL slots; allGeometry starts as snapshot clones and is
                    // overwritten only at indices of successfully-transformed items.
                    var allGeometry = new List<GeometryBase>(snapshot.Length);
                    var allAttributes = new List<ObjectAttributes>(snapshot.Length);
                    for (int i = 0; i < snapshot.Length; i++)
                    {
                        allGeometry.Add(snapshot[i].Geometry.Duplicate());
                        allAttributes.Add(snapshot[i].Attributes.Duplicate());
                    }

                    // Track which items committed so we can mark group_modify_failed correctly.
                    var committedItems = new List<TransformSlot>();

                    foreach (var slot in items)
                    {
                        // Try-then-commit: transform a duplicated copy at each target index. If any
                        // index's geom.Transform returns false, discard the proposals and skip the
                        // whole item (item_transform_failed). Siblings in the same group continue.
                        var proposed = new Dictionary<int, GeometryBase>();
                        var failed = new List<int>();
                        foreach (int idx in slot.Shape.Indices)
                        {
                            var candidate = snapshot[idx].Geometry.Duplicate();
                            if (!candidate.Transform(slot.Shape.Xform))
                            {
                                failed.Add(idx);
                            }
                            else
                            {
                                proposed[idx] = candidate;
                            }
                        }

                        if (failed.Count > 0)
                        {
                            var failedAsc = failed.OrderBy(i => i).ToArray();
                            errors.Add(BuildBatchTransformError(
                                slot.RawName,
                                slot.Shape.Indices.OrderBy(i => i).ToArray(),
                                "item_transform_failed",
                                $"geom.Transform returned false for index(es) {string.Join(", ", failedAsc)}"));
                            skipped++;
                            continue;
                        }

                        // All proposals succeeded; commit into the group's image.
                        foreach (var kvp in proposed)
                            allGeometry[kvp.Key] = kvp.Value;
                        committedItems.Add(slot);
                    }

                    if (committedItems.Count == 0)
                        continue;

                    bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);
                    if (!modified)
                    {
                        foreach (var slot in committedItems)
                        {
                            errors.Add(BuildBatchTransformError(
                                slot.RawName,
                                slot.Shape.Indices.OrderBy(i => i).ToArray(),
                                "group_modify_failed",
                                $"Failed to modify block '{idef.Name}'"));
                            skipped++;
                        }
                        continue;
                    }

                    routed += committedItems.Count;
                }

                if (redraw)
                    doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["routed"] = routed,
                    ["skipped"] = skipped,
                    ["total"] = total,
                    ["errors"] = errors,
                };

                return new ApiResponse { Success = true, Data = result };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Batch transform block object failed: {ex.Message}" };
            }
        }

        // ---- Batch-local helpers for TransformBlockObjectBatch ----

        private sealed class TransformSlot
        {
            public int RequestIndex;
            public JsonElement? RawName;       // raw JsonElement for verbatim name echo
            public TransformItemShape Shape;
        }

        private static string TransformShapeErrorCode(TransformItemShapeError err) => err switch
        {
            TransformItemShapeError.InvalidName => "invalid_name",
            TransformItemShapeError.InvalidIndices => "invalid_indices",
            TransformItemShapeError.InvalidTransform => "invalid_transform",
            TransformItemShapeError.InvalidTransformType => "invalid_transform_type",
            TransformItemShapeError.InvalidMove => "invalid_move",
            TransformItemShapeError.InvalidRotate => "invalid_rotate",
            TransformItemShapeError.InvalidScale => "invalid_scale",
            TransformItemShapeError.InvalidScale3d => "invalid_scale3d",
            _ => "exception",
        };

        private static Dictionary<string, object?> BuildBatchTransformError(
            JsonElement? rawName,
            int[]? indicesAsc,
            string errorCode,
            string? message)
        {
            var entry = new Dictionary<string, object?>();
            // rawName echoes verbatim including non-string / null / missing ("" sentinel).
            // STJ serializes boxed JsonElement in an object? value by emitting its raw JSON.
            entry["name"] = rawName.HasValue ? (object)rawName.Value : (object)"";
            if (indicesAsc != null)
                entry["indices"] = indicesAsc;
            entry["error"] = errorCode;
            if (!string.IsNullOrEmpty(message))
                entry["message"] = message;
            return entry;
        }

        /// <summary>
        /// Parse a scale JsonElement into a Transform pivoted at <paramref name="pivot"/>.
        /// Accepts a scalar or a 3-element numeric array. Zero scalar or any zero element
        /// is rejected as "invalid_scale" — composing a zero-scale transform produces
        /// degenerate geometry, and surfacing the error is more useful than silent damage.
        /// No epsilon: zero means exact 0.
        /// </summary>
        private static bool TryParseScaleOp(
            JsonElement scaleEl,
            Point3d pivot,
            out Transform scaleXform,
            out string? description,
            out string? errorCode)
        {
            scaleXform = Transform.Identity;
            description = null;
            errorCode = null;

            if (scaleEl.ValueKind == JsonValueKind.Array)
            {
                var factors = new List<double>();
                foreach (var e in scaleEl.EnumerateArray())
                {
                    if (e.ValueKind != JsonValueKind.Number)
                    {
                        errorCode = "invalid_scale";
                        return false;
                    }
                    factors.Add(e.GetDouble());
                }
                if (factors.Count != 3)
                {
                    errorCode = "invalid_scale";
                    return false;
                }
                if (factors[0] == 0.0 || factors[1] == 0.0 || factors[2] == 0.0)
                {
                    errorCode = "invalid_scale";
                    return false;
                }
                var plane = new Plane(pivot, Vector3d.XAxis, Vector3d.YAxis);
                scaleXform = Transform.Scale(plane, factors[0], factors[1], factors[2]);
                description = $"scale [{factors[0]}, {factors[1]}, {factors[2]}]";
                return true;
            }
            if (scaleEl.ValueKind == JsonValueKind.Number)
            {
                double factor = scaleEl.GetDouble();
                if (factor == 0.0)
                {
                    errorCode = "invalid_scale";
                    return false;
                }
                scaleXform = Transform.Scale(pivot, factor);
                description = $"scale {factor}";
                return true;
            }

            errorCode = "invalid_scale";
            return false;
        }
    }
}
