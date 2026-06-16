using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// Orchestrates a read-only Revit -> Rhino export: resolve the element set, freeze identities,
    /// convert geometry, assemble an in-memory File3dm + sidecar + validation, write the bundle
    /// path-safely, and verify the Rhino-object <-> sidecar-record bijection. Never mutates the
    /// active Rhino document and never mutates the Revit model (no write scope is ever opened).
    /// </summary>
    internal sealed class RevitExportService
    {
        private const string ModelLayer = "RookBim::Model";

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.Never
        };

        private readonly RevitQueryService query = new RevitQueryService();
        private readonly RevitLabelExtractor labels = new RevitLabelExtractor();

        public BimApiResponse Export(Document document, View? activeView, BimExportElementsRequest request)
        {
            // 1. Output-path safety (revalidate at the service boundary).
            var pathShape = BimExportPathPolicy.ValidateRequestShape(request.Output);
            if (!pathShape.Success)
            {
                return BimApiResponse.Fail(pathShape.ErrorCode, pathShape.Message ?? "Invalid output path.", 400);
            }

            // The bundle is exactly three sibling artifacts: <name>.3dm (geometry), <name>.sidecar.json
            // (element/room records + frozen identities), <name>.validation.json (counts + hashes).
            var paths = BimExportPathPolicy.ResolveBundlePaths(request.Output.Directory!, request.Output.Name!);
            foreach (var path in new[] { paths.Model3dm, paths.Sidecar, paths.Validation })
            {
                if (BimExportPathPolicy.EscapesIntendedDirectory(path, request.Output.Directory!))
                {
                    return BimApiResponse.Fail(
                        BimErrorCode.OutputPathInvalid, "Resolved artifact path escapes the output directory.", 400);
                }

                if (!request.Output.Overwrite && File.Exists(path))
                {
                    return BimApiResponse.Fail(
                        BimErrorCode.OutputPathInvalid,
                        $"Bundle artifact already exists (set overwrite=true to replace): {Path.GetFileName(path)}",
                        409);
                }
            }

            // 2. Resolve the element set + freeze identities.
            var resolution = ResolveElements(document, activeView, request);
            if (resolution.Failure != null)
            {
                return resolution.Failure;
            }

            var scale = RevitGeometryConverter.ScaleFromFeet(request.Output.Units);
            var converter = new RevitGeometryConverter(scale);

            // 3. Build the in-memory File3dm + element records.
            var file = new Rhino.FileIO.File3dm();
            file.Settings.ModelUnitSystem = MapUnits(request.Output.Units);
            var modelLayerIndex = EnsureLayer(file, ModelLayer);

            var elementRecords = new List<object>();
            var counts = new BimExportCounts
            {
                Requested = resolution.RequestedCount,
                Resolved = resolution.Elements.Count,
                Truncated = resolution.Truncated
            };
            var exportedKeys = new HashSet<string>(StringComparer.Ordinal);

            foreach (var element in resolution.Elements)
            {
                var key = element.UniqueId;
                try
                {
                    // Order the throw-prone Revit calls (geometry conversion, label extraction,
                    // record building) BEFORE any geometry/bijection mutation so a throw never
                    // leaves a .3dm object without a matching exported key.
                    var conversion = converter.Convert(element, request.AllowBboxProxy);
                    var labelSet = labels.Extract(document, element);
                    elementRecords.Add(BuildElementRecord(document, element, conversion, labelSet));

                    if (conversion.HasGeometry)
                    {
                        AddGeometry(file, modelLayerIndex, element, conversion);
                        exportedKeys.Add(key);
                        switch (conversion.Quality)
                        {
                            case RevitGeometryConverter.QualityConvertedBrep: counts.ExportedBrep++; break;
                            case RevitGeometryConverter.QualityMeshFallback: counts.ExportedMesh++; break;
                            case RevitGeometryConverter.QualityBboxOnly: counts.ExportedBboxProxy++; break;
                        }
                    }
                    else
                    {
                        counts.Failed++;
                    }
                }
                catch (Exception ex)
                {
                    // A single degenerate element must not abort the whole export.
                    counts.Failed++;
                    elementRecords.Add(BuildFailedElementRecord(element, ex));
                }
            }

            // 4. Rooms (typed separately).
            var roomRecords = new List<object>();
            if (request.EffectiveRooms != BimRoomsMode.Exclude)
            {
                var includeGeometry = request.EffectiveRooms == BimRoomsMode.Both;
                var roomLayerIndex = EnsureLayer(file, RevitRoomExporter.RoomsLayer);
                var rooms = new RevitRoomExporter(scale).ExportRooms(document);
                counts.Rooms = rooms.Count;
                foreach (var room in rooms)
                {
                    var rep = MaterializeRoom(file, roomLayerIndex, room, scale, includeGeometry);
                    roomRecords.Add(new
                    {
                        roomId = room.UniqueId,
                        uniqueId = room.UniqueId,
                        number = room.Number,
                        name = room.Name,
                        geometryRepresentation = rep,
                        referenceGeometry = true
                    });
                }
            }

            // 5. NoExportableGeometry guard.
            if (resolution.Elements.Count > 0 && counts.ExportedBrep + counts.ExportedMesh + counts.ExportedBboxProxy == 0)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoExportableGeometry,
                    "No element produced exportable geometry (retry with allowBboxProxy=true or a different selection).",
                    422);
            }

            // 6. Verify the bijection BEFORE writing.
            var verification = VerifyBijection(file, exportedKeys);

            // 7. Assemble sidecar + validation; write all three path-safely.
            var sidecar = BuildSidecar(document, request, resolution, elementRecords, roomRecords);
            var sidecarJson = JsonSerializer.Serialize(sidecar, JsonOptions);

            // Only paths this run actually attempts to write are eligible for cleanup; with
            // overwrite=true a pre-existing sibling we never wrote must never be deleted.
            var written = new List<string>();

            try
            {
                // A failed/partial File3dm.Write can still leave a partial file, so it is cleanable.
                written.Add(paths.Model3dm);
                if (!file.Write(paths.Model3dm, 7))
                {
                    return CleanupAndFail(written, "Failed to write the .3dm bundle artifact.");
                }

                File.WriteAllText(paths.Sidecar, sidecarJson, new UTF8Encoding(false));
                written.Add(paths.Sidecar);

                var validation = BuildValidation(document, counts, scale, request.Output.Units, paths, sidecarJson);
                File.WriteAllText(paths.Validation, JsonSerializer.Serialize(validation, JsonOptions), new UTF8Encoding(false));
                written.Add(paths.Validation);
            }
            catch (Exception ex)
            {
                return CleanupAndFail(written, $"Bundle write failed: {ex.GetType().Name}: {ex.Message}");
            }

            if (!verification.Ok)
            {
                CleanupBundle(written);
                var failure = BimApiResponse.Fail(
                    BimErrorCode.ExportFailed, "Export bijection verification failed; bundle is not a trustworthy fixture.", 500);
                failure.Data = new { verification };
                return failure;
            }

            return BimApiResponse.Ok(new BimExportResult
            {
                Paths = paths,
                Counts = counts,
                Verification = verification,
                SourceUnits = "feet",
                TargetUnits = request.Output.Units,
                UnitScaleFactor = scale
            });
        }

        private ElementResolution ResolveElements(Document document, View? activeView, BimExportElementsRequest request)
        {
            if (request.HasIdentities)
            {
                var elements = new List<Element>();
                foreach (var identity in request.Identities!)
                {
                    var resolved = RevitIdentitySerializer.Resolve(document, identity);
                    if (!resolved.Success)
                    {
                        return ElementResolution.Fail(BimApiResponse.Fail(
                            resolved.ErrorCode,
                            resolved.Message ?? "An element identity did not resolve.",
                            404));
                    }

                    elements.Add(resolved.Element!);
                }

                return ElementResolution.Ok(elements, truncated: false, requestedCount: request.Identities!.Count);
            }

            var queryResponse = query.Query(document, activeView, request.Selector!);
            if (!queryResponse.Success || !(queryResponse.Data is BimQueryElementsResult queryResult))
            {
                return ElementResolution.Fail(queryResponse);
            }

            if (queryResult.Query.Truncated && !request.AllowTruncated)
            {
                var failure = BimApiResponse.Fail(
                    BimErrorCode.QueryTruncated,
                    $"Selector resolved a truncated set ({queryResult.Query.Returned} of more than {queryResult.Query.Limit}); " +
                    "set allowTruncated=true to export the capped set.",
                    409);
                failure.Data = new { returned = queryResult.Query.Returned, limit = queryResult.Query.Limit };
                return ElementResolution.Fail(failure);
            }

            var resolvedElements = queryResult.Elements
                .Select(summary => RevitIdentitySerializer.Resolve(document, summary.Identity))
                .Where(r => r.Success)
                .Select(r => r.Element!)
                .ToList();

            return ElementResolution.Ok(resolvedElements, queryResult.Query.Truncated, requestedCount: queryResult.Query.Returned);
        }

        private object BuildElementRecord(Document document, Element element, RevitGeometryConversion conversion, RevitElementLabels labelSet)
        {
            var bb = element.get_BoundingBox(null);
            return new
            {
                identity = RevitIdentitySerializer.ElementIdentity(element),
                category = element.Category?.Name,
                family = (document.GetElement(element.GetTypeId()) as ElementType)?.FamilyName,
                type = (document.GetElement(element.GetTypeId()) as ElementType)?.Name,
                name = element.Name,
                bbox = bb == null ? null : new[] { bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z },
                geometryRepresentation = conversion.Representation,
                geometryQuality = conversion.Quality,
                fallbackReason = conversion.FallbackReason,
                labels = new
                {
                    level = Label(labelSet.Level),
                    hostId = Label(labelSet.HostId),
                    containingRoomId = Label(labelSet.ContainingRoom),
                    containingSpaceId = Label(labelSet.ContainingSpace)
                }
            };
        }

        private object BuildFailedElementRecord(Element element, Exception ex)
        {
            object identity;
            try { identity = RevitIdentitySerializer.ElementIdentity(element); }
            catch { identity = new { source = "revit", uniqueId = TryUniqueId(element) }; }

            return new
            {
                identity,
                category = (string?)null,
                family = (string?)null,
                type = (string?)null,
                name = (string?)null,
                bbox = (double[]?)null,
                geometryRepresentation = RevitGeometryConverter.RepresentationNone,
                geometryQuality = RevitGeometryConverter.QualityFailed,
                fallbackReason = $"{ex.GetType().Name}: {ex.Message}",
                labels = (object?)null
            };
        }

        private static string? TryUniqueId(Element element)
        {
            try { return element.UniqueId; } catch { return null; }
        }

        private static object Label(BimSemanticLabel label)
        {
            return new
            {
                value = label.Value,
                source = label.Source,
                confidence = label.Confidence,
                missingReason = label.MissingReason
            };
        }

        private object BuildSidecar(
            Document document,
            BimExportElementsRequest request,
            ElementResolution resolution,
            List<object> elementRecords,
            List<object> roomRecords)
        {
            return new
            {
                schemaVersion = 1,
                document = RevitIdentitySerializer.DocumentIdentity(document),
                request = new
                {
                    hasSelector = request.HasSelector,
                    hasIdentities = request.HasIdentities,
                    rooms = request.EffectiveRooms.ToString(),
                    allowTruncated = request.AllowTruncated,
                    allowBboxProxy = request.AllowBboxProxy
                },
                resolved = new
                {
                    count = resolution.Elements.Count,
                    truncated = resolution.Truncated,
                    identities = resolution.Elements.Select(RevitIdentitySerializer.ElementIdentity).ToList()
                },
                elements = elementRecords,
                rooms = roomRecords
            };
        }

        private object BuildValidation(
            Document document,
            BimExportCounts counts,
            double scale,
            string targetUnits,
            BimExportArtifactPaths paths,
            string sidecarJson)
        {
            return new
            {
                schemaVersion = 1,
                document = RevitIdentitySerializer.DocumentIdentity(document),
                units = new { source = "feet", target = targetUnits, scaleFactor = scale },
                counts,
                hashes = new
                {
                    model3dm = "sha256:" + Sha256File(paths.Model3dm),
                    sidecar = "sha256:" + Sha256String(sidecarJson)
                }
            };
        }

        private static BimExportVerification VerifyBijection(Rhino.FileIO.File3dm file, HashSet<string> exportedKeys)
        {
            var verification = new BimExportVerification { Ok = true };
            var objectKeys = new HashSet<string>(StringComparer.Ordinal);

            foreach (var obj in file.Objects)
            {
                var key = obj.Attributes.GetUserString("revit.uniqueId");
                if (string.IsNullOrEmpty(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add("A .3dm object has no revit.uniqueId user string.");
                    continue;
                }

                if (!objectKeys.Add(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($"Duplicate .3dm object for key {key}.");
                }

                if (!exportedKeys.Contains(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($".3dm object key {key} has no exported element record.");
                }
            }

            foreach (var key in exportedKeys)
            {
                if (!objectKeys.Contains(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($"Exported element {key} has no .3dm object.");
                }
            }

            return verification;
        }

        private void AddGeometry(Rhino.FileIO.File3dm file, int layerIndex, Element element, RevitGeometryConversion conversion)
        {
            var attrs = new Rhino.DocObjects.ObjectAttributes { LayerIndex = layerIndex };
            attrs.SetUserString("rook.source", "revit");
            attrs.SetUserString("revit.uniqueId", element.UniqueId);
            attrs.SetUserString("revit.elementId", element.Id.Value.ToString());
            attrs.SetUserString("revit.category", element.Category?.Name ?? string.Empty);

            if (conversion.Breps.Count > 0)
            {
                foreach (var brep in conversion.Breps)
                {
                    file.Objects.AddBrep(brep, attrs);
                }
            }
            else if (conversion.Mesh != null)
            {
                file.Objects.AddMesh(conversion.Mesh, attrs);
            }
            else if (conversion.Bbox != null)
            {
                // RhinoCommon 8 File3dmObjectTable exposes no AddBox; add the box proxy as its Brep.
                file.Objects.AddBrep(conversion.Bbox.Value.ToBrep(), attrs);
            }
        }

        private string MaterializeRoom(Rhino.FileIO.File3dm file, int layerIndex, RevitRoomExport room, double scale, bool includeGeometry)
        {
            if (!includeGeometry || room.Solid == null)
            {
                return room.Solid == null ? RevitRoomExporter.RepLabelOnly : room.Representation;
            }

            var mesh = new Rhino.Geometry.Mesh();
            foreach (Face face in room.Solid.Faces)
            {
                Mesh triangulated;
                try { triangulated = face.Triangulate(); }
                catch (Exception) { continue; }
                if (triangulated == null) { continue; }

                var baseIndex = mesh.Vertices.Count;
                for (var v = 0; v < triangulated.Vertices.Count; v++)
                {
                    var p = triangulated.Vertices[v];
                    mesh.Vertices.Add(p.X * scale, p.Y * scale, p.Z * scale);
                }

                for (var t = 0; t < triangulated.NumTriangles; t++)
                {
                    var tri = triangulated.get_Triangle(t);
                    mesh.Faces.AddFace(
                        baseIndex + (int)tri.get_Index(0),
                        baseIndex + (int)tri.get_Index(1),
                        baseIndex + (int)tri.get_Index(2));
                }
            }

            if (mesh.Vertices.Count == 0)
            {
                return RevitRoomExporter.RepLabelOnly;
            }

            mesh.Normals.ComputeNormals();
            mesh.Compact();
            var attrs = new Rhino.DocObjects.ObjectAttributes { LayerIndex = layerIndex };
            attrs.SetUserString("rook.source", "revit");
            attrs.SetUserString("revit.uniqueId", room.UniqueId);
            attrs.SetUserString("rookbim.referenceGeometry", "true");
            file.Objects.AddMesh(mesh, attrs);
            return RevitRoomExporter.RepMesh;
        }

        private static int EnsureLayer(Rhino.FileIO.File3dm file, string name)
        {
            // RhinoCommon 8 File3dmLayerTable.Add returns void, so pin the index explicitly to the
            // next table slot before adding. This keeps ObjectAttributes.LayerIndex correct for the
            // bijection/verification (objects reference this exact index).
            var index = file.AllLayers.Count;
            var layer = new Rhino.DocObjects.Layer { Name = name, Index = index };
            file.AllLayers.Add(layer);
            return index;
        }

        private static Rhino.UnitSystem MapUnits(string units)
        {
            switch ((units ?? "meters").Trim().ToLowerInvariant())
            {
                case "millimeters": case "mm": return Rhino.UnitSystem.Millimeters;
                case "centimeters": case "cm": return Rhino.UnitSystem.Centimeters;
                case "feet": case "ft": return Rhino.UnitSystem.Feet;
                case "inches": case "in": return Rhino.UnitSystem.Inches;
                default: return Rhino.UnitSystem.Meters;
            }
        }

        private BimApiResponse CleanupAndFail(IEnumerable<string> paths, string message)
        {
            CleanupBundle(paths);
            return BimApiResponse.Fail(BimErrorCode.ExportFailed, message, 500);
        }

        private static void CleanupBundle(IEnumerable<string> paths)
        {
            foreach (var path in paths)
            {
                try { if (File.Exists(path)) { File.Delete(path); } }
                catch (Exception) { /* best-effort cleanup */ }
            }
        }

        private static string Sha256File(string path)
        {
            using var sha = SHA256.Create();
            using var stream = File.OpenRead(path);
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", string.Empty).ToLowerInvariant();
        }

        private static string Sha256String(string text)
        {
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-", string.Empty).ToLowerInvariant();
        }

        private sealed class ElementResolution
        {
            public IReadOnlyList<Element> Elements { get; private set; } = Array.Empty<Element>();

            public bool Truncated { get; private set; }

            // True pre-resolution query/identity count, before any silent drop of elements that
            // failed to re-resolve. Defaults to 0 for the failure path.
            public int RequestedCount { get; private set; }

            public BimApiResponse? Failure { get; private set; }

            public static ElementResolution Ok(IReadOnlyList<Element> elements, bool truncated, int requestedCount)
            {
                return new ElementResolution { Elements = elements, Truncated = truncated, RequestedCount = requestedCount };
            }

            public static ElementResolution Fail(BimApiResponse failure)
            {
                return new ElementResolution { Failure = failure };
            }
        }
    }
}
