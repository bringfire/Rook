using System;
using System.Collections.Generic;

namespace Rook.Bim
{
    public enum BimErrorCode
    {
        None,
        RookBimUnavailable,
        NotRhinoInside,
        RevitUnavailable,
        NoActiveDocument,
        NoActiveView,
        InvalidScope,
        UnboundedDocumentQuery,
        InvalidCategory,
        AmbiguousCategory,
        CategoryNotQueryable,
        AmbiguousParameter,
        QueryLimitExceeded,
        ElementNotFound,
        DocumentMismatch,
        LinkedElementUnsupported,
        CapabilityUnavailable,
        SelectionFailed,
        QueryTruncated,
        OutputPathInvalid,
        NoExportableGeometry,
        ExportFailed,
        UnknownPreset,
        NoCategoriesResolved,
        InternalError
    }

    public enum BimDocumentGuidSource
    {
        RevitPersistentGuid,
        PathFallback,
        Unavailable
    }

    public enum BimIdentityConfidence
    {
        Exact,
        Inferred,
        Unresolved,
        Unsupported
    }

    public enum BimQueryScope
    {
        ActiveView,
        Document
    }

    public enum BimFilterOperation
    {
        Equals,
        NotEquals,
        Contains,
        IsEmpty,
        IsNotEmpty
    }

    public enum BimCategoryResolutionStatus
    {
        Resolved,
        Invalid,
        Ambiguous
    }

    public enum BimCategoryResolutionStrategy
    {
        None,
        BuiltInExact,
        CategoryIdExact,
        DocumentDisplayNameExact,
        DocumentDisplayNameNormalized,
        BuiltInTolerant,
        CuratedAlias
    }

    public sealed class BimValidationResult
    {
        public bool Success { get; set; }

        public BimErrorCode ErrorCode { get; set; }

        public string? Message { get; set; }

        public static BimValidationResult Ok
        {
            get
            {
                return new BimValidationResult
                {
                    Success = true,
                    ErrorCode = BimErrorCode.None
                };
            }
        }
    }

    public static class BimFilterSemantics
    {
        public static bool MissingParameterMatches(BimFilterOperation operation)
        {
            switch (operation)
            {
                case BimFilterOperation.NotEquals:
                case BimFilterOperation.IsEmpty:
                    return true;
                case BimFilterOperation.Equals:
                case BimFilterOperation.Contains:
                case BimFilterOperation.IsNotEmpty:
                default:
                    return false;
            }
        }
    }

    public sealed class BimApiResponse
    {
        public bool Success { get; set; }

        public BimErrorCode ErrorCode { get; set; }

        public string? Message { get; set; }

        public object? Data { get; set; }

        public int HttpStatus { get; set; } = 200;

        public static BimApiResponse Ok(object? data)
        {
            return new BimApiResponse
            {
                Success = true,
                ErrorCode = BimErrorCode.None,
                Data = data,
                HttpStatus = 200
            };
        }

        public static BimApiResponse Fail(
            BimErrorCode code,
            string message,
            int httpStatus)
        {
            return new BimApiResponse
            {
                Success = false,
                ErrorCode = code,
                Message = message,
                HttpStatus = httpStatus
            };
        }
    }

    public sealed class BimStatusResponse
    {
        public bool Available { get; set; }

        public string Runtime { get; set; } = "unavailable";

        public string? ErrorCode { get; set; }

        public string? Message { get; set; }

        public string Host { get; set; } = "unknown";

        public string Module { get; set; } = "core";
    }

    public sealed class BimDocumentIdentity
    {
        public string? Guid { get; set; }

        public BimDocumentGuidSource GuidSource { get; set; } = BimDocumentGuidSource.Unavailable;

        public string? Title { get; set; }

        public string? Path { get; set; }

        public bool IsFamilyDocument { get; set; }

        public bool IsWorkshared { get; set; }
    }

    public sealed class BimViewIdentity
    {
        public int Id { get; set; }

        public string? UniqueId { get; set; }

        public string? Name { get; set; }

        public string? Type { get; set; }
    }

    public sealed class BimElementIdentity
    {
        public string Source { get; set; } = "revit";

