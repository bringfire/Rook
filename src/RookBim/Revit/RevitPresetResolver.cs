using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// Resolves a curated preset into a frozen, deduplicated element set + organization policy by
    /// looping the preset's categories through the existing single-category query path. Read-only.
    /// </summary>
    internal sealed class RevitPresetResolver
    {
        private readonly RevitQueryService query = new RevitQueryService();

        public RevitPresetResolution Resolve(
            Document document,
            View? activeView,
            BimExportPresetRequest request,
            RevitDocumentIdentityEvidence evidence,
            BimDiagnosticContext diagnostics)
        {
            if (!BimPresetCatalog.TryGet(request.Preset, out var definition))
            {
                return RevitPresetResolution.Fail(BimApiResponse.Fail(
                    BimErrorCode.UnknownPreset, $"Unknown export preset '{request.Preset}'.", 400));
            }

            var policyResult = BimExportOrganizationPolicy.Resolve(
                definition, request.LayerPolicy, request.NamePolicy, request.MetadataProfile, out var policy);
            if (!policyResult.Success)
            {
                return RevitPresetResolution.Fail(BimApiResponse.Fail(
                    policyResult.ErrorCode, policyResult.Message ?? "Invalid organization policy override.", 400));
            }

            var effectiveRooms = ResolveRooms(definition, request.Rooms, out var roomsError);
            if (roomsError != null)
            {
                return RevitPresetResolution.Fail(roomsError);
            }

            if (definition.RoomsDriven && effectiveRooms == BimRoomsMode.Exclude)
            {
                return RevitPresetResolution.Fail(BimApiResponse.Fail(
                    BimErrorCode.NoCategoriesResolved,
                    $"Rooms-driven preset '{definition.Name}' cannot export with rooms='exclude'.",
                    422));
            }

            var limitPerCategory = request.LimitPerCategory ?? definition.DefaultLimitPerCategory;
            var categories = EffectiveCategories(definition, request);

            var context = new RevitPresetContext
            {
                Preset = definition.Name,
                Policy = policy,
                EffectiveRooms = effectiveRooms,
                RoomsDriven = definition.RoomsDriven,
                LimitPerCategory = limitPerCategory,
                EffectiveCategories = categories.ToList(),
            };

            // First category to surface a same-operation live element wins ordering.
            var seen = new HashSet<long>();
            var ordered = new List<Element>();
            var totalResolved = 0;

            foreach (var category in categories)
            {
                var selector = new BimQueryElementsRequest
                {
                    Scope = request.EffectiveScope,
                    Category = category,
                    Limit = limitPerCategory,
                };

                var execution = query.Execute(document, activeView, selector, evidence, diagnostics);
                var response = execution.Response;
                if (!response.Success || !(response.Data is BimQueryElementsResult result))
                {
                    // Unknown/unqueryable category in THIS model degrades to a warning, not a failure.
                    context.Warnings.Add(new RevitPresetWarning
                    {
                        Code = "category_unavailable",
                        Message = $"Category '{category}' is not available in this model: {response.Message}",
                    });
                    context.ResolvedCategories.Add(new RevitPresetCategoryCount
                    {
                        Category = category, Resolved = 0, Status = "unavailable",
                    });
                    continue;
                }

                if (result.Query.Truncated && !request.AllowTruncated)
                {
                    var failure = BimApiResponse.Fail(
                        BimErrorCode.QueryTruncated,
                        $"Category '{category}' resolved a truncated set ({result.Query.Returned} of more than " +
                        $"{result.Query.Limit}); set allowTruncated=true to export the capped set.",
                        409);
                    failure.Data = new { category, returned = result.Query.Returned, limit = result.Query.Limit };
                    return RevitPresetResolution.Fail(failure);
                }

                foreach (var element in execution.Elements)
                {
                    if (!RevitDocumentIdentityResolver.IsSameDocument(element.Document, evidence.Owner))
                    {
                        return RevitPresetResolution.Fail(BimApiResponse.Fail(
                            BimErrorCode.ExportFailed,
                            "Preset query returned an element outside the captured document.",
                            500));
                    }

                    var elementId = element.Id.Value;
                    if (seen.Add(elementId))
                    {
                        ordered.Add(element);
                    }
                }

                totalResolved += result.Query.Returned;
                context.ResolvedCategories.Add(new RevitPresetCategoryCount
                {
                    Category = category, Resolved = result.Query.Returned, Status = "resolved",
                });
            }

            // Success condition: non-rooms-driven presets require at least one resolved element.
            if (!definition.RoomsDriven && ordered.Count == 0)
            {
                var failure = BimApiResponse.Fail(
                    BimErrorCode.NoCategoriesResolved,
                    $"Preset '{definition.Name}' resolved no elements (none of its categories were present " +
                    "in the selected scope).",
                    422);
                failure.Data = new { warnings = context.Warnings.Select(w => new { w.Code, w.Message }).ToList() };
                return RevitPresetResolution.Fail(failure);
            }

            return new RevitPresetResolution
            {
                Elements = ordered,
                Truncated = false,
                RequestedCount = totalResolved,
                Context = context,
            };
        }

        private static IReadOnlyList<string> EffectiveCategories(
            BimPresetDefinition definition, BimExportPresetRequest request)
        {
            var categories = new List<string>(definition.Categories);
            if (request.IncludeCategories != null)
            {
                foreach (var add in request.IncludeCategories)
                {
                    if (!string.IsNullOrWhiteSpace(add) &&
                        !categories.Any(c => string.Equals(c, add, StringComparison.OrdinalIgnoreCase)))
                    {
                        categories.Add(add.Trim());
                    }
                }
            }

            if (request.ExcludeCategories != null && request.ExcludeCategories.Count > 0)
            {
                var excluded = new HashSet<string>(
                    request.ExcludeCategories.Where(c => !string.IsNullOrWhiteSpace(c)).Select(c => c.Trim()),
                    StringComparer.OrdinalIgnoreCase);
                categories = categories.Where(c => !excluded.Contains(c)).ToList();
            }

            return categories;
        }

        private static BimRoomsMode ResolveRooms(
            BimPresetDefinition definition, string? roomsOverride, out BimApiResponse? error)
        {
            error = null;
            if (string.IsNullOrWhiteSpace(roomsOverride))
            {
                return definition.DefaultRooms;
            }

            switch (roomsOverride!.Trim().ToLowerInvariant())
            {
                case "both": return BimRoomsMode.Both;
                case "labels_only": return BimRoomsMode.LabelsOnly;
                case "exclude": return BimRoomsMode.Exclude;
                default:
                    error = BimApiResponse.Fail(
                        BimErrorCode.InvalidScope, $"Invalid rooms override '{roomsOverride}'.", 400);
                    return definition.DefaultRooms;
            }
        }
    }

    internal sealed class RevitPresetResolution
    {
        public BimApiResponse? Failure { get; set; }

        public IReadOnlyList<Element> Elements { get; set; } = Array.Empty<Element>();

        public bool Truncated { get; set; }

        public int RequestedCount { get; set; }

        public RevitPresetContext Context { get; set; } = new RevitPresetContext();

        public static RevitPresetResolution Fail(BimApiResponse failure)
        {
            return new RevitPresetResolution { Failure = failure };
        }
    }
}
