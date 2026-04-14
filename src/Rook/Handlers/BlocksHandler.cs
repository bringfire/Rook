using System;
using System.Collections.Generic;
using System.Linq;
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
        /// POST /block/create - Creates a block definition from specified objects.
        /// Body: { "ids": ["guid1", "guid2"], "name": "MyBlock", "basePoint": [0,0,0], "deleteObjects": true }
        /// </summary>
        public ApiResponse CreateBlock(string? body)
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

            List<Guid> objectIds = new();
            string? blockName = null;
            Point3d basePoint = Point3d.Origin;
            bool deleteObjects = true;

            if (request.TryGetValue("ids", out var idsEl))
            {
                objectIds = idsEl.EnumerateArray()
                    .Select(e => Guid.TryParse(e.GetString(), out var g) ? g : Guid.Empty)
                    .Where(g => g != Guid.Empty)
                    .ToList();
            }

            if (request.TryGetValue("name", out var nameEl))
            {
                blockName = nameEl.GetString();
            }

            if (request.TryGetValue("basePoint", out var bpEl))
            {
                var coords = bpEl.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                if (coords.Length >= 3)
                {
                    basePoint = new Point3d(coords[0], coords[1], coords[2]);
                }
            }

            if (request.TryGetValue("deleteObjects", out var delEl))
            {
                deleteObjects = delEl.GetBoolean();
            }

            if (objectIds.Count == 0)
            {
                return new ApiResponse { Success = false, Data = "No valid object IDs provided" };
            }

            if (string.IsNullOrEmpty(blockName))
            {
                blockName = $"Block_{DateTime.Now:yyyyMMddHHmmss}";
            }

            // Check if block name already exists
            var existingDef = doc.InstanceDefinitions.Find(blockName);
            if (existingDef != null)
            {
                return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' already exists" };
            }

            try
            {
                // Get the RhinoObjects and their geometry
                var rhinoObjects = objectIds
                    .Select(id => doc.Objects.FindId(id))
                    .Where(obj => obj != null)
                    .ToArray();

                if (rhinoObjects.Length == 0)
                {
                    return new ApiResponse { Success = false, Data = "No valid objects found" };
                }

                // Extract geometry from the RhinoObjects
                var geometries = rhinoObjects
                    .Select(obj => obj!.Geometry)
                    .Where(g => g != null)
                    .ToArray();

                var attributes = rhinoObjects
                    .Select(obj => obj!.Attributes)
                    .ToArray();

                // Create the block definition
                using var undo = new UndoScope(doc, "Create Block");
                var idefIndex = doc.InstanceDefinitions.Add(blockName, "", basePoint, geometries!, attributes);

                if (idefIndex < 0)
                {
                    return new ApiResponse { Success = false, Data = "Failed to create block definition" };
                }

                // Optionally delete original objects and replace with instance
                Guid? instanceId = null;
                if (deleteObjects)
                {
                    // Delete original objects
                    foreach (var id in objectIds)
                    {
                        doc.Objects.Delete(id, true);
                    }

                    // Create instance at base point
                    var idef = doc.InstanceDefinitions[idefIndex];
                    var xform = Transform.Identity;
                    var insertedId = doc.Objects.AddInstanceObject(idefIndex, xform);
                    if (insertedId != Guid.Empty)
                    {
                        instanceId = insertedId;
                    }
                }

                doc.Views.Redraw();

                var result = new Dictionary<string, object>
                {
                    ["definitionIndex"] = idefIndex,
                    ["name"] = blockName,
                    ["objectCount"] = rhinoObjects.Length,
                    ["basePoint"] = new[] { basePoint.X, basePoint.Y, basePoint.Z }
                };

                if (instanceId.HasValue)
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
                return new ApiResponse { Success = false, Data = $"Create block failed: {ex.Message}" };
            }
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
        /// a structured error record, batch continues. Duplicate GUIDs apply in listed
        /// order with the pivot re-read between items.
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
                var blockName = request.GetProperty("name").GetString();
                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                if (!request.TryGetProperty("index", out var indexEl) || indexEl.ValueKind != JsonValueKind.Number)
                {
                    return new ApiResponse { Success = false, Data = "Object index required (integer)" };
                }
                int targetIndex = indexEl.GetInt32();

                var sourceIdStr = request.GetProperty("sourceId").GetString();
                if (string.IsNullOrEmpty(sourceIdStr) || !Guid.TryParse(sourceIdStr, out Guid sourceGuid))
                {
                    return new ApiResponse { Success = false, Data = "Valid sourceId (GUID) required" };
                }

                bool deleteOriginal = true;
                if (request.TryGetProperty("deleteOriginal", out var delEl) && delEl.ValueKind == JsonValueKind.False)
                {
                    deleteOriginal = false;
                }

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                var existingObjects = idef.GetObjects();
                if (targetIndex < 0 || targetIndex >= existingObjects.Length)
                {
                    return new ApiResponse { Success = false, Data = $"Object index {targetIndex} out of range (block has {existingObjects.Length} objects)" };
                }

                var sourceObj = doc.Objects.FindId(sourceGuid);
                if (sourceObj == null || sourceObj.Geometry == null)
                {
                    return new ApiResponse { Success = false, Data = $"Source object '{sourceIdStr}' not found in document" };
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    if (i == targetIndex)
                    {
                        // Replace geometry at target index with source object's geometry
                        allGeometry.Add(sourceObj.Geometry.Duplicate());
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
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                bool sourceDeleted = false;
                if (deleteOriginal)
                {
                    sourceDeleted = doc.Objects.Delete(sourceObj, true);
                }

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
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
                var blockName = request.GetProperty("name").GetString();
                if (string.IsNullOrEmpty(blockName))
                {
                    return new ApiResponse { Success = false, Data = "Block name required" };
                }

                if (!request.TryGetProperty("indices", out var indicesEl) || indicesEl.ValueKind != JsonValueKind.Array)
                {
                    return new ApiResponse { Success = false, Data = "indices array required" };
                }

                var indices = new HashSet<int>();
                foreach (var idx in indicesEl.EnumerateArray())
                {
                    if (idx.ValueKind != JsonValueKind.Number)
                    {
                        return new ApiResponse { Success = false, Data = "indices must be integers" };
                    }
                    indices.Add(idx.GetInt32());
                }

                if (indices.Count == 0)
                {
                    return new ApiResponse { Success = false, Data = "At least one index required" };
                }

                if (!request.TryGetProperty("transform", out var xformEl) || xformEl.ValueKind != JsonValueKind.Object)
                {
                    return new ApiResponse { Success = false, Data = "transform object required" };
                }

                var xformType = xformEl.GetProperty("type").GetString()?.ToLowerInvariant();

                var idef = doc.InstanceDefinitions.Find(blockName);
                if (idef == null)
                {
                    return new ApiResponse { Success = false, Data = $"Block definition '{blockName}' not found" };
                }

                var existingObjects = idef.GetObjects();

                // Validate all indices before mutation
                foreach (int idx in indices)
                {
                    if (idx < 0 || idx >= existingObjects.Length)
                    {
                        return new ApiResponse { Success = false, Data = $"Object index {idx} out of range (block has {existingObjects.Length} objects)" };
                    }
                }

                // Build the transform
                Transform xform;
                switch (xformType)
                {
                    case "move":
                    {
                        double x = xformEl.TryGetProperty("x", out var xp) ? xp.GetDouble() : 0;
                        double y = xformEl.TryGetProperty("y", out var yp) ? yp.GetDouble() : 0;
                        double z = xformEl.TryGetProperty("z", out var zp) ? zp.GetDouble() : 0;
                        xform = Transform.Translation(x, y, z);
                        break;
                    }
                    case "rotate":
                    {
                        double angleDeg = xformEl.GetProperty("angle").GetDouble();
                        double angleRad = angleDeg * Math.PI / 180.0;

                        Vector3d axis = Vector3d.ZAxis;
                        if (xformEl.TryGetProperty("axis", out var axisEl) && axisEl.ValueKind == JsonValueKind.Array)
                        {
                            var axisArr = axisEl.EnumerateArray().ToArray();
                            if (axisArr.Length >= 3)
                                axis = new Vector3d(axisArr[0].GetDouble(), axisArr[1].GetDouble(), axisArr[2].GetDouble());
                        }

                        Point3d center = Point3d.Origin;
                        if (xformEl.TryGetProperty("center", out var centerEl) && centerEl.ValueKind == JsonValueKind.Array)
                        {
                            var centerArr = centerEl.EnumerateArray().ToArray();
                            if (centerArr.Length >= 3)
                                center = new Point3d(centerArr[0].GetDouble(), centerArr[1].GetDouble(), centerArr[2].GetDouble());
                        }

                        xform = Transform.Rotation(angleRad, axis, center);
                        break;
                    }
                    case "scale":
                    {
                        double factor = xformEl.GetProperty("factor").GetDouble();

                        Point3d center = Point3d.Origin;
                        if (xformEl.TryGetProperty("center", out var centerEl) && centerEl.ValueKind == JsonValueKind.Array)
                        {
                            var centerArr = centerEl.EnumerateArray().ToArray();
                            if (centerArr.Length >= 3)
                                center = new Point3d(centerArr[0].GetDouble(), centerArr[1].GetDouble(), centerArr[2].GetDouble());
                        }

                        xform = Transform.Scale(center, factor);
                        break;
                    }
                    case "scale3d":
                    {
                        double sx = xformEl.TryGetProperty("x", out var sxp) ? sxp.GetDouble() : 1;
                        double sy = xformEl.TryGetProperty("y", out var syp) ? syp.GetDouble() : 1;
                        double sz = xformEl.TryGetProperty("z", out var szp) ? szp.GetDouble() : 1;

                        Point3d center = Point3d.Origin;
                        if (xformEl.TryGetProperty("center", out var centerEl) && centerEl.ValueKind == JsonValueKind.Array)
                        {
                            var centerArr = centerEl.EnumerateArray().ToArray();
                            if (centerArr.Length >= 3)
                                center = new Point3d(centerArr[0].GetDouble(), centerArr[1].GetDouble(), centerArr[2].GetDouble());
                        }

                        var plane = new Plane(center, Vector3d.XAxis, Vector3d.YAxis);
                        xform = Transform.Scale(plane, sx, sy, sz);
                        break;
                    }
                    default:
                        return new ApiResponse { Success = false, Data = $"Unknown transform type '{xformType}'. Supported: move, rotate, scale, scale3d" };
                }

                var allGeometry = new List<GeometryBase>();
                var allAttributes = new List<ObjectAttributes>();
                var failedIndices = new List<int>();

                for (int i = 0; i < existingObjects.Length; i++)
                {
                    var geom = existingObjects[i].Geometry.Duplicate();
                    if (indices.Contains(i))
                    {
                        if (!geom.Transform(xform))
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
                        Data = $"Transform failed for object(s) at index {string.Join(", ", failedIndices)}. No changes applied."
                    };
                }

                using var undo = new UndoScope(doc, "Transform Block Objects");
                bool modified = doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes);

                if (!modified)
                {
                    return new ApiResponse { Success = false, Data = $"Failed to modify block '{blockName}'" };
                }

                doc.Views.Redraw();

                return new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object>
                    {
                        ["blockName"] = blockName,
                        ["objectCount"] = existingObjects.Length,
                        ["transformedIndices"] = indices.OrderBy(i => i).ToArray(),
                        ["transformType"] = xformType ?? ""
                    }
                };
            }
            catch (Exception ex)
            {
                return new ApiResponse { Success = false, Data = $"Transform block object failed: {ex.Message}" };
            }
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