        public string? DocumentGuid { get; set; }

        public BimDocumentGuidSource DocumentGuidSource { get; set; } = BimDocumentGuidSource.Unavailable;

        public string? DocumentTitle { get; set; }

        public string? DocumentPath { get; set; }

        public int? ElementId { get; set; }

        public string? UniqueId { get; set; }

        public string? FullUniqueId { get; set; }

        public bool Linked { get; set; }

        public int? LinkInstanceId { get; set; }

        public string? LinkInstanceUniqueId { get; set; }

        public string? LinkedDocumentGuid { get; set; }

        public int? LinkedElementId { get; set; }

        public string? LinkedElementUniqueId { get; set; }

        public bool Resolved { get; set; }

        public BimIdentityConfidence Confidence { get; set; } = BimIdentityConfidence.Unresolved;
    }

    public sealed class BimCategoryParentSummary
    {
        public int? Id { get; set; }

        public string? Name { get; set; }

        public string? BuiltIn { get; set; }
    }

    public sealed class BimCategorySummary
    {
        public int? Id { get; set; }

        public string? Name { get; set; }

        public string? BuiltIn { get; set; }

        public string? CategoryType { get; set; }

        public BimCategoryParentSummary? Parent { get; set; }
    }

    public sealed class BimCategorySuggestion
    {
        public int? Id { get; set; }

        public string? Name { get; set; }

        public string? BuiltIn { get; set; }

        public string Source { get; set; } = "live_document";

        public string? MatchReason { get; set; }
    }

    public sealed class BimCategoryResolution
    {
        public int SchemaVersion { get; set; } = 1;

        public BimCategoryResolutionStatus Status { get; set; } = BimCategoryResolutionStatus.Invalid;

        public string? Input { get; set; }

        public string? NormalizedInput { get; set; }

        public List<BimCategoryResolutionStrategy> AttemptedStrategies { get; set; } = new List<BimCategoryResolutionStrategy>();

        public BimCategoryResolutionStrategy Strategy { get; set; } = BimCategoryResolutionStrategy.None;

        public bool Ambiguous { get; set; }

        public bool? Queryable { get; set; }

        public BimCategorySummary? Category { get; set; }

        public BimDocumentIdentity? Document { get; set; }

        public List<BimCategorySummary> Candidates { get; set; } = new List<BimCategorySummary>();

        public List<BimCategorySuggestion> Suggestions { get; set; } = new List<BimCategorySuggestion>();

        public List<string> AdvisorySources { get; set; } = new List<string>();
    }

    public sealed class BimListCategoriesResult
    {
        public int SchemaVersion { get; set; } = 1;

        public string Source { get; set; } = "document_category_table";

        public BimDocumentIdentity Document { get; set; } = new BimDocumentIdentity();

        public int SkippedCount { get; set; }

        public int DegradedCount { get; set; }

        public BimCategoryTableDiagnostics Diagnostics { get; set; } = new BimCategoryTableDiagnostics();

        public List<BimCategorySummary> Categories { get; set; } = new List<BimCategorySummary>();
    }

    public sealed class BimCategoryTableDiagnostics
    {
        public Dictionary<string, int> CountsByReason { get; set; } = new Dictionary<string, int>();

        public List<string> Examples { get; set; } = new List<string>();
    }

    public sealed class BimElementTypeSummary
    {
        public int? Id { get; set; }

        public string? UniqueId { get; set; }

        public string? FamilyName { get; set; }

        public string? Name { get; set; }
    }

    public sealed class BimElementSummary
    {
        public BimElementIdentity Identity { get; set; } = new BimElementIdentity();

        public string? Name { get; set; }

        public BimCategorySummary Category { get; set; } = new BimCategorySummary();

        public BimElementTypeSummary Type { get; set; } = new BimElementTypeSummary();
    }

    public sealed class BimQuerySummary
    {
        public string? Category { get; set; }

        public int Limit { get; set; }

        public int Returned { get; set; }

        public bool Truncated { get; set; }

        public BimCategoryResolution? CategoryResolution { get; set; }

