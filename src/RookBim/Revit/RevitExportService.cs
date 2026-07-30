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
    /// Orchestrates a read-only Revit -&gt; Rhino export: resolve the element set, freeze identities,
    /// convert geometry, assemble an in-memory File3dm + sidecar + validation, write the bundle
    /// path-safely, and verify the Rhino-object &lt;-&gt; sidecar-record bijection. Never mutates the
    /// active Rhino document and never mutates the Revit model (no write scope is ever opened).
    ///
    /// Legacy flat-scheme layer: RookBim::Model  (BimExportLayerNamer.LayerPath(Flat, ...) returns this).
    /// </summary>
    internal sealed class RevitExportService
    {
        // _pendingRelationships is set in ExportResolved immediately before BuildSidecar so the
        // sidecar serialization can reference the accumulated index.
        private RevitRelationshipIndex? _pendingRelationships;

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            DictionaryKeyPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.Never
        };

        private readonly RevitQueryService query = new RevitQueryService();
        private readonly RevitLabelExtractor labels = new RevitLabelExtractor();

        public BimApiResponse Export(
            Document document,
            View? activeView,
            BimExportElementsRequest request,
            RevitDocumentIdentityEvidence evidence,
            BimDiagnosticContext diagnostics)
        {
            var resolution = ResolveElements(
                document,
                activeView,
                request,
                evidence,
                diagnostics);
            if (resolution.Failure != null)
            {
                return resolution.Failure;
            }

            return ExportResolved(
                document,
                evidence,
                resolution.Elements,
                resolution.Truncated,
                resolution.RequestedCount,
                request,
                BimExportOrganizationPolicy.Legacy,
                presetContext: null);
        }

        // Shared assembly core. The raw path passes Legacy + null context (no new decoration);
        // the preset path passes a resolved policy + context (summary + relationships, Task 9).
        // The bundle is exactly three sibling artifacts: <name>.3dm (geometry), <name>.sidecar.json
        // (element/room records + frozen identities), <name>.validation.json (counts + hashes).
        internal BimApiResponse ExportResolved(
            Document document,
            RevitDocumentIdentityEvidence evidence,
            IReadOnlyList<Element> elements,
            bool truncated,
            int requestedCount,
            BimExportElementsRequest request,
            BimExportOrganizationPolicy policy,
            RevitPresetContext? presetContext)
        {
            if (!RevitDocumentIdentityResolver.IsSameDocument(document, evidence.Owner) ||
                elements.Any(element => !RevitDocumentIdentityResolver.IsSameDocument(element.Document, evidence.Owner)))
            {
                return BimApiResponse.Fail(
                    BimErrorCode.ExportFailed,
                    "Export elements do not belong to the captured Revit document.",
                    500);
            }

            // 1. Output-path safety.
            var pathShape = BimExportPathPolicy.ValidateRequestShape(request.Output);
            if (!pathShape.Success)
            {
                return BimApiResponse.Fail(pathShape.ErrorCode, pathShape.Message ?? "Invalid output path.", 400);
            }

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

            var scale = RevitGeometryConverter.ScaleFromFeet(request.Output.Units);
            var converter = new RevitGeometryConverter(scale);

            // 2. Build the in-memory File3dm + element records.
            var file = new Rhino.FileIO.File3dm();
            file.Settings.ModelUnitSystem = MapUnits(request.Output.Units);
            var layerCache = new Dictionary<string, int>(StringComparer.Ordinal);

            var elementRecords = new List<object>();
            var counts = new BimExportCounts
            {
                Requested = requestedCount,
                Resolved = elements.Count,
                Truncated = truncated,
            };
            var exportedKeys = new HashSet<string>(StringComparer.Ordinal);
            var exportedRoomKeys = new HashSet<string>(StringComparer.Ordinal);
            var relationships = new RevitRelationshipIndex();
            var perCategoryExport = new Dictionary<string, RevitCategoryExportTally>(StringComparer.OrdinalIgnoreCase);
            var exportId = 0;

            foreach (var element in elements)
            {
                var key = element.UniqueId;
                try
                {
                    var conversion = converter.Convert(element, request.AllowBboxProxy);
                    var labelSet = labels.Extract(document, element);
                    var stamp = BuildStampData(document, element, conversion, presetContext, exportId);
                    elementRecords.Add(BuildElementRecord(
                        document, evidence, element, conversion, labelSet, stamp));

                    if (presetContext != null)
                    {
                        relationships.Accumulate(element.UniqueId, labelSet);
                    }

                    if (conversion.HasGeometry)
                    {
                        var layerIndex = EnsureLayerForElement(file, layerCache, policy, stamp, labelSet);
                        AddGeometryWithPolicy(file, layerIndex, element, conversion, policy, stamp, labelSet);
                        exportedKeys.Add(key);
                        TallyExport(perCategoryExport, stamp.Category, conversion.Quality, failed: false);
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
                        TallyExport(perCategoryExport, stamp.Category, conversion.Quality, failed: true);
                    }

                    exportId++;
                }
                catch (Exception ex)
                {
                    counts.Failed++;
                    elementRecords.Add(BuildFailedElementRecord(evidence, element, ex));
                    exportId++;
                }
            }

            // 3. Rooms (typed separately).
            var roomRecords = new List<object>();
            var effectiveRooms = presetContext?.EffectiveRooms ?? request.EffectiveRooms;
            var roomRepCounts = new Dictionary<string, int>(StringComparer.Ordinal);
            if (effectiveRooms != BimRoomsMode.Exclude)
            {
                var includeGeometry = effectiveRooms == BimRoomsMode.Both;
                var roomLayerIndex = EnsureLayerPath(file, layerCache, RevitRoomExporter.RoomsLayer);
                var rooms = new RevitRoomExporter(scale).ExportRooms(document);
                counts.Rooms = rooms.Count;
                foreach (var room in rooms)
                {
                    var rep = MaterializeRoom(file, roomLayerIndex, room, scale, includeGeometry, exportedRoomKeys);
                    roomRecords.Add(new
                    {
                        roomId = room.UniqueId,
                        uniqueId = room.UniqueId,
                        number = room.Number,
                        name = room.Name,
                        geometryRepresentation = rep,
                        referenceGeometry = true
                    });
                    roomRepCounts.TryGetValue(rep, out var n);
                    roomRepCounts[rep] = n + 1;
                }
            }

            if (presetContext != null && presetContext.RoomsDriven && counts.Rooms == 0)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoCategoriesResolved,
                    $"Rooms-driven preset '{presetContext.Preset}' resolved no rooms in the selected scope.",
                    422);
            }

            // 4. NoExportableGeometry guard (unchanged: only when elements resolved but none had geometry).
            if (elements.Count > 0 && counts.ExportedBrep + counts.ExportedMesh + counts.ExportedBboxProxy == 0)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoExportableGeometry,
                    "No element produced exportable geometry (retry with allowBboxProxy=true or a different selection).",
                    422);
            }

            // 5. Verify the bijection BEFORE writing.
            var verification = VerifyBijection(file, exportedKeys, exportedRoomKeys);

            // 6. Assemble sidecar + validation; write all three path-safely.
            _pendingRelationships = presetContext == null ? null : relationships;
            var sidecar = BuildSidecar(
                evidence, request, elements, truncated, elementRecords, roomRecords, presetContext);
            var sidecarJson = JsonSerializer.Serialize(sidecar, JsonOptions);
            var written = new List<string>();

            try
            {
                written.Add(paths.Model3dm);
                if (!file.Write(paths.Model3dm, 7))
                {
                    return CleanupAndFail(written, "Failed to write the .3dm bundle artifact.");
                }

                File.WriteAllText(paths.Sidecar, sidecarJson, new UTF8Encoding(false));
                written.Add(paths.Sidecar);

                // Audit computed from the ACTUAL written File3dm objects — proves names + stamps were
                // applied to the .3dm, not merely recorded in the sidecar. Preset-path-only.
                var modelAudit = presetContext == null ? null : BuildModelObjectAudit(file);
                var summary = presetContext == null
                    ? null
                    : BuildSummary(presetContext, counts, perCategoryExport, roomRepCounts, layerCache.Count, paths);
                var validation = BuildValidation(
                    evidence, counts, scale, request.Output.Units, paths, sidecarJson, presetContext, summary, relationships, modelAudit);
                File.WriteAllText(paths.Validation, JsonSerializer.Serialize(validation, JsonOptions), new UTF8Encoding(false));
                written.Add(paths.Validation);

                if (!verification.Ok)
                {
                    CleanupBundle(written);
                    var failure = BimApiResponse.Fail(
                        BimErrorCode.ExportFailed, "Export bijection verification failed; bundle is not a trustworthy fixture.", 500);
                    failure.Data = new { verification };
                    return failure;
                }

                return BimApiResponse.Ok(BuildResult(paths, counts, verification, scale, request.Output.Units, presetContext, summary, relationships, modelAudit));
            }
            catch (Exception ex)
            {
                return CleanupAndFail(written, $"Bundle write failed: {ex.GetType().Name}: {ex.Message}");
            }
        }

        private ElementResolution ResolveElements(
            Document document,
            View? activeView,
            BimExportElementsRequest request,
            RevitDocumentIdentityEvidence evidence,
            BimDiagnosticContext diagnostics)
        {
            if (request.HasIdentities)
            {
                var identities = request.Identities!
                    .Cast<BimElementIdentity?>()
                    .ToList();
                var preflight = RevitDocumentIdentityResolver.PreflightBatch(
                    evidence,
                    identities,
                    diagnostics);
                if (!preflight.Success)
                {
                    return ElementResolution.Fail(BimApiResponse.Fail(
                        preflight.ErrorCode,
                        preflight.Message ?? "One or more element identities failed preflight.",
                        RevitDocumentIdentityResolver.HttpStatusFor(preflight.ErrorCode)));
                }

                var elements = new List<Element>();
                foreach (var identity in identities)
                {
                    var resolved = RevitDocumentIdentityResolver.ResolveAfterPreflight(
                        evidence,
                        identity!);
                    if (!resolved.Success)
                    {
                        return ElementResolution.Fail(BimApiResponse.Fail(
                            resolved.ErrorCode,
                            resolved.Message ?? "An element identity did not resolve.",
                            RevitDocumentIdentityResolver.HttpStatusFor(resolved.ErrorCode)));
                    }

                    elements.Add(resolved.Element!);
                }

                return ElementResolution.Ok(elements, truncated: false, requestedCount: identities.Count);
            }

            var execution = query.Execute(
                document,
                activeView,
                request.Selector!,
                evidence,
                diagnostics);
            var queryResponse = execution.Response;
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

            return ElementResolution.Ok(
                execution.Elements.ToList(),
                queryResult.Query.Truncated,
                requestedCount: queryResult.Query.Returned);
        }

        private object BuildElementRecord(
            Document document,
            RevitDocumentIdentityEvidence evidence,
            Element element,
            RevitGeometryConversion conversion,
            RevitElementLabels labelSet,
            RevitStampData stamp)
        {
            var bb = element.get_BoundingBox(null);
            return new
            {
                identity = RevitDocumentIdentityResolver.ProjectElement(evidence, element),
                category = stamp.Category,
                family = stamp.Family,
                type = stamp.Type,
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

        private object BuildFailedElementRecord(
            RevitDocumentIdentityEvidence evidence,
            Element element,
            Exception ex)
        {
            object identity;
            try { identity = RevitDocumentIdentityResolver.ProjectElement(evidence, element); }
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

        private static int EnsureLayerPath(Rhino.FileIO.File3dm file, Dictionary<string, int> cache, string path)
        {
            if (cache.TryGetValue(path, out var existing))
            {
                return existing;
            }

            var segments = path.Split(new[] { "::" }, StringSplitOptions.RemoveEmptyEntries);
            if (segments.Length == 0)
            {
                segments = new[] { "RookBim", "_Other" };
            }

            int? parentIndex = null;
            var currentPath = string.Empty;
            for (var i = 0; i < segments.Length; i++)
            {
                var segment = segments[i].Trim();
                if (string.IsNullOrEmpty(segment))
                {
                    segment = "_Other";
                }

                currentPath = i == 0 ? segment : currentPath + "::" + segment;
                if (cache.TryGetValue(currentPath, out var cached))
                {
                    parentIndex = cached;
                    continue;
                }

                var childIndex = FindChildLayer(file, parentIndex, segment);
                if (childIndex < 0)
                {
                    childIndex = AddLayer(file, segment, parentIndex);
                }

                cache[currentPath] = childIndex;
                parentIndex = childIndex;
            }

            var finalIndex = parentIndex ?? -1;
            cache[path] = finalIndex;
            return finalIndex;
        }

        private static int AddLayer(Rhino.FileIO.File3dm file, string name, int? parentIndex)
        {
            var index = file.AllLayers.Count;
            var layer = new Rhino.DocObjects.Layer
            {
                Id = Guid.NewGuid(),
                Name = name,
                Index = index,
            };

            if (parentIndex.HasValue)
            {
                layer.ParentLayerId = LayerAt(file, parentIndex.Value).Id;
            }

            file.AllLayers.Add(layer);
            return index;
        }

        private static int FindChildLayer(Rhino.FileIO.File3dm file, int? parentIndex, string name)
        {
            var parentId = parentIndex.HasValue ? LayerAt(file, parentIndex.Value).Id : Guid.Empty;
            for (var i = 0; i < file.AllLayers.Count; i++)
            {
                var layer = LayerAt(file, i);
                if (string.Equals(layer.Name, name, StringComparison.OrdinalIgnoreCase) &&
                    layer.ParentLayerId == parentId)
                {
                    return i;
                }
            }

            return -1;
        }

        private static int EnsureLayerForElement(
            Rhino.FileIO.File3dm file,
            Dictionary<string, int> cache,
            BimExportOrganizationPolicy policy,
            RevitStampData stamp,
            RevitElementLabels labelSet)
        {
            var levelValue = labelSet.Level?.Value;
            var layerName = BimExportLayerNamer.LayerPath(policy.LayerScheme, stamp.Category, levelValue);
            return EnsureLayerPath(file, cache, layerName);
        }

        private void AddGeometryWithPolicy(
            Rhino.FileIO.File3dm file,
            int layerIndex,
            Element element,
            RevitGeometryConversion conversion,
            BimExportOrganizationPolicy policy,
            RevitStampData stamp,
            RevitElementLabels labelSet)
        {
            var attrs = new Rhino.DocObjects.ObjectAttributes { LayerIndex = layerIndex };
            StampObject(attrs, element, conversion, policy, stamp, labelSet);

            var name = BimExportObjectNamer.ObjectName(
                policy.NameScheme, stamp.Category, stamp.Type, stamp.ElementIdValue, stamp.RevitName);
            if (!string.IsNullOrEmpty(name))
            {
                attrs.Name = name;
            }

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
                file.Objects.AddBrep(conversion.Bbox.Value.ToBrep(), attrs);
            }
        }

        // Value-only user strings. minimal = the legacy four; standard/full add Rook-derived +
        // raw Revit facts. Missing/low-confidence labels are omitted, never stamped as "unknown".
        private static void StampObject(
            Rhino.DocObjects.ObjectAttributes attrs,
            Element element,
            RevitGeometryConversion conversion,
            BimExportOrganizationPolicy policy,
            RevitStampData stamp,
            RevitElementLabels labelSet)
        {
            attrs.SetUserString("rook.source", "revit");
            attrs.SetUserString("revit.uniqueId", element.UniqueId);
            attrs.SetUserString("revit.elementId", element.Id.Value.ToString());
            attrs.SetUserString("revit.category", stamp.Category ?? string.Empty);

            if (policy.MetadataProfile == BimMetadataProfile.Minimal)
            {
                return;
            }

            attrs.SetUserString("rookbim.exportId", stamp.ExportId.ToString());
            if (!string.IsNullOrEmpty(stamp.Preset)) { attrs.SetUserString("rookbim.preset", stamp.Preset); }
            attrs.SetUserString("rookbim.geometryRepresentation", conversion.Representation);
            attrs.SetUserString("rookbim.geometryQuality", conversion.Quality);
            StampIfPresent(attrs, "revit.family", stamp.Family);
            StampIfPresent(attrs, "revit.type", stamp.Type);
            StampIfPresent(attrs, "revit.name", stamp.RevitName);
            StampLabel(attrs, "revit.level", labelSet.Level);

            if (policy.MetadataProfile != BimMetadataProfile.Full)
            {
                return;
            }

            StampLabel(attrs, "revit.hostId", labelSet.HostId);
            StampLabel(attrs, "revit.containingRoomId", labelSet.ContainingRoom);
            StampLabel(attrs, "revit.containingSpaceId", labelSet.ContainingSpace);
        }

        private static void StampIfPresent(Rhino.DocObjects.ObjectAttributes attrs, string key, string? value)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                attrs.SetUserString(key, value);
            }
        }

        private static void StampLabel(Rhino.DocObjects.ObjectAttributes attrs, string key, BimSemanticLabel? label)
        {
            if (label != null && !string.IsNullOrWhiteSpace(label.Value))
            {
                attrs.SetUserString(key, label.Value);
            }
        }

        private static RevitStampData BuildStampData(
            Document document,
            Element element,
            RevitGeometryConversion conversion,
            RevitPresetContext? presetContext,
            int exportId)
        {
            var type = document.GetElement(element.GetTypeId()) as ElementType;
            return new RevitStampData
            {
                Category = element.Category?.Name,
                Family = type?.FamilyName,
                Type = type?.Name,
                RevitName = NullIfWhiteSpace(element.Name),
                ElementIdValue = element.Id.Value,
                ExportId = exportId,
                Preset = presetContext?.Preset ?? string.Empty,
            };
        }

        private static void TallyExport(
            Dictionary<string, RevitCategoryExportTally> tallies, string? category, string quality, bool failed)
        {
            var key = string.IsNullOrWhiteSpace(category) ? "_Other" : category!;
            if (!tallies.TryGetValue(key, out var tally))
            {
                tally = new RevitCategoryExportTally();
                tallies[key] = tally;
            }

            if (failed) { tally.Failed++; } else { tally.Exported++; }
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private sealed class RevitStampData
        {
            public string? Category { get; set; }
            public string? Family { get; set; }
            public string? Type { get; set; }
            public string? RevitName { get; set; }
            public long ElementIdValue { get; set; }
            public int ExportId { get; set; }
            public string Preset { get; set; } = string.Empty;
        }

        private sealed class RevitCategoryExportTally
        {
            public int Exported { get; set; }
            public int Failed { get; set; }
        }

        private object BuildSidecar(
            RevitDocumentIdentityEvidence evidence,
            BimExportElementsRequest request,
            IReadOnlyList<Element> elements,
            bool truncated,
            List<object> elementRecords,
            List<object> roomRecords,
            RevitPresetContext? presetContext)
        {
            var requestSection = presetContext == null
                ? (object)new
                {
                    hasSelector = request.HasSelector,
                    hasIdentities = request.HasIdentities,
                    rooms = request.EffectiveRooms.ToString(),
                    allowTruncated = request.AllowTruncated,
                    allowBboxProxy = request.AllowBboxProxy
                }
                : new
                {
                    preset = presetContext.Preset,
                    effectiveCategories = presetContext.EffectiveCategories,
                    rooms = BimExportOrganizationPolicy.RoomsToWire(presetContext.EffectiveRooms),
                    layerPolicy = BimExportOrganizationPolicy.LayerToWire(presetContext.Policy.LayerScheme),
                    namePolicy = BimExportOrganizationPolicy.NameToWire(presetContext.Policy.NameScheme),
                    metadataProfile = BimExportOrganizationPolicy.ProfileToWire(presetContext.Policy.MetadataProfile),
                    limitPerCategory = presetContext.LimitPerCategory,
                    allowTruncated = request.AllowTruncated,
                    allowBboxProxy = request.AllowBboxProxy
                };

            var sidecar = new Dictionary<string, object?>
            {
                ["schemaVersion"] = 1,
                ["document"] = RevitDocumentIdentityResolver.ProjectDocument(evidence),
                ["request"] = requestSection,
                ["resolved"] = new
                {
                    count = elements.Count,
                    truncated = truncated,
                    identities = elements
                        .Select(element => RevitDocumentIdentityResolver.ProjectElement(evidence, element))
                        .ToList()
                },
                ["elements"] = elementRecords,
                ["rooms"] = roomRecords,
            };

            // Preset-only: relationships index lives in the sidecar too (Task 9 fills it).
            if (presetContext != null)
            {
                sidecar["relationships"] = _pendingRelationships?.ToWire() ?? RevitRelationshipIndex.EmptyWire();
            }

            return sidecar;
        }

        private object BuildValidation(
            RevitDocumentIdentityEvidence evidence,
            BimExportCounts counts,
            double scale,
            string targetUnits,
            BimExportArtifactPaths paths,
            string sidecarJson,
            RevitPresetContext? presetContext,
            object? summary,
            RevitRelationshipIndex relationships,
            object? modelAudit)
        {
            var validation = new Dictionary<string, object?>
            {
                ["schemaVersion"] = 1,
                ["document"] = RevitDocumentIdentityResolver.ProjectDocument(evidence),
                ["units"] = new { source = "feet", target = targetUnits, scaleFactor = scale },
                ["counts"] = counts,
                ["hashes"] = new
                {
                    model3dm = "sha256:" + Sha256File(paths.Model3dm),
                    sidecar = "sha256:" + Sha256String(sidecarJson)
                },
            };

            if (presetContext != null)
            {
                validation["summary"] = summary;
                validation["relationships"] = relationships.ToWire();
                validation["objects"] = modelAudit;
            }

            return validation;
        }

        private object BuildResult(
            BimExportArtifactPaths paths,
            BimExportCounts counts,
            BimExportVerification verification,
            double scale,
            string targetUnits,
            RevitPresetContext? presetContext,
            object? summary,
            RevitRelationshipIndex relationships,
            object? modelAudit)
        {
            var result = BimApiResponse.Ok(new BimExportResult
            {
                Paths = paths,
                Counts = counts,
                Verification = verification,
                SourceUnits = "feet",
                TargetUnits = targetUnits,
                UnitScaleFactor = scale
            });

            // For the preset path, attach summary + relationships to the response Data alongside the
            // typed result. The raw path returns the bare BimExportResult (unchanged shape).
            if (presetContext == null)
            {
                return result.Data!;
            }

            return new
            {
                schemaVersion = 1,
                paths,
                counts,
                verification,
                sourceUnits = "feet",
                targetUnits,
                unitScaleFactor = scale,
                summary,
                relationships = relationships.ToWire(),
                objects = modelAudit
            };
        }

        private static object BuildSummary(
            RevitPresetContext presetContext,
            BimExportCounts counts,
            Dictionary<string, RevitCategoryExportTally> perCategoryExport,
            Dictionary<string, int> roomRepCounts,
            int layerCount,
            BimExportArtifactPaths paths)
        {
            var resolvedCategories = presetContext.ResolvedCategories.Select(rc =>
            {
                perCategoryExport.TryGetValue(rc.Category, out var tally);
                return new
                {
                    category = rc.Category,
                    resolved = rc.Resolved,
                    exported = tally?.Exported ?? 0,
                    failed = tally?.Failed ?? 0,
                    status = rc.Status,
                };
            }).ToList();

            var warnings = presetContext.Warnings.Select(w => new { code = w.Code, message = w.Message }).ToList();
            var layerWarnings = new List<object>();
            const int LayerCountThreshold = 64;
            if (layerCount > LayerCountThreshold)
            {
                layerWarnings.Add(new
                {
                    code = "layer_count_high",
                    message = $"Export produced {layerCount} layers (threshold {LayerCountThreshold}).",
                });
            }

            var exportedTotal = counts.ExportedBrep + counts.ExportedMesh + counts.ExportedBboxProxy;
            var digest =
                $"Exported {exportedTotal} elements across {presetContext.EffectiveCategories.Count} categories: " +
                $"{counts.ExportedBrep} Breps, {counts.ExportedMesh} meshes, {counts.ExportedBboxProxy} bbox proxies, " +
                $"{counts.Failed} failed. {counts.Rooms} rooms included. {warnings.Count} warning(s).";

            return new
            {
                digest,
                preset = presetContext.Preset,
                effectiveCategories = presetContext.EffectiveCategories,
                layerPolicy = BimExportOrganizationPolicy.LayerToWire(presetContext.Policy.LayerScheme),
                namePolicy = BimExportOrganizationPolicy.NameToWire(presetContext.Policy.NameScheme),
                metadataProfile = BimExportOrganizationPolicy.ProfileToWire(presetContext.Policy.MetadataProfile),
                limitPerCategory = presetContext.LimitPerCategory,
                resolvedCategories,
                geometryQuality = new
                {
                    brep = counts.ExportedBrep,
                    mesh = counts.ExportedMesh,
                    bbox_proxy = counts.ExportedBboxProxy,
                    failed = counts.Failed,
                },
                rooms = new
                {
                    total = counts.Rooms,
                    byRepresentation = roomRepCounts,
                },
                layers = new { count = layerCount, warnings = layerWarnings },
                warnings,
            };
        }

        // Reads the ACTUAL written File3dm objects to prove names + user-string stamps reached the
        // .3dm (not just the sidecar records). Preset-path-only.
        private static object BuildModelObjectAudit(Rhino.FileIO.File3dm file)
        {
            var total = 0;
            var named = 0;
            var withUniqueId = 0;
            var withLevelStamp = 0;
            var withFamilyStamp = 0;
            var sampleNames = new List<string>();
            var sampleStampKeys = new List<string>();
            var layerNames = new List<string>();
            var layerPaths = new List<string>();
            var layerRecords = new List<object>();
            var objectLayerPaths = new List<string>();
            for (var i = 0; i < file.AllLayers.Count; i++)
            {
                var layer = LayerAt(file, i);
                layerNames.Add(layer.Name);
                var path = BuildLayerPath(file, i);
                layerPaths.Add(path);
                layerRecords.Add(new
                {
                    name = layer.Name,
                    path,
                    id = layer.Id.ToString(),
                    parentLayerId = layer.ParentLayerId.ToString(),
                    hasParent = layer.ParentLayerId != Guid.Empty,
                });
            }

            foreach (var obj in file.Objects)
            {
                total++;
                var attrs = obj.Attributes;
                if (!string.IsNullOrEmpty(attrs.Name))
                {
                    named++;
                    if (sampleNames.Count < 3) { sampleNames.Add(attrs.Name); }
                }

                if (!string.IsNullOrEmpty(attrs.GetUserString("revit.uniqueId"))) { withUniqueId++; }
                if (!string.IsNullOrEmpty(attrs.GetUserString("revit.level"))) { withLevelStamp++; }
                if (!string.IsNullOrEmpty(attrs.GetUserString("revit.family"))) { withFamilyStamp++; }

                if (sampleStampKeys.Count == 0)
                {
                    var strings = attrs.GetUserStrings();
                    foreach (var key in strings.AllKeys)
                    {
                        if (!string.IsNullOrEmpty(key)) { sampleStampKeys.Add(key); }
                    }
                }

                if (attrs.LayerIndex >= 0 && attrs.LayerIndex < file.AllLayers.Count)
                {
                    var objectLayerPath = BuildLayerPath(file, attrs.LayerIndex);
                    if (!objectLayerPaths.Contains(objectLayerPath))
                    {
                        objectLayerPaths.Add(objectLayerPath);
                    }
                }
            }

            return new
            {
                objectCount = total,
                namedObjectCount = named,
                withUniqueIdCount = withUniqueId,
                withLevelStampCount = withLevelStamp,
                withFamilyStampCount = withFamilyStamp,
                sampleNames,
                sampleStampKeys,
                layerNames,
                layerPaths,
                layerRecords,
                objectLayerPaths,
            };
        }

        private static string BuildLayerPath(Rhino.FileIO.File3dm file, int layerIndex)
        {
            if (layerIndex < 0 || layerIndex >= file.AllLayers.Count)
            {
                return string.Empty;
            }

            var segments = new Stack<string>();
            var visited = new HashSet<Guid>();
            var current = LayerAt(file, layerIndex);
            while (current != null)
            {
                segments.Push(current.Name);
                if (current.ParentLayerId == Guid.Empty || !visited.Add(current.Id))
                {
                    break;
                }

                var parentIndex = FindLayerById(file, current.ParentLayerId);
                if (parentIndex < 0)
                {
                    break;
                }

                current = LayerAt(file, parentIndex);
            }

            return string.Join("::", segments);
        }

        private static int FindLayerById(Rhino.FileIO.File3dm file, Guid id)
        {
            for (var i = 0; i < file.AllLayers.Count; i++)
            {
                if (LayerAt(file, i).Id == id)
                {
                    return i;
                }
            }

            return -1;
        }

        private static Rhino.DocObjects.Layer LayerAt(Rhino.FileIO.File3dm file, int index)
        {
            var i = 0;
            foreach (var layer in file.AllLayers)
            {
                if (i == index)
                {
                    return layer;
                }

                i++;
            }

            throw new ArgumentOutOfRangeException(nameof(index), index, "Layer index is outside the File3dm layer table.");
        }

        private static BimExportVerification VerifyBijection(
            Rhino.FileIO.File3dm file, HashSet<string> exportedKeys, HashSet<string> exportedRoomKeys)
        {
            // Every .3dm object carries a revit.uniqueId user string; collect them all (including
            // nulls, which the pure helper flags). The expected set is the union of geometry-bearing
            // element keys and rooms that actually emitted a geometry object. Multiple objects per
            // key are VALID (a multi-solid element emits one object per Brep).
            var objectKeys = new List<string?>();
            foreach (var obj in file.Objects)
            {
                objectKeys.Add(obj.Attributes.GetUserString("revit.uniqueId"));
            }

            var expected = new HashSet<string>(exportedKeys, StringComparer.Ordinal);
            expected.UnionWith(exportedRoomKeys);

            return BimExportBijection.Verify(objectKeys, expected);
        }

        private string MaterializeRoom(
            Rhino.FileIO.File3dm file, int layerIndex, RevitRoomExport room, double scale, bool includeGeometry,
            HashSet<string> exportedRoomKeys)
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
            exportedRoomKeys.Add(room.UniqueId);
            return RevitRoomExporter.RepMesh;
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
