using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitQueryService
    {
        private readonly RevitCategoryResolver categories = new RevitCategoryResolver();

        public RevitQueryExecutionResult Execute(
            Document document,
            View? activeView,
            BimQueryElementsRequest request,
            RevitDocumentIdentityEvidence evidence,
            BimDiagnosticContext diagnostics)
        {
            if (document == null)
            {
                return Failure(BimApiResponse.Fail(
                    BimErrorCode.NoActiveDocument,
                    "No active Revit document is open.",
                    409));
            }

            if (evidence == null || !RevitDocumentIdentityResolver.IsSameDocument(document, evidence.Owner))
            {
                return Failure(BimApiResponse.Fail(
                    BimErrorCode.DocumentIdentityInvalid,
                    "Query document does not match the captured identity evidence.",
                    400));
            }

            request ??= new BimQueryElementsRequest();
            var validation = request.Validate();
            if (!validation.Success)
            {
                return Failure(BimApiResponse.Fail(
                    validation.ErrorCode,
                    validation.Message ?? "BIM query validation failed.",
                    400));
            }

            if (request.EffectiveScope == BimQueryScope.ActiveView && activeView == null)
            {
                return Failure(BimApiResponse.Fail(
                    BimErrorCode.NoActiveView,
                    "active_view scope requires an active Revit view.",
                    409));
            }

            var filters = request.EffectiveFilters;
            BimCategoryResolution? categoryResolution = null;
            FilteredElementCollector collector;
            try
            {
                collector = request.EffectiveScope == BimQueryScope.ActiveView
                    ? new FilteredElementCollector(document, activeView!.Id)
                    : new FilteredElementCollector(document);
            }
            catch (Autodesk.Revit.Exceptions.ArgumentException)
            {
                return Failure(InvalidActiveViewForCollection());
            }
            catch (ArgumentException)
            {
                return Failure(InvalidActiveViewForCollection());
            }

            collector.WhereElementIsNotElementType();

            if (!string.IsNullOrWhiteSpace(request.Category))
            {
                var categoryName = request.Category!;
                var resolution = categories.Resolve(document, categoryName, evidence, diagnostics);
                categoryResolution = resolution;
                if (resolution.Status == BimCategoryResolutionStatus.Ambiguous)
                {
                    var response = BimApiResponse.Fail(
                        BimErrorCode.AmbiguousCategory,
                        $"Revit category '{categoryName}' is ambiguous.",
                        400);
                    response.Data = new { resolution = resolution };
                    return Failure(response);
                }

                if (resolution.Status != BimCategoryResolutionStatus.Resolved || resolution.Category == null)
                {
                    var response = BimApiResponse.Fail(
                        BimErrorCode.InvalidCategory,
                        $"Unknown Revit category '{categoryName}'.",
                        400);
                    response.Data = new { resolution = resolution };
                    return Failure(response);
                }

                if (!TryResolvedCategoryFilter(resolution, out var categoryFilter))
                {
                    resolution.Queryable = false;
                    var response = BimApiResponse.Fail(
                        BimErrorCode.CategoryNotQueryable,
                        $"Revit category '{categoryName}' cannot be safely used for element collection.",
                        400);
                    response.Data = new { resolution = resolution };
                    return Failure(response);
                }

                try
                {
                    collector.WherePasses(categoryFilter);
                }
                catch (Autodesk.Revit.Exceptions.ArgumentException)
                {
                    resolution.Queryable = false;
                    var response = BimApiResponse.Fail(
                        BimErrorCode.CategoryNotQueryable,
                        $"Revit category '{categoryName}' cannot be safely used for element collection.",
                        400);
                    response.Data = new { resolution = resolution };
                    return Failure(response);
                }
                catch (ArgumentException)
                {
                    resolution.Queryable = false;
                    var response = BimApiResponse.Fail(
                        BimErrorCode.CategoryNotQueryable,
                        $"Revit category '{categoryName}' cannot be safely used for element collection.",
                        400);
                    response.Data = new { resolution = resolution };
                    return Failure(response);
                }
            }

            if (filters.Count == 0)
            {
                var capped = CollectUnfilteredResults(collector, request.EffectiveLimit);
                return Success(
                    document,
                    activeView,
                    request,
                    evidence,
                    capped.Elements,
                    capped.Truncated,
                    new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase),
                    categoryResolution);
            }

            var candidates = collector.ToElements();
            var parameterAmbiguity = PreflightFilterParameterAmbiguity(document, candidates, filters);
            if (parameterAmbiguity != null)
            {
                return Failure(parameterAmbiguity);
            }

            var missingCounts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            var matched = new List<Element>();
            var matchedBeyondLimit = false;

            foreach (var element in candidates)
            {
                if (!MatchesAllFilters(element, document, filters, missingCounts))
                {
                    continue;
                }

                if (matched.Count < request.EffectiveLimit)
                {
                    matched.Add(element);
                }
                else
                {
                    matchedBeyondLimit = true;
                    break;
                }
            }

            return Success(
                document,
                activeView,
                request,
                evidence,
                matched,
                matchedBeyondLimit,
                missingCounts,
                categoryResolution);
        }

        private static RevitQueryExecutionResult Success(
            Document document,
            View? activeView,
            BimQueryElementsRequest request,
            RevitDocumentIdentityEvidence evidence,
            IEnumerable<Element> elements,
            bool truncated,
            Dictionary<string, int> missingCounts,
            BimCategoryResolution? categoryResolution)
        {
            var ordered = elements.ToList();
            if (ordered.Any(element => !RevitDocumentIdentityResolver.IsSameDocument(element.Document, evidence.Owner)))
            {
                throw new InvalidOperationException(
                    "Query returned an element outside the captured document.");
            }

            var result = new BimQueryElementsResult
            {
                Document = RevitDocumentIdentityResolver.ProjectDocument(evidence),
                Scope = request.EffectiveScope,
                View = request.EffectiveScope == BimQueryScope.ActiveView
                    ? RevitViewIdentitySerializer.ViewIdentity(activeView!)
                    : null,
                Query = new BimQuerySummary
                {
                    Category = request.Category,
                    Limit = request.EffectiveLimit,
                    Returned = ordered.Count,
                    Truncated = truncated,
                    CategoryResolution = categoryResolution,
                    Filters = request.EffectiveFilters.Select(filter => new BimQueryFilterSummary
                    {
                        Parameter = NullIfWhiteSpace(filter.Parameter),
                        Operation = filter.Operation,
                        Value = NullIfWhiteSpace(filter.Value)
                    }).ToList(),
                    MissingParameterCounts = missingCounts
                },
                Elements = ordered.Select(element => new BimElementSummary
                {
                    Identity = RevitDocumentIdentityResolver.ProjectElement(evidence, element),
                    Name = NullIfWhiteSpace(element.Name),
                    Category = new BimCategorySummary
                    {
                        Id = ToInt32OrNull(element.Category?.Id),
                        Name = NullIfWhiteSpace(element.Category?.Name)
                    },
                    Type = BuildTypeSummary(document, element)
                }).ToList()
            };

            return new RevitQueryExecutionResult(BimApiResponse.Ok(result), ordered);
        }

        private static RevitQueryExecutionResult Failure(BimApiResponse response)
        {
            return new RevitQueryExecutionResult(response);
        }

        private static bool MatchesAllFilters(
            Element element,
            Document document,
            IReadOnlyList<BimQueryFilter> filters,
            Dictionary<string, int> missingCounts)
        {
            foreach (var filter in filters)
            {
                var parameter = FindParameter(document, element, filter.Parameter);
                if (parameter == null)
                {
                    IncrementMissingCount(missingCounts, filter.Parameter);
                    if (!BimFilterSemantics.MissingParameterMatches(filter.Operation))
                    {
                        return false;
                    }

                    continue;
                }

                var display = NormalizedDisplayValue(parameter);
                var expected = Normalize(filter.Value);
                var isEmpty = string.IsNullOrWhiteSpace(display);
                bool matches;

                switch (filter.Operation)
                {
                    case BimFilterOperation.IsEmpty:
                        matches = isEmpty;
                        break;
                    case BimFilterOperation.IsNotEmpty:
                        matches = !isEmpty;
                        break;
                    case BimFilterOperation.Equals:
                        matches = string.Equals(display, expected, StringComparison.OrdinalIgnoreCase);
                        break;
                    case BimFilterOperation.NotEquals:
                        matches = !string.Equals(display, expected, StringComparison.OrdinalIgnoreCase);
                        break;
                    case BimFilterOperation.Contains:
                        matches = display.IndexOf(expected, StringComparison.OrdinalIgnoreCase) >= 0;
                        break;
                    default:
                        matches = false;
                        break;
                }

                if (!matches)
                {
                    return false;
                }
            }

            return true;
        }

        private static BimApiResponse? PreflightFilterParameterAmbiguity(
            Document document,
            ICollection<Element> candidates,
            IReadOnlyList<BimQueryFilter> filters)
        {
            foreach (var filter in filters)
            {
                var identities = new Dictionary<ParameterIdentityKey, object>();
                foreach (var element in candidates)
                {
                    foreach (var parameter in GetElementAndTypeParameters(document, element))
                    {
                        if (!string.Equals(parameter.Definition?.Name, filter.Parameter, StringComparison.OrdinalIgnoreCase))
                        {
                            continue;
                        }

                        var identity = BuildParameterIdentity(parameter);
                        if (!identities.ContainsKey(identity.Key))
                        {
                            identities.Add(identity.Key, identity.Candidate);
                        }
                    }
                }

                if (identities.Count > 1)
                {
                    var response = BimApiResponse.Fail(
                        BimErrorCode.AmbiguousParameter,
                        $"Parameter '{filter.Parameter}' is ambiguous in the target candidate set.",
                        400);
                    response.Data = new
                    {
                        error = "ambiguous_parameter",
                        parameter = filter.Parameter,
                        candidates = identities.Values.ToList()
                    };
                    return response;
                }
            }

            return null;
        }

        private static CappedElementCollection CollectUnfilteredResults(
            FilteredElementCollector collector,
            int limit)
        {
            var elements = new List<Element>();
            var maxRead = limit + 1;
            foreach (Element element in collector)
            {
                elements.Add(element);
                if (elements.Count >= maxRead)
                {
                    break;
                }
            }

            var truncated = elements.Count > limit;
            if (truncated)
            {
                elements.RemoveAt(elements.Count - 1);
            }

            return new CappedElementCollection(elements, truncated);
        }

        private static Parameter? FindParameter(Document document, Element element, string? name)
        {
            foreach (var parameter in GetElementAndTypeParameters(document, element))
            {
                if (string.Equals(parameter.Definition?.Name, name, StringComparison.OrdinalIgnoreCase))
                {
                    return parameter;
                }
            }

            return null;
        }

        private static IEnumerable<Parameter> GetElementAndTypeParameters(Document document, Element element)
        {
            foreach (Parameter parameter in element.Parameters)
            {
                yield return parameter;
            }

            var typeId = element.GetTypeId();
            if (typeId == ElementId.InvalidElementId)
            {
                yield break;
            }

            var type = document.GetElement(typeId);
            if (type == null)
            {
                yield break;
            }

            foreach (Parameter parameter in type.Parameters)
            {
                yield return parameter;
            }
        }

        private static BimApiResponse InvalidActiveViewForCollection()
        {
            return BimApiResponse.Fail(
                BimErrorCode.NoActiveView,
                "active_view scope requires a Revit view that supports element collection.",
                409);
        }

        private static BimElementTypeSummary BuildTypeSummary(Document document, Element element)
        {
            var typeId = element.GetTypeId();
            var type = typeId == ElementId.InvalidElementId ? null : document.GetElement(typeId);
            if (type == null)
            {
                return new BimElementTypeSummary();
            }

            return new BimElementTypeSummary
            {
                Id = ToInt32OrNull(type.Id),
                UniqueId = NullIfWhiteSpace(type.UniqueId),
                FamilyName = NullIfWhiteSpace(
                    type.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)?.AsString()),
                Name = NullIfWhiteSpace(type.Name)
            };
        }

        private static ParameterIdentity BuildParameterIdentity(Parameter parameter)
        {
            var candidate = new
            {
                name = parameter.Definition?.Name,
                builtIn = TryBuiltInName(parameter),
                guid = TryGuid(parameter)
            };
            return new ParameterIdentity(
                new ParameterIdentityKey(candidate.name, candidate.builtIn, candidate.guid),
                candidate);
        }

        private static string? TryBuiltInName(Parameter parameter)
        {
            var builtIn = (parameter.Definition as InternalDefinition)?.BuiltInParameter;
            return builtIn.HasValue ? builtIn.Value.ToString() : null;
        }

        private static string? TryGuid(Parameter parameter)
        {
            try
            {
                var guid = parameter.GUID;
                return guid == Guid.Empty ? null : guid.ToString("D");
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static string NormalizedDisplayValue(Parameter parameter)
        {
            return Normalize(parameter.AsValueString() ?? parameter.AsString());
        }

        private static string Normalize(string? value)
        {
            return value?.Trim() ?? string.Empty;
        }

        private static bool TryResolvedCategoryFilter(
            BimCategoryResolution resolution,
            out ElementCategoryFilter filter)
        {
            filter = null!;
            var id = resolution.Category?.Id;
            if (!id.HasValue)
            {
                return false;
            }

            try
            {
                filter = new ElementCategoryFilter(new ElementId((long)id.Value));
                return true;
            }
            catch (Autodesk.Revit.Exceptions.ArgumentException)
            {
                return false;
            }
            catch (ArgumentException)
            {
                return false;
            }
        }

        private static void IncrementMissingCount(Dictionary<string, int> missingCounts, string? parameter)
        {
            var key = string.IsNullOrWhiteSpace(parameter) ? "<unknown>" : parameter!.Trim();
            missingCounts.TryGetValue(key, out var count);
            missingCounts[key] = count + 1;
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null)
            {
                return null;
            }

            var value = id.Value;
            if (value < int.MinValue || value > int.MaxValue)
            {
                return null;
            }

            return (int)value;
        }

        private readonly struct ParameterIdentityKey : IEquatable<ParameterIdentityKey>
        {
            public ParameterIdentityKey(string? name, string? builtIn, string? guid)
            {
                Name = name;
                BuiltIn = builtIn;
                Guid = guid;
            }

            public string? Name { get; }

            public string? BuiltIn { get; }

            public string? Guid { get; }

            public bool Equals(ParameterIdentityKey other)
            {
                return string.Equals(Name, other.Name, StringComparison.OrdinalIgnoreCase) &&
                    string.Equals(BuiltIn, other.BuiltIn, StringComparison.OrdinalIgnoreCase) &&
                    string.Equals(Guid, other.Guid, StringComparison.OrdinalIgnoreCase);
            }

            public override bool Equals(object? obj)
            {
                return obj is ParameterIdentityKey other && Equals(other);
            }

            public override int GetHashCode()
            {
                unchecked
                {
                    var hash = StringComparer.OrdinalIgnoreCase.GetHashCode(Name ?? string.Empty);
                    hash = (hash * 397) ^ StringComparer.OrdinalIgnoreCase.GetHashCode(BuiltIn ?? string.Empty);
                    hash = (hash * 397) ^ StringComparer.OrdinalIgnoreCase.GetHashCode(Guid ?? string.Empty);
                    return hash;
                }
            }
        }

        private readonly struct ParameterIdentity
        {
            public ParameterIdentity(ParameterIdentityKey key, object candidate)
            {
                Key = key;
                Candidate = candidate;
            }

            public ParameterIdentityKey Key { get; }

            public object Candidate { get; }
        }

        private readonly struct CappedElementCollection
        {
            public CappedElementCollection(IReadOnlyCollection<Element> elements, bool truncated)
            {
                Elements = elements;
                Truncated = truncated;
            }

            public IReadOnlyCollection<Element> Elements { get; }

            public bool Truncated { get; }
        }
    }
}