        public List<BimQueryFilterSummary> Filters { get; set; } = new List<BimQueryFilterSummary>();

        public Dictionary<string, int> MissingParameterCounts { get; set; } = new Dictionary<string, int>();
    }

    public sealed class BimQueryFilterSummary
    {
        public string? Parameter { get; set; }

        public BimFilterOperation Operation { get; set; }

        public string? Value { get; set; }
    }

    public sealed class BimQueryElementsResult
    {
        public BimDocumentIdentity Document { get; set; } = new BimDocumentIdentity();

        public BimQueryScope Scope { get; set; } = BimQueryScope.ActiveView;

        public BimViewIdentity? View { get; set; }

        public BimQuerySummary Query { get; set; } = new BimQuerySummary();

        public List<BimElementSummary> Elements { get; set; } = new List<BimElementSummary>();
    }

    public sealed class BimQueryFilter
    {
        public string? Parameter { get; set; }

        public BimFilterOperation Operation { get; set; }

        public string? Value { get; set; }
    }

    public sealed class BimQueryElementsRequest
    {
        public const int DefaultLimit = 100;

        public const int HardMaxLimit = 1000;

        public BimQueryScope? Scope { get; set; }

        public string? Category { get; set; }

        public int? Limit { get; set; }

        public List<BimQueryFilter> Filters { get; set; } = new List<BimQueryFilter>();

        public BimQueryScope EffectiveScope
        {
            get { return Scope ?? BimQueryScope.ActiveView; }
        }

        public int EffectiveLimit
        {
            get { return Limit ?? DefaultLimit; }
        }

        public IReadOnlyList<BimQueryFilter> EffectiveFilters
        {
            get
            {
                if (Filters == null)
                {
                    return Array.Empty<BimQueryFilter>();
                }

                return Filters;
            }
        }

        public BimValidationResult Validate()
        {
            if (EffectiveLimit < 1 || EffectiveLimit > HardMaxLimit)
            {
                return Fail(
                    BimErrorCode.QueryLimitExceeded,
                    "limit must be between 1 and 1000");
            }

            if (Scope.HasValue && !Enum.IsDefined(typeof(BimQueryScope), Scope.Value))
            {
                return Fail(
                    BimErrorCode.InvalidScope,
                    "scope is invalid");
            }

            if (EffectiveScope == BimQueryScope.Document && string.IsNullOrWhiteSpace(Category))
            {
                return Fail(
                    BimErrorCode.UnboundedDocumentQuery,
                    "document scope requires category in Phase 1");
            }

            foreach (var filter in EffectiveFilters)
            {
                if (filter == null)
                {
                    return Fail(
                        BimErrorCode.InvalidScope,
                        "filter is required");
                }

                if (!Enum.IsDefined(typeof(BimFilterOperation), filter.Operation))
                {
                    return Fail(
                        BimErrorCode.InvalidScope,
                        "invalid filter operation");
                }

                if (string.IsNullOrWhiteSpace(filter.Parameter))
                {
                    return Fail(
                        BimErrorCode.InvalidScope,
                        "filter parameter is required");
                }
            }

            return BimValidationResult.Ok;
        }

        private static BimValidationResult Fail(BimErrorCode code, string message)
        {
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = code,
                Message = message
            };
        }
    }

    public sealed class BimElementRequest
    {
        public BimElementIdentity Identity { get; set; } = new BimElementIdentity();
    }

    public sealed class BimSelectElementsRequest
    {
        public List<BimElementIdentity> Identities { get; set; } = new List<BimElementIdentity>();
    }

    public enum BimRoomsMode
    {
        Both,
        LabelsOnly,
        Exclude
    }

    public sealed class BimExportOutput
    {
        public string? Directory { get; set; }

        public string? Name { get; set; }

        public string Units { get; set; } = "meters";

        public bool Overwrite { get; set; }
    }

    public sealed class BimExportElementsRequest
    {
        public BimQueryElementsRequest? Selector { get; set; }

        public List<BimElementIdentity>? Identities { get; set; }

        public BimExportOutput Output { get; set; } = new BimExportOutput();

        public BimRoomsMode? Rooms { get; set; }

        public bool AllowTruncated { get; set; }

        public bool AllowBboxProxy { get; set; }

        public BimRoomsMode EffectiveRooms
        {
            get { return Rooms ?? BimRoomsMode.Both; }
        }

        public bool HasSelector
        {
            get { return Selector != null; }
        }

        public bool HasIdentities
        {
            get { return Identities != null && Identities.Count > 0; }
        }

        public BimValidationResult Validate()
        {
            if (HasSelector == HasIdentities)
            {
                return Fail(
                    BimErrorCode.InvalidScope,
                    "export-elements requires exactly one of 'selector' or 'identities'.");
            }

            if (HasSelector)
            {
                var selectorValidation = Selector!.Validate();
                if (!selectorValidation.Success)
                {
                    return selectorValidation;
                }
            }

            var outputValidation = BimExportPathPolicy.ValidateRequestShape(Output);
            if (!outputValidation.Success)
            {
                return outputValidation;
            }

            return BimValidationResult.Ok;
        }

        private static BimValidationResult Fail(BimErrorCode code, string message)
        {
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = code,
                Message = message
            };
        }
    }

    public sealed class BimExportArtifactPaths
    {
        public string Model3dm { get; set; } = string.Empty;

        public string Sidecar { get; set; } = string.Empty;

        public string Validation { get; set; } = string.Empty;
    }

    public sealed class BimExportCounts
    {
        public int Requested { get; set; }

        public int Resolved { get; set; }

        public int ExportedBrep { get; set; }

        public int ExportedMesh { get; set; }

        public int ExportedBboxProxy { get; set; }

        public int Failed { get; set; }

        public int Rooms { get; set; }

        public bool Truncated { get; set; }
    }

    public sealed class BimExportVerification
    {
        public bool Ok { get; set; }

        public List<string> Discrepancies { get; set; } = new List<string>();
    }

    public sealed class BimExportResult
    {
        public int SchemaVersion { get; set; } = 1;

        public BimExportArtifactPaths Paths { get; set; } = new BimExportArtifactPaths();

        public BimExportCounts Counts { get; set; } = new BimExportCounts();

        public BimExportVerification Verification { get; set; } = new BimExportVerification();

        public string SourceUnits { get; set; } = "feet";

        public string TargetUnits { get; set; } = "meters";

        public double UnitScaleFactor { get; set; } = 1.0;
    }

    public sealed class BimExportPresetRequest
    {
        public string? Preset { get; set; }

        public BimExportOutput Output { get; set; } = new BimExportOutput();

        public string? Scope { get; set; }

        public List<string>? IncludeCategories { get; set; }

        public List<string>? ExcludeCategories { get; set; }

        public string? LayerPolicy { get; set; }

        public string? NamePolicy { get; set; }

        public string? MetadataProfile { get; set; }

        public string? Rooms { get; set; }

        public int? LimitPerCategory { get; set; }

        public bool AllowTruncated { get; set; }

        public bool AllowBboxProxy { get; set; }

        public BimQueryScope EffectiveScope
        {
            get
            {
                return string.Equals(Scope, "document", StringComparison.OrdinalIgnoreCase)
                    ? BimQueryScope.Document
                    : BimQueryScope.ActiveView;
            }
        }

        public BimValidationResult Validate()
        {
            if (string.IsNullOrWhiteSpace(Preset))
            {
                return Fail(BimErrorCode.UnknownPreset, "export-preset requires a 'preset' name.");
            }

            if (!string.IsNullOrWhiteSpace(Scope) &&
                !string.Equals(Scope, "active_view", StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(Scope, "document", StringComparison.OrdinalIgnoreCase))
            {
                return Fail(BimErrorCode.InvalidScope, "scope must be 'active_view' or 'document'.");
            }

            var outputValidation = BimExportPathPolicy.ValidateRequestShape(Output);
            if (!outputValidation.Success)
            {
                return outputValidation;
            }

            return BimValidationResult.Ok;
        }

        private static BimValidationResult Fail(BimErrorCode code, string message)
        {
            return new BimValidationResult { Success = false, ErrorCode = code, Message = message };
        }
    }
}
